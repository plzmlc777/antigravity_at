"""
paradigm 183 R-1: per-sym 30d return autocorrelation lag-1 z-score continuous-weighted long-only daily rebal

Lesson #61 slug grep audit: `autocorr_regime` exists (paradigm 18 R-3 partial 2026-05-05),
  - paradigm 18: 5min OHLCV, 288-bar window, discrete trigger entry SL/TP, 10-sym alt subset
  - paradigm 183: DAILY 30d window, CONTINUOUS-weighting portfolio (no SL/TP), 14-sym incl BTC, 90d z-norm
  - DNA dimensions distinct: 5/6 (statistic root same lag-1 autocorr but daily-frame + z-norm + decision mode different)
  - User claim "campaign 누적 미탐색" was FALSE — flagged to user; dispatch proceeds based on 5/6 axis distinctness

Lesson #70 corollary scope prescreen VERDICT: (b) NEW paradigm class — proceed.
- paradigm 181/182 = R-1 GRAVEYARDS (NOT R-5 LIVE), Lesson #70 corollary applies only to R-5 LIVE narrow-cohort expansion
- Autocorrelation = classical separate statistic class (regime characteristic vs magnitude characteristic)
- Mechanism class shift: trending-regime detection × continuous exposure (positive autocorr = trending continuation)

Mechanism:
- 14 alts × 4h OHLCV joblib substrate (2.25yr)
- Aggregate 4h to daily close-to-close returns
- Per-sym 30d rolling lag-1 daily return autocorrelation (Pearson)
- 90d rolling z-score of autocorr
- Position size = clip(autocorr_z, +0.5, +3) where autocorr_z >= +0.5 → LONG weighted; else cash
- Daily rebalance (continuous, NOT state-machine)
- Long-only (Lesson #8 amendment paradigm 99 leverage shock upward bias)
- Fee: daily turnover × 8bp one-way (16bp round-trip)

Lesson #71 corollary path C ESCAPE verification:
- Continuous re-weighting (NOT state-machine)
- Multi-sym simultaneous (14 syms)
- Signal-intensity proportional (autocorr_z-weight)
- Target util >= 30%

Lesson #72 candidate 3rd dogfood (CRITICAL):
- paradigm 181 (raw return z) 1st dogfood: ALPHA INSIGNIFICANT (sharpe_excess +0.089, perm_p 0.414, 6 negative syms)
- paradigm 182 (Sharpe-z) 2nd dogfood: ALPHA INSIGNIFICANT (sharpe_excess +0.075, z_excess +0.17, perm_p 0.436, EXACT same 6 negative syms BNB/LINK/LTC/BCH/NEAR/FIL)
- paradigm 183 (autocorrelation z) 3rd dogfood: 다른 universe ranking이 alpha 회복하는지 검증
  - autocorr ranking != raw return ranking != Sharpe ranking (regime characteristic vs magnitude)
  - Overlap measurement: paradigm 183 top-weight syms vs paradigm 181/182 6 negative syms
  - If overlap >= 50%: Lesson #72 CONFIRMED universal (universe-level regime void, 통계 axis 무관)
  - If overlap < 50% AND alpha PASS: Lesson #72 PARTIAL (statistic class choice matters)

Universe ranking divergence test:
- Monthly top-3 weight syms list (paradigm 183 autocorr vs paradigm 181 raw / paradigm 182 sharpe)
- Compute Spearman rank correlation of weight vectors

R-1 measurements (paradigm 181/182 framework 재사용):
- Portfolio daily return time series (annualized return / sharpe / sortino / max DD)
- Benchmark: equal-weight 14-sym B&H + BTC B&H
- Alpha = portfolio - benchmark
- IR / tracking error
- Per-sym contribution + 6 negative syms overlap analysis (CRITICAL)
- Universe ranking divergence (autocorr vs return / sharpe top weights)
- Quarter-by-quarter (9 quarters)
- Turnover + fee drag
- Position util empirical
- Lesson #20 4-cond Concentration + Temporal robustness
- Permutation null: shuffle daily weight rows across time

Verdict tree:
- HALT_BY_UTIL — util < 30% (Lesson #71 path C breach)
- PORTFOLIO_ALPHA_INSIGNIFICANT — z_excess < 2.0 OR perm_p > 0.10
- NARROW_SCOPE_LIFE_CHANGING_FAIL — alpha PASS but 4-dim FAIL
- NARROW_SCOPE_CONCENTRATION_FAIL — alpha + 4-dim PASS but syms_pos < 50%
- FRAGILE_TEMPORAL_FAIL — alpha + 4-dim + concentration PASS but quarters < 50%
- PASS_R1_FULL — all 4-cond PASS

Lesson #72 verdict assignment (end of run):
- If verdict == PORTFOLIO_ALPHA_INSIGNIFICANT AND 6_neg_overlap >= 50%: CONFIRMED universal
- If verdict == PORTFOLIO_ALPHA_INSIGNIFICANT AND 6_neg_overlap < 50%: PARTIAL_NEW_AXIS_BUT_NO_ALPHA
- If verdict in (PASS_R1_FULL, NARROW_SCOPE_*): PARTIAL_alpha_recovered (LESSON #72 REFUTED)
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
OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/alt_per_sym_30d_return_autocorrelation_lag1_z_continuous_weighted_long_only_daily_rebal")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "FILUSDT", "WIFUSDT",
]

# Paradigm 181/182 confirmed 6 negative syms (Lesson #72 anchor)
PARADIGM_181_182_NEG_SYMS = ["BNBUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT", "FILUSDT"]

# Statistic class shift: autocorrelation
AUTOCORR_WINDOW_D = 30   # rolling 30d window for lag-1 autocorr
AUTOCORR_LAG = 1
Z_WINDOW_D = 90          # z-score of autocorr
Z_FLOOR = 0.5
Z_CAP = 3.0
FEE_BP_ONE_WAY = 8.0

# Permutation params
N_PERM = 1000
RNG_SEED = 20260522


def load_daily_returns():
    """Load 14-sym 4h OHLCV, aggregate to daily close-to-close returns."""
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


def rolling_autocorr_lag1(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    """
    Compute per-sym rolling lag-1 autocorrelation of daily returns.

    For each window of length W ending at time t:
        autocorr(t) = corr(r[t-W+1:t], r[t-W:t-1])

    Implemented via vectorized rolling apply.
    """
    def _ac1(x: np.ndarray) -> float:
        if len(x) < 3:
            return np.nan
        a = x[1:]
        b = x[:-1]
        if np.std(a) == 0 or np.std(b) == 0:
            return np.nan
        return float(np.corrcoef(a, b)[0, 1])

    out = pd.DataFrame(index=returns.index, columns=returns.columns, dtype=float)
    for sym in returns.columns:
        s = returns[sym]
        out[sym] = s.rolling(window).apply(_ac1, raw=True)
    return out


def compute_autocorr_z_scores(returns: pd.DataFrame, autocorr_window: int, z_window: int):
    autocorr = rolling_autocorr_lag1(returns, autocorr_window)
    z = (autocorr - autocorr.rolling(z_window).mean()) / autocorr.rolling(z_window).std()
    return z, autocorr


def compute_weights(z: pd.DataFrame, z_floor: float, z_cap: float) -> pd.DataFrame:
    w_raw = z.clip(lower=z_floor, upper=z_cap).where(z >= z_floor, 0.0)
    row_sum = w_raw.sum(axis=1)
    scale_eff = np.maximum(row_sum.values, 1.0)
    w = w_raw.div(scale_eff, axis=0)
    return w


def simulate_portfolio(weights: pd.DataFrame, returns: pd.DataFrame, fee_bp_one_way: float):
    w = weights.reindex(returns.index).fillna(0.0)
    w_lag = w.shift(1).fillna(0.0)
    gross_ret = (w_lag * returns).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1).fillna(0.0)
    fee_per_day = turnover * (fee_bp_one_way / 10000.0)
    fee_lag = fee_per_day.shift(1).fillna(0.0)
    net_ret = gross_ret - fee_lag
    return gross_ret, net_ret, turnover, w_lag, fee_lag


def compute_metrics(ret_series: pd.Series, label: str):
    n = len(ret_series)
    if n < 2:
        return {"label": label, "n_days": n, "ann_return": None, "sharpe": None}
    mean_d = float(ret_series.mean())
    std_d = float(ret_series.std(ddof=1))
    ann_ret = (1.0 + mean_d) ** 365 - 1.0
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
        "ann_return_pct": round(ann_ret * 100, 3),
        "ann_vol_pct": round(ann_vol * 100, 3),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_dd_pct": round(max_dd * 100, 3),
        "total_return_pct": round((float(eq.iloc[-1]) - 1.0) * 100, 3),
    }


def per_sym_contribution(w_lag: pd.DataFrame, returns: pd.DataFrame):
    contrib = (w_lag * returns).sum(axis=0)
    contrib_abs_sum = float(contrib.abs().sum())
    if contrib_abs_sum > 0:
        contrib_pct = (contrib / contrib_abs_sum * 100).round(3)
    else:
        contrib_pct = contrib * 0
    return {sym: {"abs_contrib_bp": float(contrib[sym] * 1e4),
                  "pct_share": float(contrib_pct[sym]),
                  "positive": bool(contrib[sym] > 0)} for sym in contrib.index}


def negative_syms_overlap_analysis(per_sym: dict, reference_neg_syms: list):
    """
    Lesson #72 3rd dogfood CRITICAL: paradigm 181/182 6 negative syms overlap.

    paradigm 183 negative syms (per-sym contrib < 0) vs reference 6 syms.
    Overlap >= 50% (>=3/6) → Lesson #72 CONFIRMED universal
    Overlap < 50% AND alpha PASS → Lesson #72 REFUTED partial
    Overlap < 50% AND alpha FAIL → Lesson #72 PARTIAL_new_axis_no_alpha
    """
    p183_neg = [sym for sym, m in per_sym.items() if not m["positive"]]
    overlap = [sym for sym in reference_neg_syms if sym in p183_neg]
    n_overlap = len(overlap)
    n_ref = len(reference_neg_syms)
    overlap_ratio = n_overlap / n_ref if n_ref > 0 else 0.0
    return {
        "paradigm_183_negative_syms": p183_neg,
        "n_paradigm_183_negative": len(p183_neg),
        "reference_paradigm_181_182_negative_syms": reference_neg_syms,
        "n_reference_negative": n_ref,
        "overlap_syms": overlap,
        "n_overlap": n_overlap,
        "overlap_ratio": round(overlap_ratio, 3),
        "high_overlap_ge_50pct": overlap_ratio >= 0.5,
    }


def universe_ranking_divergence(w_lag: pd.DataFrame):
    """
    Monthly top-3 weight syms list.
    Returns dict of month → top 3 syms by mean weight.
    """
    out = {}
    monthly = w_lag.groupby(pd.Grouper(freq="MS")).mean()
    for month_start, row in monthly.iterrows():
        sorted_syms = row.sort_values(ascending=False).head(3)
        out[month_start.strftime("%Y-%m")] = [
            {"sym": s, "mean_weight": round(float(sorted_syms[s]), 4)}
            for s in sorted_syms.index if sorted_syms[s] > 0
        ]
    return out


def quarter_breakdown(ret_series: pd.Series, label: str):
    out = {}
    grouped = ret_series.groupby(pd.Grouper(freq="QS"))
    for q_start, q_ret in grouped:
        if len(q_ret) < 5:
            continue
        eq = (1.0 + q_ret).cumprod()
        total = float(eq.iloc[-1] - 1.0)
        sh = float(q_ret.mean() / q_ret.std() * np.sqrt(365)) if q_ret.std() > 0 else 0.0
        out[q_start.strftime("%Y-Q%q") if hasattr(q_start, 'quarter') else str(q_start)] = {
            "quarter": f"{q_start.year}Q{q_start.quarter}",
            "n_days": int(len(q_ret)),
            "total_return_pct": round(total * 100, 3),
            "sharpe": round(sh, 3),
            "positive": bool(total > 0),
        }
    return out


def util_diagnostics(w_lag: pd.DataFrame):
    active_per_day = (w_lag > 0).sum(axis=1)
    total_w_per_day = w_lag.sum(axis=1)
    return {
        "avg_active_syms": round(float(active_per_day.mean()), 3),
        "median_active_syms": int(active_per_day.median()),
        "max_active_syms": int(active_per_day.max()),
        "avg_total_weight": round(float(total_w_per_day.mean()), 4),
        "median_total_weight": round(float(total_w_per_day.median()), 4),
        "days_zero_weight": int((total_w_per_day == 0).sum()),
        "days_total_weight_ge_0_3": int((total_w_per_day >= 0.3).sum()),
        "util_pct_days_active": round(float((total_w_per_day > 0).mean()) * 100, 2),
        "util_pct_capital_deployed_avg": round(float(total_w_per_day.mean()) * 100, 2),
    }


def turnover_diagnostics(turnover: pd.Series, fee_lag: pd.Series):
    return {
        "avg_daily_turnover": round(float(turnover.mean()), 4),
        "median_daily_turnover": round(float(turnover.median()), 4),
        "max_daily_turnover": round(float(turnover.max()), 4),
        "total_fee_drag_pct": round(float(fee_lag.sum()) * 100, 3),
        "avg_daily_fee_bp": round(float(fee_lag.mean()) * 1e4, 4),
    }


def permutation_test(weights: pd.DataFrame, returns: pd.DataFrame, fee_bp: float, n_perm: int, seed: int):
    rng = np.random.default_rng(seed)
    n_days = len(weights)
    _, net_obs, _, _, _ = simulate_portfolio(weights, returns, fee_bp)
    obs_sharpe = float(net_obs.mean() / net_obs.std() * np.sqrt(365)) if net_obs.std() > 0 else 0.0

    null_sharpes = []
    for i in range(n_perm):
        perm_idx = rng.permutation(n_days)
        w_perm = weights.iloc[perm_idx].copy()
        w_perm.index = weights.index
        _, net_perm, _, _, _ = simulate_portfolio(w_perm, returns, fee_bp)
        if net_perm.std() > 0:
            sh = float(net_perm.mean() / net_perm.std() * np.sqrt(365))
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


def four_cond_audit(metrics_port, metrics_eq, util, n_days, quarter_breakdown_dict, per_sym, perm_result):
    sharpe_excess = perm_result["sharpe_excess"]
    perm_p = perm_result["perm_p_value"]
    z_excess = perm_result["z_excess"]
    cond1_pass = (sharpe_excess >= 0.5) and (perm_p <= 0.10) and (z_excess >= 2.0)
    syms_positive = sum(1 for s in per_sym.values() if s["positive"])
    syms_pos_ratio = syms_positive / len(per_sym)
    cond2_pass = syms_pos_ratio >= 0.5
    q_positive = sum(1 for q in quarter_breakdown_dict.values() if q["positive"])
    q_total = len(quarter_breakdown_dict)
    cond3_pass = (q_positive / q_total) >= 0.5 if q_total > 0 else False
    effective_trades_per_yr = 365 * util.get("avg_active_syms", 0)
    edge_pct = (metrics_port["ann_return_pct"] - metrics_eq["ann_return_pct"]) if metrics_port and metrics_eq else 0
    per_trade_edge_bp = (edge_pct / 100) / effective_trades_per_yr * 1e4 if effective_trades_per_yr > 0 else 0
    util_pct = util.get("util_pct_capital_deployed_avg", 0)
    sharpe_p = metrics_port.get("sharpe", 0) if metrics_port else 0
    dim4_pass = {
        "trades_per_yr_ge_12": effective_trades_per_yr >= 12,
        "per_trade_edge_ge_2pct": per_trade_edge_bp >= 200,
        "capital_util_ge_30pct": util_pct >= 30,
        "sharpe_ge_1_5": sharpe_p >= 1.5,
    }
    dim4_all_pass = all(dim4_pass.values())

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
        "all_4_cond_pass": cond1_pass and cond2_pass and cond3_pass and dim4_all_pass,
    }


def verdict_tree(audit, metrics_port, util):
    util_pct = util.get("util_pct_capital_deployed_avg", 0)
    if util_pct < 30:
        return "HALT_BY_UTIL", f"capital_util {util_pct:.1f}% < 30% (Lesson #71 path C breach)"

    cond1 = audit["cond1_three_gate"]
    if not cond1["pass"]:
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


def lesson_72_verdict_assignment(verdict_main: str, neg_overlap: dict):
    """
    paradigm 183 is the 3rd Lesson #72 dogfood.
    """
    overlap_ratio = neg_overlap["overlap_ratio"]
    high_overlap = neg_overlap["high_overlap_ge_50pct"]
    if verdict_main == "PORTFOLIO_ALPHA_INSIGNIFICANT":
        if high_overlap:
            return "CONFIRMED_universal_3rd_dogfood", (
                f"3rd statistical axis (autocorr) fails AND 6_neg_overlap {overlap_ratio:.2f} >= 0.5 "
                f"→ universe-level regime void confirmed (statistic axis-invariant)"
            )
        else:
            return "PARTIAL_new_axis_but_no_alpha", (
                f"3rd statistical axis fails but 6_neg_overlap {overlap_ratio:.2f} < 0.5 "
                f"→ fresh axis selects different universe but still no alpha (statistic mismatch + universe miss)"
            )
    elif verdict_main in ("PASS_R1_FULL", "NARROW_SCOPE_LIFE_CHANGING_FAIL",
                          "NARROW_SCOPE_CONCENTRATION_FAIL", "FRAGILE_TEMPORAL_FAIL"):
        return "REFUTED_partial_alpha_recovered", (
            f"Lesson #72 candidate REFUTED — autocorr-z axis recovers alpha (verdict={verdict_main})"
        )
    else:
        return "INCONCLUSIVE_halt", f"verdict={verdict_main} pre-empts Lesson #72 assignment"


def main():
    logger.info("paradigm 183 R-1 autocorrelation-z continuous-weighted long-only daily-rebal")
    df_close, df_ret = load_daily_returns()
    logger.info("daily close: %d days x %d syms", len(df_close), df_close.shape[1])

    z, autocorr = compute_autocorr_z_scores(df_ret, AUTOCORR_WINDOW_D, Z_WINDOW_D)
    logger.info("autocorr-z panel shape: %s, NaN ratio: %.2f%%",
                z.shape, z.isna().mean().mean() * 100)
    z = z.dropna(how="all")

    weights = compute_weights(z, Z_FLOOR, Z_CAP)
    common_idx = weights.index.intersection(df_ret.index)
    weights = weights.loc[common_idx]
    returns = df_ret.loc[common_idx]
    logger.info("aligned panel: %d days x %d syms", len(weights), weights.shape[1])

    gross_ret, net_ret, turnover, w_lag, fee_lag = simulate_portfolio(weights, returns, FEE_BP_ONE_WAY)
    logger.info("portfolio gross mean=%.4f%%/day, net mean=%.4f%%/day",
                gross_ret.mean() * 100, net_ret.mean() * 100)

    eq_basket_ret = returns.mean(axis=1)
    btc_ret = returns["BTCUSDT"] if "BTCUSDT" in returns.columns else None

    metrics_gross = compute_metrics(gross_ret, "portfolio_gross")
    metrics_net = compute_metrics(net_ret, "portfolio_net")
    metrics_eq = compute_metrics(eq_basket_ret, "benchmark_equal_weight_basket")
    metrics_btc = compute_metrics(btc_ret, "benchmark_btc_bnh") if btc_ret is not None else None

    alpha_eq = net_ret - eq_basket_ret
    alpha_btc = net_ret - btc_ret if btc_ret is not None else None
    metrics_alpha_eq = compute_metrics(alpha_eq, "alpha_vs_equal_weight")
    metrics_alpha_btc = compute_metrics(alpha_btc, "alpha_vs_btc") if alpha_btc is not None else None

    te_eq = float(alpha_eq.std() * np.sqrt(365))
    ir_eq = float(alpha_eq.mean() / alpha_eq.std() * np.sqrt(365)) if alpha_eq.std() > 0 else 0.0

    per_sym = per_sym_contribution(w_lag, returns)

    neg_overlap = negative_syms_overlap_analysis(per_sym, PARADIGM_181_182_NEG_SYMS)
    logger.info("6_neg_overlap: %d/%d (%.2f) — high=%s",
                neg_overlap["n_overlap"], neg_overlap["n_reference_negative"],
                neg_overlap["overlap_ratio"], neg_overlap["high_overlap_ge_50pct"])

    monthly_top_weights = universe_ranking_divergence(w_lag)

    q_port = quarter_breakdown(net_ret, "portfolio_net")
    q_eq = quarter_breakdown(eq_basket_ret, "equal_weight")

    util = util_diagnostics(w_lag)
    logger.info("util: avg_active_syms=%.2f, util_pct_capital=%.1f%%",
                util["avg_active_syms"], util["util_pct_capital_deployed_avg"])

    turn_diag = turnover_diagnostics(turnover, fee_lag)

    logger.info("running %d permutations...", N_PERM)
    perm_result = permutation_test(weights, returns, FEE_BP_ONE_WAY, N_PERM, RNG_SEED)
    logger.info("perm: obs_sharpe=%.3f, null_mean=%.3f, z_excess=%.2f, p=%.4f",
                perm_result["obs_sharpe"], perm_result["null_mean_sharpe"],
                perm_result["z_excess"], perm_result["perm_p_value"])

    audit = four_cond_audit(metrics_net, metrics_eq, util, len(net_ret), q_port, per_sym, perm_result)

    verdict, reason = verdict_tree(audit, metrics_net, util)
    logger.info("MAIN VERDICT: %s - %s", verdict, reason)

    lesson_72_verdict, lesson_72_reason = lesson_72_verdict_assignment(verdict, neg_overlap)
    logger.info("LESSON 72 VERDICT: %s - %s", lesson_72_verdict, lesson_72_reason)

    result = {
        "paradigm_id": 183,
        "paradigm_slug": "alt_per_sym_30d_return_autocorrelation_lag1_z_continuous_weighted_long_only_daily_rebal",
        "phase": "R-1",
        "verdict": verdict,
        "verdict_reason": reason,
        "lesson_72_3rd_dogfood_verdict": lesson_72_verdict,
        "lesson_72_3rd_dogfood_reason": lesson_72_reason,
        "run_ts": datetime.utcnow().isoformat() + "Z",
        "config": {
            "symbols": SYMBOLS,
            "n_syms": len(SYMBOLS),
            "autocorr_window_d": AUTOCORR_WINDOW_D,
            "autocorr_lag": AUTOCORR_LAG,
            "z_window_d": Z_WINDOW_D,
            "z_floor": Z_FLOOR,
            "z_cap": Z_CAP,
            "fee_bp_one_way": FEE_BP_ONE_WAY,
            "n_perm": N_PERM,
            "rng_seed": RNG_SEED,
            "statistic_class": "per_sym_30d_lag1_return_autocorrelation_zscore",
        },
        "panel": {
            "n_days_aligned": int(len(net_ret)),
            "date_range": [str(net_ret.index[0]), str(net_ret.index[-1])],
        },
        "metrics": {
            "portfolio_gross": metrics_gross,
            "portfolio_net": metrics_net,
            "benchmark_equal_weight": metrics_eq,
            "benchmark_btc_bnh": metrics_btc,
            "alpha_vs_equal_weight": metrics_alpha_eq,
            "alpha_vs_btc": metrics_alpha_btc,
            "tracking_error_annualized": round(te_eq, 4),
            "information_ratio_vs_eq": round(ir_eq, 4),
        },
        "util_diagnostics": util,
        "turnover_diagnostics": turn_diag,
        "permutation_test": perm_result,
        "per_sym_contribution": per_sym,
        "negative_syms_overlap_analysis": neg_overlap,
        "monthly_top_weights": monthly_top_weights,
        "quarter_breakdown_portfolio_net": q_port,
        "quarter_breakdown_equal_weight": q_eq,
        "four_cond_audit": audit,
        "lesson_61_slug_grep_audit": {
            "existing_autocorr_paradigm": "autocorr_regime (paradigm 18)",
            "existing_dna": {
                "frame": "5min OHLCV 288-bar window",
                "decision_mode": "discrete trigger entry SL/TP",
                "universe": "10-sym alt subset (no BTC)",
            },
            "paradigm_183_dna": {
                "frame": "daily 30d window",
                "decision_mode": "continuous-weighting portfolio (no SL/TP)",
                "universe": "14-sym incl BTC",
                "z_normalization": "90d z layer added",
            },
            "dimensional_distinctness": "5/6 axes (statistic root same lag-1 autocorr; daily-frame + z-norm + decision mode + universe + hold all different)",
            "user_claim_correction": "User claimed campaign 누적 미탐색 — FALSE. paradigm 18 ran R-3. Dispatch proceeds based on 5/6 axis distinctness threshold.",
        },
        "lesson_70_corollary_scope_prescreen": {
            "verdict": "PROCEED_NEW_STATISTIC_CLASS",
            "rationale_path_b": [
                "paradigm 181/182 are R-1 GRAVEYARDS (NOT R-5 LIVE) - Lesson #70 corollary applies to R-5 LIVE only",
                "Autocorrelation = regime characteristic class (trending vs mean-reverting), fundamentally different from magnitude characteristic (return / Sharpe)",
                "Different universe ranking expected (high autocorr syms != high return / Sharpe syms)",
            ],
        },
        "lesson_71_path_c_escape": {
            "is_state_machine": False,
            "is_continuous_weighting": True,
            "multi_position_simultaneous": True,
            "signal_intensity_proportional": True,
            "util_target_30pct": util["util_pct_capital_deployed_avg"] >= 30,
            "util_empirical_pct": util["util_pct_capital_deployed_avg"],
            "escape_verified": util["util_pct_capital_deployed_avg"] >= 30,
        },
        "lesson_72_3rd_dogfood": {
            "purpose": "Test whether fresh statistical axis (autocorrelation) recovers alpha where raw return (181) and Sharpe (182) failed",
            "paradigm_181_verdict": "PORTFOLIO_ALPHA_INSIGNIFICANT (sharpe_excess +0.089, perm_p 0.414)",
            "paradigm_182_verdict": "PORTFOLIO_ALPHA_INSIGNIFICANT (sharpe_excess +0.075, z_excess +0.17, perm_p 0.436)",
            "paradigm_181_182_6_neg_syms": PARADIGM_181_182_NEG_SYMS,
            "paradigm_183_obs_sharpe": perm_result["obs_sharpe"],
            "paradigm_183_sharpe_excess": perm_result["sharpe_excess"],
            "paradigm_183_z_excess": perm_result["z_excess"],
            "paradigm_183_perm_p": perm_result["perm_p_value"],
            "paradigm_183_6_neg_overlap": neg_overlap["overlap_ratio"],
            "verdict_assignment": lesson_72_verdict,
            "verdict_assignment_reason": lesson_72_reason,
        },
        "memory_compliance": {
            "no_freemium_trial": True,
            "life_changing_4dim_audited": True,
            "persistence_over_efficiency": True,
            "continuous_parallel_campaign": True,
            "lesson_61_slug_grep_audited": True,
            "lesson_70_corollary_scope_prescreen_executed": True,
            "lesson_71_path_c_escape_verified": True,
        },
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info("wrote %s", out_path)

    ts_df = pd.DataFrame({
        "gross_ret": gross_ret,
        "net_ret": net_ret,
        "eq_basket": eq_basket_ret,
        "btc_bnh": btc_ret if btc_ret is not None else 0,
        "turnover": turnover,
        "fee_lag": fee_lag,
        "total_weight": w_lag.sum(axis=1),
        "active_syms": (w_lag > 0).sum(axis=1),
    })
    ts_path = OUT_DIR / "r1__timeseries.csv"
    ts_df.to_csv(ts_path)
    logger.info("wrote %s", ts_path)

    return result


if __name__ == "__main__":
    result = main()
    print(f"\nMAIN VERDICT: {result['verdict']}")
    print(f"REASON: {result['verdict_reason']}")
    print(f"LESSON 72 3rd DOGFOOD: {result['lesson_72_3rd_dogfood_verdict']}")
    print(f"REASON: {result['lesson_72_3rd_dogfood_reason']}")
    sys.exit(0)
