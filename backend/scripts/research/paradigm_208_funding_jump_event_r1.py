"""paradigm 208 R-1 PoC — per-sym 8h funding rate Δ jump event-anchored, signed bilateral 4-quadrant SNT.

HYPOTHESIS
----------
- Per-symbol 8h funding rate Δ (sequential diff) jump magnitude is family-distinct
  from prior funding axes (level / sign flip / cs velocity / per-sym velocity /
  cs dispersion / cross-exchange spread).
- Event anchor: |Δfunding| >= T at 8h boundary (NON-routine sudden jumps, NOT 정기 funding flip).
- Bar direction signed entry, hold +4h / +8h / +24h sweep.
- 4-quadrant Symmetric Negative Test (DISJOINT trigger set per Lesson #69 Item 7
  2nd SUCCESS reinforce):
    A focus  : Δfunding >= +T (POSITIVE jump)  × bar UP  × LONG continuation
    A mirror : Δfunding >= +T (POSITIVE jump)  × bar UP  × SHORT reversal
    B same   : Δfunding <= -T (NEGATIVE jump)  × bar DOWN × SHORT continuation  [DISJOINT]
    B mirror : Δfunding <= -T (NEGATIVE jump)  × bar DOWN × LONG reversal  (Lesson #42 16th)

THRESHOLD PRESCREEN (Lesson #11+#16)
------------------------------------
Spec proposed ±0.05% but empirical distribution shows:
  - p95 |Δfunding| = 0.020%  (5.16% trigger rate, n=2487)
  - p99 |Δfunding| = 0.041%  (1.1% rate, n=~1000)
  - p99.5            0.060%  (0.5% rate, n=~500)
  - ±0.05% specifically: 158 pos + 172 neg = 330 events, 52% in AXSUSDT
    (18/20 syms have n<20 — Lesson #16 ex ante Concentration FAIL).

Adaptive primary threshold: ±0.02% (p95, ~14/20 syms ≥30 events both dirs).
Sweep: ±0.02% / ±0.03% / ±0.05% to map jump-magnitude landscape.

DATA
----
- binance_funding_rate (paradigm 22/170 substrate, 20 deep syms × 2.25yr,
  49,320+ records). Δ = sequential 8h diff within symbol.
- OHLCV 4h joblib cache (runs/ohlcv_cache_12col/, paradigm 198 cohort).
  Coverage: 2024-02-01 → 2026-04-30 (819d). Funding events trimmed to
  funding_time + 24h <= 2026-04-30 23:59 UTC.
- 4-hour bars: entry at next 4h open after funding_time, hold N×4h.
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
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p208_r1")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PARADIGM_ID = 208
PARADIGM_NAME = "alt_per_sym_funding_rate_jump_event_anchored_8h_signed"
OUT_DIR = ROOT / "runs" / "research_track" / f"paradigm_208_{PARADIGM_NAME}"
OHLCV_CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"

# 20-sym cohort (paradigm 22 cohort + paradigm 198 cohort intersection)
COHORT = [
    "AVAXUSDT", "BNBUSDT", "BTCUSDT", "LINKUSDT", "DOTUSDT", "ETHUSDT",
    "ETCUSDT", "ADAUSDT", "XRPUSDT", "NEARUSDT", "FILUSDT", "BCHUSDT",
    "LTCUSDT", "UNIUSDT", "LDOUSDT", "WLDUSDT", "DOGEUSDT", "SOLUSDT",
    "AXSUSDT",
    # TONUSDT excluded — only 1608 funding records (truncated history)
    # PYTHUSDT/JUPUSDT excluded — different funding cadence (4h not 8h)
]

JUMP_THRESHOLDS = [0.0002, 0.0003, 0.0005]  # ±0.02%, ±0.03%, ±0.05%
PRIMARY_THRESHOLD = 0.0002

HOLD_BARS_LIST = [1, 2, 6]  # 4h / 8h / 24h (4h bars)
PRIMARY_HOLD = 1  # 4h

FEE_PER_TRADE = 0.0008  # 8 bp round-trip
DB_URL = "postgresql+psycopg2://antigravity_user:antigravity_password@localhost/antigravity_db"

# Coverage trim: ensure all hold windows fit within OHLCV cache
# Funding events must satisfy funding_time + 24h <= 2026-04-30 23:59 UTC
MAX_FUNDING_TIME = pd.Timestamp("2026-04-29 23:00:00")  # 24h buffer


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_funding(symbols: list[str]) -> pd.DataFrame:
    """Load 8h funding rate panel and compute Δ (sequential diff)."""
    engine = create_engine(DB_URL)
    syms_list = ",".join(f"'{s}'" for s in symbols)
    sql = f"""
        SELECT symbol, funding_time, funding_rate
        FROM binance_funding_rate
        WHERE symbol IN ({syms_list})
        ORDER BY symbol, funding_time
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["funding_time"] = pd.to_datetime(df["funding_time"])
    df = df.sort_values(["symbol", "funding_time"]).reset_index(drop=True)
    df["delta"] = df.groupby("symbol")["funding_rate"].diff()
    log.info("funding panel: %d rows, %d syms, %s → %s",
             len(df), df.symbol.nunique(), df.funding_time.min(), df.funding_time.max())
    return df


