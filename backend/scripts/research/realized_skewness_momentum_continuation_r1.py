"""R-1 PoC -- realized_skewness_momentum_continuation.

Hypothesis
----------
Within 14 Binance USDT-perp universe, when the realized SKEWNESS of 1m
log-returns over a trailing 1-hour window reaches a z-score (vs 30-day
rolling 1h-skew distribution) with |z| >= 2, the next 30-60 minutes
exhibit momentum CONTINUATION in the same direction as the skew sign
(positive skew -> long, negative skew -> short).

This is the INVERSE direction of the failed `realized_skewness_exhaustion_mr`
graveyard (2026-05-14, t=-7.83 against MR -> gross +18~21bp pre-fee per-side
suggested continuation is the real edge -- but predecessor's naive perm
could not validate due to fee-drift trap).

This R-1 uses the new `scripts.research._perm_utils` three-gate suite:
  - signal_t_excess = obs_t - fee_aware_perm_null_mean_t
  - bootstrap_ci.ci_lower on observed net mean
  - perm_p_two_sided

Output
------
backend/runs/research_track/realized_skewness_momentum_continuation/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import skew as sp_skew
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    fee_aware_perm_test,
    bootstrap_ci,
    block_permutation_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rsk_mom_r1")

PARADIGM = "realized_skewness_momentum_continuation"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"

SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

SKEW_WINDOW = 60          # 1m bars in trailing 1h window
HOURLY_STRIDE = 60        # sample skew every 60 1m bars
Z_WINDOW_HRS = 30 * 24    # 720 hourly bars (30 days)
Z_PRIMARY = 2.0           # primary |skew_z| cutoff
Z_GRID = [1.5, 2.0, 2.5, 3.0]
HOLDS = [30, 60, 90, 120]
FEE_RT = 8e-4
PERM_N = 1000
BOOT_N = 2000
SEED = 42


# ---------- data ----------


def load_ohlcv_1m(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df


# ---------- signal ----------


def build_skew_z_series(closes: pd.Series) -> pd.DataFrame:
    """Build hourly-sampled realized skew + rolling-30d z-score.

    Skew is computed ONLY at hourly anchors (timestamp.minute == 0),
    using the trailing 60 1m log-returns ending at that anchor.

    Returns DataFrame indexed by hourly anchor timestamps with columns
    [skew, skew_z]. Drops bars with insufficient lookback (z burn-in).
    """
    lr = np.log(closes).diff()
    arr = lr.to_numpy()
    ts_idx = closes.index

    minute_arr = ts_idx.minute.to_numpy()
    anchor_positions = np.where(minute_arr == 0)[0]
    anchor_positions = anchor_positions[anchor_positions >= SKEW_WINDOW]

    sk_vals = []
    anchor_ts = []
    for pos in anchor_positions:
        window = arr[pos - SKEW_WINDOW + 1: pos + 1]
        if np.isnan(window).any():
            continue
        s = sp_skew(window, bias=False, nan_policy="omit")
        if np.isfinite(s):
            sk_vals.append(s)
            anchor_ts.append(ts_idx[pos])

    if not sk_vals:
        return pd.DataFrame(columns=["skew", "skew_z"])

    hourly = pd.Series(sk_vals, index=pd.DatetimeIndex(anchor_ts), name="skew")
    hourly = hourly.sort_index()

    mu = hourly.rolling(Z_WINDOW_HRS, min_periods=Z_WINDOW_HRS).mean()
    sd = hourly.rolling(Z_WINDOW_HRS, min_periods=Z_WINDOW_HRS).std()
    skew_z = (hourly - mu) / sd
    out = pd.DataFrame({"skew": hourly, "skew_z": skew_z}).dropna()
    return out


def build_ts_index(closes: pd.Series) -> dict:
    return {ts: i for i, ts in enumerate(closes.index)}


def trades_for_events(close_arr: np.ndarray, ts_to_pos: dict,
                      event_ts: list, dirs: np.ndarray,
                      hold_min: int) -> np.ndarray:
    """For each event, compute gross return = dirs * (exit/entry - 1).

    Entry = close[t+1m], exit = close[t+1+hold].
    """
    n = len(event_ts)
    out = np.full(n, np.nan)
    for i, ts in enumerate(event_ts):
        entry_ts = ts + pd.Timedelta(minutes=1)
        exit_ts = ts + pd.Timedelta(minutes=1 + hold_min)
        ei = ts_to_pos.get(entry_ts)
        xi = ts_to_pos.get(exit_ts)
        if ei is None or xi is None:
            continue
        ep = close_arr[ei]
        xp = close_arr[xi]
        if ep > 0 and not np.isnan(ep) and not np.isnan(xp):
            out[i] = (xp / ep - 1) * dirs[i]
    return out


def forward_returns_for_all_anchors(close_arr: np.ndarray,
                                    ts_to_pos: dict,
                                    anchor_ts: list,
                                    hold_min: int) -> np.ndarray:
    """For ALL hourly anchors (whether triggered or not), compute SIGNED
    forward gross return where the sign is RANDOM (+1 or -1 with equal prob).

    Used as candidate pool for fee_aware_perm_test. The pool needs to share
    the same fee structure & distributional shape as observed trades but
    without the trigger selection. We use random direction so that the
    null is direction-agnostic (the test is whether direction CHOICE adds
    skill above random).
    """
    rng = np.random.default_rng(SEED)
    n = len(anchor_ts)
    dirs = rng.choice([-1, 1], size=n)
    return trades_for_events(close_arr, ts_to_pos, anchor_ts, dirs, hold_min)


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

    sym_data = {}    # sym -> dict
    with SessionLocal() as db:
        for sym in SYMS:
            df = load_ohlcv_1m(db, sym)
            if df.empty:
                log.warning("missing %s", sym)
                continue
            log.info("loaded %s: %d bars %s -> %s", sym, len(df),
                     df.index.min(), df.index.max())
            sig = build_skew_z_series(df["close"])
            log.info("  %s skew_z series: %d hourly bars (post 30d burn-in)",
                     sym, len(sig))
            sym_data[sym] = {
                "close_arr": df["close"].to_numpy(),
                "ts_to_pos": build_ts_index(df["close"]),
                "signal": sig,
                "n_bars": len(df),
                "first": df.index.min(),
                "last": df.index.max(),
            }

    if not sym_data:
        log.error("no data")
        return 2

    data_first = min(d["first"] for d in sym_data.values())
    data_last = max(d["last"] for d in sym_data.values())
    data_days = (data_last - data_first).days
    log.info("data range: %s -> %s (%d days)", data_first, data_last, data_days)

    # ---- Trigger pool at primary |z| >= 2.0 ----
    # DIRECTION: +sign(skew_z) for momentum continuation (INVERSE of MR)
    triggers_per_sym = {}
    total_trig = 0
    for sym, d in sym_data.items():
        s = d["signal"]
        fire = s["skew_z"].abs() >= Z_PRIMARY
        ev = s[fire].copy()
        ev["dir"] = np.sign(ev["skew_z"]).astype(int)  # +sign for momentum
        ev = ev[ev["dir"] != 0]
        triggers_per_sym[sym] = ev
        total_trig += len(ev)
        log.info("  triggers %s @|z|>=%.1f: %d (pos_skew_long=%d neg_skew_short=%d)",
                 sym, Z_PRIMARY, len(ev),
                 int((ev["skew_z"] > 0).sum()), int((ev["skew_z"] < 0).sum()))
    log.info("total triggers @|z|>=%.1f: %d", Z_PRIMARY, total_trig)

    if total_trig == 0:
        out = {"verdict": "GRAVEYARD", "reason": "no triggers", "n_triggers": 0}
        OUT_PATH.write_text(json.dumps(out, indent=2))
        return 0

    # ---- H1: per-hold pooled + per-sym ----
    per_hold = {}
    per_sym_by_hold = {}
    per_hold_pool_net = {}
    for H in HOLDS:
        log.info("-- hold=%d min --", H)
        pool_gross = []
        pool_net = []
        per_sym = {}
        for sym, ev in triggers_per_sym.items():
            if len(ev) == 0:
                per_sym[sym] = {"n": 0}
                continue
            ev_ts = list(ev.index)
            ev_dirs = ev["dir"].to_numpy()
            rets = trades_for_events(sym_data[sym]["close_arr"],
                                     sym_data[sym]["ts_to_pos"],
                                     ev_ts, ev_dirs, H)
            valid = rets[~np.isnan(rets)]
            if len(valid) == 0:
                per_sym[sym] = {"n": 0}
                continue
            net = valid - FEE_RT
            pool_gross.extend(valid.tolist())
            pool_net.extend(net.tolist())
            per_sym[sym] = {
                "n": int(len(valid)),
                "t_stat": t_stat(net),
                "mean_net": float(np.mean(net)),
                "mean_gross": float(np.mean(valid)),
                "win_rate": float(np.mean(net > 0)),
            }
        pg = np.array(pool_gross)
        pn = np.array(pool_net)
        per_hold[str(H)] = {
            "n_trades": int(len(pn)),
            "gross": summarize(pg),
            "net": summarize(pn),
        }
        per_sym_by_hold[str(H)] = per_sym
        per_hold_pool_net[H] = pn
        log.info("  pooled n=%d net_mean=%.5f net_t=%.2f win_rate=%.3f",
                 len(pn),
                 float(np.mean(pn)) if len(pn) else float("nan"),
                 t_stat(pn),
                 float(np.mean(pn > 0)) if len(pn) else float("nan"))

    # Best hold by t_stat (we want POSITIVE alpha, so take max signed t)
    def _t_for(H):
        v = per_hold[str(H)]["net"].get("t_stat")
        return v if (v is not None and not np.isnan(v)) else -1e9
    best_hold = max(HOLDS, key=_t_for)
    best = per_hold[str(best_hold)]
    log.info("best hold by signed t: %d min, t=%.2f, net_mean=%.5f",
             best_hold, best["net"]["t_stat"], best["net"]["mean"])

    observed_net_best = per_hold_pool_net[best_hold]
    obs_t = best["net"]["t_stat"]

    # ---- H2: fee-aware perm test using candidate pool of ALL hourly anchors ----
    log.info("H2: building candidate pool (all hourly anchors, random-sign)...")
    candidate_pool_gross = []
    for sym, d in sym_data.items():
        anchors = list(d["signal"].index)
        if not anchors:
            continue
        rets = forward_returns_for_all_anchors(
            d["close_arr"], d["ts_to_pos"], anchors, best_hold
        )
        valid = rets[~np.isnan(rets)]
        candidate_pool_gross.extend(valid.tolist())
    log.info("  candidate pool size: %d (gross, random-sign)", len(candidate_pool_gross))

    log.info("H2: fee_aware_perm_test n=%d ...", PERM_N)
    fee_perm = fee_aware_perm_test(
        observed_net_returns=observed_net_best,
        candidate_pool_returns=candidate_pool_gross,
        fee_per_trade=FEE_RT,
        n_perms=PERM_N,
        rng_seed=SEED,
    )
    log.info("  obs_t=%.3f null_mean_t=%.3f signal_t_excess=%.3f perm_p_two=%.4f",
             fee_perm["obs_t"], fee_perm["null_mean_t"],
             fee_perm["signal_t_excess"], fee_perm["perm_p_two_sided"])

    # ---- H2b: bootstrap CI on observed net mean ----
    log.info("H2b: bootstrap_ci n=%d block=%d ...", BOOT_N, best_hold)
    ci = bootstrap_ci(
        observed_net_returns=observed_net_best,
        n_boot=BOOT_N,
        block_size=best_hold,
        rng_seed=SEED,
    )
    log.info("  ci.mean=%.6f lower=%.6f upper=%.6f prob_pos=%.3f",
             ci["mean"], ci["ci_lower"], ci["ci_upper"], ci["prob_positive"])

    # ---- H3 (sensitivity): block_permutation_test with block=240 ----
    # Build per-sym signal/forward-return dicts for the helper.
    log.info("H3: block_permutation_test (sensitivity, block=240) ...")
    per_sym_signal_z = {}
    per_sym_fwd = {}
    for sym, d in sym_data.items():
        sig = d["signal"]
        if sig.empty:
            continue
        per_sym_signal_z[sym] = sig["skew_z"]
        # forward returns for ALL hourly anchors (unsigned)
        anchors = list(sig.index)
        rets = np.full(len(anchors), np.nan)
        for i, ts in enumerate(anchors):
            entry_ts = ts + pd.Timedelta(minutes=1)
            exit_ts = ts + pd.Timedelta(minutes=1 + best_hold)
            ei = d["ts_to_pos"].get(entry_ts)
            xi = d["ts_to_pos"].get(exit_ts)
            if ei is None or xi is None:
                continue
            ep = d["close_arr"][ei]
            xp = d["close_arr"][xi]
            if ep > 0 and not np.isnan(ep) and not np.isnan(xp):
                rets[i] = (xp / ep - 1)  # unsigned, direction applied by helper
        per_sym_fwd[sym] = pd.Series(rets, index=pd.DatetimeIndex(anchors))

    block_perm = block_permutation_test(
        per_sym_signal=per_sym_signal_z,
        per_sym_forward_return=per_sym_fwd,
        threshold_fn=lambda s: s.abs() >= Z_PRIMARY,
        direction_fn=lambda s: np.sign(s).astype(int),  # momentum dir
        fee_per_trade=FEE_RT,
        n_perms=PERM_N // 2,  # 500 -- block-perm is slower
        block_size=240,
        rng_seed=SEED,
    )
    log.info("  block_perm: obs_t=%.3f null_mean_t=%.3f signal_t_excess=%.3f p_two=%.4f",
             block_perm.get("obs_t", float("nan")),
             block_perm.get("null_mean_t", float("nan")),
             block_perm.get("signal_t_excess", float("nan")),
             block_perm.get("perm_p_two_sided", float("nan")))

    # ---- H4: per-sym signal_t_excess (cross-sym consistency) ----
    log.info("H4: per-sym signal_t_excess ...")
    per_sym_h4 = {}
    cont_count_excess = 0
    n_sym_with_data = 0
    for sym in SYMS:
        if sym not in sym_data:
            continue
        sym_trades = []
        ev = triggers_per_sym.get(sym, pd.DataFrame())
        if not ev.empty:
            ev_ts = list(ev.index)
            ev_dirs = ev["dir"].to_numpy()
            rets = trades_for_events(sym_data[sym]["close_arr"],
                                     sym_data[sym]["ts_to_pos"],
                                     ev_ts, ev_dirs, best_hold)
            valid = rets[~np.isnan(rets)]
            sym_trades = (valid - FEE_RT).tolist()
        if len(sym_trades) < 2:
            per_sym_h4[sym] = {"n": len(sym_trades), "skip": True}
            continue
        # build per-sym candidate pool (this sym only)
        sym_pool = []
        anchors = list(sym_data[sym]["signal"].index)
        if anchors:
            rets_all = forward_returns_for_all_anchors(
                sym_data[sym]["close_arr"], sym_data[sym]["ts_to_pos"],
                anchors, best_hold
            )
            sym_pool = rets_all[~np.isnan(rets_all)].tolist()
        if len(sym_pool) < len(sym_trades) * 2:
            per_sym_h4[sym] = {"n": len(sym_trades), "skip": "pool_small"}
            continue
        sym_perm = fee_aware_perm_test(
            observed_net_returns=sym_trades,
            candidate_pool_returns=sym_pool,
            fee_per_trade=FEE_RT,
            n_perms=300,
            rng_seed=SEED + 1,
        )
        per_sym_h4[sym] = {
            "n": len(sym_trades),
            "obs_t": float(sym_perm["obs_t"]),
            "null_mean_t": float(sym_perm["null_mean_t"]),
            "signal_t_excess": float(sym_perm["signal_t_excess"]),
            "perm_p_two": float(sym_perm["perm_p_two_sided"]),
            "mean_net": float(np.mean(sym_trades)),
        }
        n_sym_with_data += 1
        if sym_perm["signal_t_excess"] >= 1.0:
            cont_count_excess += 1
    log.info("H4: %d/%d syms with signal_t_excess >= 1.0 (data_syms=%d)",
             cont_count_excess, len(SYMS), n_sym_with_data)

    # ---- H5: sign asymmetry -- pos_skew_long vs neg_skew_short ----
    log.info("H5: sign asymmetry...")
    h5 = {}
    for side, sg in [("positive_skew_long", +1), ("negative_skew_short", -1)]:
        side_net = []
        sub_trig = 0
        for sym, ev in triggers_per_sym.items():
            mask = np.sign(ev["skew_z"]).astype(int) == sg
            sub = ev[mask]
            if len(sub) == 0:
                continue
            sub_trig += len(sub)
            ev_ts = list(sub.index)
            ev_dirs = sub["dir"].to_numpy()
            rets = trades_for_events(sym_data[sym]["close_arr"],
                                     sym_data[sym]["ts_to_pos"],
                                     ev_ts, ev_dirs, best_hold)
            valid = rets[~np.isnan(rets)]
            if len(valid):
                side_net.extend((valid - FEE_RT).tolist())
        if len(side_net) < 2:
            h5[side] = {"n": len(side_net), "skip": True}
            continue
        side_perm = fee_aware_perm_test(
            observed_net_returns=side_net,
            candidate_pool_returns=candidate_pool_gross,
            fee_per_trade=FEE_RT,
            n_perms=500,
            rng_seed=SEED + 2,
        )
        side_ci = bootstrap_ci(
            observed_net_returns=side_net,
            n_boot=1000,
            block_size=best_hold,
            rng_seed=SEED + 2,
        )
        h5[side] = {
            "n_trig": int(sub_trig),
            "n_trades": int(len(side_net)),
            "obs_t": float(side_perm["obs_t"]),
            "null_mean_t": float(side_perm["null_mean_t"]),
            "signal_t_excess": float(side_perm["signal_t_excess"]),
            "perm_p_two": float(side_perm["perm_p_two_sided"]),
            "ci_lower": float(side_ci["ci_lower"]),
            "ci_upper": float(side_ci["ci_upper"]),
            "mean_net": float(np.mean(side_net)),
        }
        log.info("  %s: n=%d signal_t_excess=%.3f ci_lower=%.6f p=%.4f",
                 side, len(side_net), side_perm["signal_t_excess"],
                 side_ci["ci_lower"], side_perm["perm_p_two_sided"])

    h5_pos = h5.get("positive_skew_long", {})
    h5_neg = h5.get("negative_skew_short", {})

    def _pass3gate(d):
        if not d or d.get("skip"):
            return False
        return (
            d.get("signal_t_excess", -9) >= 2.0
            and d.get("ci_lower", -9) > 0
            and d.get("perm_p_two", 1) <= 0.10
        )

    h5_consistent = _pass3gate(h5_pos) and _pass3gate(h5_neg)

    # ---- H6: threshold monotonicity (signal_t_excess + ci_lower per |z|) ----
    log.info("H6: threshold grid...")
    h6 = {}
    for z_th in Z_GRID:
        pool_net_z = []
        n_sig_z = 0
        for sym, d in sym_data.items():
            s = d["signal"]
            fire = s["skew_z"].abs() >= z_th
            ev = s[fire].copy()
            ev["dir"] = np.sign(ev["skew_z"]).astype(int)
            ev = ev[ev["dir"] != 0]
            n_sig_z += len(ev)
            if len(ev) == 0:
                continue
            ev_ts = list(ev.index)
            ev_dirs = ev["dir"].to_numpy()
            rets = trades_for_events(d["close_arr"], d["ts_to_pos"],
                                     ev_ts, ev_dirs, best_hold)
            valid = rets[~np.isnan(rets)]
            if len(valid):
                pool_net_z.extend((valid - FEE_RT).tolist())
        if len(pool_net_z) < 2:
            h6[str(z_th)] = {"n_signals": int(n_sig_z), "n_trades": len(pool_net_z), "skip": True}
            continue
        z_perm = fee_aware_perm_test(
            observed_net_returns=pool_net_z,
            candidate_pool_returns=candidate_pool_gross,
            fee_per_trade=FEE_RT,
            n_perms=500,
            rng_seed=SEED + 3,
        )
        z_ci = bootstrap_ci(
            observed_net_returns=pool_net_z,
            n_boot=1000,
            block_size=best_hold,
            rng_seed=SEED + 3,
        )
        h6[str(z_th)] = {
            "n_signals": int(n_sig_z),
            "n_trades": int(len(pool_net_z)),
            "obs_t": float(z_perm["obs_t"]),
            "null_mean_t": float(z_perm["null_mean_t"]),
            "signal_t_excess": float(z_perm["signal_t_excess"]),
            "perm_p_two": float(z_perm["perm_p_two_sided"]),
            "ci_lower": float(z_ci["ci_lower"]),
            "ci_upper": float(z_ci["ci_upper"]),
            "mean_net": float(np.mean(pool_net_z)),
        }
        log.info("  |z|>=%.1f: n_trades=%d signal_t_excess=%.3f ci_lower=%.6f",
                 z_th, len(pool_net_z), z_perm["signal_t_excess"],
                 z_ci["ci_lower"])
    excess_seq = [h6[str(z)].get("signal_t_excess", float("-inf")) for z in Z_GRID]
    monotonic = all(excess_seq[i] <= excess_seq[i + 1] + 1e-6
                    for i in range(len(excess_seq) - 1))
    log.info("H6 signal_t_excess sequence: %s monotonic=%s",
             [round(x, 3) if np.isfinite(x) else None for x in excess_seq],
             monotonic)

    # ---- Verdict ----
    signal_t_excess = fee_perm.get("signal_t_excess", float("nan"))
    perm_p = fee_perm.get("perm_p_two_sided", float("nan"))
    ci_lower = ci.get("ci_lower", float("nan"))
    obs_mean = ci.get("mean", float("nan"))

    # Direction check: best_hold mean must be POSITIVE (momentum), else MR mode reasserts
    direction_ok = obs_mean > 0

    reasons = []
    graveyard = False

    if not direction_ok:
        graveyard = True
        reasons.append(f"direction reversed: obs_mean={obs_mean:.6f} <= 0 (MR mode)")
    if np.isnan(signal_t_excess) or signal_t_excess < 2.0:
        graveyard = True
        reasons.append(f"signal_t_excess={signal_t_excess:.3f} < 2.0")
    if np.isnan(ci_lower) or ci_lower <= 0:
        graveyard = True
        reasons.append(f"bootstrap_ci.lower={ci_lower:.6f} <= 0")
    if np.isnan(perm_p) or perm_p > 0.10:
        graveyard = True
        reasons.append(f"perm_p_two_sided={perm_p:.4f} > 0.10")
    if cont_count_excess < 10:
        graveyard = True
        reasons.append(f"H4: only {cont_count_excess}/14 syms with signal_t_excess>=1 (need >=10)")
    if not h5_consistent:
        graveyard = True
        pos_msg = f"pos_long t_excess={h5_pos.get('signal_t_excess', float('nan')):.2f} ci_l={h5_pos.get('ci_lower', float('nan')):.6f}"
        neg_msg = f"neg_short t_excess={h5_neg.get('signal_t_excess', float('nan')):.2f} ci_l={h5_neg.get('ci_lower', float('nan')):.6f}"
        reasons.append(f"H5 asymmetry: one side fails three-gate ({pos_msg}; {neg_msg})")
    if not monotonic:
        graveyard = True
        reasons.append(f"H6 signal_t_excess not monotonic in |z|: {[round(x, 3) if np.isfinite(x) else None for x in excess_seq]}")

    candidate = (
        not graveyard
        and signal_t_excess >= 2.0
        and ci_lower > 0
        and perm_p <= 0.10
        and cont_count_excess >= 12
        and h5_consistent
        and monotonic
    )
    borderline = (
        not graveyard
        and not candidate
        and (
            (1.5 <= signal_t_excess < 2.0)
            or (-0.0005 <= ci_lower <= 0 and obs_mean > 0)
        )
    )

    if graveyard:
        verdict = "GRAVEYARD"
    elif candidate:
        verdict = "CANDIDATE-FOR-R2"
    elif borderline:
        verdict = "BORDERLINE"
    else:
        verdict = "BORDERLINE"
        reasons.append("neither candidate nor graveyard -> default borderline")

    out = {
        "paradigm": PARADIGM,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "data_window": {
            "first": str(data_first),
            "last": str(data_last),
            "data_days": int(data_days),
        },
        "config": {
            "syms": SYMS,
            "skew_window_bars": SKEW_WINDOW,
            "hourly_stride_min": HOURLY_STRIDE,
            "z_window_hourly_bars": Z_WINDOW_HRS,
            "z_primary": Z_PRIMARY,
            "z_grid": Z_GRID,
            "holds_min": HOLDS,
            "fee_round_trip": FEE_RT,
            "perm_n": PERM_N,
            "boot_n": BOOT_N,
            "trade_direction": "+sign(skew_z) (momentum continuation)",
        },
        "trigger_summary": {
            "n_triggers_total": int(total_trig),
            "per_sym": {sym: int(len(ev)) for sym, ev in triggers_per_sym.items()},
        },
        "H1_per_hold": per_hold,
        "H1_best_hold_min": int(best_hold),
        "H1_per_sym_at_best": per_sym_by_hold[str(best_hold)],
        "H2_fee_aware_perm": {
            "obs_t": float(fee_perm["obs_t"]),
            "null_mean_t": float(fee_perm["null_mean_t"]),
            "null_std_t": float(fee_perm["null_std_t"]),
            "signal_t_excess": float(fee_perm["signal_t_excess"]),
            "perm_p_two_sided": float(fee_perm["perm_p_two_sided"]),
            "perm_p_one_sided_above": float(fee_perm["perm_p_one_sided_above"]),
            "n_observed": int(fee_perm["n_observed"]),
            "n_candidate": int(fee_perm["n_candidate"]),
        },
        "H2b_bootstrap_ci": {
            "mean": float(ci["mean"]),
            "ci_lower": float(ci["ci_lower"]),
            "ci_upper": float(ci["ci_upper"]),
            "prob_positive": float(ci["prob_positive"]),
            "n": int(ci["n"]),
            "block_size": int(ci.get("block_size", best_hold)),
        },
        "H3_block_perm_sensitivity": {
            "obs_t": float(block_perm.get("obs_t", float("nan"))),
            "null_mean_t": float(block_perm.get("null_mean_t", float("nan"))),
            "null_std_t": float(block_perm.get("null_std_t", float("nan"))),
            "signal_t_excess": float(block_perm.get("signal_t_excess", float("nan"))),
            "perm_p_two_sided": float(block_perm.get("perm_p_two_sided", float("nan"))),
            "n_observed": int(block_perm.get("n_observed", 0)),
            "block_size": int(block_perm.get("block_size", 240)),
        },
        "H4_per_sym": per_sym_h4,
        "H4_consistent_count_excess1": int(cont_count_excess),
        "H4_syms_total_with_data": int(n_sym_with_data),
        "H5_asymmetry": h5,
        "H5_consistent_both_sides": bool(h5_consistent),
        "H6_threshold_grid": h6,
        "H6_signal_t_excess_sequence": [
            float(x) if np.isfinite(x) else None for x in excess_seq
        ],
        "H6_monotonic": bool(monotonic),
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", OUT_PATH)
    log.info("VERDICT: %s", verdict)
    for r in reasons:
        log.info("  reason: %s", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
