"""
Live Trading AI Evaluation Service

Compares live trading performance with backtest results using current strategy config.
Provides AI-powered analysis and recommendations using Claude CLI agent.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text
from .config import DEFAULT_INITIAL_CAPITAL

logger = logging.getLogger(__name__)

# Claude CLI model priority: try best model first, fallback on rate limit
MODEL_PRIORITY = ["sonnet", "haiku"]


class LiveAIEvaluationService:
    """Service for AI-powered live trading evaluation using Claude CLI agent."""

    def __init__(self, db: Session, user_id: Optional[int] = None, **kwargs):
        self.db = db
        self.user_id = user_id

    def collect_live_stats(
        self,
        session_id: str,
        symbol: str,
        n_cycles: int = 10,
        is_paper: bool = False
    ) -> Dict[str, Any]:
        """
        Collect stats from recent N cycles of live trading.

        Args:
            session_id: Live session ID
            symbol: Trading symbol
            n_cycles: Number of recent cycles to analyze
            is_paper: True for paper trades, False for real trades

        Returns:
            Dict with live trading statistics matching BacktestStats format
        """
        from ..models.live_trading import LiveTradeExecution, ExecutionStatus
        from sqlalchemy import func

        # Get filled executions for this session, filtered by mode
        executions = self.db.query(LiveTradeExecution).filter(
            LiveTradeExecution.session_id == session_id,
            LiveTradeExecution.symbol == symbol,
            LiveTradeExecution.status == ExecutionStatus.FILLED,
            LiveTradeExecution.is_paper == is_paper
        ).order_by(LiveTradeExecution.signal_timestamp.asc()).all()

        if not executions:
            # Check what executions exist for better error message
            mode_counts = self.db.query(
                LiveTradeExecution.is_paper,
                func.count(LiveTradeExecution.id)
            ).filter(
                LiveTradeExecution.session_id == session_id,
                LiveTradeExecution.symbol == symbol,
                LiveTradeExecution.status == ExecutionStatus.FILLED
            ).group_by(LiveTradeExecution.is_paper).all()

            mode_info = {row[0]: row[1] for row in mode_counts}
            paper_count = mode_info.get(True, 0)
            real_count = mode_info.get(False, 0)

            requested_mode = "Paper" if is_paper else "Real"
            if paper_count == 0 and real_count == 0:
                error_msg = "체결된 거래가 없습니다. 거래 실행 후 다시 시도해주세요."
            else:
                available = []
                if paper_count > 0:
                    available.append(f"Paper: {paper_count}건")
                if real_count > 0:
                    available.append(f"Real: {real_count}건")
                error_msg = f"{requested_mode} 모드에 체결된 거래가 없습니다. 사용 가능: {', '.join(available)}"

            return {"error": error_msg, "cycles_analyzed": 0}

        # FIFO matching to identify cycles
        buy_queue = []
        cycles = []

        for ex in executions:
            qty = ex.filled_quantity or 0
            price = ex.executed_price or 0

            if ex.signal_type == "BUY":
                buy_queue.append({
                    "qty": qty,
                    "price": price,
                    "timestamp": ex.signal_timestamp,
                    "order_no": ex.exchange_order_no
                })
            elif ex.signal_type == "SELL" and buy_queue:
                sell_qty = qty
                sell_value = qty * price
                buy_cost = 0.0
                matched_qty = 0.0
                first_buy_time = buy_queue[0]["timestamp"] if buy_queue else None

                while sell_qty > 0 and buy_queue:
                    buy = buy_queue[0]
                    match_qty = min(sell_qty, buy["qty"])
                    buy_cost += match_qty * buy["price"]
                    matched_qty += match_qty
                    sell_qty -= match_qty
                    buy["qty"] -= match_qty
                    if buy["qty"] <= 0:
                        buy_queue.pop(0)

                if matched_qty > 0:
                    cycle_pnl = (price * matched_qty) - buy_cost
                    cycle_pnl_pct = (cycle_pnl / buy_cost * 100) if buy_cost > 0 else 0
                    duration_mins = (ex.signal_timestamp - first_buy_time).total_seconds() / 60 if first_buy_time else 0

                    cycles.append({
                        "pnl": cycle_pnl,
                        "pnl_pct": cycle_pnl_pct,
                        "entry_cost": buy_cost,
                        "exit_value": price * matched_qty,
                        "duration_mins": duration_mins,
                        "start_time": first_buy_time,
                        "end_time": ex.signal_timestamp,
                    })

        if not cycles:
            return {"error": "No completed cycles found", "cycles_analyzed": 0}

        # Take only the last N cycles
        recent_cycles = cycles[-n_cycles:] if n_cycles > 0 else cycles
        cycles_analyzed = len(recent_cycles)

        # Calculate statistics
        import statistics as stat_module

        cycle_pnls = [c["pnl"] for c in recent_cycles]
        cycle_pnl_pcts = [c["pnl_pct"] for c in recent_cycles]
        cycle_durations = [c["duration_mins"] for c in recent_cycles]

        total_pnl = sum(cycle_pnls)
        total_entry_cost = sum(c["entry_cost"] for c in recent_cycles)
        wins = sum(1 for p in cycle_pnls if p > 0)
        win_rate = (wins / cycles_analyzed) * 100

        # Total return
        total_return = (total_pnl / total_entry_cost * 100) if total_entry_cost > 0 else 0

        # Profit Factor
        gross_profit = sum(p for p in cycle_pnls if p > 0)
        gross_loss = abs(sum(p for p in cycle_pnls if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99

        # Sharpe Ratio
        if len(cycle_pnl_pcts) > 1:
            pct_stdev = stat_module.stdev(cycle_pnl_pcts)
            sharpe_ratio = (stat_module.mean(cycle_pnl_pcts) / pct_stdev * (len(cycle_pnl_pcts) ** 0.5)) if pct_stdev > 0 else 0
        else:
            sharpe_ratio = 0

        # Max Drawdown (from cumulative PnL)
        cumulative = 0
        peak = 0
        max_drawdown = 0
        for pnl in cycle_pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            drawdown = peak - cumulative
            dd_pct = (drawdown / peak * 100) if peak > 0 else 0
            if dd_pct > max_drawdown:
                max_drawdown = dd_pct

        # Holding time stats
        avg_holding_time = sum(cycle_durations) / len(cycle_durations) if cycle_durations else None
        max_holding_time = max(cycle_durations) if cycle_durations else None
        min_holding_time = min(cycle_durations) if cycle_durations else None

        # Recent 10 win rate
        recent_10 = cycle_pnls[-10:] if len(cycle_pnls) >= 10 else cycle_pnls
        recent_10_wins = sum(1 for p in recent_10 if p > 0)
        recent_10_win_rate = (recent_10_wins / len(recent_10)) * 100 if recent_10 else 0

        # Analysis window
        analysis_start = recent_cycles[0]["start_time"] if recent_cycles else None
        analysis_end = recent_cycles[-1]["end_time"] if recent_cycles else None

        return {
            "cycles_analyzed": cycles_analyzed,
            "analysis_start_time": analysis_start.isoformat() if analysis_start else None,
            "analysis_end_time": analysis_end.isoformat() if analysis_end else None,

            # BacktestStats compatible fields
            "total_return": round(total_return, 2),
            "win_rate": round(win_rate, 1),
            "recent_10_win_rate": round(recent_10_win_rate, 1),
            "total_cycles": cycles_analyzed,
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown": round(max_drawdown, 2),
            "avg_pnl": round(sum(cycle_pnl_pcts) / cycles_analyzed, 2) if cycles_analyzed > 0 else 0,
            "max_profit": round(max(cycle_pnl_pcts), 2) if cycle_pnl_pcts else 0,
            "max_loss": round(min(cycle_pnl_pcts), 2) if cycle_pnl_pcts else 0,
            "avg_holding_time": round(avg_holding_time) if avg_holding_time else None,
            "max_holding_time": round(max_holding_time) if max_holding_time else None,
            "min_holding_time": round(min_holding_time) if min_holding_time else None,

            # Live-only fields (KRW)
            "realized_pnl_krw": round(total_pnl, 0),
            "avg_pnl_krw": round(total_pnl / cycles_analyzed, 0) if cycles_analyzed > 0 else 0,
        }

    async def run_backtest_for_comparison(
        self,
        symbol: str,
        strategy_name: str,
        strategy_config: Dict[str, Any],
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Run backtest with current strategy config for comparison.

        Returns:
            Dict with backtest statistics matching BacktestStats format
        """
        from ..core.waterfall_engine import WaterfallBacktestEngine
        from ..core.strategy_registry import StrategyRegistry
        from ..services.market_data import MarketDataService

        try:
            logger.info(f"Running backtest comparison: {symbol}, {strategy_name}, {days} days")

            # Get strategy class
            strategy_class = StrategyRegistry.get_strategy_class(strategy_name)
            if not strategy_class:
                logger.error(f"Strategy not found: {strategy_name}")
                return {"error": f"Strategy not found: {strategy_name}"}

            logger.info(f"Strategy class found: {strategy_class.__name__}")

            # Get market data
            data_service = MarketDataService()
            raw_feed = await data_service.get_candles(symbol, interval="1m", days=days)

            if not raw_feed:
                logger.error(f"No market data available for {symbol}")
                return {"error": f"No market data available for {symbol}"}

            raw_feed.sort(key=lambda x: x['timestamp'])
            logger.info(f"Loaded {len(raw_feed)} candles for backtest")

            # Build config for backtest
            initial_capital = strategy_config.get("initial_capital", DEFAULT_INITIAL_CAPITAL)

            # Handle both formats: {params: {...}} or direct params at top level
            params = strategy_config.get("params", {})
            if not params:
                # If no "params" key, use strategy_config directly (excluding known non-param keys)
                # Exclude UI/meta fields that are not actual strategy parameters
                exclude_keys = {
                    "initial_capital", "symbol", "params",
                    # UI/Meta fields
                    "from_date", "interval", "uuid", "tabName", "is_active",
                    "optEnabled", "optValues", "rank",
                    "selected_version_id", "selected_version_name", "execution_mode"
                }
                params = {k: v for k, v in strategy_config.items() if k not in exclude_keys}

            logger.info(f"Strategy params for backtest: {params}")

            config = {
                "symbol": symbol,
                "initial_capital": initial_capital,
                **params
            }

            # Run backtest
            engine = WaterfallBacktestEngine(strategy_class, {})
            result = await engine.run_single_backtest(
                config=config,
                feed=raw_feed,
                initial_capital=initial_capital,
                symbol=symbol,
                optimize_mode=True,  # Skip chart data for speed
                rank=1
            )

            if not result:
                logger.error("Backtest returned no result")
                return {"error": "Backtest returned no result"}

            # Stats are at top level of result, not under 'stats' key
            logger.info(f"Backtest completed. total_cycles={result.get('total_cycles')}, total_return={result.get('total_return')}")

            return {
                "total_return": result.get("total_return", 0),
                "win_rate": result.get("win_rate", 0),
                "recent_10_win_rate": result.get("recent_10_win_rate"),
                "total_cycles": result.get("total_cycles", 0),
                "profit_factor": result.get("profit_factor", 0),
                "sharpe_ratio": result.get("sharpe_ratio", 0),
                "max_drawdown": result.get("max_drawdown", 0),
                "avg_pnl": result.get("avg_pnl", 0),
                "max_profit": result.get("max_profit", 0),
                "max_loss": result.get("max_loss", 0),
                "avg_holding_time": result.get("avg_holding_time"),
                "max_holding_time": result.get("max_holding_time"),
                "min_holding_time": result.get("min_holding_time"),
                "stability_score": result.get("stability_score", 0),
                "acceleration_score": result.get("acceleration_score", 0),
                "activity_rate": result.get("activity_rate", 0),
                "total_days": result.get("total_days", 0),
            }

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return {"error": str(e)}

    def compute_comparison(
        self,
        live_stats: Dict[str, Any],
        backtest_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute differences between live and backtest stats.
        """
        if "error" in live_stats or "error" in backtest_stats:
            return {"error": "Cannot compare: missing data"}

        def safe_diff(live_val, bt_val):
            if live_val is None or bt_val is None:
                return None
            return round(live_val - bt_val, 2)

        def safe_ratio(live_val, bt_val):
            if live_val is None or bt_val is None or bt_val == 0:
                return None
            return round(live_val / bt_val, 2)

        return {
            "return_diff": safe_diff(live_stats.get("total_return"), backtest_stats.get("total_return")),
            "win_rate_diff": safe_diff(live_stats.get("win_rate"), backtest_stats.get("win_rate")),
            "sharpe_diff": safe_diff(live_stats.get("sharpe_ratio"), backtest_stats.get("sharpe_ratio")),
            "drawdown_diff": safe_diff(live_stats.get("max_drawdown"), backtest_stats.get("max_drawdown")),
            "avg_pnl_diff": safe_diff(live_stats.get("avg_pnl"), backtest_stats.get("avg_pnl")),
            "profit_factor_diff": safe_diff(live_stats.get("profit_factor"), backtest_stats.get("profit_factor")),

            # Ratios (live / backtest)
            "return_ratio": safe_ratio(live_stats.get("total_return"), backtest_stats.get("total_return")),
            "win_rate_ratio": safe_ratio(live_stats.get("win_rate"), backtest_stats.get("win_rate")),

            # Performance grade
            "overall_grade": self._calculate_grade(live_stats, backtest_stats),
        }

    def _calculate_grade(self, live_stats: Dict, backtest_stats: Dict) -> str:
        """Calculate overall performance grade based on live vs backtest comparison."""
        try:
            live_return = live_stats.get("total_return", 0)
            bt_return = backtest_stats.get("total_return", 0)
            live_wr = live_stats.get("win_rate", 0)
            bt_wr = backtest_stats.get("win_rate", 0)

            # Compare return
            if bt_return > 0:
                return_ratio = live_return / bt_return
            else:
                return_ratio = 1.0 if live_return >= 0 else 0.5

            # Compare win rate
            if bt_wr > 0:
                wr_ratio = live_wr / bt_wr
            else:
                wr_ratio = 1.0 if live_wr >= 50 else 0.5

            # Combined score
            score = (return_ratio * 0.6 + wr_ratio * 0.4)

            if score >= 1.1:
                return "A"  # Exceeds backtest
            elif score >= 0.9:
                return "B"  # Matches backtest
            elif score >= 0.7:
                return "C"  # Below backtest
            elif score >= 0.5:
                return "D"  # Significantly below
            else:
                return "F"  # Poor performance
        except:
            return "N/A"

    def _build_evaluation_context(
        self,
        symbol: str,
        strategy_name: str,
        strategy_config: Dict[str, Any],
        live_stats: Dict[str, Any],
        backtest_stats: Dict[str, Any],
        comparison: Dict[str, Any],
        is_paper: bool = False
    ) -> Dict[str, Any]:
        """Build context data dict for Claude CLI evaluation."""

        # Handle both formats: {params: {...}} or direct params at top level
        params = strategy_config.get("params", {})
        if not params:
            exclude_keys = {
                "initial_capital", "symbol", "params",
                "from_date", "interval", "uuid", "tabName", "is_active",
                "optEnabled", "optValues", "rank",
                "selected_version_id", "selected_version_name", "execution_mode"
            }
            params = {k: v for k, v in strategy_config.items() if k not in exclude_keys}

        return {
            "session_info": {
                "symbol": symbol,
                "strategy_name": strategy_name,
                "is_paper": is_paper,
                "mode_label": "Paper (모의)" if is_paper else "Real (실거래)",
                "cycles_analyzed": live_stats.get("cycles_analyzed", 0),
            },
            "strategy_params": params,
            "live_stats": live_stats,
            "backtest_stats": backtest_stats,
            "comparison": comparison,
        }

    async def _call_claude_cli(self, context_data: Dict, symbol: str, strategy_name: str) -> Dict[str, Any]:
        """Call Claude CLI for AI evaluation. Falls back to lower model on rate limit."""
        from .config import get_claude_cli_path
        try:
            claude_path = get_claude_cli_path()
        except FileNotFoundError:
            return {"error": "Claude CLI not found"}

        tmp_file = None
        try:
            tmp_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', prefix='eval_ctx_',
                dir='/tmp', delete=False
            )
            json.dump(context_data, tmp_file, ensure_ascii=False, indent=2)
            tmp_file.close()

            prompt = (
                f"Read the context file at {tmp_file.name} and evaluate the live trading session.\n"
                f"Stock: {symbol} ({strategy_name})\n"
                f"Compare live trading stats with backtest results.\n"
                f"Respond with valid JSON only containing these fields:\n"
                f"- summary: 종합 평가 (2-3문장, 한국어)\n"
                f"- performance_analysis: 성과 분석 (라이브 vs 백테스트 비교)\n"
                f"- risk_factors: 위험 요소 (1-2문장)\n"
                f"- recommendations: 개선 제안 배열 (구체적 파라미터 조정 포함)\n"
                f"- grade: 성과 등급 (A/B/C/D/F)\n"
                f"- action: 권고 (유지/조정/중단)\n"
                f"- risk_level: 위험도 (low/medium/high)\n"
                f"응답은 한국어로, JSON만 출력하세요."
            )

            # Clean PM2 env vars
            env = os.environ.copy()
            for key in ["NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_APP_INSTANCE"]:
                env.pop(key, None)

            last_error = None
            for model in MODEL_PRIORITY:
                cmd = [
                    claude_path,
                    "-p", prompt,
                    "--output-format", "json",
                    "--model", model,
                    "--permission-mode", "bypassPermissions",
                ]

                logger.info(f"Calling Claude CLI with model={model} for evaluation of {symbol}")

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                    env=env,
                    start_new_session=True,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                except asyncio.TimeoutError:
                    proc.kill()
                    last_error = f"Claude CLI timed out (300s) with model={model}"
                    logger.warning(last_error)
                    continue

                err_msg = stderr.decode().strip() if stderr else ""

                if proc.returncode != 0:
                    if any(kw in err_msg.lower() for kw in ["rate limit", "overloaded", "529", "quota"]):
                        logger.warning(f"Model {model} rate limited, falling back to next model")
                        last_error = f"Model {model} rate limited: {err_msg[:200]}"
                        continue
                    last_error = f"Claude CLI error (model={model}): {err_msg[:300]}"
                    logger.warning(last_error)
                    continue

                raw = stdout.decode().strip()
                if not raw:
                    last_error = f"Empty response from Claude CLI (model={model})"
                    logger.warning(last_error)
                    continue

                # Parse Claude CLI JSON output (has result field)
                cli_output = json.loads(raw)
                result_text = cli_output.get("result", "")
                logger.info(f"Evaluation completed with model={model} for {symbol}")

                result = self._extract_json_from_response(result_text)
                result["_model_used"] = f"claude-{model}"
                return result

            return {"error": last_error or "All Claude models failed"}

        except Exception as e:
            logger.error(f"Claude CLI call failed: {e}")
            return {"error": str(e)}
        finally:
            if tmp_file and os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)

    def _extract_json_from_response(self, text_input: str) -> Dict:
        """Extract JSON from Claude response, handling markdown code blocks."""
        result = None

        # Try direct JSON parse
        try:
            result = json.loads(text_input)
        except json.JSONDecodeError:
            pass

        if result is None:
            # Strip markdown code fences
            stripped = text_input.strip()
            if stripped.startswith("```"):
                stripped = re.sub(r'^```(?:json)?\s*\n?', '', stripped)
                stripped = re.sub(r'\n?```\s*$', '', stripped)
                try:
                    result = json.loads(stripped.strip())
                except json.JSONDecodeError:
                    pass

        if result is None:
            # Try all markdown code blocks
            for match in re.finditer(r'```(?:json)?\s*\n([\s\S]+?)\n```', text_input):
                try:
                    result = json.loads(match.group(1).strip())
                    break
                except json.JSONDecodeError:
                    continue

        if result is None:
            # Try finding JSON object between first { and last }
            brace_start = text_input.find('{')
            brace_end = text_input.rfind('}')
            if brace_start >= 0 and brace_end > brace_start:
                try:
                    result = json.loads(text_input[brace_start:brace_end + 1])
                except json.JSONDecodeError:
                    pass

        if result is None:
            logger.warning("Could not parse JSON from Claude response, using raw text")
            return {
                "summary": text_input[:500],
                "grade": "N/A",
                "recommendations": [],
                "action": "유지",
                "risk_level": "medium",
            }

        return result

    async def run_full_evaluation(
        self,
        session_id: str,
        symbol: str,
        strategy_name: str,
        strategy_config: Dict[str, Any],
        n_cycles: int = 10,
        backtest_days: int = 30,
        evaluation_type: str = "MANUAL",
        is_paper: bool = False
    ) -> Dict[str, Any]:
        """
        Run complete AI evaluation workflow using Claude CLI agent.

        Args:
            is_paper: True to analyze paper trades, False for real trades

        Returns:
            Dict with evaluation results for storage
        """
        from datetime import datetime

        # Step 1: Collect live stats (filtered by mode)
        live_stats = self.collect_live_stats(session_id, symbol, n_cycles, is_paper=is_paper)
        if "error" in live_stats:
            return {"status": "failed", "error": live_stats["error"]}

        # Step 2: Run backtest for comparison
        backtest_stats = await self.run_backtest_for_comparison(
            symbol, strategy_name, strategy_config, backtest_days
        )

        # Step 3: Compute comparison
        comparison = self.compute_comparison(live_stats, backtest_stats)

        # Step 4: Build context data for Claude CLI
        context_data = self._build_evaluation_context(
            symbol, strategy_name, strategy_config,
            live_stats, backtest_stats, comparison,
            is_paper=is_paper
        )

        # Step 5: Call Claude CLI agent
        ai_result = await self._call_claude_cli(context_data, symbol, strategy_name)
        model_used = ai_result.pop("_model_used", "claude-sonnet")

        # Step 6: Extract key findings from AI result
        has_error = "error" in ai_result
        key_findings = {}
        if not has_error:
            key_findings = {
                "performance_summary": ai_result.get("performance_analysis") or ai_result.get("summary"),
                "risk_factors": ai_result.get("risk_factors"),
                "recommendations": ai_result.get("recommendations"),
                "action": ai_result.get("action"),
            }

        # Build AI response text for storage
        ai_response_text = json.dumps(ai_result, ensure_ascii=False) if not has_error else None

        return {
            "status": "completed",
            "session_id": session_id,
            "symbol": symbol,
            "evaluation_type": evaluation_type,
            "is_paper": is_paper,
            "trigger_cycle_count": n_cycles,
            "cycles_analyzed": live_stats.get("cycles_analyzed", 0),
            "analysis_start_time": live_stats.get("analysis_start_time"),
            "analysis_end_time": live_stats.get("analysis_end_time"),
            "live_stats": live_stats,
            "backtest_stats": backtest_stats,
            "comparison_data": comparison,
            "strategy_config": strategy_config,
            "ai_model": model_used,
            "ai_prompt": json.dumps(context_data, ensure_ascii=False),
            "ai_response": ai_response_text,
            "key_findings": key_findings,
            "recommendations": ai_result.get("recommendations", []) if not has_error else [],
            "evaluation_score": self._grade_to_score(
                ai_result.get("grade") or comparison.get("overall_grade", "N/A")
            ),
            "error_message": ai_result.get("error") if has_error else None,
            "completed_at": datetime.utcnow().isoformat(),
        }

    def _grade_to_score(self, grade: str) -> Optional[float]:
        """Convert letter grade to numeric score."""
        grade_map = {"A": 90, "B": 80, "C": 70, "D": 60, "F": 40}
        return grade_map.get(grade)
