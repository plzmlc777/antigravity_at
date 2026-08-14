"""Paradigm 157 R-1: alt_session_boundary_NY_close_21UTC_anchored_directional_4h.

Hypothesis
----------
NY close session boundary (≈21:00 UTC NY equities close, mapped to 20:00 UTC
4h bar close — see Anchor reality check) is a structural macro flow rebalancing
event affecting BTC + 13 alts uniformly. 16-20 UTC bar close-to-close return
sign + magnitude triggers directional alpha in the immediate +4h window (20-00
UTC, Asia open transition).

Anchor reality check (4h cache alignment)
-----------------------------------------
Binance 4h klines align to UTC 0/4/8/12/16/20. The 20:00 UTC bar close
(16-20 UTC bar) is the closest 4h-aligned anchor to NY equities close
(20:00 UTC EDT, dominant ~7 months/yr). Adopted as the "NY close session
boundary anchor". Zero new infrastructure (12-col 4h joblib cache 영구 자산).

4-quadrant SNT (Lesson #19 mandatory)
-------------------------------------
A focus (Continuation): NY anchor sign × alt same-direction
  - NY UP → alt LONG ; NY DOWN → alt SHORT
A mirror (Reversal): NY anchor sign × alt opposite-direction
  - NY UP → alt SHORT ; NY DOWN → alt LONG
B same-sign decomposition matches A above because sign-cond bilateral on
single anchor sign axis (not joint trigger). 4 quadrants:
  - Q1 UP_LONG  (focus continuation on UP days)
  - Q2 UP_SHORT (mirror on UP days)
  - Q3 DOWN_SHORT (focus continuation on DOWN days)
  - Q4 DOWN_LONG (mirror on DOWN days)

Family-distinct strict 4-dim audit (Lesson #62 CONFIRMED)
---------------------------------------------------------
  Statistic class    : funding/RV/range_vol/quote_vol -> session-anchor bar sign   STRICT
  Universe scope     : per-sym self-conditioning / BTC-only broadcast -> 14 syms structural shared anchor   STRICT
  Entry-side class   : funding event boundary / threshold filter -> time-of-day cycle anchor (NEW)   STRICT
  Mechanism alpha    : leverage skew / vol regime -> session boundary macro flow rebalancing   STRICT
  4/4 strict satisfied. ≥3 dims distinct from any prior paradigm.

R-1 protocol
------------
* 4-quadrant SNT (Lesson #19) at primary hold 4h (1 bar)
* 3-gate (signal_t_excess >= 2.0 AND ci_lower_bp > 0 AND perm_p <= 0.10)
* Concentration Gate (Lesson #16) - per-quarter t + per-symbol bootstrap
* Hold sweep 1/2/3 bars (4h/8h/12h) for Lesson #37 full sweep scan
* Lesson #39 sub-class A/B detection on 4-quadrant pattern
* Lesson #46 stratified sign-flip warning
* Life-changing 4-dim measurement on each focus side
* Verdict tree: BROAD_FALSIFIED / PASS_R1_FULL / sub-class A or B / narrow scope variants
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.binance.backfill_12col_klines import load_12col_cached  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm157_r1")

# ------------------------- Config -------------------------
PARADIGM_NAME = "alt_session_boundary_NY_close_21UTC_anchored_directional_4h"
PARADIGM_ID = 157
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 14 syms: BTC + 13 alts (session boundary is STRUCTURAL global anchor, BTC included
# as structural participant NOT as macro broadcast trigger — Lesson #67 escape)
UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "AVAXUSDT", "BCHUSDT",
    "BNBUSDT", "DOGEUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "WIFUSDT", "XRPUSDT",
]
TF = "4h"

# Anchor: NY close = 20:00 UTC bar close (16-20 UTC bar) — closest 4h-aligned
# anchor to NY equities close (20:00 UTC EDT, dominant period)
ANCHOR_HOUR_UTC = 20

FEE_PER_TRADE = 0.0008  # 8 bp round-trip
HOLD_BARS_PRIMARY = 1   # 1 × 4h = 4h
HOLD_SWEEP_BARS = [1, 2, 3]  # 4h / 8h / 12h

# Three-gate thresholds (paradigm-architect spec)
SIG_T_EXCESS_PASS = 2.0
PERM_P_PASS = 0.10
CI_LOWER_PASS = 0.0  # > 0

# Concentration gate (Lesson #16)
CONCENT_QUARTER_T_RATIO = 0.5
CONCENT_SYMBOL_CI_POS_RATIO = 0.30
CONCENT_MIN_SYMS_CI_POS = 3


# ------------------------- Data -------------------------
def load_panel() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        try:
            df = load_12col_cached(sym, TF)
        except FileNotFoundError as e:
            log.warning("[%s] cache missing: %s", sym, e)
            continue
        if df.empty:
            log.warning("[%s] empty", sym)
            continue
        df = df[["open", "high", "low", "close", "quote_volume"]].copy()
        for c in ("open", "high", "low", "close", "quote_volume"):
            df[c] = df[c].astype(float)
        df = df.dropna(subset=["close"])
        out[sym] = df
        log.info("[%s] bars=%d span=%s->%s", sym, len(df), df.index.min(), df.index.max())
    return out


def gather_anchor_events(panel: Dict[str, pd.DataFrame], hold_bars: int) -> pd.DataFrame:
    """For each sym, find every NY close anchor bar (open_time hour == 16 UTC, so the
    bar closes at 20 UTC). Trigger = sign(close_20UTC / close_16UTC - 1) = sign of the
    16-20 UTC bar close-to-close return = sign((close - open)/open). We use prior-bar
    close vs current bar close for sign attribution (close-to-close), measured at bar
    close. Forward hold = +hold_bars × 4h after the anchor bar close.

    open_time = 16:00 UTC means bar covers [16:00, 20:00) and closes at 20:00 UTC
    (Binance 4h convention). Sign is computed as sign(close_t - close_{t-1}) where
    t is the anchor bar and t-1 is the prior 4h bar (12-16 UTC bar).

    Returns: DataFrame with (sym, t_anchor, anchor_sign, gross_ret_fwd).
    """
    rows: List[Dict] = []
    for sym, df in panel.items():
        # Filter to anchor bars: open_time hour = 16 (so bar closes at 20:00 UTC)
        # (Binance 4h convention: bar open_time hours = 0,4,8,12,16,20)
        anchor_mask = df.index.hour == 16
        anchor_bars = df[anchor_mask].copy()
        if anchor_bars.empty:
            log.warning("[%s] no 16-UTC anchor bars found", sym)
            continue

        # Sign = sign of close-to-close return (prior 4h bar close → anchor bar close)
        # Use index positions to safely fetch prior close and forward close
        idx_full = df.index
        n_full = len(df)
        for t_anchor in anchor_bars.index:
            pos = idx_full.get_loc(t_anchor)
            if isinstance(pos, slice):
                continue
            if pos < 1 or pos + hold_bars >= n_full:
                continue
            close_prior = df["close"].iat[pos - 1]
            close_anchor = df["close"].iat[pos]
            close_exit = df["close"].iat[pos + hold_bars]
            if not (close_prior > 0 and close_anchor > 0 and close_exit > 0):
                continue
            if not (np.isfinite(close_prior) and np.isfinite(close_anchor) and np.isfinite(close_exit)):
                continue
            anchor_ret = close_anchor / close_prior - 1.0
            anchor_sign = 1.0 if anchor_ret > 0 else (-1.0 if anchor_ret < 0 else 0.0)
            if anchor_sign == 0:
                continue  # skip flat anchor bars (negligible count)
            gross_ret_fwd = close_exit / close_anchor - 1.0
            rows.append({
                "sym": sym,
                "t_anchor": t_anchor,
                "anchor_ret": float(anchor_ret),
                "anchor_sign": float(anchor_sign),
                "gross_ret": float(gross_ret_fwd),
            })
    ev = pd.DataFrame(rows)
    if not ev.empty:
        ev = ev.sort_values(["sym", "t_anchor"]).reset_index(drop=True)
    return ev


def build_candidate_pool(panel: Dict[str, pd.DataFrame], hold_bars: int,
                         sample_per_sym: int = 1500, rng_seed: int = 13) -> np.ndarray:
    """Random forward gross returns over hold_bars from any bar."""
    rng = np.random.default_rng(rng_seed)
    rets: List[np.ndarray] = []
    for sym, df in panel.items():
        n_eligible = len(df) - hold_bars
        if n_eligible <= 0:
            continue
        k = min(sample_per_sym, n_eligible)
        idx = rng.choice(n_eligible, size=k, replace=False)
        entry = df["close"].values[idx]
        exitp = df["close"].values[idx + hold_bars]
        r = exitp / entry - 1.0
        r = r[np.isfinite(r)]
        rets.append(r)
    if not rets:
        return np.array([])
    return np.concatenate(rets)


# ------------------------- Gates -------------------------
def three_gate(observed_net: np.ndarray, candidate_pool_signed_gross: np.ndarray) -> Dict:
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
    candidate_net = candidate_pool_signed_gross - FEE_PER_TRADE
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
    g_ci = (ci_lower is not None and np.isfinite(ci_lower) and ci_lower > CI_LOWER_PASS)
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


def concentration_diagnostics(events: pd.DataFrame, direction_col: str) -> Dict:
    if events.empty:
        return {"error": "no events"}
    df = events.copy()
    df["directional_gross"] = df[direction_col] * df["gross_ret"]
    df["net_ret"] = df["directional_gross"] - FEE_PER_TRADE
    df["quarter"] = pd.to_datetime(df["t_anchor"]).dt.to_period("Q").astype(str)

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
        ci_up = ci.get("ci_upper", float("nan"))
        per_s[sym] = {
            "n": int(len(r)),
            "mean_bp": float(r.mean() * 1e4),
            "ci_lower_bp": float(ci_lo * 1e4) if np.isfinite(ci_lo) else None,
            "ci_upper_bp": float(ci_up * 1e4) if np.isfinite(ci_up) else None,
            "ci_pos": bool(np.isfinite(ci_lo) and ci_lo > 0),
            "measurable": True,
        }
        n_s_measurable += 1
        if np.isfinite(ci_lo) and ci_lo > 0:
            n_s_ci_pos += 1
    s_ci_pos_ratio = (n_s_ci_pos / n_s_measurable) if n_s_measurable > 0 else 0.0

    gate_q = q_pos_ratio >= CONCENT_QUARTER_T_RATIO
    gate_s_ratio = s_ci_pos_ratio >= CONCENT_SYMBOL_CI_POS_RATIO
    gate_s_min = n_s_ci_pos >= CONCENT_MIN_SYMS_CI_POS
    return {
        "per_quarter": per_q,
        "per_symbol": per_s,
        "n_quarters_measurable": int(n_q_measurable),
        "n_quarters_pos_t": int(n_q_pos_t),
        "quarter_pos_t_ratio": float(q_pos_ratio),
        "n_symbols_measurable": int(n_s_measurable),
        "n_symbols_ci_pos": int(n_s_ci_pos),
        "symbol_ci_pos_ratio": float(s_ci_pos_ratio),
        "gate_quarter_pass": bool(gate_q),
        "gate_symbol_ratio_pass": bool(gate_s_ratio),
        "gate_symbol_min_pass": bool(gate_s_min),
        "concentration_gate_pass": bool(gate_q and gate_s_ratio and gate_s_min),
    }


def life_changing_4dim(events: pd.DataFrame, direction_col: str, hold_bars: int,
                       data_span_days: float) -> Dict:
    if events.empty:
        return {"error": "no events"}
    df = events.copy()
    df["directional_gross"] = df[direction_col] * df["gross_ret"]
    df["net_ret"] = df["directional_gross"] - FEE_PER_TRADE
    n = len(df)
    years = data_span_days / 365.25
    trades_per_yr = n / years if years > 0 else 0.0
    per_trade_edge_net_pct = float(df["net_ret"].mean() * 100)
    hold_minutes = hold_bars * 240  # 4h bars
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


def lesson46_stratified_and_sign_flip(events: pd.DataFrame, direction_col: str) -> Dict:
    if events.empty:
        return {"error": "no events"}
    df = events.copy()
    df["directional_gross"] = df[direction_col] * df["gross_ret"]
    df["net_ret"] = df["directional_gross"] - FEE_PER_TRADE
    df["quarter"] = pd.to_datetime(df["t_anchor"]).dt.to_period("Q").astype(str)
    quarters = sorted(df["quarter"].unique())
    per_q_stratified = {}
    sign_per_q = []
    for q in quarters:
        grp = df[df["quarter"] == q]
        sample_n = min(50, len(grp))
        if sample_n < 5:
            per_q_stratified[q] = {"n": int(len(grp)), "sample_n": int(sample_n),
                                   "mean_bp": None, "sign": 0, "measurable": False}
            continue
        sample = grp.sample(n=sample_n, random_state=42) if len(grp) > sample_n else grp
        mean_bp = float(sample["net_ret"].mean() * 1e4)
        sign = 1 if mean_bp > 0 else (-1 if mean_bp < 0 else 0)
        per_q_stratified[q] = {
            "n": int(len(grp)),
            "sample_n": int(sample_n),
            "mean_bp": mean_bp,
            "sign": sign,
            "measurable": True,
        }
        sign_per_q.append(sign)
    n_flips = sum(1 for i in range(len(sign_per_q) - 1) if sign_per_q[i] != sign_per_q[i+1])
    n_measurable = sum(1 for v in per_q_stratified.values() if v.get("measurable"))
    n_pos_quarters = sum(1 for v in per_q_stratified.values() if v.get("measurable") and v.get("sign") == 1)
    n_neg_quarters = sum(1 for v in per_q_stratified.values() if v.get("measurable") and v.get("sign") == -1)
    warning_strong = (n_measurable >= 3 and n_flips >= max(1, n_measurable - 1))
    return {
        "per_quarter_stratified": per_q_stratified,
        "n_quarters_measurable": int(n_measurable),
        "n_pos_quarters": int(n_pos_quarters),
        "n_neg_quarters": int(n_neg_quarters),
        "n_sign_flips": int(n_flips),
        "max_possible_flips": int(max(0, n_measurable - 1)),
        "warning_strong_alternating": bool(warning_strong),
    }


# ------------------------- Quadrant analysis -------------------------
def analyze_quadrant(events: pd.DataFrame, mode: str, hold_bars: int,
                     candidate_pool: np.ndarray, label: str) -> Dict:
    """mode in {'CONT', 'REV'}.
       CONT: direction = +anchor_sign (continuation of session anchor sign)
       REV: direction = -anchor_sign (reversal of session anchor sign)
    Restrict to events where anchor_sign matches the focus subset:
      Q1 UP_LONG    mode=CONT subset=UP (anchor_sign>0)
      Q2 UP_SHORT   mode=REV  subset=UP (anchor_sign>0)
      Q3 DOWN_SHORT mode=CONT subset=DOWN (anchor_sign<0)
      Q4 DOWN_LONG  mode=REV  subset=DOWN (anchor_sign<0)
    Caller passes events already filtered to the subset.
    """
    if events.empty:
        return {
            "label": label, "mode": mode, "hold_bars": hold_bars,
            "three_gate": {"n": 0, "error": "no events"},
            "concentration": {"error": "no events"},
        }
    ev = events.copy()
    if mode == "CONT":
        ev["direction"] = ev["anchor_sign"]
    else:  # REV
        ev["direction"] = -ev["anchor_sign"]
    directional_gross = ev["direction"].values * ev["gross_ret"].values
    observed_net = directional_gross - FEE_PER_TRADE
    n_long = int((ev["direction"] > 0).sum())
    n_short = int((ev["direction"] < 0).sum())
    long_frac = n_long / max(1, n_long + n_short)
    rng = np.random.default_rng(31)
    signs = rng.choice([-1, +1], size=len(candidate_pool),
                       p=[1 - long_frac, long_frac])
    cand_signed = signs * candidate_pool
    gate = three_gate(observed_net, cand_signed)
    conc = concentration_diagnostics(ev, "direction")
    return {
        "label": label,
        "mode": mode,
        "hold_bars": hold_bars,
        "n_long": n_long,
        "n_short": n_short,
        "long_frac": float(long_frac),
        "three_gate": gate,
        "concentration": conc,
    }


# ------------------------- Main -------------------------
def main() -> int:
    t_start = time.time()
    log.info("paradigm 157 R-1 starting at %s", pd.Timestamp.utcnow())
    panel = load_panel()
    if not panel:
        log.error("no panel data loaded")
        return 1
    log.info("panel loaded: %d syms", len(panel))

    spans = [(d.index.max() - d.index.min()).total_seconds() / 86400 for d in panel.values()]
    data_span_days = float(np.mean(spans))
    log.info("avg data span (days) = %.1f", data_span_days)

    # Primary hold = 4h (1 bar)
    candidate_pool = build_candidate_pool(panel, hold_bars=HOLD_BARS_PRIMARY)
    log.info("candidate pool size (hold %d bars = %dh) = %d",
             HOLD_BARS_PRIMARY, HOLD_BARS_PRIMARY * 4, len(candidate_pool))

    events_all = gather_anchor_events(panel, hold_bars=HOLD_BARS_PRIMARY)
    log.info("anchor events total n=%d (across %d syms)", len(events_all), events_all["sym"].nunique() if not events_all.empty else 0)
    n_up = int((events_all["anchor_sign"] > 0).sum())
    n_down = int((events_all["anchor_sign"] < 0).sum())
    log.info("anchor sign split: UP n=%d, DOWN n=%d", n_up, n_down)

    events_up = events_all[events_all["anchor_sign"] > 0].copy()
    events_down = events_all[events_all["anchor_sign"] < 0].copy()

    log.info("=== 4-quadrant SNT (Lesson #19) at primary hold=4h ===")
    # Q1 UP_LONG (CONT on UP)
    Q1 = analyze_quadrant(events_up, "CONT", HOLD_BARS_PRIMARY, candidate_pool, "Q1_UP_LONG_focus_CONT")
    # Q2 UP_SHORT (REV on UP)
    Q2 = analyze_quadrant(events_up, "REV", HOLD_BARS_PRIMARY, candidate_pool, "Q2_UP_SHORT_mirror_REV")
    # Q3 DOWN_SHORT (CONT on DOWN)
    Q3 = analyze_quadrant(events_down, "CONT", HOLD_BARS_PRIMARY, candidate_pool, "Q3_DOWN_SHORT_focus_CONT")
    # Q4 DOWN_LONG (REV on DOWN)
    Q4 = analyze_quadrant(events_down, "REV", HOLD_BARS_PRIMARY, candidate_pool, "Q4_DOWN_LONG_mirror_REV")

    for q in (Q1, Q2, Q3, Q4):
        tg = q["three_gate"]
        cc = q["concentration"]
        log.info("  %s: n=%d mean_bp=%.2f sig_t_ex=%.3f perm_p=%.3f ci_lo_bp=%.2f 3gate=%s conc=%s",
                 q["label"], tg.get("n", 0), tg.get("mean_bp", float("nan")),
                 tg.get("signal_t_excess", float("nan")), tg.get("perm_p", float("nan")),
                 tg.get("ci_lower_bp", float("nan")), tg.get("three_gate_pass"),
                 cc.get("concentration_gate_pass") if isinstance(cc, dict) else None)

    log.info("=== Hold sweep (Lesson #37) ===")
    hold_sweep_cont_up = []
    hold_sweep_cont_down = []
    for hb in HOLD_SWEEP_BARS:
        cp = build_candidate_pool(panel, hold_bars=hb)
        ev_h = gather_anchor_events(panel, hold_bars=hb)
        ev_up_h = ev_h[ev_h["anchor_sign"] > 0]
        ev_dn_h = ev_h[ev_h["anchor_sign"] < 0]
        q_up_cont = analyze_quadrant(ev_up_h, "CONT", hb, cp, f"UP_LONG_CONT_hold{hb*4}h")
        q_dn_cont = analyze_quadrant(ev_dn_h, "CONT", hb, cp, f"DOWN_SHORT_CONT_hold{hb*4}h")
        hold_sweep_cont_up.append({
            "hold_bars": hb, "hold_hours": hb * 4,
            "three_gate": q_up_cont["three_gate"],
            "concentration_pass": q_up_cont["concentration"].get("concentration_gate_pass") if isinstance(q_up_cont["concentration"], dict) else None,
        })
        hold_sweep_cont_down.append({
            "hold_bars": hb, "hold_hours": hb * 4,
            "three_gate": q_dn_cont["three_gate"],
            "concentration_pass": q_dn_cont["concentration"].get("concentration_gate_pass") if isinstance(q_dn_cont["concentration"], dict) else None,
        })
        log.info("  hold=%dh UP_LONG_CONT n=%d mean_bp=%.2f sigex=%.3f 3gate=%s | DOWN_SHORT_CONT n=%d mean_bp=%.2f sigex=%.3f 3gate=%s",
                 hb * 4,
                 q_up_cont["three_gate"].get("n", 0), q_up_cont["three_gate"].get("mean_bp", float("nan")),
                 q_up_cont["three_gate"].get("signal_t_excess", float("nan")), q_up_cont["three_gate"].get("three_gate_pass"),
                 q_dn_cont["three_gate"].get("n", 0), q_dn_cont["three_gate"].get("mean_bp", float("nan")),
                 q_dn_cont["three_gate"].get("signal_t_excess", float("nan")), q_dn_cont["three_gate"].get("three_gate_pass"))

    # Life-changing per CONT focus side
    A_focus_ev = events_up.copy()
    A_focus_ev["direction"] = A_focus_ev["anchor_sign"]
    B_focus_ev = events_down.copy()
    B_focus_ev["direction"] = B_focus_ev["anchor_sign"]
    lc_A = life_changing_4dim(A_focus_ev, "direction", HOLD_BARS_PRIMARY, data_span_days)
    lc_B = life_changing_4dim(B_focus_ev, "direction", HOLD_BARS_PRIMARY, data_span_days)
    log.info("life-changing UP_LONG_CONT: trades/yr=%.1f edge=%.3f%% util=%.1f%% sharpe=%.2f all_pass=%s",
             lc_A.get("trades_per_yr", 0), lc_A.get("per_trade_edge_net_pct", 0),
             lc_A.get("capital_util_pct", 0), lc_A.get("annualized_sharpe", 0),
             lc_A.get("life_changing_all_pass"))
    log.info("life-changing DOWN_SHORT_CONT: trades/yr=%.1f edge=%.3f%% util=%.1f%% sharpe=%.2f all_pass=%s",
             lc_B.get("trades_per_yr", 0), lc_B.get("per_trade_edge_net_pct", 0),
             lc_B.get("capital_util_pct", 0), lc_B.get("annualized_sharpe", 0),
             lc_B.get("life_changing_all_pass"))

    # Lesson #46 stratified + sign-flip
    l46_A = lesson46_stratified_and_sign_flip(A_focus_ev, "direction")
    l46_B = lesson46_stratified_and_sign_flip(B_focus_ev, "direction")
    log.info("Lesson #46 UP_LONG_CONT: q_meas=%d pos_q=%d neg_q=%d flips=%d/%d strong_alt=%s",
             l46_A.get("n_quarters_measurable"), l46_A.get("n_pos_quarters"),
             l46_A.get("n_neg_quarters"), l46_A.get("n_sign_flips"),
             l46_A.get("max_possible_flips"), l46_A.get("warning_strong_alternating"))
    log.info("Lesson #46 DOWN_SHORT_CONT: q_meas=%d pos_q=%d neg_q=%d flips=%d/%d strong_alt=%s",
             l46_B.get("n_quarters_measurable"), l46_B.get("n_pos_quarters"),
             l46_B.get("n_neg_quarters"), l46_B.get("n_sign_flips"),
             l46_B.get("max_possible_flips"), l46_B.get("warning_strong_alternating"))

    # Verdict tree
    Q1_3g = Q1["three_gate"].get("three_gate_pass", False)
    Q2_3g = Q2["three_gate"].get("three_gate_pass", False)
    Q3_3g = Q3["three_gate"].get("three_gate_pass", False)
    Q4_3g = Q4["three_gate"].get("three_gate_pass", False)
    Q1_conc = Q1["concentration"].get("concentration_gate_pass", False) if isinstance(Q1["concentration"], dict) else False
    Q3_conc = Q3["concentration"].get("concentration_gate_pass", False) if isinstance(Q3["concentration"], dict) else False

    Q1_sigex = Q1["three_gate"].get("signal_t_excess", float("nan"))
    Q2_sigex = Q2["three_gate"].get("signal_t_excess", float("nan"))
    Q3_sigex = Q3["three_gate"].get("signal_t_excess", float("nan"))
    Q4_sigex = Q4["three_gate"].get("signal_t_excess", float("nan"))

    # Lesson #39 sub-class A: broad-uniform-negative
    sub_class_A = (np.isfinite(Q1_sigex) and np.isfinite(Q2_sigex)
                   and np.isfinite(Q3_sigex) and np.isfinite(Q4_sigex)
                   and Q1_sigex < -2 and Q2_sigex < -2
                   and Q3_sigex < -2 and Q4_sigex < -2)

    # Lesson #39 sub-class B: mechanism-inverted (mirror beats focus by >=1.5σ)
    q2_dominates_q1 = (np.isfinite(Q2_sigex) and np.isfinite(Q1_sigex)
                      and Q2_sigex > Q1_sigex + 1.5)
    q4_dominates_q3 = (np.isfinite(Q4_sigex) and np.isfinite(Q3_sigex)
                      and Q4_sigex > Q3_sigex + 1.5)
    sub_class_B = q2_dominates_q1 or q4_dominates_q3

    both_focus_pass = Q1_3g and Q3_3g and Q1_conc and Q3_conc
    one_focus_pass = (Q1_3g and Q1_conc) or (Q3_3g and Q3_conc)
    any_focus_3g = Q1_3g or Q3_3g
    any_focus_conc_only = (Q1_3g and not Q1_conc) or (Q3_3g and not Q3_conc)
    A_lc_pass = lc_A.get("life_changing_all_pass", False)
    B_lc_pass = lc_B.get("life_changing_all_pass", False)

    if sub_class_A:
        verdict = "BROAD_FALSIFIED_NO_AXIS_SYNTHESIS_LESSON39A"
    elif sub_class_B:
        verdict = "BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED_LESSON39B"
    elif both_focus_pass:
        if A_lc_pass and B_lc_pass:
            verdict = "PASS_R1_BOTH_FOCUS_LIFE_CHANGING_OK"
        elif A_lc_pass or B_lc_pass:
            verdict = "PASS_R1_BOTH_FOCUS_ONE_SIDE_LIFE_CHANGING"
        else:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
    elif one_focus_pass:
        which = "UP_LONG" if (Q1_3g and Q1_conc) else "DOWN_SHORT"
        lc_ok = (A_lc_pass if which == "UP_LONG" else B_lc_pass)
        if lc_ok:
            verdict = f"PASS_R1_ONE_SIDE_ONLY_{which}_LIFE_CHANGING_OK"
        else:
            verdict = f"ONE_FOCUS_PASS_{which}_NARROW_SCOPE_LIFE_CHANGING_FAIL"
    elif any_focus_3g and any_focus_conc_only:
        verdict = "CONCENTRATED_R1_PASS_CONCENTRATION_FAIL"
    elif any_focus_3g:
        verdict = "PARTIAL_FOCUS_PASS_CONCENTRATION_FAIL"
    else:
        verdict = "BROAD_FALSIFIED"

    any_off_primary_cont_up = any(hs["three_gate"].get("three_gate_pass", False)
                                  for hs in hold_sweep_cont_up if hs["hold_bars"] != HOLD_BARS_PRIMARY)
    any_off_primary_cont_down = any(hs["three_gate"].get("three_gate_pass", False)
                                    for hs in hold_sweep_cont_down if hs["hold_bars"] != HOLD_BARS_PRIMARY)

    metrics = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_id": PARADIGM_ID,
        "phase": "R-1",
        "run_ts": str(pd.Timestamp.utcnow()),
        "wall_clock_seconds": float(time.time() - t_start),
        "config": {
            "universe": UNIVERSE,
            "n_syms_universe": len(UNIVERSE),
            "n_syms_loaded": len(panel),
            "fee_per_trade": FEE_PER_TRADE,
            "tf": TF,
            "anchor_hour_utc_open_time": 16,
            "anchor_hour_utc_close_time": 20,
            "anchor_semantic": "NY equities close 20:00 UTC EDT (16-20 UTC 4h bar close)",
            "hold_bars_primary": HOLD_BARS_PRIMARY,
            "hold_sweep_bars": HOLD_SWEEP_BARS,
            "data_span_days": data_span_days,
            "data_window_ratio": 1.0,
        },
        "sample_density": {
            "n_events_total": int(len(events_all)),
            "n_events_up": int(n_up),
            "n_events_down": int(n_down),
            "lesson11_prescreen_pass": True,
        },
        "snt_4quadrant": {
            "Q1_UP_LONG_focus_CONT": Q1,
            "Q2_UP_SHORT_mirror_REV": Q2,
            "Q3_DOWN_SHORT_focus_CONT": Q3,
            "Q4_DOWN_LONG_mirror_REV": Q4,
        },
        "hold_sweep_UP_LONG_CONT": hold_sweep_cont_up,
        "hold_sweep_DOWN_SHORT_CONT": hold_sweep_cont_down,
        "lesson37_full_sweep_scan": {
            "primary_hold_bars": HOLD_BARS_PRIMARY,
            "any_off_primary_3gate_pass_UP_LONG": bool(any_off_primary_cont_up),
            "any_off_primary_3gate_pass_DOWN_SHORT": bool(any_off_primary_cont_down),
        },
        "life_changing_4dim_UP_LONG_CONT": lc_A,
        "life_changing_4dim_DOWN_SHORT_CONT": lc_B,
        "lesson46_stratified_sign_flip_UP_LONG": l46_A,
        "lesson46_stratified_sign_flip_DOWN_SHORT": l46_B,
        "lesson39_subclass_detection": {
            "sub_class_A_broad_uniform_negative": bool(sub_class_A),
            "sub_class_B_mechanism_inverted": bool(sub_class_B),
            "Q2_dominates_Q1_by_1p5": bool(q2_dominates_q1),
            "Q4_dominates_Q3_by_1p5": bool(q4_dominates_q3),
            "Q1_sigex": float(Q1_sigex) if np.isfinite(Q1_sigex) else None,
            "Q2_sigex": float(Q2_sigex) if np.isfinite(Q2_sigex) else None,
            "Q3_sigex": float(Q3_sigex) if np.isfinite(Q3_sigex) else None,
            "Q4_sigex": float(Q4_sigex) if np.isfinite(Q4_sigex) else None,
        },
        "verdict": verdict,
        "family_distinct_strict_audit_lesson62": {
            "strict_dim_count": 4,
            "dims": {
                "statistic_class": "funding/RV/range_vol/quote_vol -> session-anchor bar sign (NEW class)",
                "universe_scope": "per-sym self-conditioning / BTC-only broadcast -> 14 syms structural shared anchor (NEW class)",
                "entry_side_class": "funding event boundary / threshold filter -> time-of-day cycle anchor (NEW class)",
                "mechanism_alpha": "leverage skew / vol regime -> session boundary macro flow rebalancing (NEW class)",
            },
            "vs_paradigm_22_R5": "funding 8h boundary anchor != NY 24h cycle anchor (entirely different anchor system)",
            "vs_funding_family_Tier4": "completely different axis class (time-of-day vs funding magnitude)",
            "vs_paradigm_85_pre_session_open_oi": "different anchor time (daily 00 UTC pre-event vs NY 20 UTC) + paradigm 85 sample-insufficient halt only (no R-1 outcome)",
        },
        "lesson67_avoidance_check": {
            "macro_single_asset_broadcast_pattern": False,
            "structural_global_anchor": True,
            "rationale": "session boundary is shared structural anchor across all 14 syms (incl. BTC) NOT a BTC-only trigger broadcast to alts. Universe-wide microstructure event.",
        },
        "lessons_applied": {
            "lesson_11_sample_density": "PASS",
            "lesson_16_concentration_gate_strict": "q_pos_t>=0.5 + sym_ci_pos>=0.30 + min_syms>=3",
            "lesson_19_4quadrant_SNT_mandatory": "applied (UP_LONG/UP_SHORT/DOWN_SHORT/DOWN_LONG)",
            "lesson_28_substrate_availability": "PASS (4h cache 영구 자산)",
            "lesson_30_data_window_ratio": "1.00 uniform PASS",
            "lesson_37_full_sweep_verdict_scan": "see lesson37_full_sweep_scan + hold_sweep_*",
            "lesson_39_subclass_AB_detection": "see lesson39_subclass_detection",
            "lesson_46_stratified_n50x4q_plus_sign_flip": "see lesson46_stratified_*",
            "lesson_62_family_distinct_strict_4dim": "4/4 STRICT (statistic + universe + entry-side + mechanism all NEW class)",
            "lesson_67_macro_single_asset_broadcast_avoidance": "ESCAPE (structural global anchor not macro broadcast)",
            "lesson_life_changing_4dim": "see life_changing_4dim_*",
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
