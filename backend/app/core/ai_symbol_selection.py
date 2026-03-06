"""
AI Symbol Selection Service

Lightweight AI-driven symbol rotation for live trading sessions.
On cycle completion, evaluates current symbol fitness and optionally
switches to a better candidate using the same strategy parameters.

Pipeline:
  1. Check current symbol against user's search conditions (Claude CLI)
  2. If unfit, find up to 20 candidates (Claude CLI)
  3. Compare candidates via backtest (14-day) with same params
  4. Return best symbol or None (keep current)
"""

import asyncio
import json
import logging
import os
import tempfile
from typing import Optional, List, Dict, Any

logger = logging.getLogger("AISymbolSelection")


class AISymbolSelectionService:
    """Singleton service for AI-driven symbol selection."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = AISymbolSelectionService()
        return cls._instance

    def __init__(self):
        # Progress tracking per session: {session_id: {stage, message, ...}}
        self._progress: Dict[str, Dict[str, Any]] = {}

        # Group-level coordination
        self._group_locks: Dict[str, asyncio.Lock] = {}       # group_id → Lock
        self._group_pending: Dict[str, Dict[str, dict]] = {}  # group_id → {session_id: session_info}
        self._group_timers: Dict[str, asyncio.Task] = {}      # group_id → timer task

        self.GROUP_COLLECT_WINDOW = 30   # Wait time for first session (seconds)
        self.GROUP_EXTEND_WINDOW = 10    # Wait time for additional sessions (seconds)

    def get_progress(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current pipeline progress for a session."""
        progress = self._progress.get(session_id)
        if progress:
            return progress
        # Check if session is in a pending group evaluation
        for group_id, pending in self._group_pending.items():
            if session_id in pending:
                return {"stage": "waiting", "message": "그룹 평가 대기 중...", "active": True}
        return None

    def _update_progress(self, session_id: str, stage: str, message: str, **kwargs):
        """Update pipeline progress for a session."""
        self._progress[session_id] = {
            "stage": stage,
            "message": message,
            "active": True,
            **kwargs,
        }

    def _clear_progress(self, session_id: str, delay: float = 10.0):
        """Mark pipeline as complete. Keep progress visible for `delay` seconds."""
        if session_id in self._progress:
            self._progress[session_id]["active"] = False

            async def _delayed_delete():
                await asyncio.sleep(delay)
                self._progress.pop(session_id, None)

            asyncio.ensure_future(_delayed_delete())

    def _save_history(
        self, session_id: str, group_id: str, action: str,
        old_symbol: str, old_symbol_name: str = None,
        new_symbol: str = None, new_symbol_name: str = None,
        search_conditions: str = None, evaluation_reason: str = None,
        backtest_results: list = None,
    ):
        """Save AI symbol selection result to DB for history tracking."""
        from ..db.session import SessionLocal
        from ..models.live_trading import AISymbolHistory

        try:
            db = SessionLocal()
            record = AISymbolHistory(
                session_id=session_id,
                group_id=group_id,
                action=action,
                old_symbol=old_symbol,
                old_symbol_name=old_symbol_name,
                new_symbol=new_symbol,
                new_symbol_name=new_symbol_name,
                search_conditions=search_conditions,
                evaluation_reason=evaluation_reason,
                backtest_results=backtest_results,
            )
            db.add(record)
            db.commit()
            logger.info(f"[AISymbol] History saved: {session_id[:8]} {action} "
                        f"{old_symbol} -> {new_symbol or '(kept)'}")
        except Exception as e:
            logger.error(f"[AISymbol] Failed to save history: {e}")
        finally:
            db.close()

    async def run_pipeline(
        self,
        session_id: str,
        current_symbol: str,
        search_conditions: str,
        strategy_name: str,
        strategy_config: dict,
        initial_capital: float,
        account_id: int,
        is_paper: bool,
        group_id: str = None,
        current_symbol_name: str = None,
    ) -> Optional[str]:
        """
        Full AI symbol selection pipeline.
        Returns new symbol code if switch is recommended, None to keep current.
        """
        _sym_name = current_symbol_name or strategy_config.get("symbol_name", current_symbol)
        logger.info(f"[AISymbol] Pipeline START for session {session_id}, "
                     f"symbol={current_symbol}, conditions='{search_conditions[:50]}...'")

        self._update_progress(session_id, "init", "파이프라인 시작...")

        try:
            # Step 1: Get symbols already used by other sessions in the same group
            excluded_symbols = set()
            if group_id:
                excluded_symbols = await self._get_group_symbols(group_id, exclude_ids={session_id})
                if excluded_symbols:
                    logger.info(f"[AISymbol] Group {group_id} excluded symbols: {excluded_symbols}")

            # Step 2: Get token for API calls
            self._update_progress(session_id, "market_data", "시장 데이터 수집 중...")
            api_url, token = await self._get_token(account_id)
            if not token:
                logger.error(f"[AISymbol] Failed to get token for account {account_id}")
                self._update_progress(session_id, "error", "토큰 획득 실패")
                self._clear_progress(session_id)
                return None

            # Step 3: Fetch market data (stock list + rankings)
            stock_data, ranking_data = await self._fetch_market_data(api_url, token)
            if not stock_data:
                logger.error("[AISymbol] Failed to fetch market data")
                self._update_progress(session_id, "error", "시장 데이터 수집 실패")
                self._clear_progress(session_id)
                return None

            # Step 4: Check if current symbol still matches conditions
            self._update_progress(session_id, "evaluating", f"현재 종목({current_symbol}) 적합성 평가 중...")
            should_switch, eval_reason = await self._check_current_symbol(
                current_symbol, search_conditions, stock_data, ranking_data
            )
            if not should_switch:
                reason = f"현재 종목({current_symbol}) 유지: {eval_reason}" if eval_reason else f"현재 종목({current_symbol}) 유지 - 조건 부합"
                logger.info(f"[AISymbol] Current symbol {current_symbol} keeping. Reason: {eval_reason}")
                self._update_progress(session_id, "done", reason)
                self._save_history(session_id, group_id, "kept",
                                   old_symbol=current_symbol,
                                   old_symbol_name=_sym_name,
                                   search_conditions=search_conditions,
                                   evaluation_reason=reason)
                self._clear_progress(session_id)
                return None

            # Step 5: Find candidate symbols
            self._update_progress(session_id, "finding", "AI가 후보 종목 탐색 중...")
            candidates = await self._find_candidates(
                current_symbol, search_conditions, stock_data, ranking_data,
                excluded_symbols=excluded_symbols,
            )
            if not candidates:
                reason = "후보 종목 없음 - 현재 종목 유지"
                logger.warning("[AISymbol] No candidates found. Keeping current symbol.")
                self._update_progress(session_id, "done", reason)
                self._save_history(session_id, group_id, "no_candidates",
                                   old_symbol=current_symbol,
                                   old_symbol_name=_sym_name,
                                   search_conditions=search_conditions,
                                   evaluation_reason=reason)
                self._clear_progress(session_id)
                return None

            logger.info(f"[AISymbol] Found {len(candidates)} candidates: {candidates}")

            # Step 6: Compare candidates via backtest
            self._update_progress(session_id, "backtesting",
                                  f"{len(candidates)}개 후보 백테스트 중... (0/{len(candidates)})",
                                  total=len(candidates), current=0, results=[])
            best_symbol = await self._compare_symbols(
                candidates, strategy_name, strategy_config, initial_capital,
                session_id=session_id,
            )
            if not best_symbol:
                bt_results = self._progress.get(session_id, {}).get("results", [])
                reason = (f"[교체 사유] {eval_reason}\n"
                          f"[결과] 적합한 후보 없음 - 현재 종목 유지")
                logger.warning("[AISymbol] No candidate outperformed. Keeping current symbol.")
                self._update_progress(session_id, "done", "적합한 후보 없음 - 현재 종목 유지")
                self._save_history(session_id, group_id, "no_candidates",
                                   old_symbol=current_symbol,
                                   old_symbol_name=_sym_name,
                                   search_conditions=search_conditions,
                                   evaluation_reason=reason,
                                   backtest_results=bt_results)
                self._clear_progress(session_id)
                return None

            bt_results = self._progress.get(session_id, {}).get("results", [])
            reason = (f"[교체 사유] {eval_reason}\n"
                      f"[결과] {current_symbol} → {best_symbol}")
            logger.info(f"[AISymbol] Pipeline COMPLETE: {current_symbol} -> {best_symbol}")
            self._update_progress(session_id, "done",
                                  f"종목 전환 완료: {current_symbol} → {best_symbol}",
                                  new_symbol=best_symbol)
            self._save_history(session_id, group_id, "switched",
                               old_symbol=current_symbol,
                               old_symbol_name=_sym_name,
                               new_symbol=best_symbol,
                               search_conditions=search_conditions,
                               evaluation_reason=reason,
                               backtest_results=bt_results)
            return best_symbol

        except Exception as e:
            logger.error(f"[AISymbol] Pipeline FAILED: {e}", exc_info=True)
            self._update_progress(session_id, "error", f"파이프라인 오류: {str(e)[:100]}")
            self._clear_progress(session_id)
            return None

    async def _get_group_symbols(self, group_id: str, exclude_ids: set = None) -> set:
        """Get symbols used by other RUNNING sessions in the same group."""
        from ..db.session import SessionLocal
        from ..models.live_trading import LiveBotSession

        _exclude = exclude_ids or set()

        def _query():
            db = SessionLocal()
            try:
                sessions = db.query(LiveBotSession).filter(
                    LiveBotSession.group_id == group_id,
                    LiveBotSession.status.in_(["RUNNING", "PAUSED"]),
                ).all()
                return {s.symbol for s in sessions if s.symbol and s.id not in _exclude}
            finally:
                db.close()

        return await asyncio.get_event_loop().run_in_executor(None, _query)

    async def _get_token(self, account_id: int) -> tuple:
        """Get API URL and token for the account."""
        from .live_manager import live_manager

        try:
            adapter = await live_manager.get_or_create_adapter(account_id)
            if hasattr(adapter, '_ensure_token'):
                await adapter._ensure_token()
            api_url = getattr(adapter, 'base_url', None)
            token = getattr(adapter, 'access_token', None)
            return api_url, token
        except Exception as e:
            logger.error(f"[AISymbol] Token error: {e}")
            return None, None

    async def _fetch_market_data(self, api_url: str, token: str) -> tuple:
        """Fetch stock list and ranking data using existing services."""
        from ..services.stock_list_service import StockListService
        from ..services.ranking_data_service import RankingDataService

        stock_service = StockListService.get_instance()
        ranking_service = RankingDataService.get_instance()

        try:
            all_stocks, rankings = await asyncio.gather(
                stock_service.get_stock_list(api_url, token),
                ranking_service.get_rankings(api_url, token),
            )
            return all_stocks, rankings
        except Exception as e:
            logger.error(f"[AISymbol] Market data fetch error: {e}")
            return None, None

    async def _check_current_symbol(
        self,
        current_symbol: str,
        search_conditions: str,
        stock_data: list,
        ranking_data: dict,
    ) -> tuple:
        """
        Check if current symbol still matches the user's conditions.
        Returns (should_switch: bool, reason: str).
        should_switch=True means symbol doesn't match conditions and should be replaced.
        """
        # Find current symbol name
        symbol_name = current_symbol
        for s in stock_data:
            if s.get("code") == current_symbol:
                symbol_name = s.get("name", current_symbol)
                break

        context_data = {
            "mode": "EVALUATE",
            "current_symbol": {"code": current_symbol, "name": symbol_name},
            "search_conditions": search_conditions,
            "stocks": self._slim_stock_data(stock_data),
            "rankings": ranking_data,
        }

        prompt = (
            f"Read the context file and evaluate if the current symbol "
            f"({current_symbol} {symbol_name}) still matches the user's conditions: "
            f"'{search_conditions}'. "
            f"Respond with ONLY a JSON object: "
            f'{{"match": true/false, "reason": "detailed explanation in Korean why this symbol matches or does not match the conditions, including specific data points like volume change rate, price change rate, etc."}}'
        )

        result = await self._call_claude(context_data, prompt)
        if result is None:
            return False, "AI 평가 오류 - 현재 종목 유지"

        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            match = parsed.get("match", True)
            reason = parsed.get("reason", "")
            logger.info(f"[AISymbol] Evaluate result: match={match}, reason={reason}")
            return not match, reason  # (should_switch, reason)
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"[AISymbol] Failed to parse evaluate response: {result[:200]}")
            return False, f"AI 응답 파싱 실패: {str(result)[:100]}"

    async def _find_candidates(
        self,
        current_symbol: str,
        search_conditions: str,
        stock_data: list,
        ranking_data: dict,
        excluded_symbols: set = None,
    ) -> List[str]:
        """Find up to 20 candidate symbols matching the conditions."""
        excluded_symbols = excluded_symbols or set()

        # Build exclusion list for the prompt
        all_excluded = {current_symbol} | excluded_symbols
        exclude_str = ", ".join(all_excluded)

        context_data = {
            "mode": "FIND",
            "current_symbol": current_symbol,
            "search_conditions": search_conditions,
            "excluded_symbols": list(all_excluded),
            "stocks": self._slim_stock_data(stock_data),
            "rankings": ranking_data,
        }

        prompt = (
            f"Read the context file and find up to 20 stock candidates that match "
            f"the user's conditions: '{search_conditions}'. "
            f"Return as many candidates as possible (up to 20). "
            f"Exclude ALL of these symbols (already in use): {exclude_str}. "
            f"Respond with ONLY a JSON object: "
            f'{{"candidates": [{{"code": "123456", "name": "종목명", "reason": "이유"}}]}}'
        )

        result = await self._call_claude(context_data, prompt)
        if result is None:
            return []

        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            candidates = parsed.get("candidates", [])
            # Extract codes and filter out any excluded symbols (safety net)
            codes = [c["code"] for c in candidates
                     if "code" in c and c["code"] not in all_excluded]
            return codes[:20]  # Max 20 candidates
        except (json.JSONDecodeError, AttributeError, KeyError):
            logger.warning(f"[AISymbol] Failed to parse find response: {result[:200]}")
            return []

    async def _compare_symbols(
        self,
        candidates: List[str],
        strategy_name: str,
        strategy_config: dict,
        initial_capital: float,
        session_id: str = None,
    ) -> Optional[str]:
        """Compare candidates via backtest (14-day) with same strategy params."""
        from ..api.mock_strategies import _run_unified_backtest

        best_symbol = None
        best_score = float('-inf')
        results_summary = []

        for i, symbol in enumerate(candidates):
            try:
                config = dict(strategy_config)
                config['symbol'] = symbol

                # Update progress
                if session_id:
                    prog = self._progress.get(session_id, {})
                    self._update_progress(
                        session_id, "backtesting",
                        f"{len(candidates)}개 후보 백테스트 중... ({i+1}/{len(candidates)}) - {symbol}",
                        total=len(candidates), current=i+1,
                        results=prog.get("results", []),
                    )

                result = await _run_unified_backtest(
                    strategy_id=strategy_name,
                    configs=[config],
                    symbol=symbol,
                    interval="1m",
                    days=14,
                    from_date=None,
                    initial_capital=int(initial_capital),
                    execution_mode="single",
                    optimize_mode=True,
                )

                if "error" in result:
                    logger.warning(f"[AISymbol] Backtest failed for {symbol}: {result['error']}")
                    continue

                # Extract score
                score = self._calculate_score(result)
                trades = int(result.get("total_cycles", 0))
                ret = float(str(result.get("total_return", "0")).replace('%', '').replace(',', ''))
                wr = float(str(result.get("win_rate", "0")).replace('%', ''))
                logger.info(f"[AISymbol] Backtest [{i+1}/{len(candidates)}] {symbol}: "
                           f"score={score:.2f}, cycles={trades}, return={ret:.1f}%, WR={wr:.1f}%")
                results_summary.append((symbol, score, trades, ret, wr))

                # Update progress with result
                if session_id:
                    bt_results = self._progress.get(session_id, {}).get("results", [])
                    bt_results.append({
                        "symbol": symbol, "score": round(score, 1),
                        "cycles": trades, "return": round(ret, 2), "win_rate": round(wr, 1),
                    })
                    self._update_progress(
                        session_id, "backtesting",
                        f"{len(candidates)}개 후보 백테스트 중... ({i+1}/{len(candidates)})",
                        total=len(candidates), current=i+1, results=bt_results,
                    )

                if score > best_score:
                    best_score = score
                    best_symbol = symbol

            except Exception as e:
                logger.warning(f"[AISymbol] Backtest error for {symbol}: {e}")
                continue

        # Log top 5 results
        if results_summary:
            results_summary.sort(key=lambda x: x[1], reverse=True)
            top5 = results_summary[:5]
            logger.info(f"[AISymbol] Top 5: {[(s, f'{sc:.1f}', t, f'{r:.1f}%') for s, sc, t, r in top5]}")

        return best_symbol

    def _calculate_score(self, result: dict) -> float:
        """Calculate a composite score from backtest results.

        Reliability-weighted: low trade count penalizes the score heavily.
        - 1-2 trades: 20-40% of base score (unreliable)
        - 3-4 trades: 50-70% of base score (low confidence)
        - 5-9 trades: 80-95% of base score (moderate)
        - 10+ trades: 100%+ of base score (reliable, with bonus)
        """
        total_return = float(str(result.get("total_return", "0")).replace('%', '').replace(',', ''))
        win_rate = float(str(result.get("win_rate", "0")).replace('%', ''))
        total_trades = int(result.get("total_cycles", 0))

        if total_trades == 0:
            return float('-inf')

        # Base score: return + win_rate contribution
        base_score = (total_return * 0.5) + (win_rate * 0.3)

        # Reliability multiplier based on trade count
        if total_trades <= 2:
            reliability = 0.2 + (total_trades * 0.1)   # 0.3 ~ 0.4
        elif total_trades <= 4:
            reliability = 0.4 + ((total_trades - 2) * 0.15)  # 0.55 ~ 0.7
        elif total_trades <= 9:
            reliability = 0.7 + ((total_trades - 4) * 0.06)  # 0.76 ~ 1.0
        else:
            reliability = 1.0 + (min(total_trades, 30) - 10) * 0.01  # 1.0 ~ 1.2 bonus

        score = base_score * reliability
        return score

    async def _call_claude(self, context_data: dict, prompt: str) -> Optional[str]:
        """Call Claude CLI with context file, reusing stock_search.py pattern."""
        claude_path = os.path.expanduser("~/.claude/local/claude")
        if not os.path.exists(claude_path):
            claude_path = "claude"  # fallback to PATH

        context_file = None
        try:
            # Write context to temp file
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', prefix='ai_symbol_',
                dir='/tmp', delete=False, encoding='utf-8'
            ) as f:
                json.dump(context_data, f, ensure_ascii=False)
                context_file = f.name

            full_prompt = (
                f"Read the context file at `{context_file}` using the Read tool. "
                f"{prompt}"
            )

            cmd = [
                claude_path,
                "-p", full_prompt,
                "--output-format", "json",
                "--agent", "symbol-evaluator",
                "--permission-mode", "bypassPermissions",
            ]

            env = os.environ.copy()
            for key in ["NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_APP_INSTANCE"]:
                env.pop(key, None)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/home/hcpark/antigravity",
                env=env,
                start_new_session=True,
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                err_msg = stderr.decode().strip() if stderr else ""
                logger.error(f"[AISymbol] Claude CLI error (rc={proc.returncode}): {err_msg[:200]}")
                return None

            raw_out = stdout.decode().strip()
            if not raw_out:
                return None

            # Parse JSON output format from Claude CLI
            try:
                output = json.loads(raw_out)
                response_text = output.get("result", raw_out)
            except json.JSONDecodeError:
                response_text = raw_out

            # Try to extract JSON from response text
            json_match = self._extract_json(response_text)
            return json_match if json_match else response_text

        except asyncio.TimeoutError:
            logger.error("[AISymbol] Claude CLI timeout (120s)")
            if 'proc' in locals():
                proc.kill()
            return None
        except Exception as e:
            logger.error(f"[AISymbol] Claude CLI call error: {e}")
            return None
        finally:
            if context_file and os.path.exists(context_file):
                try:
                    os.unlink(context_file)
                except OSError:
                    pass

    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON object from text that may contain markdown or other content."""
        import re
        # Try to find JSON block in code fence
        code_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if code_match:
            return code_match.group(1)
        # Try to find raw JSON object
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                json.loads(json_match.group(0))
                return json_match.group(0)
            except json.JSONDecodeError:
                pass
        return None

    def _slim_stock_data(self, stocks: list) -> list:
        """Extract only essential fields to reduce context size."""
        slim = []
        for s in stocks:
            slim.append({
                "code": s.get("code", ""),
                "name": s.get("name", ""),
                "marketName": s.get("marketName", ""),
                "upName": s.get("upName", ""),
                "lastPrice": s.get("lastPrice", ""),
            })
        return slim

    # ──────────────────────────────────────────────────────────
    # Group-level pipeline coordination
    # ──────────────────────────────────────────────────────────

    async def request_group_evaluation(self, session_info: dict):
        """
        Entry point for group-level AI symbol selection.
        Called by LiveTradingEngine when a grouped session completes a cycle.
        Registers the session and starts a collection timer for batch processing.
        """
        group_id = session_info["group_id"]
        session_id = session_info["session_id"]

        # Ensure group lock exists
        if group_id not in self._group_locks:
            self._group_locks[group_id] = asyncio.Lock()

        # If group pipeline is already running, skip (will retry on next cycle)
        if self._group_locks[group_id].locked():
            logger.info(f"[AISymbol] Group {group_id[:8]} pipeline running. "
                        f"Skipping session {session_id[:8]}")
            return

        # Register session as pending
        if group_id not in self._group_pending:
            self._group_pending[group_id] = {}
        self._group_pending[group_id][session_id] = session_info

        pending_count = len(self._group_pending[group_id])
        logger.info(f"[AISymbol] Session {session_id[:8]} registered for group "
                    f"{group_id[:8]} evaluation ({pending_count} pending)")

        self._update_progress(session_id, "waiting",
                              f"그룹 평가 대기 중... ({pending_count}개 세션)")

        # Start or restart the collection timer
        self._restart_collection_timer(group_id)

    def _restart_collection_timer(self, group_id: str):
        """
        (Re)start the collection window timer.
        First session: 30s wait. Additional sessions: 10s (shorter).
        """
        # Cancel existing timer
        if group_id in self._group_timers:
            self._group_timers[group_id].cancel()

        pending_count = len(self._group_pending.get(group_id, {}))
        wait = self.GROUP_EXTEND_WINDOW if pending_count > 1 else self.GROUP_COLLECT_WINDOW

        logger.info(f"[AISymbol] Group {group_id[:8]} timer set: {wait}s "
                    f"({pending_count} pending)")

        async def _fire():
            await asyncio.sleep(wait)
            await self._run_group_pipeline(group_id)

        self._group_timers[group_id] = asyncio.create_task(_fire())

    async def _run_group_pipeline(self, group_id: str):
        """
        Core group-level AI symbol selection pipeline.
        Flow:
          1. Snapshot & clear pending sessions
          2. Fetch market data ONCE
          3. EVALUATE each session's current symbol
          4. FIND candidates ONCE for all sessions needing switches
          5. COMPARE via backtest ONCE
          6. ASSIGN top N candidates to N sessions
          7. Execute symbol switches
        """
        lock = self._group_locks.get(group_id)
        if not lock:
            return

        async with lock:
            # 1. Snapshot and clear pending
            pending = self._group_pending.pop(group_id, {})
            self._group_timers.pop(group_id, None)

            if not pending:
                return

            session_infos = list(pending.values())
            session_ids = [s["session_id"] for s in session_infos]
            first = session_infos[0]

            logger.info(f"[AISymbol] Group pipeline START for {group_id[:8]}, "
                        f"{len(session_ids)} sessions: {[s[:8] for s in session_ids]}")

            # Update all sessions progress
            for sid in session_ids:
                self._update_progress(sid, "group_pipeline",
                                      f"그룹 파이프라인 시작 ({len(session_ids)}개 세션)")

            try:
                # 2. Fetch market data ONCE
                for sid in session_ids:
                    self._update_progress(sid, "market_data", "시장 데이터 수집 중...")

                api_url, token = await self._get_token(first["account_id"])
                if not token:
                    self._fail_group(session_ids, "토큰 획득 실패")
                    return

                stock_data, ranking_data = await self._fetch_market_data(api_url, token)
                if not stock_data:
                    self._fail_group(session_ids, "시장 데이터 수집 실패")
                    return

                # 3. EVALUATE each session's current symbol
                for sid in session_ids:
                    self._update_progress(sid, "evaluating",
                                          f"{len(session_ids)}개 세션 적합성 평가 중...")

                need_switch = []
                for info in session_infos:
                    sid = info["session_id"]
                    self._update_progress(sid, "evaluating",
                                          f"현재 종목({info['current_symbol']}) 적합성 평가 중...")

                    should_switch, eval_reason = await self._check_current_symbol(
                        info["current_symbol"], info["search_conditions"],
                        stock_data, ranking_data
                    )

                    if should_switch:
                        info["_eval_reason"] = eval_reason  # Save reason for later use
                        need_switch.append(info)
                        logger.info(f"[AISymbol] Session {sid[:8]} "
                                    f"({info['current_symbol']}): NEEDS SWITCH - {eval_reason}")
                    else:
                        reason = f"현재 종목({info['current_symbol']}) 유지: {eval_reason}" if eval_reason else f"현재 종목({info['current_symbol']}) 유지 - 조건 부합"
                        logger.info(f"[AISymbol] Session {sid[:8]} "
                                    f"({info['current_symbol']}): KEEPING - {eval_reason}")
                        self._update_progress(sid, "done", reason)
                        self._save_history(sid, group_id, "kept",
                                           old_symbol=info["current_symbol"],
                                           old_symbol_name=info.get("current_symbol_name"),
                                           search_conditions=info["search_conditions"],
                                           evaluation_reason=reason)
                        self._clear_progress(sid)

                N = len(need_switch)
                if N == 0:
                    logger.info(f"[AISymbol] Group {group_id[:8]}: All sessions keeping current symbols")
                    return

                logger.info(f"[AISymbol] Group {group_id[:8]}: {N} sessions need switching")

                # 4. FIND candidates ONCE
                # Excluded: group symbols (non-pending) + all current symbols in group
                excluded = await self._get_group_symbols(group_id, exclude_ids=set(session_ids))
                for info in session_infos:
                    excluded.add(info["current_symbol"])

                for info in need_switch:
                    self._update_progress(info["session_id"], "finding",
                                          f"AI가 후보 종목 탐색 중... ({N}개 세션 교체 필요)")

                candidates = await self._find_candidates(
                    current_symbol=",".join(s["current_symbol"] for s in need_switch),
                    search_conditions=first["search_conditions"],
                    stock_data=stock_data,
                    ranking_data=ranking_data,
                    excluded_symbols=excluded,
                )

                if not candidates:
                    logger.warning(f"[AISymbol] Group {group_id[:8]}: No candidates found")
                    for info in need_switch:
                        reason = "후보 종목 없음 - 현재 종목 유지"
                        self._update_progress(info["session_id"], "done", reason)
                        self._save_history(info["session_id"], group_id, "no_candidates",
                                           old_symbol=info["current_symbol"],
                                           old_symbol_name=info.get("current_symbol_name"),
                                           search_conditions=info["search_conditions"],
                                           evaluation_reason=reason)
                        self._clear_progress(info["session_id"])
                    return

                logger.info(f"[AISymbol] Group {group_id[:8]}: Found {len(candidates)} "
                            f"candidates for {N} switches")

                # 5. COMPARE via backtest ONCE (broadcast progress to all sessions)
                switch_sids = [s["session_id"] for s in need_switch]
                for sid in switch_sids:
                    self._update_progress(sid, "backtesting",
                                          f"{len(candidates)}개 후보 백테스트 중... (0/{len(candidates)})",
                                          total=len(candidates), current=0, results=[])

                ranked = await self._compare_symbols_group(
                    candidates, first["strategy_name"], first["strategy_config"],
                    first["initial_capital"], session_ids=switch_sids,
                )

                # 6. ASSIGN top N candidates to N sessions
                assignments = self._assign_candidates(ranked, need_switch, excluded)

                # 7. Execute switches
                bt_results = []
                for s_sym, s_score, s_trades, s_ret, s_wr in ranked[:10]:
                    bt_results.append({"symbol": s_sym, "score": round(s_score, 1),
                                       "cycles": s_trades, "return": round(s_ret, 2),
                                       "win_rate": round(s_wr, 1)})

                from .live_manager import live_manager
                for sid, new_symbol in assignments.items():
                    info = next(s for s in need_switch if s["session_id"] == sid)
                    old_symbol = info["current_symbol"]

                    if new_symbol:
                        # Find symbol name from stock data
                        new_name = new_symbol
                        for s in stock_data:
                            if s.get("code") == new_symbol:
                                new_name = s.get("name", new_symbol)
                                break

                        self._update_progress(sid, "switching",
                                              f"종목 전환 중: {old_symbol} → {new_symbol}",
                                              new_symbol=new_symbol)
                        await live_manager.switch_session_symbol(
                            sid, new_symbol, new_symbol_name=new_name)
                        eval_reason = info.get("_eval_reason", "")
                        reason = (f"[교체 사유] {eval_reason}\n"
                                  f"[결과] {old_symbol} → {new_symbol} ({new_name})")
                        self._update_progress(sid, "done",
                                              f"종목 전환 완료: {old_symbol} → {new_symbol}",
                                              new_symbol=new_symbol)
                        self._save_history(sid, group_id, "switched",
                                           old_symbol=old_symbol,
                                           old_symbol_name=info.get("current_symbol_name"),
                                           new_symbol=new_symbol, new_symbol_name=new_name,
                                           search_conditions=info["search_conditions"],
                                           evaluation_reason=reason,
                                           backtest_results=bt_results)
                        logger.info(f"[AISymbol] Group switch: {sid[:8]} "
                                    f"{old_symbol} -> {new_symbol}")
                    else:
                        eval_reason = info.get("_eval_reason", "")
                        reason = (f"[교체 사유] {eval_reason}\n"
                                  f"[결과] 적합한 후보 없음 - 현재 종목({old_symbol}) 유지")
                        self._update_progress(sid, "done",
                                              f"적합한 후보 없음 - 현재 종목({old_symbol}) 유지")
                        self._save_history(sid, group_id, "no_candidates",
                                           old_symbol=old_symbol,
                                           old_symbol_name=info.get("current_symbol_name"),
                                           search_conditions=info["search_conditions"],
                                           evaluation_reason=reason,
                                           backtest_results=bt_results)

                    self._clear_progress(sid)

                logger.info(f"[AISymbol] Group pipeline COMPLETE for {group_id[:8]}")

            except Exception as e:
                logger.error(f"[AISymbol] Group pipeline FAILED: {e}", exc_info=True)
                self._fail_group(session_ids, f"파이프라인 오류: {str(e)[:100]}")

    async def _compare_symbols_group(
        self,
        candidates: List[str],
        strategy_name: str,
        strategy_config: dict,
        initial_capital: float,
        session_ids: List[str] = None,
    ) -> List[tuple]:
        """
        Compare candidates via backtest. Returns ranked list:
        [(symbol, score, trades, return_pct), ...] sorted by score descending.
        Broadcasts progress to all sessions in the group.
        """
        from ..api.mock_strategies import _run_unified_backtest

        results_summary = []

        for i, symbol in enumerate(candidates):
            try:
                config = dict(strategy_config)
                config['symbol'] = symbol

                # Update progress for ALL sessions
                progress_msg = (f"{len(candidates)}개 후보 백테스트 중... "
                                f"({i+1}/{len(candidates)}) - {symbol}")
                for sid in (session_ids or []):
                    prog = self._progress.get(sid, {})
                    self._update_progress(
                        sid, "backtesting", progress_msg,
                        total=len(candidates), current=i+1,
                        results=prog.get("results", []),
                    )

                result = await _run_unified_backtest(
                    strategy_id=strategy_name,
                    configs=[config],
                    symbol=symbol,
                    interval="1m",
                    days=14,
                    from_date=None,
                    initial_capital=int(initial_capital),
                    execution_mode="single",
                    optimize_mode=True,
                )

                if "error" in result:
                    logger.warning(f"[AISymbol] Backtest failed for {symbol}: {result['error']}")
                    continue

                score = self._calculate_score(result)
                trades = int(result.get("total_cycles", 0))
                ret = float(str(result.get("total_return", "0")).replace('%', '').replace(',', ''))
                wr = float(str(result.get("win_rate", "0")).replace('%', ''))

                logger.info(f"[AISymbol] Group Backtest [{i+1}/{len(candidates)}] {symbol}: "
                            f"score={score:.2f}, cycles={trades}, return={ret:.1f}%, WR={wr:.1f}%")
                results_summary.append((symbol, score, trades, ret, wr))

                # Update progress with result for ALL sessions
                bt_entry = {
                    "symbol": symbol, "score": round(score, 1),
                    "cycles": trades, "return": round(ret, 2), "win_rate": round(wr, 1),
                }
                for sid in (session_ids or []):
                    bt_results = self._progress.get(sid, {}).get("results", [])
                    bt_results.append(bt_entry)
                    self._update_progress(
                        sid, "backtesting",
                        f"{len(candidates)}개 후보 백테스트 중... ({i+1}/{len(candidates)})",
                        total=len(candidates), current=i+1, results=bt_results,
                    )

            except Exception as e:
                logger.warning(f"[AISymbol] Backtest error for {symbol}: {e}")
                continue

        # Sort by score descending
        results_summary.sort(key=lambda x: x[1], reverse=True)

        if results_summary:
            top5 = results_summary[:5]
            logger.info(f"[AISymbol] Group Top 5: "
                        f"{[(s, f'{sc:.1f}', t, f'{r:.1f}%', f'WR{w:.0f}%') for s, sc, t, r, w in top5]}")

        return results_summary

    def _assign_candidates(
        self,
        ranked: List[tuple],
        sessions_needing_switch: List[dict],
        excluded_symbols: set,
    ) -> Dict[str, Optional[str]]:
        """
        Assign top N ranked candidates to N sessions needing switches.
        Each candidate is assigned only once (no duplicates).
        """
        assignments = {}
        used = set(excluded_symbols)

        # Remove current symbols of sessions being switched (they're being vacated)
        for info in sessions_needing_switch:
            used.discard(info["current_symbol"])

        for info in sessions_needing_switch:
            sid = info["session_id"]
            assigned = None
            for symbol, score, *_ in ranked:
                if symbol not in used and score > float('-inf'):
                    assigned = symbol
                    used.add(symbol)
                    break
            assignments[sid] = assigned

            if not assigned:
                logger.warning(f"[AISymbol] No viable candidate for session {sid[:8]}")

        return assignments

    def _fail_group(self, session_ids: List[str], message: str):
        """Mark all sessions in the group as failed."""
        for sid in session_ids:
            self._update_progress(sid, "error", message)
            self._clear_progress(sid)
