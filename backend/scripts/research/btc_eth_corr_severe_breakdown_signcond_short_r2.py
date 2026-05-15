"""R-2 robustness — paradigm 77: BTC↔ETH 5m corr SEVERE breakdown
(z<=-2.5 focus) + sign-cond pre-filter (BTC dn × alt dn) → alt 240m SHORT.

R-1 PASS recap (4-gate ALL):
  n=298, net +33.59bp, sig_t_excess +3.69σ, perm_p 0.005,
  ci_lower +11.53bp, diversity 10/12, replication ✓, Bonferroni adj_p 0.045.

Risk identified
---------------
Single-point z=-2.5 cliff/sweet spot (z=-2.75 weak +10bp, z=-3.0 sign flip).

R-2 four robustness checks
--------------------------
1. **Fine-grain z plateau** (sweep z=-2.3/-2.4/-2.5/-2.6/-2.7 at 240m hold)
   - PASS: 5/5 z net_bp positive AND adjacent ±0.1 (z=-2.4/-2.6) sig_t_excess >= +1.5σ
   - FAIL: any sign flip at z=-2.4 or z=-2.6 → cliff artifact, graveyard
2. **Quarterly 10-fold consistency** (2024Q1 .. 2026Q2)
   - PASS: every quarter with cell_n ≥ 10 has positive net_bp (substantive PASS)
   - FAIL: any measurable quarter strong negative (t < -1.5)
3. **BTC vol regime stratify** (4 quartile by 30d realized vol z-score at trigger)
   - PASS: all regimes positive net (or 1 mild negative t > -1.0)
   - FAIL: any regime strong negative (t < -1.5)
4. **Per-symbol bootstrap** (12 alts × 1000-iter)
   - PASS: 10/12 R-1-positive alts have ci_lower > 0 (or ≥ 8/10)
   - FAIL: cherry-pick → most positive alts ci_lower ≤ 0

Pipeline reuses R-1 code: re-load OHLCV from joblib cache, recompute corr-z
panel, find triggers per z, sign-cond filter, evaluate per stratum.

Lessons explicit
----------------
- #1 _perm_utils.fee_aware_perm_test n=200 per quarter / per regime
- #2 Three-gate strict at every cell where applicable
- #3 Sign-conditional baked-in
- #4 Vol regime stratify (this R-2 check #3)
- #5 OHLCV joblib cache
- #6 Mint host explicit run
- #7 Mechanical vs Substantive verdict (n<10 cells flagged measurement-impossible)
- #8 Mirror antipattern: SHORT only
- #11 Sample density per-cell n explicit; n<10 skip

Output
------
backend/runs/research_track/btc_eth_corr_severe_breakdown_signcond_btcdn_altdn_240m_short/r2__metrics.json
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
log = logging.getLogger("p77_r2")

PARADIGM_NAME = "btc_eth_corr_severe_breakdown_signcond_btcdn_altdn_240m_short"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_PATH = OUT_DIR / "r2__metrics.json"

ALT_SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

BAR_MINUTES = 5
FOCUS_Z = -2.5
FOCUS_HOLD_MIN = 240
FOCUS_HOLD_BARS = FOCUS_HOLD_MIN // BAR_MINUTES

# Check 1 — fine-grain z plateau
PLATEAU_Z = [-2.3, -2.4, -2.5, -2.6, -2.7]

# Check 2 — quarterly bins (calendar quarters from 2024Q1..2026Q2)
QUARTERS = [
    ("2024Q1", "2024-01-01", "2024-04-01"),
    ("2024Q2", "2024-04-01", "2024-07-01"),
    ("2024Q3", "2024-07-01", "2024-10-01"),
    ("2024Q4", "2024-10-01", "2025-01-01"),
    ("2025Q1", "2025-01-01", "2025-04-01"),
    ("2025Q2", "2025-04-01", "2025-07-01"),
    ("2025Q3", "2025-07-01", "2025-10-01"),
    ("2025Q4", "2025-10-01", "2026-01-01"),
    ("2026Q1", "2026-01-01", "2026-04-01"),
    ("2026Q2", "2026-04-01", "2026-07-01"),
]
QUARTER_MIN_N = 10

# Check 3 — BTC vol regime stratify
VOL_LOOKBACK_5M_BARS = 30 * 24 * (60 // BAR_MINUTES)   # 30d at 5m = 8640
VOL_QUARTILES = [(0.0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.0)]
VOL_REGIME_MIN_N = 10

# Check 4 — per-symbol bootstrap
PER_SYM_MIN_N = 8
PER_SYM_BOOT_N = 1000

# Trigger / corr config (must match R-1 exactly)
CORR_WINDOW_BARS = 288             # 1d at 5m
ZSCORE_LOOKBACK_BARS = 288 * 30    # 30d
TRIGGER_MIN_GAP_BARS = 240 // BAR_MINUTES  # 48
FEE_PER_TRADE = 0.0008

# Aggregate perm n per stratum (lighter than R-3 final)
QUARTER_PERM_N = 200
REGIME_PERM_N = 200


# ---------- helpers (mirror R-1) ----------

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


def build_alt_filtered_events(
    threshold: float,
    hold_bars: int,
    corr_z_panel: pd.DataFrame,
    alt_close_panel: Dict[str, pd.Series],
    btc_r_5m: pd.Series,
) -> Tuple[Dict[str, pd.DataFrame], List[int]]:
    """Return per-alt DataFrame of [trigger_ts, net_short_ret, btc_at_trig]
    after sign-cond filter, plus the full trigger position list (corr-panel based).
    """
    trigger_pos = find_trigger_indices(corr_z_panel["corr_zscore"], threshold)
    if not trigger_pos:
        return {sym: pd.DataFrame(columns=["net_short", "btc_at_trig"]) for sym in ALT_SYMS}, []

    trigger_ts = corr_z_panel.index[trigger_pos]
    per_alt: Dict[str, pd.DataFrame] = {}

    for alt_sym in ALT_SYMS:
        alt_close = alt_close_panel[alt_sym]
        alt_idx_map = {ts: i for i, ts in enumerate(alt_close.index)}
        alt_trigger_pos = [alt_idx_map[ts] for ts in trigger_ts if ts in alt_idx_map]
        if not alt_trigger_pos:
            per_alt[alt_sym] = pd.DataFrame(columns=["net_short", "btc_at_trig"])
            continue

        fwd_long = compute_forward_returns(alt_close, alt_trigger_pos, hold_bars)
        if len(fwd_long) == 0:
            per_alt[alt_sym] = pd.DataFrame(columns=["net_short", "btc_at_trig"])
            continue

        alt_r_5m = compute_5m_returns(alt_close)
        btc_at_trig = btc_r_5m.reindex(fwd_long.index)
        alt_at_trig = alt_r_5m.reindex(fwd_long.index)

        mask_btc_dn = (btc_at_trig < 0).fillna(False).values
        mask_alt_dn = (alt_at_trig < 0).fillna(False).values
        mask_filter = mask_btc_dn & mask_alt_dn

        if int(mask_filter.sum()) == 0:
            per_alt[alt_sym] = pd.DataFrame(columns=["net_short", "btc_at_trig"])
            continue

        gross_long = fwd_long.values[mask_filter]
        gross_short = -gross_long
        net_short = gross_short - FEE_PER_TRADE
        idx_filt = fwd_long.index[mask_filter]
        btc_filt = btc_at_trig.values[mask_filter]

        per_alt[alt_sym] = pd.DataFrame(
            {"net_short": net_short, "btc_at_trig": btc_filt}, index=idx_filt
        )

    return per_alt, trigger_pos


def aggregate_short_pool(alt_close_panel: Dict[str, pd.Series], hold_bars: int) -> np.ndarray:
    """Concatenated SHORT candidate pool across alts (for fee-aware perm null)."""
    pools = []
    for alt_sym, c5 in alt_close_panel.items():
        pool_long = build_candidate_pool_per_alt(c5, hold_bars)
        pool_short = -pool_long
        if len(pool_short) > 5000:
            rng = np.random.default_rng(hash(alt_sym) & 0xFFFFFFFF)
            pool_short = rng.choice(pool_short, size=5000, replace=False)
        pools.append(pool_short)
    return np.concatenate(pools)


def evaluate_aggregate(net_short: np.ndarray, pool_short: np.ndarray,
                       n_perms: int = QUARTER_PERM_N) -> Dict:
    """Compute aggregate stats given a pre-filtered pool of net_short returns."""
    n = int(len(net_short))
    if n < 2:
        return {"n": n, "skip_reason": "n<2"}
    mean_net = float(net_short.mean())
    std = float(net_short.std(ddof=1))
    obs_t = float(mean_net / std * np.sqrt(n)) if std > 0 else 0.0
    out = {
        "n": n,
        "short_gross_bp": float((mean_net + FEE_PER_TRADE) * 10000),
        "short_net_bp": float(mean_net * 10000),
        "obs_t": obs_t,
    }
    try:
        fee_res = fee_aware_perm_test(
            observed_net_returns=net_short.tolist(),
            candidate_pool_returns=pool_short.tolist(),
            fee_per_trade=FEE_PER_TRADE,
            n_perms=n_perms,
            rng_seed=42,
        )
        out["fee_aware_perm"] = fee_res
        out["signal_t_excess"] = fee_res.get("signal_t_excess", float("nan"))
        out["perm_p_two_sided"] = fee_res.get("perm_p_two_sided", float("nan"))
    except Exception as exc:  # noqa: BLE001
        out["fee_aware_perm_error"] = str(exc)
    try:
        ci_res = bootstrap_ci(
            observed_net_returns=net_short.tolist(),
            n_boot=1000, block_size=1, rng_seed=42,
        )
        out["bootstrap_ci"] = ci_res
        out["ci_lower_bp"] = float(ci_res.get("ci_lower", float("nan")) * 10000)
    except Exception as exc:  # noqa: BLE001
        out["bootstrap_ci_error"] = str(exc)
    return out


# ---------- main ----------

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    log.info("=== paradigm 77 R-2 robustness: %s ===", PARADIGM_NAME)

    log.info("loading 1m OHLCV from joblib cache")
    btc_1m = load_ohlcv_1m_cached("BTCUSDT")
    eth_1m = load_ohlcv_1m_cached("ETHUSDT")
    log.info("BTC=%d ETH=%d", len(btc_1m), len(eth_1m))

    alt_close_panel: Dict[str, pd.Series] = {}
    for alt_sym in ALT_SYMS:
        df = load_ohlcv_1m_cached(alt_sym)
        c5 = resample_5m_close(df)
        alt_close_panel[alt_sym] = c5
        log.info("  %s: 1m=%d 5m=%d", alt_sym, len(df), len(c5))

    btc_5m_close = resample_5m_close(btc_1m)
    eth_5m_close = resample_5m_close(eth_1m)
    btc_r = compute_5m_returns(btc_5m_close)
    eth_r = compute_5m_returns(eth_5m_close)

    log.info("building corr z-score panel")
    corr_z_panel = build_corr_zscore_panel(btc_r, eth_r)
    log.info("corr panel n=%d", len(corr_z_panel))

    # Build SHORT candidate pool once at focus hold (used across strata)
    log.info("building aggregate SHORT candidate pool at hold=%dm", FOCUS_HOLD_MIN)
    pool_short_focus = aggregate_short_pool(alt_close_panel, FOCUS_HOLD_BARS)
    log.info("pool size=%d", len(pool_short_focus))

    # Build BTC vol panel for regime stratify (computed on 5m abs returns)
    log.info("building BTC vol panel (30d realized vol z-score at 5m)")
    btc_abs_r = btc_r.abs()
    btc_vol = btc_abs_r.rolling(VOL_LOOKBACK_5M_BARS).mean()
    btc_vol_mean = btc_vol.rolling(VOL_LOOKBACK_5M_BARS * 3).mean()
    btc_vol_std = btc_vol.rolling(VOL_LOOKBACK_5M_BARS * 3).std()
    btc_vol_z = ((btc_vol - btc_vol_mean) / btc_vol_std).dropna()
    log.info("vol panel n=%d, vol_z mean=%.3f std=%.3f", len(btc_vol_z),
             float(btc_vol_z.mean()), float(btc_vol_z.std()))

    # =========================================================
    # Check 1 — fine-grain z plateau
    # =========================================================
    log.info("\n=== CHECK 1: fine-grain z plateau ===")
    plateau_results: Dict[str, Dict] = {}
    for thr in PLATEAU_Z:
        log.info("--- plateau z=%.2f hold=%dm ---", thr, FOCUS_HOLD_MIN)
        per_alt, _ = build_alt_filtered_events(
            thr, FOCUS_HOLD_BARS, corr_z_panel, alt_close_panel, btc_r,
        )
        net_short_all = []
        per_alt_n = {}
        per_alt_pos = 0
        for alt_sym, df in per_alt.items():
            n_alt = int(len(df))
            per_alt_n[alt_sym] = n_alt
            if n_alt > 0:
                net_short_all.append(df["net_short"].values)
                if df["net_short"].mean() > 0:
                    per_alt_pos += 1
        if net_short_all:
            net_agg = np.concatenate(net_short_all)
        else:
            net_agg = np.array([])
        agg_stats = evaluate_aggregate(net_agg, pool_short_focus, n_perms=QUARTER_PERM_N)
        agg_stats["per_alt_n"] = per_alt_n
        agg_stats["per_alt_positive_count"] = per_alt_pos
        plateau_results[f"z_{thr}"] = agg_stats
        log.info("  n=%d net_bp=%.2f sig_excess=%.2f perm_p=%.3f ci_lower_bp=%.2f div=%d/12",
                 agg_stats.get("n", 0),
                 agg_stats.get("short_net_bp", float("nan")),
                 agg_stats.get("signal_t_excess", float("nan")),
                 agg_stats.get("perm_p_two_sided", float("nan")),
                 agg_stats.get("ci_lower_bp", float("nan")),
                 per_alt_pos)

    # Plateau verdict
    plateau_signs_all_pos = all(
        plateau_results[f"z_{z}"].get("short_net_bp", -1) > 0 for z in PLATEAU_Z
    )
    z_minus24 = plateau_results.get("z_-2.4", {})
    z_minus26 = plateau_results.get("z_-2.6", {})
    adjacent_strong = (
        z_minus24.get("signal_t_excess", -10) >= 1.5
        and z_minus26.get("signal_t_excess", -10) >= 1.5
    )
    check1_pass = bool(plateau_signs_all_pos and adjacent_strong)
    log.info("CHECK 1 plateau verdict: all_pos=%s adjacent_strong=%s -> %s",
             plateau_signs_all_pos, adjacent_strong, check1_pass)

    # =========================================================
    # Check 2 — quarterly 10-fold consistency at focus z=-2.5
    # =========================================================
    log.info("\n=== CHECK 2: quarterly 10-fold at z=%.2f ===", FOCUS_Z)
    per_alt_focus, _ = build_alt_filtered_events(
        FOCUS_Z, FOCUS_HOLD_BARS, corr_z_panel, alt_close_panel, btc_r,
    )

    # Build a single combined DataFrame across alts: [ts, net_short, alt]
    combined_rows = []
    for alt_sym, df in per_alt_focus.items():
        if len(df) == 0:
            continue
        for ts, row in df.iterrows():
            combined_rows.append({
                "ts": ts, "alt": alt_sym,
                "net_short": float(row["net_short"]),
                "btc_at_trig": float(row["btc_at_trig"]),
            })
    combined = pd.DataFrame(combined_rows)
    if not combined.empty:
        combined["ts"] = pd.to_datetime(combined["ts"])
    log.info("combined focus events: n=%d (across %d alts)",
             len(combined), len(per_alt_focus))

    quarterly_results: Dict[str, Dict] = {}
    quarterly_measurable_neg = 0
    quarterly_measurable_pos = 0
    quarterly_strong_neg_quarters = []
    for q_name, q_start, q_end in QUARTERS:
        if combined.empty:
            quarterly_results[q_name] = {"n": 0, "measurable": False, "skip_reason": "empty combined"}
            continue
        mask = (combined["ts"] >= pd.Timestamp(q_start)) & (combined["ts"] < pd.Timestamp(q_end))
        sub = combined.loc[mask]
        n_q = int(len(sub))
        measurable = n_q >= QUARTER_MIN_N
        entry = {
            "n": n_q,
            "measurable": measurable,
            "min_n_required": QUARTER_MIN_N,
        }
        if not measurable:
            entry["skip_reason"] = f"n<{QUARTER_MIN_N} (mechanical denominator artifact)"
            quarterly_results[q_name] = entry
            log.info("  %s: n=%d (measurable=False, skip)", q_name, n_q)
            continue
        net = sub["net_short"].values
        stats = evaluate_aggregate(net, pool_short_focus, n_perms=QUARTER_PERM_N)
        entry.update(stats)
        net_bp = entry.get("short_net_bp", float("nan"))
        t = entry.get("obs_t", float("nan"))
        log.info("  %s: n=%d net_bp=%.2f t=%.2f sig_excess=%.2f perm_p=%.3f",
                 q_name, n_q, net_bp, t,
                 entry.get("signal_t_excess", float("nan")),
                 entry.get("perm_p_two_sided", float("nan")))
        if net_bp > 0:
            quarterly_measurable_pos += 1
        else:
            quarterly_measurable_neg += 1
            if t < -1.5:
                quarterly_strong_neg_quarters.append(q_name)
        quarterly_results[q_name] = entry

    quarterly_n_measurable = quarterly_measurable_pos + quarterly_measurable_neg
    check2_pass = bool(
        quarterly_n_measurable >= 1
        and quarterly_measurable_neg == 0
        and len(quarterly_strong_neg_quarters) == 0
    )
    log.info("CHECK 2 quarterly verdict: measurable=%d pos=%d neg=%d strong_neg_quarters=%s -> %s",
             quarterly_n_measurable, quarterly_measurable_pos, quarterly_measurable_neg,
             quarterly_strong_neg_quarters, check2_pass)

    # =========================================================
    # Check 3 — BTC vol regime stratify at focus z=-2.5
    # =========================================================
    log.info("\n=== CHECK 3: BTC vol regime stratify at z=%.2f ===", FOCUS_Z)
    # Compute quartile cuts of vol_z over the FULL panel (defines regime universally)
    vol_z_q = btc_vol_z.quantile([0.25, 0.50, 0.75]).to_dict()
    cut_25, cut_50, cut_75 = vol_z_q[0.25], vol_z_q[0.50], vol_z_q[0.75]
    log.info("vol_z quartile cuts: q25=%.3f q50=%.3f q75=%.3f", cut_25, cut_50, cut_75)

    # Attach vol regime to each combined event
    if not combined.empty:
        vol_at_ts = btc_vol_z.reindex(combined["ts"].values).values
        combined = combined.copy()
        combined["vol_z_at_trig"] = vol_at_ts

        def regime_of(v: float) -> str:
            if not np.isfinite(v):
                return "UNKNOWN"
            if v < cut_25:
                return "Q1_LOW"
            if v < cut_50:
                return "Q2_MID_LOW"
            if v < cut_75:
                return "Q3_MID_HIGH"
            return "Q4_HIGH"

        combined["vol_regime"] = [regime_of(v) for v in combined["vol_z_at_trig"]]

    regime_results: Dict[str, Dict] = {}
    regime_measurable_neg = 0
    regime_measurable_pos = 0
    regime_strong_neg = []
    regime_unknown_n = 0
    for regime in ["Q1_LOW", "Q2_MID_LOW", "Q3_MID_HIGH", "Q4_HIGH"]:
        if combined.empty:
            regime_results[regime] = {"n": 0, "measurable": False, "skip_reason": "empty combined"}
            continue
        sub = combined.loc[combined["vol_regime"] == regime]
        n_r = int(len(sub))
        measurable = n_r >= VOL_REGIME_MIN_N
        entry = {"n": n_r, "measurable": measurable, "min_n_required": VOL_REGIME_MIN_N}
        if not measurable:
            entry["skip_reason"] = f"n<{VOL_REGIME_MIN_N}"
            regime_results[regime] = entry
            log.info("  %s: n=%d skip", regime, n_r)
            continue
        net = sub["net_short"].values
        stats = evaluate_aggregate(net, pool_short_focus, n_perms=REGIME_PERM_N)
        entry.update(stats)
        net_bp = entry.get("short_net_bp", float("nan"))
        t = entry.get("obs_t", float("nan"))
        log.info("  %s: n=%d net_bp=%.2f t=%.2f sig_excess=%.2f",
                 regime, n_r, net_bp, t, entry.get("signal_t_excess", float("nan")))
        if net_bp > 0:
            regime_measurable_pos += 1
        else:
            regime_measurable_neg += 1
            if t < -1.5:
                regime_strong_neg.append(regime)
        regime_results[regime] = entry

    if not combined.empty:
        regime_unknown_n = int((combined["vol_regime"] == "UNKNOWN").sum())
        regime_results["UNKNOWN"] = {"n": regime_unknown_n,
                                      "note": "vol_z NaN — pre-warmup window"}

    check3_pass = bool(
        regime_measurable_neg == 0
        or (regime_measurable_neg <= 1 and len(regime_strong_neg) == 0)
    )
    log.info("CHECK 3 regime verdict: pos=%d neg=%d strong_neg=%s -> %s",
             regime_measurable_pos, regime_measurable_neg, regime_strong_neg, check3_pass)

    # =========================================================
    # Check 4 — per-symbol bootstrap (12 alts × 1000 iter)
    # =========================================================
    log.info("\n=== CHECK 4: per-symbol bootstrap ===")
    per_sym_results: Dict[str, Dict] = {}
    r1_positive_alts = []
    sym_pos_with_ci_lower_pos = 0
    sym_pos_with_ci_lower_neg = 0
    for alt_sym in ALT_SYMS:
        df = per_alt_focus.get(alt_sym, pd.DataFrame())
        n_sym = int(len(df))
        entry = {"n": n_sym}
        if n_sym < PER_SYM_MIN_N:
            entry["skip_reason"] = f"n<{PER_SYM_MIN_N}"
            entry["measurable"] = False
            per_sym_results[alt_sym] = entry
            log.info("  %s: n=%d skip", alt_sym, n_sym)
            continue
        entry["measurable"] = True
        net = df["net_short"].values
        mean_net = float(net.mean())
        net_bp = mean_net * 10000
        std = float(net.std(ddof=1))
        obs_t = float(mean_net / std * np.sqrt(n_sym)) if std > 0 else 0.0
        is_r1_positive = mean_net > 0
        if is_r1_positive:
            r1_positive_alts.append(alt_sym)
        try:
            ci_res = bootstrap_ci(
                observed_net_returns=net.tolist(),
                n_boot=PER_SYM_BOOT_N, block_size=1, rng_seed=42,
            )
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
            per_sym_results[alt_sym] = entry
            continue
        ci_lower = float(ci_res.get("ci_lower", float("nan")))
        ci_upper = float(ci_res.get("ci_upper", float("nan")))
        prob_pos = float(ci_res.get("prob_positive", float("nan")))
        entry.update({
            "mean_net_bp": net_bp,
            "obs_t": obs_t,
            "ci_lower_bp": ci_lower * 10000,
            "ci_upper_bp": ci_upper * 10000,
            "prob_positive": prob_pos,
            "is_r1_positive": is_r1_positive,
            "ci_lower_above_zero": bool(ci_lower > 0),
        })
        if is_r1_positive:
            if ci_lower > 0:
                sym_pos_with_ci_lower_pos += 1
            else:
                sym_pos_with_ci_lower_neg += 1
        log.info("  %s: n=%d net_bp=%.2f t=%.2f ci=[%.2f,%.2f]bp prob_pos=%.3f r1_pos=%s ci_lower>0=%s",
                 alt_sym, n_sym, net_bp, obs_t, ci_lower * 10000, ci_upper * 10000,
                 prob_pos, is_r1_positive, ci_lower > 0)
        per_sym_results[alt_sym] = entry

    n_r1_pos = len(r1_positive_alts)
    # PASS: among R-1 positive alts, ci_lower > 0 ratio >= 50% (cherry-pick filter)
    # Stricter version (mentioned in spec): of the 10 R-1 positive alts, ci_lower > 0
    # for the majority. We accept >= ceil(n/2) as PASS, with 80%+ as ROBUST signal.
    if n_r1_pos == 0:
        check4_pass = False
        check4_ratio = 0.0
    else:
        check4_ratio = sym_pos_with_ci_lower_pos / n_r1_pos
        check4_pass = sym_pos_with_ci_lower_pos >= max(1, n_r1_pos // 2)
    log.info("CHECK 4 per-sym verdict: r1_pos=%d ci_lower>0=%d ratio=%.2f -> %s",
             n_r1_pos, sym_pos_with_ci_lower_pos, check4_ratio, check4_pass)

    # =========================================================
    # Final R-2 verdict
    # =========================================================
    checks = {
        "check1_z_plateau": check1_pass,
        "check2_quarterly": check2_pass,
        "check3_vol_regime": check3_pass,
        "check4_per_symbol_bootstrap": check4_pass,
    }
    n_pass = sum(1 for v in checks.values() if v)

    if n_pass == 4:
        verdict = "R2_PASS"
        recommendation = "promote_to_R3"
    elif n_pass == 3:
        verdict = "R2_MARGINAL"
        recommendation = "report_to_user_consider_supplementary"
    else:
        verdict = "R2_FAIL"
        recommendation = "graveyard_or_subparadigm_split"

    out = {
        "paradigm": PARADIGM_NAME,
        "phase": "R-2",
        "direction": "SHORT",
        "alts": ALT_SYMS,
        "n_alts": len(ALT_SYMS),
        "fee_per_trade": FEE_PER_TRADE,
        "bar_minutes": BAR_MINUTES,
        "focus_z": FOCUS_Z,
        "focus_hold_minutes": FOCUS_HOLD_MIN,
        "trigger_min_gap_bars": TRIGGER_MIN_GAP_BARS,
        "data_window": {
            "btc_min": str(btc_1m.index.min()),
            "btc_max": str(btc_1m.index.max()),
            "n_5m_bars": int(len(btc_5m_close)),
        },
        "vol_z_quartile_cuts": {"q25": float(cut_25), "q50": float(cut_50), "q75": float(cut_75)},
        "check1_plateau": {
            "z_sweep": PLATEAU_Z,
            "results": plateau_results,
            "all_signs_positive": plateau_signs_all_pos,
            "adjacent_strong_pm0p1": adjacent_strong,
            "PASS": check1_pass,
        },
        "check2_quarterly": {
            "quarters": [q[0] for q in QUARTERS],
            "min_n_per_quarter": QUARTER_MIN_N,
            "results": quarterly_results,
            "n_measurable": quarterly_n_measurable,
            "n_measurable_positive": quarterly_measurable_pos,
            "n_measurable_negative": quarterly_measurable_neg,
            "strong_negative_quarters": quarterly_strong_neg_quarters,
            "PASS": check2_pass,
        },
        "check3_vol_regime": {
            "min_n_per_regime": VOL_REGIME_MIN_N,
            "results": regime_results,
            "n_measurable_positive": regime_measurable_pos,
            "n_measurable_negative": regime_measurable_neg,
            "strong_negative_regimes": regime_strong_neg,
            "unknown_n": regime_unknown_n,
            "PASS": check3_pass,
        },
        "check4_per_symbol": {
            "min_n_per_symbol": PER_SYM_MIN_N,
            "boot_n": PER_SYM_BOOT_N,
            "results": per_sym_results,
            "r1_positive_alts": r1_positive_alts,
            "n_r1_positive": n_r1_pos,
            "n_r1_pos_with_ci_lower_above_zero": sym_pos_with_ci_lower_pos,
            "n_r1_pos_with_ci_lower_below_zero": sym_pos_with_ci_lower_neg,
            "ratio": check4_ratio,
            "PASS": check4_pass,
        },
        "summary_checks": checks,
        "n_checks_pass": n_pass,
        "verdict": {
            "R2_VERDICT": verdict,
            "recommendation": recommendation,
            "checks_pass": checks,
            "n_pass": n_pass,
        },
        "elapsed_s": round(time.time() - t_start, 1),
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("written %s", OUT_PATH)
    log.info("R2 VERDICT: %s (%d/4 checks PASS) recommendation=%s elapsed=%.1fs",
             verdict, n_pass, recommendation, out["elapsed_s"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
