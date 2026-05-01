"""
MLDirect — AI-native ML classifier on multi-TF engineered features.

설계 철학:
  - 인간이 만든 indicator (RSI/MACD/BB/ATR 등)를 raw input으로 사용
  - AI는 이들의 비선형 조합을 학습 (인간 if-then보다 훨씬 복잡한 의사결정 경계)
  - Multi-TF 동시 활용 (1m/5m/15m/1h) — 인간이 동시에 못 봄
  - Target: "다음 30분 +0.3% 이상 갈 확률" (binary classification)
  - Trade: P(up) > threshold일 때만 진입

특징:
  - 인간 지표 활용 → 해석 가능 + domain knowledge embed
  - AI는 patterns 학습 (어떤 indicator 조합이 어느 시점 의미 있는지)
  - LightGBM 사용 (small data + tabular features에 강함)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import lightgbm as lgb


@dataclass
class MLDirectConfig:
    # Target definition
    target_horizon_bars: int = 30      # predict ahead 30 min
    target_threshold_pct: float = 0.003  # +0.3% threshold

    # Trade execution
    tp_pct: float = 0.005              # +0.5% take profit
    sl_pct: float = 0.003              # -0.3% stop loss
    max_hold_bars: int = 30            # exit after 30 bars
    decision_step: int = 5             # check signal every N bars

    # Signal threshold
    min_prob: float = 0.62             # P(up) >= 0.62 to trade

    # Model hyperparams
    n_estimators: int = 100
    max_depth: int = 5
    num_leaves: int = 15
    learning_rate: float = 0.05
    min_child_samples: int = 20
    reg_alpha: float = 0.1
    reg_lambda: float = 0.1

    # Sample requirements
    min_train_samples: int = 1000


# ────────────────── Indicator helpers ──────────────────


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def _atr(h, l, c, period=14):
    pc = c.shift(1)
    tr = pd.concat(
        [(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _macd(closes, fast=12, slow=26, signal=9):
    ef = closes.ewm(span=fast, adjust=False).mean()
    es = closes.ewm(span=slow, adjust=False).mean()
    macd = ef - es
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd - sig  # histogram


def _bb_pct_b(closes, period=20, std_n=2.0):
    mid = closes.rolling(period).mean()
    std = closes.rolling(period).std(ddof=0)
    upper = mid + std_n * std
    lower = mid - std_n * std
    return ((closes - lower) / (upper - lower).replace(0, np.nan)).fillna(0.5)


def _adx(h, l, c, period=14):
    up = h.diff()
    dn = -l.diff()
    pdm = ((up > dn) & (up > 0)).astype(float) * up
    mdm = ((dn > up) & (dn > 0)).astype(float) * dn
    a = _atr(h, l, c, period)
    pdi = 100 * pdm.ewm(alpha=1 / period, adjust=False).mean() / a.replace(0, np.nan)
    mdi = 100 * mdm.ewm(alpha=1 / period, adjust=False).mean() / a.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0)


def _williams_r(h, l, c, period=14):
    hh = h.rolling(period).max()
    ll = l.rolling(period).min()
    return (-100 * (hh - c) / (hh - ll).replace(0, np.nan)).fillna(-50.0)


def _resample_ohlcv(df_1m, freq_min):
    if freq_min == 1:
        return df_1m
    rule = f"{freq_min}min"
    out = df_1m.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    ).dropna(subset=["open"])
    return out


# ────────────────── Feature extraction ──────────────────


FEATURE_NAMES: List[str] = [
    # 1m features
    "rsi_1m_14",
    "ema_slope_1m_20",
    "atr_pct_1m_14",
    "bb_pctb_1m_20",
    "macd_hist_1m_norm",
    "wr_1m_14",
    "adx_1m_14",
    "vol_z_1m_60",
    "donchian_pos_1m_20",
    "ret_5m",
    # 5m features
    "rsi_5m_14",
    "ema_slope_5m_20",
    "atr_pct_5m_14",
    "bb_pctb_5m_20",
    "wr_5m_14",
    "vol_z_5m_60",
    "ret_30m",
    # 15m features
    "rsi_15m_14",
    "ema_slope_15m_20",
    "ret_2h",
    # 1h features
    "rsi_1h_14",
    "ema_slope_1h_20",
    "ret_8h",
    # cross-TF
    "trend_align_1m_5m_15m",
    "vol_regime_30d",
]
FEATURE_DIM = len(FEATURE_NAMES)


def extract_features(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Compute all features per 1m bar. Returns DataFrame indexed same as df_1m.

    All features are look-ahead safe (use only past data).
    NaN-fill at the end (early bars without enough history).
    """
    out = pd.DataFrame(index=df_1m.index)

    # Resample
    df_5m = _resample_ohlcv(df_1m, 5)
    df_15m = _resample_ohlcv(df_1m, 15)
    df_1h = _resample_ohlcv(df_1m, 60)

    # 1m features
    out["rsi_1m_14"] = _rsi(df_1m["close"], 14)
    ema20_1m = _ema(df_1m["close"], 20)
    out["ema_slope_1m_20"] = (ema20_1m - ema20_1m.shift(20)) / ema20_1m.shift(20).abs()
    out["atr_pct_1m_14"] = _atr(df_1m["high"], df_1m["low"], df_1m["close"], 14) / df_1m["close"]
    out["bb_pctb_1m_20"] = _bb_pct_b(df_1m["close"], 20, 2.0)
    macd_h = _macd(df_1m["close"])
    out["macd_hist_1m_norm"] = macd_h / df_1m["close"]
    out["wr_1m_14"] = _williams_r(df_1m["high"], df_1m["low"], df_1m["close"], 14)
    out["adx_1m_14"] = _adx(df_1m["high"], df_1m["low"], df_1m["close"], 14)
    vol_mean_60 = df_1m["volume"].rolling(60, min_periods=10).mean()
    vol_std_60 = df_1m["volume"].rolling(60, min_periods=10).std(ddof=0)
    out["vol_z_1m_60"] = ((df_1m["volume"] - vol_mean_60) / vol_std_60.replace(0, np.nan)).fillna(0)
    don_high = df_1m["high"].rolling(20).max()
    don_low = df_1m["low"].rolling(20).min()
    out["donchian_pos_1m_20"] = ((df_1m["close"] - don_low) / (don_high - don_low).replace(0, np.nan)).fillna(0.5)
    out["ret_5m"] = df_1m["close"].pct_change(5).fillna(0)

    # 5m features — LOOK-AHEAD SAFE: shift(1) so at floor(t) we see PREVIOUS completed 5m bar
    if len(df_5m) > 30:
        rsi_5m = _rsi(df_5m["close"], 14).shift(1)
        ema20_5m = _ema(df_5m["close"], 20)
        ema_slope_5m = ((ema20_5m - ema20_5m.shift(20)) / ema20_5m.shift(20).abs()).shift(1)
        atr_5m = _atr(df_5m["high"], df_5m["low"], df_5m["close"], 14).shift(1)
        atr_pct_5m = (atr_5m / df_5m["close"].shift(1))
        bb_5m = _bb_pct_b(df_5m["close"], 20, 2.0).shift(1)
        wr_5m = _williams_r(df_5m["high"], df_5m["low"], df_5m["close"], 14).shift(1)
        vol_mean_5m = df_5m["volume"].rolling(60, min_periods=10).mean()
        vol_std_5m = df_5m["volume"].rolling(60, min_periods=10).std(ddof=0)
        vz_5m = (((df_5m["volume"] - vol_mean_5m) / vol_std_5m.replace(0, np.nan))
                 .fillna(0)).shift(1)
        ret_30m_5m = df_5m["close"].pct_change(6).fillna(0).shift(1)

        floored_5m = df_1m.index.floor("5min")
        out["rsi_5m_14"] = rsi_5m.reindex(floored_5m, method="ffill").set_axis(df_1m.index)
        out["ema_slope_5m_20"] = ema_slope_5m.reindex(floored_5m, method="ffill").set_axis(df_1m.index)
        out["atr_pct_5m_14"] = atr_pct_5m.reindex(floored_5m, method="ffill").set_axis(df_1m.index)
        out["bb_pctb_5m_20"] = bb_5m.reindex(floored_5m, method="ffill").set_axis(df_1m.index)
        out["wr_5m_14"] = wr_5m.reindex(floored_5m, method="ffill").set_axis(df_1m.index)
        out["vol_z_5m_60"] = vz_5m.reindex(floored_5m, method="ffill").set_axis(df_1m.index)
        out["ret_30m"] = ret_30m_5m.reindex(floored_5m, method="ffill").set_axis(df_1m.index)
    else:
        for f in ["rsi_5m_14", "ema_slope_5m_20", "atr_pct_5m_14", "bb_pctb_5m_20",
                  "wr_5m_14", "vol_z_5m_60", "ret_30m"]:
            out[f] = 0.0

    # 15m features — shift(1) for look-ahead safety
    if len(df_15m) > 30:
        rsi_15m = _rsi(df_15m["close"], 14).shift(1)
        ema20_15m = _ema(df_15m["close"], 20)
        ema_slope_15m = ((ema20_15m - ema20_15m.shift(20)) / ema20_15m.shift(20).abs()).shift(1)
        ret_2h_15m = df_15m["close"].pct_change(8).fillna(0).shift(1)
        floored_15m = df_1m.index.floor("15min")
        out["rsi_15m_14"] = rsi_15m.reindex(floored_15m, method="ffill").set_axis(df_1m.index)
        out["ema_slope_15m_20"] = ema_slope_15m.reindex(floored_15m, method="ffill").set_axis(df_1m.index)
        out["ret_2h"] = ret_2h_15m.reindex(floored_15m, method="ffill").set_axis(df_1m.index)
    else:
        for f in ["rsi_15m_14", "ema_slope_15m_20", "ret_2h"]:
            out[f] = 0.0

    # 1h features — shift(1) for look-ahead safety
    if len(df_1h) > 30:
        rsi_1h = _rsi(df_1h["close"], 14).shift(1)
        ema20_1h = _ema(df_1h["close"], 20)
        ema_slope_1h = ((ema20_1h - ema20_1h.shift(20)) / ema20_1h.shift(20).abs()).shift(1)
        ret_8h_1h = df_1h["close"].pct_change(8).fillna(0).shift(1)
        floored_1h = df_1m.index.floor("1H")
        out["rsi_1h_14"] = rsi_1h.reindex(floored_1h, method="ffill").set_axis(df_1m.index)
        out["ema_slope_1h_20"] = ema_slope_1h.reindex(floored_1h, method="ffill").set_axis(df_1m.index)
        out["ret_8h"] = ret_8h_1h.reindex(floored_1h, method="ffill").set_axis(df_1m.index)
    else:
        for f in ["rsi_1h_14", "ema_slope_1h_20", "ret_8h"]:
            out[f] = 0.0

    # Cross-TF features
    # trend_align_1m_5m_15m: count of (slope > 0) in {1m, 5m, 15m} EMAs (0..3)
    out["trend_align_1m_5m_15m"] = (
        (out["ema_slope_1m_20"] > 0).astype(int)
        + (out["ema_slope_5m_20"] > 0).astype(int)
        + (out["ema_slope_15m_20"] > 0).astype(int)
    )

    # vol_regime_30d — shift(1) for look-ahead safety (use prior day vol percentile)
    df_1d = _resample_ohlcv(df_1m, 1440)
    if len(df_1d) >= 10:
        d_returns = df_1d["close"].pct_change().dropna()
        vol_30 = d_returns.rolling(30, min_periods=5).std()
        vol_pct = vol_30.rank(pct=True).fillna(0.5).shift(1)  # use yesterday's vol percentile
        floored_1d = df_1m.index.normalize()
        out["vol_regime_30d"] = vol_pct.reindex(floored_1d, method="ffill").set_axis(df_1m.index).fillna(0.5)
    else:
        out["vol_regime_30d"] = 0.5

    # Final NaN cleanup
    out = out.fillna(0.0).replace([np.inf, -np.inf], 0.0)

    # Reorder columns to match FEATURE_NAMES
    out = out[FEATURE_NAMES]
    return out


