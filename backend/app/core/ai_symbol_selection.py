"""
AI Symbol Selection Service

AI-driven symbol rotation for live trading sessions.
Pipeline:
  1. EVALUATE current symbol against search conditions
  2. FIND up to 20 candidates matching conditions (Claude CLI)
  3. Add current symbol as competitor ONLY IF it still meets conditions
  4. COMPARE all via backtest (14-day) with optional parameter optimization
  5. SELECT best — if current symbol wins, keep; otherwise switch
"""

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from .constants import Side

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

        # Binance volume spike cache (rolling 24h volume snapshots)
        self._binance_volume_cache: Dict[str, float] = {}   # symbol → previous quoteVolume
        self._binance_cache_time: Optional[datetime] = None  # when cache was last updated

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
        existing = self._progress.get(session_id, {})
        # Preserve accumulated results unless explicitly overridden
        if "results" not in kwargs and "results" in existing:
            kwargs["results"] = existing["results"]
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
        from sqlalchemy import func

        try:
            db = SessionLocal()

            # Dedup: skip if same session+action+old+new was saved within last 60 seconds
            cutoff = datetime.now() - timedelta(seconds=60)
            existing = db.query(AISymbolHistory).filter(
                AISymbolHistory.session_id == session_id,
                AISymbolHistory.action == action,
                AISymbolHistory.old_symbol == old_symbol,
                AISymbolHistory.new_symbol == new_symbol,
                AISymbolHistory.created_at >= cutoff,
            ).first()
            if existing:
                logger.info(f"[AISymbol] History dedup: {session_id[:8]} {action} "
                            f"{old_symbol} -> {new_symbol or '(kept)'} (skipped, recent duplicate)")
                db.close()
                return

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
        ai_optimize_params: dict = None,
        is_futures: bool = False,
        exchange_name: str = "Kiwoom",
    ) -> Optional[str]:
        """
        AI symbol selection pipeline — competitive mode with condition gate.
        Returns new symbol code if a better candidate is found, None to keep current.

        Pipeline:
          1. Fetch market data
          2. EVALUATE current symbol against search conditions
          3. FIND candidates matching conditions
          4. Current symbol competes ONLY IF it still meets conditions
          5. COMPARE via backtest → SELECT best
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

            # Step 2: Fetch market data (exchange-specific)
            self._update_progress(session_id, "market_data", "시장 데이터 수집 중...")
            _ex = (exchange_name or "").lower()
            is_binance = "binance" in _ex

            if is_binance:
                stock_data, ranking_data = await self._fetch_binance_market_data(is_futures=is_futures)
            else:
                api_url, token = await self._get_token(account_id)
                if not token:
                    logger.error(f"[AISymbol] Failed to get token for account {account_id}")
                    self._update_progress(session_id, "error", "토큰 획득 실패")
                    self._clear_progress(session_id)
                    return None
                stock_data, ranking_data = await self._fetch_market_data(api_url, token)

            if not stock_data:
                logger.error("[AISymbol] Failed to fetch market data")
                self._update_progress(session_id, "error", "시장 데이터 수집 실패")
                self._clear_progress(session_id)
                return None

            # Step 3: EVALUATE — check if current symbol still matches conditions
            self._update_progress(session_id, "evaluating",
                                  f"현재 종목({current_symbol}) 조건 충족 여부 평가 중...")
            should_switch, eval_reason = await self._check_current_symbol(
                current_symbol, search_conditions, stock_data, ranking_data,
            )
            current_meets_conditions = not should_switch
            logger.info(f"[AISymbol] EVALUATE {current_symbol}: "
                        f"meets_conditions={current_meets_conditions}, reason={eval_reason[:200]}")

            # Step 4: Find candidate symbols (current symbol excluded from AI search)
            self._update_progress(session_id, "finding", "AI가 후보 종목 탐색 중...")
            candidates = await self._find_candidates(
                current_symbol, search_conditions, stock_data, ranking_data,
                excluded_symbols=excluded_symbols,
                is_futures=is_futures,
            )

            # Step 5: Build competitor list — current symbol only if it meets conditions
            if current_meets_conditions:
                current_entry = {"code": current_symbol, "name": _sym_name, "_is_current": True}
                if is_futures:
                    current_direction = strategy_config.get("position_side", "long")
                    current_entry["direction"] = current_direction
                all_competitors = [current_entry] + (candidates or [])
                logger.info(f"[AISymbol] Current symbol PASSES conditions — competing with {len(candidates or [])} candidates")
            else:
                all_competitors = candidates or []
                logger.info(f"[AISymbol] Current symbol FAILS conditions ({eval_reason[:100]}) — "
                            f"excluded from competition. {len(all_competitors)} candidates only.")

            if not all_competitors:
                reason = f"현재 종목 조건 미충족 + 후보 없음 — 현재 종목 유지\n[평가] {eval_reason}"
                logger.warning(f"[AISymbol] No competitors at all. Keeping current symbol.")
                self._update_progress(session_id, "done", reason)
                self._save_history(session_id, group_id, "kept",
                                   old_symbol=current_symbol,
                                   old_symbol_name=_sym_name,
                                   search_conditions=search_conditions,
                                   evaluation_reason=reason)
                self._clear_progress(session_id)
                return None

            codes = [c["code"] for c in all_competitors]
            logger.info(f"[AISymbol] Competing {len(all_competitors)} symbols: {codes}")

            # Step 6: Generate optimization ranges via AI (if params selected)
            optimize_param_names = ai_optimize_params.get("params", []) if ai_optimize_params else []
            optimize_params = {}
            if optimize_param_names and isinstance(optimize_param_names, list) and len(optimize_param_names) > 0:
                self._update_progress(session_id, "optimizing",
                                      f"AI가 {len(optimize_param_names)}개 파라미터 최적화 범위 결정 중...")
                sample = candidates[0] if candidates else current_symbol
                optimize_params = await self._generate_optimize_ranges(
                    optimize_param_names, strategy_name, strategy_config, sample,
                )
                if optimize_params:
                    logger.info(f"[AISymbol] AI-generated optimize ranges: {optimize_params}")
                else:
                    logger.warning("[AISymbol] AI failed to generate ranges, proceeding without optimization")

            # Step 7: Backtest ALL competitors
            if optimize_params:
                import itertools
                keys = list(optimize_params.keys())
                values = list(optimize_params.values())
                combos = list(itertools.product(*values))
                total_bt = len(all_competitors) * len(combos)
                logger.info(f"[AISymbol] Optimization mode: {len(all_competitors)} symbols × "
                            f"{len(combos)} param combos = {total_bt} backtests")
                self._update_progress(session_id, "backtesting",
                                      f"최적화 백테스트 중... (0/{total_bt}) "
                                      f"[{len(all_competitors)}종목 × {len(combos)}조합]",
                                      total=total_bt, current=0, results=[])
            else:
                total_bt = len(all_competitors)
                self._update_progress(session_id, "backtesting",
                                      f"{len(all_competitors)}개 종목 백테스트 중... (0/{total_bt})",
                                      total=total_bt, current=0, results=[])

            compare_results = await self._compare_symbols(
                all_competitors, strategy_name, strategy_config, initial_capital,
                session_id=session_id,
                optimize_params=optimize_params,
                exchange_name=exchange_name,
            )
            if not compare_results:
                bt_results = self._progress.get(session_id, {}).get("results", [])
                reason = "백테스트 결과 없음 - 현재 종목 유지"
                logger.warning("[AISymbol] No backtest results. Keeping current symbol.")
                self._update_progress(session_id, "done", reason)
                self._save_history(session_id, group_id, "kept",
                                   old_symbol=current_symbol,
                                   old_symbol_name=_sym_name,
                                   search_conditions=search_conditions,
                                   evaluation_reason=reason,
                                   backtest_results=bt_results)
                self._clear_progress(session_id)
                return None

            # Step 8: AI selects best symbol+params from backtest results
            best_symbol, best_params, select_reason = await self._ai_select_best(
                compare_results, search_conditions, strategy_name,
                current_symbol, session_id=session_id,
            )

            if not best_symbol:
                bt_results = self._progress.get(session_id, {}).get("results", [])
                reason = "AI 최종 선택 실패 - 현재 종목 유지"
                logger.warning("[AISymbol] AI final selection failed. Keeping current symbol.")
                self._update_progress(session_id, "done", reason)
                self._save_history(session_id, group_id, "kept",
                                   old_symbol=current_symbol,
                                   old_symbol_name=_sym_name,
                                   search_conditions=search_conditions,
                                   evaluation_reason=reason,
                                   backtest_results=bt_results)
                self._clear_progress(session_id)
                return None

            bt_results = self._progress.get(session_id, {}).get("results", [])
            params_str = f" (params: {best_params})" if best_params else ""

            # Step 9: Check if current symbol won the competition
            if best_symbol == current_symbol:
                # Current symbol is the best — keep it, but apply optimized params if changed
                params_changed = False
                if best_params:
                    for k, v in best_params.items():
                        if strategy_config.get(k) != v:
                            params_changed = True
                            break

                if params_changed:
                    reason = f"{current_symbol} 유지 (경쟁 1위){params_str}"
                    if select_reason:
                        reason += f"\n[선정 사유] {select_reason}"
                    done_msg = f"종목 유지({current_symbol}) - 파라미터 최적화: {best_params}"
                    logger.info(f"[AISymbol] Current symbol WON with new params: {best_params}")
                    self._update_progress(session_id, "done", done_msg,
                                          optimized_params=best_params)
                    self._save_history(session_id, group_id, "param_optimized",
                                       old_symbol=current_symbol,
                                       old_symbol_name=_sym_name,
                                       new_symbol=current_symbol,
                                       search_conditions=search_conditions,
                                       evaluation_reason=reason,
                                       backtest_results=bt_results)
                    self._clear_progress(session_id)
                    self._last_result = {"symbol": None, "optimized_params": best_params}
                    return None  # Keep current, but caller applies optimized params
                else:
                    reason = f"{current_symbol} 유지 (경쟁 1위)"
                    if select_reason:
                        reason += f"\n[선정 사유] {select_reason}"
                    done_msg = f"종목 유지({current_symbol}) - 최고 점수"
                    logger.info(f"[AISymbol] Current symbol WON competition. Keeping.")
                    self._update_progress(session_id, "done", done_msg)
                    self._save_history(session_id, group_id, "kept",
                                       old_symbol=current_symbol,
                                       old_symbol_name=_sym_name,
                                       search_conditions=search_conditions,
                                       evaluation_reason=reason,
                                       backtest_results=bt_results)
                    self._clear_progress(session_id)
                    self._last_result = {"symbol": None, "optimized_params": None}
                    return None

            # Step 10: A new symbol won — switch
            # Find new symbol name from competitors list
            _new_sym_name = best_symbol
            for comp in all_competitors:
                if comp.get("code") == best_symbol and comp.get("name"):
                    _new_sym_name = comp["name"]
                    break

            reason = f"[결과] {current_symbol} → {best_symbol}{params_str}"
            if select_reason:
                reason += f"\n[선정 사유] {select_reason}"
            logger.info(f"[AISymbol] Pipeline COMPLETE: {current_symbol} -> {best_symbol}{params_str}")
            done_msg = f"종목 전환 완료: {current_symbol} → {best_symbol}"
            if best_params:
                done_msg += f" (최적 파라미터: {best_params})"
            self._update_progress(session_id, "done", done_msg,
                                  new_symbol=best_symbol, optimized_params=best_params)
            self._save_history(session_id, group_id, "switched",
                               old_symbol=current_symbol,
                               old_symbol_name=_sym_name,
                               new_symbol=best_symbol,
                               new_symbol_name=_new_sym_name,
                               search_conditions=search_conditions,
                               evaluation_reason=reason,
                               backtest_results=bt_results)
            self._last_result = {"symbol": best_symbol, "symbol_name": _new_sym_name, "optimized_params": best_params}
            return best_symbol

        except Exception as e:
            logger.error(f"[AISymbol] Pipeline FAILED: {e}", exc_info=True)
            self._update_progress(session_id, "error", f"파이프라인 오류: {str(e)[:100]}")
            self._clear_progress(session_id)
            return None

    async def _optimize_current_symbol(
        self,
        session_id: str,
        group_id: str,
        current_symbol: str,
        current_symbol_name: str,
        search_conditions: str,
        eval_reason: str,
        strategy_name: str,
        strategy_config: dict,
        initial_capital: float,
        optimize_param_names: list,
        is_futures: bool = False,
        candidates_for_range=None,
        exchange_name: str = "Kiwoom",
    ) -> Optional[str]:
        """Optimize parameters for the CURRENT symbol (no symbol switch).

        Runs when the symbol is kept but ai_optimize_params are configured.
        Returns None (symbol not changed) but stores optimized params in _last_result.
        """
        import itertools

        self._update_progress(session_id, "optimizing",
                              f"현재 종목({current_symbol}) 파라미터 최적화 범위 결정 중...")

        # Generate optimization ranges using AI
        sample_symbol = candidates_for_range or current_symbol
        optimize_params = await self._generate_optimize_ranges(
            optimize_param_names, strategy_name, strategy_config, sample_symbol,
        )
        if not optimize_params:
            reason = f"현재 종목({current_symbol}) 유지: {eval_reason or '조건 부합'}\n[최적화] 범위 생성 실패 - 현재 파라미터 유지"
            logger.warning(f"[AISymbol] Param optimization: failed to generate ranges for {current_symbol}")
            self._update_progress(session_id, "done", reason)
            self._save_history(session_id, group_id, "kept",
                               old_symbol=current_symbol,
                               old_symbol_name=current_symbol_name,
                               search_conditions=search_conditions,
                               evaluation_reason=reason)
            self._clear_progress(session_id)
            self._last_result = {"symbol": None, "optimized_params": None}
            return None

        # If position_side is in the optimization ranges but already set in strategy_config,
        # lock it to the current direction (don't flip long↔short during re-optimization)
        current_direction = strategy_config.get("position_side")
        if current_direction and "position_side" in optimize_params:
            optimize_params["position_side"] = [current_direction]
            logger.info(f"[AISymbol] Param optimization: locking position_side to [{current_direction}] "
                        f"(preserving current direction)")

        logger.info(f"[AISymbol] Param optimization ranges for {current_symbol}: {optimize_params}")

        # Build candidate as current symbol only
        cand = {"code": current_symbol}
        if is_futures:
            direction = current_direction
            if direction:
                cand["direction"] = direction

        # Calculate total backtests
        opt_keys = list(optimize_params.keys())
        opt_values = list(optimize_params.values())
        combos = list(itertools.product(*opt_values))
        total_bt = len(combos)

        self._update_progress(session_id, "backtesting",
                              f"현재 종목({current_symbol}) 파라미터 최적화 중... (0/{total_bt}) "
                              f"[{len(combos)}개 조합]",
                              total=total_bt, current=0, results=[])

        # Run backtest with optimization on current symbol
        compare_results = await self._compare_symbols(
            [cand], strategy_name, strategy_config, initial_capital,
            session_id=session_id,
            optimize_params=optimize_params,
            exchange_name=exchange_name,
        )

        if not compare_results:
            bt_results = self._progress.get(session_id, {}).get("results", [])
            reason = f"현재 종목({current_symbol}) 유지: {eval_reason or '조건 부합'}\n[최적화] 백테스트 결과 없음 - 현재 파라미터 유지"
            self._update_progress(session_id, "done", reason)
            self._save_history(session_id, group_id, "kept",
                               old_symbol=current_symbol,
                               old_symbol_name=current_symbol_name,
                               search_conditions=search_conditions,
                               evaluation_reason=reason,
                               backtest_results=bt_results)
            self._clear_progress(session_id)
            self._last_result = {"symbol": None, "optimized_params": None}
            return None

        # Best result is the top-scoring parameter combination for current symbol
        best = compare_results[0]
        best_params = best.get("params")

        # Check if optimized params actually differ from current
        params_changed = False
        if best_params:
            for k, v in best_params.items():
                if strategy_config.get(k) != v:
                    params_changed = True
                    break

        bt_results = self._progress.get(session_id, {}).get("results", [])
        params_str = f" (params: {best_params})" if best_params else ""

        if params_changed and best_params:
            reason = (f"현재 종목({current_symbol}) 유지: {eval_reason or '조건 부합'}\n"
                      f"[최적화] 파라미터 변경: {params_str}")
            done_msg = f"종목 유지({current_symbol}) - 파라미터 최적화 완료: {best_params}"
            logger.info(f"[AISymbol] Param optimization COMPLETE for {current_symbol}: {best_params}")
            self._update_progress(session_id, "done", done_msg,
                                  optimized_params=best_params)
            self._save_history(session_id, group_id, "param_optimized",
                               old_symbol=current_symbol,
                               old_symbol_name=current_symbol_name,
                               new_symbol=current_symbol,
                               search_conditions=search_conditions,
                               evaluation_reason=reason,
                               backtest_results=bt_results)
            self._clear_progress(session_id)
            # Store optimized params for caller to apply
            self._last_result = {"symbol": None, "optimized_params": best_params}
        else:
            reason = (f"현재 종목({current_symbol}) 유지: {eval_reason or '조건 부합'}\n"
                      f"[최적화] 현재 파라미터가 이미 최적 - 변경 없음")
            done_msg = f"종목 유지({current_symbol}) - 현재 파라미터가 최적"
            logger.info(f"[AISymbol] Param optimization: current params already optimal for {current_symbol}")
            self._update_progress(session_id, "done", done_msg)
            self._save_history(session_id, group_id, "kept",
                               old_symbol=current_symbol,
                               old_symbol_name=current_symbol_name,
                               search_conditions=search_conditions,
                               evaluation_reason=reason,
                               backtest_results=bt_results)
            self._clear_progress(session_id)
            self._last_result = {"symbol": None, "optimized_params": None}

        return None  # Symbol not changed

    async def _get_group_symbols(self, group_id: str, exclude_ids: set = None) -> set:
        """Get symbols used by other sessions in the same group (all non-STOPPED statuses + STOPPED with same group).

        Includes STOPPED sessions to prevent symbol swaps when multiple sessions
        restart simultaneously (neither is RUNNING yet, so without STOPPED inclusion
        they can't see each other's symbols).
        """
        from ..db.session import SessionLocal
        from ..models.live_trading import LiveBotSession

        _exclude = exclude_ids or set()

        def _query():
            db = SessionLocal()
            try:
                sessions = db.query(LiveBotSession).filter(
                    LiveBotSession.group_id == group_id,
                    LiveBotSession.is_active == True,
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

    async def _fetch_binance_market_data(self, is_futures: bool = False) -> tuple:
        """Fetch Binance market data via public REST API (no auth needed).

        Returns (stock_data, ranking_data) in a format compatible with Kiwoom data:
          stock_data: [{"code": "BTCUSDT", "name": "BTCUSDT", "lastPrice": "...", ...}]
          ranking_data: {"volume_top": [...], "change_top": [...], "change_bottom": [...]}
        """
        from ..core.http_client import HttpClientManager

        try:
            client = HttpClientManager.get_instance().get_client()

            if is_futures:
                url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            else:
                url = "https://api.binance.com/api/v3/ticker/24hr"

            response = await client.get(url, timeout=15)
            if response.status_code != 200:
                logger.error(f"[AISymbol] Binance ticker API error: {response.status_code}")
                return None, None

            tickers = response.json()

            # Filter USDT pairs only, exclude low-volume noise
            usdt_tickers = [
                t for t in tickers
                if t.get("symbol", "").endswith("USDT")
                and float(t.get("quoteVolume", 0)) > 100000  # min $100k volume
            ]

            # Build stock_data (compatible with Kiwoom format)
            stock_data = []
            for t in usdt_tickers:
                symbol = t["symbol"]
                price_change_pct = float(t.get("priceChangePercent", 0))
                stock_data.append({
                    "code": symbol,
                    "name": symbol.replace("USDT", ""),
                    "lastPrice": t.get("lastPrice", "0"),
                    "priceChangePercent": f"{price_change_pct:+.2f}%",
                    "quoteVolume": t.get("quoteVolume", "0"),
                    "marketName": "Futures" if is_futures else "Spot",
                })

            # Build ranking_data
            sorted_by_volume = sorted(usdt_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
            sorted_by_change = sorted(usdt_tickers, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)

            def _ticker_to_rank(t):
                return {
                    "code": t["symbol"],
                    "name": t["symbol"].replace("USDT", ""),
                    "lastPrice": t.get("lastPrice", "0"),
                    "priceChangePercent": f"{float(t.get('priceChangePercent', 0)):+.2f}%",
                    "quoteVolume": t.get("quoteVolume", "0"),
                }

            ranking_data = {
                "volume_top": [_ticker_to_rank(t) for t in sorted_by_volume[:50]],
                "change_top": [_ticker_to_rank(t) for t in sorted_by_change[:30]],
                "change_bottom": [_ticker_to_rank(t) for t in sorted_by_change[-30:]],
            }

            # ── Volume Spike: compare current 24h volume vs cached previous ──
            now = datetime.now()
            volume_spike_data = []
            if (self._binance_cache_time and
                    (now - self._binance_cache_time) > timedelta(minutes=20)):
                for t in usdt_tickers:
                    sym = t["symbol"]
                    cur_vol = float(t.get("quoteVolume", 0))
                    prev_vol = self._binance_volume_cache.get(sym)
                    if prev_vol and prev_vol > 100000:
                        spike_pct = ((cur_vol - prev_vol) / prev_vol) * 100
                        if spike_pct > 5:  # at least 5% increase
                            entry = _ticker_to_rank(t)
                            entry["spike_pct"] = f"+{spike_pct:.1f}%"
                            volume_spike_data.append((entry, spike_pct))
                volume_spike_data.sort(key=lambda x: x[1], reverse=True)
                ranking_data["volume_spike"] = [d[0] for d in volume_spike_data[:50]]
                logger.info(f"[AISymbol] Binance volume_spike: {len(ranking_data['volume_spike'])} items")
            else:
                ranking_data["volume_spike"] = []
                if not self._binance_cache_time:
                    logger.info("[AISymbol] Binance volume_spike: first run, caching volumes for next comparison")

            # Update volume cache
            self._binance_volume_cache = {
                t["symbol"]: float(t.get("quoteVolume", 0)) for t in usdt_tickers
            }
            self._binance_cache_time = now

            # ── Volatility: 24h price range (high-low)/low ──
            volatility_data = []
            for t in usdt_tickers:
                high = float(t.get("highPrice", 0))
                low = float(t.get("lowPrice", 0))
                if low > 0:
                    vol_pct = ((high - low) / low) * 100
                    entry = _ticker_to_rank(t)
                    entry["volatility"] = f"{vol_pct:.1f}%"
                    volatility_data.append((entry, vol_pct))
            volatility_data.sort(key=lambda x: x[1], reverse=True)
            ranking_data["volatility_top"] = [d[0] for d in volatility_data[:30]]

            logger.info(f"[AISymbol] Binance market data: {len(stock_data)} USDT pairs, "
                        f"{sum(len(v) for v in ranking_data.values())} ranking items")
            return stock_data, ranking_data

        except Exception as e:
            logger.error(f"[AISymbol] Binance market data fetch error: {e}")
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

        # EVALUATE only needs the current symbol's data, not the full list
        # Extract only the current symbol's info and relevant rankings
        current_stock_data = [s for s in stock_data if s.get("code") == current_symbol]
        current_rankings = {}
        for rank_type, items in (ranking_data or {}).items():
            matched = [r for r in (items or []) if r.get("code") == current_symbol]
            if matched:
                current_rankings[rank_type] = matched

        context_data = {
            "mode": "EVALUATE",
            "current_symbol": {"code": current_symbol, "name": symbol_name},
            "search_conditions": search_conditions,
            "stocks": self._slim_stock_data(current_stock_data) if current_stock_data else [{"code": current_symbol, "name": symbol_name}],
            "rankings": current_rankings,
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

            # If evaluation data is insufficient, proceed with switch direction
            # (FIND/COMPARE will validate candidates with backtest data)
            insufficient_keywords = [
                "unable to", "cannot", "could not", "exceeds", "capacity",
                "불가능", "부재", "확인할 수 없", "판단할 수 없", "데이터가 없",
                "제공되지 않", "보완 후", "재평가 필요", "데이터 부족", "알 수 없",
            ]
            if not match and any(kw in reason.lower() for kw in insufficient_keywords):
                logger.info(f"[AISymbol] Evaluate: insufficient data for current symbol, "
                           f"proceeding to FIND candidates: {reason[:200]}")
                return True, f"현재 종목 데이터 부족 - 후보 탐색 진행 ({reason[:100]})"

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
        is_futures: bool = False,
    ) -> list:
        """Find up to 20 candidate symbols matching the conditions.

        For futures exchanges, also returns recommended direction (long/short) per candidate.
        Returns:
          - Spot: [{"code": "...", "name": "...", "reason": "..."}]
          - Futures: [{"code": "...", "name": "...", "direction": "long/short", "reason": "..."}]
        """
        excluded_symbols = excluded_symbols or set()

        # Build exclusion list for the prompt
        all_excluded = {current_symbol} | excluded_symbols
        exclude_str = ", ".join(all_excluded)

        # Limit ranking data to top 100 per type to control context size
        trimmed_rankings = {}
        for rank_type, items in (ranking_data or {}).items():
            trimmed_rankings[rank_type] = (items or [])[:100]

        context_data = {
            "mode": "FIND",
            "current_symbol": current_symbol,
            "search_conditions": search_conditions,
            "excluded_symbols": list(all_excluded),
            "stocks": self._slim_stock_data(stock_data),
            "rankings": trimmed_rankings,
            "is_futures": is_futures,
        }

        if is_futures:
            prompt = (
                f"Read the context file and find up to 20 futures candidates that match "
                f"the user's conditions: '{search_conditions}'. "
                f"This is a FUTURES exchange, so for each candidate you MUST also recommend "
                f"a trading direction (long or short) based on your analysis of the chart pattern, "
                f"volume profile, momentum, and market conditions. "
                f"Return as many candidates as possible (up to 20). "
                f"Exclude ALL of these symbols (already in use): {exclude_str}. "
                f"Respond with ONLY a JSON object: "
                f'{{"candidates": [{{"code": "BTCUSDT", "name": "Bitcoin", '
                f'"direction": "long", "reason": "이유 (방향 근거 포함)"}}]}}'
            )
        else:
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
            # Filter out excluded symbols
            filtered = []
            for c in candidates:
                if "code" not in c or c["code"] in all_excluded:
                    continue
                entry = {"code": c["code"], "name": c.get("name", "")}
                if is_futures and "direction" in c:
                    direction = c["direction"].lower()
                    entry["direction"] = direction if direction in (Side.LONG, Side.SHORT) else Side.LONG
                entry["reason"] = c.get("reason", "")
                filtered.append(entry)
            return filtered[:20]
        except (json.JSONDecodeError, AttributeError, KeyError):
            logger.warning(f"[AISymbol] Failed to parse find response: {result[:200]}")
            return []

    async def _compare_symbols(
        self,
        candidates: list,
        strategy_name: str,
        strategy_config: dict,
        initial_capital: float,
        session_id: str = None,
        optimize_params: dict = None,
        exchange_name: str = "Kiwoom",
    ) -> List[dict]:
        """Compare candidates via backtest (14-day) with same strategy params.

        candidates: list of dicts {"code": "...", "direction": "long/short" (optional)}
                    or list of strings (backward compat).
        If optimize_params is provided, runs grid search per candidate.
        Returns list of per-symbol best results, sorted by score descending.
        """
        from ..api.mock_strategies import _run_unified_backtest
        import itertools

        results_summary = []

        # Normalize candidates to list of dicts
        norm_candidates = []
        for c in candidates:
            if isinstance(c, dict):
                norm_candidates.append(c)
            else:
                norm_candidates.append({"code": c})

        # Build parameter combinations (per-candidate, may vary if AI direction overrides)
        base_optimize_params = dict(optimize_params) if optimize_params else {}

        bt_counter = 0
        # Pre-calculate total for progress (approximate, recalculated per candidate)
        if base_optimize_params:
            _approx_combos = 1
            for v in base_optimize_params.values():
                _approx_combos *= len(v)
            total_bt = len(norm_candidates) * _approx_combos
        else:
            total_bt = len(norm_candidates)

        for i, cand in enumerate(norm_candidates):
            symbol = cand["code"]
            ai_direction = cand.get("direction")  # "long" / "short" / None
            symbol_best_score = float('-inf')
            symbol_best_params = None
            symbol_best_stats = {}

            # Build per-candidate optimize params
            # If AI recommended a direction, lock position_side to that direction
            cand_optimize = dict(base_optimize_params)
            if ai_direction and "position_side" in cand_optimize:
                cand_optimize["position_side"] = [ai_direction]
                logger.info(f"[AISymbol] {symbol}: AI direction={ai_direction}, "
                            f"locking position_side optimization to [{ai_direction}]")

            if cand_optimize:
                opt_keys = list(cand_optimize.keys())
                opt_values = list(cand_optimize.values())
                param_combos = list(itertools.product(*opt_values))
            else:
                opt_keys = []
                param_combos = [()]

            for combo in param_combos:
                bt_counter += 1
                try:
                    config = dict(strategy_config)
                    config['symbol'] = symbol

                    # Apply AI-recommended direction for futures (even without optimization)
                    if ai_direction:
                        config['position_side'] = ai_direction

                    # Apply optimization parameters (won't conflict with ai_direction now)
                    combo_params = {}
                    for k_idx, key in enumerate(opt_keys):
                        config[key] = combo[k_idx]
                        combo_params[key] = combo[k_idx]

                    # Update progress
                    if session_id:
                        prog = self._progress.get(session_id, {})
                        dir_tag = f" ({ai_direction})" if ai_direction else ""
                        if optimize_params:
                            params_desc = ", ".join(f"{k}={v}" for k, v in combo_params.items())
                            msg = (f"최적화 백테스트 중... ({bt_counter}/{total_bt}) "
                                   f"- {symbol}{dir_tag} [{params_desc}]")
                        else:
                            msg = (f"{len(norm_candidates)}개 후보 백테스트 중... "
                                   f"({bt_counter}/{total_bt}) - {symbol}{dir_tag}")
                        self._update_progress(
                            session_id, "backtesting", msg,
                            total=total_bt, current=bt_counter,
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
                        exchange_name=exchange_name,
                    )

                    if "error" in result:
                        logger.warning(f"[AISymbol] Backtest failed for {symbol}: {result['error']}")
                        continue

                    # Extract metrics
                    score = self._calculate_score(result)
                    trades = int(result.get("total_cycles", 0))
                    ret = float(str(result.get("total_return", "0")).replace('%', '').replace(',', ''))
                    wr = float(str(result.get("win_rate", "0")).replace('%', ''))
                    mdd = float(str(result.get("max_drawdown", "0")).replace('%', '').replace(',', ''))

                    dir_log = f" [{ai_direction}]" if ai_direction else ""
                    if optimize_params:
                        params_desc = ", ".join(f"{k}={v}" for k, v in combo_params.items())
                        logger.info(f"[AISymbol] BT [{bt_counter}/{total_bt}] {symbol}{dir_log} "
                                    f"[{params_desc}]: score={score:.2f}, cycles={trades}, "
                                    f"return={ret:.1f}%, WR={wr:.1f}%")
                    else:
                        logger.info(f"[AISymbol] BT [{bt_counter}/{total_bt}] {symbol}{dir_log}: "
                                    f"score={score:.2f}, cycles={trades}, return={ret:.1f}%, WR={wr:.1f}%")

                    # Track per-symbol best
                    if score > symbol_best_score:
                        symbol_best_score = score
                        symbol_best_params = combo_params if combo_params else None
                        symbol_best_stats = {
                            "cycles": trades, "return_pct": ret,
                            "win_rate": wr, "max_drawdown": mdd,
                        }

                except Exception as e:
                    logger.warning(f"[AISymbol] Backtest error for {symbol}: {e}")
                    continue

            # Add best result per symbol to summary
            if symbol_best_score > float('-inf'):
                entry = {
                    "symbol": symbol,
                    "score": round(symbol_best_score, 2),
                    "params": symbol_best_params,
                    **symbol_best_stats,
                }
                if ai_direction:
                    entry["direction"] = ai_direction
                    # Include direction in params for application
                    if entry["params"] is None:
                        entry["params"] = {}
                    entry["params"]["position_side"] = ai_direction
                # Carry forward FIND-stage reason (includes direction justification)
                find_reason = cand.get("reason", "")
                if find_reason:
                    entry["find_reason"] = find_reason
                results_summary.append(entry)

            # Update progress with per-symbol result
            if session_id and symbol_best_score > float('-inf'):
                bt_results = self._progress.get(session_id, {}).get("results", [])
                prog_entry = {
                    "symbol": symbol, "score": round(symbol_best_score, 1),
                    "cycles": symbol_best_stats.get("cycles", 0),
                    "return": symbol_best_stats.get("return_pct", 0),
                    "win_rate": symbol_best_stats.get("win_rate", 0),
                }
                if ai_direction:
                    prog_entry["direction"] = ai_direction
                if symbol_best_params:
                    prog_entry["optimized_params"] = symbol_best_params
                bt_results.append(prog_entry)
                self._update_progress(
                    session_id, "backtesting",
                    f"백테스트 중... ({bt_counter}/{total_bt})",
                    total=total_bt, current=bt_counter, results=bt_results,
                )

        # Sort by score descending
        results_summary.sort(key=lambda x: x["score"], reverse=True)

        # Log top 5
        for r in results_summary[:5]:
            p_str = f" {r['params']}" if r.get('params') else ""
            d_str = f" [{r['direction']}]" if r.get('direction') else ""
            logger.info(f"[AISymbol] Top: {r['symbol']}{d_str} score={r['score']:.1f} "
                        f"ret={r.get('return_pct', 0):.1f}% WR={r.get('win_rate', 0):.1f}% "
                        f"cycles={r.get('cycles', 0)}{p_str}")

        return results_summary

    async def _ai_select_best(
        self,
        bt_results: List[dict],
        search_conditions: str,
        strategy_name: str,
        current_symbol: str,
        session_id: str = None,
    ) -> tuple:
        """Ask AI to select the best symbol+params from backtest results.

        Returns (best_symbol, best_params, reason) tuple.
        Fallback: if AI fails, pick the top-scoring result mechanically.
        """
        # Take top 10 for AI evaluation
        top_results = bt_results[:10]

        # Include FIND-stage reasoning in context for data-driven direction justification
        context_results = []
        for r in top_results:
            entry = dict(r)
            # Keep find_reason in context so AI can reference actual market analysis
            context_results.append(entry)

        context_data = {
            "mode": "SELECT_BEST",
            "strategy_name": strategy_name,
            "current_symbol": current_symbol,
            "search_conditions": search_conditions,
            "backtest_results": context_results,
        }

        # Check if any result has direction info (futures mode)
        has_direction = any(r.get("direction") for r in top_results)

        direction_guidance = ""
        if has_direction:
            direction_guidance = (
                "- Direction (long/short): Each candidate has a 'find_reason' field containing the "
                "original market data analysis that determined its direction. Reference this analysis "
                "in your reason — do NOT fabricate new market analysis.\n"
            )

        prompt = (
            "Read the context file. You are given backtest results for competing symbols "
            "(each with their best parameter combination if optimization was used). "
            f"The CURRENT symbol is '{current_symbol}' — it is included in the competition. "
            "Select the single best symbol+params combination for live trading.\n\n"
            "Consider:\n"
            "- Return % and win rate (higher is better)\n"
            "- Number of cycles/trades (more trades = more reliable signal, fewer = possibly overfitted)\n"
            "- Max drawdown (lower is better, indicates risk)\n"
            "- Parameter reasonableness (extreme leverage or unusual params may indicate overfitting)\n"
            "- If the score difference between top candidates is small, prefer the one with more trades\n"
            "- The user's original search conditions for context\n"
            f"- If '{current_symbol}' (current) has a comparable score to top candidates, "
            "prefer keeping it to avoid unnecessary switching costs\n"
            f"{direction_guidance}\n"
            "Respond with ONLY a JSON object:\n"
            '{"selected_symbol": "code", "selected_params": {"key": value, ...} or null, '
            '"reason": "Korean explanation including: 1) why this symbol was chosen (backtest metrics), '
            '2) if futures, why this direction (long/short) based on the find_reason market analysis"}'
        )

        if session_id:
            self._update_progress(session_id, "ai_selecting",
                                  f"AI가 상위 {len(top_results)}개 결과에서 최적 조합 선택 중...")

        result = await self._call_claude(context_data, prompt)

        # Fallback: mechanical selection
        fallback_symbol = top_results[0]["symbol"] if top_results else None
        fallback_params = top_results[0].get("params") if top_results else None

        if result is None:
            logger.warning("[AISymbol] AI selection failed, using mechanical fallback")
            return fallback_symbol, fallback_params, ""

        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            selected_symbol = parsed.get("selected_symbol")
            selected_params = parsed.get("selected_params")
            reason = parsed.get("reason", "")

            # Validate that selected symbol is in our results
            valid_symbols = {r["symbol"] for r in top_results}
            if selected_symbol not in valid_symbols:
                logger.warning(f"[AISymbol] AI selected invalid symbol '{selected_symbol}', "
                               f"using fallback. Valid: {valid_symbols}")
                return fallback_symbol, fallback_params, ""

            # If AI selected a symbol but returned no params, use that symbol's best params
            if selected_params is None:
                for r in top_results:
                    if r["symbol"] == selected_symbol:
                        selected_params = r.get("params")
                        break

            logger.info(f"[AISymbol] AI selected: {selected_symbol} params={selected_params} "
                        f"reason={reason[:100]}")
            return selected_symbol, selected_params, reason

        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"[AISymbol] Failed to parse AI selection: {result[:200]}")
            return fallback_symbol, fallback_params, ""

    async def _generate_optimize_ranges(
        self,
        param_names: list,
        strategy_name: str,
        strategy_config: dict,
        sample_symbol: str,
    ) -> dict:
        """Ask AI to determine smart optimization ranges for selected parameters.

        Returns dict like: {"leverage": [1, 5, 10, 20], "position_side": ["long", "short"]}
        """
        from .strategy_registry import StrategyRegistry

        # Get schema for param metadata (min/max/step/options)
        schema = StrategyRegistry.get_parameter_schema(strategy_name)
        fields = schema.get("fields", []) if schema else []

        # Build param info for AI
        param_info = []
        for name in param_names:
            field = next((f for f in fields if (f.get("key") or f.get("name")) == name), None)
            current_val = strategy_config.get(name)
            info = {"name": name, "current_value": current_val}
            if field:
                info["label"] = field.get("label", name)
                info["type"] = field.get("type", "number")
                if field.get("type") == "number":
                    info["min"] = field.get("min")
                    info["max"] = field.get("max")
                    info["step"] = field.get("step")
                elif field.get("options"):
                    info["options"] = field["options"]
            param_info.append(info)

        context_data = {
            "mode": "OPTIMIZE_RANGES",
            "strategy_name": strategy_name,
            "sample_symbol": sample_symbol,
            "current_config": {k: v for k, v in strategy_config.items()
                               if k in param_names or k in ("symbol", "interval")},
            "parameters_to_optimize": param_info,
        }

        prompt = (
            "Read the context file. You need to suggest optimization ranges for the listed parameters. "
            "The current config values are provided. Generate 3-5 candidate values per parameter that "
            "would be meaningful to test via grid search backtest. "
            "Rules:\n"
            "- For number params: include the current value, plus values above and below it. "
            "Respect min/max/step constraints. Choose values that are practically meaningful "
            "(e.g., for leverage, include 1 as baseline).\n"
            "- For select params: include all options that make sense to compare.\n"
            "- Keep total combinations reasonable (under 50 if possible).\n"
            "- Consider the strategy context when choosing values.\n"
            "Respond with ONLY a JSON object:\n"
            '{"ranges": {"param_name": [value1, value2, ...], ...}}'
        )

        result = await self._call_claude(context_data, prompt, agent=None)
        if result is None:
            return {}

        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            ranges = parsed.get("ranges", {})

            # Validate and sanitize
            validated = {}
            for name in param_names:
                if name in ranges and isinstance(ranges[name], list) and len(ranges[name]) >= 2:
                    validated[name] = ranges[name]
                else:
                    logger.warning(f"[AISymbol] AI returned invalid range for '{name}', skipping")

            return validated
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"[AISymbol] Failed to parse optimize ranges response: {result[:200]}")
            return {}

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

        # Base score: return-dominant + win_rate as tiebreaker
        # Return already reflects leverage (equity-based), so weight it heavily
        base_score = (total_return * 0.7) + (win_rate * 0.15)

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

    async def _call_claude(self, context_data: dict, prompt: str, agent: str = "symbol-evaluator") -> Optional[str]:
        """Call Claude CLI with context file, reusing stock_search.py pattern."""
        from .config import get_claude_cli_path
        claude_path = get_claude_cli_path()

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
                "--permission-mode", "bypassPermissions",
            ]
            if agent:
                cmd.extend(["--agent", agent])

            env = os.environ.copy()
            for key in ["NODE_CHANNEL_FD", "NODE_CHANNEL_SERIALIZATION_MODE", "NODE_APP_INSTANCE"]:
                env.pop(key, None)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
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

                group_exchange_name = first.get("exchange_name") or "Kiwoom"
                _ex = group_exchange_name.lower()
                is_binance = "binance" in _ex

                if is_binance:
                    is_futures = first.get("is_futures", False)
                    stock_data, ranking_data = await self._fetch_binance_market_data(is_futures=is_futures)
                else:
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
                    exchange_name=group_exchange_name,
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
        exchange_name: str = "Kiwoom",
    ) -> List[tuple]:
        """
        Compare candidates via backtest. Returns ranked list:
        [(symbol, score, trades, return_pct), ...] sorted by score descending.
        Broadcasts progress to all sessions in the group.
        """
        from ..api.mock_strategies import _run_unified_backtest

        results_summary = []

        # Normalize candidates to list of dicts
        norm_candidates = []
        for c in candidates:
            if isinstance(c, dict):
                norm_candidates.append(c)
            else:
                norm_candidates.append({"code": c})

        for i, cand in enumerate(norm_candidates):
            symbol = cand["code"]
            try:
                config = dict(strategy_config)
                config['symbol'] = symbol

                # Update progress for ALL sessions
                progress_msg = (f"{len(norm_candidates)}개 후보 백테스트 중... "
                                f"({i+1}/{len(norm_candidates)}) - {symbol}")
                for sid in (session_ids or []):
                    prog = self._progress.get(sid, {})
                    self._update_progress(
                        sid, "backtesting", progress_msg,
                        total=len(norm_candidates), current=i+1,
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
                    exchange_name=exchange_name,
                )

                if "error" in result:
                    logger.warning(f"[AISymbol] Backtest failed for {symbol}: {result['error']}")
                    continue

                score = self._calculate_score(result)
                trades = int(result.get("total_cycles", 0))
                ret = float(str(result.get("total_return", "0")).replace('%', '').replace(',', ''))
                wr = float(str(result.get("win_rate", "0")).replace('%', ''))

                logger.info(f"[AISymbol] Group Backtest [{i+1}/{len(norm_candidates)}] {symbol}: "
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
                        f"{len(norm_candidates)}개 후보 백테스트 중... ({i+1}/{len(norm_candidates)})",
                        total=len(norm_candidates), current=i+1, results=bt_results,
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
