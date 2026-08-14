"""R-1 PoC — paradigm realized_correlation_regime_universe_alt_directional_4h.

Hypothesis
----------
14-sym Binance perp universe (Mint joblib cache canonical set).
91-pair (C(14,2)) average pairwise Pearson correlation of 1h log-returns
over 30d trailing window. Z-score the mean correlation vs trailing
90d distribution.

Trigger / direction:
  - z > +2  panic synchronization regime → 4h forward LONG (mean-revert)
  - z < -2  decorrelation regime           → 4h forward SHORT (continuation)

Symmetric Negative Test (Lesson #19, joint-regime trigger):
  - A_focus   z>+2 × LONG
  - A_mirror  z>+2 × SHORT  (mathematical mirror sanity)
  - B_focus   z<-2 × SHORT
  - B_mirror  z<-2 × LONG   (orthogonal class test)

Pass criteria (Three-gate strict per _perm_utils):
  signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_two_sided <= 0.10

Concentration Gate (Lesson #16):
  quarter_pos_t_ratio >= 0.5 AND symbol_ci_pos_ratio >= 0.30 AND n_symbols_ci_pos >= 3

Lesson #32 universe-baseline-coherent (level + post-conditioning payoff coherence):
  A focus payoff vs B baseline_no_event payoff per cohort.

Three-gate cells sweep:
  z threshold ∈ {1.5, 2.0, 2.5, 3.0}
  hold ∈ {2h, 4h, 8h, 24h}
  rolling baseline window ∈ {14d, 30d, 60d}  (z-distribution window kept at 90d for default,
                                              correlation window varied for sensitivity)

Primary cell: z=2.0 × hold=4h × baseline=30d.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

PARADIGM = "realized_correlation_regime_universe_alt_directional_4h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1__metrics.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("r1")

# Canonical Mint joblib cache 14-sym universe
SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

# Alt symbols (universe excl BTC + ETH for forward-return measurement = 12)
ALT_SYMS = [s for s in SYMS if s not in ("BTCUSDT", "ETHUSDT")]

# Parameter grid
Z_GRID = [1.5, 2.0, 2.5, 3.0]
HOLD_HRS = [2, 4, 8, 24]
CORR_WINDOWS_D = [14, 30, 60]  # rolling correlation window in days
Z_WINDOW_D = 90  # z-distribution baseline window (fixed)

PRIMARY_Z = 2.0
PRIMARY_HOLD = 4
PRIMARY_CORR_D = 30

# Operational
HOURLY_STRIDE_MIN = 60  # 1h frame
FEE_RT = 8e-4  # 8 bp round-trip
ENTRY_STRIDE_BARS = 4  # to avoid hold-window overlap when stacking entries (4h hold ⇒ stride 4h)


def resample_to_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Convert 1m OHLCV to 1h close prices."""
    if df_1m.empty:
        return pd.DataFrame()
    close_1h = df_1m["close"].resample("1h", label="right", closed="right").last()
    return close_1h.to_frame(name="close")


def build_returns_panel(syms: list[str]) -> pd.DataFrame:
    """Returns wide df: index=hourly UTC ts, columns=SYM, values=1h log-return."""
    pieces = {}
    for s in syms:
        df1m = load_ohlcv_1m_cached(s)
        if df1m.empty:
            log.warning("%s empty cache, dropping", s)
            continue
        h = resample_to_1h(df1m)
        pieces[s] = h["close"]
    wide = pd.concat(pieces, axis=1)
    wide.columns = list(pieces.keys())
    log_close = np.log(wide.astype(float))
    rets = log_close.diff()
    return rets


