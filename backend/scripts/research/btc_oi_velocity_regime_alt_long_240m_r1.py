"""R-1 PoC — btc_oi_velocity_regime_alt_long_240m.

Hypothesis (single sentence)
----------------------------
BTC 30-min rolling OI growth z-score (long lookback) >= +2.5 rising edge
+ 60-min cooldown
AND BTC current 30-day realized vol > 90-day-distribution p90 (HIGH vol regime,
  paradigm 69's mechanism filter)
all simultaneously hold
  -> LONG 13 alts, hold 240 min, exit at hold-bar close.

Derivation
----------
Paradigm 69 (`btc_rv_spike_highvol_filter_alt_long_240m`) seeded Q3 with a
strong substantive PASS (+13.45σ excess on 2.4y window). Its mechanism is
"BTC volatility cascade under HIGH-vol regime forces alts to mean-revert /
trend-continue".

This R-1 keeps the HIGH-vol filter mechanism BUT swaps the trigger from
RV (price-derived) to OI velocity (microstructure-derived). If alpha
survives the trigger swap, it is a genuinely orthogonal paradigm. If alpha
collapses, paradigm 69's price-based RV trigger is the unique source.

Per Q3 §6.4 fee-floor pre-screen: paradigm 69 reference UP×LONG +112.9 bp
>> 16 bp floor; OI-velocity trigger expected within same order of magnitude
under identical mechanism filter + 240m hold, so pre-screen passes.

H1 — main directional test: OI z>=+2.5 + HIGH-vol filter + LONG 240m
H2 — fee-aware perm test + bootstrap CI (mandatory _perm_utils, three-gate)
H3 — per-symbol consistency
H4 — OI z threshold sweep {+2.0, +2.5, +3.0} (single fail-fast surface)
H5 — sign-conditional split: BTC 30m return sign at OI trigger
     (UP-OI×UP-BTC vs UP-OI×DOWN-BTC)
     Per checklist 8: do NOT auto-derive mirror SHORT — diagnostic only.

Output
------
backend/runs/research_track/btc_oi_velocity_regime_alt_long_240m/r1__metrics.json

Mint host: 183.99.228.81 (per checklist 6).
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

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("oi_velocity_r1")

PARADIGM = "btc_oi_velocity_regime_alt_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

MICRO_DIR = ROOT / "runs" / "microstructure"
BTC_MICRO_PATH = MICRO_DIR / f"{BTC}_full_metrics.joblib"

# OI velocity config — 5m granularity native, so 30m window = 6 bars
OI_BARS_5M_PER_30M = 6
# z-score lookback: 30 days at 5m granularity (paradigm 69 used same tenor)
OI_Z_LOOKBACK_BARS = 30 * 24 * (60 // 5)  # = 8640 5m bars
COOLDOWN_MIN = 60

# Z thresholds H4 sweep (default = 2.5)
Z_THRESH_DEFAULT = 2.5
Z_THRESH_GRID = [2.0, 2.5, 3.0]

FEE_RT = 8e-4

# Hold/SL/TP (matches paradigm 69 R-1 spec)
DEFAULT_HOLD = 240
DEFAULT_SL = None
DEFAULT_TP = None

# HIGH-vol filter — paradigm 69 used p75 default; spec calls for p90
VOL_LOOKBACK_BARS = 30 * 24 * 60          # 30d in 1m bars
VOL_DIST_BARS = 90 * 24 * 60               # 90d distribution lookback
VOL_MIN_PERIODS = 90 * 24 * 60
VOL_CUTOFF = 0.90                          # spec: p90

N_PERMS = 1000
N_BOOT = 2000
N_POOL_SAMPLES = 20000
SEED = 42


# ---------------- data ----------------


def load_btc_micro() -> pd.DataFrame:
    if not BTC_MICRO_PATH.exists():
        raise FileNotFoundError(f"BTC microstructure joblib not found at {BTC_MICRO_PATH}")
    df = joblib.load(BTC_MICRO_PATH)
    if "open_interest" not in df.columns:
        raise RuntimeError(f"BTC microstructure missing 'open_interest' column. cols={list(df.columns)}")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def compute_oi_velocity_signal(micro: pd.DataFrame) -> pd.DataFrame:
    """30-min rolling OI growth (log-diff) z-score against 30-day distribution."""
    oi = micro["open_interest"].astype(float)
    # log-diff over 6 5m bars = 30 min OI growth
    log_oi = np.log(oi.replace(0, np.nan))
    oi_growth_30m = log_oi.diff(OI_BARS_5M_PER_30M)
    mu = oi_growth_30m.rolling(OI_Z_LOOKBACK_BARS, min_periods=OI_Z_LOOKBACK_BARS).mean()
    sd = oi_growth_30m.rolling(OI_Z_LOOKBACK_BARS, min_periods=OI_Z_LOOKBACK_BARS).std()
    z = (oi_growth_30m - mu) / sd
    df = pd.DataFrame({"oi_growth_30m": oi_growth_30m, "oi_z": z}).dropna()
    return df


def compute_btc_ret_30m_aligned(btc_ohlcv: pd.DataFrame, anchor_index: pd.Index) -> pd.Series:
    """BTC 30-min return at each 5m anchor timestamp (close[t]/close[t-30]-1)."""
    close = btc_ohlcv["close"]
    # 30m return from 1m close
    ret30 = close / close.shift(30) - 1.0
    # reindex to anchor (5m grid) using last-known minute
    aligned = ret30.reindex(anchor_index, method="ffill")
    return aligned


def compute_btc_vol_regime(btc_ohlcv: pd.DataFrame) -> pd.DataFrame:
    """30d realized vol (1m log-diff std × sqrt(60*24)) vs trailing 90d p90 quantile."""
    close = btc_ohlcv["close"]
    lr = np.log(close).diff()
    rv_30d = lr.rolling(VOL_LOOKBACK_BARS, min_periods=VOL_LOOKBACK_BARS).std() * np.sqrt(60 * 24)
    p90 = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(VOL_CUTOFF)
    return pd.DataFrame({"rv_30d": rv_30d, "p90": p90})


def extract_oi_triggers(sig: pd.DataFrame, z_thresh: float) -> pd.DataFrame:
    """Rising-edge crossings on oi_z, with 60-min cooldown."""
    z_prev = sig["oi_z"].shift(1)
    fire = (sig["oi_z"] > z_thresh) & (z_prev <= z_thresh)
    triggers = sig[fire].copy()
    if len(triggers) == 0:
        return triggers
    keep = [True]
    last_t = triggers.index[0]
    for ts in triggers.index[1:]:
        delta_min = (ts - last_t).total_seconds() / 60.0
        if delta_min < COOLDOWN_MIN:
            keep.append(False)
        else:
            keep.append(True)
            last_t = ts
    return triggers[keep]


def filter_triggers_by_highvol(triggers: pd.DataFrame, vol_df: pd.DataFrame) -> pd.DataFrame:
    """Keep triggers where BTC 30d RV > 90d p90 quantile at trigger time."""
    if len(triggers) == 0:
        return triggers
    # vol_df is 1m index; reindex to triggers via ffill (last-known)
    vol_at_trig = vol_df.reindex(triggers.index, method="ffill")
    keep = (vol_at_trig["rv_30d"] > vol_at_trig["p90"]).fillna(False)
    return triggers[keep.values]


# ---------------- trade simulation ----------------


def simulate_trade(high_arr, low_arr, close_arr, ts_to_pos, trig_ts, hold_min, sl, tp):
    """LONG: enter next-minute close after trigger 5m bar, exit at hold_min later."""
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
        if sl_price is not None and not np.isnan(lo) and lo <= sl_price:
            exit_price = sl_price
            exit_reason = "sl"
            break
        if tp_price is not None and not np.isnan(hi) and hi >= tp_price:
            exit_price = tp_price
            exit_reason = "tp"
            break
    gross = exit_price / entry_p - 1.0
    return float(gross), exit_reason


def run_cell(alt_data, alt_lookup, triggers, hold, sl, tp):
    """Run trigger panel (each trigger × each alt) into per-trade net returns."""
    nets, sym_list, ts_list = [], [], []
    trig_idx = list(triggers.index)
    for sym, dd in alt_data.items():
        ha, la, ca = dd["high"], dd["low"], dd["close"]
        ts_pos = alt_lookup[sym]
        for trig_ts in trig_idx:
            gross, _ = simulate_trade(ha, la, ca, ts_pos, trig_ts, hold, sl, tp)
            if np.isnan(gross):
                continue
            net = gross - FEE_RT
            nets.append(net)
            sym_list.append(sym)
            ts_list.append(trig_ts)
    nets_arr = np.array(nets, dtype=float)
    if len(nets_arr) < 2:
        return {
            "n_trades": 0, "net_mean_bp": float("nan"),
            "t": float("nan"), "win": float("nan"), "sharpe": float("nan"),
            "nets": [], "sym": [], "ts": [],
        }
    n = len(nets_arr)
    mn = float(nets_arr.mean())
    sd = float(nets_arr.std(ddof=1))
    t_stat = mn / sd * np.sqrt(n) if sd > 0 else 0.0
    return {
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
        ha, la, ca = alt_data[sym]["high"], alt_data[sym]["low"], alt_data[sym]["close"]
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


# ---------------- main ----------------


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "hypothesis": (
            "BTC OI velocity z(30d 5m)>=+2.5 rising edge + 60m cooldown AND "
            "BTC 30d RV > 90d p90 -> LONG 13 alts hold 240m"
        ),
        "config": {
            "btc_oi_source": str(BTC_MICRO_PATH.relative_to(ROOT)),
            "oi_bars_5m_per_30m_window": OI_BARS_5M_PER_30M,
            "oi_z_lookback_bars_5m": OI_Z_LOOKBACK_BARS,
            "z_thresh_default": Z_THRESH_DEFAULT,
            "z_thresh_grid": Z_THRESH_GRID,
            "cooldown_min": COOLDOWN_MIN,
            "fee_round_trip": FEE_RT,
            "default_hold": DEFAULT_HOLD,
            "vol_lookback_bars": VOL_LOOKBACK_BARS,
            "vol_dist_bars": VOL_DIST_BARS,
            "vol_min_periods": VOL_MIN_PERIODS,
            "vol_cutoff_quantile": VOL_CUTOFF,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
            "alts": ALTS,
            "data_source_alts": "ohlcv_cache joblib (1m)",
            "expected_btc_bars_1m": 1241280,
        },
        "derived_from": {
            "parent_paradigm": "btc_rv_spike_highvol_filter_alt_long_240m (paradigm 69)",
            "trigger_swap": "RV(30m z 30d) -> OI growth(30m z 30d) — orthogonal trigger, same mechanism filter",
        },
    }

    # Step 0 — load BTC OHLCV (must be 1,241,280 rows per checklist 6)
    log.info("Loading BTC OHLCV 1m from joblib cache ...")
    btc_ohlcv = load_ohlcv_1m_cached(BTC)
    log.info("BTC OHLCV bars=%d range=%s..%s",
             len(btc_ohlcv), btc_ohlcv.index.min(), btc_ohlcv.index.max())
    out["data_window"] = {
        "btc_ohlcv_first": str(btc_ohlcv.index.min()),
        "btc_ohlcv_last": str(btc_ohlcv.index.max()),
        "btc_ohlcv_bars": int(len(btc_ohlcv)),
    }
    if len(btc_ohlcv) != 1_241_280:
        log.warning("BTC OHLCV bar count %d != expected 1,241,280", len(btc_ohlcv))
        out["data_window"]["bar_count_mismatch"] = True
        out["verdict"] = "FAIL"
        out["verdict_reasons_fail"] = [f"btc OHLCV bars {len(btc_ohlcv)} != 1,241,280"]
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        return

    # Step 1 — load BTC microstructure (5m OI)
    log.info("Loading BTC microstructure joblib ...")
    micro = load_btc_micro()
    log.info("BTC micro bars=%d range=%s..%s columns=%s",
             len(micro), micro.index.min(), micro.index.max(), list(micro.columns))
    out["data_window"]["btc_oi_first"] = str(micro.index.min())
    out["data_window"]["btc_oi_last"] = str(micro.index.max())
    out["data_window"]["btc_oi_bars_5m"] = int(len(micro))

    # Step 2 — compute OI velocity signal
    log.info("Computing 30m OI growth z-score (lookback=%d 5m bars / %d days) ...",
             OI_Z_LOOKBACK_BARS, OI_Z_LOOKBACK_BARS // (24 * 12))
    sig = compute_oi_velocity_signal(micro)
    log.info("Signal valid bars=%d", len(sig))
    out["n_signal_bars"] = int(len(sig))

    # Step 3 — compute BTC vol regime (1m basis)
    log.info("Computing BTC 30d RV vs 90d p90 ...")
    vol_df = compute_btc_vol_regime(btc_ohlcv)
    valid_vol = vol_df.dropna()
    log.info("Vol regime valid bars=%d range=%s..%s",
             len(valid_vol), valid_vol.index.min(), valid_vol.index.max())

    # Step 4 — load all alts (joblib cache)
    log.info("Loading %d alts from joblib cache ...", len(ALTS))
    alt_data = {}
    alt_lookup = {}
    for sym in ALTS:
        df = load_ohlcv_1m_cached(sym)
        if df is None or df.empty:
            log.warning("alt %s empty", sym)
            continue
        alt_data[sym] = {
            "high": df["high"].values,
            "low": df["low"].values,
            "close": df["close"].values,
        }
        alt_lookup[sym] = {ts: i for i, ts in enumerate(df.index)}
        log.info("  %s: %d bars %s..%s", sym, len(df), df.index.min(), df.index.max())
    out["alts_loaded"] = len(alt_data)

    # Step 5 — build candidate pool ONCE (hold=240, no SL/TP)
    log.info("Building candidate pool (hold=%d, n=%d) ...", DEFAULT_HOLD, N_POOL_SAMPLES)
    pool = build_candidate_pool(alt_data, alt_lookup, DEFAULT_HOLD, DEFAULT_SL, DEFAULT_TP,
                                n_samples=N_POOL_SAMPLES, seed=SEED)
    log.info("pool size=%d", len(pool))
    out["candidate_pool_size"] = int(len(pool))

    # ============================================================
    # H4 — z-threshold sweep (do BEFORE H1/H2/H3 so we can pick the
    # default cell deterministically from data)
    # ============================================================
    out["h4_z_threshold_grid"] = []
    cells_by_z = {}
    triggers_by_z = {}
    triggers_filt_by_z = {}
    btc_ret_at_trig_by_z = {}
    for z_thr in Z_THRESH_GRID:
        log.info("[H4] z_thresh=%.2f ...", z_thr)
        triggers_raw = extract_oi_triggers(sig, z_thr)
        triggers_filt = filter_triggers_by_highvol(triggers_raw, vol_df)
        # also compute BTC 30m return at trigger anchors for H5 sign-split
        btc_ret = compute_btc_ret_30m_aligned(btc_ohlcv, triggers_filt.index)
        log.info("  raw trig=%d highvol_filt=%d (retention=%.1f%%)",
                 len(triggers_raw), len(triggers_filt),
                 100.0 * len(triggers_filt) / max(len(triggers_raw), 1))
        triggers_by_z[z_thr] = triggers_raw
        triggers_filt_by_z[z_thr] = triggers_filt
        btc_ret_at_trig_by_z[z_thr] = btc_ret

        if len(triggers_filt) < 10:
            row = {
                "z_thresh": z_thr,
                "n_triggers_raw": int(len(triggers_raw)),
                "n_triggers_highvol": int(len(triggers_filt)),
                "note": "insufficient_highvol_triggers",
            }
            out["h4_z_threshold_grid"].append(row)
            cells_by_z[z_thr] = None
            continue

        cell = run_cell(alt_data, alt_lookup, triggers_filt, DEFAULT_HOLD, DEFAULT_SL, DEFAULT_TP)
        cells_by_z[z_thr] = cell
        if cell["n_trades"] < 30:
            row = {
                "z_thresh": z_thr,
                "n_triggers_raw": int(len(triggers_raw)),
                "n_triggers_highvol": int(len(triggers_filt)),
                "n_trades": cell["n_trades"],
                "note": "insufficient_trades",
            }
            out["h4_z_threshold_grid"].append(row)
            continue

        nets_z = np.array(cell["nets"])
        # fee-aware perm + bootstrap CI per z bucket (smaller n_perms ok at sweep)
        try:
            fe_z = fee_aware_perm_test(
                observed_net_returns=nets_z,
                candidate_pool_returns=pool,
                fee_per_trade=FEE_RT,
                n_perms=400,
                rng_seed=SEED,
            )
            sig_t_ex = fe_z.get("signal_t_excess")
            null_mean_t = fe_z.get("null_mean_t")
            perm_p_two = fe_z.get("perm_p_two_sided")
            perm_p_above = fe_z.get("perm_p_one_sided_above")
        except Exception as e:
            log.exception("fee_aware_perm failed for z=%.2f: %s", z_thr, e)
            sig_t_ex = null_mean_t = perm_p_two = perm_p_above = None
        try:
            bs_z = bootstrap_ci(nets_z, n_boot=600, block_size=1, rng_seed=SEED)
            ci_lo_bp = bs_z["ci_lower"] * 1e4
            ci_hi_bp = bs_z["ci_upper"] * 1e4
            prob_pos = bs_z["prob_positive"]
        except Exception as e:
            log.exception("bootstrap_ci failed for z=%.2f: %s", z_thr, e)
            ci_lo_bp = ci_hi_bp = prob_pos = None

        row = {
            "z_thresh": z_thr,
            "n_triggers_raw": int(len(triggers_raw)),
            "n_triggers_highvol": int(len(triggers_filt)),
            "n_trades": cell["n_trades"],
            "net_mean_bp": cell["net_mean_bp"],
            "t": cell["t"],
            "win": cell["win"],
            "sharpe": cell["sharpe"],
            "signal_t_excess": sig_t_ex,
            "null_mean_t": null_mean_t,
            "perm_p_two_sided": perm_p_two,
            "perm_p_one_sided_above": perm_p_above,
            "bootstrap_ci_lower_bp": ci_lo_bp,
            "bootstrap_ci_upper_bp": ci_hi_bp,
            "bootstrap_prob_positive": prob_pos,
            # three-gate per z bucket
            "three_gate_pass": (
                sig_t_ex is not None and ci_lo_bp is not None and perm_p_two is not None
                and sig_t_ex >= 2.0 and ci_lo_bp > 0 and perm_p_two <= 0.10
            ),
        }
        out["h4_z_threshold_grid"].append(row)
        log.info("  z=%.2f: n=%d mean=%+.2f bp t=%+.2f sig_t_ex=%s ci_lo=%s perm_p2=%s gate=%s",
                 z_thr, cell["n_trades"], cell["net_mean_bp"], cell["t"],
                 f"{sig_t_ex:+.2f}" if sig_t_ex is not None else "NA",
                 f"{ci_lo_bp:+.2f}" if ci_lo_bp is not None else "NA",
                 f"{perm_p_two:.4f}" if perm_p_two is not None else "NA",
                 row["three_gate_pass"])

    # ============================================================
    # H1 + H2 + H3 — main cell at z_thresh_default = 2.5
    # ============================================================
    main_cell = cells_by_z.get(Z_THRESH_DEFAULT)
    main_triggers = triggers_filt_by_z.get(Z_THRESH_DEFAULT)
    main_btc_ret = btc_ret_at_trig_by_z.get(Z_THRESH_DEFAULT)

    if main_cell is None or main_cell["n_trades"] < 30:
        log.warning("Main cell at z=%.2f insufficient (n_trig=%d) — verdict relies on H4 sweep only",
                    Z_THRESH_DEFAULT,
                    len(main_triggers) if main_triggers is not None else 0)
        out["h1_main_cell"] = {"note": "insufficient_at_default_z"}
        out["h2"] = {}
        out["h3_per_symbol"] = []
        out["h3_alts_pos_and_t_ex_gt_1"] = 0
        out["h5_sign_split"] = {}
    else:
        nets = np.array(main_cell["nets"])
        per_trade_ts = pd.to_datetime(main_cell["ts"])
        per_trade_sym = np.array(main_cell["sym"])
        out["h1_main_cell"] = {
            "z_thresh": Z_THRESH_DEFAULT,
            "n_triggers_raw": int(len(triggers_by_z[Z_THRESH_DEFAULT])),
            "n_triggers_highvol": int(len(main_triggers)),
            "n_trades": main_cell["n_trades"],
            "net_mean_bp": main_cell["net_mean_bp"],
            "t": main_cell["t"],
            "win": main_cell["win"],
            "sharpe": main_cell["sharpe"],
        }
        log.info("[H1] z=%.2f n=%d mean=%+.2f bp t=%+.2f",
                 Z_THRESH_DEFAULT, main_cell["n_trades"], main_cell["net_mean_bp"], main_cell["t"])

        # H2 — fee-aware perm + bootstrap CI on main cell (full N_PERMS / N_BOOT)
        log.info("[H2] fee-aware perm test (n_perms=%d) + bootstrap CI (n_boot=%d) ...",
                 N_PERMS, N_BOOT)
        fe = fee_aware_perm_test(
            observed_net_returns=nets,
            candidate_pool_returns=pool,
            fee_per_trade=FEE_RT,
            n_perms=N_PERMS,
            rng_seed=SEED,
        )
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
        log.info("[H2] obs_t=%+.2f null_mean_t=%+.2f sig_t_ex=%+.2f "
                 "perm_p_two=%.4f ci_lo=%+.2fbp ci_hi=%+.2fbp prob_pos=%.3f",
                 h2["obs_t"], h2["null_mean_t"], h2["signal_t_excess"],
                 h2["perm_p_two_sided"], h2["bootstrap_ci_lower_bp"],
                 h2["bootstrap_ci_upper_bp"], h2["bootstrap_prob_positive"])

        # H3 — per-symbol breakdown
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
        log.info("[H3] %d / %d alts net>0 AND signal_t_excess>1", n_alts_pos, len(ALTS))

        # H5 — sign-conditional split (BTC 30m return sign at trigger)
        log.info("[H5] sign-conditional split ...")
        # build per-trade BTC sign array aligned with per_trade_ts
        btc_ret_series = main_btc_ret  # series indexed by trigger timestamp
        btc_ret_lookup = btc_ret_series.to_dict()
        btc_signs = np.array([
            np.sign(btc_ret_lookup.get(ts, np.nan)) if not pd.isna(btc_ret_lookup.get(ts, np.nan)) else np.nan
            for ts in per_trade_ts
        ])
        up_mask = btc_signs > 0
        down_mask = btc_signs < 0
        up_nets = nets[up_mask]
        down_nets = nets[down_mask]
        h5 = {
            "btc_up_at_trigger": {
                "n_trades": int(len(up_nets)),
                **(stats_block(up_nets) if len(up_nets) >= 2 else {"note": "insufficient"}),
            },
            "btc_down_at_trigger": {
                "n_trades": int(len(down_nets)),
                **(stats_block(down_nets) if len(down_nets) >= 2 else {"note": "insufficient"}),
            },
            "n_unknown_sign": int(np.isnan(btc_signs).sum()),
            "_note": "diagnostic only — checklist 8 forbids auto-deriving mirror SHORT",
        }
        out["h5_sign_split"] = h5
        if len(up_nets) >= 2 and len(down_nets) >= 2:
            log.info("[H5] up: n=%d mean=%+.2f bp t=%+.2f | down: n=%d mean=%+.2f bp t=%+.2f",
                     len(up_nets), h5["btc_up_at_trigger"]["mean_bp"], h5["btc_up_at_trigger"]["t"],
                     len(down_nets), h5["btc_down_at_trigger"]["mean_bp"], h5["btc_down_at_trigger"]["t"])

    # ============================================================
    # VERDICT — three-gate strict on default z=2.5 main cell
    # ============================================================
    log.info("Computing R-1 verdict ...")
    verdict_basis = {}
    h2 = out.get("h2", {})
    sig_ex = h2.get("signal_t_excess")
    ci_lo = h2.get("bootstrap_ci_lower_bp")
    perm_p_two = h2.get("perm_p_two_sided")

    gate_excess = sig_ex is not None and sig_ex >= 2.0
    gate_ci = ci_lo is not None and ci_lo > 0
    gate_perm = perm_p_two is not None and perm_p_two <= 0.10
    three_gate_pass_main = gate_excess and gate_ci and gate_perm

    verdict_basis["gate_signal_t_excess_ge_2"] = gate_excess
    verdict_basis["gate_ci_lower_pos"] = gate_ci
    verdict_basis["gate_perm_p_two_le_0p10"] = gate_perm
    verdict_basis["three_gate_pass"] = three_gate_pass_main

    # Any z bucket also passing gives an alternative "PASS at different z"
    any_z_passing = [r for r in out.get("h4_z_threshold_grid", [])
                     if r.get("three_gate_pass")]
    verdict_basis["any_z_three_gate_pass"] = bool(any_z_passing)
    verdict_basis["passing_z_thresholds"] = [r["z_thresh"] for r in any_z_passing]

    if "h1_main_cell" in out and out["h1_main_cell"].get("net_mean_bp", 0) is not None:
        direction_ok = out["h1_main_cell"].get("net_mean_bp", -1) > 0
    else:
        direction_ok = False
    verdict_basis["direction_ok"] = direction_ok

    if not direction_ok and not any_z_passing:
        verdict = "GRAVEYARD"
        recommendation = "graveyard_now"
    elif three_gate_pass_main:
        verdict = "PASS"
        recommendation = "r2_candidate_await_user_approval"
    elif any_z_passing:
        verdict = "PARTIAL_PASS"
        recommendation = "sub_paradigm_split_candidate_or_z_redefinition"
    elif sig_ex is not None and 1.0 <= sig_ex < 2.0 and direction_ok:
        verdict = "BORDERLINE"
        recommendation = "borderline_review_user"
    else:
        verdict = "GRAVEYARD"
        recommendation = "graveyard_now"

    out["verdict_basis"] = verdict_basis
    out["verdict"] = verdict
    out["recommendation"] = recommendation
    out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-1 verdict=%s recommendation=%s written to %s in %.2f min",
             verdict, recommendation, OUT_PATH, out["wall_clock_min"])


if __name__ == "__main__":
    main()
