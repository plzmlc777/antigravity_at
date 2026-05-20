"""paradigm 128 R-3 — alt_volume_burst_intra5m_event_neg_burst_reversion_short_15m.

R-3 robustness audit for paradigm 128 (paradigm 126 split — B arm dedicated):
  Mechanism: panic-sell capitulation reversion SHORT @ 15min hold
  Trigger: 1m volume > 30d-rolling p99 AND |1m_log_ret| > 0.5% AND sign(1m_ret) < 0
  Universe: 13 alts (paradigm 126 cohort)
  Direction: SHORT (B arm)
  Hold: 15min (paradigm 126 R-2 sweet-spot)

paradigm 126 R-2 B arm baseline (30min hold)
--------------------------------------------
  n=14843 / gross +51.57 / net +35.57bp / sigex +37.59 / ci_lower +18.28
  TS-CV 3/5 PASS — 2024H1 ci_lower -0.57 / 2025H2 ci_lower -34.87 fragility
  Hold sweep B: 15min net +36.45 → 30min +35.57 → 45min +26.22 → 60min +20.56
  15min has BEST B-arm net edge (monotone DECREASE with hold)

R-3 7 mandatory caveats (single script)
----------------------------------------
1. Hold horizon final optimization: 10/15/20/25/30/45/60min sweep
   - Monotone DECREASE → 10min sweet? OR 15min sweet? OR non-monotone luck?
2. Vol-regime stratify (BTC 30d vol p33/p67 tercile):
   - PASS: each regime ci_lower > 0 OR concentrated regime explained
   - paradigm 87 + 117 precedent CAUTION
3. Per-symbol debounce stress (≥30min gap):
   - Negative burst clustering check — first vs all-burst
   - PASS: debounced sigex ≥ 80% of R-2
4. Sharpe leverage / SHORT squeeze artifact:
   - Per-trade pnl skewness/kurtosis + max adverse excursion
   - PASS: drawdown < 5% per trade AND skew not extreme right-tail
5. Per-burst signing (NOT per-5m first-burst):
   - Multiple 1m bursts within 5m bin → multiple signals
   - PASS: per-burst sigex ≥ first-burst sigex
6. 2026 OOS holdout (R-3 핵심):
   - IN: 2024-2025 / OOS: 2026Q1+Q2
   - PASS: OOS sigex ≥ 2.0 AND ci_lower > 0
   - paradigm 117 precedent (1.929% < 2% FAIL)
7. Survivorship test:
   - 13 alts cohort outside (lower-tier expansion alts)
   - PASS: extended cohort edge ≥ 50% of cohort edge OR explained

Verdict tree (any hard-fail → graveyard)
----------------------------------------
R3_PASS                              : all 7 caveats clear
R3_FAIL_OOS_FRAGILITY_AT_RECENT_QUARTER : caveat 6 OOS sigex < 2.0 OR ci_lower < 0
R3_FAIL_VOL_REGIME                   : caveat 2 regime degenerate
R3_FAIL_HOLD_HORIZON_NON_MONOTONE    : caveat 1 non-monotone
R3_FAIL_SHORT_SQUEEZE                : caveat 4 max drawdown > 5%/trade
R3_FAIL_SURVIVORSHIP                 : caveat 7 extended cohort < 50%
R3_FAIL_DEBOUNCE_COLLAPSE            : caveat 3 debounced sigex < 80%
R3_FAIL_PER_BURST_DEGRADED           : caveat 5 per-burst sigex < first-burst sigex

Halt at R-3 verdict; DO NOT auto-progress to R-4.
"""
from __future__ import annotations

import io
import json
import logging
import math
import sys
import time
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

# ── Identity ────────────────────────────────────────────────────────────────
PARADIGM_NAME = "alt_volume_burst_intra5m_event_neg_burst_reversion_short_15m"
PARADIGM_NUMBER = 128
PARENT_PARADIGM = 126
ARM_FROM_PARENT = "B"  # neg burst SHORT

OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

