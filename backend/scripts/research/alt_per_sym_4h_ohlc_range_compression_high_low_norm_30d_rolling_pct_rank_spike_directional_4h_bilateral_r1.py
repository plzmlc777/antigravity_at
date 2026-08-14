"""paradigm 221 R-1 — alt_per_sym_4h_ohlc_range_compression_high_low_norm_30d_rolling_pct_rank_spike_directional_4h_bilateral

Lesson #40 prescription 2nd 처방 (paradigm 220 R-0 HALT reformulation).

Statistic
---------
range_compression = (high - low) / (high + low)        # bounded [0,1] symmetric distribution
pct_rank_30d = rolling 30d (= 180 bars at 4h) percentile rank of range_compression

Triggers
--------
cell A: pct_rank_30d >= 0.95  → wide bar regime (range share high)
cell B: pct_rank_30d <= 0.05  → compressed bar regime (range share low)

Direction (4-quadrant SNT)
---------------------------
A focus     : cell A × bar UP   × LONG  continuation
A mirror    : cell A × bar UP   × SHORT reversal
B same-sign : cell B × bar DOWN × SHORT continuation (DISJOINT trigger set from A)
B mirror    : cell B × bar DOWN × LONG  reversal     (Lesson #42 22nd dogfood)

Hold sweep : 4h primary + 8h + 12h + 24h
Universe   : 20 alts (paradigm 198 cohort) — exclude BTCUSDT baseline
Substrate  : backend/runs/ohlcv_cache_12col/{SYM}_4h.joblib (2.24yr × 21 syms)

Lesson #69 9-item template compliance.
Lesson #39 sub-class A prescreen (cross-set |A| vs |B| 9th instance).
Item 6 alpha decay 11th operational dogfood (Pattern P1 9th, 2026-era 7th).
Item 9 Life-changing 4-dim STRUCTURAL prescreen 5th operational.
Lesson #42 22nd dogfood (B mirror cell).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("p221_r1")

PARADIGM = (
    "alt_per_sym_4h_ohlc_range_compression_high_low_norm_30d_rolling_pct_rank_"
    "spike_directional_4h_bilateral"
)
OUT_DIR = REPO_ROOT / "runs/research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = REPO_ROOT / "runs/ohlcv_cache_12col"

UNIVERSE_20 = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "DOTUSDT", "ETCUSDT", "ETHUSDT", "FILUSDT", "JUPUSDT",
    "LDOUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "PYTHUSDT",
    "SOLUSDT", "UNIUSDT", "WIFUSDT", "WLDUSDT", "XRPUSDT",
]

ROLL_WINDOW_BARS = 180   # 30d × 6 bars/d
PCT_UPPER = 0.95
PCT_LOWER = 0.05
FEE_PER_TRADE = 0.0008   # 8bp round-trip
HOLD_SWEEP_BARS = [1, 2, 3, 6]      # 4h / 8h / 12h / 24h
PRIMARY_HOLD_BARS = 1                # 4h
N_PERMS = 1000
N_BOOT = 2000


# ---------------------------------------------------------------------------
# Data load
# ---------------------------------------------------------------------------
def load_sym(sym: str) -> pd.DataFrame:
    path = CACHE_DIR / f"{sym}_4h.joblib"
    df = joblib.load(path)
    df = df[["open", "high", "low", "close"]].copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


def build_per_sym() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE_20:
        df = load_sym(sym)
        df["rng_share"] = (df["high"] - df["low"]) / (df["high"] + df["low"])
        df["bar_dir"] = np.sign(df["close"] - df["open"])
        df["pct_rank_30d"] = df["rng_share"].rolling(
            ROLL_WINDOW_BARS, min_periods=ROLL_WINDOW_BARS // 2
        ).rank(pct=True)
        # forward returns
        df["fwd_close"] = df["close"]
        for h in HOLD_SWEEP_BARS:
            df[f"fwd_ret_{h}b"] = df["close"].shift(-h) / df["close"] - 1.0
        out[sym] = df
    return out


# ---------------------------------------------------------------------------
# Quadrant trade generation
# ---------------------------------------------------------------------------
def gen_quadrant(
    per_sym: Dict[str, pd.DataFrame],
    cell: str,            # "A" (high) or "B" (low)
    bar_sign: int,        # +1 UP / -1 DOWN
    direction: int,       # +1 LONG / -1 SHORT
    hold_bars: int,
) -> Tuple[pd.Series, pd.Series, Dict[str, pd.Series]]:
    """Return (per_trade_net_returns, per_trade_gross_returns_w_meta, per_sym_returns)."""
    rows: List[Tuple] = []
    per_sym_rets: Dict[str, List[float]] = {s: [] for s in UNIVERSE_20}
    for sym, df in per_sym.items():
        mask_dir = df["bar_dir"] == bar_sign
        if cell == "A":
            mask_cell = df["pct_rank_30d"] >= PCT_UPPER
        else:
            mask_cell = df["pct_rank_30d"] <= PCT_LOWER
        mask = mask_cell & mask_dir
        triggers = df.index[mask]
        for ts in triggers:
            fwd = df.at[ts, f"fwd_ret_{hold_bars}b"]
            if pd.isna(fwd):
                continue
            gross = direction * fwd
            net = gross - FEE_PER_TRADE
            rows.append((sym, ts, gross, net))
            per_sym_rets[sym].append(net)
    if not rows:
        return pd.Series([], dtype=float), pd.Series([], dtype=float), {}
    df_t = pd.DataFrame(rows, columns=["sym", "ts", "gross", "net"]).sort_values("ts")
    net = pd.Series(df_t["net"].values, index=pd.to_datetime(df_t["ts"]))
    gross = pd.Series(df_t["gross"].values, index=pd.to_datetime(df_t["ts"]))
    per_sym_series = {
        s: pd.Series(v) for s, v in per_sym_rets.items() if len(v) >= 2
    }
    return net, gross, per_sym_series


def candidate_pool(
    per_sym: Dict[str, pd.DataFrame],
    bar_sign: int,
    direction: int,
    hold_bars: int,
) -> np.ndarray:
    """Universe-wide candidate hold-window returns (direction-adjusted, GROSS)
    constrained to bar_sign of bar — used as fee_aware_perm_test pool."""
    vals: List[float] = []
    for sym, df in per_sym.items():
        mask = df["bar_dir"] == bar_sign
        fwd = df.loc[mask, f"fwd_ret_{hold_bars}b"].dropna().values
        vals.extend((direction * fwd).tolist())
    return np.asarray(vals, dtype=float)


# ---------------------------------------------------------------------------
# Metrics per quadrant
# ---------------------------------------------------------------------------
def quadrant_metrics(
    name: str,
    net: pd.Series,
    gross: pd.Series,
    per_sym_series: Dict[str, pd.Series],
    pool_gross: np.ndarray,
) -> Dict:
    n = len(net)
    if n < 30:
        return {
            "name": name,
            "n_trades": n,
            "verdict": "SAMPLE_INSUFFICIENT",
        }
    mean_net = float(net.mean())
    std_net = float(net.std(ddof=1))
    obs_t = mean_net / std_net * np.sqrt(n) if std_net > 0 else float("nan")

    perm = fee_aware_perm_test(
        observed_net_returns=net.values,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=N_PERMS,
        rng_seed=42,
    )
    ci = bootstrap_ci(net.values, n_boot=N_BOOT, block_size=1, rng_seed=42)

    # 3-gate
    sig_t_ex = perm.get("signal_t_excess", float("nan"))
    ci_lower = ci.get("ci_lower", float("nan"))
    # one-sided p: above for LONG-like (positive expectation), use two-sided as conservative
    perm_p = perm.get("perm_p_one_sided_above", float("nan"))
    three_gate = (
        (not np.isnan(sig_t_ex)) and sig_t_ex >= 2.0
        and (not np.isnan(ci_lower)) and ci_lower > 0.0
        and (not np.isnan(perm_p)) and perm_p <= 0.10
    )

    # Concentration block
    quarter_t: Dict[str, float] = {}
    for q, sub in net.groupby(pd.Grouper(freq="QE")):
        if len(sub) >= 10 and sub.std(ddof=1) > 0:
            quarter_t[str(q.date())] = float(sub.mean() / sub.std(ddof=1) * np.sqrt(len(sub)))
    q_measurable = len(quarter_t)
    q_pos_t = sum(1 for v in quarter_t.values() if v > 0)
    q_pos_t_ratio = (q_pos_t / q_measurable) if q_measurable else 0.0

    sym_ci: Dict[str, Dict] = {}
    sym_ci_pos = 0
    sym_measurable = 0
    for sym, ser in per_sym_series.items():
        if len(ser) < 10:
            continue
        sym_measurable += 1
        bci = bootstrap_ci(ser.values, n_boot=1000, block_size=1, rng_seed=42)
        is_pos = bci.get("ci_lower", float("-inf")) > 0
        if is_pos:
            sym_ci_pos += 1
        sym_ci[sym] = {
            "n": int(len(ser)),
            "mean_bp": float(ser.mean() * 1e4),
            "ci_lower_bp": float(bci.get("ci_lower", float("nan")) * 1e4),
            "ci_upper_bp": float(bci.get("ci_upper", float("nan")) * 1e4),
            "ci_pos": bool(is_pos),
        }
    sym_ci_pos_ratio = (sym_ci_pos / sym_measurable) if sym_measurable else 0.0

    concentration_gate = (
        q_pos_t_ratio >= 0.5
        and sym_ci_pos_ratio >= 0.30
        and sym_ci_pos >= 3
    )

    # Era stratify (alpha decay 11th operational dogfood)
    era_metrics: Dict[str, Dict] = {}
    for era_name, lo, hi in [
        ("2024", "2024-02-01", "2024-12-31"),
        ("2025", "2025-01-01", "2025-12-31"),
        ("2026", "2026-01-01", "2026-04-30"),
    ]:
        sub = net.loc[(net.index >= lo) & (net.index <= hi)]
        if len(sub) >= 20:
            era_metrics[era_name] = {
                "n": int(len(sub)),
                "mean_bp": float(sub.mean() * 1e4),
                "t": float(sub.mean() / sub.std(ddof=1) * np.sqrt(len(sub))) if sub.std(ddof=1) > 0 else float("nan"),
            }

    return {
        "name": name,
        "n_trades": int(n),
        "mean_bp": float(mean_net * 1e4),
        "obs_t": float(obs_t),
        "perm_null_mean_t": perm.get("null_mean_t"),
        "perm_null_std_t": perm.get("null_std_t"),
        "signal_t_excess": float(sig_t_ex) if not np.isnan(sig_t_ex) else None,
        "ci_lower_bp": float(ci_lower * 1e4) if not np.isnan(ci_lower) else None,
        "ci_upper_bp": float(ci.get("ci_upper", float("nan")) * 1e4),
        "perm_p_one_sided_above": float(perm_p) if not np.isnan(perm_p) else None,
        "perm_p_two_sided": perm.get("perm_p_two_sided"),
        "three_gate_pass": bool(three_gate),
        "concentration": {
            "q_measurable": q_measurable,
            "q_pos_t": q_pos_t,
            "q_pos_t_ratio": q_pos_t_ratio,
            "quarter_t": quarter_t,
            "sym_measurable": sym_measurable,
            "sym_ci_pos": sym_ci_pos,
            "sym_ci_pos_ratio": sym_ci_pos_ratio,
            "per_sym": sym_ci,
            "concentration_gate_pass": bool(concentration_gate),
        },
        "era_stratify": era_metrics,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    log.info("paradigm 221 R-1 START — Lesson #40 prescription 2nd 처방")
    per_sym = build_per_sym()
    log.info("loaded %d syms, computing 4 quadrants × %d holds", len(per_sym), len(HOLD_SWEEP_BARS))

    quadrants = [
        ("A_focus_wide_UP_LONG",     "A", +1, +1),
        ("A_mirror_wide_UP_SHORT",   "A", +1, -1),
        ("B_same_compressed_DOWN_SHORT", "B", -1, -1),
        ("B_mirror_compressed_DOWN_LONG", "B", -1, +1),
    ]

    # Item 7: cross-set |A| vs |B| asymmetry measurement (Lesson #39 sub-class A prescreen)
    a_count = 0
    b_count = 0
    for sym, df in per_sym.items():
        a_count += int(((df["pct_rank_30d"] >= PCT_UPPER)).sum())
        b_count += int(((df["pct_rank_30d"] <= PCT_LOWER)).sum())
    cross_set_ratio = a_count / b_count if b_count else float("inf")
    log.info("Item 7 cross-set |A|=%d |B|=%d ratio=%.3f", a_count, b_count, cross_set_ratio)

    # Item 9 Life-changing STRUCTURAL prescreen estimate
    # trades/yr/sym = (a_count + b_count) / 20 syms / 2.24yr / 4 quadrants (approx per cell)
    trades_per_yr_per_sym_per_quadrant = (a_count + b_count) / 20.0 / 2.24 / 4.0
    util_estimate_pct = trades_per_yr_per_sym_per_quadrant * (1.0 / (365.25 * 6.0 / 1.0)) * 100  # 4h hold/yr
    log.info(
        "Item 9 STRUCTURAL estimate: trades/yr/sym/q=%.1f util_pct≈%.2f%%",
        trades_per_yr_per_sym_per_quadrant, util_estimate_pct,
    )

    results: Dict = {
        "paradigm": PARADIGM,
        "lesson_template": "Lesson #69 9-item",
        "lesson_40_prescription_iteration": 2,
        "item_7_cross_set": {
            "a_count": a_count,
            "b_count": b_count,
            "ratio_a_over_b": cross_set_ratio,
            "asymmetric": abs(cross_set_ratio - 1.0) > 0.15,
        },
        "item_9_structural_prescreen": {
            "trades_per_yr_per_sym_per_quadrant": trades_per_yr_per_sym_per_quadrant,
            "util_pct_estimate": util_estimate_pct,
            "structural_fail_risk": util_estimate_pct < 10.0,
        },
        "holds": {},
    }

    for hold_bars in HOLD_SWEEP_BARS:
        hold_label = f"{hold_bars * 4}h"
        log.info("--- hold=%s ---", hold_label)
        hold_block: Dict = {"hold_label": hold_label, "quadrants": {}}
        for name, cell, bar_sign, direction in quadrants:
            net, gross, per_sym_series = gen_quadrant(per_sym, cell, bar_sign, direction, hold_bars)
            pool_gross = candidate_pool(per_sym, bar_sign, direction, hold_bars)
            log.info("  %s n=%d pool_n=%d", name, len(net), len(pool_gross))
            metrics = quadrant_metrics(name, net, gross, per_sym_series, pool_gross)
            hold_block["quadrants"][name] = metrics
        results["holds"][hold_label] = hold_block

    # Unconditional baseline (Lesson #39 sub-class B prescreen)
    # all bars × direction = +1 (LONG-pass-through) at primary hold
    uncond_rets: List[float] = []
    for sym, df in per_sym.items():
        fwd = df[f"fwd_ret_{PRIMARY_HOLD_BARS}b"].dropna()
        uncond_rets.extend((+1 * fwd - FEE_PER_TRADE).tolist())
    uncond_arr = np.asarray(uncond_rets, dtype=float)
    uncond_t = float(uncond_arr.mean() / uncond_arr.std(ddof=1) * np.sqrt(len(uncond_arr))) if len(uncond_arr) > 1 and uncond_arr.std(ddof=1) > 0 else float("nan")
    results["unconditional_baseline_primary_hold_LONG"] = {
        "n": int(len(uncond_arr)),
        "mean_bp": float(uncond_arr.mean() * 1e4),
        "t": uncond_t,
        "note": "Lesson #39 sub-class B prescreen — directional bias baseline",
    }

    # Primary verdict on 4h hold
    primary = results["holds"][f"{PRIMARY_HOLD_BARS * 4}h"]["quadrants"]
    a_focus = primary.get("A_focus_wide_UP_LONG", {})
    a_mirror = primary.get("A_mirror_wide_UP_SHORT", {})
    b_same = primary.get("B_same_compressed_DOWN_SHORT", {})
    b_mirror = primary.get("B_mirror_compressed_DOWN_LONG", {})

    # Lesson #39 sub-class A: exact symmetric ±k bp + both broad-uniform-negative?
    def safe_mean_bp(d: Dict) -> float:
        v = d.get("mean_bp")
        return float(v) if v is not None else float("nan")

    af = safe_mean_bp(a_focus)
    am = safe_mean_bp(a_mirror)
    bs = safe_mean_bp(b_same)
    bm = safe_mean_bp(b_mirror)

    a_symmetric = (not np.isnan(af)) and (not np.isnan(am)) and abs(af + am + 2 * FEE_PER_TRADE * 1e4) < 5.0
    b_symmetric = (not np.isnan(bs)) and (not np.isnan(bm)) and abs(bs + bm + 2 * FEE_PER_TRADE * 1e4) < 5.0
    all_negative = all(np.isnan(v) or v < 0 for v in [af, am, bs, bm])
    lesson_39_sub_a = a_symmetric and b_symmetric and all_negative

    primary_passes = sum(
        1 for q in primary.values()
        if isinstance(q, dict) and q.get("three_gate_pass") and q.get("concentration", {}).get("concentration_gate_pass")
    )

    # Full hold × quadrant sweep PASS scan (Lesson #37 의무)
    sweep_pass_cells: List[Dict] = []
    for hold_label, block in results["holds"].items():
        for qname, qm in block["quadrants"].items():
            if isinstance(qm, dict) and qm.get("three_gate_pass") and qm.get("concentration", {}).get("concentration_gate_pass"):
                sweep_pass_cells.append({
                    "hold": hold_label,
                    "quadrant": qname,
                    "mean_bp": qm.get("mean_bp"),
                    "signal_t_excess": qm.get("signal_t_excess"),
                    "ci_lower_bp": qm.get("ci_lower_bp"),
                    "n": qm.get("n_trades"),
                })
    results["sweep_pass_cells"] = sweep_pass_cells

    if lesson_39_sub_a:
        verdict = "BROAD_FALSIFIED_NO_AXIS_SYNTHESIS_LESSON_39_SUB_A"
    elif primary_passes == 0 and not sweep_pass_cells:
        verdict = "BROAD_FALSIFIED_FEE_FLOOR_OR_NO_ALPHA"
    elif primary_passes == 0 and sweep_pass_cells:
        verdict = "OFF_PRIMARY_PASS_LESSON_37_NARROW_CANDIDATE"
    elif primary_passes >= 1:
        verdict = "PASS_R1_PRIMARY"
    else:
        verdict = "INDETERMINATE"

    results["verdict"] = verdict
    results["lesson_39_sub_a_check"] = {
        "a_symmetric": bool(a_symmetric),
        "b_symmetric": bool(b_symmetric),
        "all_negative": bool(all_negative),
        "triggers_sub_class_a": bool(lesson_39_sub_a),
    }
    results["primary_pass_count"] = primary_passes

    out_path = OUT_DIR / "r1__metrics.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    log.info("WROTE %s", out_path)
    log.info("VERDICT: %s", verdict)
    log.info(
        "primary 4h means(bp): A_focus=%.2f A_mirror=%.2f B_same=%.2f B_mirror=%.2f",
        af, am, bs, bm,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
