"""Paradigm 114 — alt_range_breakout_24h_trailing_high_continuation_long_2h R-1 PoC

Hypothesis
----------
Classic CTA / turtle-trader / Donchian channel breakout — NEVER tested as a
paradigm in 113 graveyards. When an alt's 1h CLOSE breaks above its 24h
trailing high (max of prior 24 hourly closes), AND prior 12h has had no other
breakout event (debounce: ensures FRESH breakout, not consecutive grinding
up against the line), continuation LONG for next 2h.

Mirror: 1h close breaks below 24h trailing LOW (debounced) → continuation
SHORT for 2h.

Direction policy (4-quadrant SNT, Lesson #19)
- A focus  : close > prior 24h max AND debounced -> LONG (continuation)
- A mirror : close > prior 24h max AND debounced -> SHORT (wrong direction)
- B same   : close < prior 24h min AND debounced -> SHORT (continuation)
- B mirror : close < prior 24h min AND debounced -> LONG (wrong direction)

5-axis novelty self-check (4/5 NOVEL ex ante)
- Statistic = trailing max(24h) / min(24h) breakout flag (NOVEL — pure
  price-level deterministic event; all prior 113 paradigms used z-scores /
  percentile ranks / ratios / regime classifications. NO prior catalog
  entry on Donchian-style breakout)
- Universe = standard 13-alt (NOT NOVEL)
- Frame = 1h trigger × 2h hold (PARTIALLY NOVEL — paradigm 113 used same
  frame but trigger axis is hour-of-day anchor, totally different mechanism)
- Mechanism = trend-following / breakout continuation (NOVEL class — not
  momentum z-score, not mean-reversion, not regime-conditional)
- Trigger = deterministic price-level crossing + 12h debounce (NOVEL
  conjunction — event-time discrete crossing, not statistical threshold)

DNA collision check
- Existing paradigm `range_compression_directional_break_alt_30m_240m`
  (graveyard 2026-05-15) is volatility-compression / expansion break
  (path tortuosity z + |return| > 2× vol). It is statistical (z + vol),
  not price-level (rolling extremum). 4/5 dimensions distinct. NOT a
  DNA collision.

Substrate
---------
Reuse paradigm 113 1h OHLCV joblib cache at
`runs/research_track/intraday_hour_of_day_anchor_alt_directional_2h/klines_cache/`
(13 alts × 24 months 2024-05..2026-04, 312 files, ~11MB). ARCHIVE-DIRECT;
no DB dependency per [[feedback-paradigm-architect-local-context]].

R-0 prescreens
- Lesson #11 sample density: trailing-high breakout rate empirically
  ~3-8%/hour (rolling-max threshold). 13 alts × ~17,500 1h bars × 5%
  ≈ 11,000 events. After 12h debounce ≈ 50% retention. After 2h hold
  decimation (no overlap) ≈ same. Per-cell (4 quadrants × ~8 quarters)
  ≈ 300+. PASS.
- Lesson #19 SNT: 4-quadrant in single batch (mandatory).
- Lesson #20 narrow-scope: trigger rate measured empirically; if focus
  fails 3-gate but isolated cell PASS, narrow-scope candidate disqualified
  by life-changing 4-dim layer.
- Lesson #21 axis stacking: joint = breakout AND debounce. Diagnostic
  measures breakout-ALONE (no debounce) and debounce-ALONE is meaningless
  (debounce is conditional on having had a prior breakout, so we measure
  breakout-alone vs joint as the synthesis check).
- Lesson #28 substrate availability: 1h OHLCV via paradigm 113 cache.
  Verified present.
- Lesson #30 data window ratio: 2yr / 2.4yr ≈ 83%. PASS.
- Lesson #34 empirical distribution: trigger rate measured + logged.
- Lesson #39 sub-class A signature antipattern: price-level breakout
  inherently asymmetric direction info (vs symmetric statistic). DO NOT
  expect perfect ±k bp mirror. Document either way.
- Lesson #40 structural threshold feasibility: rolling max/min trivially
  reachable (always exists per window). PASS.

R-1 body
- 4-quadrant Symmetric Negative Test (focus, mirror, B same, B mirror)
- Concentration Gate (per-quarter t + per-sym bootstrap)
- fee_aware_perm_test + bootstrap CI via _perm_utils.py
- 16 bp fee floor (8 bp / leg round-trip)
- Life-changing 4-dim layer (Lesson #20 / NARROW_SCOPE_LIFE_CHANGING_FAIL)
- Lesson #21 axis-stacking diagnostic: breakout-alone vs joint(breakout+debounce)
- Hold sweep [60, 120, 240, 480] min on focus A

Scope
- 13 alts: SOL, HBAR, AVAX, DOGE, LINK, ADA, BCH, LTC, BNB, FIL, NEAR, XRP, ETH
- 24 months 2024-05 .. 2026-04 from paradigm 113 cache.
"""
from __future__ import annotations

