"""R-1 PoC — funding_oi_bipolar_squeeze_event.

Hypothesis (NOVEL JOINT EVENT)
==============================
At every Binance 8h funding window boundary (00/08/16 UTC), per symbol:
  funding_z   = z-score of funding rate over rolling 30 windows (~10 days)
  oi_growth_z = z-score of 8h-aligned OI %change over rolling 30 windows

Trigger:  |funding_z| >= F_THR  AND  oi_growth_z >= +OI_THR  (rising OI required)

Sub-cell A — long-crowded squeeze (funding_z > 0):
  longs paying premium AND OI rising → unsustainable → SHORT 240m hold
Sub-cell B — short-crowded squeeze (funding_z < 0):
  shorts paying premium AND OI rising → unsustainable → LONG  240m hold

Cooldown: 24h per symbol.

Mechanism is standalone (NOT borrowing paradigm 69 vol-cascade or any seeded
mechanism). Domain combination = funding × OI joint event detection with
sign-bipolar sub-cells.

Mandatory R-1 protocol (handoff 2026-05-14)
-------------------------------------------
- _perm_utils.fee_aware_perm_test + bootstrap_ci per sub-cell
- 3-gate strict per sub-cell:  signal_t_excess >= 2.0 AND ci_lower > 0
                               AND perm_p_two_sided <= 0.10
- H5 sub-cell separation: A and B reported independently
- Mirror antipattern: bipolar sub-cells ARE the mirror — no extra mirror runs
- ohlcv joblib cache mandatory
- Mint host explicit
- Architect early-termination: if per-cell n<30 -> low-sample graveyard;
  if mean |bp| < 5 first-pass -> estimate-level graveyard

Output: backend/runs/research_track/funding_oi_bipolar_squeeze_event/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("funding_oi_bipolar_squeeze_event_r1")

# Universe = intersection (funding DB ∩ microstructure 5m OI ∩ ohlcv joblib cache)
SYMBOLS = ["AVAXUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT"]

MICROSTRUCT_DIR = ROOT / "runs" / "microstructure"

# Funding boundary cadence: 8h
ROLL_WINDOWS = 30                  # rolling z-score window (events) ~ 10 days
HOLD_MINUTES = 240                 # primary hold window
HOLD_MINUTES_SENS = 480            # sensitivity hold
COOLDOWN_MIN = 24 * 60             # 24h per symbol

FUNDING_Z_THRS = [1.5, 2.0, 2.5]
OI_GROWTH_Z_THRS = [1.0, 1.5, 2.0]

FEE_PER_TRADE = 0.0008             # 8 bp round-trip

OUT_DIR = ROOT / "runs" / "research_track" / "funding_oi_bipolar_squeeze_event"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1__metrics.json"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
def load_funding(sym: str) -> pd.DataFrame:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT funding_time, funding_rate FROM binance_funding_rate "
                "WHERE symbol=:s ORDER BY funding_time"
            ),
            {"s": sym},
        ).fetchall()
    finally:
        db.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["funding_time", "funding_rate"])
    df["funding_time"] = pd.to_datetime(df["funding_time"]).dt.floor("min")
    df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
    return df.dropna().drop_duplicates(subset=["funding_time"]).sort_values("funding_time")


def load_microstructure(sym: str) -> pd.DataFrame:
    path = MICROSTRUCT_DIR / f"{sym}_full_metrics.joblib"
    if not path.exists():
        return pd.DataFrame()
    df = joblib.load(path)
    if "open_interest" not in df.columns:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index)
    return df[["open_interest"]].dropna().sort_index()


def load_ohlcv_close(sym: str) -> pd.Series:
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    return df["close"].astype(float)


# ---------------------------------------------------------------------------
# Per-symbol event extraction
# ---------------------------------------------------------------------------
def build_events_for_symbol(sym: str) -> pd.DataFrame:
    """Return DataFrame indexed by funding_time with columns:
        funding_z, oi_growth_z, fwd_ret_240m, fwd_ret_480m

    Only rows with all features non-NaN are returned.
    """
    fund = load_funding(sym)
    if fund.empty:
        log.warning("[%s] no funding data", sym)
        return pd.DataFrame()
    ms = load_microstructure(sym)
    if ms.empty:
        log.warning("[%s] no microstructure", sym)
        return pd.DataFrame()
    close = load_ohlcv_close(sym)
    if close.empty:
        log.warning("[%s] no ohlcv", sym)
        return pd.DataFrame()

    # Compute funding rolling z
    f = fund.set_index("funding_time")["funding_rate"]
    f_mean = f.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).mean()
    f_std = f.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).std(ddof=1)
    funding_z = (f - f_mean) / f_std

    # OI snapshot at funding boundary (use nearest <= funding_time within 5 min)
    # microstructure is 5m freq starting at HH:00:00, HH:05:00 etc
    # funding boundaries are HH:00:00 (00,08,16 UTC) — exact alignment
    ms_at_funding = ms.reindex(f.index, method="nearest", tolerance=pd.Timedelta("6min"))["open_interest"]
    # OI %change from previous funding window (8h)
    oi_pct = ms_at_funding.pct_change(periods=1)
    oi_mean = oi_pct.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).mean()
    oi_std = oi_pct.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).std(ddof=1)
    oi_growth_z = (oi_pct - oi_mean) / oi_std

    # Forward returns: from funding_time + 1 min (post-boundary entry) to +HOLD min
    # Use close[entry] vs close[exit]
    rets_240 = []
    rets_480 = []
    for ts in f.index:
        entry_ts = ts + pd.Timedelta(minutes=1)
        exit_240 = entry_ts + pd.Timedelta(minutes=HOLD_MINUTES)
        exit_480 = entry_ts + pd.Timedelta(minutes=HOLD_MINUTES_SENS)
        try:
            p_entry = close.asof(entry_ts)
            p_240 = close.asof(exit_240)
            p_480 = close.asof(exit_480)
        except Exception:
            rets_240.append(np.nan)
            rets_480.append(np.nan)
            continue
        if (
            p_entry is None or p_240 is None or p_480 is None
            or not np.isfinite(p_entry) or not np.isfinite(p_240) or not np.isfinite(p_480)
            or p_entry <= 0
        ):
            rets_240.append(np.nan)
            rets_480.append(np.nan)
            continue
        rets_240.append(p_240 / p_entry - 1.0)
        rets_480.append(p_480 / p_entry - 1.0)

    out = pd.DataFrame({
        "funding_z": funding_z.values,
        "oi_growth_z": oi_growth_z.values,
        "fwd_ret_240m": rets_240,
        "fwd_ret_480m": rets_480,
    }, index=f.index)
    out["symbol"] = sym
    out = out.dropna(subset=["funding_z", "oi_growth_z", "fwd_ret_240m"])
    return out


# ---------------------------------------------------------------------------
# Cooldown enforcement
# ---------------------------------------------------------------------------
def apply_cooldown(events: pd.DataFrame, cooldown_min: int = COOLDOWN_MIN) -> pd.DataFrame:
    """Drop events within cooldown_min of the previous accepted event for the same symbol."""
    if events.empty:
        return events
    out_rows = []
    for sym, sub in events.groupby("symbol", sort=False):
        sub = sub.sort_index()
        last_ts = None
        for ts, row in sub.iterrows():
            if last_ts is not None and (ts - last_ts) < pd.Timedelta(minutes=cooldown_min):
                continue
            out_rows.append((ts, row))
            last_ts = ts
    if not out_rows:
        return events.iloc[0:0]
    idx = [r[0] for r in out_rows]
    rows = [r[1] for r in out_rows]
    return pd.DataFrame(rows, index=idx)


# ---------------------------------------------------------------------------
# Sub-cell evaluation
# ---------------------------------------------------------------------------
def evaluate_subcell(
    triggered: pd.DataFrame,
    candidate_pool: pd.DataFrame,
    *,
    direction: int,         # +1 LONG, -1 SHORT
    hold_col: str,
    cell_label: str,
    f_thr: float,
    oi_thr: float,
) -> dict:
    """Apply direction + fee, run fee-aware perm + bootstrap CI."""
    if triggered.empty:
        return {
            "cell": cell_label,
            "f_thr": f_thr,
            "oi_thr": oi_thr,
            "hold_col": hold_col,
            "n_events": 0,
            "skipped": "no_triggers",
        }

    # Net per-trade returns: direction * gross - fee
    obs_gross = triggered[hold_col].astype(float).values
    obs_net = direction * obs_gross - FEE_PER_TRADE

    n = len(obs_net)
    mean_bp = float(obs_net.mean() * 10_000)

    # Architect early-termination guards
    if n < 30:
        return {
            "cell": cell_label,
            "f_thr": f_thr,
            "oi_thr": oi_thr,
            "hold_col": hold_col,
            "n_events": n,
            "mean_bp_after_fee": mean_bp,
            "skipped": "low_sample_<30",
        }

    # Candidate pool = ALL non-trigger funding-window forward returns,
    # SAME direction applied (this gives the fee-saturated null for THIS direction).
    pool_gross = candidate_pool[hold_col].astype(float).values
    pool_directional = direction * pool_gross  # direction-applied GROSS
    if len(pool_directional) < n * 2:
        return {
            "cell": cell_label,
            "f_thr": f_thr,
            "oi_thr": oi_thr,
            "hold_col": hold_col,
            "n_events": n,
            "mean_bp_after_fee": mean_bp,
            "skipped": "pool_too_small",
        }

    perm = fee_aware_perm_test(
        observed_net_returns=obs_net,
        candidate_pool_returns=pool_directional,  # gross; fee applied inside
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
    )
    ci = bootstrap_ci(obs_net, n_boot=2000, block_size=1)

    # Three-gate verdict
    sig_t_excess = perm.get("signal_t_excess", float("nan"))
    ci_lower = ci.get("ci_lower", float("nan"))
    perm_p = perm.get("perm_p_two_sided", float("nan"))
    pass_excess = (np.isfinite(sig_t_excess) and sig_t_excess >= 2.0)
    pass_ci = (np.isfinite(ci_lower) and ci_lower > 0)
    pass_perm = (np.isfinite(perm_p) and perm_p <= 0.10)
    three_gate_pass = bool(pass_excess and pass_ci and pass_perm)

    # Per-symbol breakdown
    per_sym = {}
    for sym, sub in triggered.groupby("symbol"):
        sub_net = direction * sub[hold_col].astype(float).values - FEE_PER_TRADE
        per_sym[sym] = {
            "n": int(len(sub_net)),
            "mean_bp": float(sub_net.mean() * 10_000) if len(sub_net) else None,
            "win_rate": float((sub_net > 0).mean()) if len(sub_net) else None,
        }

    return {
        "cell": cell_label,
        "f_thr": f_thr,
        "oi_thr": oi_thr,
        "hold_col": hold_col,
        "direction": direction,
        "n_events": n,
        "n_candidate_pool": int(len(pool_directional)),
        "mean_bp_after_fee": mean_bp,
        "win_rate": float((obs_net > 0).mean()),
        "obs_t": perm.get("obs_t"),
        "null_mean_t": perm.get("null_mean_t"),
        "null_std_t": perm.get("null_std_t"),
        "signal_t_excess": sig_t_excess,
        "perm_p_two_sided": perm_p,
        "perm_p_one_sided_above": perm.get("perm_p_one_sided_above"),
        "perm_p_one_sided_below": perm.get("perm_p_one_sided_below"),
        "ci_mean": ci.get("mean"),
        "ci_lower": ci_lower,
        "ci_upper": ci.get("ci_upper"),
        "ci_prob_positive": ci.get("prob_positive"),
        "three_gate_pass": three_gate_pass,
        "three_gate_detail": {
            "signal_t_excess>=2.0": pass_excess,
            "ci_lower>0": pass_ci,
            "perm_p_two<=0.10": pass_perm,
        },
        "per_symbol": per_sym,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    log.info("R-1 funding_oi_bipolar_squeeze_event — universe %s", SYMBOLS)

    # Build per-symbol event tables
    all_events = []
    per_sym_diag = {}
    for sym in SYMBOLS:
        ev = build_events_for_symbol(sym)
        per_sym_diag[sym] = {
            "n_funding_events_with_features": int(len(ev)),
            "min_ts": str(ev.index.min()) if not ev.empty else None,
            "max_ts": str(ev.index.max()) if not ev.empty else None,
        }
        log.info("[%s] %d events with full features", sym, len(ev))
        if not ev.empty:
            all_events.append(ev)

    if not all_events:
        log.error("No events across universe — aborting")
        out = {
            "paradigm": "funding_oi_bipolar_squeeze_event",
            "phase": "R-1",
            "verdict": "GRAVEYARD_NO_DATA",
            "per_symbol_diag": per_sym_diag,
        }
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        return 1

    panel = pd.concat(all_events).sort_index()
    log.info("Panel total events with features: %d", len(panel))

    # -----------------------------------------------------------------
    # Loop over (funding_z thr, oi_growth_z thr) grid for each sub-cell
    # -----------------------------------------------------------------
    results = []
    for f_thr in FUNDING_Z_THRS:
        for oi_thr in OI_GROWTH_Z_THRS:
            for hold_col in ("fwd_ret_240m", "fwd_ret_480m"):
                # Sub-cell A: long-crowded squeeze (funding_z > 0)
                trig_a_raw = panel[
                    (panel["funding_z"] >= f_thr)
                    & (panel["oi_growth_z"] >= oi_thr)
                ].copy()
                trig_a = apply_cooldown(trig_a_raw, COOLDOWN_MIN)

                # Sub-cell B: short-crowded squeeze (funding_z < 0)
                trig_b_raw = panel[
                    (panel["funding_z"] <= -f_thr)
                    & (panel["oi_growth_z"] >= oi_thr)
                ].copy()
                trig_b = apply_cooldown(trig_b_raw, COOLDOWN_MIN)

                log.info(
                    "f_thr=%.1f oi_thr=%.1f hold=%s | A_raw=%d A_post=%d | B_raw=%d B_post=%d",
                    f_thr, oi_thr, hold_col,
                    len(trig_a_raw), len(trig_a),
                    len(trig_b_raw), len(trig_b),
                )

                # Candidate pool = all panel rows (the universe of possible 8h windows)
                # for fee-aware perm. Sub-cell-specific direction is applied inside evaluate.
                res_a = evaluate_subcell(
                    triggered=trig_a, candidate_pool=panel,
                    direction=-1, hold_col=hold_col,
                    cell_label="A_long_crowded_short", f_thr=f_thr, oi_thr=oi_thr,
                )
                res_b = evaluate_subcell(
                    triggered=trig_b, candidate_pool=panel,
                    direction=+1, hold_col=hold_col,
                    cell_label="B_short_crowded_long", f_thr=f_thr, oi_thr=oi_thr,
                )
                results.append(res_a)
                results.append(res_b)

    # -----------------------------------------------------------------
    # Verdict — best cell per sub-cell type
    # -----------------------------------------------------------------
    def _is_eval(r):
        return "skipped" not in r

    cell_a_evald = [r for r in results if r["cell"].startswith("A_") and _is_eval(r)]
    cell_b_evald = [r for r in results if r["cell"].startswith("B_") and _is_eval(r)]

    def best(cells):
        if not cells:
            return None
        # Rank by signal_t_excess primarily
        return max(cells, key=lambda x: (x.get("signal_t_excess") or -1e9))

    best_a = best(cell_a_evald)
    best_b = best(cell_b_evald)

    a_pass = bool(best_a and best_a.get("three_gate_pass"))
    b_pass = bool(best_b and best_b.get("three_gate_pass"))
    any_pass = a_pass or b_pass

    if any_pass:
        verdict = "R-1_PASS_AWAIT_USER_APPROVAL_FOR_R-2"
    else:
        # Determine reason — was it low-sample, or just failed gates?
        a_reason = "no_eval_results" if not best_a else (
            "low_sample" if best_a.get("n_events", 0) < 30 else "gates_failed"
        )
        b_reason = "no_eval_results" if not best_b else (
            "low_sample" if best_b.get("n_events", 0) < 30 else "gates_failed"
        )
        verdict = f"GRAVEYARD_R1__A:{a_reason}__B:{b_reason}"

    out = {
        "paradigm": "funding_oi_bipolar_squeeze_event",
        "phase": "R-1",
        "snapshot_date": "2026-05-15",
        "universe": SYMBOLS,
        "fee_per_trade": FEE_PER_TRADE,
        "cooldown_minutes": COOLDOWN_MIN,
        "rolling_window_events": ROLL_WINDOWS,
        "panel_total_events_with_features": int(len(panel)),
        "per_symbol_diag": per_sym_diag,
        "grid_results": results,
        "best_subcell_A_long_crowded_short": best_a,
        "best_subcell_B_short_crowded_long": best_b,
        "subcell_A_three_gate_pass": a_pass,
        "subcell_B_three_gate_pass": b_pass,
        "verdict": verdict,
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("Wrote %s", OUT_PATH)
    log.info("VERDICT: %s", verdict)
    if best_a:
        log.info(
            "Best A (long-crowded SHORT): f=%.1f oi=%.1f hold=%s n=%d mean_bp=%.2f sig_t_excess=%.3f ci_lower=%.6f perm_p=%.3f three_gate=%s",
            best_a["f_thr"], best_a["oi_thr"], best_a["hold_col"],
            best_a["n_events"], best_a["mean_bp_after_fee"],
            best_a["signal_t_excess"] or float("nan"),
            best_a["ci_lower"] or float("nan"),
            best_a["perm_p_two_sided"] or float("nan"),
            best_a["three_gate_pass"],
        )
    if best_b:
        log.info(
            "Best B (short-crowded LONG): f=%.1f oi=%.1f hold=%s n=%d mean_bp=%.2f sig_t_excess=%.3f ci_lower=%.6f perm_p=%.3f three_gate=%s",
            best_b["f_thr"], best_b["oi_thr"], best_b["hold_col"],
            best_b["n_events"], best_b["mean_bp_after_fee"],
            best_b["signal_t_excess"] or float("nan"),
            best_b["ci_lower"] or float("nan"),
            best_b["perm_p_two_sided"] or float("nan"),
            best_b["three_gate_pass"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
