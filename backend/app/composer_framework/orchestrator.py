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
from .kernel import KernelConfig, KernelState, _forced_exit
from .kernel import close as _kernel_close
from .kernel import open_position as _kernel_open
from .kernel import step as kernel_step
from .pipeline_spec import build_pipeline
from .policy import Action, PolicyContext
from .signal_source import SourceContext

logger = logging.getLogger(__name__)


# ── 세션 ↔ 정본(Canon) 상태 변환 ─────────────────────────────────────────
# 거래 로직은 kernel.py(정본)에만 있다. 여기 있는 것은 영속화 형식
# (PaperSession)과 정본 상태 사이의 변환뿐이다.

def _kernel_config(session: PaperSession) -> KernelConfig:
    """오케스트레이터의 회계를 설정으로 표현한다.

    3b (2026-08-13) — 브래킷 기본값 격차 D2 해소.
      종전: policy 가 브래킷을 지정하지 않으면(None) SL 4% / TP 10% 를 **임의로**
            장착했다. backtester 는 같은 경우 비활성으로 뒀다. 같은 policy 가
            두 실행기에서 다른 전략이 되는 상태였고, 2026-08-08 사고(선언한 적
            없는 10% 익절이 실자금 43일을 오염)가 정확히 이 계열의 사고다.
      현재: 양쪽 모두 **비활성**. 브래킷은 policy 가 선언한 것만 존재한다.

      실측 영향 0 — 현행 4개 policy(LongOnly / LongShort / LifecycleDecayEarlyExit
      / FundingReversal)는 모두 진입 시 sl/tp 를 명시적으로 넣는다. 골든 재생
      112/112 · 파리티 PASS 136/FAIL 0 로 확인했다. 즉 이 수정은 **잠재 함정을
      제거**하는 것이지 지금 전략을 바꾸는 것이 아니다.

    `policy_exit_reason` 격차("policy" vs "policy_exit")는 아직 남아 있다 —
    별도 항목으로 따로 처리한다(한 커밋에 한 격차).
    """
    return KernelConfig(
        size_pct=0.95,
        fee_rate=session.fee_rate,
        apply_fee_to_short=True,
        default_sl_pct=None,
        default_tp_pct=None,
        policy_exit_reason="policy_exit",
    )


def _state_from_session(session: PaperSession) -> KernelState:
    return KernelState(
        cash=session.cash, side=session.side, qty=session.qty,
        entry_price=session.entry_price, entry_ts=session.entry_ts,
        bars_held=session.bars_held, sl_price=session.sl_price,
        tp_price=session.tp_price,
    )


