"""paradigm 211 R-1 PoC.

Hypothesis
----------
Per-symbol realized vol term structure slope (30d vol / 7d vol ratio) z-score
spike → 4h directional continuation/reversal, sign-conditional bilateral 4-quadrant
SNT (Lesson #19).

Statistic
---------
For each sym, 4h candles → close-to-close 4h log-returns r_t.
- realized vol 7d (rv7)  = std of r over trailing 7 days  (42 bars at 4h)
- realized vol 30d (rv30) = std of r over trailing 30 days (180 bars at 4h)
- slope = log(rv30 / rv7)   (symmetric domain around 0)
- z-score: rolling 90d (540 bars) mean / std on slope
- trigger: |z| >= 2.0

Cells (4-quadrant SNT, disjoint trigger sets)
---------------------------------------------
- A focus  : z >= +2 (recent contraction regime shift) × bar UP   × LONG  continuation
- A mirror : z >= +2                                   × bar UP   × SHORT reversal
- B same   : z <= -2 (recent expansion  regime shift) × bar DOWN × SHORT continuation
- B mirror : z <= -2                                   × bar DOWN × LONG  reversal

A and B trigger sets are DISJOINT (Item 7 cross-set asymmetric check).

Substrate
---------
backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib × 21 syms × 2024-02-01..2026-04-30
(2.25yr × 4920 bars). substrate_maturity ≥ 2yr verified, market maturity decay risk LOW.

Gates (per cell)
----------------
PASS = signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_one_sided_above <= 0.10
       (perm_p_one_sided_below for SHORT direction)

Item 8 (paradigm 208 amendment): Concentration + Temporal Independence on A_focus continuation only.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("paradigm211_r1")

PARADIGM_NUMBER = 211
PARADIGM_SLUG = "alt_per_sym_realized_vol_term_structure_slope_30d_vs_7d_ratio_z_spike_directional_4h_bilateral"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"

SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "DOTUSDT", "ETCUSDT", "ETHUSDT", "FILUSDT", "JUPUSDT", "LDOUSDT",
    "LINKUSDT", "LTCUSDT", "NEARUSDT", "PYTHUSDT", "SOLUSDT", "UNIUSDT",
    "WIFUSDT", "WLDUSDT", "XRPUSDT",
]

# 4h bar counts
BARS_7D = 7 * 6     # 42
BARS_30D = 30 * 6   # 180
BARS_90D = 90 * 6   # 540
Z_THRESHOLD = 2.0
FEE_PER_TRADE = 0.0008  # 8 bp round-trip

HOLD_BARS_MAP = {"4h": 1, "8h": 2, "12h": 3, "24h": 6}
HOLD_PRIMARY = "4h"


def load_sym(sym: str) -> pd.DataFrame:
    fp = CACHE_DIR / f"{sym}_4h.joblib"
    df = joblib.load(fp)
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add log return, rv7, rv30, slope, z(slope), bar_direction."""
    out = df.copy()
    out["close"] = out["close"].astype(float)
    out["logret"] = np.log(out["close"]).diff()
    out["rv7"] = out["logret"].rolling(BARS_7D, min_periods=BARS_7D).std()
    out["rv30"] = out["logret"].rolling(BARS_30D, min_periods=BARS_30D).std()
    out["slope"] = np.log(out["rv30"] / out["rv7"])
    out["slope_mean"] = out["slope"].rolling(BARS_90D, min_periods=BARS_90D).mean()
    out["slope_std"] = out["slope"].rolling(BARS_90D, min_periods=BARS_90D).std()
    out["slope_z"] = (out["slope"] - out["slope_mean"]) / out["slope_std"]
    out["bar_dir"] = np.sign(out["logret"])  # +1 up / -1 down / 0
    return out


def forward_return(close: pd.Series, hold_bars: int) -> pd.Series:
    """Gross forward return over hold_bars from current bar close."""
    return close.shift(-hold_bars) / close - 1.0