import io
import json
import logging
import sys
import time
import zipfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

PARADIGM_SLUG = "alt_range_breakout_24h_trailing_high_continuation_long_2h"
PARADIGM_NUMBER = 114
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)

# REUSE paradigm 113 cache
SHARED_CACHE_DIR = (
    ROOT
    / "runs"
    / "research_track"
    / "intraday_hour_of_day_anchor_alt_directional_2h"
    / "klines_cache"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r1__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p114_r1")

ALTS = [
    "SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT",
    "NEARUSDT", "XRPUSDT", "ETHUSDT",
]

START_MONTH = "2024-05"
END_MONTH = "2026-04"

FEE_PER_TRADE = 0.0008  # 16 bp round-trip
ROLLING_WINDOW_BARS = 24  # 24 hours trailing high/low
DEBOUNCE_BARS = 12  # 12h debounce: no prior breakout within last 12h
PRIMARY_HOLD_BARS = 2  # 2h hold
HOLD_SWEEP_BARS = [1, 2, 4, 8]  # 1h, 2h, 4h, 8h


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def load_1h_klines_from_cache(sym: str, month: str) -> pd.DataFrame:
    """Load monthly 1h klines from paradigm 113 joblib cache."""
    cache_file = SHARED_CACHE_DIR / f"{sym}_1h_{month}.joblib"
    if cache_file.exists():
        try:
            return joblib.load(cache_file)
        except Exception as e:
            log.warning("cache load fail %s %s: %s", sym, month, e)
            return pd.DataFrame()
    log.warning("cache miss %s %s — paradigm 113 cache expected", sym, month)
    return pd.DataFrame()


def build_1h_panel(sym: str, months: list[str]) -> pd.DataFrame:
    parts = []
    for m in months:
        d = load_1h_klines_from_cache(sym, m)
        if not d.empty:
            parts.append(d)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def compute_quadrant(
    quadrant_name: str,
    trigger_mask_per_sym: dict,
    fwd_per_sym: dict,
    direction_per_sym: dict,
    hold_bars: int,
    fee: float,
    candidate_pool_pool: np.ndarray,
) -> dict:
    """Aggregate trades, 3-gate + Concentration + per-quarter + per-sym + life-changing."""
    trades_per_sym: dict[str, list[float]] = {s: [] for s in trigger_mask_per_sym}
    ts_per_sym: dict[str, list[pd.Timestamp]] = {s: [] for s in trigger_mask_per_sym}

    for s, mask in trigger_mask_per_sym.items():
        fwd = fwd_per_sym.get(s)
        d = direction_per_sym[s]
        if fwd is None or len(fwd) == 0:
            continue
        idx_trig = mask.index[mask & fwd.notna()]
        if len(idx_trig) == 0:
            continue
        # decimate: ≥ hold_bars hours gap between consecutive trades per sym
        min_gap = pd.Timedelta(hours=hold_bars)
        last_t = None
        for t in idx_trig:
            if last_t is None or (t - last_t) >= min_gap:
                trades_per_sym[s].append(d * float(fwd.loc[t]))
                ts_per_sym[s].append(t)
                last_t = t

    all_trades: list[float] = []
    all_ts: list[pd.Timestamp] = []
    all_sym: list[str] = []
    for s, lst in trades_per_sym.items():
        all_trades.extend(lst)
        all_ts.extend(ts_per_sym[s])
        all_sym.extend([s] * len(lst))

    if len(all_trades) < 5:
        return {
            "quadrant": quadrant_name,
            "hold_bars": hold_bars,
            "hold_hours": hold_bars,
            "n_trades": len(all_trades),
            "error": "n_trades<5",
        }

    gross = np.asarray(all_trades, dtype=float)
    net = gross - fee
    sd = net.std(ddof=1)
    obs_t = float(net.mean() / sd * np.sqrt(len(net))) if sd > 0 else 0.0
    gross_mean_bp = float(gross.mean() * 10000)
    net_mean_bp = float(net.mean() * 10000)

    ci = bootstrap_ci(net, n_boot=1000, rng_seed=42)

    if len(candidate_pool_pool) < len(net) * 2:
        perm = {
            "perm_p_two_sided": float("nan"),
            "signal_t_excess": float("nan"),
            "null_mean_t": float("nan"),
            "perm_p_one_sided_above": float("nan"),
        }
    else:
        perm = fee_aware_perm_test(
            net, candidate_pool_pool, fee_per_trade=fee, n_perms=1000, rng_seed=42
        )

    per_sym_ci = {}
    for s, lst in trades_per_sym.items():
        if len(lst) < 5:
            per_sym_ci[s] = {"n": len(lst), "ci_lower_bp": float("nan"), "ci_pos": False}
            continue
        net_s = np.asarray(lst) - fee
        ci_s = bootstrap_ci(net_s, n_boot=500, rng_seed=42)
        per_sym_ci[s] = {
            "n": int(len(lst)),
            "mean_bp": float(net_s.mean() * 10000),
            "ci_lower_bp": float(ci_s["ci_lower"] * 10000),
            "ci_upper_bp": float(ci_s["ci_upper"] * 10000),
            "ci_pos": bool(ci_s["ci_lower"] > 0),
        }
    n_syms_ci_pos = sum(1 for v in per_sym_ci.values() if v["ci_pos"])
    syms_ci_pos_ratio = n_syms_ci_pos / len(per_sym_ci) if per_sym_ci else 0.0

    df_q = pd.DataFrame({"ts": all_ts, "ret": net, "sym": all_sym})
    df_q["quarter"] = pd.to_datetime(df_q["ts"]).dt.to_period("Q").astype(str)
    per_q = {}
    for q, sub in df_q.groupby("quarter"):
        if len(sub) < 5:
            per_q[q] = {"n": int(len(sub)), "t": float("nan"), "pos_t": False}
            continue
        sd_q = sub["ret"].std(ddof=1)
        tq = sub["ret"].mean() / sd_q * np.sqrt(len(sub)) if sd_q > 0 else 0
        per_q[q] = {
            "n": int(len(sub)),
            "mean_bp": float(sub["ret"].mean() * 10000),
            "t": float(tq),
            "pos_t": bool(tq > 0),
        }
    n_q_measurable = sum(1 for v in per_q.values() if pd.notna(v["t"]) and v["n"] >= 5)
    n_q_pos = sum(1 for v in per_q.values() if v["pos_t"] and v["n"] >= 5)
    q_pos_ratio = n_q_pos / n_q_measurable if n_q_measurable > 0 else 0.0

    gate_3 = bool(
        perm.get("signal_t_excess", float("nan")) >= 2.0
        and ci["ci_lower"] > 0
        and perm.get("perm_p_two_sided", 1.0) <= 0.10
    )
    gate_conc = bool(
        q_pos_ratio >= 0.5 and syms_ci_pos_ratio >= 0.30 and n_syms_ci_pos >= 3
    )

    # Life-changing 4-dim
    if all_ts:
        n_years = max(
            1e-6, (pd.to_datetime(max(all_ts)) - pd.to_datetime(min(all_ts))).days / 365.25
        )
    else:
        n_years = 1e-6
    trades_per_year = len(net) / n_years
    per_trade_edge_pct = net_mean_bp / 100.0  # bp -> %
    capital_util_pct = min(100.0, (hold_bars * trades_per_year) / (365.25 * 24) * 100)
    sharpe_annual = (net.mean() / sd) * np.sqrt(trades_per_year) if sd > 0 else 0.0
    life_changing_dims = {
        "trades_per_year": float(trades_per_year),
        "per_trade_edge_pct": float(per_trade_edge_pct),
        "capital_util_pct": float(capital_util_pct),
        "annualized_sharpe": float(sharpe_annual),
        "pass_trades_per_year_12": bool(trades_per_year >= 12),
        "pass_edge_2pct": bool(per_trade_edge_pct >= 2.0),
        "pass_util_30pct": bool(capital_util_pct >= 30),
        "pass_sharpe_1_5": bool(sharpe_annual >= 1.5),
        "pass_all_4_dim": bool(
            trades_per_year >= 12
            and per_trade_edge_pct >= 2.0
            and capital_util_pct >= 30
            and sharpe_annual >= 1.5
        ),
    }

    return {
        "quadrant": quadrant_name,
        "hold_bars": hold_bars,
        "hold_hours": hold_bars,
        "n_trades": int(len(net)),
        "n_trades_per_sym": {s: int(len(trades_per_sym[s])) for s in trades_per_sym},
        "obs_mean_gross_bp": gross_mean_bp,
        "obs_mean_net_bp": net_mean_bp,
        "obs_t": obs_t,
        "ci_lower_bp": float(ci["ci_lower"] * 10000),
        "ci_upper_bp": float(ci["ci_upper"] * 10000),
        "ci_pos": bool(ci["ci_lower"] > 0),
        "perm_p_two_sided": float(perm.get("perm_p_two_sided", float("nan"))),
        "perm_p_one_sided_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "gate_3_pass": gate_3,
        "per_quarter": per_q,
        "n_q_measurable": int(n_q_measurable),
        "n_q_pos": int(n_q_pos),
        "q_pos_ratio": float(q_pos_ratio),
        "per_symbol_ci": per_sym_ci,
        "n_syms_ci_pos": int(n_syms_ci_pos),
        "n_syms_total": len(per_sym_ci),
        "syms_ci_pos_ratio": float(syms_ci_pos_ratio),
        "gate_concentration_pass": gate_conc,
        "life_changing_4dim": life_changing_dims,
    }


def main() -> int:
    t_start = time.time()
    out: dict = {
        "paradigm_name": PARADIGM_SLUG,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-1",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "window_months": [START_MONTH, END_MONTH],
        "fee_per_trade": FEE_PER_TRADE,
        "rolling_window_bars": ROLLING_WINDOW_BARS,
        "debounce_bars": DEBOUNCE_BARS,
        "primary_hold_bars": PRIMARY_HOLD_BARS,
        "primary_hold_hours": PRIMARY_HOLD_BARS,
        "hold_sweep_bars": HOLD_SWEEP_BARS,
        "novelty_self_check": {
            "statistic": "NOVEL",
            "universe": "NOT NOVEL",
            "frame": "PARTIALLY NOVEL",
            "mechanism": "NOVEL",
            "trigger": "NOVEL",
            "axes_pass": 4,
            "verdict": "4/5 NOVEL - proceed",
            "dna_collision_check": (
                "vs paradigm range_compression_directional_break_alt_30m_240m "
                "(graveyard 2026-05-15): 4/5 dim distinct. Existing uses path "
                "tortuosity z + |return|>2×vol (statistical compression). "
                "Proposed uses pure price-level rolling extremum (deterministic). "
                "Different statistic, different frame, different mechanism. "
                "NOT a DNA collision."
            ),
        },
        "substrate_source": "paradigm113_klines_cache_reuse",
    }

    months = month_iter(START_MONTH, END_MONTH)
    log.info(
        "loading 1h klines for %d alts × %d months from paradigm 113 cache",
        len(ALTS), len(months),
    )
    t_bf = time.time()
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS:
        t0 = time.time()
        df = build_1h_panel(s, months)
        log.info("  %s: %d rows in %.1fs", s, len(df), time.time() - t0)
        if not df.empty:
            panel[s] = df
    bf_secs = time.time() - t_bf
    log.info("cache load done in %.1fs", bf_secs)

    if len(panel) < 5:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"cache load produced only {len(panel)}/13 series"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    # Build per-sym close series + 24h rolling max/min (prior-bar inclusive)
    close_per_sym: dict[str, pd.Series] = {}
    high_per_sym: dict[str, pd.Series] = {}
    low_per_sym: dict[str, pd.Series] = {}
    rolling_max_per_sym: dict[str, pd.Series] = {}
    rolling_min_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].copy()
        close_per_sym[s] = c
        high_per_sym[s] = df["high"].copy()
        low_per_sym[s] = df["low"].copy()
        # rolling max of the PRIOR ROLLING_WINDOW_BARS closes, EXCLUDING current bar
        # so that a "breakout" means current close strictly exceeds prior window.
        rolling_max_per_sym[s] = c.shift(1).rolling(
            ROLLING_WINDOW_BARS, min_periods=ROLLING_WINDOW_BARS
        ).max()
        rolling_min_per_sym[s] = c.shift(1).rolling(
            ROLLING_WINDOW_BARS, min_periods=ROLLING_WINDOW_BARS
        ).min()

    # Forward H-bar log return per hold value
    fwd_per_sym_by_hold: dict[int, dict[str, pd.Series]] = {}
    for h in HOLD_SWEEP_BARS:
        d = {}
        for s, c in close_per_sym.items():
            d[s] = np.log(c.shift(-h) / c)
        fwd_per_sym_by_hold[h] = d

    # Raw breakout events (NO debounce): close > prior 24h max, close < prior 24h min
    raw_up_per_sym: dict[str, pd.Series] = {}
    raw_dn_per_sym: dict[str, pd.Series] = {}
    for s in panel:
        c = close_per_sym[s]
        rmax = rolling_max_per_sym[s]
        rmin = rolling_min_per_sym[s]
        raw_up_per_sym[s] = ((c > rmax) & rmax.notna()).astype(bool)
        raw_dn_per_sym[s] = ((c < rmin) & rmin.notna()).astype(bool)

    # Debounced breakout: NO prior breakout in last DEBOUNCE_BARS bars (either direction).
    # We compute a "any breakout in last 12h" rolling flag and require it == 0 at trigger.
    debounced_up_per_sym: dict[str, pd.Series] = {}
    debounced_dn_per_sym: dict[str, pd.Series] = {}
    for s in panel:
        any_brk = (raw_up_per_sym[s] | raw_dn_per_sym[s]).astype(int)
        # count of breakouts in prior DEBOUNCE_BARS (excluding current bar)
        prior_count = any_brk.shift(1).rolling(
            DEBOUNCE_BARS, min_periods=1
        ).sum().fillna(0)
        fresh = prior_count == 0
        debounced_up_per_sym[s] = (raw_up_per_sym[s] & fresh).astype(bool)
        debounced_dn_per_sym[s] = (raw_dn_per_sym[s] & fresh).astype(bool)

    # Empirical trigger rate diagnostic (Lesson #20 / #34)
    n_bars_per_sym = {s: int(close_per_sym[s].notna().sum()) for s in panel}
    total_bars = sum(n_bars_per_sym.values())
    n_raw_up = int(sum(m.sum() for m in raw_up_per_sym.values()))
    n_raw_dn = int(sum(m.sum() for m in raw_dn_per_sym.values()))
    n_deb_up = int(sum(m.sum() for m in debounced_up_per_sym.values()))
    n_deb_dn = int(sum(m.sum() for m in debounced_dn_per_sym.values()))
    out["lesson34_empirical_distribution"] = {
        "total_1h_bars_panel": total_bars,
        "raw_up_breakouts": n_raw_up,
        "raw_dn_breakouts": n_raw_dn,
        "debounced_up_breakouts": n_deb_up,
        "debounced_dn_breakouts": n_deb_dn,
        "raw_up_rate_pct": float(100 * n_raw_up / max(1, total_bars)),
        "raw_dn_rate_pct": float(100 * n_raw_dn / max(1, total_bars)),
        "debounced_up_rate_pct": float(100 * n_deb_up / max(1, total_bars)),
        "debounced_dn_rate_pct": float(100 * n_deb_dn / max(1, total_bars)),
        "debounce_retention_up_pct": float(100 * n_deb_up / max(1, n_raw_up)),
        "debounce_retention_dn_pct": float(100 * n_deb_dn / max(1, n_raw_dn)),
    }
    log.info(
        "raw breakout rate: up=%.2f%% dn=%.2f%% | debounced: up=%.2f%% dn=%.2f%% "
        "(retention up=%.1f%% dn=%.1f%%)",
        out["lesson34_empirical_distribution"]["raw_up_rate_pct"],
        out["lesson34_empirical_distribution"]["raw_dn_rate_pct"],
        out["lesson34_empirical_distribution"]["debounced_up_rate_pct"],
        out["lesson34_empirical_distribution"]["debounced_dn_rate_pct"],
        out["lesson34_empirical_distribution"]["debounce_retention_up_pct"],
        out["lesson34_empirical_distribution"]["debounce_retention_dn_pct"],
    )

    # n_quarters & per-quarter density (Lesson #11)
    all_ts_idx = pd.concat([s for s in close_per_sym.values()], axis=1).index
    n_quarters = max(
        1, int(np.ceil((all_ts_idx.max() - all_ts_idx.min()).days / 91))
    )
    decimation = PRIMARY_HOLD_BARS
    expected_up_trades = n_deb_up / max(1, decimation)
    expected_dn_trades = n_deb_dn / max(1, decimation)
    per_quarter_up = expected_up_trades / n_quarters
    per_quarter_dn = expected_dn_trades / n_quarters
    out["lesson11_sample_density"] = {
        "n_deb_up": n_deb_up,
        "n_deb_dn": n_deb_dn,
        "n_quarters": n_quarters,
        "decimation_factor_bars": decimation,
        "expected_up_trades": float(expected_up_trades),
        "expected_dn_trades": float(expected_dn_trades),
        "per_quarter_up": float(per_quarter_up),
        "per_quarter_dn": float(per_quarter_dn),
        "lesson11_floor": 30,
        "passes_lesson11_both": bool(per_quarter_up >= 30 and per_quarter_dn >= 30),
    }
    log.info(
        "Lesson #11 per-quarter: up=%.1f / dn=%.1f (n_quarters=%d)",
        per_quarter_up, per_quarter_dn, n_quarters,
    )

    out["data_window"] = {
        "first": str(all_ts_idx.min()),
        "last": str(all_ts_idx.max()),
        "panel_years": float((all_ts_idx.max() - all_ts_idx.min()).days / 365.25),
        "n_alts_with_data": len(panel),
        "cache_load_seconds": float(bf_secs),
    }
    out["lesson30_data_window_ratio"] = {
        "window_months": len(months),
        "full_window_months_available": 24,
        "ratio": float(len(months) / 24.0),
        "passes_lesson30": bool(len(months) / 24.0 >= 0.30),
    }

    if not out["lesson11_sample_density"]["passes_lesson11_both"]:
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = (
            f"Lesson #11 fail: per-quarter up={per_quarter_up:.1f} / dn={per_quarter_dn:.1f} "
            f"< 30 cutoff."
        )
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 0

    # Candidate pool for fee_aware_perm
    fwd_primary = fwd_per_sym_by_hold[PRIMARY_HOLD_BARS]
    pool_long_vals = []
    pool_short_vals = []
    for s, f in fwd_primary.items():
        a = f.dropna().values
        pool_long_vals.append(a)
        pool_short_vals.append(-a)
    pool_long = np.concatenate(pool_long_vals) if pool_long_vals else np.array([])
    pool_short = np.concatenate(pool_short_vals) if pool_short_vals else np.array([])

    dir_long = {s: +1 for s in panel}
    dir_short = {s: -1 for s in panel}

    # 4-quadrant SNT primary (debounced)
    log.info("=== R-1 4-quadrant SNT (primary hold=%dh, debounced) ===", PRIMARY_HOLD_BARS)
    quadrants = {}
    quadrants["A_focus_breakUp_LONG"] = compute_quadrant(
        "A_focus_breakUp_LONG",
        debounced_up_per_sym,
        fwd_primary,
        dir_long,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_long,
    )
    quadrants["A_mirror_breakUp_SHORT"] = compute_quadrant(
        "A_mirror_breakUp_SHORT",
        debounced_up_per_sym,
        fwd_primary,
        dir_short,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_short,
    )
    quadrants["B_same_sign_breakDn_SHORT"] = compute_quadrant(
        "B_same_sign_breakDn_SHORT",
        debounced_dn_per_sym,
        fwd_primary,
        dir_short,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_short,
    )
    quadrants["B_mirror_breakDn_LONG"] = compute_quadrant(
        "B_mirror_breakDn_LONG",
        debounced_dn_per_sym,
        fwd_primary,
        dir_long,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_long,
    )
    out["quadrants"] = quadrants

    # ─── Lesson #21 axis-stacking diagnostic ─────────────────────────────
    # breakout ALONE (no debounce): use raw_up / raw_dn masks
    log.info("=== Lesson #21 axis-stacking diagnostic (breakout-only, no debounce) ===")
    diag_raw_up = compute_quadrant(
        "DIAG_breakUp_LONG_noDebounce",
        raw_up_per_sym,
        fwd_primary,
        dir_long,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_long,
    )
    diag_raw_dn = compute_quadrant(
        "DIAG_breakDn_SHORT_noDebounce",
        raw_dn_per_sym,
        fwd_primary,
        dir_short,
        PRIMARY_HOLD_BARS,
        FEE_PER_TRADE,
        pool_short,
    )
    out["lesson21_axis_stacking_diagnostic"] = {
        "raw_breakUp_LONG_noDebounce": diag_raw_up,
        "raw_breakDn_SHORT_noDebounce": diag_raw_dn,
        "joint_A_focus_net_bp": quadrants["A_focus_breakUp_LONG"].get(
            "obs_mean_net_bp", 0.0
        ),
        "raw_breakUp_net_bp": diag_raw_up.get("obs_mean_net_bp", 0.0),
        "joint_B_same_net_bp": quadrants["B_same_sign_breakDn_SHORT"].get(
            "obs_mean_net_bp", 0.0
        ),
        "raw_breakDn_net_bp": diag_raw_dn.get("obs_mean_net_bp", 0.0),
        "joint_synthesizes_alpha_A": bool(
            quadrants["A_focus_breakUp_LONG"].get("obs_mean_net_bp", 0.0)
            > diag_raw_up.get("obs_mean_net_bp", 0.0)
        ),
        "joint_synthesizes_alpha_B": bool(
            quadrants["B_same_sign_breakDn_SHORT"].get("obs_mean_net_bp", 0.0)
            > diag_raw_dn.get("obs_mean_net_bp", 0.0)
        ),
    }

    # ─── Hold sweep (focus A only) ─────────────────────────────────────────
    log.info("=== hold sweep on A_focus_breakUp_LONG ===")
    sweep = []
    for h in HOLD_SWEEP_BARS:
        if h == PRIMARY_HOLD_BARS:
            continue
        fwd_h = fwd_per_sym_by_hold[h]
        pool_h_vals = [f.dropna().values for f in fwd_h.values()]
        pool_h = np.concatenate(pool_h_vals) if pool_h_vals else np.array([])
        try:
            res = compute_quadrant(
                f"A_focus_breakUp_LONG_h{h}",
                debounced_up_per_sym,
                fwd_h,
                dir_long,
                h,
                FEE_PER_TRADE,
                pool_h,
            )
            sweep.append(res)
        except Exception as e:
            log.warning("sweep h=%d fail: %s", h, e)
    out["hold_sweep_A_focus"] = sweep

    # ─── Lesson #37 sweep verdict scan (auto-evaluator must scan all cells) ──
    sweep_cells_pass = []
    for res in sweep:
        if res.get("gate_3_pass", False) and res.get("gate_concentration_pass", False):
            lc = res.get("life_changing_4dim", {})
            sweep_cells_pass.append(
                {
                    "cell": res.get("quadrant"),
                    "hold_hours": res.get("hold_hours"),
                    "gross_bp": res.get("obs_mean_gross_bp"),
                    "net_bp": res.get("obs_mean_net_bp"),
                    "sigex": res.get("signal_t_excess"),
                    "lc_all_4dim_pass": lc.get("pass_all_4_dim", False),
                }
            )
    out["lesson37_sweep_scan"] = {
        "n_sweep_cells_3gate_AND_conc_pass": len(sweep_cells_pass),
        "cells": sweep_cells_pass,
    }

    # ─── Lesson #39 symmetry diagnostic ──────────────────────────────────
    a_focus_gross = quadrants["A_focus_breakUp_LONG"].get("obs_mean_gross_bp", 0.0)
    a_mirror_gross = quadrants["A_mirror_breakUp_SHORT"].get("obs_mean_gross_bp", 0.0)
    sym_diff_abs = abs(a_focus_gross + a_mirror_gross)
    out["lesson39_symmetry_diagnostic"] = {
        "A_focus_gross_bp": a_focus_gross,
        "A_mirror_gross_bp": a_mirror_gross,
        "sum_abs_bp": float(sym_diff_abs),
        "is_perfect_mirror": bool(sym_diff_abs < 1.0),
        "note": (
            "Pure price-level breakout has inherent directional info, so we do "
            "NOT expect perfect ±k bp mirror symmetry. If observed near 0, "
            "Lesson #39 sub-class A antipattern triggered."
        ),
    }

    # ─── Verdict aggregation ──────────────────────────────────────────────
    A_focus = quadrants["A_focus_breakUp_LONG"]
    A_mirror = quadrants["A_mirror_breakUp_SHORT"]
    B_same = quadrants["B_same_sign_breakDn_SHORT"]
    B_mirror = quadrants["B_mirror_breakDn_LONG"]

    a_focus_pass_3gate = A_focus.get("gate_3_pass", False)
    a_focus_pass_conc = A_focus.get("gate_concentration_pass", False)
    b_same_pass_3gate = B_same.get("gate_3_pass", False)
    b_same_pass_conc = B_same.get("gate_concentration_pass", False)
    a_focus_full = a_focus_pass_3gate and a_focus_pass_conc
    b_same_full = b_same_pass_3gate and b_same_pass_conc
    n_quadrants_pass_3gate = sum(
        1 for q in (A_focus, A_mirror, B_same, B_mirror) if q.get("gate_3_pass", False)
    )

    a_focus_lc = A_focus.get("life_changing_4dim", {})
    b_same_lc = B_same.get("life_changing_4dim", {})
    a_focus_lc_all = a_focus_lc.get("pass_all_4_dim", False)
    b_same_lc_all = b_same_lc.get("pass_all_4_dim", False)

    if a_focus_full and b_same_full:
        if a_focus_lc_all and b_same_lc_all:
            verdict = "PASS_R1_FULL"
            verdict_reason = (
                "A_focus + B_same both PASS 3-gate AND Concentration AND life-changing 4-dim. "
                "Trailing-high/low breakout continuation confirmed in both directions."
            )
            next_action = "propose_R2"
        else:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_reason = (
                "A_focus + B_same statistical PASS but life-changing 4-dim FAIL. "
                f"A_focus_lc={a_focus_lc_all} B_same_lc={b_same_lc_all}."
            )
            next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
    elif a_focus_full and not b_same_full:
        if a_focus_lc_all:
            verdict = "SPLIT_PARADIGM_A_ONLY"
            verdict_reason = (
                "A_focus (break-up LONG) PASS but B_same (break-dn SHORT) FAIL — "
                "asymmetric mechanism (continuation works on upside breakout only)."
            )
            next_action = "graveyard"
        else:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_reason = (
                "Only A_focus statistical PASS, B_same FAIL, AND A_focus life-changing FAIL."
            )
            next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
    elif b_same_full and not a_focus_full:
        if b_same_lc_all:
            verdict = "SPLIT_PARADIGM_B_ONLY"
            verdict_reason = (
                "B_same PASS but A_focus FAIL — continuation works on downside breakout only."
            )
            next_action = "graveyard"
        else:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_reason = (
                "Only B_same statistical PASS, A_focus FAIL, AND B_same life-changing FAIL."
            )
            next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
    elif n_quadrants_pass_3gate == 0:
        max_focus_gross = max(a_focus_gross, B_same.get("obs_mean_gross_bp", 0.0))
        if max_focus_gross > 0 and max_focus_gross < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"max focus gross +{max_focus_gross:.2f}bp < 16bp fee floor; "
                "mechanism may exist but uneconomic."
            )
        elif out["lesson39_symmetry_diagnostic"]["is_perfect_mirror"]:
            verdict = "BROAD_FALSIFIED_NO_AXIS_SYNTHESIS"
            verdict_reason = (
                "All 4 quadrants FAIL 3-gate AND A_focus + A_mirror mirror exactly — "
                "Lesson #39 sub-class A: trigger carries zero directional info."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                "All 4 quadrants FAIL 3-gate. Trailing breakout debounced carries no "
                "directional alpha."
            )
        next_action = "graveyard"
    else:
        mirror_only = (
            A_mirror.get("gate_3_pass", False) or B_mirror.get("gate_3_pass", False)
        ) and not (a_focus_pass_3gate or b_same_pass_3gate)
        if mirror_only:
            verdict = "BROAD_FALSIFIED_MIRROR_ONLY"
            verdict_reason = (
                "Only mirror quadrant(s) PASS 3-gate — Lesson #8 mirror antipattern, "
                "mechanism inverted (mean-reversion not continuation)."
            )
        else:
            verdict = "PARTIAL_PASS_NO_FULL_FOCUS"
            verdict_reason = (
                f"{n_quadrants_pass_3gate}/4 quadrants pass 3-gate, but no focus + concentration combo."
            )
        next_action = "graveyard"

    out["life_changing_4dim_A_focus"] = a_focus_lc
    out["life_changing_4dim_B_same"] = b_same_lc

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["next_action_recommendation"] = next_action
    out["n_quadrants_pass_3gate"] = n_quadrants_pass_3gate
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    out["_summary_one_liner"] = {
        "paradigm": PARADIGM_SLUG,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "n_samples": int(A_focus.get("n_trades", 0)),
        "A_focus_gross_bp": float(A_focus.get("obs_mean_gross_bp", 0.0)),
        "A_focus_net_bp": float(A_focus.get("obs_mean_net_bp", 0.0)),
        "sigex_focus": float(A_focus.get("signal_t_excess", float("nan"))),
        "concentration_pass": f"{A_focus.get('n_syms_ci_pos', 0)}/{A_focus.get('n_syms_total', 0)}",
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": next_action,
    }

    _write(out)
    log.info("=== R-1 DONE in %.1fmin === verdict=%s", out["wall_clock_minutes"], verdict)
    print(json.dumps(out["_summary_one_liner"], default=str))
    return 0


def _write(payload: dict) -> None:
    p = OUT_DIR / "r1__metrics.json"
    with open(p, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("wrote %s", p)


if __name__ == "__main__":
    sys.exit(main())