def make_target(df_1m: pd.DataFrame, horizon_bars: int, threshold_pct: float) -> pd.Series:
    """Binary target: did close go up by >= threshold within next horizon_bars?"""
    closes = df_1m["close"]
    # max future close within horizon
    future_max = closes.rolling(window=horizon_bars, min_periods=1).max().shift(-horizon_bars)
    target = (future_max / closes - 1.0 >= threshold_pct).astype(int)
    return target


# ────────────────── Engine ──────────────────


class MLDirectEngine:
    """Trains a LightGBM classifier on history, predicts on test window."""

    def __init__(self, config: MLDirectConfig = None):
        self.config = config or MLDirectConfig()
        self._model: Optional[lgb.LGBMClassifier] = None
        self._feature_importances: Optional[Dict[str, float]] = None
        self._n_train: int = 0
        self._train_pos_rate: float = 0.0

    def _feed_to_df(self, feed: List[Dict]) -> pd.DataFrame:
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("ts").sort_index()
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    def fit(self, historical_feed: List[Dict]) -> "MLDirectEngine":
        df = self._feed_to_df(historical_feed)
        if len(df) < self.config.min_train_samples + self.config.target_horizon_bars + 100:
            raise ValueError(
                f"Not enough data: {len(df)} < min "
                f"{self.config.min_train_samples + self.config.target_horizon_bars + 100}"
            )

        features_df = extract_features(df)
        target = make_target(df, self.config.target_horizon_bars, self.config.target_threshold_pct)

        # Drop rows with NaN target (last horizon_bars)
        valid = target.notna()
        # Also drop early rows with insufficient warmup (first 240 = enough for all rolling windows)
        valid.iloc[:240] = False

        X = features_df.loc[valid].values
        y = target.loc[valid].values.astype(int)

        if len(X) < self.config.min_train_samples:
            raise ValueError(f"After cleaning: {len(X)} < min {self.config.min_train_samples}")

        # Class imbalance — use class_weight to balance
        pos_rate = y.mean()
        if pos_rate < 0.05 or pos_rate > 0.95:
            raise ValueError(f"Severe class imbalance: pos_rate={pos_rate:.3f}")

        self._model = lgb.LGBMClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            num_leaves=self.config.num_leaves,
            learning_rate=self.config.learning_rate,
            min_child_samples=self.config.min_child_samples,
            reg_alpha=self.config.reg_alpha,
            reg_lambda=self.config.reg_lambda,
            # NO class_weight — let probability calibration stay natural
            verbose=-1,
            force_row_wise=True,
        )
        self._model.fit(X, y)
        self._n_train = len(X)
        self._train_pos_rate = float(pos_rate)

        # Feature importances
        gain = self._model.booster_.feature_importance(importance_type="gain")
        total = float(gain.sum()) or 1.0
        self._feature_importances = {FEATURE_NAMES[i]: float(gain[i] / total)
                                     for i in range(len(FEATURE_NAMES))}
        return self

    def predict_proba_series(self, feed: List[Dict]) -> pd.Series:
        """Compute P(up) for every bar in feed."""
        if self._model is None:
            raise RuntimeError("MLDirectEngine not fitted")
        df = self._feed_to_df(feed)
        features_df = extract_features(df)
        proba = self._model.predict_proba(features_df.values)[:, 1]
        return pd.Series(proba, index=features_df.index)

    def backtest(
        self,
        test_feed: List[Dict],
        initial_capital: float = 10_000.0,
        fee_rate: float = 0.0004,
    ) -> Dict:
        if self._model is None:
            raise RuntimeError("MLDirectEngine not fitted")

        cfg = self.config
        df = self._feed_to_df(test_feed)
        features_df = extract_features(df)
        proba = self._model.predict_proba(features_df.values)[:, 1]
        timestamps = features_df.index.tolist()

        closes = df["close"].values
        n = len(df)

        cash = initial_capital
        position_qty = 0.0
        entry_price = 0.0
        entry_idx = 0
        trades = []
        peak_equity = cash
        max_dd = 0.0

        # Skip warmup
        i = 240
        while i < n:
            current_price = closes[i]

            # ── Exit ──
            if position_qty > 0:
                if current_price <= entry_price * (1 - cfg.sl_pct):
                    revenue = position_qty * current_price * (1 - fee_rate)
                    cash += revenue
                    trades.append({
                        "entry_time": str(timestamps[entry_idx]),
                        "exit_time": str(timestamps[i]),
                        "entry_price": float(entry_price),
                        "exit_price": float(current_price),
                        "pnl_pct": float((current_price / entry_price - 1) - 2 * fee_rate),
                        "reason": "sl",
                    })
                    position_qty = 0.0
                    i += 1
                    continue
                if current_price >= entry_price * (1 + cfg.tp_pct):
                    revenue = position_qty * current_price * (1 - fee_rate)
                    cash += revenue
                    trades.append({
                        "entry_time": str(timestamps[entry_idx]),
                        "exit_time": str(timestamps[i]),
                        "entry_price": float(entry_price),
                        "exit_price": float(current_price),
                        "pnl_pct": float((current_price / entry_price - 1) - 2 * fee_rate),
                        "reason": "tp",
                    })
                    position_qty = 0.0
                    i += 1
                    continue
                if i - entry_idx >= cfg.max_hold_bars:
                    revenue = position_qty * current_price * (1 - fee_rate)
                    cash += revenue
                    trades.append({
                        "entry_time": str(timestamps[entry_idx]),
                        "exit_time": str(timestamps[i]),
                        "entry_price": float(entry_price),
                        "exit_price": float(current_price),
                        "pnl_pct": float((current_price / entry_price - 1) - 2 * fee_rate),
                        "reason": "max_hold",
                    })
                    position_qty = 0.0
                    i += 1
                    continue

            # ── Entry ──
            if position_qty == 0 and (i - 240) % cfg.decision_step == 0:
                if proba[i] >= cfg.min_prob:
                    qty = (cash * 0.95) / (current_price * (1 + fee_rate))
                    if qty > 0:
                        cost = qty * current_price * (1 + fee_rate)
                        cash -= cost
                        position_qty = qty
                        entry_price = current_price
                        entry_idx = i

            current_equity = cash + position_qty * current_price
            if current_equity > peak_equity:
                peak_equity = current_equity
            dd = (current_equity - peak_equity) / peak_equity * 100
            if dd < max_dd:
                max_dd = dd

            i += 1

        # Force liquidate
        if position_qty > 0:
            revenue = position_qty * closes[-1] * (1 - fee_rate)
            cash += revenue
            trades.append({
                "entry_time": str(timestamps[entry_idx]),
                "exit_time": str(timestamps[-1]),
                "entry_price": float(entry_price),
                "exit_price": float(closes[-1]),
                "pnl_pct": float((closes[-1] / entry_price - 1) - 2 * fee_rate),
                "reason": "eot",
            })
            position_qty = 0.0

        final_equity = cash
        return_pct = (final_equity - initial_capital) / initial_capital * 100

        wins = sum(1 for t in trades if t["pnl_pct"] > 0)
        win_rate = (wins / len(trades) * 100) if trades else 0.0
        avg_pnl = np.mean([t["pnl_pct"] for t in trades]) if trades else 0.0
        std_pnl = np.std([t["pnl_pct"] for t in trades]) if trades else 0.0
        sharpe = (avg_pnl / std_pnl * np.sqrt(len(trades))) if std_pnl > 0 else 0.0

        # Signal stats
        sig_count = int(np.sum(proba[240:] >= cfg.min_prob))
        avg_proba_when_signal = float(np.mean(proba[240:][proba[240:] >= cfg.min_prob])) if sig_count > 0 else 0.0

        return {
            "initial_capital": initial_capital,
            "final_equity": final_equity,
            "return_pct": return_pct,
            "trades_count": len(trades),
            "win_rate": win_rate,
            "avg_pnl_pct": avg_pnl * 100,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "n_train": self._n_train,
            "train_pos_rate": self._train_pos_rate,
            "signal_count": sig_count,
            "avg_proba_when_signal": avg_proba_when_signal,
            "trades": trades,
        }