def universe_mean_corr_rolling(rets: pd.DataFrame, window_bars: int) -> pd.Series:
    """At each hourly t, compute mean pairwise Pearson corr of returns over
    trailing `window_bars` hours across all syms in `rets.columns`.

    Implementation: at each window, compute corr matrix (14x14), take upper-triangle mean.
    For 21k hours × 14 syms: ~21k corr matrices. Use numpy stride trick or pandas rolling apply.
    Faster: compute rolling normalized return Z, then mean correlation = (||sum||^2 - n) / (n*(n-1)).
    """
    # Method: for each window, mean_pairwise_corr = ( (sum_corr_ij over upper tri) ) / n_pairs
    # Equivalent: corr matrix C, mean_pairwise = (sum(C) - trace(C)) / (n*(n-1)) = (sum(C) - n) / (n*(n-1))
    # Using normalized series Z = (X - mu)/sigma per column (in window):
    #   C_ij = E[Z_i Z_j] = sum_t Z_i,t * Z_j,t / N
    #   sum_ij C_ij = sum_t (sum_i Z_i,t)^2 / N
    # So mean_pairwise = ((sum_t (sum_i Z_i,t)^2 / N) - n) / (n*(n-1))
    # This avoids O(n^2) per window.

    rets_clean = rets.dropna(how="any")  # require all syms present
    n_syms = rets_clean.shape[1]
    if rets_clean.empty or n_syms < 2:
        return pd.Series(dtype=float)

    # Rolling mean and var per column
    rmean = rets_clean.rolling(window=window_bars, min_periods=window_bars).mean()
    rstd = rets_clean.rolling(window=window_bars, min_periods=window_bars).std(ddof=0)
    # At each t, normalized z_i,t = (r_i,t - rmean_i_t) / rstd_i_t -- but we need it across the window.
    # Trick: use rolling sum of (sum_i z_i,t)^2 across the window
    # However z requires window-stats which themselves vary per anchor t (look-ahead).
    # Correct: at anchor t, normalize using statistics of window ending at t. Each column gets
    # window-specific (μ_i, σ_i). Then for each τ in window, compute Σ_i z_i,τ.
    # We avoid recomputing Σ for each window by using algebraic identity:
    #   sum_τ (sum_i z_i,τ)^2 = sum_τ sum_i z_i,τ^2 + 2*sum_τ sum_{i<j} z_i,τ z_j,τ
    #                         = N*n  +  2 * sum_{i<j} sum_τ z_i,τ z_j,τ      (E[z^2]=1)
    #                         = N*n  +  2 * sum_{i<j} N * corr_ij
    # So mean_pairwise_corr = (1/(n_pairs)) * sum_{i<j} corr_ij = (sum_τ (sum_i z_i,τ)^2 / N - n) / (n*(n-1))
    # = ((sum_τ S_τ^2)/N - n) / (n*(n-1))  where S_τ = sum_i z_i,τ
    # But z_i,τ depends on the window endpoint. We must compute per-anchor.
    #
    # Practical: vectorize. For each anchor t in valid range, slice last `window_bars` rows,
    # compute per-column (μ, σ), normalize, compute S_τ, sum S_τ^2 / N - n, divide by n*(n-1).
    # 21k anchors × O(n*window) per = 21k × 14*720 ≈ 2.1e8 ops. ~30-60s.
    # Acceptable. Implement vectorized via numpy.

    arr = rets_clean.values  # shape (T, n)
    T = arr.shape[0]
    n = arr.shape[1]
    n_pairs = n * (n - 1) // 2

    out = np.full(T, np.nan, dtype=float)
    # rolling stats already computed
    mu = rmean.values  # (T, n)
    sd = rstd.values   # (T, n)

    # Precompute cumulative arrays for fast window operations
    # We need sum_{τ=t-window+1..t} (sum_i z_i,τ)^2 where z_i,τ = (r_i,τ - μ_i_at_t) / σ_i_at_t
    # That depends on (μ_i, σ_i) which are window-specific. Decompose:
    # z_i,τ = (r_i,τ - μ_i)/σ_i
    # S_τ = sum_i z_i,τ = sum_i r_i,τ/σ_i - sum_i μ_i/σ_i
    # S_τ^2 = (Σ a_i r_i,τ)^2 - 2(Σ a_i r_i,τ)(Σ a_i μ_i) + (Σ a_i μ_i)^2   where a_i = 1/σ_i
    # = (Σ_i a_i r_i,τ)^2 - 2(Σ_i a_i r_i,τ)*K + K^2 where K = Σ a_i μ_i
    # Then sum over window of S_τ^2:
    #   T1 = Σ_τ (Σ_i a_i r_i,τ)^2
    #   T2 = K * Σ_τ (Σ_i a_i r_i,τ) = K * Σ_τ Σ_i a_i r_i,τ = K * Σ_i a_i Σ_τ r_i,τ = K * Σ_i a_i μ_i * window = K * K * window = K^2 * window
    #   T3 = K^2 * window
    # So sum_τ S_τ^2 = T1 - 2*K^2*window + K^2*window = T1 - K^2 * window
    # And T1 = Σ_τ (a^T r_τ)^2 = a^T (Σ_τ r_τ r_τ^T) a
    # Σ_τ r_τ r_τ^T is the window covariance × N + window_mean outer product × N. So...
    # T1 = a^T (window_cov_matrix * N + N * μ μ^T) a
    #   = N * (a^T C a + (a^T μ)^2)
    #   = N * (a^T C a + K^2)
    # where C is window covariance matrix (biased N denom).
    # And K = a^T μ.
    # So sum_τ S_τ^2 = N*(a^T C a + K^2) - K^2 * N = N * a^T C a
    # Therefore:
    #   mean_pairwise_corr = ((sum_τ S_τ^2)/N - n) / (n*(n-1))
    #                     = (a^T C a - n) / (n*(n-1))
    # where a = 1/σ and C = sample covariance (biased, denom N) of r over window.
    # But C / (σ σ^T) = R (correlation matrix). So a^T C a / 1 = sum_{i,j} C_ij / (σ_i σ_j) = sum_{i,j} R_ij = sum(R).
    # → a^T C a = sum(R). Of course — diagonal entries sum to n. So
    #   mean_pairwise_corr = (sum(R) - n) / (n*(n-1)) = (2 * sum_{i<j} R_ij + n - n) / (n*(n-1)) = 2 * sum_upper(R) / (n*(n-1))
    # Which is just mean of upper triangle. As expected.
    # So we DO need to compute rolling correlation matrix R per anchor. Use pandas rolling cov directly.

    # Use pandas rolling for window cov, then convert to correlation.
    # rolling.cov returns shape (T*n, n) multiindex — slow per-window but vectorized.
    # Better: compute via custom loop using numpy convolutions of cross-products.

    # Strategy: precompute cumulative sums of cross-products (sum_t r_i,t * r_j,t) per pair.
    # Then for each window, sum_xy[t] - sum_xy[t-window] = sum over window.
    # Similarly mean_x, mean_y from rolling.mean().
    # cov_xy = (sum_xy/window) - mean_x*mean_y
    # corr_xy = cov_xy / (sd_x * sd_y)

    pair_idx = list(combinations(range(n), 2))

    # cross-product cumsum per pair: shape (T, n_pairs)
    # Memory: 21k × 91 × 8B ≈ 15 MB — fine
    xprod = np.empty((T, n_pairs), dtype=float)
    for p_k, (i, j) in enumerate(pair_idx):
        xprod[:, p_k] = arr[:, i] * arr[:, j]

    xprod_df = pd.DataFrame(xprod, index=rets_clean.index)
    rolling_mean_xprod = xprod_df.rolling(window=window_bars, min_periods=window_bars).mean().values  # (T, n_pairs)

    # Per-pair rolling cov = E[XY] - E[X]E[Y]
    cov_arr = np.empty((T, n_pairs), dtype=float)
    for p_k, (i, j) in enumerate(pair_idx):
        cov_arr[:, p_k] = rolling_mean_xprod[:, p_k] - mu[:, i] * mu[:, j]

    # Per-pair rolling corr = cov / (sd_i * sd_j)
    corr_arr = np.empty((T, n_pairs), dtype=float)
    for p_k, (i, j) in enumerate(pair_idx):
        denom = sd[:, i] * sd[:, j]
        with np.errstate(divide="ignore", invalid="ignore"):
            corr_arr[:, p_k] = np.where(denom > 0, cov_arr[:, p_k] / denom, np.nan)

    # Mean across pairs at each t
    mean_corr = np.nanmean(corr_arr, axis=1)
    out = pd.Series(mean_corr, index=rets_clean.index, name=f"mean_corr_{window_bars}h")
    return out