def compute_panel() -> Dict[str, pd.DataFrame]:
    panel = {}
    for sym in SYMS:
        try:
            df = load_sym(sym)
        except Exception as exc:
            log.warning("skip %s: %s", sym, exc)
            continue
        feats = compute_features(df)
        # forward returns
        for hk, hb in HOLD_BARS_MAP.items():
            feats[f"fwd_{hk}"] = forward_return(feats["close"], hb)
        panel[sym] = feats
    log.info("panel built: %d syms", len(panel))
    return panel


def collect_cell_trades(
    panel: Dict[str, pd.DataFrame],
    *,
    z_sign: str,       # "pos" (z >= +T) or "neg" (z <= -T)
    bar_dir: int,      # +1 or -1
    trade_dir: int,    # +1 long, -1 short
    hold_key: str,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[pd.Timestamp, float]]:
    """Return (per_trade_net_returns, per_sym_net_dict, per_trade_index_to_ret)."""
    all_net = []
    per_sym_net: Dict[str, List[float]] = {}
    per_trade_idx_ret = {}  # entry_ts -> net_ret (for temporal independence)
    fwd_col = f"fwd_{hold_key}"
    for sym, df in panel.items():
        if z_sign == "pos":
            mask = df["slope_z"] >= Z_THRESHOLD
        else:
            mask = df["slope_z"] <= -Z_THRESHOLD
        mask = mask & (df["bar_dir"] == bar_dir) & df[fwd_col].notna()
        if mask.sum() == 0:
            continue
        entries = df.loc[mask]
        gross = entries[fwd_col].astype(float).values
        net = trade_dir * gross - FEE_PER_TRADE
        all_net.append(net)
        per_sym_net[sym] = net
        for ts, r in zip(entries.index, net):
            per_trade_idx_ret[ts] = float(r)
    flat = np.concatenate(all_net) if all_net else np.array([])
    return flat, per_sym_net, per_trade_idx_ret


def candidate_pool_gross(
    panel: Dict[str, pd.DataFrame], hold_key: str
) -> np.ndarray:
    """All eligible forward returns (any bar where slope_z is defined)."""
    fwd_col = f"fwd_{hold_key}"
    pool = []
    for sym, df in panel.items():
        sub = df.loc[df["slope_z"].notna() & df[fwd_col].notna(), fwd_col]
        pool.append(sub.astype(float).values)
    if not pool:
        return np.array([])
    return np.concatenate(pool)


