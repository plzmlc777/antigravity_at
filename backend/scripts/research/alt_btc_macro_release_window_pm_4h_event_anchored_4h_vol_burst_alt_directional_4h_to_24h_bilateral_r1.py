"""paradigm 218 R-1 PoC.

slug: alt_btc_macro_release_window_pm_4h_event_anchored_4h_vol_burst_alt_directional_4h_to_24h_bilateral

Hypothesis (paradigm-architect Option E direct recommend):
US macro release calendar event window-anchored vol burst paradigm,
reformulated at BTC 4h granularity to fit available substrate.

  - timing anchor: FOMC + CPI release timestamps (~20 events/yr), ±4h window
  - trigger: BTC 4h realized vol (close-to-close abs return, 30-day rolling p90 spike)
              measured at the first BTC 4h bar containing the release
  - direction: BTC 4h directional sign at release window (UP=hawkish, DOWN=dovish)
  - forward: 13 alts × hold 4h primary, plus 8h / 12h / 24h sweep
  - 4-quadrant SNT bilateral (Lesson #19):
        A_focus  : vol spike × BTC UP × LONG  (continuation)
        A_mirror : vol spike × BTC UP × SHORT (reversal)
        B_same   : vol spike × BTC DOWN × SHORT (continuation, DISJOINT trigger set)
        B_mirror : vol spike × BTC DOWN × LONG (reversal, Lesson #42 20th dogfood)

Substrate:
  - Fed.gov calendar.json (FOMC release timestamps, government public) +
    curated 2023/2024 fill from federalreserve.gov press archive
  - BLS published CPI release schedule (advance + historical, government public)
  - Binance 4h joblib cache 819d (2024-02-01 → 2026-04-30, paradigm 69 R-5 LIVE substrate)

R-1 STRICT scope: NO R-2 auto-promote. graveyard or PASS verdict only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm218_r1")

# -------------------- constants --------------------
SLUG = "alt_btc_macro_release_window_pm_4h_event_anchored_4h_vol_burst_alt_directional_4h_to_24h_bilateral"
PARADIGM_ID = 218
OUT_DIR = ROOT / "runs" / "research_track" / SLUG
CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"
FEE_PER_TRADE = 0.0008  # 8 bp round-trip Binance taker

ALTS = [
    "ETHUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "BNBUSDT", "FILUSDT", "LTCUSDT",
    "NEARUSDT", "XRPUSDT", "DOTUSDT",
]
BTC = "BTCUSDT"

# FOMC release timestamps — Fed.gov calendar.json + curated 2023/2024
# 2:00 p.m. ET (statement release) = 19:00 UTC (EDT/EST timezone normalisation;
# Fed schedules in ET, conversion below uses fixed 18:00 UTC during EST and
# 18:00 UTC during EDT — the 4-hour window absorbs the 1h DST shift so we use
# 19:00 UTC year-round as the conservative window center).
# Sources:
#   - 2025-2026: Fed.gov calendar.json (public)
#   - 2024: federalreserve.gov/monetarypolicy/fomccalendars.htm (historical record)
#   - 2023 partial (only window 2024-02-01+ matters per BTC cache):
#     not needed (BTC cache starts 2024-02-01)
FOMC_RELEASES = [
    # 2024
    "2024-01-31 19:00", "2024-03-20 18:00", "2024-05-01 18:00", "2024-06-12 18:00",
    "2024-07-31 18:00", "2024-09-18 18:00", "2024-11-07 19:00", "2024-12-18 19:00",
    # 2025 (Fed.gov calendar.json)
    "2025-01-29 19:00", "2025-03-19 18:00", "2025-05-07 18:00", "2025-06-18 18:00",
    "2025-07-30 18:00", "2025-09-17 18:00", "2025-10-29 18:00", "2025-12-10 19:00",
    # 2026 (Fed.gov calendar.json, only meetings before cache end 2026-04-30)
    "2026-01-28 19:00", "2026-03-18 18:00", "2026-04-29 18:00",
]

# CPI release timestamps — BLS published schedule
# 8:30 a.m. ET (release) = 13:30 UTC (EDT) / 13:30 UTC (EST)
# (release time is 8:30 ET; use 13:30 UTC conservatively).
# Sources: BLS news release schedule (public government calendar archive)
CPI_RELEASES = [
    # 2024
    "2024-02-13 13:30", "2024-03-12 12:30", "2024-04-10 12:30", "2024-05-15 12:30",
    "2024-06-12 12:30", "2024-07-11 12:30", "2024-08-14 12:30", "2024-09-11 12:30",
    "2024-10-10 12:30", "2024-11-13 13:30", "2024-12-11 13:30",
    # 2025
    "2025-01-15 13:30", "2025-02-12 13:30", "2025-03-12 12:30", "2025-04-10 12:30",
    "2025-05-13 12:30", "2025-06-11 12:30", "2025-07-15 12:30", "2025-08-12 12:30",
    "2025-09-11 12:30", "2025-10-15 12:30", "2025-11-13 13:30", "2025-12-10 13:30",
    # 2026 (BLS advance schedule)
    "2026-01-14 13:30", "2026-02-11 13:30", "2026-03-11 12:30", "2026-04-10 12:30",
]


def parse_events(raw: list[str]) -> pd.DatetimeIndex:
    return pd.to_datetime(raw, utc=False)


def load_cache(sym: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{sym}_4h.joblib"
    if not path.exists():
        raise FileNotFoundError(path)
    df = joblib.load(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df[["open", "high", "low", "close", "volume"]].dropna()


def compute_btc_features(btc: pd.DataFrame, vol_window: int = 30 * 6) -> pd.DataFrame:
    """30d rolling p90 of |4h log returns|. vol_window=180 4h bars = 30d."""
    out = btc.copy()
    out["ret_4h"] = np.log(out["close"]).diff()
    out["abs_ret"] = out["ret_4h"].abs()
    # 30-day rolling p90
    out["abs_ret_p90_30d"] = out["abs_ret"].rolling(window=vol_window, min_periods=vol_window // 2).quantile(0.90)
    out["vol_spike"] = out["abs_ret"] >= out["abs_ret_p90_30d"]
    out["btc_dir"] = np.sign(out["ret_4h"]).fillna(0).astype(int)
    return out


def align_events_to_bars(events: pd.DatetimeIndex, bar_index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Find first 4h bar whose start ≥ event timestamp. 4h bars start at 00, 04, 08, 12, 16, 20 UTC."""
    aligned = []
    for ev in events:
        # find smallest bar start time >= event
        future = bar_index[bar_index >= ev]
        if len(future) == 0:
            continue
        aligned.append(future[0])
    return pd.DatetimeIndex(aligned).unique().sort_values()


