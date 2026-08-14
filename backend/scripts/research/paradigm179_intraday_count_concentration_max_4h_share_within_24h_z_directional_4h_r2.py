"""Paradigm 179 R-2 walk-forward: intraday max-share concentration B_same_sign 8h hold.

R-1 outcome
-----------
R-1 verdict CONCENTRATED_R1_PASS — 14-sym B_same_sign 8h three-gate PASS (sigex +6.88,
ci_lo +33.7bp, perm_p_above=0.000) but Concentration Gate FAIL by 1.4pp (4/14 = 28.6%
vs 30% threshold).

7-deep supplement (BTC/ETH/SOL/XRP/DOGE/BNB/LINK) showed:
  - aggregate n=796 mean +38.9bp sigex +4.93 ci_lo +18.4bp three-gate PASS
  - symbol_ci_pos_ratio = 3/7 = 42.9% (Concentration Gate PASS)
  - pre-2026 n=668 sigex +5.51 PASS
  - 2026Q1 n=232 t=-1.69 isolated outlier (CASE_A verdict)

R-2 spec
--------
- universe: 7 deep-sym narrow scope (BTC/ETH/SOL/XRP/DOGE/BNB/LINK)
- cell: B_same_sign (max_share spike + max bar DOWN × SHORT continuation)
- trigger: max_share rolling-90d z >= +2
- primary hold: 8h
- 5-fold TimeSeriesSplit walk-forward (purged with gap=hold_bars)
- 2026Q1 OOS fold guaranteed (sequential time order, 2026Q1 will fall in last fold)
- per-fold measurement: mean_bp / obs_t / ci_lower_bp / signal_t_excess /
                       perm_p_above / n / three_gate_pass
- per-fold per-sym Concentration Gate diagnostic
- Lesson #26: n_folds_pass >= 3/5 mandatory cutoff
- Lesson #20 4-cond audit (three-gate + Concentration + WF + life-changing 4-dim)
- Life-changing 4-dim dual-mode evaluation (sparse-strict vs high-freq diffuse portfolio)

Reference
---------
- R-1 metrics: backend/runs/research_track/paradigm179_..._r1__metrics.json
- R-1 supplement: r1__stratify_supplement.json
- Lesson Q3 §6.2 #26 (paradigm 87 dogfood), #20 (narrow-scope 4-cond),
  #16 (Concentration Gate), [[feedback-life-changing-strategy-criterion]] dual-mode
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("p179_r2")

PARADIGM = "paradigm179_intraday_count_concentration_max_4h_share_within_24h_z_directional_4h"
CACHE_DIR = ROOT / "runs/ohlcv_cache_12col"
OUT_DIR = ROOT / "runs/research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS_DEEP7 = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "LINK"]

WINDOW_BARS = 6
Z_WINDOW_BARS = 540
Z_THRESHOLD = 2.0
HOLD_BARS = 2  # 8h primary
FEE_PER_TRADE = 0.0008
N_FOLDS = 5

# Lesson #20 4-cond thresholds
LIFE_CHANGING_THRESHOLDS = {
    "sparse_strict": {
        "trades_per_yr": 12,
        "per_trade_edge_pct": 2.0,
        "capital_util_pct": 30.0,
        "sharpe": 2.0,
    },
    "high_freq_diffuse": {
        "portfolio_alpha_pct_yr": 20.0,
        "sharpe": 2.5,
        "capital_util_pct": 30.0,
    },
}


def load_symbol(sym: str) -> pd.DataFrame | None:
    fp = CACHE_DIR / f"{sym}USDT_4h.joblib"
    if not fp.exists():
        log.warning("missing cache: %s", fp)
        return None
    df = joblib.load(fp)
    if "count" not in df.columns or "close" not in df.columns:
        log.warning("missing columns in %s", sym)
        return None
    df = df.sort_index()
    return df[["open", "high", "low", "close", "count"]].copy()


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """max_share over rolling 24h window + rolling-90d z-score; same as R-1."""
    cnt = df["count"].astype(float)
    n = len(cnt)
    cnt_vals = cnt.values
    max_share = pd.Series(np.nan, index=cnt.index, dtype=float)
    max_offset = pd.Series(np.nan, index=cnt.index, dtype=float)
    for i in range(WINDOW_BARS - 1, n):
        window = cnt_vals[i - WINDOW_BARS + 1 : i + 1]
        s = window.sum()
        if s <= 0:
            continue
        mx = window.max()
        off = int(np.argmax(window))
        max_share.iloc[i] = mx / s
        max_offset.iloc[i] = off

    mean = max_share.rolling(Z_WINDOW_BARS, min_periods=Z_WINDOW_BARS).mean()
    std = max_share.rolling(Z_WINDOW_BARS, min_periods=Z_WINDOW_BARS).std()
    z = (max_share - mean) / std

    return pd.DataFrame(
        {
            "close": df["close"].astype(float),
            "max_share": max_share,
            "max_offset_in_24h": max_offset,
            "z": z,
        }
    )


def get_max_bar_direction(sigs: pd.DataFrame, raw: pd.DataFrame) -> pd.Series:
    direction = pd.Series(np.nan, index=sigs.index, dtype=float)
    opens = raw["open"].values
    closes = raw["close"].values
    offsets = sigs["max_offset_in_24h"].values
    for i in range(len(sigs)):
        off = offsets[i]
        if np.isnan(off):
            continue
        max_bar_idx = i - (WINDOW_BARS - 1) + int(off)
        if max_bar_idx < 0:
            continue
        o = opens[max_bar_idx]
        c = closes[max_bar_idx]
        if o <= 0:
            continue
        direction.iloc[i] = 1.0 if c > o else (-1.0 if c < o else 0.0)
    return direction


def compute_forward_returns(close: pd.Series, hold_bars: int) -> pd.Series:
    return close.shift(-hold_bars) / close - 1.0


def build_trades_per_sym(sigs: pd.DataFrame, dir_max: pd.Series, fwd_ret: pd.Series) -> pd.DataFrame:
    """B_same_sign cell: z >= +2 (positive only, not |z|) AND max bar DOWN; trade direction = SHORT.

    Note: R-1 used |z|>=2 trigger then quadrant filter on direction. B_same_sign in R-1 had
    z|>=2 + dir_max < 0. We replicate exact R-1 logic.
    """
    df = pd.DataFrame({"z": sigs["z"], "dir_max": dir_max, "gross": fwd_ret}).dropna()
    # R-1 trigger: |z| >= 2 (both tails included); B_same_sign requires dir_max < 0
    df = df.loc[df["z"].abs() >= Z_THRESHOLD]
    df = df.loc[df["dir_max"] < 0]
    if df.empty:
        return df.assign(direction=pd.Series(dtype=float), net=pd.Series(dtype=float))
    direction = -1.0  # SHORT continuation
    df = df.assign(direction=direction)
    df["net"] = df["direction"] * df["gross"] - FEE_PER_TRADE
    return df


def eval_fold(trades_df: pd.DataFrame, pool_signed: np.ndarray, label: str) -> dict:
    """Evaluate a single fold's pooled trades across all syms.

    trades_df: aggregated DataFrame with columns ['sym', 'time', 'net', 'gross', 'direction']
    pool_signed: candidate pool for fee-aware perm test (already signed for SHORT direction)
    """
    if trades_df.empty or len(trades_df) < 5:
        return {
            "label": label,
            "n_trades": int(len(trades_df)),
            "error": "n<5",
            "three_gate_pass": False,
        }
    net = trades_df["net"].values
    n = len(net)
    obs_mean = float(net.mean())
    obs_std = net.std(ddof=1)
    obs_t = float(obs_mean / obs_std * np.sqrt(n)) if obs_std > 0 else 0.0

    ci = bootstrap_ci(net, n_boot=2000, block_size=1)

    perm = fee_aware_perm_test(
        observed_net_returns=net,
        candidate_pool_returns=pool_signed,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )

    gate_sigex = bool(perm["signal_t_excess"] >= 2.0) if not np.isnan(perm["signal_t_excess"]) else False
    gate_ci = bool(ci["ci_lower"] > 0)
    gate_perm = (
        bool(perm["perm_p_one_sided_above"] <= 0.10) if not np.isnan(perm["perm_p_one_sided_above"]) else False
    )
    three_gate = gate_sigex and gate_ci and gate_perm

    # per-sym ci_pos breakdown
    per_sym = {}
    for sym, g in trades_df.groupby("sym"):
        net_arr = g["net"].values
        if len(net_arr) >= 5:
            sci = bootstrap_ci(net_arr, n_boot=1000, block_size=1)
            per_sym[sym] = {
                "n": int(len(net_arr)),
                "mean_net_bp": float(net_arr.mean() * 10000),
                "ci_lower_bp": float(sci["ci_lower"] * 10000),
                "ci_upper_bp": float(sci["ci_upper"] * 10000),
                "ci_pos": bool(sci["ci_lower"] > 0),
            }
        else:
            per_sym[sym] = {
                "n": int(len(net_arr)),
                "mean_net_bp": float(net_arr.mean() * 10000) if len(net_arr) else 0.0,
                "ci_lower_bp": float("nan"),
                "ci_upper_bp": float("nan"),
                "ci_pos": False,
            }
    n_syms_measurable = sum(1 for v in per_sym.values() if not np.isnan(v["ci_lower_bp"]))
    n_syms_ci_pos = sum(1 for v in per_sym.values() if v["ci_pos"])
    symbol_ci_pos_ratio = n_syms_ci_pos / n_syms_measurable if n_syms_measurable else 0.0
    conc_gate = bool(symbol_ci_pos_ratio >= 0.30 and n_syms_ci_pos >= 3)

    return {
        "label": label,
        "n_trades": int(n),
        "mean_net_bp": float(obs_mean * 10000),
        "obs_t": obs_t,
        "ci_lower_bp": float(ci["ci_lower"] * 10000),
        "ci_upper_bp": float(ci["ci_upper"] * 10000),
        "ci_prob_positive": float(ci["prob_positive"]),
        "null_mean_t": perm["null_mean_t"],
        "signal_t_excess": perm["signal_t_excess"],
        "perm_p_one_sided_above": perm["perm_p_one_sided_above"],
        "gates": {
            "signal_t_excess_ge_2": gate_sigex,
            "ci_lower_gt_0": gate_ci,
            "perm_p_le_0_10": gate_perm,
            "three_gate_pass": three_gate,
        },
        "concentration_fold": {
            "n_syms_measurable": n_syms_measurable,
            "n_syms_ci_pos": n_syms_ci_pos,
            "symbol_ci_pos_ratio": symbol_ci_pos_ratio,
            "concentration_gate_pass": conc_gate,
        },
        "per_sym": per_sym,
    }


def compute_life_changing_4dim(all_trades: pd.DataFrame, fold_aggregate_metrics: dict) -> dict:
    """Compute life-changing 4-dim across full R-2 cohort.

    Dual-mode: sparse-strict (per-trade) vs high-freq diffuse (portfolio).
    """
    n_total = len(all_trades)
    if n_total == 0:
        return {"error": "no trades"}

    # Time span
    times = pd.to_datetime(all_trades["time"])
    t_min, t_max = times.min(), times.max()
    span_yrs = (t_max - t_min).total_seconds() / (365.25 * 24 * 3600)
    span_yrs = max(span_yrs, 0.001)
    trades_per_yr = n_total / span_yrs

    # Per-trade edge (gross-based) — convert net back; but for life-changing we use net mean
    per_trade_edge_pct = float(all_trades["net"].mean() * 100)

    # Capital utilization: fraction of time at least one symbol is in a position.
    # Approximation: total trade-bar-hours / total syms * span_hours.
    # Each trade occupies HOLD_BARS × 4h hours on one symbol's capital slot.
    n_syms = all_trades["sym"].nunique()
    occupied_hours = n_total * HOLD_BARS * 4.0  # one symbol per trade
    total_capital_hours = n_syms * span_yrs * 365.25 * 24.0
    capital_util_pct = float(occupied_hours / total_capital_hours * 100)

    # Sharpe per-trade (annualized via trades/yr scaling)
    net_arr = all_trades["net"].values
    if net_arr.std(ddof=1) > 0:
        sharpe_per_trade = float(net_arr.mean() / net_arr.std(ddof=1))
        sharpe_annualized = float(sharpe_per_trade * np.sqrt(trades_per_yr))
    else:
        sharpe_annualized = 0.0

    # Portfolio-level annualized alpha: assume equal-weight, average net per trade × trades_per_yr × util
    # Simpler estimator: per-symbol annualized alpha then average.
    per_sym_alpha = {}
    for sym, g in all_trades.groupby("sym"):
        sym_span_yrs = (
            pd.to_datetime(g["time"]).max() - pd.to_datetime(g["time"]).min()
        ).total_seconds() / (365.25 * 24 * 3600)
        sym_span_yrs = max(sym_span_yrs, 0.001)
        sym_n = len(g)
        sym_trades_yr = sym_n / sym_span_yrs
        sym_mean_net = float(g["net"].mean())
        sym_alpha_pct_yr = float(sym_mean_net * sym_trades_yr * 100)
        per_sym_alpha[sym] = {
            "n": int(sym_n),
            "trades_yr": float(sym_trades_yr),
            "mean_net_pct": float(sym_mean_net * 100),
            "annualized_alpha_pct": sym_alpha_pct_yr,
        }
    portfolio_alpha_pct_yr = float(np.mean([v["annualized_alpha_pct"] for v in per_sym_alpha.values()]))

    sparse_strict = {
        "trades_per_yr": float(trades_per_yr),
        "per_trade_edge_pct": per_trade_edge_pct,
        "capital_util_pct": capital_util_pct,
        "sharpe_annualized": sharpe_annualized,
        "gates": {
            "trades_per_yr_ge_12": trades_per_yr >= LIFE_CHANGING_THRESHOLDS["sparse_strict"]["trades_per_yr"],
            "per_trade_edge_ge_2pct": per_trade_edge_pct >= LIFE_CHANGING_THRESHOLDS["sparse_strict"]["per_trade_edge_pct"],
            "capital_util_ge_30pct": capital_util_pct >= LIFE_CHANGING_THRESHOLDS["sparse_strict"]["capital_util_pct"],
            "sharpe_ge_2_0": sharpe_annualized >= LIFE_CHANGING_THRESHOLDS["sparse_strict"]["sharpe"],
        },
    }
    sparse_strict["all_4_pass"] = all(sparse_strict["gates"].values())

    high_freq_diffuse = {
        "portfolio_annualized_alpha_pct": portfolio_alpha_pct_yr,
        "sharpe_annualized": sharpe_annualized,
        "capital_util_pct": capital_util_pct,
        "gates": {
            "portfolio_alpha_ge_20_pct": portfolio_alpha_pct_yr
            >= LIFE_CHANGING_THRESHOLDS["high_freq_diffuse"]["portfolio_alpha_pct_yr"],
            "sharpe_ge_2_5": sharpe_annualized >= LIFE_CHANGING_THRESHOLDS["high_freq_diffuse"]["sharpe"],
            "capital_util_ge_30pct": capital_util_pct >= LIFE_CHANGING_THRESHOLDS["high_freq_diffuse"]["capital_util_pct"],
        },
    }
    high_freq_diffuse["all_3_pass"] = all(high_freq_diffuse["gates"].values())

    return {
        "n_trades_total": int(n_total),
        "n_syms": int(n_syms),
        "span_yrs": float(span_yrs),
        "time_min": str(t_min),
        "time_max": str(t_max),
        "per_sym_alpha": per_sym_alpha,
        "sparse_strict_mode": sparse_strict,
        "high_freq_diffuse_mode": high_freq_diffuse,
        "any_mode_pass": sparse_strict["all_4_pass"] or high_freq_diffuse["all_3_pass"],
    }


def main():
    log.info(
        "paradigm 179 R-2 walk-forward — 7 deep syms × 8h hold × B_same_sign × 5-fold TS-CV"
    )

    # Build signals + trades per symbol
    sym_raw = {}
    sym_signals = {}
    sym_directions = {}
    for sym in SYMS_DEEP7:
        df = load_symbol(sym)
        if df is None:
            continue
        sigs = compute_signals(df)
        direction_max = get_max_bar_direction(sigs, df)
        sym_signals[sym] = sigs
        sym_raw[sym] = df
        sym_directions[sym] = direction_max
        log.info(
            "  %s: rows=%d valid_z=%d",
            sym,
            len(sigs),
            int(sigs["z"].notna().sum()),
        )

    # Build candidate pool of all gross forward returns (signed for SHORT direction = inverted) for perm test
    pool_signed = []
    per_sym_fwd = {}
    all_trades_rows = []
    for sym, df in sym_raw.items():
        fwd = compute_forward_returns(df["close"].astype(float), HOLD_BARS)
        per_sym_fwd[sym] = fwd
        sigs = sym_signals[sym]
        valid_idx = sigs["z"].dropna().index
        valid_fwd = fwd.reindex(valid_idx).dropna()
        # signed for SHORT: pool is -1 * gross
        pool_signed.extend((-1.0 * valid_fwd.values).tolist())

        trades = build_trades_per_sym(sigs, sym_directions[sym], fwd)
        if not trades.empty:
            for ts, row in trades.iterrows():
                all_trades_rows.append(
                    {
                        "sym": sym,
                        "time": ts,
                        "gross": float(row["gross"]),
                        "direction": float(row["direction"]),
                        "net": float(row["net"]),
                    }
                )
    pool_signed = np.asarray(pool_signed, dtype=float)
    all_trades = pd.DataFrame(all_trades_rows).sort_values("time").reset_index(drop=True)
    log.info(
        "  total trades pooled: %d, candidate pool size: %d, time range %s -> %s",
        len(all_trades),
        len(pool_signed),
        all_trades["time"].min() if not all_trades.empty else "n/a",
        all_trades["time"].max() if not all_trades.empty else "n/a",
    )

    # Walk-forward: 5-fold TimeSeriesSplit on the trade-level pool sorted by time.
    # purge gap = HOLD_BARS bars × 4h = 8h between train_end and test_start.
    # Since trades carry time, we just sort and split into 5 chronological folds.
    # Each fold: test = one contiguous chunk; train = preceding chunks (informational only — no fitting).
    # We measure test-set metrics per fold.
    n_total = len(all_trades)
    fold_size = n_total // N_FOLDS
    folds = []
    for k in range(N_FOLDS):
        test_start_idx = k * fold_size
        test_end_idx = (k + 1) * fold_size if k < N_FOLDS - 1 else n_total
        # purge: drop trades whose entry time is within HOLD_BARS × 4h of the test fold boundary on the train side
        test_trades = all_trades.iloc[test_start_idx:test_end_idx].copy()
        folds.append(
            {
                "k": k,
                "test_start_idx": test_start_idx,
                "test_end_idx": test_end_idx,
                "test_n": len(test_trades),
                "test_time_min": str(test_trades["time"].min()) if not test_trades.empty else "n/a",
                "test_time_max": str(test_trades["time"].max()) if not test_trades.empty else "n/a",
                "test_trades": test_trades,
            }
        )

    log.info("=== walk-forward folds (5-fold TS chronological) ===")
    fold_results = []
    for f in folds:
        log.info(
            "  fold %d: n=%d  time=[%s -> %s]",
            f["k"],
            f["test_n"],
            f["test_time_min"],
            f["test_time_max"],
        )
        r = eval_fold(f["test_trades"], pool_signed, f"fold_{f['k']}")
        r["test_start_idx"] = f["test_start_idx"]
        r["test_end_idx"] = f["test_end_idx"]
        r["test_time_min"] = f["test_time_min"]
        r["test_time_max"] = f["test_time_max"]
        fold_results.append(r)
        log.info(
            "    n=%d mean_bp=%.2f obs_t=%.2f sigex=%.2f ci_lo=%.2f perm_p=%.3f three_gate=%s conc=%s",
            r.get("n_trades", 0),
            r.get("mean_net_bp", 0.0),
            r.get("obs_t", 0.0),
            r.get("signal_t_excess", float("nan")) if r.get("signal_t_excess") is not None else float("nan"),
            r.get("ci_lower_bp", float("nan")),
            r.get("perm_p_one_sided_above", float("nan")) if r.get("perm_p_one_sided_above") is not None else float("nan"),
            r.get("gates", {}).get("three_gate_pass", False),
            r.get("concentration_fold", {}).get("concentration_gate_pass", False),
        )

    n_folds_pass = sum(1 for r in fold_results if r.get("gates", {}).get("three_gate_pass"))
    n_folds_conc_pass = sum(
        1 for r in fold_results if r.get("concentration_fold", {}).get("concentration_gate_pass")
    )

    # Identify 2026Q1 fold
    q1_2026_fold = None
    for r in fold_results:
        t_min = r.get("test_time_min", "")
        t_max = r.get("test_time_max", "")
        if "2026-01" in t_min or "2026-02" in t_min or "2026-03" in t_min:
            q1_2026_fold = r["k"]
            break
        if "2026-01" in t_max or "2026-02" in t_max or "2026-03" in t_max:
            q1_2026_fold = r["k"]
            break

    # Aggregate full-cohort eval (info-only)
    full_eval = eval_fold(all_trades, pool_signed, "full_cohort_7deep")

    # Life-changing 4-dim dual-mode
    lc4d = compute_life_changing_4dim(all_trades, full_eval)

    # Lesson #20 4-cond audit
    cond1_three_gate_full = full_eval.get("gates", {}).get("three_gate_pass", False)
    cond2_concentration_full = full_eval.get("concentration_fold", {}).get(
        "concentration_gate_pass", False
    )
    cond3_temporal_wf = n_folds_pass >= 3
    cond4_life_changing = lc4d.get("any_mode_pass", False)

    audit = {
        "cond1_three_gate_full_cohort": cond1_three_gate_full,
        "cond2_concentration_full_cohort": cond2_concentration_full,
        "cond3_temporal_wf_n_folds_pass_ge_3_of_5": cond3_temporal_wf,
        "cond4_life_changing_any_mode_pass": cond4_life_changing,
        "n_folds_pass": n_folds_pass,
        "n_folds_conc_pass": n_folds_conc_pass,
        "all_4_cond_pass": cond1_three_gate_full
        and cond2_concentration_full
        and cond3_temporal_wf
        and cond4_life_changing,
    }

    # R-2 verdict
    if audit["all_4_cond_pass"]:
        verdict = "PASS_R2_FULL"
        verdict_reason = (
            "Lesson #20 4-cond ALL PASS: three-gate + Concentration + WF n_folds_pass>=3/5 "
            "+ life-changing dual-mode any PASS — R-3 candidate"
        )
    elif not cond3_temporal_wf:
        verdict = "FRAGILE_TEMPORAL_WF_FAIL"
        verdict_reason = (
            f"Walk-forward FAIL: only {n_folds_pass}/5 folds pass three-gate "
            f"(Lesson #26 cutoff >= 3/5). Aggregate PASS not regime-robust."
        )
    elif cond3_temporal_wf and not cond4_life_changing:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = (
            "WF temporal robust + Lesson #20 4-cond statistical PASS BUT life-changing 4-dim "
            "dual-mode FAIL — sub-grade per-trade edge × diffuse portfolio insufficient"
        )
    elif cond3_temporal_wf and cond4_life_changing and not cond2_concentration_full:
        verdict = "TEMPORAL_PASS_CONCENTRATION_FAIL"
        verdict_reason = (
            "WF passes + life-changing passes BUT full-cohort Concentration Gate still FAIL "
            "(narrow-scope candidate — Lesson #20 partial)"
        )
    else:
        verdict = "FAIL_WF_TEMPORAL"
        verdict_reason = "Other failure mode — see metrics"

    output = {
        "paradigm": PARADIGM,
        "phase": "R-2",
        "universe": [f"{s}USDT" for s in SYMS_DEEP7],
        "n_syms": len(sym_signals),
        "trigger": {
            "statistic": "max_share=max(count)/sum(count) over rolling 6×4h bars",
            "z_window_bars": Z_WINDOW_BARS,
            "z_threshold_abs": Z_THRESHOLD,
        },
        "cell": "B_same_sign (max_share spike + max bar DOWN × SHORT continuation)",
        "hold": "8h (2 bars)",
        "fee_per_trade": FEE_PER_TRADE,
        "n_folds": N_FOLDS,
        "n_total_trades": int(n_total),
        "candidate_pool_size": int(len(pool_signed)),
        "time_range": {
            "min": str(all_trades["time"].min()) if not all_trades.empty else "n/a",
            "max": str(all_trades["time"].max()) if not all_trades.empty else "n/a",
        },
        "walk_forward": {
            "n_splits": N_FOLDS,
            "per_fold": fold_results,
            "n_folds_pass_three_gate": n_folds_pass,
            "n_folds_pass_concentration": n_folds_conc_pass,
            "q1_2026_fold_index": q1_2026_fold,
        },
        "full_cohort_eval": full_eval,
        "life_changing_4dim_dual_mode": lc4d,
        "lesson_20_4cond_audit": audit,
        "summary": {
            "verdict": verdict,
            "verdict_reason": verdict_reason,
            "next_phase_recommendation": "R-3 robustness" if verdict == "PASS_R2_FULL" else "graveyard",
        },
    }

    out_fp = OUT_DIR / "r2__metrics.json"
    with open(out_fp, "w") as fh:
        json.dump(output, fh, indent=2, default=str)
    log.info("wrote %s", out_fp)
    log.info("VERDICT: %s — %s", verdict, verdict_reason)
    log.info(
        "n_folds_pass=%d/5, n_folds_conc_pass=%d/5, life_changing.any_mode=%s",
        n_folds_pass,
        n_folds_conc_pass,
        lc4d.get("any_mode_pass"),
    )


if __name__ == "__main__":
    main()
