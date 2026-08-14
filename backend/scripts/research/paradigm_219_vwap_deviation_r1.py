"""paradigm 219 R-1 PoC — per-sym 4h close / 30d rolling VWAP ratio z-spike directional 4h bilateral.

VWAP deviation axis first-use in campaign (NEW statistic class — informed-flow
accumulation/distribution detection via volume-weighted price benchmark).

Spec
----
- Statistic: per-sym 4h typical_price = (high+low+close)/3, rolling VWAP =
  sum(typical_price × volume, 30d window) / sum(volume, 30d window). Then
  ratio = close / rolling_vwap, then 90d rolling z-score of ratio.
- Universe: 20 alts (paradigm 198 cohort)
- Substrate: 4h cache 12col (high/low/close/volume all present)
- Triggers: |z| >= 2 bilateral, disjoint trigger sets (Lesson #39 sub-class A avoidance)
  - A_focus:  z >= +2 × bar UP   × LONG  (ABOVE regime continuation)
  - A_mirror: z >= +2 × bar UP   × SHORT (ABOVE regime reversal)
  - B_same:   z <= -2 × bar DOWN × SHORT (BELOW regime continuation)
  - B_mirror: z <= -2 × bar DOWN × LONG  (BELOW regime reversal, Lesson #42 21st dogfood)
- Holds: 4h primary + 8h + 12h + 24h sweep
- Threshold: |z| >= 2 primary + |z| >= 1.5 sensitivity
- Fee: 8 bp round-trip

Rolling windows
---------------
- VWAP window: 30d × 6 bars/day = 180 4h bars
- z-score window of ratio: 90d × 6 bars/day = 540 4h bars
  (Use full available history if short; min_periods enforced)

Lesson #69 9-item template + Lesson #39/40/42/67/68/70 compliance.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

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
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("paradigm_219")

PARADIGM_COUNTER = 219
PARADIGM_SLUG = (
    "alt_per_sym_4h_vwap_deviation_30d_rolling_z_spike_directional_4h_bilateral"
)
OUTPUT_DIR = ROOT / "runs" / "research_track" / (
    f"paradigm_{PARADIGM_COUNTER}_{PARADIGM_SLUG}"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OHLCV_CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"

SYMBOLS_20 = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC",
    "BCH", "NEAR", "FIL", "WIF", "JUP", "PYTH", "DOT", "ETC", "UNI", "WLD",
]

VWAP_BARS = 180   # 30d × 6 bars/day
Z_BARS = 540      # 90d × 6 bars/day
Z_PRIMARY = 2.0
Z_SENSITIVITY = 1.5
FEE_RT = 0.0008
HOLDS_BARS = {"4h": 1, "8h": 2, "12h": 3, "24h": 6}
PRIMARY_HOLD = "4h"


# ---------- data loading -----------------------------------------------

def load_ohlcv_4h(sym: str) -> pd.DataFrame:
    path = OHLCV_CACHE_DIR / f"{sym}USDT_4h.joblib"
    if not path.exists():
        raise FileNotFoundError(f"4h cache missing for {sym}: {path}")
    df = joblib.load(path)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index, utc=False)
    df.sort_index(inplace=True)
    return df


def compute_vwap_deviation_z(
    ohlcv: pd.DataFrame, vwap_window: int = VWAP_BARS, z_window: int = Z_BARS,
) -> pd.DataFrame:
    """Compute per-bar rolling VWAP deviation z-score.

    typical_price = (high + low + close) / 3
    rolling_vwap = rolling_sum(tp × vol) / rolling_sum(vol)
    ratio = close / rolling_vwap
    z = rolling_zscore(ratio, z_window)
    """
    df = ohlcv.copy()
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    tpv = tp * df["volume"]
    sum_tpv = tpv.rolling(window=vwap_window, min_periods=vwap_window).sum()
    sum_vol = df["volume"].rolling(window=vwap_window, min_periods=vwap_window).sum()
    df["rolling_vwap"] = sum_tpv / sum_vol
    df["vwap_ratio"] = df["close"] / df["rolling_vwap"]
    df["vwap_ratio_zmean"] = (
        df["vwap_ratio"].rolling(window=z_window, min_periods=z_window).mean()
    )
    df["vwap_ratio_zstd"] = (
        df["vwap_ratio"].rolling(window=z_window, min_periods=z_window).std(ddof=1)
    )
    df["vwap_z"] = (df["vwap_ratio"] - df["vwap_ratio_zmean"]) / df["vwap_ratio_zstd"]
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df["bar_dir"] = np.sign(df["close"] - df["open"]).astype(float)
    return df


def compute_forward_returns(ohlcv: pd.DataFrame, holds_bars: Dict[str, int]) -> pd.DataFrame:
    out = pd.DataFrame(index=ohlcv.index)
    next_open = ohlcv["open"].shift(-1)
    for label, h in holds_bars.items():
        exit_close = ohlcv["close"].shift(-h)
        out[f"fwd_{label}"] = (exit_close / next_open) - 1.0
    return out


# ---------- pipeline ---------------------------------------------------

def build_panel() -> Dict[str, pd.DataFrame]:
    panels: Dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS_20:
        try:
            ohlcv = load_ohlcv_4h(sym)
        except FileNotFoundError as e:
            log.warning("skip %s: %s", sym, e)
            continue
        feat = compute_vwap_deviation_z(ohlcv)
        fwd = compute_forward_returns(ohlcv, HOLDS_BARS)
        df = feat.join(fwd, how="left")
        df["sym"] = sym
        panels[sym] = df
        log.info(
            "panel %s: n=%d valid_z=%d trigger_pos=%d trigger_neg=%d",
            sym,
            len(df),
            int(df["vwap_z"].notna().sum()),
            int((df["vwap_z"] >= Z_PRIMARY).sum()),
            int((df["vwap_z"] <= -Z_PRIMARY).sum()),
        )
    return panels


def collect_triggers(panels: Dict[str, pd.DataFrame], z_thresh: float,
                     hold_label: str) -> pd.DataFrame:
    fwd_col = f"fwd_{hold_label}"
    parts = []
    for sym, df in panels.items():
        sub = df[["vwap_z", "bar_dir", fwd_col, "sym"]].dropna()
        sub = sub[(sub["vwap_z"].abs() >= z_thresh) & (sub["bar_dir"] != 0)]
        if sub.empty:
            continue
        parts.append(sub)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts)
    out["era"] = out.index.year
    return out


def four_quadrant_snt(
    triggers: pd.DataFrame, fwd_col: str, z_thresh: float,
) -> Dict[str, Dict]:
    """4-quadrant SNT with disjoint A/B trigger sets.

    A trigger set: z>=+T AND bar UP
    B trigger set: z<=-T AND bar DOWN

    Cells:
      A_focus:  A set, LONG
      A_mirror: A set, SHORT
      B_same:   B set, SHORT
      B_mirror: B set, LONG
    """
    results: Dict[str, Dict] = {}
    A_mask = (triggers["vwap_z"] >= z_thresh) & (triggers["bar_dir"] > 0)
    A_set = triggers.loc[A_mask].copy()
    B_mask = (triggers["vwap_z"] <= -z_thresh) & (triggers["bar_dir"] < 0)
    B_set = triggers.loc[B_mask].copy()

    cells = {
        "A_focus_ABOVE_UP_LONG":     (A_set, +1),
        "A_mirror_ABOVE_UP_SHORT":   (A_set, -1),
        "B_same_BELOW_DOWN_SHORT":   (B_set, -1),
        "B_mirror_BELOW_DOWN_LONG":  (B_set, +1),
    }

    for cell_name, (sub, trade_dir) in cells.items():
        if sub.empty:
            results[cell_name] = {
                "n_trig": 0,
                "n_syms": 0,
                "verdict": "EMPTY_TRIGGER_SET",
            }
            continue
        gross = trade_dir * sub[fwd_col].values
        net = gross - FEE_RT
        n = len(net)
        n_syms = sub["sym"].nunique()
        mean_gross_bp = float(np.mean(gross) * 1e4)
        mean_net_bp = float(np.mean(net) * 1e4)
        std_net = float(np.std(net, ddof=1)) if n >= 2 else float("nan")
        t_obs = (
            float(np.mean(net) / std_net * np.sqrt(n))
            if std_net > 0 and np.isfinite(std_net)
            else 0.0
        )
        win_rate = float((gross > FEE_RT).mean())
        per_year = (
            sub.assign(net=net)
            .groupby("era")["net"]
            .agg(["mean", "count"])
            .rename(columns={"mean": "mean_net", "count": "n"})
        )
        per_year_summary = {
            int(y): {
                "mean_net_bp": float(r["mean_net"] * 1e4),
                "n": int(r["n"]),
            }
            for y, r in per_year.iterrows()
        }
        results[cell_name] = {
            "n_trig": int(n),
            "n_syms": int(n_syms),
            "mean_gross_bp": mean_gross_bp,
            "mean_net_bp": mean_net_bp,
            "t_obs": t_obs,
            "win_rate": win_rate,
            "per_year": per_year_summary,
            "trade_direction": int(trade_dir),
        }
    return results


def three_gate_for_cell(
    triggers_cell: pd.DataFrame,
    trade_dir: int,
    candidate_pool_returns: np.ndarray,
    fwd_col: str,
    n_perms: int = 1000,
) -> Dict:
    if triggers_cell.empty:
        return {
            "signal_t_excess": float("nan"),
            "ci_lower_bp": float("nan"),
            "perm_p": float("nan"),
            "verdict": "EMPTY",
        }
    obs_net = trade_dir * triggers_cell[fwd_col].values - FEE_RT
    if len(obs_net) < 2:
        return {
            "signal_t_excess": float("nan"),
            "ci_lower_bp": float("nan"),
            "perm_p": float("nan"),
            "verdict": "N_TOO_SMALL",
        }
    pool_gross = trade_dir * candidate_pool_returns
    fa = fee_aware_perm_test(
        observed_net_returns=obs_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_RT,
        n_perms=n_perms,
        rng_seed=42,
    )
    ci = bootstrap_ci(obs_net, n_boot=2000, block_size=1, alpha=0.05, rng_seed=42)
    ci_lower_bp = float(ci.get("ci_lower", float("nan")) * 1e4)
    ci_upper_bp = float(ci.get("ci_upper", float("nan")) * 1e4)
    mean_bp = float(ci.get("mean", np.mean(obs_net)) * 1e4)
    perm_p_above = float(fa.get("perm_p_one_sided_above", float("nan")))
    perm_p_below = float(fa.get("perm_p_one_sided_below", float("nan")))
    perm_p = perm_p_above if fa.get("obs_t", 0.0) > 0 else perm_p_below
    sigex = float(fa.get("signal_t_excess", float("nan")))

    gate_t = (np.isfinite(sigex) and sigex >= 2.0)
    gate_ci = (np.isfinite(ci_lower_bp) and ci_lower_bp > 0)
    gate_perm = (np.isfinite(perm_p) and perm_p <= 0.10)
    if gate_t and gate_ci and gate_perm:
        verdict = "THREE_GATE_PASS"
    else:
        failed = []
        if not gate_t:
            failed.append("signal_t_excess<2")
        if not gate_ci:
            failed.append("ci_lower<=0")
        if not gate_perm:
            failed.append("perm_p>0.10")
        verdict = "FAIL_" + "_".join(failed) if failed else "FAIL_UNKNOWN"

    return {
        "obs_t": float(fa.get("obs_t", float("nan"))),
        "null_mean_t": float(fa.get("null_mean_t", float("nan"))),
        "signal_t_excess": sigex,
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": ci_upper_bp,
        "mean_bp": mean_bp,
        "prob_positive": float(ci.get("prob_positive", float("nan"))),
        "perm_p": perm_p,
        "perm_p_two_sided": float(fa.get("perm_p_two_sided", float("nan"))),
        "n_observed": int(len(obs_net)),
        "verdict": verdict,
    }


def build_candidate_pool(panels: Dict[str, pd.DataFrame], hold_label: str) -> np.ndarray:
    fwd_col = f"fwd_{hold_label}"
    parts = []
    for sym, df in panels.items():
        sub = df.loc[df["vwap_z"].notna(), fwd_col].dropna()
        if not sub.empty:
            parts.append(sub.values)
    if not parts:
        return np.array([])
    return np.concatenate(parts)


def per_sym_bootstrap(
    triggers_cell: pd.DataFrame, trade_dir: int, fwd_col: str,
) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for sym, sub in triggers_cell.groupby("sym"):
        n = len(sub)
        if n < 5:
            out[sym] = {"n": n, "ci_lower_bp": None, "ci_pos": False}
            continue
        net = trade_dir * sub[fwd_col].values - FEE_RT
        ci = bootstrap_ci(net, n_boot=1000, block_size=1, alpha=0.05, rng_seed=42)
        ci_lower_bp = float(ci.get("ci_lower", float("nan")) * 1e4)
        ci_upper_bp = float(ci.get("ci_upper", float("nan")) * 1e4)
        mean_bp = float(ci.get("mean", np.mean(net)) * 1e4)
        out[sym] = {
            "n": int(n),
            "mean_bp": mean_bp,
            "ci_lower_bp": ci_lower_bp,
            "ci_upper_bp": ci_upper_bp,
            "ci_pos": bool(ci_lower_bp > 0) if np.isfinite(ci_lower_bp) else False,
        }
    return out


def per_quarter_t(
    triggers_cell: pd.DataFrame, trade_dir: int, fwd_col: str,
) -> Dict[str, Dict]:
    if triggers_cell.empty:
        return {}
    tc = triggers_cell.copy()
    tc["yq"] = tc.index.to_period("Q").astype(str)
    out: Dict[str, Dict] = {}
    for yq, sub in tc.groupby("yq"):
        net = trade_dir * sub[fwd_col].values - FEE_RT
        n = len(net)
        if n < 2:
            out[yq] = {"n": n, "t": None, "mean_bp": None}
            continue
        sd = float(np.std(net, ddof=1))
        t = float(np.mean(net) / sd * np.sqrt(n)) if sd > 0 else 0.0
        out[yq] = {
            "n": int(n),
            "t": t,
            "mean_bp": float(np.mean(net) * 1e4),
            "pos_t": bool(t > 0),
        }
    return out


def unconditional_baseline(
    panels: Dict[str, pd.DataFrame], fwd_col: str, trade_dir: int,
) -> Dict:
    parts = []
    for sym, df in panels.items():
        sub = df.loc[df["vwap_z"].notna(), fwd_col].dropna()
        if not sub.empty:
            parts.append(sub.values)
    if not parts:
        return {"n": 0, "mean_bp": None, "t": None}
    pool = np.concatenate(parts)
    net = trade_dir * pool - FEE_RT
    n = len(net)
    if n < 2:
        return {"n": n, "mean_bp": None, "t": None}
    sd = float(np.std(net, ddof=1))
    t = float(np.mean(net) / sd * np.sqrt(n)) if sd > 0 else 0.0
    return {
        "n": int(n),
        "mean_bp": float(np.mean(net) * 1e4),
        "t": t,
        "trade_direction": int(trade_dir),
    }


def main():
    log.info(
        "paradigm_%d START — VWAP deviation axis FIRST-USE (campaign novel statistic class)",
        PARADIGM_COUNTER,
    )
    panels = build_panel()
    if not panels:
        raise RuntimeError("no panels built — substrate failed")
    log.info("panels built: %d/%d syms", len(panels), len(SYMBOLS_20))

    # ----- Per-sym empirical distribution / Item 3 sample density verify -----
    per_sym_z_diagnostics = {}
    for sym, df in panels.items():
        z = df["vwap_z"].dropna()
        if len(z) < 100:
            continue
        per_sym_z_diagnostics[sym] = {
            "n_valid": int(len(z)),
            "z_min": float(z.min()),
            "z_p01": float(z.quantile(0.01)),
            "z_p99": float(z.quantile(0.99)),
            "z_max": float(z.max()),
            "n_z_le_neg2": int((z <= -Z_PRIMARY).sum()),
            "n_z_ge_pos2": int((z >= Z_PRIMARY).sum()),
            "n_z_le_neg1p5": int((z <= -Z_SENSITIVITY).sum()),
            "n_z_ge_pos1p5": int((z >= Z_SENSITIVITY).sum()),
        }

    log.info("Per-sym z diagnostics computed for %d syms.", len(per_sym_z_diagnostics))
    for sym, d in per_sym_z_diagnostics.items():
        log.info(
            "  %s: n_valid=%d z_min=%.2f z_max=%.2f n_neg2=%d n_pos2=%d",
            sym, d["n_valid"], d["z_min"], d["z_max"], d["n_z_le_neg2"], d["n_z_ge_pos2"],
        )

    total_neg2 = sum(d["n_z_le_neg2"] for d in per_sym_z_diagnostics.values())
    total_pos2 = sum(d["n_z_ge_pos2"] for d in per_sym_z_diagnostics.values())
    log.info(
        "Total z<=-2 triggers=%d, z>=+2 triggers=%d",
        total_neg2, total_pos2,
    )

    # ----- 4-quadrant SNT for each hold -----
    all_results: Dict[str, Dict] = {}
    for hold_label in HOLDS_BARS.keys():
        log.info("---- hold=%s ----", hold_label)
        triggers = collect_triggers(panels, Z_PRIMARY, hold_label)
        fwd_col = f"fwd_{hold_label}"
        pool = build_candidate_pool(panels, hold_label)

        snt = four_quadrant_snt(triggers, fwd_col, Z_PRIMARY)
        cell_filters = {
            "A_focus_ABOVE_UP_LONG":    ((triggers["vwap_z"] >= Z_PRIMARY) & (triggers["bar_dir"] > 0), +1),
            "A_mirror_ABOVE_UP_SHORT":  ((triggers["vwap_z"] >= Z_PRIMARY) & (triggers["bar_dir"] > 0), -1),
            "B_same_BELOW_DOWN_SHORT":  ((triggers["vwap_z"] <= -Z_PRIMARY) & (triggers["bar_dir"] < 0), -1),
            "B_mirror_BELOW_DOWN_LONG": ((triggers["vwap_z"] <= -Z_PRIMARY) & (triggers["bar_dir"] < 0), +1),
        }
        three_gate = {}
        per_sym = {}
        per_q = {}
        for cell_name, (mask, dirn) in cell_filters.items():
            cell_trig = triggers.loc[mask] if not triggers.empty else triggers
            tg = three_gate_for_cell(cell_trig, dirn, pool, fwd_col, n_perms=1000)
            three_gate[cell_name] = tg
            if not cell_trig.empty:
                per_sym[cell_name] = per_sym_bootstrap(cell_trig, dirn, fwd_col)
                per_q[cell_name] = per_quarter_t(cell_trig, dirn, fwd_col)
            else:
                per_sym[cell_name] = {}
                per_q[cell_name] = {}

        uncond_long = unconditional_baseline(panels, fwd_col, +1)
        uncond_short = unconditional_baseline(panels, fwd_col, -1)

        all_results[hold_label] = {
            "snt_4_quadrant": snt,
            "three_gate_per_cell": three_gate,
            "per_sym_ci": per_sym,
            "per_quarter_t": per_q,
            "unconditional_baseline_long": uncond_long,
            "unconditional_baseline_short": uncond_short,
            "candidate_pool_size": int(len(pool)),
        }

        for cell_name, tg in three_gate.items():
            sigex = tg.get("signal_t_excess", float("nan"))
            ci_lo = tg.get("ci_lower_bp", float("nan"))
            ci_hi = tg.get("ci_upper_bp", float("nan"))
            perm_p = tg.get("perm_p", float("nan"))
            log.info(
                "  cell %s: n=%s sigex=%.2f ci=[%.2f,%.2f]bp perm_p=%.3f -> %s",
                cell_name,
                tg.get("n_observed", "?"),
                sigex if np.isfinite(sigex) else float("nan"),
                ci_lo if np.isfinite(ci_lo) else float("nan"),
                ci_hi if np.isfinite(ci_hi) else float("nan"),
                perm_p if np.isfinite(perm_p) else float("nan"),
                tg.get("verdict", "?"),
            )

    # ----- Sensitivity at |z|>=1.5 -----
    triggers_15 = collect_triggers(panels, Z_SENSITIVITY, PRIMARY_HOLD)
    fwd_col_p = f"fwd_{PRIMARY_HOLD}"
    pool_p = build_candidate_pool(panels, PRIMARY_HOLD)
    sens_filters = {
        "A_focus_ABOVE_UP_LONG":    ((triggers_15["vwap_z"] >= Z_SENSITIVITY) & (triggers_15["bar_dir"] > 0), +1),
        "B_same_BELOW_DOWN_SHORT":  ((triggers_15["vwap_z"] <= -Z_SENSITIVITY) & (triggers_15["bar_dir"] < 0), -1),
    } if not triggers_15.empty else {}
    sens = {}
    for cell_name, (mask, dirn) in sens_filters.items():
        cell_trig = triggers_15.loc[mask]
        sens[cell_name] = three_gate_for_cell(cell_trig, dirn, pool_p, fwd_col_p, n_perms=500)

    # ----- Era stratify -----
    triggers_p = collect_triggers(panels, Z_PRIMARY, PRIMARY_HOLD)
    era_stratify = {}
    era_filters = {
        "A_focus_ABOVE_UP_LONG":    (+1, True),
        "A_mirror_ABOVE_UP_SHORT":  (-1, True),
        "B_same_BELOW_DOWN_SHORT":  (-1, False),
        "B_mirror_BELOW_DOWN_LONG": (+1, False),
    }
    for cell_name, (dirn, is_A) in era_filters.items():
        if triggers_p.empty:
            era_stratify[cell_name] = {}
            continue
        if is_A:
            mask = (triggers_p["vwap_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0)
        else:
            mask = (triggers_p["vwap_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0)
        cell_trig = triggers_p.loc[mask]
        eras = {}
        if cell_trig.empty:
            era_stratify[cell_name] = {}
            continue
        for era_yr, sub in cell_trig.groupby("era"):
            net = dirn * sub[fwd_col_p].values - FEE_RT
            n = len(net)
            if n < 2:
                eras[int(era_yr)] = {"n": int(n), "mean_bp": None, "t": None}
                continue
            sd = float(np.std(net, ddof=1))
            t = float(np.mean(net) / sd * np.sqrt(n)) if sd > 0 else 0.0
            eras[int(era_yr)] = {
                "n": int(n),
                "mean_bp": float(np.mean(net) * 1e4),
                "t": t,
                "pos_t": bool(t > 0),
            }
        era_stratify[cell_name] = eras

    # ----- Cross-set asymmetry (Item 7) -----
    if not triggers_p.empty:
        A_set = triggers_p[(triggers_p["vwap_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0)]
        B_set = triggers_p[(triggers_p["vwap_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0)]
        A_only_pos = triggers_p[triggers_p["vwap_z"] >= Z_PRIMARY]
        B_only_neg = triggers_p[triggers_p["vwap_z"] <= -Z_PRIMARY]
        cross_set = {
            "n_A_zpos_AND_UP": int(len(A_set)),
            "n_B_zneg_AND_DOWN": int(len(B_set)),
            "n_zpos_total": int(len(A_only_pos)),
            "n_zneg_total": int(len(B_only_neg)),
            "asymmetry_A_to_B": (
                float(len(A_set) / len(B_set)) if len(B_set) > 0 else float("inf")
            ),
        }
    else:
        cross_set = {"empty": True}

    # ----- Rolling 6m window per-cell t-stat consistency (Lesson #72 candidate) -----
    rolling_6m_consistency = {}
    if not triggers_p.empty:
        for cell_name, (dirn, is_A) in era_filters.items():
            if is_A:
                mask = (triggers_p["vwap_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0)
            else:
                mask = (triggers_p["vwap_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0)
            cell_trig = triggers_p.loc[mask]
            if cell_trig.empty:
                rolling_6m_consistency[cell_name] = {}
                continue
            tc = cell_trig.copy()
            tc["yhalf"] = tc.index.to_period("2Q").astype(str)
            half = {}
            for yh, sub in tc.groupby("yhalf"):
                net = dirn * sub[fwd_col_p].values - FEE_RT
                n = len(net)
                if n < 2:
                    half[yh] = {"n": n, "t": None, "mean_bp": None}
                    continue
                sd = float(np.std(net, ddof=1))
                t = float(np.mean(net) / sd * np.sqrt(n)) if sd > 0 else 0.0
                half[yh] = {
                    "n": int(n),
                    "t": t,
                    "mean_bp": float(np.mean(net) * 1e4),
                    "pos_t": bool(t > 0),
                }
            rolling_6m_consistency[cell_name] = half

    # ----- write metrics -----
    final = {
        "paradigm_counter": PARADIGM_COUNTER,
        "paradigm_slug": PARADIGM_SLUG,
        "axis_first_use": "VWAP deviation (volume-weighted price benchmark) — campaign novel statistic class",
        "predecessor_context": (
            "paradigm 218 R-1 graveyard (macro-event-anchored class Tier 4 retire candidate). "
            "VWAP class fresh axis, R-5 LIVE expansion NOT (Lesson #70 ESCAPE)."
        ),
        "config": {
            "z_primary": Z_PRIMARY,
            "z_sensitivity": Z_SENSITIVITY,
            "vwap_bars": VWAP_BARS,
            "z_bars": Z_BARS,
            "fee_rt": FEE_RT,
            "holds_bars": HOLDS_BARS,
            "primary_hold": PRIMARY_HOLD,
            "universe": SYMBOLS_20,
            "n_syms_built": len(panels),
        },
        "per_sym_z_diagnostics": per_sym_z_diagnostics,
        "lesson_40_structural_feasibility": {
            "total_z_le_neg2_triggers": total_neg2,
            "total_z_ge_pos2_triggers": total_pos2,
            "symmetric_feasible": bool(total_neg2 > 0 and total_pos2 > 0),
            "verdict": (
                "PASS — VWAP ratio symmetric ±2 feasibility verified"
                if (total_neg2 > 0 and total_pos2 > 0)
                else "FAIL — VWAP ratio z structural threshold infeasible"
            ),
        },
        "results_by_hold": all_results,
        "sensitivity_z_1p5_primary_hold": sens,
        "era_stratify_alpha_decay_primary_hold": era_stratify,
        "rolling_6m_consistency_primary_hold": rolling_6m_consistency,
        "cross_set_asymmetry_item_7": cross_set,
    }

    out_path = OUTPUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, default=str)
    log.info("metrics written: %s", out_path)


if __name__ == "__main__":
    main()
