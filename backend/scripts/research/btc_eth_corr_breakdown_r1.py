"""R-1 PoC — BTC↔ETH 5m correlation breakdown event → SOL 240m forward LONG.

Paradigm 74 candidate (Q3 §6.5).

Hypothesis
----------
When the 1-day rolling Pearson correlation between BTC 5m log returns and
ETH 5m log returns drops below its trailing 30-day p10 (i.e. crosses
deeply into a corr-breakdown z-score regime), this signals cross-asset
dislocation. In dislocation regimes, alts overshoot and revert. We test
the hypothesis on SOL with a 240-minute forward LONG hold.

Distinctness vs paradigm 69
---------------------------
- p69: single-asset BTC RV spike, p90 vol regime filter, 5m trigger, 240m hold.
- p74 (this): cross-asset BTC↔ETH corr regime breakdown, NO single-asset
  vol filter, 5m trigger, 240m hold. Mechanism = cross-asset stress
  (orthogonal to single-asset vol stress). NOT a trigger-swap antipattern.

Sub-hypotheses
--------------
- H1 unsigned LONG: at corr breakdown trigger, 240m forward LONG SOL
  has positive net return.
- H5 sign-conditional: split events by (BTC 5m return sign × SOL 5m return
  sign at trigger). Identify which sub-cell (if any) carries the alpha.

Three threshold sweep
---------------------
The trigger metric is a **z-score of corr against trailing-30d corr
distribution**. We test thresholds z ≤ -1.5 / -2.0 / -2.5 (deeper
breakdown = stronger signal expected).

Stat suite (lesson #1, #2 strict 3-gate)
-----------------------------------------
- fee_aware_perm_test: signal_t_excess ≥ 2.0 vs fee-saturated null
- bootstrap_ci: ci_lower > 0 (95% CI excludes zero)
- perm_p_two_sided ≤ 0.10
ALL three required for R-1 PASS.

Fee
---
8 bp round-trip = 0.0008 (Binance Futures USDT-M).

Output
------
backend/runs/research_track/btc_eth_corr_breakdown/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p74_r1")

OUT_DIR = ROOT / "runs" / "research_track" / "btc_eth_corr_breakdown"
OUT_PATH = OUT_DIR / "r1__metrics.json"

# Trigger asset = BTC × ETH corr; alt under test = SOL (paradigm 69 fast-track)
ALT_SYM = "SOLUSDT"

# Bar geometry
BAR_MINUTES = 5
HOLD_MINUTES = 240
HOLD_BARS = HOLD_MINUTES // BAR_MINUTES  # 48 bars

# Corr regime computation
CORR_WINDOW_BARS = 288       # 1 day at 5m
ZSCORE_LOOKBACK_BARS = 288 * 30  # ~30 days of corr observations for z-score baseline
Z_THRESHOLDS = [-1.5, -2.0, -2.5]

# Trigger anti-clustering: require at least HOLD_BARS gap between triggers
# (so events do not overlap in their forward windows — clean trade pool)
TRIGGER_MIN_GAP_BARS = HOLD_BARS

# Fee
FEE_PER_TRADE = 0.0008


def resample_5m(df_1m: pd.DataFrame) -> pd.Series:
    """Take 1m close, return 5m close series."""
    return df_1m["close"].resample(f"{BAR_MINUTES}min").last().dropna()


def compute_5m_returns(close_5m: pd.Series) -> pd.Series:
    return np.log(close_5m / close_5m.shift(1))


def build_corr_zscore_panel(btc_r: pd.Series, eth_r: pd.Series) -> pd.DataFrame:
    """Compute rolling 1d Pearson corr(BTC 5m return, ETH 5m return),
    then z-score against trailing 30d corr distribution.

    Returns DataFrame indexed by 5m timestamp with columns:
      - corr: rolling Pearson correlation
      - corr_zscore: corr standardized vs trailing 30d corr observations
    """
    df = pd.DataFrame({"btc_r": btc_r, "eth_r": eth_r}).dropna()
    corr = df["btc_r"].rolling(CORR_WINDOW_BARS).corr(df["eth_r"])
    # z-score baseline: rolling mean & std of corr itself
    corr_mean = corr.rolling(ZSCORE_LOOKBACK_BARS).mean()
    corr_std = corr.rolling(ZSCORE_LOOKBACK_BARS).std()
    corr_z = (corr - corr_mean) / corr_std
    out = pd.DataFrame({
        "corr": corr,
        "corr_zscore": corr_z,
    }).dropna()
    return out


def find_trigger_indices(corr_z: pd.Series, threshold: float) -> List[int]:
    """Return positional indices where corr_zscore crosses below `threshold`,
    enforcing min-gap to prevent overlapping forward windows.

    A 'cross' = previous bar above threshold, current bar at/below threshold.
    """
    z = corr_z.values
    cross = (z[1:] <= threshold) & (z[:-1] > threshold)
    candidate_pos = np.where(cross)[0] + 1  # +1 because cross indexed from t-1
    if len(candidate_pos) == 0:
        return []
    selected = [int(candidate_pos[0])]
    for p in candidate_pos[1:]:
        if p - selected[-1] >= TRIGGER_MIN_GAP_BARS:
            selected.append(int(p))
    return selected


def compute_forward_returns(close_5m: pd.Series, trigger_positions: List[int]) -> pd.Series:
    """Given alt close series and trigger positional indices,
    compute 240m (48 bar) forward LOG return: log(close[t+48] / close[t]).
    Skip triggers where t+HOLD_BARS exceeds series length.
    """
    out_idx = []
    out_val = []
    n = len(close_5m)
    for p in trigger_positions:
        if p + HOLD_BARS >= n:
            continue
        c0 = close_5m.iloc[p]
        cT = close_5m.iloc[p + HOLD_BARS]
        if c0 <= 0 or cT <= 0:
            continue
        out_idx.append(close_5m.index[p])
        out_val.append(np.log(cT / c0))
    return pd.Series(out_val, index=out_idx, name="fwd240m_long")


def build_candidate_pool(close_5m: pd.Series, n_target: int = 30000) -> np.ndarray:
    """Build the universe of all possible 240m forward LONG returns
    sampled at every BAR_MINUTES step (entry stride = HOLD_BARS to avoid
    massive overlap). This is the fee_aware_perm_test pool.
    """
    n = len(close_5m)
    # Entry every HOLD_BARS bars to keep candidate windows non-overlapping
    starts = np.arange(0, n - HOLD_BARS, HOLD_BARS)
    if len(starts) > n_target:
        rng = np.random.default_rng(42)
        starts = rng.choice(starts, size=n_target, replace=False)
        starts = np.sort(starts)
    c = close_5m.values
    rets = np.log(c[starts + HOLD_BARS] / c[starts])
    rets = rets[np.isfinite(rets)]
    return rets


def evaluate_threshold(
    threshold: float,
    corr_z_panel: pd.DataFrame,
    sol_close_5m: pd.Series,
    btc_r_5m: pd.Series,
    candidate_pool: np.ndarray,
) -> Dict:
    """Run R-1 for one z threshold, return dict of metrics."""
    trigger_pos = find_trigger_indices(corr_z_panel["corr_zscore"], threshold)

    # Map trigger positions in corr_z_panel index back to sol_close_5m timeline
    # (they may be slightly different if NaN dropping caused offsets).
    trigger_ts = corr_z_panel.index[trigger_pos]
    # Convert to positional indices in sol_close_5m
    sol_idx_map = {ts: i for i, ts in enumerate(sol_close_5m.index)}
    sol_trigger_pos = [sol_idx_map[ts] for ts in trigger_ts if ts in sol_idx_map]

    # Forward returns (LONG)
    fwd = compute_forward_returns(sol_close_5m, sol_trigger_pos)
    n_trig = len(fwd)

    if n_trig < 10:
        return {
            "threshold": threshold,
            "n_triggers": int(n_trig),
            "skip_reason": "n_triggers<10",
        }

    # H1 unsigned LONG: net = gross - fee
    gross = fwd.values
    net = gross - FEE_PER_TRADE
    obs_t = float(net.mean() / net.std(ddof=1) * np.sqrt(len(net))) if net.std(ddof=1) > 0 else 0.0
    gross_bp = float(gross.mean() * 10000)
    net_bp = float(net.mean() * 10000)
    sharpe_proxy = float(net.mean() / net.std(ddof=1) * np.sqrt(252 * 6))  # 6 trades/day approx

    # 3-gate stat tests
    fee_res = fee_aware_perm_test(
        observed_net_returns=net.tolist(),
        candidate_pool_returns=candidate_pool.tolist(),
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )
    ci_res = bootstrap_ci(
        observed_net_returns=net.tolist(),
        n_boot=2000,
        block_size=1,  # triggers already non-overlapping by min-gap construction
        rng_seed=42,
    )

    # H5 sign-conditional: split by BTC 5m return sign AND SOL 5m return sign at trigger
    # BTC 5m return at trigger ts (the bar that caused the breakdown)
    btc_r_at_trig = btc_r_5m.reindex(fwd.index)
    sol_r_5m = compute_5m_returns(sol_close_5m)
    sol_r_at_trig = sol_r_5m.reindex(fwd.index)

    h5_cells = {}
    for btc_sign_label, btc_mask in [
        ("btc_up", btc_r_at_trig > 0),
        ("btc_dn", btc_r_at_trig < 0),
    ]:
        for sol_sign_label, sol_mask in [
            ("sol_up", sol_r_at_trig > 0),
            ("sol_dn", sol_r_at_trig < 0),
        ]:
            mask = (btc_mask & sol_mask).fillna(False).values
            cell_n = int(mask.sum())
            cell_key = f"{btc_sign_label}_{sol_sign_label}"
            if cell_n < 10:
                h5_cells[cell_key] = {"n": cell_n, "skip": "n<10"}
                continue
            cell_net = net[mask]
            cell_t = float(cell_net.mean() / cell_net.std(ddof=1) * np.sqrt(cell_n)) if cell_net.std(ddof=1) > 0 else 0.0
            h5_cells[cell_key] = {
                "n": cell_n,
                "mean_net_bp": float(cell_net.mean() * 10000),
                "mean_gross_bp": float(gross[mask].mean() * 10000),
                "t_stat": cell_t,
            }

    # 3-gate verdict
    pass_signal = fee_res.get("signal_t_excess", float("nan"))
    pass_ci = ci_res.get("ci_lower", float("nan"))
    pass_perm = fee_res.get("perm_p_two_sided", float("nan"))
    gate_signal = bool(np.isfinite(pass_signal) and pass_signal >= 2.0)
    gate_ci = bool(np.isfinite(pass_ci) and pass_ci > 0)
    gate_perm = bool(np.isfinite(pass_perm) and pass_perm <= 0.10)
    three_gate_pass = gate_signal and gate_ci and gate_perm

    return {
        "threshold": threshold,
        "n_triggers": int(n_trig),
        "h1_unsigned_long": {
            "gross_bp": gross_bp,
            "net_bp": net_bp,
            "obs_t": obs_t,
            "sharpe_proxy_ann": sharpe_proxy,
            "fee_aware_perm": fee_res,
            "bootstrap_ci": ci_res,
            "three_gate": {
                "signal_t_excess_pass": gate_signal,
                "ci_lower_pass": gate_ci,
                "perm_p_pass": gate_perm,
                "PASS_ALL": three_gate_pass,
            },
        },
        "h5_sign_conditional": h5_cells,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    log.info("loading 1m OHLCV from joblib cache: BTC, ETH, SOL")

    btc_1m = load_ohlcv_1m_cached("BTCUSDT")
    eth_1m = load_ohlcv_1m_cached("ETHUSDT")
    sol_1m = load_ohlcv_1m_cached(ALT_SYM)
    log.info("loaded BTC=%d ETH=%d SOL=%d 1m bars (%.1fs)",
             len(btc_1m), len(eth_1m), len(sol_1m), time.time() - t_start)

    btc_5m_close = resample_5m(btc_1m)
    eth_5m_close = resample_5m(eth_1m)
    sol_5m_close = resample_5m(sol_1m)
    log.info("resampled to 5m: BTC=%d ETH=%d SOL=%d", len(btc_5m_close), len(eth_5m_close), len(sol_5m_close))

    btc_r = compute_5m_returns(btc_5m_close)
    eth_r = compute_5m_returns(eth_5m_close)

    log.info("building corr z-score panel (rolling 1d corr × 30d z-baseline)")
    corr_z_panel = build_corr_zscore_panel(btc_r, eth_r)
    log.info("corr panel: n=%d, corr mean=%.3f std=%.3f, z mean=%.3f std=%.3f",
             len(corr_z_panel),
             corr_z_panel["corr"].mean(), corr_z_panel["corr"].std(),
             corr_z_panel["corr_zscore"].mean(), corr_z_panel["corr_zscore"].std())

    log.info("building candidate pool (non-overlapping 240m windows on SOL)")
    candidate_pool = build_candidate_pool(sol_5m_close, n_target=30000)
    log.info("candidate pool: n=%d, mean_gross=%.4f bp, std=%.4f",
             len(candidate_pool), candidate_pool.mean() * 10000, candidate_pool.std() * 10000)

    results = {}
    for thr in Z_THRESHOLDS:
        log.info("=== evaluating z_threshold=%.1f ===", thr)
        t0 = time.time()
        res = evaluate_threshold(thr, corr_z_panel, sol_5m_close, btc_r, candidate_pool)
        log.info("  n_trig=%s elapsed=%.1fs", res.get("n_triggers"), time.time() - t0)
        if res.get("n_triggers", 0) >= 10:
            h1 = res["h1_unsigned_long"]
            log.info("  H1: gross=%.2fbp net=%.2fbp t=%.2f signal_excess=%.2f ci_lower=%.6f perm_p=%.3f -> 3-gate PASS=%s",
                     h1["gross_bp"], h1["net_bp"], h1["obs_t"],
                     h1["fee_aware_perm"].get("signal_t_excess", float("nan")),
                     h1["bootstrap_ci"].get("ci_lower", float("nan")),
                     h1["fee_aware_perm"].get("perm_p_two_sided", float("nan")),
                     h1["three_gate"]["PASS_ALL"])
        results[f"z_{thr}"] = res

    # Aggregate verdict
    any_pass = any(
        r.get("h1_unsigned_long", {}).get("three_gate", {}).get("PASS_ALL", False)
        for r in results.values() if isinstance(r, dict) and "h1_unsigned_long" in r
    )

    out = {
        "paradigm": "btc_eth_correlation_breakdown_5m_event_alt_directional",
        "phase": "R-1",
        "alt_sym": ALT_SYM,
        "fee_per_trade": FEE_PER_TRADE,
        "bar_minutes": BAR_MINUTES,
        "hold_minutes": HOLD_MINUTES,
        "corr_window_bars": CORR_WINDOW_BARS,
        "zscore_lookback_bars": ZSCORE_LOOKBACK_BARS,
        "z_thresholds": Z_THRESHOLDS,
        "trigger_min_gap_bars": TRIGGER_MIN_GAP_BARS,
        "data_window": {
            "btc_min": str(btc_1m.index.min()),
            "btc_max": str(btc_1m.index.max()),
            "n_5m_bars": len(btc_5m_close),
        },
        "corr_panel_summary": {
            "n": int(len(corr_z_panel)),
            "corr_mean": float(corr_z_panel["corr"].mean()),
            "corr_std": float(corr_z_panel["corr"].std()),
            "corr_p10": float(corr_z_panel["corr"].quantile(0.10)),
        },
        "candidate_pool": {
            "n": int(len(candidate_pool)),
            "mean_bp": float(candidate_pool.mean() * 10000),
            "std_bp": float(candidate_pool.std() * 10000),
        },
        "by_threshold": results,
        "aggregate_verdict": {
            "any_threshold_3gate_pass": any_pass,
            "verdict": "R1_PASS" if any_pass else "R1_FAIL_GRAVEYARD_CANDIDATE",
        },
        "elapsed_s": round(time.time() - t_start, 1),
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("written %s", OUT_PATH)
    log.info("AGGREGATE VERDICT: %s", out["aggregate_verdict"]["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
