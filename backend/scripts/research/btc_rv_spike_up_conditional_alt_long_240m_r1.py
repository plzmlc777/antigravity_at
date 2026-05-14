"""R-1 PoC — btc_rv_spike_up_conditional_alt_long_240m.

Hypothesis (single sentence)
----------------------------
BTC 30-minute realized volatility z-score(30d rolling) >= +2.5 (rising edge,
60-min cooldown) AND BTC 30-minute return > 0 at trigger ("up-trigger"):
on each such event, enter LONG positions in all 13 altcoin perpetuals,
hold 240 minutes (4h), exit at hold-bar close.

Resurrection context
--------------------
67th graveyard `btc_rv_spike_alt_recovery_long_240m` H5 sign-split:
- BTC up-trigger × LONG @ 240m: n=2,353, gross_mean=+186.5bp, t=+3.58, win=53.2%
- BTC down-trigger × LONG @ 240m: n=2,756, mean=-150.1bp, t=-2.73 (opposite)
Unsigned LONG cancelled. This script tests the up-trigger-only sub-paradigm.

R-1 sub-hypotheses
------------------
H1  Pooled LONG net EV at hold=240 (up-triggers only): mean_net, t, win, n.
H2  fee_aware_perm_test + bootstrap_ci  (three-gate from new _perm_utils):
    - signal_t_excess >= 2.0
    - bootstrap_ci.ci_lower > 0
    - perm_p_two_sided <= 0.10
H3  Per-symbol consistency: count alts with signal_t_excess > 1.0 AND mean_net > 0.
    Pass: >= 10/13.
H4  Hold sensitivity grid {180, 210, 240, 270, 300}. All five positive net mean.
    Pass: monotone-ish or plateau, NO single-point spike at 240m.
H5  RV |z| threshold sensitivity {2.0, 2.5, 3.0}. Positive at all three.
H6  Non-rising-edge baseline (every BTC bar with ret_30m > 0, LONG +240m hold).
    Should be near zero — if comparable, RV filter adds no value.

Trigger
-------
BTC 1m close -> log-ret -> 30-bar rolling std (= 30m RV).
30d rolling z-score of RV (window = 43200 bars).
Rising edge: rv_z[t] > 2.5 AND rv_z[t-1] <= 2.5.
60-min cooldown after each accepted trigger.
UP filter: keep only triggers where BTC 30m return at t > 0.

Trade
-----
Entry on each of 13 alts at close[t+1m]. Hold = 240 minutes.
Exit at close[t+1+240]. Direction = +1 (LONG).
Gross = (exit / entry) - 1. Net = gross - 8bp.

Output
------
backend/runs/research_track/btc_rv_spike_up_conditional_alt_long_240m/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("btc_rv_up_r1")

PARADIGM = "btc_rv_spike_up_conditional_alt_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

RV_WINDOW = 30           # 1m bars (30-minute realized vol)
Z_WINDOW = 30 * 24 * 60  # 43200 bars = 30 days of 1m
Z_THRESH_MAIN = 2.5
Z_THRESHS_H5 = [2.0, 2.5, 3.0]
COOLDOWN = 60            # 1m bars between re-arm
HOLDS_H4 = [180, 210, 240, 270, 300]
HOLD_MAIN = 240
FEE_RT = 8e-4
N_PERMS = 1000
N_BOOT = 2000
POOL_SAMPLE_SIZE = 100_000  # subsample of candidate-pool 240m forward returns
SEED = 42


# ---------- data ----------


def load_ohlcv_1m(db, sym: str) -> pd.DataFrame:
    rows = db.execute(
        text(
            "SELECT timestamp, close FROM ohlcv "
            "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
        ),
        {"s": sym},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[~df.index.duplicated(keep="first")]
    return df


# ---------- triggers ----------


def compute_btc_signal(btc: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame indexed by BTC bar time with columns rv, rv_z, btc_ret_30m."""
    log.info("computing BTC RV / 30d z (%d bars input)", len(btc))
    lr = np.log(btc["close"]).diff()
    rv = lr.rolling(RV_WINDOW, min_periods=RV_WINDOW).std()
    rv_mu = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    rv_sd = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    rv_z = (rv - rv_mu) / rv_sd
    btc_ret_30m = btc["close"] / btc["close"].shift(RV_WINDOW) - 1
    sig = pd.DataFrame(
        {"rv": rv, "rv_z": rv_z, "btc_ret_30m": btc_ret_30m}
    ).dropna()
    log.info("signal usable bars: %d (after z_window=%d)", len(sig), Z_WINDOW)
    return sig


