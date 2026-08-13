"""
GenericBacktester — runs a Pipeline through historical data + computes KPIs.

This is the SINGLE backtester for any (sources, composer, policy) combination.
Replaces the proliferation of EventDriven / Multi / Floor / Defensive /
Adaptive backtesters in pattern_composer/ — each can be re-expressed as a
Pipeline + Policy combination if needed.

For now we provide:
  - Static-fit backtest (train once, test on the rest)
  - Walk-forward backtest (refit periodically)

Trades are simulated bar-by-bar at eval frequency. Entry executes at the next
bar's open; intra-bar SL/TP via high/low; exit reasons logged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from .kernel import KernelConfig, KernelState
from .kernel import close as kernel_close
from .kernel import step as kernel_step
from .pipeline import Pipeline
from .policy import TradingPolicy
from .signal_source import SourceContext

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    entry_ts: datetime
    exit_ts: datetime
    side: str
    entry_price: float
    exit_price: float
    qty: float
    return_pct: float
    exit_reason: str
    prediction_at_entry: float


@dataclass
class BacktestKPIs:
    symbol: str
    start: datetime
    end: datetime
    initial_capital: float
    final_capital: float
    n_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_per_trade_annualized: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    exit_reasons: dict[str, int] = field(default_factory=dict)
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    predictions: pd.Series | None = None
    buy_hold_pct: float = 0.0

    def summary(self) -> str:
        return (
            f"Backtest — {self.symbol}\n"
            f"  window     : {self.start} → {self.end}\n"
            f"  capital    : {self.initial_capital:,.0f} → {self.final_capital:,.0f}\n"
            f"  total ret  : {self.total_return_pct*100:+.2f}%   (BH: {self.buy_hold_pct*100:+.2f}%)\n"
            f"  trades     : {self.n_trades}  win_rate={self.win_rate*100:.1f}%  "
            f"PF={self.profit_factor:.2f}  Sharpe(ann)={self.sharpe_per_trade_annualized:.2f}\n"
            f"  MDD        : {self.max_drawdown_pct*100:.2f}%\n"
            f"  exits      : {self.exit_reasons}"
        )


class GenericBacktester:
    """Runs a fitted Pipeline through bars, simulating trades via Pipeline.policy."""

    def __init__(
        self,
        *,
        initial_capital: float = 1_000_000.0,
        size_pct: float = 0.95,
        fee_rate: float = 0.00015,
        apply_fee_to_short: bool = True,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.size_pct = float(size_pct)
        self.fee_rate = float(fee_rate)
        # 2026-08-12: 숏에 수수료가 아예 부과되지 않던 결함을 고쳤다(최초 커밋
        # 70ffae67 이후 3개월간 방치). 롱 분기에만 fee_rate 가 곱해져 있었고
        # 숏은 진입·청산 모두 무료였다 — 실자금 전략(신상저격수)이 숏 전용이다.
        # 이 플래그는 **수정 전/후 A/B 측정용**이며 기본값 True 가 올바른 동작이다.
        # False 는 구동작 재현 전용 — 운영에서 쓰지 말 것.
        self.apply_fee_to_short = bool(apply_fee_to_short)

    # ------------------------------------------- static fit/test

    def run_static(
        self,
        *,
        pipeline: Pipeline,
        ctx: SourceContext,
        train_frac: float = 0.5,
    ) -> BacktestKPIs:
        """Fit on first train_frac of data, test on the rest."""
        feat = pipeline.build_features(ctx)
        n = len(feat)
        split = int(n * train_frac)
        train = feat.iloc[:split]
        test = feat.iloc[split:]
        bars_test = ctx.ohlcv_eval.loc[test.index]

        pipeline.fit(train)
        preds = pipeline.predict(test)
        preds = pd.Series(preds, index=test.index)

        return self._simulate(symbol=ctx.symbol, bars=bars_test,
                              predictions=preds, policy=pipeline.policy)

    # ------------------------------------------- walk-forward

    def run_walk_forward(
        self,
        *,
        pipeline: Pipeline,
        ctx: SourceContext,
        train_window_bars: int,
        retrain_step_bars: int,
    ) -> BacktestKPIs:
        feat = pipeline.build_features(ctx)
        n = len(feat)
        preds = pd.Series(np.nan, index=feat.index, dtype=float)
        last_train_idx = -10**9
        for i in range(train_window_bars, n):
            if i - last_train_idx >= retrain_step_bars:
                lo = max(0, i - train_window_bars)
                train = feat.iloc[lo:i]
                try:
                    pipeline.fit(train)
                    last_train_idx = i
                except Exception as exc:
                    logger.warning("Pipeline.fit failed at i=%d: %s", i, exc)
                    continue
            row = feat.iloc[[i]]
            try:
                preds.iloc[i] = pipeline.predict(row)[0]
            except Exception as exc:
                logger.warning("Pipeline.predict failed at i=%d: %s", i, exc)

        return self._simulate(symbol=ctx.symbol, bars=ctx.ohlcv_eval,
                              predictions=preds, policy=pipeline.policy)

    # ------------------------------------------- simulator

    def _simulate(
        self,
        *,
        symbol: str,
        bars: pd.DataFrame,
        predictions: pd.Series,
        policy: TradingPolicy,
    ) -> BacktestKPIs:
        trades: list[BacktestTrade] = []
        eq: list[tuple[datetime, float]] = []

        bars = bars.sort_index()
        # align predictions to bars
        preds_aligned = predictions.reindex(bars.index)

        cfg = self._kernel_config()
        st = KernelState(cash=self.initial_capital)
        pred_at_entry = 0.0          # 정본은 예측을 들고 다니지 않는다 — 드라이버 몫

        def _py(t):
            return t.to_pydatetime() if hasattr(t, "to_pydatetime") else t

        def _record(tr) -> None:
            trades.append(BacktestTrade(
                entry_ts=_py(tr.entry_ts), exit_ts=_py(tr.exit_ts), side=tr.side,
                entry_price=tr.entry_price, exit_price=tr.exit_price, qty=tr.qty,
                return_pct=tr.return_pct, exit_reason=tr.exit_reason,
                prediction_at_entry=pred_at_entry,
            ))

        for i in range(len(bars)):
            ts = bars.index[i]
            row = bars.iloc[i]
            pred = float(preds_aligned.iloc[i]) if i < len(preds_aligned) else np.nan

            st, res = kernel_step(
                st, ts=ts, open_price=float(row["open"]), high_price=float(row["high"]),
                low_price=float(row["low"]), close_price=float(row["close"]),
                prediction=pred, policy=policy, cfg=cfg)

            if res.closed is not None:
                _record(res.closed)
            if res.opened:
                pred_at_entry = 0.0 if (pred is None or np.isnan(pred)) else float(pred)
            eq.append((_py(ts), res.equity))

        # close residual at last bar — 백테스트만의 규칙(라이브 세션은 열어 둔다).
        # 정본 계획에서 `close_at_end` 설정으로 표현할 항목(D6).
        if st.side != "flat":
            st, tr = kernel_close(st, float(bars.iloc[-1]["close"]), bars.index[-1],
                                  "eod", cfg)
            _record(tr)
        cash = st.cash

        bh = (float(bars.iloc[-1]["close"]) - float(bars.iloc[0]["open"])) / float(bars.iloc[0]["open"])
        kpis = BacktestKPIs(
            symbol=symbol,
            start=bars.index[0].to_pydatetime() if hasattr(bars.index[0], "to_pydatetime") else bars.index[0],
            end=bars.index[-1].to_pydatetime() if hasattr(bars.index[-1], "to_pydatetime") else bars.index[-1],
            initial_capital=self.initial_capital,
            final_capital=cash,
            trades=trades,
            equity_curve=eq,
            predictions=preds_aligned,
            buy_hold_pct=float(bh),
        )
        self._fill_kpis(kpis)
        return kpis

    # -- helpers --

    def _kernel_config(self) -> KernelConfig:
        """백테스터의 현행 회계를 정본(Canon) 설정으로 표현한다.

        브래킷 기본값 없음 — 예전 코드의 `action.sl_price or 0.0` 과 같다
        (None 도 0.0 도 비활성). orchestrator 는 SL4%/TP10% 를 넣는데, 그
        격차(D2)는 3b 에서 따로 다룬다. 2단계는 행동을 바꾸지 않는다.
        """
        return KernelConfig(size_pct=self.size_pct, fee_rate=self.fee_rate,
                            apply_fee_to_short=self.apply_fee_to_short,
                            default_sl_pct=None, default_tp_pct=None)

    def _fill_kpis(self, k: BacktestKPIs) -> None:
        n = len(k.trades)
        k.n_trades = n
        k.total_return_pct = (k.final_capital - k.initial_capital) / k.initial_capital
        if k.equity_curve:
            eq = np.array([e for _, e in k.equity_curve])
            peaks = np.maximum.accumulate(eq)
            dd = (peaks - eq) / peaks
            k.max_drawdown_pct = float(dd.max())
        if n > 0:
            rets = np.array([t.return_pct for t in k.trades])
            wins = rets[rets > 0]; losses = rets[rets <= 0]
            k.win_rate = float(len(wins) / n)
            k.avg_win_pct = float(wins.mean()) if len(wins) else 0.0
            k.avg_loss_pct = float(losses.mean()) if len(losses) else 0.0
            gw = float(wins.sum()); gl = -float(losses.sum())
            k.profit_factor = gw / gl if gl > 0 else float("inf") if gw > 0 else 0.0
            if rets.std(ddof=1) > 0:
                tpy = n / max(1.0, (k.end - k.start).days / 365.0)
                k.sharpe_per_trade_annualized = float(rets.mean() / rets.std(ddof=1) * np.sqrt(tpy))
            counts: dict[str, int] = {}
            for t in k.trades:
                counts[t.exit_reason] = counts.get(t.exit_reason, 0) + 1
            k.exit_reasons = counts
