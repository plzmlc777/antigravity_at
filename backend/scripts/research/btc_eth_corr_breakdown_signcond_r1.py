"""R-1 PoC — paradigm 75: BTC↔ETH 5m corr breakdown + sign-cond pre-filter
(BTC dn × alt up) → alt 240m forward LONG continuation.

Paradigm 75 (Q3 §6.5+ candidate). Promotion of paradigm 74 H5 sub-finding.

Hypothesis
----------
When the 1-day rolling Pearson correlation between BTC 5m log returns and
ETH 5m log returns drops to corr_zscore <= -2.0 (corr breakdown), AND
simultaneously:
  - BTC 5m return at the trigger bar < 0  (BTC sell-off)
  - alt 5m return at the trigger bar > 0  (alt resilience / decoupling)
then the alt's 240-minute forward LONG return exhibits positive
continuation alpha — the decoupling persists.

This is paradigm 74 H5 sub-cell `btc_dn × sol_up @ z=-2.0` (n=26,
+69.6 bp gross, t=+1.42 SOL only) promoted to a sign-conditional
PRE-filter R-1 hypothesis with cross-alt aggregation for power.

Distinctness vs prior paradigms
-------------------------------
- p69: single-asset BTC vol regime (RV-based) → 13 alt LONG. Mechanism =
       single-asset vol stress. ORTHOGONAL to cross-asset corr regime.
- p74: cross-asset corr breakdown, UNSIGNED LONG, SOL-only. Graveyarded.
- p75 (this): cross-asset corr breakdown + SIGN-conditional pre-filter
       (BTC dn × alt up) + 12-alt aggregate LONG.
       New mechanism. Not a trigger-swap (corr regime + sign filter is a
       distinct compound trigger). Not a mirror (only LONG side tested).

Aggregate-on-R-1 deviation (justified)
--------------------------------------
Standard paradigm-architect R-1 = single sym (e.g. SOL only). Paradigm 75
deviates: aggregate over 12 alts in cache (ADA/AVAX/BCH/BNB/DOGE/FIL/LINK/
LTC/NEAR/SOL/WIF/XRP). Justification:
  - paradigm 74 H5 SOL-only n=26 was power-limited (t=+1.42, marginal).
  - hypothesis is alt-class universal (cross-asset corr regime affects all
    alts symmetrically), so aggregation is *the* test.
  - sample density prescreen: 12 × 156 × 0.50 × 0.50 ≈ 468 events
    aggregate, ~39 per alt cell (>= 30 marginal, lesson #11 OK).

Note: cache contains 12 alts not 13 (no MATIC etc.). Spec said 13; we use
the actual 12 in cache.

Stat suite (lessons #1, #2 — three-gate strict)
-----------------------------------------------
- fee_aware_perm_test: signal_t_excess >= 2.0 (vs fee-saturated null)
- bootstrap_ci: ci_lower > 0 (95% CI on net mean excludes zero)
- perm_p_two_sided <= 0.10
ALL three required for R-1 PASS.

Per-alt diversity (R-2 criterion borrowed for R-1 power test)
-------------------------------------------------------------
- >= 6/12 alts with positive net_bp at the focus threshold (z=-2.0).
- If aggregate PASSES gates but only 1-2 alts carry the alpha,
  flag as "single-alt artifact" and do NOT promote.

Z-threshold sweep
-----------------
- z = -1.5 / -2.0 / -2.5
- Focus = -2.0 (paradigm 74 H5 trigger threshold)

Fee = 8 bp round-trip (Binance Futures USDT-M) = 0.0008.

Output
------
backend/runs/research_track/btc_eth_corr_breakdown_signcond_btcdn_altup_240m_long/r1__metrics.json
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
log = logging.getLogger("p75_r1")

PARADIGM_NAME = "btc_eth_corr_breakdown_signcond_btcdn_altup_240m_long"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_PATH = OUT_DIR / "r1__metrics.json"

# Trigger asset = BTC × ETH corr; alts under test = 12 alts in cache
ALT_SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

# Bar geometry
BAR_MINUTES = 5
HOLD_MINUTES = 240
HOLD_BARS = HOLD_MINUTES // BAR_MINUTES  # 48 bars

# Corr regime computation (matches paradigm 74)
CORR_WINDOW_BARS = 288       # 1 day at 5m
ZSCORE_LOOKBACK_BARS = 288 * 30  # ~30 days of corr observations
Z_THRESHOLDS = [-1.5, -2.0, -2.5]
FOCUS_Z = -2.0

# Trigger anti-clustering: at least HOLD_BARS gap between triggers per alt
TRIGGER_MIN_GAP_BARS = HOLD_BARS

FEE_PER_TRADE = 0.0008

# Per-alt diversity test (paradigm 74 H5 promotion guardrail)
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
    """Cross-down events: prev > thr, curr <= thr. Apply min-gap."""
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
    """Non-overlapping 240m forward windows for fee_aware_perm_test pool."""
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
    apply sign-cond pre-filter (btc_dn × alt_up at trigger),
    return (post-fee net returns array, diagnostic dict).
    """
    trigger_pos = find_trigger_indices(corr_z_panel["corr_zscore"], threshold)
    if not trigger_pos:
        return np.array([]), {"n_raw_triggers": 0}

    trigger_ts = corr_z_panel.index[trigger_pos]

    # Map to alt's 5m timeline
    alt_idx_map = {ts: i for i, ts in enumerate(alt_close_5m.index)}
    alt_trigger_pos = [alt_idx_map[ts] for ts in trigger_ts if ts in alt_idx_map]
    if not alt_trigger_pos:
        return np.array([]), {"n_raw_triggers": len(trigger_pos), "n_alt_aligned": 0}

    fwd = compute_forward_returns(alt_close_5m, alt_trigger_pos)
    if len(fwd) == 0:
        return np.array([]), {"n_raw_triggers": len(trigger_pos), "n_fwd": 0}

    # Sign-cond pre-filter: btc_dn (BTC 5m return < 0) × alt_up (alt 5m return > 0) at trigger ts
    alt_r_5m = compute_5m_returns(alt_close_5m)
    btc_at_trig = btc_r_5m.reindex(fwd.index)
    alt_at_trig = alt_r_5m.reindex(fwd.index)

    mask_btc_dn = (btc_at_trig < 0).fillna(False).values
    mask_alt_up = (alt_at_trig > 0).fillna(False).values
    mask_filter = mask_btc_dn & mask_alt_up

    n_raw_fwd = len(fwd)
    n_btc_dn = int(mask_btc_dn.sum())
    n_alt_up = int(mask_alt_up.sum())
    n_filtered = int(mask_filter.sum())

    diag = {
        "n_raw_triggers": len(trigger_pos),
        "n_alt_aligned": len(alt_trigger_pos),
        "n_fwd": n_raw_fwd,
        "n_btc_dn": n_btc_dn,
        "n_alt_up": n_alt_up,
        "n_signcond_filtered": n_filtered,
    }

    if n_filtered < 5:
        return np.array([]), diag

    gross = fwd.values[mask_filter]
    net = gross - FEE_PER_TRADE

    diag["mean_gross_bp"] = float(gross.mean() * 10000)
    diag["mean_net_bp"] = float(net.mean() * 10000)
    if len(net) > 1 and net.std(ddof=1) > 0:
        diag["t_stat"] = float(net.mean() / net.std(ddof=1) * np.sqrt(len(net)))
    else:
        diag["t_stat"] = 0.0
    return net, diag


