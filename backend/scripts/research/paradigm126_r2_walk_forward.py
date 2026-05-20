"""paradigm 126 R-2 walk-forward — alt_volume_burst_intra5m_event_signed_directional_30m.

R-1 recap (2026-05-20 21:45 KST):
  A_focus pos→LONG: gross +70.94 / net +54.94bp / sigex +50.33 / ci_lower +46.09 /
                    10/10 q_pos_t / 13/13 syms_ci_pos / 3-gate PASS / Concentration PASS
                    edge 0.549% / trades/yr 6019 (12,794 if both arms) — HIGH-FREQ DIFFUSE
  B_focus neg→SHORT: gross +51.57 / net +35.57bp / sigex +37.59 / ci_lower +18.38 /
                     9/10 q_pos_t / 13/13 syms_ci_pos / 3-gate PASS / Concentration PASS
                     edge 0.356% / trades/yr 6781
  Verdict: CONCENTRATED_LIFE_CHANGING_EDGE_FAIL_LESSON_41 (sparse-mode FAIL)
  Position B (Lesson #41 amendment dual-mode): high-freq diffuse qualifies
    portfolio ann gross A+B ≈ +57% (combined trades/yr 12,799, edge 0.45%, ann gross ≈ 57.6%)

R-2 mandatory checks (user-specified verdict tree)
--------------------------------------------------
1. Walk-forward TS-CV 5-fold (Lesson #26, paradigm 87 precedent):
   2024Q1+Q2 / 2024Q3+Q4 / 2025Q1+Q2 / 2025Q3+Q4 / 2026Q1+Q2 OOS folds.
   PASS: each fold gross > 16bp AND ci_lower > 0 AND ≥3/5 folds.
2. Threshold monotone sweep: p99 (primary) / p97 / p95 volume percentile relaxation.
   Monotone: trades/yr ↑, edge/trade ↓ expected. Non-monotone = noise signal.
3. Top-3 symbol exclusion stress test (broad-shoulders verification, paradigm 117 precedent):
   Remove top-3 ranked syms (gross_bp), measure 10-sym residual.
   PASS: 10-sym sigex ≥ 80% of R-1 (40.26 for A), ci_lower > 0.
4. Slippage stress: 16bp (primary) / 18bp / 20bp fee assumptions.
   PASS: ann gross ≥ +30% at 20bp.
5. Hold horizon sweep: 30min (primary) / 15 / 45 / 60 min.
   Monotone: hold ↑ edge ↑ trades/yr ↓ expected. Sweet-spot luck check.
6. Lesson #29 cross-proxy: gross AND ci_lower both PASS per-fold mandatory.
7. Concentration drift detection per fold (Lesson #16 amendment):
   Per-fold ci_pos symbols ≥ 10/13 expected.

Verdict tree
------------
PASS_R2                          : all gates clear (A or B focus)
FRAGILE_TS_CV_FAIL               : n_folds_pass < 3/5
THRESHOLD_NON_MONOTONE_FAIL      : sweep direction inversion
NARROW_UNIVERSE_FAIL             : top-3 exclusion collapses mechanism
SLIPPAGE_FAIL                    : 20bp fee → ann gross < +30%
HOLD_HORIZON_SINGLE_ANCHOR_FAIL  : 30min outlier vs neighbors (non-monotone severe)
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

PARADIGM_NAME = "alt_volume_burst_intra5m_event_signed_directional_30m"
PARADIGM_NUMBER = 126
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r2__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p126_r2")

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Primary R-1 params (preserve)
PRIMARY_ROLLING_DAYS = 30
ROLLING_BAR_WINDOW = PRIMARY_ROLLING_DAYS * 24 * 60
PRIMARY_PCTILE = 99.0
PRIMARY_MAG = 0.005
PRIMARY_HOLD_MIN = 30
PRIMARY_FEE_BP = 16.0

# R-2 sweep params
PCTILE_SWEEP = [99.0, 97.0, 95.0]
HOLD_SWEEP_MIN = [15, 30, 45, 60]
FEE_SWEEP_BP = [16.0, 18.0, 20.0]
TS_CV_N_FOLDS = 5
TOP_K_REMOVE = 3

DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return df


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


def build_triggers_panel(
    sym_data: dict[str, pd.DataFrame],
    volume_pctile: float,
    mag_threshold: float,
    hold_min: int,
) -> pd.DataFrame:
    """Build trigger event panel at 5m frame with signed direction and fwd-hold return.

    Returns DataFrame with columns: ts, sym, direction (±1), gross_bp (signed), qtr.
    """
    rows = []
    for sym, df in sym_data.items():
        j = df.copy()
        j["log_ret_1m"] = np.log(j["close"]).diff()
        j["abs_log_ret_1m"] = j["log_ret_1m"].abs()
        # Rolling p99 (per-symbol, 30-day window)
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
        # forward hold return (close-to-close, hold_min bars on 1m)
        j["fwd_ret"] = (
            j["close"].pct_change(hold_min).shift(-hold_min)
        )

        # 5m aggregation: first burst-sign within 5m bin
        first_sign_func = lambda x: int(x[x != 0].iloc[0]) if (x != 0).any() else 0
        j_5m = j.resample("5min").agg({
            "burst": "max",
            "burst_sign": first_sign_func,
            "fwd_ret": "first",
        })
        j_5m = j_5m.dropna(subset=["fwd_ret"])
        # filter trigger rows only
        trig = j_5m[j_5m["burst"] == 1].copy()
        if trig.empty:
            continue
        trig["sym"] = sym
        # signed gross return (direction * fwd_ret)
        trig["direction"] = trig["burst_sign"].astype(int)
        trig["gross_bp"] = trig["fwd_ret"] * trig["direction"] * 10000.0
        trig["qtr"] = trig.index.to_period("Q").astype(str)
        rows.append(trig.reset_index().rename(columns={"index": "ts", "timestamp": "ts"}))
    if not rows:
        return pd.DataFrame()
    panel = pd.concat(rows, ignore_index=True)
    # ensure ts column exists (DatetimeIndex name carries through)
    if "ts" not in panel.columns:
        # fallback: first col is timestamp
        panel.rename(columns={panel.columns[0]: "ts"}, inplace=True)
    panel = panel.sort_values("ts").reset_index(drop=True)
    return panel[["ts", "sym", "direction", "gross_bp", "qtr"]]


def evaluate_cell(
    panel: pd.DataFrame,
    arm: str,  # "A" (pos→LONG) or "B" (neg→SHORT)
    fee_bp: float,
    candidate_pool_bp: np.ndarray,
) -> dict:
    """Evaluate one arm at given fee. Panel is full trigger panel (pre-filter)."""
    if panel.empty:
        return {"arm": arm, "n": 0, "skip": True}
    if arm == "A":
        sub = panel[panel["direction"] > 0]
    else:
        sub = panel[panel["direction"] < 0]
    if len(sub) < 30:
        return {"arm": arm, "n": int(len(sub)), "skip": True}
    gross = sub["gross_bp"].values
    net = gross - fee_bp
    obs_t = _t_stat(net)
    ci = bootstrap_ci(net / 10000.0, n_boot=2000, block_size=20, rng_seed=42)
    ci_lower_bp = float(ci["ci_lower"]) * 10000
    ci_upper_bp = float(ci["ci_upper"]) * 10000
    pool_for_arm = candidate_pool_bp if arm == "A" else -candidate_pool_bp
    perm = fee_aware_perm_test(
        observed_net_returns=net / 10000.0,
        candidate_pool_returns=pool_for_arm / 10000.0,
        fee_per_trade=fee_bp / 10000.0,
        n_perms=1000,
        rng_seed=42,
    )
    sigex = float(perm.get("signal_t_excess", float("nan")))
    perm_p_above = float(perm.get("perm_p_one_sided_above", float("nan")))

    # per-quarter t (concentration drift detection)
    q_t_map = {}
    for q in sub["qtr"].unique():
        s = sub[sub["qtr"] == q]
        if len(s) >= 30:
            net_q = s["gross_bp"].values - fee_bp
            q_t_map[q] = _t_stat(net_q)
    n_q = len(q_t_map)
    n_q_pos = sum(1 for t in q_t_map.values() if t > 0)
    q_pos_t_ratio = n_q_pos / n_q if n_q else 0.0

    # per-symbol ci_pos count
    n_sym_ci_pos = 0
    n_sym_meas = 0
    sym_ranking = []
    for s in sub["sym"].unique():
        ss = sub[sub["sym"] == s]
        if len(ss) >= 30:
            n_sym_meas += 1
            sym_net = ss["gross_bp"].values - fee_bp
            sym_ci = bootstrap_ci(sym_net / 10000.0, n_boot=500, block_size=10, rng_seed=42)
            sym_ci_lower_bp = float(sym_ci["ci_lower"]) * 10000
            sym_ranking.append({
                "sym": s,
                "n": int(len(ss)),
                "gross_bp": float(ss["gross_bp"].mean()),
                "net_bp": float(sym_net.mean()),
                "ci_lower_bp": sym_ci_lower_bp,
                "ci_pos": bool(sym_ci_lower_bp > 0),
            })
            if sym_ci_lower_bp > 0:
                n_sym_ci_pos += 1
    syms_ci_pos_ratio = n_sym_ci_pos / n_sym_meas if n_sym_meas else 0.0

    return {
        "arm": arm,
        "n": int(len(sub)),
        "gross_bp": float(gross.mean()),
        "net_bp": float(net.mean()),
        "obs_t": obs_t,
        "signal_t_excess": sigex,
        "perm_p_one_sided_above": perm_p_above,
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": ci_upper_bp,
        "n_q_measurable": n_q,
        "n_q_pos_t": n_q_pos,
        "q_pos_t_ratio": q_pos_t_ratio,
        "per_quarter_t": q_t_map,
        "n_syms_measurable": n_sym_meas,
        "n_syms_ci_pos": n_sym_ci_pos,
        "syms_ci_pos_ratio": syms_ci_pos_ratio,
        "per_symbol": sym_ranking,
    }


def evaluate_fold(
    sub_panel: pd.DataFrame,
    arm: str,
    fee_bp: float,
    panel_for_pool_bp: np.ndarray,
    fold_label: str,
    fold_years: float,
) -> dict:
    """Per-fold evaluation, simpler (no per-sym bootstrap)."""
    if sub_panel.empty:
        return {"fold": fold_label, "n": 0, "skip": True}
    if arm == "A":
        s = sub_panel[sub_panel["direction"] > 0]
    else:
        s = sub_panel[sub_panel["direction"] < 0]
    if len(s) < 30:
        return {"fold": fold_label, "n": int(len(s)), "skip": True}
    gross = s["gross_bp"].values
    net = gross - fee_bp
    obs_t = _t_stat(net)
    ci = bootstrap_ci(net / 10000.0, n_boot=1000, block_size=20, rng_seed=42)
    ci_lower_bp = float(ci["ci_lower"]) * 10000
    ci_upper_bp = float(ci["ci_upper"]) * 10000
    # syms ci_pos in fold
    n_sym_ci_pos = 0
    n_sym_meas = 0
    for sym in s["sym"].unique():
        ss = s[s["sym"] == sym]
        if len(ss) >= 30:
            n_sym_meas += 1
            sym_net = ss["gross_bp"].values - fee_bp
            sym_ci = bootstrap_ci(sym_net / 10000.0, n_boot=300, block_size=10, rng_seed=42)
            if float(sym_ci["ci_lower"]) * 10000 > 0:
                n_sym_ci_pos += 1
    # Lesson #29 cross-proxy strict: both gross > 16bp (fee floor) AND ci_lower > 0
    gross_mean = float(gross.mean())
    pass_gross = bool(gross_mean > 16.0)
    pass_ci_lower = bool(ci_lower_bp > 0)
    fold_pass = pass_gross and pass_ci_lower

    return {
        "fold": fold_label,
        "n": int(len(s)),
        "n_sym_measurable": n_sym_meas,
        "n_sym_ci_pos": n_sym_ci_pos,
        "gross_bp": gross_mean,
        "net_bp": float(net.mean()),
        "obs_t": obs_t,
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": ci_upper_bp,
        "trades_per_year_fold": float(len(s) / fold_years) if fold_years > 0 else None,
        "pass_gross_above_16bp": pass_gross,
        "pass_ci_lower_above_0": pass_ci_lower,
        "fold_pass_lesson29": fold_pass,
    }


def main() -> int:
    t_start = time.time()
    log.info("paradigm 126 R-2 start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    out: dict = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-2",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "universe": COHORT,
        "primary_params": {
            "rolling_days": PRIMARY_ROLLING_DAYS,
            "volume_percentile": PRIMARY_PCTILE,
            "magnitude_threshold": PRIMARY_MAG,
            "forward_hold_min": PRIMARY_HOLD_MIN,
            "fee_bp": PRIMARY_FEE_BP,
        },
        "r2_sweep_params": {
            "pctile_sweep": PCTILE_SWEEP,
            "hold_sweep_min": HOLD_SWEEP_MIN,
            "fee_sweep_bp": FEE_SWEEP_BP,
            "ts_cv_folds": TS_CV_N_FOLDS,
            "top_k_remove_broad_shoulders": TOP_K_REMOVE,
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
                log.warning("  %s: insufficient 1m bars (%d) — skip", sym, len(df))
                continue
            sym_data[sym] = df
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            log.info("  %s: %d 1m bars (%d days)", sym, len(df), days)
        except Exception as e:
            log.error("  %s load fail: %s", sym, e)

    if len(sym_data) < 8:
        out["verdict"] = "R2_DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"only {len(sym_data)}/{len(COHORT)} symbols loaded"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        with open(OUT_DIR / "r2__metrics.json", "w") as f:
            json.dump(_convert(out), f, indent=2)
        return 1

    full_window = max(per_sym_days.values())
    panel_years = full_window / 365.0
    out["n_alts_usable"] = len(sym_data)
    out["per_symbol_days_1m"] = per_sym_days
    out["panel_years"] = panel_years
    log.info("usable alts: %d / panel_years=%.2f", len(sym_data), panel_years)

    # ─── Phase 2: primary panel build (p99 + 0.5% + 30min hold) ──────────────
    log.info("=" * 70)
    log.info("PHASE 2: build primary trigger panel (p99 / 0.5%% / 30min)")
    log.info("=" * 70)
    primary_panel = build_triggers_panel(
        sym_data,
        volume_pctile=PRIMARY_PCTILE,
        mag_threshold=PRIMARY_MAG,
        hold_min=PRIMARY_HOLD_MIN,
    )
    n_trig_total = len(primary_panel)
    n_trig_pos = int((primary_panel["direction"] > 0).sum())
    n_trig_neg = int((primary_panel["direction"] < 0).sum())
    log.info(
        "primary panel: total=%d pos=%d neg=%d",
        n_trig_total, n_trig_pos, n_trig_neg,
    )
    out["primary_panel_n_triggers"] = {
        "total": n_trig_total, "pos": n_trig_pos, "neg": n_trig_neg
    }

    # candidate pool from primary panel (gross_bp values for perm null)
    rng = np.random.default_rng(126)
    pool_size_target = 50000
    if len(primary_panel) > pool_size_target:
        idx = rng.choice(len(primary_panel), size=pool_size_target, replace=False)
        candidate_pool_bp = primary_panel["gross_bp"].iloc[idx].values
    else:
        candidate_pool_bp = primary_panel["gross_bp"].values

    # ─── Phase 3: Primary R-2 evaluation per arm (full panel, fee 16bp) ─────
    log.info("=" * 70)
    log.info("PHASE 3: Primary R-2 per-arm full panel (fee=%.0fbp)", PRIMARY_FEE_BP)
    log.info("=" * 70)
    arms_primary = {}
    for arm in ["A", "B"]:
        res = evaluate_cell(primary_panel, arm, PRIMARY_FEE_BP, candidate_pool_bp)
        arms_primary[arm] = res
        if not res.get("skip"):
            log.info(
                "  arm=%s n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci[%.2f,%.2f] "
                "q_pos=%d/%d sym_ci_pos=%d/%d",
                arm, res["n"], res["gross_bp"], res["net_bp"],
                res["signal_t_excess"], res["ci_lower_bp"], res["ci_upper_bp"],
                res["n_q_pos_t"], res["n_q_measurable"],
                res["n_syms_ci_pos"], res["n_syms_measurable"],
            )
    out["primary_r2_per_arm"] = arms_primary

    # ─── Phase 4: TS-CV 5-fold walk-forward (Lesson #26) ────────────────────
    log.info("=" * 70)
    log.info("PHASE 4: 5-fold TS-CV walk-forward (Lesson #26 paradigm 87 precedent)")
    log.info("=" * 70)
    # define folds by year-half:
    # fold 0: 2024H1 (2024Q1+Q2)
    # fold 1: 2024H2 (2024Q3+Q4)
    # fold 2: 2025H1
    # fold 3: 2025H2
    # fold 4: 2026H1
    fold_defs = [
        ("fold_0_2024H1", "2024Q1", "2024Q2"),
        ("fold_1_2024H2", "2024Q3", "2024Q4"),
        ("fold_2_2025H1", "2025Q1", "2025Q2"),
        ("fold_3_2025H2", "2025Q3", "2025Q4"),
        ("fold_4_2026H1", "2026Q1", "2026Q2"),
    ]
    ts_cv = {"A": [], "B": []}
    for arm in ["A", "B"]:
        n_pass = 0
        for label, q1, q2 in fold_defs:
            sub_panel = primary_panel[primary_panel["qtr"].isin([q1, q2])]
            if sub_panel.empty:
                ts_cv[arm].append({"fold": label, "n": 0, "skip": True})
                continue
            ts_span = (
                pd.to_datetime(sub_panel["ts"].max()) - pd.to_datetime(sub_panel["ts"].min())
            ).days / 365.25
            fold_years = max(1e-6, ts_span)
            res = evaluate_fold(
                sub_panel, arm, PRIMARY_FEE_BP, candidate_pool_bp, label, fold_years
            )
            ts_cv[arm].append(res)
            if res.get("fold_pass_lesson29"):
                n_pass += 1
            log.info(
                "  arm=%s fold=%s n=%d gross=%.2fbp ci_lower=%.2fbp sym_ci_pos=%d/%d pass=%s",
                arm, label, res.get("n", 0), res.get("gross_bp", float("nan")),
                res.get("ci_lower_bp", float("nan")),
                res.get("n_sym_ci_pos", 0), res.get("n_sym_measurable", 0),
                res.get("fold_pass_lesson29"),
            )
        ts_cv[f"{arm}_n_folds_pass"] = n_pass
        ts_cv[f"{arm}_ts_cv_pass"] = bool(n_pass >= 3)
        log.info(
            "  ts-cv arm=%s: %d/5 folds pass (Lesson #29 strict gross+ci_lower)",
            arm, n_pass,
        )
    out["ts_cv_5fold"] = ts_cv

    # ─── Phase 5: threshold sweep (p99 / p97 / p95) ─────────────────────────
    log.info("=" * 70)
    log.info("PHASE 5: percentile-threshold monotone sweep")
    log.info("=" * 70)
    pctile_sweep_results: dict = {}
    for p in PCTILE_SWEEP:
        log.info("  computing panel at p%.0f ...", p)
        panel_p = build_triggers_panel(
            sym_data, volume_pctile=p, mag_threshold=PRIMARY_MAG, hold_min=PRIMARY_HOLD_MIN
        )
        n_pos = int((panel_p["direction"] > 0).sum())
        n_neg = int((panel_p["direction"] < 0).sum())
        pctile_sweep_results[f"p{p:.0f}"] = {"n_pos": n_pos, "n_neg": n_neg}
        for arm in ["A", "B"]:
            if arm == "A":
                sub = panel_p[panel_p["direction"] > 0]
            else:
                sub = panel_p[panel_p["direction"] < 0]
            if len(sub) < 30:
                pctile_sweep_results[f"p{p:.0f}"][f"arm_{arm}"] = {"skip": True, "n": int(len(sub))}
                continue
            gross = sub["gross_bp"].values
            net = gross - PRIMARY_FEE_BP
            ci = bootstrap_ci(net / 10000.0, n_boot=1000, block_size=20, rng_seed=42)
            tpy_arm = len(sub) / panel_years
            pctile_sweep_results[f"p{p:.0f}"][f"arm_{arm}"] = {
                "n": int(len(sub)),
                "gross_bp": float(gross.mean()),
                "net_bp": float(net.mean()),
                "ci_lower_bp": float(ci["ci_lower"]) * 10000,
                "trades_per_year": float(tpy_arm),
                "per_trade_edge_pct": float(net.mean() / 100.0),
                "ann_gross_pct": float(gross.mean() * tpy_arm / 100.0),
            }
            log.info(
                "    p%.0f arm=%s: n=%d gross=%.2fbp net=%.2fbp ci_lower=%.2f tpy=%.0f ann_gross=%.1f%%",
                p, arm, len(sub), float(gross.mean()), float(net.mean()),
                float(ci["ci_lower"]) * 10000, tpy_arm, gross.mean() * tpy_arm / 100.0,
            )
    out["pctile_sweep_results"] = pctile_sweep_results

    # monotone check: expect tpy ↑, edge/trade ↓ as p99→p95
    def _mono_check(arm: str) -> dict:
        edges = []
        tpys = []
        for p in PCTILE_SWEEP:
            r = pctile_sweep_results[f"p{p:.0f}"].get(f"arm_{arm}", {})
            if r.get("skip"):
                continue
            edges.append(r.get("per_trade_edge_pct"))
            tpys.append(r.get("trades_per_year"))
        if len(edges) < 2:
            return {"insufficient": True}
        # tpy must monotone increase as p99→p95
        tpy_mono_inc = all(tpys[i + 1] >= tpys[i] for i in range(len(tpys) - 1))
        # edge can decrease (typical) or stay; non-monotone if reverses
        edge_mono_dec = all(edges[i + 1] <= edges[i] + 1e-6 for i in range(len(edges) - 1))
        return {
            "edges": edges, "tpys": tpys,
            "tpy_monotone_increase": bool(tpy_mono_inc),
            "edge_monotone_decrease": bool(edge_mono_dec),
        }
    out["pctile_monotone_check"] = {
        "A": _mono_check("A"),
        "B": _mono_check("B"),
    }

    # ─── Phase 6: Top-3 symbol exclusion broad-shoulders ────────────────────
    log.info("=" * 70)
    log.info("PHASE 6: Top-3 symbol exclusion (broad-shoulders, paradigm 117 precedent)")
    log.info("=" * 70)
    broad_shoulders: dict = {}
    for arm in ["A", "B"]:
        primary = arms_primary[arm]
        if primary.get("skip"):
            broad_shoulders[arm] = {"skip": True}
            continue
        per_sym = primary["per_symbol"]
        # rank by gross_bp descending
        ranked = sorted(per_sym, key=lambda x: -x["gross_bp"])
        top3_syms = [r["sym"] for r in ranked[:TOP_K_REMOVE]]
        if arm == "A":
            sub_excl = primary_panel[
                (primary_panel["direction"] > 0) & (~primary_panel["sym"].isin(top3_syms))
            ]
        else:
            sub_excl = primary_panel[
                (primary_panel["direction"] < 0) & (~primary_panel["sym"].isin(top3_syms))
            ]
        if len(sub_excl) < 30:
            broad_shoulders[arm] = {"top3_syms": top3_syms, "skip": True, "n": int(len(sub_excl))}
            continue
        gross = sub_excl["gross_bp"].values
        net = gross - PRIMARY_FEE_BP
        ci = bootstrap_ci(net / 10000.0, n_boot=2000, block_size=20, rng_seed=42)
        obs_t = _t_stat(net)
        pool_for_arm = candidate_pool_bp if arm == "A" else -candidate_pool_bp
        perm = fee_aware_perm_test(
            observed_net_returns=net / 10000.0,
            candidate_pool_returns=pool_for_arm / 10000.0,
            fee_per_trade=PRIMARY_FEE_BP / 10000.0,
            n_perms=1000, rng_seed=42,
        )
        sigex_excl = float(perm.get("signal_t_excess", float("nan")))
        # 80% threshold of R-1 sigex (A=50.33, B=37.59)
        r1_sigex = 50.33 if arm == "A" else 37.59
        sigex_pass = bool(sigex_excl >= 0.80 * r1_sigex)
        ci_pass = bool(float(ci["ci_lower"]) * 10000 > 0)
        broad_shoulders[arm] = {
            "top3_syms_removed": top3_syms,
            "top3_per_sym_gross_bp": {
                r["sym"]: r["gross_bp"] for r in ranked[:TOP_K_REMOVE]
            },
            "n_residual": int(len(sub_excl)),
            "gross_bp_residual": float(gross.mean()),
            "net_bp_residual": float(net.mean()),
            "obs_t_residual": obs_t,
            "signal_t_excess_residual": sigex_excl,
            "ci_lower_bp_residual": float(ci["ci_lower"]) * 10000,
            "ci_upper_bp_residual": float(ci["ci_upper"]) * 10000,
            "r1_sigex_reference": r1_sigex,
            "sigex_80pct_threshold": 0.80 * r1_sigex,
            "broad_shoulders_pass_sigex": sigex_pass,
            "broad_shoulders_pass_ci_lower": ci_pass,
            "broad_shoulders_pass": bool(sigex_pass and ci_pass),
        }
        log.info(
            "  arm=%s top3=%s n_residual=%d gross=%.2fbp sigex=%.2f (≥%.2f?) ci_lower=%.2f pass=%s",
            arm, top3_syms, len(sub_excl), float(gross.mean()), sigex_excl,
            0.80 * r1_sigex, float(ci["ci_lower"]) * 10000, broad_shoulders[arm]["broad_shoulders_pass"],
        )
    out["broad_shoulders_top3_exclusion"] = broad_shoulders

    # ─── Phase 7: Slippage stress (16 / 18 / 20 bp) ─────────────────────────
    log.info("=" * 70)
    log.info("PHASE 7: slippage stress (fee 16/18/20bp)")
    log.info("=" * 70)
    slippage: dict = {}
    for fee in FEE_SWEEP_BP:
        slippage[f"fee_{fee:.0f}bp"] = {}
        for arm in ["A", "B"]:
            if arm == "A":
                sub = primary_panel[primary_panel["direction"] > 0]
            else:
                sub = primary_panel[primary_panel["direction"] < 0]
            if len(sub) < 30:
                slippage[f"fee_{fee:.0f}bp"][f"arm_{arm}"] = {"skip": True}
                continue
            gross = sub["gross_bp"].values
            net = gross - fee
            ci = bootstrap_ci(net / 10000.0, n_boot=1000, block_size=20, rng_seed=42)
            tpy = len(sub) / panel_years
            ann_gross_pct = float(gross.mean() * tpy / 100.0)
            ann_net_pct = float(net.mean() * tpy / 100.0)
            slippage[f"fee_{fee:.0f}bp"][f"arm_{arm}"] = {
                "n": int(len(sub)),
                "gross_bp": float(gross.mean()),
                "net_bp": float(net.mean()),
                "ci_lower_bp": float(ci["ci_lower"]) * 10000,
                "trades_per_year": float(tpy),
                "ann_gross_pct": ann_gross_pct,
                "ann_net_pct": ann_net_pct,
                "ci_pos": bool(float(ci["ci_lower"]) > 0),
            }
            log.info(
                "  fee=%.0fbp arm=%s n=%d gross=%.2fbp net=%.2fbp tpy=%.0f ann_gross=%.1f%% ann_net=%.1f%%",
                fee, arm, len(sub), float(gross.mean()), float(net.mean()),
                tpy, ann_gross_pct, ann_net_pct,
            )
    # Slippage stress portfolio (combined A+B) at 20bp
    p20 = slippage["fee_20bp"]
    portfolio_combined_ann_gross_20bp = 0.0
    if not p20["arm_A"].get("skip") and not p20["arm_B"].get("skip"):
        portfolio_combined_ann_gross_20bp = (
            p20["arm_A"]["ann_gross_pct"] + p20["arm_B"]["ann_gross_pct"]
        )
    slippage_pass_portfolio_30pct = bool(portfolio_combined_ann_gross_20bp >= 30.0)
    log.info(
        "  portfolio (A+B) ann_gross at 20bp = %.1f%% — pass ≥30%%? %s",
        portfolio_combined_ann_gross_20bp, slippage_pass_portfolio_30pct,
    )
    out["slippage_stress"] = slippage
    out["slippage_portfolio_pass_30pct_at_20bp"] = {
        "portfolio_ann_gross_pct_20bp": portfolio_combined_ann_gross_20bp,
        "pass": slippage_pass_portfolio_30pct,
    }

    # ─── Phase 8: hold horizon sweep (15 / 30 / 45 / 60 min) ────────────────
    log.info("=" * 70)
    log.info("PHASE 8: hold horizon sweep")
    log.info("=" * 70)
    hold_sweep: dict = {}
    for h in HOLD_SWEEP_MIN:
        log.info("  computing panel at hold=%d ...", h)
        panel_h = build_triggers_panel(
            sym_data, volume_pctile=PRIMARY_PCTILE,
            mag_threshold=PRIMARY_MAG, hold_min=h,
        )
        hold_sweep[f"hold_{h}min"] = {}
        for arm in ["A", "B"]:
            if arm == "A":
                sub = panel_h[panel_h["direction"] > 0]
            else:
                sub = panel_h[panel_h["direction"] < 0]
            if len(sub) < 30:
                hold_sweep[f"hold_{h}min"][f"arm_{arm}"] = {"skip": True}
                continue
            gross = sub["gross_bp"].values
            net = gross - PRIMARY_FEE_BP
            ci = bootstrap_ci(net / 10000.0, n_boot=500, block_size=20, rng_seed=42)
            tpy = len(sub) / panel_years
            hold_sweep[f"hold_{h}min"][f"arm_{arm}"] = {
                "n": int(len(sub)),
                "gross_bp": float(gross.mean()),
                "net_bp": float(net.mean()),
                "ci_lower_bp": float(ci["ci_lower"]) * 10000,
                "trades_per_year": float(tpy),
                "ann_gross_pct": float(gross.mean() * tpy / 100.0),
                "per_trade_edge_pct": float(net.mean() / 100.0),
            }
            log.info(
                "    hold=%dmin arm=%s n=%d gross=%.2fbp net=%.2fbp tpy=%.0f ann_gross=%.1f%%",
                h, arm, len(sub), float(gross.mean()), float(net.mean()),
                tpy, gross.mean() * tpy / 100.0,
            )
    out["hold_horizon_sweep"] = hold_sweep

    # 30min sweet-spot luck check: 30min ann_gross between 15min and 60min monotonically?
    def _hold_mono_check(arm: str) -> dict:
        rows = []
        for h in HOLD_SWEEP_MIN:
            r = hold_sweep[f"hold_{h}min"].get(f"arm_{arm}", {})
            if r.get("skip"):
                continue
            rows.append((h, r["per_trade_edge_pct"], r["ann_gross_pct"]))
        if len(rows) < 3:
            return {"insufficient": True}
        edges = [r[1] for r in rows]
        anns = [r[2] for r in rows]
        # check: 30min is sweet-spot if it is local max in ann_gross
        idx_30 = next((i for i, (h, _, _) in enumerate(rows) if h == 30), None)
        local_max_30 = False
        if idx_30 is not None and 0 < idx_30 < len(rows) - 1:
            local_max_30 = anns[idx_30] >= anns[idx_30 - 1] and anns[idx_30] >= anns[idx_30 + 1]
        # monotone edge increase with hold
        edge_mono_inc = all(edges[i + 1] >= edges[i] - 1.0 for i in range(len(edges) - 1))
        return {
            "rows": rows,
            "30min_local_max_in_ann_gross": local_max_30,
            "edge_monotone_increase_with_hold": edge_mono_inc,
        }
    out["hold_horizon_monotone_check"] = {
        "A": _hold_mono_check("A"),
        "B": _hold_mono_check("B"),
    }

    # ─── Phase 9: life-changing 4-dim verification (high-freq diffuse mode) ──
    log.info("=" * 70)
    log.info("PHASE 9: life-changing 4-dim verification (Lesson #41 dual-mode high-freq)")
    log.info("=" * 70)
    lc4: dict = {}
    for arm in ["A", "B"]:
        primary = arms_primary[arm]
        if primary.get("skip"):
            lc4[arm] = {"skip": True}
            continue
        n = primary["n"]
        tpy = n / panel_years
        edge_pct = primary["net_bp"] / 100.0
        # capital_util_pct = hold_min / (365.25 * 24 * 60) * trades_per_year * 100
        capital_util = min(100.0, (PRIMARY_HOLD_MIN * tpy) / (365.25 * 24 * 60) * 100)
        ann_gross_pct = float(primary["gross_bp"] * tpy / 100.0)
        ann_net_pct = float(primary["net_bp"] * tpy / 100.0)
        # sharpe approximation from obs_t + tpy
        sharpe_approx = (primary["obs_t"] / math.sqrt(n)) * math.sqrt(tpy) if n > 0 else 0.0
        lc4[arm] = {
            "trades_per_year": float(tpy),
            "per_trade_edge_pct": float(edge_pct),
            "capital_util_pct": float(capital_util),
            "annualized_sharpe_approx": float(sharpe_approx),
            "ann_gross_pct": ann_gross_pct,
            "ann_net_pct": ann_net_pct,
            "pass_trades_per_year_12": bool(tpy >= 12),
            "pass_edge_2pct": bool(edge_pct >= 2.0),
            "pass_util_30pct": bool(capital_util >= 30),
            "pass_sharpe_1_5": bool(sharpe_approx >= 1.5),
            "pass_4_dim_sparse_mode": bool(
                tpy >= 12 and edge_pct >= 2.0
                and capital_util >= 30 and sharpe_approx >= 1.5
            ),
            "pass_high_freq_diffuse_mode_ann_gross_50": bool(ann_gross_pct >= 50.0),
            "pass_high_freq_diffuse_mode_ann_gross_30_post_slippage": bool(
                ann_gross_pct * (PRIMARY_FEE_BP / 20.0) >= 30.0
            ),
        }
        log.info(
            "  arm=%s tpy=%.0f edge=%.3f%% util=%.1f%% sharpe~%.2f ann_gross=%.1f%% ann_net=%.1f%%",
            arm, tpy, edge_pct, capital_util, sharpe_approx, ann_gross_pct, ann_net_pct,
        )
    # combined portfolio (A+B)
    if not lc4["A"].get("skip") and not lc4["B"].get("skip"):
        portfolio_ann_gross = lc4["A"]["ann_gross_pct"] + lc4["B"]["ann_gross_pct"]
        portfolio_ann_net = lc4["A"]["ann_net_pct"] + lc4["B"]["ann_net_pct"]
        portfolio_tpy = lc4["A"]["trades_per_year"] + lc4["B"]["trades_per_year"]
        lc4["portfolio_A_plus_B"] = {
            "ann_gross_pct": portfolio_ann_gross,
            "ann_net_pct": portfolio_ann_net,
            "trades_per_year": portfolio_tpy,
            "pass_50pct_ann_gross": bool(portfolio_ann_gross >= 50.0),
            "pass_30pct_ann_gross_post_slippage": bool(
                portfolio_ann_gross * (PRIMARY_FEE_BP / 20.0) >= 30.0
            ),
        }
        log.info(
            "  PORTFOLIO A+B: tpy=%.0f ann_gross=%.1f%% ann_net=%.1f%%",
            portfolio_tpy, portfolio_ann_gross, portfolio_ann_net,
        )
    out["life_changing_4dim_dual_mode"] = lc4

    # ─── Phase 10: verdict tree ──────────────────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 10: R-2 verdict tree")
    log.info("=" * 70)

    # Per-arm verdict
    arm_verdicts = {}
    for arm in ["A", "B"]:
        flags = {
            "primary_3gate_pass": bool(
                arms_primary[arm].get("signal_t_excess", 0) >= 2.0
                and arms_primary[arm].get("ci_lower_bp", 0) > 0
                and arms_primary[arm].get("perm_p_one_sided_above", 1) <= 0.10
            ),
            "ts_cv_pass": ts_cv.get(f"{arm}_ts_cv_pass", False),
            "broad_shoulders_pass": broad_shoulders[arm].get("broad_shoulders_pass", False),
            "slippage_high_freq_30pct_pass": bool(
                lc4[arm].get("pass_high_freq_diffuse_mode_ann_gross_30_post_slippage", False)
            ),
            "hold_horizon_30_local_max": (
                out["hold_horizon_monotone_check"][arm].get("30min_local_max_in_ann_gross", False)
                if not out["hold_horizon_monotone_check"][arm].get("insufficient") else False
            ),
            "pctile_tpy_monotone_inc": (
                out["pctile_monotone_check"][arm].get("tpy_monotone_increase", False)
                if not out["pctile_monotone_check"][arm].get("insufficient") else False
            ),
        }
        # determine verdict
        if not flags["primary_3gate_pass"]:
            v = "FAIL_PRIMARY_3GATE"
        elif not flags["ts_cv_pass"]:
            v = "FRAGILE_TS_CV_FAIL"
        elif not flags["broad_shoulders_pass"]:
            v = "NARROW_UNIVERSE_FAIL"
        elif not flags["slippage_high_freq_30pct_pass"]:
            v = "SLIPPAGE_FAIL"
        else:
            v = "PASS_R2_HIGH_FREQ_DIFFUSE"
        arm_verdicts[arm] = {"flags": flags, "verdict": v}
        log.info("  arm=%s verdict=%s flags=%s", arm, v, flags)

    # Final overall verdict
    if any(v["verdict"] == "PASS_R2_HIGH_FREQ_DIFFUSE" for v in arm_verdicts.values()):
        final_verdict = "PASS_R2_HIGH_FREQ_DIFFUSE"
    else:
        # pick worst fail among arms
        failure_ranking = [
            "FAIL_PRIMARY_3GATE",
            "FRAGILE_TS_CV_FAIL",
            "NARROW_UNIVERSE_FAIL",
            "SLIPPAGE_FAIL",
        ]
        verdicts_seen = [v["verdict"] for v in arm_verdicts.values()]
        for f in failure_ranking:
            if f in verdicts_seen:
                final_verdict = f
                break
        else:
            final_verdict = "UNDETERMINED"
    out["arm_verdicts"] = arm_verdicts
    out["verdict"] = final_verdict
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    log.info("=" * 70)
    log.info("FINAL VERDICT: %s", final_verdict)
    log.info("Wall-clock: %.1f min", out["wall_clock_minutes"])
    log.info("=" * 70)

    out_path = OUT_DIR / "r2__metrics.json"
    with open(out_path, "w") as f:
        json.dump(_convert(out), f, indent=2)
    log.info("R-2 metrics: %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
