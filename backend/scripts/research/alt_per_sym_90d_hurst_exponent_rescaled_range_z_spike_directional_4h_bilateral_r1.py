"""paradigm 204 R-1: per-sym 90d rolling Hurst (R/S) z-spike trigger.

Mechanism:
  - 4h candles -> daily close-to-close return per symbol
  - 90d rolling Hurst (rescaled-range R/S) per symbol
  - 180d rolling z-score of Hurst per symbol
  - Trigger: |z|>=2 (trending regime shift event); sign(z) determines regime type
  - Forward: 4h primary (next 4h close-to-close), plus 8h/12h/24h sweep

4-quadrant SNT (bilateral sign-conditional):
  A focus  : Hurst z>=+2 (trending regime) x bar UP x LONG continuation
  A mirror : Hurst z>=+2 (trending regime) x bar UP x SHORT reversal
  B same   : Hurst z>=+2 (trending regime) x bar DOWN x SHORT continuation
  B mirror : Hurst z>=+2 (trending regime) x bar DOWN x LONG reversal  (Lesson #42 11th dogfood)

Era stratify: 2024/2025/2026 (Item 6 alpha decay informational learning audit).
9-quarter breakdown also emitted.

NOTE: This is R-1 ONLY. No R-2 progression.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("p204_r1")

PARADIGM_NAME = "alt_per_sym_90d_hurst_exponent_rescaled_range_z_spike_directional_4h_bilateral"
SYMS: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "LINKUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "ETCUSDT", "FILUSDT",
    "NEARUSDT", "UNIUSDT", "LDOUSDT", "WIFUSDT", "WLDUSDT", "PYTHUSDT", "JUPUSDT",
]  # 21 syms (20 alts + BTC anchor); BTC kept for cohort but per-sym independent

CACHE_DIR = Path(__file__).resolve().parents[2] / "runs" / "ohlcv_cache_12col"
OUT_DIR = Path(__file__).resolve().parents[2] / "runs" / "research_track" / PARADIGM_NAME

ROLL_HURST_DAYS = 90
ROLL_Z_DAYS = 180
Z_THRESH = 2.0
HOLDS_BARS = {"4h": 1, "8h": 2, "12h": 3, "24h": 6}
PRIMARY_HOLD = "4h"
FEE_PER_TRADE = 0.0008  # 8 bp one-side, 16 bp roundtrip


def hurst_rs(series: np.ndarray) -> float:
    """Rescaled-range Hurst exponent (Mandelbrot R/S) for log-return series.

    Uses 4 chunk sizes (16, 32, 48, 72) within window=90 to keep computation
    deterministic and avoid degenerate small-n splits.
    Returns NaN if insufficient data or non-finite series.
    """
    series = np.asarray(series, dtype=float)
    if not np.all(np.isfinite(series)) or len(series) < 32:
        return float("nan")
    n = len(series)
    sizes = [s for s in (16, 32, 48, 72) if s < n]
    if len(sizes) < 2:
        return float("nan")
    log_n: List[float] = []
    log_rs: List[float] = []
    for size in sizes:
        n_chunks = n // size
        if n_chunks < 2:
            continue
        rs_vals: List[float] = []
        for i in range(n_chunks):
            chunk = series[i * size:(i + 1) * size]
            if len(chunk) < size:
                continue
            mean = chunk.mean()
            deviations = chunk - mean
            cum = np.cumsum(deviations)
            r = cum.max() - cum.min()
            s = chunk.std(ddof=0)
            if s <= 1e-12 or r <= 0:
                continue
            rs_vals.append(r / s)
        if not rs_vals:
            continue
        log_n.append(math.log(size))
        log_rs.append(math.log(np.mean(rs_vals)))
    if len(log_n) < 2:
        return float("nan")
    slope = np.polyfit(log_n, log_rs, 1)[0]
    return float(slope)


def build_daily(df_4h: pd.DataFrame) -> pd.DataFrame:
    """Resample 4h -> daily close (close-to-close) and compute log return."""
    daily_close = df_4h["close"].resample("1D").last().dropna()
    daily_ret = np.log(daily_close).diff()
    out = pd.DataFrame({"close": daily_close, "ret": daily_ret}).dropna()
    return out


def compute_hurst_zspike(daily: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame with columns [hurst, hurst_z, trigger] indexed by date."""
    rets = daily["ret"].to_numpy()
    n = len(daily)
    hurst = np.full(n, np.nan)
    for end in range(ROLL_HURST_DAYS, n + 1):
        window = rets[end - ROLL_HURST_DAYS:end]
        hurst[end - 1] = hurst_rs(window)
    daily = daily.copy()
    daily["hurst"] = hurst
    # 180d rolling z-score on hurst
    z_mu = daily["hurst"].rolling(ROLL_Z_DAYS, min_periods=int(ROLL_Z_DAYS * 0.7)).mean()
    z_sd = daily["hurst"].rolling(ROLL_Z_DAYS, min_periods=int(ROLL_Z_DAYS * 0.7)).std(ddof=0)
    daily["hurst_z"] = (daily["hurst"] - z_mu) / z_sd
    daily["trigger"] = (daily["hurst_z"].abs() >= Z_THRESH).fillna(False)
    return daily