def evaluate_threshold_aggregate(
    threshold: float,
    corr_z_panel: pd.DataFrame,
    alt_close_panel: Dict[str, pd.Series],
    alt_pool_panel: Dict[str, np.ndarray],
    btc_r_5m: pd.Series,
) -> Dict:
    """Aggregate test across all 12 alts at one threshold."""
    per_alt_nets = []
    per_alt_diag = {}
    aggregate_pool = []

    for alt_sym in ALT_SYMS:
        net, diag = evaluate_alt_at_threshold(
            alt_sym, threshold, corr_z_panel,
            alt_close_panel[alt_sym], btc_r_5m,
        )
        per_alt_diag[alt_sym] = diag
        if len(net) > 0:
            per_alt_nets.append(net)
        # Aggregate candidate pool: pool all alt's non-overlapping 240m windows together
        # (subsample for memory efficiency)
        pool = alt_pool_panel[alt_sym]
        if len(pool) > 5000:
            rng = np.random.default_rng(hash(alt_sym) & 0xFFFFFFFF)
            pool = rng.choice(pool, size=5000, replace=False)
        aggregate_pool.append(pool)

    if not per_alt_nets:
        return {
            "threshold": threshold,
            "n_signcond_aggregate": 0,
            "skip_reason": "no alt produced filtered events",
            "per_alt_diag": per_alt_diag,
        }

    aggregate_net = np.concatenate(per_alt_nets)
    aggregate_pool_arr = np.concatenate(aggregate_pool)

    n_agg = len(aggregate_net)
    if n_agg < 30:
        log.warning("threshold=%.1f: aggregate n=%d < 30 (lesson #11 marginal)", threshold, n_agg)

    gross_mean_bp = float((aggregate_net.mean() + FEE_PER_TRADE) * 10000)
    net_mean_bp = float(aggregate_net.mean() * 10000)
    if aggregate_net.std(ddof=1) > 0:
        obs_t = float(aggregate_net.mean() / aggregate_net.std(ddof=1) * np.sqrt(n_agg))
        sharpe_proxy = float(aggregate_net.mean() / aggregate_net.std(ddof=1) * np.sqrt(252 * 6))
    else:
        obs_t = 0.0
        sharpe_proxy = 0.0

    fee_res = fee_aware_perm_test(
        observed_net_returns=aggregate_net.tolist(),
        candidate_pool_returns=aggregate_pool_arr.tolist(),
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )
    ci_res = bootstrap_ci(
        observed_net_returns=aggregate_net.tolist(),
        n_boot=2000,
        block_size=1,
        rng_seed=42,
    )

    # Per-alt diversity at this threshold: count alts with positive mean_net_bp & n>=5
    pos_alt_count = 0
    diversity_alts = []
    for alt_sym, diag in per_alt_diag.items():
        if diag.get("n_signcond_filtered", 0) >= 5 and diag.get("mean_net_bp", 0) > 0:
            pos_alt_count += 1
            diversity_alts.append(alt_sym)

    # Three-gate verdict (aggregate)
    sig_excess = fee_res.get("signal_t_excess", float("nan"))
    ci_lower = ci_res.get("ci_lower", float("nan"))
    perm_p = fee_res.get("perm_p_two_sided", float("nan"))
    null_mean_t = fee_res.get("null_mean_t", float("nan"))
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
            "gross_bp": gross_mean_bp,
            "net_bp": net_mean_bp,
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
    log.info("=== paradigm 75 R-1: %s ===", PARADIGM_NAME)
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
        log.info("=== evaluating z_threshold=%.1f ===", thr)
        t0 = time.time()
        res = evaluate_threshold_aggregate(thr, corr_z_panel, alt_close_panel, alt_pool_panel, btc_r)
        log.info("  n_agg=%s elapsed=%.1fs", res.get("n_signcond_aggregate"), time.time() - t0)
        if "aggregate" in res:
            agg = res["aggregate"]
            log.info(
                "  AGG: gross=%.2fbp net=%.2fbp obs_t=%.2f null_mean_t=%.2f signal_excess=%.2f ci_lower=%.6f perm_p=%.3f",
                agg["gross_bp"], agg["net_bp"], agg["obs_t"],
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

    # Verdict — focus on z=-2.0 (the H5 sub-cell threshold)
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
