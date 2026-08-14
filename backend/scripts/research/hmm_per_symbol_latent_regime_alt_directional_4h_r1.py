"""R-1 PoC — paradigm hmm_per_symbol_latent_regime_alt_directional_4h.

Hypothesis
----------
Per-symbol 3-state Gaussian HMM fit on alt 1h log-returns over rolling 90d
window → posterior probability of each latent state. When one state's posterior
> threshold (default 0.8 strong regime identification), forward 4h directional
bet conditional on state-identity (sorted by emission std):
  - HIGH-vol state → forward SHORT (volatility mean-reversion / forced-deleveraging cycle)
  - LOW-vol state  → forward LONG  (calm continuation drift)
  - NEUTRAL state  → no trade (sanity baseline)

4-quadrant Symmetric Negative Test (Lesson #19, joint-regime trigger):
  - A_focus  HIGH-vol × SHORT (mean-revert hypothesis)
  - A_mirror HIGH-vol × LONG  (direction inversion test)
  - B_focus  LOW-vol  × LONG  (continuation hypothesis)
  - B_mirror LOW-vol  × SHORT (orthogonal class test)

Pass criteria (Three-gate strict per _perm_utils):
  signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_two_sided <= 0.10

Concentration Gate (Lesson #16):
  quarter_pos_t_ratio >= 0.5 AND symbol_ci_pos_ratio >= 0.30 AND n_symbols_ci_pos >= 3

Lesson #41 DIFFUSE_POSITIVE_CONCENTRATION_FAIL check + life-changing 4-dim.
Lesson #42 mechanism CLASS asymmetry test (mathematical mirror vs orthogonal trigger).
Lesson #32 universe baseline coherent (no-event baseline subtraction).

Sweep:
  posterior thresholds ∈ {0.6, 0.7, 0.8, 0.9}
  hold horizons       ∈ {2h, 4h, 8h, 24h}

Primary cell: posterior >= 0.8 × hold = 4h × state-identity-conditional direction.

HMM fit policy
--------------
  - GaussianHMM(n_components=3, covariance_type='diag')
  - Fit on rolling 90d window of 1h log-returns (~2160 obs)
  - Refit cadence: every 168h (weekly) — no look-ahead, week T fit used week T+1 triggers
  - State labeling: post-fit sort by emission std (smallest=LOW, largest=HIGH, middle=NEUTRAL)
  - Posterior: forward_backward (predict_proba) inferred state probability at trigger ts
  - Warm-up: 30d skipped from epoch start (HMM convergence stabilization)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
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

# Suppress hmmlearn convergence warnings (we track convergence per-fit explicitly)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*converge.*")

from hmmlearn.hmm import GaussianHMM  # noqa: E402

PARADIGM = "hmm_per_symbol_latent_regime_alt_directional_4h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1__metrics.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("r1_hmm")

# Canonical Mint joblib cache 14-sym universe
SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]
# Trade on all 14 (no BTC/ETH baseline exclusion — per-sym HMM means each is its own regime)
ALT_SYMS = list(SYMS)

# Parameter grid
POSTERIOR_GRID = [0.6, 0.7, 0.8, 0.9]
HOLD_HRS = [2, 4, 8, 24]

PRIMARY_POSTERIOR = 0.8
PRIMARY_HOLD = 4

# Operational
FEE_RT = 8e-4  # 8 bp round-trip
HMM_WINDOW_D = 90
HMM_WARMUP_D = 30
HMM_REFIT_H = 168  # weekly refit
HMM_N_STATES = 3
HMM_MAX_ITER = 30  # bounded convergence iterations
HMM_RNG_SEED = 42


def resample_to_1h(df_1m: pd.DataFrame) -> pd.Series:
    """Convert 1m close to 1h close (right-labeled / right-closed)."""
    if df_1m.empty:
        return pd.Series(dtype=float)
    return df_1m["close"].resample("1h", label="right", closed="right").last()


def build_returns_panel(syms: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns: (rets_1h, close_1h) wide df indexed by hourly UTC ts."""
    pieces_close = {}
    for s in syms:
        df1m = load_ohlcv_1m_cached(s)
        if df1m.empty:
            log.warning("%s empty cache, dropping", s)
            continue
        h = resample_to_1h(df1m)
        pieces_close[s] = h
    close = pd.concat(pieces_close, axis=1)
    close.columns = list(pieces_close.keys())
    log_close = np.log(close.astype(float))
    rets = log_close.diff()
    return rets, close


