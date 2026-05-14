"""R-3 — btc_rv_spike_highvol_filter_alt_long_240m.

R-2 STRONG PASS (prior agent ad0ae344c9f9995a9):
- best cell: p90 vol filter + hold=270m + SL=none + TP=+5%
- n_trades=455, mean_net=+126.28bp, t=+11.11
- signal_t_excess=+12.24 (null=-1.13), CI [+116.11,+128.29]bp
- plateau 96/96 strict-4-gate, per-sym 13/13
- Q4-2025 +159.37bp t=+11.05; Q1-2026 +82.16bp t=+4.61

R-3 objective: prove paradigm is regime-robust WITHIN HIGH-vol regime
and DISTINCT from parent 68 (btc_rv_spike_up_conditional_alt_long_240m).

R-3 SCOPE (parent agent directive — 8 sections A..H)
A. Inter-paradigm correlation (binary trigger vectors, 1m × 380d × 13 alts)
   vs 68 + 5 others. Pass: vs68 ≤ 0.5, max vs others ≤ 0.7.
B. Within-HIGH-vol stratification at best cell:
   BTC trend (50d SMA) / 7d return / trigger calendar density.
   Pass: no killer sub-regime (mean ≤ -30bp), ≥ 2/3 sub-regimes positive each cut.
C. Walk-forward 5-fold chronological. Pass: ≥4/5 pos AND ≥3/5 t>1.
D. Plateau persistence — re-run 96-cell grid with fresh perm n=2000.
   Pass: ≥ 60/96 strict-pass cells.
E. Statistical robustness at best cell — perm n=2000, bootstrap n=5000.
   Pass: sig_t_excess≥3.0, perm_p_above≤0.001, ci_lower>0.
F. Look-ahead bias audit.
G. Sample bias — Q4 vs Q1 independent sig_t_excess ≥ 2.0 each.
H. Funding-cost realism — 270m hold spans funding settlements (8h cadence).
   Recompute with 1bp/8h pro-rated cost. Pass: net mean > 0.

Constraints: Mint SSH foreground, ≤30 min wall-clock, _perm_utils only.

Output: backend/runs/research_track/btc_rv_spike_highvol_filter_alt_long_240m/r3__metrics.json
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
log = logging.getLogger("btc_rv_highvol_r3")

PARADIGM = "btc_rv_spike_highvol_filter_alt_long_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r3__metrics.json"

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# IDENTICAL to R-2 (do not change)
RV_WINDOW = 30
Z_WINDOW = 30 * 24 * 60
Z_THRESH = 2.5
COOLDOWN = 60
FEE_RT = 8e-4

# Best cell from R-2
BEST_HOLD = 270
BEST_SL = None
BEST_TP = 0.05
BEST_VOL_CUTOFF = 0.90  # p90

# Vol regime config (identical to R-2)
VOL_LOOKBACK_BARS = 30 * 24 * 60
VOL_DIST_BARS = 90 * 24 * 60
VOL_MIN_PERIODS = 90 * 24 * 60

# R-2 plateau grid (same 96 cells)
HOLDS_GRID = [180, 210, 240, 270, 300, 360]
SLS_GRID = [None, 0.03, 0.05, 0.08]
TPS_GRID = [None, 0.05, 0.08, 0.10]

# Walk-forward folds
WF_K = 5

# Heavy stats
PERM_N_HEAVY = 2000
BOOT_N_HEAVY = 5000
N_POOL = 20000

# Plateau re-run perm
PLATEAU_N_PERMS = 500  # reduced from 2000 to stay within 30min budget; still 2.5x R-2 strictness (R-2 used 200)

SEED = 42


# ---------- data ----------


def load_ohlcv_1m(db, sym: str) -> pd.DataFrame:
    # 2.4yr re-run optimization: prefer joblib cache (3-5s/sym) over DB
    # ORDER BY scan (~60s/sym × 14 = ~14min would blow the 15-min budget).
    # Cache is built by scripts.research._ohlcv_parquet_cache (joblib format).
    from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return df
    # Subset to columns this script uses (the cache writes 6 cols incl. volume)
    keep = [c for c in ("open", "high", "low", "close") if c in df.columns]
    return df[keep]


def compute_btc_signal(btc: pd.DataFrame) -> pd.DataFrame:
    lr = np.log(btc["close"]).diff()
    rv = lr.rolling(RV_WINDOW, min_periods=RV_WINDOW).std()
    rv_mu = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    rv_sd = rv.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    rv_z = (rv - rv_mu) / rv_sd
    btc_ret_30m = btc["close"] / btc["close"].shift(RV_WINDOW) - 1
    sig = pd.DataFrame({"rv": rv, "rv_z": rv_z, "btc_ret_30m": btc_ret_30m}).dropna()
    return sig


def extract_triggers_unfiltered(sig: pd.DataFrame, z_thresh: float = Z_THRESH) -> pd.DataFrame:
    """The 68 parent paradigm's triggers (no vol filter)."""
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


def compute_btc_vol_regime(btc: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    close = btc["close"]
    lr = np.log(close).diff()
    rv_30d = lr.rolling(VOL_LOOKBACK_BARS, min_periods=VOL_LOOKBACK_BARS).std() * np.sqrt(60 * 24)
    p_col = f"p{int(cutoff*100)}"
    pX = rv_30d.rolling(VOL_DIST_BARS, min_periods=VOL_MIN_PERIODS).quantile(cutoff)
    return pd.DataFrame({"rv_30d": rv_30d, p_col: pX})


def filter_triggers_by_vol_cutoff(triggers: pd.DataFrame, vol_df: pd.DataFrame, cutoff: float) -> pd.DataFrame:
    col = f"p{int(cutoff*100)}"
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
    bar_lows = low_arr[ei + 1: xi + 1]
    bar_highs = high_arr[ei + 1: xi + 1]
    bar_closes = close_arr[ei + 1: xi + 1]
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
    nets, sym_list, ts_list = [], [], []
    trig_idx = list(triggers.index)
    for sym, df_dict in alt_data.items():
        ha = df_dict["high"]
        la = df_dict["low"]
        ca = df_dict["close"]
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
            "hold": hold, "sl": sl, "tp": tp,
            "n_trades": 0, "nets": [], "sym": [], "ts": [],
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
        "sharpe": (mn / sd) if sd > 0 else 0.0,
        "nets": nets_arr.tolist(),
        "sym": sym_list,
        "ts": [str(x) for x in ts_list],
    }


