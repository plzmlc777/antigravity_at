"""paradigm 215 R-1 PoC — log-turnover velocity z-spike directional 4h bilateral.

Reformulation of paradigm 214 (R-0 HALT Lesson #40 STRUCTURAL THRESHOLD INFEASIBILITY).

Spec
----
- Statistic: per-sym 4h log(volume / 30d-mean-OI) ratio → 30d rolling z-score
- Universe: 20 alts (paradigm 198 cohort)
- Substrate: 4h cache + OI 5min cache (resampled to 4h mean)
- Triggers: |z| >= 2 bilateral, disjoint trigger sets
  - A_focus:  z >= +2 × bar UP   × LONG (HIGH log-turnover continuation)
  - A_mirror: z >= +2 × bar UP   × SHORT
  - B_same:   z <= -2 × bar DOWN × SHORT (LOW log-turnover continuation)
  - B_mirror: z <= -2 × bar DOWN × LONG (Lesson #42 19th dogfood, NOT artifact)
- Holds: 4h primary + 8h + 12h + 24h sweep
- Threshold: |z| >= 2 primary + |z| >= 1.5 sensitivity
- Fee: 8 bp round-trip

Lesson #69 9-item template + Lesson #40 prescription compliance.
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
log = logging.getLogger("paradigm_215")

PARADIGM_COUNTER = 215
PARADIGM_SLUG = (
    "alt_per_sym_4h_log_volume_to_oi_ratio_turnover_velocity_30d_rolling_z_spike_"
    "directional_4h_bilateral"
)
OUTPUT_DIR = ROOT / "runs" / "research_track" / (
    f"paradigm_{PARADIGM_COUNTER}_{PARADIGM_SLUG}"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OHLCV_CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"
OI_CACHE_DIR = ROOT / "runs" / "microstructure" / "cache"

SYMBOLS_20 = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC",
    "BCH", "NEAR", "FIL", "WIF", "JUP", "PYTH", "DOT", "ETC", "UNI", "WLD",
]

ROLLING_BARS = 180  # 30d × 6 bars/day = 180 4h bars
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


def load_oi_4h_aggregated(sym: str) -> pd.DataFrame:
    """Load per-day OI 5min joblibs, concat, resample to 4h mean."""
    pattern = f"{sym}USDT__*.joblib"
    files = sorted(OI_CACHE_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(f"OI cache missing for {sym} (pattern={pattern})")
    parts: List[pd.DataFrame] = []
    for f in files:
        try:
            d = joblib.load(f)
            if d is None or len(d) == 0:
                continue
            if "open_interest" not in d.columns:
                continue
            parts.append(d[["open_interest"]])
        except Exception as e:
            log.debug("skip OI file %s: %s", f.name, e)
            continue
    if not parts:
        raise FileNotFoundError(f"OI cache empty for {sym}")
    oi = pd.concat(parts).sort_index()
    oi = oi[~oi.index.duplicated(keep="last")]
    # Resample 5min -> 4h MEAN of OI (OI is a stock variable, mean over the bar)
    oi_4h = oi["open_interest"].resample("4h", label="left", closed="left").mean()
    return oi_4h.to_frame("oi_4h")


def compute_log_turnover_z(
    ohlcv: pd.DataFrame, oi: pd.DataFrame, window: int = ROLLING_BARS,
) -> pd.DataFrame:
    """Compute per-bar log(volume / rolling-mean-OI) z-score over rolling window."""
    df = ohlcv.join(oi, how="left").copy()
    df["oi_rolling_mean"] = df["oi_4h"].rolling(window=window, min_periods=window).mean()
    # log-transform on ratio: log( (volume + eps) / (oi_rolling_mean + eps) )
    # Use eps tiny relative to typical magnitude to handle zero-volume bars.
    eps = 1e-9
    df["log_turnover"] = np.log((df["volume"] + eps) / (df["oi_rolling_mean"] + eps))
    df["log_turnover_zmean"] = (
        df["log_turnover"].rolling(window=window, min_periods=window).mean()
    )
    df["log_turnover_zstd"] = (
        df["log_turnover"].rolling(window=window, min_periods=window).std(ddof=1)
    )
    df["log_turnover_z"] = (
        (df["log_turnover"] - df["log_turnover_zmean"]) / df["log_turnover_zstd"]
    )
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    # Bar direction at trigger bar (close vs open)
    df["bar_dir"] = np.sign(df["close"] - df["open"]).astype(float)
    return df


def compute_forward_returns(ohlcv: pd.DataFrame, holds_bars: Dict[str, int]) -> pd.DataFrame:
    """Forward simple returns at each hold horizon. Entry at next-bar open after
    trigger bar (avoid look-ahead). Use close-to-close on next H bars as proxy
    of trade outcome over the hold horizon.
    """
    out = pd.DataFrame(index=ohlcv.index)
    # Entry on next bar's open, exit on close H bars later → next_open ... close(t+H)
    next_open = ohlcv["open"].shift(-1)
    for label, h in holds_bars.items():
        exit_close = ohlcv["close"].shift(-h)
        out[f"fwd_{label}"] = (exit_close / next_open) - 1.0
    return out


# ---------- pipeline ---------------------------------------------------

def build_panel() -> Dict[str, pd.DataFrame]:
    """Build per-sym dataframe with log_turnover_z + forward returns."""
    panels: Dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS_20:
        try:
            ohlcv = load_ohlcv_4h(sym)
            oi = load_oi_4h_aggregated(sym)
        except FileNotFoundError as e:
            log.warning("skip %s: %s", sym, e)
            continue
        feat = compute_log_turnover_z(ohlcv, oi)
        fwd = compute_forward_returns(ohlcv, HOLDS_BARS)
        df = feat.join(fwd, how="left")
        df["sym"] = sym
        panels[sym] = df
        log.info(
            "panel %s: n=%d valid_z=%d trigger_pos=%d trigger_neg=%d",
            sym,
            len(df),
            int(df["log_turnover_z"].notna().sum()),
            int((df["log_turnover_z"] >= Z_PRIMARY).sum()),
            int((df["log_turnover_z"] <= -Z_PRIMARY).sum()),
        )
    return panels


def collect_triggers(panels: Dict[str, pd.DataFrame], z_thresh: float,
                     hold_label: str) -> pd.DataFrame:
    """Build trigger frame across all syms for a single threshold and hold."""
    fwd_col = f"fwd_{hold_label}"
    parts = []
    for sym, df in panels.items():
        sub = df[["log_turnover_z", "bar_dir", fwd_col, "sym"]].dropna()
        sub = sub[(sub["log_turnover_z"].abs() >= z_thresh) & (sub["bar_dir"] != 0)]
        if sub.empty:
            continue
        parts.append(sub)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts)
    out["era"] = out.index.year
    return out


def quadrant_classify(row, z_thresh: float) -> str:
    z = row["log_turnover_z"]
    bd = row["bar_dir"]
    if z >= z_thresh and bd > 0:
        return "A_focus_HIGH_UP_LONG"
    if z >= z_thresh and bd < 0:
        return "A_mirror_HIGH_DOWN_LONG"
    # bar direction is the trigger-bar direction; mirror cells defined by
    # bar direction not opposite-of-A. Use spec exact:
    # A_focus: z>=+2 × bar UP × LONG    -> z>=+2 bd>0 dir=+1
    # A_mirror: z>=+2 × bar UP × SHORT  -> z>=+2 bd>0 dir=-1
    # B_same:  z<=-2 × bar DOWN × SHORT -> z<=-2 bd<0 dir=-1
    # B_mirror: z<=-2 × bar DOWN × LONG -> z<=-2 bd<0 dir=+1
    # So the "quadrant" key by (z_sign, bar_dir) and we'll attach two trade
    # directions per cell separately.
    if z <= -z_thresh and bd < 0:
        return "B_DOWN_zneg"
    if z <= -z_thresh and bd > 0:
        return "B_UP_zneg"
    if z >= z_thresh and bd < 0:
        return "A_DOWN_zpos"
    if z >= z_thresh and bd > 0:
        return "A_UP_zpos"
    return "other"


def four_quadrant_snt(
    triggers: pd.DataFrame, fwd_col: str, z_thresh: float,
) -> Dict[str, Dict]:
    """Compute 4-quadrant SNT per spec.

    The 4 cells are DISJOINT trigger sets keyed by (z_sign, bar_dir),
    with a fixed trade direction per cell.

    A_focus:  (z>=+T) ∧ (bar UP)   LONG
    A_mirror: (z>=+T) ∧ (bar UP)   SHORT
    B_same:   (z<=-T) ∧ (bar DOWN) SHORT
    B_mirror: (z<=-T) ∧ (bar DOWN) LONG

    A_focus and A_mirror share the SAME trigger set (z>=+T ∧ UP) but opposite
    direction. Same for B_same and B_mirror.
    """
    results: Dict[str, Dict] = {}

    # Cell A trigger set: z>=+T AND bar UP
    A_mask = (triggers["log_turnover_z"] >= z_thresh) & (triggers["bar_dir"] > 0)
    A_set = triggers.loc[A_mask].copy()
    # Cell B trigger set: z<=-T AND bar DOWN
    B_mask = (triggers["log_turnover_z"] <= -z_thresh) & (triggers["bar_dir"] < 0)
    B_set = triggers.loc[B_mask].copy()

    cells = {
        "A_focus_HIGH_UP_LONG":     (A_set, +1),
        "A_mirror_HIGH_UP_SHORT":   (A_set, -1),
        "B_same_LOW_DOWN_SHORT":    (B_set, -1),
        "B_mirror_LOW_DOWN_LONG":   (B_set, +1),
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
        # win rate
        win_rate = float((gross > FEE_RT).mean())
        # Quarter spread (era)
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
    """Compute three-gate (signal_t_excess, ci_lower_bp, perm_p) for a cell."""
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
    # Candidate pool: GROSS returns of ALL forward windows (any direction).
    # The pool is direction-agnostic; we apply same direction to candidate pool
    # by mirroring observation direction.
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
    # one-sided depending on direction of observed t
    perm_p = perm_p_above if fa.get("obs_t", 0.0) > 0 else perm_p_below
    sigex = float(fa.get("signal_t_excess", float("nan")))

    # Three-gate verdict
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
    """All forward returns over the panel, valid where z is defined (after warm-up)."""
    fwd_col = f"fwd_{hold_label}"
    parts = []
    for sym, df in panels.items():
        sub = df.loc[df["log_turnover_z"].notna(), fwd_col].dropna()
        if not sub.empty:
            parts.append(sub.values)
    if not parts:
        return np.array([])
    return np.concatenate(parts)


def per_sym_bootstrap(
    triggers_cell: pd.DataFrame, trade_dir: int, fwd_col: str,
) -> Dict[str, Dict]:
    """Per-sym CI for Concentration gate."""
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
    """Per-quarter t-stat for Concentration gate (era proxy via year-quarter)."""
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
    """Lesson #39 sub-class B: unconditional baseline test — apply same trade
    direction to ALL bars (no z trigger). If unconditional bias is significant,
    A_focus PASS may be artifact.
    """
    parts = []
    for sym, df in panels.items():
        sub = df.loc[df["log_turnover_z"].notna(), fwd_col].dropna()
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
        "paradigm_%d START — log-transform reformulation of paradigm 214 "
        "(Lesson #40 prescription 1st 처방 사례)",
        PARADIGM_COUNTER,
    )
    panels = build_panel()
    if not panels:
        raise RuntimeError("no panels built — substrate failed")
    log.info("panels built: %d/%d syms", len(panels), len(SYMBOLS_20))

    # ----- Per-sym log-transform empirical distribution -----
    per_sym_z_diagnostics = {}
    for sym, df in panels.items():
        z = df["log_turnover_z"].dropna()
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

    log.info(
        "Per-sym z diagnostics computed: %d syms. "
        "Cell B feasibility check (z<=-2 trigger counts):",
        len(per_sym_z_diagnostics),
    )
    for sym, d in per_sym_z_diagnostics.items():
        log.info(
            "  %s: n_valid=%d z_min=%.2f n_neg2=%d n_pos2=%d",
            sym, d["n_valid"], d["z_min"], d["n_z_le_neg2"], d["n_z_ge_pos2"],
        )

    # Verify Lesson #40 prescription: cell B trigger count
    total_neg2 = sum(d["n_z_le_neg2"] for d in per_sym_z_diagnostics.values())
    total_pos2 = sum(d["n_z_ge_pos2"] for d in per_sym_z_diagnostics.values())
    log.info(
        "Lesson #40 prescription verification: total z<=-2 triggers=%d, z>=+2 triggers=%d",
        total_neg2, total_pos2,
    )

    # ----- 4-quadrant SNT for primary hold and threshold -----
    all_results: Dict[str, Dict] = {}
    for hold_label in HOLDS_BARS.keys():
        log.info("---- hold=%s ----", hold_label)
        triggers = collect_triggers(panels, Z_PRIMARY, hold_label)
        fwd_col = f"fwd_{hold_label}"
        pool = build_candidate_pool(panels, hold_label)

        snt = four_quadrant_snt(triggers, fwd_col, Z_PRIMARY)
        # Run three-gate per cell
        cell_filters = {
            "A_focus_HIGH_UP_LONG":   ((triggers["log_turnover_z"] >= Z_PRIMARY) & (triggers["bar_dir"] > 0), +1),
            "A_mirror_HIGH_UP_SHORT": ((triggers["log_turnover_z"] >= Z_PRIMARY) & (triggers["bar_dir"] > 0), -1),
            "B_same_LOW_DOWN_SHORT":  ((triggers["log_turnover_z"] <= -Z_PRIMARY) & (triggers["bar_dir"] < 0), -1),
            "B_mirror_LOW_DOWN_LONG": ((triggers["log_turnover_z"] <= -Z_PRIMARY) & (triggers["bar_dir"] < 0), +1),
        }
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

        # Unconditional baseline (Lesson #39 sub-class B) for primary hold
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
            log.info(
                "  cell %s: n=%s sigex=%.2f ci=[%.2f,%.2f]bp perm_p=%.3f -> %s",
                cell_name,
                tg.get("n_observed", "?"),
                tg.get("signal_t_excess", float("nan")) if np.isfinite(tg.get("signal_t_excess", float("nan"))) else float("nan"),
                tg.get("ci_lower_bp", float("nan")) if np.isfinite(tg.get("ci_lower_bp", float("nan"))) else float("nan"),
                tg.get("ci_upper_bp", float("nan")) if np.isfinite(tg.get("ci_upper_bp", float("nan"))) else float("nan"),
                tg.get("perm_p", float("nan")) if np.isfinite(tg.get("perm_p", float("nan"))) else float("nan"),
                tg.get("verdict", "?"),
            )

    # ----- Sensitivity at |z|>=1.5 (primary hold only) -----
    triggers_15 = collect_triggers(panels, Z_SENSITIVITY, PRIMARY_HOLD)
    fwd_col_p = f"fwd_{PRIMARY_HOLD}"
    pool_p = build_candidate_pool(panels, PRIMARY_HOLD)
    sens_filters = {
        "A_focus_HIGH_UP_LONG":   ((triggers_15["log_turnover_z"] >= Z_SENSITIVITY) & (triggers_15["bar_dir"] > 0), +1),
        "B_same_LOW_DOWN_SHORT":  ((triggers_15["log_turnover_z"] <= -Z_SENSITIVITY) & (triggers_15["bar_dir"] < 0), -1),
    }
    sens = {}
    for cell_name, (mask, dirn) in sens_filters.items():
        cell_trig = triggers_15.loc[mask]
        sens[cell_name] = three_gate_for_cell(cell_trig, dirn, pool_p, fwd_col_p, n_perms=500)

    # ----- Era stratify (alpha decay 5-pattern audit, Item 6) -----
    triggers_p = collect_triggers(panels, Z_PRIMARY, PRIMARY_HOLD)
    era_stratify = {}
    for cell_name, (mask, dirn) in {
        "A_focus_HIGH_UP_LONG":   ((triggers_p["log_turnover_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0), +1),
        "A_mirror_HIGH_UP_SHORT": ((triggers_p["log_turnover_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0), -1),
        "B_same_LOW_DOWN_SHORT":  ((triggers_p["log_turnover_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0), -1),
        "B_mirror_LOW_DOWN_LONG": ((triggers_p["log_turnover_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0), +1),
    }.items():
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

    # ----- Cross-set |A| vs |B| asymmetry (Item 7) -----
    A_set = triggers_p[(triggers_p["log_turnover_z"] >= Z_PRIMARY) & (triggers_p["bar_dir"] > 0)]
    B_set = triggers_p[(triggers_p["log_turnover_z"] <= -Z_PRIMARY) & (triggers_p["bar_dir"] < 0)]
    A_only_pos = triggers_p[triggers_p["log_turnover_z"] >= Z_PRIMARY]
    B_only_neg = triggers_p[triggers_p["log_turnover_z"] <= -Z_PRIMARY]
    cross_set = {
        "n_A_zpos_AND_UP": int(len(A_set)),
        "n_B_zneg_AND_DOWN": int(len(B_set)),
        "n_zpos_total": int(len(A_only_pos)),
        "n_zneg_total": int(len(B_only_neg)),
        "asymmetry_A_to_B": (
            float(len(A_set) / len(B_set)) if len(B_set) > 0 else float("inf")
        ),
    }

    # ----- write metrics -----
    final = {
        "paradigm_counter": PARADIGM_COUNTER,
        "paradigm_slug": PARADIGM_SLUG,
        "lesson_40_prescription": "log-transform on volume/OI multiplicative composite (1st 처방 사례)",
        "predecessor": "paradigm 214 R-0 HALT Lesson #40 STRUCTURAL THRESHOLD INFEASIBILITY",
        "config": {
            "z_primary": Z_PRIMARY,
            "z_sensitivity": Z_SENSITIVITY,
            "rolling_bars": ROLLING_BARS,
            "fee_rt": FEE_RT,
            "holds_bars": HOLDS_BARS,
            "primary_hold": PRIMARY_HOLD,
            "universe": SYMBOLS_20,
            "n_syms_built": len(panels),
        },
        "per_sym_log_z_diagnostics": per_sym_z_diagnostics,
        "lesson_40_verification": {
            "total_z_le_neg2_triggers": total_neg2,
            "total_z_ge_pos2_triggers": total_pos2,
            "symmetric_feasible": bool(total_neg2 > 0 and total_pos2 > 0),
            "verdict": (
                "PASS — log-transform restored symmetric ±2 feasibility"
                if (total_neg2 > 0 and total_pos2 > 0)
                else "FAIL — log-transform did NOT restore feasibility"
            ),
        },
        "results_by_hold": all_results,
        "sensitivity_z_1p5_primary_hold": sens,
        "era_stratify_alpha_decay_primary_hold": era_stratify,
        "cross_set_asymmetry_item_7": cross_set,
    }

    out_path = OUTPUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, default=str)
    log.info("metrics written: %s", out_path)


if __name__ == "__main__":
    main()