def extract_triggers(sig: pd.DataFrame, z_thresh: float,
                     up_only: bool = True) -> pd.DataFrame:
    """Rising-edge z>thresh, 60-min cooldown. up_only=True keeps btc_ret_30m>0."""
    z_prev = sig["rv_z"].shift(1)
    fire = (sig["rv_z"] > z_thresh) & (z_prev <= z_thresh)
    triggers = sig[fire].copy()
    if up_only:
        triggers = triggers[triggers["btc_ret_30m"] > 0]
    if len(triggers) == 0:
        return triggers
    # 60-min cooldown
    keep = [True]
    last_t = triggers.index[0]
    for ts in triggers.index[1:]:
        delta_min = (ts - last_t).total_seconds() / 60.0
        if delta_min < COOLDOWN:
            keep.append(False)
        else:
            keep.append(True)
            last_t = ts
    return triggers[keep]


# ---------- trade construction ----------


def build_ts_index(closes: pd.Series) -> dict:
    return {ts: i for i, ts in enumerate(closes.index)}


def long_returns_for_alt(close_arr: np.ndarray, ts_to_pos: dict,
                         trig_ts: list, hold_min: int) -> np.ndarray:
    """LONG return for each trigger ts on this alt. Returns gross (not net)."""
    n = len(trig_ts)
    out = np.full(n, np.nan)
    for i, ts in enumerate(trig_ts):
        entry_ts = ts + pd.Timedelta(minutes=1)
        exit_ts = ts + pd.Timedelta(minutes=1 + hold_min)
        ei = ts_to_pos.get(entry_ts)
        xi = ts_to_pos.get(exit_ts)
        if ei is None or xi is None:
            continue
        ep = close_arr[ei]
        xp = close_arr[xi]
        if ep > 0 and not np.isnan(ep) and not np.isnan(xp):
            out[i] = (xp / ep) - 1.0
    return out


def candidate_pool_returns(close_arr: np.ndarray, hold_min: int,
                           stride: int = 60) -> np.ndarray:
    """All forward-LONG GROSS returns over hold_min, sampled every `stride` bars."""
    n = len(close_arr)
    if n <= hold_min + 1:
        return np.array([])
    ep = close_arr[: -hold_min - 1 : stride]
    xp = close_arr[hold_min + 1 :: stride]
    m = min(len(ep), len(xp))
    ep = ep[:m]
    xp = xp[:m]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (xp / ep) - 1.0
    return r[np.isfinite(r)]


def t_stat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(x.mean() / sd * np.sqrt(len(x)))