def zscore_rolling(series: pd.Series, window_bars: int) -> pd.Series:
    mu = series.rolling(window=window_bars, min_periods=window_bars).mean()
    sd = series.rolling(window=window_bars, min_periods=window_bars).std(ddof=1)
    z = (series - mu) / sd
    return z.replace([np.inf, -np.inf], np.nan)


def build_forward_returns_alt(close_1h: pd.DataFrame, hold_h: int) -> pd.DataFrame:
    """For alt syms, fwd `hold_h` log-return = log(p[t+hold] / p[t]).
    Returns wide df indexed by hourly t, columns=ALT_SYMS."""
    log_close = np.log(close_1h.astype(float))
    fwd = log_close.shift(-hold_h) - log_close
    return fwd


def evaluate_cell(
    rets: pd.DataFrame,
    close_1h_alt: pd.DataFrame,
    corr_z: pd.Series,
    z_thr: float,
    hold_h: int,
    direction: int,
    polarity: str,
) -> dict:
    """Evaluate one cell: polarity ('high' for z>+thr, 'low' for z<-thr),
    direction 1=LONG / -1=SHORT, hold horizon.
    Returns dict with all metrics for the cell.
    """
    fwd = build_forward_returns_alt(close_1h_alt, hold_h)  # (T, n_alts)

    # Trigger mask per anchor t
    if polarity == "high":
        trig_mask = corr_z >= z_thr
    elif polarity == "low":
        trig_mask = corr_z <= -z_thr
    else:
        raise ValueError(polarity)

    # Trade events: for each alt, at each trigger t, fwd[sym].iloc[t]
    # Stride entries to ENTRY_STRIDE_BARS (= hold_h to avoid overlap)
    trig_mask = trig_mask.dropna()

    # Apply non-overlap: keep only triggers spaced >= hold_h apart
    valid_idx = []
    last_t = None
    for ts, flag in trig_mask.items():
        if not flag:
            continue
        if last_t is None or (ts - last_t).total_seconds() / 3600 >= hold_h:
            valid_idx.append(ts)
            last_t = ts
    trig_ts = pd.DatetimeIndex(valid_idx)
    n_triggers = len(trig_ts)

    # Per-sym net returns at triggers
    per_sym_net: dict[str, np.ndarray] = {}
    per_sym_gross: dict[str, np.ndarray] = {}
    for sym in close_1h_alt.columns:
        if sym not in fwd.columns:
            continue
        # gross log-return at trigger ts (signed by direction)
        candidate_gross = (fwd[sym].reindex(trig_ts) * direction).dropna().values
        if len(candidate_gross) == 0:
            continue
        # convert log to simple
        candidate_simple = np.exp(candidate_gross) - 1
        net = candidate_simple - FEE_RT
        per_sym_gross[sym] = candidate_simple
        per_sym_net[sym] = net

    # Pool observed net
    pool_net = np.concatenate(list(per_sym_net.values())) if per_sym_net else np.array([])
    pool_gross = np.concatenate(list(per_sym_gross.values())) if per_sym_gross else np.array([])

    n_obs = int(len(pool_net))
    if n_obs < 30:
        return {
            "polarity": polarity, "direction": direction, "z_thr": z_thr, "hold_h": hold_h,
            "n_triggers": n_triggers, "n_obs": n_obs, "skip_reason": "n<30",
        }

    # Candidate pool = all fwd returns for all alts at all non-trigger anchors (signed by direction)
    # Use a random sample-equivalent pool of ALL fwd returns across panel (for fee_aware_perm)
    pool_all = []
    for sym in close_1h_alt.columns:
        if sym not in fwd.columns:
            continue
        all_fwd_log = fwd[sym].dropna().values
        all_fwd_simple = (np.exp(all_fwd_log) - 1) * direction
        pool_all.append(all_fwd_simple)
    pool_all = np.concatenate(pool_all) if pool_all else np.array([])

    # fee_aware_perm_test
    perm = fee_aware_perm_test(
        observed_net_returns=pool_net,
        candidate_pool_returns=pool_all,
        fee_per_trade=FEE_RT,
        n_perms=1000,
        rng_seed=42,
    )

    # bootstrap_ci
    boot = bootstrap_ci(pool_net, n_boot=2000, block_size=1, rng_seed=42)

    # Three-gate
    three_gate_pass = bool(
        (not np.isnan(perm.get("signal_t_excess", np.nan)))
        and (perm.get("signal_t_excess", -np.inf) >= 2.0)
        and (boot.get("ci_lower", -np.inf) > 0)
        and (perm.get("perm_p_two_sided", 1.0) <= 0.10)
    )

    # Concentration: per-symbol bootstrap CI (n_syms_ci_pos / total_alts)
    per_sym_ci: dict[str, dict] = {}
    n_alts_total = len(per_sym_net)
    n_ci_pos = 0
    n_pos_mean = 0
    for sym, net_arr in per_sym_net.items():
        if len(net_arr) < 10:
            per_sym_ci[sym] = {"n": int(len(net_arr)), "skip": "n<10"}
            continue
        b = bootstrap_ci(net_arr, n_boot=2000, block_size=1, rng_seed=42)
        ci_pos = bool(b.get("ci_lower", -np.inf) > 0)
        mean_pos = bool(b.get("mean", 0) > 0)
        per_sym_ci[sym] = {
            "n": int(len(net_arr)),
            "mean": float(b.get("mean", np.nan)),
            "ci_lower": float(b.get("ci_lower", np.nan)),
            "ci_pos": ci_pos,
            "mean_pos": mean_pos,
        }
        if ci_pos:
            n_ci_pos += 1
        if mean_pos:
            n_pos_mean += 1

    syms_ci_pos_ratio = n_ci_pos / n_alts_total if n_alts_total else 0.0
    syms_pos_mean_ratio = n_pos_mean / n_alts_total if n_alts_total else 0.0

    # Per-quarter t-stat
    # Build a flat df of (timestamp, net_return) for pool
    flat_records = []
    for sym, net_arr in per_sym_net.items():
        # We don't have the per-trade ts in arr; reconstruct by realigning trig_ts × sym
        valid_fwd = fwd[sym].reindex(trig_ts)
        valid_fwd_clean = valid_fwd.dropna()
        valid_ts = valid_fwd_clean.index
        valid_simple = (np.exp(valid_fwd_clean.values * direction) - 1) - FEE_RT
        for ts, ret in zip(valid_ts, valid_simple):
            flat_records.append((ts, sym, float(ret)))
    flat_df = pd.DataFrame(flat_records, columns=["ts", "sym", "net"]) if flat_records else pd.DataFrame(columns=["ts","sym","net"])
    if not flat_df.empty:
        flat_df["quarter"] = pd.to_datetime(flat_df["ts"]).dt.to_period("Q")
        per_q = flat_df.groupby("quarter")["net"]
        q_stats = {}
        q_pos_t = 0
        q_measurable = 0
        for q, grp in per_q:
            arr_q = grp.values
            if len(arr_q) < 5:
                q_stats[str(q)] = {"n": int(len(arr_q)), "skip": "n<5"}
                continue
            t_q = arr_q.mean() / arr_q.std(ddof=1) * np.sqrt(len(arr_q)) if arr_q.std(ddof=1) > 0 else 0.0
            q_stats[str(q)] = {"n": int(len(arr_q)), "mean": float(arr_q.mean()), "t": float(t_q)}
            q_measurable += 1
            if t_q > 0:
                q_pos_t += 1
        q_pos_t_ratio = q_pos_t / q_measurable if q_measurable else 0.0
    else:
        q_stats = {}
        q_pos_t_ratio = 0.0
        q_measurable = 0

    # Lesson #16 Concentration Gate
    concentration_pass = bool(
        (q_pos_t_ratio >= 0.5)
        and (syms_ci_pos_ratio >= 0.30)
        and (n_ci_pos >= 3)
        and (q_measurable >= 4)  # Lesson #26 amendment
    )

    # Lesson #41 DIFFUSE_POSITIVE candidate
    diffuse_pos_candidate = bool(
        three_gate_pass
        and (perm.get("signal_t_excess", 0) >= 4.0)
        and (boot.get("ci_lower", 0) > 0)
        and (syms_ci_pos_ratio < 0.30)
        and (np.mean([per_sym_ci[s].get("n", 0) for s in per_sym_ci]) < 100)
    )

    # Life-changing 4-dim measurement
    # trades/yr = n_obs / yrs_in_data
    yrs = (close_1h_alt.index.max() - close_1h_alt.index.min()).days / 365.25
    trades_per_yr = n_obs / yrs if yrs > 0 else np.nan
    per_trade_edge = float(np.mean(pool_net))
    # capital util ≈ (trades/yr * hold_h/24) / 365  -- fraction of capital deployed
    # If hold=4h and 100 trades/yr, util = 100*4/24/365 = 4.5% --- this assumes single position.
    # With multiple syms, util multiplies by avg concurrent positions
    capital_util = (trades_per_yr * hold_h / 24) / 365 if not np.isnan(trades_per_yr) else np.nan
    # annualized sharpe ≈ obs_t * sqrt(trades_per_yr / n_obs) — but cleaner:
    # ann_sharpe = mean(net)/std(net) * sqrt(trades_per_yr)
    if pool_net.std(ddof=1) > 0:
        ann_sharpe = float(pool_net.mean() / pool_net.std(ddof=1) * np.sqrt(trades_per_yr))
    else:
        ann_sharpe = np.nan

    lc4 = {
        "trades_per_yr": float(trades_per_yr),
        "trades_per_yr_pass": bool(trades_per_yr >= 12),
        "per_trade_edge": per_trade_edge,
        "per_trade_edge_pass": bool(per_trade_edge >= 0.02),
        "capital_util": float(capital_util),
        "capital_util_pass": bool(capital_util >= 0.30),
        "ann_sharpe": ann_sharpe,
        "ann_sharpe_pass": bool(ann_sharpe >= 1.5),
    }
    lc4["dim_pass_count"] = sum(int(lc4[k]) for k in ("trades_per_yr_pass", "per_trade_edge_pass", "capital_util_pass", "ann_sharpe_pass"))

    # Fee floor 16bp gross prescreen
    max_abs_gross_bp = float(np.max(np.abs(pool_gross)) * 1e4)
    mean_gross_bp = float(np.mean(pool_gross) * 1e4)
    fee_floor_pass = bool(abs(mean_gross_bp) >= 16)

    return {
        "polarity": polarity,
        "direction": direction,
        "z_thr": z_thr,
        "hold_h": hold_h,
        "n_triggers": int(n_triggers),
        "n_obs": n_obs,
        "n_alts": n_alts_total,
        "obs_mean_net": float(perm.get("obs_mean", np.nan)),
        "obs_mean_net_bp": float(perm.get("obs_mean", 0) * 1e4),
        "obs_t": float(perm.get("obs_t", np.nan)),
        "null_mean_t": float(perm.get("null_mean_t", np.nan)),
        "signal_t_excess": float(perm.get("signal_t_excess", np.nan)),
        "perm_p_two_sided": float(perm.get("perm_p_two_sided", np.nan)),
        "ci_mean": float(boot.get("mean", np.nan)),
        "ci_lower": float(boot.get("ci_lower", np.nan)),
        "ci_upper": float(boot.get("ci_upper", np.nan)),
        "prob_positive": float(boot.get("prob_positive", np.nan)),
        "ci_lower_bp": float(boot.get("ci_lower", 0) * 1e4),
        "ci_upper_bp": float(boot.get("ci_upper", 0) * 1e4),
        "three_gate_pass": three_gate_pass,
        "n_syms_ci_pos": n_ci_pos,
        "n_syms_pos_mean": n_pos_mean,
        "syms_ci_pos_ratio": syms_ci_pos_ratio,
        "syms_pos_mean_ratio": syms_pos_mean_ratio,
        "per_sym_ci": per_sym_ci,
        "q_pos_t_ratio": q_pos_t_ratio,
        "q_measurable": q_measurable,
        "per_q_stats": q_stats,
        "concentration_pass": concentration_pass,
        "diffuse_pos_candidate": diffuse_pos_candidate,
        "max_abs_gross_bp": max_abs_gross_bp,
        "mean_gross_bp": mean_gross_bp,
        "fee_floor_pass": fee_floor_pass,
        "lc4": lc4,
    }


