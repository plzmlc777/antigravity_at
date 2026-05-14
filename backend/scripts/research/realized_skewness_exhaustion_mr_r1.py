"""R-1 PoC -- realized_skewness_exhaustion_mr.

Hypothesis
----------
Within 14 Binance USDT-perp universe, when the realized SKEWNESS of 1m
log-returns over a trailing 1-hour window reaches a z-score (vs 30-day
rolling 1h-skew distribution) with |z| >= 2, the next 30-60 minutes
exhibit systematic price MEAN-REVERSION against the skew sign
(positive skew -> short, negative skew -> long).

Mechanism
---------
- Positive 1h skew  = right-tail jumps -> up-side over-extension. Bias short.
- Negative 1h skew  = down-jump cascade -> exhaustion bounce. Bias long.
- 3rd statistical moment as a NEW data dimension (no seeded paradigm uses
  higher-order moments).

Trigger
-------
- For each sym, 1m ohlcv -> 1m log-returns.
- Realized skewness over trailing 60 1m bars, computed ONLY at hourly
  anchors (timestamp.minute == 0) for cost efficiency.
- 30-day rolling z-score of skew: window = 30 * 24 = 720 hourly bars.
- Trigger event: |skew_z| >= 2 (per |z| grid in H6 -- primary cut |z|>=2).
- Trigger sign = sign(skew_z). Trade direction = -sign(skew_z) (MR).

Trade
-----
For each trigger at sym `s`, hourly close timestamp `t`:
- Entry on `s` at close[t+1m] (1m execution lag).
- Hold H in {30, 60, 90, 120} min -> exit close[t+1+H].
- Gross return = -sign(skew_z) * (exit/entry - 1).
- Net return  = gross - 8e-4 (8 bp round-trip).

Output
------
backend/runs/research_track/realized_skewness_exhaustion_mr/r1__metrics.json
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rsk_mr_r1")

PARADIGM = "realized_skewness_exhaustion_mr"
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
PERM_N = 500
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

    # Build hourly anchor positions (timestamp.minute == 0).
    minute_arr = ts_idx.minute.to_numpy()
    anchor_positions = np.where(minute_arr == 0)[0]
    # Drop anchors with insufficient lookback
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

    # 30-day rolling z-score on hourly skew
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
    triggers_per_sym = {}
    total_trig = 0
    for sym, d in sym_data.items():
        s = d["signal"]
        fire = s["skew_z"].abs() >= Z_PRIMARY
        ev = s[fire].copy()
        ev["dir"] = -np.sign(ev["skew_z"]).astype(int)
        ev = ev[ev["dir"] != 0]
        triggers_per_sym[sym] = ev
        total_trig += len(ev)
        log.info("  triggers %s @|z|>=%.1f: %d (pos_skew=%d neg_skew=%d)",
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
        log.info("  pooled n=%d net_mean=%.5f net_t=%.2f win_rate=%.3f",
                 len(pn),
                 float(np.mean(pn)) if len(pn) else float("nan"),
                 t_stat(pn),
                 float(np.mean(pn > 0)) if len(pn) else float("nan"))

    # Best hold by |t_stat|
    def _t_for(H):
        v = per_hold[str(H)]["net"].get("t_stat")
        return abs(v) if (v is not None and not np.isnan(v)) else 0
    best_hold = max(HOLDS, key=_t_for)
    best = per_hold[str(best_hold)]
    log.info("best hold by |t|: %d min, t=%.2f, net_mean=%.5f",
             best_hold, best["net"]["t_stat"], best["net"]["mean"])

    # ---- H2: ann alpha ----
    h2_per_sym = {}
    best_per_sym = per_sym_by_hold[str(best_hold)]
    for sym, ev in triggers_per_sym.items():
        d_sym = best_per_sym.get(sym, {"n": 0})
        if d_sym.get("n", 0) > 0:
            ny = len(ev) * (365.0 / max(data_days, 1))
            h2_per_sym[sym] = {
                "n_trades": d_sym["n"],
                "mean_net": d_sym["mean_net"],
                "ann_alpha_estimate": float(d_sym["mean_net"] * ny),
                "triggers_per_year": float(ny),
            }
    total_trigs_per_year = total_trig * (365.0 / max(data_days, 1))
    portfolio_ann = best["net"]["mean"] * total_trigs_per_year
    log.info("H2: total triggers/yr=%.1f portfolio_ann=%.4f",
             total_trigs_per_year, portfolio_ann)

    # ---- H3: permutation null at best hold ----
    log.info("H3: permutation null (n=%d) at hold=%d ...", PERM_N, best_hold)
    rng = np.random.default_rng(SEED)
    per_sym_anchors = {sym: list(d["signal"].index) for sym, d in sym_data.items()}
    per_sym_trig_count = {sym: len(ev) for sym, ev in triggers_per_sym.items()}

    perm_t = np.full(PERM_N, np.nan)
    for k in range(PERM_N):
        all_net = []
        for sym, n_trig in per_sym_trig_count.items():
            if n_trig == 0:
                continue
            anchors = per_sym_anchors[sym]
            if len(anchors) < n_trig:
                continue
            sample_pos = rng.choice(len(anchors), size=n_trig, replace=False)
            sample_ts = [anchors[i] for i in sample_pos]
            signs = rng.choice([-1, 1], size=n_trig)
            rets = trades_for_events(sym_data[sym]["close_arr"],
                                     sym_data[sym]["ts_to_pos"],
                                     sample_ts, signs, best_hold)
            valid_r = rets[~np.isnan(rets)]
            if len(valid_r):
                all_net.extend((valid_r - FEE_RT).tolist())
        if len(all_net) > 1:
            arr = np.array(all_net)
            sd = np.std(arr, ddof=1)
            if sd > 0:
                perm_t[k] = np.mean(arr) / (sd / np.sqrt(len(arr)))
        if (k + 1) % 100 == 0:
            log.info("  perm progress: %d/%d", k + 1, PERM_N)

    obs_t = best["net"]["t_stat"]
    ts_arr = perm_t[~np.isnan(perm_t)]
    p_two = float(np.mean(np.abs(ts_arr) >= abs(obs_t))) if len(ts_arr) else None
    perm_out = {
        "obs_t": float(obs_t),
        "perm_p_two_sided": p_two,
        "perm_n_done": int(len(ts_arr)),
        "perm_t_mean": float(np.mean(ts_arr)) if len(ts_arr) else None,
        "perm_t_std": float(np.std(ts_arr)) if len(ts_arr) else None,
    }
    log.info("H3: perm_p=%s", perm_out.get("perm_p_two_sided"))

    # ---- H4: cross-sym consistency ----
    cont_count = sum(1 for sym, d in best_per_sym.items()
                     if d.get("n", 0) > 0 and (d.get("t_stat") or 0) > 1.0)
    opp_count = sum(1 for sym, d in best_per_sym.items()
                    if d.get("n", 0) > 0 and (d.get("t_stat") or 0) < -1.0)
    n_sym_with_data = sum(1 for d in best_per_sym.values() if d.get("n", 0) > 0)
    log.info("H4: consistent syms (t>+1)=%d / opposite (t<-1)=%d / data_syms=%d",
             cont_count, opp_count, n_sym_with_data)

    # ---- H5: skew sign asymmetry ----
    h5 = {}
    for side, sg in [("positive_skew_short", +1), ("negative_skew_long", -1)]:
        pool = []
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
            valid_r = rets[~np.isnan(rets)]
            if len(valid_r):
                pool.extend((valid_r - FEE_RT).tolist())
        arr = np.array(pool)
        h5[side] = {
            "n_trig": int(sub_trig),
            "n_trades": int(len(arr)),
            "mean_net": float(np.mean(arr)) if len(arr) else float("nan"),
            "t_stat": t_stat(arr) if len(arr) else float("nan"),
            "win_rate": float(np.mean(arr > 0)) if len(arr) else float("nan"),
        }
    pos_mn = h5.get("positive_skew_short", {}).get("mean_net", float("nan"))
    neg_mn = h5.get("negative_skew_long", {}).get("mean_net", float("nan"))
    h5_consistent = (
        not np.isnan(pos_mn) and not np.isnan(neg_mn)
        and pos_mn > 0 and neg_mn > 0
    )
    log.info("H5: pos_skew_short_mn=%.5f neg_skew_long_mn=%.5f consistent=%s",
             pos_mn, neg_mn, h5_consistent)

    # ---- H6: threshold robustness ----
    h6 = {}
    for z_th in Z_GRID:
        pool_net_z = []
        n_sig_z = 0
        for sym, d in sym_data.items():
            s = d["signal"]
            fire = s["skew_z"].abs() >= z_th
            ev = s[fire].copy()
            ev["dir"] = -np.sign(ev["skew_z"]).astype(int)
            ev = ev[ev["dir"] != 0]
            n_sig_z += len(ev)
            if len(ev) == 0:
                continue
            ev_ts = list(ev.index)
            ev_dirs = ev["dir"].to_numpy()
            rets = trades_for_events(d["close_arr"], d["ts_to_pos"],
                                     ev_ts, ev_dirs, best_hold)
            valid_r = rets[~np.isnan(rets)]
            if len(valid_r):
                pool_net_z.extend((valid_r - FEE_RT).tolist())
        arr = np.array(pool_net_z)
        if len(arr) > 1:
            mn = float(np.mean(arr))
            ts_z = t_stat(arr)
            sd_z = float(np.std(arr, ddof=1))
            sharpe = float(mn / sd_z * np.sqrt(len(arr))) if sd_z > 0 else float("nan")
        else:
            mn = float("nan"); ts_z = float("nan"); sharpe = float("nan")
        h6[str(z_th)] = {
            "n_signals": int(n_sig_z),
            "n_trades": int(len(arr)),
            "mean_net": mn,
            "t_stat": ts_z,
            "sharpe_trade": sharpe,
        }
        log.info("  H6 |z|>=%.1f: n_sig=%d t=%.3f mn=%.6f",
                 z_th, n_sig_z, ts_z if not np.isnan(ts_z) else 0.0,
                 mn if not np.isnan(mn) else 0.0)
    t_seq = [abs(h6[str(z)]["t_stat"]) if not np.isnan(h6[str(z)]["t_stat"]) else 0
             for z in Z_GRID]
    monotonic = all(t_seq[i] <= t_seq[i + 1] + 1e-9 for i in range(len(t_seq) - 1))
    log.info("H6 |t| sequence by z: %s monotonic=%s",
             [round(x, 3) for x in t_seq], monotonic)

    # ---- Verdict ----
    reasons = []
    graveyard = False
    if obs_t is None or np.isnan(obs_t) or abs(obs_t) < 1.8:
        graveyard = True
        reasons.append(f"|H1 t|={obs_t} < 1.8")
    if best["net"]["mean"] <= 0:
        graveyard = True
        reasons.append(f"H2 net_mean={best['net']['mean']:.6f} <= 0 after fee")
    p_two_val = perm_out.get("perm_p_two_sided")
    if p_two_val is not None and p_two_val > 0.05:
        graveyard = True
        reasons.append(f"H3 perm_p={p_two_val:.3f} > 0.05")
    if total_trig < 500:
        graveyard = True
        reasons.append(f"H4 total triggers={total_trig} < 500")
    if cont_count < 8:
        graveyard = True
        reasons.append(f"H4 only {cont_count}/14 syms consistent (need >=8)")
    if not h5_consistent:
        graveyard = True
        reasons.append("H5 sign asymmetry inconsistent (one side not positive)")
    if not monotonic:
        graveyard = True
        reasons.append(f"H6 |t| not monotonic in |z|: {[round(x, 3) for x in t_seq]}")

    candidate = (
        not graveyard
        and abs(obs_t) >= 2.5
        and best["net"]["mean"] > 0
        and (p_two_val is not None and p_two_val <= 0.01)
        and cont_count >= 10
        and h5_consistent
        and monotonic
    )
    borderline = (
        not graveyard
        and not candidate
        and (
            (1.8 <= abs(obs_t) < 2.5)
            or (p_two_val is not None and 0.01 < p_two_val <= 0.05)
        )
        and best["net"]["mean"] > 0
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
        },
        "trigger_summary": {
            "n_triggers_total": int(total_trig),
            "per_sym": {sym: int(len(ev)) for sym, ev in triggers_per_sym.items()},
            "triggers_per_year_est": float(total_trigs_per_year),
        },
        "H1_per_hold": per_hold,
        "H1_best_hold_min": int(best_hold),
        "H1_per_sym_at_best": best_per_sym,
        "H2_portfolio_ann_alpha": float(portfolio_ann),
        "H2_per_sym": h2_per_sym,
        "H3_perm": perm_out,
        "H4_consistent_count": int(cont_count),
        "H4_opposite_count": int(opp_count),
        "H4_syms_total_with_data": int(n_sym_with_data),
        "H5_asymmetry": h5,
        "H5_consistent_both_sides": bool(h5_consistent),
        "H6_threshold_grid": h6,
        "H6_t_sequence": [float(x) for x in t_seq],
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