def eval_cell(
    name: str,
    flat_net: np.ndarray,
    per_sym_net: Dict[str, np.ndarray],
    pool_gross: np.ndarray,
    *,
    trade_dir: int,
    per_trade_idx_ret: Dict[pd.Timestamp, float],
    do_concentration: bool = False,
) -> Dict:
    n = len(flat_net)
    res = {"name": name, "n": int(n)}
    if n < 30:
        res["verdict"] = "INSUFFICIENT_N"
        return res
    perm = fee_aware_perm_test(
        observed_net_returns=flat_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
    )
    ci = bootstrap_ci(flat_net, n_boot=2000, block_size=1)

    res["mean_bp"] = float(np.mean(flat_net) * 10000)
    res["median_bp"] = float(np.median(flat_net) * 10000)
    res["obs_t"] = perm["obs_t"]
    res["null_mean_t"] = perm["null_mean_t"]
    res["signal_t_excess"] = perm["signal_t_excess"]
    # one-sided p: LONG uses above, SHORT uses below
    res["perm_p_one_sided"] = (
        perm["perm_p_one_sided_above"] if trade_dir == 1 else perm["perm_p_one_sided_below"]
    )
    res["perm_p_two_sided"] = perm["perm_p_two_sided"]
    res["ci_lower_bp"] = float(ci["ci_lower"] * 10000)
    res["ci_upper_bp"] = float(ci["ci_upper"] * 10000)
    res["prob_positive"] = ci["prob_positive"]

    # 3-gate verdict
    gate_t = res["signal_t_excess"] >= 2.0
    gate_ci = ci["ci_lower"] > 0
    gate_perm = res["perm_p_one_sided"] <= 0.10
    res["gate_t_excess"] = bool(gate_t)
    res["gate_ci_lower"] = bool(gate_ci)
    res["gate_perm_p"] = bool(gate_perm)
    res["three_gate_pass"] = bool(gate_t and gate_ci and gate_perm)

    # Concentration + Temporal Independence (Item 8 — only on A_focus continuation)
    if do_concentration:
        per_sym_ci_pos = 0
        per_sym_n_measured = 0
        per_sym_ci_pos_syms = []
        for sym, arr in per_sym_net.items():
            if len(arr) < 10:
                continue
            per_sym_n_measured += 1
            sym_ci = bootstrap_ci(arr, n_boot=1000, block_size=1)
            if sym_ci["ci_lower"] > 0:
                per_sym_ci_pos += 1
                per_sym_ci_pos_syms.append(sym)
        res["sym_n_measured"] = per_sym_n_measured
        res["sym_n_ci_pos"] = per_sym_ci_pos
        res["sym_ci_pos_ratio"] = (
            per_sym_ci_pos / per_sym_n_measured if per_sym_n_measured > 0 else 0.0
        )
        res["sym_ci_pos_syms"] = per_sym_ci_pos_syms

        # Quarter t-stat
        ts_to_q = {}
        ts_arr = []
        ret_arr = []
        for ts, r in per_trade_idx_ret.items():
            q = pd.Timestamp(ts).to_period("Q")
            ts_to_q[ts] = str(q)
            ts_arr.append(str(q))
            ret_arr.append(r)
        q_df = pd.DataFrame({"q": ts_arr, "r": ret_arr})
        q_results = {}
        n_pos_t = 0
        n_q_measurable = 0
        for q, sub in q_df.groupby("q"):
            if len(sub) < 5:
                continue
            n_q_measurable += 1
            arr = sub["r"].values
            mean = arr.mean()
            sd = arr.std(ddof=1)
            t = mean / sd * np.sqrt(len(arr)) if sd > 0 else 0.0
            q_results[q] = {"n": int(len(sub)), "mean_bp": float(mean * 10000), "t": float(t)}
            if t > 0:
                n_pos_t += 1
        res["per_quarter"] = q_results
        res["q_n_measurable"] = n_q_measurable
        res["q_n_pos_t"] = n_pos_t
        res["quarter_pos_t_ratio"] = n_pos_t / n_q_measurable if n_q_measurable > 0 else 0.0

        # Temporal Independence: % of trades whose previous trade is in same hold window
        sorted_ts = sorted(per_trade_idx_ret.keys())
        hold_bars = HOLD_BARS_MAP[HOLD_PRIMARY]
        independent = 0
        for i, ts in enumerate(sorted_ts):
            if i == 0:
                independent += 1
                continue
            delta = (ts - sorted_ts[i - 1]).total_seconds() / 3600
            if delta >= hold_bars * 4:
                independent += 1
        res["temporal_cluster_ratio"] = independent / len(sorted_ts) if sorted_ts else 0.0

    return res


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    log.info("paradigm 211 R-1 START %s", started.isoformat())

    panel = compute_panel()
    if not panel:
        log.error("no panel data")
        return

    # Trigger rate diagnostics
    diag = {}
    for sym, df in panel.items():
        z = df["slope_z"]
        diag[sym] = {
            "n_bars": int(z.notna().sum()),
            "z_pos_count": int((z >= Z_THRESHOLD).sum()),
            "z_neg_count": int((z <= -Z_THRESHOLD).sum()),
            "z_min": float(z.min()),
            "z_max": float(z.max()),
            "z_std": float(z.std()),
        }
    total_z_pos = sum(d["z_pos_count"] for d in diag.values())
    total_z_neg = sum(d["z_neg_count"] for d in diag.values())
    log.info("trigger diagnostics: total z>=+%.1f = %d / total z<=-%.1f = %d",
             Z_THRESHOLD, total_z_pos, Z_THRESHOLD, total_z_neg)

    # Unconditional baseline (Lesson #39 sub-class B prescreen)
    unconditional_baselines = {}
    for hk in HOLD_BARS_MAP:
        all_long = []
        all_short = []
        for sym, df in panel.items():
            sub = df.loc[df[f"fwd_{hk}"].notna() & df["bar_dir"].abs().eq(1)]
            for _, row in sub.iterrows():
                bd = row["bar_dir"]
                fr = row[f"fwd_{hk}"]
                if bd > 0:
                    all_long.append(fr - FEE_PER_TRADE)
                else:
                    all_short.append(-fr - FEE_PER_TRADE)
        ul = np.array(all_long); us = np.array(all_short)
        unconditional_baselines[hk] = {
            "continuation_long_bar_up_n": int(len(ul)),
            "continuation_long_bar_up_mean_bp": float(ul.mean() * 10000) if len(ul) else 0.0,
            "continuation_short_bar_down_n": int(len(us)),
            "continuation_short_bar_down_mean_bp": float(us.mean() * 10000) if len(us) else 0.0,
        }
    log.info("unconditional baselines: %s", unconditional_baselines[HOLD_PRIMARY])

    # 4-quadrant × hold sweep
    cells_spec = [
        ("A_focus_z_pos_bar_up_LONG_continuation",   "pos", +1, +1),
        ("A_mirror_z_pos_bar_up_SHORT_reversal",     "pos", +1, -1),
        ("B_same_z_neg_bar_down_SHORT_continuation", "neg", -1, -1),
        ("B_mirror_z_neg_bar_down_LONG_reversal",    "neg", -1, +1),
    ]

    results = {}
    for hk in HOLD_BARS_MAP:
        log.info("hold=%s evaluating 4 cells", hk)
        pool_gross = candidate_pool_gross(panel, hk)
        log.info("  candidate pool n=%d", len(pool_gross))
        hk_results = {}
        for cell_name, zs, bd, td in cells_spec:
            flat, per_sym, per_trade_idx = collect_cell_trades(
                panel, z_sign=zs, bar_dir=bd, trade_dir=td, hold_key=hk
            )
            do_conc = (cell_name.startswith("A_focus") and hk == HOLD_PRIMARY)
            cell_res = eval_cell(
                cell_name, flat, per_sym, pool_gross,
                trade_dir=td, per_trade_idx_ret=per_trade_idx,
                do_concentration=do_conc,
            )
            log.info("  %s: n=%d mean_bp=%.2f t=%.2f sigex=%.2f ci_lo=%.2f perm_p=%.3f PASS=%s",
                     cell_name, cell_res["n"],
                     cell_res.get("mean_bp", float("nan")),
                     cell_res.get("obs_t", float("nan")),
                     cell_res.get("signal_t_excess", float("nan")),
                     cell_res.get("ci_lower_bp", float("nan")),
                     cell_res.get("perm_p_one_sided", float("nan")),
                     cell_res.get("three_gate_pass", False))
            hk_results[cell_name] = cell_res
        results[hk] = hk_results

    # Era stratify (2024 / 2025 / 2026) for A_focus continuation primary
    era_strat = {}
    a_focus_name = "A_focus_z_pos_bar_up_LONG_continuation"
    for hk in HOLD_BARS_MAP:
        flat, per_sym, per_trade_idx = collect_cell_trades(
            panel, z_sign="pos", bar_dir=+1, trade_dir=+1, hold_key=hk
        )
        era_buckets = {"2024": [], "2025": [], "2026": []}
        quarter_buckets = {}
        for ts, r in per_trade_idx.items():
            y = pd.Timestamp(ts).year
            yk = str(y) if y in (2024, 2025, 2026) else "other"
            if yk in era_buckets:
                era_buckets[yk].append(r)
            qk = str(pd.Timestamp(ts).to_period("Q"))
            quarter_buckets.setdefault(qk, []).append(r)
        e = {}
        for era, arr in era_buckets.items():
            if len(arr) < 5:
                e[era] = {"n": len(arr), "mean_bp": None, "t": None}
                continue
            a = np.array(arr)
            sd = a.std(ddof=1)
            t = a.mean() / sd * np.sqrt(len(a)) if sd > 0 else 0.0
            e[era] = {"n": int(len(a)), "mean_bp": float(a.mean() * 10000), "t": float(t)}
        q = {}
        for qk, arr in sorted(quarter_buckets.items()):
            if len(arr) < 5:
                q[qk] = {"n": len(arr), "mean_bp": None, "t": None}
                continue
            a = np.array(arr)
            sd = a.std(ddof=1)
            t = a.mean() / sd * np.sqrt(len(a)) if sd > 0 else 0.0
            q[qk] = {"n": int(len(a)), "mean_bp": float(a.mean() * 10000), "t": float(t)}
        era_strat[hk] = {"era": e, "quarter": q}

    # Item 7 cross-set asymmetric check on PRIMARY hold (|A trigger set| vs |B trigger set|)
    n_A_focus = results[HOLD_PRIMARY]["A_focus_z_pos_bar_up_LONG_continuation"]["n"]
    n_A_mirror = results[HOLD_PRIMARY]["A_mirror_z_pos_bar_up_SHORT_reversal"]["n"]
    n_B_same = results[HOLD_PRIMARY]["B_same_z_neg_bar_down_SHORT_continuation"]["n"]
    n_B_mirror = results[HOLD_PRIMARY]["B_mirror_z_neg_bar_down_LONG_reversal"]["n"]
    a_total = n_A_focus + n_A_mirror
    b_total = n_B_same + n_B_mirror
    cross_set_asymmetry = {
        "n_A_z_pos_total_trigger_set": int(a_total),
        "n_B_z_neg_total_trigger_set": int(b_total),
        "asymmetry_ratio_A_over_B": (a_total / b_total) if b_total > 0 else None,
        "n_A_focus_continuation": int(n_A_focus),
        "n_A_mirror_reversal": int(n_A_mirror),
        "n_B_same_continuation": int(n_B_same),
        "n_B_mirror_reversal": int(n_B_mirror),
    }

    finished = datetime.now()
    out_obj = {
        "paradigm_number": PARADIGM_NUMBER,
        "paradigm_slug": PARADIGM_SLUG,
        "phase": "R-1",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "wall_seconds": (finished - started).total_seconds(),
        "config": {
            "syms": SYMS,
            "n_syms": len(panel),
            "z_threshold": Z_THRESHOLD,
            "fee_per_trade": FEE_PER_TRADE,
            "hold_primary": HOLD_PRIMARY,
            "hold_sweep": list(HOLD_BARS_MAP.keys()),
            "bars_7d": BARS_7D,
            "bars_30d": BARS_30D,
            "bars_90d": BARS_90D,
        },
        "trigger_diagnostics_per_sym": diag,
        "trigger_totals": {
            "z_pos_total": int(total_z_pos),
            "z_neg_total": int(total_z_neg),
        },
        "unconditional_baselines": unconditional_baselines,
        "cells_4q_x_hold_sweep": results,
        "era_stratify_A_focus_continuation": era_strat,
        "cross_set_asymmetry_item_7": cross_set_asymmetry,
    }

    out_fp = OUT_DIR / "r1__metrics.json"
    with open(out_fp, "w") as f:
        json.dump(out_obj, f, indent=2, default=str)
    log.info("metrics saved: %s", out_fp)


if __name__ == "__main__":
    main()