def compute_forward_return(df: pd.DataFrame, entry_idx: pd.DatetimeIndex, hold_bars: int) -> pd.Series:
    """For each entry timestamp, compute (close_{t+hold_bars} - open_{t}) / open_{t}.

    Entry at open of bar at entry_idx, exit at close of bar at entry_idx + hold_bars - 1.
    """
    out = {}
    bar_positions = df.index.get_indexer(entry_idx)
    closes = df["close"].values
    opens = df["open"].values
    n = len(df)
    for ev, pos in zip(entry_idx, bar_positions):
        if pos < 0:
            continue
        exit_pos = pos + hold_bars - 1
        if exit_pos >= n:
            continue
        op = opens[pos]
        cl = closes[exit_pos]
        if not (op > 0 and cl > 0):
            continue
        out[ev] = (cl - op) / op
    return pd.Series(out)


def evaluate_cell(
    label: str,
    observed_net: np.ndarray,
    candidate_pool: np.ndarray,
    fee: float = FEE_PER_TRADE,
) -> dict:
    """Run fee-aware perm + bootstrap CI."""
    if len(observed_net) < 2:
        return {
            "cell": label,
            "n_obs": int(len(observed_net)),
            "verdict": "INSUFFICIENT_N",
        }
    perm = fee_aware_perm_test(
        observed_net_returns=observed_net,
        candidate_pool_returns=candidate_pool,
        fee_per_trade=fee,
        n_perms=1000,
    )
    ci = bootstrap_ci(observed_net, n_boot=2000, block_size=1)
    out = {
        "cell": label,
        "n_obs": int(len(observed_net)),
        "obs_mean_bp": float(np.mean(observed_net) * 1e4),
        "obs_t": float(perm.get("obs_t", float("nan"))),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "perm_p_two_sided": float(perm.get("perm_p_two_sided", float("nan"))),
        "ci_lower_bp": float(ci.get("ci_lower", float("nan"))) * 1e4,
        "ci_upper_bp": float(ci.get("ci_upper", float("nan"))) * 1e4,
        "prob_positive": float(ci.get("prob_positive", float("nan"))),
    }
    # 3-gate
    three_gate = (
        out["signal_t_excess"] >= 2.0
        and out["ci_lower_bp"] > 0
        and out["perm_p_two_sided"] <= 0.10
    )
    out["three_gate_pass"] = bool(three_gate)
    return out


