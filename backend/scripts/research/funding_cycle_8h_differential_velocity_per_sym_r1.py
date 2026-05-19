"""R-1 PoC — funding_cycle_8h_differential_velocity_per_sym (P3, batch ad-hoc 2026-05-19).

Hypothesis
==========
Per-sym 8h-to-8h Δfunding = funding(t) - funding(t-8h). Per-sym rolling history (30d, ~90 cycles)
z-score |z(Δf)| > 2.0 outlier → mean-reversion fade.

DNA distinct from:
- paradigm 96 sign flip: categorical (sign change) vs continuous (Δ magnitude z) — axis 2 mismatch
- paradigm 79 funding extreme level: level z vs velocity z — axis 2 (statistic class L vs Δ)
- paradigm 22 funding_carry: 3-sym specific continuous level vs 14-sym Δvelocity — axis 5 + axis 2
- P1 funding_velocity cross-section: cross-section z (universe-relative) vs per-sym history z (self-relative) — axis 4 (universe-level vs per-sym)

Protocol
========
- _perm_utils.fee_aware_perm_test + bootstrap_ci
- 3-gate strict per cell
- Concentration Gate on focus cell
- Lesson #19 Symmetric Negative Test (4-quadrant single batch)
- Life-changing 4-dim metrics

4-quadrant cells
================
For per-sym history z(Δf):
  A focus  : z(Δf) > +Z × LONG  (high velocity outlier → mean-reversal UP fade, expect LONG profit if direction = sign of overshoot)
  A mirror : z(Δf) > +Z × SHORT
  B mirror : z(Δf) < -Z × LONG
  B focus  : z(Δf) < -Z × SHORT

Note: focus direction selection follows P1 convention (high outlier → LONG, low outlier → SHORT).
"Mean reversion" here means dispersion of Δfunding reverts to mean of Δf, but trade direction
follows the convention "fade the overshoot": price OVER-extended one way after leverage shift → continue.
Equivalently: this is momentum hypothesis on the leverage velocity signal. If 4-quadrant fully resolves
mechanism direction we'll see asymmetric PASS pattern.

Substrate: binance_funding_rate (~2,736 cycles per sym, 2.5yr) + ohlcv joblib cache
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p3_funding_per_sym_velocity_r1")

SYMBOLS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

HOLD_MINUTES = {"fwd_ret_4h": 240, "fwd_ret_8h": 480, "fwd_ret_16h": 960}
FOCUS_HOLD_COL = "fwd_ret_8h"

Z_THRS = [1.5, 2.0, 2.5]
FOCUS_Z = 2.0

ROLL_WINDOWS = 90  # per-sym rolling history ~30d (90 cycles)
COOLDOWN_MIN = 8 * 60

FEE_PER_TRADE = 0.0008

PARADIGM = "funding_cycle_8h_differential_velocity_per_sym"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1__metrics.json"


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


def load_ohlcv_close(sym: str) -> pd.Series:
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    return df["close"].astype(float)


def build_panel():
    frames = []
    per_sym_diag = {}
    for sym in SYMBOLS:
        fund = load_funding(sym)
        if fund.empty:
            per_sym_diag[sym] = {"n_cycles": 0}
            continue
        close = load_ohlcv_close(sym)
        if close.empty:
            per_sym_diag[sym] = {"n_cycles": 0}
            continue

        f = fund.set_index("funding_time")["funding_rate"]
        delta_f = f.diff(periods=1)
        df_mean = delta_f.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).mean()
        df_std = delta_f.rolling(ROLL_WINDOWS, min_periods=ROLL_WINDOWS).std(ddof=1)
        z_delta_f = (delta_f - df_mean) / df_std

        rets = {col: [] for col in HOLD_MINUTES}
        for ts in f.index:
            entry_ts = ts + pd.Timedelta(minutes=1)
            try:
                p_entry = close.asof(entry_ts)
            except Exception:
                for col in HOLD_MINUTES:
                    rets[col].append(np.nan)
                continue
            if p_entry is None or not np.isfinite(p_entry) or p_entry <= 0:
                for col in HOLD_MINUTES:
                    rets[col].append(np.nan)
                continue
            for col, hold in HOLD_MINUTES.items():
                exit_ts = entry_ts + pd.Timedelta(minutes=hold)
                try:
                    p_exit = close.asof(exit_ts)
                except Exception:
                    rets[col].append(np.nan)
                    continue
                if p_exit is None or not np.isfinite(p_exit) or p_exit <= 0:
                    rets[col].append(np.nan)
                else:
                    rets[col].append(p_exit / p_entry - 1.0)

        df = pd.DataFrame({
            "delta_f": delta_f.values,
            "z_delta_f": z_delta_f.values,
            **{c: rets[c] for c in HOLD_MINUTES},
        }, index=f.index)
        df["symbol"] = sym
        df = df.dropna(subset=["z_delta_f", FOCUS_HOLD_COL])
        frames.append(df)
        per_sym_diag[sym] = {
            "n_cycles": int(len(df)),
            "min_ts": str(df.index.min()) if not df.empty else None,
            "max_ts": str(df.index.max()) if not df.empty else None,
        }
        log.info("[%s] %d cycles with z(Δf) features", sym, len(df))

    if not frames:
        return pd.DataFrame(), per_sym_diag
    panel = pd.concat(frames).sort_index()
    return panel, per_sym_diag


def apply_cooldown(events, cooldown_min: int = COOLDOWN_MIN):
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


def compute_concentration(triggered, *, direction, hold_col):
    if triggered.empty:
        return {"skip": "no_triggers"}
    df = triggered.copy()
    df["net_return"] = direction * df[hold_col].astype(float) - FEE_PER_TRADE
    df = df.dropna(subset=["net_return"])
    if df.empty:
        return {"skip": "no_net_returns"}
    df = df.reset_index().rename(columns={"index": "ts"})
    df["ts"] = pd.to_datetime(df["ts"])
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
    per_sym_records = []
    for sym, sub in df.groupby("symbol"):
        if len(sub) < 10:
            per_sym_records.append({"symbol": sym, "n_trades": int(len(sub)), "skip": "n<10"})
            continue
        ci = bootstrap_ci(sub["net_return"].values, n_boot=2000, block_size=1)
        per_sym_records.append({
            "symbol": sym, "n_trades": int(len(sub)),
            "mean_bp": float(sub["net_return"].mean() * 10000),
            "ci_lower_bp": float(ci["ci_lower"] * 10000),
            "ci_upper_bp": float(ci["ci_upper"] * 10000),
            "ci_lower_pos": bool(ci["ci_lower"] > 0),
        })
    n_sym_measurable = sum(1 for r in per_sym_records if r.get("skip") is None)
    n_sym_ci_pos = sum(1 for r in per_sym_records if r.get("ci_lower_pos") is True)
    return {
        "per_quarter_t_stats": per_quarter_records,
        "n_quarters_measurable": n_q_measurable, "n_quarters_pos_t": n_q_pos_t,
        "quarter_pos_t_ratio": (n_q_pos_t / n_q_measurable) if n_q_measurable else float("nan"),
        "per_symbol_bootstrap": per_sym_records,
        "n_symbols_measurable": n_sym_measurable, "n_symbols_ci_pos": n_sym_ci_pos,
        "symbol_ci_pos_ratio": (n_sym_ci_pos / n_sym_measurable) if n_sym_measurable else float("nan"),
    }


def apply_concentration_gate(conc):
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
        "quarter_pos_t_ratio": q_ratio, "symbol_ci_pos_ratio": s_ratio, "n_symbols_ci_pos": n_sym_pos,
    }


def life_changing_metrics(obs_net, hold_minutes, panel_span_days):
    n = len(obs_net)
    if n < 2 or panel_span_days <= 0:
        return {"skip": "insufficient_data"}
    yrs = panel_span_days / 365.25
    trades_per_year = n / yrs
    per_trade_edge_pct = float(obs_net.mean() * 100)
    hold_days = hold_minutes / 1440.0
    capital_util = trades_per_year * hold_days / 365.25
    sd = float(obs_net.std(ddof=1)) if n >= 2 else float("nan")
    per_trade_sharpe = float(obs_net.mean() / sd) if sd > 0 else float("nan")
    annualized_sharpe = per_trade_sharpe * (trades_per_year ** 0.5) if np.isfinite(per_trade_sharpe) else float("nan")
    return {
        "n_trades": int(n), "panel_span_days": float(panel_span_days),
        "trades_per_year": float(trades_per_year),
        "per_trade_edge_pct": per_trade_edge_pct, "capital_util": float(capital_util),
        "annualized_sharpe": float(annualized_sharpe),
        "gate_trades_per_year>=12": bool(trades_per_year >= 12),
        "gate_per_trade_edge_pct>=2": bool(per_trade_edge_pct >= 2.0),
        "gate_capital_util>=0.30": bool(capital_util >= 0.30),
        "gate_annualized_sharpe>=1.5": bool(np.isfinite(annualized_sharpe) and annualized_sharpe >= 1.5),
        "life_changing_all_pass": bool(
            trades_per_year >= 12 and per_trade_edge_pct >= 2.0
            and capital_util >= 0.30 and np.isfinite(annualized_sharpe) and annualized_sharpe >= 1.5
        ),
    }


def evaluate_quadrant(triggered, candidate_pool, *, direction, hold_col, cell_label, z_thr, is_focus, panel_span_days):
    if triggered.empty:
        return {"cell": cell_label, "z_thr": z_thr, "hold_col": hold_col, "n_events": 0, "skipped": "no_triggers"}
    obs_gross = triggered[hold_col].astype(float).values
    obs_net = direction * obs_gross - FEE_PER_TRADE
    n = len(obs_net)
    mean_bp = float(obs_net.mean() * 10_000)
    if n < 30:
        return {"cell": cell_label, "z_thr": z_thr, "hold_col": hold_col,
                "n_events": n, "mean_bp_after_fee": mean_bp, "skipped": "low_sample_<30"}
    pool_gross = candidate_pool[hold_col].astype(float).values
    pool_directional = direction * pool_gross
    if len(pool_directional) < n * 2:
        return {"cell": cell_label, "z_thr": z_thr, "hold_col": hold_col,
                "n_events": n, "mean_bp_after_fee": mean_bp, "skipped": "pool_too_small"}

    perm = fee_aware_perm_test(
        observed_net_returns=obs_net, candidate_pool_returns=pool_directional,
        fee_per_trade=FEE_PER_TRADE, n_perms=1000,
    )
    ci = bootstrap_ci(obs_net, n_boot=2000, block_size=1)
    sig_t_excess = perm.get("signal_t_excess", float("nan"))
    ci_lower = ci.get("ci_lower", float("nan"))
    perm_p = perm.get("perm_p_two_sided", float("nan"))
    pass_excess = (np.isfinite(sig_t_excess) and sig_t_excess >= 2.0)
    pass_ci = (np.isfinite(ci_lower) and ci_lower > 0)
    pass_perm = (np.isfinite(perm_p) and perm_p <= 0.10)
    three_gate_pass = bool(pass_excess and pass_ci and pass_perm)

    hold_min = HOLD_MINUTES.get(hold_col, 480)
    lc = life_changing_metrics(obs_net, hold_min, panel_span_days)

    per_sym = {}
    for sym, sub in triggered.groupby("symbol"):
        sub_net = direction * sub[hold_col].astype(float).values - FEE_PER_TRADE
        per_sym[sym] = {
            "n": int(len(sub_net)),
            "mean_bp": float(sub_net.mean() * 10_000) if len(sub_net) else None,
            "win_rate": float((sub_net > 0).mean()) if len(sub_net) else None,
        }

    result = {
        "cell": cell_label, "z_thr": z_thr, "hold_col": hold_col, "direction": direction,
        "n_events": n, "n_candidate_pool": int(len(pool_directional)),
        "mean_bp_after_fee": mean_bp, "win_rate": float((obs_net > 0).mean()),
        "obs_t": perm.get("obs_t"), "null_mean_t": perm.get("null_mean_t"),
        "signal_t_excess": sig_t_excess, "perm_p_two_sided": perm_p,
        "perm_p_one_sided_above": perm.get("perm_p_one_sided_above"),
        "perm_p_one_sided_below": perm.get("perm_p_one_sided_below"),
        "ci_mean": ci.get("mean"), "ci_lower": ci_lower, "ci_upper": ci.get("ci_upper"),
        "ci_prob_positive": ci.get("prob_positive"),
        "three_gate_pass": three_gate_pass,
        "three_gate_detail": {
            "signal_t_excess>=2.0": pass_excess,
            "ci_lower>0": pass_ci,
            "perm_p_two<=0.10": pass_perm,
        },
        "life_changing": lc,
        "per_symbol": per_sym,
    }
    if is_focus:
        conc = compute_concentration(triggered, direction=direction, hold_col=hold_col)
        result["concentration"] = conc
        result["concentration_gate"] = apply_concentration_gate(conc)
    return result


def main() -> int:
    log.info("R-1 %s — universe %s", PARADIGM, SYMBOLS)
    panel, per_sym_diag = build_panel()
    if panel.empty:
        log.error("Panel empty, aborting")
        OUT_PATH.write_text(json.dumps({
            "paradigm": PARADIGM, "phase": "R-1", "verdict": "GRAVEYARD_NO_DATA",
            "per_symbol_diag": per_sym_diag,
        }, indent=2, default=str))
        return 1

    n_panel = len(panel)
    span_days = (panel.index.max() - panel.index.min()).total_seconds() / 86400.0
    log.info("Panel %d cycles, span_days=%.1f (%.2f yr)", n_panel, span_days, span_days / 365.25)

    results = []
    for z_thr in Z_THRS:
        for hold_col in HOLD_MINUTES.keys():
            trig_high = apply_cooldown(panel[panel["z_delta_f"] > z_thr].copy(), COOLDOWN_MIN)
            trig_low = apply_cooldown(panel[panel["z_delta_f"] < -z_thr].copy(), COOLDOWN_MIN)
            log.info("z=%.1f hold=%s | high=%d low=%d", z_thr, hold_col, len(trig_high), len(trig_low))
            is_focus = (z_thr == FOCUS_Z and hold_col == FOCUS_HOLD_COL)
            results.append(evaluate_quadrant(
                trig_high, panel, direction=+1, hold_col=hold_col,
                cell_label="A_focus_high_LONG", z_thr=z_thr,
                is_focus=is_focus, panel_span_days=span_days,
            ))
            results.append(evaluate_quadrant(
                trig_high, panel, direction=-1, hold_col=hold_col,
                cell_label="A_mirror_high_SHORT", z_thr=z_thr,
                is_focus=False, panel_span_days=span_days,
            ))
            results.append(evaluate_quadrant(
                trig_low, panel, direction=+1, hold_col=hold_col,
                cell_label="B_mirror_low_LONG", z_thr=z_thr,
                is_focus=False, panel_span_days=span_days,
            ))
            results.append(evaluate_quadrant(
                trig_low, panel, direction=-1, hold_col=hold_col,
                cell_label="B_focus_low_SHORT", z_thr=z_thr,
                is_focus=is_focus, panel_span_days=span_days,
            ))

    def _find(prefix):
        for r in results:
            if (r.get("cell", "").startswith(prefix)
                and r.get("z_thr") == FOCUS_Z
                and r.get("hold_col") == FOCUS_HOLD_COL):
                return r
        return None

    fa = _find("A_focus_high_LONG")
    fa_m = _find("A_mirror_high_SHORT")
    fb_m = _find("B_mirror_low_LONG")
    fb = _find("B_focus_low_SHORT")

    def _three_gate(r): return bool(r and "skipped" not in r and r.get("three_gate_pass"))
    def _conc_gate(r): return bool(r and r.get("concentration_gate", {}).get("pass"))
    def _lc(r): return bool(r and r.get("life_changing", {}).get("life_changing_all_pass"))

    a_pass_3g, a_pass_cg, a_pass_lc = _three_gate(fa), _conc_gate(fa), _lc(fa)
    b_pass_3g, b_pass_cg, b_pass_lc = _three_gate(fb), _conc_gate(fb), _lc(fb)
    am_pass_3g = _three_gate(fa_m)
    bm_pass_3g = _three_gate(fb_m)

    any_focus_pass = a_pass_3g or b_pass_3g
    any_mirror_pass = am_pass_3g or bm_pass_3g

    if not (a_pass_3g or b_pass_3g or am_pass_3g or bm_pass_3g):
        verdict = "BROAD_FALSIFIED"
    elif any_focus_pass and any_mirror_pass:
        verdict = "BROAD_FALSIFIED_DEGENERATE_BOTH_DIRECTIONS"
    elif any_focus_pass:
        focus_cell = "A_focus_high_LONG" if a_pass_3g else "B_focus_low_SHORT"
        focus_conc = a_pass_cg if a_pass_3g else b_pass_cg
        focus_lc = a_pass_lc if a_pass_3g else b_pass_lc
        if focus_conc and focus_lc:
            verdict = f"PASS_R1_FULL__{focus_cell}"
        elif focus_conc and not focus_lc:
            verdict = f"NARROW_SCOPE_LIFE_CHANGING_FAIL__{focus_cell}"
        else:
            verdict = f"CONCENTRATED_R1_PASS__{focus_cell}"
    else:
        verdict = "BROAD_FALSIFIED_MIRROR_ONLY"

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "session_date": "2026-05-19",
        "campaign": "batch_ad_hoc_R1_funding_family_distinct_P3",
        "hypothesis": "Per-sym 8h-to-8h Δfunding history-z |z(Δf)|>2 outlier → mean-rev fade",
        "dna_distinct_from": [
            "paradigm 96 sign flip (categorical vs continuous)",
            "paradigm 79 extreme level (level z vs velocity z)",
            "paradigm 22 funding_carry (3 syms specific vs 14 syms)",
            "P1 funding_velocity cross_section (cs z vs per-sym history z)",
        ],
        "universe": SYMBOLS,
        "rolling_windows": ROLL_WINDOWS,
        "z_thresholds": Z_THRS,
        "focus": {"z_thr": FOCUS_Z, "hold_col": FOCUS_HOLD_COL},
        "fee_per_trade": FEE_PER_TRADE, "cooldown_minutes": COOLDOWN_MIN,
        "panel_total_cycles": int(n_panel),
        "panel_span_days": float(span_days),
        "per_symbol_diag": per_sym_diag,
        "grid_results": results,
        "focus_A_LONG": fa, "focus_A_mirror_SHORT": fa_m,
        "focus_B_mirror_LONG": fb_m, "focus_B_SHORT": fb,
        "verdict_components": {
            "A_focus_three_gate": a_pass_3g, "A_focus_concentration_gate": a_pass_cg, "A_focus_life_changing": a_pass_lc,
            "A_mirror_three_gate": am_pass_3g,
            "B_mirror_three_gate": bm_pass_3g,
            "B_focus_three_gate": b_pass_3g, "B_focus_concentration_gate": b_pass_cg, "B_focus_life_changing": b_pass_lc,
        },
        "verdict": verdict,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("Wrote %s", OUT_PATH)
    log.info("VERDICT: %s", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
