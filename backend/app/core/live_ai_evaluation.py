"""
Live Trading AI Evaluation Service

Compares live trading performance with backtest results using current strategy config.
Provides AI-powered analysis and recommendations.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import httpx

from sqlalchemy.orm import Session
from sqlalchemy import text
from .config import DEFAULT_INITIAL_CAPITAL

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.0-flash-001"


class LiveAIEvaluationService:
    """Service for AI-powered live trading evaluation."""

    def __init__(self, db: Session, user_id: Optional[int] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        self.db = db
        self.user_id = user_id

        # Try to get API key from: 1) explicit param, 2) database, 3) env vars
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL

        if not self.api_key and user_id:
            # Get from database
            self._load_api_key_from_db(user_id)

        if not self.api_key:
            # Fallback to env vars
            self.api_key = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            logger.warning("Google AI API key not set. AI evaluation will be disabled.")

    def _load_api_key_from_db(self, user_id: int):
        """Load Google API key from user record."""
        from ..models.user import User
        from ..core import security

        try:
            user = self.db.query(User).filter(User.id == user_id).first()

            if user and user.encrypted_google_api_key:
                self.api_key = security.decrypt_key(user.encrypted_google_api_key)
                if user.ai_model:
                    self.model = user.ai_model
                logger.info(f"Loaded Google API key from database for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to load API key from database: {e}")

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
            "total_trades": cycles_analyzed,
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
            logger.info(f"Backtest completed. total_trades={result.get('total_trades')}, total_return={result.get('total_return')}")

            return {
                "total_return": result.get("total_return", 0),
                "win_rate": result.get("win_rate", 0),
                "recent_10_win_rate": result.get("recent_10_win_rate"),
                "total_trades": result.get("total_trades", 0),
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

    def build_evaluation_prompt(
        self,
        symbol: str,
        strategy_name: str,
        strategy_config: Dict[str, Any],
        live_stats: Dict[str, Any],
        backtest_stats: Dict[str, Any],
        comparison: Dict[str, Any],
        is_paper: bool = False
    ) -> str:
        """Build prompt for AI evaluation."""

        # Handle both formats: {params: {...}} or direct params at top level
        params = strategy_config.get("params", {})
        if not params:
            # Exclude UI/meta fields that are not actual strategy parameters
            exclude_keys = {
                "initial_capital", "symbol", "params",
                "from_date", "interval", "uuid", "tabName", "is_active",
                "optEnabled", "optValues", "rank",
                "selected_version_id", "selected_version_name", "execution_mode"
            }
            params = {k: v for k, v in strategy_config.items() if k not in exclude_keys}

        mode_label = "Paper (모의)" if is_paper else "Real (실거래)"

        prompt = f"""# 라이브 트레이딩 성과 평가 요청

## 1. 세션 정보
- 종목: {symbol}
- 전략: {strategy_name}
- 거래 모드: **{mode_label}**
- 분석 사이클 수: {live_stats.get('cycles_analyzed', 0)}개

## 2. 전략 파라미터
```json
{json.dumps(params, indent=2, ensure_ascii=False)}
```

## 3. 라이브 트레이딩 실적
| 지표 | 라이브 | 백테스트 | 차이 |
|------|--------|----------|------|
| 총 수익률 | {live_stats.get('total_return', 0):.2f}% | {backtest_stats.get('total_return', 0):.2f}% | {comparison.get('return_diff', 'N/A')} |
| 승률 | {live_stats.get('win_rate', 0):.1f}% | {backtest_stats.get('win_rate', 0):.1f}% | {comparison.get('win_rate_diff', 'N/A')} |
| Sharpe Ratio | {live_stats.get('sharpe_ratio', 0):.2f} | {backtest_stats.get('sharpe_ratio', 0):.2f} | {comparison.get('sharpe_diff', 'N/A')} |
| Max Drawdown | {live_stats.get('max_drawdown', 0):.2f}% | {backtest_stats.get('max_drawdown', 0):.2f}% | {comparison.get('drawdown_diff', 'N/A')} |
| Profit Factor | {live_stats.get('profit_factor', 0):.2f} | {backtest_stats.get('profit_factor', 0):.2f} | {comparison.get('profit_factor_diff', 'N/A')} |
| 평균 수익률 | {live_stats.get('avg_pnl', 0):.2f}% | {backtest_stats.get('avg_pnl', 0):.2f}% | {comparison.get('avg_pnl_diff', 'N/A')} |

## 4. 추가 라이브 데이터
- 최근 10 사이클 승률: {live_stats.get('recent_10_win_rate', 'N/A')}%
- 평균 보유 시간: {live_stats.get('avg_holding_time', 'N/A')}분
- 최대/최소 수익률: {live_stats.get('max_profit', 'N/A')}% / {live_stats.get('max_loss', 'N/A')}%
- 실현 손익 (KRW): {live_stats.get('realized_pnl_krw', 0):,.0f}원

