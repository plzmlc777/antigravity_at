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

from .pipeline import Pipeline
from .policy import Action, PolicyContext, TradingPolicy
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
        cash = self.initial_capital
        qty = 0.0
        side = "flat"
        entry_price = 0.0
        entry_idx = -1
        sl_price = 0.0
        tp_price = 0.0
        trades: list[BacktestTrade] = []
        eq: list[tuple[datetime, float]] = []

        bars = bars.sort_index()
        # align predictions to bars
        preds_aligned = predictions.reindex(bars.index)

        for i in range(len(bars)):
            ts = bars.index[i]
            o = float(bars.iloc[i]["open"])
            h = float(bars.iloc[i]["high"])
            l = float(bars.iloc[i]["low"])
            c = float(bars.iloc[i]["close"])
            pred = float(preds_aligned.iloc[i]) if i < len(preds_aligned) else np.nan

            # 1) Forced exits (SL/TP intrabar) — checked BEFORE policy.decide for fairness
            forced_exit_reason: Optional[str] = None
            forced_exit_price: Optional[float] = None
            # 0.0 = bracket disabled (policy returned None/0) — must not be read
            # as a level, else `h >= 0` / `l <= 0` fires an instant exit at 0.
            if side == "long":
                if sl_price > 0 and l <= sl_price:
                    forced_exit_reason, forced_exit_price = "sl", sl_price
                elif tp_price > 0 and h >= tp_price:
                    forced_exit_reason, forced_exit_price = "tp", tp_price
            elif side == "short":
                if sl_price > 0 and h >= sl_price:
                    forced_exit_reason, forced_exit_price = "sl", sl_price
                elif tp_price > 0 and l <= tp_price:
                    forced_exit_reason, forced_exit_price = "tp", tp_price

            # 2) Policy decision (sees current bar)
            ctx = PolicyContext(
                timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                prediction=pred, open_price=o, high_price=h, low_price=l, close_price=c,
                in_position=(side != "flat"), side=side,
                entry_price=entry_price,
                bars_held=(i - entry_idx) if side != "flat" else 0,
            )
            action = policy.decide(ctx)

            # 3) Apply exits
            if forced_exit_reason is not None:
                self._close_position(
                    side=side, qty=qty, entry_price=entry_price,
                    exit_price=forced_exit_price, exit_ts=ts, entry_ts=bars.index[entry_idx],
                    exit_reason=forced_exit_reason, prediction_entry=preds_aligned.iloc[entry_idx],
                    cash_holder=lambda d: setattr(self, "_tmp_cash", cash + d),
                    trades=trades,
                )
                cash = getattr(self, "_tmp_cash")
                qty = 0.0; side = "flat"
            elif action.kind == "exit" and side != "flat":
                self._close_position(
                    side=side, qty=qty, entry_price=entry_price,
                    exit_price=o, exit_ts=ts, entry_ts=bars.index[entry_idx],
                    exit_reason=action.note or "policy",
                    prediction_entry=preds_aligned.iloc[entry_idx],
                    cash_holder=lambda d: setattr(self, "_tmp_cash", cash + d),
                    trades=trades,
                )
                cash = getattr(self, "_tmp_cash")
                qty = 0.0; side = "flat"

            # 4) Entries
            if side == "flat" and action.kind in ("enter_long", "enter_short"):
                if action.kind == "enter_long":
                    qty = (cash * self.size_pct) / (o * (1 + self.fee_rate))
                    cash -= qty * o * (1 + self.fee_rate)
                    side = "long"
                else:
                    qty = (cash * self.size_pct) / o
                    cash -= qty * o  # collateral
                    side = "short"
                entry_price = o
                entry_idx = i
                sl_price = action.sl_price or 0.0
                tp_price = action.tp_price or 0.0

            # 5) Mark-to-market
            if side == "long":
                mtm = cash + qty * c
            elif side == "short":
                mtm = cash + qty * (entry_price - c) + qty * entry_price
            else:
                mtm = cash
            eq.append((ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts, mtm))

        # close residual at last bar
        if side != "flat":
            last_close = float(bars.iloc[-1]["close"])
            self._close_position(
                side=side, qty=qty, entry_price=entry_price,
                exit_price=last_close, exit_ts=bars.index[-1],
                entry_ts=bars.index[entry_idx],
                exit_reason="eod",
                prediction_entry=preds_aligned.iloc[entry_idx],
                cash_holder=lambda d: setattr(self, "_tmp_cash", cash + d),
                trades=trades,
            )
            cash = getattr(self, "_tmp_cash")

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

    def _close_position(
        self, *, side, qty, entry_price, exit_price, exit_ts, entry_ts,
        exit_reason, prediction_entry, cash_holder, trades,
    ):
        if side == "long":
            proceeds = qty * exit_price * (1 - self.fee_rate)
            cost = qty * entry_price * (1 + self.fee_rate)
            ret = (proceeds - cost) / cost
            cash_holder(proceeds)
        else:  # short
            # 숏 수수료는 **양다리 모두 청산 시점에** 계상한다. 진입 시 차감하면
            # 구방식으로 이미 열려 있는 포지션이 진입 수수료를 낸 적이 없는데
            # 청산에서 빼게 돼 보고 수익률과 현금 변화가 어긋난다. 완결된 거래
            # 기준으로는 진입 시 차감과 경제적으로 동일하다.
            fee = self.fee_rate if self.apply_fee_to_short else 0.0
            gross = qty * (entry_price - float(exit_price))
            fees = qty * entry_price * fee + qty * float(exit_price) * fee
            proceeds = gross - fees
            cost = qty * entry_price
            ret = proceeds / cost
            cash_holder(cost + proceeds)
        trades.append(BacktestTrade(
            entry_ts=entry_ts.to_pydatetime() if hasattr(entry_ts, "to_pydatetime") else entry_ts,
            exit_ts=exit_ts.to_pydatetime() if hasattr(exit_ts, "to_pydatetime") else exit_ts,
            side=side, entry_price=entry_price, exit_price=float(exit_price),
            qty=qty, return_pct=float(ret), exit_reason=exit_reason,
            prediction_at_entry=float(prediction_entry) if prediction_entry is not None and not np.isnan(prediction_entry) else 0.0,
        ))

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