def summarize(arr: np.ndarray) -> dict:
    arr = np.asarray(arr, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {"n": 0}
    return {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else float("nan"),
        "t_stat": t_stat(arr),
        "win_rate": float(np.mean(arr > 0)),
    }


# ---------- main ----------


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("== R-1 PoC: %s ==", PARADIGM)

    with SessionLocal() as db:
        btc = load_ohlcv_1m(db, BTC)
        if btc.empty:
            log.error("no BTC ohlcv")
            return 2
        log.info(
            "BTC bars: %d  range %s -> %s",
            len(btc), btc.index.min(), btc.index.max(),
        )

        sig = compute_btc_signal(btc)
        triggers_main = extract_triggers(sig, Z_THRESH_MAIN, up_only=True)
        n_trig = len(triggers_main)
        log.info("main up-triggers (z=%.1f): %d", Z_THRESH_MAIN, n_trig)

        if n_trig == 0:
            out = {
                "paradigm": PARADIGM,
                "verdict": "GRAVEYARD",
                "reason": "no up-triggers in available BTC window",
                "btc_range": [str(btc.index.min()), str(btc.index.max())],
            }
            OUT_PATH.write_text(json.dumps(out, indent=2))
            return 0

        # Load alts
        alt_data: dict[str, np.ndarray] = {}
        alt_lookup: dict[str, dict] = {}
        for sym in ALTS:
            df = load_ohlcv_1m(db, sym)
            if df.empty:
                log.warning("missing %s", sym)
                continue
            alt_data[sym] = df["close"].to_numpy()
            alt_lookup[sym] = build_ts_index(df["close"])
            log.info("  loaded %s: %d bars", sym, len(df))
        log.info("alts available: %d / 13", len(alt_data))

        # ---- H1: pooled LONG net at hold=240 ----
        log.info("-- H1: hold=%d min, up-only LONG --", HOLD_MAIN)
        trig_ts_list = list(triggers_main.index)
        pool_gross_main: list[float] = []
        per_alt_main: dict[str, dict] = {}
        per_alt_gross_arr: dict[str, np.ndarray] = {}
        for sym, close_arr in alt_data.items():
            rets = long_returns_for_alt(
                close_arr, alt_lookup[sym], trig_ts_list, HOLD_MAIN,
            )
            per_alt_gross_arr[sym] = rets
            valid = rets[~np.isnan(rets)]
            if len(valid) == 0:
                per_alt_main[sym] = {
                    "n": 0, "mean_net": float("nan"),
                    "t_net": float("nan"), "win_rate": float("nan"),
                }
                continue
            net = valid - FEE_RT
            pool_gross_main.extend(valid.tolist())
            per_alt_main[sym] = {
                "n": int(len(valid)),
                "mean_gross": float(np.mean(valid)),
                "mean_net": float(np.mean(net)),
                "t_net": t_stat(net),
                "win_rate": float(np.mean(net > 0)),
            }
        pool_gross_arr = np.array(pool_gross_main)
        pool_net_arr = pool_gross_arr - FEE_RT
        h1 = {
            "n_triggers": int(n_trig),
            "n_trades": int(len(pool_net_arr)),
            "gross": summarize(pool_gross_arr),
            "net": summarize(pool_net_arr),
        }
        log.info(
            "  H1 pooled: n=%d  gross_mean=%.5f  net_mean=%.5f  t=%.2f  win=%.3f",
            h1["n_trades"],
            h1["gross"].get("mean", float("nan")),
            h1["net"].get("mean", float("nan")),
            h1["net"].get("t_stat", float("nan")),
            h1["net"].get("win_rate", float("nan")),
        )

        # ---- H2: fee-aware perm + bootstrap CI ----
        # Candidate pool: forward 240m GROSS returns across all 13 alts (stride=60)
        log.info("building candidate pool (stride=60, hold=%d)", HOLD_MAIN)
        pool_chunks = []
        for sym, close_arr in alt_data.items():
            r = candidate_pool_returns(close_arr, HOLD_MAIN, stride=60)
            pool_chunks.append(r)
        candidate_pool = np.concatenate(pool_chunks) if pool_chunks else np.array([])
        log.info("candidate pool size: %d", len(candidate_pool))
        rng_pool = np.random.default_rng(SEED)
        if len(candidate_pool) > POOL_SAMPLE_SIZE:
            idx_sub = rng_pool.choice(
                len(candidate_pool), size=POOL_SAMPLE_SIZE, replace=False,
            )
            candidate_pool_use = candidate_pool[idx_sub]
        else:
            candidate_pool_use = candidate_pool
        log.info("candidate pool used: %d", len(candidate_pool_use))

        log.info("H2: fee_aware_perm_test n_perms=%d", N_PERMS)
        fee_res = fee_aware_perm_test(
            observed_net_returns=pool_net_arr,
            candidate_pool_returns=candidate_pool_use,
            fee_per_trade=FEE_RT,
            n_perms=N_PERMS,
            rng_seed=SEED,
        )
        log.info(
            "  obs_t=%.3f  null_mean_t=%.3f  excess=%.3f  p_two=%.4f  p_above=%.4f",
            fee_res["obs_t"], fee_res["null_mean_t"],
            fee_res["signal_t_excess"], fee_res["perm_p_two_sided"],
            fee_res["perm_p_one_sided_above"],
        )

        log.info("H2: bootstrap_ci n_boot=%d  block=240", N_BOOT)
        ci_res = bootstrap_ci(
            observed_net_returns=pool_net_arr,
            n_boot=N_BOOT,
            block_size=240,
            rng_seed=SEED,
        )
        log.info(
            "  boot mean=%.5f  ci=[%.5f, %.5f]  P(>0)=%.3f",
            ci_res["mean"], ci_res["ci_lower"], ci_res["ci_upper"],
            ci_res["prob_positive"],
        )

        three_gate = {
            "signal_t_excess_pass": bool(fee_res["signal_t_excess"] >= 2.0),
            "ci_lower_pass": bool(ci_res["ci_lower"] > 0),
            "perm_p_two_pass": bool(fee_res["perm_p_two_sided"] <= 0.10),
        }
        three_gate_all = all(three_gate.values())

        # ---- H3: per-symbol consistency ----
        log.info("H3: per-symbol signal_t_excess vs sym-specific pool")
        h3_per_alt = {}
        h3_pass_count = 0
        for sym, close_arr in alt_data.items():
            gr = per_alt_gross_arr[sym]
            valid = gr[~np.isnan(gr)]
            if len(valid) < 2:
                h3_per_alt[sym] = {"n": int(len(valid)), "excess": None,
                                    "mean_net": None, "passes": False}
                continue
            sym_obs = valid - FEE_RT
            sym_pool = candidate_pool_returns(close_arr, HOLD_MAIN, stride=60)
            if len(sym_pool) < len(sym_obs) * 2 + 10:
                h3_per_alt[sym] = {
                    "n": int(len(sym_obs)),
                    "excess": None,
                    "mean_net": float(np.mean(sym_obs)),
                    "passes": False,
                    "note": "pool too small",
                }
                continue
            if len(sym_pool) > 50_000:
                sym_pool = sym_pool[rng_pool.choice(
                    len(sym_pool), size=50_000, replace=False,
                )]
            sub_fee = fee_aware_perm_test(
                observed_net_returns=sym_obs,
                candidate_pool_returns=sym_pool,
                fee_per_trade=FEE_RT,
                n_perms=500,
                rng_seed=SEED,
            )
            excess = sub_fee["signal_t_excess"]
            mean_net = float(np.mean(sym_obs))
            passes = bool(excess > 1.0 and mean_net > 0)
            if passes:
                h3_pass_count += 1
            h3_per_alt[sym] = {
                "n": int(len(sym_obs)),
                "obs_t": float(sub_fee["obs_t"]),
                "null_mean_t": float(sub_fee["null_mean_t"]),
                "excess": float(excess),
                "mean_net": mean_net,
                "perm_p_two": float(sub_fee["perm_p_two_sided"]),
                "passes": passes,
            }
        log.info("H3: %d / %d alts pass (need >=10)", h3_pass_count, len(alt_data))

        # ---- H4: hold sensitivity grid ----
        log.info("H4: hold sensitivity grid %s", HOLDS_H4)
        h4 = {}
        for H in HOLDS_H4:
            if H == HOLD_MAIN:
                h4[str(H)] = {
                    "n_trades": h1["n_trades"],
                    "mean_net": h1["net"].get("mean"),
                    "t_net": h1["net"].get("t_stat"),
                    "win_rate": h1["net"].get("win_rate"),
                }
                continue
            pg = []
            for sym, close_arr in alt_data.items():
                r = long_returns_for_alt(
                    close_arr, alt_lookup[sym], trig_ts_list, H,
                )
                pg.extend(r[~np.isnan(r)].tolist())
            arr = np.array(pg) - FEE_RT
            h4[str(H)] = {
                "n_trades": int(len(arr)),
                "mean_net": float(np.mean(arr)) if len(arr) else float("nan"),
                "t_net": t_stat(arr),
                "win_rate": float(np.mean(arr > 0)) if len(arr) else float("nan"),
            }
            log.info(
                "  hold=%d  n=%d  net=%.5f  t=%.2f",
                H, h4[str(H)]["n_trades"], h4[str(H)]["mean_net"],
                h4[str(H)]["t_net"],
            )
        h4_all_positive = all(
            (v["mean_net"] is not None and not np.isnan(v["mean_net"])
             and v["mean_net"] > 0)
            for v in h4.values()
        )

        # ---- H5: |z| threshold sensitivity ----
        log.info("H5: |z| threshold grid %s", Z_THRESHS_H5)
        h5 = {}
        for z in Z_THRESHS_H5:
            trig_z = extract_triggers(sig, z, up_only=True)
            if len(trig_z) == 0:
                h5[str(z)] = {"n_trig": 0}
                continue
            ts_list_z = list(trig_z.index)
            pg = []
            for sym, close_arr in alt_data.items():
                r = long_returns_for_alt(
                    close_arr, alt_lookup[sym], ts_list_z, HOLD_MAIN,
                )
                pg.extend(r[~np.isnan(r)].tolist())
            arr = np.array(pg) - FEE_RT
            h5[str(z)] = {
                "n_trig": int(len(trig_z)),
                "n_trades": int(len(arr)),
                "mean_net": float(np.mean(arr)) if len(arr) else float("nan"),
                "t_net": t_stat(arr),
            }
            log.info(
                "  z>=%.1f  n_trig=%d  n_trades=%d  net=%.5f  t=%.2f",
                z, h5[str(z)]["n_trig"], h5[str(z)]["n_trades"],
                h5[str(z)]["mean_net"], h5[str(z)]["t_net"],
            )
        h5_all_positive = all(
            (v.get("mean_net") is not None
             and not np.isnan(v.get("mean_net", float("nan")))
             and v["mean_net"] > 0)
            for v in h5.values() if "mean_net" in v
        )

        # ---- H6: baseline (every bar with btc_ret_30m>0, no RV filter) ----
        # Random subsample of bars to keep n comparable to triggers
        log.info("H6: non-rising-edge baseline")
        up_bars = sig[sig["btc_ret_30m"] > 0]
        rng_h6 = np.random.default_rng(SEED + 1)
        if len(up_bars) > n_trig:
            idx_h6 = rng_h6.choice(len(up_bars), size=n_trig, replace=False)
            up_sample = up_bars.iloc[np.sort(idx_h6)]
        else:
            up_sample = up_bars
        ts_h6 = list(up_sample.index)
        pg = []
        for sym, close_arr in alt_data.items():
            r = long_returns_for_alt(
                close_arr, alt_lookup[sym], ts_h6, HOLD_MAIN,
            )
            pg.extend(r[~np.isnan(r)].tolist())
        arr_h6 = np.array(pg) - FEE_RT
        h6_mean_net = float(np.mean(arr_h6)) if len(arr_h6) else float("nan")
        ratio_h1_h6 = None
        if (
            len(arr_h6) > 0
            and not np.isnan(h6_mean_net)
            and h6_mean_net != 0
        ):
            ratio_h1_h6 = float(h1["net"]["mean"] / h6_mean_net)
        h6 = {
            "n_bars_sampled": int(len(up_sample)),
            "n_trades": int(len(arr_h6)),
            "mean_net": h6_mean_net,
            "t_net": t_stat(arr_h6),
            "win_rate": float(np.mean(arr_h6 > 0)) if len(arr_h6) else float("nan"),
            "ratio_h1_over_h6": ratio_h1_h6,
        }
        log.info(
            "  H6 baseline: n=%d  net=%.5f  t=%.2f  H1/H6 ratio=%s",
            h6["n_trades"], h6["mean_net"], h6["t_net"],
            h6.get("ratio_h1_over_h6"),
        )

        # ---- Verdict ----
        reasons = []
        graveyard = False

        excess = fee_res["signal_t_excess"]
        ci_lo = ci_res["ci_lower"]
        p2 = fee_res["perm_p_two_sided"]
        h1_mean = h1["net"]["mean"]

        if not isinstance(excess, float) or np.isnan(excess) or excess < 2.0:
            graveyard = True
            reasons.append(f"signal_t_excess={excess:.3f} < 2.0")
        if not isinstance(ci_lo, float) or np.isnan(ci_lo) or ci_lo <= 0:
            graveyard = True
            reasons.append(f"bootstrap_ci.ci_lower={ci_lo:.5f} <= 0")
        if not isinstance(p2, float) or np.isnan(p2) or p2 > 0.10:
            graveyard = True
            reasons.append(f"perm_p_two_sided={p2:.4f} > 0.10")
        if h1_mean is None or np.isnan(h1_mean) or h1_mean <= 0:
            graveyard = True
            reasons.append(
                f"H1 net mean={h1_mean} <= 0 (direction wrong)"
            )
        if h3_pass_count < 10:
            graveyard = True
            reasons.append(f"H3 only {h3_pass_count}/13 alts consistent (need >=10)")
        # H4: any non-240 hold negative?
        non_main_negatives = [
            H for H, v in h4.items()
            if int(H) != HOLD_MAIN
            and v.get("mean_net") is not None
            and not np.isnan(v.get("mean_net", float("nan")))
            and v["mean_net"] <= 0
        ]
        if non_main_negatives:
            graveyard = True
            reasons.append(
                f"H4 single-point overfit: holds {non_main_negatives} negative"
            )
        if not h5_all_positive:
            graveyard = True
            reasons.append("H5 not all |z| thresholds positive")
        # H6: if baseline is comparable or stronger, RV filter adds no value
        ratio = h6.get("ratio_h1_over_h6")
        if (
            ratio is not None
            and not np.isnan(ratio)
            and (ratio < 1.5)
            and h6.get("mean_net", 0) > 0
        ):
            graveyard = True
            reasons.append(
                f"H6 baseline ratio H1/H6={ratio:.2f} < 1.5 (RV filter weak)"
            )

        candidate = (
            not graveyard
            and three_gate_all
            and h3_pass_count >= 11
            and not non_main_negatives
            and h5_all_positive
            and (ratio is None or np.isnan(ratio) or ratio >= 1.5)
        )
        borderline = (
            not graveyard
            and not candidate
            and three_gate_all
        )

        if graveyard:
            verdict = "GRAVEYARD"
        elif candidate:
            verdict = "CANDIDATE-FOR-R2"
        elif borderline:
            verdict = "BORDERLINE"
        else:
            verdict = "BORDERLINE"
            reasons.append("default borderline")

        out = {
            "paradigm": PARADIGM,
            "verdict": verdict,
            "verdict_reasons": reasons,
            "data_window": {
                "btc_first": str(btc.index.min()),
                "btc_last": str(btc.index.max()),
                "btc_bars": int(len(btc)),
                "alts_loaded": list(alt_data.keys()),
                "alts_missing": [s for s in ALTS if s not in alt_data],
            },
            "config": {
                "rv_window_bars": RV_WINDOW,
                "z_window_bars": Z_WINDOW,
                "z_thresh_main": Z_THRESH_MAIN,
                "z_thresh_grid": Z_THRESHS_H5,
                "cooldown_min": COOLDOWN,
                "hold_main_min": HOLD_MAIN,
                "hold_grid_min": HOLDS_H4,
                "fee_round_trip": FEE_RT,
                "n_perms": N_PERMS,
                "n_boot": N_BOOT,
                "pool_sample_size": POOL_SAMPLE_SIZE,
                "long_only": True,
                "up_trigger_filter": True,
            },
            "H1": h1,
            "H2_three_gate": {
                "fee_aware_perm": fee_res,
                "bootstrap_ci": ci_res,
                "gate_pass": three_gate,
                "gate_pass_all": bool(three_gate_all),
            },
            "H3_per_symbol": h3_per_alt,
            "H3_pass_count": int(h3_pass_count),
            "H3_total_alts": int(len(alt_data)),
            "H4_hold_grid": h4,
            "H4_all_positive": bool(h4_all_positive),
            "H4_non_main_negatives": non_main_negatives,
            "H5_threshold_grid": h5,
            "H5_all_positive": bool(h5_all_positive),
            "H6_baseline": h6,
            "trigger_summary": {
                "n_up_triggers_main": int(n_trig),
                "first_trigger": str(triggers_main.index.min()),
                "last_trigger": str(triggers_main.index.max()),
            },
            "per_alt_at_main_hold": per_alt_main,
        }

        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("wrote %s", OUT_PATH)
        log.info("VERDICT: %s", verdict)
        for r in reasons:
            log.info("  reason: %s", r)
        return 0


if __name__ == "__main__":
    sys.exit(main())
