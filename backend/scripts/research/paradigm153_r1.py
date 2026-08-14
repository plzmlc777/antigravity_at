"""Paradigm 153 R-1: alt_range_volume_divergence_percentile_rank_directional_4h.

Lesson #40 reformulate first STRUCTURED dogfood
-----------------------------------------------
paradigm 152 (z-score subtraction) graveyarded R-0 Lesson #40 sub-class D
(asymmetric distribution, p99 < 2.0 on 13/13 syms positive side). paradigm 153
reformulates trigger via percentile rank on the same divergence statistic to
bypass the structural asymmetry. Underlying mechanism story unchanged (thin /
consolidation regime classifier).

Mechanism
---------
- substrate: 12-col klines 4h cache (paradigm 142/152 reuse, no new infra)
- range = (high - low) / close
- vol = quote_volume
- range_z / vol_z = per-sym 30d rolling z (180 bars @ 4h)
- divergence = range_z - vol_z
- pct_rank = 30d (180 bars) rolling percentile rank of divergence ∈ [0, 1]
- Trigger: rank > 0.95 (top 5%) OR rank < 0.05 (bottom 5%)
- Direction story:
  - rank > 0.95 (HIGH divergence: range outsized vs volume → thin / low-liquidity
    spike) → 4h **MEAN-REVERSION** of trigger-bar close direction
  - rank < 0.05 (LOW/negative divergence: volume outsized vs range → consolidation
    / absorption regime) → 4h **CONTINUATION** of trigger-bar close direction

4-quadrant SNT (Lesson #19 mandatory)
-------------------------------------
- A focus: rank > 0.95 × MR direction (close > prior → SHORT; close < prior → LONG)
- A mirror: rank > 0.95 × continuation direction
- B focus: rank < 0.05 × continuation direction (close > prior → LONG; close < prior → SHORT)
- B mirror: rank < 0.05 × MR direction

paradigm 110 mechanism-direction inversion risk (Lesson #44 37th xref)
----------------------------------------------------------------------
paradigm 110 (funding neg z → pct rank ≤0.10) achieved structural reformulate
SUCCESS but mechanism DIRECTION inverted graveyard. paradigm 153 must validate
direction via 4-quadrant SNT. If A_mirror or B_mirror dominates focus by ≥1.5σ
sigex → Lesson #39 sub-class B detection (mechanism inverted).
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
log = logging.getLogger("paradigm153_r1")

# ------------------------- Config -------------------------
PARADIGM_NAME = "alt_range_volume_divergence_percentile_rank_directional_4h"
PARADIGM_ID = 153
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = ["ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
            "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
            "SOLUSDT", "WIFUSDT", "XRPUSDT"]  # 13 alts (BTC excluded as universe-baseline)
TF = "4h"

FEE_PER_TRADE = 0.0008  # 8 bp round-trip
HOLD_BARS_PRIMARY = 1  # 1 × 4h = 4h
HOLD_SWEEP_BARS = [1, 2, 3]  # 4h / 8h / 12h
ROLLING_BARS_Z = 180  # 30d × 6 bars/day (z-score lookback)
ROLLING_BARS_RANK = 180  # 30d × 6 bars/day (pct rank lookback)
RANK_UPPER = 0.95
RANK_LOWER = 0.05

# Three-gate thresholds
SIG_T_EXCESS_PASS = 2.0
PERM_P_PASS = 0.10
CI_LOWER_PASS = 0.0

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
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["quote_volume"] = df["quote_volume"].astype(float)
        out[sym] = df
        log.info("[%s] bars=%d span=%s->%s", sym, len(df), df.index.min(), df.index.max())
    return out


def compute_panel_features(panel: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """range_z, vol_z, divergence, pct_rank, plus close-to-close prior-bar sign."""
    out = {}
    for sym, df in panel.items():
        d = df.copy()
        range_ = (d["high"] - d["low"]) / d["close"]
        vol = d["quote_volume"]
        safe_range_sd = range_.rolling(ROLLING_BARS_Z, min_periods=60).std(ddof=1).shift(1)
        safe_vol_sd = vol.rolling(ROLLING_BARS_Z, min_periods=60).std(ddof=1).shift(1)
        range_mu = range_.rolling(ROLLING_BARS_Z, min_periods=60).mean().shift(1)
        vol_mu = vol.rolling(ROLLING_BARS_Z, min_periods=60).mean().shift(1)
        d["range_z"] = (range_ - range_mu) / safe_range_sd.where(safe_range_sd > 1e-12, np.nan)
        d["vol_z"] = (vol - vol_mu) / safe_vol_sd.where(safe_vol_sd > 1e-12, np.nan)
        d["divergence"] = d["range_z"] - d["vol_z"]
        # rolling pct rank (shifted by 1 to avoid lookahead)
        try:
            d["pct_rank"] = d["divergence"].rolling(
                ROLLING_BARS_RANK, min_periods=60
            ).rank(pct=True).shift(1)
        except (TypeError, AttributeError):
            log.warning("[%s] pandas rolling.rank fallback (slow)", sym)
            d["pct_rank"] = d["divergence"].rolling(
                ROLLING_BARS_RANK, min_periods=60
            ).apply(lambda x: (x.argsort().argsort()[-1] + 1) / len(x), raw=False).shift(1)
        # trigger-bar close direction (prior bar close vs current bar close)
        d["bar_sign"] = np.sign(d["close"].diff())
        out[sym] = d
    return out


def gather_events(panel_feat: Dict[str, pd.DataFrame], side: str,
                  hold_bars: int) -> pd.DataFrame:
    """side='top' → pct_rank > RANK_UPPER ; side='bot' → pct_rank < RANK_LOWER."""
    rows: List[Dict] = []
    for sym, d in panel_feat.items():
        if side == "top":
            mask = d["pct_rank"] > RANK_UPPER
        else:
            mask = d["pct_rank"] < RANK_LOWER
        idx_trigger = d.index[mask.fillna(False)]
        for t in idx_trigger:
            pos = d.index.get_loc(t)
            if isinstance(pos, slice):
                continue
            ix_exit = pos + hold_bars
            if ix_exit >= len(d):
                continue
            entry = d["close"].iat[pos]
            exitp = d["close"].iat[ix_exit]
            bar_sign = d["bar_sign"].iat[pos]
            if not (entry > 0 and np.isfinite(entry) and np.isfinite(exitp)):
                continue
            if not np.isfinite(bar_sign) or bar_sign == 0:
                continue  # skip flat bars (rare)
            gross_ret = exitp / entry - 1.0
            rows.append({
                "sym": sym,
                "t_event": t,
                "pct_rank": float(d["pct_rank"].iat[pos]),
                "divergence": float(d["divergence"].iat[pos]),
                "bar_sign": float(bar_sign),
                "gross_ret": float(gross_ret),
            })
    ev = pd.DataFrame(rows)
    if not ev.empty:
        ev = ev.sort_values(["sym", "t_event"]).reset_index(drop=True)
    return ev


def build_candidate_pool(panel_feat: Dict[str, pd.DataFrame], hold_bars: int,
                         sample_per_sym: int = 1500, rng_seed: int = 13) -> np.ndarray:
    """Random forward gross returns over hold_bars from non-trigger bars."""
    rng = np.random.default_rng(rng_seed)
    rets: List[np.ndarray] = []
    for sym, d in panel_feat.items():
        valid = d.dropna(subset=["pct_rank"])
        if len(valid) < hold_bars + 10:
            continue
        n_eligible = len(valid) - hold_bars
        if n_eligible <= 0:
            continue
        k = min(sample_per_sym, n_eligible)
        idx = rng.choice(n_eligible, size=k, replace=False)
        entry = valid["close"].values[idx]
        exitp = valid["close"].values[idx + hold_bars]
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
    """events with `direction_col` already containing per-row {-1,+1}, and `gross_ret`."""
    if events.empty:
        return {"error": "no events"}
    df = events.copy()
    df["directional_gross"] = df[direction_col] * df["gross_ret"]
    df["net_ret"] = df["directional_gross"] - FEE_PER_TRADE
    df["quarter"] = pd.to_datetime(df["t_event"]).dt.to_period("Q").astype(str)

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
    df["quarter"] = pd.to_datetime(df["t_event"]).dt.to_period("Q").astype(str)
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
    """mode ∈ {'MR', 'CONT'}.
       MR: direction = -bar_sign (mean-revert prior bar direction).
       CONT: direction = +bar_sign (continue prior bar direction).
    Each event already carries bar_sign ∈ {-1, +1}; gather_events filters out 0.
    """
    if events.empty:
        return {
            "label": label,
            "mode": mode,
            "hold_bars": hold_bars,
            "three_gate": {"n": 0, "error": "no events"},
            "concentration": {"error": "no events"},
        }
    ev = events.copy()
    if mode == "MR":
        ev["direction"] = -ev["bar_sign"]
    else:
        ev["direction"] = ev["bar_sign"]
    directional_gross = ev["direction"].values * ev["gross_ret"].values
    observed_net = directional_gross - FEE_PER_TRADE
    # signed candidate pool: paradigm has mixed LONG/SHORT, so we evaluate fee-aware
    # null as the average across both signs (each event has its own direction).
    # We approximate by passing raw gross pool and letting fee_aware_perm_test
    # treat null as raw forward returns minus fee. Direction is intrinsic to event.
    # For symmetry, sample candidate pool with equal prob of +/- sign (since
    # observed dir mix is empirical):
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
    log.info("paradigm 153 R-1 starting at %s", pd.Timestamp.utcnow())
    panel = load_panel()
    if not panel:
        log.error("no panel data loaded")
        return 1
    log.info("panel loaded: %d syms", len(panel))

    panel_feat = compute_panel_features(panel)

    spans = [(d.index.max() - d.index.min()).total_seconds() / 86400 for d in panel.values()]
    data_span_days = float(np.mean(spans))
    log.info("avg data span (days) = %.1f", data_span_days)

    candidate_pool = build_candidate_pool(panel_feat, hold_bars=HOLD_BARS_PRIMARY)
    log.info("candidate pool size (hold %d bars = %dh) = %d",
             HOLD_BARS_PRIMARY, HOLD_BARS_PRIMARY * 4, len(candidate_pool))

    events_top = gather_events(panel_feat, side="top", hold_bars=HOLD_BARS_PRIMARY)
    events_bot = gather_events(panel_feat, side="bot", hold_bars=HOLD_BARS_PRIMARY)
    log.info("trigger events: top n=%d, bot n=%d", len(events_top), len(events_bot))

    log.info("=== 4-quadrant SNT (Lesson #19) ===")
    A_focus = analyze_quadrant(events_top, "MR", HOLD_BARS_PRIMARY, candidate_pool,
                                "A_focus_top_MR")
    A_mirror = analyze_quadrant(events_top, "CONT", HOLD_BARS_PRIMARY, candidate_pool,
                                 "A_mirror_top_CONT")
    B_focus = analyze_quadrant(events_bot, "CONT", HOLD_BARS_PRIMARY, candidate_pool,
                                "B_focus_bot_CONT")
    B_mirror = analyze_quadrant(events_bot, "MR", HOLD_BARS_PRIMARY, candidate_pool,
                                 "B_mirror_bot_MR")

    for q in (A_focus, A_mirror, B_focus, B_mirror):
        tg = q["three_gate"]
        cc = q["concentration"]
        log.info("  %s: n=%d mean_bp=%.2f sig_t_ex=%.3f perm_p=%.3f ci_lo_bp=%.2f 3gate=%s conc=%s",
                 q["label"], tg.get("n", 0), tg.get("mean_bp", float("nan")),
                 tg.get("signal_t_excess", float("nan")), tg.get("perm_p", float("nan")),
                 tg.get("ci_lower_bp", float("nan")), tg.get("three_gate_pass"),
                 cc.get("concentration_gate_pass") if isinstance(cc, dict) else None)

    log.info("=== Hold sweep (Lesson #37) ===")
    hold_sweep_a_focus = []
    hold_sweep_b_focus = []
    for hb in HOLD_SWEEP_BARS:
        cp = build_candidate_pool(panel_feat, hold_bars=hb)
        ep = gather_events(panel_feat, side="top", hold_bars=hb)
        en = gather_events(panel_feat, side="bot", hold_bars=hb)
        q_af = analyze_quadrant(ep, "MR", hb, cp, f"A_focus_top_MR_hold{hb*4}h")
        q_bf = analyze_quadrant(en, "CONT", hb, cp, f"B_focus_bot_CONT_hold{hb*4}h")
        hold_sweep_a_focus.append({
            "hold_bars": hb,
            "hold_hours": hb * 4,
            "three_gate": q_af["three_gate"],
            "concentration_pass": q_af["concentration"].get("concentration_gate_pass") if isinstance(q_af["concentration"], dict) else None,
        })
        hold_sweep_b_focus.append({
            "hold_bars": hb,
            "hold_hours": hb * 4,
            "three_gate": q_bf["three_gate"],
            "concentration_pass": q_bf["concentration"].get("concentration_gate_pass") if isinstance(q_bf["concentration"], dict) else None,
        })
        log.info("  hold=%dh A_focus_MR n=%d mean_bp=%.2f sigex=%.3f 3gate=%s | B_focus_CONT n=%d mean_bp=%.2f sigex=%.3f 3gate=%s",
                 hb * 4,
                 q_af["three_gate"].get("n", 0), q_af["three_gate"].get("mean_bp", float("nan")),
                 q_af["three_gate"].get("signal_t_excess", float("nan")), q_af["three_gate"].get("three_gate_pass"),
                 q_bf["three_gate"].get("n", 0), q_bf["three_gate"].get("mean_bp", float("nan")),
                 q_bf["three_gate"].get("signal_t_excess", float("nan")), q_bf["three_gate"].get("three_gate_pass"))

    # Life-changing per focus side
    A_focus_ev = events_top.copy()
    A_focus_ev["direction"] = -A_focus_ev["bar_sign"]
    B_focus_ev = events_bot.copy()
    B_focus_ev["direction"] = B_focus_ev["bar_sign"]
    lc_A = life_changing_4dim(A_focus_ev, "direction", HOLD_BARS_PRIMARY, data_span_days)
    lc_B = life_changing_4dim(B_focus_ev, "direction", HOLD_BARS_PRIMARY, data_span_days)
    log.info("life-changing A_focus_MR: trades/yr=%.1f edge=%.3f%% util=%.1f%% sharpe=%.2f all_pass=%s",
             lc_A.get("trades_per_yr", 0), lc_A.get("per_trade_edge_net_pct", 0),
             lc_A.get("capital_util_pct", 0), lc_A.get("annualized_sharpe", 0),
             lc_A.get("life_changing_all_pass"))
    log.info("life-changing B_focus_CONT: trades/yr=%.1f edge=%.3f%% util=%.1f%% sharpe=%.2f all_pass=%s",
             lc_B.get("trades_per_yr", 0), lc_B.get("per_trade_edge_net_pct", 0),
             lc_B.get("capital_util_pct", 0), lc_B.get("annualized_sharpe", 0),
             lc_B.get("life_changing_all_pass"))

    # Lesson #46 stratified + sign-flip
    l46_A = lesson46_stratified_and_sign_flip(A_focus_ev, "direction")
    l46_B = lesson46_stratified_and_sign_flip(B_focus_ev, "direction")
    log.info("Lesson #46 A_focus: q_meas=%d pos_q=%d neg_q=%d flips=%d/%d strong_alt=%s",
             l46_A.get("n_quarters_measurable"), l46_A.get("n_pos_quarters"),
             l46_A.get("n_neg_quarters"), l46_A.get("n_sign_flips"),
             l46_A.get("max_possible_flips"), l46_A.get("warning_strong_alternating"))
    log.info("Lesson #46 B_focus: q_meas=%d pos_q=%d neg_q=%d flips=%d/%d strong_alt=%s",
             l46_B.get("n_quarters_measurable"), l46_B.get("n_pos_quarters"),
             l46_B.get("n_neg_quarters"), l46_B.get("n_sign_flips"),
             l46_B.get("max_possible_flips"), l46_B.get("warning_strong_alternating"))

    # Verdict tree (Lesson #39 sub-class detection)
    A_focus_3g = A_focus["three_gate"].get("three_gate_pass", False)
    A_mirror_3g = A_mirror["three_gate"].get("three_gate_pass", False)
    B_focus_3g = B_focus["three_gate"].get("three_gate_pass", False)
    B_mirror_3g = B_mirror["three_gate"].get("three_gate_pass", False)
    A_focus_conc = A_focus["concentration"].get("concentration_gate_pass", False) if isinstance(A_focus["concentration"], dict) else False
    B_focus_conc = B_focus["concentration"].get("concentration_gate_pass", False) if isinstance(B_focus["concentration"], dict) else False
    A_focus_sigex = A_focus["three_gate"].get("signal_t_excess", float("nan"))
    A_mirror_sigex = A_mirror["three_gate"].get("signal_t_excess", float("nan"))
    B_focus_sigex = B_focus["three_gate"].get("signal_t_excess", float("nan"))
    B_mirror_sigex = B_mirror["three_gate"].get("signal_t_excess", float("nan"))

    # Lesson #39 sub-class A: broad-uniform-negative
    sub_class_A = (np.isfinite(A_focus_sigex) and np.isfinite(A_mirror_sigex)
                   and np.isfinite(B_focus_sigex) and np.isfinite(B_mirror_sigex)
                   and A_focus_sigex < -2 and A_mirror_sigex < -2
                   and B_focus_sigex < -2 and B_mirror_sigex < -2)

    # Lesson #39 sub-class B: mechanism-inverted (mirror beats focus by ≥1.5σ)
    # paradigm 110 precedent direction-inversion risk
    a_mirror_dominates = (np.isfinite(A_mirror_sigex) and np.isfinite(A_focus_sigex)
                          and A_mirror_sigex > A_focus_sigex + 1.5)
    b_mirror_dominates = (np.isfinite(B_mirror_sigex) and np.isfinite(B_focus_sigex)
                          and B_mirror_sigex > B_focus_sigex + 1.5)
    sub_class_B = a_mirror_dominates or b_mirror_dominates

    # Lesson #39 sub-class D detection (paradigm 152): N/A here because structural
    # threshold attainability already fixed via pct rank (R-0 verified).

    both_focus_pass = A_focus_3g and B_focus_3g and A_focus_conc and B_focus_conc
    one_focus_pass = (A_focus_3g and A_focus_conc) or (B_focus_3g and B_focus_conc)
    any_focus_3g = A_focus_3g or B_focus_3g
    any_focus_conc_only = (A_focus_3g and not A_focus_conc) or (B_focus_3g and not B_focus_conc)

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
        which = "A" if (A_focus_3g and A_focus_conc) else "B"
        lc_ok = (A_lc_pass if which == "A" else B_lc_pass)
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

    any_off_primary_a = any(hs["three_gate"].get("three_gate_pass", False)
                            for hs in hold_sweep_a_focus if hs["hold_bars"] != HOLD_BARS_PRIMARY)
    any_off_primary_b = any(hs["three_gate"].get("three_gate_pass", False)
                            for hs in hold_sweep_b_focus if hs["hold_bars"] != HOLD_BARS_PRIMARY)

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
            "hold_bars_primary": HOLD_BARS_PRIMARY,
            "hold_sweep_bars": HOLD_SWEEP_BARS,
            "rolling_bars_z": ROLLING_BARS_Z,
            "rolling_bars_rank": ROLLING_BARS_RANK,
            "rank_upper": RANK_UPPER,
            "rank_lower": RANK_LOWER,
            "data_span_days": data_span_days,
            "data_window_ratio": 1.0,
        },
        "sample_density": {
            "n_events_top": int(len(events_top)),
            "n_events_bot": int(len(events_bot)),
            "lesson11_prescreen_pass": True,
        },
        "snt_4quadrant": {
            "A_focus_top_MR": A_focus,
            "A_mirror_top_CONT": A_mirror,
            "B_focus_bot_CONT": B_focus,
            "B_mirror_bot_MR": B_mirror,
        },
        "hold_sweep_A_focus_MR": hold_sweep_a_focus,
        "hold_sweep_B_focus_CONT": hold_sweep_b_focus,
        "lesson37_full_sweep_scan": {
            "primary_hold_bars": HOLD_BARS_PRIMARY,
            "any_off_primary_3gate_pass_A": bool(any_off_primary_a),
            "any_off_primary_3gate_pass_B": bool(any_off_primary_b),
        },
        "life_changing_4dim_A_focus_MR": lc_A,
        "life_changing_4dim_B_focus_CONT": lc_B,
        "lesson46_stratified_sign_flip_A": l46_A,
        "lesson46_stratified_sign_flip_B": l46_B,
        "lesson39_subclass_detection": {
            "sub_class_A_broad_uniform_negative": bool(sub_class_A),
            "sub_class_B_mechanism_inverted": bool(sub_class_B),
            "A_mirror_dominates_A_focus_by_1p5": bool(a_mirror_dominates),
            "B_mirror_dominates_B_focus_by_1p5": bool(b_mirror_dominates),
            "A_focus_sigex": float(A_focus_sigex) if np.isfinite(A_focus_sigex) else None,
            "A_mirror_sigex": float(A_mirror_sigex) if np.isfinite(A_mirror_sigex) else None,
            "B_focus_sigex": float(B_focus_sigex) if np.isfinite(B_focus_sigex) else None,
            "B_mirror_sigex": float(B_mirror_sigex) if np.isfinite(B_mirror_sigex) else None,
            "paradigm_110_precedent_inversion_risk_check": "see sub_class_B flag",
        },
        "verdict": verdict,
        "family_distinct_paradigms": {
            "paradigm_152_z_score_subtraction_GRAVEYARD": "distinct: pct rank reformulate vs z asymmetric distribution",
            "paradigm_110_funding_pct_rank_GRAVEYARD": "precedent: structural fix SUCCESS but mechanism direction inverted - sub_class_B check mandatory",
            "paradigm_116_volume_confirmed_atr_breakout": "distinct: ATR breakout (continuation single-axis) vs range-volume joint divergence pct",
            "paradigm_129_parkinson_range_vol": "distinct: single-axis raw range vs joint divergence+pct rank",
            "paradigm_137_yang_zhang_close_ratio": "distinct: vol-of-vol close ratio vs range-volume joint pct",
            "paradigm_142_quote_vol_imbalance": "distinct: taker_buy filter on quote_vol vs range_z-vol_z+pct rank",
            "paradigm_144_quote_vol_count_ratio": "distinct: avg_trade_size ratio vs joint divergence pct",
            "dna_overlap_dim": "substrate (12-col klines 4h) shared; statistic class (pct-rank of divergence) NEW vs p152",
        },
        "lessons_applied": {
            "lesson_11_sample_density": "PASS per-cell top=365 bot=369 (R-0 verified)",
            "lesson_16_concentration_gate_strict": "q_pos_t>=0.5 + sym_ci_pos>=0.30 + min_syms>=3",
            "lesson_19_4quadrant_SNT_mandatory": "applied (top×MR, top×CONT, bot×CONT, bot×MR)",
            "lesson_30_data_window_ratio": "1.00 uniform PASS (paradigm 152 verified)",
            "lesson_37_full_sweep_verdict_scan": "see lesson37_full_sweep_scan + hold_sweep_*",
            "lesson_39_subclass_AB_detection": "see lesson39_subclass_detection (paradigm 110 direction inversion risk)",
            "lesson_40_structural_threshold_feasibility": "REFORMULATE FIX VERIFIED via pct rank (R-0 PASS top/bot symmetric 0.99 ratio)",
            "lesson_40_reformulate_first_structured_dogfood": "paradigm 152 sub-class D detection → paradigm 153 pct rank reformulate (paradigm 110 1st natural precedent)",
            "lesson_44_37th_xref": "see family_distinct_paradigms",
            "lesson_46_stratified_n50x4q_plus_sign_flip": "see lesson46_stratified_*",
            "lesson_54_same_bar_subtraction": "subtraction not ratio, identical to p152, no degeneracy",
            "lesson_58_corr_xref_p152": "paradigm 152 PASS confirmed (corr 0.65-0.78 healthy zone), no rerun",
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
