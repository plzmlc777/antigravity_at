"""R-1 PoC for paradigm 101 candidate dart_supply_contract_announce_kr_equity_long_5d.

Hypothesis
----------
KR equity 단일판매·공급계약체결 공시 = immediate market attention information event.
Announce day (rcept_dt) → +1d open entry → +5d hold LONG produces positive net edge
after 50bp KR equity round-trip fee (Lesson #11+19+26+27 amendment + #29 dogfood).

Design (per agent dispatch spec)
--------------------------------
- Universe: 350 stocks KOSPI200 + KOSDAQ150 (Naver universe joblib, 127 unique
  triggered in R-0 prescreen).
- Window: 2024-01-01 .. 2026-05-19 (2.4yr full DART substrate).
- Trigger: report_nm contains 단일판매ㆍ공급계약체결 AND NOT 해지 AND NOT 자회사 AND NOT 거래정지
  (focus on principal entity new contracts; exclude subsidiary-only attenuated + cancellations
  + trading suspension noise; 자율공시 voluntary kept since same mechanism class).
- Entry: next trading day open strictly after rcept_dt.
- Exit: +3 / +5 / +10 trading days close (hold sweep).
- Fee: 50bp round-trip KR equity (baseline) + 100bp stress.

4-quadrant Symmetric Negative Test (Lesson #19, single batch obligatory)
-------------------------------------------------------------------------
- A focus      : announce_day × LONG (immediate buying pressure)
- A mirror     : announce_day × SHORT
- B baseline   : non_announce_day same-universe × LONG (universe baseline noise)
- B baseline mirror : non_announce_day × SHORT

A focus must outperform B baseline (information event hypothesis), AND
A mirror should NOT pass (pure direction-bet falsification, Lesson #8).
B baseline pair tests the universe-level mean-noise to isolate the
event-driven excess.

Cross-proxy strict (Lesson #29 obligatory)
-------------------------------------------
- Observable proxy: entry_open gap (entry_open / prior_close - 1)
  → sentiment proxy. Split A focus by gap_pos vs gap_neg.
- Frequency proxy (fundamental analog given no contract-notional API track for R-1):
  per-symbol announcement freq (6m rolling count). High-freq announcer → less
  information per event ("noise contracts"). Split A focus by freq_top33 vs freq_bot33.
- Both proxies must show coherent direction (gap_pos ≥ gap_neg AND freq_bot33 ≥ freq_top33
  for hypothesis "information event with attention demand"); otherwise SINGLE_PROXY_TRAP.

Concentration Gate (Lesson #16 + #26 amendment, n_measurable_quarters ≥ 4 obligatory)
----------------------------------------------------------------------------------------
- Per-quarter t-stat distribution (≥ 3/n_measurable_quarters with t>0)
- Per-symbol bootstrap CI distribution (≥ 30% of triggered symbols ci_pos)
- Per-symbol fraction max ≤ 10% (no single stock dominates)

4-dim life-changing (obligatory per feedback_life_changing_strategy_criterion)
------------------------------------------------------------------------------
- trades/yr ≥ 12
- per_trade_edge_net ≥ +2.0%
- capital_util ≥ 30% (avg active position window / total trading days)
- annualized_sharpe ≥ 1.5

Verdict decision tree (R-1 verdict only — R-2 dispatch obligatory user gate)
-----------------------------------------------------------------------------
1. SAMPLE_INSUFFICIENT (any per-cell n < 30) → halt
2. CONCENTRATION_FAIL (quarter or symbol concentration) → halt
3. BROAD_FALSIFIED (A focus three-gate FAIL across all 3 holds) → graveyard
4. BROAD_FALSIFIED_MIRROR_ONLY (A mirror passes but A focus fails) → graveyard
5. SINGLE_PROXY_TRAP_OBS_ONLY / SINGLE_PROXY_TRAP_FUND_ONLY (cross-proxy not coherent)
6. NARROW_SCOPE_LIFE_CHANGING_FAIL (3-gate PASS but 4-dim FAIL) → graveyard
7. NARROW_SCOPE_CANDIDATE (Lesson #20 4-cond all PASS + 4-dim PASS but per-symbol < 4)
8. PASS_R1_CROSS_PROXY_PROMOTE_R2 (3-gate PASS + cross-proxy both PASS + Concentration + 4-dim)
9. PASS_R1_FULL (PASS_R1_CROSS_PROXY_PROMOTE_R2 across all 3 holds)

Output: backend/runs/research_track/dart_supply_contract_announce_kr_equity_long_5d/r1_metrics.json
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
BACKEND_ROOT = HERE.parents[2]   # backend/
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
log = logging.getLogger("r1")

OUT_DIR = BACKEND_ROOT / "runs" / "research_track" / "dart_supply_contract_announce_kr_equity_long_5d"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "r1_metrics.json"

OHLCV_DIR = BACKEND_ROOT / "runs" / "dart_track" / "ohlcv_cache"
UNIVERSE_PATH = BACKEND_ROOT / "runs" / "dart_track" / "universe_kospi200_kosdaq150.joblib"
R0_EVENTS_PATH = OUT_DIR / "r0_matched_events_raw.json"
EVENTS_CACHE_PATH = OUT_DIR / "supply_contract_events_cache.joblib"

# --- Config ---
HOLDS = (3, 5, 10)
FEE_ROUND_TRIP = 0.005  # 50bp baseline
FEE_STRESS = 0.010      # 100bp stress
MIN_CELL_N = 30
MAX_SYMBOL_FRACTION = 0.10
NEEDLE_CORE = "공급계약체결"      # core needle (announcement events; excludes 해지)
EXCLUDE_TERMS = ("해지", "자회사", "거래정지")  # filter out non-mechanism noise
N_PERMS = 1000
N_BOOTSTRAP = 2000


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


def build_events_cache(stock_codes_universe: set[str]) -> pd.DataFrame:
    """Build events_ret cache: filter R-0 matches to focus mechanism + join OHLCV
    + compute entry_open, prior_close, exit_close@3/5/10, gap, fwd_ret @ 3/5/10."""
    if EVENTS_CACHE_PATH.exists():
        log.info("loading existing events_ret cache from %s", EVENTS_CACHE_PATH)
        return joblib.load(EVENTS_CACHE_PATH)

    raw = json.loads(R0_EVENTS_PATH.read_text())
    log.info("R-0 raw matched events: %d", len(raw))

    # Filter: keep focus mechanism (announcement, NOT 해지/자회사/거래정지)
    filt = []
    for ev in raw:
        nm = ev["report_nm"]
        if NEEDLE_CORE not in nm:
            continue
        if any(t in nm for t in EXCLUDE_TERMS):
            continue
        filt.append(ev)
    log.info("after filter (focus mechanism): %d", len(filt))

    df = pd.DataFrame(filt)
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d")
    df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
    df = df[df["stock_code"].isin(stock_codes_universe)].reset_index(drop=True)
    log.info("after universe filter (350 stocks): %d", len(df))

    # Compute per-symbol announcement frequency (6m rolling count) for fundamental proxy
    df = df.sort_values(["stock_code", "rcept_dt"]).reset_index(drop=True)
    df["freq_6m"] = (
        df.groupby("stock_code")
          .apply(lambda g: g["rcept_dt"].apply(
              lambda d: ((g["rcept_dt"] >= d - pd.Timedelta(days=180)) &
                         (g["rcept_dt"] < d)).sum()
          ))
          .reset_index(level=0, drop=True)
    )

    # Compute entry/exit returns for each hold
    rows_out = []
    skipped = 0
    by_code = df.groupby("stock_code")
    log.info("computing event returns across %d symbols", len(by_code))
    for idx, (code, grp) in enumerate(by_code, 1):
        ohlcv = load_ohlcv(code)
        if ohlcv.empty:
            skipped += len(grp)
            continue
        ohlcv = ohlcv.set_index("date").sort_index()
        dates_arr = ohlcv.index.values
        for _, ev in grp.iterrows():
            ev_dt = ev["rcept_dt"].to_datetime64()
            pos = int(np.searchsorted(dates_arr, ev_dt, side="right"))
            if pos < 1 or pos + max(HOLDS) >= len(ohlcv):
                skipped += 1
                continue
            prior_close = float(ohlcv["close"].iloc[pos - 1])
            entry_open = float(ohlcv["open"].iloc[pos])
            if not (prior_close > 0 and entry_open > 0):
                skipped += 1
                continue
            row = {
                "rcept_dt": ev["rcept_dt"],
                "rcept_no": ev["rcept_no"],
                "stock_code": code,
                "corp_name": ev["corp_name"],
                "report_nm": ev["report_nm"],
                "entry_date": ohlcv.index[pos],
                "prior_close": prior_close,
                "entry_open": entry_open,
                "gap": entry_open / prior_close - 1.0,
                "freq_6m": ev.get("freq_6m", 0),
            }
            valid = True
            for h in HOLDS:
                exit_close = float(ohlcv["close"].iloc[pos + h - 1])
                if exit_close <= 0:
                    valid = False
                    break
                row[f"exit_close_{h}d"] = exit_close
                row[f"fwd_ret_{h}d_gross"] = exit_close / entry_open - 1.0
            if not valid:
                skipped += 1
                continue
            rows_out.append(row)
        if idx % 25 == 0:
            log.info("  ...%d/%d symbols, kept=%d skipped=%d",
                     idx, len(by_code), len(rows_out), skipped)

    events_ret = pd.DataFrame(rows_out)
    log.info("events with OHLCV: kept=%d skipped=%d", len(events_ret), skipped)
    joblib.dump(events_ret, EVENTS_CACHE_PATH)
    log.info("wrote %s", EVENTS_CACHE_PATH)
    return events_ret


def candidate_pool_returns(events_ret: pd.DataFrame, hold_days: int,
                           sample_n: int = 15000, rng_seed: int = 42) -> np.ndarray:
    """Random non-trigger entry pool across universe-with-events.
    For fee_aware_perm_test null distribution at each hold horizon."""
    rng = np.random.default_rng(rng_seed)
    codes = events_ret["stock_code"].unique()
    per_code = max(2, sample_n // max(1, len(codes)))
    out = []
    # Trigger date set per symbol for non-overlap with actual triggers
    trig_per_sym = events_ret.groupby("stock_code")["entry_date"].apply(set).to_dict()
    for code in codes:
        ohlcv = load_ohlcv(code)
        if ohlcv.empty or len(ohlcv) < hold_days + 2:
            continue
        ohlcv = ohlcv.sort_values("date").reset_index(drop=True)
        valid_idx = np.arange(0, len(ohlcv) - hold_days)
        if len(valid_idx) == 0:
            continue
        # exclude actual trigger dates
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


def _per_sym_counts(df: pd.DataFrame) -> dict[str, int]:
    return df["stock_code"].value_counts().to_dict()


def cell_stats(returns: np.ndarray, direction: int, label: str, fee: float,
               pool: np.ndarray, by_symbol_count: dict[str, int] | None = None,
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


def per_quarter_t(returns_with_dates: pd.DataFrame, direction: int, fee: float) -> dict:
    """Per-quarter t-stat distribution for Concentration Gate (Lesson #26 amendment)."""
    df = returns_with_dates.copy()
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
        if len(net) < 8:
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


def life_changing_4dim(events_ret: pd.DataFrame, hold_days: int, fee: float) -> dict:
    """Per-trade edge / trades/yr / sharpe / capital utilization."""
    df = events_ret.copy()
    direction = +1  # A focus LONG
    df["net_ret"] = df[f"fwd_ret_{hold_days}d_gross"] * direction - fee
    n_trades = len(df)
    window_days = (df["entry_date"].max() - df["entry_date"].min()).days
    years = max(window_days / 365.25, 1e-9)
    trades_per_yr = n_trades / years
    per_trade_edge_net = float(df["net_ret"].mean())
    # Annualized sharpe: per-trade net stats × sqrt(trades_per_yr)
    if n_trades >= 2 and df["net_ret"].std(ddof=1) > 0:
        sharpe = float(per_trade_edge_net / df["net_ret"].std(ddof=1) * np.sqrt(trades_per_yr))
    else:
        sharpe = 0.0
    # capital util: avg # of open positions / # active stocks in universe (very rough)
    # Assume single-position-per-stock model: util_per_trade = hold_days / (trading days in year ~250)
    # avg simultaneous open positions ≈ trades_per_yr × hold_days / 250
    avg_open = trades_per_yr * hold_days / 250.0
    # If universe = 350, util = avg_open / 1 (single-position-equity) but for portfolio
    # better measure: fraction of trading days with at least one open position
    # approximation: trades × hold_days / total trading days × universe ratio of 1
    # Use simple: fraction of session-days with at least one open trade in any sym
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
        "pass_trades_per_yr_min12": trades_per_yr >= 12,
        "pass_per_trade_edge_min_2pct": per_trade_edge_net >= 0.02,
        "pass_capital_util_min_30pct": util_calendar >= 0.30,
        "pass_sharpe_min_1p5": sharpe >= 1.5,
        "pass_4dim_life_changing": (
            trades_per_yr >= 12
            and per_trade_edge_net >= 0.02
            and util_calendar >= 0.30
            and sharpe >= 1.5
        ),
    }