def run_one_hold(
    btc: pd.DataFrame,
    alts: dict[str, pd.DataFrame],
    event_bars: pd.DatetimeIndex,
    hold_bars: int,
    fee: float = FEE_PER_TRADE,
) -> dict:
    """For one hold horizon, compute 4-cell SNT + per-cell key numbers."""
    # filter event bars to those where vol_spike == True at the BTC entry bar
    btc_at_event = btc.loc[btc.index.isin(event_bars)]
    spike_mask = btc_at_event["vol_spike"].fillna(False)
    spike_bars = btc_at_event.index[spike_mask]
    btc_dir_at_spike = btc_at_event.loc[spike_bars, "btc_dir"]
    up_bars = spike_bars[btc_dir_at_spike > 0]
    dn_bars = spike_bars[btc_dir_at_spike < 0]

    # Build candidate pool: forward returns at ALL 4h bars per sym (gross)
    pool_per_sym = {}
    for sym, df in alts.items():
        # all hold-window returns starting at every available bar
        op = df["open"].values
        cl = df["close"].values
        n = len(df)
        if n < hold_bars + 1:
            continue
        # vectorised: forward gross return for entries at index i, exit at i+hold_bars-1
        valid = np.arange(0, n - hold_bars)
        rets = (cl[valid + hold_bars - 1] - op[valid]) / op[valid]
        pool_per_sym[sym] = rets[np.isfinite(rets)]
    full_pool = np.concatenate(list(pool_per_sym.values())) if pool_per_sym else np.array([])

    # Build observed trades per cell
    def gather(entry_bars: pd.DatetimeIndex, direction_sign: int) -> tuple[np.ndarray, dict]:
        """direction_sign: +1 = LONG, -1 = SHORT."""
        per_sym_obs = {}
        rows = []
        for sym, df in alts.items():
            fwd = compute_forward_return(df, entry_bars, hold_bars)
            if fwd.empty:
                continue
            net = direction_sign * fwd.values - fee
            per_sym_obs[sym] = net
            rows.append(net)
        if not rows:
            return np.array([]), per_sym_obs
        return np.concatenate(rows), per_sym_obs

    cells = {
        "A_focus":  ("LONG_after_UP_spike",   up_bars, +1),
        "A_mirror": ("SHORT_after_UP_spike",  up_bars, -1),
        "B_same":   ("SHORT_after_DN_spike",  dn_bars, -1),
        "B_mirror": ("LONG_after_DN_spike",   dn_bars, +1),
    }
    results = {"hold_bars": hold_bars, "hold_hours": hold_bars * 4}
    results["n_event_bars"] = int(len(event_bars))
    results["n_event_bars_with_spike"] = int(len(spike_bars))
    results["n_up_spike"] = int(len(up_bars))
    results["n_dn_spike"] = int(len(dn_bars))
    cell_results = {}
    per_sym_per_cell = {}
    for code, (desc, entry_bars, sign) in cells.items():
        net, per_sym_obs = gather(entry_bars, sign)
        cell_eval = evaluate_cell(f"{code}_{desc}", net, full_pool, fee)
        cell_eval["desc"] = desc
        cell_results[code] = cell_eval
        per_sym_per_cell[code] = per_sym_obs
    results["cells"] = cell_results
    results["_per_sym_per_cell_internal"] = per_sym_per_cell
    return results


