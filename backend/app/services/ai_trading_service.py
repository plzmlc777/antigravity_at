"""
AI Trading Service - Orchestrator for autonomous AI-driven trading.

Flow:
1. User starts AI trading → initial decision pipeline
2. Pipeline: stock selection (Claude CLI) → optimization (BacktestEngine) → final decision (Claude CLI)
3. Session transition: stop old → start new with AI's chosen symbol + params
"""
import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime
from itertools import product
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..db.session import SessionLocal
from ..models.ai_trading import AITradingProfile, AITradingDecision

logger = logging.getLogger(__name__)

MODEL_PRIORITY = ["sonnet", "haiku"]


class AITradingService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = AITradingService()
        return cls._instance

    def __init__(self):
        self._decision_locks: Dict[str, asyncio.Lock] = {}

    # ── Public API ──────────────────────────────────────────────

    async def start_ai_trading(self, profile_id: str, user_id: int, account_ctx=None) -> Dict:
        """Start AI trading for a profile. Runs initial decision pipeline."""
        db = SessionLocal()
        try:
            profile = db.query(AITradingProfile).filter(
                AITradingProfile.id == profile_id,
                AITradingProfile.user_id == user_id,
                AITradingProfile.is_active == True,
            ).first()
            if not profile:
                return {"error": "Profile not found"}
            if profile.is_running:
                return {"error": "Profile already running"}

            profile.is_running = True
            profile.updated_at = datetime.utcnow()
            db.commit()

            # Run initial decision in background
            asyncio.create_task(
                self._run_decision_pipeline(profile_id, user_id, "initial_start", account_ctx=account_ctx)
            )

            return {"status": "started", "profile_id": profile_id}
        finally:
            db.close()

    async def stop_ai_trading(self, profile_id: str, user_id: int) -> Dict:
        """Stop AI trading. Does NOT stop the current live session."""
        db = SessionLocal()
        try:
            profile = db.query(AITradingProfile).filter(
                AITradingProfile.id == profile_id,
                AITradingProfile.user_id == user_id,
            ).first()
            if not profile:
                return {"error": "Profile not found"}

            profile.is_running = False
            profile.updated_at = datetime.utcnow()
            db.commit()

            return {"status": "stopped", "profile_id": profile_id}
        finally:
            db.close()

    async def trigger_decision(self, profile_id: str, user_id: int, account_ctx=None) -> Dict:
        """Manually trigger an AI decision."""
        db = SessionLocal()
        try:
            profile = db.query(AITradingProfile).filter(
                AITradingProfile.id == profile_id,
                AITradingProfile.user_id == user_id,
                AITradingProfile.is_active == True,
            ).first()
            if not profile:
                return {"error": "Profile not found"}

            # Run decision pipeline in background
            asyncio.create_task(
                self._run_decision_pipeline(profile_id, user_id, "manual", account_ctx=account_ctx)
            )

            return {"status": "decision_triggered", "profile_id": profile_id}
        finally:
            db.close()

    async def get_decisions(self, profile_id: str, user_id: int, limit: int = 20) -> List[Dict]:
        """Get decision history for a profile."""
        db = SessionLocal()
        try:
            profile = db.query(AITradingProfile).filter(
                AITradingProfile.id == profile_id,
                AITradingProfile.user_id == user_id,
            ).first()
            if not profile:
                return []

            decisions = db.query(AITradingDecision).filter(
                AITradingDecision.profile_id == profile_id
            ).order_by(AITradingDecision.created_at.desc()).limit(limit).all()

            return [self._decision_to_dict(d) for d in decisions]
        finally:
            db.close()

    async def get_decision_detail(self, decision_id: str, user_id: int) -> Optional[Dict]:
        """Get full decision details."""
        db = SessionLocal()
        try:
            decision = db.query(AITradingDecision).filter(
                AITradingDecision.id == decision_id
            ).first()
            if not decision:
                return None

            profile = db.query(AITradingProfile).filter(
                AITradingProfile.id == decision.profile_id,
                AITradingProfile.user_id == user_id,
            ).first()
            if not profile:
                return None

            return self._decision_to_dict(decision, full=True)
        finally:
            db.close()

    # ── Decision Pipeline ───────────────────────────────────────

    async def _run_decision_pipeline(
        self,
        profile_id: str,
        user_id: int,
        trigger_type: str,
        previous_session_id: str = None,
        previous_cycle_pnl: float = None,
        account_ctx=None,
    ):
        """Multi-step AI decision pipeline."""
        # Acquire lock to prevent concurrent decisions
        if profile_id not in self._decision_locks:
            self._decision_locks[profile_id] = asyncio.Lock()

        if self._decision_locks[profile_id].locked():
            logger.warning(f"[AITrading] Decision already in progress for profile {profile_id}")
            return

        async with self._decision_locks[profile_id]:
            db = SessionLocal()
            decision = None
            try:
                profile = db.query(AITradingProfile).filter(
                    AITradingProfile.id == profile_id
                ).first()
                if not profile:
                    logger.error(f"[AITrading] Profile {profile_id} not found")
                    return

                # Create decision record
                decision = AITradingDecision(
                    id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    trigger_type=trigger_type,
                    previous_session_id=previous_session_id or profile.current_session_id,
                    previous_symbol=profile.current_symbol,
                    previous_cycle_pnl=previous_cycle_pnl,
                    status="EXECUTING",
                )
                db.add(decision)
                db.commit()

                logger.info(f"[AITrading] Starting pipeline: profile={profile.name}, trigger={trigger_type}")

                # Step 1: Stock Selection
                candidates = await self._step1_stock_selection(profile, decision, db, account_ctx)
                if not candidates:
                    decision.status = "SKIPPED"
                    decision.error_message = "No suitable candidates found"
                    decision.completed_at = datetime.utcnow()
                    db.commit()
                    return

                # Step 2: Optimization
                opt_results = await self._step2_optimization(profile, candidates, decision, db)
                if not opt_results:
                    decision.status = "FAILED"
                    decision.error_message = "Optimization returned no results"
                    decision.completed_at = datetime.utcnow()
                    db.commit()
                    return

                # Step 3: Final Decision
                final = await self._step3_final_decision(profile, opt_results, decision, db)
                if not final or final.get("skip"):
                    decision.status = "SKIPPED"
                    decision.error_message = final.get("skip_reason", "AI decided to skip")
                    decision.completed_at = datetime.utcnow()
                    db.commit()
                    return

                # Step 4: Execute Session Transition
                await self._step4_execute_transition(profile, decision, final, db)

                logger.info(
                    f"[AITrading] Pipeline complete: {profile.name} → "
                    f"{decision.chosen_symbol} ({decision.chosen_symbol_name})"
                )

            except Exception as e:
                logger.error(f"[AITrading] Pipeline error: {e}", exc_info=True)
                if decision:
                    decision.status = "FAILED"
                    decision.error_message = str(e)[:500]
                    decision.completed_at = datetime.utcnow()
                    try:
                        db.commit()
                    except Exception:
                        pass
            finally:
                db.close()

    # ── Step 1: Stock Selection ──────────────────────────────────

    async def _step1_stock_selection(self, profile, decision, db, account_ctx=None) -> List[Dict]:
        """Select candidate stocks via Claude CLI."""
        start_ms = int(time.time() * 1000)

        if profile.stock_source_mode == "FIXED":
            candidates = profile.fixed_symbols or []
            for c in candidates:
                c["score"] = 100
                c["reason"] = "고정 종목"
            decision.stock_candidates = candidates
            decision.stock_selection_duration_ms = int(time.time() * 1000) - start_ms
            db.commit()
            return candidates

        # Fetch market data
        rankings = {}
        stocks = []
        try:
            api_url, token = await self._get_kiwoom_credentials(profile, account_ctx)
            if api_url and token:
                from ..services.stock_list_service import StockListService
                from ..services.ranking_data_service import RankingDataService

                stock_service = StockListService.get_instance()
                ranking_service = RankingDataService.get_instance()

                stocks, rankings = await asyncio.gather(
                    stock_service.get_stock_list(api_url, token),
                    ranking_service.get_rankings(api_url, token),
                )
        except Exception as e:
            logger.error(f"[AITrading] Failed to fetch market data: {e}")

        # Build context for Claude CLI
        context = {
            "search_conditions": profile.search_conditions or "거래량 상위 + 외국인 순매수 종목",
            "stock_source_mode": profile.stock_source_mode,
            "candidate_symbols": profile.candidate_symbols if profile.stock_source_mode == "CANDIDATE_LIST" else None,
            "previous_performance": {
                "symbol": profile.current_symbol,
                "cycles_completed": profile.cycles_completed,
                "consecutive_losses": profile.consecutive_losses,
                "pnl": decision.previous_cycle_pnl,
            },
            "strategy_name": profile.strategy_name,
            "stocks": self._slim_stocks(stocks),
            "rankings": rankings,
        }

        result = await self._call_claude_cli(
            context, agent="ai-stock-selector", timeout=300
        )

        duration_ms = int(time.time() * 1000) - start_ms
        decision.stock_selection_duration_ms = duration_ms

        if not result or "error" in result:
            logger.error(f"[AITrading] Stock selection failed: {result}")
            decision.stock_selection_model = result.get("model") if result else None
            db.commit()
            return []

        decision.stock_selection_model = result.get("model")

        # Parse candidates from Claude response
        candidates = []
        try:
            response_text = result.get("response", "")
            parsed = json.loads(response_text) if isinstance(response_text, str) else response_text
            candidates = parsed.get("candidates", [])

            if parsed.get("skip_recommendation"):
                decision.stock_candidates = candidates
                db.commit()
                return []
        except (json.JSONDecodeError, AttributeError):
            logger.error(f"[AITrading] Failed to parse stock selection response")

        decision.stock_candidates = candidates
        db.commit()
        return candidates

    # ── Step 2: Optimization ─────────────────────────────────────

    async def _step2_optimization(self, profile, candidates, decision, db) -> List[Dict]:
        """Run backtest optimization for candidate stocks."""
        from ..api.mock_strategies import _run_unified_backtest, build_backtest_config
        from ..core.strategy_registry import StrategyRegistry

        start_ms = int(time.time() * 1000)
        results = []

        param_schema = StrategyRegistry.get_parameter_schema(profile.strategy_name)
        top_n = min(profile.optimization_top_n or 5, len(candidates))

        for candidate in candidates[:top_n]:
            symbol = candidate.get("code")
            if not symbol:
                continue

            try:
                # Generate parameter combinations
                param_combos = self._generate_param_combos(
                    param_schema, profile.param_ranges, profile.fixed_params,
                    max_combos=profile.max_optimization_combos or 500,
                )

                best = None
                for params in param_combos:
                    config = build_backtest_config(
                        params, symbol,
                        profile.backtest_interval or "1m",
                        profile.backtest_days or 30,
                        None,  # from_date
                        int(profile.initial_capital),
                    )
                    try:
                        bt_result = await _run_unified_backtest(
                            strategy_id=profile.strategy_name,
                            configs=[config],
                            symbol=symbol,
                            interval=profile.backtest_interval or "1m",
                            days=profile.backtest_days or 30,
                            from_date=None,
                            initial_capital=int(profile.initial_capital),
                            execution_mode="single",
                            optimize_mode=True,
                        )
                    except Exception as e:
                        logger.warning(f"[AITrading] Backtest failed for {symbol}: {e}")
                        continue

                    if bt_result.get("error"):
                        continue

                    score = self._compute_score(bt_result)
                    if not best or score > best["optimization_score"]:
                        best = {
                            "symbol": symbol,
                            "symbol_name": candidate.get("name", symbol),
                            "selection_reason": candidate.get("reason", ""),
                            "selection_score": candidate.get("score", 0),
                            "best_params": params,
                            "backtest_stats": {
                                "total_return": bt_result.get("total_return", "0%"),
                                "win_rate": bt_result.get("win_rate", "0%"),
                                "max_drawdown": bt_result.get("max_drawdown", "0%"),
                                "total_cycles": bt_result.get("total_cycles", 0),
                                "profit_factor": bt_result.get("profit_factor", "0"),
                                "sharpe_ratio": bt_result.get("sharpe_ratio", "0"),
                                "avg_pnl": bt_result.get("avg_pnl", "0%"),
                                "stability_score": bt_result.get("stability_score", "0"),
                            },
                            "optimization_score": score,
                        }

                if best:
                    results.append(best)

            except Exception as e:
                logger.error(f"[AITrading] Optimization error for {symbol}: {e}")

        results.sort(key=lambda r: r["optimization_score"], reverse=True)

        decision.optimization_results = results
        decision.optimization_duration_ms = int(time.time() * 1000) - start_ms
        db.commit()

        return results

    # ── Step 3: Final Decision ───────────────────────────────────

    async def _step3_final_decision(self, profile, opt_results, decision, db) -> Optional[Dict]:
        """Call Claude CLI for final stock + parameter decision."""
        start_ms = int(time.time() * 1000)

        # If only one candidate, use it directly
        if len(opt_results) == 1:
            r = opt_results[0]
            decision.chosen_symbol = r["symbol"]
            decision.chosen_symbol_name = r["symbol_name"]
            decision.chosen_params = r["best_params"]
            decision.chosen_score = r["optimization_score"]
            decision.chosen_reasoning = f"유일한 후보: {r['symbol_name']} (최적화 점수 {r['optimization_score']:.1f})"
            decision.final_decision_duration_ms = int(time.time() * 1000) - start_ms
            db.commit()
            return {"skip": False}

        context = {
            "optimization_results": opt_results,
            "previous_performance": {
                "symbol": profile.current_symbol,
                "pnl": decision.previous_cycle_pnl,
                "total_cycles": profile.cycles_completed,
                "consecutive_losses": profile.consecutive_losses,
            },
            "strategy_name": profile.strategy_name,
            "is_paper": profile.is_paper,
            "initial_capital": profile.initial_capital,
        }

        result = await self._call_claude_cli(
            context, agent="ai-trading-decision", timeout=300
        )

        duration_ms = int(time.time() * 1000) - start_ms
        decision.final_decision_duration_ms = duration_ms
        decision.final_decision_model = result.get("model") if result else None

        if not result or "error" in result:
            # Fallback: use top optimization result
            logger.warning("[AITrading] Final decision failed, using top optimization result")
            r = opt_results[0]
            decision.chosen_symbol = r["symbol"]
            decision.chosen_symbol_name = r["symbol_name"]
            decision.chosen_params = r["best_params"]
            decision.chosen_score = r["optimization_score"]
            decision.chosen_reasoning = f"AI 결정 실패, 최적화 1위 사용: {r['symbol_name']}"
            db.commit()
            return {"skip": False}

        # Parse final decision
        try:
            response_text = result.get("response", "")
            parsed = json.loads(response_text) if isinstance(response_text, str) else response_text

            if parsed.get("skip"):
                db.commit()
                return {"skip": True, "skip_reason": parsed.get("skip_reason")}

            d = parsed.get("decision", {})
            decision.chosen_symbol = d.get("symbol")
            decision.chosen_symbol_name = d.get("symbol_name")
            decision.chosen_params = d.get("params")
            decision.chosen_score = parsed.get("confidence", 0)
            decision.chosen_reasoning = d.get("reasoning", "")

        except (json.JSONDecodeError, AttributeError):
            # Fallback
            r = opt_results[0]
            decision.chosen_symbol = r["symbol"]
            decision.chosen_symbol_name = r["symbol_name"]
            decision.chosen_params = r["best_params"]
            decision.chosen_score = r["optimization_score"]
            decision.chosen_reasoning = f"응답 파싱 실패, 최적화 1위 사용: {r['symbol_name']}"

        db.commit()
        return {"skip": False}

    # ── Step 4: Session Transition ───────────────────────────────

    async def _step4_execute_transition(self, profile, decision, final, db):
        """Stop old session, start new session with AI's decision."""
        from ..core.live_manager import live_manager

        # Stop old session if exists
        if profile.current_session_id:
            try:
                await live_manager.stop_session(profile.current_session_id, force=False)
                logger.info(f"[AITrading] Stopped old session: {profile.current_session_id}")
            except Exception as e:
                logger.warning(f"[AITrading] Failed to stop old session: {e}")

        # Start new session
        config = {
            "symbol": decision.chosen_symbol,
            "strategy_name": profile.strategy_name,
            "strategy_config": {
                **(decision.chosen_params or {}),
                "initial_capital": profile.initial_capital,
            },
            "initial_capital": profile.initial_capital,
            "is_paper": profile.is_paper,
            "account_id": profile.account_id,
            "auto_start": True,
            "ai_profile_id": profile.id,
            "profile_name": f"AI: {profile.name}",
        }

        try:
            new_session_id = await live_manager.start_session(config)
        except Exception as e:
            decision.status = "FAILED"
            decision.error_message = f"Session start failed: {str(e)[:300]}"
            decision.completed_at = datetime.utcnow()
            db.commit()
            raise

        # Update profile state
        profile.current_session_id = new_session_id
        profile.current_symbol = decision.chosen_symbol
        profile.last_decision_at = datetime.utcnow()
        profile.cycles_completed += 1
        if decision.previous_cycle_pnl is not None and decision.previous_cycle_pnl < 0:
            profile.consecutive_losses += 1
        else:
            profile.consecutive_losses = 0

        # Update decision
        decision.new_session_id = new_session_id
        decision.status = "COMPLETED"
        decision.completed_at = datetime.utcnow()
        db.commit()

    # ── Claude CLI Helper ────────────────────────────────────────

    async def _call_claude_cli(self, context_data: Dict, agent: str, timeout: int = 300) -> Optional[Dict]:
        """Call Claude CLI with context data. Returns parsed response or error dict."""
        from ..core.config import get_claude_cli_path

        try:
            claude_path = get_claude_cli_path()
        except FileNotFoundError:
            return {"error": "Claude CLI not found"}

        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', prefix=f'ai_trading_{agent}_',
                dir='/tmp', delete=False, encoding='utf-8'
            ) as f:
                json.dump(context_data, f, ensure_ascii=False, default=str)
                tmp_file = f.name

            prompt = (
                f"Read the context file at `{tmp_file}` using the Read tool. "
                f"Analyze the data and provide your decision as JSON."
            )

            for model in MODEL_PRIORITY:
                cmd = [
                    claude_path,
                    "-p", prompt,
                    "--output-format", "json",
                    "--agent", agent,
                    "--model", model,
                    "--permission-mode", "bypassPermissions",
                ]

                env = os.environ.copy()
                for key in ["NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_APP_INSTANCE"]:
                    env.pop(key, None)

                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        stdin=asyncio.subprocess.DEVNULL,
                        env=env,
                        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

                    if proc.returncode != 0:
                        err_text = stderr.decode("utf-8", errors="replace")[:500]
                        if any(kw in err_text.lower() for kw in ["rate limit", "overloaded", "529"]):
                            logger.warning(f"[AITrading] Rate limited on {model}, trying next")
                            continue
                        return {"error": f"CLI error ({model}): {err_text}", "model": model}

                    output = stdout.decode("utf-8", errors="replace")
                    try:
                        parsed = json.loads(output)
                        response = parsed.get("result", output)
                        return {"response": response, "model": model}
                    except json.JSONDecodeError:
                        return {"response": output, "model": model}

                except asyncio.TimeoutError:
                    logger.error(f"[AITrading] Claude CLI timeout ({model}, {timeout}s)")
                    continue

            return {"error": "All models failed"}

        except Exception as e:
            return {"error": str(e)}
        finally:
            if tmp_file:
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass

    # ── Helpers ──────────────────────────────────────────────────

    async def _get_kiwoom_credentials(self, profile, account_ctx=None):
        """Get Kiwoom API URL and token for data fetching."""
        if account_ctx:
            try:
                token = await account_ctx.ensure_token()
                return account_ctx.api_url, token
            except Exception:
                pass

        # Fallback: try to get from account_id
        if profile.account_id:
            from ..core.kiwoom_token_manager import KiwoomTokenManager
            from ..models.account import ExchangeAccount
            from ..core import security

            db = SessionLocal()
            try:
                account = db.query(ExchangeAccount).filter(
                    ExchangeAccount.id == profile.account_id
                ).first()
                if account and account.encrypted_app_key:
                    app_key = security.decrypt_key(account.encrypted_app_key)
                    secret_key = security.decrypt_key(account.encrypted_secret_key)
                    token_mgr = KiwoomTokenManager()
                    token = await token_mgr.get_token(
                        account.api_url or "https://api.kiwoom.com",
                        app_key, secret_key
                    )
                    return account.api_url or "https://api.kiwoom.com", token
            except Exception as e:
                logger.error(f"[AITrading] Token fetch error: {e}")
            finally:
                db.close()

        return None, None

    def _slim_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """Reduce stock data to essential fields."""
        keep = {"code", "name", "marketName", "upName", "upSizeName", "lastPrice", "state", "orderWarning"}
        return [{k: v for k, v in s.items() if k in keep} for s in stocks]

    def _generate_param_combos(
        self,
        schema: Optional[Dict],
        param_ranges: Optional[Dict],
        fixed_params: Optional[Dict],
        max_combos: int = 500,
    ) -> List[Dict]:
        """Generate parameter combinations for optimization."""
        if not schema:
            return [fixed_params or {}]

        fields = schema.get("fields", [])
        varying = {}
        base = dict(fixed_params or {})

        for field in fields:
            name = field.get("key") or field.get("name")
            if not name:
                continue

            # Fixed param: skip optimization
            if fixed_params and name in fixed_params:
                continue

            # User-defined ranges
            if param_ranges and name in param_ranges:
                r = param_ranges[name]
                if isinstance(r, dict) and "min" in r and "max" in r:
                    step = r.get("step", field.get("step", 1))
                    values = []
                    v = r["min"]
                    while v <= r["max"]:
                        values.append(round(v, 4))
                        v += step
                    if values:
                        varying[name] = values
                        continue

            # Use defaultOptRange if available
            opt_range = field.get("defaultOptRange")
            if opt_range and isinstance(opt_range, str):
                try:
                    values = [float(x.strip()) for x in opt_range.split(",")]
                    if values:
                        varying[name] = values
                        continue
                except ValueError:
                    pass

            # Use default value
            default = field.get("default")
            if default is not None:
                base[name] = default

        if not varying:
            return [base]

        # Generate combinations, capped at max_combos
        keys = list(varying.keys())
        value_lists = [varying[k] for k in keys]

        total = 1
        for vl in value_lists:
            total *= len(vl)

        combos = []
        if total <= max_combos:
            for combo in product(*value_lists):
                config = dict(base)
                for k, v in zip(keys, combo):
                    config[k] = v
                combos.append(config)
        else:
            # Sample uniformly
            import random
            all_combos = list(product(*value_lists))
            random.shuffle(all_combos)
            for combo in all_combos[:max_combos]:
                config = dict(base)
                for k, v in zip(keys, combo):
                    config[k] = v
                combos.append(config)

        return combos

    def _compute_score(self, result: Dict) -> float:
        """Compute a composite score from backtest results."""
        def parse_pct(val):
            if isinstance(val, str):
                return float(val.replace("%", "").replace(",", ""))
            return float(val or 0)

        try:
            total_return = parse_pct(result.get("total_return", "0"))
            win_rate = parse_pct(result.get("win_rate", "0"))
            mdd = abs(parse_pct(result.get("max_drawdown", "0")))
            profit_factor = parse_pct(result.get("profit_factor", "0"))
            sharpe = parse_pct(result.get("sharpe_ratio", "0"))
            total_cycles = int(result.get("total_cycles", 0))

            if total_cycles < 3:
                return 0.0

            score = (
                total_return * 1.0
                + sharpe * 10.0
                + win_rate * 0.3
                + profit_factor * 5.0
                - mdd * 0.5
            )
            return round(max(score, 0), 2)
        except (ValueError, TypeError):
            return 0.0

    def _decision_to_dict(self, d: AITradingDecision, full: bool = False) -> Dict:
        """Convert decision model to dict."""
        data = {
            "id": d.id,
            "profile_id": d.profile_id,
            "trigger_type": d.trigger_type,
            "previous_symbol": d.previous_symbol,
            "previous_cycle_pnl": d.previous_cycle_pnl,
            "chosen_symbol": d.chosen_symbol,
            "chosen_symbol_name": d.chosen_symbol_name,
            "chosen_score": d.chosen_score,
            "chosen_reasoning": d.chosen_reasoning,
            "new_session_id": d.new_session_id,
            "status": d.status,
            "error_message": d.error_message,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
        }
        if full:
            data.update({
                "stock_candidates": d.stock_candidates,
                "stock_selection_model": d.stock_selection_model,
                "stock_selection_duration_ms": d.stock_selection_duration_ms,
                "optimization_results": d.optimization_results,
                "optimization_duration_ms": d.optimization_duration_ms,
                "chosen_params": d.chosen_params,
                "final_decision_model": d.final_decision_model,
                "final_decision_duration_ms": d.final_decision_duration_ms,
            })
        return data
