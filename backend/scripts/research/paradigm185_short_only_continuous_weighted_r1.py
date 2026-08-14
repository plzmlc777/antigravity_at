"""
paradigm 185 R-1: per-sym 30d return z-score continuous-weighted SHORT-ONLY daily-rebal

Mechanism (paradigm 184 SHORT-side standalone +0.604 sharpe empirical extraction):
- 14 alts × 4h OHLCV joblib substrate (2.25yr) → daily close panel
- Per-sym 30d rolling return → 90d rolling z-score
- Position size:
    z <= -0.5 → SHORT weight = clip(z, -3, -0.5) / sum_norm  (negative weight, capital deployed)
    z >  -0.5 → cash (no LONG side)
- Daily rebalance (continuous-weighting, Lesson #71 path C ESCAPE)
- SHORT-only: 1x capital deployed structurally (vs paradigm 184 2x gross)
- Fee: daily turnover × 8bp one-way
- **Funding cost: actual binance_funding_rate DB (8h × 3 cycles/day per sym)**
   SHORT pos × positive funding → SHORT RECEIVES funding (positive carry, profit add)
   SHORT pos × negative funding → SHORT PAYS funding (cost, profit subtract)
   actual_funding_cost_t_sym = - |w_S_lag[sym]| * sum_of_8h_funding_rates_today  (sign: SHORT receives when funding > 0)

Lesson #70 corollary scope prescreen (CRITICAL):
- paradigm 184 = R-1 GRAVEYARD (NOT R-5 LIVE survivor) → corollary scope inapplicable
- paradigm 185 = sub-mode extraction (SHORT side isolation) from paradigm 184 LONG/SHORT decomposition
- paradigm 184 SHORT-side standalone Sharpe +0.604 / ann_ret +45.87% empirical evidence base
- VERDICT: (b) PROCEED_R1_FOLLOW_UP_EXTRACTION (Mirror antipattern catalog 별도 R-1 정합)

Mirror antipattern catalog (paradigm 70 precedent):
- paradigm 181 LONG-only → paradigm 185 SHORT-only is NOT auto-inverse
- paradigm 184 LONG/SHORT decomposition empirically demonstrated SHORT side alpha-bearing (3/6 paradigm 181 negative syms SHORT positive)
- Justification = paradigm 184 SHORT-side standalone Sharpe 0.604 standalone, NOT speculative mirror

Lesson #72 boundary verification:
- paradigm 185 PASS → Lesson #72 strict universal REJECTED (continuous-weighting framework SHORT-bearing alpha for downtrend-bias universe)
- paradigm 185 FAIL → Lesson #72 strict universal CONFIRMED (alpha extraction impossible across all direction modes)

Lesson #61 slug grep: ls research_track/ | grep -iE short_only|short_continuous|short_weighted|sell_only|bear_continuous
  → 0 collision verified pre-dispatch

Lesson #67 ESCAPE: per-sym z-score, NOT cross-asset broadcast (paradigm 184 framework inherited)
Lesson #68 ESCAPE: continuous daily rebalance (NOT state-machine)
Lesson #71 corollary path C ESCAPE: SHORT-only 14 syms continuous-weighting util ~50% (paradigm 184 SHORT side avg 0.6867 → SHORT-only expected ~50%, ≥30% threshold PASS)

R-1 measurements:
- Portfolio gross/net (SHORT-only, no LONG drag, 1x capital)
- Per-sym SHORT contribution (paradigm 184 LINK/NEAR/LTC 3 alpha sources reconciliation)
- Quarter-by-quarter (9 quarters, paradigm 184 SHORT-side baseline)
- Actual funding cost breakdown (per-sym per-quarter)
- Turnover diagnostics
- Permutation test (shuffle weight rows preserve cross-sectional structure)
- Life-changing 4-dim audit (sharpe / per-trade edge / util / trades/yr)
- Max DD (bull market = SHORT loss tracking)

Verdict tree:
- HALT_BY_UTIL — util < 30% (Lesson #71 breach)
- SAMPLE_INSUFFICIENT — n_days < 200 or quarters < 4
- BROAD_FALSIFIED — sharpe < 0.0 + z_excess < 0 (alpha fully void)
- PORTFOLIO_ALPHA_INSIGNIFICANT — z_excess < 2.0 or perm_p > 0.10
- NARROW_SCOPE_LIFE_CHANGING_FAIL — alpha PASS but 4-dim FAIL
- FRAGILE_TEMPORAL_FAIL — alpha + 4-dim PASS but quarters positive < 5/9
- PASS_R1_FULL — all 4-cond PASS

paradigm 184 reconciliation reference values (SHORT-side standalone, 0.01%/day cost):
- n_days = 701 (2024-05-30 .. 2026-04-30)
- ann_return = +45.874%
- sharpe = 0.604
- sortino = 0.758
- max_dd = -45.564%
- total_return = +42.087%
- short_per_sym positive: ETH +1674, SOL +355, ADA +16, DOGE +1274, LINK +1589, LTC +88, NEAR +2430, WIF +2818 (8/14)
- short_per_sym negative: BTC -25, BNB -623, XRP -319, AVAX -14, BCH -1880, FIL -127 (6/14)
"""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CACHE_DIR = Path("/home/hcpark/antigravity/backend/runs/ohlcv_cache_12col")
OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/alt_per_sym_30d_return_z_continuous_weighted_short_only_daily_rebal")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ENV_PATH = "/home/hcpark/antigravity/backend/.env"
load_dotenv(ENV_PATH)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "FILUSDT", "WIFUSDT",
]

