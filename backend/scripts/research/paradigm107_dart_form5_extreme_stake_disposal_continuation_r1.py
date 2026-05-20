"""R-1 PoC for paradigm 107:
dart_form5_extreme_stake_disposal_kr_equity_continuation_short_d5.

Hypothesis
----------
DART Form 5 (주식등의대량보유상황보고서) signed Δstake_pct EXTREME magnitude
(≤ -3.0% institutional disposal / ≥ +3.0% institutional accumulation) ×
D+5 hold CONTINUATION direction (institutional information asymmetry →
continued downside on extreme disposal / continued upside on extreme accumulation).

Lesson #36 candidate first direct verification.
paradigm 106 inverted discovery cell (thr=3.0%×hold=5d×A_mirror_sell_short)
delivered sigex +2.92 / perm_p 0.003 / gross 166.7bp net 131.7bp,
but ci_lower=-58.77bp blocked 3-gate. paradigm 107 directly targets
this cell as A_focus with tightened CI (n_boot=2000, n_perms=2000) +
extended hold sweep (D+3/D+5/D+10/D+20) + threshold safety
(primary thr=2.5%, fallback thr=3.0% if sample-density fails).

Direction model
---------------
- A_focus: SELL (Δ ≤ -thr) × SHORT — continuation hypothesis (informed seller exit signals weakness)
- A_mirror: SELL × LONG — paradigm 106 original mean-reversion direction (falsifier)
- B_focus: BUY (Δ ≥ +thr) × LONG — continuation hypothesis (informed buyer accumulation signals strength)
- B_mirror: BUY × SHORT — mean-reversion fade direction (falsifier)

Expected quadrant signature if continuation real: [A_focus +, A_mirror -, B_focus +, B_mirror -]
paradigm 106 cache evidence at thr=3.0%×hold=5d (cross-paradigm):
  A_focus (= 106 A_mirror_sell_short) gross +166.7bp, sigex +2.92, perm_p 0.003, ci_lower -58.77bp
  B_focus (= 106 B_mirror_buy_long)   gross +146.0bp, sigex +0.44, perm_p 0.326, ci_lower -51.30bp
→ Asymmetric continuation expected (SELL side stronger), B may not pass even at extreme magnitude.

Substrate: paradigm 106 events_with_returns.joblib REUSED + extended fwd_ret @ D+10/D+20
from OHLCV cache. 2,075 events / 278 stocks / 2024-05-21 .. 2026-05-11 (~24 mo).

Skill-spec novelty exception
-----------------------------
1/5 NOVEL axes (only Mechanism: magnitude-dependent direction inversion).
Justification: paradigm 107 is direct Lesson #36 candidate verification, the
candidate was discovered as side observation in paradigm 106 (sourced upstream).
Single-axis NOVEL accepted as Lesson #36 dogfood vehicle.
Document in r1_metrics.json __novelty_exception_note.

Verdict tree
------------
1. SAMPLE_INSUFFICIENT — per-cell n < 30 even at fallback thr=2.5%
2. SUBSTRATE_INSUFFICIENT — n_measurable_quarters < 4
3. UNIVERSE_DRIFT_ARTIFACT — A_focus & B_focus both fail to exceed baseline
4. PASS_R1_FULL — A_focus + B_focus + 3-gate + Concentration + 4-dim ALL PASS
5. NARROW_SCOPE_CANDIDATE_ASYMMETRIC — only A or B passes 3-gate + 4-dim
6. NARROW_SCOPE_LIFE_CHANGING_FAIL — Lesson #20 4-cond PASS but life-changing 4-dim FAIL
7. CONCENTRATION_FAIL — 3-gate PASS but Concentration Gate FAIL
8. BROAD_FALSIFIED_FEE_FLOOR — gross < 35bp across all sweeps
9. BROAD_FALSIFIED_DIRECTION_INVERTED — A_mirror/B_mirror passes (paradigm 106 thesis valid)
10. BROAD_FALSIFIED — A_focus + B_focus + mirrors all fail
11. LESSON_36_INVALIDATED — explicit verdict for paradigm 106 inverted finding ruled noise

Output: backend/runs/research_track/dart_form5_extreme_stake_disposal_kr_equity_continuation_short_d5/r1_metrics.json
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
BACKEND_ROOT = HERE.parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

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
log = logging.getLogger("p107_r1")

PARADIGM_NAME = "dart_form5_extreme_stake_disposal_kr_equity_continuation_short_d5"
OUT_DIR = BACKEND_ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1_metrics.json"

OHLCV_DIR = BACKEND_ROOT / "runs" / "dart_track" / "ohlcv_cache"

# Reuse paradigm 106 event cache (substrate audit verified)
P106_DIR = BACKEND_ROOT / "runs" / "research_track" / "kind_block_trade_announce_kr_equity_mean_reversion_long_d1"
P106_EVENTS_CACHE = P106_DIR / "events_with_returns.joblib"
P107_EVENTS_EXT_CACHE = OUT_DIR / "events_with_returns_ext.joblib"

# --- Config ---
HOLDS = (3, 5, 10, 20)              # D+3 / D+5 (primary) / D+10 / D+20
HOLD_PRIMARY = 5
THRESHOLD_SWEEP = (2.0, 2.5, 3.0, 5.0)
THRESHOLD_FOCUS = 2.5               # primary safer than 3.0% for n>=30/cell/quarter
THRESHOLD_FALLBACK = 3.0            # paradigm 106 inverted-discovery cell
FEE_ROUND_TRIP = 0.0035             # 35bp KR equity baseline
FEE_STRESS = 0.0050                 # 50bp KR equity stress
MIN_CELL_N = 30
MAX_SYMBOL_FRACTION = 0.10
N_PERMS = 2000                      # tightened vs paradigm 106 (1000) for ci stability check
N_BOOTSTRAP = 2000                  # paradigm 106 also used 2000, kept

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


def build_extended_events_with_returns() -> pd.DataFrame:
    """Reuse paradigm 106 events_with_returns + add fwd_ret_10d_gross / fwd_ret_20d_gross."""
    if P107_EVENTS_EXT_CACHE.exists():
        log.info("loading cached extended events from %s", P107_EVENTS_EXT_CACHE)
        return joblib.load(P107_EVENTS_EXT_CACHE)

    if not P106_EVENTS_CACHE.exists():
        log.error("paradigm 106 events cache missing: %s", P106_EVENTS_CACHE)
        raise FileNotFoundError(P106_EVENTS_CACHE)

    base = joblib.load(P106_EVENTS_CACHE)
    log.info("paradigm 106 base events loaded: %d rows / %d stocks",
             len(base), base["stock_code"].nunique())

    # Add D+3, D+10, D+20 (D+5 already present)
    needed = [3, 10, 20]
    for h in needed:
        base[f"fwd_ret_{h}d_gross"] = np.nan

    by_code = base.groupby("stock_code")
    valid_mask = np.zeros(len(base), dtype=bool)
    log.info("computing extended fwd_ret across %d symbols", len(by_code))
    for idx, (code, grp) in enumerate(by_code, 1):
        ohlcv = load_ohlcv(code)
        if ohlcv.empty:
            continue
        ohlcv = ohlcv.set_index("date").sort_index()
        dates_arr = ohlcv.index.values
        for ev_idx, ev in grp.iterrows():
            ev_dt = ev["rcept_dt"].to_datetime64() if hasattr(ev["rcept_dt"], "to_datetime64") \
                else np.datetime64(ev["rcept_dt"])
            pos = int(np.searchsorted(dates_arr, ev_dt, side="right"))
            if pos < 1 or pos + max(needed) >= len(ohlcv):
                continue
            entry_open = float(ohlcv["open"].iloc[pos])
            if entry_open <= 0:
                continue
            ok = True
            for h in needed:
                ec = float(ohlcv["close"].iloc[pos + h - 1])
                if ec <= 0:
                    ok = False
                    break
                base.at[ev_idx, f"fwd_ret_{h}d_gross"] = ec / entry_open - 1.0
            if ok:
                valid_mask[base.index.get_loc(ev_idx)] = True
        if idx % 30 == 0:
            log.info("  ...%d/%d symbols processed", idx, len(by_code))

    n_full = int(base[[f"fwd_ret_{h}d_gross" for h in (3, 5, 10, 20)]].notna().all(axis=1).sum())
    log.info("extended events: total=%d / full-horizon (D+3/5/10/20)=%d", len(base), n_full)
    joblib.dump(base, P107_EVENTS_EXT_CACHE)
    log.info("wrote %s", P107_EVENTS_EXT_CACHE)
    return base


def candidate_pool_returns(events_ret: pd.DataFrame, hold_days: int,
                           sample_n: int = 12000, rng_seed: int = 42) -> np.ndarray:
    """Universe-baseline-coherent (Lesson #32) non-event-day random sample."""
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
    """4-quadrant SNT for paradigm 107 CONTINUATION direction.

    A_focus = SELL × SHORT   (continuation hypothesis)
    A_mirror = SELL × LONG   (paradigm 106 mean-rev direction = falsifier)
    B_focus = BUY × LONG     (continuation hypothesis symmetric)
    B_mirror = BUY × SHORT   (mean-rev fade = falsifier)
    """
    ret_col = f"fwd_ret_{hold_days}d_gross"
    df_all = events_ret.dropna(subset=[ret_col]).copy()
    df_all["ret"] = df_all[ret_col]

    df_sell = df_all[df_all["stkrt_irds_sum"] <= -threshold_pct].copy()
    df_buy = df_all[df_all["stkrt_irds_sum"] >= +threshold_pct].copy()

    log.info("hold=%dd |Δ|>=%.2f%%: total_in_window=%d  sell=%d  buy=%d",
             hold_days, threshold_pct, len(df_all), len(df_sell), len(df_buy))

    pool = candidate_pool_returns(df_all, hold_days)
    log.info("  candidate pool size: %d", len(pool))

    cells = {}

    sym_counts_sell = _per_sym_counts(df_sell)
    cells["A_focus_sell_short"] = cell_stats(
        df_sell["ret"].values, direction=-1, label="block_SELL × SHORT (CONTINUATION hypothesis)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_sell, total_trades=len(df_sell),
    )
    cells["A_mirror_sell_long"] = cell_stats(
        df_sell["ret"].values, direction=+1, label="block_SELL × LONG (paradigm 106 mean-rev / falsifier)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_sell, total_trades=len(df_sell),
    )
    sym_counts_buy = _per_sym_counts(df_buy)
    cells["B_focus_buy_long"] = cell_stats(
        df_buy["ret"].values, direction=+1, label="block_BUY × LONG (CONTINUATION hypothesis symmetric)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_buy, total_trades=len(df_buy),
    )
    cells["B_mirror_buy_short"] = cell_stats(
        df_buy["ret"].values, direction=-1, label="block_BUY × SHORT (mean-rev fade / falsifier)",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts_buy, total_trades=len(df_buy),
    )
    # Stress fee 50bp on A focus + B focus
    cells["A_focus_sell_short_stress50bp"] = cell_stats(
        df_sell["ret"].values, direction=-1, label="block_SELL × SHORT @ 50bp",
        fee=FEE_STRESS, pool=pool,
        by_symbol_count=sym_counts_sell, total_trades=len(df_sell),
    )
    cells["B_focus_buy_long_stress50bp"] = cell_stats(
        df_buy["ret"].values, direction=+1, label="block_BUY × LONG @ 50bp",
        fee=FEE_STRESS, pool=pool,
        by_symbol_count=sym_counts_buy, total_trades=len(df_buy),
    )

    # Cross-proxy strict (Lesson #29)
    # Observable proxy = entry_open gap sign
    # Continuation-coherent:
    #   A_focus (SELL→SHORT continuation): gap_neg better (overnight already selling pressure = continued informed exit)
    #   B_focus (BUY→LONG continuation): gap_pos better (overnight already buying pressure = continued informed accumulation)
    cross_proxy = {}
    if len(df_sell):
        gap_pos_sell = df_sell[df_sell["gap"] > 0]
        gap_neg_sell = df_sell[df_sell["gap"] <= 0]
        cross_proxy["A_focus_gap_neg_short"] = cell_stats(
            gap_neg_sell["ret"].values, direction=-1,
            label="A_focus gap_neg × SHORT (continuation-coherent)",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_neg_sell), total_trades=len(gap_neg_sell),
        ) if len(gap_neg_sell) else {"n": 0}
        cross_proxy["A_focus_gap_pos_short"] = cell_stats(
            gap_pos_sell["ret"].values, direction=-1,
            label="A_focus gap_pos × SHORT",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_pos_sell), total_trades=len(gap_pos_sell),
        ) if len(gap_pos_sell) else {"n": 0}
    if len(df_buy):
        gap_pos_buy = df_buy[df_buy["gap"] > 0]
        gap_neg_buy = df_buy[df_buy["gap"] <= 0]
        cross_proxy["B_focus_gap_pos_long"] = cell_stats(
            gap_pos_buy["ret"].values, direction=+1,
            label="B_focus gap_pos × LONG (continuation-coherent)",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_pos_buy), total_trades=len(gap_pos_buy),
        ) if len(gap_pos_buy) else {"n": 0}
        cross_proxy["B_focus_gap_neg_long"] = cell_stats(
            gap_neg_buy["ret"].values, direction=+1,
            label="B_focus gap_neg × LONG",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_neg_buy), total_trades=len(gap_neg_buy),
        ) if len(gap_neg_buy) else {"n": 0}

    cross_proxy_summary = {
        "A_focus_gap_neg_better_than_gap_pos":
            (cross_proxy.get("A_focus_gap_neg_short", {}).get("net_mean_bp", 0)
             > cross_proxy.get("A_focus_gap_pos_short", {}).get("net_mean_bp", 0))
            if cross_proxy.get("A_focus_gap_neg_short", {}).get("n", 0) >= MIN_CELL_N
            and cross_proxy.get("A_focus_gap_pos_short", {}).get("n", 0) >= MIN_CELL_N
            else None,
        "B_focus_gap_pos_better_than_gap_neg":
            (cross_proxy.get("B_focus_gap_pos_long", {}).get("net_mean_bp", 0)
             > cross_proxy.get("B_focus_gap_neg_long", {}).get("net_mean_bp", 0))
            if cross_proxy.get("B_focus_gap_pos_long", {}).get("n", 0) >= MIN_CELL_N
            and cross_proxy.get("B_focus_gap_neg_long", {}).get("n", 0) >= MIN_CELL_N
            else None,
    }

    # Lesson #32 universe-baseline-coherent
    b_baseline_short = cell_stats(
        pool, direction=-1, label="non_event × SHORT (universe baseline)",
        fee=FEE_ROUND_TRIP, pool=pool,
    )
    b_baseline_long = cell_stats(
        pool, direction=+1, label="non_event × LONG (universe baseline)",
        fee=FEE_ROUND_TRIP, pool=pool,
    )
    universe_drift = {
        "A_focus_net_bp": cells["A_focus_sell_short"].get("net_mean_bp", 0),
        "B_baseline_short_net_bp": b_baseline_short.get("net_mean_bp", 0),
        "A_focus_vs_baseline_excess_bp": (
            cells["A_focus_sell_short"].get("net_mean_bp", 0)
            - b_baseline_short.get("net_mean_bp", 0)
        ),
        "B_focus_net_bp": cells["B_focus_buy_long"].get("net_mean_bp", 0),
        "B_baseline_long_net_bp": b_baseline_long.get("net_mean_bp", 0),
        "B_focus_vs_baseline_excess_bp": (
            cells["B_focus_buy_long"].get("net_mean_bp", 0)
            - b_baseline_long.get("net_mean_bp", 0)
        ),
        "pass_A_focus_exceeds_baseline": (
            cells["A_focus_sell_short"].get("net_mean_bp", 0)
            > b_baseline_short.get("net_mean_bp", 0)
        ),
        "pass_B_focus_exceeds_baseline": (
            cells["B_focus_buy_long"].get("net_mean_bp", 0)
            > b_baseline_long.get("net_mean_bp", 0)
        ),
    }

    per_q_A = per_quarter_t(df_sell[["entry_date", "ret"]],
                            direction=-1, fee=FEE_ROUND_TRIP) if len(df_sell) else {"__summary": {}}
    per_s_A = per_symbol_ci(df_sell[["stock_code", "ret"]],
                            direction=-1, fee=FEE_ROUND_TRIP) if len(df_sell) else {"__summary": {}}
    per_q_B = per_quarter_t(df_buy[["entry_date", "ret"]],
                            direction=+1, fee=FEE_ROUND_TRIP) if len(df_buy) else {"__summary": {}}
    per_s_B = per_symbol_ci(df_buy[["stock_code", "ret"]],
                            direction=+1, fee=FEE_ROUND_TRIP) if len(df_buy) else {"__summary": {}}

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

    four_dim_A = life_changing_4dim(df_sell, hold_days, direction=-1, fee=FEE_ROUND_TRIP) \
        if len(df_sell) else {"n_trades": 0, "pass_4dim_life_changing": False}
    four_dim_B = life_changing_4dim(df_buy, hold_days, direction=+1, fee=FEE_ROUND_TRIP) \
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
        "B_baseline_short": b_baseline_short,
        "B_baseline_long": b_baseline_long,
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
    log.info("=== R-1 PoC: paradigm 107 %s ===", PARADIGM_NAME)

    events_ret = build_extended_events_with_returns()
    if events_ret.empty:
        out = {"verdict": "SAMPLE_INSUFFICIENT_OHLCV", "n_events_with_returns": 0}
        OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        log.info("HALT: no events with returns")
        return 0

    log.info("events with returns: %d (across %d symbols)",
             len(events_ret), events_ret["stock_code"].nunique())

    abs_arr = events_ret["stkrt_irds_sum"].abs().values
    distrib = {
        "p50": float(np.percentile(abs_arr, 50)),
        "p70": float(np.percentile(abs_arr, 70)),
        "p75": float(np.percentile(abs_arr, 75)),
        "p80": float(np.percentile(abs_arr, 80)),
        "p85": float(np.percentile(abs_arr, 85)),
        "p90": float(np.percentile(abs_arr, 90)),
        "p95": float(np.percentile(abs_arr, 95)),
        "p99": float(np.percentile(abs_arr, 99)),
        "max": float(abs_arr.max()),
    }
    log.info("|stkrt_irds_sum| dist: p50=%.2f%% p75=%.2f%% p90=%.2f%% p99=%.2f%%",
             distrib["p50"], distrib["p75"], distrib["p90"], distrib["p99"])

    # Sample-density per quadrant per quarter at primary thr (Lesson #11 / #23)
    df_primary_sell = events_ret[events_ret["stkrt_irds_sum"] <= -THRESHOLD_FOCUS]
    df_primary_buy = events_ret[events_ret["stkrt_irds_sum"] >= +THRESHOLD_FOCUS]
    sample_density = {
        "threshold_pct": THRESHOLD_FOCUS,
        "n_sell_at_thr": int(len(df_primary_sell)),
        "n_buy_at_thr": int(len(df_primary_buy)),
        "per_quarter_sell": {},
        "per_quarter_buy": {},
    }
    for df_x, key in [(df_primary_sell, "per_quarter_sell"),
                      (df_primary_buy, "per_quarter_buy")]:
        if len(df_x):
            q = df_x["entry_date"].dt.year.astype(str) + "Q" + (
                (df_x["entry_date"].dt.month - 1) // 3 + 1).astype(str)
            sample_density[key] = q.value_counts().to_dict()

    # Run threshold × hold matrix
    all_results = {}
    for thr in THRESHOLD_SWEEP:
        for h in HOLDS:
            key = f"thr_{thr:.1f}_hold_{h}d"
            log.info(">>> threshold=%.2f%% hold=%dd", thr, h)
            all_results[key] = run_one_hold_threshold(events_ret, h, thr)

    # ----- Verdict logic -----
    primary_key = f"thr_{THRESHOLD_FOCUS:.1f}_hold_{HOLD_PRIMARY}d"
    fallback_key = f"thr_{THRESHOLD_FALLBACK:.1f}_hold_{HOLD_PRIMARY}d"
    primary = all_results[primary_key]
    fallback = all_results[fallback_key]

    afoc = primary["quadrants"]["A_focus_sell_short"]
    amir = primary["quadrants"]["A_mirror_sell_long"]
    bfoc = primary["quadrants"]["B_focus_buy_long"]
    bmir = primary["quadrants"]["B_mirror_buy_short"]

    # Sample sufficiency at primary AND fallback
    sample_ok_primary = (afoc.get("n", 0) >= MIN_CELL_N
                         and bfoc.get("n", 0) >= MIN_CELL_N)
    sample_ok_fallback = (fallback["quadrants"]["A_focus_sell_short"].get("n", 0) >= MIN_CELL_N
                          and fallback["quadrants"]["B_focus_buy_long"].get("n", 0) >= MIN_CELL_N)

    verdict_meta = {}
    if not (sample_ok_primary or sample_ok_fallback):
        verdict = "SAMPLE_INSUFFICIENT"
    else:
        # Substrate Q audit using primary
        per_q_A_summary = primary["concentration_per_quarter_A"].get("__summary", {})
        per_q_B_summary = primary["concentration_per_quarter_B"].get("__summary", {})
        substrate_ok = (per_q_A_summary.get("pass_lesson_26_amendment_n_measurable_min4")
                        and per_q_B_summary.get("pass_lesson_26_amendment_n_measurable_min4"))
        if not substrate_ok:
            verdict = "SUBSTRATE_INSUFFICIENT"
        else:
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

                gross_A = abs(afoc.get("gross_mean_bp", 0))
                gross_B = abs(bfoc.get("gross_mean_bp", 0))
                fee_floor_bp = FEE_ROUND_TRIP * 10_000

                # Lesson #36 verification logic
                # CONFIRMED: A_focus (continuation SHORT) AND B_focus (continuation LONG) both 3-gate PASS
                # INVALIDATED: A_focus FAIL AND A_mirror (paradigm 106 MR direction) PASS
                # PARTIAL: A_focus PASS but B_focus FAIL (asymmetric magnitude-direction inversion)
                # MAINTAINED: A_focus marginal (sigex>=2.0 + perm_p<=0.10 BUT ci_lower<=0)
                a_marginal = (afoc.get("signal_t_excess") is not None
                              and afoc["signal_t_excess"] >= 2.0
                              and afoc.get("perm_p_one_sided_above") is not None
                              and afoc["perm_p_one_sided_above"] <= 0.10
                              and not afoc_pass)
                if afoc_pass and bfoc_pass:
                    lesson36_verdict = "CONFIRMED_SYMMETRIC"
                elif afoc_pass and not bfoc_pass:
                    lesson36_verdict = "CONFIRMED_ASYMMETRIC_SELL_ONLY"
                elif amir_pass and not afoc_pass:
                    lesson36_verdict = "INVALIDATED_PARADIGM_106_MR_DIRECTION_WON"
                elif a_marginal:
                    lesson36_verdict = "CANDIDATE_MAINTAINED_MARGINAL"
                else:
                    lesson36_verdict = "INVALIDATED_BOTH_FAIL"
                verdict_meta["lesson_36_verdict"] = lesson36_verdict

                # Decision tree
                if gross_A < fee_floor_bp and gross_B < fee_floor_bp:
                    verdict = "BROAD_FALSIFIED_FEE_FLOOR"
                elif not afoc_pass and not bfoc_pass:
                    if amir_pass or bmir_pass:
                        verdict = "BROAD_FALSIFIED_DIRECTION_INVERTED"
                    elif a_marginal:
                        # Marginal A_focus — check if any (hold × threshold) cell elsewhere passes 3-gate
                        any_a_pass_in_sweep = False
                        passing_sweep_cells = []
                        for k, r in all_results.items():
                            af = r["quadrants"].get("A_focus_sell_short", {})
                            if af.get("pass_three_gate"):
                                any_a_pass_in_sweep = True
                                passing_sweep_cells.append({
                                    "key": k,
                                    "n": af.get("n"),
                                    "gross_bp": af.get("gross_mean_bp"),
                                    "sigex": af.get("signal_t_excess"),
                                    "ci_lower_bp": af.get("ci_lower_bp"),
                                    "perm_p_one": af.get("perm_p_one_sided_above"),
                                })
                        verdict_meta["any_A_focus_pass_in_sweep"] = any_a_pass_in_sweep
                        verdict_meta["passing_sweep_cells_A_focus"] = passing_sweep_cells
                        if any_a_pass_in_sweep:
                            # Lesson #20 narrow-scope qualification check
                            # Single isolated cell pass requires (a) Concentration A pass at that cell,
                            # (b) Bonferroni-corrected p adj, (c) life-changing 4-dim PASS.
                            verdict_meta["lesson_20_4cond_evaluation"] = "deferred_review"
                            verdict = "NARROW_SCOPE_CANDIDATE_ASYMMETRIC_HOLD_SWEEP"
                        else:
                            verdict = "BROAD_FALSIFIED"
                    else:
                        verdict = "BROAD_FALSIFIED"
                elif afoc_pass and bfoc_pass and cgate_A and cgate_B and four_dim_A_pass and four_dim_B_pass:
                    verdict = "PASS_R1_FULL"
                elif (afoc_pass and not bfoc_pass) or (bfoc_pass and not afoc_pass):
                    if four_dim_A_pass or four_dim_B_pass:
                        verdict = "NARROW_SCOPE_CANDIDATE_ASYMMETRIC"
                    else:
                        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
                elif afoc_pass and bfoc_pass and not (cgate_A and cgate_B):
                    verdict = "CONCENTRATION_FAIL"
                elif afoc_pass and bfoc_pass and not (four_dim_A_pass and four_dim_B_pass):
                    verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
                else:
                    verdict = "BROAD_FALSIFIED"

    # Cross-paradigm comparison: paradigm 106 evidence vs paradigm 107
    cross_paradigm_106_v_107 = {
        "paradigm_106_inverted_cell_thr_3p0_hold_5d": {
            "A_mirror_sell_short_sigex": 2.92,
            "A_mirror_sell_short_perm_p": 0.003,
            "A_mirror_sell_short_gross_bp": 166.65,
            "A_mirror_sell_short_ci_lower_bp": -58.77,
            "B_mirror_buy_long_sigex": 0.44,
            "B_mirror_buy_long_gross_bp": 145.98,
            "B_mirror_buy_long_ci_lower_bp": -51.30,
            "interpretation": (
                "Asymmetric inverted finding: SELL→SHORT continuation strong, "
                "BUY→LONG continuation weak. ci_lower<0 blocked 3-gate."
            ),
        },
        "paradigm_107_primary_cell_thr_2p5_hold_5d": {
            "A_focus_sell_short_sigex": afoc.get("signal_t_excess"),
            "A_focus_sell_short_perm_p": afoc.get("perm_p_one_sided_above"),
            "A_focus_sell_short_gross_bp": afoc.get("gross_mean_bp"),
            "A_focus_sell_short_ci_lower_bp": afoc.get("ci_lower_bp"),
            "B_focus_buy_long_sigex": bfoc.get("signal_t_excess"),
            "B_focus_buy_long_gross_bp": bfoc.get("gross_mean_bp"),
            "B_focus_buy_long_ci_lower_bp": bfoc.get("ci_lower_bp"),
        },
        "paradigm_107_fallback_cell_thr_3p0_hold_5d": {
            "A_focus_sell_short_sigex": fallback["quadrants"]["A_focus_sell_short"].get("signal_t_excess"),
            "A_focus_sell_short_gross_bp": fallback["quadrants"]["A_focus_sell_short"].get("gross_mean_bp"),
            "A_focus_sell_short_ci_lower_bp": fallback["quadrants"]["A_focus_sell_short"].get("ci_lower_bp"),
            "A_focus_sell_short_perm_p": fallback["quadrants"]["A_focus_sell_short"].get("perm_p_one_sided_above"),
            "A_focus_sell_short_pass_three_gate": fallback["quadrants"]["A_focus_sell_short"].get("pass_three_gate"),
        },
    }

    # Lesson #35 fail mode classification (only if FAIL)
    fail_mode = None
    if verdict.startswith("BROAD_FALSIFIED") or verdict.startswith("NARROW_SCOPE"):
        gross_A_abs = abs(afoc.get("gross_mean_bp", 0))
        gross_B_abs = abs(bfoc.get("gross_mean_bp", 0))
        fee_bp = FEE_ROUND_TRIP * 10_000
        if gross_A_abs < fee_bp and gross_B_abs < fee_bp:
            fail_mode = "FEE_TRAP"
        else:
            # gross > fee but perm/ci fail → check perm_p
            perm_a = afoc.get("perm_p_one_sided_above")
            perm_b = bfoc.get("perm_p_one_sided_above")
            if (perm_a is not None and perm_a > 0.2) or (perm_b is not None and perm_b > 0.2):
                fail_mode = "POOL_DRIFT"
            elif (afoc.get("ci_lower_bp") is not None and afoc["ci_lower_bp"] <= 0
                  and afoc.get("signal_t_excess", 0) is not None
                  and (afoc.get("signal_t_excess") or 0) >= 2.0):
                fail_mode = "CI_LOWER_NEGATIVE_HIGH_VARIANCE"
            else:
                fail_mode = "MIXED"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "phase": "R-1",
        "verdict": verdict,
        "verdict_meta": verdict_meta,
        "lesson_36_verdict": verdict_meta.get("lesson_36_verdict"),
        "fail_mode_lesson_35": fail_mode,
        "primary_threshold_pct": THRESHOLD_FOCUS,
        "fallback_threshold_pct": THRESHOLD_FALLBACK,
        "primary_hold_days": HOLD_PRIMARY,
        "n_events_total": int(len(events_ret)),
        "n_distinct_stocks": int(events_ret["stock_code"].nunique()),
        "window_kst": (f"{events_ret['entry_date'].min().date()} .. "
                       f"{events_ret['entry_date'].max().date()} (~24mo DART Form 5)"),
        "substrate_note": (
            "Paradigm 106 events_with_returns.joblib REUSED + extended fwd_ret "
            "(D+3/D+10/D+20) computed from OHLCV cache. DART majorstock.json "
            "주식등의대량보유상황보고서 (Form 5, 5%+ stake change) signed sum across co-reporters."
        ),
        "__novelty_exception_note": (
            "1/5 NOVEL axis (Mechanism only: magnitude-dependent direction inversion). "
            "Skill-spec borderline (≥2/5). Justification: paradigm 107 is direct Lesson #36 "
            "candidate verification, with Mechanism dimension itself being a NEW mechanism class "
            "(magnitude-direction interaction). Single-axis NOVEL accepted as Lesson #36 dogfood vehicle."
        ),
        "stkrt_irds_distribution_lesson_34": distrib,
        "sample_density_lesson_11": sample_density,
        "cross_paradigm_106_vs_107": cross_paradigm_106_v_107,
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
            "threshold_fallback_pct": THRESHOLD_FALLBACK,
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
    log.info("LESSON_36: %s", verdict_meta.get("lesson_36_verdict"))
    log.info("FAIL_MODE: %s", fail_mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