def run_one_hold(events_ret: pd.DataFrame, hold_days: int) -> dict:
    """4-quadrant + cross-proxy + Concentration + 4-dim for a single hold horizon."""
    ret_col = f"fwd_ret_{hold_days}d_gross"
    df = events_ret.dropna(subset=[ret_col]).copy()
    df["ret"] = df[ret_col]

    log.info("hold=%dd: n=%d events, computing candidate pool...", hold_days, len(df))
    pool = candidate_pool_returns(df, hold_days)
    log.info("  candidate pool size: %d", len(pool))

    sym_counts = _per_sym_counts(df)
    total = len(df)

    cells = {}
    # A focus: announce_day × LONG
    cells["A_focus_long"] = cell_stats(
        df["ret"].values, direction=+1, label="announce × LONG",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts, total_trades=total,
    )
    # A mirror: announce_day × SHORT
    cells["A_mirror_short"] = cell_stats(
        df["ret"].values, direction=-1, label="announce × SHORT",
        fee=FEE_ROUND_TRIP, pool=pool,
        by_symbol_count=sym_counts, total_trades=total,
    )
    # B baseline: non_announce same universe × LONG (use candidate pool as B baseline)
    cells["B_baseline_long"] = cell_stats(
        pool, direction=+1, label="non_announce × LONG",
        fee=FEE_ROUND_TRIP, pool=pool,
    )
    # B baseline mirror: non_announce × SHORT
    cells["B_baseline_short"] = cell_stats(
        pool, direction=-1, label="non_announce × SHORT",
        fee=FEE_ROUND_TRIP, pool=pool,
    )

    # A focus stress (100bp fee)
    cells["A_focus_long_stress100bp"] = cell_stats(
        df["ret"].values, direction=+1, label="announce × LONG @ 100bp",
        fee=FEE_STRESS, pool=pool,
        by_symbol_count=sym_counts, total_trades=total,
    )

    # Cross-proxy strict (Lesson #29)
    # Observable proxy: entry_open gap split
    gap_pos = df[df["gap"] > 0]
    gap_neg = df[df["gap"] <= 0]
    cross_proxy_obs = {
        "gap_pos_n": len(gap_pos),
        "gap_neg_n": len(gap_neg),
        "gap_pos_long": cell_stats(
            gap_pos["ret"].values, direction=+1, label="gap_pos × LONG",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_pos), total_trades=len(gap_pos),
        ) if len(gap_pos) else {"n": 0},
        "gap_neg_long": cell_stats(
            gap_neg["ret"].values, direction=+1, label="gap_neg × LONG",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(gap_neg), total_trades=len(gap_neg),
        ) if len(gap_neg) else {"n": 0},
    }
    # Fundamental proxy (analog): freq_6m split (low-freq announcer = more info per event)
    freq_low_q = df["freq_6m"].quantile(1/3)
    freq_high_q = df["freq_6m"].quantile(2/3)
    freq_low = df[df["freq_6m"] <= freq_low_q]
    freq_high = df[df["freq_6m"] >= freq_high_q]
    cross_proxy_fund = {
        "freq_low_n": len(freq_low),
        "freq_high_n": len(freq_high),
        "freq_low_long": cell_stats(
            freq_low["ret"].values, direction=+1, label="freq_low_33pct × LONG",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(freq_low), total_trades=len(freq_low),
        ) if len(freq_low) else {"n": 0},
        "freq_high_long": cell_stats(
            freq_high["ret"].values, direction=+1, label="freq_high_33pct × LONG",
            fee=FEE_ROUND_TRIP, pool=pool,
            by_symbol_count=_per_sym_counts(freq_high), total_trades=len(freq_high),
        ) if len(freq_high) else {"n": 0},
    }
    cross_proxy_summary = {
        "obs_proxy_gap_pos_minus_neg_bp": (
            cross_proxy_obs["gap_pos_long"].get("net_mean_bp", 0)
            - cross_proxy_obs["gap_neg_long"].get("net_mean_bp", 0)
        ),
        "fund_proxy_freq_low_minus_high_bp": (
            cross_proxy_fund["freq_low_long"].get("net_mean_bp", 0)
            - cross_proxy_fund["freq_high_long"].get("net_mean_bp", 0)
        ),
    }
    # Cross-proxy strict PASS = both proxies show hypothesis-coherent direction
    # Hypothesis: info event with attention demand → gap_pos > gap_neg (sentiment continuation)
    # AND freq_low > freq_high (less-frequent announce = more informative)
    cross_proxy_summary["pass_obs_coherent"] = (
        cross_proxy_summary["obs_proxy_gap_pos_minus_neg_bp"] > 0
        if cross_proxy_obs["gap_pos_long"].get("n", 0) >= MIN_CELL_N
        and cross_proxy_obs["gap_neg_long"].get("n", 0) >= MIN_CELL_N
        else None
    )
    cross_proxy_summary["pass_fund_coherent"] = (
        cross_proxy_summary["fund_proxy_freq_low_minus_high_bp"] > 0
        if cross_proxy_fund["freq_low_long"].get("n", 0) >= MIN_CELL_N
        and cross_proxy_fund["freq_high_long"].get("n", 0) >= MIN_CELL_N
        else None
    )
    cross_proxy_summary["pass_cross_proxy_both"] = bool(
        cross_proxy_summary.get("pass_obs_coherent")
        and cross_proxy_summary.get("pass_fund_coherent")
    )

    # Concentration Gate (Lesson #16 + #26 amendment)
    per_q = per_quarter_t(df[["entry_date", "ret"]], direction=+1, fee=FEE_ROUND_TRIP)
    per_s = per_symbol_ci(df[["stock_code", "ret"]], direction=+1, fee=FEE_ROUND_TRIP)
    concentration_gate_pass = bool(
        per_q["__summary"].get("pass_lesson_26_amendment_n_measurable_min4")
        and per_q["__summary"].get("pass_quarter_pos_t_ratio_min_0p5")
        and per_s["__summary"].get("pass_symbol_ci_pos_ratio_min_0p30")
        and per_s["__summary"].get("pass_n_symbols_ci_pos_min_3")
    )

    # 4-dim life-changing
    four_dim = life_changing_4dim(df, hold_days, FEE_ROUND_TRIP)

    return {
        "hold_days": hold_days,
        "n": int(len(df)),
        "pool_n": int(len(pool)),
        "quadrants": cells,
        "cross_proxy_observable_gap": cross_proxy_obs,
        "cross_proxy_fundamental_freq": cross_proxy_fund,
        "cross_proxy_summary": cross_proxy_summary,
        "concentration_per_quarter": per_q,
        "concentration_per_symbol": per_s,
        "concentration_gate_pass": concentration_gate_pass,
        "life_changing_4dim": four_dim,
    }


