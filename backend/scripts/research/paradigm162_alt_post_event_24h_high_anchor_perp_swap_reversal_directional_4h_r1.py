"""Paradigm 162 — alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h R-1 PoC

Reframe context
---------------
post lifecycle_pump_decay R-5 promotion. R-0 inventory check verified:
- paradigm 158 A_mirror_pump_SHORT @ p90 hold 24h: gross -1.98bp sigex -0.31
- paradigm 158 A_mirror_pump_SHORT @ p95 hold 24h: gross -23.63bp
- paradigm 117 R-1 4h B_same_sign_pump_SHORT: gross +35.55bp sigex +1.87 (3-gate FAIL)

paradigm 162 = 24h max-running anchor event × SHORT 4h hold mean-reversion.
Family-distinct strict 4-dim audit vs paradigm 117/158:
  - vs 117 strict count 2/5 (mechanism direction + hold)
  - vs 158 strict count 3/5 (entry-side anchor + mechanism + hold) STRICT family-distinct
Lesson #62 BOUNDARY_PASS achieved.

Hypothesis
----------
Per-symbol 24h rolling-high cross-up event를 anchor로 사용, anchor cross-up
직후 4h hold SHORT reversal mean-reversion 알파 가설.

A_focus  : 24h new high cross-up × SHORT 4h hold (resistance reversal MR)
A_mirror : 24h new high cross-up × LONG  4h hold (breakout continuation)
B_same   : 24h new low cross-down × LONG 4h hold (support reversal MR)
B_mirror : 24h new low cross-down × SHORT 4h hold (breakdown continuation)

Lesson prescreens
  - #11 sample density: 24h new high empirical rate 측정, debounce ≥6 bars (24h)
  - #19 SNT: 4-quadrant in single batch
  - #28 substrate: 12-col 4h joblib cache 13 syms × ~4914 bars
  - #30 data window: 2.25yr / 2.4yr = 93.75% PASS
  - #34 empirical distribution: anchor event rate + per-sym distribution measured + logged
  - #67 ESCAPE: per-sym idiosyncratic anchor (no cross-asset broadcast)
  - #68 ESCAPE: 4h hold + per-sym anchor (no session-boundary universe-wide)
  - #21 ESCAPE: single axis × single mechanism
  - #42 prediction cross-reference: paradigm 158 A_mirror 24h pattern subspace 4h timescale 첫 explicit test

Scope
  - 13 alts 12-col 4h joblib cache (영구 자산)
  - 2024-02..2026-04 ~2.25yr (data_window_ratio 93.75% PASS Lesson #30)

Verdict tree (post-pivot edge≥2%/trade PRIMARY hard-block)
  PASS_R1_FULL                       : any cell 3-gate + Conc + lc4
  NARROW_SCOPE_LIFE_CHANGING_FAIL    : 3-gate + Conc + edge≥2% but other dim fail
  BROAD_FALSIFIED_DIRECTION_INVERTED : A_focus gross significantly negative
  BROAD_FALSIFIED_FEE_FLOOR          : A_focus 0<g<16bp net sub-fee 4h
  BROAD_FALSIFIED_NO_THREE_GATE      : no quadrant clears 3-gate
  BROAD_FALSIFIED                    : all 4 quadrants non-positive gross
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

ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

PARADIGM_SLUG = "alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h"
PARADIGM_NUMBER = 162
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r1__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p162_r1")

# 12-col 4h cache verified syms (alts only, BTC excluded from universe)
ALTS = [
    "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT",
    "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT", "NEARUSDT",
    "XRPUSDT", "ETHUSDT", "WIFUSDT",
]

FEE_PER_TRADE = 0.0008  # 16 bp round-trip

ROLLING_24H_BARS = 6   # 24h / 4h = 6 bars (anchor window)
DEBOUNCE_BARS_4H = 6   # 24h debounce to keep anchor cross-up events independent

PRIMARY_HOLD_BARS_4H = 1   # 4h primary (paradigm 162 short hold)
HOLD_SWEEP_BARS_4H = [1, 3, 6]  # 4h / 12h / 24h


def load_4h_klines(sym: str) -> pd.DataFrame:
    p = CACHE_DIR / f"{sym}_4h.joblib"
    if not p.exists():
        return pd.DataFrame()
    df = joblib.load(p)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def compute_debounced_count(mask_per_sym: dict[str, pd.Series], debounce_bars: int) -> int:
    """Count debounced triggers across syms (≥debounce_bars × 4h gap)."""
    total = 0
    min_gap = pd.Timedelta(hours=debounce_bars * 4)
    for s, mask in mask_per_sym.items():
        idx_trig = mask.index[mask.fillna(False)]
        if len(idx_trig) == 0:
            continue
        last_t = None
        for t in idx_trig:
            if last_t is None or (t - last_t) >= min_gap:
                total += 1
                last_t = t
    return total


def compute_quadrant(
    quadrant_name: str,
    trigger_mask_per_sym: dict,
    fwd_per_sym: dict,
    direction_per_sym: dict,
    hold_bars: int,
    debounce_bars: int,
    fee: float,
    candidate_pool: np.ndarray,
) -> dict:
    """4-gate (3-gate + Concentration + per-sym CI + life-changing 4-dim)."""
    trades_per_sym: dict[str, list[float]] = {s: [] for s in trigger_mask_per_sym}
    ts_per_sym: dict[str, list[pd.Timestamp]] = {s: [] for s in trigger_mask_per_sym}

    min_gap = pd.Timedelta(hours=debounce_bars * 4)
    for s, mask in trigger_mask_per_sym.items():
        fwd = fwd_per_sym.get(s)
        d = direction_per_sym[s]
        if fwd is None or len(fwd) == 0:
            continue
        idx_trig = mask.index[mask.fillna(False) & fwd.notna()]
        if len(idx_trig) == 0:
            continue
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
            "hold_bars_4h": hold_bars,
            "hold_hours": hold_bars * 4,
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

    if len(candidate_pool) < len(net) * 2:
        perm = {
            "perm_p_two_sided": float("nan"),
            "signal_t_excess": float("nan"),
            "null_mean_t": float("nan"),
            "perm_p_one_sided_above": float("nan"),
        }
    else:
        perm = fee_aware_perm_test(
            net, candidate_pool, fee_per_trade=fee, n_perms=1000, rng_seed=42
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

    if all_ts:
        n_years = max(
            1e-6, (pd.to_datetime(max(all_ts)) - pd.to_datetime(min(all_ts))).days / 365.25
        )
    else:
        n_years = 1e-6
    trades_per_year = len(net) / n_years
    per_trade_edge_pct = net_mean_bp / 100.0
    capital_util_pct = min(100.0, (hold_bars * 4 * trades_per_year) / (365.25 * 24) * 100)
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
        "hold_bars_4h": hold_bars,
        "hold_hours": hold_bars * 4,
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


def _convert(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _convert(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert(v) for v in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    return obj


def _write(out: dict) -> None:
    metrics_path = OUT_DIR / "r1__metrics.json"
    with metrics_path.open("w") as f:
        json.dump(_convert(out), f, indent=2)
    log.info("metrics written: %s", metrics_path)


def main() -> int:
    t_start = time.time()
    out: dict = {
        "paradigm_name": PARADIGM_SLUG,
        "paradigm_number": PARADIGM_NUMBER,
        "phase": "R-1",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "reframe_context": (
            "paradigm 117 R-1 4h B_same_sign_pump_SHORT gross +35.55bp sigex +1.87 "
            "(3-gate FAIL) + paradigm 158 A_mirror_pump_SHORT 24h hold sub-fee = "
            "paradigm 162 anchor event reformulation 4h subspace explicit test. "
            "Family-distinct strict count vs 117=2/5 vs 158=3/5 BOUNDARY_PASS."
        ),
        "family_distinct_strict_audit_lesson62": {
            "vs_paradigm_117": {
                "statistic": "partial (anchor cross-up vs cum return ≤-15%)",
                "universe": "partial (13 alts subset vs 28 alts)",
                "entry_side_class": "partial (UP anchor vs DOWN magnitude)",
                "mechanism_alpha_class": "STRICT (reversal SHORT vs MR LONG)",
                "hold": "STRICT (4h vs 24h)",
                "strict_count": 2,
                "verdict": "BOUNDARY_PASS",
            },
            "vs_paradigm_158": {
                "statistic": "partial (anchor cross-up vs p90 threshold both UP-side)",
                "universe": "identical (13 alts)",
                "entry_side_class": "STRICT (anchor event vs magnitude threshold)",
                "mechanism_alpha_class": "STRICT (reversal SHORT vs continuation LONG)",
                "hold": "STRICT (4h vs 24h)",
                "strict_count": 3,
                "verdict": "STRICT_FAMILY_DISTINCT",
            },
        },
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "substrate": "12-col 4h klines joblib cache (영구 자산)",
        "rolling_24h_bars_4h": ROLLING_24H_BARS,
        "debounce_bars_4h": DEBOUNCE_BARS_4H,
        "fee_per_trade": FEE_PER_TRADE,
        "primary_hold_bars_4h": PRIMARY_HOLD_BARS_4H,
        "primary_hold_hours": PRIMARY_HOLD_BARS_4H * 4,
        "hold_sweep_bars_4h": HOLD_SWEEP_BARS_4H,
        "trigger_definition": (
            "A_focus: close[t] > max(close[t-1..t-6]) (24h new-high cross-up). "
            "B_same: close[t] < min(close[t-1..t-6]) (24h new-low cross-down). "
            "Debounce ≥ 6 bars (24h) keeps anchor events independent."
        ),
    }

    log.info("loading 4h klines for %d alts from 12-col joblib cache", len(ALTS))
    t_bf = time.time()
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS:
        df = load_4h_klines(s)
        if df.empty:
            log.warning("  %s: empty cache — drop", s)
            continue
        if len(df) < 3000:
            log.warning("  %s: only %d rows (<3000) — drop", s, len(df))
            continue
        panel[s] = df
    bf_secs = time.time() - t_bf
    log.info(
        "cache load done in %.1fs (%d/%d alts usable)",
        bf_secs, len(panel), len(ALTS),
    )

    if len(panel) < 8:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = (
            f"cache load produced only {len(panel)}/{len(ALTS)} usable series"
        )
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    out["n_alts_usable"] = len(panel)
    out["alts_usable"] = sorted(panel.keys())

    # Per-sym close + 24h new-high anchor event detection
    close_per_sym: dict[str, pd.Series] = {}
    high_anchor_mask_per_sym: dict[str, pd.Series] = {}
    low_anchor_mask_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].astype(float).copy()
        close_per_sym[s] = c
        # rolling 24h max BEFORE current bar (shift 1 to exclude current bar from window)
        rolling_max = c.rolling(window=ROLLING_24H_BARS, min_periods=ROLLING_24H_BARS).max().shift(1)
        rolling_min = c.rolling(window=ROLLING_24H_BARS, min_periods=ROLLING_24H_BARS).min().shift(1)
        # anchor cross-up event: close[t] > prior 24h max
        high_anchor_mask_per_sym[s] = (c > rolling_max) & rolling_max.notna()
        # anchor cross-down event: close[t] < prior 24h min
        low_anchor_mask_per_sym[s] = (c < rolling_min) & rolling_min.notna()

    # Forward returns per hold
    fwd_per_sym_by_hold: dict[int, dict[str, pd.Series]] = {}
    for h in HOLD_SWEEP_BARS_4H:
        d = {}
        for s, c in close_per_sym.items():
            d[s] = np.log(c.shift(-h) / c)
        fwd_per_sym_by_hold[h] = d

    fwd_primary = fwd_per_sym_by_hold[PRIMARY_HOLD_BARS_4H]
    pool_long_primary = (
        np.concatenate([f.dropna().values for f in fwd_primary.values()])
        if fwd_primary else np.array([])
    )
    pool_short_primary = -pool_long_primary

    dir_long = {s: +1 for s in panel}
    dir_short = {s: -1 for s in panel}

    # Lesson #34 empirical anchor event rate
    n_bars_total = sum(int(close_per_sym[s].notna().sum()) for s in panel)
    n_raw_high = int(sum(m.sum() for m in high_anchor_mask_per_sym.values()))
    n_raw_low = int(sum(m.sum() for m in low_anchor_mask_per_sym.values()))
    n_deb_high = compute_debounced_count(high_anchor_mask_per_sym, DEBOUNCE_BARS_4H)
    n_deb_low = compute_debounced_count(low_anchor_mask_per_sym, DEBOUNCE_BARS_4H)

    all_ts_idx = pd.concat([s for s in close_per_sym.values()], axis=1).index
    n_quarters = max(
        1, int(np.ceil((all_ts_idx.max() - all_ts_idx.min()).days / 91))
    )
    per_q_high = n_deb_high / n_quarters
    per_q_low = n_deb_low / n_quarters

    out["lesson34_empirical_anchor_event_rate"] = {
        "n_bars_total": int(n_bars_total),
        "n_raw_high_anchor": int(n_raw_high),
        "n_raw_low_anchor": int(n_raw_low),
        "n_debounced_high_anchor": int(n_deb_high),
        "n_debounced_low_anchor": int(n_deb_low),
        "raw_high_anchor_rate_pct": float(100 * n_raw_high / max(1, n_bars_total)),
        "raw_low_anchor_rate_pct": float(100 * n_raw_low / max(1, n_bars_total)),
        "debounced_high_per_quarter": float(per_q_high),
        "debounced_low_per_quarter": float(per_q_low),
        "n_quarters": int(n_quarters),
    }
    log.info(
        "empirical anchor event rates: raw_high=%d (%.2f%%) deb_high=%d (%.1f/quarter) | "
        "raw_low=%d (%.2f%%) deb_low=%d (%.1f/quarter)",
        n_raw_high,
        out["lesson34_empirical_anchor_event_rate"]["raw_high_anchor_rate_pct"],
        n_deb_high, per_q_high,
        n_raw_low,
        out["lesson34_empirical_anchor_event_rate"]["raw_low_anchor_rate_pct"],
        n_deb_low, per_q_low,
    )

    lesson11_high_pass = per_q_high >= 30
    lesson11_low_pass = per_q_low >= 30
    out["lesson11_high_pass"] = bool(lesson11_high_pass)
    out["lesson11_low_pass"] = bool(lesson11_low_pass)

    if not lesson11_high_pass:
        log.warning(
            "Lesson #11 HALT — debounced high anchor %.1f/quarter < 30 cutoff",
            per_q_high,
        )
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = (
            f"24h high anchor debounced events {per_q_high:.1f}/quarter < 30 "
            f"Lesson #11 cutoff. trigger reformulation (anchor + magnitude threshold) needed."
        )
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    # 4-quadrant SNT @ primary hold (4h)
    log.info(
        "=== 4-quadrant SNT @ primary hold=%dh ===",
        PRIMARY_HOLD_BARS_4H * 4,
    )
    quadrants_primary = {}
    quadrants_primary["A_focus_high_anchor_SHORT"] = compute_quadrant(
        f"A_focus_high_anchor_SHORT_h{PRIMARY_HOLD_BARS_4H * 4}",
        high_anchor_mask_per_sym, fwd_primary, dir_short,
        PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
        pool_short_primary,
    )
    quadrants_primary["A_mirror_high_anchor_LONG"] = compute_quadrant(
        f"A_mirror_high_anchor_LONG_h{PRIMARY_HOLD_BARS_4H * 4}",
        high_anchor_mask_per_sym, fwd_primary, dir_long,
        PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
        pool_long_primary,
    )
    if lesson11_low_pass:
        quadrants_primary["B_same_low_anchor_LONG"] = compute_quadrant(
            f"B_same_low_anchor_LONG_h{PRIMARY_HOLD_BARS_4H * 4}",
            low_anchor_mask_per_sym, fwd_primary, dir_long,
            PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
            pool_long_primary,
        )
        quadrants_primary["B_mirror_low_anchor_SHORT"] = compute_quadrant(
            f"B_mirror_low_anchor_SHORT_h{PRIMARY_HOLD_BARS_4H * 4}",
            low_anchor_mask_per_sym, fwd_primary, dir_short,
            PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
            pool_short_primary,
        )
    out["quadrants_primary"] = quadrants_primary

    # Lesson #39 mirror diagnostic (A side)
    a_focus_gross = quadrants_primary["A_focus_high_anchor_SHORT"].get("obs_mean_gross_bp", 0.0)
    a_mirror_gross = quadrants_primary["A_mirror_high_anchor_LONG"].get("obs_mean_gross_bp", 0.0)
    sum_abs_mirror_A = abs(a_focus_gross + a_mirror_gross)

    b_same_gross = quadrants_primary.get("B_same_low_anchor_LONG", {}).get("obs_mean_gross_bp", float("nan"))
    b_mirror_gross = quadrants_primary.get("B_mirror_low_anchor_SHORT", {}).get("obs_mean_gross_bp", float("nan"))
    if b_same_gross is not None and b_mirror_gross is not None and not np.isnan(b_same_gross) and not np.isnan(b_mirror_gross):
        sum_abs_mirror_B = abs(b_same_gross + b_mirror_gross)
    else:
        sum_abs_mirror_B = float("nan")

    out["lesson39_symmetry"] = {
        "A_focus_gross_bp": a_focus_gross,
        "A_mirror_gross_bp": a_mirror_gross,
        "A_sum_abs_bp": float(sum_abs_mirror_A),
        "A_is_perfect_mirror": bool(sum_abs_mirror_A < 1.0),
        "B_same_gross_bp": float(b_same_gross) if b_same_gross is not None and not np.isnan(b_same_gross) else None,
        "B_mirror_gross_bp": float(b_mirror_gross) if b_mirror_gross is not None and not np.isnan(b_mirror_gross) else None,
        "B_sum_abs_bp": float(sum_abs_mirror_B) if not np.isnan(sum_abs_mirror_B) else None,
        "B_is_perfect_mirror": bool(sum_abs_mirror_B < 1.0) if not np.isnan(sum_abs_mirror_B) else None,
    }

    # Lesson #8 universal LONG bias check
    long_bias_check = {
        "A_mirror_high_anchor_LONG_gross_bp": a_mirror_gross,
        "B_same_low_anchor_LONG_gross_bp": float(b_same_gross) if b_same_gross is not None and not np.isnan(b_same_gross) else None,
        "both_LONG_positive": bool(
            a_mirror_gross > 0
            and b_same_gross is not None and not np.isnan(b_same_gross) and b_same_gross > 0
        ),
    }
    out["lesson8_long_bias_check"] = long_bias_check

    # Summary log of all 4 quadrants
    for qname, q in quadrants_primary.items():
        log.info(
            "  %s n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci=[%.2f,%.2f] 3gate=%s conc=%s edge=%.2f%% trades/yr=%.0f lc4=%s",
            qname,
            q.get("n_trades", 0),
            q.get("obs_mean_gross_bp", 0),
            q.get("obs_mean_net_bp", 0),
            q.get("signal_t_excess") if q.get("signal_t_excess") is not None else -999,
            q.get("ci_lower_bp", 0),
            q.get("ci_upper_bp", 0),
            q.get("gate_3_pass"),
            q.get("gate_concentration_pass"),
            q.get("life_changing_4dim", {}).get("per_trade_edge_pct", 0),
            q.get("life_changing_4dim", {}).get("trades_per_year", 0),
            q.get("life_changing_4dim", {}).get("pass_all_4_dim"),
        )

    # Hold sweep on A_focus_high_anchor_SHORT (primary mechanism)
    log.info("=== hold sweep on A_focus_high_anchor_SHORT ===")
    sweep_results = []
    for h in HOLD_SWEEP_BARS_4H:
        if h == PRIMARY_HOLD_BARS_4H:
            sweep_results.append(
                {**quadrants_primary["A_focus_high_anchor_SHORT"], "is_primary_hold": True}
            )
            continue
        fwd_h = fwd_per_sym_by_hold[h]
        pool_h = -np.concatenate([f.dropna().values for f in fwd_h.values()])  # SHORT direction
        try:
            res = compute_quadrant(
                f"A_focus_high_anchor_SHORT_h{h * 4}",
                high_anchor_mask_per_sym, fwd_h, dir_short,
                h, DEBOUNCE_BARS_4H, FEE_PER_TRADE, pool_h,
            )
            res["is_primary_hold"] = False
            sweep_results.append(res)
            log.info(
                "  hold=%dh n=%d gross=%.2fbp net=%.2fbp sigex=%.2f edge=%.2f%% lc4=%s",
                h * 4,
                res.get("n_trades", 0),
                res.get("obs_mean_gross_bp", 0),
                res.get("obs_mean_net_bp", 0),
                res.get("signal_t_excess") if res.get("signal_t_excess") is not None else -999,
                res.get("life_changing_4dim", {}).get("per_trade_edge_pct", 0),
                res.get("life_changing_4dim", {}).get("pass_all_4_dim"),
            )
        except Exception as e:
            log.warning("hold sweep h=%d fail: %s", h, e)

    out["hold_sweep_A_focus"] = sweep_results

    # Lesson #37 sweep verdict scan
    sweep_full_pass_cells = []
    sweep_narrow_scope_cells = []
    for res in sweep_results:
        g3 = res.get("gate_3_pass", False)
        gc = res.get("gate_concentration_pass", False)
        lc = res.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
        edge_pass = res.get("life_changing_4dim", {}).get("pass_edge_2pct", False)
        if g3 and gc and lc:
            sweep_full_pass_cells.append({
                "cell": res.get("quadrant"),
                "hold_hours": res.get("hold_hours"),
                "net_bp": res.get("obs_mean_net_bp"),
                "edge_pct": res.get("life_changing_4dim", {}).get("per_trade_edge_pct"),
                "trades_per_year": res.get("life_changing_4dim", {}).get("trades_per_year"),
            })
        elif g3 and gc and edge_pass and not lc:
            sweep_narrow_scope_cells.append({
                "cell": res.get("quadrant"),
                "hold_hours": res.get("hold_hours"),
                "net_bp": res.get("obs_mean_net_bp"),
                "edge_pct": res.get("life_changing_4dim", {}).get("per_trade_edge_pct"),
                "trades_per_year": res.get("life_changing_4dim", {}).get("trades_per_year"),
                "fail_dims": [
                    k for k, v in res.get("life_changing_4dim", {}).items()
                    if k.startswith("pass_") and not v
                ],
            })

    # Scan all 4 quadrants @ primary hold too (full coverage, not only A_focus)
    for qname, q in quadrants_primary.items():
        g3 = q.get("gate_3_pass", False)
        gc = q.get("gate_concentration_pass", False)
        lc = q.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
        edge_pass = q.get("life_changing_4dim", {}).get("pass_edge_2pct", False)
        if g3 and gc and lc:
            sweep_full_pass_cells.append({
                "cell": qname + "_h4",
                "hold_hours": 4,
                "net_bp": q.get("obs_mean_net_bp"),
                "edge_pct": q.get("life_changing_4dim", {}).get("per_trade_edge_pct"),
                "trades_per_year": q.get("life_changing_4dim", {}).get("trades_per_year"),
            })
        elif g3 and gc and edge_pass and not lc:
            sweep_narrow_scope_cells.append({
                "cell": qname + "_h4",
                "hold_hours": 4,
                "net_bp": q.get("obs_mean_net_bp"),
                "edge_pct": q.get("life_changing_4dim", {}).get("per_trade_edge_pct"),
                "trades_per_year": q.get("life_changing_4dim", {}).get("trades_per_year"),
                "fail_dims": [
                    k for k, v in q.get("life_changing_4dim", {}).items()
                    if k.startswith("pass_") and not v
                ],
            })

    out["lesson37_sweep_scan"] = {
        "n_full_pass_cells": len(sweep_full_pass_cells),
        "n_narrow_scope_edge_pass_cells": len(sweep_narrow_scope_cells),
        "full_pass_cells": sweep_full_pass_cells,
        "narrow_scope_edge_pass_cells": sweep_narrow_scope_cells,
    }

    # ─── Verdict ──────────────────────────────────────────────────────────
    n_three_gate_pass_total = 0
    n_quadrants_negative_gross = 0
    n_quadrants_total = 0
    max_quadrant_gross_any = -np.inf
    a_focus = quadrants_primary["A_focus_high_anchor_SHORT"]
    a_focus_gross = a_focus.get("obs_mean_gross_bp", -np.inf)
    a_focus_obs_t = a_focus.get("obs_t", 0.0)

    for qname, q in quadrants_primary.items():
        n_quadrants_total += 1
        g = q.get("obs_mean_gross_bp", 0.0)
        if g < 0:
            n_quadrants_negative_gross += 1
        if g > max_quadrant_gross_any:
            max_quadrant_gross_any = g
        if q.get("gate_3_pass"):
            n_three_gate_pass_total += 1

    out["a_focus_gross_bp"] = float(a_focus_gross) if a_focus_gross != -np.inf else None
    out["max_quadrant_gross_any_bp"] = float(max_quadrant_gross_any) if max_quadrant_gross_any != -np.inf else None
    out["n_three_gate_pass_total"] = n_three_gate_pass_total
    out["n_quadrants_total"] = n_quadrants_total
    out["n_quadrants_negative_gross"] = n_quadrants_negative_gross

    if sweep_full_pass_cells:
        verdict = "PASS_R1_FULL"
        verdict_reason = (
            f"Cell(s) {[c['cell'] for c in sweep_full_pass_cells]} achieved "
            f"3-gate + Concentration + life-changing 4-dim. 24h high anchor reversal "
            f"mechanism viable at 4h subspace — paradigm 117 4h B_same precedent strengthened."
        )
        next_action = "propose_R2_user_approval"
    elif sweep_narrow_scope_cells:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = (
            f"Cell(s) {[c['cell'] for c in sweep_narrow_scope_cells]} PASS 3-gate + "
            f"Concentration + edge≥2% BUT other lc dim fail."
        )
        next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL_graveyard"
    else:
        if n_quadrants_total > 0 and n_quadrants_negative_gross == n_quadrants_total:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                f"All {n_quadrants_total} quadrants non-positive gross. "
                f"24h high anchor reversal hypothesis falsified at 4h scale. "
                f"Lesson #56 OUTCOME-LEVEL FAMILY PROXY 14th instance (magnitude-event family)."
            )
        elif a_focus_gross < 0 and a_focus_obs_t < -1.5:
            verdict = "BROAD_FALSIFIED_DIRECTION_INVERTED"
            verdict_reason = (
                f"A_focus high_anchor × SHORT (hypothesis cell) gross {a_focus_gross:.2f}bp "
                f"obs_t {a_focus_obs_t:.2f} significantly negative — 24h new high event "
                f"triggers UP continuation (breakout follow-through), not reversal. "
                f"A_mirror high_anchor × LONG may be alpha-bearing requires verification."
            )
        elif max_quadrant_gross_any > 0 and max_quadrant_gross_any < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"Best gross across quadrants {max_quadrant_gross_any:.2f}bp < 16bp "
                f"round-trip fee floor at 4h hold. Anchor reversal mechanism has weak "
                f"directional bias but sub-fee."
            )
        else:
            verdict = "BROAD_FALSIFIED_NO_THREE_GATE"
            verdict_reason = (
                f"No quadrant cleared 3-gate. Max quadrant gross {max_quadrant_gross_any:.2f}bp. "
                f"Noisy or absent directional alpha at 4h scale."
            )
        next_action = "graveyard"

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["next_action_recommendation"] = next_action
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    _write(out)

    log.info("=" * 70)
    log.info("VERDICT: %s", verdict)
    log.info("REASON: %s", verdict_reason)
    log.info(
        "A_focus gross %.2fbp obs_t %.2f | max-quadrant gross any: %.2fbp",
        a_focus_gross if a_focus_gross != -np.inf else 0,
        a_focus_obs_t,
        max_quadrant_gross_any if max_quadrant_gross_any != -np.inf else 0,
    )
    log.info(
        "Total 3-gate quadrants pass: %d / %d total | broad falsified: %d",
        n_three_gate_pass_total, n_quadrants_total, n_quadrants_negative_gross,
    )
    log.info(
        "Sweep full-pass cells: %d, narrow-scope edge-pass: %d",
        len(sweep_full_pass_cells), len(sweep_narrow_scope_cells),
    )
    log.info("Wall clock: %.2f min", out["wall_clock_minutes"])
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