def concentration_per_sym(per_sym_obs: dict[str, np.ndarray]) -> dict:
    """Bootstrap CI per symbol; report fraction with ci_lower > 0."""
    syms_ci_pos = []
    sym_stats = {}
    for sym, arr in per_sym_obs.items():
        if len(arr) < 2:
            continue
        ci = bootstrap_ci(arr, n_boot=1000, block_size=1)
        ci_lo_bp = ci.get("ci_lower", float("nan")) * 1e4
        sym_stats[sym] = {
            "n": int(len(arr)),
            "mean_bp": float(np.mean(arr) * 1e4),
            "ci_lower_bp": float(ci_lo_bp),
            "ci_pos": bool(ci_lo_bp > 0),
        }
        if ci_lo_bp > 0:
            syms_ci_pos.append(sym)
    n_meas = len(sym_stats)
    return {
        "n_syms_measurable": n_meas,
        "n_syms_ci_pos": len(syms_ci_pos),
        "syms_ci_pos": syms_ci_pos,
        "ratio_ci_pos": (len(syms_ci_pos) / n_meas) if n_meas else 0.0,
        "per_sym": sym_stats,
    }


def quarterly_t(per_sym_obs: dict[str, np.ndarray], entry_bars: pd.DatetimeIndex) -> dict:
    """Per-quarter t-stat across pooled cell trades."""
    # need to recover entries per trade; we approximate by binning per sym
    # For SNT cells the entries are entry_bars (same across syms); use quarter labels
    quarters = pd.Series(entry_bars).dt.to_period("Q").astype(str).tolist()
    pooled_by_q = {}
    for sym, arr in per_sym_obs.items():
        if len(arr) != len(quarters):
            # length mismatch (some entries lacked forward in df); skip per-quarter for this sym
            continue
        for q, v in zip(quarters, arr):
            pooled_by_q.setdefault(q, []).append(v)
    q_stats = {}
    for q, vals in pooled_by_q.items():
        v = np.asarray(vals, dtype=float)
        if len(v) < 2:
            continue
        sd = v.std(ddof=1)
        t = float(v.mean() / sd * np.sqrt(len(v))) if sd > 0 else float("nan")
        q_stats[q] = {"n": len(v), "mean_bp": float(v.mean() * 1e4), "t": t}
    n_q = len(q_stats)
    n_pos_t = sum(1 for s in q_stats.values() if (s["t"] is not None and s["t"] > 0))
    return {
        "n_quarters": n_q,
        "n_pos_t": n_pos_t,
        "ratio_pos_t": (n_pos_t / n_q) if n_q else 0.0,
        "per_quarter": q_stats,
    }