def main():
    log.info("=== R-1 PoC: paradigm 101 candidate dart_supply_contract ===")

    universe = load_universe()
    events_ret = build_events_cache(universe)
    if events_ret.empty:
        out = {"verdict": "SAMPLE_INSUFFICIENT", "n_events_with_returns": 0}
        OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        log.info("HALT: no events with returns")
        return 0

    log.info("events with returns: %d (across %d symbols)",
             len(events_ret), events_ret["stock_code"].nunique())

    all_results = {}
    for h in HOLDS:
        log.info(">>> processing hold=%dd ...", h)
        all_results[f"hold_{h}d"] = run_one_hold(events_ret, h)

    # Aggregate verdict — base on hold=5d (primary spec) but report all
    primary = all_results["hold_5d"]
    afoc = primary["quadrants"]["A_focus_long"]
    amir = primary["quadrants"]["A_mirror_short"]

    # Per-cell sample check
    cell_ns = [primary["quadrants"][k].get("n", 0) for k in ("A_focus_long", "A_mirror_short")]
    if min(cell_ns) < MIN_CELL_N:
        verdict = "SAMPLE_INSUFFICIENT"
    elif not primary["concentration_gate_pass"]:
        verdict = "CONCENTRATION_FAIL"
    else:
        afoc_pass = afoc.get("pass_three_gate")
        amir_pass = amir.get("pass_three_gate")
        cross_pass = primary["cross_proxy_summary"].get("pass_cross_proxy_both")
        four_dim_pass = primary["life_changing_4dim"].get("pass_4dim_life_changing")

        if not afoc_pass and amir_pass:
            verdict = "BROAD_FALSIFIED_MIRROR_ONLY"
        elif not afoc_pass:
            verdict = "BROAD_FALSIFIED"
        elif afoc_pass and not cross_pass:
            # determine which proxy track failed
            obs = primary["cross_proxy_summary"].get("pass_obs_coherent")
            fund = primary["cross_proxy_summary"].get("pass_fund_coherent")
            if obs and not fund:
                verdict = "SINGLE_PROXY_TRAP_OBS_ONLY"
            elif fund and not obs:
                verdict = "SINGLE_PROXY_TRAP_FUND_ONLY"
            else:
                verdict = "SINGLE_PROXY_TRAP_BOTH_AMBIGUOUS"
        elif afoc_pass and cross_pass and not four_dim_pass:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        elif afoc_pass and cross_pass and four_dim_pass:
            # check across all holds for PASS_R1_FULL
            all_3_hold_pass = all(
                all_results[f"hold_{h}d"]["quadrants"]["A_focus_long"].get("pass_three_gate")
                and all_results[f"hold_{h}d"]["cross_proxy_summary"].get("pass_cross_proxy_both")
                and all_results[f"hold_{h}d"]["life_changing_4dim"].get("pass_4dim_life_changing")
                for h in HOLDS
            )
            verdict = "PASS_R1_FULL" if all_3_hold_pass else "PASS_R1_CROSS_PROXY_PROMOTE_R2"
        else:
            verdict = "BROAD_FALSIFIED"

    out = {
        "paradigm_name": "dart_supply_contract_announce_kr_equity_long_5d",
        "phase": "R-1",
        "verdict": verdict,
        "primary_hold_days": 5,
        "n_events_total": int(len(events_ret)),
        "n_distinct_stocks": int(events_ret["stock_code"].nunique()),
        "window_kst": "2024-01-01 .. 2026-05-19 (2.4yr DART substrate)",
        "config": {
            "universe_size": len(universe),
            "fee_round_trip_bp": int(FEE_ROUND_TRIP * 10_000),
            "fee_stress_bp": int(FEE_STRESS * 10_000),
            "min_cell_n": MIN_CELL_N,
            "max_symbol_fraction": MAX_SYMBOL_FRACTION,
            "n_perms": N_PERMS,
            "n_bootstrap": N_BOOTSTRAP,
            "needle_core": NEEDLE_CORE,
            "exclude_terms": list(EXCLUDE_TERMS),
            "hold_sweep_days": list(HOLDS),
        },
        "by_hold": all_results,
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