def fit_hmm_single_window(returns_arr: np.ndarray, rng_seed: int = HMM_RNG_SEED) -> GaussianHMM | None:
    """Fit a single 3-state Gaussian HMM on a fixed window of returns.
    Returns fitted model or None on failure.
    """
    arr = returns_arr.reshape(-1, 1)
    arr = arr[~np.isnan(arr[:, 0])]
    if len(arr) < 200:
        return None
    try:
        model = GaussianHMM(
            n_components=HMM_N_STATES,
            covariance_type="diag",
            n_iter=HMM_MAX_ITER,
            random_state=rng_seed,
            tol=1e-3,
        )
        model.fit(arr)
        if not model.monitor_.converged:
            # Still usable; we record but don't fail
            pass
        return model
    except Exception as e:
        log.debug("HMM fit failed: %s", e)
        return None


def sort_state_labels_by_std(model: GaussianHMM) -> dict[int, str]:
    """Given a fitted HMM, return mapping {raw_state_idx → label in {LOW, NEUTRAL, HIGH}}
    by sorting raw states by emission std (covar) ascending.
    """
    # For diag cov, model.covars_ is (n_states, 1, 1) or (n_states, 1)
    covars = model.covars_.reshape(-1)
    stds = np.sqrt(covars)
    order = np.argsort(stds)  # ascending: smallest=LOW, largest=HIGH
    labels = ["LOW", "NEUTRAL", "HIGH"]
    mapping = {int(order[i]): labels[i] for i in range(len(order))}
    return mapping


def build_per_symbol_state_series(
    sym: str,
    rets_sym: pd.Series,
) -> tuple[pd.Series, pd.Series, dict] | None:
    """Fit walk-forward HMM per symbol. Returns:
      (state_label_series, max_posterior_series, fit_diagnostics)
    where the series are indexed by hourly UTC ts, aligned to rets_sym.index.

    Walk-forward:
      For each refit time T (every 168h after warmup), fit HMM on returns
      [T-90d : T]. Use that fit's predict_proba for hourly ts in [T : T+168h]
      to label each ts with (state_label, posterior_max).
    """
    rets_clean = rets_sym.dropna()
    if len(rets_clean) < (HMM_WINDOW_D + HMM_WARMUP_D) * 24:
        log.warning("[%s] insufficient data %d < %d", sym, len(rets_clean), (HMM_WINDOW_D + HMM_WARMUP_D) * 24)
        return None

    ts_index = rets_clean.index
    n_total = len(ts_index)

    # First refit anchor: after (warmup + window) hours
    first_anchor_h = (HMM_WARMUP_D + HMM_WINDOW_D) * 24
    if first_anchor_h >= n_total:
        log.warning("[%s] not enough history for first anchor", sym)
        return None

    state_labels = pd.Series(index=ts_index, dtype=object)
    posterior_max = pd.Series(index=ts_index, dtype=float)

    fit_diag = {
        "n_fits": 0,
        "n_converged": 0,
        "n_failed": 0,
        "state_dist_balanced": 0,  # fits where no state dominates >85% of window
        "state_dist_dominant": 0,  # fits where one state >85%
    }

    refit_step = HMM_REFIT_H
    cur = first_anchor_h
    while cur < n_total:
        # Fit window: [cur - HMM_WINDOW_D*24 : cur]
        fit_window_start = cur - HMM_WINDOW_D * 24
        fit_window_end = cur
        fit_window_arr = rets_clean.iloc[fit_window_start:fit_window_end].values

        model = fit_hmm_single_window(fit_window_arr)
        fit_diag["n_fits"] += 1
        if model is None:
            fit_diag["n_failed"] += 1
            cur += refit_step
            continue
        if model.monitor_.converged:
            fit_diag["n_converged"] += 1

        # Map raw state idx to LOW/NEUTRAL/HIGH
        label_map = sort_state_labels_by_std(model)

        # Check state distribution on fit window
        try:
            fit_seq = model.predict(fit_window_arr.reshape(-1, 1))
            unique, counts = np.unique(fit_seq, return_counts=True)
            max_state_frac = counts.max() / counts.sum()
            if max_state_frac > 0.85:
                fit_diag["state_dist_dominant"] += 1
            else:
                fit_diag["state_dist_balanced"] += 1
        except Exception:
            pass

        # Use this model to label [cur : cur + refit_step]
        apply_start = cur
        apply_end = min(cur + refit_step, n_total)
        apply_arr = rets_clean.iloc[apply_start:apply_end].values.reshape(-1, 1)
        apply_arr_clean = apply_arr[~np.isnan(apply_arr[:, 0])]
        if len(apply_arr_clean) == 0:
            cur += refit_step
            continue

        try:
            posterior = model.predict_proba(apply_arr_clean)  # (n_apply, 3)
            states_seq = posterior.argmax(axis=1)
            posterior_max_arr = posterior.max(axis=1)
            apply_ts = rets_clean.iloc[apply_start:apply_end].dropna().index
            # apply_arr_clean length should match apply_ts length
            if len(apply_ts) == len(states_seq):
                for k, ts in enumerate(apply_ts):
                    state_labels.loc[ts] = label_map[int(states_seq[k])]
                    posterior_max.loc[ts] = float(posterior_max_arr[k])
        except Exception as e:
            log.debug("[%s] predict_proba failed at %d: %s", sym, cur, e)

        cur += refit_step

    return state_labels, posterior_max, fit_diag


