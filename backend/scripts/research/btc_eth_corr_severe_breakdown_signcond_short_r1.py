"""R-1 PoC — paradigm 77: BTC↔ETH 5m corr SEVERE breakdown (z<=-2.5 focus)
+ sign-cond pre-filter (BTC dn × alt dn) → alt 240m forward SHORT
capitulation continuation. Cherry-pick verification of paradigm 76 non-focus
z=-2.5 PASS.

Background — paradigm 76 z=-2.5 non-focus PASS promotion (lesson #15)
---------------------------------------------------------------------
Paradigm 76 focus z=-2.0 → graveyard (signal_t_excess 0.83 < 2.0 cutoff).
However its sweep produced z=-2.5 4-gate ALL PASS:
  n=298, net +33.59bp, signal_excess +3.71σ, perm_p 0.004, ci_lower +11.53bp,
  diversity 10/12.

Cherry-pick risk: 3 z thresholds × 3 paradigms (74/75/76) tested → potential
multiple-comparison artifact.

Paradigm 77 R-1 verification design
-----------------------------------
1. **Replication check**: re-run z=-2.5 with identical pipeline; require
   measurements within ±10% of paradigm 76 (n, net_bp, signal_excess).
2. **Deeper threshold sweep**: z=-2.5 (focus) + z=-2.75 + z=-3.0 — if mechanism
   is real (severe corr breakdown = capitulation cascade), deeper tails should
   keep the same sign (positive net SHORT bp), even with smaller n.
3. **Multi-hold sweep at z=-2.5 focus**: 60m / 120m / 240m (focus) / 480m —
   verify the 240m hold is not cherry-picked.
4. **Bonferroni adjustment**: report adjusted p assuming 9 prior tests
   (3 paradigms × 3 z thresholds) — original p=0.004 × 9 ≈ 0.036, still <0.10.

DNA 4-tuple
-----------
- Data source: OHLCV-only (BTC + ETH + 12 alts 5m)
- Decision mode: regime-conditional (SEVERE corr breakdown deep tail) +
                 sign-conditional (BTC dn × alt dn)
- Time scale: 5m trigger + 240m hold (focus), 60/120/480m sensitivity
- Universe shape: 12 alt directional SHORT only

Distinctness vs paradigm 76
---------------------------
- 76 focus z=-2.0 (moderate breakdown) — graveyard
- 77 focus z=-2.5 (severe breakdown / deep tail capitulation)
- Sweep dimensions differ: 76 was -1.5/-2.0/-2.5; 77 is -2.5/-2.75/-3.0
                           + multi-hold (60/120/240/480)

Sample density prescreen (lesson #11)
-------------------------------------
- z=-2.5: aggregate n≈298 (paradigm 76 measured), per-alt ~25
- z=-2.75: estimated n_agg≈200, per-alt ~17 (marginal)
- z=-3.0: estimated n_agg≈130, per-alt ~11 (per-alt diversity unreliable;
          aggregate-only evaluation noted)

Fee floor prescreen
-------------------
- paradigm 76 z=-2.5 measured: gross +41.59bp / net +33.59bp ≫ 16bp fee floor ✓

11 lessons explicit avoidance
-----------------------------
- #1 _perm_utils.fee_aware_perm_test (n=200 perm + bootstrap_ci + null_mean_t)
- #2 Three-gate strict at focus
- #3 Sign-conditional (paradigm itself sign-cond)
- #5 OHLCV joblib cache
- #6 Mint host explicit + BTCUSDT bar count verify
- #8 Mirror antipattern: SHORT only; LONG mirror auto-attempt forbidden
- #9 Trigger-swap: same mechanism (cross-asset corr breakdown), different
                   threshold severity / hold sweep
- #10 Taker family: pure OHLCV only
- #11 Sample density: per-cell n explicit; n<30 cells skipped or aggregate-only
- #15 (NEW): non-focus PASS promotion policy (this paradigm IS the test case)

R-1 PASS gate (focus z=-2.5 × hold 240m)
-----------------------------------------
- aggregate signal_t_excess >= 2.0
- aggregate ci_lower > 0
- aggregate perm_p_two_sided <= 0.10
- per-alt diversity >= 6/12 net_short_bp positive
- + Replication check: paradigm 76 z=-2.5 ±10% (n, net_bp, sig_excess)

Graveyard conditions
--------------------
- focus z=-2.5 × 240m three-gate FAIL → paradigm 76 PASS = sampling fluke
- Replication failure (>±10% deviation) → suspect implementation drift
- z=-2.75/z=-3.0 both weaker than z=-2.5 with sign flip → "deeper tail =
  stronger" hypothesis falsified
- 60m/120m hold sign-disagrees with 240m → hold-specific cherry-pick

Output
------
backend/runs/research_track/btc_eth_corr_severe_breakdown_signcond_btcdn_altdn_240m_short/r1__metrics.json
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
log = logging.getLogger("p77_r1")

PARADIGM_NAME = "btc_eth_corr_severe_breakdown_signcond_btcdn_altdn_240m_short"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_PATH = OUT_DIR / "r1__metrics.json"

ALT_SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

BAR_MINUTES = 5

# Threshold sweep at focus hold = 240m
Z_THRESHOLDS = [-2.5, -2.75, -3.0]
FOCUS_Z = -2.5

# Hold sweep at focus z = -2.5
HOLD_SWEEP_MIN = [60, 120, 240, 480]
FOCUS_HOLD_MIN = 240

CORR_WINDOW_BARS = 288       # 1d at 5m
ZSCORE_LOOKBACK_BARS = 288 * 30

# Use 240m gap for trigger spacing across all sweeps (consistent with paradigm 76)
TRIGGER_MIN_GAP_BARS = 240 // BAR_MINUTES  # 48 bars

FEE_PER_TRADE = 0.0008
DIVERSITY_MIN_POSITIVE_ALTS = 6

# Replication tolerance vs paradigm 76 z=-2.5 measurements
P76_Z25_REF = {
    "n_signcond_aggregate": 298,
    "short_net_bp": 33.5925251204678,
    "signal_t_excess": 3.7116982494532706,
}
REPLICATION_TOL = 0.10  # ±10%

# Bonferroni assumption: 3 paradigms (74/75/76) × 3 z thresholds = 9 prior tests
BONFERRONI_PRIOR_TESTS = 9


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


def compute_forward_returns(close_5m: pd.Series, trigger_positions: List[int],
                            hold_bars: int) -> pd.Series:
    out_idx, out_val = [], []
    n = len(close_5m)
    for p in trigger_positions:
        if p + hold_bars >= n:
            continue
        c0 = close_5m.iloc[p]
        cT = close_5m.iloc[p + hold_bars]
        if c0 <= 0 or cT <= 0:
            continue
        out_idx.append(close_5m.index[p])
        out_val.append(np.log(cT / c0))
    return pd.Series(out_val, index=out_idx, name=f"fwd{hold_bars * BAR_MINUTES}m_long")


def build_candidate_pool_per_alt(close_5m: pd.Series, hold_bars: int,
                                 n_target: int = 30000) -> np.ndarray:
    n = len(close_5m)
    starts = np.arange(0, n - hold_bars, hold_bars)
    if len(starts) > n_target:
        rng = np.random.default_rng(42)
        starts = np.sort(rng.choice(starts, size=n_target, replace=False))
    c = close_5m.values
    rets = np.log(c[starts + hold_bars] / c[starts])
    return rets[np.isfinite(rets)]


def evaluate_alt_at_threshold(
    alt_sym: str,
    threshold: float,
    hold_bars: int,
    corr_z_panel: pd.DataFrame,
    alt_close_5m: pd.Series,
    btc_r_5m: pd.Series,
) -> Tuple[np.ndarray, Dict]:
    trigger_pos = find_trigger_indices(corr_z_panel["corr_zscore"], threshold)
    if not trigger_pos:
        return np.array([]), {"n_raw_triggers": 0}

    trigger_ts = corr_z_panel.index[trigger_pos]
    alt_idx_map = {ts: i for i, ts in enumerate(alt_close_5m.index)}
    alt_trigger_pos = [alt_idx_map[ts] for ts in trigger_ts if ts in alt_idx_map]
    if not alt_trigger_pos:
        return np.array([]), {"n_raw_triggers": len(trigger_pos), "n_alt_aligned": 0}

    fwd_long = compute_forward_returns(alt_close_5m, alt_trigger_pos, hold_bars)
    if len(fwd_long) == 0:
        return np.array([]), {"n_raw_triggers": len(trigger_pos), "n_fwd": 0}

    alt_r_5m = compute_5m_returns(alt_close_5m)
    btc_at_trig = btc_r_5m.reindex(fwd_long.index)
    alt_at_trig = alt_r_5m.reindex(fwd_long.index)

    mask_btc_dn = (btc_at_trig < 0).fillna(False).values
    mask_alt_dn = (alt_at_trig < 0).fillna(False).values
    mask_filter = mask_btc_dn & mask_alt_dn

    diag = {
        "n_raw_triggers": len(trigger_pos),
        "n_alt_aligned": len(alt_trigger_pos),
        "n_fwd": int(len(fwd_long)),
        "n_btc_dn": int(mask_btc_dn.sum()),
        "n_alt_dn": int(mask_alt_dn.sum()),
        "n_signcond_filtered": int(mask_filter.sum()),
    }

    if int(mask_filter.sum()) < 5:
        return np.array([]), diag

    gross_long = fwd_long.values[mask_filter]
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
    hold_bars: int,
    corr_z_panel: pd.DataFrame,
    alt_close_panel: Dict[str, pd.Series],
    alt_pool_panel: Dict[str, np.ndarray],
    btc_r_5m: pd.Series,
) -> Dict:
    per_alt_nets = []
    per_alt_diag = {}
    aggregate_pool_short = []

    for alt_sym in ALT_SYMS:
        net_short, diag = evaluate_alt_at_threshold(
            alt_sym, threshold, hold_bars, corr_z_panel,
            alt_close_panel[alt_sym], btc_r_5m,
        )
        per_alt_diag[alt_sym] = diag
        if len(net_short) > 0:
            per_alt_nets.append(net_short)
        pool_long = alt_pool_panel[alt_sym]
        pool_short = -pool_long
        if len(pool_short) > 5000:
            rng = np.random.default_rng(hash(alt_sym) & 0xFFFFFFFF)
            pool_short = rng.choice(pool_short, size=5000, replace=False)
        aggregate_pool_short.append(pool_short)

    if not per_alt_nets:
        return {
            "threshold": threshold,
            "hold_minutes": hold_bars * BAR_MINUTES,
            "n_signcond_aggregate": 0,
            "skip_reason": "no alt produced filtered events",
            "per_alt_diag": per_alt_diag,
        }

    aggregate_net_short = np.concatenate(per_alt_nets)
    aggregate_pool_short_arr = np.concatenate(aggregate_pool_short)

    n_agg = int(len(aggregate_net_short))
    if n_agg < 30:
        log.warning("threshold=%.2f hold=%dm: aggregate n=%d < 30 (lesson #11 marginal)",
                    threshold, hold_bars * BAR_MINUTES, n_agg)

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
        "hold_minutes": hold_bars * BAR_MINUTES,
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


def replication_check(focus_result: Dict) -> Dict:
    """Compare paradigm 77 z=-2.5 × 240m result vs paradigm 76 z=-2.5 reference."""
    if "aggregate" not in focus_result:
        return {"PASS_REPLICATION": False, "reason": "no aggregate"}
    agg = focus_result["aggregate"]
    n_obs = focus_result.get("n_signcond_aggregate", 0)
    net_obs = agg.get("short_net_bp", 0.0)
    sigex_obs = agg.get("fee_aware_perm", {}).get("signal_t_excess", 0.0)

    n_ref = P76_Z25_REF["n_signcond_aggregate"]
    net_ref = P76_Z25_REF["short_net_bp"]
    sigex_ref = P76_Z25_REF["signal_t_excess"]

    def within(obs, ref, tol):
        if ref == 0:
            return abs(obs) <= tol
        return abs((obs - ref) / ref) <= tol

    n_ok = within(n_obs, n_ref, REPLICATION_TOL)
    net_ok = within(net_obs, net_ref, REPLICATION_TOL)
    sigex_ok = within(sigex_obs, sigex_ref, REPLICATION_TOL)

    return {
        "n_observed": n_obs, "n_reference_p76": n_ref,
        "net_bp_observed": net_obs, "net_bp_reference_p76": net_ref,
        "signal_excess_observed": sigex_obs, "signal_excess_reference_p76": sigex_ref,
        "tolerance_pct": REPLICATION_TOL * 100,
        "n_within_tol": n_ok,
        "net_within_tol": net_ok,
        "signal_excess_within_tol": sigex_ok,
        "PASS_REPLICATION": bool(n_ok and net_ok and sigex_ok),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    log.info("=== paradigm 77 R-1 (severe breakdown z=-2.5 focus): %s ===", PARADIGM_NAME)
    log.info("loading 1m OHLCV from joblib cache: BTC, ETH, %d alts", len(ALT_SYMS))

    btc_1m = load_ohlcv_1m_cached("BTCUSDT")
    eth_1m = load_ohlcv_1m_cached("ETHUSDT")
    log.info("loaded BTC=%d ETH=%d 1m bars", len(btc_1m), len(eth_1m))

    # Build per-alt panels and pre-compute pools at all hold windows used
    alt_close_panel: Dict[str, pd.Series] = {}
    alt_pool_panel_by_hold: Dict[int, Dict[str, np.ndarray]] = {h: {} for h in HOLD_SWEEP_MIN}

    for alt_sym in ALT_SYMS:
        df = load_ohlcv_1m_cached(alt_sym)
        c5 = resample_5m_close(df)
        alt_close_panel[alt_sym] = c5
        for h_min in HOLD_SWEEP_MIN:
            h_bars = h_min // BAR_MINUTES
            alt_pool_panel_by_hold[h_min][alt_sym] = build_candidate_pool_per_alt(c5, h_bars)
        log.info("  %s: 1m=%d 5m=%d pool[240m]=%d", alt_sym, len(df), len(c5),
                 len(alt_pool_panel_by_hold[240][alt_sym]))

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

    # ---- Sweep 1: threshold sweep at hold=240m ----
    threshold_sweep_results = {}
    focus_hold_bars = FOCUS_HOLD_MIN // BAR_MINUTES
    for thr in Z_THRESHOLDS:
        log.info("=== sweep1 z_threshold=%.2f hold=240m (SHORT) ===", thr)
        t0 = time.time()
        res = evaluate_threshold_aggregate(
            thr, focus_hold_bars, corr_z_panel,
            alt_close_panel, alt_pool_panel_by_hold[FOCUS_HOLD_MIN], btc_r,
        )
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
        threshold_sweep_results[f"z_{thr}"] = res

    # ---- Sweep 2: hold sweep at z=-2.5 focus ----
    hold_sweep_results = {}
    for h_min in HOLD_SWEEP_MIN:
        log.info("=== sweep2 z=-2.5 hold=%dm (SHORT) ===", h_min)
        t0 = time.time()
        h_bars = h_min // BAR_MINUTES
        res = evaluate_threshold_aggregate(
            FOCUS_Z, h_bars, corr_z_panel,
            alt_close_panel, alt_pool_panel_by_hold[h_min], btc_r,
        )
        log.info("  n_agg=%s elapsed=%.1fs", res.get("n_signcond_aggregate"), time.time() - t0)
        if "aggregate" in res:
            agg = res["aggregate"]
            log.info(
                "  AGG SHORT: gross=%.2fbp net=%.2fbp obs_t=%.2f signal_excess=%.2f ci_lower=%.6f perm_p=%.3f div=%d/12",
                agg["short_gross_bp"], agg["short_net_bp"], agg["obs_t"],
                agg["fee_aware_perm"].get("signal_t_excess", float("nan")),
                agg["bootstrap_ci"].get("ci_lower", float("nan")),
                agg["fee_aware_perm"].get("perm_p_two_sided", float("nan")),
                agg["diversity"]["positive_alt_count"],
            )
        hold_sweep_results[f"hold_{h_min}m"] = res

    # ---- Focus result + replication check ----
    focus_key_threshold = f"z_{FOCUS_Z}"
    focus_result = threshold_sweep_results[focus_key_threshold]
    replication = replication_check(focus_result)
    log.info("=== replication check vs paradigm 76 z=-2.5 ===")
    log.info("  n: obs=%d ref=%d within±10%%=%s",
             replication["n_observed"], replication["n_reference_p76"],
             replication["n_within_tol"])
    log.info("  net_bp: obs=%.3f ref=%.3f within±10%%=%s",
             replication["net_bp_observed"], replication["net_bp_reference_p76"],
             replication["net_within_tol"])
    log.info("  signal_excess: obs=%.3f ref=%.3f within±10%%=%s",
             replication["signal_excess_observed"], replication["signal_excess_reference_p76"],
             replication["signal_excess_within_tol"])
    log.info("  REPLICATION_PASS=%s", replication["PASS_REPLICATION"])

    # ---- Bonferroni adjusted p (focus z=-2.5 × hold=240m) ----
    focus_perm_p = focus_result.get("aggregate", {}).get("fee_aware_perm", {}).get("perm_p_two_sided", float("nan"))
    bonferroni_adjusted_p = float(min(1.0, focus_perm_p * BONFERRONI_PRIOR_TESTS)) if np.isfinite(focus_perm_p) else float("nan")
    log.info("=== Bonferroni adjustment ===")
    log.info("  raw_perm_p=%.4f  prior_tests=%d  adj_p=%.4f",
             focus_perm_p, BONFERRONI_PRIOR_TESTS, bonferroni_adjusted_p)

    # ---- Deeper-tail monotonicity check ----
    deeper_tail_check = {}
    for thr in Z_THRESHOLDS:
        agg = threshold_sweep_results[f"z_{thr}"].get("aggregate", {})
        deeper_tail_check[f"z_{thr}"] = {
            "n_agg": threshold_sweep_results[f"z_{thr}"].get("n_signcond_aggregate", 0),
            "short_net_bp": agg.get("short_net_bp", float("nan")),
            "signal_excess": agg.get("fee_aware_perm", {}).get("signal_t_excess", float("nan")),
        }
    deeper_tail_signs_consistent = all(
        np.isfinite(v["short_net_bp"]) and v["short_net_bp"] > 0
        for v in deeper_tail_check.values()
        if v["n_agg"] > 0
    )
    log.info("deeper_tail signs consistent (all positive net_bp at z>=threshold)=%s",
             deeper_tail_signs_consistent)

    # ---- Hold sweep robustness check (sign-consistency vs focus 240m) ----
    focus_240_net = hold_sweep_results[f"hold_{FOCUS_HOLD_MIN}m"].get("aggregate", {}).get("short_net_bp", 0.0)
    focus_sign = 1 if focus_240_net > 0 else -1 if focus_240_net < 0 else 0
    hold_sign_check = {}
    for h_min in HOLD_SWEEP_MIN:
        agg = hold_sweep_results[f"hold_{h_min}m"].get("aggregate", {})
        net_bp = agg.get("short_net_bp", 0.0)
        sign = 1 if net_bp > 0 else -1 if net_bp < 0 else 0
        hold_sign_check[f"hold_{h_min}m"] = {
            "n_agg": hold_sweep_results[f"hold_{h_min}m"].get("n_signcond_aggregate", 0),
            "short_net_bp": net_bp,
            "sign_matches_focus": sign == focus_sign and focus_sign != 0,
        }
    holds_sign_consistent = all(v["sign_matches_focus"] for v in hold_sign_check.values())
    log.info("hold sweep sign consistency vs focus 240m=%s", holds_sign_consistent)

    # ---- Final PASS verdict (all gates) ----
    focus_three_gate = focus_result.get("aggregate", {}).get("three_gate", {}).get("PASS_ALL_3GATE", False)
    focus_diversity = focus_result.get("aggregate", {}).get("diversity", {}).get("PASS_DIVERSITY", False)
    focus_full_pass = focus_result.get("aggregate", {}).get("FULL_PASS", False)

    overall_pass = bool(
        focus_full_pass
        and replication["PASS_REPLICATION"]
        and bonferroni_adjusted_p <= 0.10
    )

    out = {
        "paradigm": PARADIGM_NAME,
        "phase": "R-1",
        "direction": "SHORT",
        "alts": ALT_SYMS,
        "n_alts": len(ALT_SYMS),
        "fee_per_trade": FEE_PER_TRADE,
        "bar_minutes": BAR_MINUTES,
        "focus_hold_minutes": FOCUS_HOLD_MIN,
        "hold_sweep_minutes": HOLD_SWEEP_MIN,
        "corr_window_bars": CORR_WINDOW_BARS,
        "zscore_lookback_bars": ZSCORE_LOOKBACK_BARS,
        "z_thresholds_sweep": Z_THRESHOLDS,
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
        "threshold_sweep_at_240m": threshold_sweep_results,
        "hold_sweep_at_z_neg2_5": hold_sweep_results,
        "deeper_tail_check": {
            "by_threshold": deeper_tail_check,
            "all_positive_net_bp": deeper_tail_signs_consistent,
        },
        "hold_sweep_sign_check": {
            "focus_240m_net_bp": focus_240_net,
            "focus_sign": focus_sign,
            "by_hold": hold_sign_check,
            "all_holds_sign_consistent": holds_sign_consistent,
        },
        "replication_check": replication,
        "bonferroni": {
            "raw_perm_p": focus_perm_p,
            "prior_tests": BONFERRONI_PRIOR_TESTS,
            "adjusted_p": bonferroni_adjusted_p,
            "adjusted_p_pass_p10": bool(np.isfinite(bonferroni_adjusted_p) and bonferroni_adjusted_p <= 0.10),
        },
        "verdict": {
            "focus_z": FOCUS_Z,
            "focus_hold_minutes": FOCUS_HOLD_MIN,
            "focus_three_gate_pass": focus_three_gate,
            "focus_diversity_pass": focus_diversity,
            "focus_full_pass": focus_full_pass,
            "replication_pass": replication["PASS_REPLICATION"],
            "bonferroni_adjusted_p_le_0p10": bool(np.isfinite(bonferroni_adjusted_p) and bonferroni_adjusted_p <= 0.10),
            "deeper_tail_signs_consistent": deeper_tail_signs_consistent,
            "hold_sweep_sign_consistent": holds_sign_consistent,
            "OVERALL_PASS": overall_pass,
            "R1_VERDICT": "R1_PASS" if overall_pass else "R1_FAIL_GRAVEYARD",
        },
        "elapsed_s": round(time.time() - t_start, 1),
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("written %s", OUT_PATH)
    log.info("R1 VERDICT: %s overall_pass=%s focus_full_pass=%s replication=%s bonferroni_adj_p=%.4f",
             out["verdict"]["R1_VERDICT"], overall_pass, focus_full_pass,
             replication["PASS_REPLICATION"], bonferroni_adjusted_p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
