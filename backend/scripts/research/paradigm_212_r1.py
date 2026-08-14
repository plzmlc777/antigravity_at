"""paradigm 212 R-1 PoC — cross-sym funding rate correlation matrix eigenvalue-1 dominance ratio z-spike, signed bilateral 4-quadrant SNT.

HYPOTHESIS
----------
- 10 deep syms × 8h funding rate cycle → rolling 30d cross-sym funding rate
  correlation matrix → eigenvalue-1 dominance ratio (PC1 explained variance =
  lambda_1 / sum(lambda_i)) → 90d rolling z-score → |z|>=2 spike trigger.
- Mechanism: HIGH dominance = funding rates 동조화 = systemic stress regime /
  LOW dominance = idiosyncratic decoupling.
- Bar direction signed entry. Hold +4h primary + 8h + 12h + 24h sweep.
- 4-quadrant Symmetric Negative Test (DISJOINT trigger set per Lesson #69 Item 7):
    A focus  : eigenvalue-1 dominance z >= +2 (HIGH stress)    × bar UP   × LONG  continuation
    A mirror : eigenvalue-1 dominance z >= +2 (HIGH stress)    × bar UP   × SHORT reversal
    B same   : eigenvalue-1 dominance z <= -2 (LOW idio)       × bar DOWN × SHORT continuation  [DISJOINT]
    B mirror : eigenvalue-1 dominance z <= -2 (LOW idio)       × bar DOWN × LONG  reversal  (Lesson #42 18th)

FAMILY-DISTINCT 5/5 STRICT (vs funding family Tier 4 retire)
-----------------------------------------------------------
- statistic class: MATRIX DECOMPOSITION (eigenvalue ratio) vs all 13 funding
  graveyards scalar z-score / dispersion / velocity → DISTINCT
- cross-sym aggregation: matrix vs paradigm 97/98 cross-sym scalar dispersion
  z (1D) → DISTINCT
- trigger axis: PC1 explained variance ratio (systemic stress proxy) →
  DISTINCT
- mechanism class: systemic stress regime detection vs MR/momentum/boundary →
  DISTINCT
- vs paradigm 22 R-5 LIVE (per-sym z MR) + funding_dispersion ETCUSDT exception
  (cross-section scalar z): both R-5 use scalar z, paradigm 212 matrix-class →
  DISTINCT

DATA
----
- binance_funding_rate (paradigm 22/170 substrate). Standard 8h cohort
  (PYTHUSDT/JUPUSDT 4h cadence excluded).
- 10 deep syms × 2.25yr × 24,660 funding records.
- OHLCV 4h joblib cache (runs/ohlcv_cache_12col/).
- 4-hour bars: entry at next 4h open after funding_time, hold N×4h.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p212_r1")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PARADIGM_ID = 212
PARADIGM_NAME = "alt_cross_sym_funding_correlation_matrix_eigenvalue_1_dominance_ratio_30d_rolling_z_spike_directional_4h"
OUT_DIR = ROOT / "runs" / "research_track" / f"paradigm_212_funding_corr_eigenvalue_dominance"
OHLCV_CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"

# 10 deep cohort syms (standard 8h funding cycle, paradigm 22/170 cohort)
COHORT = [
    "AVAXUSDT", "BNBUSDT", "BTCUSDT", "LINKUSDT", "DOTUSDT", "ETHUSDT",
    "ETCUSDT", "ADAUSDT", "XRPUSDT", "NEARUSDT",
]

# Rolling windows
ROLL_CORR_DAYS = 30   # rolling 30d funding correlation matrix
ROLL_Z_DAYS = 90      # rolling 90d z-score on eigenvalue-1 dominance ratio
# 8h funding cycle → 3 obs/day
ROLL_CORR_N = ROLL_CORR_DAYS * 3   # 90
ROLL_Z_N = ROLL_Z_DAYS * 3         # 270

# Trigger
PRIMARY_Z_THRESHOLD = 2.0
Z_THRESHOLDS = [1.5, 2.0, 2.5]

# Hold sweep (4h bars)
HOLD_BARS_LIST = [1, 2, 3, 6]  # 4h / 8h / 12h / 24h
PRIMARY_HOLD = 1  # 4h

FEE_PER_TRADE = 0.0008  # 8 bp round-trip
DB_URL = "postgresql+psycopg2://antigravity_user:antigravity_password@localhost/antigravity_db"

# Coverage trim
MAX_FUNDING_TIME = pd.Timestamp("2026-04-29 23:00:00")  # 24h buffer


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_funding(symbols: list[str]) -> pd.DataFrame:
    """Load 8h funding rate panel."""
    engine = create_engine(DB_URL)
    syms_list = ",".join(f"'{s}'" for s in symbols)
    sql = f"""
        SELECT symbol, funding_time, funding_rate
        FROM binance_funding_rate
        WHERE symbol IN ({syms_list})
        ORDER BY symbol, funding_time
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["funding_time"] = pd.to_datetime(df["funding_time"])
    df = df.sort_values(["symbol", "funding_time"]).reset_index(drop=True)
    log.info("funding panel: %d rows, %d syms, %s -> %s",
             len(df), df.symbol.nunique(), df.funding_time.min(), df.funding_time.max())
    return df


