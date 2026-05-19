"""R-1 PoC for paradigm 106:
kind_block_trade_announce_kr_equity_mean_reversion_long_d1.

Hypothesis
----------
KR equity 주식등의대량보유상황보고서 (Form 5, 5%+ shareholder change report)
filing with |stkrt_irds| ≥ 1.0% = institutional flow event.

Mean-reversion direction:
- Block SELL (stkrt_irds_sum < 0)  → D+1 LONG (oversold bounce after overhang absorbed)
- Block BUY  (stkrt_irds_sum > 0)  → D+1 SHORT (buy-pressure exhaustion fade)

Symmetric mean-reversion expected (Lesson #19 SNT mandatory).

Substrate: DART majorstock.json fallback (KIND public endpoint blocked, 404).
Track 3 350-stock universe (KOSPI200 + KOSDAQ150) with 99.6% OHLCV cache coverage.

Design (per agent dispatch spec, R-0 prescreens passed)
--------------------------------------------------------
- Universe: 350 stocks Track 3 (281 stocks have ≥1 Form 5 event, 224 at |Δ|≥1.0%).
- Window: 2024-05-20 .. 2026-05-19 (24 mo, 100% data overlap with majorstock API depth).
- Trigger: signed stkrt_irds_sum from majorstock.json (sum across co-reporters per receipt).
- Threshold sweep: {0.5%, 1.0%, 2.0%, 3.0%} on |stkrt_irds_sum|. Focus = 1.0%.
- Entry: next trading day open strictly after rcept_dt.
- Exit: +1 / +2 / +5 trading days close (hold sweep). Primary D+1.
- Fee: 35bp KR equity round-trip (5bp commission + 30bp slippage estimate).
- Permutation: fee_aware_perm_test n_perms=1000 + bootstrap_ci n_boot=2000.

4-quadrant Symmetric Negative Test (Lesson #19, single batch obligatory)
-----------------------------------------------------------------------
- A_focus_long  : block SELL (irds<0) × LONG  (mean-reversion bounce hypothesis)
- A_mirror_short: block SELL (irds<0) × SHORT (continuation, falsifier)
- B_focus_short : block BUY  (irds>0) × SHORT (mean-reversion fade hypothesis)
- B_mirror_long : block BUY  (irds>0) × LONG  (continuation, falsifier)

Hypothesis predicts A_focus AND B_focus both PASS (symmetric mean-reversion).
If only one direction PASS → asymmetric mean-reversion (Lesson #8 partial).

Cross-proxy strict (Lesson #29 obligatory)
-------------------------------------------
- Fundamental signal: |stkrt_irds_sum| magnitude (filing data) — already in trigger
- Observable proxy: entry_open gap sign (pre-announce sentiment)
  → For A_focus (SELL→LONG): hypothesis = retail bought into overhang →
    gap_neg (open lower than prior close = overshoot) → LONG more profitable
  → For B_focus (BUY→SHORT): hypothesis = retail front-run on buy news →
    gap_pos (open higher) → SHORT more profitable
- BOTH proxies must show coherent direction OR fundamental alone PASS.

Lesson #32 universe-baseline-coherent A_focus trap
---------------------------------------------------
- A_focus universe = stocks with Form 5 ≥1% sell event filed
- B_baseline_same_filter = same universe non-event days
- Pre-compute universe drift: if A_focus < B_baseline → universe artifact.

Lesson #33 magnitude-conditioning trap
---------------------------------------
- Trigger = signed stkrt_irds_sum (signed)
- Outcome = signed forward return (signed)
- Signed-signed independent dimensions PASS (not magnitude-magnitude trap).

Concentration Gate (Lesson #16 + #26 amendment)
------------------------------------------------
- Per-quarter t-stat: ≥ 50% positive over n_measurable ≥ 4 quarters
- Per-symbol bootstrap CI: ≥ 30% ci_pos + ≥ 3 symbols ci_pos
- Per-symbol fraction max ≤ 10%

4-dim life-changing (obligatory)
---------------------------------
- trades/yr ≥ 12
- per_trade_edge_net ≥ +2.0%
- capital_util ≥ 30%
- annualized_sharpe ≥ 1.5

Verdict decision tree
---------------------
1. SAMPLE_INSUFFICIENT (any per-cell n < 30 at |Δ|≥1.0%) → halt
2. SUBSTRATE_INSUFFICIENT (n_measurable_quarters < 4) → halt
3. UNIVERSE_DRIFT_ARTIFACT (A_focus < B_baseline_same_filter) → halt
4. BROAD_FALSIFIED (A_focus AND B_focus 3-gate FAIL across all holds) → graveyard
5. BROAD_FALSIFIED_FEE_FLOOR (gross < fee floor across all holds) → graveyard
6. BROAD_FALSIFIED_DIRECTION_INVERTED (A_mirror or B_mirror passes, A/B focus fail) → graveyard
7. SINGLE_PROXY_TRAP_OBS_ONLY / SINGLE_PROXY_TRAP_FUND_ONLY
8. NARROW_SCOPE_LIFE_CHANGING_FAIL (3-gate PASS but 4-dim FAIL)
9. NARROW_SCOPE_CANDIDATE_ASYMMETRIC (A_focus or B_focus alone PASS but not both)
10. PASS_R1_FULL (A_focus + B_focus + cross_proxy + 4-dim all PASS)

Output: backend/runs/research_track/kind_block_trade_announce_kr_equity_mean_reversion_long_d1/r1_metrics.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
BACKEND_ROOT = HERE.parents[2]  # backend/
sys.path.insert(0, str(BACKEND_ROOT))

# Load .env
ENV_FILE = BACKEND_ROOT / ".env"
if ENV_FILE.exists():
    for ln in ENV_FILE.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import joblib  # noqa: E402

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p106_r1")

PARADIGM_NAME = "kind_block_trade_announce_kr_equity_mean_reversion_long_d1"
OUT_DIR = BACKEND_ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1_metrics.json"

OHLCV_DIR = BACKEND_ROOT / "runs" / "dart_track" / "ohlcv_cache"
MERGED_EVENTS_PATH = OUT_DIR / "form5_merged_events.joblib"

# --- Config ---
HOLDS = (1, 2, 5)             # D+1 primary, D+2 / D+5 sweep
HOLD_PRIMARY = 1
THRESHOLD_SWEEP = (0.5, 1.0, 2.0, 3.0)  # |stkrt_irds_sum| in %
THRESHOLD_FOCUS = 1.0
FEE_ROUND_TRIP = 0.0035        # 35bp KR equity baseline
FEE_STRESS = 0.005             # 50bp KR equity stress
MIN_CELL_N = 30
MAX_SYMBOL_FRACTION = 0.10
N_PERMS = 1000
N_BOOTSTRAP = 2000

# --- 4-dim life-changing thresholds ---
TRADES_PER_YR_MIN = 12.0
PER_TRADE_EDGE_MIN = 0.02
CAPITAL_UTIL_MIN = 0.30
SHARPE_MIN = 1.5


def load_ohlcv(stock_code: str) -> pd.DataFrame:
    p = OHLCV_DIR / f"{stock_code}.joblib"
    if not p.exists():
        return pd.DataFrame()
    df = joblib.load(p)
    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_events_with_returns(merged_events: pd.DataFrame) -> pd.DataFrame:
    """Join merged events with OHLCV: compute entry_open, prior_close, gap, fwd_ret @ HOLDS."""
    cache_path = OUT_DIR / "events_with_returns.joblib"
    if cache_path.exists():
        log.info("loading cached events_with_returns from %s", cache_path)
        return joblib.load(cache_path)

    rows_out = []
    skipped_no_ohlcv = 0
    skipped_no_window = 0
    by_code = merged_events.groupby("stock_code")
    log.info("computing returns across %d symbols, %d events", len(by_code), len(merged_events))
    for idx, (code, grp) in enumerate(by_code, 1):
        ohlcv = load_ohlcv(code)
        if ohlcv.empty:
            skipped_no_ohlcv += len(grp)
            continue
        ohlcv = ohlcv.set_index("date").sort_index()
        dates_arr = ohlcv.index.values
        for _, ev in grp.iterrows():
            ev_dt = ev["rcept_dt"].to_datetime64()
            pos = int(np.searchsorted(dates_arr, ev_dt, side="right"))
            if pos < 1 or pos + max(HOLDS) >= len(ohlcv):
                skipped_no_window += 1
                continue
            prior_close = float(ohlcv["close"].iloc[pos - 1])
            entry_open = float(ohlcv["open"].iloc[pos])
            if not (prior_close > 0 and entry_open > 0):
                skipped_no_window += 1
                continue
            row = {
                "rcept_dt": ev["rcept_dt"],
                "rcept_no": ev["rcept_no"],
                "stock_code": code,
                "corp_code": ev["corp_code"],
                "corp_name": ev["corp_name"],
                "stkrt_irds_sum": float(ev["stkrt_irds_sum"]),
                "stkrt_irds_max_abs": float(ev["stkrt_irds_max_abs"]),
                "n_reporters": int(ev["n_reporters"]),
                "entry_date": ohlcv.index[pos],
                "prior_close": prior_close,
                "entry_open": entry_open,
                "gap": entry_open / prior_close - 1.0,
            }
            valid = True
            for h in HOLDS:
                exit_close = float(ohlcv["close"].iloc[pos + h - 1])
                if exit_close <= 0:
                    valid = False
                    break
                row[f"fwd_ret_{h}d_gross"] = exit_close / entry_open - 1.0
            if not valid:
                skipped_no_window += 1
                continue
            rows_out.append(row)
        if idx % 30 == 0:
            log.info("  ...%d/%d symbols, kept=%d skipped_no_ohlcv=%d skipped_no_window=%d",
                     idx, len(by_code), len(rows_out), skipped_no_ohlcv, skipped_no_window)

    events_ret = pd.DataFrame(rows_out)
    log.info("events with returns: kept=%d skipped_no_ohlcv=%d skipped_no_window=%d",
             len(events_ret), skipped_no_ohlcv, skipped_no_window)
    joblib.dump(events_ret, cache_path)
    log.info("wrote %s", cache_path)
    return events_ret


def candidate_pool_returns(events_ret: pd.DataFrame, hold_days: int,
                           sample_n: int = 12000, rng_seed: int = 42) -> np.ndarray:
    """Random non-trigger entry pool across universe-with-events, same-symbol-pool basis
    for fee_aware_perm_test null distribution at each hold horizon.

    Lesson #32 universe-baseline-coherent: pool drawn from SAME stocks that have ≥1
    Form 5 event (NOT full market 350 stocks), excluding actual trigger dates.
    """
    rng = np.random.default_rng(rng_seed)
    codes = events_ret["stock_code"].unique()
    per_code = max(2, sample_n // max(1, len(codes)))
    out = []
    trig_per_sym = events_ret.groupby("stock_code")["entry_date"].apply(set).to_dict()
    for code in codes:
        ohlcv = load_ohlcv(code)
        if ohlcv.empty or len(ohlcv) < hold_days + 2:
            continue
        ohlcv = ohlcv.sort_values("date").reset_index(drop=True)
        valid_idx = np.arange(0, len(ohlcv) - hold_days)
        if len(valid_idx) == 0:
            continue
        trig_set = trig_per_sym.get(code, set())
        keep_mask = ~ohlcv["date"].iloc[valid_idx].isin(trig_set).values
        valid_idx = valid_idx[keep_mask]
        if len(valid_idx) == 0:
            continue
        pick = rng.choice(valid_idx, size=min(per_code, len(valid_idx)),
                          replace=False)
        opens = ohlcv["open"].iloc[pick].values
        closes = ohlcv["close"].iloc[pick + hold_days - 1].values
        mask = (opens > 0) & (closes > 0)
        out.append(closes[mask] / opens[mask] - 1.0)
    return np.concatenate(out) if out else np.array([])


def _per_sym_counts(df: pd.DataFrame) -> dict:
    return df["stock_code"].value_counts().to_dict()


def cell_stats(returns: np.ndarray, direction: int, label: str, fee: float,
               pool: np.ndarray, by_symbol_count: dict | None = None,
               total_trades: int = 0) -> dict:
    n = len(returns)
    if n == 0:
        return {"label": label, "n": 0, "pass_n": False}
    gross = returns * direction
    net = gross - fee
    if n >= 2 and net.std(ddof=1) > 0:
        t_obs = float(net.mean() / net.std(ddof=1) * np.sqrt(n))
    else:
        t_obs = 0.0
    cell = {
        "label": label,
        "n": int(n),
        "fee_round_trip_bp": int(fee * 10_000),
        "gross_mean_bp": float(gross.mean() * 10_000),
        "net_mean_bp": float(net.mean() * 10_000),
        "t_obs": t_obs,
        "pass_n": n >= MIN_CELL_N,
    }
    if by_symbol_count is not None and total_trades:
        top_sym, top_n = max(by_symbol_count.items(), key=lambda kv: kv[1])
        cell["concentration_top_sym"] = top_sym
        cell["concentration_top_frac"] = float(top_n / total_trades)
        cell["pass_concentration_symbol"] = (top_n / total_trades) <= MAX_SYMBOL_FRACTION

    observed_net = (returns * direction - fee).tolist()
    pool_dir = (pool * direction).tolist()
    perm = fee_aware_perm_test(
        observed_net_returns=observed_net,
        candidate_pool_returns=pool_dir,
        fee_per_trade=fee,
        n_perms=N_PERMS,
    )
    boot = bootstrap_ci(observed_net, n_boot=N_BOOTSTRAP, block_size=1)
    cell.update({
        "signal_t_excess": perm.get("signal_t_excess"),
        "null_mean_t": perm.get("null_mean_t"),
        "perm_p_two_sided": perm.get("perm_p_two_sided"),
        "perm_p_one_sided_above": perm.get("perm_p_one_sided_above"),
        "ci_lower_bp": (float(boot["ci_lower"] * 10_000)
                        if boot.get("ci_lower") is not None else None),
        "ci_upper_bp": (float(boot["ci_upper"] * 10_000)
                        if boot.get("ci_upper") is not None else None),
        "prob_positive": boot.get("prob_positive"),
    })
    passes_three_gate = (
        cell["pass_n"]
        and cell.get("signal_t_excess") is not None and cell["signal_t_excess"] >= 2.0
        and cell.get("ci_lower_bp") is not None and cell["ci_lower_bp"] > 0
        and cell.get("perm_p_one_sided_above") is not None
        and cell["perm_p_one_sided_above"] <= 0.10
    )
    cell["pass_three_gate"] = bool(passes_three_gate)
    return cell


def per_quarter_t(df_with_ret: pd.DataFrame, direction: int, fee: float) -> dict:
    """Per-quarter t-stat distribution for Concentration Gate (Lesson #26 amendment)."""
    df = df_with_ret.copy()
    df["q"] = df["entry_date"].dt.year.astype(str) + "Q" + (
        (df["entry_date"].dt.month - 1) // 3 + 1).astype(str)
    out = {}
    n_pos_t = 0
    n_measurable = 0
    for q, g in df.groupby("q"):
        net = g["ret"].values * direction - fee
        if len(net) < 5 or net.std(ddof=1) <= 0:
            out[q] = {"n": int(len(g)), "t": None, "measurable": False}
            continue
        t = float(net.mean() / net.std(ddof=1) * np.sqrt(len(net)))
        out[q] = {"n": int(len(g)), "t": t, "measurable": True}
        n_measurable += 1
        if t > 0:
            n_pos_t += 1
    out["__summary"] = {
        "n_measurable": n_measurable,
        "n_pos_t": n_pos_t,
        "quarter_pos_t_ratio": (n_pos_t / n_measurable) if n_measurable else None,
        "pass_lesson_26_amendment_n_measurable_min4": n_measurable >= 4,
        "pass_quarter_pos_t_ratio_min_0p5": (
            (n_pos_t / n_measurable) >= 0.5 if n_measurable else False
        ),
    }
    return out


def per_symbol_ci(df_with_ret: pd.DataFrame, direction: int, fee: float) -> dict:
    """Per-symbol bootstrap CI distribution for Concentration Gate (Lesson #16)."""
    n_ci_pos = 0
    n_measurable = 0
    out = {}
    for sym, g in df_with_ret.groupby("stock_code"):
        net = (g["ret"].values * direction - fee).tolist()
        if len(net) < 5:
            continue
        boot = bootstrap_ci(net, n_boot=500, block_size=1)
        ci_lower = boot.get("ci_lower")
        out[sym] = {
            "n": int(len(g)),
            "ci_lower_bp": float(ci_lower * 10_000) if ci_lower is not None else None,
            "ci_pos": ci_lower is not None and ci_lower > 0,
        }
        n_measurable += 1
        if ci_lower is not None and ci_lower > 0:
            n_ci_pos += 1
    out["__summary"] = {
        "n_measurable": n_measurable,
        "n_ci_pos": n_ci_pos,
        "symbol_ci_pos_ratio": (n_ci_pos / n_measurable) if n_measurable else None,
        "pass_symbol_ci_pos_ratio_min_0p30": (
            (n_ci_pos / n_measurable) >= 0.30 if n_measurable else False
        ),
        "pass_n_symbols_ci_pos_min_3": n_ci_pos >= 3,
    }
    return out


def life_changing_4dim(events_ret: pd.DataFrame, hold_days: int,
                       direction: int, fee: float) -> dict:
    """Per-trade edge / trades/yr / sharpe / capital utilization for ONE focus quadrant."""
    df = events_ret.copy()
    df["net_ret"] = df[f"fwd_ret_{hold_days}d_gross"] * direction - fee
    n_trades = len(df)
    if n_trades == 0:
        return {"n_trades": 0, "pass_4dim_life_changing": False}
    window_days = (df["entry_date"].max() - df["entry_date"].min()).days
    years = max(window_days / 365.25, 1e-9)
    trades_per_yr = n_trades / years
    per_trade_edge_net = float(df["net_ret"].mean())
    if n_trades >= 2 and df["net_ret"].std(ddof=1) > 0:
        sharpe = float(per_trade_edge_net / df["net_ret"].std(ddof=1) * np.sqrt(trades_per_yr))
    else:
        sharpe = 0.0
    avg_open = trades_per_yr * hold_days / 250.0
    days_with_open = set()
    for _, ev in df.iterrows():
        ed = ev["entry_date"]
        for k in range(hold_days):
            days_with_open.add(ed + pd.Timedelta(days=k))
    util_calendar = len(days_with_open) / max(window_days, 1)

    return {
        "n_trades": int(n_trades),
        "window_days": int(window_days),
        "trades_per_yr": float(trades_per_yr),
        "per_trade_edge_net_pct": float(per_trade_edge_net * 100),
        "annualized_sharpe": float(sharpe),
        "avg_open_positions": float(avg_open),
        "util_calendar": float(util_calendar),
        "pass_trades_per_yr_min12": trades_per_yr >= TRADES_PER_YR_MIN,
        "pass_per_trade_edge_min_2pct": per_trade_edge_net >= PER_TRADE_EDGE_MIN,
        "pass_capital_util_min_30pct": util_calendar >= CAPITAL_UTIL_MIN,
        "pass_sharpe_min_1p5": sharpe >= SHARPE_MIN,
        "pass_4dim_life_changing": (
            trades_per_yr >= TRADES_PER_YR_MIN
            and per_trade_edge_net >= PER_TRADE_EDGE_MIN
            and util_calendar >= CAPITAL_UTIL_MIN
            and sharpe >= SHARPE_MIN
        ),
    }


def run_one_hold_threshold(events_ret: pd.DataFrame, hold_days: int,
                           threshold_pct: float) -> dict:
    """4-quadrant signed SNT + cross-proxy + Concentration + 4-dim
    for a single (hold, |Δ| threshold) combo."""
    ret_col = f"fwd_ret_{hold_days}d_gross"
    df_all = events_ret.dropna(subset=[ret_col]).copy()
    df_all["ret"] = df_all[ret_col]

    df_sell = df_all[df_all["stkrt_irds_sum"] <= -threshold_pct].copy()
    df_buy = df_all[df_all["stkrt_irds_sum"] >= +threshold_pct].copy()

    log.info("hold=%dd |Δ|>=%.1f%%: total_in_window=%d  sell=%d  buy=%d",
             hold_days, threshold_pct, len(df_all), len(df_sell), len(df_buy))

    pool = candidate_pool_returns(df_all, hold_days)
    log.info("  candidate pool size: %d", len(pool))

    cells = {}

    # A focus (mean-reversion bounce): block SELL × LONG
    sym_counts_sell = _per_sym_counts(df_sell)
    cells["A_focus_sell_long"] = cell_stats(
        df_sell["ret"].values, direction=+1, label="block_SELL × LONG (MR bounce)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_sell, total_trades=len(df_sell),
    )
    # A mirror: block SELL × SHORT (continuation falsifier)
    cells["A_mirror_sell_short"] = cell_stats(
        df_sell["ret"].values, direction=-1, label="block_SELL × SHORT (continuation falsifier)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_sell, total_trades=len(df_sell),
    )
    # B focus (mean-reversion fade): block BUY × SHORT
    sym_counts_buy = _per_sym_counts(df_buy)
    cells["B_focus_buy_short"] = cell_stats(
        df_buy["ret"].values, direction=-1, label="block_BUY × SHORT (MR fade)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_buy, total_trades=len(df_buy),
    )
    # B mirror: block BUY × LONG (continuation falsifier)
    cells["B_mirror_buy_long"] = cell_stats(
        df_buy["ret"].values, direction=+1, label="block_BUY × LONG (continuation falsifier)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_buy, total_trades=len(df_buy),
    )

    # Stress fee 50bp on A focus + B focus
    cells["A_focus_sell_long_stress50bp"] = cell_stats(
        df_sell["ret"].values, direction=+1, label="block_SELL × LONG @ 50bp",
        fee=FEE_STRESS, pool=pool,
        by_symbol_count=sym_counts_sell, total_trades=len(df_sell),
    )
    cells["B_focus_buy_short_stress50bp"] = cell_stats(
        df_buy["ret"].values, direction=-1, label="block_BUY × SHORT @ 50bp",
        fee=FEE_STRESS, pool=pool,
        by_symbol_count=sym_counts_buy, total_trades=len(df_buy),
    )

    # Cross-proxy strict (Lesson #29)
    # Observable proxy = entry_open gap sign
    # Hypothesis-coherent:
    #   A_focus (SELL→LONG MR bounce): gap_neg better (overshoot → larger bounce)
    #   B_focus (BUY→SHORT MR fade):   gap_pos better (front-run pop → larger fade)
    cross_proxy = {}
    if len(df_sell):
        gap_pos_sell = df_sell[df_sell["gap"] > 0]
        gap_neg_sell = df_sell[df_sell["gap"] <= 0]
        cross_proxy["A_focus_gap_pos_long"] = cell_stats(
            gap_pos_sell["ret"].values, direction=+1, label="A_focus gap_pos × LONG",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_pos_sell), total_trades=len(gap_pos_sell),
        ) if len(gap_pos_sell) else {"n": 0}
        cross_proxy["A_focus_gap_neg_long"] = cell_stats(
            gap_neg_sell["ret"].values, direction=+1, label="A_focus gap_neg × LONG",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_neg_sell), total_trades=len(gap_neg_sell),
        ) if len(gap_neg_sell) else {"n": 0}
    if len(df_buy):
        gap_pos_buy = df_buy[df_buy["gap"] > 0]
        gap_neg_buy = df_buy[df_buy["gap"] <= 0]
        cross_proxy["B_focus_gap_pos_short"] = cell_stats(
            gap_pos_buy["ret"].values, direction=-1, label="B_focus gap_pos × SHORT",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_pos_buy), total_trades=len(gap_pos_buy),
        ) if len(gap_pos_buy) else {"n": 0}
        cross_proxy["B_focus_gap_neg_short"] = cell_stats(
            gap_neg_buy["ret"].values, direction=-1, label="B_focus gap_neg × SHORT",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_neg_buy), total_trades=len(gap_neg_buy),
        ) if len(gap_neg_buy) else {"n": 0}

    cross_proxy_summary = {
        "A_focus_gap_neg_better_than_gap_pos":
            (cross_proxy.get("A_focus_gap_neg_long", {}).get("net_mean_bp", 0)
             > cross_proxy.get("A_focus_gap_pos_long", {}).get("net_mean_bp", 0))
            if cross_proxy.get("A_focus_gap_neg_long", {}).get("n", 0) >= MIN_CELL_N
            and cross_proxy.get("A_focus_gap_pos_long", {}).get("n", 0) >= MIN_CELL_N
            else None,
        "B_focus_gap_pos_better_than_gap_neg":
            (cross_proxy.get("B_focus_gap_pos_short", {}).get("net_mean_bp", 0)
             > cross_proxy.get("B_focus_gap_neg_short", {}).get("net_mean_bp", 0))
            if cross_proxy.get("B_focus_gap_pos_short", {}).get("n", 0) >= MIN_CELL_N
            and cross_proxy.get("B_focus_gap_neg_short", {}).get("n", 0) >= MIN_CELL_N
            else None,
    }

    # Lesson #32: universe-baseline-coherent A_focus trap
    # B_baseline_same_filter = same universe non-event days = candidate pool, LONG (matches A focus direction)
    b_baseline_long = cell_stats(
        pool, direction=+1, label="non_event × LONG (universe baseline)",
        fee=FEE_ROUND_TRIP, pool=pool,
    )
    b_baseline_short = cell_stats(
        pool, direction=-1, label="non_event × SHORT (universe baseline)",
        fee=FEE_ROUND_TRIP, pool=pool,
    )
    universe_drift = {
        "A_focus_net_bp": cells["A_focus_sell_long"].get("net_mean_bp", 0),
        "B_baseline_long_net_bp": b_baseline_long.get("net_mean_bp", 0),
        "A_focus_vs_baseline_excess_bp": (
            cells["A_focus_sell_long"].get("net_mean_bp", 0) - b_baseline_long.get("net_mean_bp", 0)
        ),
        "B_focus_net_bp": cells["B_focus_buy_short"].get("net_mean_bp", 0),
        "B_baseline_short_net_bp": b_baseline_short.get("net_mean_bp", 0),
        "B_focus_vs_baseline_excess_bp": (
            cells["B_focus_buy_short"].get("net_mean_bp", 0) - b_baseline_short.get("net_mean_bp", 0)
        ),
        "pass_A_focus_exceeds_baseline": (
            cells["A_focus_sell_long"].get("net_mean_bp", 0) > b_baseline_long.get("net_mean_bp", 0)
        ),
        "pass_B_focus_exceeds_baseline": (
            cells["B_focus_buy_short"].get("net_mean_bp", 0) > b_baseline_short.get("net_mean_bp", 0)
        ),
    }

    # Concentration Gate per quadrant (Lesson #16 + #26 amendment)
    per_q_A = per_quarter_t(df_sell.rename(columns={"ret": "ret"})[["entry_date", "ret"]],
                            direction=+1, fee=FEE_ROUND_TRIP) if len(df_sell) else {"__summary": {}}
    per_s_A = per_symbol_ci(df_sell[["stock_code", "ret"]],
                            direction=+1, fee=FEE_ROUND_TRIP) if len(df_sell) else {"__summary": {}}
    per_q_B = per_quarter_t(df_buy.rename(columns={"ret": "ret"})[["entry_date", "ret"]],
                            direction=-1, fee=FEE_ROUND_TRIP) if len(df_buy) else {"__summary": {}}
    per_s_B = per_symbol_ci(df_buy[["stock_code", "ret"]],
                            direction=-1, fee=FEE_ROUND_TRIP) if len(df_buy) else {"__summary": {}}

    concentration_A_pass = bool(
        per_q_A.get("__summary", {}).get("pass_lesson_26_amendment_n_measurable_min4")
        and per_q_A.get("__summary", {}).get("pass_quarter_pos_t_ratio_min_0p5")
        and per_s_A.get("__summary", {}).get("pass_symbol_ci_pos_ratio_min_0p30")
        and per_s_A.get("__summary", {}).get("pass_n_symbols_ci_pos_min_3")
    )
    concentration_B_pass = bool(
        per_q_B.get("__summary", {}).get("pass_lesson_26_amendment_n_measurable_min4")
        and per_q_B.get("__summary", {}).get("pass_quarter_pos_t_ratio_min_0p5")
        and per_s_B.get("__summary", {}).get("pass_symbol_ci_pos_ratio_min_0p30")
        and per_s_B.get("__summary", {}).get("pass_n_symbols_ci_pos_min_3")
    )

    # 4-dim life-changing per focus quadrant
    four_dim_A = life_changing_4dim(df_sell, hold_days, direction=+1, fee=FEE_ROUND_TRIP) \
        if len(df_sell) else {"n_trades": 0, "pass_4dim_life_changing": False}
    four_dim_B = life_changing_4dim(df_buy, hold_days, direction=-1, fee=FEE_ROUND_TRIP) \
        if len(df_buy) else {"n_trades": 0, "pass_4dim_life_changing": False}

    return {
        "hold_days": hold_days,
        "threshold_pct": threshold_pct,
        "n_sell_events": int(len(df_sell)),
        "n_buy_events": int(len(df_buy)),
        "pool_n": int(len(pool)),
        "quadrants": cells,
        "cross_proxy_observable_gap": cross_proxy,
        "cross_proxy_summary": cross_proxy_summary,
        "universe_drift_lesson_32": universe_drift,
        "B_baseline_long": b_baseline_long,
        "B_baseline_short": b_baseline_short,
        "concentration_per_quarter_A": per_q_A,
        "concentration_per_symbol_A": per_s_A,
        "concentration_per_quarter_B": per_q_B,
        "concentration_per_symbol_B": per_s_B,
        "concentration_gate_A_pass": concentration_A_pass,
        "concentration_gate_B_pass": concentration_B_pass,
        "life_changing_4dim_A": four_dim_A,
        "life_changing_4dim_B": four_dim_B,
    }