def load_ohlcv_panel(symbols: list[str]) -> dict[str, pd.DataFrame]:
    """Load 4h OHLCV joblib cache per symbol."""
    out = {}
    for sym in symbols:
        path = OHLCV_CACHE_DIR / f"{sym}_4h.joblib"
        if not path.exists():
            log.warning("ohlcv cache missing for %s — skipping", sym)
            continue
        df = joblib.load(path)
        if df.index.name != "open_time":
            df = df.copy()
            df.index.name = "open_time"
        df = df.sort_index()
        # keep open + close only for speed
        out[sym] = df[["open", "close"]].copy()
    log.info("ohlcv panel loaded for %d syms", len(out))
    return out


# ---------------------------------------------------------------------------
# Event construction
# ---------------------------------------------------------------------------
def build_events(
    funding: pd.DataFrame,
    ohlcv: dict[str, pd.DataFrame],
    threshold: float,
    hold_bars: int,
) -> pd.DataFrame:
    """Build per-event records.

    For each (sym, funding_time) where |Δ| >= threshold:
      - entry: next 4h bar open after funding_time
      - bar direction: sign of (entry_bar.close - entry_bar.open) (the 4h bar
        containing funding_time, evaluated PRIOR to funding settlement)
      - hold: enter at next bar open, exit at open of bar + hold_bars
      - gross_ret = (exit_price - entry_price) / entry_price  (LONG sign default)

    Returns DataFrame with columns:
      symbol, funding_time, delta, jump_sign, bar_dir, entry_time, entry_price,
      exit_time, exit_price, gross_ret_long, era_year
    """
    records = []
    for sym, g in funding.groupby("symbol"):
        if sym not in ohlcv:
            continue
        bars = ohlcv[sym]
        # restrict to events within bars coverage and respect MAX_FUNDING_TIME
        g_trig = g[
            (g["delta"].abs() >= threshold)
            & (g["funding_time"] <= MAX_FUNDING_TIME)
        ].copy()
        if g_trig.empty:
            continue

        for _, row in g_trig.iterrows():
            ft = row["funding_time"]
            # bar direction: 4h bar containing funding_time (asof ft)
            # 4h bars start at 00,04,08,12,16,20 UTC. funding_time at 00,08,16 UTC
            # so funding_time aligns with bar start.
            bar_idx = bars.index.searchsorted(ft, side="right") - 1
            if bar_idx < 0 or bar_idx >= len(bars):
                continue
            bar_open_time = bars.index[bar_idx]
            bar_open = bars.iloc[bar_idx]["open"]
            bar_close = bars.iloc[bar_idx]["close"]
            if not (np.isfinite(bar_open) and np.isfinite(bar_close)) or bar_open <= 0:
                continue
            bar_dir = np.sign(bar_close - bar_open)
            if bar_dir == 0:
                continue

            # Entry: next bar open (the bar that starts AFTER funding settles)
            entry_idx = bar_idx + 1
            exit_idx = entry_idx + hold_bars - 1 + 1  # close at open of (entry+hold)
            if exit_idx >= len(bars):
                continue
            entry_time = bars.index[entry_idx]
            entry_price = bars.iloc[entry_idx]["open"]
            exit_time = bars.index[exit_idx]
            exit_price = bars.iloc[exit_idx]["open"]
            if not (np.isfinite(entry_price) and np.isfinite(exit_price)) or entry_price <= 0:
                continue

            gross_long = (exit_price - entry_price) / entry_price
            records.append({
                "symbol": sym,
                "funding_time": ft,
                "delta": row["delta"],
                "jump_sign": int(np.sign(row["delta"])),
                "bar_dir": int(bar_dir),
                "entry_time": entry_time,
                "entry_price": entry_price,
                "exit_time": exit_time,
                "exit_price": exit_price,
                "gross_ret_long": gross_long,
                "era_year": entry_time.year,
            })

    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df.sort_values(["entry_time", "symbol"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Candidate pool (for fee-aware perm test)
# ---------------------------------------------------------------------------
def build_candidate_pool(
    ohlcv: dict[str, pd.DataFrame],
    hold_bars: int,
    cap_per_sym: int = 5000,
) -> np.ndarray:
    """Build GROSS LONG returns across all valid hold-windows in the panel.
    Used for fee_aware_perm_test candidate_pool_returns argument.

    Limited to cap_per_sym per sym to keep memory bounded.
    """
    rng = np.random.default_rng(2026)
    pool = []
    for sym, bars in ohlcv.items():
        opens = bars["open"].values
        n = len(opens)
        if n <= hold_bars + 1:
            continue
        entries = opens[:n - hold_bars]
        exits = opens[hold_bars:]
        valid = (entries > 0) & np.isfinite(entries) & np.isfinite(exits)
        gross = (exits[valid] - entries[valid]) / entries[valid]
        # cap
        if len(gross) > cap_per_sym:
            sel = rng.choice(len(gross), size=cap_per_sym, replace=False)
            gross = gross[sel]
        pool.append(gross)
    if not pool:
        return np.array([])
    return np.concatenate(pool)


# ---------------------------------------------------------------------------
# 4-quadrant SNT evaluation
# ---------------------------------------------------------------------------
def eval_quadrant(
    events: pd.DataFrame,
    jump_sign: int,
    bar_dir: int,
    trade_side: int,
    candidate_pool_long: np.ndarray,
    fee: float = FEE_PER_TRADE,
    label: str = "",
) -> dict:
    """Evaluate one of 4 SNT cells.

    jump_sign: +1 (positive Δ jump) or -1 (negative Δ jump)  -- DISJOINT trigger set
    bar_dir:   +1 (bar UP)   or -1 (bar DOWN)
    trade_side:+1 (LONG)     or -1 (SHORT)

    Net return: trade_side * gross_long - fee
    Candidate pool: trade_side * candidate_pool_long (preserves fee-floor properties)
    """
    sub = events[(events["jump_sign"] == jump_sign) & (events["bar_dir"] == bar_dir)].copy()
    n = len(sub)
    if n < 10:
        return {
            "label": label, "n": n,
            "obs_mean_bp": float("nan"), "obs_t": float("nan"),
            "signal_t_excess": float("nan"), "null_mean_t": float("nan"),
            "perm_p_above": float("nan"), "perm_p_below": float("nan"),
            "ci_lower_bp": float("nan"), "ci_upper_bp": float("nan"),
            "ci_mean_bp": float("nan"), "prob_positive": float("nan"),
            "n_syms_pos_ci": 0, "n_syms_measurable": 0,
            "verdict": "INSUFFICIENT_N",
        }

    net = trade_side * sub["gross_ret_long"].values - fee
    pool_side = trade_side * candidate_pool_long

    # CI
    ci = bootstrap_ci(net.tolist(), n_boot=2000, block_size=20, rng_seed=42)
    # Fee-aware perm
    perm = fee_aware_perm_test(
        observed_net_returns=net.tolist(),
        candidate_pool_returns=pool_side.tolist(),
        fee_per_trade=fee,
        n_perms=1000,
        rng_seed=42,
    )

    # Per-symbol CI for Concentration diagnostics
    sym_results = {}
    n_pos_ci = 0
    n_measurable = 0
    for sym, gsub in sub.groupby("symbol"):
        if len(gsub) < 5:
            continue
        n_measurable += 1
        net_sym = trade_side * gsub["gross_ret_long"].values - fee
        ci_sym = bootstrap_ci(net_sym.tolist(), n_boot=500, block_size=10, rng_seed=42)
        sym_results[sym] = {
            "n": len(gsub),
            "mean_bp": float(ci_sym["mean"]) * 10000,
            "ci_lower_bp": float(ci_sym["ci_lower"]) * 10000,
            "ci_upper_bp": float(ci_sym["ci_upper"]) * 10000,
            "prob_positive": float(ci_sym["prob_positive"]),
        }
        if ci_sym["ci_lower"] > 0:
            n_pos_ci += 1

    # Per-era stratification
    era_results = {}
    for era, gsub in sub.groupby("era_year"):
        if len(gsub) < 10:
            continue
        net_era = trade_side * gsub["gross_ret_long"].values - fee
        # short ci
        ci_era = bootstrap_ci(net_era.tolist(), n_boot=500, block_size=10, rng_seed=42)
        era_results[int(era)] = {
            "n": len(gsub),
            "mean_bp": float(ci_era["mean"]) * 10000,
            "ci_lower_bp": float(ci_era["ci_lower"]) * 10000,
            "prob_positive": float(ci_era["prob_positive"]),
        }

    # Verdict
    sigex = float(perm.get("signal_t_excess", float("nan")))
    ci_lower = float(ci["ci_lower"])
    # Use one-sided perm_p_above for continuation cells (jump_sign matches bar_dir matches trade_side)
    # Use perm_p_below for reversal cells (trade_side opposite of bar_dir)
    if (jump_sign == bar_dir) and (trade_side == bar_dir):
        perm_p = float(perm.get("perm_p_one_sided_above", float("nan")))
    else:
        # reversal: trade_side opposite of bar_dir
        perm_p = float(perm.get("perm_p_one_sided_above", float("nan")))  # we want above-null

    three_gate = (sigex >= 2.0) and (ci_lower > 0) and (perm_p <= 0.10)
    verdict = "PASS_R1" if three_gate else "FAIL_R1"

    return {
        "label": label,
        "n": n,
        "obs_mean_bp": float(np.mean(net)) * 10000,
        "obs_t": float(perm["obs_t"]),
        "signal_t_excess": sigex,
        "null_mean_t": float(perm["null_mean_t"]),
        "perm_p_above": float(perm["perm_p_one_sided_above"]),
        "perm_p_below": float(perm["perm_p_one_sided_below"]),
        "perm_p_two_sided": float(perm["perm_p_two_sided"]),
        "ci_lower_bp": ci_lower * 10000,
        "ci_upper_bp": float(ci["ci_upper"]) * 10000,
        "ci_mean_bp": float(ci["mean"]) * 10000,
        "prob_positive": float(ci["prob_positive"]),
        "n_syms_pos_ci": n_pos_ci,
        "n_syms_measurable": n_measurable,
        "sym_ci_pos_ratio": (n_pos_ci / n_measurable) if n_measurable else 0.0,
        "per_sym": sym_results,
        "per_era": era_results,
        "three_gate_pass": three_gate,
        "verdict": verdict,
    }


def measure_temporal_clusters(events: pd.DataFrame, min_gap_h: int = 24) -> dict:
    """Measure temporal_cluster_ratio = n_independent_episodes / n_aggregate.
    Per Lesson candidate post-206 (CONFIRMED-자격 2 dogfoods, paradigm 208 = 3rd test).

    Independent episode: events separated by >= min_gap_h hours within same symbol.
    """
    if events.empty:
        return {"n_aggregate": 0, "n_independent": 0, "ratio": 0.0}
    n_agg = len(events)
    n_indep = 0
    for sym, g in events.groupby("symbol"):
        g_sorted = g.sort_values("entry_time")
        prev_t = None
        for t in g_sorted["entry_time"]:
            if prev_t is None or (t - prev_t).total_seconds() >= min_gap_h * 3600:
                n_indep += 1
                prev_t = t
    return {
        "n_aggregate": n_agg,
        "n_independent": n_indep,
        "ratio": n_indep / n_agg if n_agg else 0.0,
        "min_gap_h": min_gap_h,
    }


# ---------------------------------------------------------------------------
# Main R-1 sweep
# ---------------------------------------------------------------------------
def run_r1():
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    funding = load_funding(COHORT)
    ohlcv = load_ohlcv_panel(COHORT)

    # Cohort effective = intersection of funding-eligible and ohlcv-cached
    eff_cohort = sorted(set(funding.symbol.unique()) & set(ohlcv.keys()))
    log.info("effective cohort = %d syms: %s", len(eff_cohort), eff_cohort)

    results = {
        "paradigm_id": PARADIGM_ID,
        "paradigm_name": PARADIGM_NAME,
        "fee_per_trade": FEE_PER_TRADE,
        "primary_threshold": PRIMARY_THRESHOLD,
        "primary_hold_bars": PRIMARY_HOLD,
        "cohort": eff_cohort,
        "max_funding_time": str(MAX_FUNDING_TIME),
        "sweep": {},
    }

    for thr in JUMP_THRESHOLDS:
        for hb in HOLD_BARS_LIST:
            cell_key = f"thr_{thr*100:.3f}_hold_{hb*4}h"
            log.info("=== sweep cell: threshold=±%.3f%%, hold=%dh ===", thr * 100, hb * 4)

            events = build_events(funding, ohlcv, threshold=thr, hold_bars=hb)
            if events.empty:
                results["sweep"][cell_key] = {"n_events_total": 0, "error": "no events"}
                continue

            pool = build_candidate_pool(ohlcv, hold_bars=hb)

            n_pos_jump = (events["jump_sign"] == 1).sum()
            n_neg_jump = (events["jump_sign"] == -1).sum()
            log.info("events total=%d  pos_jump=%d  neg_jump=%d  pool=%d",
                     len(events), n_pos_jump, n_neg_jump, len(pool))

            # 4-quadrant SNT
            quadrants = {
                "A_focus":   eval_quadrant(events, jump_sign=+1, bar_dir=+1, trade_side=+1,
                                            candidate_pool_long=pool, label="A_focus_POSjump_barUP_LONG"),
                "A_mirror":  eval_quadrant(events, jump_sign=+1, bar_dir=+1, trade_side=-1,
                                            candidate_pool_long=pool, label="A_mirror_POSjump_barUP_SHORT"),
                "B_same":    eval_quadrant(events, jump_sign=-1, bar_dir=-1, trade_side=-1,
                                            candidate_pool_long=pool, label="B_same_NEGjump_barDOWN_SHORT"),
                "B_mirror":  eval_quadrant(events, jump_sign=-1, bar_dir=-1, trade_side=+1,
                                            candidate_pool_long=pool, label="B_mirror_NEGjump_barDOWN_LONG"),
            }

            # Temporal cluster ratio (24h gap)
            temp_focus = measure_temporal_clusters(
                events[(events["jump_sign"] == 1) & (events["bar_dir"] == 1)],
                min_gap_h=24,
            )
            temp_bsame = measure_temporal_clusters(
                events[(events["jump_sign"] == -1) & (events["bar_dir"] == -1)],
                min_gap_h=24,
            )

            # Item 7 cross-set asymmetry: |A_focus_n| vs |B_same_n|
            n_A = quadrants["A_focus"]["n"]
            n_B = quadrants["B_same"]["n"]
            cross_set_ratio = max(n_A, n_B) / max(min(n_A, n_B), 1)

            results["sweep"][cell_key] = {
                "threshold": thr,
                "hold_bars": hb,
                "hold_h": hb * 4,
                "n_events_total": len(events),
                "n_pos_jump": int(n_pos_jump),
                "n_neg_jump": int(n_neg_jump),
                "quadrants": quadrants,
                "temporal_cluster_A_focus": temp_focus,
                "temporal_cluster_B_same": temp_bsame,
                "item7_cross_set": {
                    "n_A_focus": n_A,
                    "n_B_same": n_B,
                    "asym_ratio": cross_set_ratio,
                    "is_disjoint": True,
                    "note": "DISJOINT trigger sets by construction (jump_sign +1 vs -1, bar_dir +1 vs -1)",
                },
            }

    # Primary cell summary
    primary_key = f"thr_{PRIMARY_THRESHOLD*100:.3f}_hold_{PRIMARY_HOLD*4}h"
    primary = results["sweep"].get(primary_key, {})

    results["primary_summary"] = {
        "primary_key": primary_key,
        "n_events_total": primary.get("n_events_total", 0),
        "A_focus_three_gate": primary.get("quadrants", {}).get("A_focus", {}).get("three_gate_pass", False),
        "B_same_three_gate": primary.get("quadrants", {}).get("B_same", {}).get("three_gate_pass", False),
        "A_focus_sigex": primary.get("quadrants", {}).get("A_focus", {}).get("signal_t_excess"),
        "B_same_sigex": primary.get("quadrants", {}).get("B_same", {}).get("signal_t_excess"),
    }

    results["wall_clock_sec"] = round(time.time() - t0, 1)

    out_json = OUT_DIR / "r1__metrics.json"
    with open(out_json, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    log.info("wrote %s (wall=%.1fs)", out_json, results["wall_clock_sec"])

    return results


if __name__ == "__main__":
    run_r1()
