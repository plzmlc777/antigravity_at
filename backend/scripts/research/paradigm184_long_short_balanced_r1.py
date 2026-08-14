"""
paradigm 184 R-1: per-sym 30d return z-score continuous-weighted LONG-SHORT BALANCED daily-rebal

Mechanism (paradigm 181 framework + SHORT extension):
- 14 alts × 4h OHLCV joblib substrate (2.25yr)
- Aggregate 4h to daily close-to-close
- Per-sym 30d rolling return → 90d rolling z-score
- Position size:
    z >= +0.5 → LONG  weight = clip(z, +0.5, +3) / sum_norm
    z <= -0.5 → SHORT weight = clip(z, -3, -0.5) / sum_norm  (negative weight)
    |z| < 0.5 → cash
- Daily rebalance (continuous, NOT state-machine)
- Long-short balanced (target net market neutral; sum(w) ~ 0 if symmetric)
- Fee: daily turnover × 8bp one-way
- SHORT funding cost: 0.01%/day simplified avg on |SHORT weight|

Lesson #70 corollary scope prescreen (CRITICAL):
- paradigm 181 = R-1 GRAVEYARD (NOT R-5 LIVE survivor)
- direction class shift NEW (long-only -> long-short balanced)
- Fama-French / Jegadeesh-Titman literature classical separate families
- VERDICT: (b) PROCEED_NEW_DIRECTION_CLASS

Lesson #72 boundary test:
- paradigm 181 + 182 + 183 (long-only) consistent 6 negative syms (FIL/LINK/BCH/NEAR/BNB/LTC)
- paradigm 184 SHORTs those 6 syms -> alpha recovery? long-only constraint problem?
- Outcomes:
    A. long-short alpha PASS (sharpe>1.0 or z_excess>2.0) -> long-only constraint = problem
    B. long-short also alpha-void -> Lesson #72 strict universal CONFIRMED
    C. partial (sharpe 0.5-1.0) -> universe-level downtrend bias, SHORT carries alpha

R-1 measurements:
- Portfolio gross/net (LONG + SHORT combined)
- LONG-side vs SHORT-side decomposition (separate alpha attribution)
- 6 negative syms SHORT contribution
- Primary benchmark = 0% market-neutral baseline
- eq-weight basket = reference only (long-only ineligible primary benchmark)
- Permutation null = shuffle weight rows across time (preserves cross-sectional structure)
- Quarter-by-quarter (9 quarters)
- Turnover (LONG + SHORT separately) + fee drag + SHORT funding drag
- Life-changing 4-dim dual-mode

Verdict tree:
- HALT_BY_UTIL — util < 30% (Lesson #71 breach)
- PORTFOLIO_ALPHA_INSIGNIFICANT — z_excess < 2.0 OR perm_p > 0.10
- BROAD_FALSIFIED — full 4-quadrant (LONG-side + SHORT-side) all alpha-void
- NARROW_SCOPE_LIFE_CHANGING_FAIL — alpha PASS but 4-dim FAIL
- PASS_R1_FULL — alpha PASS + 4-cond ALL PASS
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CACHE_DIR = Path("/home/hcpark/antigravity/backend/runs/ohlcv_cache_12col")
OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/alt_per_sym_30d_return_z_continuous_weighted_long_short_balanced_neutral_daily_rebal")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "FILUSDT", "WIFUSDT",
]

# paradigm 181 graveyard-confirmed 6 negative syms (long-only -1600~-6000bp alpha drag)
NEGATIVE_SYMS_181 = ["FILUSDT", "LINKUSDT", "BCHUSDT", "NEARUSDT", "BNBUSDT", "LTCUSDT"]

# Position sizing params (identical to paradigm 181)
RETURN_WINDOW_D = 30
Z_WINDOW_D = 90
Z_FLOOR = 0.5  # |z| floor (LONG: z>=+0.5, SHORT: z<=-0.5)
Z_CAP = 3.0
FEE_BP_ONE_WAY = 8.0

# SHORT funding cost (simplified; spec: ~0.01%/day avg on |SHORT weight|)
SHORT_FUNDING_PCT_PER_DAY = 0.0001  # 0.01%/day = 1bp/day

# Permutation
N_PERM = 1000
RNG_SEED = 20260522


def load_daily_returns():
    daily_close = {}
    for sym in SYMBOLS:
        fp = CACHE_DIR / f"{sym}_4h.joblib"
        if not fp.exists():
            logger.warning("missing substrate %s", sym)
            continue
        df = joblib.load(fp)
        d = df["close"].resample("1D").last().dropna()
        daily_close[sym] = d
    df_close = pd.DataFrame(daily_close).sort_index()
    df_close = df_close.dropna(how="any")
    logger.info("daily close panel shape: %s, range %s..%s",
                df_close.shape, df_close.index[0], df_close.index[-1])
    df_ret = df_close.pct_change().dropna(how="any")
    return df_close, df_ret


def compute_z_scores(df_close: pd.DataFrame, return_window: int, z_window: int) -> pd.DataFrame:
    df_ret_window = df_close / df_close.shift(return_window) - 1.0
    z = (df_ret_window - df_ret_window.rolling(z_window).mean()) / df_ret_window.rolling(z_window).std()
    return z


def compute_long_short_weights(z: pd.DataFrame, z_floor: float, z_cap: float) -> tuple:
    """LONG-SHORT balanced weights.

    LONG side: w_L_i = clip(z_i, z_floor, z_cap) where z_i >= z_floor; else 0
    SHORT side: w_S_i = clip(z_i, -z_cap, -z_floor) where z_i <= -z_floor; else 0 (negative values)

    Normalize independently so:
      sum(w_L) <= 1 (long capital capped at 1x)
      sum(|w_S|) <= 1 (short capital capped at 1x)
    Total gross exposure <= 2 (long + short), net <= 1 (long - short magnitude).
    Cash residual if either side row_sum < 1 (sparse signal).
    """
    # LONG raw: positive z above floor
    w_L_raw = z.clip(lower=z_floor, upper=z_cap).where(z >= z_floor, 0.0)
    # SHORT raw: negative z below -floor (kept negative)
    w_S_raw = z.clip(lower=-z_cap, upper=-z_floor).where(z <= -z_floor, 0.0)

    # Independent normalization per side (sum LONG, abs-sum SHORT)
    row_sum_L = w_L_raw.sum(axis=1)
    row_sum_S = w_S_raw.abs().sum(axis=1)

    # Scale floor = max(sum, 1.0). Sparse signal -> cash residual.
    scale_L = np.maximum(row_sum_L.values, 1.0)
    scale_S = np.maximum(row_sum_S.values, 1.0)

    w_L = w_L_raw.div(scale_L, axis=0)
    w_S = w_S_raw.div(scale_S, axis=0)  # stays negative

    # Combined weight: LONG positive + SHORT negative
    w = w_L + w_S  # net signed weight per sym

    return w, w_L, w_S


def simulate_portfolio_long_short(w: pd.DataFrame, w_L: pd.DataFrame, w_S: pd.DataFrame,
                                   returns: pd.DataFrame, fee_bp_one_way: float,
                                   short_funding_pct_day: float):
    """Daily-rebal LONG-SHORT portfolio.

    gross_ret_t = sum(w_lag * ret_t)  where w_lag has LONG positive + SHORT negative
    SHORT profits = -w_S_lag * ret_t (because w_S is negative, profit when ret<0)

    Turnover: sum(|w_t - w_{t-1}|) for both LONG and SHORT magnitude changes.
    Trading fee: turnover * fee_bp_one_way / 10000
    SHORT funding cost: |w_S_lag| * short_funding_pct_day  (drag every day held)
    """
    w = w.reindex(returns.index).fillna(0.0)
    w_L = w_L.reindex(returns.index).fillna(0.0)
    w_S = w_S.reindex(returns.index).fillna(0.0)

    # Lag weights by 1 day
    w_lag = w.shift(1).fillna(0.0)
    w_L_lag = w_L.shift(1).fillna(0.0)
    w_S_lag = w_S.shift(1).fillna(0.0)

    # Gross return: signed weights * returns
    gross_ret = (w_lag * returns).sum(axis=1)
    long_side_ret = (w_L_lag * returns).sum(axis=1)
    short_side_ret = (w_S_lag * returns).sum(axis=1)  # negative weights -> profit when ret<0

    # Turnover (rebalance applied at close of t-1, fee on day t)
    turnover_L = w_L.diff().abs().sum(axis=1).fillna(0.0)
    turnover_S = w_S.diff().abs().sum(axis=1).fillna(0.0)
    turnover_total = turnover_L + turnover_S

    fee_per_day = turnover_total * (fee_bp_one_way / 10000.0)
    fee_lag = fee_per_day.shift(1).fillna(0.0)

    # SHORT funding cost: |w_S_lag| * short_funding_pct_day each day held
    short_exposure_per_day = w_S_lag.abs().sum(axis=1)
    short_funding_drag = short_exposure_per_day * short_funding_pct_day

    net_ret = gross_ret - fee_lag - short_funding_drag

    return {
        "gross_ret": gross_ret,
        "net_ret": net_ret,
        "long_side_ret": long_side_ret,
        "short_side_ret": short_side_ret,
        "turnover_L": turnover_L,
        "turnover_S": turnover_S,
        "turnover_total": turnover_total,
        "fee_lag": fee_lag,
        "short_funding_drag": short_funding_drag,
        "w_lag": w_lag,
        "w_L_lag": w_L_lag,
        "w_S_lag": w_S_lag,
    }


def compute_metrics(ret_series: pd.Series, label: str):
    n = len(ret_series)
    if n < 2:
        return {"label": label, "n_days": n, "ann_return": None, "sharpe": None}
    mean_d = float(ret_series.mean())
    std_d = float(ret_series.std(ddof=1))
    ann_ret = (1.0 + mean_d) ** 365 - 1.0 if abs(mean_d) < 1 else None
    ann_vol = std_d * np.sqrt(365)
    sharpe = (mean_d / std_d) * np.sqrt(365) if std_d > 0 else 0.0
    downside = ret_series[ret_series < 0]
    down_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = (mean_d / down_std) * np.sqrt(365) if down_std > 0 else 0.0
    eq = (1.0 + ret_series).cumprod()
    peak = eq.cummax()
    dd = (eq / peak - 1.0)
    max_dd = float(dd.min())
    return {
        "label": label,
        "n_days": int(n),
        "mean_daily_bp": round(mean_d * 1e4, 4),
        "std_daily_bp": round(std_d * 1e4, 4),
        "ann_return_pct": round(ann_ret * 100, 3) if ann_ret is not None else None,
        "ann_vol_pct": round(ann_vol * 100, 3),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_dd_pct": round(max_dd * 100, 3),
        "total_return_pct": round((float(eq.iloc[-1]) - 1.0) * 100, 3),
    }


def per_sym_contribution_signed(w_lag: pd.DataFrame, returns: pd.DataFrame):
    """Per-sym signed contribution: profit when weight*ret > 0."""
    contrib = (w_lag * returns).sum(axis=0)
    abs_total = contrib.abs().sum() if contrib.abs().sum() > 0 else 1.0
    return {sym: {"abs_contrib_bp": float(contrib[sym] * 1e4),
                  "pct_share": float(contrib[sym] / abs_total * 100),
                  "positive": bool(contrib[sym] > 0)} for sym in contrib.index}


def long_short_decomposition(sim: dict, returns: pd.DataFrame):
    """LONG-side and SHORT-side independent alpha attribution."""
    metrics_long = compute_metrics(sim["long_side_ret"], "long_side_only")
    metrics_short = compute_metrics(sim["short_side_ret"], "short_side_only")

    # Per-sym LONG contribution
    long_contrib = (sim["w_L_lag"] * returns).sum(axis=0)
    # Per-sym SHORT contribution (w_S is negative; profit when ret<0 -> w_S*ret > 0)
    short_contrib = (sim["w_S_lag"] * returns).sum(axis=0)

    long_per_sym = {sym: {
        "contrib_bp": float(long_contrib[sym] * 1e4),
        "positive": bool(long_contrib[sym] > 0),
    } for sym in long_contrib.index}
    short_per_sym = {sym: {
        "contrib_bp": float(short_contrib[sym] * 1e4),
        "positive": bool(short_contrib[sym] > 0),
    } for sym in short_contrib.index}

    # 6 negative syms from paradigm 181 SHORT contribution
    neg_syms_short = {sym: short_per_sym[sym] for sym in NEGATIVE_SYMS_181 if sym in short_per_sym}
    neg_syms_short_positive = sum(1 for v in neg_syms_short.values() if v["positive"])
    neg_syms_short_total_bp = sum(v["contrib_bp"] for v in neg_syms_short.values())

    return {
        "long_side_metrics": metrics_long,
        "short_side_metrics": metrics_short,
        "long_per_sym": long_per_sym,
        "short_per_sym": short_per_sym,
        "paradigm_181_negative_syms_short_attribution": {
            "syms": NEGATIVE_SYMS_181,
            "per_sym": neg_syms_short,
            "syms_short_positive_count": neg_syms_short_positive,
            "syms_short_positive_ratio": round(neg_syms_short_positive / len(neg_syms_short), 3) if neg_syms_short else 0,
            "total_short_contrib_bp": round(neg_syms_short_total_bp * 1e4, 2) if neg_syms_short_total_bp else 0,
        },
    }


def quarter_breakdown(ret_series: pd.Series):
    out = {}
    grouped = ret_series.groupby(pd.Grouper(freq="QS"))
    for q_start, q_ret in grouped:
        if len(q_ret) < 5:
            continue
        eq = (1.0 + q_ret).cumprod()
        total = float(eq.iloc[-1] - 1.0)
        sh = float(q_ret.mean() / q_ret.std() * np.sqrt(365)) if q_ret.std() > 0 else 0.0
        key = f"{q_start.year}Q{q_start.quarter}"
        out[key] = {
            "quarter": key,
            "n_days": int(len(q_ret)),
            "total_return_pct": round(total * 100, 3),
            "sharpe": round(sh, 3),
            "positive": bool(total > 0),
        }
    return out


def util_diagnostics_long_short(sim: dict):
    """Util for LONG-SHORT: LONG capital + SHORT capital separately + combined."""
    w_L = sim["w_L_lag"]
    w_S = sim["w_S_lag"]
    long_per_day = w_L.sum(axis=1)
    short_per_day = w_S.abs().sum(axis=1)
    total_gross_per_day = long_per_day + short_per_day

    active_long = (w_L > 0).sum(axis=1)
    active_short = (w_S < 0).sum(axis=1)
    active_total = active_long + active_short

    return {
        "avg_active_syms_long": round(float(active_long.mean()), 3),
        "avg_active_syms_short": round(float(active_short.mean()), 3),
        "avg_active_syms_total": round(float(active_total.mean()), 3),
        "median_active_total": int(active_total.median()),
        "max_active_total": int(active_total.max()),
        "avg_long_capital": round(float(long_per_day.mean()), 4),
        "avg_short_capital": round(float(short_per_day.mean()), 4),
        "avg_gross_capital_deployed": round(float(total_gross_per_day.mean()), 4),
        "util_pct_gross_capital_avg": round(float(total_gross_per_day.mean()) * 100, 2),
        "util_pct_days_active": round(float((total_gross_per_day > 0).mean()) * 100, 2),
        "days_long_only": int(((long_per_day > 0) & (short_per_day == 0)).sum()),
        "days_short_only": int(((long_per_day == 0) & (short_per_day > 0)).sum()),
        "days_both_sides": int(((long_per_day > 0) & (short_per_day > 0)).sum()),
        "days_zero_exposure": int(((long_per_day == 0) & (short_per_day == 0)).sum()),
    }


def turnover_diagnostics_long_short(sim: dict):
    return {
        "avg_daily_turnover_long": round(float(sim["turnover_L"].mean()), 4),
        "avg_daily_turnover_short": round(float(sim["turnover_S"].mean()), 4),
        "avg_daily_turnover_total": round(float(sim["turnover_total"].mean()), 4),
        "max_daily_turnover_total": round(float(sim["turnover_total"].max()), 4),
        "total_fee_drag_pct": round(float(sim["fee_lag"].sum()) * 100, 3),
        "avg_daily_fee_bp": round(float(sim["fee_lag"].mean()) * 1e4, 4),
        "total_short_funding_drag_pct": round(float(sim["short_funding_drag"].sum()) * 100, 3),
        "avg_daily_short_funding_bp": round(float(sim["short_funding_drag"].mean()) * 1e4, 4),
    }


def permutation_test_ls(w: pd.DataFrame, w_L: pd.DataFrame, w_S: pd.DataFrame,
                         returns: pd.DataFrame, fee_bp: float, short_funding: float,
                         n_perm: int, seed: int):
    """Shuffle weight rows across time (preserving cross-sectional structure per day)."""
    rng = np.random.default_rng(seed)
    n_days = len(w)
    # Observed
    sim_obs = simulate_portfolio_long_short(w, w_L, w_S, returns, fee_bp, short_funding)
    net_obs = sim_obs["net_ret"]
    obs_sharpe = float(net_obs.mean() / net_obs.std() * np.sqrt(365)) if net_obs.std() > 0 else 0.0

    null_sharpes = []
    for i in range(n_perm):
        perm_idx = rng.permutation(n_days)
        w_perm = w.iloc[perm_idx].copy(); w_perm.index = w.index
        w_L_perm = w_L.iloc[perm_idx].copy(); w_L_perm.index = w_L.index
        w_S_perm = w_S.iloc[perm_idx].copy(); w_S_perm.index = w_S.index
        sim_p = simulate_portfolio_long_short(w_perm, w_L_perm, w_S_perm, returns, fee_bp, short_funding)
        np_ret = sim_p["net_ret"]
        if np_ret.std() > 0:
            sh = float(np_ret.mean() / np_ret.std() * np.sqrt(365))
        else:
            sh = 0.0
        null_sharpes.append(sh)
    null_sharpes = np.array(null_sharpes)
    null_mean = float(null_sharpes.mean())
    null_std = float(null_sharpes.std(ddof=1))
    sharpe_excess = obs_sharpe - null_mean
    p_value = float((null_sharpes >= obs_sharpe).mean())
    z_excess = (obs_sharpe - null_mean) / null_std if null_std > 0 else 0.0
    return {
        "obs_sharpe": round(obs_sharpe, 4),
        "null_mean_sharpe": round(null_mean, 4),
        "null_std_sharpe": round(null_std, 4),
        "sharpe_excess": round(sharpe_excess, 4),
        "z_excess": round(z_excess, 4),
        "perm_p_value": round(p_value, 4),
        "n_perm": n_perm,
    }


def four_cond_audit_ls(metrics_net, util, q_port, per_sym, perm_result, ls_decomp):
    """Lesson #20 4-cond + life-changing 4-dim for LONG-SHORT.

    Cond 1 three-gate: z_excess >= 2.0 + perm_p <= 0.10 + sharpe_excess > 0 vs market-neutral baseline (0)
    Cond 2 concentration: signed contribution positive ratio (combined LONG + SHORT)
    Cond 3 temporal: quarters positive
    Cond 4 life-changing 4-dim
    """
    sharpe_excess = perm_result["sharpe_excess"]
    perm_p = perm_result["perm_p_value"]
    z_excess = perm_result["z_excess"]
    cond1_pass = (sharpe_excess >= 0.5) and (perm_p <= 0.10) and (z_excess >= 2.0)

    syms_positive = sum(1 for s in per_sym.values() if s["positive"])
    syms_pos_ratio = syms_positive / len(per_sym) if per_sym else 0
    cond2_pass = syms_pos_ratio >= 0.5

    q_positive = sum(1 for q in q_port.values() if q["positive"])
    q_total = len(q_port)
    cond3_pass = (q_positive / q_total) >= 0.5 if q_total > 0 else False

    n_days = metrics_net["n_days"]
    effective_trades_per_yr = 365 * util.get("avg_active_syms_total", 0)
    sharpe_p = metrics_net.get("sharpe", 0) or 0
    ann_ret_pct = metrics_net.get("ann_return_pct", 0) or 0
    # vs market-neutral 0% baseline
    edge_vs_neutral_pct = ann_ret_pct  # since baseline = 0
    per_trade_edge_bp = (edge_vs_neutral_pct / 100) / effective_trades_per_yr * 1e4 if effective_trades_per_yr > 0 else 0
    util_pct = util.get("util_pct_gross_capital_avg", 0)

    dim4_pass = {
        "trades_per_yr_ge_12": effective_trades_per_yr >= 12,
        "per_trade_edge_ge_2pct": per_trade_edge_bp >= 200,
        "capital_util_ge_30pct": util_pct >= 30,
        "sharpe_ge_1_5": sharpe_p >= 1.5,
    }
    dim4_all_pass = all(dim4_pass.values())

    # Lesson #72 boundary verdict computation
    long_sharpe = ls_decomp["long_side_metrics"].get("sharpe", 0) or 0
    short_sharpe = ls_decomp["short_side_metrics"].get("sharpe", 0) or 0
    long_ann = ls_decomp["long_side_metrics"].get("ann_return_pct", 0) or 0
    short_ann = ls_decomp["short_side_metrics"].get("ann_return_pct", 0) or 0

    if z_excess >= 2.0 or sharpe_p >= 1.0:
        lesson_72_verdict = "LONG_ONLY_CONSTRAINT_PROBLEM"
        lesson_72_reason = f"long-short alpha recovered (z_excess={z_excess:.2f}, sharpe={sharpe_p:.3f}); long-only paradigm 181/182/183 was constrained by universe-level downtrend bias"
    elif sharpe_p >= 0.5:
        lesson_72_verdict = "UNIVERSE_DOWNTREND_BIAS_SHORT_PARTIAL_ALPHA"
        lesson_72_reason = f"partial alpha (sharpe={sharpe_p:.3f}); SHORT side carries some alpha vs LONG side"
    else:
        lesson_72_verdict = "LESSON_72_STRICT_UNIVERSAL_CONFIRMED"
        lesson_72_reason = f"long-short also alpha-void (sharpe={sharpe_p:.3f}); continuous-weighting framework family Tier 4 retire candidate strengthened"

    return {
        "cond1_three_gate": {
            "pass": cond1_pass,
            "sharpe_excess": sharpe_excess,
            "z_excess": z_excess,
            "perm_p": perm_p,
        },
        "cond2_concentration": {
            "pass": cond2_pass,
            "syms_positive": syms_positive,
            "syms_total": len(per_sym),
            "ratio": round(syms_pos_ratio, 3),
        },
        "cond3_temporal": {
            "pass": cond3_pass,
            "quarters_positive": q_positive,
            "quarters_total": q_total,
        },
        "cond4_life_changing_4dim": {
            "pass": dim4_all_pass,
            "trades_per_yr_effective": round(effective_trades_per_yr, 1),
            "per_trade_edge_bp": round(per_trade_edge_bp, 3),
            "capital_util_pct": util_pct,
            "sharpe": sharpe_p,
            "dim_pass": dim4_pass,
        },
        "lesson_72_boundary": {
            "verdict": lesson_72_verdict,
            "reason": lesson_72_reason,
            "long_side_sharpe": long_sharpe,
            "short_side_sharpe": short_sharpe,
            "long_side_ann_return_pct": long_ann,
            "short_side_ann_return_pct": short_ann,
        },
        "all_4_cond_pass": cond1_pass and cond2_pass and cond3_pass and dim4_all_pass,
    }


def verdict_tree_ls(audit, metrics_net, util, ls_decomp):
    util_pct = util.get("util_pct_gross_capital_avg", 0)
    if util_pct < 30:
        return "HALT_BY_UTIL", f"gross_capital_util {util_pct:.1f}% < 30% (Lesson #71 path C breach)"

    cond1 = audit["cond1_three_gate"]
    long_sharpe = ls_decomp["long_side_metrics"].get("sharpe", 0) or 0
    short_sharpe = ls_decomp["short_side_metrics"].get("sharpe", 0) or 0

    if not cond1["pass"]:
        # Check BROAD_FALSIFIED if both sides alpha-void
        if long_sharpe < 0.3 and short_sharpe < 0.3:
            return "BROAD_FALSIFIED", f"both LONG (sharpe={long_sharpe:.3f}) and SHORT (sharpe={short_sharpe:.3f}) alpha-void; z_excess={cond1['z_excess']:.2f}"
        if cond1["sharpe_excess"] < 0:
            return "PORTFOLIO_ALPHA_INSIGNIFICANT", f"sharpe_excess {cond1['sharpe_excess']:+.3f} <= 0"
        elif cond1["z_excess"] < 2.0:
            return "PORTFOLIO_ALPHA_INSIGNIFICANT", f"z_excess {cond1['z_excess']:.2f} < 2.0"
        elif cond1["perm_p"] > 0.10:
            return "PORTFOLIO_ALPHA_INSIGNIFICANT", f"perm_p {cond1['perm_p']:.3f} > 0.10"

    dim4 = audit["cond4_life_changing_4dim"]
    if not dim4["pass"]:
        fails = [k for k, v in dim4["dim_pass"].items() if not v]
        return "NARROW_SCOPE_LIFE_CHANGING_FAIL", f"cond1 PASS but 4-dim FAIL: {fails}"

    if not audit["cond2_concentration"]["pass"]:
        return "NARROW_SCOPE_CONCENTRATION_FAIL", f"syms_pos_ratio {audit['cond2_concentration']['ratio']:.2f} < 0.5"

    if not audit["cond3_temporal"]["pass"]:
        return "FRAGILE_TEMPORAL_FAIL", f"quarters positive {audit['cond3_temporal']['quarters_positive']}/{audit['cond3_temporal']['quarters_total']}"

    return "PASS_R1_FULL", "all 4-cond PASS"


def main():
    logger.info("paradigm 184 R-1 continuous-weighted LONG-SHORT BALANCED daily-rebal")
    df_close, df_ret = load_daily_returns()
    logger.info("daily close: %d days x %d syms", len(df_close), df_close.shape[1])

    z = compute_z_scores(df_close, RETURN_WINDOW_D, Z_WINDOW_D)
    logger.info("z-score panel shape: %s, NaN ratio: %.2f%%",
                z.shape, z.isna().mean().mean() * 100)
    z = z.dropna(how="all")

    w, w_L, w_S = compute_long_short_weights(z, Z_FLOOR, Z_CAP)
    common_idx = w.index.intersection(df_ret.index)
    w = w.loc[common_idx]
    w_L = w_L.loc[common_idx]
    w_S = w_S.loc[common_idx]
    returns = df_ret.loc[common_idx]
    logger.info("aligned panel: %d days x %d syms", len(w), w.shape[1])

    sim = simulate_portfolio_long_short(w, w_L, w_S, returns, FEE_BP_ONE_WAY, SHORT_FUNDING_PCT_PER_DAY)
    logger.info("portfolio gross=%.4f%%/day, net=%.4f%%/day, long=%.4f%%/day, short=%.4f%%/day",
                sim["gross_ret"].mean() * 100, sim["net_ret"].mean() * 100,
                sim["long_side_ret"].mean() * 100, sim["short_side_ret"].mean() * 100)

    # Benchmarks
    eq_basket_ret = returns.mean(axis=1)
    btc_ret = returns["BTCUSDT"] if "BTCUSDT" in returns.columns else None

    # Metrics
    metrics_gross = compute_metrics(sim["gross_ret"], "portfolio_gross")
    metrics_net = compute_metrics(sim["net_ret"], "portfolio_net")
    metrics_eq = compute_metrics(eq_basket_ret, "reference_equal_weight_basket")
    metrics_btc = compute_metrics(btc_ret, "reference_btc_bnh") if btc_ret is not None else None

    # vs market-neutral (0%) baseline = portfolio itself
    metrics_alpha_eq = compute_metrics(sim["net_ret"] - eq_basket_ret, "alpha_vs_equal_weight_REFERENCE_ONLY")

    # LONG/SHORT decomposition (CRITICAL for Lesson #72 boundary)
    ls_decomp = long_short_decomposition(sim, returns)

    # Per-sym signed contribution
    per_sym = per_sym_contribution_signed(sim["w_lag"], returns)

    # Quarter
    q_port = quarter_breakdown(sim["net_ret"])
    q_long = quarter_breakdown(sim["long_side_ret"])
    q_short = quarter_breakdown(sim["short_side_ret"])

    # Util / turnover
    util = util_diagnostics_long_short(sim)
    logger.info("util: avg_active_total=%.2f, gross_capital=%.1f%%",
                util["avg_active_syms_total"], util["util_pct_gross_capital_avg"])
    turn_diag = turnover_diagnostics_long_short(sim)

    # Permutation test
    logger.info("running %d permutations...", N_PERM)
    perm_result = permutation_test_ls(w, w_L, w_S, returns, FEE_BP_ONE_WAY,
                                       SHORT_FUNDING_PCT_PER_DAY, N_PERM, RNG_SEED)
    logger.info("perm: obs_sharpe=%.3f, null_mean=%.3f, z_excess=%.2f, p=%.4f",
                perm_result["obs_sharpe"], perm_result["null_mean_sharpe"],
                perm_result["z_excess"], perm_result["perm_p_value"])

    # 4-cond audit + Lesson #72 boundary
    audit = four_cond_audit_ls(metrics_net, util, q_port, per_sym, perm_result, ls_decomp)

    verdict, reason = verdict_tree_ls(audit, metrics_net, util, ls_decomp)
    logger.info("VERDICT: %s — %s", verdict, reason)
    logger.info("Lesson #72 boundary: %s", audit["lesson_72_boundary"]["verdict"])

    result = {
        "paradigm_id": 184,
        "paradigm_slug": "alt_per_sym_30d_return_z_continuous_weighted_long_short_balanced_neutral_daily_rebal",
        "phase": "R-1",
        "verdict": verdict,
        "verdict_reason": reason,
        "run_ts": datetime.utcnow().isoformat() + "Z",
        "lesson_70_corollary_scope_prescreen": {
            "branch_a_spec_adaptive_expansion_of_paradigm_181": False,
            "branch_b_direction_class_shift_new_paradigm_class": True,
            "verdict": "PROCEED_NEW_DIRECTION_CLASS",
            "rationale": [
                "paradigm 181 = R-1 GRAVEYARD, NOT R-5 LIVE survivor (Lesson #70 corollary scope inapplicable)",
                "Long-only vs long-short = Fama-French / Jegadeesh-Titman literature classical separate strategy families",
                "Direction class shift = portfolio construction methodology fundamental change (capital deployed 2x, market neutral hedge mechanism)",
                "paradigm 181 graveyard Path B next-action explicitly mentions separate R-1 obligation",
                "paradigm 182 graveyard precedent (same rationale, (b) PROCEED verdict adopted)",
            ],
            "second_dogfood_of_lesson_70_corollary_scope_clarification": True,
        },
        "config": {
            "symbols": SYMBOLS,
            "n_syms": len(SYMBOLS),
            "return_window_d": RETURN_WINDOW_D,
            "z_window_d": Z_WINDOW_D,
            "z_floor": Z_FLOOR,
            "z_cap": Z_CAP,
            "fee_bp_one_way": FEE_BP_ONE_WAY,
            "short_funding_pct_per_day": SHORT_FUNDING_PCT_PER_DAY,
            "n_perm": N_PERM,
            "rng_seed": RNG_SEED,
        },
        "panel": {
            "n_days_aligned": int(len(sim["net_ret"])),
            "date_range": [str(sim["net_ret"].index[0]), str(sim["net_ret"].index[-1])],
        },
        "metrics": {
            "portfolio_gross": metrics_gross,
            "portfolio_net": metrics_net,
            "reference_equal_weight": metrics_eq,
            "reference_btc_bnh": metrics_btc,
            "alpha_vs_equal_weight_REFERENCE_ONLY": metrics_alpha_eq,
        },
        "long_short_decomposition": ls_decomp,
        "util_diagnostics_long_short": util,
        "turnover_diagnostics_long_short": turn_diag,
        "permutation_test": perm_result,
        "per_sym_contribution_signed": per_sym,
        "quarter_breakdown_portfolio_net": q_port,
        "quarter_breakdown_long_side": q_long,
        "quarter_breakdown_short_side": q_short,
        "four_cond_audit": audit,
        "lesson_72_boundary_verdict": audit["lesson_72_boundary"],
        "lesson_71_path_c_escape": {
            "is_state_machine": False,
            "is_continuous_weighting": True,
            "multi_position_simultaneous": True,
            "signal_intensity_proportional": True,
            "util_target_30pct": util["util_pct_gross_capital_avg"] >= 30,
            "util_empirical_pct": util["util_pct_gross_capital_avg"],
            "escape_verified": util["util_pct_gross_capital_avg"] >= 30,
            "note": "LONG-SHORT path: capital deployed 2x structural (LONG side + SHORT side simultaneous)",
        },
        "memory_compliance": {
            "no_freemium_trial": True,
            "life_changing_4dim_audited": True,
            "persistence_over_efficiency": True,
            "continuous_parallel_campaign": True,
        },
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info("wrote %s", out_path)

    # Time series dump
    ts_df = pd.DataFrame({
        "gross_ret": sim["gross_ret"],
        "net_ret": sim["net_ret"],
        "long_side_ret": sim["long_side_ret"],
        "short_side_ret": sim["short_side_ret"],
        "eq_basket": eq_basket_ret,
        "btc_bnh": btc_ret if btc_ret is not None else 0,
        "turnover_long": sim["turnover_L"],
        "turnover_short": sim["turnover_S"],
        "fee_lag": sim["fee_lag"],
        "short_funding_drag": sim["short_funding_drag"],
        "long_capital": sim["w_L_lag"].sum(axis=1),
        "short_capital": sim["w_S_lag"].abs().sum(axis=1),
        "active_long_syms": (sim["w_L_lag"] > 0).sum(axis=1),
        "active_short_syms": (sim["w_S_lag"] < 0).sum(axis=1),
    })
    ts_path = OUT_DIR / "r1__timeseries.csv"
    ts_df.to_csv(ts_path)
    logger.info("wrote %s", ts_path)

    return result


if __name__ == "__main__":
    result = main()
    print(f"\nVERDICT: {result['verdict']}")
    print(f"REASON: {result['verdict_reason']}")
    print(f"Lesson #72 boundary: {result['four_cond_audit']['lesson_72_boundary']['verdict']}")
    sys.exit(0)