def build_forward_returns(close_1h: pd.DataFrame, hold_h: int) -> pd.DataFrame:
    """Forward `hold_h` log-return = log(p[t+hold] / p[t]) per sym."""
    log_close = np.log(close_1h.astype(float))
    fwd = log_close.shift(-hold_h) - log_close
    return fwd


def evaluate_cell(
    close_1h: pd.DataFrame,
    state_series_by_sym: dict[str, pd.Series],
    posterior_max_by_sym: dict[str, pd.Series],
    target_state: str,
    posterior_thr: float,
    hold_h: int,
    direction: int,
) -> dict:
    """Evaluate one cell: triggers when state_series == target_state AND posterior_max >= thr.
    direction = +1 (LONG) or -1 (SHORT). Returns per-cell metrics dict.
    Stride: non-overlap = hold_h hours apart per symbol.
    """
    fwd = build_forward_returns(close_1h, hold_h)

    per_sym_net: dict[str, np.ndarray] = {}
    per_sym_gross: dict[str, np.ndarray] = {}
    per_sym_ts: dict[str, list] = {}
    n_triggers_total = 0

    for sym in close_1h.columns:
        if sym not in state_series_by_sym or sym not in posterior_max_by_sym:
            continue
        states = state_series_by_sym[sym]
        posts = posterior_max_by_sym[sym]
        # Align with fwd
        trig_mask = (states == target_state) & (posts >= posterior_thr)
        trig_mask = trig_mask & fwd[sym].notna()
        # Apply non-overlap: stride hold_h hours
        valid_ts = []
        last_t = None
        for ts in trig_mask.index[trig_mask.values]:
            if last_t is None or (ts - last_t).total_seconds() / 3600 >= hold_h:
                valid_ts.append(ts)
                last_t = ts
        n_triggers_total += len(valid_ts)
        if not valid_ts:
            continue
        valid_idx = pd.DatetimeIndex(valid_ts)
        gross_log = fwd[sym].reindex(valid_idx).values * direction
        gross_simple = np.exp(gross_log) - 1
        net = gross_simple - FEE_RT
        per_sym_gross[sym] = gross_simple
        per_sym_net[sym] = net
        per_sym_ts[sym] = list(valid_idx)

    pool_net = np.concatenate(list(per_sym_net.values())) if per_sym_net else np.array([])
    pool_gross = np.concatenate(list(per_sym_gross.values())) if per_sym_gross else np.array([])
    n_obs = int(len(pool_net))

    if n_obs < 30:
        return {
            "target_state": target_state, "posterior_thr": posterior_thr,
            "hold_h": hold_h, "direction": direction,
            "n_triggers": n_triggers_total, "n_obs": n_obs,
            "skip_reason": "n<30",
        }

    # Candidate pool = all fwd returns × direction across panel (for fee_aware_perm)
    pool_all = []
    for sym in close_1h.columns:
        if sym not in fwd.columns:
            continue
        arr = fwd[sym].dropna().values
        arr_signed = (np.exp(arr * direction) - 1)
        pool_all.append(arr_signed)
    pool_all = np.concatenate(pool_all) if pool_all else np.array([])

    # fee_aware_perm
    perm = fee_aware_perm_test(
        observed_net_returns=pool_net,
        candidate_pool_returns=pool_all,
        fee_per_trade=FEE_RT,
        n_perms=1000,
        rng_seed=42,
    )

    # bootstrap CI
    boot = bootstrap_ci(pool_net, n_boot=2000, block_size=1, rng_seed=42)

    three_gate_pass = bool(
        (not np.isnan(perm.get("signal_t_excess", np.nan)))
        and (perm.get("signal_t_excess", -np.inf) >= 2.0)
        and (boot.get("ci_lower", -np.inf) > 0)
        and (perm.get("perm_p_two_sided", 1.0) <= 0.10)
    )

    # Concentration: per-symbol bootstrap CI
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
            "mean_bp": float(b.get("mean", np.nan) * 1e4),
            "ci_lower_bp": float(b.get("ci_lower", np.nan) * 1e4),
            "ci_pos": ci_pos,
            "mean_pos": mean_pos,
        }
        if ci_pos:
            n_ci_pos += 1
        if mean_pos:
            n_pos_mean += 1

    syms_ci_pos_ratio = n_ci_pos / n_alts_total if n_alts_total else 0.0
    syms_pos_mean_ratio = n_pos_mean / n_alts_total if n_alts_total else 0.0

    # Per-quarter
    flat_records = []
    for sym, net_arr in per_sym_net.items():
        ts_list = per_sym_ts[sym]
        for ts, ret in zip(ts_list, net_arr):
            flat_records.append((ts, sym, float(ret)))
    flat_df = pd.DataFrame(flat_records, columns=["ts", "sym", "net"]) if flat_records else pd.DataFrame(columns=["ts","sym","net"])
    q_stats: dict = {}
    q_pos_t = 0
    q_measurable = 0
    if not flat_df.empty:
        flat_df["quarter"] = pd.to_datetime(flat_df["ts"]).dt.to_period("Q")
        for q, grp in flat_df.groupby("quarter"):
            arr_q = grp["net"].values
            if len(arr_q) < 5:
                q_stats[str(q)] = {"n": int(len(arr_q)), "skip": "n<5"}
                continue
            sd_q = arr_q.std(ddof=1)
            t_q = arr_q.mean() / sd_q * np.sqrt(len(arr_q)) if sd_q > 0 else 0.0
            q_stats[str(q)] = {"n": int(len(arr_q)), "mean_bp": float(arr_q.mean() * 1e4), "t": float(t_q)}
            q_measurable += 1
            if t_q > 0:
                q_pos_t += 1
    q_pos_t_ratio = q_pos_t / q_measurable if q_measurable else 0.0

    concentration_pass = bool(
        (q_pos_t_ratio >= 0.5)
        and (syms_ci_pos_ratio >= 0.30)
        and (n_ci_pos >= 3)
        and (q_measurable >= 4)
    )

    diffuse_pos_candidate = bool(
        three_gate_pass
        and (perm.get("signal_t_excess", 0) >= 4.0)
        and (boot.get("ci_lower", 0) > 0)
        and (syms_ci_pos_ratio < 0.30)
    )

    # Life-changing 4-dim
    data_span_days = (close_1h.index.max() - close_1h.index.min()).days
    yrs = data_span_days / 365.25
    trades_per_yr = n_obs / yrs if yrs > 0 else np.nan
    per_trade_edge = float(np.mean(pool_net))
    capital_util = (trades_per_yr * hold_h / 24) / 365 if not np.isnan(trades_per_yr) else np.nan
    sd_net = pool_net.std(ddof=1)
    if sd_net > 0 and not np.isnan(trades_per_yr):
        ann_sharpe = float(pool_net.mean() / sd_net * np.sqrt(trades_per_yr))
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
    lc4["dim_pass_count"] = sum(int(lc4[k]) for k in (
        "trades_per_yr_pass", "per_trade_edge_pass", "capital_util_pass", "ann_sharpe_pass"))

    max_abs_gross_bp = float(np.max(np.abs(pool_gross)) * 1e4)
    mean_gross_bp = float(np.mean(pool_gross) * 1e4)
    fee_floor_pass = bool(abs(mean_gross_bp) >= 16)

    return {
        "target_state": target_state,
        "posterior_thr": posterior_thr,
        "hold_h": hold_h,
        "direction": direction,
        "n_triggers": int(n_triggers_total),
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


def universe_baseline_payoff(close_1h: pd.DataFrame, hold_h: int, direction: int) -> dict:
    """Lesson #32 — universe baseline (no event filter), all hourly anchors × all alts."""
    fwd = build_forward_returns(close_1h, hold_h)
    pool = []
    for sym in close_1h.columns:
        if sym not in fwd.columns:
            continue
        arr = fwd[sym].dropna().values
        arr_signed = (np.exp(arr * direction) - 1) - FEE_RT
        pool.append(arr_signed)
    pool = np.concatenate(pool) if pool else np.array([])
    if len(pool) < 30:
        return {"n": int(len(pool)), "mean_bp": np.nan, "t": np.nan}
    sd = pool.std(ddof=1)
    t = pool.mean() / sd * np.sqrt(len(pool)) if sd > 0 else 0.0
    return {
        "n": int(len(pool)),
        "mean_bp": float(pool.mean() * 1e4),
        "t": float(t),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Quick mode: primary cell only, no sweep")
    ap.add_argument("--symbols", default=",".join(SYMS), help="Comma-separated symbol list")
    args = ap.parse_args(argv)

    t_start = time.time()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    log.info("loading 1m OHLCV for %d symbols from joblib cache", len(syms))
    rets, close_1h = build_returns_panel(syms)
    log.info("rets shape=%s close shape=%s range=%s..%s",
             rets.shape, close_1h.shape, rets.index.min(), rets.index.max())

    # Per-sym HMM fit
    state_series_by_sym: dict[str, pd.Series] = {}
    posterior_max_by_sym: dict[str, pd.Series] = {}
    fit_diag_by_sym: dict[str, dict] = {}
    n_failed_syms = 0

    for sym in syms:
        if sym not in rets.columns:
            continue
        t0 = time.time()
        result = build_per_symbol_state_series(sym, rets[sym])
        elapsed = time.time() - t0
        if result is None:
            log.warning("[%s] HMM build FAILED, skipping (%.1fs)", sym, elapsed)
            n_failed_syms += 1
            continue
        state_series, posterior_max, fit_diag = result
        state_series_by_sym[sym] = state_series
        posterior_max_by_sym[sym] = posterior_max
        fit_diag_by_sym[sym] = fit_diag
        # State distribution diagnostics
        non_nan_states = state_series.dropna()
        if len(non_nan_states) > 0:
            counts = non_nan_states.value_counts()
            log.info("[%s] HMM done %.1fs n_fits=%d converged=%d failed=%d balanced=%d dominant=%d | state dist LOW=%.1f%% NEU=%.1f%% HIGH=%.1f%%",
                     sym, elapsed,
                     fit_diag["n_fits"], fit_diag["n_converged"], fit_diag["n_failed"],
                     fit_diag["state_dist_balanced"], fit_diag["state_dist_dominant"],
                     counts.get("LOW", 0) / len(non_nan_states) * 100,
                     counts.get("NEUTRAL", 0) / len(non_nan_states) * 100,
                     counts.get("HIGH", 0) / len(non_nan_states) * 100)
        else:
            log.warning("[%s] HMM produced 0 state labels", sym)
            n_failed_syms += 1

    if n_failed_syms > len(syms) / 2:
        log.error("HMM fit FAIL > 50%% syms (%d/%d) — DISPATCH_IMPOSSIBLE", n_failed_syms, len(syms))
        results = {
            "paradigm": PARADIGM,
            "verdict": "DISPATCH_IMPOSSIBLE_HMM_FIT_FAIL",
            "n_failed_syms": n_failed_syms,
            "n_total_syms": len(syms),
            "fit_diag_by_sym": fit_diag_by_sym,
        }
        OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
        return 1

    # Empirical trigger rates per state per sym (Lesson #11 diagnostic)
    trigger_rates = {}
    for sym, states in state_series_by_sym.items():
        posts = posterior_max_by_sym[sym]
        non_nan = states.dropna()
        if len(non_nan) == 0:
            continue
        post_aligned = posts.loc[non_nan.index]
        trigger_rates[sym] = {}
        for state in ("LOW", "NEUTRAL", "HIGH"):
            for thr in POSTERIOR_GRID:
                mask = (non_nan == state) & (post_aligned >= thr)
                rate = mask.sum() / len(non_nan) * 100
                trigger_rates[sym][f"{state}_p{int(thr*100)}"] = round(float(rate), 2)

    results = {
        "paradigm": PARADIGM,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_start)),
        "universe": syms,
        "n_failed_syms": n_failed_syms,
        "data_range_min": str(rets.index.min()),
        "data_range_max": str(rets.index.max()),
        "data_n_hours": int(len(rets)),
        "fee_rt": FEE_RT,
        "hmm_config": {
            "n_states": HMM_N_STATES,
            "window_d": HMM_WINDOW_D,
            "warmup_d": HMM_WARMUP_D,
            "refit_h": HMM_REFIT_H,
            "max_iter": HMM_MAX_ITER,
            "covariance_type": "diag",
        },
        "primary_cell": {"posterior_thr": PRIMARY_POSTERIOR, "hold_h": PRIMARY_HOLD},
        "fit_diag_by_sym": fit_diag_by_sym,
        "trigger_rates_by_sym": trigger_rates,
    }

    # 4-quadrant primary cell (Lesson #19)
    log.info("=== PRIMARY CELL: posterior>=%.1f hold=%dh ===", PRIMARY_POSTERIOR, PRIMARY_HOLD)
    primary_quadrants = {}
    for quadrant_name, target_state, direction in [
        ("A_focus_HIGH_SHORT",  "HIGH", -1),
        ("A_mirror_HIGH_LONG",  "HIGH",  1),
        ("B_focus_LOW_LONG",    "LOW",   1),
        ("B_mirror_LOW_SHORT",  "LOW",  -1),
    ]:
        log.info("  evaluating %s target_state=%s dir=%+d", quadrant_name, target_state, direction)
        cell = evaluate_cell(
            close_1h, state_series_by_sym, posterior_max_by_sym,
            target_state=target_state,
            posterior_thr=PRIMARY_POSTERIOR,
            hold_h=PRIMARY_HOLD,
            direction=direction,
        )
        baseline = universe_baseline_payoff(close_1h, PRIMARY_HOLD, direction)
        cell["universe_baseline_no_event"] = baseline
        cell["lesson32_drift_excess_bp"] = float(cell.get("obs_mean_net_bp", 0) - baseline.get("mean_bp", 0))
        primary_quadrants[quadrant_name] = cell
        log.info("    %s n_obs=%d mean_bp=%.2f sigex=%.2f ci_lower_bp=%.2f perm_p=%.3f three_gate=%s concentration=%s lc4=%d/4",
                 quadrant_name, cell.get("n_obs", 0),
                 cell.get("obs_mean_net_bp", 0), cell.get("signal_t_excess", 0),
                 cell.get("ci_lower_bp", 0), cell.get("perm_p_two_sided", 1),
                 cell.get("three_gate_pass"), cell.get("concentration_pass"),
                 cell.get("lc4", {}).get("dim_pass_count", 0))

    # NEUTRAL state sanity baseline (no trade — diagnostic only)
    neutral_diag = {}
    for hold_h in [PRIMARY_HOLD]:
        for direction in [1, -1]:
            label = f"NEUTRAL_dir{direction:+d}_hold{hold_h}h"
            cell = evaluate_cell(
                close_1h, state_series_by_sym, posterior_max_by_sym,
                target_state="NEUTRAL",
                posterior_thr=PRIMARY_POSTERIOR,
                hold_h=hold_h,
                direction=direction,
            )
            neutral_diag[label] = {
                "n_obs": cell.get("n_obs", 0),
                "mean_bp": cell.get("obs_mean_net_bp", np.nan),
                "sigex": cell.get("signal_t_excess", np.nan),
            }
    results["neutral_state_diagnostic"] = neutral_diag

    results["primary_quadrants"] = primary_quadrants

    # SWEEP (skip if --quick)
    if not args.quick:
        log.info("=== SWEEP: posterior_thr × hold_h ===")
        sweep_records = []
        for thr in POSTERIOR_GRID:
            for hold_h in HOLD_HRS:
                # State-conditional: HIGH→SHORT (focus), LOW→LONG (focus)
                for target_state, direction, name in [
                    ("HIGH", -1, "HIGH_SHORT"),
                    ("LOW",   1, "LOW_LONG"),
                ]:
                    c = evaluate_cell(
                        close_1h, state_series_by_sym, posterior_max_by_sym,
                        target_state=target_state,
                        posterior_thr=thr,
                        hold_h=hold_h,
                        direction=direction,
                    )
                    rec = {
                        "posterior_thr": thr, "hold_h": hold_h,
                        "target_state": target_state, "direction": direction, "name": name,
                        "n_obs": c.get("n_obs", 0),
                        "obs_mean_bp": c.get("obs_mean_net_bp", np.nan),
                        "sigex": c.get("signal_t_excess", np.nan),
                        "ci_lower_bp": c.get("ci_lower_bp", np.nan),
                        "perm_p": c.get("perm_p_two_sided", np.nan),
                        "three_gate": c.get("three_gate_pass", False),
                        "concentration": c.get("concentration_pass", False),
                        "lc4_pass": c.get("lc4", {}).get("dim_pass_count", 0),
                        "syms_ci_pos_ratio": c.get("syms_ci_pos_ratio", 0),
                        "diffuse_candidate": c.get("diffuse_pos_candidate", False),
                    }
                    sweep_records.append(rec)
        results["sweep_records"] = sweep_records
        passing = [r for r in sweep_records if r["three_gate"]]
        results["sweep_n_three_gate_pass"] = len(passing)
        results["sweep_passing_cells"] = passing

    # Verdict tree
    pq = primary_quadrants
    a_focus = pq.get("A_focus_HIGH_SHORT", {})
    b_focus = pq.get("B_focus_LOW_LONG", {})
    a_mirror = pq.get("A_mirror_HIGH_LONG", {})
    b_mirror = pq.get("B_mirror_LOW_SHORT", {})

    n_passing_focus = sum(int(c.get("three_gate_pass", False)) for c in [a_focus, b_focus])
    n_passing_mirror = sum(int(c.get("three_gate_pass", False)) for c in [a_mirror, b_mirror])

    all_focus_max_gross = max([abs(c.get("mean_gross_bp", 0)) for c in pq.values()]) if pq else 0
    all_four_fail = (n_passing_focus + n_passing_mirror) == 0
    broad_fee_floor = all_four_fail and all_focus_max_gross < 16

    if broad_fee_floor:
        verdict = "BROAD_FALSIFIED_FEE_FLOOR"
    elif all_four_fail:
        verdict = "BROAD_FALSIFIED"
    elif n_passing_focus > 0:
        passing_focus_cells = [(k, c) for k, c in [("A_focus_HIGH_SHORT", a_focus), ("B_focus_LOW_LONG", b_focus)] if c.get("three_gate_pass")]
        all_passing_have_concentration = all(c.get("concentration_pass") for _, c in passing_focus_cells)
        any_lc4_pass = any(c.get("lc4", {}).get("dim_pass_count", 0) == 4 for _, c in passing_focus_cells)
        any_lc4_per_trade_fail = any(not c.get("lc4", {}).get("per_trade_edge_pass") for _, c in passing_focus_cells)
        any_diffuse_candidate = any(c.get("diffuse_pos_candidate") for _, c in passing_focus_cells)

        if all_passing_have_concentration and any_lc4_pass:
            if n_passing_focus == 2:
                verdict = "PASS_R1_BIDIRECTIONAL_PROMOTE_R2"
            else:
                verdict = "PASS_R1_NARROW_PROMOTE_R2"
        elif any_diffuse_candidate and any_lc4_per_trade_fail:
            verdict = "DIFFUSE_POSITIVE_NARROW_SCOPE_LIFE_CHANGING_FAIL"
        elif any_diffuse_candidate:
            verdict = "DIFFUSE_POSITIVE_CONCENTRATION_FAIL"
        elif any_lc4_per_trade_fail and all_passing_have_concentration:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        else:
            verdict = "CONCENTRATED_R1_PASS"
    elif n_passing_mirror > 0 and n_passing_focus == 0:
        verdict = "MIRROR_ONLY_BROAD_FALSIFIED"
    else:
        verdict = "UNDETERMINED"

    # Lesson #32 universe drift artifact check
    drift_check = {
        "a_focus_obs_bp": a_focus.get("obs_mean_net_bp", np.nan),
        "a_focus_baseline_bp": a_focus.get("universe_baseline_no_event", {}).get("mean_bp", np.nan),
        "a_focus_excess_bp": a_focus.get("lesson32_drift_excess_bp", np.nan),
        "b_focus_obs_bp": b_focus.get("obs_mean_net_bp", np.nan),
        "b_focus_baseline_bp": b_focus.get("universe_baseline_no_event", {}).get("mean_bp", np.nan),
        "b_focus_excess_bp": b_focus.get("lesson32_drift_excess_bp", np.nan),
    }
    drift_check["drift_artifact_risk"] = bool(
        (a_focus.get("three_gate_pass") and a_focus.get("obs_mean_net_bp", 0) <= a_focus.get("universe_baseline_no_event", {}).get("mean_bp", 0))
        or (b_focus.get("three_gate_pass") and b_focus.get("obs_mean_net_bp", 0) <= b_focus.get("universe_baseline_no_event", {}).get("mean_bp", 0))
    )
    results["universe_drift_check_lesson32"] = drift_check
    if verdict.startswith("PASS_R1") and drift_check["drift_artifact_risk"]:
        verdict = "BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT"

    # Lesson #42 mechanism CLASS asymmetry diagnostic
    # A focus (HIGH×SHORT) vs B same_sign_orthogonal (LOW×LONG, i.e. B_focus here)
    # If A focus PASS but B focus null while A mirror also null → mechanism is direction-asymmetric
    mech_class_diag = {
        "a_focus_sigex": a_focus.get("signal_t_excess", np.nan),
        "b_focus_sigex": b_focus.get("signal_t_excess", np.nan),
        "asymmetric_mechanism_flag": bool(
            a_focus.get("three_gate_pass", False)
            and (b_focus.get("signal_t_excess", -np.inf) < 1.0)
        ) or bool(
            b_focus.get("three_gate_pass", False)
            and (a_focus.get("signal_t_excess", -np.inf) < 1.0)
        ),
    }
    results["mechanism_class_asymmetry_lesson42"] = mech_class_diag

    results["verdict"] = verdict
    results["elapsed_seconds"] = round(time.time() - t_start, 1)

    log.info("=== VERDICT: %s ===", verdict)
    log.info("A_focus  HIGH×SHORT  sigex=%.2f ci_lower_bp=%.2f three_gate=%s concentration=%s lc4=%d/4",
             a_focus.get("signal_t_excess", np.nan), a_focus.get("ci_lower_bp", np.nan),
             a_focus.get("three_gate_pass"), a_focus.get("concentration_pass"),
             a_focus.get("lc4", {}).get("dim_pass_count", 0))
    log.info("B_focus  LOW×LONG    sigex=%.2f ci_lower_bp=%.2f three_gate=%s concentration=%s lc4=%d/4",
             b_focus.get("signal_t_excess", np.nan), b_focus.get("ci_lower_bp", np.nan),
             b_focus.get("three_gate_pass"), b_focus.get("concentration_pass"),
             b_focus.get("lc4", {}).get("dim_pass_count", 0))
    log.info("A_mirror HIGH×LONG   sigex=%.2f ci_lower_bp=%.2f three_gate=%s",
             a_mirror.get("signal_t_excess", np.nan), a_mirror.get("ci_lower_bp", np.nan),
             a_mirror.get("three_gate_pass"))
    log.info("B_mirror LOW×SHORT   sigex=%.2f ci_lower_bp=%.2f three_gate=%s",
             b_mirror.get("signal_t_excess", np.nan), b_mirror.get("ci_lower_bp", np.nan),
             b_mirror.get("three_gate_pass"))

    OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    log.info("wrote %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
