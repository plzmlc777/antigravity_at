"""R-3.5 regime-filtered booster — btc_rv_spike_up_conditional_alt_long_240m.

R-3 PASS on aggregate but regime-stratification revealed (parent agent
a2af06d5019564312, 2026-05-14):
- UNKNOWN vol (365d lookback unfulfilled): n=1144 mean=+57.57 bp t=+6.44 (alpha source)
- HIGH vol: n=689 mean=-20.11 bp t=-1.94 (FAIL)
- MID vol: n=793 mean=-15.18 bp t=-2.39 (FAIL)
- WF Fold 4 (2026Q1): -42.71 bp t=-4.96 (regime shift)

UNKNOWN bucket is inadmissible for live trading (lookback always fulfilled in
production). R-3.5 asks: does a LOW vol bucket (using a SHORTER 90d lookback)
carry genuine alpha?

R-3.5 SCOPE (parent directive)
==============================
1. Shorten vol lookback: 30d rolling realized vol vs past-90d p25/p75
   (instead of past-365d). UNKNOWN shrinks to first 90d only (~< 200 trades).
2. Per-bucket stats with shorter lookback (same best cell h=300m SL=-5% TP=none).
3. Define `lowvol_filter` variant: entry only when BTC 30d vol < p50 of past 90d.
4. Re-run filtered variant: full sample, stats + bootstrap + perm.
5. Quarterly fold on filtered variant.
6. WF 5-fold on filtered variant.
7. Plateau persistence on filtered variant.
8. Comparison vs unfiltered R-3 best cell.

Constraints
-----------
- ≤20 min wall-clock foreground
- Re-uses R-3 trigger / sim logic verbatim — just adds vol filter
- Best cell only for filter analysis (no full grid re-sweep)

Output
------
backend/runs/research_track/btc_rv_spike_up_conditional_alt_long_240m/r3_5__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("btc_rv_up_r3_5")

PARADIGM = "btc_rv_spike_up_conditional_alt_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r3_5__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# IDENTICAL TO R-2 / R-3
RV_WINDOW = 30
Z_WINDOW = 30 * 24 * 60
Z_THRESH = 2.5
COOLDOWN = 60
FEE_RT = 8e-4
BEST_HOLD = 300
BEST_SL = 0.05
BEST_TP = None

# R-3.5: shorter vol lookback for regime classification
VOL_LOOKBACK_BARS = 30 * 24 * 60   # 30 day RV (same as R-3 rv_30d)
VOL_DIST_BARS = 90 * 24 * 60       # NEW: compare to 90d (not 365d) percentile distribution
VOL_MIN_PERIODS = 90 * 24 * 60     # require full 90d before classifying (first 90d = UNKNOWN)

# Plateau grid for filtered variant (smaller — confirm robustness)
HOLDS = [180, 240, 300, 360]
SLS = [None, 0.05]
TPS = [None, 0.05, 0.08]

WF_K = 5
N_PERMS = 1000
N_BOOT = 2000
SEED = 42


# ---------- data ----------


def load_ohlcv_1m(db, sym: str) -> pd.DataFrame:
    rows = db.execute(
        text(
            "SELECT timestamp, open, high, low, close FROM ohlcv "
            "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
        ),
        {"s": sym},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[~df.index.duplicated(keep="first")]
    return df


def compute_btc_signal(btc: pd.DataFrame) -> pd.DataFrame:
    lr = np.log(btc["close"]).diff()
    rv = lr.rolling(RV_WINDOW, min_periods=RV_WINDOW).std()
    rv_mu = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    rv_sd = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    rv_z = (rv - rv_mu) / rv_sd
    btc_ret_30m = btc["close"] / btc["close"].shift(RV_WINDOW) - 1
    sig = pd.DataFrame({"rv": rv, "rv_z": rv_z, "btc_ret_30m": btc_ret_30m}).dropna()
    return sig


def extract_triggers(sig: pd.DataFrame, z_thresh: float = Z_THRESH) -> pd.DataFrame:
    z_prev = sig["rv_z"].shift(1)
    fire = (sig["rv_z"] > z_thresh) & (z_prev <= z_thresh)
    triggers = sig[fire].copy()
    triggers = triggers[triggers["btc_ret_30m"] > 0]
    if len(triggers) == 0:
        return triggers
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


# ---------- R-3.5 short-lookback vol regime ----------


def compute_btc_vol_regime_short(btc: pd.DataFrame) -> pd.DataFrame:
    """Vol regime using 30d realized vol vs past-90d p25/p50/p75 distribution.

    - rv_30d: rolling 30d std of log returns, annualized via sqrt(60*24)
    - p25/p50/p75: rolling 90d windows of rv_30d
    - regime: HIGH (> p75), MID (p25..p75), LOW (< p25), UNKNOWN (first 90d)

    Also returns boolean filter `lowvol_filter`: rv_30d < p50 (covers LOW + half of MID).
    """
    close = btc["close"]
    lr = np.log(close).diff()
    rv_30d = lr.rolling(VOL_LOOKBACK_BARS, min_periods=VOL_LOOKBACK_BARS).std() * np.sqrt(60 * 24)
    rv_p25 = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(0.25)
    rv_p50 = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(0.50)
    rv_p75 = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(0.75)

    vol = pd.Series(index=close.index, dtype="object")
    vol.loc[rv_30d > rv_p75] = "HIGH"
    vol.loc[(rv_30d <= rv_p75) & (rv_30d >= rv_p25)] = "MID"
    vol.loc[rv_30d < rv_p25] = "LOW"
    vol = vol.fillna("UNKNOWN")

    lowvol_filter = (rv_30d < rv_p50) & rv_30d.notna() & rv_p50.notna()

    return pd.DataFrame({
        "rv_30d": rv_30d,
        "p25": rv_p25,
        "p50": rv_p50,
        "p75": rv_p75,
        "vol_regime": vol,
        "lowvol_filter": lowvol_filter.fillna(False).astype(bool),
    })


# ---------- trade simulation (identical to R-3) ----------


def simulate_trade(high_arr, low_arr, close_arr, ts_to_pos, trig_ts, hold_min, sl, tp):
    entry_ts = trig_ts + pd.Timedelta(minutes=1)
    final_exit_ts = trig_ts + pd.Timedelta(minutes=1 + hold_min)
    ei = ts_to_pos.get(entry_ts)
    xi = ts_to_pos.get(final_exit_ts)
    if ei is None or xi is None:
        return float("nan"), "invalid"
    entry_p = close_arr[ei]
    if not (entry_p > 0) or np.isnan(entry_p):
        return float("nan"), "invalid"
    bar_lows = low_arr[ei + 1 : xi + 1]
    bar_highs = high_arr[ei + 1 : xi + 1]
    bar_closes = close_arr[ei + 1 : xi + 1]
    if len(bar_closes) == 0:
        return float("nan"), "invalid"
    sl_price = entry_p * (1.0 - sl) if sl else None
    tp_price = entry_p * (1.0 + tp) if tp else None
    exit_reason = "time"
    exit_price = bar_closes[-1]
    for k in range(len(bar_closes)):
        lo = bar_lows[k]
        hi = bar_highs[k]
        sl_hit = sl_price is not None and not np.isnan(lo) and lo <= sl_price
        tp_hit = tp_price is not None and not np.isnan(hi) and hi >= tp_price
        if sl_hit:
            exit_price = sl_price
            exit_reason = "sl"
            break
        if tp_hit:
            exit_price = tp_price
            exit_reason = "tp"
            break
    gross = exit_price / entry_p - 1.0
    return float(gross), exit_reason


def run_cell(alt_data, alt_lookup, triggers, hold, sl, tp):
    """Run one (hold,sl,tp) cell across all alts × all triggers."""
    nets, sym_list, ts_list = [], [], []
    trig_idx = list(triggers.index)
    for sym, df_dict in alt_data.items():
        ha = df_dict["high"]
        la = df_dict["low"]
        ca = df_dict["close"]
        ts_pos = alt_lookup[sym]
        for trig_ts in trig_idx:
            gross, _reason = simulate_trade(ha, la, ca, ts_pos, trig_ts, hold, sl, tp)
            if np.isnan(gross):
                continue
            net = gross - FEE_RT
            nets.append(net)
            sym_list.append(sym)
            ts_list.append(trig_ts)
    nets_arr = np.array(nets, dtype=float)
    if len(nets_arr) < 2:
        return {
            "hold": hold, "sl": sl, "tp": tp,
            "n_trades": 0, "net_mean_bp": float("nan"),
            "t": float("nan"), "win": float("nan"),
            "sharpe": float("nan"),
            "nets": [], "sym": [], "ts": [],
        }
    n = len(nets_arr)
    mn = float(nets_arr.mean())
    sd = float(nets_arr.std(ddof=1))
    t_stat = mn / sd * np.sqrt(n) if sd > 0 else 0.0
    return {
        "hold": hold, "sl": sl, "tp": tp,
        "n_trades": n,
        "net_mean_bp": mn * 1e4,
        "t": t_stat,
        "win": float((nets_arr > 0).mean()),
        "sharpe": mn / sd if sd > 0 else 0.0,
        "nets": nets_arr.tolist(),
        "sym": sym_list,
        "ts": [str(x) for x in ts_list],
    }


def build_candidate_pool(alt_data, alt_lookup, hold, sl, tp, n_samples=20000, seed=SEED):
    rng = np.random.default_rng(seed)
    pool = []
    sym_keys = list(alt_data.keys())
    for sym in sym_keys:
        ha = alt_data[sym]["high"]
        la = alt_data[sym]["low"]
        ca = alt_data[sym]["close"]
        ts_pos = alt_lookup[sym]
        ts_list = list(ts_pos.keys())
        n_per_sym = n_samples // len(sym_keys)
        max_i = len(ts_list) - hold - 5
        if max_i <= 0:
            continue
        idxs = rng.choice(max_i, size=min(n_per_sym, max_i), replace=False)
        for idx in idxs:
            trig_ts = ts_list[idx]
            gross, _ = simulate_trade(ha, la, ca, ts_pos, trig_ts, hold, sl, tp)
            if not np.isnan(gross):
                pool.append(gross)
    return np.array(pool, dtype=float)


# ---------- main ----------


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "phase": "R-3.5",
        "config": {
            "rv_window_bars": RV_WINDOW,
            "z_window_bars": Z_WINDOW,
            "z_thresh": Z_THRESH,
            "cooldown_min": COOLDOWN,
            "fee_round_trip": FEE_RT,
            "best_hold": BEST_HOLD,
            "best_sl": BEST_SL,
            "best_tp": BEST_TP,
            "vol_lookback_bars": VOL_LOOKBACK_BARS,
            "vol_dist_bars": VOL_DIST_BARS,
            "vol_min_periods": VOL_MIN_PERIODS,
            "vol_classification": "30d_rv_vs_90d_p25_p50_p75",
            "filter_rule": "lowvol_filter = (rv_30d < p50_of_past_90d)",
            "plateau_holds": HOLDS,
            "plateau_sls": SLS,
            "plateau_tps": TPS,
            "wf_k": WF_K,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
        },
        "r3_baseline_reference": {
            "n_trades": 2626,
            "net_mean_bp": 15.22,
            "t": 2.94,
            "signal_t_excess": 5.29,
            "ci_lower_bp": 8.04,
            "fold4_mean_bp": -42.71,
            "fold4_t": -4.96,
        },
    }

    db = SessionLocal()
    try:
        log.info("Loading BTC ohlcv 1m ...")
        btc = load_ohlcv_1m(db, BTC)
        if btc.empty:
            raise SystemExit("BTC ohlcv empty")
        log.info("BTC bars=%d range=%s..%s", len(btc), btc.index[0], btc.index[-1])
        out["data_window"] = {
            "btc_first": str(btc.index[0]),
            "btc_last": str(btc.index[-1]),
            "btc_bars": int(len(btc)),
        }

        log.info("Computing BTC RV signal ...")
        sig = compute_btc_signal(btc)

        log.info("Computing R-3.5 short-lookback vol regime (30d_rv vs 90d_dist) ...")
        vol_df = compute_btc_vol_regime_short(btc)

        log.info("Extracting triggers (z=%.2f, up-only, cooldown=%d min) ...", Z_THRESH, COOLDOWN)
        triggers = extract_triggers(sig, z_thresh=Z_THRESH)
        log.info("Found %d unfiltered triggers", len(triggers))
        out["n_triggers_unfiltered"] = int(len(triggers))

        log.info("Loading %d alts ...", len(ALTS))
        alt_data = {}
        alt_lookup = {}
        for sym in ALTS:
            df = load_ohlcv_1m(db, sym)
            if df.empty:
                log.warning("alt %s empty", sym)
                continue
            alt_data[sym] = {
                "high": df["high"].values,
                "low": df["low"].values,
                "close": df["close"].values,
                "index": df.index,
            }
            alt_lookup[sym] = {ts: i for i, ts in enumerate(df.index)}
        log.info("loaded %d alts", len(alt_data))

        # ============================================================
        # STEP 1 + 2: re-classify regime, per-bucket stats on best cell
        # ============================================================
        log.info("[Step 1+2] Best-cell re-run + short-lookback regime stratification ...")
        best = run_cell(alt_data, alt_lookup, triggers, BEST_HOLD, BEST_SL, BEST_TP)
        nets = np.array(best["nets"])
        per_trade_ts = pd.to_datetime(best["ts"])

        out["best_cell_recheck"] = {
            "n_trades": best["n_trades"],
            "net_mean_bp": best["net_mean_bp"],
            "t": best["t"],
            "win": best["win"],
            "sharpe": best["sharpe"],
        }
        log.info("best recheck: n=%d net=%.2f bp t=%.2f", best["n_trades"], best["net_mean_bp"], best["t"])

        # Tag each trade with new short-lookback vol regime
        regimes_at_trade = []
        for ts in per_trade_ts:
            if ts in vol_df.index:
                regimes_at_trade.append(vol_df.at[ts, "vol_regime"])
            else:
                regimes_at_trade.append("UNKNOWN")
        regimes_arr = np.array(regimes_at_trade)

        # Build candidate pool ONCE
        log.info("Building candidate pool (n=20000) ...")
        pool = build_candidate_pool(alt_data, alt_lookup, BEST_HOLD, BEST_SL, BEST_TP,
                                    n_samples=20000, seed=SEED)
        log.info("pool size=%d", len(pool))

        # Per-bucket
        short_vol_break = {}
        for b in sorted(set(regimes_arr)):
            mask = regimes_arr == b
            sub = nets[mask]
            if len(sub) < 5:
                short_vol_break[b] = {"n": int(len(sub)), "note": "insufficient"}
                continue
            m = float(sub.mean())
            s = float(sub.std(ddof=1))
            t_s = m / s * np.sqrt(len(sub)) if s > 0 else 0.0
            try:
                fe = fee_aware_perm_test(
                    observed_net_returns=sub,
                    candidate_pool_returns=pool,
                    fee_per_trade=FEE_RT,
                    n_perms=400,
                    rng_seed=SEED,
                )
                sig_t_excess = fe.get("signal_t_excess")
                perm_p = fe.get("perm_p_one_sided_above")
            except Exception:
                sig_t_excess, perm_p = None, None
            try:
                bs = bootstrap_ci(sub, n_boot=500, block_size=1, rng_seed=SEED)
                ci_lower = bs["ci_lower"] * 1e4
            except Exception:
                ci_lower = None
            short_vol_break[b] = {
                "n": int(len(sub)),
                "mean_net_bp": m * 1e4,
                "t": t_s,
                "win": float((sub > 0).mean()),
                "signal_t_excess": sig_t_excess,
                "perm_p_above": perm_p,
                "ci_lower_bp": ci_lower,
            }
        out["short_lookback_vol_stratification"] = short_vol_break
        for b, info in short_vol_break.items():
            if isinstance(info, dict) and "mean_net_bp" in info:
                log.info("  vol=%s n=%d mean=%+.2f bp t=%+.2f sig_t_ex=%s",
                         b, info["n"], info["mean_net_bp"], info["t"],
                         f"{info.get('signal_t_excess'):+.2f}" if info.get("signal_t_excess") is not None else "NA")

        # ============================================================
        # STEP 3: lowvol_filter variant — filter triggers by BTC vol < p50
        # ============================================================
        log.info("[Step 3] lowvol_filter variant: filter triggers by rv_30d < p50_of_past_90d ...")
        triggers_lowvol = triggers.copy()
        keep_mask = []
        for ts in triggers_lowvol.index:
            if ts in vol_df.index:
                keep_mask.append(bool(vol_df.at[ts, "lowvol_filter"]))
            else:
                keep_mask.append(False)
        triggers_lowvol = triggers_lowvol[keep_mask]
        log.info("filtered triggers: %d / %d (%.1f%% retained)",
                 len(triggers_lowvol), len(triggers),
                 100.0 * len(triggers_lowvol) / max(len(triggers), 1))
        out["n_triggers_filtered"] = int(len(triggers_lowvol))
        out["trigger_retention_ratio"] = (len(triggers_lowvol) / max(len(triggers), 1))

        # Run filtered best cell
        filt = run_cell(alt_data, alt_lookup, triggers_lowvol, BEST_HOLD, BEST_SL, BEST_TP)
        filt_nets = np.array(filt["nets"])
        filt_ts = pd.to_datetime(filt["ts"])
        log.info("filtered best cell: n=%d mean=%+.2f bp t=%+.2f sharpe=%+.4f",
                 filt["n_trades"], filt["net_mean_bp"], filt["t"], filt["sharpe"])

        if len(filt_nets) < 50:
            log.warning("filtered variant n<50, statistics unreliable")
            out["filtered_best_cell"] = {
                "n_trades": filt["n_trades"],
                "note": "n<50, halting filtered analysis",
            }
            out["verdict"] = "FAIL"
            out["verdict_reasons_fail"] = [f"filtered n={filt['n_trades']} too small"]
            out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return

        # Bootstrap + perm on filtered best cell
        try:
            bs_f = bootstrap_ci(filt_nets, n_boot=N_BOOT, block_size=1, rng_seed=SEED)
            filt_ci = {
                "mean_bp": bs_f["mean"] * 1e4,
                "ci_lower_bp": bs_f["ci_lower"] * 1e4,
                "ci_upper_bp": bs_f["ci_upper"] * 1e4,
                "prob_positive": bs_f["prob_positive"],
                "n": bs_f["n"],
            }
        except Exception as exc:
            filt_ci = {"error": str(exc)}
        try:
            fe_f = fee_aware_perm_test(
                observed_net_returns=filt_nets,
                candidate_pool_returns=pool,
                fee_per_trade=FEE_RT,
                n_perms=N_PERMS,
                rng_seed=SEED,
            )
            filt_perm = {
                "obs_mean_bp": fe_f["obs_mean"] * 1e4,
                "obs_t": fe_f["obs_t"],
                "null_mean_t": fe_f["null_mean_t"],
                "signal_t_excess": fe_f["signal_t_excess"],
                "perm_p_above": fe_f["perm_p_one_sided_above"],
                "perm_p_two_sided": fe_f["perm_p_two_sided"],
                "n_observed": fe_f["n_observed"],
                "n_candidate": fe_f["n_candidate"],
            }
        except Exception as exc:
            filt_perm = {"error": str(exc)}

        out["filtered_best_cell"] = {
            "n_trades": filt["n_trades"],
            "net_mean_bp": filt["net_mean_bp"],
            "t": filt["t"],
            "win": filt["win"],
            "sharpe": filt["sharpe"],
            "bootstrap": filt_ci,
            "fee_aware_perm": filt_perm,
        }

        # ============================================================
        # STEP 4: quarterly fold on filtered variant
        # ============================================================
        log.info("[Step 4] Quarterly fold on filtered variant ...")
        quarter_edges = [
            ("2025Q3", pd.Timestamp("2025-07-01"), pd.Timestamp("2025-10-01")),
            ("2025Q4", pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")),
            ("2026Q1", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")),
            ("2026Q2", pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")),
        ]
        quarterly = []
        for qname, qstart, qend in quarter_edges:
            mask = (filt_ts >= qstart) & (filt_ts < qend)
            sub = filt_nets[mask.values] if hasattr(mask, "values") else filt_nets[mask]
            if len(sub) < 5:
                quarterly.append({
                    "quarter": qname, "n": int(len(sub)), "note": "insufficient",
                })
                continue
            m = float(sub.mean())
            s = float(sub.std(ddof=1))
            t_s = m / s * np.sqrt(len(sub)) if s > 0 else 0.0
            quarterly.append({
                "quarter": qname,
                "n": int(len(sub)),
                "mean_net_bp": m * 1e4,
                "t": t_s,
                "win": float((sub > 0).mean()),
            })
        out["quarterly_fold_filtered"] = quarterly
        q_pos = sum(1 for q in quarterly if q.get("mean_net_bp", 0) > 0)
        q1_2026 = next((q for q in quarterly if q.get("quarter") == "2026Q1"), None)
        out["quarterly_pos_count"] = q_pos
        out["q1_2026_mean_bp"] = q1_2026.get("mean_net_bp") if q1_2026 else None

        # ============================================================
        # STEP 5: WF 5-fold on filtered variant
        # ============================================================
        log.info("[Step 5] WF 5-fold on filtered variant ...")
        ts_arr = filt_ts.values
        sort_idx = np.argsort(ts_arr)
        nets_sorted = filt_nets[sort_idx]
        ts_sorted = ts_arr[sort_idx]
        t_min, t_max = ts_sorted[0], ts_sorted[-1]
        span = t_max - t_min
        fold_edges = [t_min + (span * k / WF_K) for k in range(WF_K + 1)]
        wf_folds = []
        for k in range(WF_K):
            mask = (ts_sorted >= fold_edges[k]) & (ts_sorted < fold_edges[k + 1])
            if k == WF_K - 1:
                mask = mask | (ts_sorted == fold_edges[-1])
            sub = nets_sorted[mask]
            if len(sub) < 5:
                wf_folds.append({"fold": k + 1, "n": int(len(sub)), "note": "insufficient"})
                continue
            m = float(sub.mean())
            s = float(sub.std(ddof=1))
            t_s = m / s * np.sqrt(len(sub)) if s > 0 else 0.0
            wf_folds.append({
                "fold": k + 1,
                "n": int(len(sub)),
                "mean_net_bp": m * 1e4,
                "t": t_s,
                "win": float((sub > 0).mean()),
                "fold_start": str(pd.Timestamp(fold_edges[k])),
                "fold_end": str(pd.Timestamp(fold_edges[k + 1])),
            })
        out["wf_5fold_filtered"] = wf_folds
        wf_pos = sum(1 for f in wf_folds if f.get("mean_net_bp", 0) > 0)
        wf_t1 = sum(1 for f in wf_folds if f.get("t", 0) > 1.0)
        out["wf_pos_count"] = wf_pos
        out["wf_t_gt_1_count"] = wf_t1

        # ============================================================
        # STEP 6: plateau persistence on filtered variant
        # ============================================================
        log.info("[Step 6] Plateau persistence on filtered variant (holds=%s sls=%s tps=%s) ...",
                 HOLDS, SLS, TPS)
        plateau = []
        plateau_pass = 0
        for hold in HOLDS:
            # pool per hold
            if hold == BEST_HOLD:
                cur_pool = pool
            else:
                cur_pool = build_candidate_pool(alt_data, alt_lookup, hold, BEST_SL, BEST_TP,
                                                n_samples=8000, seed=SEED)
            for sl in SLS:
                for tp in TPS:
                    cell = run_cell(alt_data, alt_lookup, triggers_lowvol, hold, sl, tp)
                    if cell["n_trades"] < 50:
                        plateau.append({
                            "hold": hold, "sl": sl, "tp": tp,
                            "n_trades": cell["n_trades"],
                            "note": "n<50",
                        })
                        continue
                    sub = np.array(cell["nets"])
                    try:
                        fe = fee_aware_perm_test(
                            observed_net_returns=sub,
                            candidate_pool_returns=cur_pool,
                            fee_per_trade=FEE_RT,
                            n_perms=400,
                            rng_seed=SEED,
                        )
                        sig_excess = fe.get("signal_t_excess", float("nan"))
                        perm_p_above = fe.get("perm_p_one_sided_above", float("nan"))
                    except Exception:
                        sig_excess, perm_p_above = float("nan"), float("nan")
                    try:
                        bs = bootstrap_ci(sub, n_boot=400, block_size=1, rng_seed=SEED)
                        ci_lo = bs["ci_lower"] * 1e4
                    except Exception:
                        ci_lo = float("nan")
                    row = {
                        "hold": hold, "sl": sl, "tp": tp,
                        "n_trades": cell["n_trades"],
                        "net_mean_bp": cell["net_mean_bp"],
                        "t": cell["t"],
                        "win": cell["win"],
                        "sharpe": cell["sharpe"],
                        "signal_t_excess": sig_excess,
                        "ci_lower_bp": ci_lo,
                        "perm_p_above": perm_p_above,
                    }
                    plateau.append(row)
                    if (sig_excess is not None and sig_excess >= 2.0
                            and ci_lo is not None and ci_lo > 0
                            and perm_p_above is not None and perm_p_above <= 0.05):
                        plateau_pass += 1
        out["plateau_filtered"] = plateau
        out["plateau_pass_count"] = plateau_pass
        out["plateau_total_cells"] = len([c for c in plateau if c.get("n_trades", 0) >= 50])

        # ============================================================
        # STEP 7: comparison table to unfiltered R-3
        # ============================================================
        comparison = {
            "n_trades": {
                "unfiltered": 2626,
                "filtered": int(filt["n_trades"]),
                "delta": int(filt["n_trades"]) - 2626,
            },
            "net_mean_bp": {
                "unfiltered": 15.22,
                "filtered": round(filt["net_mean_bp"], 2),
                "delta_bp": round(filt["net_mean_bp"] - 15.22, 2),
            },
            "t": {
                "unfiltered": 2.94,
                "filtered": round(filt["t"], 2),
                "delta": round(filt["t"] - 2.94, 2),
            },
            "signal_t_excess": {
                "unfiltered": 5.29,
                "filtered": round(filt_perm.get("signal_t_excess", float("nan")), 2)
                            if "signal_t_excess" in filt_perm else None,
            },
            "ci_lower_bp": {
                "unfiltered": 8.04,
                "filtered": round(filt_ci.get("ci_lower_bp", float("nan")), 2)
                            if "ci_lower_bp" in filt_ci else None,
            },
            "fold4_mean_bp": {
                "unfiltered": -42.71,
                "filtered": None,  # filled below
            },
            "q1_2026_mean_bp": {
                "unfiltered": -33.96,
                "filtered": out.get("q1_2026_mean_bp"),
            },
        }
        # fold4 of filtered WF
        if len(wf_folds) >= 4:
            f4 = wf_folds[3]
            comparison["fold4_mean_bp"]["filtered"] = f4.get("mean_net_bp")
        out["comparison_vs_unfiltered"] = comparison

        # ============================================================
        # VERDICT
        # ============================================================
        log.info("Computing R-3.5 verdict ...")
        criteria = {}
        reasons_pass = []
        reasons_fail = []

        sig_ex = filt_perm.get("signal_t_excess")
        ci_lo = filt_ci.get("ci_lower_bp")
        ppa = filt_perm.get("perm_p_above")
        ret_ratio = out["trigger_retention_ratio"]

        criteria["filtered_sig_t_excess_ge_2"] = sig_ex is not None and sig_ex >= 2.0
        criteria["filtered_ci_lower_pos"] = ci_lo is not None and ci_lo > 0
        criteria["filtered_perm_p_le_0p05"] = ppa is not None and ppa <= 0.05
        criteria["q_pos_ge_3"] = q_pos >= 3
        criteria["q1_2026_above_neg10"] = (out.get("q1_2026_mean_bp") is None
                                           or out["q1_2026_mean_bp"] > -10.0)
        criteria["wf_pos_ge_4"] = wf_pos >= 4
        criteria["plateau_ge_10"] = plateau_pass >= 10
        criteria["retention_ge_0p30"] = ret_ratio >= 0.30

        for k, v in criteria.items():
            (reasons_pass if v else reasons_fail).append(f"{k}={v}")

        all_pass = all(criteria.values())
        borderline = all_pass and ret_ratio < 0.30  # never triggered since retention is a criteria
        if all_pass:
            verdict = "CANDIDATE-FOR-R4"
        else:
            # if any of the "alpha core" criteria fail → GRAVEYARD
            alpha_core = ["filtered_sig_t_excess_ge_2", "filtered_ci_lower_pos",
                          "filtered_perm_p_le_0p05"]
            if any(not criteria[k] for k in alpha_core):
                verdict = "GRAVEYARD"
            else:
                verdict = "BORDERLINE"

        out["criteria"] = criteria
        out["reasons_pass"] = reasons_pass
        out["reasons_fail"] = reasons_fail
        out["verdict"] = verdict

        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("R-3.5 verdict=%s written to %s in %.2f min",
                 verdict, OUT_PATH, out["wall_clock_min"])
        log.info("PASS: %s", "; ".join(reasons_pass))
        log.info("FAIL: %s", "; ".join(reasons_fail))
    finally:
        db.close()


if __name__ == "__main__":
    main()