def quadrant_label(z_sign: int, bar_dir: int) -> str:
    """A_focus / A_mirror / B_same / B_mirror."""
    # Trigger regime = trending (|z|>=2). We classify by bar direction (UP/DN)
    # and which side (LONG/SHORT) is taken.
    # We emit four cells per trigger so each event contributes once per cell.
    raise NotImplementedError


def evaluate_quadrants(events: pd.DataFrame, fwd_col: str) -> Dict[str, dict]:
    """Compute per-quadrant gross/net edge, perm test, bootstrap CI.

    events columns required: [bar_up (bool), fwd_ret (float)]
    A_focus  = bar UP -> long  (signed +fwd_ret) minus 2*fee
    A_mirror = bar UP -> short (signed -fwd_ret) minus 2*fee
    B_same   = bar DN -> short (signed -fwd_ret) minus 2*fee
    B_mirror = bar DN -> long  (signed +fwd_ret) minus 2*fee
    """
    results: Dict[str, dict] = {}
    up = events[events["bar_up"]]
    dn = events[~events["bar_up"]]
    cells = {
        "A_focus": (up[fwd_col].to_numpy(), 1),
        "A_mirror": (-up[fwd_col].to_numpy(), 1),
        "B_same": (-dn[fwd_col].to_numpy(), 1),
        "B_mirror": (dn[fwd_col].to_numpy(), 1),
    }
    # Build candidate pool from ALL non-trigger forward returns for perm null.
    # We don't have direct access here; caller passes pool via events attribute.
    pool = events.attrs.get("pool", np.array([]))
    for name, (rets, _) in cells.items():
        rets = rets[np.isfinite(rets)]
        n = len(rets)
        if n < 30:
            results[name] = {
                "n": n,
                "skipped": "n<30",
                "gross_bp": float(np.mean(rets) * 10000) if n > 0 else float("nan"),
            }
            continue
        gross_bp = float(np.mean(rets) * 10000)
        net = rets - 2 * FEE_PER_TRADE  # roundtrip fee
        net_bp = float(np.mean(net) * 10000)
        # t-stat (Welch-style, against 0)
        sd = float(np.std(net, ddof=1))
        obs_t = float(np.mean(net) / (sd / math.sqrt(n))) if sd > 0 else float("nan")
        # perm test
        if len(pool) > 0:
            perm = fee_aware_perm_test(
                observed_net_returns=net,
                candidate_pool_returns=pool,
                fee_per_trade=FEE_PER_TRADE,
                n_perms=1000,
                rng_seed=42,
            )
        else:
            perm = {"signal_t_excess": float("nan"), "perm_p": float("nan"), "null_mean_t": float("nan")}
        # bootstrap CI on net returns
        ci = bootstrap_ci(net, n_boot=2000, alpha=0.05, rng_seed=42)
        results[name] = {
            "n": n,
            "gross_bp": gross_bp,
            "net_bp": net_bp,
            "obs_t": obs_t,
            "signal_t_excess": perm.get("signal_t_excess"),
            "perm_p": perm.get("perm_p"),
            "null_mean_t": perm.get("null_mean_t"),
            "ci_lower_bp": float(ci.get("ci_lower", float("nan")) * 10000),
            "ci_upper_bp": float(ci.get("ci_upper", float("nan")) * 10000),
            "ci_pos": bool(ci.get("ci_lower", -1) > 0),
            "three_gate_pass": bool(
                (perm.get("signal_t_excess") is not None and perm.get("signal_t_excess") >= 2.0)
                and (ci.get("ci_lower", -1) > 0)
                and (perm.get("perm_p") is not None and perm.get("perm_p") <= 0.10)
            ),
        }
    return results


