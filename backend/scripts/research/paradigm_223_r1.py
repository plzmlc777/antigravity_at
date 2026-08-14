"""paradigm 223 R-1 PoC — cross-sym co-firing density regime detection
≥5 alts simultaneous |rv_z|>=2 in same 4h bar × collective majority direction (≥3 same dir)
× universe-wide LONG/SHORT continuation 4h/8h hold.

Lesson #73 prescription 1st operational dogfood: density escape via cross-sym co-firing
→ Item 9 STRUCTURAL FAIL 회피 시도 (4h × 20 syms × ~3-5% co-firing rate ≈ 30%+ util).

paradigm-architect Candidate C self-recommend (mode-switch preserved).
[[feedback-lesson-74-candidate-per-sym-ohlcv-z-spike-halt-by-default]] ESCAPE 조건 1
(cross-sym co-firing regime detection) 1st operational dogfood test.

Spec
----
- Substrate: 4h cache 12col, 20 syms × 2.24yr (paradigm 198 cohort)
- Per-sym 7d (42 bars on 4h) realized vol z-score (60d window = 360 bars).
- Cross-sym co-firing event: in each 4h bar, count syms with |rv_z|>=2.
  Co-firing event = ≥5 alts trigger simultaneously.
- Collective regime majority direction:
  - UP regime: among ≥5 firing alts, ≥3 have bar_dir > 0 → universe-wide LONG
  - DOWN regime: among ≥5 firing alts, ≥3 have bar_dir < 0 → universe-wide SHORT
- Universe-level trade: aggregate forward return = mean across firing syms × trade_dir
- 4-quadrant SNT:
  - A_focus:   ≥5 co-firing × ≥3 UP × universe-wide LONG  continuation
  - A_mirror:  ≥5 co-firing × ≥3 UP × universe-wide SHORT reversal
  - B_same:    ≥5 co-firing × ≥3 DOWN × universe-wide SHORT continuation
  - B_mirror:  ≥5 co-firing × ≥3 DOWN × universe-wide LONG reversal (Lesson #42 24th)
- Holds: 4h primary + 8h sweep
- Fee: 8 bp round-trip (per universe-aggregate trade)
- Era stratify 2024/2025/2026 (Pattern P1 11th + 2026 universal 9th tests)
- Lesson #74 candidate ESCAPE 조건 1 verification: cross-sym co-firing distinct DNA

Lesson #69 9-item template compliance.
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
log = logging.getLogger("paradigm_223")

PARADIGM_COUNTER = 223
PARADIGM_SLUG = (
    "alt_cross_sym_co_firing_5plus_alts_simultaneous_realized_vol_z_spike_"
    "collective_regime_directional_4h_majority_dir"
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

# 4h-bar parameters
RV_WINDOW = 42      # 7d on 4h = 7*6 = 42 bars
Z_WINDOW = 360      # 60d on 4h = 60*6 = 360 bars
Z_PRIMARY = 2.0
Z_SENSITIVITY = 1.5
FEE_RT = 0.0008

# Co-firing event params
COFIRE_K_PRIMARY = 5      # ≥5 alts simultaneous |rv_z|>=2
COFIRE_DIR_MAJ = 3        # ≥3 same-direction within firing group
COFIRE_K_SENSITIVITY = 4  # sensitivity at ≥4

# Hold horizons in 4h bars
HOLDS_BARS = {"4h": 1, "8h": 2}
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


def compute_rv_z_4h(
    ohlcv_4h: pd.DataFrame, rv_window: int = RV_WINDOW, z_window: int = Z_WINDOW,
) -> pd.DataFrame:
    """Compute per-bar realized vol z-score on 4h frame.

    log_ret_4h = log(close / close_prev)
    rv_7d = rolling_std(log_ret_4h, 42 bars)
    rv_z_60d = (rv_7d - rolling_mean(rv_7d, 360 bars)) / rolling_std(rv_7d, 360 bars)
    bar_dir = sign(close - open) on 4h bar
    """
    df = ohlcv_4h.copy()
    df["log_ret_4h"] = np.log(df["close"] / df["close"].shift(1))
    df["rv_7d"] = df["log_ret_4h"].rolling(window=rv_window, min_periods=rv_window).std(ddof=1)
    df["rv_z_mean"] = df["rv_7d"].rolling(window=z_window, min_periods=z_window).mean()
    df["rv_z_std"] = df["rv_7d"].rolling(window=z_window, min_periods=z_window).std(ddof=1)
    df["rv_z"] = (df["rv_7d"] - df["rv_z_mean"]) / df["rv_z_std"]
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df["bar_dir"] = np.sign(df["close"] - df["open"]).astype(float)
    return df


def compute_forward_returns(ohlcv_4h: pd.DataFrame, holds_bars: Dict[str, int]) -> pd.DataFrame:
    """Universe-level entry at next-bar open, exit at close after h bars."""
    out = pd.DataFrame(index=ohlcv_4h.index)
    next_open = ohlcv_4h["open"].shift(-1)
    for label, h in holds_bars.items():
        exit_close = ohlcv_4h["close"].shift(-h)
        out[f"fwd_{label}"] = (exit_close / next_open) - 1.0
    return out


# ---------- pipeline ---------------------------------------------------

def build_panel() -> Dict[str, pd.DataFrame]:
    panels: Dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS_20:
        try:
            ohlcv_4h = load_ohlcv_4h(sym)
        except FileNotFoundError as e:
            log.warning("skip %s: %s", sym, e)
            continue
        feat = compute_rv_z_4h(ohlcv_4h)
        fwd = compute_forward_returns(ohlcv_4h, HOLDS_BARS)
        df = feat.join(fwd, how="left")
        df["sym"] = sym
        panels[sym] = df
        log.info(
            "panel %s: n_4h=%d valid_z=%d trig_pos2=%d trig_neg2=%d",
            sym,
            len(df),
            int(df["rv_z"].notna().sum()),
            int((df["rv_z"] >= Z_PRIMARY).sum()),
            int((df["rv_z"] <= -Z_PRIMARY).sum()),
        )
    return panels


def detect_co_firing_events(
    panels: Dict[str, pd.DataFrame], z_thresh: float, k_min: int, hold_label: str,
) -> pd.DataFrame:
    """Per 4h bar, count syms with |rv_z|>=z_thresh.
    Returns dataframe indexed by 4h bar timestamp with:
        - n_fire: total firing syms in bar
        - n_up: firing syms with bar_dir>0
        - n_down: firing syms with bar_dir<0
        - fwd_agg: mean forward return across firing syms
        - is_event: n_fire >= k_min
        - majority_dir: +1 if n_up >= COFIRE_DIR_MAJ, -1 if n_down >= COFIRE_DIR_MAJ, else 0
        - era: year
    """
    fwd_col = f"fwd_{hold_label}"
    # Build long-format frame of all (bar, sym) with rv_z, bar_dir, fwd
    parts = []
    for sym, df in panels.items():
        sub = df[["rv_z", "bar_dir", fwd_col]].copy()
        sub = sub.dropna(subset=["rv_z", "bar_dir"])
        sub["sym"] = sym
        sub["fires"] = (sub["rv_z"].abs() >= z_thresh) & (sub["bar_dir"] != 0)
        parts.append(sub)
    if not parts:
        return pd.DataFrame()
    long_df = pd.concat(parts)
    long_df["bar_ts"] = long_df.index
    fire = long_df[long_df["fires"]].copy()
    if fire.empty:
        return pd.DataFrame()
    # Aggregate per bar
    agg = fire.groupby("bar_ts").agg(
        n_fire=("sym", "count"),
        n_up=("bar_dir", lambda x: int((x > 0).sum())),
        n_down=("bar_dir", lambda x: int((x < 0).sum())),
        fwd_agg=(fwd_col, "mean"),
    )
    agg = agg.dropna(subset=["fwd_agg"])
    agg["is_event"] = agg["n_fire"] >= k_min
    agg["majority_dir"] = 0
    agg.loc[agg["n_up"] >= COFIRE_DIR_MAJ, "majority_dir"] = 1
    # If both ≥3 up AND ≥3 down, prefer larger; here assign down only if not up
    agg.loc[(agg["majority_dir"] == 0) & (agg["n_down"] >= COFIRE_DIR_MAJ), "majority_dir"] = -1
    # If tie (both ≥3 up AND ≥3 down), break by larger count
    tie_mask = (agg["n_up"] >= COFIRE_DIR_MAJ) & (agg["n_down"] >= COFIRE_DIR_MAJ)
    agg.loc[tie_mask & (agg["n_down"] > agg["n_up"]), "majority_dir"] = -1
    agg.loc[tie_mask & (agg["n_up"] > agg["n_down"]), "majority_dir"] = 1
    # ties exactly equal — drop those events from quadrants
    agg["era"] = agg.index.year
    events = agg[agg["is_event"] & (agg["majority_dir"] != 0)].copy()
    return events


def four_quadrant_snt(events: pd.DataFrame) -> Dict[str, Dict]:
    """4-quadrant SNT for co-firing events.

    A set: events with majority_dir == +1 (UP regime)
    B set: events with majority_dir == -1 (DOWN regime)
    """
    results: Dict[str, Dict] = {}
    A_set = events[events["majority_dir"] == 1].copy()
    B_set = events[events["majority_dir"] == -1].copy()

    cells = {
        "A_focus_COFIRE_UP_LONG":    (A_set, +1),
        "A_mirror_COFIRE_UP_SHORT":  (A_set, -1),
        "B_same_COFIRE_DOWN_SHORT":  (B_set, -1),
        "B_mirror_COFIRE_DOWN_LONG": (B_set, +1),
    }

    for cell_name, (sub, trade_dir) in cells.items():
        if sub.empty:
            results[cell_name] = {
                "n_trig": 0,
                "verdict": "EMPTY_TRIGGER_SET",
            }
            continue
        gross = trade_dir * sub["fwd_agg"].values
        net = gross - FEE_RT
        n = len(net)
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
            "mean_gross_bp": mean_gross_bp,
            "mean_net_bp": mean_net_bp,
            "t_obs": t_obs,
            "win_rate": win_rate,
            "per_year": per_year_summary,
            "trade_direction": int(trade_dir),
            "n_up_mean": float(sub["n_up"].mean()),
            "n_down_mean": float(sub["n_down"].mean()),
            "n_fire_mean": float(sub["n_fire"].mean()),
        }
    return results


def three_gate_for_cell(
    cell_events: pd.DataFrame, trade_dir: int,
    candidate_pool_returns: np.ndarray, n_perms: int = 1000,
) -> Dict:
    if cell_events.empty:
        return {
            "signal_t_excess": float("nan"),
            "ci_lower_bp": float("nan"),
            "perm_p": float("nan"),
            "verdict": "EMPTY",
        }
    obs_net = trade_dir * cell_events["fwd_agg"].values - FEE_RT
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


def build_candidate_pool_universe(panels: Dict[str, pd.DataFrame], hold_label: str) -> np.ndarray:
    """Universe-level pool = per-bar mean fwd across syms (matches event aggregation).
    For each 4h bar with ≥1 valid sym fwd, mean across syms — full universe baseline pool.
    """
    fwd_col = f"fwd_{hold_label}"
    parts = []
    for sym, df in panels.items():
        sub = df.loc[df["rv_z"].notna(), fwd_col].dropna()
        if not sub.empty:
            parts.append(sub.rename(sym))
    if not parts:
        return np.array([])
    wide = pd.concat(parts, axis=1)
    bar_mean = wide.mean(axis=1, skipna=True).dropna()
    return bar_mean.values


def per_quarter_t(events_cell: pd.DataFrame, trade_dir: int) -> Dict[str, Dict]:
    if events_cell.empty:
        return {}
    tc = events_cell.copy()
    tc["yq"] = tc.index.to_period("Q").astype(str)
    out: Dict[str, Dict] = {}
    for yq, sub in tc.groupby("yq"):
        net = trade_dir * sub["fwd_agg"].values - FEE_RT
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


def unconditional_baseline_universe(
    panels: Dict[str, pd.DataFrame], hold_label: str, trade_dir: int,
) -> Dict:
    """Universe-aggregate unconditional baseline = mean of per-bar means × trade_dir - fee."""
    pool = build_candidate_pool_universe(panels, hold_label)
    if len(pool) < 2:
        return {"n": int(len(pool)), "mean_bp": None, "t": None}
    net = trade_dir * pool - FEE_RT
    sd = float(np.std(net, ddof=1))
    t = float(np.mean(net) / sd * np.sqrt(len(net))) if sd > 0 else 0.0
    return {
        "n": int(len(net)),
        "mean_bp": float(np.mean(net) * 1e4),
        "t": t,
        "trade_direction": int(trade_dir),
    }


def main():
    log.info(
        "paradigm_%d START — cross-sym co-firing density regime detection "
        "(≥%d alts |rv_z|>=2 simultaneous × ≥%d same-dir × universe-wide hold 4h/8h)",
        PARADIGM_COUNTER, COFIRE_K_PRIMARY, COFIRE_DIR_MAJ,
    )
    panels = build_panel()
    if not panels:
        raise RuntimeError("no panels built — substrate failed")
    log.info("panels built: %d/%d syms", len(panels), len(SYMBOLS_20))

    # ----- Per-sym z diagnostics -----
    per_sym_z_diagnostics = {}
    for sym, df in panels.items():
        z = df["rv_z"].dropna()
        if len(z) < 360:
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

    total_neg2 = sum(d["n_z_le_neg2"] for d in per_sym_z_diagnostics.values())
    total_pos2 = sum(d["n_z_ge_pos2"] for d in per_sym_z_diagnostics.values())
    log.info("Total per-sym z<=-2 trig=%d, z>=+2 trig=%d", total_neg2, total_pos2)

    # ----- 4-quadrant SNT for each hold -----
    all_results: Dict[str, Dict] = {}
    for hold_label in HOLDS_BARS.keys():
        log.info("---- hold=%s ----", hold_label)
        events = detect_co_firing_events(panels, Z_PRIMARY, COFIRE_K_PRIMARY, hold_label)
        log.info(
            "  co-firing events k>=%d: n=%d (UP_maj=%d, DOWN_maj=%d, tie/drop=%d)",
            COFIRE_K_PRIMARY,
            len(events),
            int((events["majority_dir"] == 1).sum()) if not events.empty else 0,
            int((events["majority_dir"] == -1).sum()) if not events.empty else 0,
            0,  # ties already dropped in detect
        )

        pool = build_candidate_pool_universe(panels, hold_label)
        log.info("  universe pool size=%d", len(pool))

        snt = four_quadrant_snt(events)

        three_gate = {}
        per_q = {}
        cell_specs = {
            "A_focus_COFIRE_UP_LONG":    (1, +1),
            "A_mirror_COFIRE_UP_SHORT":  (1, -1),
            "B_same_COFIRE_DOWN_SHORT":  (-1, -1),
            "B_mirror_COFIRE_DOWN_LONG": (-1, +1),
        }
        for cell_name, (regime_dir, trade_dir) in cell_specs.items():
            cell_events = events[events["majority_dir"] == regime_dir] if not events.empty else events
            tg = three_gate_for_cell(cell_events, trade_dir, pool, n_perms=1000)
            three_gate[cell_name] = tg
            per_q[cell_name] = per_quarter_t(cell_events, trade_dir) if not cell_events.empty else {}

        uncond_long = unconditional_baseline_universe(panels, hold_label, +1)
        uncond_short = unconditional_baseline_universe(panels, hold_label, -1)

        all_results[hold_label] = {
            "snt_4_quadrant": snt,
            "three_gate_per_cell": three_gate,
            "per_quarter_t": per_q,
            "unconditional_baseline_long": uncond_long,
            "unconditional_baseline_short": uncond_short,
            "candidate_pool_size": int(len(pool)),
            "n_events": int(len(events)),
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

    # ----- Sensitivity at k>=4 + |z|>=1.5 on primary hold -----
    sens = {}
    for label, (z_t, k_min) in {
        "z2_k4": (Z_PRIMARY, COFIRE_K_SENSITIVITY),
        "z1p5_k5": (Z_SENSITIVITY, COFIRE_K_PRIMARY),
    }.items():
        sens_events = detect_co_firing_events(panels, z_t, k_min, PRIMARY_HOLD)
        sens_pool = build_candidate_pool_universe(panels, PRIMARY_HOLD)
        sens_three_gate = {}
        for cell_name, (regime_dir, trade_dir) in {
            "A_focus_COFIRE_UP_LONG":   (1, +1),
            "B_same_COFIRE_DOWN_SHORT": (-1, -1),
        }.items():
            ce = sens_events[sens_events["majority_dir"] == regime_dir] if not sens_events.empty else sens_events
            sens_three_gate[cell_name] = three_gate_for_cell(ce, trade_dir, sens_pool, n_perms=500)
        sens[label] = {
            "n_events": int(len(sens_events)),
            "three_gate": sens_three_gate,
        }

    # ----- Era stratify (alpha decay informational learning audit) -----
    events_p = detect_co_firing_events(panels, Z_PRIMARY, COFIRE_K_PRIMARY, PRIMARY_HOLD)
    era_stratify = {}
    cell_specs_era = {
        "A_focus_COFIRE_UP_LONG":    (1, +1),
        "A_mirror_COFIRE_UP_SHORT":  (1, -1),
        "B_same_COFIRE_DOWN_SHORT":  (-1, -1),
        "B_mirror_COFIRE_DOWN_LONG": (-1, +1),
    }
    for cell_name, (regime_dir, trade_dir) in cell_specs_era.items():
        if events_p.empty:
            era_stratify[cell_name] = {}
            continue
        cell_events = events_p[events_p["majority_dir"] == regime_dir]
        eras = {}
        if cell_events.empty:
            era_stratify[cell_name] = {}
            continue
        for era_yr, sub in cell_events.groupby("era"):
            net = trade_dir * sub["fwd_agg"].values - FEE_RT
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

    # ----- Cross-set asymmetry (Item 7, 11th instance, Lesson #75 5x test) -----
    if not events_p.empty:
        A_set = events_p[events_p["majority_dir"] == 1]
        B_set = events_p[events_p["majority_dir"] == -1]
        a_n = int(len(A_set))
        b_n = int(len(B_set))
        if b_n > 0:
            asym_a_to_b = float(a_n / b_n)
        elif a_n > 0:
            asym_a_to_b = float("inf")
        else:
            asym_a_to_b = float("nan")
        # Lesson #75 5x test
        lesson_75_5x_test = bool(
            np.isfinite(asym_a_to_b)
            and (asym_a_to_b >= 5.0 or (b_n > 0 and a_n / b_n <= 0.2))
        )
        cross_set = {
            "n_A_UP_majority": a_n,
            "n_B_DOWN_majority": b_n,
            "asymmetry_A_to_B": asym_a_to_b,
            "lesson_75_5x_threshold_exceeded": lesson_75_5x_test,
            "instance_11th_pattern_p1_test": True,
        }
    else:
        cross_set = {"empty": True}

    # ----- Rolling 6-month consistency (Lesson #72) -----
    rolling_6m_consistency = {}
    if not events_p.empty:
        for cell_name, (regime_dir, trade_dir) in cell_specs_era.items():
            cell_events = events_p[events_p["majority_dir"] == regime_dir]
            if cell_events.empty:
                rolling_6m_consistency[cell_name] = {}
                continue
            tc = cell_events.copy()
            tc["yhalf"] = tc.index.to_period("2Q").astype(str)
            half = {}
            for yh, sub in tc.groupby("yhalf"):
                net = trade_dir * sub["fwd_agg"].values - FEE_RT
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

    # ----- Item 9 Life-changing 4-dim STRUCTURAL prescreen (7th operational, Lesson #73 1st) -----
    item9 = {}
    for hold_label, h_bars in HOLDS_BARS.items():
        events_h = detect_co_firing_events(panels, Z_PRIMARY, COFIRE_K_PRIMARY, hold_label)
        if events_h.empty:
            item9[hold_label] = {"n_total": 0, "util_passes_30pct": False}
            continue
        years_obs = (events_h.index.max() - events_h.index.min()).days / 365.25
        n_total = len(events_h)
        # 4 cells (A focus + A mirror + B same + B mirror) — each trade per event-direction
        # Aggregate trades/yr across all 4 cells
        n_per_cell_total = {
            "A_focus": int((events_h["majority_dir"] == 1).sum()),
            "A_mirror": int((events_h["majority_dir"] == 1).sum()),
            "B_same": int((events_h["majority_dir"] == -1).sum()),
            "B_mirror": int((events_h["majority_dir"] == -1).sum()),
        }
        trades_per_yr_per_cell = {
            k: float(v / years_obs) if years_obs > 0 else float("nan")
            for k, v in n_per_cell_total.items()
        }
        # Capital util heuristic for universe-aggregate trade (each event = 1 universe-wide trade):
        # util = h_bars * n_events / total_bars (universe-wide trade occupies full universe for h bars)
        total_bars = (events_h.index.max() - events_h.index.min()).total_seconds() / (4 * 3600)
        capital_util_est = (
            float(h_bars * n_total / total_bars)
            if total_bars > 0 else float("nan")
        )
        item9[hold_label] = {
            "n_total_events": int(n_total),
            "n_per_cell": n_per_cell_total,
            "trades_per_yr_per_cell": trades_per_yr_per_cell,
            "capital_util_estimate": capital_util_est,
            "hold_bars": h_bars,
            "years_obs": float(years_obs),
            "util_passes_30pct": bool(capital_util_est >= 0.30),
            "trades_per_yr_min_12": bool(min(trades_per_yr_per_cell.values()) >= 12),
        }

    # ----- write metrics -----
    final = {
        "paradigm_counter": PARADIGM_COUNTER,
        "paradigm_slug": PARADIGM_SLUG,
        "axis_first_use": (
            "Cross-sym co-firing density regime detection (≥5 alts simultaneous "
            "|rv_z|>=2 in same 4h bar × collective majority direction ≥3 same-dir × "
            "universe-wide LONG/SHORT 4h/8h hold). Lesson #73 density escape 1st "
            "operational dogfood + Lesson #74 candidate ESCAPE 조건 1 1st test "
            "(cross-sym co-firing distinct DNA vs per-sym OHLCV z-spike)."
        ),
        "predecessor_context": (
            "paradigm 222 graveyard (Pattern P1 10th + 2026 era-universal 8th + "
            "Item 9 STRUCTURAL FAIL 6th + 3 new Lesson #73/#74/#75 candidates). "
            "paradigm 223 = cross-sym co-firing density event class FIRST-USE, "
            "Item 9 STRUCTURAL FAIL 회피 via density escape mechanism."
        ),
        "config": {
            "z_primary": Z_PRIMARY,
            "z_sensitivity": Z_SENSITIVITY,
            "rv_window_bars": RV_WINDOW,
            "z_window_bars": Z_WINDOW,
            "fee_rt": FEE_RT,
            "holds_bars": HOLDS_BARS,
            "primary_hold": PRIMARY_HOLD,
            "cofire_k_primary": COFIRE_K_PRIMARY,
            "cofire_k_sensitivity": COFIRE_K_SENSITIVITY,
            "cofire_dir_majority": COFIRE_DIR_MAJ,
            "universe": SYMBOLS_20,
            "n_syms_built": len(panels),
        },
        "per_sym_z_diagnostics": per_sym_z_diagnostics,
        "lesson_40_structural_feasibility": {
            "total_z_le_neg2_per_sym_triggers": total_neg2,
            "total_z_ge_pos2_per_sym_triggers": total_pos2,
            "symmetric_feasible": bool(total_neg2 > 0 and total_pos2 > 0),
            "verdict": (
                "PASS — 4h per-sym z symmetric ±2 feasibility verified"
                if (total_neg2 > 0 and total_pos2 > 0)
                else "FAIL — 4h z structural threshold infeasible"
            ),
        },
        "results_by_hold": all_results,
        "sensitivity_variants_primary_hold": sens,
        "era_stratify_alpha_decay_primary_hold": era_stratify,
        "rolling_6m_consistency_primary_hold": rolling_6m_consistency,
        "cross_set_asymmetry_item_7_11th_instance": cross_set,
        "item_9_life_changing_structural_prescreen_7th_operational": item9,
    }

    out_path = OUTPUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(final, f, indent=2, default=str)
    log.info("metrics written: %s", out_path)


if __name__ == "__main__":
    main()
