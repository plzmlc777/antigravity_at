"""R-1 PoC — Paradigm 231: Binance Launchpool BNB demand event-anchored bilateral 1d-to-7d.

Hypothesis:
    Binance Launchpool events create systematic BNB demand cycles:
    (A) Pre-farm accumulation: Users accumulate BNB 2-7 days before farm_start
        to participate in staking -> positive BNB drift -> LONG signal
    (B) Post-farm distribution: Users unstake BNB 1-7 days after farm_end
        -> BNB supply overhang -> negative BNB drift -> SHORT signal

DNA (5-axis novelty):
    - Substrate: Launchpool farm event calendar (NEW)
    - Statistic: days-to-event temporal proximity
    - Direction: bilateral (LONG pre-start, SHORT post-end)
    - Universe: BNBUSDT single-symbol perpetual
    - Mechanism: staking capital demand flow (NEW, non-price/OI/funding)

4-quadrant Symmetric Negative Test (Lesson #19 mandatory):
    A_focus:  in_pre_farm_window & bar_up  -> LONG   (accumulation continuation)
    A_mirror: in_pre_farm_window & bar_up  -> SHORT  (null test)
    B_focus:  in_post_farm_window & bar_dn -> SHORT  (distribution continuation)
    B_mirror: in_post_farm_window & bar_dn -> LONG   (null test)

Three-gate (Lesson #16):
    signal_t_excess >= 2.0  AND  ci_lower_bp > 0  AND  perm_p_one_sided <= 0.10

Concentration diagnostic: single-symbol (BNBUSDT only), per-quarter t-stat
scan for era stability instead of cross-sym.

Sample density (Lesson #11 + paradigm 230 batch-clustering IID amendment):
    - Event-anchored, unique event count = 34 (Jan 2024 - Jan 2025)
    - Per-quadrant: n = 34 * days_in_window (window-days-per-event)
    - Independent unit is EVENT, not event-day; measure both.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paradigm_231_r1")

REPO = Path(__file__).resolve().parents[3]
OHLCV_CACHE_DIR = REPO / "backend/runs/ohlcv_cache"
EVENTS_CSV = REPO / "backend/runs/research_track/paradigm_231_binance_launchpool_bnb_demand_event_anchored_bilateral_1d_to_7d/launchpool_events.csv"

TARGET_SYM = "BNBUSDT"
FEE_BPS = 8.0  # round-trip
FEE_FRAC = FEE_BPS / 10000.0


# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------

def load_bnb_daily() -> pd.DataFrame:
    """Load BNBUSDT daily OHLCV from 1m joblib cache."""
    path = OHLCV_CACHE_DIR / f"{TARGET_SYM}_1m.joblib"
    if not path.exists():
        raise FileNotFoundError(f"BNB 1m cache missing: {path}")
    df = joblib.load(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    daily = pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
        "volume": df["volume"].resample("1D").sum(),
    }).dropna()
    daily.index = daily.index.normalize()
    return daily


def load_events() -> pd.DataFrame:
    df = pd.read_csv(EVENTS_CSV)
    df["farm_start_utc"] = pd.to_datetime(df["farm_start_utc"])
    df["farm_end_utc"] = pd.to_datetime(df["farm_end_utc"])
    return df


# ----------------------------------------------------------------------------
# Event-anchored trigger construction
# ----------------------------------------------------------------------------

def build_event_masks(
    daily_index: pd.DatetimeIndex,
    events: pd.DataFrame,
    pre_days_window: tuple[int, int],
    post_days_window: tuple[int, int],
) -> Dict[str, pd.Series]:
    """Return per-bar boolean masks:
        in_pre_farm: True if bar falls within [farm_start - pre_days_max, farm_start - pre_days_min]
        in_post_farm: True if bar falls within [farm_end + post_days_min, farm_end + post_days_max]
        event_id_pre: event_id for pre window (for IID tracking)
        event_id_post: event_id for post window
    """
    pre_min, pre_max = pre_days_window  # e.g. (1, 7) → 1-7 days BEFORE start
    post_min, post_max = post_days_window  # e.g. (0, 7) → 0-7 days AFTER end

    n = len(daily_index)
    in_pre = pd.Series(False, index=daily_index)
    in_post = pd.Series(False, index=daily_index)
    pre_event = pd.Series("", index=daily_index)
    post_event = pd.Series("", index=daily_index)

    for _, row in events.iterrows():
        start = row["farm_start_utc"]
        end = row["farm_end_utc"]
        proj = str(row["project"])

        # Pre-farm window: [start - pre_max, start - pre_min]
        pre_lo = start - pd.Timedelta(days=pre_max)
        pre_hi = start - pd.Timedelta(days=pre_min)
        mask_pre = (daily_index >= pre_lo) & (daily_index <= pre_hi)
        in_pre |= pd.Series(mask_pre, index=daily_index)
        # tag with first-project-match to preserve IID (single event per bar in most cases)
        pre_event.loc[mask_pre & (pre_event == "")] = proj

        # Post-farm window: [end + post_min, end + post_max]
        post_lo = end + pd.Timedelta(days=post_min)
        post_hi = end + pd.Timedelta(days=post_max)
        mask_post = (daily_index >= post_lo) & (daily_index <= post_hi)
        in_post |= pd.Series(mask_post, index=daily_index)
        post_event.loc[mask_post & (post_event == "")] = proj

    return {
        "in_pre_farm": in_pre,
        "in_post_farm": in_post,
        "pre_event_id": pre_event,
        "post_event_id": post_event,
    }


def compute_forward_return(daily: pd.DataFrame, hold_days: int) -> pd.Series:
    return daily["close"].shift(-hold_days) / daily["close"] - 1


# ----------------------------------------------------------------------------
# Backtest — 4-quadrant SNT with per-event IID aggregation
# ----------------------------------------------------------------------------

def simulate_quadrants(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    pre_days_window: tuple[int, int],
    post_days_window: tuple[int, int],
    hold_days: int,
) -> dict:
    masks = build_event_masks(daily.index, events, pre_days_window, post_days_window)
    df = daily.copy()
    df["in_pre_farm"] = masks["in_pre_farm"].values
    df["in_post_farm"] = masks["in_post_farm"].values
    df["pre_event_id"] = masks["pre_event_id"].values
    df["post_event_id"] = masks["post_event_id"].values
    df["bar_dir"] = np.sign(df["close"] - df["open"])
    df["fwd"] = compute_forward_return(df, hold_days)

    pool_gross = df["fwd"].dropna().values

    quadrants = {
        "A_focus":  (df["in_pre_farm"] & (df["bar_dir"] > 0), +1, "pre_event_id"),
        "A_mirror": (df["in_pre_farm"] & (df["bar_dir"] > 0), -1, "pre_event_id"),
        "B_focus":  (df["in_post_farm"] & (df["bar_dir"] < 0), -1, "post_event_id"),
        "B_mirror": (df["in_post_farm"] & (df["bar_dir"] < 0), +1, "post_event_id"),
    }

    out: Dict[str, dict] = {}
    for qname, (mask, side, event_col) in quadrants.items():
        sub = df[mask & df["fwd"].notna()].copy()
        if len(sub) < 10:
            out[qname] = {"n": int(len(sub)), "three_gate_pass": False, "reason": "n<10"}
            continue

        # Bar-level net returns (fee applied per trade)
        net = side * sub["fwd"].values - FEE_FRAC
        net_bps = net * 10000

        # Event-level aggregation (IID unit: unique event)
        sub["net_bp"] = net_bps
        event_agg = sub.groupby(event_col)["net_bp"].mean()
        n_events = int(len(event_agg))
        n_events_pos = int((event_agg > 0).sum())

        # Bootstrap CI on bar-level net (bar-level; sub-events are related)
        boot = bootstrap_ci(net, n_boot=2000, block_size=1)

        pool_side = side * pool_gross
        perm = fee_aware_perm_test(
            observed_net_returns=net,
            candidate_pool_returns=pool_side,
            fee_per_trade=FEE_FRAC,
            n_perms=500,
            rng_seed=42,
        )

        # Event-level bootstrap (more conservative than bar-level)
        if n_events >= 5:
            boot_event = bootstrap_ci(event_agg.values / 10000.0, n_boot=2000, block_size=1)
            ci_lo_event_bp = boot_event["ci_lower"] * 10000
        else:
            boot_event = None
            ci_lo_event_bp = None

        # Quarter stratify (concentration diagnostic for single-symbol)
        sub_q = sub.copy()
        sub_q["quarter"] = sub_q.index.to_period("Q").astype(str)
        q_stats = {}
        for q, g in sub_q.groupby("quarter"):
            arr = g["net_bp"].values
            if len(arr) < 3:
                q_stats[q] = {"n": int(len(arr)), "t": None}
                continue
            t = arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr))) if arr.std(ddof=1) > 0 else None
            q_stats[q] = {"n": int(len(arr)), "mean_bp": float(arr.mean()),
                          "t": float(t) if t is not None else None}

        sigex = perm.get("signal_t_excess")
        ci_lo_bp = boot["ci_lower"] * 10000
        pp = perm.get("perm_p_one_sided_above") if side > 0 else perm.get("perm_p_one_sided_below")

        three_gate = (
            sigex is not None and not np.isnan(sigex) and sigex >= 2.0
            and ci_lo_bp > 0
            and pp is not None and not np.isnan(pp) and pp <= 0.10
        )
        # Event-level three-gate (more stringent)
        three_gate_event = (
            three_gate and ci_lo_event_bp is not None and ci_lo_event_bp > 0
        )

        # Per-quarter t-stat ratio (concentration diagnostic single-sym)
        q_ts = [v["t"] for v in q_stats.values() if v.get("t") is not None]
        q_pos_ratio = (sum(1 for t in q_ts if t > 0) / len(q_ts)) if q_ts else None

        out[qname] = {
            "n_bars": int(len(sub)),
            "n_events": n_events,
            "n_events_pos": n_events_pos,
            "event_pos_ratio": float(n_events_pos / n_events) if n_events > 0 else 0.0,
            "mean_bp": float(net_bps.mean()),
            "std_bp": float(net_bps.std(ddof=1)),
            "event_mean_bp": float(event_agg.mean()),
            "event_std_bp": float(event_agg.std(ddof=1)) if n_events > 1 else None,
            "obs_t": float(perm.get("obs_t", 0)),
            "signal_t_excess": float(sigex) if sigex is not None and not np.isnan(sigex) else None,
            "null_mean_t": float(perm.get("null_mean_t", 0)),
            "ci_lower_bp": float(ci_lo_bp),
            "ci_upper_bp": float(boot["ci_upper"] * 10000),
            "ci_lower_bp_event_agg": float(ci_lo_event_bp) if ci_lo_event_bp is not None else None,
            "perm_p_one_sided": float(pp) if pp is not None else None,
            "three_gate_pass": bool(three_gate),
            "three_gate_pass_event_agg": bool(three_gate_event),
            "quarter_stats": q_stats,
            "quarter_pos_t_ratio": float(q_pos_ratio) if q_pos_ratio is not None else None,
            "n_pool": int(len(pool_gross)),
        }
    return out


# ----------------------------------------------------------------------------
# Main sweep — Lesson #37 full hold x window sweep
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre-min", type=int, default=1)
    ap.add_argument("--pre-max", type=int, default=7)
    ap.add_argument("--post-min", type=int, default=0)
    ap.add_argument("--post-max", type=int, default=7)
    ap.add_argument("--hold-days", type=int, default=2)
    ap.add_argument("--tag", default="r1_baseline_pre1_7_post0_7_h2")
    ap.add_argument("--out-dir", default="backend/runs/research_track/paradigm_231_binance_launchpool_bnb_demand_event_anchored_bilateral_1d_to_7d")
    args = ap.parse_args()

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== Paradigm 231 R-1 %s ===", args.tag)
    log.info("Config: pre=(%d,%d) post=(%d,%d) hold=%dd fee=%.1fbp",
             args.pre_min, args.pre_max, args.post_min, args.post_max, args.hold_days, FEE_BPS)

    daily = load_bnb_daily()
    log.info("BNBUSDT daily: %d days (%s .. %s)",
             len(daily), daily.index[0].date(), daily.index[-1].date())

    events = load_events()
    log.info("Launchpool events: %d (%s .. %s)",
             len(events),
             events["farm_start_utc"].min().date(),
             events["farm_start_utc"].max().date())

    # Empirical density audit
    masks = build_event_masks(daily.index, events,
                              (args.pre_min, args.pre_max),
                              (args.post_min, args.post_max))
    n_pre = int(masks["in_pre_farm"].sum())
    n_post = int(masks["in_post_farm"].sum())
    n_pre_bar_up = int((masks["in_pre_farm"] & (np.sign(daily["close"] - daily["open"]) > 0)).sum())
    n_post_bar_dn = int((masks["in_post_farm"] & (np.sign(daily["close"] - daily["open"]) < 0)).sum())
    density = {
        "n_days_total": int(len(daily)),
        "n_pre_farm_days": n_pre,
        "n_post_farm_days": n_post,
        "n_pre_bar_up_days": n_pre_bar_up,
        "n_post_bar_dn_days": n_post_bar_dn,
        "pre_pct": round(100 * n_pre / len(daily), 2),
        "post_pct": round(100 * n_post / len(daily), 2),
    }
    log.info("Density: pre=%d(%.2f%%) post=%d(%.2f%%) pre_bar_up=%d post_bar_dn=%d",
             n_pre, density["pre_pct"], n_post, density["post_pct"],
             n_pre_bar_up, n_post_bar_dn)

    results = simulate_quadrants(
        daily=daily,
        events=events,
        pre_days_window=(args.pre_min, args.pre_max),
        post_days_window=(args.post_min, args.post_max),
        hold_days=args.hold_days,
    )

    for qn, m in results.items():
        if "n_bars" not in m:
            continue
        log.info("  %s: n_bars=%d n_events=%d(%d pos) mean=%.1fbp sig_t_ex=%s ci_lo_bar=%.1f ci_lo_event=%s perm_p=%s q_pos_t=%s 3gate_bar=%s 3gate_event=%s",
                 qn, m["n_bars"], m["n_events"], m["n_events_pos"],
                 m.get("mean_bp", 0),
                 f"{m.get('signal_t_excess'):.2f}" if m.get('signal_t_excess') is not None else "NA",
                 m.get("ci_lower_bp", 0),
                 f"{m.get('ci_lower_bp_event_agg'):.1f}" if m.get('ci_lower_bp_event_agg') is not None else "NA",
                 f"{m.get('perm_p_one_sided'):.3f}" if m.get('perm_p_one_sided') is not None else "NA",
                 f"{m.get('quarter_pos_t_ratio'):.2f}" if m.get('quarter_pos_t_ratio') is not None else "NA",
                 m.get("three_gate_pass"),
                 m.get("three_gate_pass_event_agg"))

    metrics = {
        "paradigm_number": 231,
        "paradigm_slug": "binance_launchpool_bnb_demand_event_anchored_bilateral_1d_to_7d",
        "phase": "R-1",
        "tag": args.tag,
        "config": {
            "pre_days_window": [args.pre_min, args.pre_max],
            "post_days_window": [args.post_min, args.post_max],
            "hold_days": args.hold_days,
            "fee_bps": FEE_BPS,
            "target_symbol": TARGET_SYM,
            "n_events": int(len(events)),
            "events_window": [str(events["farm_start_utc"].min().date()),
                              str(events["farm_start_utc"].max().date())],
            "kline_window": [str(daily.index[0].date()), str(daily.index[-1].date())],
        },
        "density": density,
        "quadrants": results,
    }

    out_file = out_dir / f"{args.tag}__metrics.json"
    out_file.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("Wrote %s", out_file)


if __name__ == "__main__":
    main()
