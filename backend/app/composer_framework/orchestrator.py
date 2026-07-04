"""PaperOrchestrator — runs a daily cycle for one PaperSession.

Cycle steps:
  1. Load session state from disk
  2. Build runtime data (OHLCV up to today, signals, flow if needed)
  3. Build Pipeline from spec + runtime data
  4. If session.last_fit_ts is None or (now - last_fit) >= refit_interval, fit
  5. Predict for the latest bar
  6. Build PolicyContext from session state + latest bar
  7. policy.decide(...) → Action
  8. Apply action to session state, record trade if entry/exit
  9. Mark equity, save session

All side effects (state changes, trade records) are persisted via SessionStore.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from .paper_session import (
    CycleResult,
    PaperSession,
    SessionStore,
    TradeRecord,
)
from .pipeline_spec import build_pipeline
from .policy import Action, PolicyContext
from .signal_source import SourceContext

logger = logging.getLogger(__name__)


@dataclass
class RuntimeBundle:
    """Inputs needed for a single orchestrator cycle on one symbol."""
    ohlcv_1m: pd.DataFrame
    ohlcv_eval: pd.DataFrame
    signals_df: Optional[pd.DataFrame] = None
    flow_df: Optional[pd.DataFrame] = None
    binance_metrics_5m: Optional[pd.DataFrame] = None
    binance_funding_df: Optional[pd.DataFrame] = None
    binance_oi_df: Optional[pd.DataFrame] = None
    binance_funding_universe_df: Optional[pd.DataFrame] = None  # wide: index=time, cols=symbols
    leader_ohlcv_eval: Optional[pd.DataFrame] = None  # leader symbol's eval-tf ohlcv (e.g. BTC 5m)
    leader_ohlcv_1m: Optional[pd.DataFrame] = None    # leader symbol's raw 1m ohlcv (used by bn_btc_rv_highvol_long)
    book_depth_daily: Optional[pd.DataFrame] = None
    premium_df: Optional[pd.DataFrame] = None
    eth_ohlcv_eval: Optional[pd.DataFrame] = None


class PaperOrchestrator:
    def __init__(self, store: SessionStore) -> None:
        self.store = store

    def run_cycle(
        self,
        session: PaperSession,
        bundle: RuntimeBundle,
    ) -> CycleResult:
        """Run one cycle on `session` using the latest data in `bundle`.

        Mutates `session` in-place; persists state via self.store.
        """
        if session.status != "active":
            raise ValueError(f"Cannot run cycle on {session.status} session")

        df_eval = bundle.ohlcv_eval
        # No-fit composers (passthrough variants) need at least 2 eval bars
        # for forward-return target. ML composers need a longer training
        # window. Branch on composer type instead of a one-size-fits-all.
        from .composers import PassthroughComposer, NegationPassthroughComposer
        spec_composer_type = session.pipeline_spec.get("composer", {}).get("type", "")
        is_no_fit_composer = spec_composer_type in ("passthrough", "negation_passthrough")
        min_eval_bars = 2 if is_no_fit_composer else 30
        if len(df_eval) < min_eval_bars:
            raise ValueError(f"Need at least {min_eval_bars} eval bars, got {len(df_eval)}")

        # Build runtime data dict for Pipeline construction
        runtime_data = {
            "symbol": session.symbol,
            "ohlcv_1m": bundle.ohlcv_1m,
            "ohlcv_eval": df_eval,
        }
        if bundle.signals_df is not None:
            runtime_data["signals_df"] = bundle.signals_df
        if bundle.flow_df is not None:
            runtime_data["flow_df"] = bundle.flow_df
        if bundle.binance_metrics_5m is not None:
            runtime_data["binance_metrics_5m"] = bundle.binance_metrics_5m
        if bundle.binance_funding_df is not None:
            runtime_data["binance_funding_df"] = bundle.binance_funding_df
        if bundle.binance_oi_df is not None:
            runtime_data["binance_oi_df"] = bundle.binance_oi_df
        if bundle.binance_funding_universe_df is not None:
            runtime_data["binance_funding_universe_df"] = bundle.binance_funding_universe_df
        if bundle.leader_ohlcv_eval is not None:
            runtime_data["leader_ohlcv_eval"] = bundle.leader_ohlcv_eval
        if bundle.leader_ohlcv_1m is not None:
            runtime_data["leader_ohlcv_1m"] = bundle.leader_ohlcv_1m
        if bundle.book_depth_daily is not None:
            runtime_data["book_depth_daily"] = bundle.book_depth_daily
        if bundle.premium_df is not None:
            runtime_data["premium_df"] = bundle.premium_df
        if bundle.eth_ohlcv_eval is not None:
            runtime_data["eth_ohlcv_eval"] = bundle.eth_ohlcv_eval

        eval_freq_min = session.pipeline_spec.get("config", {}).get("eval_freq_minutes", 1440)
        ctx = SourceContext(
            symbol=session.symbol,
            eval_freq_minutes=eval_freq_min,
            ohlcv_1m=bundle.ohlcv_1m,
            ohlcv_eval=df_eval,
        )

        pipeline = build_pipeline(session.pipeline_spec, runtime_data)

        # Build features over full history up to current bar
        feat = pipeline.build_features(ctx)

        # Always fit at the start of each cycle — Pipeline (and thus the
        # composer) is freshly constructed every run, so there's no carried
        # state to reuse. last_fit_ts is kept as an audit field; the
        # refit_interval policy now only governs WHETHER we use a longer or
        # shorter training window (future enhancement), not whether to fit.
        # Skip insufficient_train check for no-fit composers — their fit()
        # is a no-op and they don't need a training window.
        if is_no_fit_composer:
            try:
                pipeline.fit(feat.iloc[:0])  # no-op for passthrough
            except Exception:
                pass
            session.last_fit_ts = datetime.utcnow().isoformat(timespec="seconds")
        else:
            train_df = feat.dropna(subset=[pipeline.config.target_col])
            if len(train_df) < 30:
                logger.warning("Session %s: too few training samples (%d)", session.session_id, len(train_df))
                return self._record_no_op(session, feat, "insufficient_train")
            pipeline.fit(train_df)
            session.last_fit_ts = datetime.utcnow().isoformat(timespec="seconds")

        # ── Catch-up replay ──────────────────────────────────────────────
        # Process EVERY un-processed eval bar since last_cycle_ts, not just the
        # latest one. A once-daily cron on a 5m-eval session would otherwise
        # evaluate 1 of 288 bars/day (intraday under-sampling): the source emits
        # signals but the loop never sees them → 0 trades / +0.00% forever.
        # Daily-eval sessions are unaffected (their gap is ~1 bar/run, so the
        # loop runs once = identical to the old single-bar behavior). Position,
        # cash, bars_held, and SL/TP state carry across the replayed bars.
        eval_index = df_eval.index
        n_bars = len(eval_index)
        if session.last_cycle_ts:
            try:
                last_ts = pd.Timestamp(session.last_cycle_ts)
                start_pos = int(eval_index.searchsorted(last_ts, side="right"))
            except Exception:
                start_pos = n_bars - 1
        else:
            # fresh session: start clean from the latest bar (do NOT replay all
            # of history — this is a live paper session, not a backtest).
            start_pos = n_bars - 1
        gap_positions = list(range(max(start_pos, 0), n_bars))
        # Safety bound: cap one cycle's replay at ~1 week of 5m bars (e.g. the
        # first run after a long outage) so a single cycle stays bounded.
        MAX_CATCHUP_BARS = 2016
        if len(gap_positions) > MAX_CATCHUP_BARS:
            gap_positions = gap_positions[-MAX_CATCHUP_BARS:]
        if not gap_positions:
            # Already up to date (no new bar) — no-op, do not re-execute.
            return self._record_no_op(session, feat, "no_new_bar")

        # Predict the whole gap at once (vectorized), then step bar-by-bar for
        # the inherently-sequential policy/position/execution logic.
        try:
            pred_all = pipeline.predict(feat.iloc[gap_positions])
        except Exception as exc:
            logger.warning("Session %s predict failed: %s", session.session_id, exc)
            return self._record_no_op(session, feat, f"predict_error: {exc}")

        cycle: Optional[CycleResult] = None
        for k, pos in enumerate(gap_positions):
            prediction = float(pred_all[k])
            bar = df_eval.iloc[pos]
            bar_ts = eval_index[pos]
            ts_iso = pd.Timestamp(bar_ts).isoformat()
            policy_ctx = PolicyContext(
                timestamp=bar_ts.to_pydatetime() if hasattr(bar_ts, "to_pydatetime") else bar_ts,
                prediction=prediction,
                open_price=float(bar["open"]),
                high_price=float(bar["high"]),
                low_price=float(bar["low"]),
                close_price=float(bar["close"]),
                in_position=(session.side != "flat"),
                side=session.side,
                entry_price=session.entry_price,
                bars_held=session.bars_held,
            )

            # Forced-exit check (SL/TP hit intra-bar) BEFORE policy.decide
            forced_exit = self._check_forced_exit(session, bar)

            action = pipeline.policy.decide(policy_ctx)

            side_before = session.side
            trade_id: Optional[str] = None

            if forced_exit:
                trade = self._close_position(session, forced_exit["price"], bar_ts, forced_exit["reason"], prediction)
                trade_id = trade.trade_id
                self.store.append_trade(session.session_id, trade)
            elif action.kind == "exit" and session.side != "flat":
                trade = self._close_position(session, float(bar["open"]), bar_ts, action.note or "policy_exit", prediction)
                trade_id = trade.trade_id
                self.store.append_trade(session.session_id, trade)

            # Apply entry if flat now
            if session.side == "flat" and action.kind == "enter_long":
                self._open_long(session, float(bar["open"]), bar_ts, action, prediction)
            elif session.side == "flat" and action.kind == "enter_short":
                self._open_short(session, float(bar["open"]), bar_ts, action, prediction)
            elif session.side != "flat" and action.kind == "hold":
                session.bars_held += 1

            # Mark equity
            if session.side == "long":
                equity = session.cash + session.qty * float(bar["close"])
            elif session.side == "short":
                equity = session.cash + session.qty * (session.entry_price - float(bar["close"])) + session.qty * session.entry_price
            else:
                equity = session.cash

            session.final_equity = equity
            session.total_return_pct = (equity - session.initial_capital) / session.initial_capital
            session.last_cycle_ts = ts_iso
            session.n_cycles += 1
            self.store.append_equity(session.session_id, ts_iso, equity)

            cycle = CycleResult(
                timestamp=ts_iso, prediction=prediction,
                action_kind=action.kind, action_note=action.note,
                bar_open=float(bar["open"]), bar_close=float(bar["close"]),
                side_before=side_before, side_after=session.side,
                cash_after=session.cash, equity_after=equity,
                sl_price=session.sl_price, tp_price=session.tp_price,
                trade_id=trade_id,
                forced_exit_reason=forced_exit["reason"] if forced_exit else None,
            )
            self.store.append_cycle(session.session_id, cycle)

        self.store.save(session)
        return cycle

    # ───────────────────── helpers ─────────────────────

    def _needs_fit(self, session: PaperSession) -> bool:
        if session.last_fit_ts is None:
            return True
        try:
            last = datetime.fromisoformat(session.last_fit_ts)
        except Exception:
            return True
        return (datetime.utcnow() - last).days >= session.refit_interval_days

    def _check_forced_exit(self, session: PaperSession, bar: pd.Series) -> Optional[dict]:
        if session.side == "flat":
            return None
        if session.side == "long":
            if float(bar["low"]) <= session.sl_price:
                return {"price": session.sl_price, "reason": "sl"}
            if float(bar["high"]) >= session.tp_price:
                return {"price": session.tp_price, "reason": "tp"}
        else:  # short
            if float(bar["high"]) >= session.sl_price:
                return {"price": session.sl_price, "reason": "sl"}
            if float(bar["low"]) <= session.tp_price:
                return {"price": session.tp_price, "reason": "tp"}
        return None

    def _open_long(self, session: PaperSession, price: float, ts: pd.Timestamp,
                   action: Action, prediction: float) -> None:
        size_pct = 0.95
        qty = (session.cash * size_pct) / (price * (1 + session.fee_rate))
        if qty <= 0:
            return
        cost = qty * price * (1 + session.fee_rate)
        session.cash -= cost
        session.qty = qty
        session.side = "long"
        session.entry_price = price
        session.entry_ts = pd.Timestamp(ts).isoformat()
        session.sl_price = action.sl_price or price * 0.96
        session.tp_price = action.tp_price or price * 1.10
        session.bars_held = 0

    def _open_short(self, session: PaperSession, price: float, ts: pd.Timestamp,
                    action: Action, prediction: float) -> None:
        qty = (session.cash * 0.95) / price
        if qty <= 0:
            return
        session.cash -= qty * price  # collateral
        session.qty = qty
        session.side = "short"
        session.entry_price = price
        session.entry_ts = pd.Timestamp(ts).isoformat()
        session.sl_price = action.sl_price or price * 1.04
        session.tp_price = action.tp_price or price * 0.90
        session.bars_held = 0

    def _close_position(self, session: PaperSession, exit_price: float,
                        exit_ts: pd.Timestamp, reason: str,
                        prediction_at_entry: float) -> TradeRecord:
        if session.side == "long":
            proceeds = session.qty * exit_price * (1 - session.fee_rate)
            cost = session.qty * session.entry_price * (1 + session.fee_rate)
            session.cash += proceeds
            ret = (proceeds - cost) / cost
            pnl_cash = proceeds - cost
        else:  # short
            proceeds = session.qty * (session.entry_price - exit_price)
            cost = session.qty * session.entry_price
            session.cash += cost + proceeds
            ret = proceeds / cost
            pnl_cash = proceeds

        trade_id = str(uuid.uuid4())[:12]
        trade = TradeRecord(
            trade_id=trade_id,
            side=session.side,
            entry_ts=session.entry_ts or "",
            exit_ts=pd.Timestamp(exit_ts).isoformat(),
            entry_price=session.entry_price,
            exit_price=float(exit_price),
            qty=session.qty,
            return_pct=float(ret),
            pnl_cash=float(pnl_cash),
            exit_reason=reason,
            prediction_at_entry=float(prediction_at_entry),
        )

        session.qty = 0.0
        session.side = "flat"
        session.entry_price = 0.0
        session.entry_ts = None
        session.sl_price = 0.0
        session.tp_price = 0.0
        session.bars_held = 0
        session.n_trades += 1
        return trade

    def _record_no_op(self, session: PaperSession, feat: pd.DataFrame, reason: str) -> CycleResult:
        ts_iso = pd.Timestamp(feat.index[-1]).isoformat()
        cycle = CycleResult(
            timestamp=ts_iso, prediction=float("nan"),
            action_kind="hold", action_note=reason,
            bar_open=0.0, bar_close=0.0,
            side_before=session.side, side_after=session.side,
            cash_after=session.cash, equity_after=session.final_equity,
        )
        self.store.append_cycle(session.session_id, cycle)
        session.last_cycle_ts = ts_iso
        session.n_cycles += 1
        self.store.save(session)
        return cycle