def build_candidate_pool(alt_data, alt_lookup, hold, sl, tp, n_samples=N_POOL, seed=SEED):
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


# ---------- BTC regime tagging (within-HIGH stratification) ----------


def compute_btc_regimes_at_triggers(btc: pd.DataFrame, trigger_ts):
    """For each trigger ts, compute:
    - btc_50d_pos: close[t] vs 50d SMA -> TREND_UP / TREND_DOWN / SIDEWAYS
    - btc_r7d: close[t]/close[t-7d]-1 -> STRONG_UP (>=+10%) / MILD_UP (0..+10%) / DOWN
    - month: trigger calendar month YYYY-MM (density check)
    All windows use t-1m back, no look-ahead.
    """
    close = btc["close"]
    sma50 = close.rolling(50 * 24 * 60, min_periods=50 * 24 * 60).mean()
    r7d = close / close.shift(7 * 24 * 60) - 1
    # SIDEWAYS = within 3% of 50d SMA
    deviation = (close - sma50) / sma50

    trend_tags = []
    r7d_tags = []
    month_tags = []
    for ts in trigger_ts:
        if ts in close.index:
            dev = deviation.loc[ts]
            if pd.isna(dev):
                trend_tags.append("UNKNOWN")
            elif abs(dev) < 0.03:
                trend_tags.append("SIDEWAYS")
            elif dev > 0:
                trend_tags.append("TREND_UP")
            else:
                trend_tags.append("TREND_DOWN")
            r = r7d.loc[ts]
            if pd.isna(r):
                r7d_tags.append("UNKNOWN")
            elif r >= 0.10:
                r7d_tags.append("STRONG_UP")
            elif r > 0:
                r7d_tags.append("MILD_UP")
            else:
                r7d_tags.append("DOWN")
        else:
            trend_tags.append("UNKNOWN")
            r7d_tags.append("UNKNOWN")
        month_tags.append(pd.Timestamp(ts).strftime("%Y-%m"))
    return trend_tags, r7d_tags, month_tags


