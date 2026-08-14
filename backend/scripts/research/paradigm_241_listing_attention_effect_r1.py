"""
Paradigm 241: alt_new_perp_listing_attention_effect_existing_alts_bilateral_5d
R-1 PoC script

Hypothesis
----------
Each Binance USDT-M perp new listing event creates a measurable directional
5-day return effect on the pre-existing 14 alt perp universe:
- A_focus  (LONG existing alts post-listing)   halo/attention rotation
- A_mirror (SHORT existing alts post-listing)  attention drain
- B_focus  (bear-BTC-regime listings LONG)     regime conditioning
- B_mirror (bear-BTC-regime listings SHORT)    regime conditioning

Trigger
-------
listing_dates.json onboard_date for USDT-M perp base tokens.
Entry: bar at (onboard_date +24h UTC).
Exit : bar at (entry + 5d UTC).
Hold : 5 calendar days.
Universe: 14 pre-existing alts (BTC/ETH/BNB/SOL/XRP/DOGE/ADA/AVAX/LINK/LTC/BCH/FIL/NEAR/WIF).

Exclusions
----------
- self-referential: the newly-listed token itself is skipped.
- min 3-day debounce between events per (sym, date) is enforced.

Stats
-----
- fee_aware_perm_test  (fee=8bp round-trip; candidate pool = every possible
  5d hold within cache range for each sym, sampled)
- bootstrap_ci         (block=5)
- 3-gate PASS: signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_two_sided <= 0.10

Concentration
-------------
- per-symbol bootstrap  (14 syms)
- per-quarter t-stat    (11 quarters)

Era stratification (Alpha-Decay P1)
-----------------------------------
2024H1 / 2024H2 / 2025H1 / 2025H2 / 2026H1
"""
from __future__ import annotations

import json
import logging
import pathlib
import sys
import time
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from research._perm_utils import bootstrap_ci, fee_aware_perm_test  # type: ignore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("p241_r1")

PARADIGM_NAME = "paradigm_241_listing_attention_effect"
PARADIGM_NUMBER = 241
FEE = 0.0008  # 8bp round-trip
HOLD_DAYS = 5
ENTRY_LAG_HOURS = 24  # entry at onboard + 24h
DEBOUNCE_DAYS = 3
CUTOFF_DATE = "2024-01-01"
CACHE_DIR = pathlib.Path("/home/mint/auto_trading/backend/runs/ohlcv_cache")
LISTING_JSON = pathlib.Path(
    "/home/mint/auto_trading/backend/runs/research_track/lifecycle_phase/listing_dates.json"
)
OUT_DIR = pathlib.Path(
    "/home/mint/auto_trading/backend/runs/research_track/paradigm_241_listing_attention_effect"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALT_UNIVERSE = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "FILUSDT",
    "NEARUSDT",
    "WIFUSDT",
]

# Approximate historical Binance USDT-M perp listing dates for alts in universe
# (used to prevent trading a sym that wasn't yet listed at event time).
ALT_LISTING = {
    "BTCUSDT": "2019-09-08",
    "ETHUSDT": "2019-11-27",
    "BNBUSDT": "2020-02-10",
    "SOLUSDT": "2020-09-14",
    "XRPUSDT": "2020-01-06",
    "DOGEUSDT": "2020-07-10",
    "ADAUSDT": "2020-01-31",
    "AVAXUSDT": "2020-09-23",
    "LINKUSDT": "2020-01-17",
    "LTCUSDT": "2020-01-09",
    "BCHUSDT": "2019-11-14",
    "FILUSDT": "2020-10-15",
    "NEARUSDT": "2021-01-27",
    "WIFUSDT": "2024-03-05",
}


def _load_cache() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for s in ALT_UNIVERSE:
        p = CACHE_DIR / f"{s}_1m.joblib"
        if not p.exists():
            log.warning("missing cache for %s", s)
            continue
        df = joblib.load(p)
        # ensure sorted, tz-naive UTC
        df = df.sort_index()
        out[s] = df
    log.info("loaded %d sym caches", len(out))
    return out


