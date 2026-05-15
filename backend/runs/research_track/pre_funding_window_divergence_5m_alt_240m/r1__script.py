"""R-1 PoC — pre_funding_window_divergence_5m_alt_240m
=====================================================

Hypothesis
----------
At each 8h funding settlement boundary (00:00/08:00/16:00 UTC), in the
pre-event micro window W = [b - 60min, b - 30min], when premium 5m
z-velocity (`pv_z`) and OI 5m direction (`oi_dir`) DIVERGE in sign, an
abnormal arbitrage flow exists. Entering at the settlement timestamp b
and holding 240m captures the post-settlement normalization.

Four-quadrant Symmetric Negative Test (Lesson #19) is mandatory because
the trigger is a joint event (pv_z sign × oi_dir sign × magnitude).

Universe
--------
13 alts (universe minus BTC):
  ETH, SOL, ADA, AVAX, BCH, BNB, DOGE, FIL, LINK, LTC, NEAR, WIF, XRP

Data
----
- premium_index/{SYM}_premium_5m.joblib  — close column = premium ratio
- microstructure/{SYM}_full_metrics.joblib — `open_interest`
- ohlcv_cache/{SYM}_1m.joblib — entry+exit close

Output
------
runs/research_track/pre_funding_window_divergence_5m_alt_240m/r1__metrics.json

R-1 ONLY — halt regardless of verdict.
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pre_funding_window_divergence_5m_alt_240m_r1")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

PARADIGM = "pre_funding_window_divergence_5m_alt_240m"
RESEARCH_DIR = ROOT / "runs" / "research_track" / PARADIGM
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

PREMIUM_DIR = ROOT / "runs" / "premium_index"
MICRO_DIR = ROOT / "runs" / "microstructure"
OHLCV_CACHE_DIR = ROOT / "runs" / "ohlcv_cache"

UNIVERSE_FULL = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "AVAXUSDT", "BCHUSDT",
    "BNBUSDT", "DOGEUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "WIFUSDT", "XRPUSDT",
]
ALT_UNIVERSE = [s for s in UNIVERSE_FULL if s != "BTCUSDT"]

FEE_ROUND_TRIP = 0.0008   # 8 bp round trip (Lesson #10 fee floor)
HOLD_MIN = 240            # 4h hold
PRE_WIN_START_OFFSET_MIN = -60
PRE_WIN_END_OFFSET_MIN = -30
PREMIUM_Z_LOOKBACK_BARS = 30 * 288  # 30 days × 288 (5m) bars/day

# Trigger thresholds
THETA_PV_Z_DELTA = 0.5    # premium z-velocity magnitude (in z-units)
THETA_OI_REL = 0.0005     # |Δ_OI / OI| ≥ 5 bp over 30m window

DATE_MIN = pd.Timestamp("2024-11-07 00:00:00")  # later of premium-5m and OI starts
DATE_MAX = pd.Timestamp("2026-05-02 00:00:00")  # earlier of premium-5m and OI ends

# --------------------------------------------------------------------------- #
# Data loaders
# --------------------------------------------------------------------------- #

def load_premium_5m(sym: str) -> pd.DataFrame:
    path = PREMIUM_DIR / f"{sym}_premium_5m.joblib"
    df = joblib.load(path)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def load_oi_5m(sym: str) -> pd.Series:
    path = MICRO_DIR / f"{sym}_full_metrics.joblib"
    df = joblib.load(path)
    s = df["open_interest"].dropna().sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def load_ohlcv_1m_close(sym: str) -> pd.Series:
    path = OHLCV_CACHE_DIR / f"{sym}_1m.joblib"
    df = joblib.load(path)
    df.index = pd.to_datetime(df.index)
    s = df["close"].astype(float).sort_index()
    s = s[~s.index.duplicated(keep="first")]
    return s


def boundary_set(d_min: pd.Timestamp, d_max: pd.Timestamp) -> pd.DatetimeIndex:
    """Every 00/08/16 UTC timestamp in [d_min, d_max]."""
    boundaries = []
    cur = pd.Timestamp(d_min.date())
    while cur <= d_max:
        for h in (0, 8, 16):
            b = cur.replace(hour=h, minute=0, second=0)
            if d_min <= b <= d_max:
                boundaries.append(b)
        cur += pd.Timedelta(days=1)
    return pd.DatetimeIndex(boundaries)


# --------------------------------------------------------------------------- #
# Trigger computation per symbol
# --------------------------------------------------------------------------- #

def compute_triggers_for_symbol(sym: str, boundaries: pd.DatetimeIndex) -> pd.DataFrame:
    """For each boundary, compute (pv_z_start, pv_z_end, pv_z_delta, oi_start,
    oi_end, oi_rel_delta, oi_dir, entry_close, exit_close, gross_return).

    Returns a DataFrame indexed by boundary timestamp; rows with any NaN are
    dropped from valid trigger candidates.
    """
    prem = load_premium_5m(sym)["close"]  # premium ratio at 5m close
    oi = load_oi_5m(sym)
    px = load_ohlcv_1m_close(sym)

    # Build a 30d rolling z-score of the premium series (~30d × 288 bars = 8640)
    # Use a long rolling lookback for stability; min_periods ensures we skip
    # the early period when no full window is yet available.
    rolling = prem.rolling(window=PREMIUM_Z_LOOKBACK_BARS, min_periods=PREMIUM_Z_LOOKBACK_BARS // 4)
    mu = rolling.mean()
    sd = rolling.std(ddof=1)
    pz = (prem - mu) / sd
    pz = pz.replace([np.inf, -np.inf], np.nan)

    # Pre-window timestamps
    starts = boundaries + pd.Timedelta(minutes=PRE_WIN_START_OFFSET_MIN)
    ends = boundaries + pd.Timedelta(minutes=PRE_WIN_END_OFFSET_MIN)

    # asof/reindex onto 5m grid via .reindex (premium/oi already on 5m grid → exact match)
    pz_start = pz.reindex(starts).values
    pz_end = pz.reindex(ends).values
    oi_start = oi.reindex(starts).values
    oi_end = oi.reindex(ends).values

    # Entry price = 1m close at boundary; exit = 1m close at boundary + 240m
    entry_px = px.reindex(boundaries).values
    exit_px = px.reindex(boundaries + pd.Timedelta(minutes=HOLD_MIN)).values

    df = pd.DataFrame({
        "boundary": boundaries,
        "pv_z_start": pz_start,
        "pv_z_end": pz_end,
        "oi_start": oi_start,
        "oi_end": oi_end,
        "entry_px": entry_px,
        "exit_px": exit_px,
    }).set_index("boundary")

    df["pv_z_delta"] = df["pv_z_end"] - df["pv_z_start"]
    df["oi_rel_delta"] = (df["oi_end"] - df["oi_start"]) / df["oi_start"]
    df["oi_dir"] = np.sign(df["oi_rel_delta"]).astype(float)
    df["pv_dir"] = np.sign(df["pv_z_delta"]).astype(float)
    df["gross_return"] = (df["exit_px"] - df["entry_px"]) / df["entry_px"]
    df["symbol"] = sym
    return df


def build_full_event_table(boundaries: pd.DatetimeIndex) -> pd.DataFrame:
    frames = []
    for sym in ALT_UNIVERSE:
        try:
            log.info("computing triggers for %s ...", sym)
            f = compute_triggers_for_symbol(sym, boundaries)
            frames.append(f)
        except FileNotFoundError as e:
            log.warning("missing data for %s: %s", sym, e)
    return pd.concat(frames, axis=0).reset_index()


# --------------------------------------------------------------------------- #
# Quadrant evaluation
# --------------------------------------------------------------------------- #

QUADRANTS = {
    "A_focus_pvneg_oiup_LONG": {
        "pv_sign": -1, "oi_sign": +1, "direction": +1,
        "desc": "pv_z falling, OI rising (divergence) → settlement rebound, LONG",
    },
    "A_mirror_pvneg_oiup_SHORT": {
        "pv_sign": -1, "oi_sign": +1, "direction": -1,
        "desc": "mirror of A focus, SHORT (expected opposite sign of A)",
    },
    "B_same_sign_pvpos_oidn_SHORT": {
        "pv_sign": +1, "oi_sign": -1, "direction": -1,
        "desc": "pv_z rising, OI falling (divergence) → settlement drop, SHORT",
    },
    "B_mirror_pvpos_oidn_LONG": {
        "pv_sign": +1, "oi_sign": -1, "direction": +1,
        "desc": "mirror of B same-sign, LONG",
    },
}


def evaluate_quadrant(events: pd.DataFrame, quadrant_spec: dict, signed_pool_gross: np.ndarray, do_concentration: bool) -> dict:
    """For a given quadrant filter, compute net returns + three-gate stats +
    optional concentration block.

    Candidate pool semantics
    ------------------------
    `signed_pool_gross` = gross returns of ALL boundary-anchored 240m windows
    in the panel (regardless of whether they triggered or not). To form the
    null we apply this quadrant's direction sign, producing the gross-return
    distribution a random non-selective trader following the same direction
    would have observed. `fee_aware_perm_test` then subtracts the same fee
    from each draw so the fee-drift baseline is built in.
    """
    pv_s = quadrant_spec["pv_sign"]
    oi_s = quadrant_spec["oi_sign"]
    direction = quadrant_spec["direction"]

    # Filter triggers: matching pv_dir sign, matching oi_dir sign, magnitudes meeting thresholds
    f = events.dropna(subset=["pv_z_delta", "oi_rel_delta", "gross_return"]).copy()
    f = f[
        (np.sign(f["pv_z_delta"]) == pv_s) &
        (np.sign(f["oi_rel_delta"]) == oi_s) &
        (f["pv_z_delta"].abs() >= THETA_PV_Z_DELTA) &
        (f["oi_rel_delta"].abs() >= THETA_OI_REL)
    ].copy()

    n = len(f)
    if n < 30:
        return {
            "n": int(n),
            "skip": "n<30 (Lesson #11 floor)",
            "spec": quadrant_spec,
        }

    f["net_return"] = direction * f["gross_return"] - FEE_ROUND_TRIP

    # Three-gate stats
    obs = f["net_return"].values
    direction_aligned_pool_gross = direction * signed_pool_gross
    fee_result = fee_aware_perm_test(
        observed_net_returns=obs,
        candidate_pool_returns=direction_aligned_pool_gross,
        fee_per_trade=FEE_ROUND_TRIP,
        n_perms=1000,
    )
    # 4h hold → 240m / 5m_grid = 48 bars; use block_size=48 in bootstrap
    ci_result = bootstrap_ci(obs, n_boot=2000, block_size=48)

    three_gate = {
        "signal_t_excess": fee_result["signal_t_excess"],
        "ci_lower": ci_result["ci_lower"],
        "perm_p_two_sided": fee_result["perm_p_two_sided"],
        "pass_signal_t_excess": fee_result["signal_t_excess"] >= 2.0,
        "pass_ci_lower_pos": ci_result["ci_lower"] > 0,
        "pass_perm_p": fee_result["perm_p_two_sided"] <= 0.10,
    }
    three_gate["pass_all"] = (
        three_gate["pass_signal_t_excess"]
        and three_gate["pass_ci_lower_pos"]
        and three_gate["pass_perm_p"]
    )

    out: Dict[str, object] = {
        "spec": quadrant_spec,
        "n_signals": int(n),
        "obs_mean_bp": float(np.mean(obs) * 1e4),
        "obs_median_bp": float(np.median(obs) * 1e4),
        "fee_aware_perm": fee_result,
        "bootstrap_ci_bp": {
            "mean": ci_result["mean"] * 1e4,
            "ci_lower": ci_result["ci_lower"] * 1e4,
            "ci_upper": ci_result["ci_upper"] * 1e4,
            "prob_positive": ci_result["prob_positive"],
        },
        "three_gate": three_gate,
    }

    if do_concentration:
        out["concentration"] = _compute_concentration(f)
    return out


def _compute_concentration(f: pd.DataFrame) -> dict:
    """Per-quarter and per-symbol concentration diagnostics (Lesson #16)."""
    f = f.copy()
    f["quarter"] = f["boundary"].dt.to_period("Q").astype(str)

    # Per-quarter t-stats
    per_q_records: List[dict] = []
    for q, sub in f.groupby("quarter"):
        ret = sub["net_return"].values
        n_q = len(ret)
        if n_q < 3 or np.std(ret, ddof=1) == 0:
            t_q = float("nan")
        else:
            t_q = float(ret.mean() / ret.std(ddof=1) * math.sqrt(n_q))
        per_q_records.append({
            "quarter": q,
            "n_trades": int(n_q),
            "mean_bp": float(ret.mean() * 1e4),
            "t_stat": t_q,
        })
    measurable = [r for r in per_q_records if r["n_trades"] >= 10 and not math.isnan(r["t_stat"])]
    n_q_meas = len(measurable)
    n_q_pos = sum(1 for r in measurable if r["t_stat"] > 0)
    q_pos_ratio = (n_q_pos / n_q_meas) if n_q_meas else float("nan")

    # Per-symbol bootstrap CI
    per_sym_records: List[dict] = []
    for sym, sub in f.groupby("symbol"):
        ret = sub["net_return"].values
        n_s = len(ret)
        if n_s < 10:
            per_sym_records.append({"symbol": sym, "n_trades": int(n_s), "skip": "n<10"})
            continue
        ci = bootstrap_ci(ret, n_boot=2000, block_size=1)
        per_sym_records.append({
            "symbol": sym,
            "n_trades": int(n_s),
            "mean_bp": float(ret.mean() * 1e4),
            "ci_lower_bp": float(ci["ci_lower"] * 1e4),
            "ci_upper_bp": float(ci["ci_upper"] * 1e4),
            "ci_lower_pos": bool(ci["ci_lower"] > 0),
        })
    measurable_syms = [r for r in per_sym_records if r.get("skip") is None]
    n_sym_meas = len(measurable_syms)
    n_sym_ci_pos = sum(1 for r in measurable_syms if r.get("ci_lower_pos") is True)
    sym_pos_ratio = (n_sym_ci_pos / n_sym_meas) if n_sym_meas else float("nan")

    pass_q = (not math.isnan(q_pos_ratio)) and q_pos_ratio >= 0.5
    pass_sym_ratio = (not math.isnan(sym_pos_ratio)) and sym_pos_ratio >= 0.30
    pass_sym_floor = n_sym_ci_pos >= 3

    return {
        "per_quarter_t_stats": per_q_records,
        "n_quarters_measurable": int(n_q_meas),
        "n_quarters_pos_t": int(n_q_pos),
        "quarter_pos_t_ratio": q_pos_ratio,
        "per_symbol_bootstrap": per_sym_records,
        "n_symbols_measurable": int(n_sym_meas),
        "n_symbols_ci_pos": int(n_sym_ci_pos),
        "symbol_ci_pos_ratio": sym_pos_ratio,
        "concentration_gate_pass": bool(pass_q and pass_sym_ratio and pass_sym_floor),
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    t0 = time.time()
    log.info("paradigm=%s window=[-60min,-30min] hold=%dmin universe=%d alts",
             PARADIGM, HOLD_MIN, len(ALT_UNIVERSE))

    boundaries = boundary_set(DATE_MIN, DATE_MAX)
    log.info("boundary set: %d events (range %s -> %s)", len(boundaries), boundaries.min(), boundaries.max())

    log.info("building event table for %d alts ...", len(ALT_UNIVERSE))
    events = build_full_event_table(boundaries)
    log.info("raw event rows (sym × boundary, pre-filter): %d", len(events))

    events_valid = events.dropna(subset=["pv_z_delta", "oi_rel_delta", "gross_return"])
    log.info("events with all fields populated: %d / %d", len(events_valid), len(events))

    # Trigger trigger rate diagnostic (any divergence ≥ thresholds, regardless of sign quadrant)
    divergence_any = events_valid[
        (np.sign(events_valid["pv_z_delta"]) != np.sign(events_valid["oi_rel_delta"])) &
        (events_valid["pv_z_delta"].abs() >= THETA_PV_Z_DELTA) &
        (events_valid["oi_rel_delta"].abs() >= THETA_OI_REL)
    ]
    trigger_rate = len(divergence_any) / max(len(events_valid), 1)
    log.info("any-quadrant divergence triggers: %d (%.2f%% of valid events)",
             len(divergence_any), trigger_rate * 100.0)

    # Candidate pool = signed gross returns of ALL boundary-anchored 240m windows
    # (regardless of trigger). evaluate_quadrant multiplies by its direction sign to
    # form the direction-aligned gross-return distribution for the fee-aware perm null.
    signed_pool = events_valid["gross_return"].values

    log.info("candidate pool size (signed, pre-direction-multiply): %d", len(signed_pool))

    # Pre-screen gross return magnitude (Lesson #10 16bp fee floor)
    gross_abs_median_bp = float(np.median(np.abs(signed_pool))) * 1e4
    log.info("gross |return| median across all valid events: %.2f bp", gross_abs_median_bp)

    quadrant_results: Dict[str, dict] = {}
    for name, spec in QUADRANTS.items():
        log.info("evaluating quadrant %s ...", name)
        do_conc = name.startswith("A_focus") or name.startswith("B_same_sign")
        res = evaluate_quadrant(events_valid, spec, signed_pool, do_concentration=do_conc)
        quadrant_results[name] = res
        if "skip" in res:
            log.info("  %s: SKIP n=%d (%s)", name, res["n"], res["skip"])
        else:
            tg = res["three_gate"]
            log.info("  %s: n=%d mean_bp=%.2f sig_t_ex=%.2f ci_lower_bp=%.2f perm_p=%.3f pass_all=%s",
                     name, res["n_signals"], res["obs_mean_bp"], tg["signal_t_excess"],
                     res["bootstrap_ci_bp"]["ci_lower"], tg["perm_p_two_sided"], tg["pass_all"])

    # Verdict
    a_focus = quadrant_results.get("A_focus_pvneg_oiup_LONG", {})
    b_focus = quadrant_results.get("B_same_sign_pvpos_oidn_SHORT", {})
    a_pass = a_focus.get("three_gate", {}).get("pass_all", False)
    b_pass = b_focus.get("three_gate", {}).get("pass_all", False)

    a_mirror = quadrant_results.get("A_mirror_pvneg_oiup_SHORT", {})
    b_mirror = quadrant_results.get("B_mirror_pvpos_oidn_LONG", {})
    a_mirror_pass = a_mirror.get("three_gate", {}).get("pass_all", False)
    b_mirror_pass = b_mirror.get("three_gate", {}).get("pass_all", False)

    any_pass = a_pass or b_pass or a_mirror_pass or b_mirror_pass

    if not any_pass:
        verdict = "BROAD_FALSIFIED"
    elif (a_pass or b_pass) and not (a_mirror_pass or b_mirror_pass):
        # Focus passed, mirror failed = healthy directional signal
        if a_pass:
            conc = a_focus.get("concentration", {})
            verdict = "PASS_A_FOCUS" if conc.get("concentration_gate_pass") else "CONCENTRATED_R1_PASS_A"
        else:
            conc = b_focus.get("concentration", {})
            verdict = "PASS_B_FOCUS" if conc.get("concentration_gate_pass") else "CONCENTRATED_R1_PASS_B"
    elif (a_mirror_pass or b_mirror_pass) and not (a_pass or b_pass):
        verdict = "MIRROR_PASS_FOCUS_FAIL"  # paradigm direction inverted
    else:
        verdict = "MULTI_QUADRANT_PASS"  # regime-dependent — flag for user

    metrics = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "halt_after": "R-1",
        "config": {
            "universe": ALT_UNIVERSE,
            "fee_round_trip": FEE_ROUND_TRIP,
            "hold_minutes": HOLD_MIN,
            "pre_window_offset_minutes": [PRE_WIN_START_OFFSET_MIN, PRE_WIN_END_OFFSET_MIN],
            "premium_z_lookback_bars": PREMIUM_Z_LOOKBACK_BARS,
            "theta_pv_z_delta": THETA_PV_Z_DELTA,
            "theta_oi_rel": THETA_OI_REL,
            "date_min": str(DATE_MIN),
            "date_max": str(DATE_MAX),
        },
        "diagnostics": {
            "n_boundaries": int(len(boundaries)),
            "n_events_raw": int(len(events)),
            "n_events_valid": int(len(events_valid)),
            "n_divergence_any_quadrant": int(len(divergence_any)),
            "trigger_rate_divergence": float(trigger_rate),
            "candidate_pool_size": int(len(signed_pool)),
            "gross_abs_median_bp": gross_abs_median_bp,
        },
        "symmetric_variants": quadrant_results,
        "verdict": verdict,
        "lessons_compliance": {
            "L1_perm_utils_used": True,
            "L2_three_gate_strict": True,
            "L3_sign_conditional_split": True,
            "L5_ohlcv_cache_used": True,
            "L11_sample_density_prescreen_ok": int(len(events_valid)) >= 30 * 4,
            "L16_concentration_block_emitted": True,
            "L19_symmetric_negative_test": True,
            "L20_partial_pass_narrow_scope_policy": "report-only at R-1",
        },
        "elapsed_seconds": round(time.time() - t0, 1),
    }

    out_path = RESEARCH_DIR / "r1__metrics.json"
    with out_path.open("w") as f:
        json.dump(metrics, f, indent=2, default=str)

    log.info("=" * 64)
    log.info("VERDICT: %s", verdict)
    log.info("  A focus (pv_z<0, oi>0, LONG): pass=%s n=%s", a_pass, a_focus.get("n_signals", "skip"))
    log.info("  A mirror SHORT:               pass=%s n=%s", a_mirror_pass, a_mirror.get("n_signals", "skip"))
    log.info("  B same-sign (pv_z>0, oi<0, SHORT): pass=%s n=%s", b_pass, b_focus.get("n_signals", "skip"))
    log.info("  B mirror LONG:                pass=%s n=%s", b_mirror_pass, b_mirror.get("n_signals", "skip"))
    log.info("written: %s (elapsed %.1fs)", out_path, time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
