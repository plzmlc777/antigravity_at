"""R-1 PoC — taker_buy_volume_5m_zscore_signcond.

Hypothesis (single sentence)
----------------------------
Per-symbol 5m taker-buy quote volume z-score (30-bar window) >= +2.0 spikes,
filtered to BTC up-regime (BTC 1h return > 0 at trigger), produce LONG alpha
on the same alt over a 60m hold window — an info-flow / aggressive-buyer-
imbalance momentum signal.

Mechanism distinction (Q3 §6.2 #9 antipattern check)
----------------------------------------------------
- This is a STANDALONE first-derivative volume info-flow signal.
- NOT borrowing paradigm 69 vol-cascade filter (no BTC RV trigger).
- NOT graveyard 23 (TBS ratio raw): we use a volume-weighted proxy and
  z-score it (event detection vs continuous ratio indicator).
- NOT graveyard 60 (LSR contrarian): LONG continuation direction, volume
  origin, not position-balance.
- BTC up-regime sign filter is to avoid paradigm-67 sign-cancellation.

Data plumbing note (read carefully)
-----------------------------------
The microstructure joblib (5m, 1.5yr) on Mint contains
`taker_buy_sell_ratio` but NOT raw `taker_buy_quote_volume` /
`taker_buy_base_asset_volume`. Postgres ohlcv table also has only `volume`
(total). We construct a proxy:

    taker_buy_quote_vol_5m  ≈  taker_buy_share_5m × total_quote_vol_5m
    where  taker_buy_share = ratio / (1 + ratio)
       and total_quote_vol_5m ≈ Σ(close_1m × volume_1m) over the 5m bin.

This is mathematically the implied taker buy quote volume given the only
two inputs available; it has the desired absolute-magnitude property
(signal weighted by abs flow, not just ratio extremity).

Trigger
-------
- For each alt sym independently:
  - resample 1m ohlcv to 5m: total_quote_vol_5m
  - join with microstructure 5m taker_buy_sell_ratio (inner)
  - compute taker_buy_share = ratio / (1 + ratio)  (both finite, ratio ≥ 0)
  - implied_tbq_vol = taker_buy_share × total_quote_vol_5m
  - z-score over rolling 30-bar window (= 150 minutes)
  - rising-edge: z[t] >= Z AND z[t-1] < Z  for Z in {1.5, 2.0, 2.5}
  - 30m per-sym cooldown
- Sign-conditional filter: keep only triggers where BTC 1h return at the
  trigger 5m bar is > 0 (BTC up regime). H5 diagnostic also reports
  unfiltered (all triggers).

Trade construction
------------------
- Entry: alt close at trigger 5m bar end + 1m
- Exit:  alt close at entry + 60m
- Direction: +1 (LONG)
- Net = gross - 8e-4 (round-trip fee)

Three-gate criteria
-------------------
For the BTC-up-filtered pool at each Z:
  - signal_t_excess >= 2.0
  - bootstrap_ci.ci_lower > 0
  - perm_p_two_sided <= 0.10
ALL three required for PASS.

Architect early-termination rule (handoff fee_floor_prescreen)
--------------------------------------------------------------
After trigger build at Z=2.0 (default) BEFORE running perm/bootstrap:
  if pre-sign-cond first-pass mean |return| <= 5 bp,
    abort — write GRAVEYARD verdict, save metrics with reason
    "estimate_level_subfee", do NOT spend compute on perm/bootstrap.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)
from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tbv_signcond_r1")

PARADIGM = "taker_buy_volume_5m_zscore_signcond"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"
MICRO_DIR = ROOT / "runs" / "microstructure"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Trigger config
Z_WINDOW = 30        # 30 5m-bars = 150 minutes rolling
Z_GRID = [1.5, 2.0, 2.5]
Z_DEFAULT = 2.0
COOLDOWN_MIN = 30    # per-sym
HOLD_MIN = 60        # 60-minute LONG hold
FEE_RT = 8e-4
EARLY_TERM_BP = 5.0  # |mean_bp| <= 5 -> graveyard early at Z_DEFAULT

# Stat config
PERM_N = 1000
BOOT_N = 2000
SEED = 42

# BTC sign filter window
BTC_RET_WINDOW_MIN = 60  # BTC 1h return > 0 at trigger


# ---------- data loading ----------


def load_microstructure_5m(sym: str) -> pd.DataFrame:
    p = MICRO_DIR / f"{sym}_full_metrics.joblib"
    if not p.exists():
        return pd.DataFrame()
    df = joblib.load(p)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def build_5m_quote_vol_from_1m(ohlcv_1m: pd.DataFrame) -> pd.Series:
    """Aggregate 1m close*vol into 5m quote volume bins, indexed at bin start."""
    if ohlcv_1m.empty:
        return pd.Series(dtype=float)
    qv1 = ohlcv_1m["close"].astype(float) * ohlcv_1m["volume"].astype(float)
    qv5 = qv1.resample("5min", label="left", closed="left").sum()
    return qv5.dropna()


def build_btc_1h_ret(btc_1m: pd.DataFrame) -> pd.Series:
    """BTC 1h return from 1m closes, computed at every minute."""
    close = btc_1m["close"].astype(float)
    ret = close / close.shift(BTC_RET_WINDOW_MIN) - 1
    return ret.dropna()


# ---------- signal & triggers ----------


def build_per_sym_signal(sym: str, ohlcv_1m: pd.DataFrame) -> pd.DataFrame:
    """Returns DataFrame indexed by 5m bin start with cols:
        ratio, qv5, taker_buy_share, implied_tbq, z
    """
    micro = load_microstructure_5m(sym)
    if micro.empty:
        log.warning("[%s] microstructure missing", sym)
        return pd.DataFrame()
    if "taker_buy_sell_ratio" not in micro.columns:
        log.warning("[%s] no taker_buy_sell_ratio col", sym)
        return pd.DataFrame()
    qv5 = build_5m_quote_vol_from_1m(ohlcv_1m)
    if qv5.empty:
        return pd.DataFrame()

    # microstructure index is 5m boundaries (e.g., 00:05, 00:10, ...).
    # Our resampled qv5 has labels at left-edge (00:00, 00:05, ...).
    # We want to align: the 5m bin starting at HH:00 has microstructure
    # ratio captured at HH:05 (end of bin). Shift ratio to align with
    # bin-start index: ratio_at_bin_start = ratio.shift(-1) is wrong because
    # we need the ratio that was CAPTURED OVER that 5m window. The micro
    # row at 00:05 represents the just-closed window 00:00-00:05. So we
    # shift the index back 5 minutes to align with bin-start.
    ratio = micro["taker_buy_sell_ratio"].copy()
    ratio.index = ratio.index - pd.Timedelta(minutes=5)
    df = pd.DataFrame({"ratio": ratio, "qv5": qv5}).dropna()
    if df.empty:
        return pd.DataFrame()
    # taker_buy_share in [0, 1]
    df["taker_buy_share"] = df["ratio"] / (1.0 + df["ratio"])
    df["implied_tbq"] = df["taker_buy_share"] * df["qv5"]

    mu = df["implied_tbq"].rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    sd = df["implied_tbq"].rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    df["z"] = (df["implied_tbq"] - mu) / sd
    return df.dropna(subset=["z"])


def find_triggers(sig_df: pd.DataFrame, z_thresh: float) -> pd.DatetimeIndex:
    """Rising-edge z>=z_thresh, with COOLDOWN_MIN per-sym cooldown."""
    z = sig_df["z"]
    z_prev = z.shift(1)
    fire_mask = (z >= z_thresh) & (z_prev < z_thresh)
    candidates = sig_df.index[fire_mask]
    if len(candidates) == 0:
        return candidates
    keep = []
    last_t = None
    for ts in candidates:
        if last_t is None:
            keep.append(ts)
            last_t = ts
            continue
        delta_min = (ts - last_t).total_seconds() / 60.0
        if delta_min >= COOLDOWN_MIN:
            keep.append(ts)
            last_t = ts
    return pd.DatetimeIndex(keep)


# ---------- trade execution ----------


def compute_long_returns(close_1m: pd.Series, trig_5m_starts: pd.DatetimeIndex,
                         hold_min: int) -> np.ndarray:
    """LONG returns. Entry at (trigger_5m_start + 5m + 1m) close, exit + hold_min."""
    out = np.full(len(trig_5m_starts), np.nan)
    pos = {ts: i for i, ts in enumerate(close_1m.index)}
    arr = close_1m.to_numpy()
    for i, ts in enumerate(trig_5m_starts):
        # trigger 5m bin starts at ts, ends at ts+5m. First entry candle
        # close is the bar after the trigger close (ts + 5m + 1m).
        entry_ts = ts + pd.Timedelta(minutes=6)
        exit_ts = entry_ts + pd.Timedelta(minutes=hold_min)
        ei = pos.get(entry_ts)
        xi = pos.get(exit_ts)
        if ei is None or xi is None:
            continue
        ep = arr[ei]
        xp = arr[xi]
        if ep > 0 and not np.isnan(ep) and not np.isnan(xp):
            out[i] = xp / ep - 1.0
    return out


def all_forward_long_returns_60m(close_1m: pd.Series) -> np.ndarray:
    """Candidate pool: every possible 60m forward return."""
    arr = close_1m.to_numpy()
    n = len(arr)
    if n <= HOLD_MIN + 2:
        return np.array([])
    entry = arr[: n - HOLD_MIN]
    exit_ = arr[HOLD_MIN:]
    ret = exit_ / entry - 1
    valid = np.isfinite(ret) & (entry > 0)
    return ret[valid]


# ---------- stats ----------


def t_stat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan")
    sd = np.std(x, ddof=1)
    if sd == 0:
        return float("nan")
    return float(np.mean(x) / (sd / np.sqrt(len(x))))


def summarize(arr: np.ndarray) -> dict:
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {"n": 0}
    return {
        "n": int(len(arr)),
        "mean_bp": float(np.mean(arr) * 1e4),
        "median_bp": float(np.median(arr) * 1e4),
        "std_bp": float(np.std(arr, ddof=1) * 1e4) if len(arr) > 1 else float("nan"),
        "t_stat": t_stat(arr),
        "win_rate": float(np.mean(arr > 0)),
    }


# ---------- main ----------


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("== R-1 PoC: %s ==", PARADIGM)
    t_start = time.time()

    # Mint host explicit check (handoff #6)
    log.info("loading BTC 1m ohlcv (cached) ...")
    btc_1m = load_ohlcv_1m_cached(BTC)
    log.info("BTC 1m bars: %d (range %s -> %s)",
             len(btc_1m), btc_1m.index.min(), btc_1m.index.max())
    if len(btc_1m) < 1_000_000:
        log.error("BTC bars < 1M -- abort, expected ~1.24M on Mint")
        return 2

    btc_1h_ret = build_btc_1h_ret(btc_1m)
    log.info("BTC 1h return series: %d obs", len(btc_1h_ret))

    # Per-sym triggers + per-z accumulators
    per_sym_diag = {}
    per_z_observed_signed = {z: [] for z in Z_GRID}
    per_z_observed_unsigned = {z: [] for z in Z_GRID}
    per_z_per_sym = {z: {} for z in Z_GRID}
    per_z_n_total = {z: 0 for z in Z_GRID}
    per_z_n_signed = {z: 0 for z in Z_GRID}

    for sym in ALTS:
        log.info("--- %s ---", sym)
        ohlcv_1m = load_ohlcv_1m_cached(sym)
        if ohlcv_1m.empty:
            log.warning("[%s] no 1m ohlcv", sym)
            per_sym_diag[sym] = {"status": "no_ohlcv"}
            continue
        sig_df = build_per_sym_signal(sym, ohlcv_1m)
        if sig_df.empty:
            log.warning("[%s] no signal", sym)
            per_sym_diag[sym] = {"status": "no_signal"}
            continue
        log.info("[%s] signal bars: %d, range %s -> %s",
                 sym, len(sig_df), sig_df.index.min(), sig_df.index.max())
        per_sym_diag[sym] = {
            "status": "ok",
            "n_signal_bars": int(len(sig_df)),
            "z_range": [float(sig_df["z"].min()), float(sig_df["z"].max())],
            "per_z": {},
        }

        # close series for trade execution
        close_1m = ohlcv_1m["close"].astype(float)

        for z_thresh in Z_GRID:
            trigs = find_triggers(sig_df, z_thresh)
            if len(trigs) == 0:
                per_sym_diag[sym]["per_z"][str(z_thresh)] = {"n_trig": 0}
                continue

            rets_unsigned = compute_long_returns(close_1m, trigs, HOLD_MIN)
            valid_mask = ~np.isnan(rets_unsigned)
            n_valid_unsigned = int(valid_mask.sum())

            # BTC sign filter: BTC 1h return > 0 at trigger 5m bin start
            # The BTC return is at minute t; we look up the BTC return at
            # the trigger timestamp itself (5m boundary).
            btc_signs = []
            for ts in trigs:
                v = btc_1h_ret.get(ts, np.nan)
                btc_signs.append(v)
            btc_signs = np.asarray(btc_signs, dtype=float)
            up_mask = (btc_signs > 0) & valid_mask
            n_signed = int(up_mask.sum())

            rets_signed = rets_unsigned[up_mask]

            per_z_observed_unsigned[z_thresh].extend(rets_unsigned[valid_mask].tolist())
            per_z_observed_signed[z_thresh].extend(rets_signed.tolist())
            per_z_n_total[z_thresh] += n_valid_unsigned
            per_z_n_signed[z_thresh] += n_signed

            net_signed = rets_signed - FEE_RT
            per_z_per_sym[z_thresh][sym] = {
                "n_trig_total": int(len(trigs)),
                "n_valid": n_valid_unsigned,
                "n_signed": n_signed,
                "mean_bp_signed_net": float(np.mean(net_signed) * 1e4) if n_signed >= 2 else None,
                "t_stat_signed_net": t_stat(net_signed) if n_signed >= 2 else None,
                "mean_bp_unsigned_net": (
                    float(np.mean(rets_unsigned[valid_mask] - FEE_RT) * 1e4)
                    if n_valid_unsigned >= 2 else None
                ),
            }
            per_sym_diag[sym]["per_z"][str(z_thresh)] = {
                "n_trig": int(len(trigs)),
                "n_valid": n_valid_unsigned,
                "n_signed": n_signed,
            }
            log.info("[%s] z=%s: n_trig=%d n_valid=%d n_signed=%d",
                     sym, z_thresh, len(trigs), n_valid_unsigned, n_signed)

    # ============================================================
    # H1 — early-term pre-screen at Z_DEFAULT (UNSIGNED first-pass)
    # ============================================================
    log.info("== early-term pre-screen at z=%.1f (UNSIGNED) ==", Z_DEFAULT)
    pre_unsigned = np.asarray(per_z_observed_unsigned[Z_DEFAULT], dtype=float)
    if len(pre_unsigned) >= 2:
        pre_net = pre_unsigned - FEE_RT
        pre_mean_bp = float(np.mean(pre_net) * 1e4)
        pre_t = t_stat(pre_net)
        log.info("  n=%d unsigned net mean=%.2fbp t=%.3f", len(pre_net), pre_mean_bp, pre_t)
    else:
        pre_mean_bp = float("nan")
        pre_t = float("nan")
        log.warning("  insufficient pre-screen sample n=%d", len(pre_unsigned))

    early_term = False
    if np.isfinite(pre_mean_bp) and abs(pre_mean_bp) <= EARLY_TERM_BP:
        early_term = True
        log.warning("  EARLY-TERM TRIGGERED: |mean_bp|=%.2f <= %.1f. Skipping perm/bootstrap.",
                    abs(pre_mean_bp), EARLY_TERM_BP)

    # ============================================================
    # H2 — full per-z perm + bootstrap on SIGNED pool (skip if early-term)
    # ============================================================
    per_z_results = {}

    if not early_term:
        log.info("building candidate pool (60m forward returns over all 13 alts) ...")
        candidate_pool = []
        for sym in ALTS:
            ohlcv_1m = load_ohlcv_1m_cached(sym)
            if ohlcv_1m.empty:
                continue
            close_1m = ohlcv_1m["close"].astype(float)
            fwd = all_forward_long_returns_60m(close_1m)
            candidate_pool.extend(fwd.tolist())
        log.info("  candidate pool size: %d", len(candidate_pool))

        for z_thresh in Z_GRID:
            log.info("== H2: perm + bootstrap @ z=%.1f ==", z_thresh)
            obs_signed = np.asarray(per_z_observed_signed[z_thresh], dtype=float)
            obs_unsigned = np.asarray(per_z_observed_unsigned[z_thresh], dtype=float)

            entry = {
                "z_thresh": z_thresh,
                "n_total_unsigned": int(len(obs_unsigned)),
                "n_signed_btc_up": int(len(obs_signed)),
                "unsigned_summary_net": summarize(obs_unsigned - FEE_RT) if len(obs_unsigned) else {"n": 0},
                "signed_summary_net": summarize(obs_signed - FEE_RT) if len(obs_signed) else {"n": 0},
            }

            if len(obs_signed) < 30:
                log.warning("  insufficient signed sample n=%d, skipping perm", len(obs_signed))
                entry["fee_aware_perm"] = {"error": "n_signed < 30"}
                entry["bootstrap_ci"] = {"error": "n_signed < 30"}
                entry["three_gate_verdict"] = "FAIL"
                entry["three_gate_reason"] = f"insufficient signed sample n={len(obs_signed)}"
                per_z_results[str(z_thresh)] = entry
                continue

            obs_signed_net = obs_signed - FEE_RT
            log.info("  signed pool n=%d, fee_aware_perm n=%d ...", len(obs_signed_net), PERM_N)
            fee_perm = fee_aware_perm_test(
                observed_net_returns=obs_signed_net.tolist(),
                candidate_pool_returns=candidate_pool,
                fee_per_trade=FEE_RT,
                n_perms=PERM_N,
                rng_seed=SEED,
            )
            log.info("    obs_t=%.3f null_mean_t=%.3f sig_t_excess=%.3f perm_p_two=%.4f perm_p_above=%.4f",
                     fee_perm["obs_t"], fee_perm["null_mean_t"],
                     fee_perm["signal_t_excess"], fee_perm["perm_p_two_sided"],
                     fee_perm["perm_p_one_sided_above"])

            log.info("  bootstrap_ci n=%d block=%d ...", BOOT_N, HOLD_MIN)
            ci = bootstrap_ci(
                observed_net_returns=obs_signed_net.tolist(),
                n_boot=BOOT_N,
                block_size=HOLD_MIN,
                rng_seed=SEED,
            )
            log.info("    ci.mean=%.6f lower=%.6f upper=%.6f prob_pos=%.3f",
                     ci["mean"], ci["ci_lower"], ci["ci_upper"], ci["prob_positive"])

            # Three-gate
            g1 = (np.isfinite(fee_perm.get("signal_t_excess", float("nan")))
                  and fee_perm["signal_t_excess"] >= 2.0)
            g2 = (np.isfinite(ci.get("ci_lower", float("nan")))
                  and ci["ci_lower"] > 0.0)
            g3 = (np.isfinite(fee_perm.get("perm_p_two_sided", float("nan")))
                  and fee_perm["perm_p_two_sided"] <= 0.10)
            verdict = "PASS" if (g1 and g2 and g3) else "FAIL"
            failed = []
            if not g1: failed.append("signal_t_excess<2.0")
            if not g2: failed.append("ci_lower<=0")
            if not g3: failed.append("perm_p_two_sided>0.10")

            entry["fee_aware_perm"] = fee_perm
            entry["bootstrap_ci"] = ci
            entry["three_gate_verdict"] = verdict
            entry["three_gate_reason"] = "; ".join(failed) if failed else "all gates passed"
            per_z_results[str(z_thresh)] = entry

    else:
        # early-term: just record the per-z observed summary stats
        for z_thresh in Z_GRID:
            obs_signed = np.asarray(per_z_observed_signed[z_thresh], dtype=float)
            obs_unsigned = np.asarray(per_z_observed_unsigned[z_thresh], dtype=float)
            per_z_results[str(z_thresh)] = {
                "z_thresh": z_thresh,
                "n_total_unsigned": int(len(obs_unsigned)),
                "n_signed_btc_up": int(len(obs_signed)),
                "unsigned_summary_net": summarize(obs_unsigned - FEE_RT) if len(obs_unsigned) else {"n": 0},
                "signed_summary_net": summarize(obs_signed - FEE_RT) if len(obs_signed) else {"n": 0},
                "three_gate_verdict": "EARLY_TERM_SKIP",
                "three_gate_reason": "pre-screen unsigned |mean_bp| <= 5",
            }

    # ============================================================
    # Per-symbol flag (mean_bp > 20bp + t > 1.5 in signed pool at Z_DEFAULT)
    # ============================================================
    flagged_syms = []
    for sym, info in per_z_per_sym[Z_DEFAULT].items():
        m = info.get("mean_bp_signed_net")
        t = info.get("t_stat_signed_net")
        if m is not None and t is not None and m > 20.0 and t > 1.5:
            flagged_syms.append({"sym": sym, "mean_bp": m, "t_stat": t,
                                 "n_signed": info["n_signed"]})

    # ============================================================
    # Final verdict
    # ============================================================
    verdicts_per_z = {z: per_z_results[z]["three_gate_verdict"] for z in per_z_results}
    any_pass = any(v == "PASS" for v in verdicts_per_z.values())
    if early_term:
        final_verdict = "GRAVEYARD"
        final_reason = (f"estimate_level_subfee: pre-sign-cond unsigned mean = "
                        f"{pre_mean_bp:.2f}bp (<=5bp threshold), perm/bootstrap skipped to save compute")
        recommendation = "graveyard now"
    elif any_pass:
        final_verdict = "PASS"
        passing = [z for z, v in verdicts_per_z.items() if v == "PASS"]
        final_reason = f"three-gate PASS at z={passing}"
        if flagged_syms:
            recommendation = "R-2 candidate (await user approval) -- consider sub-paradigm split per flagged sym"
        else:
            recommendation = "R-2 candidate (await user approval)"
    else:
        final_verdict = "FAIL"
        final_reason = ("three-gate FAIL at all z; failures: "
                        + "; ".join(f"z={z}:{per_z_results[z]['three_gate_reason']}"
                                    for z in per_z_results))
        if flagged_syms:
            recommendation = "graveyard pooled, but per-sym sub-paradigm split worth investigating"
        else:
            recommendation = "graveyard now"

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "verdict": final_verdict,
        "reason": final_reason,
        "recommendation": recommendation,
        "config": {
            "btc": BTC,
            "alts": ALTS,
            "z_window_bars": Z_WINDOW,
            "z_grid": Z_GRID,
            "z_default": Z_DEFAULT,
            "cooldown_min": COOLDOWN_MIN,
            "hold_min": HOLD_MIN,
            "fee_rt": FEE_RT,
            "btc_ret_window_min": BTC_RET_WINDOW_MIN,
            "perm_n": PERM_N,
            "boot_n": BOOT_N,
            "seed": SEED,
            "early_term_bp_threshold": EARLY_TERM_BP,
            "data_window": "microstructure 5m joblib (~1.5yr from 2024-11-07)",
            "signal_construction": "implied_tbq = (ratio/(1+ratio)) * Σ(close_1m * vol_1m) over 5m bin; z over 30-bar rolling",
        },
        "early_term_pre_screen": {
            "z": Z_DEFAULT,
            "n_unsigned": int(len(pre_unsigned)),
            "mean_bp_unsigned_net": float(pre_mean_bp) if np.isfinite(pre_mean_bp) else None,
            "t_unsigned_net": float(pre_t) if np.isfinite(pre_t) else None,
            "triggered": bool(early_term),
            "threshold_bp": EARLY_TERM_BP,
        },
        "per_z_results": per_z_results,
        "per_sym_at_z_default": per_z_per_sym[Z_DEFAULT],
        "per_sym_diagnostics": per_sym_diag,
        "flagged_per_sym": flagged_syms,
        "trigger_counts_summary": {
            str(z): {"n_total_unsigned": per_z_n_total[z], "n_signed_btc_up": per_z_n_signed[z]}
            for z in Z_GRID
        },
        "wall_clock_s": round(time.time() - t_start, 1),
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("== DONE in %.1fs -> %s ==", out["wall_clock_s"], OUT_PATH)
    log.info("VERDICT: %s | %s", final_verdict, final_reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
