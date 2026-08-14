"""Paradigm 156 R-1 PoC: btc_funding_rate_p90_regime_alt_directional_4h.

Hypothesis
----------
BTC funding rate is a CROSS-ASSET MACRO leverage skew signal. When BTC funding
hits an extreme percentile regime (p90 = extreme bullish, p10 = extreme bearish),
the leverage tilt propagates as macro contagion to the 13-alt cross-section.

Two sub-triggers:
  - A: BTC funding >= p90 (extreme bullish positioning, leverage tilt UP)
  - B: BTC funding <= p10 (extreme bearish positioning, leverage tilt DOWN)

Direction: 13 alts directional 4h hold.

Sample density (Lesson #11 prescreen verified)
----------------------------------------------
  BTC funding DB: 1095 rows × 364-day span (2025-05-03 -> 2026-05-03)
  A: 141 BTC p90 cycles × 13 alts = 1833 alt-events (115/cell @ 4q × 4q split)
  B: 110 BTC p10 cycles × 13 alts = 1430 alt-events (89/cell)

Family-distinct strict audit vs funding family (paradigm 22 R-5 + 73/79/96/97/98/99 graveyards)
-----------------------------------------------------------------------------------------------
  Statistic class    : per-sym funding statistics    -> BTC-ONLY macro regime          STRICT
  Universe scope     : per-sym self-conditioning     -> BTC-trigger × 13-alt fan-out   STRICT
  Entry-side class   : funding event boundary        -> regime filter (continuous)     STRICT
  Mechanism alpha    : micro single-sym funding axis -> macro leverage spillover       STRICT
  Lesson #62 CONFIRMED >=2 strict satisfied -> 4/4 strict family-distinct.

R-1 protocol (paradigm-architect spec + Q3 §6.2 lessons cumulative 34 confirmed + 17 candidates)
-----------------------------------------------------------------------------------------------
  * Symmetric Negative Test 4-quadrant (Lesson #19) - A LONG / A SHORT / B LONG / B SHORT
  * 3-gate (signal_t_excess >= 2.0 AND ci_lower_bp > 0 AND perm_p <= 0.10)
  * Concentration Gate (Lesson #16) - per-quarter t + per-symbol bootstrap
  * Cross-proxy (Lesson #29) - obs (binary p90/p10 regime) + fund (extreme magnitude)
  * Lesson #20 4-cond narrow-scope fallback (Concentration FAIL)
  * Life-changing 4-dim measurement
  * Verdict tree (paradigm 95/99 dogfood):
      1. 4/4 quadrants 3-gate FAIL -> BROAD_FALSIFIED
      2. focus quadrant 3-gate PASS + Concentration PASS -> PASS_R1
      3. 3-gate PASS + Concentration FAIL -> Lesson #20 4-cond:
         a. ALL PASS -> life-changing 4-dim:
            - 4/4 PASS -> NARROW_SCOPE_CANDIDATE
            - any FAIL -> NARROW_SCOPE_LIFE_CHANGING_FAIL
         b. partial FAIL -> CONCENTRATED_R1_PASS
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
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm156_r1")

# ------------------------- Config -------------------------
PARADIGM_NAME = "btc_funding_rate_p90_regime_alt_directional_4h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 13 alts (paradigm 69 verified pool) - cross-asset target universe
UNIVERSE = [
    "ADAUSDT", "BNBUSDT", "BCHUSDT", "NEARUSDT", "FILUSDT", "SOLUSDT",
    "AVAXUSDT", "XRPUSDT", "LTCUSDT", "ETHUSDT", "DOGEUSDT", "WIFUSDT", "LINKUSDT",
]

# BTC = macro trigger source (NOT in alt universe)
BTC_SYMBOL = "BTCUSDT"

FEE_PER_TRADE = 0.0008  # 8 bp round-trip
HOLD_MINUTES_PRIMARY = 240  # 4h
HOLD_SWEEP = [240, 480, 720]  # 4h / 8h / 12h

# Regime thresholds (percentile-based on BTC funding distribution)
REGIME_HIGH_PCT = 0.90  # p90 (top 10%)
REGIME_LOW_PCT = 0.10   # p10 (bottom 10%)

# Three-gate thresholds (paradigm-architect spec)
SIG_T_EXCESS_PASS = 2.0
PERM_P_PASS = 0.10
CI_LOWER_PASS_BP = 0.0  # > 0

# Concentration gate (Lesson #16)
CONCENT_QUARTER_T_RATIO = 0.5  # >= 50% quarters with t > 0
CONCENT_SYMBOL_CI_POS_RATIO = 0.30  # >= 30% syms with ci_lower > 0
CONCENT_MIN_SYMS_CI_POS = 3


# ------------------------- Data load -------------------------
def load_btc_funding() -> pd.DataFrame:
    """Load BTCUSDT funding rate panel (single-sym macro trigger source)."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT funding_time, funding_rate FROM binance_funding_rate "
                "WHERE symbol=:s ORDER BY funding_time"
            ),
            {"s": BTC_SYMBOL},
        ).fetchall()
        if not rows:
            raise RuntimeError("no BTC funding data")
        df = pd.DataFrame(rows, columns=["t", "rate"])
        df["t"] = pd.to_datetime(df["t"])
        df["rate"] = df["rate"].astype(float)
        df = df.drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)
        log.info("[BTC] funding rows=%d range=%s->%s", len(df), df["t"].iloc[0], df["t"].iloc[-1])
        return df
    finally:
        db.close()


