"""R-1 PoC — paradigm 76: BTC↔ETH 5m corr breakdown + sign-cond pre-filter
(BTC dn × alt dn) → alt 240m forward SHORT capitulation continuation.

Paradigm 76. NOT a blind mirror of paradigm 75 LONG (that was BTC dn × alt up).

Justification for separate R-1 (vs paradigm 70 mirror antipattern lesson #8)
---------------------------------------------------------------------------
Paradigm 74 H5 sub-cell analysis (pre-existing evidence):
  - LONG cell  btc_dn × sol_up @ z=-2.0:  n=26  +69.6bp  t=+1.42  (paradigm 75)
  - SHORT cell btc_dn × sol_dn @ z=-2.0:  n=45  -39.9bp  t=-1.60  (this paradigm)

The SHORT sub-cell carried a STRONGER pre-existing |t| (1.60 > 1.42) on a
LARGER sample (45 > 26) in paradigm 74's H5 stratification. Paradigm 75 (LONG
mirror direction) was tested first and graveyarded with focus_z=-2.0 aggregate
n=330, +11bp net, signal_t_excess=+1.78 (just below the 2.0 cutoff), div=7/12.

By the strict paradigm-architect protocol, the per-cell evidence in paradigm
74 H5 favored SHORT over LONG. Therefore this is NOT a "let's also try the
mirror" blind antipattern (paradigm 70 case = UP×LONG +113bp vs DOWN×SHORT
-49bp 13σ gap, no prior evidence justified the mirror); it is an
evidence-prioritized direction selection that happens to be tested second.

Mechanism difference (LONG vs SHORT)
------------------------------------
- LONG (paradigm 75): "BTC sells off but alt holds → alt 240m revert/continue
  UP" (decoupling resilience → mean-reversion / momentum-up).
- SHORT (paradigm 76, here): "BTC sells off and alt joins → 240m alt
  capitulation continuation" (joint sell-off → momentum-down).

Both economic stories are plausible. H5 evidence + lesson #8 protocol favor
testing the SHORT version explicitly with its own three-gate strict R-1.

Hypothesis (1-line)
-------------------
When BTC↔ETH 1d-rolling 5m corr drops to corr_zscore <= -2.0 AND BTC 5m
return < 0 AND alt 5m return < 0 at the trigger bar, the alt's 240-minute
forward SHORT return exhibits positive (post-fee) capitulation continuation
alpha aggregated across 12 alts.

DNA 4-tuple
-----------
- Data source: OHLCV-only (BTC + ETH + 12 alts 5m)
- Decision mode: regime-conditional + sign-conditional pre-filter (BTC dn × alt dn)
- Time scale: 5m trigger + 240m hold
- Universe shape: 12 alt directional SHORT only

Distinctness vs prior paradigms
-------------------------------
- p70: paradigm 69 mirror SHORT — single-asset BTC vol regime DOWN×SHORT, 13σ
       below paradigm 69 LONG side, graveyard precedent. Different mechanism
       (single-asset vol stress), different DNA. Lesson #8 cites it as the
       reason mirrors require independent R-1 evidence — which this paradigm
       provides via paradigm 74 H5.
- p74: cross-asset corr breakdown UNSIGNED LONG, SOL only. Graveyard.
- p75: cross-asset corr breakdown signed BTC dn × alt UP LONG. Graveyard
       (focus signal_t_excess 1.78 below 2.0 cutoff, div 7/12 at focus).
- p76 (this): cross-asset corr breakdown signed BTC dn × alt DN SHORT.
       OPPOSITE sign-cond pre-filter from p75, OPPOSITE direction.

Aggregate-on-R-1 (lesson #11 sample density)
---------------------------------------------
- Per-alt cell n estimate: ~110 raw × 50% btc_dn × ~50% alt_dn ≈ 27-30
- Aggregate over 12 alts: ~330-360 events expected (vs paradigm 75 LONG = 330)
- Borderline per-alt n; aggregate sufficient

Stat suite (lessons #1, #2 — three-gate strict, SHORT-aware)
------------------------------------------------------------
For SHORT direction:
  gross_short = -fwd_long_return   (alt -X% → SHORT gain +X% gross)
  net_short   = gross_short - fee  (8 bp round-trip)

- fee_aware_perm_test(observed=net_short, pool=-pool_long): signal_t_excess >= 2.0
- bootstrap_ci(observed=net_short): ci_lower > 0
- perm_p_two_sided <= 0.10
- Per-alt diversity: >= 6/12 alts with net_short_bp > 0
ALL four required for R-1 PASS.

Z-threshold sweep
-----------------
- z = -1.5 / -2.0 / -2.5
- Focus = -2.0 (paradigm 74 H5 trigger threshold, paradigm 75 same focus)

Fee = 8 bp round-trip = 0.0008.

Output
------
backend/runs/research_track/btc_eth_corr_breakdown_signcond_btcdn_altdn_240m_short/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

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
log = logging.getLogger("p76_r1")

PARADIGM_NAME = "btc_eth_corr_breakdown_signcond_btcdn_altdn_240m_short"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_PATH = OUT_DIR / "r1__metrics.json"

ALT_SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

BAR_MINUTES = 5
HOLD_MINUTES = 240
HOLD_BARS = HOLD_MINUTES // BAR_MINUTES  # 48 bars

CORR_WINDOW_BARS = 288       # 1 day at 5m
ZSCORE_LOOKBACK_BARS = 288 * 30
Z_THRESHOLDS = [-1.5, -2.0, -2.5]
FOCUS_Z = -2.0

TRIGGER_MIN_GAP_BARS = HOLD_BARS

FEE_PER_TRADE = 0.0008
DIVERSITY_MIN_POSITIVE_ALTS = 6


def resample_5m_close(df_1m: pd.DataFrame) -> pd.Series:
    return df_1m["close"].resample(f"{BAR_MINUTES}min").last().dropna()


def compute_5m_returns(close_5m: pd.Series) -> pd.Series:
    return np.log(close_5m / close_5m.shift(1))


def build_corr_zscore_panel(btc_r: pd.Series, eth_r: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"btc_r": btc_r, "eth_r": eth_r}).dropna()
    corr = df["btc_r"].rolling(CORR_WINDOW_BARS).corr(df["eth_r"])
    corr_mean = corr.rolling(ZSCORE_LOOKBACK_BARS).mean()
    corr_std = corr.rolling(ZSCORE_LOOKBACK_BARS).std()
    corr_z = (corr - corr_mean) / corr_std
    return pd.DataFrame({"corr": corr, "corr_zscore": corr_z}).dropna()


def find_trigger_indices(corr_z: pd.Series, threshold: float) -> List[int]:
    z = corr_z.values
    cross = (z[1:] <= threshold) & (z[:-1] > threshold)
    candidate_pos = np.where(cross)[0] + 1
    if len(candidate_pos) == 0:
        return []
    selected = [int(candidate_pos[0])]
    for p in candidate_pos[1:]:
        if p - selected[-1] >= TRIGGER_MIN_GAP_BARS:
            selected.append(int(p))
    return selected


def compute_forward_returns(close_5m: pd.Series, trigger_positions: List[int]) -> pd.Series:
    """Compute LONG-direction forward log returns; SHORT = -this."""
    out_idx, out_val = [], []
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


def build_candidate_pool_per_alt(close_5m: pd.Series, n_target: int = 30000) -> np.ndarray:
    """Non-overlapping 240m forward LONG returns; for SHORT use -1 * pool."""
    n = len(close_5m)
    starts = np.arange(0, n - HOLD_BARS, HOLD_BARS)
    if len(starts) > n_target:
        rng = np.random.default_rng(42)
        starts = np.sort(rng.choice(starts, size=n_target, replace=False))
    c = close_5m.values
    rets = np.log(c[starts + HOLD_BARS] / c[starts])
    return rets[np.isfinite(rets)]


def evaluate_alt_at_threshold(
    alt_sym: str,
    threshold: float,
    corr_z_panel: pd.DataFrame,
    alt_close_5m: pd.Series,
    btc_r_5m: pd.Series,
) -> Tuple[np.ndarray, Dict]:
    """For one alt at one z threshold:
    apply sign-cond pre-filter (btc_dn × alt_dn at trigger),
    return (post-fee NET-SHORT returns array, diagnostic dict).

    SHORT mechanics: net_short = -fwd_long_return - FEE_PER_TRADE
    """
    trigger_pos = find_trigger_indices(corr_z_panel["corr_zscore"], threshold)
    if not trigger_pos:
        return np.array([]), {"n_raw_triggers": 0}

    trigger_ts = corr_z_panel.index[trigger_pos]

    alt_idx_map = {ts: i for i, ts in enumerate(alt_close_5m.index)}
    alt_trigger_pos = [alt_idx_map[ts] for ts in trigger_ts if ts in alt_idx_map]
    if not alt_trigger_pos:
        return np.array([]), {"n_raw_triggers": len(trigger_pos), "n_alt_aligned": 0}

    fwd_long = compute_forward_returns(alt_close_5m, alt_trigger_pos)
    if len(fwd_long) == 0:
        return np.array([]), {"n_raw_triggers": len(trigger_pos), "n_fwd": 0}

    alt_r_5m = compute_5m_returns(alt_close_5m)
    btc_at_trig = btc_r_5m.reindex(fwd_long.index)
    alt_at_trig = alt_r_5m.reindex(fwd_long.index)

    # SHORT-side sign-cond pre-filter: btc_dn × alt_dn
    mask_btc_dn = (btc_at_trig < 0).fillna(False).values
    mask_alt_dn = (alt_at_trig < 0).fillna(False).values
    mask_filter = mask_btc_dn & mask_alt_dn

    n_raw_fwd = len(fwd_long)
    n_btc_dn = int(mask_btc_dn.sum())
    n_alt_dn = int(mask_alt_dn.sum())
    n_filtered = int(mask_filter.sum())

    diag = {
        "n_raw_triggers": len(trigger_pos),
        "n_alt_aligned": len(alt_trigger_pos),
        "n_fwd": n_raw_fwd,
        "n_btc_dn": n_btc_dn,
        "n_alt_dn": n_alt_dn,
        "n_signcond_filtered": n_filtered,
    }

    if n_filtered < 5:
        return np.array([]), diag

    gross_long = fwd_long.values[mask_filter]
    # SHORT direction
    gross_short = -gross_long
    net_short = gross_short - FEE_PER_TRADE

    diag["mean_long_gross_bp"] = float(gross_long.mean() * 10000)
    diag["mean_short_gross_bp"] = float(gross_short.mean() * 10000)
    diag["mean_short_net_bp"] = float(net_short.mean() * 10000)
    if len(net_short) > 1 and net_short.std(ddof=1) > 0:
        diag["t_stat"] = float(net_short.mean() / net_short.std(ddof=1) * np.sqrt(len(net_short)))
    else:
        diag["t_stat"] = 0.0
    return net_short, diag


def evaluate_threshold_aggregate(
    threshold: float,
    corr_z_panel: pd.DataFrame,
    alt_close_panel: Dict[str, pd.Series],
    alt_pool_panel: Dict[str, np.ndarray],
    btc_r_5m: pd.Series,
) -> Dict:
    """Aggregate test across all 12 alts at one threshold (SHORT direction)."""
    per_alt_nets = []
    per_alt_diag = {}
    aggregate_pool_short = []

    for alt_sym in ALT_SYMS:
        net_short, diag = evaluate_alt_at_threshold(
            alt_sym, threshold, corr_z_panel,
            alt_close_panel[alt_sym], btc_r_5m,
        )
        per_alt_diag[alt_sym] = diag
        if len(net_short) > 0:
            per_alt_nets.append(net_short)
        # SHORT pool = -1 * LONG pool (the natural mirror of the candidate distribution)
        pool_long = alt_pool_panel[alt_sym]
        pool_short = -pool_long  # SHORT gross from same windows
        if len(pool_short) > 5000:
            rng = np.random.default_rng(hash(alt_sym) & 0xFFFFFFFF)
            pool_short = rng.choice(pool_short, size=5000, replace=False)
        aggregate_pool_short.append(pool_short)

    if not per_alt_nets:
        return {
            "threshold": threshold,
            "n_signcond_aggregate": 0,
            "skip_reason": "no alt produced filtered events",
            "per_alt_diag": per_alt_diag,
        }

    aggregate_net_short = np.concatenate(per_alt_nets)
    aggregate_pool_short_arr = np.concatenate(aggregate_pool_short)

    n_agg = len(aggregate_net_short)
    if n_agg < 30:
        log.warning("threshold=%.1f: aggregate n=%d < 30 (lesson #11 marginal)", threshold, n_agg)

    short_gross_mean_bp = float((aggregate_net_short.mean() + FEE_PER_TRADE) * 10000)
    short_net_mean_bp = float(aggregate_net_short.mean() * 10000)
    if aggregate_net_short.std(ddof=1) > 0:
        obs_t = float(aggregate_net_short.mean() / aggregate_net_short.std(ddof=1) * np.sqrt(n_agg))
        sharpe_proxy = float(aggregate_net_short.mean() / aggregate_net_short.std(ddof=1) * np.sqrt(252 * 6))
    else:
        obs_t = 0.0
        sharpe_proxy = 0.0

    fee_res = fee_aware_perm_test(
        observed_net_returns=aggregate_net_short.tolist(),
        candidate_pool_returns=aggregate_pool_short_arr.tolist(),
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )
    ci_res = bootstrap_ci(
        observed_net_returns=aggregate_net_short.tolist(),
        n_boot=2000,
        block_size=1,
        rng_seed=42,
    )

    pos_alt_count = 0
    diversity_alts = []
    for alt_sym, diag in per_alt_diag.items():
        if diag.get("n_signcond_filtered", 0) >= 5 and diag.get("mean_short_net_bp", 0) > 0:
            pos_alt_count += 1
            diversity_alts.append(alt_sym)

    sig_excess = fee_res.get("signal_t_excess", float("nan"))
    ci_lower = ci_res.get("ci_lower", float("nan"))
    perm_p = fee_res.get("perm_p_two_sided", float("nan"))
    gate_signal = bool(np.isfinite(sig_excess) and sig_excess >= 2.0)
    gate_ci = bool(np.isfinite(ci_lower) and ci_lower > 0)
    gate_perm = bool(np.isfinite(perm_p) and perm_p <= 0.10)
    gate_diversity = pos_alt_count >= DIVERSITY_MIN_POSITIVE_ALTS
    three_gate_pass = gate_signal and gate_ci and gate_perm
    full_pass = three_gate_pass and gate_diversity

    return {
        "threshold": threshold,
        "n_signcond_aggregate": n_agg,
        "aggregate": {
            "short_gross_bp": short_gross_mean_bp,
            "short_net_bp": short_net_mean_bp,
            "obs_t": obs_t,
            "sharpe_proxy_ann": sharpe_proxy,
            "fee_aware_perm": fee_res,
            "bootstrap_ci": ci_res,
            "three_gate": {
                "signal_t_excess_pass": gate_signal,
                "ci_lower_pass": gate_ci,
                "perm_p_pass": gate_perm,
                "PASS_ALL_3GATE": three_gate_pass,
            },
            "diversity": {
                "positive_alt_count": pos_alt_count,
                "min_required": DIVERSITY_MIN_POSITIVE_ALTS,
                "PASS_DIVERSITY": gate_diversity,
                "positive_alts": diversity_alts,
            },
            "FULL_PASS": full_pass,
        },
        "per_alt_diag": per_alt_diag,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    log.info("=== paradigm 76 R-1 (SHORT mirror with H5 evidence): %s ===", PARADIGM_NAME)
    log.info("loading 1m OHLCV from joblib cache: BTC, ETH, %d alts", len(ALT_SYMS))

    btc_1m = load_ohlcv_1m_cached("BTCUSDT")
    eth_1m = load_ohlcv_1m_cached("ETHUSDT")
    log.info("loaded BTC=%d ETH=%d 1m bars", len(btc_1m), len(eth_1m))

    alt_close_panel = {}
    alt_pool_panel = {}
    for alt_sym in ALT_SYMS:
        df = load_ohlcv_1m_cached(alt_sym)
        c5 = resample_5m_close(df)
        alt_close_panel[alt_sym] = c5
        alt_pool_panel[alt_sym] = build_candidate_pool_per_alt(c5)
        log.info("  %s: 1m=%d 5m=%d pool_n=%d", alt_sym, len(df), len(c5), len(alt_pool_panel[alt_sym]))

    btc_5m_close = resample_5m_close(btc_1m)
    eth_5m_close = resample_5m_close(eth_1m)
    btc_r = compute_5m_returns(btc_5m_close)
    eth_r = compute_5m_returns(eth_5m_close)

    log.info("building corr z-score panel (rolling 1d corr × 30d z-baseline)")
    corr_z_panel = build_corr_zscore_panel(btc_r, eth_r)
    log.info("corr panel: n=%d, corr mean=%.3f std=%.3f, z mean=%.3f std=%.3f",
             len(corr_z_panel),
             corr_z_panel["corr"].mean(), corr_z_panel["corr"].std(),
             corr_z_panel["corr_zscore"].mean(), corr_z_panel["corr_zscore"].std())

    results_by_threshold = {}
    for thr in Z_THRESHOLDS:
        log.info("=== evaluating z_threshold=%.1f (SHORT) ===", thr)
        t0 = time.time()
        res = evaluate_threshold_aggregate(thr, corr_z_panel, alt_close_panel, alt_pool_panel, btc_r)
        log.info("  n_agg=%s elapsed=%.1fs", res.get("n_signcond_aggregate"), time.time() - t0)
        if "aggregate" in res:
            agg = res["aggregate"]
            log.info(
                "  AGG SHORT: gross=%.2fbp net=%.2fbp obs_t=%.2f null_mean_t=%.2f signal_excess=%.2f ci_lower=%.6f perm_p=%.3f",
                agg["short_gross_bp"], agg["short_net_bp"], agg["obs_t"],
                agg["fee_aware_perm"].get("null_mean_t", float("nan")),
                agg["fee_aware_perm"].get("signal_t_excess", float("nan")),
                agg["bootstrap_ci"].get("ci_lower", float("nan")),
                agg["fee_aware_perm"].get("perm_p_two_sided", float("nan")),
            )
            log.info(
                "  3-gate=%s diversity=%s/%d FULL_PASS=%s",
                agg["three_gate"]["PASS_ALL_3GATE"],
                agg["diversity"]["positive_alt_count"], DIVERSITY_MIN_POSITIVE_ALTS,
                agg["FULL_PASS"],
            )
        results_by_threshold[f"z_{thr}"] = res

    focus_key = f"z_{FOCUS_Z}"
    focus_res = results_by_threshold.get(focus_key, {})
    focus_pass = bool(focus_res.get("aggregate", {}).get("FULL_PASS", False))

    any_pass = any(
        r.get("aggregate", {}).get("FULL_PASS", False)
        for r in results_by_threshold.values()
        if isinstance(r, dict) and "aggregate" in r
    )

    out = {
        "paradigm": PARADIGM_NAME,
        "phase": "R-1",
        "direction": "SHORT",
        "alts": ALT_SYMS,
        "n_alts": len(ALT_SYMS),
        "fee_per_trade": FEE_PER_TRADE,
        "bar_minutes": BAR_MINUTES,
        "hold_minutes": HOLD_MINUTES,
        "corr_window_bars": CORR_WINDOW_BARS,
        "zscore_lookback_bars": ZSCORE_LOOKBACK_BARS,
        "z_thresholds": Z_THRESHOLDS,
        "focus_z": FOCUS_Z,
        "trigger_min_gap_bars": TRIGGER_MIN_GAP_BARS,
        "diversity_min_positive_alts": DIVERSITY_MIN_POSITIVE_ALTS,
        "data_window": {
            "btc_min": str(btc_1m.index.min()),
            "btc_max": str(btc_1m.index.max()),
            "n_5m_bars": int(len(btc_5m_close)),
        },
        "corr_panel_summary": {
            "n": int(len(corr_z_panel)),
            "corr_mean": float(corr_z_panel["corr"].mean()),
            "corr_std": float(corr_z_panel["corr"].std()),
            "corr_p10": float(corr_z_panel["corr"].quantile(0.10)),
        },
        "by_threshold": results_by_threshold,
        "verdict": {
            "focus_z": FOCUS_Z,
            "focus_full_pass": focus_pass,
            "any_threshold_full_pass": any_pass,
            "R1_VERDICT": "R1_PASS" if focus_pass else (
                "R1_PARTIAL_NONFOCUS" if any_pass else "R1_FAIL_GRAVEYARD"
            ),
        },
        "elapsed_s": round(time.time() - t_start, 1),
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("written %s", OUT_PATH)
    log.info("R1 VERDICT: %s (focus_z=%s focus_pass=%s any_pass=%s)",
             out["verdict"]["R1_VERDICT"], FOCUS_Z, focus_pass, any_pass)
    return 0


if __name__ == "__main__":
    sys.exit(main())