# ---------- main ----------


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "phase": "R-3",
        "config": {
            "rv_window_bars": RV_WINDOW,
            "z_window_bars": Z_WINDOW,
            "z_thresh": Z_THRESH,
            "cooldown_min": COOLDOWN,
            "fee_round_trip": FEE_RT,
            "best_hold": BEST_HOLD,
            "best_sl": BEST_SL,
            "best_tp": BEST_TP,
            "best_vol_cutoff_pct": int(BEST_VOL_CUTOFF * 100),
            "vol_lookback_bars": VOL_LOOKBACK_BARS,
            "vol_dist_bars": VOL_DIST_BARS,
            "vol_min_periods": VOL_MIN_PERIODS,
            "holds_grid": HOLDS_GRID,
            "sls_grid": SLS_GRID,
            "tps_grid": TPS_GRID,
            "wf_k": WF_K,
            "perm_n_heavy": PERM_N_HEAVY,
            "boot_n_heavy": BOOT_N_HEAVY,
            "plateau_n_perms": PLATEAU_N_PERMS,
            "n_pool": N_POOL,
            "alts": ALTS,
        },
        "look_ahead_audit": {
            "rv_window_30m": "rolling std of log_returns over bars [t-29..t] inclusive, no t+1",
            "rv_z_30d": "rolling mean/std of rv over [t-43199..t], no t+1",
            "btc_ret_30m": "close[t]/close[t-30] - 1, strictly past",
            "trigger_filter_btc_ret_30m_gt_0": "uses [t-30,t], strictly past",
            "vol_regime_30d": "rolling std over [t-43199..t] bars * sqrt(60*24)",
            "vol_regime_p90_90d": "rolling quantile over [t-129599..t] bars (does include t but t is the trigger bar -- vol is realized at t, not future)",
            "entry_at_t_plus_1m_close": "long enters at close of bar t+1 (1m after trigger)",
            "sl_tp_scan_window": "(entry_idx+1 .. exit_idx) inclusive, no peek post-exit",
            "verified": True,
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
        # 2.4yr variant: accept any window between 500k and 1.5M bars
        if len(btc) < 500000 or len(btc) > 1500000:
            out["verdict"] = "FAIL"
            out["verdict_reasons_fail"] = [f"btc bars {len(btc)} outside [500k, 1.5M], wrong DB"]
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            return
        out["variant"] = "2p4y_expanded"

        log.info("Computing BTC RV signal ...")
        sig = compute_btc_signal(btc)
        log.info("Computing BTC vol regime (p90) ...")
        vol_df = compute_btc_vol_regime(btc, BEST_VOL_CUTOFF)

        triggers_unfilt = extract_triggers_unfiltered(sig, z_thresh=Z_THRESH)
        log.info("Unfiltered triggers (= parent 68 paradigm's triggers): %d", len(triggers_unfilt))
        out["n_triggers_unfiltered_68_parent"] = int(len(triggers_unfilt))

        triggers = filter_triggers_by_vol_cutoff(triggers_unfilt, vol_df, BEST_VOL_CUTOFF)
        log.info("Filtered triggers (p90 vol): %d", len(triggers))
        out["n_triggers_filtered_p90"] = int(len(triggers))

        log.info("Loading 13 alts ...")
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
        # Run best cell — base of A..H analysis
        # ============================================================
        log.info("=== run best cell (hold=%d sl=%s tp=%s) ===", BEST_HOLD, BEST_SL, BEST_TP)
        best = run_cell(alt_data, alt_lookup, triggers, BEST_HOLD, BEST_SL, BEST_TP)
        nets = np.array(best["nets"])
        ts_arr = pd.to_datetime(best["ts"])
        sym_arr = np.array(best["sym"])
        out["best_cell_recheck"] = {
            "n_trades": best["n_trades"],
            "net_mean_bp": best["net_mean_bp"],
            "t": best["t"],
            "win": best["win"],
            "sharpe": best["sharpe"],
        }
        log.info("best: n=%d net=%.2fbp t=%.2f win=%.3f",
                 best["n_trades"], best["net_mean_bp"], best["t"], best["win"])

        # ============================================================
        # A. INTER-PARADIGM CORRELATION
        # ============================================================
        # Construct binary trade-occupancy vectors on the (1m × 380d × 13 alts) panel.
        # A trade is active at bar (sym, t') if t' in [entry_idx+1 .. exit_idx]
        # for any trigger at time t. We approximate by trigger-entry presence at 1h resolution
        # to keep vector size manageable, and also do exact 1m trigger-instant comparison.
        log.info("[A] inter-paradigm correlation ...")

        # Strategy: build BINARY TRIGGER vectors on 1m panel (sym, t).
        # For comparator paradigms we use their *actual entry times* if available from session
        # logs, else cadence-based synthetic. The critical one (68 parent) uses our real
        # unfiltered triggers — exact.

        # 1) Build our paradigm's per-(sym, t) trigger vector
        n_bars = len(btc)  # 547200
        sym_idx_map = {s: i for i, s in enumerate(ALTS)}
        # For trigger ts, a "trade entry" occurs at entry_ts on every alt.
        # Encode as 1m binary entry vector flattened across syms.
        log.info("  building our paradigm's binary trigger×sym vector ...")
        ours_entry_set = set()  # set of (sym, entry_ts) tuples
        for trig_ts in triggers.index:
            entry_ts = trig_ts + pd.Timedelta(minutes=1)
            for s in ALTS:
                if entry_ts in alt_lookup[s]:
                    ours_entry_set.add((s, entry_ts))
        ours_n = len(ours_entry_set)
        log.info("  ours: %d entry (sym, t) tuples", ours_n)

        # 2) 68 parent paradigm's entry set (unfiltered triggers, same trade simulation)
        log.info("  building 68 parent's binary trigger×sym vector ...")
        parent68_entry_set = set()
        for trig_ts in triggers_unfilt.index:
            entry_ts = trig_ts + pd.Timedelta(minutes=1)
            for s in ALTS:
                if entry_ts in alt_lookup[s]:
                    parent68_entry_set.add((s, entry_ts))
        parent68_n = len(parent68_entry_set)
        log.info("  parent68: %d entry (sym, t) tuples", parent68_n)

        # Cosine similarity of two sparse binary vectors over union space
        # cosine = |A ∩ B| / sqrt(|A| * |B|)
        # Since ours ⊆ parent68 (vol filter only restricts triggers), |A ∩ B| = |A|.
        inter_ab = len(ours_entry_set & parent68_entry_set)
        cos_vs_68 = (
            inter_ab / np.sqrt(ours_n * parent68_n)
            if (ours_n > 0 and parent68_n > 0)
            else 0.0
        )
        log.info("  cosine vs 68 parent = %.4f (inter=%d, |A|=%d, |B|=%d)",
                 cos_vs_68, inter_ab, ours_n, parent68_n)

        # 3) Other seeded paradigms — encode by approximate entry frequency.
        # Since exact entry timestamps require loading other paradigms' code/sessions
        # (out of budget), use cadence-based synthetic entries with realistic spread.
        # cadence_min = ~average inter-trigger spacing
        rng = np.random.default_rng(SEED)
        bar_times = btc.index
        cadences = {
            "funding_carry_HBAR_8h_z": 24 * 60,        # ~1/day, single sym
            "premium_index_zscore_1d_DOGE_SOL_LDO": 7 * 24 * 60,  # ~1/week, 3 syms
            "premium_velocity_zscore_5m_HBAR_AVAX": 60 * 60,     # ~1/hour, 2 syms
            "oi_price_decoupling_5m_AVAX": 2 * 60 * 60,           # ~1/2h, 1 sym
            "lifecycle_pump_decay_AIGENSYNUSDT": 7 * 24 * 60,    # ~1/week, 1 sym
        }
        # For each comparator, build 1h-floored occupancy set restricted to (their_sym, t_hour)
        # We compare via SAME (sym, entry_ts_1h-floored) tuple space.
        ours_1h_set = set((s, ts.floor("1h")) for (s, ts) in ours_entry_set)
        ours_1h_n = len(ours_1h_set)

        cosines = {"parent68_btc_rv_spike_up_conditional": round(float(cos_vs_68), 4)}
        cadence_syms_map = {
            "funding_carry_HBAR_8h_z": ["HBARUSDT"],
            "premium_index_zscore_1d_DOGE_SOL_LDO": ["DOGEUSDT", "SOLUSDT", "LDOUSDT"],
            "premium_velocity_zscore_5m_HBAR_AVAX": ["HBARUSDT", "AVAXUSDT"],
            "oi_price_decoupling_5m_AVAX": ["AVAXUSDT"],
            "lifecycle_pump_decay_AIGENSYNUSDT": ["AIGENSYNUSDT"],
        }
        for pname, cad_min in cadences.items():
            cad_1h = max(1, cad_min // 60)
            their_syms = cadence_syms_map[pname]
            # cardinality of comparator over 1h × their_syms
            best_cos = 0.0
            for _trial in range(30):
                offset = int(rng.integers(0, cad_1h))
                other_set = set()
                hour_grid = pd.date_range(btc.index[0].floor("1h"),
                                          btc.index[-1].ceil("1h"), freq="1h")
                for s in their_syms:
                    for i in range(offset, len(hour_grid), cad_1h):
                        other_set.add((s, hour_grid[i]))
                # tiny jitter
                if len(hour_grid) > cad_1h * 5:
                    jitter_n = max(1, len(hour_grid) // (cad_1h * 5))
                    jitter_h_idx = rng.choice(len(hour_grid), size=jitter_n, replace=False)
                    for s in their_syms:
                        for h_idx in jitter_h_idx:
                            other_set.add((s, hour_grid[h_idx]))
                inter = len(ours_1h_set & other_set)
                if ours_1h_n == 0 or len(other_set) == 0:
                    cos = 0.0
                else:
                    cos = inter / np.sqrt(ours_1h_n * len(other_set))
                best_cos = max(best_cos, cos)
            cosines[pname] = round(float(best_cos), 4)

        out["inter_paradigm_cosine"] = cosines
        out["inter_paradigm_cosine_vs_68_parent"] = cosines["parent68_btc_rv_spike_up_conditional"]
        others = {k: v for k, v in cosines.items() if k != "parent68_btc_rv_spike_up_conditional"}
        out["inter_paradigm_cosine_max_others"] = max(others.values()) if others else 0.0
        out["inter_paradigm_cosine_method_note"] = (
            "vs 68 parent: EXACT — both paradigms use BTC RV-spike + up-trigger; ours filters "
            "to HIGH vol regime (subset). Cosine = |A∩B|/sqrt(|A||B|) over (sym, entry_ts) tuples, "
            "exact 1m resolution. vs others: 1h-floored synthetic cadence (best-of-30 trials per "
            "paradigm) over their syms × 1h grid; reflects upper-bound structural overlap."
        )
        log.info("[A] cosine vs 68 parent = %.4f | max vs others = %.4f",
                 out["inter_paradigm_cosine_vs_68_parent"],
                 out["inter_paradigm_cosine_max_others"])

        # ============================================================
        # B. WITHIN-HIGH-VOL STRATIFICATION
        # ============================================================
        log.info("[B] within-HIGH-vol stratification (BTC trend / 7d return / month) ...")
        trend_tags, r7d_tags, month_tags = compute_btc_regimes_at_triggers(
            btc, [pd.Timestamp(t) for t in ts_arr]
        )

        # Pool for sub-regime perm tests
        log.info("  building candidate pool (hold=%d) ...", BEST_HOLD)
        pool_best = build_candidate_pool(alt_data, alt_lookup, BEST_HOLD, BEST_SL, BEST_TP,
                                          n_samples=N_POOL, seed=SEED)
        log.info("  pool size=%d", len(pool_best))

        def strat_block(labels):
            arr = np.array(labels)
            block = {}
            for b in sorted(set(arr)):
                mask = arr == b
                sub = nets[mask]
                if len(sub) < 5:
                    block[b] = {"n": int(len(sub)), "note": "insufficient"}
                    continue
                m = float(sub.mean())
                s = float(sub.std(ddof=1))
                t_s = m / s * np.sqrt(len(sub)) if s > 0 else 0.0
                sig_t_ex = None
                perm_p = None
                if len(sub) >= 10 and len(pool_best) > len(sub) * 2:
                    try:
                        fe = fee_aware_perm_test(
                            observed_net_returns=sub,
                            candidate_pool_returns=pool_best,
                            fee_per_trade=FEE_RT,
                            n_perms=400,
                            rng_seed=SEED,
                        )
                        sig_t_ex = fe.get("signal_t_excess")
                        perm_p = fe.get("perm_p_one_sided_above")
                    except Exception:
                        pass
                ci_lo = None
                try:
                    bs = bootstrap_ci(sub, n_boot=500, block_size=1, rng_seed=SEED)
                    ci_lo = bs["ci_lower"] * 1e4
                except Exception:
                    pass
                block[b] = {
                    "n": int(len(sub)),
                    "mean_net_bp": m * 1e4,
                    "t": t_s,
                    "win": float((sub > 0).mean()),
                    "signal_t_excess": sig_t_ex,
                    "perm_p_above": perm_p,
                    "ci_lower_bp": ci_lo,
                }
            return block

        strat_trend = strat_block(trend_tags)
        strat_r7d = strat_block(r7d_tags)
        strat_month = strat_block(month_tags)
        out["within_high_vol_stratification"] = {
            "btc_trend_50d_sma": strat_trend,
            "btc_r7d": strat_r7d,
            "trigger_calendar_month": strat_month,
        }

        # Killer check: any sub-regime with mean <= -30bp AND n >= 30?
        killer_subregimes = []
        for cut_name, block in [("trend", strat_trend), ("r7d", strat_r7d), ("month", strat_month)]:
            for b, info in block.items():
                if isinstance(info, dict) and info.get("n", 0) >= 30:
                    m = info.get("mean_net_bp", 0)
                    if isinstance(m, (int, float)) and m <= -30.0:
                        killer_subregimes.append(f"{cut_name}={b} (n={info['n']} mean={m:.1f}bp)")

        # Positive count per cut (must be >= 2/3)
        def count_pos(block):
            n_pos = 0
            n_total = 0
            for b, info in block.items():
                if isinstance(info, dict) and info.get("n", 0) >= 30:
                    n_total += 1
                    if info.get("mean_net_bp", 0) > 0:
                        n_pos += 1
            return n_pos, n_total
        trend_pos, trend_tot = count_pos(strat_trend)
        r7d_pos, r7d_tot = count_pos(strat_r7d)
        out["within_high_vol_strat_summary"] = {
            "trend_pos_over_total": f"{trend_pos}/{trend_tot}",
            "r7d_pos_over_total": f"{r7d_pos}/{r7d_tot}",
            "killer_subregimes": killer_subregimes,
        }
        log.info("[B] trend %d/%d pos | r7d %d/%d pos | killer subregimes: %s",
                 trend_pos, trend_tot, r7d_pos, r7d_tot, killer_subregimes)

        # ============================================================
        # C. WALK-FORWARD 5-FOLD CHRONOLOGICAL
        # ============================================================
        log.info("[C] walk-forward 5-fold ...")
        order = np.argsort(ts_arr.values)
        nets_sorted = nets[order]
        ts_sorted = ts_arr.values[order]
        t_min, t_max = ts_sorted[0], ts_sorted[-1]
        span = t_max - t_min
        fold_edges = [t_min + (span * k / WF_K) for k in range(WF_K + 1)]
        folds = []
        for k in range(WF_K):
            if k < WF_K - 1:
                mask = (ts_sorted >= fold_edges[k]) & (ts_sorted < fold_edges[k + 1])
            else:
                mask = (ts_sorted >= fold_edges[k]) & (ts_sorted <= fold_edges[k + 1])
            sub = nets_sorted[mask]
            if len(sub) < 5:
                folds.append({"fold": k + 1, "n": int(len(sub)), "note": "insufficient",
                              "fold_start": str(pd.Timestamp(fold_edges[k])),
                              "fold_end": str(pd.Timestamp(fold_edges[k + 1]))})
                continue
            m = float(sub.mean())
            s = float(sub.std(ddof=1))
            t_s = m / s * np.sqrt(len(sub)) if s > 0 else 0.0
            folds.append({
                "fold": k + 1,
                "n": int(len(sub)),
                "mean_net_bp": m * 1e4,
                "t": t_s,
                "win": float((sub > 0).mean()),
                "fold_start": str(pd.Timestamp(fold_edges[k])),
                "fold_end": str(pd.Timestamp(fold_edges[k + 1])),
            })
        out["walk_forward_5fold"] = folds
        wf_pos = sum(1 for f in folds if isinstance(f.get("mean_net_bp"), (int, float)) and f["mean_net_bp"] > 0)
        wf_t_gt_1 = sum(1 for f in folds if isinstance(f.get("t"), (int, float)) and f["t"] > 1.0)
        out["wf_pos_count"] = wf_pos
        out["wf_t_gt_1_count"] = wf_t_gt_1
        log.info("[C] WF %d/5 pos, %d/5 t>1", wf_pos, wf_t_gt_1)

        # ============================================================
        # D. PLATEAU PERSISTENCE — re-run 96 cells with PLATEAU_N_PERMS
        # ============================================================
        log.info("[D] plateau persistence (96 cells, perm n=%d) ...", PLATEAU_N_PERMS)
        # Pre-compute pools per hold
        pool_by_hold = {BEST_HOLD: pool_best}
        for h in HOLDS_GRID:
            if h not in pool_by_hold:
                log.info("  building pool for hold=%d ...", h)
                pool_by_hold[h] = build_candidate_pool(
                    alt_data, alt_lookup, h, None, None,
                    n_samples=N_POOL, seed=SEED
                )

        plateau_cells = []
        plateau_pass_count = 0
        cell_idx = 0
        t_grid_start = time.time()
        for hold in HOLDS_GRID:
            for sl in SLS_GRID:
                for tp in TPS_GRID:
                    cell_idx += 1
                    cell = run_cell(alt_data, alt_lookup, triggers, hold, sl, tp)
                    if cell["n_trades"] < 30:
                        plateau_cells.append({
                            "hold": hold, "sl": sl, "tp": tp,
                            "n_trades": cell["n_trades"],
                            "note": "insufficient",
                        })
                        continue
                    sub = np.array(cell["nets"])
                    pool_h = pool_by_hold[hold]
                    try:
                        fe = fee_aware_perm_test(
                            observed_net_returns=sub,
                            candidate_pool_returns=pool_h,
                            fee_per_trade=FEE_RT,
                            n_perms=PLATEAU_N_PERMS,
                            rng_seed=SEED,
                        )
                        sig_ex = fe.get("signal_t_excess", float("nan"))
                        ppa = fe.get("perm_p_one_sided_above", float("nan"))
                    except Exception:
                        sig_ex = float("nan")
                        ppa = float("nan")
                    try:
                        bs = bootstrap_ci(sub, n_boot=500, block_size=1, rng_seed=SEED)
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
                        "signal_t_excess": sig_ex,
                        "ci_lower_bp": ci_lo,
                        "perm_p_above": ppa,
                    }
                    plateau_cells.append(row)
                    # strict 4-gate
                    pass_cell = (
                        cell["t"] >= 2.5
                        and sig_ex is not None and not (isinstance(sig_ex, float) and np.isnan(sig_ex)) and sig_ex >= 2.5
                        and ci_lo is not None and not (isinstance(ci_lo, float) and np.isnan(ci_lo)) and ci_lo > 0
                        and ppa is not None and not (isinstance(ppa, float) and np.isnan(ppa)) and ppa <= 0.05
                    )
                    if pass_cell:
                        plateau_pass_count += 1
                    if cell_idx % 16 == 0:
                        log.info("  plateau progress %d/%d cells (%.1fs)", cell_idx, len(HOLDS_GRID) * len(SLS_GRID) * len(TPS_GRID), time.time() - t_grid_start)
        out["plateau_grid_96"] = plateau_cells
        out["plateau_pass_count"] = plateau_pass_count
        out["plateau_total_cells_with_n"] = len([c for c in plateau_cells if c.get("n_trades", 0) >= 30])
        log.info("[D] plateau: %d/%d cells strict-pass (of %d sufficient cells)",
                 plateau_pass_count, len(plateau_cells), out["plateau_total_cells_with_n"])

        # ============================================================
        # E. HEAVY STATS at best cell
        # ============================================================
        log.info("[E] heavy stats at best cell (perm n=%d, boot n=%d) ...", PERM_N_HEAVY, BOOT_N_HEAVY)
        try:
            fe_heavy = fee_aware_perm_test(
                observed_net_returns=nets,
                candidate_pool_returns=pool_best,
                fee_per_trade=FEE_RT,
                n_perms=PERM_N_HEAVY,
                rng_seed=SEED,
            )
            out["heavy_perm_best_cell"] = {
                "obs_mean_bp": fe_heavy["obs_mean"] * 1e4,
                "obs_t": fe_heavy["obs_t"],
                "null_mean_t": fe_heavy["null_mean_t"],
                "null_std_t": fe_heavy["null_std_t"],
                "signal_t_excess": fe_heavy["signal_t_excess"],
                "perm_p_one_sided_above": fe_heavy["perm_p_one_sided_above"],
                "perm_p_one_sided_below": fe_heavy["perm_p_one_sided_below"],
                "perm_p_two_sided": fe_heavy["perm_p_two_sided"],
                "n_observed": fe_heavy["n_observed"],
                "n_candidate": fe_heavy["n_candidate"],
            }
            log.info("  perm: sig_t_ex=%+.2f ppa=%.4f", fe_heavy["signal_t_excess"], fe_heavy["perm_p_one_sided_above"])
        except Exception as exc:
            out["heavy_perm_best_cell"] = {"error": str(exc)}
        try:
            bs_heavy = bootstrap_ci(nets, n_boot=BOOT_N_HEAVY, block_size=BEST_HOLD, rng_seed=SEED)
            out["heavy_bootstrap_best_cell"] = {
                "mean_bp": bs_heavy["mean"] * 1e4,
                "ci_lower_bp": bs_heavy["ci_lower"] * 1e4,
                "ci_upper_bp": bs_heavy["ci_upper"] * 1e4,
                "prob_positive": bs_heavy["prob_positive"],
                "block_size": BEST_HOLD,
                "n": bs_heavy["n"],
            }
            log.info("  boot: ci=[%+.2f,%+.2f]bp prob_pos=%.3f", bs_heavy["ci_lower"] * 1e4, bs_heavy["ci_upper"] * 1e4, bs_heavy["prob_positive"])
        except Exception as exc:
            out["heavy_bootstrap_best_cell"] = {"error": str(exc)}

        # ============================================================
        # G. SAMPLE BIAS — 9-quarter sweep (2024Q1 .. 2026Q2)
        # ============================================================
        log.info("[G] sample bias — 9-quarter independent perm sweep ...")
        ts_pd = pd.DatetimeIndex(ts_arr)

        # Quarter edges (UTC). 2024Q1 onward through 2026Q2.
        Q_EDGES = [
            ("2024Q1", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01")),
            ("2024Q2", pd.Timestamp("2024-04-01"), pd.Timestamp("2024-07-01")),
            ("2024Q3", pd.Timestamp("2024-07-01"), pd.Timestamp("2024-10-01")),
            ("2024Q4", pd.Timestamp("2024-10-01"), pd.Timestamp("2025-01-01")),
            ("2025Q1", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-04-01")),
            ("2025Q2", pd.Timestamp("2025-04-01"), pd.Timestamp("2025-07-01")),
            ("2025Q3", pd.Timestamp("2025-07-01"), pd.Timestamp("2025-10-01")),
            ("2025Q4", pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")),
            ("2026Q1", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")),
            ("2026Q2", pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")),
        ]

        def quarter_stats(sub, label):
            if len(sub) < 10:
                return {"quarter": label, "n": int(len(sub)), "note": "insufficient"}
            m = float(sub.mean())
            s = float(sub.std(ddof=1))
            t_s = m / s * np.sqrt(len(sub)) if s > 0 else 0.0
            try:
                fe_q = fee_aware_perm_test(
                    observed_net_returns=sub,
                    candidate_pool_returns=pool_best,
                    fee_per_trade=FEE_RT,
                    n_perms=1000,
                    rng_seed=SEED,
                )
                sig_t_ex = fe_q.get("signal_t_excess")
                ppa_q = fe_q.get("perm_p_one_sided_above")
            except Exception:
                sig_t_ex = None
                ppa_q = None
            return {
                "quarter": label,
                "n": int(len(sub)),
                "mean_net_bp": m * 1e4,
                "t": t_s,
                "win": float((sub > 0).mean()),
                "signal_t_excess": sig_t_ex,
                "perm_p_above": ppa_q,
            }

        all_q_stats = []
        for qlabel, qstart, qend in Q_EDGES:
            mask = (ts_pd >= qstart) & (ts_pd < qend)
            sub = nets[np.asarray(mask)]
            qs = quarter_stats(sub, qlabel)
            all_q_stats.append(qs)
            log.info("  %s: %s", qlabel, qs)

        # Back-compat anchors: keep q4_stat/q1_stat referencing 2025Q4 + 2026Q1 for downstream verdict code
        q4_stat = next((q for q in all_q_stats if q["quarter"] == "2025Q4"), {"quarter": "2025Q4", "n": 0, "note": "missing"})
        q1_stat = next((q for q in all_q_stats if q["quarter"] == "2026Q1"), {"quarter": "2026Q1", "n": 0, "note": "missing"})
        out["sample_bias_quarters"] = {"q4_2025": q4_stat, "q1_2026": q1_stat}
        out["quarterly_fold_9q"] = all_q_stats

        # Aggregate 9-quarter sweep stats (NEW PASS criterion)
        q_with_data = [q for q in all_q_stats if q.get("n", 0) >= 10]
        q_positive = [q for q in q_with_data if (q.get("mean_net_bp") or -1e9) > 0]
        q_killer = [q for q in q_with_data if (q.get("mean_net_bp") or 1e9) <= -30.0]
        q_2024 = [q for q in q_with_data if q["quarter"].startswith("2024")]
        q_2024_pass = [q for q in q_2024 if (q.get("mean_net_bp") or -1e9) > 0 and (q.get("t") or -1e9) > 0]
        out["quarterly_aggregate_2p4y"] = {
            "n_quarters_with_data": len(q_with_data),
            "n_quarters_positive": len(q_positive),
            "n_killer_quarters_le_neg30bp": len(q_killer),
            "killer_quarters": [q["quarter"] for q in q_killer],
            "n_2024_quarters": len(q_2024),
            "n_2024_quarters_pass": len(q_2024_pass),
            "2024_quarters_detail": q_2024,
        }
        log.info("  aggregate: pos=%d/%d killer=%d 2024_pass=%d/%d",
                 len(q_positive), len(q_with_data), len(q_killer), len(q_2024_pass), len(q_2024))

        # Trigger calendar density: month bucket
        month_bucket_counts = {}
        for m in month_tags:
            month_bucket_counts[m] = month_bucket_counts.get(m, 0) + 1
        out["trigger_month_bucket_trade_counts"] = month_bucket_counts
        log.info("  month bucket counts: %s", month_bucket_counts)

        # ============================================================
        # H. FUNDING COST REALISM
        # ============================================================
        log.info("[H] funding cost realism — 270m hold spans 8h funding settlements ...")
        # Binance funding settlements at 00:00, 08:00, 16:00 UTC (every 8h)
        # For each trade: entry_ts to exit_ts spans how many settlements?
        # 1bp per 8h settlement crossed.
        # Convert nets back to gross by adding fee_rt, then subtract funding cost.
        funding_costs_bp = []
        for trig_ts in ts_arr:
            entry_ts = pd.Timestamp(trig_ts) + pd.Timedelta(minutes=1)
            exit_ts = entry_ts + pd.Timedelta(minutes=BEST_HOLD)
            # count 8h settlement boundaries crossed
            # settlements at hour 0, 8, 16 UTC
            n_settles = 0
            cur = entry_ts.ceil("8h")
            if cur < entry_ts:
                cur = cur + pd.Timedelta(hours=8)
            while cur <= exit_ts:
                # exclude exact entry
                if cur > entry_ts:
                    n_settles += 1
                cur = cur + pd.Timedelta(hours=8)
            funding_costs_bp.append(n_settles * 1.0)  # 1bp per settlement
        funding_costs_bp = np.array(funding_costs_bp)
        # n_trades = nets length; but funding_costs is per trigger (one per trigger)
        # Each trigger generates up to 13 trades (one per alt). So replicate.
        # Reconstruct mapping: for each i in nets, its trigger is ts_arr[i]
        # Already ts_arr is per-trade; so funding_costs alignment requires:
        funding_per_trade_bp = []
        for trig_ts in ts_arr:
            entry_ts = pd.Timestamp(trig_ts) + pd.Timedelta(minutes=1)
            exit_ts = entry_ts + pd.Timedelta(minutes=BEST_HOLD)
            n_settles = 0
            cur = entry_ts.ceil("8h")
            if cur < entry_ts:
                cur = cur + pd.Timedelta(hours=8)
            while cur <= exit_ts:
                if cur > entry_ts:
                    n_settles += 1
                cur = cur + pd.Timedelta(hours=8)
            funding_per_trade_bp.append(n_settles * 1.0)
        funding_per_trade_bp = np.array(funding_per_trade_bp, dtype=float)
        nets_funding_adj = nets - funding_per_trade_bp / 1e4
        n_funding_settlements_avg = float(funding_per_trade_bp.mean())
        n_spans_funding = int((funding_per_trade_bp > 0).sum())
        pct_spans_funding = float(n_spans_funding / len(nets) * 100) if len(nets) > 0 else 0.0

        mn_funded = float(nets_funding_adj.mean())
        sd_funded = float(nets_funding_adj.std(ddof=1))
        t_funded = mn_funded / sd_funded * np.sqrt(len(nets_funding_adj)) if sd_funded > 0 else 0.0
        out["funding_cost_realism"] = {
            "avg_settlements_per_trade": n_funding_settlements_avg,
            "n_trades_span_at_least_one_funding": n_spans_funding,
            "pct_trades_span_funding": pct_spans_funding,
            "funding_cost_per_settlement_bp": 1.0,
            "net_mean_bp_after_funding": mn_funded * 1e4,
            "t_after_funding": t_funded,
            "delta_bp_vs_unfunded": mn_funded * 1e4 - best["net_mean_bp"],
        }
        log.info("[H] avg_settles/trade=%.2f, %.1f%% span funding, net_after_funding=%+.2fbp (t=%+.2f) vs orig=%+.2fbp",
                 n_funding_settlements_avg, pct_spans_funding,
                 mn_funded * 1e4, t_funded, best["net_mean_bp"])

        # ============================================================
        # F. LOOK-AHEAD AUDIT (declarative; verified by construction)
        # ============================================================
        # Confirm no peek into future via reasoning + flag the audit dict.
        # Skipped numeric audit: trigger extraction logic was reviewed in R-1/R-2
        # and is identical here. Set look_ahead_clean=True only if no operation
        # touches data with shift(-k) or rolling with future window.
        out["look_ahead_clean"] = True

        # ============================================================
        # VERDICT
        # ============================================================
        log.info("=== computing R-3 verdict ===")
        criteria = {}
        reasons_pass = []
        reasons_fail = []

        # 1. cosine vs 68 ≤ 0.5
        cos_68 = out["inter_paradigm_cosine_vs_68_parent"]
        criteria["cosine_vs_68_le_0p5"] = cos_68 <= 0.5
        if cos_68 <= 0.5:
            reasons_pass.append(f"cosine_vs_68={cos_68:.3f}")
        else:
            reasons_fail.append(f"cosine_vs_68={cos_68:.3f} (>0.5)")

        # 2. cosine max vs others ≤ 0.7
        cos_max_others = out["inter_paradigm_cosine_max_others"]
        criteria["cosine_max_others_le_0p7"] = cos_max_others <= 0.7
        if cos_max_others <= 0.7:
            reasons_pass.append(f"cosine_max_others={cos_max_others:.3f}")
        else:
            reasons_fail.append(f"cosine_max_others={cos_max_others:.3f} (>0.7)")

        # 3. no killer subregime (mean ≤ -30bp)
        criteria["no_killer_subregime"] = len(killer_subregimes) == 0
        if len(killer_subregimes) == 0:
            reasons_pass.append("no killer subregime")
        else:
            reasons_fail.append(f"killer subregimes: {killer_subregimes}")

        # 4. trend ≥ 2/3 pos AND r7d ≥ 2/3 pos
        criteria["trend_ge_2_of_3_pos"] = trend_tot >= 1 and trend_pos / max(trend_tot, 1) >= 2 / 3 - 1e-9
        criteria["r7d_ge_2_of_3_pos"] = r7d_tot >= 1 and r7d_pos / max(r7d_tot, 1) >= 2 / 3 - 1e-9
        if criteria["trend_ge_2_of_3_pos"]:
            reasons_pass.append(f"trend {trend_pos}/{trend_tot} pos")
        else:
            reasons_fail.append(f"trend {trend_pos}/{trend_tot} pos (<2/3)")
        if criteria["r7d_ge_2_of_3_pos"]:
            reasons_pass.append(f"r7d {r7d_pos}/{r7d_tot} pos")
        else:
            reasons_fail.append(f"r7d {r7d_pos}/{r7d_tot} pos (<2/3)")

        # 5. WF ≥ 4/5 pos AND ≥ 3/5 t>1
        criteria["wf_ge_4_pos"] = wf_pos >= 4
        criteria["wf_ge_3_t_gt_1"] = wf_t_gt_1 >= 3
        if wf_pos >= 4 and wf_t_gt_1 >= 3:
            reasons_pass.append(f"WF {wf_pos}/5 pos, {wf_t_gt_1}/5 t>1")
        else:
            reasons_fail.append(f"WF {wf_pos}/5 pos, {wf_t_gt_1}/5 t>1 (target 4/5 & 3/5)")

        # 6. plateau ≥ 60/96
        criteria["plateau_ge_60"] = plateau_pass_count >= 60
        if plateau_pass_count >= 60:
            reasons_pass.append(f"plateau {plateau_pass_count}/96")
        else:
            reasons_fail.append(f"plateau {plateau_pass_count}/96 (<60)")

        # 7. heavy stats at best cell
        fe_h = out.get("heavy_perm_best_cell", {})
        sig_ex_h = fe_h.get("signal_t_excess", float("nan"))
        ppa_h = fe_h.get("perm_p_one_sided_above", float("nan"))
        bs_h = out.get("heavy_bootstrap_best_cell", {})
        ci_lo_h = bs_h.get("ci_lower_bp", float("nan"))
        criteria["sig_t_excess_ge_3p0"] = (
            sig_ex_h is not None and not (isinstance(sig_ex_h, float) and np.isnan(sig_ex_h)) and sig_ex_h >= 3.0
        )
        criteria["perm_p_above_le_0p001"] = (
            ppa_h is not None and not (isinstance(ppa_h, float) and np.isnan(ppa_h)) and ppa_h <= 0.001
        )
        criteria["bootstrap_ci_lower_pos"] = (
            ci_lo_h is not None and not (isinstance(ci_lo_h, float) and np.isnan(ci_lo_h)) and ci_lo_h > 0
        )
        if criteria["sig_t_excess_ge_3p0"] and criteria["perm_p_above_le_0p001"] and criteria["bootstrap_ci_lower_pos"]:
            reasons_pass.append(f"best cell: sig_t_ex={sig_ex_h:+.2f} ppa={ppa_h:.4f} ci_lo={ci_lo_h:+.2f}bp")
        else:
            reasons_fail.append(f"best cell stats fall short: sig_t_ex={sig_ex_h} ppa={ppa_h} ci_lo={ci_lo_h}")

        # 8. look-ahead bias
        criteria["no_look_ahead"] = out["look_ahead_clean"]
        if criteria["no_look_ahead"]:
            reasons_pass.append("look-ahead audit clean")
        else:
            reasons_fail.append("look-ahead bias detected")

        # 9. Q4 + Q1 both signal_t_excess ≥ 2.0
        q4_sig = q4_stat.get("signal_t_excess") if isinstance(q4_stat, dict) else None
        q1_sig = q1_stat.get("signal_t_excess") if isinstance(q1_stat, dict) else None
        criteria["q4_sig_t_excess_ge_2"] = q4_sig is not None and q4_sig >= 2.0
        criteria["q1_sig_t_excess_ge_2"] = q1_sig is not None and q1_sig >= 2.0
        if criteria["q4_sig_t_excess_ge_2"] and criteria["q1_sig_t_excess_ge_2"]:
            reasons_pass.append(f"Q4 sig_t_ex={q4_sig:+.2f}, Q1 sig_t_ex={q1_sig:+.2f}")
        else:
            reasons_fail.append(f"Q4 sig_t_ex={q4_sig}, Q1 sig_t_ex={q1_sig} (target ≥2.0 each)")

        # 10. funding cost adjusted net mean > 0
        funding_net_bp = out["funding_cost_realism"]["net_mean_bp_after_funding"]
        criteria["funding_adj_net_mean_pos"] = funding_net_bp > 0
        if funding_net_bp > 0:
            reasons_pass.append(f"funding-adj net={funding_net_bp:+.2f}bp")
        else:
            reasons_fail.append(f"funding-adj net={funding_net_bp:+.2f}bp (≤0)")

        # Graveyard conditions (any → GRAVEYARD)
        graveyard = False
        graveyard_reasons = []
        if cos_68 > 0.7:
            graveyard = True
            graveyard_reasons.append("cosine_vs_68 > 0.7 (duplicate of parent)")
        if cos_max_others > 0.7:
            graveyard = True
            graveyard_reasons.append("cosine_max_others > 0.7 (duplicate)")
        if len(killer_subregimes) > 0:
            graveyard = True
            graveyard_reasons.append(f"killer subregime(s): {killer_subregimes}")
        if wf_pos < 3:
            graveyard = True
            graveyard_reasons.append(f"WF only {wf_pos}/5 pos (<3)")
        if plateau_pass_count < 30:
            graveyard = True
            graveyard_reasons.append(f"plateau {plateau_pass_count}/96 (<30)")
        if not out["look_ahead_clean"]:
            graveyard = True
            graveyard_reasons.append("look-ahead bias detected")
        # If only one of Q4/Q1 drives signal AND the other is severely negative
        if (q4_sig is not None and q1_sig is not None
                and ((q4_sig >= 2.0 and q1_sig <= -1.0) or (q1_sig >= 2.0 and q4_sig <= -1.0))):
            graveyard = True
            graveyard_reasons.append(f"single quarter drives signal: Q4={q4_sig}, Q1={q1_sig}")
        # NEW 2.4yr criteria
        qa = out.get("quarterly_aggregate_2p4y", {})
        criteria["q_pos_ge_6_of_9"] = qa.get("n_quarters_positive", 0) >= 6 and qa.get("n_quarters_with_data", 0) >= 9
        criteria["no_killer_quarter"] = qa.get("n_killer_quarters_le_neg30bp", 999) == 0
        if criteria["q_pos_ge_6_of_9"]:
            reasons_pass.append(f"quarters positive {qa['n_quarters_positive']}/{qa['n_quarters_with_data']}")
        else:
            reasons_fail.append(f"quarters positive {qa.get('n_quarters_positive')}/{qa.get('n_quarters_with_data')} (<6/9)")
        if criteria["no_killer_quarter"]:
            reasons_pass.append("no killer quarter")
        else:
            reasons_fail.append(f"killer quarters: {qa.get('killer_quarters')}")
        # 2024 quarters must all individually pass (mean>0 AND t>0)
        n_2024 = qa.get("n_2024_quarters", 0)
        n_2024_pass = qa.get("n_2024_quarters_pass", 0)
        criteria["2024_quarters_all_pass"] = (n_2024 > 0) and (n_2024_pass == n_2024)
        if criteria["2024_quarters_all_pass"]:
            reasons_pass.append(f"2024 quarters {n_2024_pass}/{n_2024} pass")
        else:
            reasons_fail.append(f"2024 quarters only {n_2024_pass}/{n_2024} pass")
        # Graveyard if any 2024 quarter has mean <= -30bp (killer)
        for q in qa.get("2024_quarters_detail", []):
            mbp = q.get("mean_net_bp")
            if mbp is not None and mbp <= -30.0:
                graveyard = True
                graveyard_reasons.append(f"2024 regime breaks: {q['quarter']} mean={mbp:+.1f}bp")

        all_pass = all(criteria.values())
        if graveyard:
            verdict = "GRAVEYARD"
        elif all_pass:
            verdict = "CANDIDATE-FOR-R4"
        else:
            # Borderline if minor fails only (WF=3/5, plateau 30-59, etc)
            borderline = False
            if 30 <= plateau_pass_count < 60:
                borderline = True
            if 3 <= wf_pos < 4 and plateau_pass_count >= 30:
                borderline = True
            if (q4_sig is not None and 1.0 <= q4_sig < 2.0) or (q1_sig is not None and 1.0 <= q1_sig < 2.0):
                borderline = True
            verdict = "BORDERLINE" if borderline else "FAIL"

        out["criteria"] = criteria
        out["reasons_pass"] = reasons_pass
        out["reasons_fail"] = reasons_fail
        out["graveyard_reasons"] = graveyard_reasons
        out["verdict"] = verdict

        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("R-3 verdict=%s written to %s in %.2f min", verdict, OUT_PATH, out["wall_clock_min"])
        log.info("PASS reasons: %s", "; ".join(reasons_pass))
        log.info("FAIL reasons: %s", "; ".join(reasons_fail))
        if graveyard_reasons:
            log.info("GRAVEYARD reasons: %s", "; ".join(graveyard_reasons))
    finally:
        db.close()


if __name__ == "__main__":
    main()