def _apply_state(session: PaperSession, st: KernelState) -> None:
    session.cash = st.cash
    session.side = st.side
    session.qty = st.qty
    session.entry_price = st.entry_price
    session.entry_ts = (None if st.entry_ts is None
                        else pd.Timestamp(st.entry_ts).isoformat())
    session.bars_held = st.bars_held
    session.sl_price = st.sl_price
    session.tp_price = st.tp_price


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

        # 바 처리 로직은 **정본에만** 있다. 여기는 세션 상태를 정본 상태로 옮기고
        # 결과를 영속화하는 얇은 껍데기다. 두 실행기가 각자 루프를 갖고 있던 것이
        # 2026-08-08 사고의 원인이었다 (같은 policy, 다른 실행기, 다른 전략).
        cfg = _kernel_config(session)
        st = _state_from_session(session)

        cycle: Optional[CycleResult] = None
        for k, pos in enumerate(gap_positions):
            prediction = float(pred_all[k])
            bar = df_eval.iloc[pos]
            bar_ts = eval_index[pos]
            ts_iso = pd.Timestamp(bar_ts).isoformat()

            st, res = kernel_step(
                st,
                ts=bar_ts.to_pydatetime() if hasattr(bar_ts, "to_pydatetime") else bar_ts,
                open_price=float(bar["open"]), high_price=float(bar["high"]),
                low_price=float(bar["low"]), close_price=float(bar["close"]),
                prediction=prediction, policy=pipeline.policy, cfg=cfg)

            side_before = res.side_before
            action = res.action
            trade_id: Optional[str] = None
            for _c in res.closed:
                session.n_trades += 1
                trade = TradeRecord(
                    trade_id=str(uuid.uuid4())[:12], side=_c.side,
                    entry_ts=(pd.Timestamp(_c.entry_ts).isoformat()
                              if _c.entry_ts is not None else ""),
                    exit_ts=pd.Timestamp(_c.exit_ts).isoformat(),
                    entry_price=_c.entry_price, exit_price=_c.exit_price,
                    qty=_c.qty, return_pct=_c.return_pct,
                    pnl_cash=_c.pnl_cash, exit_reason=_c.exit_reason,
                    prediction_at_entry=prediction,
                )
                trade_id = trade.trade_id      # CycleResult 에는 마지막 것을 남긴다
                self.store.append_trade(session.session_id, trade)

            _apply_state(session, st)
            equity = res.equity
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
                forced_exit_reason=res.forced_exit_reason,
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

    # ── 아래 헬퍼들은 **정본 위임**이다 ─────────────────────────────────
    # 회계식을 여기에 다시 쓰면 그 순간 두 번째 구현이 생긴다 (2026-08-08 사고).
    # 기존 테스트(test_bracket_semantics / test_short_fee)가 이 진입점을 쓰므로
    # 시그니처는 유지하되 내용은 전부 정본(kernel)으로 넘긴다.

    def _check_forced_exit(self, session: PaperSession, bar: pd.Series) -> Optional[dict]:
        hit = _forced_exit(_state_from_session(session),
                           float(bar["high"]), float(bar["low"]))
        return None if hit is None else {"price": hit[0], "reason": hit[1]}

    @staticmethod
    def _bar_at(price: float) -> dict:
        """가격 하나만 아는 호출부(_open_long/_open_short)를 위한 최소 바.

        시장가 체결 규칙은 시가만 본다. 지정가·스톱 규칙은 고저를 보므로 이
        경로로는 쓸 수 없다 — 그 경로는 run_cycle 이 실제 바를 넘긴다.
        """
        p = float(price)
        return {"open_price": p, "high_price": p, "low_price": p, "close_price": p}

    def _open_long(self, session: PaperSession, price: float, ts: pd.Timestamp,
                   action: Action, prediction: float) -> None:
        st = _kernel_open(_state_from_session(session), "enter_long",
                          self._bar_at(price), pd.Timestamp(ts).isoformat(),
                          action, _kernel_config(session))
        _apply_state(session, st)

    def _open_short(self, session: PaperSession, price: float, ts: pd.Timestamp,
                    action: Action, prediction: float) -> None:
        st = _kernel_open(_state_from_session(session), "enter_short",
                          self._bar_at(price), pd.Timestamp(ts).isoformat(),
                          action, _kernel_config(session))
        _apply_state(session, st)

    def _close_position(self, session: PaperSession, exit_price: float,
                        exit_ts: pd.Timestamp, reason: str,
                        prediction_at_entry: float) -> TradeRecord:
        st, tr = _kernel_close(_state_from_session(session), float(exit_price),
                               exit_ts, reason, _kernel_config(session))
        _apply_state(session, st)
        session.n_trades += 1
        return TradeRecord(
            trade_id=str(uuid.uuid4())[:12], side=tr.side,
            entry_ts=(pd.Timestamp(tr.entry_ts).isoformat()
                      if tr.entry_ts is not None else ""),
            exit_ts=pd.Timestamp(tr.exit_ts).isoformat(),
            entry_price=tr.entry_price, exit_price=tr.exit_price, qty=tr.qty,
            return_pct=tr.return_pct, pnl_cash=tr.pnl_cash,
            exit_reason=tr.exit_reason,
            prediction_at_entry=float(prediction_at_entry),
        )

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
