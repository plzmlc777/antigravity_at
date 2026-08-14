"""R-1 PoC — alt_crypto_options_expiry_gamma_unwind_bilateral_4h.

Hypothesis
----------
Weekly Deribit crypto options expiry (Friday 08:00 UTC) causes gamma-hedge
unwinding: MM delta-hedge in perp futures pre-expiry is removed instantly
at expiry, producing a REVERSAL of the pre-expiry 8h trend in the 4-8h
post-expiry window.

R-1 Design
----------
Anchor: every Friday 08:00 UTC from 2024-01-05 to 2026-05-09 (in-data range).
Symbols: 14-alt cohort (BTC + 13 alts).

Signal: sign(pre_ret_8h) where pre_ret_8h = log(close[T]/close[T-8h])
Prediction: contrarian to pre-trend.
  A_focus: pre-trend UP → SHORT next 4h  (test reversal down)
  B_focus: pre-trend DOWN → LONG next 4h (test reversal up)
Mirror (Lesson #19 SNT):
  A_mirror: pre-trend UP → LONG (test whether trend continues)
  B_mirror: pre-trend DOWN → SHORT (test whether trend continues)

Only report focus quadrants for 3-gate primary; mirror is diagnostic.

Sample density
--------------
Fridays in [2024-01-05, 2026-05-09] ≈ 122 events × 14 syms = 1708 obs.
Sign split expected ~50/50 → ~854 per quadrant → per-quadrant » 30 floor.

Gates (Lesson #16 Concentration mandatory)
------------------------------------------
Three-gate: signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p <= 0.10
Concentration: quarter_pos_t_ratio >= 0.5 AND symbol_ci_pos_ratio >= 0.30
              AND n_symbols_ci_pos >= 3.

Output
------
backend/runs/research_track/alt_crypto_options_expiry_gamma_unwind_bilateral_4h/
    r1__metrics.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("options_expiry_r1")

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "runs" / "ohlcv_cache"
OUT_DIR = ROOT / "runs" / "research_track" / "alt_crypto_options_expiry_gamma_unwind_bilateral_4h"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "BNBUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "FILUSDT", "NEARUSDT", "WIFUSDT",
]

FEE_ROUND_TRIP = 0.0008  # 8 bp per trade round-trip (Binance perp taker+taker)
PRE_WINDOW_H = 8
POST_HOLD_H = 4  # primary
POST_HOLD_ALT = [4, 8]  # sweep
DATA_START = pd.Timestamp("2024-01-05")
DATA_END = pd.Timestamp("2026-05-09")


def _load_symbol(sym: str) -> pd.DataFrame:
    fp = CACHE_DIR / f"{sym}_1m.joblib"
    if not fp.exists():
        log.warning("missing cache for %s at %s", sym, fp)
        return pd.DataFrame()
    df = joblib.load(fp)
    if df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    # normalize to naive UTC (data is naive; treat as UTC)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    return df[["close"]].astype(float).sort_index()


def _build_expiry_calendar() -> pd.DatetimeIndex:
    """All Fridays at 08:00 UTC within data range."""
    fridays = pd.date_range(start="2024-01-05", end="2026-05-09", freq="W-FRI")
    stamps = fridays + pd.Timedelta(hours=8)
    return pd.DatetimeIndex(stamps)


def _close_at(df: pd.DataFrame, ts: pd.Timestamp) -> float:
    """Get close price at or just before ts (1m bars)."""
    if df.empty:
        return float("nan")
    idx = df.index.searchsorted(ts, side="right") - 1
    if idx < 0 or idx >= len(df):
        return float("nan")
    return float(df["close"].iloc[idx])


def _returns_at_events(
    df: pd.DataFrame,
    events: pd.DatetimeIndex,
    pre_h: int,
    post_h: int,
) -> pd.DataFrame:
    """For each event T: compute (pre_ret over [T-pre_h,T], post_ret over [T,T+post_h])."""
    rows = []
    for T in events:
        c_pre = _close_at(df, T - pd.Timedelta(hours=pre_h))
        c_at = _close_at(df, T)
        c_post = _close_at(df, T + pd.Timedelta(hours=post_h))
        if not (np.isfinite(c_pre) and np.isfinite(c_at) and np.isfinite(c_post)):
            continue
        if c_pre <= 0 or c_at <= 0 or c_post <= 0:
            continue
        pre_ret = np.log(c_at / c_pre)
        post_ret = np.log(c_post / c_at)
        rows.append({"event_ts": T, "pre_ret": pre_ret, "post_ret": post_ret})
    return pd.DataFrame(rows)


def _quadrant_returns(
    df_events: pd.DataFrame,
    direction_when_up: int,
    direction_when_down: int,
) -> np.ndarray:
    """Return per-trade NET returns for the specified quadrant configuration.

    direction_when_up: +1 long, -1 short, 0 skip (for pre_ret > 0)
    direction_when_down: analogous for pre_ret < 0
    """
    net = []
    for _, row in df_events.iterrows():
        pre = row["pre_ret"]
        post = row["post_ret"]
        if pre > 0 and direction_when_up != 0:
            gross = direction_when_up * post
            net.append(gross - FEE_ROUND_TRIP)
        elif pre < 0 and direction_when_down != 0:
            gross = direction_when_down * post
            net.append(gross - FEE_ROUND_TRIP)
    return np.asarray(net, dtype=float)


def _per_quarter_t(per_event_records: List[dict]) -> Dict[str, float]:
    """t-stat per calendar quarter across all symbols (for Concentration Gate).

    per_event_records: list of {'event_ts', 'net_ret'} for the focus quadrant.
    """
    if not per_event_records:
        return {"n_quarters_measurable": 0, "n_quarters_pos_t": 0, "quarter_pos_t_ratio": 0.0, "detail": {}}
    df = pd.DataFrame(per_event_records)
    df["quarter"] = df["event_ts"].dt.to_period("Q").astype(str)
    detail: Dict[str, float] = {}
    n_meas = 0
    n_pos = 0
    for q, sub in df.groupby("quarter"):
        arr = sub["net_ret"].values
        if len(arr) < 5:
            detail[q] = None
            continue
        sd = arr.std(ddof=1)
        if sd == 0 or not np.isfinite(sd):
            detail[q] = None
            continue
        t = float(arr.mean() / sd * np.sqrt(len(arr)))
        detail[q] = t
        n_meas += 1
        if t > 0:
            n_pos += 1
    ratio = n_pos / n_meas if n_meas else 0.0
    return {
        "n_quarters_measurable": n_meas,
        "n_quarters_pos_t": n_pos,
        "quarter_pos_t_ratio": ratio,
        "detail": detail,
    }


def _per_symbol_ci(per_symbol_returns: Dict[str, np.ndarray]) -> Dict[str, object]:
    """Bootstrap CI per symbol for the focus quadrant."""
    detail: Dict[str, dict] = {}
    n_meas = 0
    n_ci_pos = 0
    for sym, arr in per_symbol_returns.items():
        if len(arr) < 5:
            detail[sym] = {"n": len(arr), "ci_lower_bp": None, "ci_pos": False}
            continue
        ci = bootstrap_ci(arr, n_boot=1000, block_size=1, rng_seed=17)
        cl_bp = ci["ci_lower"] * 1e4
        pos = bool(ci["ci_lower"] > 0)
        detail[sym] = {
            "n": len(arr),
            "mean_bp": ci["mean"] * 1e4,
            "ci_lower_bp": cl_bp,
            "ci_upper_bp": ci["ci_upper"] * 1e4,
            "ci_pos": pos,
        }
        n_meas += 1
        if pos:
            n_ci_pos += 1
    ratio = n_ci_pos / n_meas if n_meas else 0.0
    return {
        "n_symbols_measurable": n_meas,
        "n_symbols_ci_pos": n_ci_pos,
        "symbol_ci_pos_ratio": ratio,
        "detail": detail,
    }


def _evaluate_quadrant(
    name: str,
    per_sym_events: Dict[str, pd.DataFrame],
    direction_up: int,
    direction_down: int,
    candidate_pool_returns: np.ndarray,
) -> dict:
    """Full evaluation for one quadrant: aggregate stats + per-quarter + per-symbol."""
    all_net: List[float] = []
    per_symbol_returns: Dict[str, np.ndarray] = {}
    per_event_records: List[dict] = []

    for sym, df_ev in per_sym_events.items():
        if df_ev.empty:
            per_symbol_returns[sym] = np.array([])
            continue
        rets = []
        for _, row in df_ev.iterrows():
            pre = row["pre_ret"]
            post = row["post_ret"]
            if pre > 0 and direction_up != 0:
                net = direction_up * post - FEE_ROUND_TRIP
                rets.append(net)
                per_event_records.append({"event_ts": row["event_ts"], "net_ret": net})
            elif pre < 0 and direction_down != 0:
                net = direction_down * post - FEE_ROUND_TRIP
                rets.append(net)
                per_event_records.append({"event_ts": row["event_ts"], "net_ret": net})
        per_symbol_returns[sym] = np.asarray(rets, dtype=float)
        all_net.extend(rets)

    all_arr = np.asarray(all_net, dtype=float)
    n = len(all_arr)
    if n < 30:
        return {
            "quadrant": name,
            "n": n,
            "verdict": "INSUFFICIENT_N",
            "obs_mean_bp": float(all_arr.mean() * 1e4) if n else 0.0,
        }

    # Three gates
    perm = fee_aware_perm_test(
        observed_net_returns=all_arr,
        candidate_pool_returns=candidate_pool_returns,
        fee_per_trade=FEE_ROUND_TRIP,
        n_perms=1000,
        rng_seed=42,
    )
    ci = bootstrap_ci(all_arr, n_boot=2000, block_size=1, rng_seed=13)

    signal_t_excess = perm["signal_t_excess"]
    ci_lower = ci["ci_lower"]
    perm_p = perm["perm_p_one_sided_above"]

    pass_three = (
        signal_t_excess >= 2.0
        and ci_lower > 0
        and perm_p <= 0.10
    )

    # Concentration diagnostics
    quarter = _per_quarter_t(per_event_records)
    symbol = _per_symbol_ci(per_symbol_returns)

    conc_pass = (
        quarter["quarter_pos_t_ratio"] >= 0.5
        and symbol["symbol_ci_pos_ratio"] >= 0.30
        and symbol["n_symbols_ci_pos"] >= 3
    )

    if pass_three and conc_pass:
        verdict = "PASS"
    elif pass_three and not conc_pass:
        verdict = "CONCENTRATED_R1_PASS"
    else:
        verdict = "FAIL"

    return {
        "quadrant": name,
        "n": n,
        "obs_mean_bp": float(all_arr.mean() * 1e4),
        "obs_t": perm["obs_t"],
        "null_mean_t": perm["null_mean_t"],
        "signal_t_excess": signal_t_excess,
        "perm_p_one_sided_above": perm_p,
        "ci_lower_bp": ci_lower * 1e4,
        "ci_upper_bp": ci["ci_upper"] * 1e4,
        "prob_positive": ci["prob_positive"],
        "three_gate_pass": pass_three,
        "concentration": {
            "quarter": quarter,
            "symbol": symbol,
            "concentration_gate_pass": conc_pass,
        },
        "verdict": verdict,
    }


def main() -> None:
    events = _build_expiry_calendar()
    log.info("expiry events: %d (%s to %s)", len(events), events[0], events[-1])

    per_sym_events: Dict[str, pd.DataFrame] = {}
    per_sym_pool: Dict[str, np.ndarray] = {}

    for sym in SYMBOLS:
        df = _load_symbol(sym)
        if df.empty:
            log.warning("skip %s: empty", sym)
            continue
        # Restrict events to symbol coverage
        sym_first, sym_last = df.index[0], df.index[-1]
        ev_ok = events[
            (events >= sym_first + pd.Timedelta(hours=PRE_WINDOW_H))
            & (events <= sym_last - pd.Timedelta(hours=POST_HOLD_H))
        ]
        rec = _returns_at_events(df, ev_ok, PRE_WINDOW_H, POST_HOLD_H)
        per_sym_events[sym] = rec
        log.info("%-10s events=%d pre_ret_p50=%.4f post_ret_p50=%.4f",
                 sym, len(rec),
                 float(np.median(rec["pre_ret"])) if len(rec) else float("nan"),
                 float(np.median(rec["post_ret"])) if len(rec) else float("nan"))

        # Candidate pool: 4h forward returns sampled across all bars at 30m stride
        # (proxy for "any 4h window" fee-drift null)
        stride_min = 30
        if len(df) > POST_HOLD_H * 60 + stride_min:
            close = df["close"].values
            step = stride_min
            hold_bars = POST_HOLD_H * 60
            starts = np.arange(0, len(df) - hold_bars - 1, step)
            rets = np.log(close[starts + hold_bars] / close[starts])
            per_sym_pool[sym] = rets

    all_events_df = pd.concat([
        df.assign(symbol=sym) for sym, df in per_sym_events.items() if not df.empty
    ], ignore_index=True) if per_sym_events else pd.DataFrame()
    log.info("total event obs across syms: %d", len(all_events_df))

    # Candidate pool: concat across all symbols
    if per_sym_pool:
        candidate_pool = np.concatenate([arr for arr in per_sym_pool.values() if len(arr) > 0])
    else:
        candidate_pool = np.array([])
    log.info("candidate pool size: %d", len(candidate_pool))

    # Four quadrants (Lesson #19 SNT)
    quadrants = {
        "A_focus_shortUp_and_zero": (-1, 0),      # pre_UP → SHORT (reversal test)
        "B_focus_zero_and_longDown": (0, +1),      # pre_DOWN → LONG (reversal test)
        "A_mirror_longUp_and_zero": (+1, 0),       # pre_UP → LONG (continuation test)
        "B_mirror_zero_and_shortDown": (0, -1),    # pre_DOWN → SHORT (continuation test)
    }

    results = {}
    for qname, (du, dd) in quadrants.items():
        r = _evaluate_quadrant(qname, per_sym_events, du, dd, candidate_pool)
        results[qname] = r
        log.info("quadrant %-32s n=%d obs_t=%.3f signal_t_excess=%.3f ci_lower_bp=%.2f perm_p=%.3f verdict=%s",
                 qname, r["n"],
                 r.get("obs_t", 0.0),
                 r.get("signal_t_excess", 0.0),
                 r.get("ci_lower_bp", 0.0),
                 r.get("perm_p_one_sided_above", 1.0),
                 r["verdict"])

    # Combined bilateral focus (A_focus + B_focus pooled as single strategy)
    bilateral_records: List[dict] = []
    bilateral_per_sym: Dict[str, list] = {sym: [] for sym in per_sym_events}
    for sym, df_ev in per_sym_events.items():
        for _, row in df_ev.iterrows():
            pre = row["pre_ret"]; post = row["post_ret"]
            if pre > 0:
                net = -1 * post - FEE_ROUND_TRIP
            elif pre < 0:
                net = +1 * post - FEE_ROUND_TRIP
            else:
                continue
            bilateral_records.append({"event_ts": row["event_ts"], "net_ret": net, "sym": sym})
            bilateral_per_sym[sym].append(net)

    bilateral_arr = np.asarray([r["net_ret"] for r in bilateral_records], dtype=float)
    log.info("bilateral focus pooled n=%d obs_mean_bp=%.2f",
             len(bilateral_arr),
             float(bilateral_arr.mean() * 1e4) if len(bilateral_arr) else float("nan"))

    if len(bilateral_arr) >= 30:
        b_perm = fee_aware_perm_test(bilateral_arr, candidate_pool, FEE_ROUND_TRIP, 1000, 42)
        b_ci = bootstrap_ci(bilateral_arr, n_boot=2000, block_size=1, rng_seed=13)
        b_quarter = _per_quarter_t(bilateral_records)
        b_symbol = _per_symbol_ci({sym: np.asarray(v, dtype=float) for sym, v in bilateral_per_sym.items()})
        b_three_gate = (
            b_perm["signal_t_excess"] >= 2.0
            and b_ci["ci_lower"] > 0
            and b_perm["perm_p_one_sided_above"] <= 0.10
        )
        b_conc = (
            b_quarter["quarter_pos_t_ratio"] >= 0.5
            and b_symbol["symbol_ci_pos_ratio"] >= 0.30
            and b_symbol["n_symbols_ci_pos"] >= 3
        )
        bilateral_result = {
            "n": len(bilateral_arr),
            "obs_mean_bp": float(bilateral_arr.mean() * 1e4),
            "obs_t": b_perm["obs_t"],
            "signal_t_excess": b_perm["signal_t_excess"],
            "perm_p_one_sided_above": b_perm["perm_p_one_sided_above"],
            "ci_lower_bp": b_ci["ci_lower"] * 1e4,
            "ci_upper_bp": b_ci["ci_upper"] * 1e4,
            "three_gate_pass": b_three_gate,
            "concentration": {
                "quarter": b_quarter,
                "symbol": b_symbol,
                "concentration_gate_pass": b_conc,
            },
            "verdict": (
                "PASS" if (b_three_gate and b_conc)
                else "CONCENTRATED_R1_PASS" if b_three_gate else "FAIL"
            ),
        }
    else:
        bilateral_result = {"n": len(bilateral_arr), "verdict": "INSUFFICIENT_N"}

    # Sweep post_hold in [4, 8] (single symbol pooled) for context
    sweep_results = {}
    for hold_h in POST_HOLD_ALT:
        rec_list = []
        for sym in per_sym_events:
            df = _load_symbol(sym)
            if df.empty:
                continue
            ev_ok = events[
                (events >= df.index[0] + pd.Timedelta(hours=PRE_WINDOW_H))
                & (events <= df.index[-1] - pd.Timedelta(hours=hold_h))
            ]
            r = _returns_at_events(df, ev_ok, PRE_WINDOW_H, hold_h)
            for _, row in r.iterrows():
                pre = row["pre_ret"]; post = row["post_ret"]
                if pre > 0:
                    rec_list.append(-1 * post - FEE_ROUND_TRIP)
                elif pre < 0:
                    rec_list.append(+1 * post - FEE_ROUND_TRIP)
        arr = np.asarray(rec_list, dtype=float)
        if len(arr) >= 30:
            perm = fee_aware_perm_test(arr, candidate_pool, FEE_ROUND_TRIP, 500, 42)
            ci = bootstrap_ci(arr, n_boot=1000, block_size=1, rng_seed=13)
            sweep_results[f"post_hold_{hold_h}h"] = {
                "n": len(arr),
                "obs_mean_bp": float(arr.mean() * 1e4),
                "signal_t_excess": perm["signal_t_excess"],
                "perm_p_one_sided_above": perm["perm_p_one_sided_above"],
                "ci_lower_bp": ci["ci_lower"] * 1e4,
                "three_gate_pass": (
                    perm["signal_t_excess"] >= 2.0
                    and ci["ci_lower"] > 0
                    and perm["perm_p_one_sided_above"] <= 0.10
                ),
            }
        else:
            sweep_results[f"post_hold_{hold_h}h"] = {"n": len(arr), "verdict": "INSUFFICIENT_N"}

    out = {
        "paradigm": "alt_crypto_options_expiry_gamma_unwind_bilateral_4h",
        "phase": "R-1",
        "config": {
            "symbols": SYMBOLS,
            "pre_window_h": PRE_WINDOW_H,
            "post_hold_h_primary": POST_HOLD_H,
            "fee_round_trip": FEE_ROUND_TRIP,
            "n_expiry_events": int(len(events)),
            "data_range": [str(DATA_START), str(DATA_END)],
        },
        "quadrants": results,
        "bilateral_focus_pooled": bilateral_result,
        "sweep_post_hold": sweep_results,
        "gates_definition": {
            "three_gate": "signal_t_excess>=2.0 AND ci_lower>0 AND perm_p_one_sided_above<=0.10",
            "concentration_gate": "quarter_pos_t_ratio>=0.5 AND symbol_ci_pos_ratio>=0.30 AND n_symbols_ci_pos>=3",
        },
    }

    out_fp = OUT_DIR / "r1__metrics.json"
    out_fp.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", out_fp)

    # Compact console summary
    print("=== R-1 SUMMARY ===")
    print(f"events={len(events)} pool_size={len(candidate_pool)}")
    for qname, r in results.items():
        print(f"  {qname:34s} n={r['n']:4d} exc={r.get('signal_t_excess', 0):.2f} "
              f"cil_bp={r.get('ci_lower_bp', 0):.2f} p={r.get('perm_p_one_sided_above', 1):.3f} "
              f"→ {r['verdict']}")
    if "verdict" in bilateral_result and bilateral_result["verdict"] != "INSUFFICIENT_N":
        print(f"  BILATERAL_POOLED                    n={bilateral_result['n']:4d} "
              f"exc={bilateral_result['signal_t_excess']:.2f} cil_bp={bilateral_result['ci_lower_bp']:.2f} "
              f"p={bilateral_result['perm_p_one_sided_above']:.3f} → {bilateral_result['verdict']}")


if __name__ == "__main__":
    main()
