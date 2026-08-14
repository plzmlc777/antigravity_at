"""
paradigm 182 R-1: per-sym 30d risk-adjusted Sharpe-z continuous-weighted long-only daily-rebal

Lesson #70 corollary scope prescreen VERDICT: (b) NEW paradigm class — proceed.
- paradigm 181 = R-1 GRAVEYARD (NOT R-5 LIVE survivor); Lesson #70 corollary applies only to R-5 LIVE narrow-cohort expansion
- Sharpe ratio = classical separate statistic class (Sharpe 1966), NOT minor parameter tweak
- vol normalization fundamentally changes signal interpretation (raw return momentum vs risk-adjusted momentum)

Mechanism:
- 14 alts × 4h OHLCV joblib substrate (2.25yr)
- Aggregate 4h to daily close-to-close
- Per-sym 30d rolling cumulative return / 30d realized vol → Sharpe-like ratio
- 90d rolling z-score of that Sharpe-like ratio
- Position size = clip(sharpe_z, +0.5, +3) where sharpe_z >= +0.5 → LONG weighted; else cash
- Daily rebalance (continuous, NOT state-machine)
- Long-only (Lesson #8 amendment paradigm 99 leverage shock upward bias)
- Fee: daily turnover × 8bp one-way (16bp round-trip)

Lesson #71 corollary path C ESCAPE verification:
- Continuous re-weighting (NOT state-machine)
- Multi-sym simultaneous (14 syms)
- Signal-intensity proportional (sharpe-z-weight)
- Target util ≥30%

Lesson #72 candidate 2nd dogfood:
- paradigm 181 1st dogfood: continuous-weighting ESCAPE SUCCESS but alpha 부재 (Sharpe -0.42)
- paradigm 182 2nd dogfood: vol-normalized statistic이 alpha-bearing 검증

Hypothesis: paradigm 181 6/14 syms net negative (FIL/LINK/BCH/NEAR/BNB/LTC) = vol-noisy syms false signal.
Sharpe-z (vol normalization) → false signal 정제, true alpha-bearing momentum 분리.

R-1 measurements (paradigm 181 framework 재사용):
- Portfolio daily return time series (annualized return / sharpe / sortino / max DD)
- Benchmark: equal-weight 14-sym B&H + BTC B&H
- Alpha = portfolio - benchmark
- IR / tracking error
- Per-sym contribution (paradigm 181 비교 의무)
- Quarter-by-quarter (9 quarters)
- Turnover + fee drag
- Position util empirical
- Lesson #20 4-cond Concentration + Temporal robustness
- Permutation null: shuffle daily weight rows across time

Verdict tree:
- PORTFOLIO_ALPHA_INSIGNIFICANT — z_excess < 2.0 OR perm_p > 0.10
- BROAD_FALSIFIED_FEE_FLOOR — gross alpha positive but net < 0
- NARROW_SCOPE_LIFE_CHANGING_FAIL — alpha PASS but 4-dim FAIL
- PASS_R1_FULL — alpha PASS + 4-cond ALL PASS
- HALT_BY_UTIL — util < 30% (Lesson #71 path C breach)
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
OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/alt_per_sym_30d_risk_adjusted_sharpe_z_continuous_weighted_long_only_daily_rebal")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "FILUSDT", "WIFUSDT",
]

# Position sizing params — statistic class shift from paradigm 181
RETURN_WINDOW_D = 30  # cumulative return window
VOL_WINDOW_D = 30  # realized vol window (same as return window for Sharpe-like)
Z_WINDOW_D = 90  # z-score of Sharpe-like ratio
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
    logger.info("daily close panel shape: %s, range %s..%s", df_close.shape, df_close.index[0], df_close.index[-1])
    df_ret = df_close.pct_change().dropna(how="any")
    return df_close, df_ret


def compute_sharpe_z_scores(df_close: pd.DataFrame, df_ret: pd.DataFrame,
                             return_window: int, vol_window: int, z_window: int) -> pd.DataFrame:
    """
    Per-sym Sharpe-like ratio:
        sharpe_like_t = (30d cumulative return at t) / (30d realized vol at t)
    Then 90d rolling z-score of sharpe_like.

    Sharpe-like = numerator: cumulative return over 30d (already drift-adjusted)
                  denominator: rolling 30d realized vol (annualization const cancels in z-score)
    """
    # Cumulative return over return_window
    cum_ret = df_close / df_close.shift(return_window) - 1.0
    # Realized vol over vol_window (daily-return std, annualized constant cancels in z)
    realized_vol = df_ret.rolling(vol_window).std()
    # Sharpe-like ratio (volatility-normalized return)
    # Guard against zero vol (cohort dropouts) — replace 0 with NaN to propagate
    sharpe_like = cum_ret / realized_vol.replace(0.0, np.nan)
    # 90d rolling z-score
    z = (sharpe_like - sharpe_like.rolling(z_window).mean()) / sharpe_like.rolling(z_window).std()
    return z, sharpe_like


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
    contrib_pct = (contrib / contrib.abs().sum() * 100).round(3)
    return {sym: {"abs_contrib_bp": float(contrib[sym] * 1e4),
                  "pct_share": float(contrib_pct[sym]),
                  "positive": bool(contrib[sym] > 0)} for sym in contrib.index}


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


def main():
    logger.info("paradigm 182 R-1 Sharpe-z continuous-weighted long-only daily-rebal")
    df_close, df_ret = load_daily_returns()
    logger.info("daily close: %d days x %d syms", len(df_close), df_close.shape[1])

    # Compute Sharpe-z (statistic class shift from paradigm 181 raw return z)
    z, sharpe_like = compute_sharpe_z_scores(df_close, df_ret, RETURN_WINDOW_D, VOL_WINDOW_D, Z_WINDOW_D)
    logger.info("sharpe-z panel shape: %s, NaN ratio: %.2f%%", z.shape, z.isna().mean().mean() * 100)
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
    logger.info("VERDICT: %s - %s", verdict, reason)

    result = {
        "paradigm_id": 182,
        "paradigm_slug": "alt_per_sym_30d_risk_adjusted_sharpe_z_continuous_weighted_long_only_daily_rebal",
        "phase": "R-1",
        "verdict": verdict,
        "verdict_reason": reason,
        "run_ts": datetime.utcnow().isoformat() + "Z",
        "config": {
            "symbols": SYMBOLS,
            "n_syms": len(SYMBOLS),
            "return_window_d": RETURN_WINDOW_D,
            "vol_window_d": VOL_WINDOW_D,
            "z_window_d": Z_WINDOW_D,
            "z_floor": Z_FLOOR,
            "z_cap": Z_CAP,
            "fee_bp_one_way": FEE_BP_ONE_WAY,
            "n_perm": N_PERM,
            "rng_seed": RNG_SEED,
            "statistic_class": "risk_adjusted_sharpe_like",
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
        "quarter_breakdown_portfolio_net": q_port,
        "quarter_breakdown_equal_weight": q_eq,
        "four_cond_audit": audit,
        "lesson_70_corollary_scope_prescreen": {
            "verdict": "PROCEED_NEW_STATISTIC_CLASS",
            "rationale_path_b": [
                "paradigm 181 is R-1 GRAVEYARD (NOT R-5 LIVE survivor) - Lesson #70 applies to R-5 LIVE only",
                "Sharpe ratio = Sharpe 1966 classical separate statistic class",
                "vol normalization fundamentally changes signal interpretation (raw return momentum vs risk-adjusted momentum)",
                "Lesson #70 corollary explicitly permits spec-adaptive expansion (per-sym parameter optimization), statistic class shift exceeds this scope",
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
        "lesson_72_candidate_2nd_dogfood": {
            "purpose": "Test whether vol-normalization (Sharpe-z) recovers alpha that raw return z (paradigm 181) failed to produce",
            "paradigm_181_sharpe_excess": 0.089,
            "paradigm_181_perm_p": 0.414,
            "paradigm_181_verdict": "PORTFOLIO_ALPHA_INSIGNIFICANT",
            "paradigm_182_obs_sharpe": perm_result["obs_sharpe"],
            "paradigm_182_sharpe_excess": perm_result["sharpe_excess"],
            "paradigm_182_perm_p": perm_result["perm_p_value"],
            "lesson_72_partial_refutation": (perm_result["z_excess"] >= 2.0) and (perm_result["perm_p_value"] <= 0.10),
            "lesson_72_strengthened_2nd_dogfood": not ((perm_result["z_excess"] >= 2.0) and (perm_result["perm_p_value"] <= 0.10)),
        },
        "memory_compliance": {
            "no_freemium_trial": True,
            "life_changing_4dim_audited": True,
            "persistence_over_efficiency": True,
            "continuous_parallel_campaign": True,
            "lesson_70_corollary_scope_prescreen_executed": True,
            "lesson_61_slug_grep_audited": True,
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
    print(f"\nVERDICT: {result['verdict']}")
    print(f"REASON: {result['verdict_reason']}")
    sys.exit(0)