def universe_baseline_payoff(close_1h_alt: pd.DataFrame, hold_h: int, direction: int) -> dict:
    """Lesson #32/33 — universe baseline payoff (no event filter).
    Returns mean fwd net return across ALL hourly anchors × ALL alts, signed by direction.
    """
    fwd = build_forward_returns_alt(close_1h_alt, hold_h)
    pool = []
    for sym in close_1h_alt.columns:
        if sym not in fwd.columns:
            continue
        arr = fwd[sym].dropna().values
        arr_signed = (np.exp(arr * direction) - 1) - FEE_RT
        pool.append(arr_signed)
    pool = np.concatenate(pool) if pool else np.array([])
    if len(pool) < 30:
        return {"n": int(len(pool)), "mean_bp": np.nan, "t": np.nan}
    t = pool.mean() / pool.std(ddof=1) * np.sqrt(len(pool)) if pool.std(ddof=1) > 0 else 0.0
    return {
        "n": int(len(pool)),
        "mean_bp": float(pool.mean() * 1e4),
        "t": float(t),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Quick mode: skip full sweep, primary cell only")
    args = ap.parse_args(argv)

    t_start = time.time()
    log.info("loading 14-sym 1m OHLCV from joblib cache")
    rets = build_returns_panel(SYMS)
    log.info("rets panel shape=%s (T x n_syms), range=%s..%s",
             rets.shape, rets.index.min(), rets.index.max())

    # Resample to 1h close for fwd returns (alts only — exclude BTC/ETH)
    alts_1m_close = {}
    for s in ALT_SYMS:
        df1m = load_ohlcv_1m_cached(s)
        if df1m.empty:
            continue
        h = df1m["close"].resample("1h", label="right", closed="right").last()
        alts_1m_close[s] = h
    close_1h_alt = pd.concat(alts_1m_close, axis=1)
    close_1h_alt.columns = list(alts_1m_close.keys())
    log.info("close_1h_alt shape=%s", close_1h_alt.shape)

    results = {
        "paradigm": PARADIGM,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_start)),
        "universe": SYMS,
        "alts": list(close_1h_alt.columns),
        "data_range_min": str(rets.index.min()),
        "data_range_max": str(rets.index.max()),
        "data_n_hours": int(len(rets)),
        "fee_rt": FEE_RT,
        "primary_cell": {"z_thr": PRIMARY_Z, "hold_h": PRIMARY_HOLD, "corr_window_d": PRIMARY_CORR_D},
        "cells": [],
        "sweep": {},
    }

    # Compute corr-z series for each corr-window
    corr_z_by_window: dict[int, pd.Series] = {}
    for cw_d in CORR_WINDOWS_D:
        cw_bars = cw_d * 24
        log.info("computing rolling pairwise mean corr window=%dd (%d bars)", cw_d, cw_bars)
        t1 = time.time()
        mean_corr = universe_mean_corr_rolling(rets, cw_bars)
        log.info("  mean_corr ready %d non-nan in %.1fs", mean_corr.notna().sum(), time.time() - t1)
        z_bars = Z_WINDOW_D * 24
        z = zscore_rolling(mean_corr, z_bars)
        corr_z_by_window[cw_d] = z
        log.info("  z-score ready (window=%dd) %d non-nan", Z_WINDOW_D, z.notna().sum())
        # Print z distribution
        z_clean = z.dropna()
        if len(z_clean) > 0:
            log.info("  z dist: min=%.2f p1=%.2f p10=%.2f p50=%.2f p90=%.2f p99=%.2f max=%.2f",
                     z_clean.min(), z_clean.quantile(0.01), z_clean.quantile(0.10),
                     z_clean.median(), z_clean.quantile(0.90), z_clean.quantile(0.99), z_clean.max())

    # 4-quadrant primary cell
    primary_corr_z = corr_z_by_window[PRIMARY_CORR_D]
    primary_results = {}

    log.info("=== PRIMARY CELL: z_thr=%.1f hold=%dh corr_window=%dd ===", PRIMARY_Z, PRIMARY_HOLD, PRIMARY_CORR_D)
    for quadrant, polarity, direction in [
        ("A_focus_high_LONG",   "high",  1),
        ("A_mirror_high_SHORT", "high", -1),
        ("B_focus_low_SHORT",   "low",  -1),
        ("B_mirror_low_LONG",   "low",   1),
    ]:
        log.info("  evaluating %s polarity=%s direction=%+d", quadrant, polarity, direction)
        cell = evaluate_cell(
            rets, close_1h_alt, primary_corr_z,
            z_thr=PRIMARY_Z, hold_h=PRIMARY_HOLD,
            direction=direction, polarity=polarity,
        )
        # Lesson #32 universe baseline coherent
        baseline = universe_baseline_payoff(close_1h_alt, PRIMARY_HOLD, direction)
        cell["universe_baseline_no_event"] = baseline
        cell["lesson32_drift_excess_bp"] = float(cell.get("obs_mean_net_bp", 0) - baseline.get("mean_bp", 0))
        primary_results[quadrant] = cell
        log.info("    %s n_obs=%d obs_mean_bp=%.2f sigex=%.2f ci_lower_bp=%.2f perm_p=%.3f three_gate=%s concentration=%s lc4=%d/4",
                 quadrant, cell.get("n_obs", 0),
                 cell.get("obs_mean_net_bp", 0), cell.get("signal_t_excess", 0),
                 cell.get("ci_lower_bp", 0), cell.get("perm_p_two_sided", 1),
                 cell.get("three_gate_pass"), cell.get("concentration_pass"),
                 cell.get("lc4", {}).get("dim_pass_count", 0))

    results["primary_quadrants"] = primary_results

    # SWEEP (skip if --quick)
    if not args.quick:
        log.info("=== SWEEP cells: z × hold × corr_window ===")
        sweep_records = []
        for cw_d in CORR_WINDOWS_D:
            corr_z = corr_z_by_window[cw_d]
            for z_thr in Z_GRID:
                for hold_h in HOLD_HRS:
                    for polarity, direction, name in [
                        ("high", 1, "A_focus"),
                        ("low", -1, "B_focus"),
                    ]:
                        c = evaluate_cell(
                            rets, close_1h_alt, corr_z,
                            z_thr=z_thr, hold_h=hold_h, direction=direction, polarity=polarity,
                        )
                        rec = {
                            "cw_d": cw_d, "z_thr": z_thr, "hold_h": hold_h,
                            "polarity": polarity, "direction": direction, "name": name,
                            "n_obs": c.get("n_obs", 0),
                            "obs_mean_bp": c.get("obs_mean_net_bp", np.nan),
                            "sigex": c.get("signal_t_excess", np.nan),
                            "ci_lower_bp": c.get("ci_lower_bp", np.nan),
                            "perm_p": c.get("perm_p_two_sided", np.nan),
                            "three_gate": c.get("three_gate_pass", False),
                            "concentration": c.get("concentration_pass", False),
                            "lc4_pass": c.get("lc4", {}).get("dim_pass_count", 0),
                        }
                        sweep_records.append(rec)
        results["sweep_records"] = sweep_records
        # Identify best non-primary cells
        passing = [r for r in sweep_records if r["three_gate"]]
        results["sweep_n_three_gate_pass"] = len(passing)
        results["sweep_passing_cells"] = passing

    # Verdict tree
    pq = results.get("primary_quadrants", {})
    a_focus = pq.get("A_focus_high_LONG", {})
    b_focus = pq.get("B_focus_low_SHORT", {})

    n_passing_focus = sum(int(c.get("three_gate_pass", False)) for c in [a_focus, b_focus])
    n_passing_mirror = sum(int(pq.get(k, {}).get("three_gate_pass", False)) for k in ["A_mirror_high_SHORT", "B_mirror_low_LONG"])

    # Symmetric Negative Test broad falsification
    all_focus_max_gross = max([abs(c.get("mean_gross_bp", 0)) for c in pq.values()]) if pq else 0
    all_four_fail = (n_passing_focus + n_passing_mirror) == 0
    broad_fee_floor = all_four_fail and all_focus_max_gross < 16

    if broad_fee_floor:
        verdict = "BROAD_FALSIFIED_FEE_FLOOR"
    elif all_four_fail:
        verdict = "BROAD_FALSIFIED"
    elif n_passing_focus > 0:
        # check concentration on passing focus cells
        passing_focus_cells = [(k, c) for k, c in [("A_focus_high_LONG", a_focus), ("B_focus_low_SHORT", b_focus)] if c.get("three_gate_pass")]
        all_passing_have_concentration = all(c.get("concentration_pass") for _, c in passing_focus_cells)
        any_lc4_pass = any(c.get("lc4", {}).get("dim_pass_count", 0) == 4 for _, c in passing_focus_cells)
        any_lc4_per_trade_fail = any(not c.get("lc4", {}).get("per_trade_edge_pass") for _, c in passing_focus_cells)
        any_diffuse_candidate = any(c.get("diffuse_pos_candidate") for _, c in passing_focus_cells)

        if all_passing_have_concentration and any_lc4_pass:
            if n_passing_focus == 2:
                verdict = "PASS_R1_BIDIRECTIONAL_PROMOTE_R2"
            else:
                verdict = "PASS_R1_NARROW_PROMOTE_R2"
        elif any_lc4_per_trade_fail and all_passing_have_concentration:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        elif any_diffuse_candidate:
            verdict = "DIFFUSE_POSITIVE_CONCENTRATION_FAIL"
        else:
            verdict = "CONCENTRATED_R1_PASS"
    elif n_passing_mirror > 0 and n_passing_focus == 0:
        verdict = "MIRROR_ONLY_BROAD_FALSIFIED"
    else:
        verdict = "UNDETERMINED"

    # Lesson #32 universe-baseline-coherent check at LEVEL on A_focus
    a_excess = a_focus.get("lesson32_drift_excess_bp", 0)
    b_excess = b_focus.get("lesson32_drift_excess_bp", 0)
    universe_drift_check = {
        "a_focus_obs_bp": a_focus.get("obs_mean_net_bp", np.nan),
        "a_focus_baseline_bp": a_focus.get("universe_baseline_no_event", {}).get("mean_bp", np.nan),
        "a_excess_bp": float(a_excess),
        "b_focus_obs_bp": b_focus.get("obs_mean_net_bp", np.nan),
        "b_focus_baseline_bp": b_focus.get("universe_baseline_no_event", {}).get("mean_bp", np.nan),
        "b_excess_bp": float(b_excess),
        "drift_artifact_risk": bool(
            (a_focus.get("three_gate_pass") and a_focus.get("obs_mean_net_bp", 0) <= a_focus.get("universe_baseline_no_event", {}).get("mean_bp", 0))
            or (b_focus.get("three_gate_pass") and b_focus.get("obs_mean_net_bp", 0) <= b_focus.get("universe_baseline_no_event", {}).get("mean_bp", 0))
        ),
    }
    results["universe_drift_check_lesson32"] = universe_drift_check
    if verdict.startswith("PASS_R1") and universe_drift_check["drift_artifact_risk"]:
        verdict = "BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT"

    results["verdict"] = verdict
    results["elapsed_seconds"] = round(time.time() - t_start, 1)

    log.info("=== VERDICT: %s ===", verdict)
    log.info("primary A_focus(high>+%.1f LONG):  sigex=%.2f ci_lower_bp=%.2f three_gate=%s concentration=%s",
             PRIMARY_Z, a_focus.get("signal_t_excess", np.nan), a_focus.get("ci_lower_bp", np.nan),
             a_focus.get("three_gate_pass"), a_focus.get("concentration_pass"))
    log.info("primary B_focus(low<-%.1f SHORT): sigex=%.2f ci_lower_bp=%.2f three_gate=%s concentration=%s",
             PRIMARY_Z, b_focus.get("signal_t_excess", np.nan), b_focus.get("ci_lower_bp", np.nan),
             b_focus.get("three_gate_pass"), b_focus.get("concentration_pass"))

    # Write metrics
    OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    log.info("wrote %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