## 5. 성과 등급: {comparison.get('overall_grade', 'N/A')}

## 6. 평가 요청

당신은 자동매매 전략 분석 전문가입니다. 위 데이터를 분석하여 다음을 제공하세요:

### A. 성과 분석 (2-3문장)
- 라이브 성과가 백테스트 대비 어떤지 평가
- 주요 차이점과 그 원인 추정

### B. 위험 요소 (1-2문장)
- 현재 파라미터 또는 시장 상황에서의 위험 요소

### C. 개선 제안 (1-2문장)
- 성과 개선을 위한 구체적인 파라미터 조정 또는 전략 수정 제안

### D. 권고 등급 (한 단어)
- 유지 / 조정 / 중단 중 하나

**응답은 한국어로, 간결하게 작성해주세요.**
"""
        return prompt

    async def call_ai_api(self, prompt: str) -> Dict[str, Any]:
        """Call Google Gemini API for evaluation."""
        if not self.api_key:
            return {"error": "Google AI API key not configured"}

        url = f"{GEMINI_API_URL}/{self.model}:generateContent?key={self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    headers={"content-type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "maxOutputTokens": 8192,
                            "temperature": 0.5
                        }
                    }
                )

                if response.status_code != 200:
                    logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                    return {"error": f"Gemini API error: {response.status_code}"}

                result = response.json()

                try:
                    content = result["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError) as e:
                    logger.error(f"Failed to parse Gemini response: {e}")
                    return {"error": "Failed to parse Gemini response"}

                usage = {}
                if "usageMetadata" in result:
                    usage = {
                        "input_tokens": result["usageMetadata"].get("promptTokenCount", 0),
                        "output_tokens": result["usageMetadata"].get("candidatesTokenCount", 0)
                    }

                return {
                    "content": content,
                    "model": self.model,
                    "usage": usage
                }

        except Exception as e:
            logger.error(f"AI API call failed: {e}")
            return {"error": str(e)}

    def extract_key_findings(self, ai_response: str) -> Dict[str, Any]:
        """Extract structured findings from AI response text."""
        findings = {
            "performance_summary": None,
            "risk_factors": None,
            "recommendations": None,
            "action": None,  # 유지/조정/중단
        }

        try:
            lines = ai_response.split('\n')
            current_section = None

            for line in lines:
                line_lower = line.lower().strip()

                if '성과 분석' in line_lower or 'a.' in line_lower[:3]:
                    current_section = 'performance_summary'
                elif '위험' in line_lower or 'b.' in line_lower[:3]:
                    current_section = 'risk_factors'
                elif '개선' in line_lower or '제안' in line_lower or 'c.' in line_lower[:3]:
                    current_section = 'recommendations'
                elif '권고' in line_lower or '등급' in line_lower or 'd.' in line_lower[:3]:
                    current_section = 'action'
                elif current_section and line.strip():
                    # Clean markdown formatting
                    clean_line = line.strip().lstrip('-').lstrip('*').strip()
                    if clean_line:
                        if current_section == 'action':
                            # Extract action keyword
                            if '유지' in clean_line:
                                findings['action'] = '유지'
                            elif '조정' in clean_line:
                                findings['action'] = '조정'
                            elif '중단' in clean_line:
                                findings['action'] = '중단'
                        else:
                            if findings[current_section]:
                                findings[current_section] += ' ' + clean_line
                            else:
                                findings[current_section] = clean_line

        except Exception as e:
            logger.warning(f"Failed to extract findings: {e}")

        return findings

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
        Run complete AI evaluation workflow.

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

        # Step 4: Build AI prompt
        prompt = self.build_evaluation_prompt(
            symbol, strategy_name, strategy_config,
            live_stats, backtest_stats, comparison,
            is_paper=is_paper
        )

        # Step 5: Call AI API
        ai_result = await self.call_ai_api(prompt)

        # Step 6: Extract key findings
        if "error" not in ai_result:
            key_findings = self.extract_key_findings(ai_result.get("content", ""))
        else:
            key_findings = {}

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
            "ai_model": ai_result.get("model"),
            "ai_prompt": prompt,
            "ai_response": ai_result.get("content") if "error" not in ai_result else None,
            "key_findings": key_findings,
            "recommendations": [key_findings.get("recommendations")] if key_findings.get("recommendations") else [],
            "evaluation_score": self._grade_to_score(comparison.get("overall_grade", "N/A")),
            "error_message": ai_result.get("error"),
            "completed_at": datetime.utcnow().isoformat(),
        }

    def _grade_to_score(self, grade: str) -> Optional[float]:
        """Convert letter grade to numeric score."""
        grade_map = {"A": 90, "B": 80, "C": 70, "D": 60, "F": 40}
        return grade_map.get(grade)