def _daily_close(df1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1m to UTC daily OHLC."""
    daily = df1m.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(how="all")
    return daily


def _btc_30d_return(btc_daily: pd.DataFrame) -> pd.Series:
    """rolling 30d simple return per day (aligned to daily close)."""
    return btc_daily["close"].pct_change(30)


def _load_events() -> List[Tuple[str, pd.Timestamp]]:
    d = json.load(LISTING_JSON.open())
    events: List[Tuple[str, pd.Timestamp]] = []
    for sym, meta in d.items():
        if not sym.endswith("USDT"):
            continue
        od = meta.get("onboard_date")
        if not od or od < CUTOFF_DATE:
            continue
        ts = pd.Timestamp(od, tz=None)
        events.append((sym, ts))
    events.sort(key=lambda x: x[1])
    log.info("loaded %d listing events", len(events))
    return events


def _debounce_events(events: List[Tuple[str, pd.Timestamp]]) -> List[Tuple[str, pd.Timestamp]]:
    """Keep events but skip if <3 days from previous kept event (any symbol)."""
    if not events:
        return events
    kept = [events[0]]
    for sym, ts in events[1:]:
        if (ts - kept[-1][1]).days >= DEBOUNCE_DAYS:
            kept.append((sym, ts))
    log.info("after %dd debounce: %d events", DEBOUNCE_DAYS, len(kept))
    return kept


def _entry_exit_prices(
    df1m: pd.DataFrame, entry_ts: pd.Timestamp, exit_ts: pd.Timestamp
) -> Tuple[float, float] | None:
    """Return (entry_open, exit_close) or None if out-of-range."""
    if entry_ts < df1m.index[0] or exit_ts > df1m.index[-1]:
        return None
    # nearest bar >= entry_ts
    idx_e = df1m.index.searchsorted(entry_ts, side="left")
    if idx_e >= len(df1m):
        return None
    entry_open = float(df1m["open"].iloc[idx_e])
    idx_x = df1m.index.searchsorted(exit_ts, side="left")
    if idx_x >= len(df1m):
        return None
    exit_close = float(df1m["close"].iloc[idx_x])
    if entry_open <= 0 or exit_close <= 0 or not np.isfinite(entry_open) or not np.isfinite(exit_close):
        return None
    return entry_open, exit_close


def _era_of(ts: pd.Timestamp) -> str:
    y = ts.year
    h = "H1" if ts.month <= 6 else "H2"
    return f"{y}{h}"


def _quarter_of(ts: pd.Timestamp) -> str:
    q = (ts.month - 1) // 3 + 1
    return f"{ts.year}Q{q}"


def _build_observations(
    caches: Dict[str, pd.DataFrame],
    events: List[Tuple[str, pd.Timestamp]],
    btc_30d_ret: pd.Series,
) -> pd.DataFrame:
    """
    For each listing event, iterate over the 14 existing-alt universe.
    Skip if the alt itself was the newly-listed token, or wasn't yet listed.
    Compute 5-day log return from entry (onboard_date+24h) to exit (+5d).
    """
    listing_ts_thresholds = {s: pd.Timestamp(ALT_LISTING[s]) for s in ALT_UNIVERSE}
    rows = []
    for listed_sym, ts in events:
        entry_ts = ts + pd.Timedelta(hours=ENTRY_LAG_HOURS)
        exit_ts = entry_ts + pd.Timedelta(days=HOLD_DAYS)

        # BTC 30d return at entry (for regime)
        try:
            entry_day = pd.Timestamp(entry_ts.normalize())
            # find last available btc 30d value <= entry_day
            btc_val = btc_30d_ret.loc[:entry_day].iloc[-1] if len(btc_30d_ret.loc[:entry_day]) else np.nan
        except Exception:
            btc_val = np.nan

        for sym in ALT_UNIVERSE:
            if sym == listed_sym:
                continue
            if ts < listing_ts_thresholds[sym]:
                continue  # this alt wasn't listed yet at event time
            df = caches.get(sym)
            if df is None:
                continue
            pr = _entry_exit_prices(df, entry_ts, exit_ts)
            if pr is None:
                continue
            entry_open, exit_close = pr
            log_ret = float(np.log(exit_close / entry_open))
            rows.append(
                {
                    "listed_sym": listed_sym,
                    "listing_date": ts,
                    "entry_ts": entry_ts,
                    "exit_ts": exit_ts,
                    "sym": sym,
                    "log_return": log_ret,
                    "era": _era_of(ts),
                    "quarter": _quarter_of(ts),
                    "btc_30d_ret": float(btc_val) if np.isfinite(btc_val) else np.nan,
                }
            )
    df = pd.DataFrame(rows)
    log.info("built %d observations across %d events", len(df), df["listing_date"].nunique() if len(df) else 0)
    return df


def _build_candidate_pool(caches: Dict[str, pd.DataFrame], n_target: int = 60000) -> np.ndarray:
    """Build a random pool of gross 5d log-returns across all syms/times
    for the fee-aware perm null. Sampled uniformly across each sym's history."""
    rng = np.random.default_rng(1234)
    hold_min = HOLD_DAYS * 24 * 60
    per_sym_quota = max(1, n_target // len(caches))
    out: List[float] = []
    for sym, df in caches.items():
        n = len(df)
        if n <= hold_min + 10:
            continue
        opens = df["open"].values
        closes = df["close"].values
        max_start = n - hold_min - 1
        starts = rng.integers(0, max_start, size=per_sym_quota)
        for s in starts:
            o = opens[s]
            c = closes[s + hold_min]
            if o <= 0 or c <= 0 or not np.isfinite(o) or not np.isfinite(c):
                continue
            out.append(float(np.log(c / o)))
    arr = np.array(out, dtype=float)
    log.info("candidate pool: %d gross 5d log-returns", len(arr))
    return arr


def _three_gate(
    net_returns: np.ndarray,
    pool_gross: np.ndarray,
    label: str,
    n_perms: int = 1000,
    n_boot: int = 2000,
) -> Dict[str, float]:
    """Compute fee_aware_perm + bootstrap + gate verdict for one quadrant."""
    if len(net_returns) < 30:
        return {
            "label": label,
            "n": int(len(net_returns)),
            "mean_bp": float(net_returns.mean() * 1e4) if len(net_returns) else 0.0,
            "obs_t": 0.0,
            "signal_t_excess": float("nan"),
            "perm_p_two_sided": float("nan"),
            "ci_lower_bp": float("nan"),
            "ci_upper_bp": float("nan"),
            "prob_positive": float("nan"),
            "gate_pass": False,
            "gate_reason": f"n<30 ({len(net_returns)})",
        }
    fee_res = fee_aware_perm_test(
        observed_net_returns=net_returns.tolist(),
        candidate_pool_returns=pool_gross.tolist(),
        fee_per_trade=FEE,
        n_perms=n_perms,
        rng_seed=42,
    )
    boot = bootstrap_ci(net_returns.tolist(), n_boot=n_boot, block_size=5, rng_seed=42)
    signal_excess = fee_res.get("signal_t_excess", float("nan"))
    perm_p = fee_res.get("perm_p_two_sided", float("nan"))
    ci_lower = boot.get("ci_lower", float("nan"))
    ci_upper = boot.get("ci_upper", float("nan"))
    gate_pass = (
        np.isfinite(signal_excess)
        and np.isfinite(perm_p)
        and np.isfinite(ci_lower)
        and signal_excess >= 2.0
        and ci_lower > 0
        and perm_p <= 0.10
    )
    return {
        "label": label,
        "n": int(len(net_returns)),
        "mean_bp": float(net_returns.mean() * 1e4),
        "obs_t": float(fee_res.get("obs_t", 0.0)),
        "null_mean_t": float(fee_res.get("null_mean_t", float("nan"))),
        "signal_t_excess": float(signal_excess),
        "perm_p_two_sided": float(perm_p),
        "ci_lower_bp": float(ci_lower * 1e4),
        "ci_upper_bp": float(ci_upper * 1e4),
        "prob_positive": float(boot.get("prob_positive", float("nan"))),
        "gate_pass": bool(gate_pass),
    }


def _concentration(observations: pd.DataFrame, direction: int) -> Dict[str, object]:
    """Per-symbol bootstrap and per-quarter t-stat under a fixed direction."""
    # Net return per obs = direction * log_return - FEE
    df = observations.copy()
    df["net_ret"] = direction * df["log_return"] - FEE

    # per-symbol
    sym_stats: Dict[str, Dict[str, float]] = {}
    n_syms_ci_pos = 0
    n_syms_measured = 0
    for sym, grp in df.groupby("sym"):
        arr = grp["net_ret"].values
        if len(arr) < 30:
            sym_stats[sym] = {"n": int(len(arr)), "mean_bp": float(arr.mean() * 1e4) if len(arr) else 0.0, "ci_lower_bp": float("nan"), "ci_pos": False}
            continue
        b = bootstrap_ci(arr.tolist(), n_boot=1000, block_size=5, rng_seed=42)
        ci_lower_bp = float(b["ci_lower"] * 1e4)
        ci_pos = ci_lower_bp > 0
        if ci_pos:
            n_syms_ci_pos += 1
        n_syms_measured += 1
        sym_stats[sym] = {
            "n": int(len(arr)),
            "mean_bp": float(arr.mean() * 1e4),
            "ci_lower_bp": ci_lower_bp,
            "ci_upper_bp": float(b["ci_upper"] * 1e4),
            "ci_pos": bool(ci_pos),
        }

    syms_ci_pos_ratio = n_syms_ci_pos / n_syms_measured if n_syms_measured else 0.0

    # per-quarter
    q_stats: Dict[str, Dict[str, float]] = {}
    n_q_measured = 0
    n_q_pos_t = 0
    for q, grp in df.groupby("quarter"):
        arr = grp["net_ret"].values
        if len(arr) < 20:
            continue
        sd = arr.std(ddof=1)
        if sd == 0 or not np.isfinite(sd):
            continue
        t = float(arr.mean() / sd * np.sqrt(len(arr)))
        q_stats[q] = {"n": int(len(arr)), "mean_bp": float(arr.mean() * 1e4), "t_stat": t}
        n_q_measured += 1
        if t > 0:
            n_q_pos_t += 1

    q_pos_t_ratio = n_q_pos_t / n_q_measured if n_q_measured else 0.0

    conc_pass = (
        q_pos_t_ratio >= 0.5
        and syms_ci_pos_ratio >= 0.30
        and n_syms_ci_pos >= 3
    )

    return {
        "direction": direction,
        "n_obs": int(len(df)),
        "per_sym": sym_stats,
        "n_syms_measured": int(n_syms_measured),
        "n_syms_ci_pos": int(n_syms_ci_pos),
        "syms_ci_pos_ratio": float(syms_ci_pos_ratio),
        "per_quarter": q_stats,
        "n_quarters_measured": int(n_q_measured),
        "n_quarters_pos_t": int(n_q_pos_t),
        "q_pos_t_ratio": float(q_pos_t_ratio),
        "concentration_pass": bool(conc_pass),
    }


def _era_stratify(observations: pd.DataFrame, direction: int) -> Dict[str, Dict[str, float]]:
    df = observations.copy()
    df["net_ret"] = direction * df["log_return"] - FEE
    out: Dict[str, Dict[str, float]] = {}
    for era, grp in df.groupby("era"):
        arr = grp["net_ret"].values
        if len(arr) < 20:
            out[era] = {"n": int(len(arr)), "mean_bp": float(arr.mean() * 1e4) if len(arr) else 0.0, "t_stat": float("nan")}
            continue
        sd = arr.std(ddof=1)
        t = float(arr.mean() / sd * np.sqrt(len(arr))) if sd > 0 else float("nan")
        out[era] = {
            "n": int(len(arr)),
            "mean_bp": float(arr.mean() * 1e4),
            "t_stat": t,
        }
    return out


def _run() -> Dict[str, object]:
    t0 = time.time()

    caches = _load_cache()
    if not caches:
        raise RuntimeError("no OHLCV caches loaded")

    btc_daily = _daily_close(caches["BTCUSDT"])
    btc_30d = _btc_30d_return(btc_daily)

    events = _load_events()
    events = _debounce_events(events)

    obs = _build_observations(caches, events, btc_30d)
    if len(obs) < 100:
        raise RuntimeError(f"insufficient observations: {len(obs)}")

    obs_path = OUT_DIR / "observations.parquet"
    try:
        obs.to_parquet(obs_path)
    except Exception as e:
        log.warning("parquet dump failed: %s (falling back to csv)", e)
        obs.to_csv(OUT_DIR / "observations.csv", index=False)

    pool_gross = _build_candidate_pool(caches, n_target=60000)

    # ============ 4-QUADRANT SNT ============
    quadrants = {}

    # A_focus: LONG, all events
    a_focus_net = obs["log_return"].values - FEE  # +1 dir
    quadrants["A_focus_long_all_events"] = _three_gate(a_focus_net, pool_gross, "A_focus_long_all")

    # A_mirror: SHORT, all events
    a_mirror_net = -obs["log_return"].values - FEE
    quadrants["A_mirror_short_all_events"] = _three_gate(a_mirror_net, pool_gross, "A_mirror_short_all")

    # B_focus: LONG, bear-BTC-regime listings only (btc_30d_ret < 0)
    bear_mask = obs["btc_30d_ret"] < 0
    b_focus_net = obs.loc[bear_mask, "log_return"].values - FEE
    quadrants["B_focus_long_bear_btc"] = _three_gate(b_focus_net, pool_gross, "B_focus_long_bear")

    # B_mirror: SHORT, bear-BTC-regime listings
    b_mirror_net = -obs.loc[bear_mask, "log_return"].values - FEE
    quadrants["B_mirror_short_bear_btc"] = _three_gate(b_mirror_net, pool_gross, "B_mirror_short_bear")

    # C: LONG, bull-BTC-regime listings only (btc_30d_ret >= 0)  -- extra diagnostic cell
    bull_mask = obs["btc_30d_ret"] >= 0
    c_long_bull_net = obs.loc[bull_mask, "log_return"].values - FEE
    quadrants["C_long_bull_btc"] = _three_gate(c_long_bull_net, pool_gross, "C_long_bull")
    c_short_bull_net = -obs.loc[bull_mask, "log_return"].values - FEE
    quadrants["C_short_bull_btc"] = _three_gate(c_short_bull_net, pool_gross, "C_short_bull")

    # ============ Concentration diagnostics ============
    conc_long_all = _concentration(obs, direction=+1)
    conc_short_all = _concentration(obs, direction=-1)

    # ============ Era stratify (P1 alpha decay) ============
    era_long = _era_stratify(obs, direction=+1)
    era_short = _era_stratify(obs, direction=-1)

    # ============ Verdict ============
    any_gate_pass = any(v.get("gate_pass") for v in quadrants.values())
    conc_pass_at_signal = None
    if quadrants["A_focus_long_all_events"].get("gate_pass"):
        conc_pass_at_signal = conc_long_all["concentration_pass"]
        verdict_dir = "long"
    elif quadrants["A_mirror_short_all_events"].get("gate_pass"):
        conc_pass_at_signal = conc_short_all["concentration_pass"]
        verdict_dir = "short"
    else:
        verdict_dir = None

    verdict = "FAIL"
    if any_gate_pass:
        if conc_pass_at_signal is True:
            verdict = "PASS"
        elif conc_pass_at_signal is False:
            verdict = "CONCENTRATED_R1_PASS"
        else:
            verdict = "PARTIAL_PASS_NEEDS_REVIEW"
    else:
        # broad falsification: all 4 SNT quadrants have gate_pass False
        broad_fail = all(not quadrants[k].get("gate_pass") for k in ["A_focus_long_all_events", "A_mirror_short_all_events", "B_focus_long_bear_btc", "B_mirror_short_bear_btc"])
        if broad_fail:
            verdict = "BROAD_FALSIFIED"
        else:
            verdict = "FAIL"

    metrics = {
        "paradigm_number": PARADIGM_NUMBER,
        "paradigm_name": PARADIGM_NAME,
        "phase": "R-1",
        "hold_days": HOLD_DAYS,
        "entry_lag_hours": ENTRY_LAG_HOURS,
        "debounce_days": DEBOUNCE_DAYS,
        "fee_round_trip": FEE,
        "cutoff_date": CUTOFF_DATE,
        "n_events": int(obs["listing_date"].nunique()),
        "n_events_bear_btc": int(obs.loc[bear_mask, "listing_date"].nunique()),
        "n_events_bull_btc": int(obs.loc[bull_mask, "listing_date"].nunique()),
        "n_observations": int(len(obs)),
        "candidate_pool_n": int(len(pool_gross)),
        "quadrants": quadrants,
        "concentration": {
            "long_all_events": conc_long_all,
            "short_all_events": conc_short_all,
        },
        "era_stratify": {
            "long": era_long,
            "short": era_short,
        },
        "verdict_direction": verdict_dir,
        "r1_verdict": verdict,
        "runtime_sec": round(time.time() - t0, 2),
    }

    (OUT_DIR / "r1__metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    log.info("R-1 verdict: %s (%.1fs)", verdict, metrics["runtime_sec"])
    return metrics


if __name__ == "__main__":
    _run()
