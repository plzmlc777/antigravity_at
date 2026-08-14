"""paradigm 205 R-1 STRICT
KS 2-sample distribution-shift z-score spike + signed direction (variance ratio sign).

4-quadrant SNT:
  A_focus      : KS_z >= +2 × recent_heavier × LONG  (variance expansion continuation)
  A_mirror     : KS_z >= +2 × recent_heavier × SHORT (expansion reversal)
  B_same_sign  : KS_z >= +2 × recent_lighter × SHORT (contraction continuation)
  B_mirror     : KS_z >= +2 × recent_lighter × LONG  (contraction reversal, Lesson #42 12th dogfood)

Substrate: 20 alts × 4h cache × 2.25yr (paradigm 198 cohort).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paradigm205_r1")

CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"
OUT_DIR = ROOT / "runs" / "research_track" / (
    "alt_per_sym_90d_ks_2sample_distribution_shift_z_spike_signed_"
    "heavier_tail_directional_4h_bilateral"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = [
    "ADA", "AVAX", "BCH", "BNB", "DOGE", "DOT", "ETC", "ETH", "FIL",
    "JUP", "LDO", "LINK", "LTC", "NEAR", "PYTH", "SOL", "UNI", "WIF",
    "WLD", "XRP",
]
FEE = 0.0008  # taker round-trip ≈ 8 bp (single side ≈ 4 bp, but use 8 bp net per trade per spec)
SPLIT_DAYS = 45            # split window 45d/45d
WINDOW_DAYS = SPLIT_DAYS * 2  # 90d total
ZSCORE_WIN_DAYS = 180      # rolling z-window
Z_TRIGGER = 2.0            # |KS_z| >= 2
HOLDS_4H = {"4h": 1, "8h": 2, "12h": 3, "24h": 6}


def load_daily_returns(sym: str) -> pd.DataFrame:
    fp = CACHE_DIR / f"{sym}USDT_4h.joblib"
    if not fp.exists():
        return pd.DataFrame()
    df = joblib.load(fp).copy()
    df = df.sort_index()
    # daily aggregate (UTC date)
    daily_close = df["close"].resample("1D").last().dropna()
    daily_ret = np.log(daily_close).diff().dropna().rename("daily_ret")
    return pd.DataFrame({"daily_ret": daily_ret})


def compute_ks_and_sign(daily_ret: pd.Series) -> pd.DataFrame:
    """For each day t, compute KS 2-sample stat over recent45d vs prior45d,
    plus sign = +1 if var(recent)>var(prior), else -1."""
    arr = daily_ret.values
    idx = daily_ret.index
    n = len(arr)
    ks_stat = np.full(n, np.nan)
    sign = np.full(n, 0, dtype=int)
    for i in range(WINDOW_DAYS, n):
        prior = arr[i - WINDOW_DAYS:i - SPLIT_DAYS]
        recent = arr[i - SPLIT_DAYS:i]
        if len(prior) < SPLIT_DAYS or len(recent) < SPLIT_DAYS:
            continue
        try:
            stat, _ = ks_2samp(recent, prior)
        except Exception:
            continue
        ks_stat[i] = stat
        var_r = float(np.var(recent))
        var_p = float(np.var(prior))
        sign[i] = 1 if var_r > var_p else -1
    out = pd.DataFrame({"ks": ks_stat, "sign": sign}, index=idx)
    # rolling z over ZSCORE_WIN_DAYS
    out["ks_mean"] = out["ks"].rolling(ZSCORE_WIN_DAYS, min_periods=60).mean()
    out["ks_std"] = out["ks"].rolling(ZSCORE_WIN_DAYS, min_periods=60).std()
    out["ks_z"] = (out["ks"] - out["ks_mean"]) / out["ks_std"]
    return out


def load_4h_close(sym: str) -> pd.Series:
    fp = CACHE_DIR / f"{sym}USDT_4h.joblib"
    if not fp.exists():
        return pd.Series(dtype=float)
    df = joblib.load(fp).copy().sort_index()
    return df["close"]


def collect_events(sym: str, ks_df: pd.DataFrame, close_4h: pd.Series,
                   holds_bars: Dict[str, int]) -> List[dict]:
    """For each daily KS trigger, find first 4h bar at next 00:00 UTC and compute fwd ret per hold."""
    trig = ks_df[(ks_df["ks_z"].abs() >= Z_TRIGGER) & (ks_df["sign"] != 0)].copy()
    events: List[dict] = []
    close_arr = close_4h.values
    close_idx = close_4h.index
    # we need to find next 4h bar entry at (date + 1 day, 00:00 UTC) and hold
    for ts, row in trig.iterrows():
        # entry at next day 00:00 UTC
        entry_ts = (ts + pd.Timedelta(days=1)).normalize()
        # locate in 4h grid
        loc = close_4h.index.searchsorted(entry_ts)
        if loc >= len(close_idx):
            continue
        entry_px = close_arr[loc]
        for h_name, h_bars in holds_bars.items():
            exit_loc = loc + h_bars
            if exit_loc >= len(close_arr):
                continue
            exit_px = close_arr[exit_loc]
            log_ret = float(np.log(exit_px / entry_px))
            events.append({
                "sym": sym,
                "ts": ts,
                "entry_ts": close_idx[loc],
                "ks_z": float(row["ks_z"]),
                "sign": int(row["sign"]),
                "hold": h_name,
                "log_ret": log_ret,
            })
    return events


def classify(sign: int, side: str) -> str:
    """quadrant naming."""
    # sign = +1 (recent heavier-tail / variance expansion), -1 (recent lighter-tail / contraction)
    if sign == 1 and side == "LONG":
        return "A_focus"
    if sign == 1 and side == "SHORT":
        return "A_mirror"
    if sign == -1 and side == "SHORT":
        return "B_same_sign"
    if sign == -1 and side == "LONG":
        return "B_mirror"
    return "UNK"


def side_return(log_ret: float, side: str) -> float:
    return log_ret if side == "LONG" else -log_ret


def per_symbol_pool(daily_ret_by_sym: Dict[str, pd.Series],
                    close_4h_by_sym: Dict[str, pd.Series],
                    hold_bars: int) -> np.ndarray:
    """4h close-to-close pooled returns matching hold_bars window length, across syms."""
    pool: List[float] = []
    for sym, close in close_4h_by_sym.items():
        arr = close.values
        if len(arr) < hold_bars + 2:
            continue
        # sample every hold_bars stride to avoid overlap inflation
        for i in range(0, len(arr) - hold_bars, hold_bars):
            try:
                r = float(np.log(arr[i + hold_bars] / arr[i]))
            except Exception:
                continue
            if np.isfinite(r):
                pool.append(r)
    return np.asarray(pool, dtype=float)


def quadrant_metrics(rows: List[dict], side: str, sign_filter: int,
                     pool: np.ndarray, fee: float) -> dict:
    sub = [r for r in rows if r["sign"] == sign_filter]
    rets = np.asarray([side_return(r["log_ret"], side) for r in sub], dtype=float)
    n = len(rets)
    if n < 5:
        return {"n": n, "gross_bp": None, "net_bp": None, "sigex": None,
                "perm_p": None, "ci_lower_bp": None, "ci_upper_bp": None,
                "ci_pos": False, "syms": {}, "per_quarter": {}}
    gross_mean = float(rets.mean())
    net_rets = rets - fee
    # signal_t_excess via fee_aware_perm_test
    perm = fee_aware_perm_test(net_rets.tolist(), pool.tolist(), fee_per_trade=fee,
                               n_perms=1000, rng_seed=42)
    ci = bootstrap_ci(net_rets.tolist(), n_boot=2000, alpha=0.05, rng_seed=42)
    # per-sym ci
    sym_bag: Dict[str, List[float]] = {}
    for r, sub_r in zip(rets, sub):
        sym_bag.setdefault(sub_r["sym"], []).append(float(r - fee))
    sym_stats = {}
    for s, vals in sym_bag.items():
        if len(vals) < 5:
            sym_stats[s] = {"n": len(vals), "ci_lower_bp": None, "ci_pos": False, "mean_bp": float(np.mean(vals)) * 1e4}
            continue
        c = bootstrap_ci(vals, n_boot=1000, alpha=0.05, rng_seed=42)
        sym_stats[s] = {"n": len(vals), "ci_lower_bp": c["ci_lower"] * 1e4,
                        "ci_upper_bp": c["ci_upper"] * 1e4,
                        "ci_pos": c["ci_lower"] > 0,
                        "mean_bp": float(np.mean(vals)) * 1e4}
    # per-quarter
    per_q: Dict[str, dict] = {}
    for r, sub_r in zip(net_rets, sub):
        q = pd.Timestamp(sub_r["ts"]).to_period("Q").strftime("%Y-Q%q") if False else f"{pd.Timestamp(sub_r['ts']).year}Q{((pd.Timestamp(sub_r['ts']).month - 1) // 3) + 1}"
        per_q.setdefault(q, []).append(float(r))
    q_stats = {}
    for q, vals in per_q.items():
        if len(vals) < 5:
            q_stats[q] = {"n": len(vals), "t": None, "mean_bp": float(np.mean(vals)) * 1e4}
            continue
        a = np.asarray(vals)
        t = float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))) if a.std(ddof=1) > 0 else None
        q_stats[q] = {"n": len(vals), "t": t, "mean_bp": float(a.mean()) * 1e4}
    # era stratify (Item 6)
    era_stats = {}
    for era_name, year_set in {"2024": {2024}, "2025": {2025}, "2026": {2026}}.items():
        era_vals = [float(r) for r, sub_r in zip(net_rets, sub)
                    if pd.Timestamp(sub_r["ts"]).year in year_set]
        if len(era_vals) < 5:
            era_stats[era_name] = {"n": len(era_vals), "sigex": None, "mean_bp": float(np.mean(era_vals)) * 1e4 if era_vals else None}
            continue
        ev = np.asarray(era_vals)
        if pool.size > 0:
            pool_mean = pool.mean() - fee
            pool_std = pool.std(ddof=1)
            sigex_era = (ev.mean() - pool_mean) / (pool_std / np.sqrt(len(ev))) if pool_std > 0 else None
        else:
            sigex_era = None
        era_stats[era_name] = {"n": len(era_vals), "sigex": sigex_era, "mean_bp": float(ev.mean()) * 1e4}
    n_syms_ci_pos = sum(1 for v in sym_stats.values() if v.get("ci_pos"))
    n_q_pos_t = sum(1 for v in q_stats.values() if v.get("t") and v["t"] > 0)
    n_q_meas = sum(1 for v in q_stats.values() if v.get("t") is not None)
    return {
        "n": n,
        "gross_bp": gross_mean * 1e4,
        "net_bp": float(net_rets.mean()) * 1e4,
        "sigex": perm.get("signal_t_excess"),
        "perm_p": perm.get("perm_p"),
        "null_mean_t": perm.get("null_mean_t"),
        "ci_lower_bp": ci["ci_lower"] * 1e4,
        "ci_upper_bp": ci["ci_upper"] * 1e4,
        "ci_pos": ci["ci_lower"] > 0,
        "n_syms_unique": len(sym_stats),
        "n_syms_ci_pos": n_syms_ci_pos,
        "syms": sym_stats,
        "per_quarter": q_stats,
        "n_q_measurable": n_q_meas,
        "n_q_pos_t": n_q_pos_t,
        "q_pos_t_ratio": (n_q_pos_t / n_q_meas) if n_q_meas else None,
        "era": era_stats,
    }


def three_gate_pass(m: dict) -> bool:
    if m["n"] < 5:
        return False
    if m["sigex"] is None or m["ci_lower_bp"] is None or m["perm_p"] is None:
        return False
    return (m["sigex"] >= 2.0) and (m["ci_lower_bp"] > 0) and (m["perm_p"] <= 0.10)


def main():
    log.info("loading daily returns for %d syms", len(UNIVERSE))
    daily_ret_by_sym: Dict[str, pd.Series] = {}
    close_4h_by_sym: Dict[str, pd.Series] = {}
    for s in UNIVERSE:
        ds = load_daily_returns(s)
        if ds.empty:
            log.warning("missing %s daily", s)
            continue
        daily_ret_by_sym[s] = ds["daily_ret"]
        c4 = load_4h_close(s)
        if c4.empty:
            log.warning("missing %s 4h close", s)
            continue
        close_4h_by_sym[s] = c4
    log.info("loaded %d syms with both daily+4h", len(daily_ret_by_sym))

    # compute KS+sign per sym
    all_events: List[dict] = []
    per_sym_trig_count: Dict[str, int] = {}
    for s, dr in daily_ret_by_sym.items():
        ks_df = compute_ks_and_sign(dr)
        trig = ks_df[(ks_df["ks_z"].abs() >= Z_TRIGGER) & (ks_df["sign"] != 0)]
        per_sym_trig_count[s] = int(len(trig))
        evs = collect_events(s, ks_df, close_4h_by_sym[s], HOLDS_4H)
        all_events.extend(evs)
    log.info("total events collected: %d", len(all_events))
    log.info("per-sym trigger counts: %s", per_sym_trig_count)

    # split by hold
    results: Dict[str, Dict[str, dict]] = {}
    # build pools per hold_bars
    pool_cache: Dict[int, np.ndarray] = {}
    for h_name, h_bars in HOLDS_4H.items():
        if h_bars not in pool_cache:
            pool_cache[h_bars] = per_symbol_pool(daily_ret_by_sym, close_4h_by_sym, h_bars)
        pool = pool_cache[h_bars]
        log.info("hold %s pool n=%d mean_bp=%.2f", h_name, len(pool), pool.mean() * 1e4 if len(pool) else 0)
        hold_events = [e for e in all_events if e["hold"] == h_name]
        quadrants = {
            "A_focus":     {"side": "LONG",  "sign": 1},
            "A_mirror":    {"side": "SHORT", "sign": 1},
            "B_same_sign": {"side": "SHORT", "sign": -1},
            "B_mirror":    {"side": "LONG",  "sign": -1},
        }
        results[h_name] = {}
        for qname, qcfg in quadrants.items():
            m = quadrant_metrics(hold_events, qcfg["side"], qcfg["sign"], pool, FEE)
            m["pass"] = three_gate_pass(m)
            results[h_name][qname] = m
            log.info("hold=%s quadrant=%s n=%d gross=%.2fbp sigex=%s perm_p=%s ci_lo=%s pass=%s",
                     h_name, qname, m["n"],
                     m["gross_bp"] if m["gross_bp"] is not None else float("nan"),
                     m["sigex"], m["perm_p"], m["ci_lower_bp"], m["pass"])

    # summary
    out = {
        "paradigm": "alt_per_sym_90d_ks_2sample_distribution_shift_z_spike_signed_heavier_tail_directional_4h_bilateral",
        "n_syms": len(daily_ret_by_sym),
        "universe": list(daily_ret_by_sym.keys()),
        "fee": FEE,
        "z_trigger": Z_TRIGGER,
        "split_days": SPLIT_DAYS,
        "window_days": WINDOW_DAYS,
        "zscore_win_days": ZSCORE_WIN_DAYS,
        "per_sym_trigger_counts": per_sym_trig_count,
        "results": results,
        "pool_sizes_per_hold": {h: int(len(pool_cache[HOLDS_4H[h]])) for h in HOLDS_4H},
    }
    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("WROTE %s", out_path)
    print("DONE", out_path)


if __name__ == "__main__":
    main()