def era_stratify(per_sym_obs: dict[str, np.ndarray], entry_bars: pd.DatetimeIndex) -> dict:
    """Decompose pooled returns by era 2024 / 2025 / 2026 (Pattern P1 audit)."""
    years = pd.Series(entry_bars).dt.year.tolist()
    pooled_by_y = {}
    for sym, arr in per_sym_obs.items():
        if len(arr) != len(years):
            continue
        for y, v in zip(years, arr):
            pooled_by_y.setdefault(int(y), []).append(v)
    out = {}
    for y, vals in sorted(pooled_by_y.items()):
        v = np.asarray(vals, dtype=float)
        if len(v) < 2:
            out[str(y)] = {"n": int(len(v)), "verdict": "INSUFFICIENT_N"}
            continue
        sd = v.std(ddof=1)
        t = float(v.mean() / sd * np.sqrt(len(v))) if sd > 0 else float("nan")
        out[str(y)] = {
            "n": int(len(v)),
            "mean_bp": float(v.mean() * 1e4),
            "t": t,
        }
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(OUT_DIR / "r1__metrics.json"))
    args = p.parse_args()

    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- substrate audit ----
    log.info("[setup] loading BTC + 13 alts 4h cache (819d substrate)")
    btc = load_cache(BTC)
    alts = {sym: load_cache(sym) for sym in ALTS}
    log.info("BTC bars=%d span=%s -> %s", len(btc), btc.index[0], btc.index[-1])

    # ---- compute BTC features ----
    btc_feat = compute_btc_features(btc, vol_window=180)
    log.info("[btc_features] vol p90 rolling 30d (180 bars), spike_rate=%.3f",
             btc_feat["vol_spike"].mean())

    # ---- assemble events ----
    fomc_dt = parse_events(FOMC_RELEASES)
    cpi_dt = parse_events(CPI_RELEASES)
    all_events = pd.DatetimeIndex(sorted(set(fomc_dt) | set(cpi_dt)))
    # filter to BTC cache span
    cache_start = btc.index[0]
    cache_end = btc.index[-1]
    in_span = all_events[(all_events >= cache_start) & (all_events <= cache_end)]
    log.info("[events] FOMC=%d CPI=%d total_unique_in_span=%d (span %s → %s)",
             len(fomc_dt), len(cpi_dt), len(in_span), cache_start, cache_end)
    # align to bar starts
    event_bars = align_events_to_bars(in_span, btc.index)
    log.info("[events] aligned to 4h bars = %d", len(event_bars))

    # ---- unconditional baseline (Lesson #39 sub-class B) ----
    # No filter at all: every 4h bar entry, no direction filter
    log.info("[baseline] computing unconditional BTC dir UP / DN continuation t-stat")
    baseline_results = {}
    for hold_bars in (1, 2, 3, 6):  # 4h, 8h, 12h, 24h
        # All BTC bars where dir != 0
        all_bars = btc.index
        for dir_label, dir_filter in [("UP", btc_feat["btc_dir"] > 0), ("DN", btc_feat["btc_dir"] < 0)]:
            entry_bars_unc = btc.index[dir_filter.values]
            for cell_label, sign in [("LONG", +1), ("SHORT", -1)]:
                pooled_rows = []
                for sym, df in alts.items():
                    fwd = compute_forward_return(df, entry_bars_unc, hold_bars)
                    if fwd.empty:
                        continue
                    net = sign * fwd.values - FEE_PER_TRADE
                    pooled_rows.append(net)
                if not pooled_rows:
                    continue
                pooled = np.concatenate(pooled_rows)
                if len(pooled) < 2:
                    continue
                sd = pooled.std(ddof=1)
                t_ = float(pooled.mean() / sd * np.sqrt(len(pooled))) if sd > 0 else float("nan")
                key = f"unconditional_BTC_{dir_label}_{cell_label}_hold{hold_bars*4}h"
                baseline_results[key] = {
                    "n": int(len(pooled)),
                    "mean_bp": float(pooled.mean() * 1e4),
                    "t": t_,
                }

    # ---- 4-quadrant SNT per hold horizon ----
    log.info("[SNT] running 4 holds × 4 quadrants")
    hold_results = {}
    for hb in (1, 2, 3, 6):  # 4h, 8h, 12h, 24h
        log.info("  hold = %d bars (%d h)", hb, hb * 4)
        res = run_one_hold(btc_feat, alts, event_bars, hb)
        hold_results[f"hold{hb*4}h"] = res

    # ---- diagnostics on PRIMARY hold (4h) ----
    primary = hold_results["hold4h"]
    primary_per_sym = primary.pop("_per_sym_per_cell_internal", {})
    diagnostics = {}
    btc_at_event = btc_feat.loc[btc_feat.index.isin(event_bars)]
    spike_mask = btc_at_event["vol_spike"].fillna(False)
    spike_bars = btc_at_event.index[spike_mask]
    btc_dir_spike = btc_at_event.loc[spike_bars, "btc_dir"]
    up_bars = spike_bars[btc_dir_spike > 0]
    dn_bars = spike_bars[btc_dir_spike < 0]
    cell_to_entry = {
        "A_focus": up_bars,
        "A_mirror": up_bars,
        "B_same": dn_bars,
        "B_mirror": dn_bars,
    }
    for code, per_sym_obs in primary_per_sym.items():
        # Need per_sym_obs aligned to entry_bars to do quarterly + era stratify
        # gather raw forward returns per sym + apply direction
        diagnostics[code] = {
            "concentration": concentration_per_sym(per_sym_obs),
            "quarterly": quarterly_t(per_sym_obs, cell_to_entry[code]),
            "era_stratify": era_stratify(per_sym_obs, cell_to_entry[code]),
        }
    # remove _per_sym_per_cell_internal from other holds too
    for hb_key, res in hold_results.items():
        res.pop("_per_sym_per_cell_internal", None)

    # ---- cross-set asymmetry (Item 7) ----
    cross_set = {
        "n_up_spike": int(len(up_bars)),
        "n_dn_spike": int(len(dn_bars)),
        "ratio_up_over_dn": (len(up_bars) / max(1, len(dn_bars))),
        "ratio_dn_over_up": (len(dn_bars) / max(1, len(up_bars))),
    }

    # ---- Lesson #42 20th dogfood (B_mirror) ----
    bm_eval = primary["cells"]["B_mirror"]
    lesson_42_20th = {
        "B_mirror_obs_t": bm_eval.get("obs_t"),
        "B_mirror_signal_t_excess": bm_eval.get("signal_t_excess"),
        "B_mirror_ci_lower_bp": bm_eval.get("ci_lower_bp"),
        "B_mirror_three_gate_pass": bm_eval.get("three_gate_pass"),
        "chain_position": 20,
        "chain_3tier_before": "10 CONFIRMED / 8 NEGATIVE / 1 PASS_AS_ARTIFACT",
    }

    # ---- final verdict ----
    cell_verdicts = {code: c["three_gate_pass"] for code, c in primary["cells"].items()
                     if "three_gate_pass" in c}
    any_pass = any(cell_verdicts.values())
    # Full hold×cell sweep PASS scan (Lesson #37)
    sweep_pass_cells = []
    for hb_key, hb_res in hold_results.items():
        for code, ce in hb_res["cells"].items():
            if ce.get("three_gate_pass"):
                sweep_pass_cells.append(f"{hb_key}/{code}")

    if not any_pass and not sweep_pass_cells:
        # Check if all cells fee-floor broad-falsified
        all_obs_means = [c.get("obs_mean_bp") for c in primary["cells"].values()
                         if "obs_mean_bp" in c]
        all_broad_neg = all(m is not None and m < 0 for m in all_obs_means)
        if all_broad_neg:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
        else:
            verdict = "R1_FAIL_NO_THREE_GATE"
    elif sweep_pass_cells:
        verdict = "R1_PASS_SWEEP_CELL"
    else:
        verdict = "R1_PASS_PRIMARY"

    summary = {
        "paradigm_id": PARADIGM_ID,
        "slug": SLUG,
        "phase": "R-1",
        "fee_per_trade": FEE_PER_TRADE,
        "n_universe": len(ALTS),
        "btc_cache_span_days": int((btc.index[-1] - btc.index[0]).days),
        "event_count": {
            "fomc_raw": len(fomc_dt),
            "cpi_raw": len(cpi_dt),
            "events_in_span": len(in_span),
            "event_bars_aligned": len(event_bars),
            "events_with_vol_spike": int(len(spike_bars)),
            "up_spike": int(len(up_bars)),
            "dn_spike": int(len(dn_bars)),
        },
        "cross_set_asymmetry": cross_set,
        "primary_4h_cells": {code: {k: v for k, v in c.items()
                                    if not isinstance(v, dict)}
                             for code, c in primary["cells"].items()},
        "hold_sweep": hold_results,
        "concentration_quarterly_era_per_cell": diagnostics,
        "unconditional_baseline": baseline_results,
        "lesson_42_20th_dogfood": lesson_42_20th,
        "sweep_pass_cells": sweep_pass_cells,
        "verdict": verdict,
        "wall_time_s": round(time.time() - t0, 1),
    }

    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info("[done] verdict=%s wall=%.1fs out=%s",
             verdict, summary["wall_time_s"], args.out)
    print(json.dumps({
        "verdict": verdict,
        "n_events_aligned": len(event_bars),
        "n_up_spike": int(len(up_bars)),
        "n_dn_spike": int(len(dn_bars)),
        "primary_cells": {c: (v.get("obs_mean_bp"), v.get("signal_t_excess"),
                              v.get("ci_lower_bp"), v.get("three_gate_pass"))
                          for c, v in primary["cells"].items() if "obs_mean_bp" in v},
        "sweep_pass_cells": sweep_pass_cells,
        "out": args.out,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
