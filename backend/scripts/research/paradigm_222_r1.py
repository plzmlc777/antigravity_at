"""paradigm 222 R-1 PoC — per-sym 1d close-to-close return realized vol 7d rolling
z-spike directional 1d-to-3d swing bilateral.

1d swing trade horizon class FIRST-USE in campaign (Item 9 capital util ceiling
회피 시도 — 4h sparse-trigger formal universal에 회피).

Spec
----
- Substrate: 4h cache 12col aggregated to 1d (resample by day, last close, sum vol)
- Statistic: per-sym 1d close-to-close return, then 7d rolling realized vol
  (std of 7d log returns), then 60d rolling z-score of that vol series.
- Universe: 20 alts (paradigm 198 cohort)
- Triggers: |z| >= 2 bilateral, disjoint A/B trigger sets (Lesson #39 sub-class A avoidance)
  - A_focus:   z >= +2 (HIGH vol regime) × bar UP   × LONG continuation
  - A_mirror:  z >= +2 × bar UP   × SHORT reversal
  - B_same:    z <= -2 (LOW vol regime,  DISJOINT) × bar DOWN × SHORT continuation
  - B_mirror:  z <= -2 × bar DOWN × LONG  reversal (Lesson #42 23rd dogfood)
- Holds: 1d primary + 2d + 3d sweep (swing horizon, 4h hold class 회피)
- Fee: 8 bp round-trip
- Era stratify: 2024 / 2025 / 2026 — Pattern P1 (10th consecutive test) +
  2026 era-universal decay (8th instance test)

Lesson #69 9-item template + Lesson #39/40/42/67/68/70/72 compliance.
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
log = logging.getLogger("paradigm_222")

PARADIGM_COUNTER = 222
PARADIGM_SLUG = (
    "alt_per_sym_1d_close_to_close_return_realized_vol_7d_rolling_"
    "z_spike_directional_1d_to_3d_swing_bilateral"
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

# Trigger params
RV_WINDOW = 7        # 7d rolling realized vol
Z_WINDOW = 60        # 60d rolling z-score of vol
Z_PRIMARY = 2.0
Z_SENSITIVITY = 1.5
FEE_RT = 0.0008

# Hold horizons in 1d bars
HOLDS_DAYS = {"1d": 1, "2d": 2, "3d": 3}
PRIMARY_HOLD = "1d"


# ---------- data loading -----------------------------------------------

def load_ohlcv_1d(sym: str) -> pd.DataFrame:
    """Load 4h cache and aggregate to 1d bars (day close, day open, day vol)."""
    path = OHLCV_CACHE_DIR / f"{sym}USDT_4h.joblib"
    if not path.exists():
        raise FileNotFoundError(f"4h cache missing for {sym}: {path}")
    df = joblib.load(path)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index, utc=False)
    df.sort_index(inplace=True)
    # aggregate 4h -> 1d
    daily = pd.DataFrame()
    g = df.resample("1D")
    daily["open"] = g["open"].first()
    daily["high"] = g["high"].max()
    daily["low"] = g["low"].min()
    daily["close"] = g["close"].last()
    daily["volume"] = g["volume"].sum()
    daily.dropna(subset=["close"], inplace=True)
    return daily


def compute_rv_z(
    ohlcv_1d: pd.DataFrame, rv_window: int = RV_WINDOW, z_window: int = Z_WINDOW,
) -> pd.DataFrame:
    """Compute per-bar 7d realized vol z-score on 1d frame.

    log_ret = log(close / close_prev)
    rv_7d = rolling_std(log_ret, 7d)
    rv_z_60d = (rv_7d - rolling_mean(rv_7d, 60d)) / rolling_std(rv_7d, 60d)
    bar_dir = sign(close - open)  on 1d bar
    """
    df = ohlcv_1d.copy()
    df["log_ret_1d"] = np.log(df["close"] / df["close"].shift(1))
    df["rv_7d"] = df["log_ret_1d"].rolling(window=rv_window, min_periods=rv_window).std(ddof=1)
    df["rv_z_mean"] = df["rv_7d"].rolling(window=z_window, min_periods=z_window).mean()
    df["rv_z_std"] = df["rv_7d"].rolling(window=z_window, min_periods=z_window).std(ddof=1)
    df["rv_z"] = (df["rv_7d"] - df["rv_z_mean"]) / df["rv_z_std"]
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df["bar_dir"] = np.sign(df["close"] - df["open"]).astype(float)
    return df


def compute_forward_returns(ohlcv_1d: pd.DataFrame, holds_days: Dict[str, int]) -> pd.DataFrame:
    out = pd.DataFrame(index=ohlcv_1d.index)
    next_open = ohlcv_1d["open"].shift(-1)
    for label, h in holds_days.items():
        exit_close = ohlcv_1d["close"].shift(-h)
        out[f"fwd_{label}"] = (exit_close / next_open) - 1.0
    return out


# ---------- pipeline ---------------------------------------------------

def build_panel() -> Dict[str, pd.DataFrame]:
    panels: Dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS_20:
        try:
            ohlcv_1d = load_ohlcv_1d(sym)
        except FileNotFoundError as e:
            log.warning("skip %s: %s", sym, e)
            continue
        feat = compute_rv_z(ohlcv_1d)
        fwd = compute_forward_returns(ohlcv_1d, HOLDS_DAYS)
        df = feat.join(fwd, how="left")
        df["sym"] = sym
        panels[sym] = df
        log.info(
            "panel %s: n_1d=%d valid_z=%d trigger_pos=%d trigger_neg=%d",
            sym,
            len(df),
            int(df["rv_z"].notna().sum()),
            int((df["rv_z"] >= Z_PRIMARY).sum()),
            int((df["rv_z"] <= -Z_PRIMARY).sum()),
        )
    return panels


def collect_triggers(panels: Dict[str, pd.DataFrame], z_thresh: float,
                     hold_label: str) -> pd.DataFrame:
    fwd_col = f"fwd_{hold_label}"
    parts = []
    for sym, df in panels.items():
        sub = df[["rv_z", "bar_dir", fwd_col, "sym"]].dropna()
        sub = sub[(sub["rv_z"].abs() >= z_thresh) & (sub["bar_dir"] != 0)]
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

    A trigger set: rv_z>=+T AND bar UP   (HIGH vol regime + up move)
    B trigger set: rv_z<=-T AND bar DOWN (LOW  vol regime + down move)
    """
    results: Dict[str, Dict] = {}
    A_mask = (triggers["rv_z"] >= z_thresh) & (triggers["bar_dir"] > 0)
    A_set = triggers.loc[A_mask].copy()
    B_mask = (triggers["rv_z"] <= -z_thresh) & (triggers["bar_dir"] < 0)
    B_set = triggers.loc[B_mask].copy()

    cells = {
        "A_focus_HIGHVOL_UP_LONG":     (A_set, +1),
        "A_mirror_HIGHVOL_UP_SHORT":   (A_set, -1),
        "B_same_LOWVOL_DOWN_SHORT":    (B_set, -1),
        "B_mirror_LOWVOL_DOWN_LONG":   (B_set, +1),
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
        sub = df.loc[df["rv_z"].notna(), fwd_col].dropna()
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
        sub = df.loc[df["rv_z"].notna(), fwd_col].dropna()
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
        "paradigm_%d START — 1d swing horizon class FIRST-USE "
        "(per-sym 1d realized vol z-spike, hold 1d/2d/3d)",
        PARADIGM_COUNTER,
    )
    panels = build_panel()
    if not panels:
        raise RuntimeError("no panels built — substrate failed")
    log.info("panels built: %d/%d syms", len(panels), len(SYMBOLS_20))

    # ----- Per-sym empirical distribution / Item 3 sample density -----
    per_sym_z_diagnostics = {}
    for sym, df in panels.items():
        z = df["rv_z"].dropna()
        if len(z) < 60:
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
    log.info("Total z<=-2 triggers=%d, z>=+2 triggers=%d", total_neg2, total_pos2)

    # ----- 4-quadrant SNT for each hold -----
    all_results: Dict[str, Dict] = {}
    for hold_label in HOLDS_DAYS.keys():
        log.info("---- hold=%s ----", hold_label)
        triggers = collect_triggers(panels, Z_PRIMARY, hold_label)
        fwd_col = f"fwd_{hold_label}"
        pool = build_candidate_pool(panels, hold_label)

        snt = four_quadrant_snt(triggers, fwd_col, Z_PRIMARY)
        if not triggers.empty:
            cell_filters = {
                "A_focus_HIGHVOL_UP_LONG":     ((triggers["rv_z"] >= Z_PRIMARY) & (triggers["bar_dir"] > 0), +1),
                "A_mirror_HIGHVOL_UP_SHORT":   ((triggers["rv_z"] >= Z_PRIMARY) & (triggers["bar_dir"] > 0), -1),
                "B_same_LOWVOL_DOWN_SHORT":    ((triggers["rv_z"] <= -Z_PRIMARY) & (triggers["bar_dir"] < 0), -1),
                "B_mirror_LOWVOL_DOWN_LONG":   ((triggers["rv_z"] <= -Z_PRIMARY) & (triggers["bar_dir"] < 0), +1),
            }
        else:
            cell_filters = {}
        three_gate = {}
        per_sym = {}
        per_q = {}
        for cell_name, (mask, dirn) in cell_filters.items():
            cell_trig = triggers.loc[mask]
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

    # ----- Sensitivity at |z|>=1.5 on primary hold -----
    triggers_15 = collect_triggers(panels, Z_SENSITIVITY, PRIMARY_HOLD)
    fwd_col_p = f"fwd_{PRIMARY_HOLD}"
    pool_p = build_candidate_pool(panels, PRIMARY_HOLD)
    if not triggers_15.empty:
        sens_filters = {
            "A_focus_HIGHVOL_UP_LONG":     ((triggers_15["rv_z"] >= Z_SENSITIVITY) & (triggers_15["bar_dir"] > 0), +1),
            "B_same_LOWVOL_DOWN_SHORT":    ((triggers_15["rv_z"] <= -Z_SENSITIVITY) & (triggers_15["bar_dir"] < 0), -1),
        }
    else:
        sens_filters = {}
    sens = {}
    for cell_name, (mask, dirn) in sens_filters.items():
        cell_trig = triggers_15.loc[mask]
        sens[cell_name] = three_gate_for_cell(cell_trig, dirn, pool_p, fwd_col_p, n_perms=500)

    # ----- Era stratify (alpha decay informational learning audit) -----
    triggers_p = collect_triggers(panels, Z_PRIMARY, PRIMARY_HOLD)
    era_stratify = {}
    era_filters = {
        "A_focus_HIGHVOL_UP_LONG":     (+1, True),
        "A_mirror_HIGHVOL_UP_SHORT":   (-1, True),
        "B_same_LOWVOL_DOWN_SHORT":    (-1, False),
        "B_mirror_LOWVOL_DOWN_LONG":   (+1, False),
    }
    for cell_name, (dirn, is_A) in era_filters.items():
        if triggers_p.empty:
            era_stratify[cell_name] = {}
            continue
        if is_A:
            mask = (triggers_p["rv_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0)
        else:
            mask = (triggers_p["rv_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0)
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

    # ----- Cross-set asymmetry (Item 7, 10th instance) -----
    if not triggers_p.empty:
        A_set = triggers_p[(triggers_p["rv_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0)]
        B_set = triggers_p[(triggers_p["rv_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0)]
        A_only_pos = triggers_p[triggers_p["rv_z"] >= Z_PRIMARY]
        B_only_neg = triggers_p[triggers_p["rv_z"] <= -Z_PRIMARY]
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
                mask = (triggers_p["rv_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0)
            else:
                mask = (triggers_p["rv_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0)
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

    # ----- Life-changing 4-dim STRUCTURAL prescreen (Item 9, 6th operational) -----
    # Capital util heuristic: avg n_concurrent_holds / universe_size
    item9 = {}
    for hold_label, h_days in HOLDS_DAYS.items():
        trig_h = collect_triggers(panels, Z_PRIMARY, hold_label)
        if trig_h.empty:
            item9[hold_label] = {"n_total": 0}
            continue
        # universe-coverage: trades/yr aggregate + per-sym mean
        years_obs = (trig_h.index.max() - trig_h.index.min()).days / 365.25
        n_total = len(trig_h)
        trades_per_yr = float(n_total / years_obs) if years_obs > 0 else float("nan")
        # capital util heuristic: hold_days * n_total / (universe * total_days)
        total_days = (trig_h.index.max() - trig_h.index.min()).days
        capital_util_est = (
            float(h_days * n_total / (len(SYMBOLS_20) * total_days))
            if total_days > 0 else float("nan")
        )
        item9[hold_label] = {
            "n_total": int(n_total),
            "trades_per_yr_estimate": trades_per_yr,
            "capital_util_estimate": capital_util_est,
            "hold_days": h_days,
            "years_obs": float(years_obs),
            "util_passes_30pct": bool(capital_util_est >= 0.30),
        }

    # ----- write metrics -----
    final = {
        "paradigm_counter": PARADIGM_COUNTER,
        "paradigm_slug": PARADIGM_SLUG,
        "axis_first_use": (
            "1d swing horizon class (per-sym 1d realized vol 7d rolling z-spike, "
            "hold 1d/2d/3d) — campaign-first multi-day swing horizon class. "
            "Item 9 capital util 30%+ feasibility direct test (4h sparse-trigger "
            "ceiling 회피)."
        ),
        "predecessor_context": (
            "paradigm 221 graveyard (Pattern P1 9th + 2026 era-universal 7th + "
            "Item 9 STRUCTURAL FAIL 5th + Lesson #40 prescription 2nd methodologically "
            "functional but mechanism non-alpha). paradigm 222 = 1d swing horizon "
            "class first-use, hold horizon distinct from 4h sparse-trigger class."
        ),
        "config": {
            "z_primary": Z_PRIMARY,
            "z_sensitivity": Z_SENSITIVITY,
            "rv_window_days": RV_WINDOW,
            "z_window_days": Z_WINDOW,
            "fee_rt": FEE_RT,
            "holds_days": HOLDS_DAYS,
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
                "PASS — 1d realized vol z symmetric ±2 feasibility verified"
                if (total_neg2 > 0 and total_pos2 > 0)
                else "FAIL — 1d realized vol z structural threshold infeasible"
            ),
        },
        "results_by_hold": all_results,
        "sensitivity_z_1p5_primary_hold": sens,
        "era_stratify_alpha_decay_primary_hold": era_stratify,
        "rolling_6m_consistency_primary_hold": rolling_6m_consistency,
        "cross_set_asymmetry_item_7": cross_set,
        "item_9_life_changing_structural_prescreen": item9,
    }

    out_path = OUTPUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, default=str)
    log.info("metrics written: %s", out_path)


if __name__ == "__main__":
    main()