def per_symbol_concentration(events_by_sym: Dict[str, pd.DataFrame], fwd_col: str, cell_name: str) -> dict:
    """For a given quadrant cell, compute per-symbol bootstrap CI to assess concentration."""
    sym_metrics: Dict[str, dict] = {}
    for sym, ev in events_by_sym.items():
        up = ev[ev["bar_up"]]
        dn = ev[~ev["bar_up"]]
        if cell_name == "A_focus":
            rets = up[fwd_col].to_numpy()
        elif cell_name == "A_mirror":
            rets = -up[fwd_col].to_numpy()
        elif cell_name == "B_same":
            rets = -dn[fwd_col].to_numpy()
        elif cell_name == "B_mirror":
            rets = dn[fwd_col].to_numpy()
        else:
            continue
        rets = rets[np.isfinite(rets)]
        if len(rets) < 10:
            sym_metrics[sym] = {"n": len(rets), "skipped": "n<10"}
            continue
        net = rets - 2 * FEE_PER_TRADE
        ci = bootstrap_ci(net, n_boot=1000, alpha=0.05, rng_seed=42)
        sym_metrics[sym] = {
            "n": len(rets),
            "net_bp": float(np.mean(net) * 10000),
            "ci_lower_bp": float(ci.get("ci_lower", float("nan")) * 10000),
            "ci_pos": bool(ci.get("ci_lower", -1) > 0),
        }
    n_measurable = sum(1 for v in sym_metrics.values() if "ci_pos" in v)
    n_ci_pos = sum(1 for v in sym_metrics.values() if v.get("ci_pos"))
    return {
        "syms": sym_metrics,
        "n_measurable": n_measurable,
        "n_ci_pos": n_ci_pos,
        "ratio_ci_pos": (n_ci_pos / n_measurable) if n_measurable > 0 else float("nan"),
    }


def era_label(ts: pd.Timestamp) -> str:
    if ts.year == 2024:
        return "2024"
    if ts.year == 2025:
        return "2025"
    return "2026"


def quarter_label(ts: pd.Timestamp) -> str:
    return f"{ts.year}Q{((ts.month - 1) // 3) + 1}"


def stratify_era(events: pd.DataFrame, fwd_col: str) -> Dict[str, Dict[str, dict]]:
    """Return {era: {cell: metrics}} for 2024/2025/2026."""
    out: Dict[str, Dict[str, dict]] = {}
    for era, group in events.groupby("era"):
        group_evt = group.copy()
        group_evt.attrs["pool"] = events.attrs.get("pool", np.array([]))
        out[era] = evaluate_quadrants(group_evt, fwd_col)
    return out


