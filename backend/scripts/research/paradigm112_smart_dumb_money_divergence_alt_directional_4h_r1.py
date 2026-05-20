"""Paradigm 112 — smart_dumb_money_divergence_alt_directional_4h R-1 PoC

Hypothesis
----------
Two LSR (long/short ratio) sources exist in `binance_positioning_metric` table:
  - `top_long_short_position` (whale / large-position long_pos / total_pos, size-weighted)
  - `global_long_short_account` (retail account count long/total, headcount)

Mechanism: when **smart money (top_position_LSR) is bullishly positioned
extreme** (percentile_rank ≥ 0.95 over rolling 30-day window) AND simultaneously
**dumb money (global_account_LSR) is bearishly positioned extreme**
(percentile_rank ≤ 0.05), the divergence (gap > 0.85, smart > dumb) implies
**LONG continuation** for next 4h ("smart is right, dumb is wrong").

Mirror: top_lsr_pr ≤ 0.05 AND global_lsr_pr ≥ 0.95 AND gap < -0.85 →
**SHORT continuation**.

4-quadrant Symmetric Negative Test per Lesson #19:
  - A_focus: smart_HIGH + dumb_LOW → LONG (mechanism direction)
  - A_mirror: smart_HIGH + dumb_LOW → SHORT (wrong direction)
  - B_same_sign: smart_LOW + dumb_HIGH → SHORT (mirror-mechanism direction)
  - B_mirror: smart_LOW + dumb_HIGH → LONG (wrong direction)

Lesson #21 axis-alone diagnostic (mandatory for joint-trigger):
  - top_lsr_pr ≥ 0.95 alone → LONG (single axis)
  - global_lsr_pr ≤ 0.05 alone → LONG (single axis)
  If both individually FAIL but conjunction PASSES, dual conjunction is
  synthesizing. If either individually carries the signal, Lesson #21 invoked.

Novelty self-check (3/5 NOVEL ex ante)
- Statistic: dual percentile rank cross-source divergence (NOVEL — two distinct
  metric_type tables, gap-based; paradigm 23/72 TBS used single axis)
- Universe: 14 alts (NOT NOVEL — paradigm 69/110 cohort)
- Frame: 5m positioning × 4h hold (NOT NOVEL — paradigm 80/83 territory)
- Mechanism: smart-dumb DIVERGENCE class (NOVEL — cross-source disagreement
  classifier; distinct from §3-G LSR single-axis family)
- Trigger: dual percentile-rank conjunction with sign + gap threshold (NOVEL)

Substrate: binance_positioning_metric — both metric_types present 5m
granularity, 14 syms, ~35 days (2026-04-05 .. 2026-05-10).

Lesson #30 data window ratio
- Available window: 35 days (DB positioning_metric backfill)
- Full archive available: ~24 months (binance.vision archive)
- ratio = 35/720 ≈ 4.9% < 30% threshold
- **Verdict is ADVISORY-ONLY per [[feedback_lesson_30_short_data_verdict]]**
- Full-window re-run mandatory for production conclusion

R-0 prescreens: Lessons 11/19/21/28/30/34
R-1 body: 4-quadrant SNT + axis-alone single-axis diagnostic + Concentration
Gate + Life-changing 4-dim layer + fee_aware_perm + bootstrap CI.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

PARADIGM_NAME = "smart_dumb_money_divergence_alt_directional_4h"
PARADIGM_NUMBER = 112

OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r1__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p112_r1")

# 14 alts with positioning data + OHLCV 1m available
ALTS = [
    "SOLUSDT", "HBARUSDT", "AXSUSDT", "DOGEUSDT", "UNIUSDT", "PYTHUSDT",
    "TONUSDT", "ETCUSDT", "JUPUSDT", "COMPUSDT", "WLDUSDT", "LDOUSDT",
    "AVAXUSDT", "LINKUSDT",
]

FEE_PER_TRADE = 0.0008  # 16bp round-trip
ROLLING_30D_5M_BARS = 288 * 30  # 8640 5-min bars

PRIMARY_LOW = 0.05
PRIMARY_HIGH = 0.95
GAP_THRESHOLD = 0.85  # |top_pr - global_pr| > 0.85

PRIMARY_HOLD_BARS = 48  # 48 × 5m = 4h
HOLD_SWEEP_BARS = [12, 24, 48, 96]  # 60m, 120m, 240m, 480m
DECIMATION_GAP = PRIMARY_HOLD_BARS  # ≥ 4h gap between consecutive trades per sym


def load_positioning(sym: str, metric_type: str) -> pd.Series:
    """Load 5m positioning ratio series for given sym + metric_type."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT timestamp, ratio FROM binance_positioning_metric "
                "WHERE symbol=:s AND metric_type=:mt AND period='5m' "
                "ORDER BY timestamp"
            ),
            {"s": sym, "mt": metric_type},
        ).fetchall()
    finally:
        db.close()
    if not rows:
        return pd.Series(dtype=float, name=metric_type)
    df = pd.DataFrame(rows, columns=["ts", "ratio"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["ratio"] = pd.to_numeric(df["ratio"], errors="coerce")
    s = df.set_index("ts")["ratio"].sort_index()
    s = s[~s.index.duplicated(keep="first")]
    s.name = metric_type
    return s


def load_ohlcv_5m(sym: str, ts_min: pd.Timestamp, ts_max: pd.Timestamp) -> pd.Series:
    """Load 1m OHLCV close, resample to 5m close, return series in [ts_min, ts_max]."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT timestamp, close FROM ohlcv "
                "WHERE symbol=:s AND time_frame='1m' "
                "AND timestamp >= :tmin AND timestamp <= :tmax "
                "ORDER BY timestamp"
            ),
            {"s": sym, "tmin": ts_min - pd.Timedelta(hours=1),
             "tmax": ts_max + pd.Timedelta(hours=10)},
        ).fetchall()
    finally:
        db.close()
    if not rows:
        return pd.Series(dtype=float, name=sym)
    df = pd.DataFrame(rows, columns=["ts", "close"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.set_index("ts").sort_index()
    # Resample to 5m (right-closed-and-labeled to match positioning_metric).
    s5 = df["close"].resample("5min", label="right", closed="right").last()
    s5.name = sym
    return s5


def rolling_percentile_rank(s: pd.Series, window: int) -> pd.Series:
    """Trailing rolling-window ECDF percentile rank.

    For each index i, fraction of past `window` observations (including i) with
    value <= current value. NaN if min_periods not met.
    """
    arr = s.values.astype(float)
    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    min_periods = max(50, window // 4)  # at least ~50 obs needed for rank
    for i in range(n):
        start = max(0, i - window + 1)
        win = arr[start: i + 1]
        win = win[~np.isnan(win)]
        if len(win) < min_periods:
            continue
        v = arr[i]
        if np.isnan(v):
            continue
        out[i] = float((win <= v).mean())
    return pd.Series(out, index=s.index, name=s.name)


def compute_quadrant(
    quadrant_name: str,
    trigger_mask_per_sym: dict,  # sym -> bool Series (aligned to fwd index)
    perp_fwd_panel: pd.DataFrame,
    direction_per_sym: dict,  # sym -> +1 LONG / -1 SHORT
    hold_bars: int,
) -> dict:
    """Take signed forward perp return × direction at each trigger. Net fee.
    Decimate to ≥ hold_bars gap per sym."""
    trades_per_sym = {s: [] for s in trigger_mask_per_sym}
    ts_per_sym = {s: [] for s in trigger_mask_per_sym}

    for s, mask in trigger_mask_per_sym.items():
        if s not in perp_fwd_panel.columns:
            continue
        fwd = perp_fwd_panel[s]
        # Align mask to fwd index
        aligned_mask = mask.reindex(fwd.index, fill_value=False) & fwd.notna()
        idx_trig = aligned_mask[aligned_mask].index
        # Decimate ≥ hold_bars × 5m
        if len(idx_trig) > 0:
            last_t = None
            min_gap = pd.Timedelta(minutes=5 * DECIMATION_GAP)
            kept = []
            for t in idx_trig:
                if last_t is None or (t - last_t) >= min_gap:
                    kept.append(t)
                    last_t = t
            idx_trig = pd.DatetimeIndex(kept)
        d = direction_per_sym[s]
        for t in idx_trig:
            r = fwd.loc[t]
            if pd.notna(r):
                trades_per_sym[s].append(d * float(r))
                ts_per_sym[s].append(t)

    all_trades = []
    all_ts = []
    all_sym = []
    for s, lst in trades_per_sym.items():
        for v, t in zip(lst, ts_per_sym[s]):
            all_trades.append(v)
            all_ts.append(t)
            all_sym.append(s)

    if len(all_trades) < 5:
        return {
            "quadrant": quadrant_name,
            "n_trades": len(all_trades),
            "error": "n_trades<5",
            "gate_3_pass": False,
            "gate_concentration_pass": False,
        }

    gross = np.asarray(all_trades, dtype=float)
    net = gross - FEE_PER_TRADE
    obs_t = float(net.mean() / net.std(ddof=1) * np.sqrt(len(net))) if net.std(ddof=1) > 0 else 0.0
    gross_mean_bp = float(gross.mean() * 10000)
    net_mean_bp = float(net.mean() * 10000)

    ci = bootstrap_ci(net, n_boot=1000, rng_seed=42)

    # Perm pool: direction-applied forward returns over all valid bars
    pool_vals = []
    for s in perp_fwd_panel.columns:
        fwd = perp_fwd_panel[s].dropna()
        if s not in direction_per_sym:
            continue
        d = direction_per_sym[s]
        if len(fwd) > 0:
            pool_vals.append(d * fwd.values)
    pool = np.concatenate(pool_vals) if pool_vals else np.array([])

    if len(pool) < len(net) * 2:
        perm = {
            "perm_p_two_sided": float("nan"),
            "signal_t_excess": float("nan"),
            "null_mean_t": float("nan"),
            "perm_p_one_sided_above": float("nan"),
        }
    else:
        perm = fee_aware_perm_test(net, pool, fee_per_trade=FEE_PER_TRADE,
                                   n_perms=1000, rng_seed=42)

    # Per-symbol CI
    per_sym_ci = {}
    for s, lst in trades_per_sym.items():
        if len(lst) < 5:
            per_sym_ci[s] = {"n": len(lst), "ci_lower_bp": float("nan"), "ci_pos": False}
            continue
        net_s = np.asarray(lst) - FEE_PER_TRADE
        ci_s = bootstrap_ci(net_s, n_boot=500, rng_seed=42)
        per_sym_ci[s] = {
            "n": int(len(lst)),
            "mean_bp": float(net_s.mean() * 10000),
            "ci_lower_bp": float(ci_s["ci_lower"] * 10000),
            "ci_upper_bp": float(ci_s["ci_upper"] * 10000),
            "ci_pos": bool(ci_s["ci_lower"] > 0),
        }
    n_syms_ci_pos = sum(1 for v in per_sym_ci.values() if v["ci_pos"])
    syms_ci_pos_ratio = n_syms_ci_pos / max(1, len(per_sym_ci))

    # Per-quarter (only 1 quarter in 35d window — Lesson #30)
    df_q = pd.DataFrame({"ts": all_ts, "ret": net, "sym": all_sym})
    df_q["quarter"] = pd.to_datetime(df_q["ts"]).dt.to_period("Q").astype(str)
    per_q = {}
    for q, sub in df_q.groupby("quarter"):
        if len(sub) < 5:
            per_q[q] = {"n": len(sub), "t": float("nan"), "pos_t": False}
            continue
        sd_q = sub["ret"].std(ddof=1)
        tq = sub["ret"].mean() / sd_q * np.sqrt(len(sub)) if sd_q > 0 else 0
        per_q[q] = {
            "n": int(len(sub)),
            "mean_bp": float(sub["ret"].mean() * 10000),
            "t": float(tq),
            "pos_t": bool(tq > 0),
        }
    n_q_measurable = sum(1 for v in per_q.values() if pd.notna(v["t"]) and v["n"] >= 5)
    n_q_pos = sum(1 for v in per_q.values() if v["pos_t"] and v["n"] >= 5)
    q_pos_ratio = n_q_pos / max(1, n_q_measurable)

    gate_3 = bool(
        perm.get("signal_t_excess", float("nan")) >= 2.0
        and ci["ci_lower"] > 0
        and perm.get("perm_p_two_sided", 1.0) <= 0.10
    )
    gate_conc = bool(
        q_pos_ratio >= 0.5 and syms_ci_pos_ratio >= 0.30 and n_syms_ci_pos >= 3
    )

    # Life-changing 4-dim
    if len(all_ts) >= 2:
        n_years = max(1e-6, (pd.to_datetime(max(all_ts)) - pd.to_datetime(min(all_ts))).days / 365.25)
    else:
        n_years = 1e-6
    trades_per_year = len(net) / n_years
    per_trade_edge_pct = net_mean_bp / 100
    capital_util_pct = min(100.0, (hold_bars * 5 * trades_per_year) / (365.25 * 24 * 60) * 100)
    sharpe_annual = (
        (net.mean() / net.std(ddof=1)) * np.sqrt(trades_per_year)
        if net.std(ddof=1) > 0 else 0.0
    )
    life_changing_dims = {
        "trades_per_year": float(trades_per_year),
        "per_trade_edge_pct": float(per_trade_edge_pct),
        "capital_util_pct": float(capital_util_pct),
        "annualized_sharpe": float(sharpe_annual),
        "pass_trades_per_year_12": bool(trades_per_year >= 12),
        "pass_edge_2pct": bool(per_trade_edge_pct >= 2.0),
        "pass_util_30pct": bool(capital_util_pct >= 30),
        "pass_sharpe_1_5": bool(sharpe_annual >= 1.5),
        "pass_all_4_dim": bool(
            trades_per_year >= 12 and per_trade_edge_pct >= 2.0
            and capital_util_pct >= 30 and sharpe_annual >= 1.5
        ),
    }

    return {
        "quadrant": quadrant_name,
        "hold_bars": hold_bars,
        "hold_min": hold_bars * 5,
        "n_trades": int(len(net)),
        "n_trades_per_sym": {s: int(len(trades_per_sym[s])) for s in trades_per_sym},
        "obs_mean_gross_bp": gross_mean_bp,
        "obs_mean_net_bp": net_mean_bp,
        "obs_t": obs_t,
        "ci_lower_bp": float(ci["ci_lower"] * 10000),
        "ci_upper_bp": float(ci["ci_upper"] * 10000),
        "ci_pos": bool(ci["ci_lower"] > 0),
        "perm_p_two_sided": float(perm.get("perm_p_two_sided", float("nan"))),
        "perm_p_one_sided_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "gate_3_pass": gate_3,
        "per_quarter": per_q,
        "n_q_measurable": int(n_q_measurable),
        "n_q_pos": int(n_q_pos),
        "q_pos_ratio": float(q_pos_ratio),
        "per_symbol_ci": per_sym_ci,
        "n_syms_ci_pos": int(n_syms_ci_pos),
        "n_syms_total": len(per_sym_ci),
        "syms_ci_pos_ratio": float(syms_ci_pos_ratio),
        "gate_concentration_pass": gate_conc,
        "life_changing_4dim": life_changing_dims,
    }


def main() -> int:
    t_start = time.time()
    out: dict = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-1",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "fee_per_trade": FEE_PER_TRADE,
        "primary_low": PRIMARY_LOW,
        "primary_high": PRIMARY_HIGH,
        "gap_threshold": GAP_THRESHOLD,
        "primary_hold_bars": PRIMARY_HOLD_BARS,
        "rolling_window_5m_bars": ROLLING_30D_5M_BARS,
    }

    # ─── Stage 1: Load positioning + OHLCV ───────────────────────────────────
    log.info("loading positioning metrics for %d alts", len(ALTS))
    t_load = time.time()

    top_lsr = {}
    glob_lsr = {}
    for s in ALTS:
        t0 = time.time()
        tl = load_positioning(s, "top_long_short_position")
        gl = load_positioning(s, "global_long_short_account")
        if not tl.empty:
            top_lsr[s] = tl
        if not gl.empty:
            glob_lsr[s] = gl
        log.info("  %s: top=%d global=%d (%.2fs)", s, len(tl), len(gl), time.time() - t0)

    if not top_lsr or not glob_lsr:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = "positioning metric load returned 0 series"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    top_df = pd.concat(top_lsr, axis=1).sort_index()
    top_df = top_df[~top_df.index.duplicated(keep="first")]
    glob_df = pd.concat(glob_lsr, axis=1).sort_index()
    glob_df = glob_df[~glob_df.index.duplicated(keep="first")]

    # Inner-join: both series must be present at each (ts, sym)
    common_idx = top_df.index.intersection(glob_df.index)
    top_df = top_df.loc[common_idx]
    glob_df = glob_df.loc[common_idx]
    log.info("positioning panel: %d rows × %d syms", len(common_idx), len(top_df.columns))

    ts_min = common_idx.min()
    ts_max = common_idx.max()

    log.info("loading OHLCV 5m for fwd returns")
    mark_panel = {}
    for s in ALTS:
        if s not in top_df.columns:
            continue
        t0 = time.time()
        m = load_ohlcv_5m(s, ts_min, ts_max)
        log.info("  %s ohlcv 5m: %d (%.2fs)", s, len(m), time.time() - t0)
        if not m.empty:
            mark_panel[s] = m
    if not mark_panel:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = "OHLCV 5m load returned 0 series"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1
    mark_df = pd.concat(mark_panel, axis=1)
    mark_df.columns = list(mark_panel.keys())
    mark_df = mark_df.sort_index()

    load_secs = time.time() - t_load
    log.info("load done in %.1fs", load_secs)

    out["data_window"] = {
        "ts_min": str(ts_min),
        "ts_max": str(ts_max),
        "n_5m_bars": int(len(common_idx)),
        "n_alts_with_positioning": int(len(top_df.columns)),
        "n_alts_with_ohlcv": int(len(mark_panel)),
        "panel_days": float((ts_max - ts_min).days),
        "load_seconds": float(load_secs),
    }

    # Lesson #30 — data window ratio
    panel_days = float((ts_max - ts_min).days)
    full_archive_days = 720  # ~24 months
    ratio = panel_days / full_archive_days
    out["lesson30_data_window_ratio"] = {
        "panel_days": panel_days,
        "full_archive_days": full_archive_days,
        "ratio": float(ratio),
        "passes_lesson30_30pct": bool(ratio >= 0.30),
        "verdict_reliability": "advisory_only" if ratio < 0.30 else "moderate",
        "note": "positioning_metric backfill 35d. Full conclusion requires re-run after substrate extension.",
    }

    # ─── Stage 2: Percentile rank ─────────────────────────────────────────────
    log.info("computing rolling p_rank window=%d 5m bars (~30d)", ROLLING_30D_5M_BARS)
    t_pr = time.time()
    top_pr_cols = {}
    glob_pr_cols = {}
    for s in top_df.columns:
        # Note: with only 35d data, rolling window = 30d means p_rank saturated.
        # Use shorter effective window since min_periods is the binding constraint.
        top_pr_cols[s] = rolling_percentile_rank(top_df[s].dropna(), ROLLING_30D_5M_BARS).reindex(common_idx)
        glob_pr_cols[s] = rolling_percentile_rank(glob_df[s].dropna(), ROLLING_30D_5M_BARS).reindex(common_idx)
    top_pr_df = pd.concat(top_pr_cols, axis=1)
    top_pr_df.columns = list(top_pr_cols.keys())
    glob_pr_df = pd.concat(glob_pr_cols, axis=1)
    glob_pr_df.columns = list(glob_pr_cols.keys())
    log.info("p_rank done in %.1fs", time.time() - t_pr)

    # Forward returns (5m bars)
    fwd_panels = {}
    for h in HOLD_SWEEP_BARS:
        f = np.log(mark_df.shift(-h) / mark_df)
        fwd_panels[h] = f

    # Lesson #34 — empirical distribution of percentile ranks (sanity)
    top_pr_all = top_pr_df.stack().dropna()
    glob_pr_all = glob_pr_df.stack().dropna()
    gap = (top_pr_df - glob_pr_df).stack().dropna()
    out["lesson34_empirical_distribution"] = {
        "top_pr_p01": float(top_pr_all.quantile(0.01)),
        "top_pr_p05": float(top_pr_all.quantile(0.05)),
        "top_pr_p50": float(top_pr_all.quantile(0.50)),
        "top_pr_p95": float(top_pr_all.quantile(0.95)),
        "top_pr_p99": float(top_pr_all.quantile(0.99)),
        "glob_pr_p01": float(glob_pr_all.quantile(0.01)),
        "glob_pr_p05": float(glob_pr_all.quantile(0.05)),
        "glob_pr_p50": float(glob_pr_all.quantile(0.50)),
        "glob_pr_p95": float(glob_pr_all.quantile(0.95)),
        "glob_pr_p99": float(glob_pr_all.quantile(0.99)),
        "gap_p01": float(gap.quantile(0.01)),
        "gap_p05": float(gap.quantile(0.05)),
        "gap_p50": float(gap.quantile(0.50)),
        "gap_p95": float(gap.quantile(0.95)),
        "gap_p99": float(gap.quantile(0.99)),
        "gap_max": float(gap.max()),
        "gap_min": float(gap.min()),
        "n_obs": int(len(top_pr_all)),
    }
    log.info(
        "top_pr p05=%.3f p95=%.3f / glob_pr p05=%.3f p95=%.3f / gap p05=%.3f p95=%.3f",
        out["lesson34_empirical_distribution"]["top_pr_p05"],
        out["lesson34_empirical_distribution"]["top_pr_p95"],
        out["lesson34_empirical_distribution"]["glob_pr_p05"],
        out["lesson34_empirical_distribution"]["glob_pr_p95"],
        out["lesson34_empirical_distribution"]["gap_p05"],
        out["lesson34_empirical_distribution"]["gap_p95"],
    )

    # Build trigger masks per sym per quadrant
    # A: smart_HIGH (top_pr >= 0.95) + dumb_LOW (glob_pr <= 0.05) + gap > 0.85
    # B: smart_LOW (top_pr <= 0.05) + dumb_HIGH (glob_pr >= 0.95) + gap < -0.85
    gap_df = top_pr_df - glob_pr_df

    mask_A_per_sym = {}
    mask_B_per_sym = {}
    for s in top_pr_df.columns:
        mA = (top_pr_df[s] >= PRIMARY_HIGH) & (glob_pr_df[s] <= PRIMARY_LOW) & (gap_df[s] > GAP_THRESHOLD)
        mB = (top_pr_df[s] <= PRIMARY_LOW) & (glob_pr_df[s] >= PRIMARY_HIGH) & (gap_df[s] < -GAP_THRESHOLD)
        mask_A_per_sym[s] = mA.fillna(False)
        mask_B_per_sym[s] = mB.fillna(False)

    # Sample density (Lesson #11)
    n_A_raw = sum(int(m.sum()) for m in mask_A_per_sym.values())
    n_B_raw = sum(int(m.sum()) for m in mask_B_per_sym.values())
    out["lesson11_sample_density"] = {
        "n_A_trigger_raw": n_A_raw,
        "n_B_trigger_raw": n_B_raw,
        "n_quarters_in_window": 1,  # 35d single quarter
        "decimation_factor": DECIMATION_GAP,
        "expected_A_trades_post_decimation": float(n_A_raw / DECIMATION_GAP),
        "expected_B_trades_post_decimation": float(n_B_raw / DECIMATION_GAP),
        "note_lesson30_advisory": "1 quarter only — per-quarter floor N/A. Pool-level n must ≥30.",
        "passes_pool_n30_A": bool(n_A_raw / DECIMATION_GAP >= 30),
        "passes_pool_n30_B": bool(n_B_raw / DECIMATION_GAP >= 30),
    }
    log.info(
        "Lesson #11 sample density: A raw=%d B raw=%d (post-decimation est A=%.0f B=%.0f)",
        n_A_raw, n_B_raw, n_A_raw / DECIMATION_GAP, n_B_raw / DECIMATION_GAP,
    )

    if (n_A_raw / DECIMATION_GAP < 30) and (n_B_raw / DECIMATION_GAP < 30):
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = (
            f"Lesson #11 prescreen FAIL: both A and B post-decimation pool n < 30. "
            f"A_est={n_A_raw/DECIMATION_GAP:.0f} B_est={n_B_raw/DECIMATION_GAP:.0f}. "
            f"Compounded by Lesson #30 (data ratio {ratio:.3f} < 0.30 advisory-only)."
        )
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        out["_summary_one_liner"] = {
            "paradigm": PARADIGM_NAME,
            "verdict": "SAMPLE_INSUFFICIENT",
            "verdict_reason": out["verdict_reason"],
            "n_samples": 0,
            "A_focus_gross_bp": 0.0,
            "sigex_focus": float("nan"),
            "concentration_pass": "0/0",
            "wall_clock_minutes": float(out["wall_clock_minutes"]),
            "next_action_recommendation": "graveyard",
        }
        _write(out)
        log.warning("HALT — SAMPLE_INSUFFICIENT (Lesson #11)")
        return 0

    # ─── Stage 3: 4-quadrant SNT ──────────────────────────────────────────────
    log.info("=== R-1 4-quadrant SNT (hold=%d bars=%dmin) ===", PRIMARY_HOLD_BARS, PRIMARY_HOLD_BARS * 5)
    fwd_primary = fwd_panels[PRIMARY_HOLD_BARS]

    dir_long = {s: +1 for s in mark_df.columns}
    dir_short = {s: -1 for s in mark_df.columns}

    quadrants = {}
    quadrants["A_focus_smartHIGH_dumbLOW_LONG"] = compute_quadrant(
        "A_focus_smartHIGH_dumbLOW_LONG",
        mask_A_per_sym, fwd_primary, dir_long, PRIMARY_HOLD_BARS,
    )
    quadrants["A_mirror_smartHIGH_dumbLOW_SHORT"] = compute_quadrant(
        "A_mirror_smartHIGH_dumbLOW_SHORT",
        mask_A_per_sym, fwd_primary, dir_short, PRIMARY_HOLD_BARS,
    )
    quadrants["B_same_sign_smartLOW_dumbHIGH_SHORT"] = compute_quadrant(
        "B_same_sign_smartLOW_dumbHIGH_SHORT",
        mask_B_per_sym, fwd_primary, dir_short, PRIMARY_HOLD_BARS,
    )
    quadrants["B_mirror_smartLOW_dumbHIGH_LONG"] = compute_quadrant(
        "B_mirror_smartLOW_dumbHIGH_LONG",
        mask_B_per_sym, fwd_primary, dir_long, PRIMARY_HOLD_BARS,
    )
    out["quadrants"] = quadrants

    # ─── Stage 4: Lesson #21 axis-alone diagnostic ────────────────────────────
    log.info("=== Lesson #21 axis-alone single-axis check ===")
    # top_lsr_pr >= 0.95 alone → LONG
    mask_top_high = {s: (top_pr_df[s] >= PRIMARY_HIGH).fillna(False) for s in top_pr_df.columns}
    # global_lsr_pr <= 0.05 alone → LONG (retail bearish = contrarian LONG signal)
    mask_glob_low = {s: (glob_pr_df[s] <= PRIMARY_LOW).fillna(False) for s in glob_pr_df.columns}

    axis_alone = {}
    axis_alone["top_HIGH_alone_LONG"] = compute_quadrant(
        "top_HIGH_alone_LONG", mask_top_high, fwd_primary, dir_long, PRIMARY_HOLD_BARS,
    )
    axis_alone["glob_LOW_alone_LONG"] = compute_quadrant(
        "glob_LOW_alone_LONG", mask_glob_low, fwd_primary, dir_long, PRIMARY_HOLD_BARS,
    )
    out["lesson21_axis_alone"] = axis_alone

    # ─── Stage 5: Hold sweep on A_focus ──────────────────────────────────────
    log.info("=== hold sweep on A_focus ===")
    sweep = []
    for h in HOLD_SWEEP_BARS:
        if h == PRIMARY_HOLD_BARS:
            continue
        try:
            res = compute_quadrant(
                f"A_focus_h{h}", mask_A_per_sym, fwd_panels[h], dir_long, h,
            )
            sweep.append(res)
        except Exception as e:
            log.warning("sweep h=%d fail: %s", h, e)
    out["hold_sweep_A_focus"] = sweep

    # ─── Verdict aggregation ─────────────────────────────────────────────────
    A_focus = quadrants["A_focus_smartHIGH_dumbLOW_LONG"]
    A_mirror = quadrants["A_mirror_smartHIGH_dumbLOW_SHORT"]
    B_same = quadrants["B_same_sign_smartLOW_dumbHIGH_SHORT"]
    B_mirror = quadrants["B_mirror_smartLOW_dumbHIGH_LONG"]

    a_focus_pass = A_focus.get("gate_3_pass", False) and A_focus.get("gate_concentration_pass", False)
    b_same_pass = B_same.get("gate_3_pass", False) and B_same.get("gate_concentration_pass", False)
    n_quadrants_pass = sum(1 for q in (A_focus, A_mirror, B_same, B_mirror) if q.get("gate_3_pass", False))

    # Lesson #21 invocation check
    top_alone_pass = axis_alone["top_HIGH_alone_LONG"].get("gate_3_pass", False)
    glob_alone_pass = axis_alone["glob_LOW_alone_LONG"].get("gate_3_pass", False)
    axis_alone_carries_signal = top_alone_pass or glob_alone_pass

    if a_focus_pass and b_same_pass:
        verdict = "PASS_R1_FULL"
        verdict_reason = (
            "A_focus (smart_HIGH + dumb_LOW → LONG) and B_same (smart_LOW + dumb_HIGH → SHORT) "
            "both PASS 3-gate + Concentration. Smart-dumb divergence mechanism bidirectionally confirmed."
        )
        next_action = "propose_R2"
        if axis_alone_carries_signal:
            verdict = "PASS_R1_FULL_LESSON21_FLAG"
            verdict_reason += (
                f" WARNING Lesson #21: single-axis also PASSES "
                f"(top_alone={top_alone_pass} glob_alone={glob_alone_pass}). "
                "Dual conjunction may NOT be synthesizing alpha — check incremental gain."
            )
    elif a_focus_pass and not b_same_pass:
        verdict = "SPLIT_PARADIGM_A_ONLY"
        verdict_reason = (
            "A_focus PASS but B_same FAIL — only smart-bullish/dumb-bearish direction holds. "
            "Asymmetric mechanism."
        )
        next_action = "graveyard"
        if axis_alone_carries_signal:
            verdict = "BROAD_FALSIFIED_LESSON21_AXIS_STACKING"
            verdict_reason = (
                "A_focus PASS but Lesson #21: single-axis carries signal alone — "
                "dual conjunction does not synthesize. Falls under axis-stacking antipattern."
            )
    elif b_same_pass and not a_focus_pass:
        verdict = "SPLIT_PARADIGM_B_ONLY"
        verdict_reason = (
            "B_same PASS but A_focus FAIL — only smart-bearish/dumb-bullish direction works."
        )
        next_action = "graveyard"
    elif n_quadrants_pass == 0:
        a_focus_gross = A_focus.get("obs_mean_gross_bp", 0)
        if a_focus_gross > 0 and a_focus_gross < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"A_focus gross +{a_focus_gross:.2f}bp positive but < 16bp fee floor. "
                "Mechanism may exist but uneconomic."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = "All 4 quadrants FAIL 3-gate. No divergence mechanism at 5m × 4h."
        next_action = "graveyard"
    else:
        mirror_only = A_mirror.get("gate_3_pass", False) or B_mirror.get("gate_3_pass", False)
        if mirror_only:
            verdict = "BROAD_FALSIFIED_MIRROR_ONLY"
            verdict_reason = (
                "Only mirror quadrant(s) PASS — Lesson #8 mirror antipattern. Mechanism direction inverted."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = "Partial PASS but neither focus quadrant passes."
        next_action = "graveyard"

    # Life-changing 4-dim check on A_focus
    lc_A = A_focus.get("life_changing_4dim", {})
    if verdict.startswith("PASS_R1") and not lc_A.get("pass_all_4_dim", False):
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = (
            f"3-gate + Concentration PASS but Life-changing 4-dim FAIL: "
            f"trades/yr={lc_A.get('trades_per_year', 0):.1f} (need ≥12), "
            f"edge={lc_A.get('per_trade_edge_pct', 0):.2f}% (need ≥2%), "
            f"util={lc_A.get('capital_util_pct', 0):.1f}% (need ≥30%), "
            f"sharpe={lc_A.get('annualized_sharpe', 0):.2f} (need ≥1.5)."
        )
        next_action = "graveyard"

    out["lesson30_advisory_note"] = (
        f"DATA WINDOW RATIO {ratio:.3f} < 0.30 — verdict ADVISORY ONLY. "
        "Full-window re-run after positioning_metric backfill extension required for production conclusion."
    )

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["next_action_recommendation"] = next_action
    out["n_quadrants_pass_3gate"] = n_quadrants_pass
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    out["_summary_one_liner"] = {
        "paradigm": PARADIGM_NAME,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "n_samples": int(A_focus.get("n_trades", 0)),
        "A_focus_gross_bp": float(A_focus.get("obs_mean_gross_bp", 0)),
        "A_focus_net_bp": float(A_focus.get("obs_mean_net_bp", 0)),
        "sigex_focus": float(A_focus.get("signal_t_excess", float("nan"))),
        "concentration_pass": f"{A_focus.get('n_syms_ci_pos', 0)}/{A_focus.get('n_syms_total', 0)}",
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": next_action,
    }

    _write(out)
    log.info("=== R-1 DONE in %.1fmin === verdict=%s", out["wall_clock_minutes"], verdict)
    return 0


def _write(payload: dict) -> None:
    p = OUT_DIR / "r1__metrics.json"
    with open(p, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("wrote %s", p)


if __name__ == "__main__":
    sys.exit(main())