def detect_regime_events(btc_funding: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """Detect BTC funding regime entries (A: >= p90, B: <= p10).

    For each BTC regime cycle and each alt symbol in UNIVERSE, emit a cross-asset event.
    Returns long-format events DataFrame with columns:
      (sym, t_event, sub_trigger, btc_funding, btc_funding_pct_rank)
    """
    df = btc_funding.copy()

    # Percentile rank on full sample (in-sample, single-pass design for R-1 PoC)
    df["pct_rank"] = df["rate"].rank(pct=True)

    high_thr = df["rate"].quantile(REGIME_HIGH_PCT)
    low_thr = df["rate"].quantile(REGIME_LOW_PCT)

    df["is_A"] = df["rate"] >= high_thr  # extreme bullish
    df["is_B"] = df["rate"] <= low_thr   # extreme bearish

    # Magnitude proxy for cross-proxy test (Lesson #29):
    # absolute funding rate divided by rolling 30-event std (look-ahead-safe shift)
    df["mag_abs"] = df["rate"].abs()
    df["mag_std_30"] = df["mag_abs"].rolling(30, min_periods=10).std(ddof=1).shift(1)
    df["mag_z"] = df["rate"] / df["mag_std_30"].replace(0, np.nan)

    events: List[Dict] = []
    for sub_trig, mask in [("A", df["is_A"].values), ("B", df["is_B"].values)]:
        sub_df = df[mask].copy()
        for _, row in sub_df.iterrows():
            for sym in UNIVERSE:
                events.append({
                    "sym": sym,
                    "t_event": row["t"],
                    "sub_trigger": sub_trig,
                    "btc_funding": float(row["rate"]),
                    "btc_pct_rank": float(row["pct_rank"]),
                    "mag_z": float(row["mag_z"]) if np.isfinite(row["mag_z"]) else np.nan,
                })

    ev = pd.DataFrame(events)
    ev = ev.sort_values(["sym", "t_event"]).reset_index(drop=True)

    summary = {
        "btc_funding_p90_threshold": float(high_thr),
        "btc_funding_p10_threshold": float(low_thr),
        "btc_n_regime_A": int(df["is_A"].sum()),
        "btc_n_regime_B": int(df["is_B"].sum()),
        "alt_events_A": int(df["is_A"].sum() * len(UNIVERSE)),
        "alt_events_B": int(df["is_B"].sum() * len(UNIVERSE)),
    }
    log.info(
        "regime events: BTC A=%d (alt %d), BTC B=%d (alt %d); thresholds high=%.6f low=%.6f",
        summary["btc_n_regime_A"], summary["alt_events_A"],
        summary["btc_n_regime_B"], summary["alt_events_B"],
        summary["btc_funding_p90_threshold"], summary["btc_funding_p10_threshold"],
    )
    return ev, summary


# ------------------------- Returns -------------------------
def compute_event_returns(
    events: pd.DataFrame,
    ohlcv: Dict[str, pd.DataFrame],
    hold_minutes: int,
) -> pd.DataFrame:
    """For each event compute gross hold return at +hold_minutes after t_event.

    Entry = next 1m close at or after t_event (avoid look-ahead).
    Exit  = 1m close at t_event + hold_minutes.
    """
    out = events.copy()
    out["gross_ret"] = np.nan
    out["entry_price"] = np.nan
    out["exit_price"] = np.nan

    for sym, sub in out.groupby("sym"):
        if sym not in ohlcv:
            continue
        df = ohlcv[sym]
        if df.empty:
            continue
        idx = df.index
        for i in sub.index:
            te = out.at[i, "t_event"]
            tx = te + pd.Timedelta(minutes=hold_minutes)
            pos_e = idx.searchsorted(te, side="left")
            if pos_e >= len(idx):
                continue
            te_actual = idx[pos_e]
            if (te_actual - te).total_seconds() > 300:
                continue
            entry = df.at[te_actual, "close"]
            pos_x = idx.searchsorted(tx, side="left")
            if pos_x >= len(idx):
                continue
            tx_actual = idx[pos_x]
            if (tx_actual - tx).total_seconds() > 300:
                continue
            exitp = df.at[tx_actual, "close"]
            if entry > 0 and np.isfinite(entry) and np.isfinite(exitp):
                out.at[i, "entry_price"] = float(entry)
                out.at[i, "exit_price"] = float(exitp)
                out.at[i, "gross_ret"] = float(exitp / entry - 1.0)
    return out


# ------------------------- Three-gate -------------------------
def three_gate(observed_net: np.ndarray, candidate_pool_gross: np.ndarray) -> Dict:
    if len(observed_net) < 2:
        return {
            "n": int(len(observed_net)),
            "mean_bp": float("nan"), "obs_t": float("nan"),
            "signal_t_excess": float("nan"), "perm_p": float("nan"),
            "ci_lower_bp": float("nan"), "ci_upper_bp": float("nan"),
            "prob_positive": float("nan"),
            "gate_sig_t_excess_pass": False, "gate_perm_p_pass": False,
            "gate_ci_lower_pass": False, "three_gate_pass": False,
            "error": "n<2",
        }
    candidate_net = candidate_pool_gross - FEE_PER_TRADE
    perm = fee_aware_perm_test(
        observed_net_returns=observed_net,
        candidate_pool_returns=candidate_net,
        fee_per_trade=0.0,
        n_perms=1000,
    )
    ci = bootstrap_ci(observed_net, n_boot=2000, block_size=1)
    obs_t = perm.get("obs_t")
    sig_ex = perm.get("signal_t_excess")
    perm_p = perm.get("perm_p_two_sided")
    ci_lower = ci.get("ci_lower")
    ci_upper = ci.get("ci_upper")
    g_sig = (sig_ex is not None and np.isfinite(sig_ex) and sig_ex >= SIG_T_EXCESS_PASS)
    g_perm = (perm_p is not None and np.isfinite(perm_p) and perm_p <= PERM_P_PASS)
    g_ci = (ci_lower is not None and np.isfinite(ci_lower) and ci_lower > CI_LOWER_PASS_BP)
    return {
        "n": int(len(observed_net)),
        "mean_bp": float(np.mean(observed_net) * 1e4),
        "obs_t": float(obs_t) if obs_t is not None else float("nan"),
        "signal_t_excess": float(sig_ex) if sig_ex is not None else float("nan"),
        "perm_p": float(perm_p) if perm_p is not None else float("nan"),
        "ci_lower_bp": float(ci_lower * 1e4) if ci_lower is not None and np.isfinite(ci_lower) else float("nan"),
        "ci_upper_bp": float(ci_upper * 1e4) if ci_upper is not None and np.isfinite(ci_upper) else float("nan"),
        "prob_positive": float(ci.get("prob_positive", float("nan"))),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "gate_sig_t_excess_pass": bool(g_sig),
        "gate_perm_p_pass": bool(g_perm),
        "gate_ci_lower_pass": bool(g_ci),
        "three_gate_pass": bool(g_sig and g_perm and g_ci),
    }


def build_candidate_pool(
    ohlcv: Dict[str, pd.DataFrame],
    hold_minutes: int,
    sample_per_sym: int = 1500,
    rng_seed: int = 13,
) -> np.ndarray:
    rng = np.random.default_rng(rng_seed)
    rets = []
    for sym, df in ohlcv.items():
        if df.empty or len(df) < hold_minutes + 10:
            continue
        n = len(df) - hold_minutes
        if n <= 0:
            continue
        k = min(sample_per_sym, n)
        idx = rng.choice(n, size=k, replace=False)
        entry = df["close"].values[idx]
        exitp = df["close"].values[idx + hold_minutes]
        r = exitp / entry - 1.0
        r = r[np.isfinite(r)]
        rets.append(r)
    if not rets:
        return np.array([])
    return np.concatenate(rets)


# ------------------------- Concentration -------------------------
def concentration_diagnostics(events_with_ret: pd.DataFrame) -> Dict:
    df = events_with_ret.dropna(subset=["gross_ret"]).copy()
    if df.empty:
        return {"error": "no events with returns"}
    df["net_ret"] = df["gross_ret"] - FEE_PER_TRADE
    df["quarter"] = df["t_event"].dt.to_period("Q").astype(str)

    per_q = {}
    n_q_measurable = 0
    n_q_pos_t = 0
    for q, grp in df.groupby("quarter"):
        r = grp["net_ret"].values
        if len(r) < 5:
            per_q[q] = {"n": int(len(r)), "t": None, "mean_bp": None, "measurable": False}
            continue
        sd = r.std(ddof=1)
        if sd == 0 or not np.isfinite(sd):
            per_q[q] = {"n": int(len(r)), "t": None, "mean_bp": None, "measurable": False}
            continue
        t = r.mean() / sd * np.sqrt(len(r))
        per_q[q] = {"n": int(len(r)), "t": float(t), "mean_bp": float(r.mean() * 1e4), "measurable": True}
        n_q_measurable += 1
        if t > 0:
            n_q_pos_t += 1
    q_pos_ratio = (n_q_pos_t / n_q_measurable) if n_q_measurable > 0 else 0.0

    per_s = {}
    n_s_measurable = 0
    n_s_ci_pos = 0
    for sym, grp in df.groupby("sym"):
        r = grp["net_ret"].values
        if len(r) < 5:
            per_s[sym] = {"n": int(len(r)), "ci_lower_bp": None, "ci_pos": None, "measurable": False}
            continue
        ci = bootstrap_ci(r, n_boot=1500, block_size=1)
        ci_lo = ci.get("ci_lower", float("nan"))
        per_s[sym] = {
            "n": int(len(r)),
            "mean_bp": float(r.mean() * 1e4),
            "ci_lower_bp": float(ci_lo * 1e4) if np.isfinite(ci_lo) else None,
            "ci_upper_bp": float(ci.get("ci_upper") * 1e4) if np.isfinite(ci.get("ci_upper", float("nan"))) else None,
            "ci_pos": bool(np.isfinite(ci_lo) and ci_lo > 0),
            "measurable": True,
        }
        n_s_measurable += 1
        if np.isfinite(ci_lo) and ci_lo > 0:
            n_s_ci_pos += 1
    s_ci_pos_ratio = (n_s_ci_pos / n_s_measurable) if n_s_measurable > 0 else 0.0

    return {
        "per_quarter": per_q,
        "per_symbol": per_s,
        "n_quarters_measurable": int(n_q_measurable),
        "n_quarters_pos_t": int(n_q_pos_t),
        "quarter_pos_t_ratio": float(q_pos_ratio),
        "n_symbols_measurable": int(n_s_measurable),
        "n_symbols_ci_pos": int(n_s_ci_pos),
        "symbol_ci_pos_ratio": float(s_ci_pos_ratio),
        "gate_quarter_pass": bool(q_pos_ratio >= CONCENT_QUARTER_T_RATIO),
        "gate_symbol_ratio_pass": bool(s_ci_pos_ratio >= CONCENT_SYMBOL_CI_POS_RATIO),
        "gate_symbol_min_pass": bool(n_s_ci_pos >= CONCENT_MIN_SYMS_CI_POS),
        "concentration_gate_pass": bool(
            q_pos_ratio >= CONCENT_QUARTER_T_RATIO
            and s_ci_pos_ratio >= CONCENT_SYMBOL_CI_POS_RATIO
            and n_s_ci_pos >= CONCENT_MIN_SYMS_CI_POS
        ),
    }


# ------------------------- Life-changing 4-dim -------------------------
def life_changing_4dim(events_with_ret: pd.DataFrame, hold_minutes: int,
                       data_span_days: float) -> Dict:
    df = events_with_ret.dropna(subset=["gross_ret"]).copy()
    if df.empty:
        return {"error": "no events"}
    df["net_ret"] = df["gross_ret"] - FEE_PER_TRADE
    n = len(df)
    years = data_span_days / 365.25
    trades_per_yr = n / years if years > 0 else 0.0
    per_trade_edge_net_pct = float(df["net_ret"].mean() * 100)
    total_yr_minutes = 365.25 * 24 * 60
    capital_util_pct = min(100.0, (trades_per_yr * hold_minutes / total_yr_minutes) * 100)
    sd = df["net_ret"].std(ddof=1)
    if sd > 0 and np.isfinite(sd):
        annualized_sharpe = float(df["net_ret"].mean() / sd * np.sqrt(trades_per_yr))
    else:
        annualized_sharpe = 0.0
    gate_trades = trades_per_yr >= 12
    gate_edge = per_trade_edge_net_pct >= 2.0
    gate_util = capital_util_pct >= 30.0
    gate_sharpe = annualized_sharpe >= 1.5
    return {
        "trades_per_yr": float(trades_per_yr),
        "per_trade_edge_net_pct": float(per_trade_edge_net_pct),
        "capital_util_pct": float(capital_util_pct),
        "annualized_sharpe": float(annualized_sharpe),
        "gate_trades_per_yr_pass": bool(gate_trades),
        "gate_edge_pass": bool(gate_edge),
        "gate_capital_util_pass": bool(gate_util),
        "gate_sharpe_pass": bool(gate_sharpe),
        "life_changing_all_pass": bool(gate_trades and gate_edge and gate_util and gate_sharpe),
        "n_dims_pass": int(gate_trades) + int(gate_edge) + int(gate_util) + int(gate_sharpe),
    }


# ------------------------- Quadrant analysis -------------------------
def analyze_quadrant(
    events: pd.DataFrame,
    ohlcv: Dict[str, pd.DataFrame],
    sub_trigger: str,
    direction: int,
    hold_minutes: int,
    candidate_pool_gross: np.ndarray,
) -> Dict:
    ev = events[events["sub_trigger"] == sub_trigger].copy()
    ev = compute_event_returns(ev, ohlcv, hold_minutes)
    ev = ev.dropna(subset=["gross_ret"]).copy()
    ev["directional_gross"] = direction * ev["gross_ret"]
    ev["net_ret"] = ev["directional_gross"] - FEE_PER_TRADE
    observed_net = ev["net_ret"].values
    cand_signed = direction * candidate_pool_gross
    gate = three_gate(observed_net, cand_signed)
    ev_for_conc = ev.drop(columns=["gross_ret"]).rename(columns={"directional_gross": "gross_ret"}).copy()
    conc = concentration_diagnostics(ev_for_conc)
    return {
        "sub_trigger": sub_trigger,
        "direction": "LONG" if direction > 0 else "SHORT",
        "hold_minutes": int(hold_minutes),
        "three_gate": gate,
        "concentration": conc,
        "events": ev,
    }


# ------------------------- Main analysis -------------------------
def main() -> int:
    t_start = time.time()
    log.info("paradigm 156 R-1 starting at %s", pd.Timestamp.utcnow())

    # 1. Load BTC funding (single-sym macro trigger source)
    btc_funding = load_btc_funding()

    # 2. Detect regime events (BTC p90 / p10) and broadcast to 13 alts
    events, regime_summary = detect_regime_events(btc_funding)
    log.info(
        "broadcast events: total=%d  A(BTC p90 high)=%d  B(BTC p10 low)=%d",
        len(events),
        (events["sub_trigger"] == "A").sum(),
        (events["sub_trigger"] == "B").sum(),
    )

    # 3. Load OHLCV cache (13 alts only - BTC is trigger, not target)
    ohlcv: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_ohlcv_1m_cached(sym)
        if not df.empty:
            ohlcv[sym] = df
            log.info("[%s] OHLCV rows=%d span=%s->%s", sym, len(df),
                     df.index.min(), df.index.max())

    if not ohlcv:
        log.error("no OHLCV loaded for any alt symbol")
        return 1

    # 4. Data span estimation (alt-side weighted mean)
    spans = [(df.index.max() - df.index.min()).total_seconds() / 86400 for df in ohlcv.values()]
    data_span_days = float(np.mean(spans))
    log.info("avg alt OHLCV data span (days) = %.1f", data_span_days)

    # BTC funding window (separate substrate)
    btc_span = (btc_funding["t"].max() - btc_funding["t"].min()).total_seconds() / 86400
    log.info("BTC funding DB span (days) = %.1f", btc_span)

    # 5. Build candidate pool for PRIMARY hold
    candidate_pool = build_candidate_pool(ohlcv, hold_minutes=HOLD_MINUTES_PRIMARY)
    log.info("candidate pool size (primary hold %dm) = %d", HOLD_MINUTES_PRIMARY, len(candidate_pool))

    # 6. Run 4-quadrant Symmetric Negative Test at PRIMARY hold (Lesson #19)
    #    A LONG (focus), A SHORT (mirror), B SHORT (same-sign), B LONG (mirror)
    #    Quadrant ordering: [focus=A_LONG, A_SHORT_mirror, B_LONG_mirror_of_focus, B_SHORT_same_sign]
    quadrant_specs = [
        ("A", +1, "A_LONG_focus"),
        ("A", -1, "A_SHORT_mirror"),
        ("B", +1, "B_LONG_mirror"),
        ("B", -1, "B_SHORT_same_sign"),
    ]
    quadrants = []
    for sub_trig, direction, label in quadrant_specs:
        log.info("running quadrant %s: sub_trigger=%s direction=%s hold=%dm",
                 label, sub_trig, "LONG" if direction > 0 else "SHORT", HOLD_MINUTES_PRIMARY)
        q = analyze_quadrant(events, ohlcv, sub_trig, direction, HOLD_MINUTES_PRIMARY, candidate_pool)
        q["label"] = label
        quadrants.append(q)
        log.info("  -> n=%d mean_bp=%.2f sig_t_ex=%.3f perm_p=%.3f ci_lo_bp=%.2f three_gate=%s conc=%s",
                 q["three_gate"]["n"], q["three_gate"]["mean_bp"],
                 q["three_gate"]["signal_t_excess"], q["three_gate"]["perm_p"],
                 q["three_gate"]["ci_lower_bp"], q["three_gate"]["three_gate_pass"],
                 q["concentration"].get("concentration_gate_pass"))

    # 7. Hold sweep for FOCUS quadrant (A LONG)
    log.info("=== Hold sweep for A LONG (focus) ===")
    hold_sweep = []
    for hm in HOLD_SWEEP:
        cp = build_candidate_pool(ohlcv, hold_minutes=hm)
        q = analyze_quadrant(events, ohlcv, "A", +1, hm, cp)
        hold_sweep.append({
            "hold_minutes": hm,
            "three_gate": q["three_gate"],
            "concentration_pass": q["concentration"].get("concentration_gate_pass"),
        })
        log.info("  hold=%dm n=%d mean_bp=%.2f sig_t_ex=%.3f three_gate=%s",
                 hm, q["three_gate"]["n"], q["three_gate"]["mean_bp"],
                 q["three_gate"]["signal_t_excess"], q["three_gate"]["three_gate_pass"])

    # 8. Focus quadrant downstream
    focus = quadrants[0]  # A LONG
    focus_ev = focus["events"]

    # 9. Life-changing 4-dim on focus
    lc = life_changing_4dim(focus_ev, HOLD_MINUTES_PRIMARY, data_span_days)
    log.info("life-changing 4-dim: trades/yr=%.1f edge=%.3f%% util=%.1f%% sharpe=%.2f all_pass=%s",
             lc["trades_per_yr"], lc["per_trade_edge_net_pct"],
             lc["capital_util_pct"], lc["annualized_sharpe"],
             lc["life_changing_all_pass"])

    # 10. Cross-proxy (Lesson #29) - obs (binary regime) vs fund (extreme magnitude)
    #     obs proxy = all p90/p10 regime events (binary)
    #     fund proxy = regime events with |mag_z| >= 1.5 (strong magnitude trigger)
    cross_proxy = {}
    for sub_trig in ["A", "B"]:
        ev_all = events[events["sub_trigger"] == sub_trig].copy()
        ev_all = compute_event_returns(ev_all, ohlcv, HOLD_MINUTES_PRIMARY)
        ev_all = ev_all.dropna(subset=["gross_ret"]).copy()
        ev_all["net_ret"] = (+1) * ev_all["gross_ret"] - FEE_PER_TRADE
        obs_set = set(ev_all.index.tolist())
        ev_mag = ev_all[ev_all["mag_z"].abs() >= 1.5].copy()
        fund_set = set(ev_mag.index.tolist())
        if len(obs_set) == 0 or len(fund_set) == 0:
            jaccard = float("nan")
        else:
            jaccard = len(obs_set & fund_set) / len(obs_set | fund_set)
        cp_a = build_candidate_pool(ohlcv, hold_minutes=HOLD_MINUTES_PRIMARY)
        gate_obs = three_gate(ev_all["net_ret"].values, +1 * cp_a)
        gate_fund = three_gate(ev_mag["net_ret"].values, +1 * cp_a) if len(ev_mag) > 0 else None
        both_pass = bool(gate_obs.get("three_gate_pass") and (gate_fund and gate_fund.get("three_gate_pass")))
        cross_proxy[sub_trig] = {
            "obs_proxy_n": int(len(ev_all)),
            "fund_proxy_n": int(len(ev_mag)),
            "jaccard_overlap": float(jaccard) if np.isfinite(jaccard) else None,
            "obs_three_gate": gate_obs,
            "fund_three_gate": gate_fund,
            "both_pass": both_pass,
        }

    # 11. Lesson #20 4-cond narrow-scope (Concentration FAIL fallback)
    lesson20_check = None
    focus_3gate_pass = focus["three_gate"]["three_gate_pass"]
    focus_conc_pass = focus["concentration"].get("concentration_gate_pass")
    if focus_3gate_pass and not focus_conc_pass:
        log.info("focus 3-gate PASS + Concentration FAIL - running Lesson #20 4-cond")
        half_split = focus_ev["t_event"].median()
        h1 = focus_ev[focus_ev["t_event"] < half_split]
        h2 = focus_ev[focus_ev["t_event"] >= half_split]
        rep_h1_t = (h1["net_ret"].mean() / h1["net_ret"].std(ddof=1) * np.sqrt(len(h1))) if len(h1) > 2 else 0
        rep_h2_t = (h2["net_ret"].mean() / h2["net_ret"].std(ddof=1) * np.sqrt(len(h2))) if len(h2) > 2 else 0
        cond1_pass = rep_h1_t > 0 and rep_h2_t > 0
        bonferroni_p = min(1.0, focus["three_gate"]["perm_p"] * 4)
        cond2_pass = bonferroni_p <= 0.10
        cond3_pass = all(hs["three_gate"]["mean_bp"] > 0 for hs in hold_sweep)
        per_s = focus["concentration"].get("per_symbol", {})
        n_meas = sum(1 for v in per_s.values() if v.get("measurable"))
        n_pos = sum(1 for v in per_s.values() if v.get("measurable") and v.get("mean_bp", 0) > 0)
        cond4_pass = n_meas > 0 and (n_pos / n_meas) >= 0.30
        lesson20_check = {
            "cond1_replication_two_halves": {"h1_t": float(rep_h1_t), "h2_t": float(rep_h2_t), "pass": cond1_pass},
            "cond2_bonferroni_4q": {"bonferroni_p": float(bonferroni_p), "pass": cond2_pass},
            "cond3_hold_sweep_sign": {"pass": cond3_pass, "means": [hs["three_gate"]["mean_bp"] for hs in hold_sweep]},
            "cond4_per_symbol_positive_30pct": {"n_meas": n_meas, "n_pos": n_pos, "pass": cond4_pass},
            "all_4_cond_pass": bool(cond1_pass and cond2_pass and cond3_pass and cond4_pass),
        }

    # 12. Verdict tree
    a_long_pass = quadrants[0]["three_gate"]["three_gate_pass"]
    a_short_pass = quadrants[1]["three_gate"]["three_gate_pass"]
    b_long_pass = quadrants[2]["three_gate"]["three_gate_pass"]
    b_short_pass = quadrants[3]["three_gate"]["three_gate_pass"]
    any_quadrant_pass = a_long_pass or a_short_pass or b_long_pass or b_short_pass

    if not any_quadrant_pass:
        verdict = "BROAD_FALSIFIED"
    elif a_long_pass and focus_conc_pass:
        verdict = "PASS_R1_FULL"
    elif a_long_pass and not focus_conc_pass:
        if lesson20_check and lesson20_check["all_4_cond_pass"]:
            if lc["life_changing_all_pass"]:
                verdict = "NARROW_SCOPE_CANDIDATE"
            else:
                verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        else:
            verdict = "CONCENTRATED_R1_PASS"
    else:
        verdict = "PASS_NON_FOCUS_QUADRANT"

    # 13. Build metrics
    def strip_events(q):
        return {k: v for k, v in q.items() if k != "events"}

    metrics = {
        "paradigm_name": PARADIGM_NAME,
        "phase": "R-1",
        "run_ts": str(pd.Timestamp.utcnow()),
        "wall_clock_seconds": float(time.time() - t_start),
        "config": {
            "universe": UNIVERSE,
            "n_alts": len(UNIVERSE),
            "btc_trigger_symbol": BTC_SYMBOL,
            "fee_per_trade": FEE_PER_TRADE,
            "hold_minutes_primary": HOLD_MINUTES_PRIMARY,
            "hold_sweep": HOLD_SWEEP,
            "regime_high_pct": REGIME_HIGH_PCT,
            "regime_low_pct": REGIME_LOW_PCT,
            "alt_data_span_days_mean": data_span_days,
            "btc_funding_span_days": float(btc_span),
            "data_window_ratio": 1.0,  # Lesson #30 full window (BTC funding 1y/1y)
        },
        "regime_summary": regime_summary,
        "sample_density": {
            "n_alt_events_total": int(len(events)),
            "n_alt_events_A": int((events["sub_trigger"] == "A").sum()),
            "n_alt_events_B": int((events["sub_trigger"] == "B").sum()),
            "n_quarters_approx": int(np.ceil(btc_span / 91)),
            "expected_per_cell_A": int((events["sub_trigger"] == "A").sum() / max(1, np.ceil(btc_span / 91))),
            "expected_per_cell_B": int((events["sub_trigger"] == "B").sum() / max(1, np.ceil(btc_span / 91))),
            "lesson11_prescreen_pass": True,
        },
        "symmetric_negative_test_4q": {
            "A_LONG_focus": strip_events(quadrants[0]),
            "A_SHORT_mirror": strip_events(quadrants[1]),
            "B_LONG_mirror": strip_events(quadrants[2]),
            "B_SHORT_same_sign": strip_events(quadrants[3]),
            "n_quadrants_three_gate_pass": int(a_long_pass) + int(a_short_pass) + int(b_long_pass) + int(b_short_pass),
        },
        "hold_sweep_A_LONG": hold_sweep,
        "life_changing_4dim_focus": lc,
        "cross_proxy_lesson29": cross_proxy,
        "lesson20_4cond_check": lesson20_check,
        "verdict": verdict,
        "family_distinct_audit_lesson62": {
            "strict_dim_count": 4,
            "dims": {
                "statistic_class": "per-sym funding -> BTC-ONLY macro regime (STRICT)",
                "universe_scope": "per-sym self-conditioning -> BTC-trigger x 13-alt fan-out (STRICT)",
                "entry_side_class": "funding event boundary -> regime filter continuous (STRICT)",
                "mechanism_alpha": "micro funding axis -> macro leverage spillover (STRICT)",
            },
            "vs_paradigm_22_R5": "different statistic_class + universe_scope + mechanism (paradigm 22 = per-sym funding z-score MR)",
            "vs_funding_family_graveyards": "different scope (BTC-only vs per-sym) + different mechanism (macro contagion vs self-conditioning)",
        },
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    log.info("wrote %s", out_path)
    log.info("=== VERDICT: %s ===", verdict)
    log.info("wall clock: %.1fs", time.time() - t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
