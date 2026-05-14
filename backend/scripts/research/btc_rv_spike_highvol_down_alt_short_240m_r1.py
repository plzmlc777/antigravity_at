"""R-1 PoC — btc_rv_spike_highvol_down_alt_short_240m.

Hypothesis (single sentence)
----------------------------
BTC 30m RV z-score(30d) >= +2.5 rising edge + 60m cooldown
AND BTC 30m return < 0 at trigger (DOWN-trigger, mirror of paradigm 69)
AND BTC current 30d RV >= p90 of past 90d (HIGH vol regime)
  -> SHORT 13 alts, hold 240 min, exit at hold-bar close, fee 8bp RT.

Derivation
----------
67th graveyard H5 measured BTC down-trigger × LONG @ 240m:
    mean=-150.1 bp, t=-2.73, win=47.4% (n_down ~212/380d).
The mirror SHORT direction should yield +150 bp / trade gross (precedent).
Paradigm 69 R-3 HIGH-vol filter (p90 cutoff) retained ~17% events.
Expect n_filtered_down ~ 80-100 / 2.4yr -> ~1000-1300 trades.

H1 — main directional test on HIGH-vol filtered DOWN-triggers, SHORT, hold=240m
H2 — fee-aware perm test + bootstrap CI (mandatory, via _perm_utils)
H3 — per-symbol consistency (>= 10/13 alts net positive AND signal_t_excess > 1)
H4 — hold sensitivity grid {180, 210, 240, 270, 300}, pass 4/5 positive
H5 — vol cutoff sensitivity grid {p60, p70, p75, p80, p90}, monotone-ish stricter-better
H6 — comparison to mirror paradigm 69 (UP-trigger + LONG) on SAME data
H7 — baseline: BTC 30m_ret<0 (no RV filter, no vol regime) SHORT 240m

Output
------
backend/runs/research_track/btc_rv_spike_highvol_down_alt_short_240m/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

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
log = logging.getLogger("btc_rv_highvol_down_short_r1")

PARADIGM = "btc_rv_spike_highvol_down_alt_short_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Identical signal config to paradigm 69
RV_WINDOW = 30
Z_WINDOW = 30 * 24 * 60
Z_THRESH = 2.5
COOLDOWN = 60
FEE_RT = 8e-4

DEFAULT_HOLD = 240
# Default vol cutoff = p90 (mirror of paradigm 69's strictest cutoff per spec)
DEFAULT_VOL_CUTOFF = 0.90
VOL_CUTOFFS = [0.60, 0.70, 0.75, 0.80, 0.90]
HOLDS = [180, 210, 240, 270, 300]

VOL_LOOKBACK_BARS = 30 * 24 * 60
VOL_DIST_BARS = 90 * 24 * 60
VOL_MIN_PERIODS = 90 * 24 * 60

N_PERMS = 1000
N_BOOT = 2000
N_POOL_SAMPLES = 20000
SEED = 42

# Trade direction: -1 = SHORT all alts
TRADE_DIRECTION = -1


# ---------- signal ----------


def compute_btc_signal(btc: pd.DataFrame) -> pd.DataFrame:
    lr = np.log(btc["close"]).diff()
    rv = lr.rolling(RV_WINDOW, min_periods=RV_WINDOW).std()
    rv_mu = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    rv_sd = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    rv_z = (rv - rv_mu) / rv_sd
    btc_ret_30m = btc["close"] / btc["close"].shift(RV_WINDOW) - 1
    sig = pd.DataFrame({"rv": rv, "rv_z": rv_z, "btc_ret_30m": btc_ret_30m}).dropna()
    return sig


def extract_triggers_directional(sig: pd.DataFrame, z_thresh: float, direction: str) -> pd.DataFrame:
    """direction = 'up' (btc_ret_30m>0) or 'down' (btc_ret_30m<0)."""
    z_prev = sig["rv_z"].shift(1)
    fire = (sig["rv_z"] > z_thresh) & (z_prev <= z_thresh)
    triggers = sig[fire].copy()
    if direction == "up":
        triggers = triggers[triggers["btc_ret_30m"] > 0]
    elif direction == "down":
        triggers = triggers[triggers["btc_ret_30m"] < 0]
    else:
        raise ValueError(f"bad direction: {direction}")
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
    close = btc["close"]
    lr = np.log(close).diff()
    rv_30d = lr.rolling(VOL_LOOKBACK_BARS, min_periods=VOL_LOOKBACK_BARS).std() * np.sqrt(60 * 24)
    cols = {"rv_30d": rv_30d}
    for c in VOL_CUTOFFS:
        cols[f"p{int(c * 100)}"] = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(c)
    return pd.DataFrame(cols)


def filter_triggers_by_vol_cutoff(triggers: pd.DataFrame, vol_df: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    col = f"p{int(cutoff * 100)}"
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
            keep_mask.append(bool(rv >= thr))
    return triggers[keep_mask]


# ---------- trade simulation ----------


def simulate_trade(high_arr, low_arr, close_arr, ts_to_pos, trig_ts, hold_min):
    """No SL/TP at R-1. Returns gross return signed by TRADE_DIRECTION applied
    EXTERNALLY (this returns the raw price-change gross from entry to exit)."""
    entry_ts = trig_ts + pd.Timedelta(minutes=1)
    final_exit_ts = trig_ts + pd.Timedelta(minutes=1 + hold_min)
    ei = ts_to_pos.get(entry_ts)
    xi = ts_to_pos.get(final_exit_ts)
    if ei is None or xi is None:
        return float("nan")
    entry_p = close_arr[ei]
    if not (entry_p > 0) or np.isnan(entry_p):
        return float("nan")
    bar_closes = close_arr[ei + 1 : xi + 1]
    if len(bar_closes) == 0:
        return float("nan")
    exit_price = bar_closes[-1]
    gross = exit_price / entry_p - 1.0
    return float(gross)


def run_cell(alt_data, alt_lookup, triggers, hold, direction):
    """Run trigger panel (each trigger × each alt). direction ∈ {-1, +1}."""
    nets, sym_list, ts_list = [], [], []
    trig_idx = list(triggers.index)
    for sym, df_dict in alt_data.items():
        ha = df_dict["high"]
        la = df_dict["low"]
        ca = df_dict["close"]
        ts_pos = alt_lookup[sym]
        for trig_ts in trig_idx:
            gross = simulate_trade(ha, la, ca, ts_pos, trig_ts, hold)
            if np.isnan(gross):
                continue
            # Signed return per direction, then subtract fee
            net = direction * gross - FEE_RT
            nets.append(net)
            sym_list.append(sym)
            ts_list.append(trig_ts)
    nets_arr = np.array(nets, dtype=float)
    if len(nets_arr) < 2:
        return {
            "hold": hold, "direction": direction,
            "n_trades": 0, "net_mean_bp": float("nan"),
            "t": float("nan"), "win": float("nan"), "sharpe": float("nan"),
            "nets": [], "sym": [], "ts": [],
        }
    n = len(nets_arr)
    mn = float(nets_arr.mean())
    sd = float(nets_arr.std(ddof=1))
    t_stat = mn / sd * np.sqrt(n) if sd > 0 else 0.0
    return {
        "hold": hold, "direction": direction,
        "n_trades": n,
        "net_mean_bp": mn * 1e4,
        "t": t_stat,
        "win": float((nets_arr > 0).mean()),
        "sharpe": mn / sd if sd > 0 else 0.0,
        "nets": nets_arr.tolist(),
        "sym": sym_list,
        "ts": [str(x) for x in ts_list],
    }


def build_candidate_pool(alt_data, alt_lookup, hold, direction, n_samples=N_POOL_SAMPLES, seed=SEED):
    """Build a candidate pool of GROSS returns for the perm test.
    fee_aware_perm_test expects gross (it subtracts the same fee internally),
    and signs are determined by direction (sample SHORT side: pool entries
    are -gross because SHORT realizes -gross of underlying)."""
    rng = np.random.default_rng(seed)
    pool = []
    sym_keys = list(alt_data.keys())
    n_per_sym = n_samples // max(len(sym_keys), 1)
    for sym in sym_keys:
        ca = alt_data[sym]["close"]
        ts_pos = alt_lookup[sym]
        ts_list = list(ts_pos.keys())
        max_i = len(ts_list) - hold - 5
        if max_i <= 0:
            continue
        idxs = rng.choice(max_i, size=min(n_per_sym, max_i), replace=False)
        for idx in idxs:
            trig_ts = ts_list[idx]
            gross = simulate_trade(
                alt_data[sym]["high"], alt_data[sym]["low"], ca, ts_pos, trig_ts, hold
            )
            if not np.isnan(gross):
                pool.append(direction * gross)  # signed gross matching trade direction
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


# ---------- main ----------


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "hypothesis": (
            "BTC 30m RV z(30d)>=+2.5 rising edge AND BTC 30m ret<0 AND BTC 30d RV >= p90(90d) "
            "-> SHORT 13 alts hold 240m"
        ),
        "config": {
            "rv_window_bars": RV_WINDOW,
            "z_window_bars": Z_WINDOW,
            "z_thresh": Z_THRESH,
            "cooldown_min": COOLDOWN,
            "fee_round_trip": FEE_RT,
            "default_hold": DEFAULT_HOLD,
            "default_vol_cutoff": DEFAULT_VOL_CUTOFF,
            "trade_direction": TRADE_DIRECTION,
            "vol_lookback_bars": VOL_LOOKBACK_BARS,
            "vol_dist_bars": VOL_DIST_BARS,
            "vol_min_periods": VOL_MIN_PERIODS,
            "hold_grid": HOLDS,
            "vol_cutoff_grid": VOL_CUTOFFS,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
            "alts": ALTS,
            "data_source": "joblib cache (load_ohlcv_1m_cached)",
            "expected_btc_bars": 1241280,
        },
        "derived_from": {
            "mirror_paradigm": "btc_rv_spike_highvol_filter_alt_long_240m (#69 R-5 seeded)",
            "precedent_67_h5_down_trig_LONG_240m": {
                "n_estimate": "~212 down-triggers over 380d",
                "mean_bp": -150.1,
                "t": -2.73,
                "win": 0.474,
                "note": "mirror SHORT direction should yield +150 bp gross (precedent)",
            },
        },
    }

    # ============================================================
    # Load BTC + 13 alts from joblib cache
    # ============================================================
    log.info("Loading BTC ohlcv 1m from joblib cache ...")
    btc = load_ohlcv_1m_cached(BTC)
    if btc.empty:
        raise SystemExit("BTC cache empty")
    log.info("BTC bars=%d range=%s..%s", len(btc), btc.index[0], btc.index[-1])
    out["data_window"] = {
        "btc_first": str(btc.index[0]),
        "btc_last": str(btc.index[-1]),
        "btc_bars": int(len(btc)),
    }
    if len(btc) != 1241280:
        log.warning("BTC bar count %d != expected 1241280", len(btc))
        out["data_window"]["bar_count_mismatch"] = True
        out["verdict"] = "FAIL"
        out["verdict_reasons_fail"] = [f"btc bars {len(btc)} != 1241280, wrong cache"]
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        return

    log.info("Computing BTC RV signal ...")
    sig = compute_btc_signal(btc)
    log.info("Computing BTC vol regime (30d RV vs 90d p60/p70/p75/p80/p90) ...")
    vol_df = compute_btc_vol_regime(btc)

    # DOWN triggers (primary)
    triggers_down_raw = extract_triggers_directional(sig, z_thresh=Z_THRESH, direction="down")
    triggers_up_raw = extract_triggers_directional(sig, z_thresh=Z_THRESH, direction="up")
    log.info("Unfiltered DOWN-triggers: %d  UP-triggers: %d",
             len(triggers_down_raw), len(triggers_up_raw))
    out["n_triggers_down_unfiltered"] = int(len(triggers_down_raw))
    out["n_triggers_up_unfiltered"] = int(len(triggers_up_raw))

    triggers_filt = filter_triggers_by_vol_cutoff(triggers_down_raw, vol_df, DEFAULT_VOL_CUTOFF)
    log.info("HIGH-vol filtered DOWN-triggers (p%d cutoff): %d / %d (%.1f%% retained)",
             int(DEFAULT_VOL_CUTOFF * 100),
             len(triggers_filt), len(triggers_down_raw),
             100.0 * len(triggers_filt) / max(len(triggers_down_raw), 1))
    out["n_triggers_down_highvol_p90"] = int(len(triggers_filt))
    out["trigger_retention_ratio_p90"] = (len(triggers_filt) / max(len(triggers_down_raw), 1))

    if len(triggers_filt) < 10:
        log.warning("HIGH-vol DOWN-triggers < 10, cannot run statistics")
        out["verdict"] = "GRAVEYARD"
        out["verdict_reasons_fail"] = [f"n_triggers_highvol_down={len(triggers_filt)} < 10"]
        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        return

    # Load alts
    log.info("Loading %d alts from joblib cache ...", len(ALTS))
    alt_data = {}
    alt_lookup = {}
    for sym in ALTS:
        df = load_ohlcv_1m_cached(sym)
        if df.empty:
            log.warning("alt %s cache empty", sym)
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
    # H1 — main directional test on HIGH-vol filtered DOWN-triggers, SHORT
    # ============================================================
    log.info("[H1] Main cell: HIGH-vol DOWN-filt + SHORT + hold=%dm ...", DEFAULT_HOLD)
    main_cell = run_cell(alt_data, alt_lookup, triggers_filt, DEFAULT_HOLD, TRADE_DIRECTION)
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

    # Candidate pool: SHORT direction (signed gross) for fair perm null
    log.info("Building candidate pool (hold=%d, dir=%d, n=%d) ...",
             DEFAULT_HOLD, TRADE_DIRECTION, N_POOL_SAMPLES)
    pool = build_candidate_pool(alt_data, alt_lookup, DEFAULT_HOLD, TRADE_DIRECTION,
                                n_samples=N_POOL_SAMPLES, seed=SEED)
    log.info("pool size=%d", len(pool))

    # ============================================================
    # H2 — fee-aware perm + bootstrap CI
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
            cell = run_cell(alt_data, alt_lookup, triggers_filt, hold, TRADE_DIRECTION)
            cur_pool = build_candidate_pool(alt_data, alt_lookup, hold, TRADE_DIRECTION,
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
        t_filt = filter_triggers_by_vol_cutoff(triggers_down_raw, vol_df, cutoff)
        if len(t_filt) < 10:
            h5.append({
                "cutoff_pct": int(cutoff * 100),
                "n_triggers": len(t_filt),
                "note": "insufficient triggers",
            })
            continue
        cell = run_cell(alt_data, alt_lookup, t_filt, DEFAULT_HOLD, TRADE_DIRECTION)
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

    means_by_cutoff = [(r["cutoff_pct"], r.get("net_mean_bp"))
                       for r in h5 if "net_mean_bp" in r]
    h5_monotone = False
    if len(means_by_cutoff) >= 3:
        means_by_cutoff.sort(key=lambda x: x[0])
        all_pos = all(m > 0 for _, m in means_by_cutoff if m is not None)
        p75 = next((m for c, m in means_by_cutoff if c == 75), None)
        p90 = next((m for c, m in means_by_cutoff if c == 90), None)
        if all_pos and p75 is not None and p90 is not None:
            # Stricter (higher pct) cutoff should preserve or strengthen alpha
            h5_monotone = p90 >= p75 - 30  # within 30bp tolerance, prefer p90 >= p75
        elif all_pos:
            h5_monotone = True
    out["h5_monotone"] = h5_monotone

    # ============================================================
    # H6 — comparison to mirror paradigm 69 (UP-trigger + LONG, same vol filter)
    # ============================================================
    log.info("[H6] mirror paradigm 69 comparison (UP-trigger + LONG on SAME data) ...")
    triggers_up_filt = filter_triggers_by_vol_cutoff(triggers_up_raw, vol_df, DEFAULT_VOL_CUTOFF)
    log.info("HIGH-vol filtered UP-triggers (p%d cutoff): %d", int(DEFAULT_VOL_CUTOFF * 100), len(triggers_up_filt))
    h6 = {"n_triggers_up_highvol_p90": int(len(triggers_up_filt))}
    if len(triggers_up_filt) >= 10:
        long_pool = build_candidate_pool(alt_data, alt_lookup, DEFAULT_HOLD, +1,
                                         n_samples=N_POOL_SAMPLES, seed=SEED)
        long_cell = run_cell(alt_data, alt_lookup, triggers_up_filt, DEFAULT_HOLD, +1)
        if long_cell["n_trades"] >= 30:
            long_nets = np.array(long_cell["nets"])
            try:
                fe_long = fee_aware_perm_test(
                    observed_net_returns=long_nets,
                    candidate_pool_returns=long_pool,
                    fee_per_trade=FEE_RT,
                    n_perms=500,
                    rng_seed=SEED,
                )
                bs_long = bootstrap_ci(long_nets, n_boot=400, block_size=1, rng_seed=SEED)
                h6["paradigm_69_long_side"] = {
                    "n_trades": long_cell["n_trades"],
                    "mean_bp": long_cell["net_mean_bp"],
                    "t": long_cell["t"],
                    "win": long_cell["win"],
                    "signal_t_excess": fe_long.get("signal_t_excess"),
                    "ci_lower_bp": bs_long["ci_lower"] * 1e4,
                }
            except Exception as e:
                h6["paradigm_69_long_side"] = {"error": str(e)}
        else:
            h6["paradigm_69_long_side"] = {"note": f"n_trades={long_cell['n_trades']} < 30"}
    else:
        h6["paradigm_69_long_side"] = {"note": "insufficient up-triggers"}

    h6["this_paradigm_short_side"] = {
        "n_trades": main_cell["n_trades"],
        "mean_bp": main_cell["net_mean_bp"],
        "t": main_cell["t"],
        "win": main_cell["win"],
        "signal_t_excess": h2["signal_t_excess"],
        "ci_lower_bp": h2["bootstrap_ci_lower_bp"],
    }
    # Standalone-significant test: short side must NOT be ≥50% weaker than long
    h6_standalone_ok = False
    long_mean = h6.get("paradigm_69_long_side", {}).get("mean_bp")
    short_mean = main_cell["net_mean_bp"]
    if (long_mean is not None and isinstance(long_mean, (int, float)) and not np.isnan(long_mean)
            and short_mean is not None and not np.isnan(short_mean)):
        # short standalone-ok if short_mean >= 0.5 * long_mean (mirror parity tolerance)
        if long_mean > 0:
            h6_standalone_ok = short_mean >= 0.5 * long_mean
        else:
            # If long side itself failed, short being positive is sufficient
            h6_standalone_ok = short_mean > 0
    h6["standalone_ok"] = h6_standalone_ok
    out["h6_mirror_paradigm_69"] = h6

    # ============================================================
    # H7 — baseline: BTC 30m_ret < 0 (no RV filter, no vol regime) SHORT 240m
    # ============================================================
    log.info("[H7] no-RV-filter baseline (BTC 30m_ret < 0 every bar, SHORT 240m) ...")
    # Re-extract baseline triggers: bars where btc_ret_30m < 0, with cooldown to match
    base_mask = sig["btc_ret_30m"] < 0
    base_triggers_full = sig[base_mask].copy()
    # Apply cooldown (same 60 min)
    if len(base_triggers_full) > 0:
        keep = [True]
        last_t = base_triggers_full.index[0]
        for ts in base_triggers_full.index[1:]:
            delta_min = (ts - last_t).total_seconds() / 60.0
            if delta_min < COOLDOWN:
                keep.append(False)
            else:
                keep.append(True)
                last_t = ts
        base_triggers = base_triggers_full[keep]
    else:
        base_triggers = base_triggers_full

    # Cap baseline triggers to avoid 100K+ trades (use random sub-sample, capped at 2000 triggers)
    BASELINE_MAX = 2000
    if len(base_triggers) > BASELINE_MAX:
        log.info("baseline triggers cap: %d -> %d (random subsample)", len(base_triggers), BASELINE_MAX)
        rng_b = np.random.default_rng(SEED)
        idxs = rng_b.choice(len(base_triggers), size=BASELINE_MAX, replace=False)
        base_triggers = base_triggers.iloc[sorted(idxs)]
    log.info("baseline triggers (cooldown-applied, capped): %d", len(base_triggers))
    h7 = {"n_baseline_triggers_unfiltered": int(len(base_triggers_full)),
          "n_baseline_triggers_capped": int(len(base_triggers))}

    if len(base_triggers) >= 30:
        base_cell = run_cell(alt_data, alt_lookup, base_triggers, DEFAULT_HOLD, TRADE_DIRECTION)
        h7["n_trades"] = base_cell["n_trades"]
        h7["net_mean_bp"] = base_cell["net_mean_bp"]
        h7["t"] = base_cell["t"]
        h7["win"] = base_cell["win"]
        log.info("H7: baseline n=%d mean=%+.2f bp t=%+.2f",
                 base_cell["n_trades"], base_cell["net_mean_bp"], base_cell["t"])
        # Baseline-add-value check: triggered must be ≥125% of baseline mean (RV filter adds >=25%)
        bp_trig = main_cell["net_mean_bp"]
        bp_base = base_cell["net_mean_bp"]
        if bp_base is not None and not np.isnan(bp_base):
            if bp_base > 0:
                h7["alpha_ratio_triggered_over_baseline"] = (bp_trig / bp_base) if bp_base != 0 else None
                h7["filter_adds_value"] = (bp_trig >= 1.25 * bp_base) if bp_trig > 0 else False
            else:
                # baseline negative — triggered being positive is sufficient
                h7["alpha_ratio_triggered_over_baseline"] = None
                h7["filter_adds_value"] = bp_trig > 0
        h7["alpha_delta_bp"] = bp_trig - bp_base
    else:
        h7["note"] = f"n_baseline_triggers={len(base_triggers)} < 30"
    out["h7_no_rv_filter_baseline"] = h7

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

    criteria["h2_sig_t_excess_ge_2p0"] = sig_ex is not None and sig_ex >= 2.0
    criteria["h2_ci_lower_pos"] = ci_lo is not None and ci_lo > 0
    criteria["h2_perm_p_above_le_0p05"] = ppa is not None and ppa <= 0.05
    criteria["h1_mean_positive"] = main_cell["net_mean_bp"] > 0
    criteria["h3_alts_pos_ge_10"] = n_alts_pos >= 10
    criteria["h3_alts_pos_ge_11"] = n_alts_pos >= 11
    criteria["h4_holds_pos_ge_4"] = h4_pos >= 4
    criteria["h4_holds_pos_ge_5"] = h4_pos >= 5
    criteria["h5_monotone"] = h5_monotone
    criteria["h6_standalone_ok"] = h6_standalone_ok
    criteria["h7_filter_adds_value"] = h7.get("filter_adds_value", False)

    three_gate = (criteria["h2_sig_t_excess_ge_2p0"]
                  and criteria["h2_ci_lower_pos"]
                  and criteria["h2_perm_p_above_le_0p05"])

    for k, v in criteria.items():
        (reasons_pass if v else reasons_fail).append(f"{k}={v}")

    direction_opposite = main_cell["net_mean_bp"] <= 0
    borderline_excess = (sig_ex is not None and 1.5 <= sig_ex < 2.0
                         and main_cell["net_mean_bp"] > 0)
    h4_severe_fail = h4_pos <= 2

    if direction_opposite:
        verdict = "GRAVEYARD"
    elif (three_gate
          and criteria["h3_alts_pos_ge_10"]
          and not h4_severe_fail
          and criteria["h4_holds_pos_ge_4"]
          and criteria["h5_monotone"]
          and criteria["h6_standalone_ok"]
          and criteria["h7_filter_adds_value"]):
        if (criteria["h3_alts_pos_ge_11"]
                and criteria["h4_holds_pos_ge_5"]
                and criteria["h5_monotone"]):
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


if __name__ == "__main__":
    main()
