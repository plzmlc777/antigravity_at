"""
Pattern Memory Trader (PMT) — AI-native strategy.

핵심 아이디어:
  "지금 시점 60-bar 패턴이 과거 어느 상황과 가장 비슷한가?
   비슷한 과거 상황들이 직후 어떻게 움직였나?
   상승 패턴이 다수면 매수, 아니면 hold."

인간이 만든 indicator 없음. 순수 패턴 매칭. AI 메모리 기반 매매.

Look-ahead 안전성:
  - 시점 t에서 결정할 때, KNN reference는 t보다 이전에 종료된 60-bar window만 사용
  - "future_return"은 reference window의 직후 30분 (이미 발생한 과거)
  - 시점 t의 미래 데이터 절대 사용 안 함
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.neighbors import NearestNeighbors


@dataclass
class PMTConfig:
    window_bars: int = 60          # signature window size (in resampled bars)
    horizon_bars: int = 30         # predict ahead (in resampled bars)
    k_neighbors: int = 20          # KNN k
    hit_threshold: float = 0.005   # +0.5% target return
    min_hit_rate: float = 0.65     # >65% of neighbors must hit
    min_mean_return: float = 0.003  # >0.3% mean expected
    tp_pct: float = 0.005          # take profit
    sl_pct: float = 0.003          # stop loss
    max_hold_bars: int = 30        # force exit after N bars (in 1m bars regardless of resample)
    decision_step: int = 5         # decide every N 1m-bars
    min_history_signatures: int = 200  # need at least N past patterns
    resample_minutes: int = 1      # 1=use raw 1m, 5=resample to 5m, 15=15m, etc.
                                    # Higher = less noise, slower decisions


class PMTEngine:
    """
    PMT engine — KNN-based pattern matching.

    Workflow:
      1. fit(historical_feed): build KNN reference from all past 60-bar windows
      2. backtest(window_feed): run backtest on a window using fitted KNN
    """

    def __init__(self, config: PMTConfig = None):
        self.config = config or PMTConfig()
        self._reference_signatures: Optional[np.ndarray] = None
        self._reference_returns: Optional[np.ndarray] = None
        self._nn_model: Optional[NearestNeighbors] = None

    # ─────────────────── Signature extraction ───────────────────

    def _signature(
        self,
        closes: np.ndarray,
        volumes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
    ) -> np.ndarray:
        """Compute normalized 180-dim signature from 60 OHLCV bars.

        Components (3 × 60-1 = 177):
          - Normalized log returns (60-1 = 59 dims)
          - Normalized log volumes (60 dims)
          - Normalized log ranges (high-low, 60 dims)
          - Total = 59 + 60 + 60 = 179 dims (close to 180)
        """
        # Log returns
        log_rets = np.log(closes[1:] / closes[:-1])
        log_rets = (log_rets - log_rets.mean()) / (log_rets.std() + 1e-9)

        # Log volumes (add 1 to avoid log(0))
        log_vols = np.log(volumes + 1.0)
        log_vols = (log_vols - log_vols.mean()) / (log_vols.std() + 1e-9)

        # Log ranges (add 1 to avoid log(0))
        ranges = np.maximum(highs - lows, 1e-9)
        log_ranges = np.log(ranges)
        log_ranges = (log_ranges - log_ranges.mean()) / (log_ranges.std() + 1e-9)

        return np.concatenate([log_rets, log_vols, log_ranges]).astype(np.float32)

    def _build_signature_db(
        self,
        feed: List[Dict],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Extract all (signature, future_return) pairs from feed.

        For each 60-bar window ending at index i (using bars i-W..i-1),
        compute signature and future_return = close[i+H-1]/close[i-1] - 1.
        Look-ahead safe: pair (sig_i, ret_i) is fully realized at index i+H.
        """
        W = self.config.window_bars
        H = self.config.horizon_bars

        n = len(feed)
        if n < W + H + 10:
            return np.empty((0, 0), dtype=np.float32), np.empty(0, dtype=np.float32)

        closes = np.array([float(c["close"]) for c in feed], dtype=np.float64)
        volumes = np.array([float(c["volume"]) for c in feed], dtype=np.float64)
        highs = np.array([float(c["high"]) for c in feed], dtype=np.float64)
        lows = np.array([float(c["low"]) for c in feed], dtype=np.float64)

        signatures = []
        future_returns = []

        for i in range(W, n - H):
            sig = self._signature(
                closes[i - W : i],
                volumes[i - W : i],
                highs[i - W : i],
                lows[i - W : i],
            )
            # future return: from i (decision time) to i+H
            future_ret = closes[i + H - 1] / closes[i - 1] - 1.0
            signatures.append(sig)
            future_returns.append(future_ret)

        return np.array(signatures, dtype=np.float32), np.array(future_returns, dtype=np.float32)

    # ─────────────────── Fit (build KNN reference) ───────────────────

    def fit(self, historical_feed: List[Dict]) -> "PMTEngine":
        """Build KNN reference from historical OHLCV feed.

        Args:
            historical_feed: list of 1m bars (timestamp, OHLCV) — should END before
                the test window starts to avoid look-ahead.
        """
        sigs, rets = self._build_signature_db(historical_feed)
        if len(sigs) < self.config.min_history_signatures:
            raise ValueError(
                f"Not enough history: {len(sigs)} signatures < min "
                f"{self.config.min_history_signatures}"
            )
        self._reference_signatures = sigs
        self._reference_returns = rets
        self._nn_model = NearestNeighbors(
            n_neighbors=min(self.config.k_neighbors, len(sigs)),
            metric="euclidean",
            algorithm="auto",
        )
        self._nn_model.fit(sigs)
        return self

    # ─────────────────── Predict at single point ───────────────────

    def predict(
        self,
        current_window_closes: np.ndarray,
        current_window_volumes: np.ndarray,
        current_window_highs: np.ndarray,
        current_window_lows: np.ndarray,
    ) -> Dict:
        """Given current 60-bar window, return prediction.

        Returns dict with: hit_rate, mean_return, std_return, k_used, signal (bool).
        """
        if self._nn_model is None:
            return {"signal": False, "reason": "not_fitted"}

        sig = self._signature(
            current_window_closes,
            current_window_volumes,
            current_window_highs,
            current_window_lows,
        )
        distances, indices = self._nn_model.kneighbors(sig.reshape(1, -1))
        neighbor_returns = self._reference_returns[indices[0]]

        hit_rate = float((neighbor_returns > self.config.hit_threshold).mean())
        mean_return = float(neighbor_returns.mean())
        std_return = float(neighbor_returns.std(ddof=0))

        signal = (
            hit_rate >= self.config.min_hit_rate
            and mean_return >= self.config.min_mean_return
        )

        return {
            "signal": signal,
            "hit_rate": hit_rate,
            "mean_return": mean_return,
            "std_return": std_return,
            "k_used": len(neighbor_returns),
            "neighbor_distances": distances[0].tolist(),
        }

    # ─────────────────── Backtest on test window ───────────────────

    def backtest(
        self,
        test_feed: List[Dict],
        initial_capital: float = 10_000.0,
        fee_rate: float = 0.0004,
    ) -> Dict:
        """Run backtest on test window. Engine must be fitted first.

        Returns: dict with return_pct, sharpe, trades, win_rate, max_drawdown, etc.
        """
        if self._nn_model is None:
            raise RuntimeError("PMTEngine not fitted")

        cfg = self.config
        W = cfg.window_bars
        n = len(test_feed)
        if n < W + 5:
            return self._empty_result()

        closes = np.array([float(c["close"]) for c in test_feed], dtype=np.float64)
        volumes = np.array([float(c["volume"]) for c in test_feed], dtype=np.float64)
        highs = np.array([float(c["high"]) for c in test_feed], dtype=np.float64)
        lows = np.array([float(c["low"]) for c in test_feed], dtype=np.float64)
        timestamps = [c["timestamp"] for c in test_feed]

        cash = initial_capital
        position_qty = 0.0
        entry_price = 0.0
        entry_idx = 0
        trades = []
        equity_curve = [(timestamps[0], cash)]
        peak_equity = cash
        max_dd = 0.0

        i = W
        while i < n:
            current_price = closes[i]

            # ── Exit logic (if in position) ──
            if position_qty > 0:
                # SL
                if current_price <= entry_price * (1 - cfg.sl_pct):
                    revenue = position_qty * current_price * (1 - fee_rate)
                    cash += revenue
                    pnl = revenue - position_qty * entry_price * (1 + fee_rate)
                    trades.append({
                        "entry_time": timestamps[entry_idx],
                        "exit_time": timestamps[i],
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": (current_price / entry_price - 1) - 2 * fee_rate,
                        "reason": "sl",
                    })
                    position_qty = 0.0
                    i += 1
                    continue
                # TP
                if current_price >= entry_price * (1 + cfg.tp_pct):
                    revenue = position_qty * current_price * (1 - fee_rate)
                    cash += revenue
                    trades.append({
                        "entry_time": timestamps[entry_idx],
                        "exit_time": timestamps[i],
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": (current_price / entry_price - 1) - 2 * fee_rate,
                        "reason": "tp",
                    })
                    position_qty = 0.0
                    i += 1
                    continue
                # Max hold
                if i - entry_idx >= cfg.max_hold_bars:
                    revenue = position_qty * current_price * (1 - fee_rate)
                    cash += revenue
                    trades.append({
                        "entry_time": timestamps[entry_idx],
                        "exit_time": timestamps[i],
                        "entry_price": entry_price,
                        "exit_price": current_price,
                        "pnl_pct": (current_price / entry_price - 1) - 2 * fee_rate,
                        "reason": "max_hold",
                    })
                    position_qty = 0.0
                    i += 1
                    continue

            # ── Entry logic (if no position, every decision_step bars) ──
            if position_qty == 0 and (i - W) % cfg.decision_step == 0:
                pred = self.predict(
                    closes[i - W : i],
                    volumes[i - W : i],
                    highs[i - W : i],
                    lows[i - W : i],
                )
                if pred.get("signal", False):
                    qty = (cash * 0.95) / (current_price * (1 + fee_rate))
                    if qty > 0:
                        cost = qty * current_price * (1 + fee_rate)
                        cash -= cost
                        position_qty = qty
                        entry_price = current_price
                        entry_idx = i

            # Equity tracking
            current_equity = cash + position_qty * current_price
            if current_equity > peak_equity:
                peak_equity = current_equity
            dd = (current_equity - peak_equity) / peak_equity * 100
            if dd < max_dd:
                max_dd = dd
            equity_curve.append((timestamps[i], current_equity))

            i += 1

        # Force liquidate at end
        if position_qty > 0:
            revenue = position_qty * closes[-1] * (1 - fee_rate)
            cash += revenue
            trades.append({
                "entry_time": timestamps[entry_idx],
                "exit_time": timestamps[-1],
                "entry_price": entry_price,
                "exit_price": closes[-1],
                "pnl_pct": (closes[-1] / entry_price - 1) - 2 * fee_rate,
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

        return {
            "initial_capital": initial_capital,
            "final_equity": final_equity,
            "return_pct": return_pct,
            "trades_count": len(trades),
            "win_rate": win_rate,
            "avg_pnl_pct": avg_pnl * 100,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "trades": trades,
        }

    def _empty_result(self):
        return {
            "initial_capital": 0,
            "final_equity": 0,
            "return_pct": 0,
            "trades_count": 0,
            "win_rate": 0,
            "avg_pnl_pct": 0,
            "sharpe": 0,
            "max_drawdown": 0,
            "trades": [],
        }