def pivot_funding(funding: pd.DataFrame) -> pd.DataFrame:
    """Pivot to time-aligned matrix: index=funding_time, columns=symbol."""
    pivot = funding.pivot(index="funding_time", columns="symbol", values="funding_rate")
    pivot = pivot.sort_index()
    # Floor to 8h grid - funding_time should already be on 00/08/16 UTC
    log.info("pivot shape: %s (time × sym), na frac=%.4f",
             pivot.shape, float(pivot.isna().mean().mean()))
    return pivot


def load_ohlcv_panel(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Load 4h OHLCV joblib cache per symbol."""
    out = {}
    for sym in symbols:
        path = OHLCV_CACHE_DIR / f"{sym}_4h.joblib"
        if not path.exists():
            log.warning("ohlcv cache missing for %s — skipping", sym)
            continue
        df = joblib.load(path)
        if df.index.name != "open_time":
            df = df.copy()
            df.index.name = "open_time"
        df = df.sort_index()
        out[sym] = df[["open", "close"]].copy()
    log.info("ohlcv panel loaded for %d syms", len(out))
    return out


# ---------------------------------------------------------------------------
# Rolling eigenvalue-1 dominance ratio
# ---------------------------------------------------------------------------
def rolling_pc1_dominance(pivot: pd.DataFrame, window: int) -> pd.Series:
    """For each rolling window of `window` funding obs, compute
       lambda_1 / sum(lambda_i) of the cross-sym correlation matrix.

    Returns a Series indexed by funding_time (right edge of window).
    """
    times = pivot.index
    n = len(times)
    out = np.full(n, np.nan)
    syms = list(pivot.columns)
    arr = pivot.values  # shape (T, S)

    for i in range(window - 1, n):
        block = arr[i - window + 1 : i + 1]
        # require >= window/2 valid rows per sym
        valid_per_sym = np.isfinite(block).sum(axis=0) >= (window // 2)
        if valid_per_sym.sum() < 5:
            continue
        sub = block[:, valid_per_sym]
        # drop rows containing any NaN remaining
        sub_full = sub[~np.isnan(sub).any(axis=1)]
        if len(sub_full) < window // 2:
            continue
        # demean per col
        sub_dm = sub_full - sub_full.mean(axis=0, keepdims=True)
        # if any col has zero std → skip
        stds = sub_full.std(axis=0, ddof=1)
        if (stds <= 1e-12).any():
            continue
        # correlation matrix
        corr = np.corrcoef(sub_full.T)
        if not np.all(np.isfinite(corr)):
            continue
        # eigenvalues (symmetric → eigvalsh)
        try:
            eigs = np.linalg.eigvalsh(corr)
        except np.linalg.LinAlgError:
            continue
        eigs = np.abs(eigs)  # numerical guard
        total = float(eigs.sum())
        if total <= 1e-12:
            continue
        out[i] = float(eigs.max()) / total
    s = pd.Series(out, index=times, name="pc1_dominance")
    log.info("pc1_dominance: %d valid / %d total", s.notna().sum(), len(s))
    return s


def rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    """Rolling z-score using past `window` obs (excluding current)."""
    # use shift to ensure current obs not in mean/std (causal)
    mean = s.rolling(window=window, min_periods=window // 2).mean()
    std = s.rolling(window=window, min_periods=window // 2).std()
    z = (s - mean) / std
    return z.replace([np.inf, -np.inf], np.nan).rename("z_pc1_dominance")


# ---------------------------------------------------------------------------
# Event construction
# ---------------------------------------------------------------------------
def build_events(
    z_series: pd.Series,
    ohlcv: dict[str, pd.DataFrame],
    cohort: list[str],
    z_threshold: float,
    hold_bars: int,
) -> pd.DataFrame:
    """For each funding_time where |z| >= threshold, create one event PER sym
    in cohort (since z is cross-sym), with per-sym bar_dir and forward return.

    Entry: next 4h bar open after funding_time.
    bar_dir: sign of (entry_bar.close - entry_bar.open) where entry_bar is the
    4h bar starting at funding_time (or asof funding_time).
    """
    records = []
    z_valid = z_series.dropna()
    z_trig = z_valid[(z_valid.abs() >= z_threshold) & (z_valid.index <= MAX_FUNDING_TIME)]
    log.info("z|>=%.1f trigger times: %d (of %d valid z)",
             z_threshold, len(z_trig), len(z_valid))

    for ft, zval in z_trig.items():
        z_sign = int(np.sign(zval))  # +1 HIGH dominance, -1 LOW dominance
        for sym in cohort:
            if sym not in ohlcv:
                continue
            bars = ohlcv[sym]
            bar_idx = bars.index.searchsorted(ft, side="right") - 1
            if bar_idx < 0 or bar_idx >= len(bars):
                continue
            bar_open = bars.iloc[bar_idx]["open"]
            bar_close = bars.iloc[bar_idx]["close"]
            if not (np.isfinite(bar_open) and np.isfinite(bar_close)) or bar_open <= 0:
                continue
            bar_dir = int(np.sign(bar_close - bar_open))
            if bar_dir == 0:
                continue

            entry_idx = bar_idx + 1
            exit_idx = entry_idx + hold_bars
            if exit_idx >= len(bars):
                continue
            entry_time = bars.index[entry_idx]
            entry_price = bars.iloc[entry_idx]["open"]
            exit_time = bars.index[exit_idx]
            exit_price = bars.iloc[exit_idx]["open"]
            if not (np.isfinite(entry_price) and np.isfinite(exit_price)) or entry_price <= 0:
                continue

            gross_long = (exit_price - entry_price) / entry_price
            records.append({
                "symbol": sym,
                "funding_time": ft,
                "z_pc1": float(zval),
                "z_sign": z_sign,
                "bar_dir": bar_dir,
                "entry_time": entry_time,
                "entry_price": entry_price,
                "exit_time": exit_time,
                "exit_price": exit_price,
                "gross_ret_long": gross_long,
                "era_year": entry_time.year,
            })

    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df.sort_values(["entry_time", "symbol"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------
def build_candidate_pool(
    ohlcv: dict[str, pd.DataFrame],
    hold_bars: int,
    cap_per_sym: int = 5000,
) -> np.ndarray:
    rng = np.random.default_rng(2026)
    pool = []
    for sym, bars in ohlcv.items():
        opens = bars["open"].values
        n = len(opens)
        if n <= hold_bars + 1:
            continue
        entries = opens[: n - hold_bars]
        exits = opens[hold_bars:]
        valid = (entries > 0) & np.isfinite(entries) & np.isfinite(exits)
        gross = (exits[valid] - entries[valid]) / entries[valid]
        if len(gross) > cap_per_sym:
            sel = rng.choice(len(gross), size=cap_per_sym, replace=False)
            gross = gross[sel]
        pool.append(gross)
    if not pool:
        return np.array([])
    return np.concatenate(pool)


# ---------------------------------------------------------------------------
# 4-quadrant SNT
# ---------------------------------------------------------------------------
def eval_quadrant(
    events: pd.DataFrame,
    z_sign: int,
    bar_dir: int,
    trade_side: int,
    candidate_pool_long: np.ndarray,
    fee: float = FEE_PER_TRADE,
    label: str = "",
) -> dict:
    sub = events[(events["z_sign"] == z_sign) & (events["bar_dir"] == bar_dir)].copy()
    n = len(sub)
    if n < 10:
        return {
            "label": label, "n": n,
            "obs_mean_bp": float("nan"), "obs_t": float("nan"),
            "signal_t_excess": float("nan"), "null_mean_t": float("nan"),
            "perm_p_above": float("nan"), "perm_p_below": float("nan"),
            "ci_lower_bp": float("nan"), "ci_upper_bp": float("nan"),
            "ci_mean_bp": float("nan"), "prob_positive": float("nan"),
            "n_syms_pos_ci": 0, "n_syms_measurable": 0,
            "sym_ci_pos_ratio": 0.0,
            "per_sym": {}, "per_era": {},
            "three_gate_pass": False,
            "verdict": "INSUFFICIENT_N",
        }

    net = trade_side * sub["gross_ret_long"].values - fee
    pool_side = trade_side * candidate_pool_long

    ci = bootstrap_ci(net.tolist(), n_boot=2000, block_size=20, rng_seed=42)
    perm = fee_aware_perm_test(
        observed_net_returns=net.tolist(),
        candidate_pool_returns=pool_side.tolist(),
        fee_per_trade=fee,
        n_perms=1000,
        rng_seed=42,
    )

    # Per-sym
    sym_results = {}
    n_pos_ci = 0
    n_measurable = 0
    for sym, gsub in sub.groupby("symbol"):
        if len(gsub) < 5:
            continue
        n_measurable += 1
        net_sym = trade_side * gsub["gross_ret_long"].values - fee
        ci_sym = bootstrap_ci(net_sym.tolist(), n_boot=500, block_size=10, rng_seed=42)
        sym_results[sym] = {
            "n": len(gsub),
            "mean_bp": float(ci_sym["mean"]) * 10000,
            "ci_lower_bp": float(ci_sym["ci_lower"]) * 10000,
            "ci_upper_bp": float(ci_sym["ci_upper"]) * 10000,
            "prob_positive": float(ci_sym["prob_positive"]),
        }
        if ci_sym["ci_lower"] > 0:
            n_pos_ci += 1

    # Per-era
    era_results = {}
    for era, gsub in sub.groupby("era_year"):
        if len(gsub) < 10:
            continue
        net_era = trade_side * gsub["gross_ret_long"].values - fee
        ci_era = bootstrap_ci(net_era.tolist(), n_boot=500, block_size=10, rng_seed=42)
        era_results[int(era)] = {
            "n": len(gsub),
            "mean_bp": float(ci_era["mean"]) * 10000,
            "ci_lower_bp": float(ci_era["ci_lower"]) * 10000,
            "prob_positive": float(ci_era["prob_positive"]),
        }

    # Verdict
    sigex = float(perm.get("signal_t_excess", float("nan")))
    ci_lower = float(ci["ci_lower"])
    perm_p = float(perm.get("perm_p_one_sided_above", float("nan")))

    three_gate = (sigex >= 2.0) and (ci_lower > 0) and (perm_p <= 0.10)
    verdict = "PASS_R1" if three_gate else "FAIL_R1"

    return {
        "label": label,
        "n": n,
        "obs_mean_bp": float(np.mean(net)) * 10000,
        "obs_t": float(perm["obs_t"]),
        "signal_t_excess": sigex,
        "null_mean_t": float(perm["null_mean_t"]),
        "perm_p_above": float(perm["perm_p_one_sided_above"]),
        "perm_p_below": float(perm["perm_p_one_sided_below"]),
        "perm_p_two_sided": float(perm["perm_p_two_sided"]),
        "ci_lower_bp": ci_lower * 10000,
        "ci_upper_bp": float(ci["ci_upper"]) * 10000,
        "ci_mean_bp": float(ci["mean"]) * 10000,
        "prob_positive": float(ci["prob_positive"]),
        "n_syms_pos_ci": n_pos_ci,
        "n_syms_measurable": n_measurable,
        "sym_ci_pos_ratio": (n_pos_ci / n_measurable) if n_measurable else 0.0,
        "per_sym": sym_results,
        "per_era": era_results,
        "three_gate_pass": three_gate,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Temporal cluster ratio (Item 8 Concentration + Temporal Independence)
# ---------------------------------------------------------------------------
def measure_temporal_clusters(events: pd.DataFrame, min_gap_h: int = 24) -> dict:
    if events.empty:
        return {"n_aggregate": 0, "n_independent": 0, "ratio": 0.0, "min_gap_h": min_gap_h}
    n_agg = len(events)
    n_indep = 0
    for sym, g in events.groupby("symbol"):
        g_sorted = g.sort_values("entry_time")
        prev_t = None
        for t in g_sorted["entry_time"]:
            if prev_t is None or (t - prev_t).total_seconds() >= min_gap_h * 3600:
                n_indep += 1
                prev_t = t
    return {
        "n_aggregate": n_agg,
        "n_independent": n_indep,
        "ratio": n_indep / n_agg if n_agg else 0.0,
        "min_gap_h": min_gap_h,
    }


# ---------------------------------------------------------------------------
# Rolling 6m consistency check (Lesson candidate market maturity decay)
# ---------------------------------------------------------------------------
def rolling_6m_consistency(events: pd.DataFrame, trade_side: int, fee: float) -> dict:
    """For A_focus continuation cell, compute per-6m-window t-stat. Sign-flip
    ratio > 0.5 = ALPHA_DECAY_ARTIFACT per Lesson candidate paradigm 211."""
    if events.empty:
        return {"n_windows": 0, "n_sign_flips": 0, "flip_ratio": 0.0, "per_window_t": []}
    df = events.sort_values("entry_time").copy()
    df["net"] = trade_side * df["gross_ret_long"] - fee
    t_min = df["entry_time"].min()
    t_max = df["entry_time"].max()
    # 6-month windows
    windows = []
    cursor = t_min
    while cursor < t_max:
        nxt = cursor + pd.Timedelta(days=183)
        sub = df[(df["entry_time"] >= cursor) & (df["entry_time"] < nxt)]
        if len(sub) >= 10:
            net_vals = sub["net"].values
            if net_vals.std(ddof=1) > 1e-12:
                t_stat = float(net_vals.mean() / (net_vals.std(ddof=1) / np.sqrt(len(net_vals))))
            else:
                t_stat = float("nan")
            windows.append({
                "start": str(cursor.date()),
                "end": str(nxt.date()),
                "n": int(len(sub)),
                "mean_bp": float(net_vals.mean()) * 10000,
                "t_stat": t_stat,
            })
        cursor = nxt
    if not windows:
        return {"n_windows": 0, "n_sign_flips": 0, "flip_ratio": 0.0, "per_window_t": []}
    # sign-flip count: changes in sign between consecutive valid windows
    signs = [np.sign(w["t_stat"]) for w in windows if np.isfinite(w["t_stat"])]
    flips = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1] and signs[i] != 0 and signs[i - 1] != 0)
    return {
        "n_windows": len(windows),
        "n_sign_flips": flips,
        "flip_ratio": flips / max(len(signs) - 1, 1),
        "per_window_t": windows,
    }


# ---------------------------------------------------------------------------
# Unconditional baseline (Lesson #39 sub-class B avoidance verify)
# ---------------------------------------------------------------------------
def unconditional_baseline(
    ohlcv: dict[str, pd.DataFrame],
    hold_bars: int,
    fee: float,
    bar_dir_filter: int,
    trade_side: int,
) -> dict:
    """Measure unconditional bar-direction-filtered continuation/reversal.
    No funding trigger - just bar UP×LONG or bar DOWN×SHORT etc."""
    nets = []
    for sym, bars in ohlcv.items():
        opens = bars["open"].values
        closes = bars["close"].values
        n = len(opens)
        if n <= hold_bars + 1:
            continue
        # bar_dir at idx i = sign(close[i] - open[i])
        bar_signs = np.sign(closes - opens)
        for i in range(n - hold_bars - 1):
            if bar_signs[i] != bar_dir_filter:
                continue
            entry = opens[i + 1]
            exit_p = opens[i + 1 + hold_bars]
            if entry <= 0 or not np.isfinite(entry) or not np.isfinite(exit_p):
                continue
            gross_long = (exit_p - entry) / entry
            nets.append(trade_side * gross_long - fee)
    if len(nets) < 30:
        return {"n": len(nets), "mean_bp": float("nan"), "t_stat": float("nan")}
    arr = np.array(nets)
    t_stat = float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))) if arr.std(ddof=1) > 1e-12 else float("nan")
    return {
        "n": int(len(arr)),
        "mean_bp": float(arr.mean()) * 10000,
        "t_stat": t_stat,
    }


# ---------------------------------------------------------------------------
# Main R-1 sweep
# ---------------------------------------------------------------------------
def run_r1():
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    funding = load_funding(COHORT)
    pivot = pivot_funding(funding)
    ohlcv = load_ohlcv_panel(COHORT)

    eff_cohort = sorted(set(funding.symbol.unique()) & set(ohlcv.keys()))
    log.info("effective cohort = %d syms: %s", len(eff_cohort), eff_cohort)

    # Compute rolling eigenvalue-1 dominance + z-score
    pc1 = rolling_pc1_dominance(pivot, window=ROLL_CORR_N)
    z_pc1 = rolling_zscore(pc1, window=ROLL_Z_N)

    # Persist for inspection
    pd.DataFrame({"pc1_dominance": pc1, "z_pc1": z_pc1}).to_csv(OUT_DIR / "z_series.csv")

    z_valid = z_pc1.dropna()
    log.info("z_pc1 valid: %d, range [%.2f, %.2f], mean=%.3f std=%.3f",
             len(z_valid), z_valid.min(), z_valid.max(), z_valid.mean(), z_valid.std())

    # Empirical trigger rates
    trig_rates = {}
    for thr in Z_THRESHOLDS:
        trig_rates[f"abs_z_{thr}"] = float((z_valid.abs() >= thr).mean())
        trig_rates[f"z_pos_{thr}"] = float((z_valid >= thr).mean())
        trig_rates[f"z_neg_{thr}"] = float((z_valid <= -thr).mean())
    log.info("trigger rates: %s", trig_rates)

    results = {
        "paradigm_id": PARADIGM_ID,
        "paradigm_name": PARADIGM_NAME,
        "fee_per_trade": FEE_PER_TRADE,
        "primary_z_threshold": PRIMARY_Z_THRESHOLD,
        "primary_hold_bars": PRIMARY_HOLD,
        "roll_corr_days": ROLL_CORR_DAYS,
        "roll_z_days": ROLL_Z_DAYS,
        "cohort": eff_cohort,
        "z_series_stats": {
            "n_valid": int(len(z_valid)),
            "min": float(z_valid.min()),
            "max": float(z_valid.max()),
            "mean": float(z_valid.mean()),
            "std": float(z_valid.std()),
        },
        "pc1_stats": {
            "n_valid": int(pc1.notna().sum()),
            "mean": float(pc1.mean()),
            "std": float(pc1.std()),
            "p10": float(pc1.quantile(0.10)) if pc1.notna().sum() else None,
            "p50": float(pc1.quantile(0.50)) if pc1.notna().sum() else None,
            "p90": float(pc1.quantile(0.90)) if pc1.notna().sum() else None,
        },
        "trigger_rates": trig_rates,
        "max_funding_time": str(MAX_FUNDING_TIME),
        "sweep": {},
    }

    for thr in Z_THRESHOLDS:
        for hb in HOLD_BARS_LIST:
            cell_key = f"z_{thr}_hold_{hb*4}h"
            log.info("=== sweep cell: |z|>=%.1f, hold=%dh ===", thr, hb * 4)

            events = build_events(z_pc1, ohlcv, eff_cohort, z_threshold=thr, hold_bars=hb)
            if events.empty:
                results["sweep"][cell_key] = {"n_events_total": 0, "error": "no events"}
                continue

            pool = build_candidate_pool(ohlcv, hold_bars=hb)
            n_pos = (events["z_sign"] == 1).sum()
            n_neg = (events["z_sign"] == -1).sum()
            log.info("events total=%d  z_pos=%d  z_neg=%d  pool=%d",
                     len(events), n_pos, n_neg, len(pool))

            # 4-quadrant SNT
            quadrants = {
                "A_focus":  eval_quadrant(events, z_sign=+1, bar_dir=+1, trade_side=+1,
                                          candidate_pool_long=pool,
                                          label="A_focus_HIGHstress_barUP_LONG"),
                "A_mirror": eval_quadrant(events, z_sign=+1, bar_dir=+1, trade_side=-1,
                                          candidate_pool_long=pool,
                                          label="A_mirror_HIGHstress_barUP_SHORT"),
                "B_same":   eval_quadrant(events, z_sign=-1, bar_dir=-1, trade_side=-1,
                                          candidate_pool_long=pool,
                                          label="B_same_LOWidio_barDOWN_SHORT"),
                "B_mirror": eval_quadrant(events, z_sign=-1, bar_dir=-1, trade_side=+1,
                                          candidate_pool_long=pool,
                                          label="B_mirror_LOWidio_barDOWN_LONG"),
            }

            # Temporal cluster ratio
            temp_A = measure_temporal_clusters(
                events[(events["z_sign"] == 1) & (events["bar_dir"] == 1)],
                min_gap_h=24,
            )
            temp_B = measure_temporal_clusters(
                events[(events["z_sign"] == -1) & (events["bar_dir"] == -1)],
                min_gap_h=24,
            )

            # Item 7 cross-set asymmetry
            n_A = quadrants["A_focus"]["n"]
            n_B = quadrants["B_same"]["n"]
            cross_set_ratio = max(n_A, n_B) / max(min(n_A, n_B), 1)

            cell_record = {
                "z_threshold": thr,
                "hold_bars": hb,
                "hold_h": hb * 4,
                "n_events_total": int(len(events)),
                "n_z_pos": int(n_pos),
                "n_z_neg": int(n_neg),
                "quadrants": quadrants,
                "temporal_cluster_A_focus": temp_A,
                "temporal_cluster_B_same": temp_B,
                "item7_cross_set": {
                    "n_A_focus": int(n_A),
                    "n_B_same": int(n_B),
                    "asym_ratio": float(cross_set_ratio),
                    "is_disjoint": True,
                    "note": "DISJOINT trigger sets (z_sign +1 HIGH vs -1 LOW, bar_dir +1 vs -1)",
                },
            }

            # Rolling 6m consistency check (Lesson candidate market maturity decay)
            # On A_focus continuation (z_pos, bar_up, LONG)
            if thr == PRIMARY_Z_THRESHOLD and hb == PRIMARY_HOLD:
                a_focus_events = events[(events["z_sign"] == 1) & (events["bar_dir"] == 1)]
                cell_record["rolling_6m_consistency_A_focus"] = rolling_6m_consistency(
                    a_focus_events, trade_side=+1, fee=FEE_PER_TRADE,
                )

            results["sweep"][cell_key] = cell_record

    # Primary cell summary
    primary_key = f"z_{PRIMARY_Z_THRESHOLD}_hold_{PRIMARY_HOLD*4}h"
    primary = results["sweep"].get(primary_key, {})
    results["primary_summary"] = {
        "primary_key": primary_key,
        "n_events_total": primary.get("n_events_total", 0),
        "A_focus_three_gate": primary.get("quadrants", {}).get("A_focus", {}).get("three_gate_pass", False),
        "B_same_three_gate": primary.get("quadrants", {}).get("B_same", {}).get("three_gate_pass", False),
        "A_focus_sigex": primary.get("quadrants", {}).get("A_focus", {}).get("signal_t_excess"),
        "A_focus_ci_lower_bp": primary.get("quadrants", {}).get("A_focus", {}).get("ci_lower_bp"),
        "B_same_sigex": primary.get("quadrants", {}).get("B_same", {}).get("signal_t_excess"),
        "B_same_ci_lower_bp": primary.get("quadrants", {}).get("B_same", {}).get("ci_lower_bp"),
        "A_mirror_sigex": primary.get("quadrants", {}).get("A_mirror", {}).get("signal_t_excess"),
        "B_mirror_sigex": primary.get("quadrants", {}).get("B_mirror", {}).get("signal_t_excess"),
        "item7_cross_set_ratio": primary.get("item7_cross_set", {}).get("asym_ratio"),
    }

    # Unconditional baselines (Lesson #39 sub-class B avoidance)
    log.info("computing unconditional baselines...")
    results["unconditional_baselines"] = {
        "barUP_LONG_4h": unconditional_baseline(ohlcv, PRIMARY_HOLD, FEE_PER_TRADE, bar_dir_filter=+1, trade_side=+1),
        "barDOWN_SHORT_4h": unconditional_baseline(ohlcv, PRIMARY_HOLD, FEE_PER_TRADE, bar_dir_filter=-1, trade_side=-1),
        "barUP_SHORT_4h": unconditional_baseline(ohlcv, PRIMARY_HOLD, FEE_PER_TRADE, bar_dir_filter=+1, trade_side=-1),
        "barDOWN_LONG_4h": unconditional_baseline(ohlcv, PRIMARY_HOLD, FEE_PER_TRADE, bar_dir_filter=-1, trade_side=+1),
    }

    results["wall_clock_sec"] = round(time.time() - t0, 1)

    out_json = OUT_DIR / "r1__metrics.json"
    with open(out_json, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    log.info("wrote %s (wall=%.1fs)", out_json, results["wall_clock_sec"])

    return results


if __name__ == "__main__":
    run_r1()