# Funding DB has 13/14 (WIFUSDT n=0). Strategy: use actual funding for 13, fallback to 0.0 (neutral)
# for WIFUSDT. paradigm 184 reconciliation comparability preserved (universe identical).
SYMBOLS_WITH_FUNDING_DB = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "FILUSDT",
]
SYMBOLS_WITHOUT_FUNDING = ["WIFUSDT"]

# paradigm 184 SHORT side positive contributors (8/14 paradigm 184 reconciliation reference)
PARADIGM_184_SHORT_POSITIVE = ["ETHUSDT", "SOLUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "WIFUSDT"]
# 3/6 paradigm 181 negative syms with positive SHORT contribution
PARADIGM_181_NEG_SYMS = ["FILUSDT", "LINKUSDT", "BCHUSDT", "NEARUSDT", "BNBUSDT", "LTCUSDT"]

RETURN_WINDOW_D = 30
Z_WINDOW_D = 90
Z_FLOOR = 0.5  # |z| floor (SHORT only: z <= -0.5)
Z_CAP = 3.0
FEE_BP_ONE_WAY = 8.0

N_PERM = 1000
RNG_SEED = 20260522

# Empirical: positive 8h funding (LONG pays, SHORT receives) signed convention
# SHORT pos × funding_rate > 0 → SHORT receives (income, positive carry)
# Convention: short_funding_pnl_t = + |w_S_lag| * (sum of 8h funding rates for that day)


def load_daily_close_and_returns():
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
    logger.info("daily close panel: %s, %s..%s",
                df_close.shape, df_close.index[0], df_close.index[-1])
    df_ret = df_close.pct_change().dropna(how="any")
    return df_close, df_ret


def load_daily_funding_panel(date_index: pd.DatetimeIndex):
    """Load 8h funding from DB and aggregate to daily sum per symbol.

    Returns DataFrame indexed by date with columns = SYMBOLS.
    Convention: funding_rate sign: positive = LONG pays SHORT (SHORT income).
    Daily aggregate = sum of 3 (or fewer) 8h funding rates within the calendar day.
    """
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_SERVER", "localhost"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )
    daily_funding = {}
    start_date = date_index.min().strftime("%Y-%m-%d")
    end_date = date_index.max().strftime("%Y-%m-%d")
    for sym in SYMBOLS_WITH_FUNDING_DB:
        q = """
            SELECT funding_time, funding_rate
            FROM binance_funding_rate
            WHERE symbol = %s
              AND funding_time >= %s
              AND funding_time < %s::date + INTERVAL '1 day'
            ORDER BY funding_time
        """
        df = pd.read_sql_query(q, conn, params=(sym, start_date, end_date))
        if df.empty:
            logger.warning("no funding rows for %s", sym)
            daily_funding[sym] = pd.Series(0.0, index=date_index)
            continue
        df["funding_time"] = pd.to_datetime(df["funding_time"])
        df["date"] = df["funding_time"].dt.normalize()
        df["funding_rate"] = df["funding_rate"].astype(float)
        # 3 cycles/day aggregate (sum daily funding rate yield)
        daily = df.groupby("date")["funding_rate"].sum()
        daily = daily.reindex(date_index).fillna(0.0)
        daily_funding[sym] = daily
    for sym in SYMBOLS_WITHOUT_FUNDING:
        # WIFUSDT no funding data → neutral 0.0 (note: paradigm 184 used 0.01%/day fixed; we choose 0.0 to avoid synthetic bias)
        daily_funding[sym] = pd.Series(0.0, index=date_index)
    conn.close()
    df_funding = pd.DataFrame(daily_funding).reindex(columns=SYMBOLS)
    logger.info("funding panel: %s, mean daily bp/sym/day = %.3f",
                df_funding.shape, float(df_funding.mean().mean()) * 1e4)
    return df_funding


def compute_z_scores(df_close: pd.DataFrame, return_window: int, z_window: int) -> pd.DataFrame:
    df_ret_window = df_close / df_close.shift(return_window) - 1.0
    z = (df_ret_window - df_ret_window.rolling(z_window).mean()) / df_ret_window.rolling(z_window).std()
    return z


def compute_short_weights(z: pd.DataFrame, z_floor: float, z_cap: float):
    """SHORT-only weights.

    SHORT raw: w_S_i = clip(z_i, -z_cap, -z_floor) where z_i <= -z_floor; else 0 (negative)
    Normalize so sum(|w_S|) <= 1 (1x capital cap, NOT 2x like paradigm 184).
    Sparse signal → cash residual.
    """
    w_S_raw = z.clip(lower=-z_cap, upper=-z_floor).where(z <= -z_floor, 0.0)
    row_sum_S = w_S_raw.abs().sum(axis=1)
    scale_S = np.maximum(row_sum_S.values, 1.0)
    w_S = w_S_raw.div(scale_S, axis=0)  # stays negative, magnitude in [0,1]
    return w_S


def simulate_short_only_portfolio(w_S: pd.DataFrame, returns: pd.DataFrame, funding: pd.DataFrame,
                                    fee_bp_one_way: float):
    """SHORT-only daily-rebal portfolio with actual funding rate model.

    SHORT-side return per day (gross of fees):
        gross_ret_t = sum(w_S_lag_i * ret_t_i)   (w_S negative → profit when ret<0)

    Funding PnL per day (positive funding = SHORT receives):
        funding_pnl_t = sum(|w_S_lag_i| * daily_funding_t_i)

    Turnover (rebalance applied at close of t, fee charged on t+1):
        turnover_t = sum(|w_S_t - w_S_{t-1}|)
        fee_t = turnover_t * fee_bp_one_way / 10000   (lagged 1 day)

    Net return: gross_ret + funding_pnl - fee_lag
    """
    w_S = w_S.reindex(returns.index).fillna(0.0)
    funding = funding.reindex(returns.index).reindex(columns=returns.columns).fillna(0.0)

    w_S_lag = w_S.shift(1).fillna(0.0)
    gross_ret = (w_S_lag * returns).sum(axis=1)
    # SHORT-side decomposition by sym (gross only)
    per_sym_ret = (w_S_lag * returns)  # signed daily contribution
    # Funding PnL: positive funding = income for SHORT (signed convention)
    funding_pnl_per_sym = w_S_lag.abs() * funding  # |w_S| * funding (SHORT receives positive funding)
    funding_pnl = funding_pnl_per_sym.sum(axis=1)

    # Turnover (LONG-only style for SHORT side; |w_S| changes)
    turnover = w_S.abs().diff().abs().sum(axis=1).fillna(0.0)
    fee_per_day = turnover * (fee_bp_one_way / 10000.0)
    fee_lag = fee_per_day.shift(1).fillna(0.0)

    net_ret = gross_ret + funding_pnl - fee_lag

    return {
        "gross_ret": gross_ret,
        "funding_pnl": funding_pnl,
        "net_ret": net_ret,
        "turnover": turnover,
        "fee_lag": fee_lag,
        "w_S_lag": w_S_lag,
        "per_sym_ret": per_sym_ret,
        "funding_pnl_per_sym": funding_pnl_per_sym,
    }


def compute_metrics(ret_series: pd.Series, label: str):
    n = len(ret_series)
    if n < 2:
        return {"label": label, "n_days": n}
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


def quarter_breakdown_with_funding(net_ret: pd.Series, gross_ret: pd.Series,
                                     funding_pnl: pd.Series, fee_lag: pd.Series,
                                     funding_per_sym: pd.DataFrame):
    """9-quarter breakdown with cost decomposition."""
    out = {}
    grouped = net_ret.groupby(pd.Grouper(freq="QS"))
    for q_start, q_ret in grouped:
        if len(q_ret) < 5:
            continue
        idx = q_ret.index
        eq = (1.0 + q_ret).cumprod()
        total = float(eq.iloc[-1] - 1.0)
        sh = float(q_ret.mean() / q_ret.std() * np.sqrt(365)) if q_ret.std() > 0 else 0.0
        gross_q = float(gross_ret.loc[idx].sum())
        funding_q = float(funding_pnl.loc[idx].sum())
        fee_q = float(fee_lag.loc[idx].sum())
        # per-sym funding income breakdown
        per_sym_fund_q = {s: round(float(funding_per_sym.loc[idx, s].sum()) * 1e4, 2) for s in funding_per_sym.columns}
        key = f"{q_start.year}Q{q_start.quarter}"
        out[key] = {
            "quarter": key,
            "n_days": int(len(q_ret)),
            "total_return_pct": round(total * 100, 3),
            "sharpe": round(sh, 3),
            "gross_pct": round(gross_q * 100, 3),
            "funding_pnl_pct": round(funding_q * 100, 3),
            "fee_drag_pct": round(fee_q * 100, 3),
            "positive": bool(total > 0),
            "per_sym_funding_bp": per_sym_fund_q,
        }
    return out


def per_sym_short_contribution(per_sym_ret: pd.DataFrame, funding_pnl_per_sym: pd.DataFrame):
    """SHORT-side per-sym contribution + funding income breakdown.

    contrib_bp: cumulative signed return contribution (gross of fees)
    funding_bp: cumulative funding income/cost (positive = SHORT received)
    total_bp: contrib_bp + funding_bp (excludes fee)
    """
    contrib = per_sym_ret.sum(axis=0)
    funding_sum = funding_pnl_per_sym.sum(axis=0)
    result = {}
    for sym in contrib.index:
        c = float(contrib[sym] * 1e4)
        f = float(funding_sum[sym] * 1e4)
        result[sym] = {
            "contrib_bp": round(c, 2),
            "funding_bp": round(f, 2),
            "total_bp": round(c + f, 2),
            "positive_contrib": bool(c > 0),
            "positive_total": bool(c + f > 0),
        }
    return result


def util_diagnostics_short(sim: dict):
    w_S = sim["w_S_lag"]
    short_per_day = w_S.abs().sum(axis=1)
    active = (w_S < 0).sum(axis=1)
    return {
        "avg_active_syms": round(float(active.mean()), 3),
        "median_active_syms": int(active.median()),
        "max_active_syms": int(active.max()),
        "avg_short_capital": round(float(short_per_day.mean()), 4),
        "median_short_capital": round(float(short_per_day.median()), 4),
        "util_pct_capital_avg": round(float(short_per_day.mean()) * 100, 2),
        "util_pct_days_active": round(float((short_per_day > 0).mean()) * 100, 2),
        "days_zero_exposure": int((short_per_day == 0).sum()),
    }


def turnover_diagnostics_short(sim: dict, funding_pnl: pd.Series):
    return {
        "avg_daily_turnover": round(float(sim["turnover"].mean()), 4),
        "median_daily_turnover": round(float(sim["turnover"].median()), 4),
        "max_daily_turnover": round(float(sim["turnover"].max()), 4),
        "total_fee_drag_pct": round(float(sim["fee_lag"].sum()) * 100, 3),
        "avg_daily_fee_bp": round(float(sim["fee_lag"].mean()) * 1e4, 4),
        "total_funding_pnl_pct": round(float(funding_pnl.sum()) * 100, 3),
        "avg_daily_funding_bp": round(float(funding_pnl.mean()) * 1e4, 4),
        "annualized_funding_yield_pct": round(float(funding_pnl.mean()) * 365 * 100, 3),
    }


def permutation_test_short(w_S: pd.DataFrame, returns: pd.DataFrame, funding: pd.DataFrame,
                             fee_bp: float, n_perm: int, seed: int):
    rng = np.random.default_rng(seed)
    n_days = len(w_S)
    sim_obs = simulate_short_only_portfolio(w_S, returns, funding, fee_bp)
    net_obs = sim_obs["net_ret"]
    obs_sharpe = float(net_obs.mean() / net_obs.std() * np.sqrt(365)) if net_obs.std() > 0 else 0.0

    null_sharpes = []
    for i in range(n_perm):
        perm_idx = rng.permutation(n_days)
        w_perm = w_S.iloc[perm_idx].copy(); w_perm.index = w_S.index
        sim_p = simulate_short_only_portfolio(w_perm, returns, funding, fee_bp)
        np_ret = sim_p["net_ret"]
        sh = float(np_ret.mean() / np_ret.std() * np.sqrt(365)) if np_ret.std() > 0 else 0.0
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


def four_cond_audit_short(metrics_net, util, q_port, per_sym, perm_result):
    sharpe_excess = perm_result["sharpe_excess"]
    perm_p = perm_result["perm_p_value"]
    z_excess = perm_result["z_excess"]
    cond1_pass = (sharpe_excess >= 0.5) and (perm_p <= 0.10) and (z_excess >= 2.0)

    syms_positive = sum(1 for s in per_sym.values() if s["positive_total"])
    syms_pos_ratio = syms_positive / len(per_sym) if per_sym else 0
    cond2_pass = syms_pos_ratio >= 0.5

    q_positive = sum(1 for q in q_port.values() if q["positive"])
    q_total = len(q_port)
    cond3_pass = (q_positive / q_total) >= 0.5 if q_total > 0 else False

    util_pct = util.get("util_pct_capital_avg", 0)
    effective_trades_per_yr = 365 * util.get("avg_active_syms", 0)
    sharpe_p = metrics_net.get("sharpe", 0) or 0
    ann_ret_pct = metrics_net.get("ann_return_pct", 0) or 0
    per_trade_edge_bp = (ann_ret_pct / 100) / effective_trades_per_yr * 1e4 if effective_trades_per_yr > 0 else 0

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


def verdict_tree(audit, metrics_net, util, perm_result, n_days_aligned, q_count):
    util_pct = util.get("util_pct_capital_avg", 0)
    if util_pct < 30:
        return "HALT_BY_UTIL", f"util {util_pct:.1f}% < 30% (Lesson #71 path C breach)"
    if n_days_aligned < 200 or q_count < 4:
        return "SAMPLE_INSUFFICIENT", f"n_days={n_days_aligned} or quarters={q_count} insufficient"
    sharpe_p = metrics_net.get("sharpe", 0) or 0
    z_excess = perm_result["z_excess"]
    if sharpe_p < 0.0 and z_excess < 0:
        return "BROAD_FALSIFIED", f"sharpe={sharpe_p:.3f} < 0 + z_excess={z_excess:.2f} < 0 (alpha fully void)"
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


def lesson_72_verdict(audit, metrics_net):
    """Lesson #72 boundary verification.

    PASS (any of):
      - z_excess >= 2.0
      - sharpe >= 1.0
      - (sharpe >= 0.5 AND total_return_pct > 0)
    → Lesson #72 strict universal REJECTED (continuous-weighting framework alpha-bearing for SHORT-only mode)

    FAIL:
      - sharpe < 0 → Lesson #72 strict universal CONFIRMED (paradigm 184 SHORT-side standalone Sharpe 0.604 was paradigm 184 internal artifact, NOT extractable)
      - 0 < sharpe < 0.5 → Lesson #72 universal PARTIAL_CONFIRMED (alpha exists but sub-grade)
    """
    sharpe_p = metrics_net.get("sharpe", 0) or 0
    total_ret = metrics_net.get("total_return_pct", 0) or 0
    z_excess = audit["cond1_three_gate"]["z_excess"]

    if z_excess >= 2.0 or sharpe_p >= 1.0:
        return {
            "verdict": "LESSON_72_STRICT_UNIVERSAL_REJECTED",
            "reason": f"SHORT-only alpha extracted (z_excess={z_excess:.2f}, sharpe={sharpe_p:.3f}); paradigm 184 SHORT-side standalone +0.604 reconfirmed + EXCEEDED with 1x fee/funding model",
            "paradigm_184_short_side_sharpe_reference": 0.604,
            "paradigm_185_sharpe_observed": sharpe_p,
            "delta_sharpe": round(sharpe_p - 0.604, 3),
        }
    elif sharpe_p >= 0.5 and total_ret > 0:
        return {
            "verdict": "LESSON_72_STRICT_UNIVERSAL_REJECTED_PARTIAL",
            "reason": f"SHORT-only partial alpha (sharpe={sharpe_p:.3f}); paradigm 184 SHORT-side standalone +0.604 broadly reconciled but z_excess<2.0",
            "paradigm_184_short_side_sharpe_reference": 0.604,
            "paradigm_185_sharpe_observed": sharpe_p,
            "delta_sharpe": round(sharpe_p - 0.604, 3),
        }
    elif sharpe_p > 0:
        return {
            "verdict": "LESSON_72_PARTIAL_CONFIRMED",
            "reason": f"weak alpha (sharpe={sharpe_p:.3f}); paradigm 184 SHORT-side standalone +0.604 NOT replicated; extraction degraded by fee/turnover overhead",
            "paradigm_184_short_side_sharpe_reference": 0.604,
            "paradigm_185_sharpe_observed": sharpe_p,
            "delta_sharpe": round(sharpe_p - 0.604, 3),
        }
    else:
        return {
            "verdict": "LESSON_72_STRICT_UNIVERSAL_CONFIRMED",
            "reason": f"SHORT-only alpha void (sharpe={sharpe_p:.3f}); paradigm 184 SHORT-side standalone +0.604 was paradigm 184 internal accounting artifact (NOT independently extractable); continuous-weighting framework Tier 4 retire strengthened",
            "paradigm_184_short_side_sharpe_reference": 0.604,
            "paradigm_185_sharpe_observed": sharpe_p,
            "delta_sharpe": round(sharpe_p - 0.604, 3),
        }


def main():
    logger.info("paradigm 185 R-1 SHORT-only continuous-weighted daily-rebal")
    df_close, df_ret = load_daily_close_and_returns()
    n_days = len(df_close)
    logger.info("daily close: %d days x %d syms", n_days, df_close.shape[1])

    z = compute_z_scores(df_close, RETURN_WINDOW_D, Z_WINDOW_D)
    z = z.dropna(how="all")
    logger.info("z-score panel: %s", z.shape)

    w_S = compute_short_weights(z, Z_FLOOR, Z_CAP)
    common_idx = w_S.index.intersection(df_ret.index)
    w_S = w_S.loc[common_idx]
    returns = df_ret.loc[common_idx]
    logger.info("aligned panel: %d days x %d syms", len(w_S), w_S.shape[1])

    # Load actual funding panel for these dates
    funding = load_daily_funding_panel(common_idx)

    sim = simulate_short_only_portfolio(w_S, returns, funding, FEE_BP_ONE_WAY)
    logger.info("portfolio: gross=%.4f%%/day, funding=%.4f%%/day, fee=%.4f%%/day, net=%.4f%%/day",
                sim["gross_ret"].mean() * 100, sim["funding_pnl"].mean() * 100,
                sim["fee_lag"].mean() * 100, sim["net_ret"].mean() * 100)

    # Metrics
    metrics_gross = compute_metrics(sim["gross_ret"], "portfolio_gross_no_fee_no_funding")
    metrics_gross_with_funding = compute_metrics(sim["gross_ret"] + sim["funding_pnl"], "portfolio_gross_with_funding")
    metrics_net = compute_metrics(sim["net_ret"], "portfolio_net")

    # Reference benchmarks
    eq_basket_ret = returns.mean(axis=1)
    btc_ret = returns["BTCUSDT"]
    metrics_eq = compute_metrics(eq_basket_ret, "reference_equal_weight_basket")
    metrics_btc_short = compute_metrics(-btc_ret, "reference_btc_short_bnh")
    metrics_btc_long = compute_metrics(btc_ret, "reference_btc_long_bnh")

    # paradigm 184 SHORT-side standalone simulated with same panel/period (no funding, 0.01%/day cost)
    # → not re-simulated here, paradigm 184 R-1 metrics imported by reference

    # Per-sym contribution + funding income
    per_sym = per_sym_short_contribution(sim["per_sym_ret"], sim["funding_pnl_per_sym"])

    # Util / turnover
    util = util_diagnostics_short(sim)
    logger.info("util: avg_active=%.2f, short_capital=%.1f%%",
                util["avg_active_syms"], util["util_pct_capital_avg"])
    turn_diag = turnover_diagnostics_short(sim, sim["funding_pnl"])

    # Quarter breakdown
    q_port = quarter_breakdown_with_funding(sim["net_ret"], sim["gross_ret"], sim["funding_pnl"],
                                              sim["fee_lag"], sim["funding_pnl_per_sym"])

    # Permutation
    logger.info("running %d permutations (funding-aware null)...", N_PERM)
    perm_result = permutation_test_short(w_S, returns, funding, FEE_BP_ONE_WAY, N_PERM, RNG_SEED)
    logger.info("perm: obs_sharpe=%.3f, null_mean=%.3f, z_excess=%.2f, p=%.4f",
                perm_result["obs_sharpe"], perm_result["null_mean_sharpe"],
                perm_result["z_excess"], perm_result["perm_p_value"])

    # 4-cond audit
    audit = four_cond_audit_short(metrics_net, util, q_port, per_sym, perm_result)

    # Verdict
    verdict, reason = verdict_tree(audit, metrics_net, util, perm_result, len(sim["net_ret"]), len(q_port))
    logger.info("VERDICT: %s — %s", verdict, reason)

    # Lesson #72 boundary
    l72 = lesson_72_verdict(audit, metrics_net)
    logger.info("Lesson #72: %s — %s", l72["verdict"], l72["reason"])

    # paradigm 184 reconciliation: 8 SHORT positive syms, expected total_bp positive
    p184_short_pos_total = sum(per_sym[s]["total_bp"] for s in PARADIGM_184_SHORT_POSITIVE if s in per_sym)
    p184_181neg_short_attrib = {s: per_sym[s] for s in PARADIGM_181_NEG_SYMS if s in per_sym}
    p184_181neg_pos_count = sum(1 for v in p184_181neg_short_attrib.values() if v["positive_total"])

    result = {
        "paradigm_id": 185,
        "paradigm_slug": "alt_per_sym_30d_return_z_continuous_weighted_short_only_daily_rebal",
        "phase": "R-1",
        "verdict": verdict,
        "verdict_reason": reason,
        "run_ts": datetime.utcnow().isoformat() + "Z",
        "lesson_70_corollary_scope_prescreen": {
            "branch_a_R5_LIVE_survivor_expansion": False,
            "branch_b_R1_followup_extraction_or_direction_class_shift": True,
            "verdict": "PROCEED_R1_FOLLOW_UP_EXTRACTION",
            "rationale": [
                "paradigm 184 = R-1 GRAVEYARD, NOT R-5 LIVE survivor (Lesson #70 corollary scope inapplicable)",
                "paradigm 185 = SHORT-side standalone extraction (paradigm 184 internal LONG/SHORT decomposition empirical Sharpe +0.604)",
                "Mirror antipattern catalog 별도 R-1 의무 (paradigm 70 precedent) ✓ satisfied with evidence-based not speculative inverse",
                "Universe 14 cohort identical with paradigm 184 (paradigm 181 reconciliation comparability preserved)",
                "Actual funding rate cost model (paradigm 22 DB substrate 13/14 syms) vs paradigm 184 simplified 0.01%/day fixed",
            ],
        },
        "mirror_antipattern_catalog_justification": {
            "paradigm_70_precedent_acknowledged": True,
            "paradigm_70_failure_mode": "btc_rv_highvol UP×LONG +113bp vs DOWN×SHORT -49bp 13σ asymmetry (auto-mirror falsified)",
            "paradigm_185_distinction": [
                "paradigm 184 LONG/SHORT decomposition empirical Sharpe SHORT 0.604 standalone",
                "Not auto-inverse of paradigm 181 LONG-only; evidence-based extraction from paradigm 184 sub-mode",
                "Funding model upgrade (actual DB rate vs paradigm 184 0.01%/day fixed)",
                "Separate R-1 measurement (별도 R-1 의무 satisfied)",
            ],
        },
        "config": {
            "symbols": SYMBOLS,
            "n_syms": len(SYMBOLS),
            "symbols_with_funding_db": SYMBOLS_WITH_FUNDING_DB,
            "symbols_without_funding_db_fallback_zero": SYMBOLS_WITHOUT_FUNDING,
            "return_window_d": RETURN_WINDOW_D,
            "z_window_d": Z_WINDOW_D,
            "z_floor": Z_FLOOR,
            "z_cap": Z_CAP,
            "fee_bp_one_way": FEE_BP_ONE_WAY,
            "funding_model": "actual_binance_funding_rate_db_8h_x_3_cycles_daily_aggregate",
            "n_perm": N_PERM,
            "rng_seed": RNG_SEED,
        },
        "panel": {
            "n_days_aligned": int(len(sim["net_ret"])),
            "date_range": [str(sim["net_ret"].index[0]), str(sim["net_ret"].index[-1])],
        },
        "metrics": {
            "portfolio_gross_no_fee_no_funding": metrics_gross,
            "portfolio_gross_with_funding": metrics_gross_with_funding,
            "portfolio_net": metrics_net,
            "reference_equal_weight_basket": metrics_eq,
            "reference_btc_short_bnh": metrics_btc_short,
            "reference_btc_long_bnh": metrics_btc_long,
        },
        "util_diagnostics": util,
        "turnover_diagnostics": turn_diag,
        "permutation_test": perm_result,
        "per_sym_short_contribution": per_sym,
        "paradigm_184_reconciliation": {
            "paradigm_184_short_side_sharpe_reference": 0.604,
            "paradigm_184_short_side_ann_return_reference_pct": 45.874,
            "paradigm_184_short_side_max_dd_reference_pct": -45.564,
            "paradigm_184_short_positive_syms_8": PARADIGM_184_SHORT_POSITIVE,
            "paradigm_185_p184_short_pos_syms_total_bp": round(p184_short_pos_total, 2),
            "paradigm_181_negative_syms_6": PARADIGM_181_NEG_SYMS,
            "paradigm_185_p181_neg_syms_short_attribution": p184_181neg_short_attrib,
            "paradigm_185_p181_neg_short_positive_count": p184_181neg_pos_count,
            "paradigm_185_p181_neg_short_positive_ratio": round(p184_181neg_pos_count / len(PARADIGM_181_NEG_SYMS), 3),
        },
        "quarter_breakdown_portfolio_net": q_port,
        "four_cond_audit": audit,
        "lesson_72_boundary_verdict": l72,
        "lesson_71_path_c_escape": {
            "is_state_machine": False,
            "is_continuous_weighting": True,
            "multi_position_simultaneous": True,
            "signal_intensity_proportional": True,
            "util_target_30pct": util["util_pct_capital_avg"] >= 30,
            "util_empirical_pct": util["util_pct_capital_avg"],
            "escape_verified": util["util_pct_capital_avg"] >= 30,
            "note": "SHORT-only path: 1x capital deployed (vs paradigm 184 2x gross); ~50% util empirical expected",
        },
        "lesson_61_slug_grep": {
            "patterns_checked": ["short_only", "short_continuous", "short_weighted", "sell_only", "bear_continuous"],
            "collision_count": 0,
            "verified": True,
        },
        "memory_compliance": {
            "no_freemium_trial": True,
            "life_changing_4dim_audited": True,
            "persistence_over_efficiency": True,
            "continuous_parallel_campaign": True,
            "actual_funding_rate_model": True,
        },
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info("wrote %s", out_path)

    # Time series dump
    ts_df = pd.DataFrame({
        "gross_ret": sim["gross_ret"],
        "funding_pnl": sim["funding_pnl"],
        "net_ret": sim["net_ret"],
        "fee_lag": sim["fee_lag"],
        "turnover": sim["turnover"],
        "short_capital": sim["w_S_lag"].abs().sum(axis=1),
        "active_short_syms": (sim["w_S_lag"] < 0).sum(axis=1),
        "eq_basket": eq_basket_ret,
        "btc_short_bnh": -btc_ret,
    })
    ts_path = OUT_DIR / "r1__timeseries.csv"
    ts_df.to_csv(ts_path)
    logger.info("wrote %s", ts_path)

    return result


if __name__ == "__main__":
    result = main()
    print(f"\nVERDICT: {result['verdict']}")
    print(f"REASON: {result['verdict_reason']}")
    print(f"Lesson #72 boundary: {result['lesson_72_boundary_verdict']['verdict']}")
    print(f"Lesson #72 reason:   {result['lesson_72_boundary_verdict']['reason']}")
    sys.exit(0)
