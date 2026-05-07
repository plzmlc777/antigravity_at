"""Walk-forward LightGBM backtester.

Pipeline:
  1. Build feature matrix on full eval-frequency data
  2. Walk-forward CV: train on rolling window of past N days, predict next M days
  3. Trade based on predictions: if predicted_fwd_ret > entry_threshold → long,
     if < -entry_threshold → short (if long_only=False); else hold
  4. Track trades, equity, KPIs

This is the bona fide "AI-native composer" — fully learned, not heuristic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from .features import build_feature_matrix
from .lgbm_composer import LGBMComposer, LGBMComposerConfig

logger = logging.getLogger(__name__)


@dataclass
class MLBacktestConfig:
    eval_freq_minutes: int = 60 * 24       # daily
    forward_bars: int = 5                  # 5d forward target
    train_window_bars: int = 200           # ~200 daily bars = 9 months
    retrain_step_bars: int = 20            # retrain every 20 daily bars (~1 month)
    pattern_lookback_bars: int = 5
    entry_threshold: float = 0.005         # |predicted| >= this → take position
    sl_pct: float = 0.05
    tp_pct: float = 0.15
    long_only: bool = False
    fee_rate: float = 0.0005               # crypto futures default
    size_pct: float = 0.95
    holding_bars: int = 5                  # exit after N bars regardless


class MLPatternBacktester:
    def __init__(
        self,
        *,
        initial_capital: float = 10_000.0,
        config: MLBacktestConfig | None = None,
        composer_config: LGBMComposerConfig | None = None,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.config = config or MLBacktestConfig()
        self.composer_config = composer_config or LGBMComposerConfig()

    def run(
        self,
        *,
        symbol: str,
        ohlcv_eval: pd.DataFrame,
        signals_df: pd.DataFrame,
        regime_eval: pd.DataFrame,
    ) -> dict:
        cfg = self.config
        # 1) features
        feat = build_feature_matrix(
            ohlcv_eval=ohlcv_eval,
            signals_df=signals_df,
            regime_eval=regime_eval,
            eval_freq_minutes=cfg.eval_freq_minutes,
            forward_bars=cfg.forward_bars,
            pattern_lookback_bars=cfg.pattern_lookback_bars,
        )

        # 2) walk-forward predictions
        predictions = pd.Series(np.nan, index=feat.index, dtype=float)
        n = len(feat)
        first_predict_at = cfg.train_window_bars
        retrain_count = 0
        last_train_idx = -10**9

        for i in range(first_predict_at, n):
            if i - last_train_idx >= cfg.retrain_step_bars or self._no_model:
                # retrain on past train_window_bars samples ending at i (exclusive)
                train_start = max(0, i - cfg.train_window_bars)
                train_df = feat.iloc[train_start:i].copy()
                # only train on rows where target is observed
                train_df = train_df.dropna(subset=["target_fwd_ret"])
                if len(train_df) < 50:
                    continue
                self.composer = LGBMComposer(self.composer_config)
                self.composer.fit(train_df, target_col="target_fwd_ret")
                last_train_idx = i
                retrain_count += 1
            # predict for current bar
            row = feat.iloc[[i]]
            pred = self.composer.predict(row)[0]
            predictions.iloc[i] = pred

        # 3) backtest using predictions
        bars = ohlcv_eval.copy()
        cash = self.initial_capital
        qty = 0.0
        side = "flat"
        entry_price = 0.0
        entry_idx = -1
        equity = []
        trades: list[dict] = []

        for i in range(len(bars)):
            ts = bars.index[i]
            o = float(bars.iloc[i]["open"])
            close = float(bars.iloc[i]["close"])
            pred = predictions.iloc[i] if i < len(predictions) else np.nan

            # exit logic first
            if side != "flat":
                bars_held = i - entry_idx
                exit_reason = None
                exit_price = o

                if side == "long":
                    if (close <= entry_price * (1 - cfg.sl_pct)):
                        exit_reason = "sl"
                        exit_price = entry_price * (1 - cfg.sl_pct)
                    elif (close >= entry_price * (1 + cfg.tp_pct)):
                        exit_reason = "tp"
                        exit_price = entry_price * (1 + cfg.tp_pct)
                else:
                    if (close >= entry_price * (1 + cfg.sl_pct)):
                        exit_reason = "sl"
                        exit_price = entry_price * (1 + cfg.sl_pct)
                    elif (close <= entry_price * (1 - cfg.tp_pct)):
                        exit_reason = "tp"
                        exit_price = entry_price * (1 - cfg.tp_pct)

                if exit_reason is None and bars_held >= cfg.holding_bars:
                    exit_reason = "time"
                    exit_price = o

                if exit_reason is None and not np.isnan(pred):
                    if side == "long" and pred < -cfg.entry_threshold * 0.5:
                        exit_reason = "flip"; exit_price = o
                    elif side == "short" and pred > cfg.entry_threshold * 0.5:
                        exit_reason = "flip"; exit_price = o

                if exit_reason:
                    if side == "long":
                        proceeds = qty * exit_price * (1 - cfg.fee_rate)
                        cost = qty * entry_price * (1 + cfg.fee_rate)
                        ret = (proceeds - cost) / cost
                        cash += proceeds
                    else:  # short
                        # P&L = qty * (entry - exit) - fees
                        proceeds = qty * (entry_price - exit_price) - qty * (entry_price + exit_price) * cfg.fee_rate / 2
                        cost = qty * entry_price
                        ret = proceeds / cost
                        cash += cost + proceeds  # release initial collateral + pnl
                    trades.append({
                        "entry_ts": bars.index[entry_idx], "exit_ts": ts,
                        "side": side, "entry_price": entry_price, "exit_price": exit_price,
                        "ret_pct": ret, "exit_reason": exit_reason,
                        "predicted": predictions.iloc[entry_idx] if entry_idx < len(predictions) else np.nan,
                    })
                    qty = 0.0
                    side = "flat"

            # entry logic
            if side == "flat" and not np.isnan(pred):
                if pred > cfg.entry_threshold:
                    qty = (cash * cfg.size_pct) / (o * (1 + cfg.fee_rate))
                    cash -= qty * o * (1 + cfg.fee_rate)
                    side = "long"; entry_price = o; entry_idx = i
                elif (not cfg.long_only) and pred < -cfg.entry_threshold:
                    # short: lock collateral = qty * entry_price
                    qty = (cash * cfg.size_pct) / o
                    cash -= qty * o  # collateral
                    side = "short"; entry_price = o; entry_idx = i

            # mark-to-market
            if side == "long":
                mtm = cash + qty * close
            elif side == "short":
                mtm = cash + qty * (entry_price - close) + qty * entry_price  # collateral + pnl
            else:
                mtm = cash
            equity.append((ts, mtm))

        # close at last
        if side != "flat":
            last_close = float(bars.iloc[-1]["close"])
            if side == "long":
                proceeds = qty * last_close * (1 - cfg.fee_rate)
                cost = qty * entry_price * (1 + cfg.fee_rate)
                ret = (proceeds - cost) / cost
                cash += proceeds
            else:
                proceeds = qty * (entry_price - last_close)
                cost = qty * entry_price
                ret = proceeds / cost
                cash += cost + proceeds
            trades.append({
                "entry_ts": bars.index[entry_idx], "exit_ts": bars.index[-1],
                "side": side, "entry_price": entry_price, "exit_price": last_close,
                "ret_pct": ret, "exit_reason": "eod",
                "predicted": predictions.iloc[entry_idx] if entry_idx < len(predictions) else np.nan,
            })

        # KPIs
        rets = np.array([t["ret_pct"] for t in trades]) if trades else np.array([])
        eq = np.array([e for _, e in equity])
        peaks = np.maximum.accumulate(eq) if len(eq) else np.array([])
        dd = (peaks - eq) / peaks if len(eq) else np.array([])
        bh = (float(bars.iloc[-1]["close"]) - float(bars.iloc[0]["open"])) / float(bars.iloc[0]["open"])

        kpis = {
            "symbol": symbol,
            "n_retrain": retrain_count,
            "n_trades": len(trades),
            "win_rate": float((rets > 0).mean()) if len(rets) else 0.0,
            "total_return_pct": (cash - self.initial_capital) / self.initial_capital,
            "buy_hold_pct": float(bh),
            "max_drawdown_pct": float(dd.max()) if len(dd) else 0.0,
            "sharpe_per_trade_annualized": float(rets.mean() / rets.std() * np.sqrt(len(rets) / max(1.0, (bars.index[-1] - bars.index[0]).days / 365.0))) if len(rets) > 1 and rets.std() > 0 else 0.0,
            "trades": trades,
            "equity_curve": equity,
            "predictions_avail": int(predictions.notna().sum()),
            "exit_reasons": pd.Series([t["exit_reason"] for t in trades]).value_counts().to_dict() if trades else {},
        }
        return kpis

    @property
    def _no_model(self) -> bool:
        return not hasattr(self, "composer") or self.composer is None or self.composer.model is None