def stratify_quarter(events: pd.DataFrame, fwd_col: str) -> Dict[str, Dict[str, dict]]:
    out: Dict[str, Dict[str, dict]] = {}
    for q, group in events.groupby("quarter"):
        group_evt = group.copy()
        group_evt.attrs["pool"] = events.attrs.get("pool", np.array([]))
        out[q] = evaluate_quadrants(group_evt, fwd_col)
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("paradigm 204 R-1 dispatch start. syms=%d", len(SYMS))

    all_events: List[pd.DataFrame] = []
    events_by_sym: Dict[str, pd.DataFrame] = {}
    pool_returns: List[float] = []
    sym_event_count: Dict[str, int] = {}

    for sym in SYMS:
        path = CACHE_DIR / f"{sym}_4h.joblib"
        if not path.exists():
            log.warning("missing cache: %s", path)
            continue
        df_4h = joblib.load(path)
        if "close" not in df_4h.columns:
            log.warning("no close col: %s", sym)
            continue
        daily = build_daily(df_4h)
        daily = compute_hurst_zspike(daily)

        # For each daily trigger date, locate the FIRST 4h bar of that day in df_4h
        # and compute forward returns at multiple horizons.
        # Trigger date timestamp = day boundary (00:00 UTC).
        # We measure forward 4h ret = (close[+1bar] - close[+0bar]) / close[+0bar]
        # entry bar = first 4h bar of next day (after we've seen full prior day close).

        # Build 4h-indexed forward ret columns
        df = df_4h[["close"]].copy()
        for label, k in HOLDS_BARS.items():
            df[f"fwd_{label}"] = df["close"].shift(-k) / df["close"] - 1.0
        # bar direction at entry bar (prior 4h close-to-close to define UP/DN trigger bar)
        df["prior_4h_ret"] = df["close"] / df["close"].shift(1) - 1.0

        # For each daily trigger day, entry = first 4h bar of NEXT day
        triggers = daily[daily["trigger"]].copy()
        if triggers.empty:
            continue

        # Map trigger day -> first 4h bar of next day
        events_rows: List[dict] = []
        for trig_day, row in triggers.iterrows():
            # next day = trig_day + 1d, first bar at 00:00
            entry_ts = trig_day + pd.Timedelta(days=1)
            if entry_ts not in df.index:
                # find first bar after entry_ts
                idx = df.index.searchsorted(entry_ts)
                if idx >= len(df.index):
                    continue
                entry_ts = df.index[idx]
            bar = df.loc[entry_ts]
            fwd = {f"fwd_{lab}": float(bar[f"fwd_{lab}"]) for lab in HOLDS_BARS}
            if not np.isfinite(fwd[f"fwd_{PRIMARY_HOLD}"]):
                continue
            prior = bar["prior_4h_ret"]
            if not np.isfinite(prior):
                continue
            events_rows.append({
                "sym": sym,
                "trig_day": trig_day,
                "entry_ts": entry_ts,
                "hurst": float(row["hurst"]),
                "hurst_z": float(row["hurst_z"]),
                "bar_up": bool(prior > 0),
                **fwd,
                "era": era_label(entry_ts),
                "quarter": quarter_label(entry_ts),
            })

        if not events_rows:
            continue
        df_ev = pd.DataFrame(events_rows)
        events_by_sym[sym] = df_ev
        all_events.append(df_ev)
        sym_event_count[sym] = len(df_ev)

        # pool = ALL valid forward 4h returns (non-trigger anchored)
        pool_arr = df[f"fwd_{PRIMARY_HOLD}"].dropna().to_numpy()
        if len(pool_arr) > 0:
            # subsample to keep pool manageable (~3000 per sym)
            if len(pool_arr) > 3000:
                rng = np.random.default_rng(42 + hash(sym) % 1000)
                idx = rng.choice(len(pool_arr), 3000, replace=False)
                pool_arr = pool_arr[idx]
            pool_returns.extend(pool_arr.tolist())

    if not all_events:
        log.error("no events collected")
        return

    events = pd.concat(all_events, ignore_index=True)
    pool_arr = np.array(pool_returns, dtype=float)
    pool_arr = pool_arr[np.isfinite(pool_arr)]
    events.attrs["pool"] = pool_arr
    log.info(
        "aggregate events: n=%d, syms_with_events=%d, pool=%d",
        len(events), len(events_by_sym), len(pool_arr),
    )

    # =================== aggregate 4-quadrant SNT (primary 4h) ===================
    fwd_col = f"fwd_{PRIMARY_HOLD}"
    quad_primary = evaluate_quadrants(events, fwd_col)

    # =================== hold sweep ===================
    hold_sweep: Dict[str, Dict[str, dict]] = {}
    for label in HOLDS_BARS:
        hold_sweep[label] = evaluate_quadrants(events, f"fwd_{label}")

    # =================== per-sym concentration (primary, all 4 cells) ===================
    concentration: Dict[str, dict] = {}
    for cell in ("A_focus", "A_mirror", "B_same", "B_mirror"):
        concentration[cell] = per_symbol_concentration(events_by_sym, fwd_col, cell)

    # =================== era stratify (Item 6) ===================
    era_strat = stratify_era(events, fwd_col)

    # =================== quarter stratify ===================
    quarter_strat = stratify_quarter(events, fwd_col)

    # =================== summary verdicts ===================
    any_three_gate = {cell: quad_primary[cell].get("three_gate_pass", False) for cell in quad_primary}
    n_3g_pass = sum(1 for v in any_three_gate.values() if v)

    summary = {
        "paradigm": PARADIGM_NAME,
        "paradigm_id": 204,
        "phase": "R-1",
        "syms_universe": SYMS,
        "syms_with_events": list(events_by_sym.keys()),
        "n_events_total": int(len(events)),
        "n_events_per_sym": sym_event_count,
        "pool_size": int(len(pool_arr)),
        "fee_per_trade": FEE_PER_TRADE,
        "z_threshold": Z_THRESH,
        "hurst_window_days": ROLL_HURST_DAYS,
        "z_window_days": ROLL_Z_DAYS,
        "primary_hold": PRIMARY_HOLD,
        "holds_evaluated": list(HOLDS_BARS.keys()),
        "quadrant_primary": quad_primary,
        "hold_sweep": hold_sweep,
        "concentration_primary": concentration,
        "era_stratify": era_strat,
        "quarter_stratify": quarter_strat,
        "n_quadrants_three_gate_pass": n_3g_pass,
        "any_three_gate": any_three_gate,
    }

    metrics_path = OUT_DIR / "r1__metrics.json"
    with metrics_path.open("w") as f:
        json.dump(summary, f, indent=2, default=lambda x: float(x) if isinstance(x, (np.floating,)) else str(x))
    log.info("wrote %s", metrics_path)

    # human-readable summary
    log.info("=" * 80)
    log.info("PRIMARY 4h QUADRANT VERDICT")
    log.info("=" * 80)
    for cell, m in quad_primary.items():
        log.info(
            "%-9s n=%-4d gross=%+7.2fbp net=%+7.2fbp sigex=%+5.2f perm_p=%.3f ci=[%+7.2f,%+7.2f] ci_pos=%s 3gate=%s",
            cell,
            m.get("n", 0),
            m.get("gross_bp", float("nan")),
            m.get("net_bp", float("nan")),
            m.get("signal_t_excess", float("nan")) or float("nan"),
            m.get("perm_p", float("nan")) or float("nan"),
            m.get("ci_lower_bp", float("nan")),
            m.get("ci_upper_bp", float("nan")),
            m.get("ci_pos", False),
            m.get("three_gate_pass", False),
        )

    log.info("=" * 80)
    log.info("HOLD SWEEP (per cell, signal_t_excess)")
    log.info("=" * 80)
    for label, cells in hold_sweep.items():
        line = f"{label:>4}: "
        for cell, m in cells.items():
            sigex = m.get("signal_t_excess", float("nan"))
            sigex_str = f"{sigex:+5.2f}" if isinstance(sigex, (int, float)) and not (isinstance(sigex, float) and math.isnan(sigex)) else "  nan"
            line += f"{cell}={sigex_str} "
        log.info(line)

    log.info("=" * 80)
    log.info("ERA STRATIFY (Item 6 alpha decay informational learning audit)")
    log.info("=" * 80)
    for era, cells in era_strat.items():
        line = f"{era}: "
        for cell, m in cells.items():
            sigex = m.get("signal_t_excess", float("nan"))
            n = m.get("n", 0)
            sigex_str = f"{sigex:+5.2f}" if isinstance(sigex, (int, float)) and not (isinstance(sigex, float) and math.isnan(sigex)) else "  nan"
            line += f"{cell}(n={n}/sigex={sigex_str}) "
        log.info(line)

    log.info("=" * 80)
    log.info("VERDICT: %d/4 quadrants three-gate PASS", n_3g_pass)
    log.info("=" * 80)


if __name__ == "__main__":
    main()
