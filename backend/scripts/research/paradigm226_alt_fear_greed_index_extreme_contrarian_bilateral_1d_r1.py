"""R-1 PoC — paradigm 226 alt_fear_greed_index_extreme_contrarian_bilateral_1d.

Hypothesis (single sentence)
----------------------------
Daily Crypto Fear & Greed Index (Alternative.me composite 0-100) extreme readings
predict contrarian 1d-3d mean-reversion in Binance USDT-M perp alts.

Symmetric Negative Test (Lesson #19) — 4-quadrant single R-1 batch
-----------------------------------------------------------------
- A_focus  : F&G <= 25 (EXTREME_FEAR) -> LONG alts, hold 24h
- A_mirror : F&G <= 25 (EXTREME_FEAR) -> SHORT alts (mechanical mirror)
- B_focus  : F&G >= 75 (EXTREME_GREED) -> SHORT alts, hold 24h
- B_mirror : F&G >= 75 (EXTREME_GREED) -> LONG alts (mechanical mirror)

Hold sweep (Lesson #37 CONFIRMED-eligible): [24h, 48h, 72h] all cells scanned.

Lesson #40 (threshold feasibility): PASS — raw bounded 0-100 score with
natural economic thresholds; NOT z-score of non-negative aggregate. Empirical
FEAR<=25 rate 24.2%, GREED>=75 rate 9.7% on 2000d substrate window.

Lesson #46 (R-0 stratified advisory): per-quarter mean + t on A_focus reported.

Substrate
---------
- Fear & Greed daily JSON (already downloaded to
  backend/runs/research_track/alt_fear_greed_index_extreme_contrarian_bilateral_1d/fear_greed_daily.json)
- OHLCV 1m joblib caches for 13 alts (2024-01-02 -> 2026-05-12)
  resampled to daily UTC close-to-close returns

Output
------
backend/runs/research_track/alt_fear_greed_index_extreme_contrarian_bilateral_1d/r1__metrics.json
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p226_r1")

PARADIGM = "alt_fear_greed_index_extreme_contrarian_bilateral_1d"
PARADIGM_N = 226
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"
FNG_PATH = OUT_DIR / "fear_greed_daily.json"
OHLCV_DIR = ROOT / "runs" / "ohlcv_cache"

ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

FEAR_THRESHOLD = 25   # <= 25 -> EXTREME FEAR
GREED_THRESHOLD = 75  # >= 75 -> EXTREME GREED
HOLDS_HOURS = [24, 48, 72]
FEE_RT = 0.0008   # 8 bp round-trip
N_PERMS = 1000
N_BOOT = 2000
SEED = 42

# ---------- data loaders ----------


def load_fng() -> pd.Series:
    """Return daily F&G Series indexed by UTC midnight timestamps (00:00)."""
    d = json.loads(FNG_PATH.read_text())
    rows = d.get("data", [])
    ts_list, val_list = [], []
    for r in rows:
        ts = pd.to_datetime(int(r["timestamp"]), unit="s", utc=True).tz_convert(None)
        # normalize to date (midnight UTC)
        ts = ts.normalize()
        ts_list.append(ts)
        val_list.append(int(r["value"]))
    s = pd.Series(val_list, index=pd.DatetimeIndex(ts_list, name="date"), name="fng")
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s


def load_daily_close(sym: str) -> pd.Series:
    """Load 1m joblib, resample to daily 00:00 UTC close."""
    fp = OHLCV_DIR / f"{sym}_1m.joblib"
    if not fp.exists():
        log.warning("missing joblib: %s", fp)
        return pd.Series(dtype=float)
    df = joblib.load(fp)
    if len(df) == 0:
        return pd.Series(dtype=float)
    # daily close = last 1m close of each UTC day
    daily = df["close"].resample("1D").last().dropna()
    daily.name = sym
    return daily


def compute_forward_returns(daily_close: pd.Series, hold_days: int) -> pd.Series:
    """Return per-day forward close-to-close return over `hold_days` days.
    Indexed by the entry timestamp (t) — value is close(t+h)/close(t) - 1.
    """
    if len(daily_close) < hold_days + 1:
        return pd.Series(dtype=float)
    fwd = daily_close.shift(-hold_days) / daily_close - 1.0
    return fwd


# ---------- core evaluation ----------


def eval_cell(
    fng: pd.Series,
    per_sym_fwd: dict,
    threshold_side: str,   # "FEAR" or "GREED"
    direction: int,        # +1 LONG, -1 SHORT
    hold_h: int,
    label: str,
    rng_seed: int = SEED,
) -> dict:
    """Evaluate one 4-quadrant cell.

    Trigger:
      - FEAR side: fng.value <= FEAR_THRESHOLD (25)
      - GREED side: fng.value >= GREED_THRESHOLD (75)
    direction: multiplied into forward return; fee subtracted per round-trip.
    """
    if threshold_side == "FEAR":
        trigger_mask = fng <= FEAR_THRESHOLD
    else:
        trigger_mask = fng >= GREED_THRESHOLD

    per_trade_returns = []      # per-trade net
    per_trade_ts = []
    per_trade_sym = []
    all_candidate_gross = []    # for fee_aware_perm pool

    for sym, fwd_all in per_sym_fwd.items():
        # align fng and fwd_all on their intersecting daily index
        aligned = pd.concat({"fng": fng, "fwd": fwd_all}, axis=1).dropna()
        if aligned.empty:
            continue
        cell_mask = aligned["fng"] <= FEAR_THRESHOLD if threshold_side == "FEAR" else aligned["fng"] >= GREED_THRESHOLD
        # observed trades
        obs = aligned.loc[cell_mask, "fwd"].values * direction - FEE_RT
        per_trade_returns.append(obs)
        per_trade_ts.append(aligned.loc[cell_mask].index.values)
        per_trade_sym.extend([sym] * cell_mask.sum())
        # candidate pool = ALL forward returns in aligned (regardless of trigger),
        # signed by trial direction, fees applied in perm test
        all_candidate_gross.append(aligned["fwd"].values * direction)

    if not per_trade_returns:
        return {"label": label, "n_trades": 0, "error": "no_data"}

    obs_all = np.concatenate(per_trade_returns)
    pool_all = np.concatenate(all_candidate_gross)
    per_sym_arrays = {
        sym: arr for sym, arr in zip(per_sym_fwd.keys(), per_trade_returns)
    }
    ts_all = np.concatenate(per_trade_ts) if per_trade_ts else np.array([], dtype="datetime64[ns]")
    syms_all = np.array(per_trade_sym)

    n_trades = len(obs_all)
    if n_trades < 5:
        return {
            "label": label, "n_trades": int(n_trades),
            "error": "n<5",
        }

    # Three-gate stats
    obs_mean = float(obs_all.mean())
    obs_std = float(obs_all.std(ddof=1))
    obs_t = float(obs_all.mean() / obs_all.std(ddof=1) * np.sqrt(n_trades)) if obs_std > 0 else 0.0

    perm = fee_aware_perm_test(
        observed_net_returns=obs_all.tolist(),
        candidate_pool_returns=pool_all.tolist(),
        fee_per_trade=FEE_RT,
        n_perms=N_PERMS,
        rng_seed=rng_seed,
    )
    ci = bootstrap_ci(observed_net_returns=obs_all.tolist(), n_boot=N_BOOT, block_size=1, rng_seed=rng_seed)

    # Concentration diagnostics (Lesson #16)
    ts_series = pd.to_datetime(ts_all)
    quarters = pd.PeriodIndex(ts_series, freq="Q")
    per_quarter_t = {}
    per_quarter_mean = {}
    n_pos_t = 0
    n_measurable_q = 0
    for q, sub in pd.Series(obs_all, index=quarters).groupby(level=0):
        if len(sub) < 2 or sub.std(ddof=1) == 0:
            continue
        n_measurable_q += 1
        t = float(sub.mean() / sub.std(ddof=1) * np.sqrt(len(sub)))
        per_quarter_t[str(q)] = t
        per_quarter_mean[str(q)] = float(sub.mean())
        if t > 0:
            n_pos_t += 1
    quarter_pos_t_ratio = n_pos_t / n_measurable_q if n_measurable_q > 0 else 0.0

    # per-symbol bootstrap
    per_sym_stats = {}
    n_ci_pos = 0
    n_measurable_sym = 0
    n_mean_pos = 0
    for sym, arr in per_sym_arrays.items():
        if len(arr) < 5:
            continue
        n_measurable_sym += 1
        sym_ci = bootstrap_ci(observed_net_returns=arr.tolist(), n_boot=1000, block_size=1, rng_seed=rng_seed)
        per_sym_stats[sym] = {
            "n": int(len(arr)),
            "mean": float(arr.mean()),
            "ci_lower": sym_ci.get("ci_lower"),
            "ci_upper": sym_ci.get("ci_upper"),
        }
        if arr.mean() > 0:
            n_mean_pos += 1
        if sym_ci.get("ci_lower", -1) is not None and sym_ci["ci_lower"] > 0:
            n_ci_pos += 1
    symbol_ci_pos_ratio = n_ci_pos / n_measurable_sym if n_measurable_sym > 0 else 0.0

    # Life-changing 4-dim (rough R-1 estimate)
    # window = universe intersection window in years
    # per-symbol trades/year = n_trades / len(alts) / years
    # for A_focus we count fresh triggers per alt
    trades_per_year_per_sym = float(n_trades / max(1, len(per_sym_fwd)) / (858 / 365.0))
    edge_pct_per_trade = float(obs_mean * 100)

    # Three-gate PASS
    three_gate_pass = (
        perm.get("signal_t_excess", -99) >= 1.5
        and (ci.get("ci_lower", -1) or -1) > 0
        and (perm.get("perm_p_one_sided_above", 1.0) if direction > 0 else perm.get("perm_p_one_sided_below", 1.0)) < 0.05
    )
    # Concentration gate
    concentration_pass = (
        quarter_pos_t_ratio >= 0.5
        and symbol_ci_pos_ratio >= 0.30
        and n_ci_pos >= 3
    )

    return {
        "label": label,
        "threshold_side": threshold_side,
        "direction": int(direction),
        "hold_hours": int(hold_h),
        "n_trades": int(n_trades),
        "obs_mean_net": obs_mean,
        "obs_mean_bp": float(obs_mean * 1e4),
        "obs_t": obs_t,
        "signal_t_excess": perm.get("signal_t_excess"),
        "perm_null_mean_t": perm.get("null_mean_t"),
        "perm_null_std_t": perm.get("null_std_t"),
        "perm_p_two_sided": perm.get("perm_p_two_sided"),
        "perm_p_one_sided_above": perm.get("perm_p_one_sided_above"),
        "perm_p_one_sided_below": perm.get("perm_p_one_sided_below"),
        "ci_mean": ci.get("mean"),
        "ci_lower": ci.get("ci_lower"),
        "ci_upper": ci.get("ci_upper"),
        "ci_lower_bp": float((ci.get("ci_lower") or 0) * 1e4),
        "ci_upper_bp": float((ci.get("ci_upper") or 0) * 1e4),
        "quarter_pos_t_ratio": float(quarter_pos_t_ratio),
        "n_measurable_quarters": int(n_measurable_q),
        "n_quarters_pos_t": int(n_pos_t),
        "per_quarter_t": per_quarter_t,
        "per_quarter_mean": per_quarter_mean,
        "symbol_ci_pos_ratio": float(symbol_ci_pos_ratio),
        "n_symbols_measurable": int(n_measurable_sym),
        "n_symbols_ci_pos": int(n_ci_pos),
        "n_symbols_mean_pos": int(n_mean_pos),
        "per_symbol_stats": per_sym_stats,
        "trades_per_year_per_sym_estimate": trades_per_year_per_sym,
        "edge_pct_per_trade_estimate": edge_pct_per_trade,
        "three_gate_pass": bool(three_gate_pass),
        "concentration_gate_pass": bool(concentration_pass),
    }


# ---------- main ----------


def main() -> None:
    t0 = time.time()
    log.info("paradigm226 R-1 starting")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fng = load_fng()
    log.info("F&G loaded: n=%d, range %s -> %s", len(fng), fng.index.min(), fng.index.max())

    # load daily close per alt
    daily_close_by_sym = {}
    for sym in ALTS:
        dc = load_daily_close(sym)
        if len(dc) < 60:
            log.warning("skip %s: only %d daily rows", sym, len(dc))
            continue
        # normalize to date (midnight UTC) index
        dc.index = pd.DatetimeIndex(dc.index).normalize()
        daily_close_by_sym[sym] = dc
        log.info("  %s: %d daily rows (%s -> %s)", sym, len(dc), dc.index.min(), dc.index.max())

    if not daily_close_by_sym:
        raise RuntimeError("no alt daily data loaded")

    # window overlap
    ohlcv_min = min(dc.index.min() for dc in daily_close_by_sym.values())
    ohlcv_max = max(dc.index.max() for dc in daily_close_by_sym.values())
    fng_min = fng.index.min()
    fng_max = fng.index.max()
    overlap_min = max(ohlcv_min, fng_min)
    overlap_max = min(ohlcv_max, fng_max)
    log.info("overlap: %s -> %s (%d days)", overlap_min, overlap_max, (overlap_max - overlap_min).days)

    # empirical trigger rate on overlap window
    fng_overlap = fng.loc[(fng.index >= overlap_min) & (fng.index <= overlap_max)]
    n_fear = int((fng_overlap <= FEAR_THRESHOLD).sum())
    n_greed = int((fng_overlap >= GREED_THRESHOLD).sum())
    log.info("overlap FEAR<=25: %d (%.1f%%), GREED>=75: %d (%.1f%%)",
             n_fear, 100 * n_fear / max(1, len(fng_overlap)),
             n_greed, 100 * n_greed / max(1, len(fng_overlap)))

    # 4-quadrant × 3-hold sweep
    quadrants = [
        ("A_focus_FEAR_LONG", "FEAR", +1),
        ("A_mirror_FEAR_SHORT", "FEAR", -1),
        ("B_focus_GREED_SHORT", "GREED", -1),
        ("B_mirror_GREED_LONG", "GREED", +1),
    ]

    all_cells = []
    for hold_h in HOLDS_HOURS:
        hold_days = hold_h // 24
        # compute forward returns per sym for this hold
        per_sym_fwd = {}
        for sym, dc in daily_close_by_sym.items():
            fwd = compute_forward_returns(dc, hold_days)
            fwd = fwd.loc[(fwd.index >= overlap_min) & (fwd.index <= overlap_max)]
            per_sym_fwd[sym] = fwd
        for label, side, direction in quadrants:
            log.info("evaluating cell hold=%dh label=%s...", hold_h, label)
            cell = eval_cell(fng_overlap, per_sym_fwd, side, direction, hold_h, label)
            all_cells.append(cell)

    # Identify primary cells (24h focus)
    primary_A_focus = next((c for c in all_cells if c["label"] == "A_focus_FEAR_LONG" and c["hold_hours"] == 24), None)
    primary_A_mirror = next((c for c in all_cells if c["label"] == "A_mirror_FEAR_SHORT" and c["hold_hours"] == 24), None)
    primary_B_focus = next((c for c in all_cells if c["label"] == "B_focus_GREED_SHORT" and c["hold_hours"] == 24), None)
    primary_B_mirror = next((c for c in all_cells if c["label"] == "B_mirror_GREED_LONG" and c["hold_hours"] == 24), None)

    # Lesson #37: scan all cells for three-gate PASS + concentration PASS
    three_gate_pass_cells = [c["label"] + f"_h{c['hold_hours']}" for c in all_cells if c.get("three_gate_pass")]
    concentration_pass_cells = [c["label"] + f"_h{c['hold_hours']}" for c in all_cells if c.get("concentration_gate_pass")]

    # Lesson #39: symmetric mirror antipattern check
    # If A_focus and A_mirror both broad-uniform-negative -> sub-class A
    # If A_focus broad-negative but A_mirror shows real concentration -> sub-class B (fee-floor mechanism inverted)
    lesson39_verdict = None
    if primary_A_focus and primary_A_mirror:
        a_f_neg = (primary_A_focus.get("signal_t_excess", 99) or 99) < 1.5
        a_m_neg = (primary_A_mirror.get("signal_t_excess", 99) or 99) < 1.5
        a_m_conc = (primary_A_mirror.get("quarter_pos_t_ratio", 0) or 0) >= 0.30
        if a_f_neg and a_m_neg and not a_m_conc:
            lesson39_verdict = "SUB_CLASS_A_broad_uniform_negative_no_axis_synthesis"
        elif a_f_neg and a_m_conc:
            lesson39_verdict = "SUB_CLASS_B_fee_floor_mechanism_inverted"

    # Verdict tree
    verdict = "UNRESOLVED"
    verdict_reasons = []

    # Primary focus PASS?
    focus_pass_A = primary_A_focus and primary_A_focus.get("three_gate_pass") and primary_A_focus.get("concentration_gate_pass")
    focus_pass_B = primary_B_focus and primary_B_focus.get("three_gate_pass") and primary_B_focus.get("concentration_gate_pass")

    if focus_pass_A or focus_pass_B:
        verdict = "PASS_R1_PROMOTE_R2"
        if focus_pass_A:
            verdict_reasons.append("A_focus_FEAR_LONG_24h three-gate + concentration PASS")
        if focus_pass_B:
            verdict_reasons.append("B_focus_GREED_SHORT_24h three-gate + concentration PASS")
    elif primary_A_focus and primary_A_focus.get("three_gate_pass") and not primary_A_focus.get("concentration_gate_pass"):
        verdict = "CONCENTRATED_R1_PASS"
        verdict_reasons.append("A_focus three-gate PASS but concentration FAIL")
    elif primary_B_focus and primary_B_focus.get("three_gate_pass") and not primary_B_focus.get("concentration_gate_pass"):
        verdict = "CONCENTRATED_R1_PASS"
        verdict_reasons.append("B_focus three-gate PASS but concentration FAIL")
    elif len(three_gate_pass_cells) == 0:
        verdict = "BROAD_FALSIFIED"
        verdict_reasons.append("all 12 cells (4-quadrant × 3-hold) three-gate FAIL")
    elif len(three_gate_pass_cells) > 0:
        # non-primary PASS
        verdict = "NON_FOCUS_PASS_LESSON_15_CANDIDATE"
        verdict_reasons.append(f"non-focus cells three-gate PASS: {three_gate_pass_cells}")

    # Assemble metrics
    metrics = {
        "paradigm": PARADIGM,
        "paradigm_number": PARADIGM_N,
        "phase": "R-1",
        "generated_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "elapsed_s": round(time.time() - t0, 2),
        "universe": ALTS,
        "n_alts": len(daily_close_by_sym),
        "overlap_window": {
            "min": str(overlap_min),
            "max": str(overlap_max),
            "n_days": int((overlap_max - overlap_min).days),
        },
        "empirical_trigger_rate": {
            "n_fng_days_overlap": int(len(fng_overlap)),
            "n_fear_le_25": n_fear,
            "n_greed_ge_75": n_greed,
            "rate_fear_pct": round(100 * n_fear / max(1, len(fng_overlap)), 2),
            "rate_greed_pct": round(100 * n_greed / max(1, len(fng_overlap)), 2),
        },
        "config": {
            "fear_threshold": FEAR_THRESHOLD,
            "greed_threshold": GREED_THRESHOLD,
            "holds_hours": HOLDS_HOURS,
            "fee_rt": FEE_RT,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
        },
        "cells": all_cells,
        "primary_summary": {
            "A_focus_FEAR_LONG_24h": _brief(primary_A_focus),
            "A_mirror_FEAR_SHORT_24h": _brief(primary_A_mirror),
            "B_focus_GREED_SHORT_24h": _brief(primary_B_focus),
            "B_mirror_GREED_LONG_24h": _brief(primary_B_mirror),
        },
        "lesson_37_all_pass_cells_three_gate": three_gate_pass_cells,
        "lesson_37_all_pass_cells_concentration": concentration_pass_cells,
        "lesson_39_verdict": lesson39_verdict,
        "verdict": verdict,
        "verdict_reasons": verdict_reasons,
    }

    OUT_PATH.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("wrote %s", OUT_PATH)
    log.info("VERDICT: %s", verdict)
    for r in verdict_reasons:
        log.info("  reason: %s", r)


def _brief(cell: dict | None) -> dict:
    if not cell:
        return {}
    keys = [
        "n_trades", "obs_mean_bp", "obs_t", "signal_t_excess",
        "perm_p_one_sided_above", "perm_p_one_sided_below",
        "ci_lower_bp", "ci_upper_bp",
        "quarter_pos_t_ratio", "symbol_ci_pos_ratio",
        "n_symbols_ci_pos", "n_symbols_mean_pos",
        "trades_per_year_per_sym_estimate", "edge_pct_per_trade_estimate",
        "three_gate_pass", "concentration_gate_pass",
    ]
    return {k: cell.get(k) for k in keys}


if __name__ == "__main__":
    main()