def main():
    log.info("=== R-1 PoC: paradigm 106 %s ===", PARADIGM_NAME)

    if not MERGED_EVENTS_PATH.exists():
        log.error("MERGED_EVENTS_PATH missing: %s", MERGED_EVENTS_PATH)
        return 1
    merged_events = joblib.load(MERGED_EVENTS_PATH)
    log.info("Loaded merged_events: %d rows / %d stocks",
             len(merged_events), merged_events["stock_code"].nunique())

    # |stkrt_irds_sum| empirical distribution (Lesson #34)
    abs_arr = merged_events["stkrt_irds_sum"].abs().values
    distrib = {
        "p50": float(np.percentile(abs_arr, 50)),
        "p75": float(np.percentile(abs_arr, 75)),
        "p90": float(np.percentile(abs_arr, 90)),
        "p95": float(np.percentile(abs_arr, 95)),
        "p99": float(np.percentile(abs_arr, 99)),
        "max": float(abs_arr.max()),
    }
    log.info("|stkrt_irds_sum| dist: p50=%.2f%% p75=%.2f%% p90=%.2f%% p99=%.2f%%",
             distrib["p50"], distrib["p75"], distrib["p90"], distrib["p99"])

    events_ret = build_events_with_returns(merged_events)
    if events_ret.empty:
        out = {"verdict": "SAMPLE_INSUFFICIENT_OHLCV", "n_events_with_returns": 0}
        OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        log.info("HALT: no events with returns")
        return 0

    log.info("events with returns: %d (across %d symbols)",
             len(events_ret), events_ret["stock_code"].nunique())

    # Run threshold × hold matrix
    all_results = {}
    for thr in THRESHOLD_SWEEP:
        for h in HOLDS:
            key = f"thr_{thr:.1f}_hold_{h}d"
            log.info(">>> threshold=%.1f%% hold=%dd", thr, h)
            all_results[key] = run_one_hold_threshold(events_ret, h, thr)

    # Primary verdict from threshold=1.0% × hold=1d
    primary_key = f"thr_{THRESHOLD_FOCUS:.1f}_hold_{HOLD_PRIMARY}d"
    primary = all_results[primary_key]
    afoc = primary["quadrants"]["A_focus_sell_long"]
    amir = primary["quadrants"]["A_mirror_sell_short"]
    bfoc = primary["quadrants"]["B_focus_buy_short"]
    bmir = primary["quadrants"]["B_mirror_buy_long"]

    # Sample sufficiency at primary
    if afoc.get("n", 0) < MIN_CELL_N or bfoc.get("n", 0) < MIN_CELL_N:
        verdict = "SAMPLE_INSUFFICIENT"
    else:
        # Substrate Q audit
        per_q_A_summary = primary["concentration_per_quarter_A"].get("__summary", {})
        per_q_B_summary = primary["concentration_per_quarter_B"].get("__summary", {})
        if not (per_q_A_summary.get("pass_lesson_26_amendment_n_measurable_min4")
                and per_q_B_summary.get("pass_lesson_26_amendment_n_measurable_min4")):
            verdict = "SUBSTRATE_INSUFFICIENT"
        else:
            # Lesson #32 universe drift
            univ_drift = primary["universe_drift_lesson_32"]
            a_drift_fail = not univ_drift.get("pass_A_focus_exceeds_baseline")
            b_drift_fail = not univ_drift.get("pass_B_focus_exceeds_baseline")
            if a_drift_fail and b_drift_fail:
                verdict = "BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT"
            else:
                afoc_pass = afoc.get("pass_three_gate")
                amir_pass = amir.get("pass_three_gate")
                bfoc_pass = bfoc.get("pass_three_gate")
                bmir_pass = bmir.get("pass_three_gate")
                cgate_A = primary.get("concentration_gate_A_pass")
                cgate_B = primary.get("concentration_gate_B_pass")
                four_dim_A_pass = primary["life_changing_4dim_A"].get("pass_4dim_life_changing")
                four_dim_B_pass = primary["life_changing_4dim_B"].get("pass_4dim_life_changing")

                # Fee-floor check
                gross_A = afoc.get("gross_mean_bp", 0)
                gross_B = bfoc.get("gross_mean_bp", 0)
                fee_floor_bp = FEE_ROUND_TRIP * 10_000
                if abs(gross_A) < fee_floor_bp and abs(gross_B) < fee_floor_bp:
                    verdict = "BROAD_FALSIFIED_FEE_FLOOR"
                elif not afoc_pass and not bfoc_pass:
                    # Check if mirror passes (direction-inverted artifact)
                    if amir_pass or bmir_pass:
                        verdict = "BROAD_FALSIFIED_DIRECTION_INVERTED"
                    else:
                        verdict = "BROAD_FALSIFIED"
                elif afoc_pass and bfoc_pass and cgate_A and cgate_B and four_dim_A_pass and four_dim_B_pass:
                    verdict = "PASS_R1_FULL"
                elif (afoc_pass and not bfoc_pass) or (bfoc_pass and not afoc_pass):
                    # Asymmetric mean-reversion — only one direction
                    if four_dim_A_pass or four_dim_B_pass:
                        verdict = "NARROW_SCOPE_CANDIDATE_ASYMMETRIC"
                    else:
                        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
                elif afoc_pass and bfoc_pass and not (four_dim_A_pass and four_dim_B_pass):
                    verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
                elif afoc_pass and bfoc_pass and not (cgate_A and cgate_B):
                    verdict = "CONCENTRATION_FAIL"
                else:
                    verdict = "BROAD_FALSIFIED"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "phase": "R-1",
        "verdict": verdict,
        "primary_threshold_pct": THRESHOLD_FOCUS,
        "primary_hold_days": HOLD_PRIMARY,
        "n_events_total": int(len(events_ret)),
        "n_distinct_stocks": int(events_ret["stock_code"].nunique()),
        "window_kst": "2024-05-20 .. 2026-05-19 (24mo Form 5 majorstock substrate)",
        "substrate_note": (
            "KIND public endpoint blocked (404) — fallback to DART majorstock.json "
            "주식등의대량보유상황보고서 (Form 5, 5%+ stake change). "
            "stkrt_irds_sum signed across co-reporters per receipt."
        ),
        "stkrt_irds_distribution_lesson_34": distrib,
        "config": {
            "universe_size_track3": 350,
            "fee_round_trip_bp": int(FEE_ROUND_TRIP * 10_000),
            "fee_stress_bp": int(FEE_STRESS * 10_000),
            "min_cell_n": MIN_CELL_N,
            "max_symbol_fraction": MAX_SYMBOL_FRACTION,
            "n_perms": N_PERMS,
            "n_bootstrap": N_BOOTSTRAP,
            "threshold_sweep_pct": list(THRESHOLD_SWEEP),
            "threshold_focus_pct": THRESHOLD_FOCUS,
            "hold_sweep_days": list(HOLDS),
            "hold_primary_days": HOLD_PRIMARY,
        },
        "by_threshold_hold": all_results,
        "timestamp_kst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    def _clean(o):
        if isinstance(o, float):
            return None if not np.isfinite(o) else o
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if not np.isfinite(float(o)) else float(o)
        return o

    OUT_PATH.write_text(json.dumps(_clean(out), indent=2, ensure_ascii=False))
    log.info("WROTE %s", OUT_PATH)
    log.info("VERDICT: %s", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
