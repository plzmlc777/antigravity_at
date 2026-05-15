"""R-1 PoC — funding_oi_bipolar_squeeze_event_retry_2025_2026 (paradigm 79).

RETRY of paradigm 73 (graveyarded 2026-05-15 turn 1 for Lesson #11 sample-density prescreen).

Mechanism (UNCHANGED — paradigm-agnostic re-validation)
=======================================================
At every Binance 8h funding window boundary (00/08/16 UTC), per symbol:
  funding_z   = z-score of funding rate over rolling 30 windows (~10 days)
  oi_growth_z = z-score of 8h-aligned OI %change over rolling 30 windows

Trigger:  |funding_z| >= F_THR  AND  oi_growth_z >= +OI_THR  (rising OI required)

Sub-cell A — long-crowded squeeze (funding_z > 0):
  longs paying premium AND OI rising → unsustainable → SHORT 240m hold
Sub-cell B — short-crowded squeeze (funding_z < 0):
  shorts paying premium AND OI rising → unsustainable → LONG  240m hold

Cooldown: 24h per symbol.

Sample density boost vs paradigm 73
===================================
- Universe: 6 → 14 syms (2.3x)
- Sample: ~1yr → 2.2yr alt / 1.5yr BTC (~2.2x effective)
- ~5x event count boost — focus cell expected ~50 events (was ~10)

Mandatory R-1 protocol (paradigm-architect spec 2026-05-15 turn 3)
==================================================================
- _perm_utils.fee_aware_perm_test + bootstrap_ci per sub-cell
- 3-gate strict per sub-cell:  signal_t_excess >= 2.0 AND ci_lower > 0
                               AND perm_p_two_sided <= 0.10
- Lesson #16 Concentration Gate (NEW) — auto-emit `concentration` block per sub-cell:
    * per-quarter t-stat distribution
    * per-symbol bootstrap CI
    * Gate: quarter_pos_t_ratio >= 0.5 AND symbol_ci_pos_ratio >= 0.30 AND n_symbols_ci_pos >= 3
- Lesson #8 NOT applicable (bipolar sub-cells ARE the mirror)
- ohlcv joblib cache mandatory
- Mint host explicit
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
log = logging.getLogger("funding_oi_bipolar_retry_r1")

# Universe = 14 OHLCV-aligned syms (paradigm 69 standard)
SYMBOLS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

MICROSTRUCT_DIR = ROOT / "runs" / "microstructure"

ROLL_WINDOWS = 30
HOLD_MINUTES = 240
HOLD_MINUTES_SENS = 480
COOLDOWN_MIN = 24 * 60

FUNDING_Z_THRS = [1.5, 2.0, 2.5]
OI_GROWTH_Z_THRS = [1.0, 1.5, 2.0]

FOCUS_F_THR = 2.0
FOCUS_OI_THR = 1.5
FOCUS_HOLD_COL = "fwd_ret_240m"

FEE_PER_TRADE = 0.0008

PARADIGM = "funding_oi_bipolar_squeeze_event_retry_2025_2026"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
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

    f = fund.set_index("funding_time")["funding_rate"]
    f_mean = f.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).mean()
    f_std = f.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).std(ddof=1)
    funding_z = (f - f_mean) / f_std

    ms_at_funding = ms.reindex(f.index, method="nearest", tolerance=pd.Timedelta("6min"))["open_interest"]
    oi_pct = ms_at_funding.pct_change(periods=1)
    oi_mean = oi_pct.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).mean()
    oi_std = oi_pct.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).std(ddof=1)
    oi_growth_z = (oi_pct - oi_mean) / oi_std

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


def apply_cooldown(events: pd.DataFrame, cooldown_min: int = COOLDOWN_MIN) -> pd.DataFrame:
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
# Lesson #16 Concentration Diagnostics (auto-emit per sub-cell)
# ---------------------------------------------------------------------------
def compute_concentration(triggered: pd.DataFrame, *, direction: int, hold_col: str) -> dict:
    """Return concentration diagnostics dict for the trigger set.

    Trigger DataFrame must have:
      index = entry timestamps
      columns: symbol, hold_col
    """
    if triggered.empty:
        return {"skip": "no_triggers"}

    df = triggered.copy()
    df["net_return"] = direction * df[hold_col].astype(float) - FEE_PER_TRADE
    df = df.dropna(subset=["net_return"])
    if df.empty:
        return {"skip": "no_net_returns"}

    df = df.reset_index().rename(columns={"index": "ts"})
    df["ts"] = pd.to_datetime(df["ts"])

    # (1) Per-quarter t-stat
    df["quarter"] = df["ts"].dt.to_period("Q").astype(str)

    def _t_stat(s):
        if len(s) >= 3 and s.std(ddof=1) > 0:
            return float(s.mean() / s.std(ddof=1) * (len(s) ** 0.5))
        return float("nan")

    per_q = df.groupby("quarter").agg(
        n_trades=("net_return", "size"),
        mean_bp=("net_return", lambda s: float(s.mean() * 10000)),
        t_stat=("net_return", _t_stat),
    ).reset_index()
    per_quarter_records = per_q.to_dict(orient="records")
    n_q_measurable = int((per_q["n_trades"] >= 10).sum())
    n_q_pos_t = int(((per_q["t_stat"] > 0) & (per_q["n_trades"] >= 10)).sum())

    # (2) Per-symbol bootstrap CI
    per_sym_records = []
    for sym, sub in df.groupby("symbol"):
        if len(sub) < 10:
            per_sym_records.append({"symbol": sym, "n_trades": int(len(sub)), "skip": "n<10"})
            continue
        ci = bootstrap_ci(sub["net_return"].values, n_boot=2000, block_size=1)
        per_sym_records.append({
            "symbol": sym,
            "n_trades": int(len(sub)),
            "mean_bp": float(sub["net_return"].mean() * 10000),
            "ci_lower_bp": float(ci["ci_lower"] * 10000),
            "ci_upper_bp": float(ci["ci_upper"] * 10000),
            "ci_lower_pos": bool(ci["ci_lower"] > 0),
        })
    n_sym_measurable = sum(1 for r in per_sym_records if r.get("skip") is None)
    n_sym_ci_pos = sum(1 for r in per_sym_records if r.get("ci_lower_pos") is True)

    return {
        "per_quarter_t_stats": per_quarter_records,
        "n_quarters_measurable": n_q_measurable,
        "n_quarters_pos_t": n_q_pos_t,
        "quarter_pos_t_ratio": (n_q_pos_t / n_q_measurable) if n_q_measurable else float("nan"),
        "per_symbol_bootstrap": per_sym_records,
        "n_symbols_measurable": n_sym_measurable,
        "n_symbols_ci_pos": n_sym_ci_pos,
        "symbol_ci_pos_ratio": (n_sym_ci_pos / n_sym_measurable) if n_sym_measurable else float("nan"),
    }


def apply_concentration_gate(conc: dict) -> dict:
    """Apply Lesson #16 Concentration Gate. Returns dict with pass + detail."""
    if "skip" in conc:
        return {"pass": False, "reason": conc["skip"]}
    q_ratio = conc.get("quarter_pos_t_ratio", float("nan"))
    s_ratio = conc.get("symbol_ci_pos_ratio", float("nan"))
    n_sym_pos = conc.get("n_symbols_ci_pos", 0)
    pass_q = np.isfinite(q_ratio) and q_ratio >= 0.5
    pass_s = np.isfinite(s_ratio) and s_ratio >= 0.30
    pass_min = n_sym_pos >= 3
    return {
        "pass": bool(pass_q and pass_s and pass_min),
        "quarter_pos_t_ratio>=0.5": bool(pass_q),
        "symbol_ci_pos_ratio>=0.30": bool(pass_s),
        "n_symbols_ci_pos>=3": bool(pass_min),
        "quarter_pos_t_ratio": q_ratio,
        "symbol_ci_pos_ratio": s_ratio,
        "n_symbols_ci_pos": n_sym_pos,
    }


