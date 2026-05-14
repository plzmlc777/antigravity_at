"""R-1 PoC — btc_rv_spike_highvol_filter_alt_long_240m.

Hypothesis (single sentence)
----------------------------
BTC 30-min RV z-score(30d) >= +2.5 rising edge + 60-min cooldown
AND BTC 30-min return > 0 at trigger
AND BTC current 30d realized vol > 90d-distribution p75 (HIGH vol regime)
all simultaneously hold
  -> LONG 13 alts, hold 240 min, exit at hold-bar close.

Derivation
----------
68th paradigm (btc_rv_spike_up_conditional_alt_long_240m) R-3.5 stratification
revealed the HIGH vol bucket (90d lookback p75+) had n=689, mean=+59.99bp,
t=+4.30, signal_t_excess=+5.63 — far stronger than the aggregate's +15.22 bp.

This R-1 isolates the HIGH-vol bucket as a standalone paradigm and verifies
the three-gate elite cutoff (signal_t_excess >= 2.5 AND ci_lower > 0 AND
perm_p_one_sided_above <= 0.05).

H1 — main directional test on HIGH-vol filtered triggers (hold=240m, no SL/TP)
H2 — fee-aware perm test + bootstrap CI (mandatory, via _perm_utils)
H3 — per-symbol consistency (>= 10/13 alts net positive AND signal_t_excess > 1)
H4 — hold sensitivity grid {180, 210, 240, 270, 300}
H5 — vol cutoff sensitivity grid {p60, p70, p75, p80, p90}
H6 — quarterly fold (5 quarters 2025Q2..2026Q2), >= 3/5 positive
H7 — comparison to unfiltered baseline (apples-to-apples: hold=240, no SL/TP).
     filter must add >= 20bp alpha-per-trade.

Output
------
backend/runs/research_track/btc_rv_spike_highvol_filter_alt_long_240m/r1__metrics.json
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
log = logging.getLogger("btc_rv_highvol_r1")

PARADIGM = "btc_rv_spike_highvol_filter_alt_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Identical signal config to 68th paradigm (R-2/R-3)
RV_WINDOW = 30
Z_WINDOW = 30 * 24 * 60
Z_THRESH = 2.5
COOLDOWN = 60
FEE_RT = 8e-4

# R-1 paradigm definition: hold 240 min, no SL, no TP
DEFAULT_HOLD = 240
DEFAULT_SL = None
DEFAULT_TP = None

# H5 vol cutoff grid (default p75 = paradigm definition)
VOL_CUTOFFS = [0.60, 0.70, 0.75, 0.80, 0.90]
DEFAULT_VOL_CUTOFF = 0.75

# H4 hold sensitivity grid
HOLDS = [180, 210, 240, 270, 300]

# Vol regime config (same as 68th R-3.5)
VOL_LOOKBACK_BARS = 30 * 24 * 60
VOL_DIST_BARS = 90 * 24 * 60
VOL_MIN_PERIODS = 90 * 24 * 60

N_PERMS = 1000
N_BOOT = 2000
N_POOL_SAMPLES = 20000
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


def compute_btc_vol_regime(btc: pd.DataFrame) -> pd.DataFrame:
    """30d realized vol vs trailing 90d distribution percentiles.

    Returns dataframe indexed by minute with cols:
        rv_30d, p60, p70, p75, p80, p90
    """
    close = btc["close"]
    lr = np.log(close).diff()
    rv_30d = lr.rolling(VOL_LOOKBACK_BARS, min_periods=VOL_LOOKBACK_BARS).std() * np.sqrt(60 * 24)
    cols = {"rv_30d": rv_30d}
    for c in VOL_CUTOFFS:
        cols[f"p{int(c*100)}"] = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(c)
    return pd.DataFrame(cols)


# ---------- trade simulation ----------


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
    """Run trigger panel (each trigger × each alt) into per-trade net returns."""
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
            "t": float("nan"), "win": float("nan"), "sharpe": float("nan"),
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


def build_candidate_pool(alt_data, alt_lookup, hold, sl, tp, n_samples=N_POOL_SAMPLES, seed=SEED):
    rng = np.random.default_rng(seed)
    pool = []
    sym_keys = list(alt_data.keys())
    n_per_sym = n_samples // max(len(sym_keys), 1)
    for sym in sym_keys:
        ha = alt_data[sym]["high"]
        la = alt_data[sym]["low"]
        ca = alt_data[sym]["close"]
        ts_pos = alt_lookup[sym]
        ts_list = list(ts_pos.keys())
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


# ---------- helpers ----------


def filter_triggers_by_vol_cutoff(triggers: pd.DataFrame, vol_df: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    col = f"p{int(cutoff*100)}"
    if col not in vol_df.columns:
        return triggers.iloc[0:0]
    keep_mask = []
    for ts in triggers.index:
        if ts not in vol_df.index:
            keep_mask.append(False)
            continue
        rv = vol_df.at[ts, "rv_30d"]
        thr = vol_df.at[ts, col]
        if pd.isna(rv) or pd.isna(thr):
            keep_mask.append(False)
        else:
            keep_mask.append(bool(rv > thr))
    return triggers[keep_mask]


def stats_block(nets_arr: np.ndarray) -> dict:
    if len(nets_arr) < 2:
        return {"n": int(len(nets_arr)), "mean_bp": float("nan"), "t": float("nan"), "win": float("nan")}
    m = float(nets_arr.mean())
    s = float(nets_arr.std(ddof=1))
    t_s = m / s * np.sqrt(len(nets_arr)) if s > 0 else 0.0
    return {
        "n": int(len(nets_arr)),
        "mean_bp": m * 1e4,
        "t": t_s,
        "win": float((nets_arr > 0).mean()),
        "sharpe": (m / s) if s > 0 else 0.0,
    }


# ---------- main ----------


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "hypothesis": (
            "BTC 30m RV z(30d)>=+2.5 rising edge AND BTC 30m ret>0 AND BTC 30d RV > p75(90d) "
            "-> LONG 13 alts hold 240m"
        ),
        "config": {
            "rv_window_bars": RV_WINDOW,
            "z_window_bars": Z_WINDOW,
            "z_thresh": Z_THRESH,
            "cooldown_min": COOLDOWN,
            "fee_round_trip": FEE_RT,
            "default_hold": DEFAULT_HOLD,
            "default_sl": DEFAULT_SL,
            "default_tp": DEFAULT_TP,
            "default_vol_cutoff": DEFAULT_VOL_CUTOFF,
            "vol_lookback_bars": VOL_LOOKBACK_BARS,
            "vol_dist_bars": VOL_DIST_BARS,
            "vol_min_periods": VOL_MIN_PERIODS,
            "vol_classification": "30d_rv_vs_90d_pXX",
            "hold_grid": HOLDS,
            "vol_cutoff_grid": VOL_CUTOFFS,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
            "alts": ALTS,
            "data_source": "Mint DB ohlcv 1m",
            "expected_btc_bars": 547200,
        },
        "derived_from": {
            "parent_paradigm": "btc_rv_spike_up_conditional_alt_long_240m",
            "parent_r3_5_high_vol_bucket": {
                "n_trades": 689,
                "mean_net_bp": 59.99,
                "t": 4.30,
                "signal_t_excess": 5.63,
            },
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
        if len(btc) != 547200:
            log.warning("BTC bar count %d != expected 547200", len(btc))
            out["data_window"]["bar_count_mismatch"] = True
            out["verdict"] = "FAIL"
            out["verdict_reasons_fail"] = [f"btc bars {len(btc)} != 547200, wrong DB"]
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return

        log.info("Computing BTC RV signal ...")
        sig = compute_btc_signal(btc)
        log.info("Computing BTC vol regime (30d RV vs 90d p60/p70/p75/p80/p90) ...")
        vol_df = compute_btc_vol_regime(btc)

        log.info("Extracting unfiltered triggers (z=%.2f, up-only, cooldown=%d min) ...", Z_THRESH, COOLDOWN)
        triggers = extract_triggers(sig, z_thresh=Z_THRESH)
        log.info("Unfiltered triggers: %d", len(triggers))
        out["n_triggers_unfiltered"] = int(len(triggers))

        # Filter triggers by paradigm default cutoff (p75) — primary set
        triggers_filt = filter_triggers_by_vol_cutoff(triggers, vol_df, DEFAULT_VOL_CUTOFF)
        log.info("HIGH-vol filtered triggers (p%d cutoff): %d / %d (%.1f%% retained)",
                 int(DEFAULT_VOL_CUTOFF * 100),
                 len(triggers_filt), len(triggers),
                 100.0 * len(triggers_filt) / max(len(triggers), 1))
        out["n_triggers_highvol_p75"] = int(len(triggers_filt))
        out["trigger_retention_ratio_p75"] = (len(triggers_filt) / max(len(triggers), 1))

        if len(triggers_filt) < 10:
            log.warning("HIGH-vol triggers < 10, cannot run statistics")
            out["verdict"] = "GRAVEYARD"
            out["verdict_reasons_fail"] = [f"n_triggers_highvol={len(triggers_filt)} < 10"]
            out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return

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
        out["alts_loaded"] = len(alt_data)

        # ============================================================
        # H1 — main directional test on HIGH-vol filtered triggers
        # ============================================================
        log.info("[H1] Main cell: HIGH-vol filtered + hold=%dm + no SL/TP ...", DEFAULT_HOLD)
        main_cell = run_cell(alt_data, alt_lookup, triggers_filt, DEFAULT_HOLD, DEFAULT_SL, DEFAULT_TP)
        nets = np.array(main_cell["nets"])
        per_trade_ts = pd.to_datetime(main_cell["ts"])
        per_trade_sym = np.array(main_cell["sym"])

        out["h1_main_cell"] = {
            "n_trades": main_cell["n_trades"],
            "net_mean_bp": main_cell["net_mean_bp"],
            "t": main_cell["t"],
            "win": main_cell["win"],
            "sharpe": main_cell["sharpe"],
        }
        log.info("H1: n=%d mean=%+.2f bp t=%+.2f win=%.4f",
                 main_cell["n_trades"], main_cell["net_mean_bp"], main_cell["t"], main_cell["win"])

        if main_cell["n_trades"] < 30:
            log.warning("H1 n<30, halting")
            out["verdict"] = "GRAVEYARD"
            out["verdict_reasons_fail"] = [f"H1 n_trades={main_cell['n_trades']} < 30"]
            out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return

        # ============================================================
        # Build candidate pool (hold=240, no SL/TP) — used by H2 + H5
        # ============================================================
        log.info("Building candidate pool (hold=%d, n=%d) ...", DEFAULT_HOLD, N_POOL_SAMPLES)
        pool = build_candidate_pool(alt_data, alt_lookup, DEFAULT_HOLD, DEFAULT_SL, DEFAULT_TP,
                                    n_samples=N_POOL_SAMPLES, seed=SEED)
        log.info("pool size=%d", len(pool))

        # ============================================================
        # H2 — fee-aware perm + bootstrap CI (MANDATORY)
        # ============================================================
        log.info("[H2] fee-aware perm test (n_perms=%d) ...", N_PERMS)
        fe = fee_aware_perm_test(
            observed_net_returns=nets,
            candidate_pool_returns=pool,
            fee_per_trade=FEE_RT,
            n_perms=N_PERMS,
            rng_seed=SEED,
        )
        log.info("[H2] bootstrap CI (n_boot=%d) ...", N_BOOT)
        bs = bootstrap_ci(nets, n_boot=N_BOOT, block_size=1, rng_seed=SEED)
        h2 = {
            "obs_mean_bp": fe["obs_mean"] * 1e4,
            "obs_t": fe["obs_t"],
            "null_mean_t": fe["null_mean_t"],
            "null_std_t": fe["null_std_t"],
            "signal_t_excess": fe["signal_t_excess"],
            "perm_p_two_sided": fe["perm_p_two_sided"],
            "perm_p_one_sided_above": fe["perm_p_one_sided_above"],
            "perm_p_one_sided_below": fe["perm_p_one_sided_below"],
            "n_observed": fe["n_observed"],
            "n_candidate": fe["n_candidate"],
            "bootstrap_mean_bp": bs["mean"] * 1e4,
            "bootstrap_ci_lower_bp": bs["ci_lower"] * 1e4,
            "bootstrap_ci_upper_bp": bs["ci_upper"] * 1e4,
            "bootstrap_prob_positive": bs["prob_positive"],
        }
        out["h2"] = h2
        log.info("H2: obs_t=%+.2f null_mean_t=%+.2f sig_t_excess=%+.2f perm_p_above=%.4f ci_lower=%+.2f bp",
                 h2["obs_t"], h2["null_mean_t"], h2["signal_t_excess"],
                 h2["perm_p_one_sided_above"], h2["bootstrap_ci_lower_bp"])

        # ============================================================
        # H3 — per-symbol consistency
        # ============================================================
        log.info("[H3] per-symbol breakdown ...")
        per_sym = []
        n_alts_pos = 0
        for sym in ALTS:
            mask = per_trade_sym == sym
            sub = nets[mask]
            if len(sub) < 2:
                per_sym.append({"sym": sym, "n": int(len(sub)), "note": "insufficient"})
                continue
            try:
                fe_s = fee_aware_perm_test(
                    observed_net_returns=sub,
                    candidate_pool_returns=pool,
                    fee_per_trade=FEE_RT,
                    n_perms=300,
                    rng_seed=SEED,
                )
                sig_t_ex = fe_s.get("signal_t_excess")
            except Exception:
                sig_t_ex = None
            stat = stats_block(sub)
            stat["sym"] = sym
            stat["signal_t_excess"] = sig_t_ex
            per_sym.append(stat)
            if stat["mean_bp"] > 0 and (sig_t_ex is not None and sig_t_ex > 1.0):
                n_alts_pos += 1
        out["h3_per_symbol"] = per_sym
        out["h3_alts_pos_and_t_ex_gt_1"] = n_alts_pos
        log.info("H3: %d / %d alts net>0 AND signal_t_excess>1", n_alts_pos, len(ALTS))

        # ============================================================
        # H4 — hold sensitivity grid
        # ============================================================
        log.info("[H4] hold sensitivity grid %s ...", HOLDS)
        h4 = []
        h4_pos = 0
        for hold in HOLDS:
            if hold == DEFAULT_HOLD:
                cell = main_cell
                cur_pool = pool
            else:
                cell = run_cell(alt_data, alt_lookup, triggers_filt, hold, None, None)
                cur_pool = build_candidate_pool(alt_data, alt_lookup, hold, None, None,
                                                n_samples=8000, seed=SEED)
            if cell["n_trades"] < 30:
                h4.append({"hold": hold, "n_trades": cell["n_trades"], "note": "insufficient"})
                continue
            sub = np.array(cell["nets"])
            try:
                fe_h = fee_aware_perm_test(
                    observed_net_returns=sub,
                    candidate_pool_returns=cur_pool,
                    fee_per_trade=FEE_RT,
                    n_perms=400,
                    rng_seed=SEED,
                )
                sig_t_ex = fe_h.get("signal_t_excess")
                perm_p_above = fe_h.get("perm_p_one_sided_above")
            except Exception:
                sig_t_ex, perm_p_above = None, None
            try:
                bs_h = bootstrap_ci(sub, n_boot=400, block_size=1, rng_seed=SEED)
                ci_lo = bs_h["ci_lower"] * 1e4
            except Exception:
                ci_lo = None
            row = {
                "hold": hold,
                "n_trades": cell["n_trades"],
                "net_mean_bp": cell["net_mean_bp"],
                "t": cell["t"],
                "win": cell["win"],
                "signal_t_excess": sig_t_ex,
                "ci_lower_bp": ci_lo,
                "perm_p_above": perm_p_above,
            }
            h4.append(row)
            if cell["net_mean_bp"] > 0:
                h4_pos += 1
            log.info("  hold=%d: n=%d mean=%+.2f bp t=%+.2f sig_t_ex=%s",
                     hold, cell["n_trades"], cell["net_mean_bp"], cell["t"],
                     f"{sig_t_ex:+.2f}" if sig_t_ex is not None else "NA")
        out["h4_hold_grid"] = h4
        out["h4_pos_count"] = h4_pos

        # ============================================================
        # H5 — vol cutoff sensitivity grid
        # ============================================================
        log.info("[H5] vol cutoff sensitivity grid %s ...", VOL_CUTOFFS)
        h5 = []
        for cutoff in VOL_CUTOFFS:
            t_filt = filter_triggers_by_vol_cutoff(triggers, vol_df, cutoff)
            if len(t_filt) < 10:
                h5.append({
                    "cutoff_pct": int(cutoff * 100),
                    "n_triggers": len(t_filt),
                    "note": "insufficient triggers",
                })
                continue
            cell = run_cell(alt_data, alt_lookup, t_filt, DEFAULT_HOLD, None, None)
            if cell["n_trades"] < 30:
                h5.append({
                    "cutoff_pct": int(cutoff * 100),
                    "n_triggers": len(t_filt),
                    "n_trades": cell["n_trades"],
                    "note": "insufficient trades",
                })
                continue
            sub = np.array(cell["nets"])
            try:
                fe_c = fee_aware_perm_test(
                    observed_net_returns=sub,
                    candidate_pool_returns=pool,
                    fee_per_trade=FEE_RT,
                    n_perms=400,
                    rng_seed=SEED,
                )
                sig_t_ex = fe_c.get("signal_t_excess")
            except Exception:
                sig_t_ex = None
            row = {
                "cutoff_pct": int(cutoff * 100),
                "n_triggers": int(len(t_filt)),
                "n_trades": cell["n_trades"],
                "net_mean_bp": cell["net_mean_bp"],
                "t": cell["t"],
                "win": cell["win"],
                "signal_t_excess": sig_t_ex,
            }
            h5.append(row)
            log.info("  cutoff=p%d: n_trig=%d n=%d mean=%+.2f bp t=%+.2f sig_t_ex=%s",
                     int(cutoff * 100), len(t_filt), cell["n_trades"], cell["net_mean_bp"], cell["t"],
                     f"{sig_t_ex:+.2f}" if sig_t_ex is not None else "NA")
        out["h5_vol_cutoff_grid"] = h5

        # Monotonicity check: stricter cutoff (higher percentile) should preserve or strengthen alpha
        means_by_cutoff = [(r["cutoff_pct"], r.get("net_mean_bp"))
                           for r in h5 if "net_mean_bp" in r]
        h5_monotone = False
        if len(means_by_cutoff) >= 3:
            means_by_cutoff.sort(key=lambda x: x[0])
            # all means positive
            all_pos = all(m > 0 for _, m in means_by_cutoff if m is not None)
            # p90 not significantly below p75
            p75 = next((m for c, m in means_by_cutoff if c == 75), None)
            p90 = next((m for c, m in means_by_cutoff if c == 90), None)
            if all_pos and p75 is not None and p90 is not None:
                h5_monotone = p90 >= p75 - 30  # within 30bp tolerance
            elif all_pos:
                h5_monotone = True
        out["h5_monotone"] = h5_monotone

        # ============================================================
        # H6 — quarterly fold (regime stability)
        # ============================================================
        log.info("[H6] quarterly fold ...")
        quarter_edges = [
            ("2025Q2", pd.Timestamp("2025-04-01"), pd.Timestamp("2025-07-01")),
            ("2025Q3", pd.Timestamp("2025-07-01"), pd.Timestamp("2025-10-01")),
            ("2025Q4", pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")),
            ("2026Q1", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")),
            ("2026Q2", pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")),
        ]
        quarterly = []
        for qname, qstart, qend in quarter_edges:
            mask = (per_trade_ts >= qstart) & (per_trade_ts < qend)
            sub = nets[mask.values] if hasattr(mask, "values") else nets[mask]
            if len(sub) < 5:
                quarterly.append({"quarter": qname, "n": int(len(sub)), "note": "insufficient"})
                continue
            quarterly.append({
                "quarter": qname,
                **stats_block(sub),
            })
        out["h6_quarterly_fold"] = quarterly
        h6_pos = sum(1 for q in quarterly if q.get("mean_bp", 0) > 0)
        out["h6_pos_count"] = h6_pos
        log.info("H6: %d / %d quarters net>0", h6_pos, len(quarter_edges))

        # ============================================================
        # H7 — comparison to unfiltered baseline (apples-to-apples)
        # ============================================================
        log.info("[H7] unfiltered baseline (hold=240, no SL/TP) ...")
        unf_cell = run_cell(alt_data, alt_lookup, triggers, DEFAULT_HOLD, None, None)
        unf_stat = {
            "n_trades": unf_cell["n_trades"],
            "net_mean_bp": unf_cell["net_mean_bp"],
            "t": unf_cell["t"],
            "win": unf_cell["win"],
        }
        out["h7_unfiltered_baseline"] = unf_stat
        delta_bp = (main_cell["net_mean_bp"] - unf_cell["net_mean_bp"]) if unf_cell["n_trades"] >= 30 else None
        out["h7_alpha_delta_bp"] = delta_bp
        log.info("H7: unfiltered n=%d mean=%+.2f bp | filtered n=%d mean=%+.2f bp | delta=%+.2f bp",
                 unf_cell["n_trades"], unf_cell["net_mean_bp"],
                 main_cell["n_trades"], main_cell["net_mean_bp"],
                 delta_bp if delta_bp is not None else float("nan"))

        # ============================================================
        # VERDICT — three-gate + H3..H7 supplements
        # ============================================================
        log.info("Computing R-1 verdict ...")
        criteria = {}
        reasons_pass = []
        reasons_fail = []

        sig_ex = h2["signal_t_excess"]
        ci_lo = h2["bootstrap_ci_lower_bp"]
        ppa = h2["perm_p_one_sided_above"]

        criteria["h2_sig_t_excess_ge_2p5"] = sig_ex is not None and sig_ex >= 2.5
        criteria["h2_ci_lower_pos"] = ci_lo is not None and ci_lo > 0
        criteria["h2_perm_p_above_le_0p05"] = ppa is not None and ppa <= 0.05
        criteria["h1_mean_positive"] = main_cell["net_mean_bp"] > 0
        criteria["h3_alts_pos_ge_10"] = n_alts_pos >= 10
        criteria["h4_holds_pos_ge_3"] = h4_pos >= 3  # gravey: <3 means majority hold negatives
        criteria["h5_monotone"] = h5_monotone
        criteria["h6_quarters_pos_ge_3"] = h6_pos >= 3
        criteria["h7_alpha_uplift_ge_20bp"] = delta_bp is not None and delta_bp >= 20.0

        # Three-gate STRICT for elite
        three_gate = (criteria["h2_sig_t_excess_ge_2p5"]
                      and criteria["h2_ci_lower_pos"]
                      and criteria["h2_perm_p_above_le_0p05"])

        alts_pos_ge_11 = n_alts_pos >= 11
        h4_pos_ge_4 = h4_pos >= 4
        h6_pos_ge_4 = h6_pos >= 4

        for k, v in criteria.items():
            (reasons_pass if v else reasons_fail).append(f"{k}={v}")

        # Borderline definition: signal_t_excess in [2.0, 2.5)
        borderline_excess = (sig_ex is not None and 2.0 <= sig_ex < 2.5
                             and criteria["h2_ci_lower_pos"]
                             and criteria["h2_perm_p_above_le_0p05"])

        # Direction sanity
        direction_opposite = main_cell["net_mean_bp"] <= 0

        # Hold sensitivity reject: 3+ of 5 cells negative
        h4_severe_fail = h4_pos <= 2  # 0,1,2 positive of 5

        # H5 monotone reject: spec said "p90 significantly worse than p75"
        # We already capture this in h5_monotone

        if direction_opposite:
            verdict = "GRAVEYARD"
        elif three_gate and criteria["h3_alts_pos_ge_10"] and not h4_severe_fail and criteria["h5_monotone"] and criteria["h6_quarters_pos_ge_3"] and criteria["h7_alpha_uplift_ge_20bp"]:
            if alts_pos_ge_11 and h4_pos_ge_4 and h6_pos_ge_4 and criteria["h5_monotone"]:
                verdict = "CANDIDATE-FOR-R2"
            else:
                verdict = "PASS"
        elif borderline_excess:
            verdict = "BORDERLINE"
        else:
            verdict = "GRAVEYARD"

        out["criteria"] = criteria
        out["three_gate_pass"] = three_gate
        out["reasons_pass"] = reasons_pass
        out["reasons_fail"] = reasons_fail
        out["verdict"] = verdict

        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("R-1 verdict=%s written to %s in %.2f min",
                 verdict, OUT_PATH, out["wall_clock_min"])
        log.info("PASS: %s", "; ".join(reasons_pass))
        log.info("FAIL: %s", "; ".join(reasons_fail))
    finally:
        db.close()


if __name__ == "__main__":
    main()
