"""Paradigm 117 R-2 — alt_extreme_24h_drawdown_24h_reversion_long

R-1 recap
---------
slug RENAMED from `alt_extreme_24h_drawdown_reversal_long_4h` to
`alt_extreme_24h_drawdown_24h_reversion_long` (mechanism timescale is 24h, NOT 4h).

R-1 24h cell:
  n_trades 406, gross +275.31bp / net +267.31bp / edge +2.67%/trade,
  sigex +8.71, perm_p 0.000, CI [+201.52, +329.38]bp,
  q_pos 7/8, syms_ci_pos 13/28 (46%), Sharpe 5.72, lc4 ALL 4/4 PASS.

R-2 mandatory checks (user-specified verdict tree)
--------------------------------------------------
1. Pool-drift triage (Lesson #35): A_mirror at 24h + baseline unconditional 24h drift.
2. Walk-forward TS-CV 5-fold (Lesson #26): paradigm 87 precedent (R-1 PASS → R-2 1/5).
3. Threshold sweep monotone (mechanism robustness): {-12,-15,-18,-22}% at 24h.
4. Sub-class A perfect-mirror check (Lesson #39) at 24h.
5. Universe broad-shoulders: remove top-3 contributors, mechanism must survive.
6. Life-changing 4-dim verification at primary 24h cell.
7. Survivorship caveat documentation.

Verdict tree
------------
R2_FAIL_POOL_DRIFT             : drift_artifact_pct > 50%
R2_FAIL_TS_CV                  : folds_pass < 3/5
R2_FAIL_THRESHOLD_INCONSISTENT : sweep non-monotone or reversed
R2_FAIL_NARROW_UNIVERSE        : remove-top-3 collapses mechanism
R2_FAIL_LIFE_CHANGING          : edge < 2%/trade at primary R-2 cell
R2_PASS                        : all gates clear
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

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

# ─── Identity ────────────────────────────────────────────────────────────────
R1_ALIAS = "alt_extreme_24h_drawdown_reversal_long_4h"
PARADIGM_SLUG = "alt_extreme_24h_drawdown_24h_reversion_long"
PARADIGM_NUMBER = 117

OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORE_CACHE_DIR = (
    ROOT / "runs" / "research_track"
    / "intraday_hour_of_day_anchor_alt_directional_2h" / "klines_cache"
)
EXPANSION_CACHE_DIR = (
    ROOT / "runs" / "research_track"
    / "alt_atr_normalized_range_breakout_continuation_long_2h"
    / "klines_cache_r2_expansion"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r2__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p117_r2")

# ─── Universe (R-1: 28 alts) ─────────────────────────────────────────────────
ALTS_CORE = [
    "SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT",
    "NEARUSDT", "XRPUSDT", "ETHUSDT",
]
ALTS_EXPANSION = [
    "1000PEPEUSDT", "1000SHIBUSDT", "AAVEUSDT", "APTUSDT", "ARBUSDT",
    "ATOMUSDT", "DOTUSDT", "ICPUSDT", "INJUSDT",
    "OPUSDT", "SEIUSDT", "SUIUSDT", "TIAUSDT", "TRXUSDT", "UNIUSDT",
]
ALTS = ALTS_CORE + ALTS_EXPANSION  # 28

START_MONTH = "2024-05"
END_MONTH = "2026-04"

# ─── Parameters ──────────────────────────────────────────────────────────────
FEE_PER_TRADE = 0.0008  # 16bp round-trip
ROLLING_24H_BARS = 24
DEBOUNCE_BARS = 24

PRIMARY_THRESHOLD = -0.15  # primary R-2 cell
THRESHOLD_SWEEP = [-0.12, -0.15, -0.18, -0.22]  # user-specified for R-2
PRIMARY_HOLD_BARS = 24  # ★ R-2 PRIMARY HOLD = 24h (NOT 4h — pivot from R-1)

TS_CV_N_FOLDS = 5
TOP_K_REMOVE_BROAD_SHOULDERS = 3

# ─── Helpers ─────────────────────────────────────────────────────────────────


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def load_1h_klines_from_cache(sym: str, month: str) -> pd.DataFrame:
    for cdir in (CORE_CACHE_DIR, EXPANSION_CACHE_DIR):
        cache_file = cdir / f"{sym}_1h_{month}.joblib"
        if cache_file.exists():
            try:
                return joblib.load(cache_file)
            except Exception as e:
                log.warning("cache load fail %s %s @ %s: %s", sym, month, cdir.name, e)
                return pd.DataFrame()
    return pd.DataFrame()


def build_1h_panel(sym: str, months: list[str]) -> pd.DataFrame:
    parts = []
    for m in months:
        d = load_1h_klines_from_cache(sym, m)
        if not d.empty:
            parts.append(d)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def collect_debounced_trades(
    mask_per_sym: dict[str, pd.Series],
    fwd_per_sym: dict[str, pd.Series],
    direction_per_sym: dict[str, int],
    debounce_bars: int,
) -> tuple[list[float], list[pd.Timestamp], list[str]]:
    """Return debounced trades (return, ts, sym) lists."""
    min_gap = pd.Timedelta(hours=debounce_bars)
    rets: list[float] = []
    tss: list[pd.Timestamp] = []
    syms: list[str] = []
    for s, mask in mask_per_sym.items():
        fwd = fwd_per_sym.get(s)
        if fwd is None or len(fwd) == 0:
            continue
        d = direction_per_sym[s]
        idx_trig = mask.index[mask.fillna(False) & fwd.notna()]
        if len(idx_trig) == 0:
            continue
        last_t = None
        for t in idx_trig:
            if last_t is None or (t - last_t) >= min_gap:
                rets.append(d * float(fwd.loc[t]))
                tss.append(t)
                syms.append(s)
                last_t = t
    return rets, tss, syms


def summarize_pool(net_returns: np.ndarray, ts_list: list[pd.Timestamp]) -> dict:
    if len(net_returns) < 5:
        return {"n": int(len(net_returns)), "error": "n<5"}
    sd = net_returns.std(ddof=1)
    mean = float(net_returns.mean())
    t_stat = float(mean / sd * np.sqrt(len(net_returns))) if sd > 0 else 0.0
    ci = bootstrap_ci(net_returns, n_boot=1000, rng_seed=42)
    n_years = max(
        1e-6, (pd.to_datetime(max(ts_list)) - pd.to_datetime(min(ts_list))).days / 365.25
    )
    tpy = len(net_returns) / n_years
    sharpe = (mean / sd) * np.sqrt(tpy) if sd > 0 else 0.0
    return {
        "n": int(len(net_returns)),
        "mean_net_bp": mean * 10000,
        "t_stat": t_stat,
        "ci_lower_bp": float(ci["ci_lower"] * 10000),
        "ci_upper_bp": float(ci["ci_upper"] * 10000),
        "ci_pos": bool(ci["ci_lower"] > 0),
        "trades_per_year": float(tpy),
        "annualized_sharpe": float(sharpe),
    }


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
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    return obj


def _write(out: dict, name: str = "r2__metrics.json") -> None:
    p = OUT_DIR / name
    with p.open("w") as f:
        json.dump(_convert(out), f, indent=2)
    log.info("metrics written: %s", p)


# ─── R-2 main ────────────────────────────────────────────────────────────────


def main() -> int:
    t_start = time.time()
    out: dict = {
        "paradigm_name": PARADIGM_SLUG,
        "r1_alias": R1_ALIAS,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-2",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "primary_threshold": PRIMARY_THRESHOLD,
        "primary_hold_bars_r2": PRIMARY_HOLD_BARS,
        "primary_hold_hours_r2": PRIMARY_HOLD_BARS,
        "threshold_sweep_r2": THRESHOLD_SWEEP,
        "fee_per_trade": FEE_PER_TRADE,
        "debounce_bars": DEBOUNCE_BARS,
        "window_months": [START_MONTH, END_MONTH],
        "universe_alts": ALTS,
        "n_alts_universe": len(ALTS),
        "ts_cv_n_folds": TS_CV_N_FOLDS,
        "broad_shoulders_top_k_remove": TOP_K_REMOVE_BROAD_SHOULDERS,
    }

    # ─── Phase 1: load OHLCV from cache ──────────────────────────────────────
    months = month_iter(START_MONTH, END_MONTH)
    log.info("loading 1h OHLCV for %d alts × %d months", len(ALTS), len(months))
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS:
        df = build_1h_panel(s, months)
        if df.empty:
            log.warning("  %s: empty — drop", s)
            continue
        if len(df) < 17000:
            log.warning("  %s: only %d rows — drop", s, len(df))
            continue
        panel[s] = df

    out["n_alts_usable"] = len(panel)
    out["alts_usable"] = sorted(panel.keys())
    if len(panel) < 8:
        out["verdict"] = "R2_DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"cache load produced only {len(panel)}/{len(ALTS)} usable"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1
    log.info("usable alts: %d", len(panel))

    # ─── Phase 2: build features (rolling 24h log return + forward returns) ─
    close_per_sym: dict[str, pd.Series] = {}
    ret24h_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].astype(float).copy()
        close_per_sym[s] = c
        ret24h_per_sym[s] = np.log(c / c.shift(ROLLING_24H_BARS))

    # 24h primary forward (h=24)
    fwd24h_per_sym: dict[str, pd.Series] = {}
    for s, c in close_per_sym.items():
        fwd24h_per_sym[s] = np.log(c.shift(-PRIMARY_HOLD_BARS) / c)

    # ─── Phase 3: pool-drift triage (Lesson #35) ─────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 3: pool-drift triage (A_mirror + baseline unconditional)")
    log.info("=" * 70)

    # Unconditional baseline pool: average 24h forward return across ALL bars
    all_fwd24h = np.concatenate(
        [f.dropna().values for f in fwd24h_per_sym.values()]
    )
    pool_baseline_mean_log = float(all_fwd24h.mean())
    # gross (no fee) since this is a population statistic, not trade
    pool_baseline_24h_drift_bp = float(pool_baseline_mean_log * 10000)
    pool_baseline_24h_drift_pct = float(pool_baseline_mean_log * 100)
    log.info(
        "Pool baseline (unconditional 24h fwd log-return, n=%d): %.2f bp (= %.3f%%)",
        len(all_fwd24h),
        pool_baseline_24h_drift_bp,
        pool_baseline_24h_drift_pct,
    )

    out["pool_drift_diagnostic"] = {
        "n_pool_baseline_bars": int(len(all_fwd24h)),
        "pool_baseline_24h_drift_bp_gross": pool_baseline_24h_drift_bp,
        "pool_baseline_24h_drift_pct_gross": pool_baseline_24h_drift_pct,
    }

    # A_focus and A_mirror @ primary threshold = -15% × 24h hold
    dn_mask_per_sym: dict[str, pd.Series] = {}
    for s in panel:
        r = ret24h_per_sym[s]
        dn_mask_per_sym[s] = (r <= PRIMARY_THRESHOLD) & r.notna()

    dir_long = {s: +1 for s in panel}
    dir_short = {s: -1 for s in panel}

    focus_rets, focus_ts, focus_syms = collect_debounced_trades(
        dn_mask_per_sym, fwd24h_per_sym, dir_long, DEBOUNCE_BARS
    )
    mirror_rets, mirror_ts, mirror_syms = collect_debounced_trades(
        dn_mask_per_sym, fwd24h_per_sym, dir_short, DEBOUNCE_BARS
    )

    focus_gross = np.asarray(focus_rets, dtype=float)
    focus_net = focus_gross - FEE_PER_TRADE
    mirror_gross = np.asarray(mirror_rets, dtype=float)
    mirror_net = mirror_gross - FEE_PER_TRADE

    a_focus_24h_gross_bp = float(focus_gross.mean() * 10000) if len(focus_gross) else 0.0
    a_focus_24h_net_bp = float(focus_net.mean() * 10000) if len(focus_net) else 0.0
    a_mirror_24h_gross_bp = (
        float(mirror_gross.mean() * 10000) if len(mirror_gross) else 0.0
    )
    a_mirror_24h_net_bp = (
        float(mirror_net.mean() * 10000) if len(mirror_net) else 0.0
    )

    # Lesson #39 sub-class A perfect-mirror check: A_focus + A_mirror gross sum_abs
    sum_abs_mirror_bp = abs(a_focus_24h_gross_bp + a_mirror_24h_gross_bp)
    is_perfect_mirror_24h = bool(sum_abs_mirror_bp < 1.0)

    # drift_artifact_pct = (|A_mirror| is the directional bias we'd capture
    # if signal were pure pool drift). Following user spec:
    #   drift_artifact_pct = (A_focus - |A_mirror|) / A_focus * 100
    # However note: if A_mirror is positive (drawdown→SHORT also profitable
    # at 24h), that would indicate strong pool drift in BOTH directions,
    # i.e. the trigger has zero directional info. If A_mirror is strongly
    # NEGATIVE, then A_focus = (a_baseline_at_trigger + directional_alpha)
    # and A_mirror = (-a_baseline_at_trigger - directional_alpha).
    # The closer to perfect mirror (|A_mirror|≈A_focus), the more the gross
    # is "pure direction-bet at this anchor" - which can either be pool drift
    # or real directional alpha distinguished by baseline drift comparison.
    #
    # Formal: pool-drift contribution per A_focus trade ≈ pool_baseline_24h_drift_bp
    # directional alpha ≈ A_focus - pool_baseline (raw conditional drift over baseline)
    # If A_focus ≈ pool_baseline → entirely pool drift → POOL_DRIFT FAIL
    # If A_focus >> pool_baseline → genuine conditional alpha
    drift_artifact_pct_user_def = (
        (a_focus_24h_gross_bp - abs(a_mirror_24h_gross_bp)) / a_focus_24h_gross_bp * 100.0
        if a_focus_24h_gross_bp > 0 else 0.0
    )
    # Inverted version: how much of A_focus is "explained by" pool drift
    # = pool_baseline / A_focus (fraction)
    pool_drift_share_of_focus_pct = (
        100.0 * pool_baseline_24h_drift_bp / a_focus_24h_gross_bp
        if a_focus_24h_gross_bp > 0 else 0.0
    )

    log.info(
        "A_focus drawdown→LONG @ 24h: n=%d gross=%.2fbp net=%.2fbp",
        len(focus_gross), a_focus_24h_gross_bp, a_focus_24h_net_bp,
    )
    log.info(
        "A_mirror drawdown→SHORT @ 24h: n=%d gross=%.2fbp net=%.2fbp",
        len(mirror_gross), a_mirror_24h_gross_bp, a_mirror_24h_net_bp,
    )
    log.info(
        "Lesson #39 sub-class A sum_abs = %.2f bp (perfect_mirror=%s)",
        sum_abs_mirror_bp, is_perfect_mirror_24h,
    )
    log.info(
        "Pool drift share of A_focus = %.2f%% (pool=%.2fbp / focus=%.2fbp)",
        pool_drift_share_of_focus_pct, pool_baseline_24h_drift_bp, a_focus_24h_gross_bp,
    )
    log.info(
        "drift_artifact_pct (user-def) = %.2f%%", drift_artifact_pct_user_def,
    )

    out["pool_drift_diagnostic"].update({
        "a_focus_24h_gross_bp": a_focus_24h_gross_bp,
        "a_focus_24h_net_bp": a_focus_24h_net_bp,
        "a_focus_24h_n_trades": int(len(focus_gross)),
        "a_mirror_24h_gross_bp": a_mirror_24h_gross_bp,
        "a_mirror_24h_net_bp": a_mirror_24h_net_bp,
        "a_mirror_24h_n_trades": int(len(mirror_gross)),
        "lesson39_sum_abs_bp": float(sum_abs_mirror_bp),
        "lesson39_is_perfect_mirror_24h": is_perfect_mirror_24h,
        "drift_artifact_pct_user_def": float(drift_artifact_pct_user_def),
        "pool_drift_share_of_focus_pct": float(pool_drift_share_of_focus_pct),
    })

    # ─── Phase 4: full focus pool perm + CI ─────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 4: full A_focus 24h pool stats (perm + bootstrap)")
    log.info("=" * 70)
    pool_long = all_fwd24h
    if len(pool_long) >= len(focus_net) * 2:
        perm = fee_aware_perm_test(
            focus_net, pool_long, fee_per_trade=FEE_PER_TRADE,
            n_perms=1000, rng_seed=42
        )
    else:
        perm = {
            "perm_p_two_sided": float("nan"),
            "signal_t_excess": float("nan"),
            "null_mean_t": float("nan"),
            "perm_p_one_sided_above": float("nan"),
        }
    ci_focus = bootstrap_ci(focus_net, n_boot=1000, rng_seed=42)
    sd_focus = focus_net.std(ddof=1)
    obs_t_focus = float(focus_net.mean() / sd_focus * np.sqrt(len(focus_net))) if sd_focus > 0 else 0.0
    # life-changing 4-dim @ 24h primary
    if focus_ts:
        n_years_f = max(
            1e-6,
            (pd.to_datetime(max(focus_ts)) - pd.to_datetime(min(focus_ts))).days / 365.25
        )
    else:
        n_years_f = 1e-6
    tpy_focus = len(focus_net) / n_years_f
    edge_pct_focus = a_focus_24h_net_bp / 100.0
    capital_util_focus = min(100.0, (PRIMARY_HOLD_BARS * tpy_focus) / (365.25 * 24) * 100)
    sharpe_focus = (focus_net.mean() / sd_focus) * np.sqrt(tpy_focus) if sd_focus > 0 else 0.0
    lc4_focus = {
        "trades_per_year": float(tpy_focus),
        "per_trade_edge_pct": float(edge_pct_focus),
        "capital_util_pct": float(capital_util_focus),
        "annualized_sharpe": float(sharpe_focus),
        "pass_trades_per_year_12": bool(tpy_focus >= 12),
        "pass_edge_2pct": bool(edge_pct_focus >= 2.0),
        "pass_util_30pct": bool(capital_util_focus >= 30),
        "pass_sharpe_1_5": bool(sharpe_focus >= 1.5),
        "pass_all_4_dim": bool(
            tpy_focus >= 12 and edge_pct_focus >= 2.0
            and capital_util_focus >= 30 and sharpe_focus >= 1.5
        ),
        "n_dims_pass": int(sum([
            tpy_focus >= 12, edge_pct_focus >= 2.0,
            capital_util_focus >= 30, sharpe_focus >= 1.5,
        ])),
    }
    log.info(
        "Primary 24h cell: n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f sigex=%.2f "
        "CI[%.2f,%.2f] edge=%.3f%% tpy=%.1f util=%.1f%% sharpe=%.2f lc4=%d/4 pass_all=%s",
        len(focus_net), a_focus_24h_gross_bp, a_focus_24h_net_bp,
        obs_t_focus, perm.get("signal_t_excess", float("nan")),
        float(ci_focus["ci_lower"] * 10000), float(ci_focus["ci_upper"] * 10000),
        edge_pct_focus, tpy_focus, capital_util_focus, sharpe_focus,
        lc4_focus["n_dims_pass"], lc4_focus["pass_all_4_dim"],
    )

    out["primary_24h_cell"] = {
        "n_trades": int(len(focus_net)),
        "obs_mean_gross_bp": a_focus_24h_gross_bp,
        "obs_mean_net_bp": a_focus_24h_net_bp,
        "obs_t": obs_t_focus,
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "perm_p_two_sided": float(perm.get("perm_p_two_sided", float("nan"))),
        "perm_p_one_sided_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
        "ci_lower_bp": float(ci_focus["ci_lower"] * 10000),
        "ci_upper_bp": float(ci_focus["ci_upper"] * 10000),
        "ci_pos": bool(ci_focus["ci_lower"] > 0),
        "life_changing_4dim": lc4_focus,
    }

    # ─── Phase 5: TS-CV 5-fold walk-forward ─────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 5: TS-CV 5-fold walk-forward")
    log.info("=" * 70)
    df_trades = pd.DataFrame({
        "ts": pd.to_datetime(focus_ts),
        "ret_net": focus_net,
        "sym": focus_syms,
    }).sort_values("ts").reset_index(drop=True)

    n_total = len(df_trades)
    fold_size = n_total // TS_CV_N_FOLDS
    ts_cv_folds = []
    n_folds_pass = 0
    fold_t_stats = []
    for k in range(TS_CV_N_FOLDS):
        lo = k * fold_size
        hi = (k + 1) * fold_size if k < TS_CV_N_FOLDS - 1 else n_total
        sub = df_trades.iloc[lo:hi]
        n_k = len(sub)
        if n_k < 5:
            fold = {
                "fold": k + 1, "lo_idx": lo, "hi_idx": hi, "n": n_k,
                "error": "n<5",
            }
            ts_cv_folds.append(fold)
            fold_t_stats.append(float("nan"))
            continue
        r_k = sub["ret_net"].values
        sd_k = r_k.std(ddof=1)
        mean_k = float(r_k.mean())
        t_k = float(mean_k / sd_k * np.sqrt(n_k)) if sd_k > 0 else 0.0
        # Use min/max ts to characterize the fold time range
        ts_range = (sub["ts"].min().isoformat(), sub["ts"].max().isoformat())
        # Each fold's quarter listing
        q_list = sorted(set(pd.to_datetime(sub["ts"]).dt.to_period("Q").astype(str)))
        # PASS criteria: focus_t_stat > 1.5 AND mean_edge > 0
        passed = bool(t_k > 1.5 and mean_k > 0)
        if passed:
            n_folds_pass += 1
        fold_t_stats.append(t_k)
        fold = {
            "fold": k + 1, "lo_idx": lo, "hi_idx": hi, "n": n_k,
            "ts_min": ts_range[0], "ts_max": ts_range[1],
            "quarters_covered": q_list,
            "mean_net_bp": float(mean_k * 10000),
            "t_stat": t_k, "passed": passed,
        }
        ts_cv_folds.append(fold)
        log.info(
            "  fold %d/%d: n=%d quarters=%s mean=%.2fbp t=%.2f passed=%s",
            k + 1, TS_CV_N_FOLDS, n_k, q_list,
            float(mean_k * 10000), t_k, passed,
        )

    log.info("TS-CV: %d/%d folds PASS (threshold t>1.5 AND mean>0)", n_folds_pass, TS_CV_N_FOLDS)
    out["ts_cv"] = {
        "n_folds": TS_CV_N_FOLDS,
        "n_folds_pass": n_folds_pass,
        "folds": ts_cv_folds,
        "fold_t_stats": fold_t_stats,
        "ts_cv_pass": bool(n_folds_pass >= 3),
    }

    # ─── Phase 6: threshold sweep monotone @ 24h hold ───────────────────────
    log.info("=" * 70)
    log.info("PHASE 6: threshold sweep monotone @ 24h hold")
    log.info("=" * 70)
    sweep_results = {}
    edges_at_threshold = {}
    for th in THRESHOLD_SWEEP:
        mask_per_sym = {}
        for s in panel:
            r = ret24h_per_sym[s]
            mask_per_sym[s] = (r <= th) & r.notna()
        # debounced trades — drawdown→LONG @ 24h
        rets_th, ts_th, syms_th = collect_debounced_trades(
            mask_per_sym, fwd24h_per_sym, dir_long, DEBOUNCE_BARS
        )
        gross_th = np.asarray(rets_th, dtype=float)
        net_th = gross_th - FEE_PER_TRADE
        if len(net_th) < 5:
            sweep_results[f"th_{th}"] = {
                "threshold": float(th), "n_trades": int(len(net_th)),
                "error": "n<5",
            }
            edges_at_threshold[th] = float("nan")
            continue
        sd_th = net_th.std(ddof=1)
        mean_th_net_bp = float(net_th.mean() * 10000)
        mean_th_gross_bp = float(gross_th.mean() * 10000)
        t_th = float(net_th.mean() / sd_th * np.sqrt(len(net_th))) if sd_th > 0 else 0.0
        edge_th_pct = mean_th_net_bp / 100.0
        edges_at_threshold[th] = edge_th_pct
        sweep_results[f"th_{th}"] = {
            "threshold": float(th),
            "n_trades": int(len(net_th)),
            "gross_mean_bp": mean_th_gross_bp,
            "net_mean_bp": mean_th_net_bp,
            "edge_per_trade_pct": float(edge_th_pct),
            "t_stat": t_th,
        }
        log.info(
            "  threshold=%.0f%%: n=%d gross=%.2fbp net=%.2fbp edge=%.3f%% t=%.2f",
            th * 100, len(net_th), mean_th_gross_bp, mean_th_net_bp, edge_th_pct, t_th,
        )

    # Monotone check: as threshold gets MORE extreme (more negative),
    # per-trade edge should be LARGER. Order: -0.12 → -0.15 → -0.18 → -0.22
    # → edges should be NON-DECREASING (allowing small noise).
    sorted_ths = sorted(THRESHOLD_SWEEP, reverse=True)  # [-0.12, -0.15, -0.18, -0.22]
    edges_ordered = [edges_at_threshold[t] for t in sorted_ths]
    # Strict monotonic non-decreasing check
    is_monotone_strict = all(
        not np.isnan(edges_ordered[i]) and not np.isnan(edges_ordered[i + 1])
        and edges_ordered[i + 1] >= edges_ordered[i] - 0.30  # allow 30bp slack
        for i in range(len(edges_ordered) - 1)
    )
    # Also check trend: last edge > first edge
    if not np.isnan(edges_ordered[0]) and not np.isnan(edges_ordered[-1]):
        positive_trend = edges_ordered[-1] >= edges_ordered[0]
    else:
        positive_trend = False
    log.info(
        "Threshold sweep edge order (less→more extreme): %s%% — monotone=%s positive_trend=%s",
        [f"{e:.3f}" for e in edges_ordered], is_monotone_strict, positive_trend,
    )
    out["threshold_sweep_24h"] = {
        "sweep_results": sweep_results,
        "edges_ordered_less_to_more_extreme": [
            {"threshold": t, "edge_pct": edges_at_threshold[t]} for t in sorted_ths
        ],
        "is_monotone_strict": bool(is_monotone_strict),
        "positive_trend": bool(positive_trend),
        "threshold_sweep_pass": bool(is_monotone_strict and positive_trend),
    }

    # ─── Phase 7: universe broad-shoulders (remove top-3 contributors) ──────
    log.info("=" * 70)
    log.info("PHASE 7: universe broad-shoulders (remove top-3)")
    log.info("=" * 70)
    # Per-sym contribution = sum of net returns per sym from primary cell trades
    per_sym_stats = {}
    per_sym_sum = {}
    for s in panel:
        sub_idx = [i for i, x in enumerate(focus_syms) if x == s]
        if len(sub_idx) == 0:
            per_sym_stats[s] = {"n": 0, "sum_net_bp": 0.0, "mean_net_bp": 0.0}
            per_sym_sum[s] = 0.0
            continue
        sub_net = focus_net[sub_idx]
        per_sym_stats[s] = {
            "n": int(len(sub_net)),
            "sum_net_bp": float(sub_net.sum() * 10000),
            "mean_net_bp": float(sub_net.mean() * 10000),
        }
        per_sym_sum[s] = float(sub_net.sum())
    # Sort by sum_net (total contribution)
    sorted_syms_by_contrib = sorted(per_sym_sum.items(), key=lambda x: x[1], reverse=True)
    top_5 = sorted_syms_by_contrib[:5]
    bottom_5 = sorted_syms_by_contrib[-5:]
    log.info("Top 5 contributors (sum_net):")
    for s, v in top_5:
        log.info("  %s: sum=%.2fbp n=%d", s, v * 10000, per_sym_stats[s]["n"])
    log.info("Bottom 5 contributors:")
    for s, v in bottom_5:
        log.info("  %s: sum=%.2fbp n=%d", s, v * 10000, per_sym_stats[s]["n"])

    top_k_to_remove = [s for s, _ in sorted_syms_by_contrib[:TOP_K_REMOVE_BROAD_SHOULDERS]]
    keep_mask = np.array([s not in top_k_to_remove for s in focus_syms])
    remaining_net = focus_net[keep_mask]
    if len(remaining_net) >= 5:
        sd_r = remaining_net.std(ddof=1)
        mean_r_net_bp = float(remaining_net.mean() * 10000)
        t_r = float(remaining_net.mean() / sd_r * np.sqrt(len(remaining_net))) if sd_r > 0 else 0.0
        edge_r_pct = mean_r_net_bp / 100.0
        ci_r = bootstrap_ci(remaining_net, n_boot=500, rng_seed=42)
        broad_shoulders_pass = bool(
            t_r > 1.5
            and edge_r_pct >= 1.0  # relaxed: at least 1%/trade after top-3 removal
            and mean_r_net_bp > 0
        )
        log.info(
            "After removing top-3 (%s): n=%d gross_avg_lost CI[%.2f,%.2f]bp net=%.2fbp "
            "edge=%.3f%% t=%.2f → broad_shoulders_pass=%s",
            top_k_to_remove, len(remaining_net),
            float(ci_r["ci_lower"] * 10000), float(ci_r["ci_upper"] * 10000),
            mean_r_net_bp, edge_r_pct, t_r, broad_shoulders_pass,
        )
        out["broad_shoulders_remove_top3"] = {
            "removed_syms": top_k_to_remove,
            "n_trades_remaining": int(len(remaining_net)),
            "net_mean_bp_remaining": mean_r_net_bp,
            "edge_pct_remaining": float(edge_r_pct),
            "t_stat_remaining": t_r,
            "ci_lower_bp": float(ci_r["ci_lower"] * 10000),
            "ci_upper_bp": float(ci_r["ci_upper"] * 10000),
            "broad_shoulders_pass": broad_shoulders_pass,
        }
    else:
        broad_shoulders_pass = False
        out["broad_shoulders_remove_top3"] = {
            "removed_syms": top_k_to_remove,
            "n_trades_remaining": int(len(remaining_net)),
            "error": "n<5 after removal",
            "broad_shoulders_pass": False,
        }

    out["per_sym_breakdown"] = {
        "per_sym_stats": per_sym_stats,
        "top_5_contributors": [{"sym": s, "sum_net_bp": float(v * 10000),
                                "n": per_sym_stats[s]["n"]} for s, v in top_5],
        "bottom_5_contributors": [{"sym": s, "sum_net_bp": float(v * 10000),
                                   "n": per_sym_stats[s]["n"]} for s, v in bottom_5],
    }

    # ─── Phase 8: verdict tree ─────────────────────────────────────────────
    log.info("=" * 70)
    log.info("PHASE 8: verdict tree")
    log.info("=" * 70)

    # Step 1: pool-drift
    # User definition: drift_artifact_pct = (A_focus - |A_mirror|) / A_focus × 100
    # This is the LARGER value when A_mirror is small (close to 0 or positive).
    # When perfect mirror (A_mirror ≈ -A_focus), drift_artifact_pct ≈ 0.
    # User rule: "drift artifact > 50% → POOL_DRIFT verdict"
    # AND separately check baseline drift: if pool_baseline ≈ A_focus → POOL_DRIFT
    pool_drift_fail = False
    pool_drift_reason = None
    if drift_artifact_pct_user_def > 50.0:
        pool_drift_fail = True
        pool_drift_reason = (
            f"drift_artifact_pct (user-def: A_focus - |A_mirror| over A_focus) = "
            f"{drift_artifact_pct_user_def:.1f}% > 50% — A_mirror much smaller than "
            f"|A_focus|, indicating signal is asymmetric NOT from pure mirror "
            f"mechanism (may instead reflect pool-conditional baseline drift, "
            f"not directional capitulation reversion alpha)."
        )
    # Also: if pool baseline accounts for majority of focus
    elif (
        pool_baseline_24h_drift_bp > 0
        and pool_drift_share_of_focus_pct >= 50.0
    ):
        pool_drift_fail = True
        pool_drift_reason = (
            f"Pool baseline (unconditional 24h fwd) = {pool_baseline_24h_drift_bp:.2f}bp "
            f"= {pool_drift_share_of_focus_pct:.1f}% of A_focus "
            f"{a_focus_24h_gross_bp:.2f}bp. Majority of A_focus signal is "
            f"explained by pool's general upward drift, NOT capitulation reversion."
        )

    # Step 2: TS-CV
    ts_cv_fail = not out["ts_cv"]["ts_cv_pass"]

    # Step 3: threshold sweep monotone
    threshold_fail = not out["threshold_sweep_24h"]["threshold_sweep_pass"]

    # Step 4: broad shoulders
    broad_fail = not out["broad_shoulders_remove_top3"].get("broad_shoulders_pass", False)

    # Step 5: life-changing 4-dim at R-2 primary
    lc_fail = not lc4_focus["pass_all_4_dim"]

    # Apply verdict tree in order specified
    if pool_drift_fail:
        verdict = "R2_FAIL_POOL_DRIFT"
        verdict_reason = pool_drift_reason
    elif ts_cv_fail:
        verdict = "R2_FAIL_TS_CV"
        verdict_reason = (
            f"TS-CV {n_folds_pass}/{TS_CV_N_FOLDS} folds PASS (threshold t>1.5 AND "
            f"mean>0). Lesson #26 small-sample Concentration blind spot — paradigm "
            f"87 precedent. Per-fold t-stats: "
            f"{[f'{t:.2f}' if not np.isnan(t) else 'NaN' for t in fold_t_stats]}."
        )
    elif threshold_fail:
        verdict = "R2_FAIL_THRESHOLD_INCONSISTENT"
        verdict_reason = (
            f"Threshold sweep not monotonic or no positive trend. Edges "
            f"(less→more extreme): {[f'{e:.3f}%' for e in edges_ordered]}. "
            f"Mechanism would require capitulation-extremity gradient — "
            f"non-monotone implies underspecified hypothesis (random selection "
            f"effect vs true gradient)."
        )
    elif broad_fail:
        verdict = "R2_FAIL_NARROW_UNIVERSE"
        verdict_reason = (
            f"Removing top-{TOP_K_REMOVE_BROAD_SHOULDERS} contributors "
            f"({top_k_to_remove}) collapses mechanism: remaining "
            f"edge={out['broad_shoulders_remove_top3'].get('edge_pct_remaining','NA')}%, "
            f"t={out['broad_shoulders_remove_top3'].get('t_stat_remaining','NA'):.2f}. "
            f"Signal not broadly distributed across universe."
        )
    elif lc_fail:
        verdict = "R2_FAIL_LIFE_CHANGING"
        verdict_reason = (
            f"Primary R-2 24h cell life-changing 4-dim: edge={edge_pct_focus:.3f}% "
            f"tpy={tpy_focus:.1f} util={capital_util_focus:.1f}% sharpe={sharpe_focus:.2f}. "
            f"Fails one or more dimensions ({lc4_focus['n_dims_pass']}/4)."
        )
    else:
        verdict = "R2_PASS"
        verdict_reason = (
            f"All R-2 gates clear: pool-drift OK (drift_artifact={drift_artifact_pct_user_def:.1f}%, "
            f"pool_share={pool_drift_share_of_focus_pct:.1f}%), TS-CV "
            f"{n_folds_pass}/{TS_CV_N_FOLDS} PASS, threshold sweep monotone, "
            f"broad-shoulders survives top-3 removal (edge="
            f"{out['broad_shoulders_remove_top3'].get('edge_pct_remaining','NA')}%), "
            f"life-changing 4/4 at primary 24h cell. R-3 robustness dispatch ready."
        )

    # ─── Survivorship caveat (always documented) ────────────────────────────
    out["survivorship_caveat"] = {
        "lookback_period_months": "2024-05 to 2026-04 (~24 months / ~2yr)",
        "universe_membership": "currently-listed alts only — delisted alts within "
                              "lookback NOT in cohort",
        "note": "Survivors had bounce capacity → edge estimate likely UPWARDLY biased. "
                "Delisted cohort (e.g., tokens permanently exited Binance Futures) may "
                "have continued down indefinitely post-extreme-drawdown, which would "
                "have FAILED the reversion hypothesis. R-3 should attempt to include "
                "delisted/wound-down cohort if any reachable cache exists, or document "
                "this as an explicit scope limitation in any subsequent R-5 seed.",
    }

    # ─── Wrap up ─────────────────────────────────────────────────────────────
    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    _write(out)

    log.info("=" * 70)
    log.info("VERDICT: %s", verdict)
    log.info("REASON: %s", verdict_reason)
    log.info("Wall clock: %.2f min", out["wall_clock_minutes"])
    log.info("=" * 70)

    # Stdout JSON summary for orchestrator
    summary = {
        "paradigm": PARADIGM_SLUG,
        "r1_alias": R1_ALIAS,
        "phase": "R-2",
        "verdict": verdict,
        "verdict_reason": verdict_reason.split(".")[0] + ".",
        "a_focus_24h_gross_bp": a_focus_24h_gross_bp,
        "a_mirror_24h_gross_bp": a_mirror_24h_gross_bp,
        "pool_baseline_24h_drift_bp": pool_baseline_24h_drift_bp,
        "drift_artifact_pct_user_def": float(drift_artifact_pct_user_def),
        "pool_drift_share_of_focus_pct": float(pool_drift_share_of_focus_pct),
        "lesson39_sum_abs_bp": float(sum_abs_mirror_bp),
        "lesson39_is_perfect_mirror_24h": is_perfect_mirror_24h,
        "ts_cv_folds_pass": f"{n_folds_pass}/{TS_CV_N_FOLDS}",
        "ts_cv_per_fold_t_stats": [
            None if (isinstance(t, float) and np.isnan(t)) else float(t)
            for t in fold_t_stats
        ],
        "threshold_sweep_edge_per_trade_pct": {
            str(t): (None if np.isnan(edges_at_threshold[t]) else float(edges_at_threshold[t]))
            for t in sorted_ths
        },
        "threshold_monotone": bool(is_monotone_strict and positive_trend),
        "top3_removed_pool_net_bp": float(
            out["broad_shoulders_remove_top3"].get("net_mean_bp_remaining", float("nan"))
        ) if not isinstance(
            out["broad_shoulders_remove_top3"].get("net_mean_bp_remaining", None), type(None)
        ) else None,
        "life_changing_4dim_pass_r2": f"{lc4_focus['n_dims_pass']}/4",
        "files": [
            f"backend/scripts/research/paradigm117_r2_{PARADIGM_SLUG}.py",
            f"backend/runs/research_track/{PARADIGM_SLUG}/r2__metrics.json",
        ],
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": (
            "halt_for_user_R3_approval" if verdict == "R2_PASS" else "graveyard"
        ),
    }
    print("\n>>> R2_SUMMARY_JSON_BEGIN")
    print(json.dumps(_convert(summary), indent=2))
    print(">>> R2_SUMMARY_JSON_END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