# ---------------------------------------------------------------------------
# Sub-cell evaluation
# ---------------------------------------------------------------------------
def evaluate_subcell(
    triggered: pd.DataFrame,
    candidate_pool: pd.DataFrame,
    *,
    direction: int,
    hold_col: str,
    cell_label: str,
    f_thr: float,
    oi_thr: float,
    emit_concentration: bool = False,
) -> dict:
    if triggered.empty:
        return {
            "cell": cell_label,
            "f_thr": f_thr,
            "oi_thr": oi_thr,
            "hold_col": hold_col,
            "n_events": 0,
            "skipped": "no_triggers",
        }

    obs_gross = triggered[hold_col].astype(float).values
    obs_net = direction * obs_gross - FEE_PER_TRADE

    n = len(obs_net)
    mean_bp = float(obs_net.mean() * 10_000)

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

    pool_gross = candidate_pool[hold_col].astype(float).values
    pool_directional = direction * pool_gross
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
        candidate_pool_returns=pool_directional,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
    )
    ci = bootstrap_ci(obs_net, n_boot=2000, block_size=1)

    sig_t_excess = perm.get("signal_t_excess", float("nan"))
    ci_lower = ci.get("ci_lower", float("nan"))
    perm_p = perm.get("perm_p_two_sided", float("nan"))
    pass_excess = (np.isfinite(sig_t_excess) and sig_t_excess >= 2.0)
    pass_ci = (np.isfinite(ci_lower) and ci_lower > 0)
    pass_perm = (np.isfinite(perm_p) and perm_p <= 0.10)
    three_gate_pass = bool(pass_excess and pass_ci and pass_perm)

    per_sym = {}
    for sym, sub in triggered.groupby("symbol"):
        sub_net = direction * sub[hold_col].astype(float).values - FEE_PER_TRADE
        per_sym[sym] = {
            "n": int(len(sub_net)),
            "mean_bp": float(sub_net.mean() * 10_000) if len(sub_net) else None,
            "win_rate": float((sub_net > 0).mean()) if len(sub_net) else None,
        }

    result = {
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

    if emit_concentration:
        conc = compute_concentration(triggered, direction=direction, hold_col=hold_col)
        result["concentration"] = conc
        result["concentration_gate"] = apply_concentration_gate(conc)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    log.info("R-1 %s — universe %s", PARADIGM, SYMBOLS)

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
            "paradigm": PARADIGM,
            "phase": "R-1",
            "verdict": "GRAVEYARD_NO_DATA",
            "per_symbol_diag": per_sym_diag,
        }
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        return 1

    panel = pd.concat(all_events).sort_index()
    log.info("Panel total events with features: %d", len(panel))

    # Sample density prescreen
    n_panel = len(panel)
    log.info("Sample-density prescreen: panel=%d (paradigm 73 was %d ~9750)", n_panel, 9750)

    results = []
    for f_thr in FUNDING_Z_THRS:
        for oi_thr in OI_GROWTH_Z_THRS:
            for hold_col in ("fwd_ret_240m", "fwd_ret_480m"):
                trig_a_raw = panel[
                    (panel["funding_z"] >= f_thr)
                    & (panel["oi_growth_z"] >= oi_thr)
                ].copy()
                trig_a = apply_cooldown(trig_a_raw, COOLDOWN_MIN)

                trig_b_raw = panel[
                    (panel["funding_z"] <= -f_thr)
                    & (panel["oi_growth_z"] >= oi_thr)
                ].copy()
                trig_b = apply_cooldown(trig_b_raw, COOLDOWN_MIN)

                log.info(
                    "f=%.1f oi=%.1f hold=%s | A_raw=%d A_post=%d | B_raw=%d B_post=%d",
                    f_thr, oi_thr, hold_col,
                    len(trig_a_raw), len(trig_a),
                    len(trig_b_raw), len(trig_b),
                )

                # Emit concentration for focus cell only (cost: bootstrap_ci per sym)
                is_focus = (f_thr == FOCUS_F_THR and oi_thr == FOCUS_OI_THR and hold_col == FOCUS_HOLD_COL)

                res_a = evaluate_subcell(
                    triggered=trig_a, candidate_pool=panel,
                    direction=-1, hold_col=hold_col,
                    cell_label="A_long_crowded_short", f_thr=f_thr, oi_thr=oi_thr,
                    emit_concentration=is_focus,
                )
                res_b = evaluate_subcell(
                    triggered=trig_b, candidate_pool=panel,
                    direction=+1, hold_col=hold_col,
                    cell_label="B_short_crowded_long", f_thr=f_thr, oi_thr=oi_thr,
                    emit_concentration=is_focus,
                )
                results.append(res_a)
                results.append(res_b)

    # ----- Verdict at focus -----
    def _find(cells, prefix):
        for r in cells:
            if (r.get("cell", "").startswith(prefix)
                and r.get("f_thr") == FOCUS_F_THR
                and r.get("oi_thr") == FOCUS_OI_THR
                and r.get("hold_col") == FOCUS_HOLD_COL):
                return r
        return None

    focus_a = _find(results, "A_")
    focus_b = _find(results, "B_")

    def _three_gate(r):
        return bool(r and "skipped" not in r and r.get("three_gate_pass"))

    def _conc_gate(r):
        return bool(r and r.get("concentration_gate", {}).get("pass"))

    a_3gate = _three_gate(focus_a)
    b_3gate = _three_gate(focus_b)
    a_conc = _conc_gate(focus_a) if a_3gate else False
    b_conc = _conc_gate(focus_b) if b_3gate else False

    # Sub-cell verdict
    def _verdict(r, three_gate, conc):
        if r is None or "skipped" in r:
            return f"FAIL_{(r or {}).get('skipped', 'no_focus_cell')}"
        if three_gate and conc:
            return "PASS"
        if three_gate and not conc:
            return "CONCENTRATED_R1_PASS"
        return "FAIL_three_gate"

    a_verdict = _verdict(focus_a, a_3gate, a_conc)
    b_verdict = _verdict(focus_b, b_3gate, b_conc)

    # Overall paradigm verdict
    if a_verdict == "PASS" and b_verdict == "PASS":
        overall_verdict = "R-1_PASS_BOTH_SUBCELLS"
    elif a_verdict == "PASS" or b_verdict == "PASS":
        overall_verdict = f"R-1_HALF_PARADIGM__A:{a_verdict}__B:{b_verdict}"
    elif a_verdict.startswith("CONCENTRATED") or b_verdict.startswith("CONCENTRATED"):
        overall_verdict = f"R-1_CONCENTRATED__A:{a_verdict}__B:{b_verdict}"
    else:
        overall_verdict = f"R-1_GRAVEYARD__A:{a_verdict}__B:{b_verdict}"

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "snapshot_date": "2026-05-15",
        "retry_of": "funding_oi_bipolar_squeeze_event (paradigm 73, graveyard 2026-05-15 turn 1)",
        "retry_rationale": "Lesson #11 sample-density boost: universe 6->14 (2.3x), sample 1yr->2.2yr (2.2x)",
        "universe": SYMBOLS,
        "fee_per_trade": FEE_PER_TRADE,
        "cooldown_minutes": COOLDOWN_MIN,
        "rolling_window_events": ROLL_WINDOWS,
        "focus_cell": {"f_thr": FOCUS_F_THR, "oi_thr": FOCUS_OI_THR, "hold_col": FOCUS_HOLD_COL},
        "panel_total_events_with_features": int(n_panel),
        "per_symbol_diag": per_sym_diag,
        "grid_results": results,
        "focus_subcell_A": focus_a,
        "focus_subcell_B": focus_b,
        "subcell_A_three_gate_pass": a_3gate,
        "subcell_B_three_gate_pass": b_3gate,
        "subcell_A_concentration_gate_pass": a_conc,
        "subcell_B_concentration_gate_pass": b_conc,
        "subcell_A_verdict": a_verdict,
        "subcell_B_verdict": b_verdict,
        "verdict": overall_verdict,
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("Wrote %s", OUT_PATH)
    log.info("VERDICT: %s", overall_verdict)
    log.info("A (long-crowded SHORT) focus: %s | B (short-crowded LONG) focus: %s", a_verdict, b_verdict)

    def _log_cell(label, r):
        if r is None:
            log.info("  %s: NOT FOUND", label); return
        if "skipped" in r:
            log.info("  %s: SKIPPED (%s, n=%d)", label, r["skipped"], r.get("n_events", 0)); return
        log.info(
            "  %s: n=%d mean_bp=%.2f sigex=%.3f ci_lower_bp=%.2f perm_p=%.4f 3gate=%s",
            label, r["n_events"], r["mean_bp_after_fee"],
            r.get("signal_t_excess") or float("nan"),
            (r.get("ci_lower") or 0.0) * 10000,
            r.get("perm_p_two_sided") or float("nan"),
            r.get("three_gate_pass"),
        )
        if "concentration_gate" in r:
            cg = r["concentration_gate"]
            log.info(
                "    Concentration: q_ratio=%.2f s_ratio=%.2f n_sym_pos=%d gate=%s",
                cg.get("quarter_pos_t_ratio") or float("nan"),
                cg.get("symbol_ci_pos_ratio") or float("nan"),
                cg.get("n_symbols_ci_pos", 0),
                cg.get("pass"),
            )

    _log_cell("Focus A SHORT", focus_a)
    _log_cell("Focus B LONG", focus_b)

    return 0


if __name__ == "__main__":
    sys.exit(main())
