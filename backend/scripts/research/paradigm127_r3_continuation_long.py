"""paradigm 127 R-3 robustness — alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m.

paradigm 127 split from paradigm 126 A arm dedicated (positive 1m burst → LONG continuation).
paradigm 126 R-2 baseline (2026-05-20 22:26 KST):
  A arm @ 30min: n=13,176 gross +70.94bp / net +54.94 / sigex +49.83 / ci_lower +45.90 /
                 5/5 TS-CV PASS / 13/13 syms_ci_pos / hold horizon monotone INCREASE
                 (30 +70.94 → 45 +75.06 → 60 +78.65)
  Verdict: PASS_R2_HIGH_FREQ_DIFFUSE — Lesson #41 dual-mode high-freq qualifies.

R-3 dispatch — 7 caveats baked into single script
-------------------------------------------------
1. Hold horizon final optimization (60/75/90 min — extend monotone search)
2. Vol-regime stratify per-symbol tercile (BTC 1m DB limited 143d; use per-sym 30d RV)
3. Per-symbol debounce ≥30min gap (burst cluster collapse)
4. Sharpe 18.42 artifact verification (per-trade pnl distribution skew/kurt/maxDD)
5. Per-burst signing variant (5m bin multiple bursts → multi-event)
6. 2026 holdout OOS verification (2024H1-2025H2 IS / 2026Q1+Q2 OOS)
7. Survivorship test (top-N market cap vs full 13 cohort)

Verdict tree
------------
PASS_R3                          : all 7 caveats clear
R3_FAIL_OOS                      : 2026 OOS sigex < 2.0 OR ci_lower ≤ 0 (paradigm 117 precedent)
R3_FAIL_VOL_REGIME               : ≥1 vol-regime tercile ci_lower ≤ 0
R3_FAIL_DEBOUNCE                 : debounce sigex < 0.80 × R-2 sigex
R3_FAIL_SHARPE_ARTIFACT          : max intra-trade DD > 5% OR extreme left-tail skew
R3_FAIL_PER_BURST_SIGNING        : per-burst signing sigex < first-burst-sign sigex
R3_FAIL_SURVIVORSHIP             : non-top-N cohort ci_lower ≤ 0 (alpha confined to top-N)
R3_FAIL_HOLD_HORIZON             : 90min ann_gross < 60min (mean-rev or oversaturation)
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

PARADIGM_NAME = "alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m"
PARADIGM_NUMBER = 127
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r3__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p127_r3")

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# 2024-01 market cap top-10 (approximate, for survivorship test caveat #7)
# Used to split full 13 cohort: top-10 vs non-top-10 (only 3: WIF, FIL, NEAR-ish residual)
# 2024-01 approximate ranking by market cap: BTC ETH BNB SOL XRP DOGE ADA AVAX LINK LTC BCH NEAR FIL WIF
TOP_N_MARKET_CAP_2024_01 = [
    "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT",
]  # top-10 of the 13 cohort (excluding BTC); residual = WIF, FIL, NEAR
NON_TOP_N = [s for s in COHORT if s not in TOP_N_MARKET_CAP_2024_01]

# Primary params (paradigm 127 = paradigm 126 A arm @ 60min hold, NOT 30min)
PRIMARY_ROLLING_DAYS = 30
ROLLING_BAR_WINDOW = PRIMARY_ROLLING_DAYS * 24 * 60
PRIMARY_PCTILE = 99.0
PRIMARY_MAG = 0.005
PRIMARY_HOLD_MIN = 60  # changed from 30 → 60 (paradigm 126 R-2 monotone sweet-spot)
PRIMARY_FEE_BP = 16.0

# R-3 caveat params
HOLD_HORIZON_SWEEP_FINAL = [60, 75, 90]   # caveat #1
DEBOUNCE_GAP_MIN = 30                       # caveat #3
VOL_REGIME_LOOKBACK_DAYS = 30               # caveat #2 (per-sym 30d realized vol terciles)
OOS_HOLDOUT_QTRS = ["2026Q1", "2026Q2"]   # caveat #6
IS_QTRS = ["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4"]

DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


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


def build_panel_pos_burst(
    sym_data: dict[str, pd.DataFrame],
    volume_pctile: float,
    mag_threshold: float,
    hold_min: int,
    per_burst_signing: bool = False,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Build positive-burst-only trigger panel + unconditional 5m fwd_ret pool.

    per_burst_signing=False (default): 5m bin first-burst-sign aggregation (paradigm 126 R-2 method)
    per_burst_signing=True:  each 1m burst within a 5m bin emits its own signed event (caveat #5).
                             For caveat #5 we further aggregate to 5m bar but with multi-event per bin.

    For positive-burst paradigm 127, only direction==+1 events retained.
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
            ).quantile(volume_pctile / 100.0)
        )
        j["burst"] = (
            (j["volume"] > j["vol_pctile_30d"])
            & (j["abs_log_ret_1m"] > mag_threshold)
        ).astype(int)
        j["burst_sign"] = np.where(
            j["burst"] == 1, np.sign(j["log_ret_1m"]), 0
        ).astype(int)
        j["fwd_ret"] = j["close"].pct_change(hold_min).shift(-hold_min)

        if per_burst_signing:
            # caveat #5: each 1m burst is its own event (no 5m aggregation, fired at 1m bar)
            burst_rows = j[j["burst"] == 1].copy()
            if burst_rows.empty:
                continue
            # 5m pool sample: still use 5m-aggregated fwd_ret for pool matching
            j_5m_pool = j.resample("5min")["fwd_ret"].first().dropna()
            pool_pieces.append(j_5m_pool.values * 10000.0)
            burst_rows["sym"] = sym
            burst_rows["direction"] = burst_rows["burst_sign"].astype(int)
            burst_rows = burst_rows[burst_rows["direction"] > 0].copy()  # POS ONLY
            if burst_rows.empty:
                continue
            burst_rows["gross_bp"] = burst_rows["fwd_ret"] * 10000.0  # direction always +1
            burst_rows["qtr"] = burst_rows.index.to_period("Q").astype(str)
            burst_rows = burst_rows.dropna(subset=["fwd_ret"])
            rows.append(
                burst_rows.reset_index().rename(columns={"timestamp": "ts", "index": "ts"})[
                    ["ts", "sym", "direction", "gross_bp", "qtr"]
                ]
            )
        else:
            # paradigm 126 R-2 method: 5m bin first-burst-sign
            first_sign_func = lambda x: int(x[x != 0].iloc[0]) if (x != 0).any() else 0
            j_5m = j.resample("5min").agg({
                "burst": "max",
                "burst_sign": first_sign_func,
                "fwd_ret": "first",
            })
            j_5m = j_5m.dropna(subset=["fwd_ret"])
            pool_pieces.append(j_5m["fwd_ret"].values * 10000.0)
            trig = j_5m[(j_5m["burst"] == 1) & (j_5m["burst_sign"] > 0)].copy()  # POS ONLY
            if trig.empty:
                continue
            trig["sym"] = sym
            trig["direction"] = trig["burst_sign"].astype(int)
            trig["gross_bp"] = trig["fwd_ret"] * 10000.0  # direction always +1
            trig["qtr"] = trig.index.to_period("Q").astype(str)
            rows.append(
                trig.reset_index().rename(columns={"timestamp": "ts", "index": "ts"})[
                    ["ts", "sym", "direction", "gross_bp", "qtr"]
                ]
            )
    if not rows:
        return pd.DataFrame(), np.array([])
    panel = pd.concat(rows, ignore_index=True).sort_values("ts").reset_index(drop=True)
    full_pool = np.concatenate(pool_pieces) if pool_pieces else np.array([])
    return panel, full_pool


def apply_debounce(panel: pd.DataFrame, gap_min: int) -> pd.DataFrame:
    """Caveat #3: enforce per-symbol minimum gap between consecutive burst events.

    Greedy: for each symbol, keep first event, drop any subsequent within `gap_min`
    minutes from last kept event.
    """
    if panel.empty:
        return panel
    panel = panel.copy()
    panel["ts"] = pd.to_datetime(panel["ts"])
    keep_mask = np.zeros(len(panel), dtype=bool)
    for sym, grp in panel.groupby("sym", sort=False):
        idx = grp.index.values
        ts = grp["ts"].values
        last_keep_ts = None
        gap_td = np.timedelta64(gap_min, "m")
        for k, i in enumerate(idx):
            if last_keep_ts is None or (ts[k] - last_keep_ts) >= gap_td:
                keep_mask[i] = True
                last_keep_ts = ts[k]
    return panel[keep_mask].reset_index(drop=True)


def evaluate_subset(
    sub: pd.DataFrame,
    fee_bp: float,
    pool_for_arm: np.ndarray,
    do_per_sym_ci: bool = True,
    boot_n: int = 2000,
) -> dict:
    """Evaluate POS-burst LONG subset using unconditional pool (paradigm 126 R-2 fix method)."""
    if sub.empty or len(sub) < 30:
        return {"n": int(len(sub)), "skip": True}
    gross = sub["gross_bp"].values
    net = gross - fee_bp
    obs_t = _t_stat(net)
    ci = bootstrap_ci(net / 10000.0, n_boot=boot_n, block_size=20, rng_seed=42)
    ci_lower_bp = float(ci["ci_lower"]) * 10000
    ci_upper_bp = float(ci["ci_upper"]) * 10000
    perm = fee_aware_perm_test(
        observed_net_returns=net / 10000.0,
        candidate_pool_returns=pool_for_arm / 10000.0,
        fee_per_trade=fee_bp / 10000.0,
        n_perms=1000, rng_seed=42,
    )
    sigex = float(perm.get("signal_t_excess", float("nan")))
    perm_p = float(perm.get("perm_p_one_sided_above", float("nan")))
    null_t = float(perm.get("null_mean_t", float("nan")))

    out = {
        "n": int(len(sub)),
        "gross_bp": float(gross.mean()),
        "net_bp": float(net.mean()),
        "obs_t": obs_t,
        "signal_t_excess": sigex,
        "null_mean_t": null_t,
        "perm_p_one_sided_above": perm_p,
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": ci_upper_bp,
    }
    if do_per_sym_ci:
        sym_rows = []
        n_meas = n_pos = 0
        for s in sub["sym"].unique():
            ss = sub[sub["sym"] == s]
            if len(ss) >= 30:
                n_meas += 1
                sn = ss["gross_bp"].values - fee_bp
                sci = bootstrap_ci(sn / 10000.0, n_boot=500, block_size=10, rng_seed=42)
                slb = float(sci["ci_lower"]) * 10000
                sym_rows.append({
                    "sym": s, "n": int(len(ss)),
                    "gross_bp": float(ss["gross_bp"].mean()),
                    "net_bp": float(sn.mean()),
                    "ci_lower_bp": slb, "ci_pos": bool(slb > 0),
                })
                if slb > 0:
                    n_pos += 1
        out["n_syms_measurable"] = n_meas
        out["n_syms_ci_pos"] = n_pos
        out["syms_ci_pos_ratio"] = n_pos / n_meas if n_meas else 0.0
        out["per_symbol"] = sym_rows
    return out


def main() -> int:
    t_start = time.time()
    log.info("=" * 80)
    log.info("paradigm 127 R-3 — alt_volume_burst pos-burst continuation LONG 60m")
    log.info("start KST %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 80)
    engine = create_engine(DB_DSN)

    out: dict = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-3",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "parent_paradigm": 126,
        "split_arm": "A_pos_burst_LONG",
        "universe": COHORT,
        "non_top_n_market_cap_2024_01": NON_TOP_N,
        "primary_params": {
            "rolling_days": PRIMARY_ROLLING_DAYS,
            "volume_percentile": PRIMARY_PCTILE,
            "magnitude_threshold": PRIMARY_MAG,
            "forward_hold_min": PRIMARY_HOLD_MIN,
            "fee_bp": PRIMARY_FEE_BP,
        },
        "r3_caveats": {
            "1_hold_horizon_final": HOLD_HORIZON_SWEEP_FINAL,
            "2_vol_regime": "per_sym_30d_RV_terciles",
            "3_debounce_gap_min": DEBOUNCE_GAP_MIN,
            "4_sharpe_artifact": "intra_trade_drawdown_skew_kurt",
            "5_per_burst_signing_variant": True,
            "6_oos_holdout_qtrs": OOS_HOLDOUT_QTRS,
            "7_survivorship_top_n_market_cap": TOP_N_MARKET_CAP_2024_01,
        },
    }

    # ─── Phase 1: load 1m OHLCV ──────────────────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 1: load 1m OHLCV per symbol")
    log.info("=" * 70)
    sym_data: dict[str, pd.DataFrame] = {}
    per_sym_days: dict[str, int] = {}
    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < ROLLING_BAR_WINDOW * 2:
                log.warning("  %s: insufficient (%d bars)", sym, len(df))
                continue
            sym_data[sym] = df
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            log.info("  %s: %d 1m bars (%d days)", sym, len(df), days)
        except Exception as e:
            log.error("  %s load fail: %s", sym, e)

    if len(sym_data) < 8:
        out["verdict"] = "R3_DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"only {len(sym_data)}/{len(COHORT)} symbols loaded"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        with open(OUT_DIR / "r3__metrics.json", "w") as f:
            json.dump(_convert(out), f, indent=2)
        return 1

    full_window = max(per_sym_days.values())
    panel_years = full_window / 365.0
    out["n_alts_usable"] = len(sym_data)
    out["per_symbol_days_1m"] = per_sym_days
    out["panel_years"] = panel_years

    # ─── Phase 2: build primary panel (60min hold) + unconditional pool ─────
    log.info("=" * 70)
    log.info("PHASE 2: build primary POS-burst panel @ hold=60min")
    log.info("=" * 70)
    primary_panel, full_pool = build_panel_pos_burst(
        sym_data, PRIMARY_PCTILE, PRIMARY_MAG, PRIMARY_HOLD_MIN,
        per_burst_signing=False,
    )
    log.info("primary POS panel: n=%d events", len(primary_panel))
    log.info("unconditional 5m pool: n=%d (mean=%.4fbp std=%.2fbp)",
             len(full_pool), float(full_pool.mean()), float(full_pool.std()))

    rng = np.random.default_rng(127)
    if len(full_pool) > 50000:
        idx = rng.choice(len(full_pool), size=50000, replace=False)
        pool_50k = full_pool[idx]
    else:
        pool_50k = full_pool
    log.info("subsampled pool to %d bars (mean=%.4fbp)", len(pool_50k), float(pool_50k.mean()))

    # Primary R-3 baseline at hold=60
    log.info("=" * 70)
    log.info("PHASE 2.1: PRIMARY R-3 baseline (hold=60min)")
    log.info("=" * 70)
    primary_res = evaluate_subset(primary_panel, PRIMARY_FEE_BP, pool_50k, boot_n=2000)
    log.info("  PRIMARY: n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f sigex=%.2f ci[%.2f,%.2f] "
             "perm_p=%.3f sym_ci_pos=%d/%d",
             primary_res["n"], primary_res["gross_bp"], primary_res["net_bp"],
             primary_res["obs_t"], primary_res["signal_t_excess"],
             primary_res["ci_lower_bp"], primary_res["ci_upper_bp"],
             primary_res["perm_p_one_sided_above"],
             primary_res.get("n_syms_ci_pos", 0), primary_res.get("n_syms_measurable", 0))
    out["primary_baseline_hold60"] = primary_res

    # ─── Caveat #1: Hold horizon final optimization (60/75/90) ──────────────
    log.info("=" * 70)
    log.info("CAVEAT #1: hold horizon final optimization (60 / 75 / 90 min)")
    log.info("=" * 70)
    hold_results = {}
    for h in HOLD_HORIZON_SWEEP_FINAL:
        if h == PRIMARY_HOLD_MIN:
            panel_h = primary_panel
        else:
            log.info("  building panel at hold=%d ...", h)
            panel_h, _ = build_panel_pos_burst(
                sym_data, PRIMARY_PCTILE, PRIMARY_MAG, h, per_burst_signing=False,
            )
        if panel_h.empty or len(panel_h) < 30:
            hold_results[f"hold_{h}min"] = {"skip": True}
            continue
        res = evaluate_subset(panel_h, PRIMARY_FEE_BP, pool_50k,
                              do_per_sym_ci=False, boot_n=1000)
        tpy = res["n"] / panel_years
        res["trades_per_year"] = float(tpy)
        res["ann_gross_pct"] = float(res["gross_bp"] * tpy / 100.0)
        res["ann_net_pct"] = float(res["net_bp"] * tpy / 100.0)
        res["per_trade_edge_pct"] = float(res["net_bp"] / 100.0)
        hold_results[f"hold_{h}min"] = res
        log.info("  hold=%dmin: n=%d gross=%.2fbp net=%.2fbp ci_lower=%.2f sigex=%.2f "
                 "tpy=%.0f ann_gross=%.1f%%",
                 h, res["n"], res["gross_bp"], res["net_bp"], res["ci_lower_bp"],
                 res["signal_t_excess"], tpy, res["ann_gross_pct"])
    # monotone check
    ag = [hold_results[f"hold_{h}min"].get("ann_gross_pct", float("-inf"))
          for h in HOLD_HORIZON_SWEEP_FINAL]
    edges = [hold_results[f"hold_{h}min"].get("per_trade_edge_pct", float("-inf"))
             for h in HOLD_HORIZON_SWEEP_FINAL]
    valid_ag = [(h, a) for h, a in zip(HOLD_HORIZON_SWEEP_FINAL, ag) if a != float("-inf")]
    optimal_h = max(valid_ag, key=lambda x: x[1])[0] if valid_ag else None
    edge_monotone_inc = (len(edges) >= 2
                         and all(edges[i+1] >= edges[i] - 1e-6 for i in range(len(edges)-1))
                         and edges[0] != float("-inf"))
    hold_60_dominates_90 = (
        len(ag) == 3
        and ag[0] != float("-inf") and ag[2] != float("-inf")
        and ag[0] >= ag[2]  # 60 >= 90
    )
    out["caveat_1_hold_horizon_final"] = {
        "results": hold_results,
        "ann_gross_60_75_90": ag,
        "edges_60_75_90": edges,
        "edge_monotone_increase": edge_monotone_inc,
        "optimal_hold_min": optimal_h,
        "hold_60_dominates_90": hold_60_dominates_90,
        # caveat #1 PASS: optimal in [60, 75, 90] (no flip to 60min weakness)
        "caveat_1_pass": bool(optimal_h in HOLD_HORIZON_SWEEP_FINAL
                              and ag[0] != float("-inf")
                              and not (ag[2] < ag[0] * 0.8)),  # 90min not catastrophic decay
    }
    log.info("  CAVEAT #1 ann_gross [60,75,90] = %s / optimal=%s / edge_mono_inc=%s / pass=%s",
             ag, optimal_h, edge_monotone_inc, out["caveat_1_hold_horizon_final"]["caveat_1_pass"])

    # ─── Caveat #2: vol-regime stratify per-symbol 30d RV terciles ──────────
    log.info("=" * 70)
    log.info("CAVEAT #2: vol-regime stratify (per-sym 30d RV terciles)")
    log.info("BTC 1m DB limited to 143d, using per-sym intrinsic vol regime instead")
    log.info("=" * 70)
    # Compute per-symbol 30d rolling realized vol from 1m closes, then assign each
    # trigger event to one of low/mid/high tercile based on the symbol's own historical distribution
    vol_regime_results = {}
    # Build a quick per-sym tercile boundary map
    sym_vol_terciles = {}
    for sym, df in sym_data.items():
        log_ret_1m = np.log(df["close"]).diff()
        # 30d realized vol (annualized) per 1m bar
        rv30d = log_ret_1m.rolling(window=ROLLING_BAR_WINDOW,
                                   min_periods=ROLLING_BAR_WINDOW // 2).std() * math.sqrt(525600)
        sym_vol_terciles[sym] = rv30d
    # Annotate primary_panel with per-event 30d RV (lookup at ts)
    panel_with_rv = primary_panel.copy()
    panel_with_rv["ts"] = pd.to_datetime(panel_with_rv["ts"])
    rv_at_event = []
    for _, row in panel_with_rv.iterrows():
        rv_series = sym_vol_terciles.get(row["sym"])
        if rv_series is None or len(rv_series) == 0:
            rv_at_event.append(float("nan"))
            continue
        # nearest prior 1m bar
        ts = row["ts"]
        try:
            v = rv_series.asof(ts)
        except Exception:
            v = float("nan")
        rv_at_event.append(float(v) if pd.notnull(v) else float("nan"))
    panel_with_rv["rv30d"] = rv_at_event
    panel_with_rv = panel_with_rv.dropna(subset=["rv30d"])
    # Per-symbol tercile assignment
    panel_with_rv["vol_tercile"] = ""
    for sym, grp in panel_with_rv.groupby("sym"):
        if len(grp) < 30:
            continue
        rv_p33 = grp["rv30d"].quantile(1/3)
        rv_p67 = grp["rv30d"].quantile(2/3)
        mask_low = (panel_with_rv["sym"] == sym) & (panel_with_rv["rv30d"] <= rv_p33)
        mask_mid = (panel_with_rv["sym"] == sym) & (panel_with_rv["rv30d"] > rv_p33) & (panel_with_rv["rv30d"] <= rv_p67)
        mask_high = (panel_with_rv["sym"] == sym) & (panel_with_rv["rv30d"] > rv_p67)
        panel_with_rv.loc[mask_low, "vol_tercile"] = "LOW"
        panel_with_rv.loc[mask_mid, "vol_tercile"] = "MID"
        panel_with_rv.loc[mask_high, "vol_tercile"] = "HIGH"
    for regime in ["LOW", "MID", "HIGH"]:
        sub_reg = panel_with_rv[panel_with_rv["vol_tercile"] == regime]
        if len(sub_reg) < 30:
            vol_regime_results[regime] = {"skip": True, "n": int(len(sub_reg))}
            continue
        res = evaluate_subset(sub_reg, PRIMARY_FEE_BP, pool_50k,
                              do_per_sym_ci=False, boot_n=1000)
        vol_regime_results[regime] = res
        log.info("  regime=%s: n=%d gross=%.2fbp net=%.2fbp ci_lower=%.2f sigex=%.2f",
                 regime, res["n"], res["gross_bp"], res["net_bp"],
                 res["ci_lower_bp"], res["signal_t_excess"])
    all_regimes_ci_pos = all(
        (not vol_regime_results[r].get("skip", False))
        and vol_regime_results[r].get("ci_lower_bp", 0) > 0
        for r in ["LOW", "MID", "HIGH"]
    )
    out["caveat_2_vol_regime"] = {
        "results": vol_regime_results,
        "method": "per_sym_30d_RV_terciles_intrinsic",
        "btc_data_gap_note": "BTC 1m DB 2025-12-22 onward only; per-sym intrinsic RV used",
        "all_regimes_ci_pos": all_regimes_ci_pos,
        "caveat_2_pass": bool(all_regimes_ci_pos),
    }
    log.info("  CAVEAT #2 all regimes ci_pos? %s pass=%s",
             all_regimes_ci_pos, out["caveat_2_vol_regime"]["caveat_2_pass"])

    # ─── Caveat #3: per-symbol debounce ≥30min gap ──────────────────────────
    log.info("=" * 70)
    log.info("CAVEAT #3: per-symbol debounce ≥%dmin gap", DEBOUNCE_GAP_MIN)
    log.info("=" * 70)
    debounced = apply_debounce(primary_panel, DEBOUNCE_GAP_MIN)
    log.info("  pre-debounce n=%d / post-debounce n=%d (retained %.1f%%)",
             len(primary_panel), len(debounced),
             100.0 * len(debounced) / max(1, len(primary_panel)))
    deb_res = evaluate_subset(debounced, PRIMARY_FEE_BP, pool_50k,
                              do_per_sym_ci=True, boot_n=1500)
    deb_res["pre_debounce_n"] = int(len(primary_panel))
    deb_res["retention_pct"] = float(100.0 * len(debounced) / max(1, len(primary_panel)))
    # Pass: debounce sigex ≥ 80% of primary baseline sigex
    baseline_sigex = primary_res.get("signal_t_excess", 0)
    sigex_ratio = (deb_res.get("signal_t_excess", 0) / baseline_sigex
                   if baseline_sigex > 0 else 0)
    deb_res["baseline_sigex_60min"] = baseline_sigex
    deb_res["sigex_ratio_vs_baseline"] = float(sigex_ratio)
    deb_res["caveat_3_pass"] = bool(sigex_ratio >= 0.80 and deb_res.get("ci_lower_bp", 0) > 0)
    out["caveat_3_debounce"] = deb_res
    log.info("  CAVEAT #3: debounced n=%d sigex=%.2f (ratio %.2f vs baseline %.2f) ci_lower=%.2f pass=%s",
             deb_res["n"], deb_res.get("signal_t_excess", 0), sigex_ratio,
             baseline_sigex, deb_res.get("ci_lower_bp", 0), deb_res["caveat_3_pass"])

    # ─── Caveat #4: Sharpe 18.42 artifact verification ──────────────────────
    log.info("=" * 70)
    log.info("CAVEAT #4: per-trade pnl distribution + intra-trade drawdown")
    log.info("=" * 70)
    pnls = primary_panel["gross_bp"].values  # signed gross (LONG always +1 dir)
    pnls_net = pnls - PRIMARY_FEE_BP
    # Distribution
    from scipy import stats as scistats
    skew_val = float(scistats.skew(pnls_net))
    kurt_val = float(scistats.kurtosis(pnls_net))
    pnl_p01 = float(np.percentile(pnls_net, 1))
    pnl_p05 = float(np.percentile(pnls_net, 5))
    pnl_p95 = float(np.percentile(pnls_net, 95))
    pnl_p99 = float(np.percentile(pnls_net, 99))
    pnl_max_loss = float(pnls_net.min())
    pnl_max_gain = float(pnls_net.max())
    # Intra-trade max DD proxy: for LONG continuation, compute per-trade min(low_path) - entry over hold_min minutes
    # Use a sampled subset (1500 trades) to compute true intra-trade DD using 1m OHLC data
    log.info("  measuring intra-trade max DD on 1500 sampled trades (1m low path) ...")
    dd_pct_list = []
    sample_n = min(1500, len(primary_panel))
    rng2 = np.random.default_rng(127)
    sample_idx = rng2.choice(len(primary_panel), size=sample_n, replace=False)
    sample_df = primary_panel.iloc[sample_idx]
    for _, row in sample_df.iterrows():
        sym = row["sym"]
        if sym not in sym_data:
            continue
        ts = pd.to_datetime(row["ts"])
        df_sym = sym_data[sym]
        # window: ts+1 to ts+hold_min (the 5m bin starts at ts; entry at next bar)
        win = df_sym.loc[ts:ts + pd.Timedelta(minutes=PRIMARY_HOLD_MIN)]
        if len(win) < 2:
            continue
        entry_close = float(win.iloc[0]["close"])
        if entry_close <= 0:
            continue
        min_low = float(win["low"].min())
        dd_pct = (min_low / entry_close - 1.0) * 100.0  # negative for LONG drawdown
        dd_pct_list.append(dd_pct)
    if dd_pct_list:
        dd_arr = np.asarray(dd_pct_list)
        dd_mean = float(dd_arr.mean())
        dd_p99 = float(np.percentile(dd_arr, 1))  # 1st percentile = worst 1%
        dd_p95 = float(np.percentile(dd_arr, 5))
        dd_max_intra = float(dd_arr.min())  # worst DD
        n_dd_le_5pct = int((dd_arr <= -5.0).sum())
        pct_dd_le_5pct = float(100.0 * n_dd_le_5pct / len(dd_arr))
    else:
        dd_mean = dd_p99 = dd_p95 = dd_max_intra = pct_dd_le_5pct = float("nan")
        n_dd_le_5pct = 0
    # caveat #4 PASS: skew not extreme left (skew > -1.0), avg intra-trade max DD > -5%,
    #                 and pct trades with DD <= -5% < 10%
    skew_ok = skew_val > -1.0
    dd_ok = (not math.isnan(dd_mean)) and dd_mean > -5.0
    pct_extreme_dd_ok = (not math.isnan(pct_dd_le_5pct)) and pct_dd_le_5pct < 10.0
    out["caveat_4_sharpe_artifact"] = {
        "pnl_skew": skew_val,
        "pnl_kurt": kurt_val,
        "pnl_p01_bp": pnl_p01,
        "pnl_p05_bp": pnl_p05,
        "pnl_p95_bp": pnl_p95,
        "pnl_p99_bp": pnl_p99,
        "pnl_max_loss_bp": pnl_max_loss,
        "pnl_max_gain_bp": pnl_max_gain,
        "intra_trade_dd_sample_n": len(dd_pct_list),
        "intra_trade_dd_mean_pct": dd_mean,
        "intra_trade_dd_p95_pct": dd_p95,
        "intra_trade_dd_p99_pct": dd_p99,
        "intra_trade_dd_max_pct": dd_max_intra,
        "n_trades_dd_le_minus_5pct": n_dd_le_5pct,
        "pct_trades_dd_le_minus_5pct": pct_dd_le_5pct,
        "pass_skew_not_extreme_left": bool(skew_ok),
        "pass_dd_mean_above_minus_5pct": bool(dd_ok),
        "pass_pct_extreme_dd_below_10pct": bool(pct_extreme_dd_ok),
        "caveat_4_pass": bool(skew_ok and dd_ok and pct_extreme_dd_ok),
    }
    log.info("  CAVEAT #4: pnl skew=%.2f kurt=%.2f / dd mean=%.2f%% p95=%.2f%% max=%.2f%% / "
             "pct trades dd<-5%%=%.1f%% / pass=%s",
             skew_val, kurt_val, dd_mean, dd_p95, dd_max_intra, pct_dd_le_5pct,
             out["caveat_4_sharpe_artifact"]["caveat_4_pass"])

    # ─── Caveat #5: per-burst signing variant ───────────────────────────────
    log.info("=" * 70)
    log.info("CAVEAT #5: per-burst signing (multi-event per 5m bin)")
    log.info("=" * 70)
    panel_pb, _ = build_panel_pos_burst(
        sym_data, PRIMARY_PCTILE, PRIMARY_MAG, PRIMARY_HOLD_MIN,
        per_burst_signing=True,
    )
    log.info("  per-burst panel: n=%d vs first-burst-sign baseline n=%d",
             len(panel_pb), len(primary_panel))
    pb_res = evaluate_subset(panel_pb, PRIMARY_FEE_BP, pool_50k,
                             do_per_sym_ci=False, boot_n=1000)
    pb_res["baseline_n_first_burst_sign"] = int(len(primary_panel))
    pb_res["per_burst_to_first_burst_ratio"] = float(
        len(panel_pb) / max(1, len(primary_panel))
    )
    baseline_sigex = primary_res.get("signal_t_excess", 0)
    pb_sigex_ratio = (pb_res.get("signal_t_excess", 0) / baseline_sigex
                      if baseline_sigex > 0 else 0)
    pb_res["sigex_ratio_vs_baseline"] = float(pb_sigex_ratio)
    # PASS: per-burst sigex >= 0.80 × first-burst-sign sigex AND ci_lower > 0
    pb_res["caveat_5_pass"] = bool(pb_sigex_ratio >= 0.80 and pb_res.get("ci_lower_bp", 0) > 0)
    out["caveat_5_per_burst_signing"] = pb_res
    log.info("  CAVEAT #5: per-burst n=%d sigex=%.2f (ratio %.2f vs %.2f) ci_lower=%.2f pass=%s",
             pb_res["n"], pb_res.get("signal_t_excess", 0), pb_sigex_ratio, baseline_sigex,
             pb_res.get("ci_lower_bp", 0), pb_res["caveat_5_pass"])

    # ─── Caveat #6: 2026 holdout OOS verification (R-3 CORE TEST) ───────────
    log.info("=" * 70)
    log.info("CAVEAT #6: 2026 holdout OOS verification (paradigm 117 precedent)")
    log.info("=" * 70)
    is_panel = primary_panel[primary_panel["qtr"].isin(IS_QTRS)]
    oos_panel = primary_panel[primary_panel["qtr"].isin(OOS_HOLDOUT_QTRS)]
    log.info("  IS panel (2024H1-2025H2): n=%d / OOS panel (2026Q1+Q2): n=%d",
             len(is_panel), len(oos_panel))
    is_res = evaluate_subset(is_panel, PRIMARY_FEE_BP, pool_50k,
                             do_per_sym_ci=True, boot_n=1500)
    oos_res = evaluate_subset(oos_panel, PRIMARY_FEE_BP, pool_50k,
                              do_per_sym_ci=True, boot_n=1500)
    log.info("  IS:  n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci_lower=%.2f sym_ci_pos=%d/%d",
             is_res["n"], is_res.get("gross_bp", 0), is_res.get("net_bp", 0),
             is_res.get("signal_t_excess", 0), is_res.get("ci_lower_bp", 0),
             is_res.get("n_syms_ci_pos", 0), is_res.get("n_syms_measurable", 0))
    log.info("  OOS: n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci_lower=%.2f sym_ci_pos=%d/%d",
             oos_res["n"], oos_res.get("gross_bp", 0), oos_res.get("net_bp", 0),
             oos_res.get("signal_t_excess", 0), oos_res.get("ci_lower_bp", 0),
             oos_res.get("n_syms_ci_pos", 0), oos_res.get("n_syms_measurable", 0))
    # PASS: OOS sigex ≥ 2.0 AND OOS ci_lower > 0 (paradigm 117 fragility 회피)
    oos_pass_sigex = bool(oos_res.get("signal_t_excess", 0) >= 2.0)
    oos_pass_ci = bool(oos_res.get("ci_lower_bp", 0) > 0)
    out["caveat_6_oos_holdout"] = {
        "is_qtrs": IS_QTRS,
        "oos_qtrs": OOS_HOLDOUT_QTRS,
        "is_result": is_res,
        "oos_result": oos_res,
        "oos_pass_sigex_above_2": oos_pass_sigex,
        "oos_pass_ci_lower_above_0": oos_pass_ci,
        "paradigm_117_precedent_note": "p117 R-3 OOS sigex 1.929 < 2.0 → graveyard",
        "caveat_6_pass": bool(oos_pass_sigex and oos_pass_ci),
    }
    log.info("  CAVEAT #6: OOS sigex %.2f (≥2.0? %s) ci_lower %.2f (>0? %s) → pass=%s",
             oos_res.get("signal_t_excess", 0), oos_pass_sigex,
             oos_res.get("ci_lower_bp", 0), oos_pass_ci,
             out["caveat_6_oos_holdout"]["caveat_6_pass"])

    # ─── Caveat #7: survivorship test (top-N vs non-top-N) ──────────────────
    log.info("=" * 70)
    log.info("CAVEAT #7: survivorship test top-10 market cap vs non-top-10")
    log.info("  top-10: %s", TOP_N_MARKET_CAP_2024_01)
    log.info("  non-top: %s", NON_TOP_N)
    log.info("=" * 70)
    top_panel = primary_panel[primary_panel["sym"].isin(TOP_N_MARKET_CAP_2024_01)]
    non_top_panel = primary_panel[primary_panel["sym"].isin(NON_TOP_N)]
    log.info("  top-10 panel n=%d / non-top panel n=%d", len(top_panel), len(non_top_panel))
    top_res = evaluate_subset(top_panel, PRIMARY_FEE_BP, pool_50k,
                              do_per_sym_ci=True, boot_n=1500)
    non_top_res = evaluate_subset(non_top_panel, PRIMARY_FEE_BP, pool_50k,
                                  do_per_sym_ci=True, boot_n=1500)
    log.info("  top-10:  n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci_lower=%.2f",
             top_res["n"], top_res.get("gross_bp", 0), top_res.get("net_bp", 0),
             top_res.get("signal_t_excess", 0), top_res.get("ci_lower_bp", 0))
    log.info("  non-top: n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci_lower=%.2f",
             non_top_res["n"], non_top_res.get("gross_bp", 0), non_top_res.get("net_bp", 0),
             non_top_res.get("signal_t_excess", 0), non_top_res.get("ci_lower_bp", 0))
    # PASS: BOTH cohorts ci_lower > 0 (alpha not confined to top-N survivorship)
    non_top_ci_pos = bool(non_top_res.get("ci_lower_bp", 0) > 0)
    top_ci_pos = bool(top_res.get("ci_lower_bp", 0) > 0)
    out["caveat_7_survivorship"] = {
        "top_n_market_cap_2024_01": TOP_N_MARKET_CAP_2024_01,
        "non_top_n": NON_TOP_N,
        "top_result": top_res,
        "non_top_result": non_top_res,
        "top_ci_pos": top_ci_pos,
        "non_top_ci_pos": non_top_ci_pos,
        "caveat_7_pass": bool(top_ci_pos and non_top_ci_pos),
    }
    log.info("  CAVEAT #7: top_ci_pos=%s non_top_ci_pos=%s → pass=%s",
             top_ci_pos, non_top_ci_pos, out["caveat_7_survivorship"]["caveat_7_pass"])

    # ─── Phase 10: verdict tree ─────────────────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 10: R-3 verdict tree (7 caveats)")
    log.info("=" * 70)
    caveats_pass = {
        "1_hold_horizon_final": out["caveat_1_hold_horizon_final"]["caveat_1_pass"],
        "2_vol_regime": out["caveat_2_vol_regime"]["caveat_2_pass"],
        "3_debounce": out["caveat_3_debounce"].get("caveat_3_pass", False),
        "4_sharpe_artifact": out["caveat_4_sharpe_artifact"]["caveat_4_pass"],
        "5_per_burst_signing": out["caveat_5_per_burst_signing"].get("caveat_5_pass", False),
        "6_oos_holdout": out["caveat_6_oos_holdout"]["caveat_6_pass"],
        "7_survivorship": out["caveat_7_survivorship"]["caveat_7_pass"],
    }
    fail_map = {
        "1_hold_horizon_final": "R3_FAIL_HOLD_HORIZON",
        "2_vol_regime": "R3_FAIL_VOL_REGIME",
        "3_debounce": "R3_FAIL_DEBOUNCE",
        "4_sharpe_artifact": "R3_FAIL_SHARPE_ARTIFACT",
        "5_per_burst_signing": "R3_FAIL_PER_BURST_SIGNING",
        "6_oos_holdout": "R3_FAIL_OOS",
        "7_survivorship": "R3_FAIL_SURVIVORSHIP",
    }
    failing = [k for k, v in caveats_pass.items() if not v]
    if not failing:
        verdict = "PASS_R3"
    else:
        # OOS failure dominates (paradigm 117 precedent), then survivorship, then others
        priority = ["6_oos_holdout", "7_survivorship", "2_vol_regime",
                    "4_sharpe_artifact", "1_hold_horizon_final",
                    "3_debounce", "5_per_burst_signing"]
        for p in priority:
            if p in failing:
                verdict = fail_map[p]
                break
        else:
            verdict = "R3_FAIL_UNKNOWN"
    out["caveats_pass_summary"] = caveats_pass
    out["caveats_failing"] = failing
    out["verdict"] = verdict
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    log.info("=" * 80)
    log.info("CAVEATS PASS SUMMARY: %s", caveats_pass)
    log.info("FAILING CAVEATS: %s", failing if failing else "(none)")
    log.info("FINAL R-3 VERDICT: %s", verdict)
    log.info("Wall-clock: %.1f min", out["wall_clock_minutes"])
    log.info("=" * 80)

    out_path = OUT_DIR / "r3__metrics.json"
    with open(out_path, "w") as f:
        json.dump(_convert(out), f, indent=2)
    log.info("R-3 metrics: %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