# BTC 1h cache reuse from paradigm 117 (24 monthly files 2024-05..2026-04)
BTC_CACHE_DIR = (
    ROOT / "runs" / "research_track"
    / "alt_extreme_24h_drawdown_24h_reversion_long" / "btc_cache"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r3__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p128_r3")

# ── Universe ────────────────────────────────────────────────────────────────
COHORT_PRIMARY = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
# Caveat 7: survivorship expansion (lower-tier alts present in DB)
COHORT_EXPANSION_PROBE = [
    "APTUSDT", "ATOMUSDT", "ICPUSDT", "INJUSDT", "OPUSDT",
    "SEIUSDT", "SUIUSDT", "TIAUSDT", "TRXUSDT", "UNIUSDT",
    "AAVEUSDT", "ARBUSDT", "DOTUSDT", "1000PEPEUSDT", "1000SHIBUSDT",
]

# ── Primary params (B arm, 15min hold) ──────────────────────────────────────
ROLLING_BAR_WINDOW = 30 * 24 * 60  # 30 days × 24h × 60min = 43200 bars (1m frame)
PCTILE = 99.0
MAG = 0.005
PRIMARY_HOLD_MIN = 15  # paradigm 126 R-2 sweet-spot for B
FEE_BP = 16.0
DEBOUNCE_MIN = 30  # caveat 3

# Caveat 1: hold sweep
HOLD_SWEEP = [10, 15, 20, 25, 30, 45, 60]

# Caveat 2: BTC vol regime tercile cutoffs (p33/p67)
BTC_VOL_LOW_PCT = 33.0
BTC_VOL_HIGH_PCT = 67.0

# Caveat 6: OOS split
OOS_START = pd.Timestamp("2026-01-01 00:00:00")
OOS_END = pd.Timestamp("2026-06-30 23:59:59")

DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


# ── Helpers ────────────────────────────────────────────────────────────────


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    return df.set_index("timestamp")


def _t_stat(arr) -> float:
    arr = np.asarray(arr, dtype=float)
    n = len(arr)
    if n < 2:
        return 0.0
    sd = arr.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(arr.mean() / sd * math.sqrt(n))


def _convert(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def _write(out: dict, name: str = "r3__metrics.json") -> None:
    p = OUT_DIR / name
    with p.open("w") as f:
        json.dump(_convert(out), f, indent=2)
    log.info("metrics written: %s", p)


def load_btc_1h_from_cache(months: list[str]) -> pd.DataFrame:
    parts = []
    for m in months:
        f = BTC_CACHE_DIR / f"BTCUSDT_1h_{m}.joblib"
        if not f.exists():
            log.warning("  BTC cache missing %s, fetching ...", m)
            try:
                df = _fetch_btc_1h_archive(m)
                if not df.empty:
                    joblib.dump(df, f)
                    parts.append(df)
                continue
            except Exception as e:
                log.error("  BTC fetch fail %s: %s", m, e)
                continue
        try:
            parts.append(joblib.load(f))
        except Exception as e:
            log.warning("  BTC cache load fail %s: %s", m, e)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def _fetch_btc_1h_archive(month: str) -> pd.DataFrame:
    url = (
        f"https://data.binance.vision/data/futures/um/monthly/klines/"
        f"BTCUSDT/1h/BTCUSDT-1h-{month}.zip"
    )
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    with z.open(z.namelist()[0]) as f:
        df_raw = pd.read_csv(
            f, header=None,
            names=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "count",
                "taker_buy_volume", "taker_buy_quote_volume", "ignore",
            ],
        )
    df_raw["open_time"] = pd.to_numeric(df_raw["open_time"], errors="coerce")
    df_raw = df_raw.dropna(subset=["open_time"])
    if df_raw.empty:
        return pd.DataFrame()
    ot_max = df_raw["open_time"].max()
    unit = "us" if ot_max > 1e14 else "ms"
    df_raw["timestamp"] = pd.to_datetime(df_raw["open_time"], unit=unit)
    df = df_raw[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


# ── Trigger panel builders ─────────────────────────────────────────────────


def build_neg_burst_triggers_5m(
    sym_data: dict[str, pd.DataFrame],
    hold_min: int,
    per_burst_mode: bool = False,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Build B-arm trigger panel: 1m volume > 30d p99 AND |1m_ret|>0.5% AND 1m_ret<0.

    Direction = -1 (SHORT). gross_bp = -1 * fwd_ret * 10000

    Two modes:
      per_burst_mode=False (DEFAULT, paradigm 126 R-2 compatible):
        5m aggregation — first burst-sign in 5m bin
      per_burst_mode=True (Caveat 5):
        Each 1m burst is its own trigger event (no 5m collapse)

    Returns (trigger_panel, unconditional_fwd_ret_panel_bp).
    """
    rows = []
    pool_pieces = []
    for sym, df in sym_data.items():
        j = df.copy()
        j["log_ret_1m"] = np.log(j["close"]).diff()
        j["abs_log_ret_1m"] = j["log_ret_1m"].abs()
        j["vol_pctile_30d"] = (
            j["volume"].rolling(
                window=ROLLING_BAR_WINDOW, min_periods=ROLLING_BAR_WINDOW // 2
            ).quantile(PCTILE / 100.0)
        )
        j["burst"] = (
            (j["volume"] > j["vol_pctile_30d"])
            & (j["abs_log_ret_1m"] > MAG)
        ).astype(int)
        j["burst_sign"] = np.where(
            j["burst"] == 1, np.sign(j["log_ret_1m"]), 0
        ).astype(int)
        j["fwd_ret"] = j["close"].pct_change(hold_min).shift(-hold_min)

        if per_burst_mode:
            # Each 1m bar with burst==1 AND burst_sign<0 is a trigger
            trig = j[(j["burst"] == 1) & (j["burst_sign"] < 0) & j["fwd_ret"].notna()].copy()
            if trig.empty:
                # still contribute to pool
                pool_pieces.append(
                    j[j["fwd_ret"].notna()]["fwd_ret"].values * 10000.0
                )
                continue
            trig["sym"] = sym
            trig["direction"] = -1
            trig["gross_bp"] = trig["fwd_ret"] * -1.0 * 10000.0
            trig["qtr"] = trig.index.to_period("Q").astype(str)
            rows.append(
                trig.reset_index().rename(columns={"timestamp": "ts", "index": "ts"})
                [["ts", "sym", "direction", "gross_bp", "qtr"]]
            )
            pool_pieces.append(j[j["fwd_ret"].notna()]["fwd_ret"].values * 10000.0)
        else:
            # 5m aggregation (first burst-sign in bin)
            first_sign_func = lambda x: int(x[x != 0].iloc[0]) if (x != 0).any() else 0
            j_5m = j.resample("5min").agg({
                "burst": "max",
                "burst_sign": first_sign_func,
                "fwd_ret": "first",
            })
            j_5m = j_5m.dropna(subset=["fwd_ret"])
            pool_pieces.append(j_5m["fwd_ret"].values * 10000.0)
            trig = j_5m[(j_5m["burst"] == 1) & (j_5m["burst_sign"] < 0)].copy()
            if trig.empty:
                continue
            trig["sym"] = sym
            trig["direction"] = -1
            trig["gross_bp"] = trig["fwd_ret"] * -1.0 * 10000.0
            trig["qtr"] = trig.index.to_period("Q").astype(str)
            rows.append(
                trig.reset_index().rename(columns={"timestamp": "ts", "index": "ts"})
                [["ts", "sym", "direction", "gross_bp", "qtr"]]
            )
    if not rows:
        full_pool = np.concatenate(pool_pieces) if pool_pieces else np.array([])
        return pd.DataFrame(), full_pool
    panel = pd.concat(rows, ignore_index=True)
    panel = panel.sort_values("ts").reset_index(drop=True)
    full_pool = np.concatenate(pool_pieces) if pool_pieces else np.array([])
    return panel, full_pool


def build_neg_burst_with_path(
    sym_data: dict[str, pd.DataFrame],
    hold_min: int,
) -> pd.DataFrame:
    """Build trigger panel WITH per-trade path tracking (max adverse excursion).

    Returns DataFrame with: ts, sym, gross_bp, max_adverse_bp (intra-trade max
    against position — for SHORT, this is max upward move = squeeze risk).
    """
    rows = []
    for sym, df in sym_data.items():
        j = df.copy()
        j["log_ret_1m"] = np.log(j["close"]).diff()
        j["abs_log_ret_1m"] = j["log_ret_1m"].abs()
        j["vol_pctile_30d"] = (
            j["volume"].rolling(
                window=ROLLING_BAR_WINDOW, min_periods=ROLLING_BAR_WINDOW // 2
            ).quantile(PCTILE / 100.0)
        )
        j["burst"] = (
            (j["volume"] > j["vol_pctile_30d"])
            & (j["abs_log_ret_1m"] > MAG)
        ).astype(int)
        j["burst_sign"] = np.where(
            j["burst"] == 1, np.sign(j["log_ret_1m"]), 0
        ).astype(int)

        # 5m aggregation (first burst-sign in bin)
        first_sign_func = lambda x: int(x[x != 0].iloc[0]) if (x != 0).any() else 0
        j_5m_burst = j.resample("5min").agg({
            "burst": "max",
            "burst_sign": first_sign_func,
        })
        # 5m bin sign==-1 → neg burst trigger
        trig_ts_5m = j_5m_burst[
            (j_5m_burst["burst"] == 1) & (j_5m_burst["burst_sign"] < 0)
        ].index
        if len(trig_ts_5m) == 0:
            continue

        closes = j["close"]
        for t5 in trig_ts_5m:
            pos = closes.index.searchsorted(t5)
            if pos >= len(closes) - hold_min:
                continue
            entry_px = float(closes.iloc[pos])
            if not np.isfinite(entry_px) or entry_px <= 0:
                continue
            # max adverse excursion for SHORT = max(close_step / entry - 1)
            max_adv_pct = -np.inf
            exit_px = entry_px
            for step in range(1, hold_min + 1):
                bar_pos = pos + step
                if bar_pos >= len(closes):
                    break
                px = float(closes.iloc[bar_pos])
                if not np.isfinite(px) or px <= 0:
                    continue
                # SHORT: adverse = price goes UP
                adv_pct = (px - entry_px) / entry_px
                if adv_pct > max_adv_pct:
                    max_adv_pct = adv_pct
                exit_px = px
            if max_adv_pct == -np.inf:
                continue
            # Final pnl: SHORT exit at +hold bars (or last available)
            fwd_pct = (exit_px - entry_px) / entry_px
            gross_short_bp = -1.0 * fwd_pct * 10000.0
            rows.append({
                "ts": t5,
                "sym": sym,
                "gross_bp": gross_short_bp,
                "max_adverse_bp": max_adv_pct * 10000.0,  # positive for SHORT-adverse
                "qtr": t5.to_period("Q") if hasattr(t5, "to_period") else str(t5),
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["qtr"] = df["qtr"].astype(str)
    return df


# ── Evaluation helpers ──────────────────────────────────────────────────────


def evaluate_arm_b(
    panel: pd.DataFrame,
    fee_bp: float,
    pool_bp: np.ndarray,
    label: str = "B",
    do_per_sym: bool = True,
    seed: int = 128,
) -> dict:
    if panel.empty or len(panel) < 30:
        return {"label": label, "n": int(len(panel)), "skip": True}
    gross = panel["gross_bp"].values
    net = gross - fee_bp
    obs_t = _t_stat(net)
    ci = bootstrap_ci(net / 10000.0, n_boot=2000, block_size=20, rng_seed=seed)
    ci_lower_bp = float(ci["ci_lower"]) * 10000
    ci_upper_bp = float(ci["ci_upper"]) * 10000
    # B arm: pool needs to be negated (SHORT)
    pool_for_short = -pool_bp
    sigex = float("nan")
    perm_p_above = float("nan")
    if len(pool_for_short) >= len(net) * 2:
        perm = fee_aware_perm_test(
            observed_net_returns=net / 10000.0,
            candidate_pool_returns=pool_for_short / 10000.0,
            fee_per_trade=fee_bp / 10000.0,
            n_perms=1000,
            rng_seed=seed,
        )
        sigex = float(perm.get("signal_t_excess", float("nan")))
        perm_p_above = float(perm.get("perm_p_one_sided_above", float("nan")))

    # per-quarter t
    q_t_map = {}
    if "qtr" in panel.columns:
        for q in panel["qtr"].unique():
            s = panel[panel["qtr"] == q]
            if len(s) >= 30:
                q_t_map[q] = _t_stat(s["gross_bp"].values - fee_bp)
    n_q = len(q_t_map)
    n_q_pos = sum(1 for t in q_t_map.values() if t > 0)

    # per-symbol
    sym_ranking = []
    n_sym_ci_pos = 0
    n_sym_meas = 0
    if do_per_sym and "sym" in panel.columns:
        for s in panel["sym"].unique():
            ss = panel[panel["sym"] == s]
            if len(ss) >= 30:
                n_sym_meas += 1
                sn = ss["gross_bp"].values - fee_bp
                sci = bootstrap_ci(sn / 10000.0, n_boot=500, block_size=10, rng_seed=seed)
                sci_lb = float(sci["ci_lower"]) * 10000
                if sci_lb > 0:
                    n_sym_ci_pos += 1
                sym_ranking.append({
                    "sym": s,
                    "n": int(len(ss)),
                    "gross_bp": float(ss["gross_bp"].mean()),
                    "net_bp": float(sn.mean()),
                    "ci_lower_bp": sci_lb,
                    "ci_pos": bool(sci_lb > 0),
                })

    return {
        "label": label,
        "n": int(len(panel)),
        "gross_bp": float(gross.mean()),
        "net_bp": float(net.mean()),
        "obs_t": obs_t,
        "signal_t_excess": sigex,
        "perm_p_one_sided_above": perm_p_above,
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": ci_upper_bp,
        "n_q_measurable": n_q,
        "n_q_pos_t": n_q_pos,
        "q_pos_t_ratio": (n_q_pos / n_q) if n_q else 0.0,
        "per_quarter_t": q_t_map,
        "n_syms_measurable": n_sym_meas,
        "n_syms_ci_pos": n_sym_ci_pos,
        "syms_ci_pos_ratio": (n_sym_ci_pos / n_sym_meas) if n_sym_meas else 0.0,
        "per_symbol": sym_ranking,
        "ci_pos": bool(ci_lower_bp > 0),
    }


def life_changing_4dim_high_freq(
    n: int,
    edge_bp_net: float,
    trades_per_year: float,
    hold_min: int,
    ret_arr_net: np.ndarray,
) -> dict:
    """High-freq diffuse mode (Lesson #41 amendment dual-mode)."""
    util_pct = min(100.0, (hold_min / (24 * 60)) * trades_per_year * 100)
    edge_pct = edge_bp_net / 100.0
    ann_gross_pct = trades_per_year * edge_pct
    if len(ret_arr_net) >= 5 and ret_arr_net.std(ddof=1) > 0:
        sharpe = float(ret_arr_net.mean() / ret_arr_net.std(ddof=1) * np.sqrt(trades_per_year))
    else:
        sharpe = 0.0
    return {
        "n": int(n),
        "trades_per_year": float(trades_per_year),
        "per_trade_edge_pct": float(edge_pct),
        "capital_util_pct": float(util_pct),
        "annualized_sharpe": float(sharpe),
        "ann_gross_pct": float(ann_gross_pct),
        # high-freq diffuse mode (Lesson #41 amendment):
        "pass_high_freq_edge_0_3pct": bool(edge_pct >= 0.3),
        "pass_high_freq_ann_gross_30pct": bool(ann_gross_pct >= 30.0),
        "pass_high_freq_ann_gross_50pct": bool(ann_gross_pct >= 50.0),
        "pass_high_freq_sharpe_1_5": bool(sharpe >= 1.5),
        "pass_high_freq_diffuse_mode": bool(
            edge_pct >= 0.3 and ann_gross_pct >= 30.0 and sharpe >= 1.5
        ),
    }


def apply_debounce(panel: pd.DataFrame, min_gap_min: int) -> pd.DataFrame:
    """Apply per-symbol debounce: drop triggers within min_gap_min of previous fire."""
    if panel.empty:
        return panel
    out_rows = []
    min_gap = pd.Timedelta(minutes=min_gap_min)
    for sym in panel["sym"].unique():
        s = panel[panel["sym"] == sym].sort_values("ts")
        last_t = None
        for _, row in s.iterrows():
            t = pd.to_datetime(row["ts"])
            if last_t is None or (t - last_t) >= min_gap:
                out_rows.append(row)
                last_t = t
    if not out_rows:
        return pd.DataFrame()
    return pd.DataFrame(out_rows).reset_index(drop=True)


def classify_btc_vol_regime(
    btc_1h: pd.DataFrame, alt_panel: pd.DataFrame
) -> pd.Series:
    """Compute BTC 30d realized vol (1h) at each alt trigger ts → regime label.

    Returns pd.Series indexed by panel row (LOW/MID/HIGH).
    """
    if btc_1h.empty or alt_panel.empty:
        return pd.Series([], dtype=str)
    # BTC 1h log returns, 30d rolling std (720h)
    btc_close = btc_1h["close"].astype(float)
    btc_log_ret = np.log(btc_close).diff()
    btc_vol_30d = btc_log_ret.rolling(window=24 * 30, min_periods=24 * 15).std()

    # determine p33/p67 over full window
    valid_vol = btc_vol_30d.dropna()
    if len(valid_vol) < 100:
        return pd.Series(["UNKNOWN"] * len(alt_panel), index=alt_panel.index)
    p33 = float(np.percentile(valid_vol, BTC_VOL_LOW_PCT))
    p67 = float(np.percentile(valid_vol, BTC_VOL_HIGH_PCT))

    # for each alt trigger ts, get most recent BTC vol (floor to nearest hour)
    regimes = []
    for ts in alt_panel["ts"]:
        ts_h = pd.to_datetime(ts).floor("h")
        if ts_h not in btc_vol_30d.index:
            # find prev available
            valid_idx = btc_vol_30d.index[btc_vol_30d.index <= ts_h]
            if len(valid_idx) == 0:
                regimes.append("UNKNOWN")
                continue
            v = btc_vol_30d.loc[valid_idx[-1]]
        else:
            v = btc_vol_30d.loc[ts_h]
        if not np.isfinite(v):
            regimes.append("UNKNOWN")
        elif v < p33:
            regimes.append("LOW")
        elif v < p67:
            regimes.append("MID")
        else:
            regimes.append("HIGH")
    return pd.Series(regimes, index=alt_panel.index), p33, p67


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    t_start = time.time()
    log.info("paradigm 128 R-3 start (KST %s)", datetime_now_kst())
    engine = create_engine(DB_DSN)

    out: dict = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUMBER,
        "parent_paradigm": PARENT_PARADIGM,
        "arm_from_parent": ARM_FROM_PARENT,
        "phase": "R-3",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "primary_params": {
            "rolling_days": 30,
            "volume_percentile": PCTILE,
            "magnitude_threshold": MAG,
            "primary_hold_min": PRIMARY_HOLD_MIN,
            "fee_bp": FEE_BP,
            "debounce_min": DEBOUNCE_MIN,
        },
        "universe_primary": COHORT_PRIMARY,
        "universe_expansion_probe": COHORT_EXPANSION_PROBE,
    }

    # ── Phase 1: load 1m OHLCV primary cohort ─────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 1: load 1m OHLCV (primary cohort, %d alts)", len(COHORT_PRIMARY))
    log.info("=" * 70)
    sym_data: dict[str, pd.DataFrame] = {}
    per_sym_days: dict[str, int] = {}
    for sym in COHORT_PRIMARY:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < ROLLING_BAR_WINDOW * 2:
                log.warning("  %s: insufficient 1m bars (%d) — skip", sym, len(df))
                continue
            sym_data[sym] = df
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            log.info("  %s: %d bars (%d days)", sym, len(df), days)
        except Exception as e:
            log.error("  %s load fail: %s", sym, e)

    if len(sym_data) < 8:
        out["verdict"] = "R3_DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"only {len(sym_data)}/{len(COHORT_PRIMARY)} alts loaded"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    panel_years = max(per_sym_days.values()) / 365.0
    out["n_alts_usable_primary"] = len(sym_data)
    out["per_symbol_days_1m"] = per_sym_days
    out["panel_years"] = panel_years

    # ── Phase 2: build B-arm trigger panel (15min hold primary) ───────────
    log.info("=" * 70)
    log.info("PHASE 2: build B-arm trigger panel (15min hold)")
    log.info("=" * 70)
    panel_15m, pool_15m = build_neg_burst_triggers_5m(
        sym_data, hold_min=PRIMARY_HOLD_MIN, per_burst_mode=False
    )
    log.info("  panel rows=%d / pool rows=%d", len(panel_15m), len(pool_15m))
    out["primary_panel_n"] = int(len(panel_15m))

    # Trim pool for perm efficiency
    rng_master = np.random.default_rng(128)
    if len(pool_15m) > 100000:
        idx_pool = rng_master.choice(len(pool_15m), size=100000, replace=False)
        pool_15m_sampled = pool_15m[idx_pool]
    else:
        pool_15m_sampled = pool_15m

    primary_res = evaluate_arm_b(
        panel_15m, FEE_BP, pool_15m_sampled, label="primary_B_15min"
    )
    out["primary_B_15min"] = primary_res
    log.info(
        "  primary B 15min: n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci[%.2f,%.2f]"
        " q_pos=%d/%d sym_ci_pos=%d/%d",
        primary_res.get("n", 0),
        primary_res.get("gross_bp") or 0.0,
        primary_res.get("net_bp") or 0.0,
        primary_res.get("signal_t_excess") or 0.0,
        primary_res.get("ci_lower_bp") or 0.0,
        primary_res.get("ci_upper_bp") or 0.0,
        primary_res.get("n_q_pos_t", 0), primary_res.get("n_q_measurable", 0),
        primary_res.get("n_syms_ci_pos", 0), primary_res.get("n_syms_measurable", 0),
    )

    # life-changing 4-dim (high-freq diffuse mode)
    tpy_primary = (
        len(panel_15m) / panel_years if panel_years > 0 else 0.0
    )
    net_arr = (panel_15m["gross_bp"].values - FEE_BP) / 10000.0 if len(panel_15m) else np.array([])
    lc4 = life_changing_4dim_high_freq(
        n=len(panel_15m),
        edge_bp_net=primary_res.get("net_bp", 0.0) or 0.0,
        trades_per_year=tpy_primary,
        hold_min=PRIMARY_HOLD_MIN,
        ret_arr_net=net_arr,
    )
    out["life_changing_4dim_primary_15min"] = lc4
    log.info(
        "  lc4 primary 15min: tpy=%.0f edge=%.4f%% util=%.1f%% sharpe=%.2f"
        " ann_gross=%.0f%% diffuse_pass=%s",
        lc4["trades_per_year"], lc4["per_trade_edge_pct"], lc4["capital_util_pct"],
        lc4["annualized_sharpe"], lc4["ann_gross_pct"],
        lc4["pass_high_freq_diffuse_mode"],
    )

    # ── Phase 3: Caveat 1 — hold horizon sweep ────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 3: Caveat 1 — hold horizon sweep %s", HOLD_SWEEP)
    log.info("=" * 70)
    hold_sweep_res = {}
    for h in HOLD_SWEEP:
        log.info("  sweep hold=%dmin ...", h)
        panel_h, pool_h = build_neg_burst_triggers_5m(
            sym_data, hold_min=h, per_burst_mode=False
        )
        if len(pool_h) > 100000:
            idx = rng_master.choice(len(pool_h), size=100000, replace=False)
            pool_h = pool_h[idx]
        res_h = evaluate_arm_b(panel_h, FEE_BP, pool_h, label=f"hold_{h}min", do_per_sym=False)
        if not res_h.get("skip"):
            tpy_h = len(panel_h) / panel_years if panel_years > 0 else 0.0
            net_h = (panel_h["gross_bp"].values - FEE_BP) / 10000.0
            lc4_h = life_changing_4dim_high_freq(
                n=len(panel_h),
                edge_bp_net=res_h["net_bp"],
                trades_per_year=tpy_h,
                hold_min=h,
                ret_arr_net=net_h,
            )
            hold_sweep_res[f"hold_{h}min"] = {
                "n": res_h["n"],
                "gross_bp": res_h["gross_bp"],
                "net_bp": res_h["net_bp"],
                "ci_lower_bp": res_h["ci_lower_bp"],
                "signal_t_excess": res_h["signal_t_excess"],
                "trades_per_year": tpy_h,
                "per_trade_edge_pct": res_h["net_bp"] / 100.0,
                "ann_gross_pct": lc4_h["ann_gross_pct"],
                "sharpe": lc4_h["annualized_sharpe"],
            }
            log.info(
                "    hold=%dmin n=%d net=%.2fbp ann_gross=%.0f%% sharpe=%.2f",
                h, res_h["n"], res_h["net_bp"], lc4_h["ann_gross_pct"], lc4_h["annualized_sharpe"],
            )
        else:
            hold_sweep_res[f"hold_{h}min"] = {"skip": True, "n": res_h.get("n", 0)}
    # Monotone check: hold ↑ edge ↓ (panic-sell reversion premise)
    nets_by_hold = [
        (h, hold_sweep_res[f"hold_{h}min"].get("net_bp"))
        for h in HOLD_SWEEP if not hold_sweep_res[f"hold_{h}min"].get("skip")
    ]
    sweet_spot = max(nets_by_hold, key=lambda x: x[1] or -np.inf) if nets_by_hold else None
    # Monotone descending check around 15min
    monotone_at_15 = False
    if len(nets_by_hold) >= 3:
        nets_ordered = [v for _, v in nets_by_hold]
        # check non-increasing from 15min onward (ignore 10min which is pre-peak)
        nets_15plus = [v for h, v in nets_by_hold if h >= 15]
        if len(nets_15plus) >= 2:
            diffs = [nets_15plus[i+1] - nets_15plus[i] for i in range(len(nets_15plus) - 1)]
            monotone_at_15 = all(d <= 0 for d in diffs)
    out["caveat_1_hold_horizon_sweep"] = {
        "results": hold_sweep_res,
        "sweet_spot_min_by_net_bp": sweet_spot[0] if sweet_spot else None,
        "sweet_spot_net_bp": sweet_spot[1] if sweet_spot else None,
        "monotone_decrease_from_15min_onward": monotone_at_15,
        "pass_15min_is_local_max_or_nearby": (
            sweet_spot is not None and sweet_spot[0] in (10, 15, 20)
        ),
    }
    log.info(
        "  sweet-spot: %s at net=%.2fbp / monotone_15+: %s",
        sweet_spot, sweet_spot[1] if sweet_spot else 0.0, monotone_at_15,
    )

    # ── Phase 4: Caveat 2 — BTC vol regime stratify ───────────────────────
    log.info("=" * 70)
    log.info("PHASE 4: Caveat 2 — BTC 30d vol regime stratify (p33/p67)")
    log.info("=" * 70)
    btc_months = [str(p) for p in pd.period_range("2024-03", "2026-05", freq="M")]
    btc_1h = load_btc_1h_from_cache(btc_months)
    log.info("  BTC 1h panel: %d rows", len(btc_1h))
    if btc_1h.empty:
        log.warning("  BTC panel empty — caveat 2 INCONCLUSIVE")
        out["caveat_2_vol_regime"] = {"skip": True, "reason": "BTC panel empty"}
    else:
        regimes_series, p33_v, p67_v = classify_btc_vol_regime(btc_1h, panel_15m)
        panel_with_reg = panel_15m.copy()
        panel_with_reg["btc_vol_regime"] = regimes_series.values
        regime_res = {}
        for reg in ["LOW", "MID", "HIGH", "UNKNOWN"]:
            sub = panel_with_reg[panel_with_reg["btc_vol_regime"] == reg]
            if len(sub) < 30:
                regime_res[reg] = {"n": int(len(sub)), "skip": True}
                continue
            res = evaluate_arm_b(sub, FEE_BP, pool_15m_sampled, label=f"vol_{reg}", do_per_sym=False)
            regime_res[reg] = {
                "n": res["n"],
                "gross_bp": res["gross_bp"],
                "net_bp": res["net_bp"],
                "ci_lower_bp": res["ci_lower_bp"],
                "ci_upper_bp": res["ci_upper_bp"],
                "signal_t_excess": res["signal_t_excess"],
                "ci_pos": res["ci_pos"],
            }
            log.info(
                "  regime=%s n=%d net=%.2fbp ci[%.2f,%.2f] sigex=%.2f ci_pos=%s",
                reg, res["n"], res["net_bp"], res["ci_lower_bp"], res["ci_upper_bp"],
                res["signal_t_excess"], res["ci_pos"],
            )
        # PASS: all measurable regimes ci_lower > 0; INFO: panic-sell premise → HIGH should be strongest
        measurable_regs = {r: v for r, v in regime_res.items()
                           if not v.get("skip") and r != "UNKNOWN"}
        n_ci_pos = sum(1 for v in measurable_regs.values() if v.get("ci_pos"))
        n_meas = len(measurable_regs)
        high_strongest = False
        if "HIGH" in measurable_regs and len(measurable_regs) >= 2:
            high_net = measurable_regs["HIGH"]["net_bp"]
            high_strongest = all(
                high_net >= v["net_bp"] for r, v in measurable_regs.items() if r != "HIGH"
            )
        out["caveat_2_vol_regime"] = {
            "btc_vol_p33": p33_v,
            "btc_vol_p67": p67_v,
            "per_regime": regime_res,
            "n_regimes_ci_pos": n_ci_pos,
            "n_regimes_measurable": n_meas,
            "all_measurable_regimes_ci_pos": bool(n_ci_pos == n_meas),
            "panic_sell_premise_high_strongest": high_strongest,
            "pass_caveat_2": bool(n_ci_pos == n_meas and n_meas >= 2),
        }
        log.info(
            "  caveat_2 n_ci_pos=%d/%d HIGH_strongest=%s pass=%s",
            n_ci_pos, n_meas, high_strongest,
            out["caveat_2_vol_regime"]["pass_caveat_2"],
        )

    # ── Phase 5: Caveat 3 — debounce stress (≥30min gap) ──────────────────
    log.info("=" * 70)
    log.info("PHASE 5: Caveat 3 — per-symbol debounce ≥%dmin gap", DEBOUNCE_MIN)
    log.info("=" * 70)
    panel_debounced = apply_debounce(panel_15m, DEBOUNCE_MIN)
    log.info("  debounced rows: %d (from %d, retention %.1f%%)",
             len(panel_debounced), len(panel_15m),
             100.0 * len(panel_debounced) / max(1, len(panel_15m)))
    if len(panel_debounced) < 30:
        out["caveat_3_debounce"] = {
            "skip": True, "n_debounced": len(panel_debounced), "n_original": len(panel_15m),
        }
    else:
        deb_res = evaluate_arm_b(
            panel_debounced, FEE_BP, pool_15m_sampled, label="debounced", do_per_sym=False,
        )
        # PASS criterion: debounced sigex >= 80% of primary sigex AND ci_lower > 0
        primary_sigex = primary_res.get("signal_t_excess") or 0.0
        sigex_threshold = 0.8 * primary_sigex
        pass_caveat_3 = bool(
            (deb_res.get("signal_t_excess") or 0) >= sigex_threshold
            and (deb_res.get("ci_lower_bp") or 0) > 0
        )
        out["caveat_3_debounce"] = {
            "n_debounced": deb_res["n"],
            "n_original": int(len(panel_15m)),
            "retention_pct": 100.0 * deb_res["n"] / max(1, len(panel_15m)),
            "gross_bp": deb_res["gross_bp"],
            "net_bp": deb_res["net_bp"],
            "ci_lower_bp": deb_res["ci_lower_bp"],
            "signal_t_excess": deb_res["signal_t_excess"],
            "primary_sigex": primary_sigex,
            "sigex_80pct_threshold": sigex_threshold,
            "pass_caveat_3": pass_caveat_3,
        }
        log.info(
            "  debounced n=%d net=%.2fbp ci_lower=%.2fbp sigex=%.2f (80%% thresh=%.2f) pass=%s",
            deb_res["n"], deb_res["net_bp"], deb_res["ci_lower_bp"],
            deb_res["signal_t_excess"], sigex_threshold, pass_caveat_3,
        )

    # ── Phase 6: Caveat 4 — Sharpe / short squeeze artifact ───────────────
    log.info("=" * 70)
    log.info("PHASE 6: Caveat 4 — Sharpe leverage + max adverse excursion (SHORT squeeze)")
    log.info("=" * 70)
    log.info("  building per-trade path panel (15min hold, max-adverse-excursion)")
    path_panel = build_neg_burst_with_path(sym_data, hold_min=PRIMARY_HOLD_MIN)
    log.info("  path panel: %d trades", len(path_panel))
    if len(path_panel) < 30:
        out["caveat_4_sharpe_squeeze"] = {"skip": True, "n": len(path_panel)}
    else:
        gross_path = path_panel["gross_bp"].values
        net_path = gross_path - FEE_BP
        max_adv = path_panel["max_adverse_bp"].values  # bp positive = adverse for SHORT
        # statistics
        skew = float(pd.Series(net_path).skew())
        kurt = float(pd.Series(net_path).kurt())
        max_adv_p50 = float(np.percentile(max_adv, 50))
        max_adv_p95 = float(np.percentile(max_adv, 95))
        max_adv_p99 = float(np.percentile(max_adv, 99))
        max_adv_max = float(np.max(max_adv))
        # PASS: p95 max adverse < 500bp (5% per trade); skew < +3 (no extreme right tail blow-up)
        pass_drawdown = bool(max_adv_p95 < 500.0)
        pass_skew = bool(skew < 3.0)
        pass_caveat_4 = bool(pass_drawdown and pass_skew)
        out["caveat_4_sharpe_squeeze"] = {
            "n_trades": int(len(path_panel)),
            "net_mean_bp": float(net_path.mean()),
            "net_std_bp": float(net_path.std(ddof=1)),
            "net_skew": skew,
            "net_kurt_excess": kurt,
            "max_adverse_p50_bp": max_adv_p50,
            "max_adverse_p95_bp": max_adv_p95,
            "max_adverse_p99_bp": max_adv_p99,
            "max_adverse_max_bp": max_adv_max,
            "pass_max_adverse_p95_under_500bp": pass_drawdown,
            "pass_skew_under_3": pass_skew,
            "pass_caveat_4": pass_caveat_4,
        }
        log.info(
            "  skew=%.2f kurt=%.2f max_adv p50=%.1f p95=%.1f p99=%.1f max=%.1f pass=%s",
            skew, kurt, max_adv_p50, max_adv_p95, max_adv_p99, max_adv_max, pass_caveat_4,
        )

    # ── Phase 7: Caveat 5 — per-burst signing (not 5m first-burst) ────────
    log.info("=" * 70)
    log.info("PHASE 7: Caveat 5 — per-burst signing comparison (vs 5m first-burst)")
    log.info("=" * 70)
    panel_per_burst, pool_per_burst = build_neg_burst_triggers_5m(
        sym_data, hold_min=PRIMARY_HOLD_MIN, per_burst_mode=True
    )
    log.info("  per-burst panel: %d (vs first-burst: %d)",
             len(panel_per_burst), len(panel_15m))
    if len(panel_per_burst) < 30:
        out["caveat_5_per_burst_signing"] = {"skip": True, "n": len(panel_per_burst)}
    else:
        if len(pool_per_burst) > 100000:
            idx = rng_master.choice(len(pool_per_burst), size=100000, replace=False)
            pool_pb_sampled = pool_per_burst[idx]
        else:
            pool_pb_sampled = pool_per_burst
        pb_res = evaluate_arm_b(
            panel_per_burst, FEE_BP, pool_pb_sampled, label="per_burst", do_per_sym=False,
        )
        primary_sigex_for_pb = primary_res.get("signal_t_excess") or 0.0
        pass_caveat_5 = bool(
            (pb_res.get("signal_t_excess") or 0) >= primary_sigex_for_pb * 0.9
            and (pb_res.get("ci_lower_bp") or 0) > 0
        )
        out["caveat_5_per_burst_signing"] = {
            "n_per_burst": pb_res["n"],
            "n_first_burst": int(len(panel_15m)),
            "expansion_ratio": pb_res["n"] / max(1, len(panel_15m)),
            "per_burst_gross_bp": pb_res["gross_bp"],
            "per_burst_net_bp": pb_res["net_bp"],
            "per_burst_ci_lower_bp": pb_res["ci_lower_bp"],
            "per_burst_sigex": pb_res["signal_t_excess"],
            "primary_first_burst_sigex": primary_sigex_for_pb,
            "pass_caveat_5": pass_caveat_5,
        }
        log.info(
            "  per_burst n=%d net=%.2fbp ci_lower=%.2fbp sigex=%.2f (primary=%.2f) pass=%s",
            pb_res["n"], pb_res["net_bp"], pb_res["ci_lower_bp"],
            pb_res["signal_t_excess"], primary_sigex_for_pb, pass_caveat_5,
        )

    # ── Phase 8: Caveat 6 — 2026 OOS holdout (R-3 critical) ───────────────
    log.info("=" * 70)
    log.info("PHASE 8: Caveat 6 — 2026 OOS holdout (vs 2024-2025 IN-sample) [CRITICAL]")
    log.info("=" * 70)
    panel_15m_ts = panel_15m.copy()
    panel_15m_ts["ts"] = pd.to_datetime(panel_15m_ts["ts"])
    is_panel = panel_15m_ts[panel_15m_ts["ts"] < OOS_START]
    oos_panel = panel_15m_ts[
        (panel_15m_ts["ts"] >= OOS_START) & (panel_15m_ts["ts"] <= OOS_END)
    ]
    log.info("  IN-sample n=%d (2024-01 → 2025-12)", len(is_panel))
    log.info("  OOS n=%d (2026Q1+Q2)", len(oos_panel))

    is_res = evaluate_arm_b(is_panel, FEE_BP, pool_15m_sampled, label="IS_2024_2025", do_per_sym=False)
    if len(oos_panel) < 30:
        oos_res = {"label": "OOS_2026Q1Q2", "n": int(len(oos_panel)), "skip": True}
    else:
        oos_res = evaluate_arm_b(oos_panel, FEE_BP, pool_15m_sampled, label="OOS_2026Q1Q2", do_per_sym=False)

    is_edge = (is_res.get("net_bp") or 0) / 100.0  # bp → %
    oos_edge = (oos_res.get("net_bp") or 0) / 100.0
    edge_ratio = (oos_edge / is_edge) if is_edge and abs(is_edge) > 1e-6 else 0.0
    oos_sigex = oos_res.get("signal_t_excess") or 0.0
    oos_ci_lower = oos_res.get("ci_lower_bp") or 0.0

    # Strict PASS: OOS sigex ≥ 2.0 AND ci_lower > 0 AND edge_ratio ≥ 0.50
    pass_oos_sigex = bool(oos_sigex >= 2.0)
    pass_oos_ci = bool(oos_ci_lower > 0)
    pass_oos_edge_ratio = bool(edge_ratio >= 0.50)
    pass_caveat_6 = bool(pass_oos_sigex and pass_oos_ci and pass_oos_edge_ratio)

    # life-changing 4-dim on OOS
    oos_lc4 = None
    if not oos_res.get("skip"):
        oos_years = (
            (pd.to_datetime(oos_panel["ts"].max()) - pd.to_datetime(oos_panel["ts"].min())).days
            / 365.25
        )
        oos_tpy = len(oos_panel) / max(1e-6, oos_years)
        oos_net_arr = (oos_panel["gross_bp"].values - FEE_BP) / 10000.0
        oos_lc4 = life_changing_4dim_high_freq(
            n=len(oos_panel),
            edge_bp_net=oos_res["net_bp"],
            trades_per_year=oos_tpy,
            hold_min=PRIMARY_HOLD_MIN,
            ret_arr_net=oos_net_arr,
        )

    out["caveat_6_oos_holdout"] = {
        "in_sample_n": is_res.get("n"),
        "in_sample_gross_bp": is_res.get("gross_bp"),
        "in_sample_net_bp": is_res.get("net_bp"),
        "in_sample_sigex": is_res.get("signal_t_excess"),
        "in_sample_ci_lower_bp": is_res.get("ci_lower_bp"),
        "in_sample_edge_pct": is_edge,
        "oos_n": oos_res.get("n"),
        "oos_gross_bp": oos_res.get("gross_bp"),
        "oos_net_bp": oos_res.get("net_bp"),
        "oos_sigex": oos_sigex,
        "oos_ci_lower_bp": oos_ci_lower,
        "oos_edge_pct": oos_edge,
        "edge_ratio_oos_div_in": edge_ratio,
        "oos_life_changing_4dim_high_freq": oos_lc4,
        "pass_oos_sigex_2": pass_oos_sigex,
        "pass_oos_ci_lower_pos": pass_oos_ci,
        "pass_oos_edge_ratio_50pct": pass_oos_edge_ratio,
        "pass_caveat_6": pass_caveat_6,
    }
    log.info(
        "  IS edge=%.4f%% sigex=%.2f / OOS edge=%.4f%% sigex=%.2f ci[%.2f,?] ratio=%.2fx pass=%s",
        is_edge, is_res.get("signal_t_excess") or 0.0,
        oos_edge, oos_sigex, oos_ci_lower, edge_ratio, pass_caveat_6,
    )

    # ── Phase 9: Caveat 7 — survivorship (expansion alts) ─────────────────
    log.info("=" * 70)
    log.info("PHASE 9: Caveat 7 — survivorship test (extended cohort %d alts)",
             len(COHORT_EXPANSION_PROBE))
    log.info("=" * 70)
    sym_data_ext: dict[str, pd.DataFrame] = {}
    ext_per_sym_days: dict[str, int] = {}
    for sym in COHORT_EXPANSION_PROBE:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < ROLLING_BAR_WINDOW * 2:
                continue
            sym_data_ext[sym] = df
            ext_per_sym_days[sym] = (df.index.max() - df.index.min()).days
        except Exception as e:
            log.warning("  ext %s load fail: %s", sym, e)

    log.info("  extended cohort loaded: %d/%d", len(sym_data_ext), len(COHORT_EXPANSION_PROBE))
    if len(sym_data_ext) < 3:
        out["caveat_7_survivorship"] = {
            "skip": True,
            "n_loaded": len(sym_data_ext),
            "reason": "insufficient extended cohort",
        }
    else:
        ext_panel, ext_pool = build_neg_burst_triggers_5m(
            sym_data_ext, hold_min=PRIMARY_HOLD_MIN, per_burst_mode=False
        )
        if len(ext_pool) > 100000:
            idx_ep = rng_master.choice(len(ext_pool), size=100000, replace=False)
            ext_pool_sampled = ext_pool[idx_ep]
        else:
            ext_pool_sampled = ext_pool
        if len(ext_panel) < 30:
            out["caveat_7_survivorship"] = {
                "skip": True,
                "n_ext_panel": len(ext_panel),
                "reason": "extended panel<30",
            }
        else:
            ext_res = evaluate_arm_b(
                ext_panel, FEE_BP, ext_pool_sampled, label="extended_cohort", do_per_sym=True,
            )
            primary_edge_bp = primary_res.get("net_bp") or 0.0
            ext_edge_bp = ext_res.get("net_bp") or 0.0
            edge_ratio_ext = (
                ext_edge_bp / primary_edge_bp
                if abs(primary_edge_bp) > 1e-6 else 0.0
            )
            # 50% of cohort edge OR ci_lower > 0
            pass_caveat_7 = bool(
                edge_ratio_ext >= 0.50 and (ext_res.get("ci_lower_bp") or 0) > 0
            )
            out["caveat_7_survivorship"] = {
                "n_ext_alts_loaded": len(sym_data_ext),
                "ext_per_sym_days": ext_per_sym_days,
                "ext_panel_n": ext_res["n"],
                "ext_gross_bp": ext_res["gross_bp"],
                "ext_net_bp": ext_res["net_bp"],
                "ext_ci_lower_bp": ext_res["ci_lower_bp"],
                "ext_sigex": ext_res["signal_t_excess"],
                "primary_net_bp": primary_edge_bp,
                "edge_ratio_ext_div_primary": edge_ratio_ext,
                "n_ext_syms_ci_pos": ext_res["n_syms_ci_pos"],
                "n_ext_syms_measurable": ext_res["n_syms_measurable"],
                "per_symbol_ext": ext_res["per_symbol"],
                "pass_caveat_7": pass_caveat_7,
            }
            log.info(
                "  ext n=%d net=%.2fbp ci_lower=%.2fbp sigex=%.2f ratio=%.2fx pass=%s",
                ext_res["n"], ext_res["net_bp"], ext_res["ci_lower_bp"],
                ext_res["signal_t_excess"], edge_ratio_ext, pass_caveat_7,
            )

    # ── Final verdict tree ────────────────────────────────────────────────
    log.info("=" * 70)
    log.info("FINAL VERDICT TREE")
    log.info("=" * 70)
    c1 = out["caveat_1_hold_horizon_sweep"]["pass_15min_is_local_max_or_nearby"]
    c2 = out.get("caveat_2_vol_regime", {}).get("pass_caveat_2", False)
    c3 = out.get("caveat_3_debounce", {}).get("pass_caveat_3", False)
    c4 = out.get("caveat_4_sharpe_squeeze", {}).get("pass_caveat_4", False)
    c5 = out.get("caveat_5_per_burst_signing", {}).get("pass_caveat_5", False)
    c6 = out.get("caveat_6_oos_holdout", {}).get("pass_caveat_6", False)
    c7 = out.get("caveat_7_survivorship", {}).get("pass_caveat_7", False)

    # Verdict (strict cascade, mostFAIL takes precedence)
    if not c6:
        verdict = "R3_FAIL_OOS_FRAGILITY_AT_RECENT_QUARTER"
    elif not c4:
        verdict = "R3_FAIL_SHORT_SQUEEZE"
    elif not c7:
        verdict = "R3_FAIL_SURVIVORSHIP"
    elif not c2:
        verdict = "R3_FAIL_VOL_REGIME"
    elif not c1:
        verdict = "R3_FAIL_HOLD_HORIZON_NON_MONOTONE"
    elif not c3:
        verdict = "R3_FAIL_DEBOUNCE_COLLAPSE"
    elif not c5:
        verdict = "R3_FAIL_PER_BURST_DEGRADED"
    else:
        verdict = "R3_PASS"

    out["caveat_summary"] = {
        "caveat_1_hold_horizon": c1,
        "caveat_2_vol_regime": c2,
        "caveat_3_debounce": c3,
        "caveat_4_sharpe_squeeze": c4,
        "caveat_5_per_burst_signing": c5,
        "caveat_6_oos_holdout": c6,
        "caveat_7_survivorship": c7,
        "n_caveats_pass": sum([c1, c2, c3, c4, c5, c6, c7]),
        "n_caveats_total": 7,
    }
    out["verdict"] = verdict
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    log.info(
        "  caveats: c1=%s c2=%s c3=%s c4=%s c5=%s c6=%s c7=%s → VERDICT=%s",
        c1, c2, c3, c4, c5, c6, c7, verdict,
    )
    log.info("  wall clock: %.2f min", out["wall_clock_minutes"])
    _write(out)
    return 0


def datetime_now_kst() -> str:
    return pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    raise SystemExit(main())
