"""R-1 PoC for paradigm 102 candidate
`dart_supply_contract_announce_kr_equity_vol_expansion_5d`.

Hypothesis
----------
KR equity 단일판매·공급계약체결 공시 = market attention information shock →
post-event 5d realized volatility EXPANSION magnitude. Direction-blind
(magnitude-only) univariate paradigm: long-straddle / abs-return payoff.

Distinct from paradigm 101 (directional LONG, BROAD_FALSIFIED_UNIVERSE_DRIFT
ARTIFACT) — measures `vol_post_5d / vol_pre_30d` ratio + straddle-payoff
`|fwd_ret_5d|`.

Family-distinct path
--------------------
KR equity DART entry-side family retire 4 graveyards (paradigm 92+93+100+101)
all directional / mean-reversion / immediate-demand directional axis.
Direction-blind volatility magnitude axis = family-distinct
(feedback_family_retire_kr_post_earnings §"비-directional volatility event
paradigm" first row, 2026-05-19 amendment).

4-quadrant Symmetric Negative Test (Lesson #19 obligatory)
-----------------------------------------------------------
- A focus  : announce × vol_ratio ≥ 1.5   ("expansion happened")
- A mirror : announce × vol_ratio < 1.0    ("contraction happened")
- B base+  : non_announce × vol_ratio ≥ 1.5 (universe baseline expansion rate)
- B base−  : non_announce × vol_ratio < 1.0

Outcome metric per cell: straddle_payoff_bp = mean(|fwd_ret_5d|) × 10000 − 2×fee
(straddle = long put + long call, abs payoff, 2× round-trip fee at 50bp each leg
delta-neutral assumption).

A focus straddle payoff must be POSITIVE and exceed B baseline + (A mirror, B base−).

Lesson #32 candidate dogfood (paradigm 101 → 102 2nd dogfood)
-------------------------------------------------------------
Universe baseline coherence check: compare A focus mean(vol_ratio) vs B baseline
mean(vol_ratio). signal_t_excess on |fwd_ret_5d| must be ≥ 2.0 AND
A_focus_vol_ratio > B_baseline_vol_ratio (universe-incremental excess vol).

Cross-proxy strict (Lesson #29 obligatory)
-------------------------------------------
- Observable proxy: |open_gap| (entry_open/prior_close - 1, absolute value)
  → sentiment / surprise magnitude. Top-quartile vs bottom-quartile.
- Fundamental proxy: contract_freq_6m (per-symbol 6m rolling announcement
  count). Top-quartile (frequent announcer = noise contracts, less info) vs
  bottom-quartile (infrequent = high-info contracts).
- Hypothesis: |gap| top33 ≥ bot33 (surprise magnitude → larger vol expansion);
  freq bot33 ≥ top33 (rare contract = larger info-shock → larger vol expansion).

Concentration Gate (Lesson #16 + #26 amendment)
------------------------------------------------
- Per-stock straddle-payoff bootstrap CI (>=30% ci_pos AND >=3 syms ci_pos)
- Per-quarter straddle-payoff t-stat (>=50% quarters t>0)
- Per-symbol fraction <=10% (no single stock dominates focus n)

4-dim life-changing (obligatory)
---------------------------------
Straddle interpretation (long both directions):
  per_trade_edge_net = mean(|fwd_ret_5d|) - 2×fee
  trades/yr = events/yr (each announcement = 1 straddle entry)
  sharpe = annualized using per-trade abs payoff
  capital_util ≈ events × 5d / 250 trading days (rough overlap heuristic)

Verdict decision tree (R-1 ONLY — R-2 dispatch requires explicit user gate)
----------------------------------------------------------------------------
1. SAMPLE_INSUFFICIENT (any per-cell n < 30, esp. focus A) → halt
2. BROAD_FALSIFIED (A focus straddle three-gate FAIL) → graveyard
3. BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT (A_vol_ratio ≤ B_baseline_vol_ratio
   despite payoff ≥ 0, Lesson #32 dogfood failure)
4. CONCENTRATION_FAIL → halt
5. SINGLE_PROXY_TRAP_OBS_ONLY / SINGLE_PROXY_TRAP_FUND_ONLY (Lesson #29)
6. NARROW_SCOPE_LIFE_CHANGING_FAIL (3-gate PASS but 4-dim FAIL, Lesson #20)
7. NARROW_SCOPE_CANDIDATE (Lesson #20 4-cond all PASS + 4-dim PASS)
8. PASS_R1_CROSS_PROXY_PROMOTE_R2 (3-gate + Concentration + 4-dim + cross-proxy)
9. PASS_R1_FULL (above across primary 5d hold + robust threshold 1.5)

Output: backend/runs/research_track/
        dart_supply_contract_announce_kr_equity_vol_expansion_5d/r1_metrics.json
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
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

from scripts.research._perm_utils import (  # noqa: E402
    fee_aware_perm_test,
    bootstrap_ci,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vol_exp_r1")

OUT_DIR = (
    BACKEND_ROOT
    / "runs"
    / "research_track"
    / "dart_supply_contract_announce_kr_equity_vol_expansion_5d"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1_metrics.json"
EVENTS_CACHE_PATH = OUT_DIR / "vol_expansion_events_cache.joblib"

OHLCV_DIR = BACKEND_ROOT / "runs" / "dart_track" / "ohlcv_cache"
UNIVERSE_PATH = BACKEND_ROOT / "runs" / "dart_track" / "universe_kospi200_kosdaq150.joblib"
P101_DIR = (
    BACKEND_ROOT
    / "runs"
    / "research_track"
    / "dart_supply_contract_announce_kr_equity_long_5d"
)
R0_EVENTS_PATH = P101_DIR / "r0_matched_events_raw.json"

# --- Config ---
PRIMARY_HOLD = 5  # 5 trading days post-event for vol_post measurement
PRE_WINDOW = 30  # 30 trading days for vol_pre baseline
FEE_LEG_BP = 50   # 50bp round-trip per leg
STRADDLE_FEE_BP = 2 * FEE_LEG_BP  # 100bp (long put + long call, each 50bp round-trip)
STRESS_FEE_BP = 200  # 200bp stress (each leg 100bp)
MIN_CELL_N = 30
MAX_SYMBOL_FRACTION = 0.10
NEEDLE_CORE = "공급계약체결"
EXCLUDE_TERMS = ("해지", "자회사", "거래정지")
N_PERMS = 1000
N_BOOTSTRAP = 2000
VOL_EXPANSION_THRESHOLD = 1.5    # A focus: vol_ratio >= 1.5
VOL_CONTRACTION_THRESHOLD = 1.0  # A mirror: vol_ratio < 1.0


# ---------------- data prep ----------------

def load_universe() -> set[str]:
    u = joblib.load(UNIVERSE_PATH)
    return set(u["itemCode"].astype(str).str.zfill(6).tolist())


def load_ohlcv(stock_code: str) -> pd.DataFrame:
    p = OHLCV_DIR / f"{stock_code}.joblib"
    if not p.exists():
        return pd.DataFrame()
    df = joblib.load(p)
    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _realized_vol(closes: np.ndarray) -> float:
    """Std of log-returns of the given close-price array."""
    if len(closes) < 2:
        return float("nan")
    lr = np.diff(np.log(np.clip(closes, 1e-9, None)))
    if len(lr) < 2:
        return float("nan")
    return float(np.std(lr, ddof=1))


def build_events_cache(universe: set[str]) -> pd.DataFrame:
    """Build events cache with vol_pre/post and straddle-payoff per event.

    Schema:
      rcept_dt, rcept_no, stock_code, corp_name, report_nm,
      entry_date, prior_close, entry_open, gap, abs_gap, freq_6m,
      vol_pre_30d, vol_post_5d, vol_ratio,
      fwd_ret_5d_gross, abs_fwd_ret_5d, intraday_range_5d
    """
    if EVENTS_CACHE_PATH.exists():
        log.info("loading existing vol_expansion events cache from %s", EVENTS_CACHE_PATH)
        return joblib.load(EVENTS_CACHE_PATH)

    raw = json.loads(R0_EVENTS_PATH.read_text())
    log.info("R-0 raw matched events: %d", len(raw))

    # focus mechanism filter
    filt = []
    for ev in raw:
        nm = ev["report_nm"]
        if NEEDLE_CORE not in nm:
            continue
        if any(t in nm for t in EXCLUDE_TERMS):
            continue
        filt.append(ev)
    log.info("after focus filter: %d", len(filt))

    df = pd.DataFrame(filt)
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    df = df[df["stock_code"].isin(universe)].reset_index(drop=True)
    log.info("after universe filter: %d", len(df))

    # per-symbol freq_6m rolling count
    df = df.sort_values(["stock_code", "rcept_dt"]).reset_index(drop=True)
    freq_vals: list[int] = []
    for code, grp in df.groupby("stock_code"):
        dts = grp["rcept_dt"].values
        for d in dts:
            d_ts = pd.Timestamp(d)
            mask = (grp["rcept_dt"] >= d_ts - pd.Timedelta(days=180)) & (
                grp["rcept_dt"] < d_ts
            )
            freq_vals.append(int(mask.sum()))
    df["freq_6m"] = freq_vals

    rows_out = []
    skipped = 0
    by_code = df.groupby("stock_code")
    log.info("computing vol_pre/post + straddle payoff across %d symbols", len(by_code))
    for idx_code, (code, grp) in enumerate(by_code, 1):
        ohlcv = load_ohlcv(code)
        if ohlcv.empty:
            skipped += len(grp)
            continue
        ohlcv = ohlcv.set_index("date").sort_index()
        dates_arr = ohlcv.index.values
        closes_arr = ohlcv["close"].values.astype(float)
        opens_arr = ohlcv["open"].values.astype(float)
        highs_arr = ohlcv["high"].values.astype(float)
        lows_arr = ohlcv["low"].values.astype(float)
        for _, ev in grp.iterrows():
            ev_dt = ev["rcept_dt"].to_datetime64()
            pos = int(np.searchsorted(dates_arr, ev_dt, side="right"))
            # need PRE_WINDOW bars before, PRIMARY_HOLD bars after entry
            if pos < PRE_WINDOW + 1:
                skipped += 1
                continue
            if pos + PRIMARY_HOLD >= len(ohlcv):
                skipped += 1
                continue
            prior_close = closes_arr[pos - 1]
            entry_open = opens_arr[pos]
            if not (prior_close > 0 and entry_open > 0):
                skipped += 1
                continue
            # vol_pre: closes from pos-PRE_WINDOW-1 .. pos-1  (PRE_WINDOW returns)
            pre_closes = closes_arr[pos - PRE_WINDOW - 1 : pos]
            vol_pre = _realized_vol(pre_closes)
            # vol_post: closes from pos .. pos+PRIMARY_HOLD-1  (PRIMARY_HOLD-1 returns)
            # use entry_open as anchor: combine entry_open + closes[pos..pos+PRIMARY_HOLD-1]
            post_arr = np.concatenate(([entry_open], closes_arr[pos : pos + PRIMARY_HOLD]))
            vol_post = _realized_vol(post_arr)
            if not (np.isfinite(vol_pre) and np.isfinite(vol_post)) or vol_pre <= 0:
                skipped += 1
                continue
            vol_ratio = vol_post / vol_pre
            exit_close = closes_arr[pos + PRIMARY_HOLD - 1]
            if exit_close <= 0:
                skipped += 1
                continue
            fwd_ret = exit_close / entry_open - 1.0
            # intraday range avg over hold window
            ranges = []
            for k in range(PRIMARY_HOLD):
                h = highs_arr[pos + k]
                lw = lows_arr[pos + k]
                c = closes_arr[pos + k]
                if c > 0:
                    ranges.append((h - lw) / c)
            intraday_range = float(np.mean(ranges)) if ranges else float("nan")
            rows_out.append({
                "rcept_dt": ev["rcept_dt"],
                "rcept_no": str(ev["rcept_no"]),
                "stock_code": code,
                "corp_name": str(ev["corp_name"]),
                "entry_date": ohlcv.index[pos],
                "prior_close": prior_close,
                "entry_open": entry_open,
                "gap": entry_open / prior_close - 1.0,
                "abs_gap": abs(entry_open / prior_close - 1.0),
                "freq_6m": int(ev["freq_6m"]),
                "vol_pre_30d": vol_pre,
                "vol_post_5d": vol_post,
                "vol_ratio": vol_ratio,
                "fwd_ret_5d_gross": fwd_ret,
                "abs_fwd_ret_5d": abs(fwd_ret),
                "intraday_range_5d": intraday_range,
            })
        if idx_code % 25 == 0:
            log.info("  ...%d/%d syms, kept=%d skipped=%d",
                     idx_code, len(by_code), len(rows_out), skipped)

    events_ret = pd.DataFrame(rows_out)
    log.info("events with vol features: kept=%d skipped=%d", len(events_ret), skipped)
    joblib.dump(events_ret, EVENTS_CACHE_PATH)
    log.info("wrote %s", EVENTS_CACHE_PATH)
    return events_ret


def candidate_pool(events_ret: pd.DataFrame, sample_n: int = 30000,
                   rng_seed: int = 42) -> pd.DataFrame:
    """Random non-trigger entry pool across universe-with-events for B baseline.

    Returns DataFrame with columns: stock_code, entry_date, vol_pre_30d, vol_post_5d,
    vol_ratio, fwd_ret_5d_gross, abs_fwd_ret_5d. Excludes actual trigger dates.
    """
    rng = np.random.default_rng(rng_seed)
    codes = events_ret["stock_code"].unique()
    per_code = max(2, sample_n // max(1, len(codes)))
    rows: list[dict] = []
    trig_per_sym = events_ret.groupby("stock_code")["entry_date"].apply(set).to_dict()

    for code in codes:
        ohlcv = load_ohlcv(code)
        if ohlcv.empty or len(ohlcv) < PRE_WINDOW + PRIMARY_HOLD + 2:
            continue
        ohlcv = ohlcv.set_index("date").sort_index()
        closes_arr = ohlcv["close"].values.astype(float)
        opens_arr = ohlcv["open"].values.astype(float)
        trig_set = trig_per_sym.get(code, set())
        valid_low = PRE_WINDOW + 1
        valid_high = len(ohlcv) - PRIMARY_HOLD
        all_valid = np.arange(valid_low, valid_high)
        # filter out actual trigger positions
        date_arr = ohlcv.index.values
        keep_mask = np.array(
            [pd.Timestamp(date_arr[i]) not in trig_set for i in all_valid]
        )
        all_valid = all_valid[keep_mask]
        if len(all_valid) == 0:
            continue
        pick = rng.choice(
            all_valid, size=min(per_code, len(all_valid)), replace=False
        )
        for pos in pick:
            prior_close = closes_arr[pos - 1]
            entry_open = opens_arr[pos]
            if not (prior_close > 0 and entry_open > 0):
                continue
            pre_closes = closes_arr[pos - PRE_WINDOW - 1 : pos]
            vol_pre = _realized_vol(pre_closes)
            post_arr = np.concatenate(([entry_open], closes_arr[pos : pos + PRIMARY_HOLD]))
            vol_post = _realized_vol(post_arr)
            if not (np.isfinite(vol_pre) and np.isfinite(vol_post)) or vol_pre <= 0:
                continue
            exit_close = closes_arr[pos + PRIMARY_HOLD - 1]
            if exit_close <= 0:
                continue
            fwd_ret = exit_close / entry_open - 1.0
            rows.append({
                "stock_code": code,
                "entry_date": pd.Timestamp(date_arr[pos]),
                "vol_pre_30d": vol_pre,
                "vol_post_5d": vol_post,
                "vol_ratio": vol_post / vol_pre,
                "fwd_ret_5d_gross": fwd_ret,
                "abs_fwd_ret_5d": abs(fwd_ret),
            })
    return pd.DataFrame(rows)


# ---------------- cell-level statistics ----------------

def cell_stats_straddle(df_cell: pd.DataFrame, pool_abs_returns: np.ndarray,
                        fee_bp: int, label: str,
                        by_symbol_count: dict[str, int] | None = None,
                        total_trades: int = 0) -> dict:
    """Straddle-payoff cell stats (direction-blind: abs return - 2-leg fee).

    Three-gate uses one-sided perm test (above) since hypothesis is positive
    expansion payoff.
    """
    n = len(df_cell)
    if n == 0:
        return {"label": label, "n": 0, "pass_n": False}
    abs_returns = df_cell["abs_fwd_ret_5d"].values
    fee = fee_bp / 10_000
    net = abs_returns - fee
    if n >= 2 and net.std(ddof=1) > 0:
        t_obs = float(net.mean() / net.std(ddof=1) * np.sqrt(n))
    else:
        t_obs = 0.0
    out = {
        "label": label,
        "n": int(n),
        "fee_round_trip_bp": int(fee_bp),
        "gross_mean_abs_bp": float(abs_returns.mean() * 10_000),
        "net_mean_bp": float(net.mean() * 10_000),
        "t_obs": t_obs,
        "pass_n": n >= MIN_CELL_N,
        "mean_vol_ratio": float(df_cell["vol_ratio"].mean()),
        "median_vol_ratio": float(df_cell["vol_ratio"].median()),
    }
    if by_symbol_count is not None and total_trades:
        top_sym, top_n = max(by_symbol_count.items(), key=lambda kv: kv[1])
        out["concentration_top_sym"] = top_sym
        out["concentration_top_frac"] = float(top_n / total_trades)
        out["pass_concentration_symbol"] = (top_n / total_trades) <= MAX_SYMBOL_FRACTION

    observed_net = net.tolist()
    pool_net_pool = pool_abs_returns - fee  # apply same fee to pool abs returns
    perm = fee_aware_perm_test(
        observed_net_returns=observed_net,
        candidate_pool_returns=pool_abs_returns.tolist(),  # gross; helper applies fee
        fee_per_trade=fee,
        n_perms=N_PERMS,
    )
    boot = bootstrap_ci(observed_net, n_boot=N_BOOTSTRAP, block_size=1)
    out.update({
        "signal_t_excess": perm.get("signal_t_excess"),
        "null_mean_t": perm.get("null_mean_t"),
        "perm_p_two_sided": perm.get("perm_p_two_sided"),
        "perm_p_one_sided_above": perm.get("perm_p_one_sided_above"),
        "ci_lower_bp": (
            float(boot["ci_lower"] * 10_000) if boot.get("ci_lower") is not None
            else None
        ),
        "ci_upper_bp": (
            float(boot["ci_upper"] * 10_000) if boot.get("ci_upper") is not None
            else None
        ),
        "prob_positive": boot.get("prob_positive"),
    })
    sig_ex = out.get("signal_t_excess")
    ci_l = out.get("ci_lower_bp")
    p_above = out.get("perm_p_one_sided_above")
    passes_three_gate = bool(
        out["pass_n"]
        and sig_ex is not None
        and isinstance(sig_ex, (int, float)) and not (isinstance(sig_ex, float) and math.isnan(sig_ex))
        and sig_ex >= 2.0
        and ci_l is not None and ci_l > 0
        and p_above is not None and p_above <= 0.10
    )
    out["pass_three_gate"] = passes_three_gate
    return out


def per_quarter_t(df_cell: pd.DataFrame, fee_bp: int) -> dict:
    """Per-quarter straddle-payoff t-stat for Concentration Gate."""
    fee = fee_bp / 10_000
    df = df_cell.copy()
    df["q"] = df["entry_date"].dt.year.astype(str) + "Q" + (
        (df["entry_date"].dt.month - 1) // 3 + 1).astype(str)
    out: dict = {}
    n_pos_t = 0
    n_measurable = 0
    for q, g in df.groupby("q"):
        net = g["abs_fwd_ret_5d"].values - fee
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
        "pass_n_measurable_min4": n_measurable >= 4,
        "pass_quarter_pos_t_ratio_min_0p5": (
            (n_pos_t / n_measurable) >= 0.5 if n_measurable else False
        ),
    }
    return out


def per_symbol_ci(df_cell: pd.DataFrame, fee_bp: int) -> dict:
    """Per-symbol bootstrap CI on straddle payoff."""
    fee = fee_bp / 10_000
    n_ci_pos = 0
    n_measurable = 0
    out: dict = {}
    for sym, g in df_cell.groupby("stock_code"):
        net = (g["abs_fwd_ret_5d"].values - fee).tolist()
        if len(net) < 8:
            continue
        boot = bootstrap_ci(net, n_boot=500, block_size=1)
        ci_l = boot.get("ci_lower")
        out[sym] = {
            "n": int(len(g)),
            "ci_lower_bp": float(ci_l * 10_000) if ci_l is not None else None,
            "ci_pos": ci_l is not None and ci_l > 0,
        }
        n_measurable += 1
        if ci_l is not None and ci_l > 0:
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


def life_changing_4dim_straddle(df_focus: pd.DataFrame, fee_bp: int) -> dict:
    """4-dim life-changing applied to straddle payoff (direction-blind).

    per_trade_edge = mean(|fwd_ret_5d|) - 2*fee (straddle pair fee already in fee_bp)
    """
    fee = fee_bp / 10_000
    df = df_focus.copy()
    df["net_payoff"] = df["abs_fwd_ret_5d"] - fee
    n_trades = len(df)
    window_days = (df["entry_date"].max() - df["entry_date"].min()).days
    years = max(window_days / 365.25, 1e-9)
    trades_per_yr = n_trades / years
    edge_net = float(df["net_payoff"].mean())
    if n_trades >= 2 and df["net_payoff"].std(ddof=1) > 0:
        sharpe = float(edge_net / df["net_payoff"].std(ddof=1) * math.sqrt(trades_per_yr))
    else:
        sharpe = 0.0
    days_with_open = set()
    for _, ev in df.iterrows():
        ed = ev["entry_date"]
        for k in range(PRIMARY_HOLD):
            days_with_open.add(ed + pd.Timedelta(days=k))
    util_calendar = len(days_with_open) / max(window_days, 1)
    return {
        "n_trades": int(n_trades),
        "window_days": int(window_days),
        "trades_per_yr": float(trades_per_yr),
        "per_trade_edge_net_pct": float(edge_net * 100),
        "annualized_sharpe": float(sharpe),
        "util_calendar": float(util_calendar),
        "pass_trades_per_yr_min12": trades_per_yr >= 12,
        "pass_per_trade_edge_min_2pct": edge_net >= 0.02,
        "pass_capital_util_min_30pct": util_calendar >= 0.30,
        "pass_sharpe_min_1p5": sharpe >= 1.5,
        "pass_4dim_life_changing": (
            trades_per_yr >= 12
            and edge_net >= 0.02
            and util_calendar >= 0.30
            and sharpe >= 1.5
        ),
    }


# ---------------- main pipeline ----------------

def run() -> dict:
    universe = load_universe()
    log.info("universe size: %d", len(universe))
    events_ret = build_events_cache(universe)
    log.info("events_ret: %d events / %d distinct stocks",
             len(events_ret), events_ret["stock_code"].nunique())

    log.info("building B baseline candidate pool ...")
    pool_df = candidate_pool(events_ret)
    log.info("pool size: %d", len(pool_df))

    # ---- 4-quadrant split by vol_ratio ----
    A_focus = events_ret[events_ret["vol_ratio"] >= VOL_EXPANSION_THRESHOLD].copy()
    A_mirror = events_ret[events_ret["vol_ratio"] < VOL_CONTRACTION_THRESHOLD].copy()
    B_focus = pool_df[pool_df["vol_ratio"] >= VOL_EXPANSION_THRESHOLD].copy()
    B_mirror = pool_df[pool_df["vol_ratio"] < VOL_CONTRACTION_THRESHOLD].copy()
    log.info("4-quadrant: A_focus=%d  A_mirror=%d  B_focus=%d  B_mirror=%d",
             len(A_focus), len(A_mirror), len(B_focus), len(B_mirror))

    pool_abs = pool_df["abs_fwd_ret_5d"].values

    # ---- cells ----
    sym_counts_A_focus = A_focus["stock_code"].value_counts().to_dict()
    cells = {
        "A_focus": cell_stats_straddle(
            A_focus, pool_abs, STRADDLE_FEE_BP, "announce × vol_ratio>=1.5",
            by_symbol_count=sym_counts_A_focus, total_trades=len(A_focus),
        ),
        "A_mirror": cell_stats_straddle(
            A_mirror, pool_abs, STRADDLE_FEE_BP, "announce × vol_ratio<1.0",
        ),
        "B_baseline_expand": cell_stats_straddle(
            B_focus, pool_abs, STRADDLE_FEE_BP, "non_announce × vol_ratio>=1.5",
        ),
        "B_baseline_contract": cell_stats_straddle(
            B_mirror, pool_abs, STRADDLE_FEE_BP, "non_announce × vol_ratio<1.0",
        ),
        "A_focus_stress200bp": cell_stats_straddle(
            A_focus, pool_abs, STRESS_FEE_BP, "announce × vol_ratio>=1.5 @ 200bp",
            by_symbol_count=sym_counts_A_focus, total_trades=len(A_focus),
        ),
    }

    # ---- Lesson #32 candidate dogfood: universe-baseline coherence ----
    A_focus_vol_ratio = float(A_focus["vol_ratio"].mean()) if len(A_focus) else None
    B_baseline_vol_ratio_all = float(pool_df["vol_ratio"].mean()) if len(pool_df) else None
    lesson_32 = {
        "A_focus_mean_vol_ratio": A_focus_vol_ratio,
        "B_baseline_all_mean_vol_ratio": B_baseline_vol_ratio_all,
        "A_minus_B_vol_ratio_excess": (
            (A_focus_vol_ratio - B_baseline_vol_ratio_all)
            if (A_focus_vol_ratio is not None and B_baseline_vol_ratio_all is not None)
            else None
        ),
        "pass_universe_baseline_coherent_min_excess_0p05": (
            (A_focus_vol_ratio - B_baseline_vol_ratio_all) >= 0.05
            if (A_focus_vol_ratio is not None and B_baseline_vol_ratio_all is not None)
            else False
        ),
        "note": (
            "Lesson #32 dogfood: A focus vol_ratio must exceed B baseline universe "
            "vol_ratio to claim event-driven volatility excess (not universe drift "
            "artifact). Threshold 0.05 conservative (5% relative excess in vol ratio)."
        ),
    }

    # ---- Concentration Gate on A_focus ----
    concentration = {
        "per_quarter_straddle_t": per_quarter_t(A_focus, STRADDLE_FEE_BP),
        "per_symbol_straddle_ci": per_symbol_ci(A_focus, STRADDLE_FEE_BP),
    }
    pq = concentration["per_quarter_straddle_t"]["__summary"]
    ps = concentration["per_symbol_straddle_ci"]["__summary"]
    concentration["pass_concentration_gate"] = bool(
        pq.get("pass_n_measurable_min4")
        and pq.get("pass_quarter_pos_t_ratio_min_0p5")
        and ps.get("pass_symbol_ci_pos_ratio_min_0p30")
        and ps.get("pass_n_symbols_ci_pos_min_3")
    )

    # ---- Cross-proxy (Lesson #29) on A_focus only ----
    cross_proxy = {}
    if len(A_focus) > 0:
        gap_qs = A_focus["abs_gap"].quantile([0.33, 0.67]).values
        gap_top = A_focus[A_focus["abs_gap"] >= gap_qs[1]]
        gap_bot = A_focus[A_focus["abs_gap"] <= gap_qs[0]]
        freq_qs = A_focus["freq_6m"].quantile([0.33, 0.67]).values
        freq_top = A_focus[A_focus["freq_6m"] >= freq_qs[1]]
        freq_bot = A_focus[A_focus["freq_6m"] <= freq_qs[0]]

        cross_proxy = {
            "observable_gap_split": {
                "top33_n": len(gap_top), "bot33_n": len(gap_bot),
                "top33_payoff": cell_stats_straddle(
                    gap_top, pool_abs, STRADDLE_FEE_BP, "gap_top33"
                ) if len(gap_top) else {"n": 0},
                "bot33_payoff": cell_stats_straddle(
                    gap_bot, pool_abs, STRADDLE_FEE_BP, "gap_bot33"
                ) if len(gap_bot) else {"n": 0},
            },
            "fundamental_freq_split": {
                "top33_n": len(freq_top), "bot33_n": len(freq_bot),
                "top33_payoff": cell_stats_straddle(
                    freq_top, pool_abs, STRADDLE_FEE_BP, "freq_top33"
                ) if len(freq_top) else {"n": 0},
                "bot33_payoff": cell_stats_straddle(
                    freq_bot, pool_abs, STRADDLE_FEE_BP, "freq_bot33"
                ) if len(freq_bot) else {"n": 0},
            },
        }
        # coherence:
        obs_top = cross_proxy["observable_gap_split"]["top33_payoff"].get("net_mean_bp")
        obs_bot = cross_proxy["observable_gap_split"]["bot33_payoff"].get("net_mean_bp")
        fund_top = cross_proxy["fundamental_freq_split"]["top33_payoff"].get("net_mean_bp")
        fund_bot = cross_proxy["fundamental_freq_split"]["bot33_payoff"].get("net_mean_bp")
        cross_proxy["coherence"] = {
            "obs_top_gap_ge_bot": (
                obs_top is not None and obs_bot is not None and obs_top >= obs_bot
            ),
            "fund_bot_freq_ge_top": (
                fund_top is not None and fund_bot is not None and fund_bot >= fund_top
            ),
            "obs_top_minus_bot_bp": (
                obs_top - obs_bot
                if (obs_top is not None and obs_bot is not None) else None
            ),
            "fund_bot_minus_top_bp": (
                fund_bot - fund_top
                if (fund_top is not None and fund_bot is not None) else None
            ),
        }
        cross_proxy["coherence"]["pass_both_proxies"] = bool(
            cross_proxy["coherence"]["obs_top_gap_ge_bot"]
            and cross_proxy["coherence"]["fund_bot_freq_ge_top"]
        )

    # ---- 4-dim life-changing on A_focus straddle ----
    four_dim = life_changing_4dim_straddle(A_focus, STRADDLE_FEE_BP)

    # ---- Verdict tree ----
    a_focus_cell = cells["A_focus"]
    a_focus_pass_three = a_focus_cell.get("pass_three_gate", False)
    n_a_focus = a_focus_cell.get("n", 0)

    verdict = None
    verdict_reason = None

    if n_a_focus < MIN_CELL_N:
        verdict = "SAMPLE_INSUFFICIENT"
        verdict_reason = f"A_focus n={n_a_focus} < {MIN_CELL_N}"
    elif not a_focus_pass_three:
        # check direction: if A_focus payoff negative, mirror trivially better and
        # universe drift artifact is concentration-dependent decision
        if (
            not lesson_32["pass_universe_baseline_coherent_min_excess_0p05"]
            and (a_focus_cell.get("signal_t_excess") or 0) < 2.0
        ):
            verdict = "BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT"
            verdict_reason = (
                f"A_focus vol_ratio={A_focus_vol_ratio:.3f} ≈ B_baseline "
                f"{B_baseline_vol_ratio_all:.3f} (excess "
                f"{lesson_32['A_minus_B_vol_ratio_excess']:.4f} < 0.05) AND "
                f"three-gate FAIL"
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                f"A_focus three-gate FAIL: sig_ex={a_focus_cell.get('signal_t_excess')} "
                f"ci_l_bp={a_focus_cell.get('ci_lower_bp')} "
                f"perm_p_above={a_focus_cell.get('perm_p_one_sided_above')}"
            )
    elif not concentration["pass_concentration_gate"]:
        verdict = "CONCENTRATION_FAIL"
        verdict_reason = (
            f"per_quarter_pos_t_ratio={pq.get('quarter_pos_t_ratio')} "
            f"(min 0.5, n_meas={pq.get('n_measurable')}) "
            f"OR symbol_ci_pos_ratio={ps.get('symbol_ci_pos_ratio')} "
            f"(min 0.30, n_ci_pos={ps.get('n_ci_pos')})"
        )
    elif not lesson_32["pass_universe_baseline_coherent_min_excess_0p05"]:
        verdict = "BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT"
        verdict_reason = (
            f"Lesson #32 dogfood FAIL: A_focus vol_ratio={A_focus_vol_ratio:.3f} "
            f"≈ B_baseline {B_baseline_vol_ratio_all:.3f} (excess "
            f"{lesson_32['A_minus_B_vol_ratio_excess']:.4f} < 0.05). Even though "
            f"three-gate PASS, payoff source = universe baseline vol not event-driven."
        )
    else:
        # check 4-dim and cross-proxy
        proxy_pass = cross_proxy.get("coherence", {}).get("pass_both_proxies", False)
        if not four_dim["pass_4dim_life_changing"]:
            # Lesson #20 narrow-scope qualification: need 4-cond cross-proxy PASS
            if proxy_pass:
                verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
                verdict_reason = (
                    f"3-gate PASS + Lesson #20 4-cond proxy PASS but 4-dim FAIL: "
                    f"trades/yr={four_dim['trades_per_yr']:.1f} edge="
                    f"{four_dim['per_trade_edge_net_pct']:.2f}% util="
                    f"{four_dim['util_calendar']:.3f} sharpe={four_dim['annualized_sharpe']:.2f}"
                )
            else:
                verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
                verdict_reason = (
                    f"3-gate PASS but cross-proxy FAIL (obs_coh="
                    f"{cross_proxy['coherence']['obs_top_gap_ge_bot']} fund_coh="
                    f"{cross_proxy['coherence']['fund_bot_freq_ge_top']}) AND "
                    f"4-dim FAIL"
                )
        else:
            # 4-dim PASS — check cross-proxy strict
            if not proxy_pass:
                # check which proxy failed
                obs_ok = cross_proxy["coherence"]["obs_top_gap_ge_bot"]
                fund_ok = cross_proxy["coherence"]["fund_bot_freq_ge_top"]
                if obs_ok and not fund_ok:
                    verdict = "SINGLE_PROXY_TRAP_OBS_ONLY"
                elif fund_ok and not obs_ok:
                    verdict = "SINGLE_PROXY_TRAP_FUND_ONLY"
                else:
                    verdict = "SINGLE_PROXY_TRAP_NEITHER"
                verdict_reason = (
                    f"3-gate PASS + 4-dim PASS but Lesson #29 cross-proxy FAIL: "
                    f"obs_top_ge_bot={obs_ok} fund_bot_ge_top={fund_ok}"
                )
            else:
                # check primary 5d hold three-gate at 200bp stress as robustness
                stress_pass = cells["A_focus_stress200bp"].get("pass_three_gate", False)
                if stress_pass:
                    verdict = "PASS_R1_FULL"
                    verdict_reason = (
                        "A_focus three-gate PASS @ 100bp AND @ 200bp stress + "
                        "Concentration + 4-dim + Lesson #29 cross-proxy both + "
                        "Lesson #32 universe-baseline coherent."
                    )
                else:
                    verdict = "PASS_R1_CROSS_PROXY_PROMOTE_R2"
                    verdict_reason = (
                        "A_focus three-gate PASS @ 100bp + Concentration + "
                        "4-dim + Lesson #29 cross-proxy both + Lesson #32 "
                        "universe-baseline coherent (stress 200bp FAIL)."
                    )

    output = {
        "paradigm_name": "dart_supply_contract_announce_kr_equity_vol_expansion_5d",
        "paradigm_index_proposed": 102,
        "phase": "R-1",
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "primary_hold_days": PRIMARY_HOLD,
        "pre_vol_window_days": PRE_WINDOW,
        "vol_expansion_threshold": VOL_EXPANSION_THRESHOLD,
        "vol_contraction_threshold": VOL_CONTRACTION_THRESHOLD,
        "straddle_fee_bp_baseline": STRADDLE_FEE_BP,
        "straddle_fee_bp_stress": STRESS_FEE_BP,
        "n_events_total": int(len(events_ret)),
        "n_distinct_stocks": int(events_ret["stock_code"].nunique()),
        "n_pool_total": int(len(pool_df)),
        "window_kst": "2024-01-01 .. 2026-05-19 (2.4yr full DART substrate)",
        "config": {
            "universe_size": 350,
            "needle_core": NEEDLE_CORE,
            "exclude_terms": list(EXCLUDE_TERMS),
            "min_cell_n": MIN_CELL_N,
            "max_symbol_fraction": MAX_SYMBOL_FRACTION,
            "n_perms": N_PERMS,
            "n_bootstrap": N_BOOTSTRAP,
            "fee_leg_bp": FEE_LEG_BP,
        },
        "cells_4quadrant": cells,
        "lesson_32_universe_baseline_coherence": lesson_32,
        "concentration_gate": concentration,
        "cross_proxy_lesson29": cross_proxy,
        "life_changing_4dim_straddle": four_dim,
        "lesson_grid_applied": [
            "#11 sample density (R-0 prescreen confirmed PASS at 2,421 events)",
            "#16 Concentration Gate (per-stock + per-quarter on straddle payoff)",
            "#19 Symmetric Negative Test (4-quadrant single batch)",
            "#20 narrow-scope 4-cond qualification (cross-proxy + 4-dim)",
            "#21 axis stacking (univariate vol_ratio, single-axis OK)",
            "#22 stateful change-point (5d realized vol = stateless ratio, OK)",
            "#23 event-anchored sparse trap (not boundary statistic)",
            "#26 amendment (year-round 10/10 quarters from R-0)",
            "#27 amendment (N/A — direction-blind, not entry-side directional)",
            "#28 substrate availability (paradigm 101 cache+OHLCV reused)",
            "#29 cross-proxy strict (observable abs_gap + fundamental freq_6m)",
            "#30 short-data verdict (full 2.4yr window used)",
            "#31 DNA inventory cross-check (vol expansion DNA distinct from p101)",
            "#32 candidate dogfood (A_focus vs B_baseline vol_ratio excess)",
        ],
        "next_step_recommendation": (
            "User explicit gate required before R-2. R-1 verdict above is final "
            "for this dispatch. PASS_R1_* paths propose R-2 walk-forward + cohort "
            "expansion. Graveyards halt + report to lessons grid update."
        ),
    }

    OUT_PATH.write_text(json.dumps(output, default=str, ensure_ascii=False, indent=2))
    log.info("wrote %s — verdict=%s", OUT_PATH, verdict)
    return output


if __name__ == "__main__":
    res = run()
    print(json.dumps({
        "verdict": res["verdict"],
        "n_events_total": res["n_events_total"],
        "A_focus_n": res["cells_4quadrant"]["A_focus"]["n"],
        "A_focus_net_bp": res["cells_4quadrant"]["A_focus"].get("net_mean_bp"),
        "A_focus_sig_ex": res["cells_4quadrant"]["A_focus"].get("signal_t_excess"),
    }, default=str, ensure_ascii=False))
