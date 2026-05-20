"""Paradigm 117 — alt_extreme_24h_drawdown_reversal_long_4h R-1 PoC

Pivot context
-------------
Predecessor paradigm 114→115→116→115_R2 chain confirmed the
`level-crossing + vol-conditioning + axis-stacking` mechanism class is
real but NARROW_SCOPE_LIFE_CHANGING_FAIL (4th dogfood: edge<2%/trade
hard-block per [[feedback-life-changing-strategy-criterion]]).

PIVOT REQUIRED: sparse event-driven mechanism with ≥2%/trade expected
edge — the lifecycle paradigm shape (Day-1 listing short was the
existing PASS case at median +21.6%/trade).

Hypothesis
----------
Pure mean-reversion on extreme drawdown event. When an alt's rolling
24h cumulative log return drops below −15% (capitulation territory),
4h forward LONG continuation shows mean-reversion bounce.

Trigger rate (~2-5% of bars per alt) → rare event → high expected
per-event edge consistent with life-changing 4-dim PASS threshold.

5-axis novelty self-check vs paradigm 65 (skewness_mr) and paradigm 63
(cross_sec_weekly_mr)
  - Statistic = 24h rolling cumulative log return ≤ −15% threshold
    (NOVEL — magnitude-event threshold, not 3rd moment, not cross-sec
    rank)
  - Universe = ~28 alts (13 + 15 expansion after MATICUSDT drop);
    slight novelty vs 13-alt fixed
  - Frame = 24h trigger window × 4h hold (NOVEL combination)
  - Mechanism = extreme drawdown capitulation mean-reversion (NOVEL)
  - Trigger = single-threshold rolling 24h return (NOT NOVEL — single-axis)
  Verdict: 4/5 NOVEL — proceed.

Lesson prescreens (with empirical debounce)
  - #11 sample density: COMPUTED via actual debounce (≥24h gap between
    consecutive triggers per sym). Skip threshold if debounced per-
    (quadrant × quarter) cell < 30.
  - #19 SNT: 4-quadrant in single batch per threshold.
  - #20 narrow-scope: handled in verdict tree.
  - #27 entry immediate: drawdown observable in real-time → entry next
    bar open.
  - #28 substrate: 1h OHLCV verified (MATICUSDT dropped: 3202/17520 rows).
  - #34 empirical distribution: measured + logged.
  - #35 fee floor: target ≥2%/trade = 200bp ≫ 16bp.
  - #37 sweep verdict scan: full hold sweep cell scan for narrow-scope.
  - #39 symmetric mirror antipattern: A_focus vs A_mirror diagnostic.

Scope
  - 28 alts (13 core + 15 expansion; MATICUSDT excluded for data gap).
  - 24 months 2024-05..2026-04 from existing caches.

Verdict tree (post-pivot edge≥2%/trade PRIMARY hard-block)
  PASS_R1_FULL                     : any cell 3-gate + Conc + lc4 (edge≥2%)
  NARROW_SCOPE_LIFE_CHANGING_FAIL  : 3-gate + Conc + edge≥2% but other lc dim fail
  BROAD_FALSIFIED_DIRECTION_INVERTED: A_focus gross significantly negative
  BROAD_FALSIFIED_FEE_FLOOR        : A_focus gross 0<g<16bp net sub-fee
  BROAD_FALSIFIED                  : all 4 quadrants × thresholds ≤0 gross
  CONCENTRATED_OR_FEE_BOUND_FAIL   : 3-gate PASS but Conc/lc fail
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

PARADIGM_SLUG = "alt_extreme_24h_drawdown_reversal_long_4h"
PARADIGM_NUMBER = 117
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_SLUG
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORE_CACHE_DIR = (
    ROOT
    / "runs"
    / "research_track"
    / "intraday_hour_of_day_anchor_alt_directional_2h"
    / "klines_cache"
)
EXPANSION_CACHE_DIR = (
    ROOT
    / "runs"
    / "research_track"
    / "alt_atr_normalized_range_breakout_continuation_long_2h"
    / "klines_cache_r2_expansion"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(OUT_DIR / "r1__stdout.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p117_r1")

ALTS_CORE = [
    "SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "LINKUSDT",
    "ADAUSDT", "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT",
    "NEARUSDT", "XRPUSDT", "ETHUSDT",
]
ALTS_EXPANSION = [
    "1000PEPEUSDT", "1000SHIBUSDT", "AAVEUSDT", "APTUSDT", "ARBUSDT",
    "ATOMUSDT", "DOTUSDT", "ICPUSDT", "INJUSDT",
    # "MATICUSDT" — excluded due to data gap (3202/17520 rows)
    "OPUSDT", "SEIUSDT", "SUIUSDT", "TIAUSDT", "TRXUSDT", "UNIUSDT",
]
ALTS = ALTS_CORE + ALTS_EXPANSION  # 28

START_MONTH = "2024-05"
END_MONTH = "2026-04"

FEE_PER_TRADE = 0.0008  # 16 bp round-trip
ROLLING_24H_BARS = 24
DEBOUNCE_BARS = 24  # require ≥24h between consecutive triggers per sym

PRIMARY_THRESHOLD = -0.15  # −15% 24h cumulative log return primary
THRESHOLD_SWEEP = [-0.10, -0.15, -0.20, -0.25]  # negative drawdown levels

PRIMARY_HOLD_BARS = 4  # 4h primary
HOLD_SWEEP_BARS = [1, 4, 12, 24]


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def load_1h_klines_from_cache(sym: str, month: str) -> pd.DataFrame:
    """Try core cache first, fall back to expansion cache."""
    for cdir in (CORE_CACHE_DIR, EXPANSION_CACHE_DIR):
        cache_file = cdir / f"{sym}_1h_{month}.joblib"
        if cache_file.exists():
            try:
                return joblib.load(cache_file)
            except Exception as e:
                log.warning("cache load fail %s %s @ %s: %s", sym, month, cdir.name, e)
                return pd.DataFrame()
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


def compute_debounced_count(mask_per_sym: dict[str, pd.Series], debounce_bars: int) -> int:
    """Return the total debounced trigger count across syms (≥debounce_bars gap)."""
    total = 0
    min_gap = pd.Timedelta(hours=debounce_bars)
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
    """4-gate (3-gate + Concentration + per-sym CI + life-changing)."""
    trades_per_sym: dict[str, list[float]] = {s: [] for s in trigger_mask_per_sym}
    ts_per_sym: dict[str, list[pd.Timestamp]] = {s: [] for s in trigger_mask_per_sym}

    for s, mask in trigger_mask_per_sym.items():
        fwd = fwd_per_sym.get(s)
        d = direction_per_sym[s]
        if fwd is None or len(fwd) == 0:
            continue
        idx_trig = mask.index[mask.fillna(False) & fwd.notna()]
        if len(idx_trig) == 0:
            continue
        min_gap = pd.Timedelta(hours=debounce_bars)
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
        "pass_edge_only_primary_block": bool(per_trade_edge_pct >= 2.0),
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
        "pivot_context": (
            "post paradigm 114→115→116→115_R2 level-crossing class "
            "NARROW_SCOPE_LIFE_CHANGING_FAIL 4th dogfood — pivoted to "
            "sparse event-driven extreme drawdown reversion"
        ),
        "universe_alts_core": ALTS_CORE,
        "universe_alts_expansion": ALTS_EXPANSION,
        "n_alts_total": len(ALTS),
        "window_months": [START_MONTH, END_MONTH],
        "fee_per_trade": FEE_PER_TRADE,
        "rolling_24h_bars": ROLLING_24H_BARS,
        "debounce_bars": DEBOUNCE_BARS,
        "primary_threshold": PRIMARY_THRESHOLD,
        "threshold_sweep": THRESHOLD_SWEEP,
        "primary_hold_bars": PRIMARY_HOLD_BARS,
        "primary_hold_hours": PRIMARY_HOLD_BARS,
        "hold_sweep_bars": HOLD_SWEEP_BARS,
        "novelty_self_check": {
            "statistic": "NOVEL (24h cumulative return ≤ −15% magnitude event)",
            "universe": "SLIGHTLY NOVEL (28-alt = 13 core + 15 expansion; MATIC dropped)",
            "frame": "NOVEL (24h rolling × 4h hold)",
            "mechanism": "NOVEL (capitulation mean-reversion event-driven)",
            "trigger": "NOT NOVEL (single-axis threshold)",
            "axes_pass": 4,
            "verdict": "4/5 NOVEL — proceed",
        },
        "substrate_source": (
            "paradigm113_klines_cache + paradigm115_r2_expansion "
            "(28-alt 1h × 24 months pure OHLCV)"
        ),
    }

    months = month_iter(START_MONTH, END_MONTH)
    log.info(
        "loading 1h klines for %d alts × %d months from cache (core+expansion)",
        len(ALTS), len(months),
    )
    t_bf = time.time()
    panel: dict[str, pd.DataFrame] = {}
    for s in ALTS:
        df = build_1h_panel(s, months)
        if df.empty:
            log.warning("  %s: empty — drop", s)
            continue
        if len(df) < 17000:
            log.warning("  %s: only %d rows (<17000) — drop", s, len(df))
            continue
        panel[s] = df
    bf_secs = time.time() - t_bf
    log.info("cache load done in %.1fs (%d/%d syms usable)", bf_secs, len(panel), len(ALTS))

    if len(panel) < 8:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = f"cache load produced only {len(panel)}/{len(ALTS)} usable series"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    out["n_alts_usable"] = len(panel)
    out["alts_usable"] = sorted(panel.keys())

    # Build per-sym close + 24h log return + forward returns
    close_per_sym: dict[str, pd.Series] = {}
    ret24h_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].astype(float).copy()
        close_per_sym[s] = c
        ret24h_per_sym[s] = np.log(c / c.shift(ROLLING_24H_BARS))

    fwd_per_sym_by_hold: dict[int, dict[str, pd.Series]] = {}
    for h in HOLD_SWEEP_BARS:
        d = {}
        for s, c in close_per_sym.items():
            d[s] = np.log(c.shift(-h) / c)
        fwd_per_sym_by_hold[h] = d

    fwd_primary = fwd_per_sym_by_hold[PRIMARY_HOLD_BARS]
    pool_long_primary = (
        np.concatenate([f.dropna().values for f in fwd_primary.values()])
        if fwd_primary
        else np.array([])
    )
    pool_short_primary = -pool_long_primary

    dir_long = {s: +1 for s in panel}
    dir_short = {s: -1 for s in panel}

    # Lesson #34 empirical distribution
    ret24h_all = np.concatenate(
        [v.dropna().values for v in ret24h_per_sym.values()]
    )
    out["lesson34_empirical_24h_return_distribution"] = {
        "n_obs": int(len(ret24h_all)),
        "p01_pct": float(np.percentile(ret24h_all, 1) * 100),
        "p05_pct": float(np.percentile(ret24h_all, 5) * 100),
        "p10_pct": float(np.percentile(ret24h_all, 10) * 100),
        "p50_pct": float(np.percentile(ret24h_all, 50) * 100),
        "p90_pct": float(np.percentile(ret24h_all, 90) * 100),
        "p99_pct": float(np.percentile(ret24h_all, 99) * 100),
        "min_pct": float(ret24h_all.min() * 100),
        "max_pct": float(ret24h_all.max() * 100),
        "frac_below_neg10_pct": float((ret24h_all <= -0.10).mean() * 100),
        "frac_below_neg15_pct": float((ret24h_all <= -0.15).mean() * 100),
        "frac_below_neg20_pct": float((ret24h_all <= -0.20).mean() * 100),
        "frac_below_neg25_pct": float((ret24h_all <= -0.25).mean() * 100),
        "frac_above_pos10_pct": float((ret24h_all >= 0.10).mean() * 100),
        "frac_above_pos15_pct": float((ret24h_all >= 0.15).mean() * 100),
        "frac_above_pos20_pct": float((ret24h_all >= 0.20).mean() * 100),
        "frac_above_pos25_pct": float((ret24h_all >= 0.25).mean() * 100),
    }
    log.info(
        "empirical 24h log-return distribution: p01=%.2f%% p05=%.2f%% p99=%.2f%% min=%.2f%% max=%.2f%%",
        out["lesson34_empirical_24h_return_distribution"]["p01_pct"],
        out["lesson34_empirical_24h_return_distribution"]["p05_pct"],
        out["lesson34_empirical_24h_return_distribution"]["p99_pct"],
        out["lesson34_empirical_24h_return_distribution"]["min_pct"],
        out["lesson34_empirical_24h_return_distribution"]["max_pct"],
    )

    # Per-threshold pre-compute: raw + debounced counts (Lesson #11 with REAL debounce)
    n_bars_total = sum(int(close_per_sym[s].notna().sum()) for s in panel)
    empirical_per_th = {}
    masks_per_th: dict[float, dict] = {}
    for th in THRESHOLD_SWEEP:
        dn_mask_per_sym: dict[str, pd.Series] = {}
        up_mask_per_sym: dict[str, pd.Series] = {}
        for s in panel:
            r = ret24h_per_sym[s]
            dn_mask_per_sym[s] = (r <= th) & r.notna()
            up_mask_per_sym[s] = (r >= -th) & r.notna()
        n_raw_dn = int(sum(m.sum() for m in dn_mask_per_sym.values()))
        n_raw_up = int(sum(m.sum() for m in up_mask_per_sym.values()))
        n_deb_dn = compute_debounced_count(dn_mask_per_sym, DEBOUNCE_BARS)
        n_deb_up = compute_debounced_count(up_mask_per_sym, DEBOUNCE_BARS)

        masks_per_th[th] = {"dn": dn_mask_per_sym, "up": up_mask_per_sym}

        # all_ts_idx
        all_ts_idx = pd.concat([s for s in close_per_sym.values()], axis=1).index
        n_quarters = max(
            1, int(np.ceil((all_ts_idx.max() - all_ts_idx.min()).days / 91))
        )
        per_q_dn = n_deb_dn / n_quarters
        per_q_up = n_deb_up / n_quarters

        empirical_per_th[f"th_{th}"] = {
            "threshold": float(th),
            "n_raw_drawdown": n_raw_dn,
            "n_raw_pump": n_raw_up,
            "n_debounced_drawdown": n_deb_dn,
            "n_debounced_pump": n_deb_up,
            "raw_drawdown_rate_pct": float(100 * n_raw_dn / max(1, n_bars_total)),
            "raw_pump_rate_pct": float(100 * n_raw_up / max(1, n_bars_total)),
            "debounced_drawdown_per_quarter": float(per_q_dn),
            "debounced_pump_per_quarter": float(per_q_up),
            "n_quarters": int(n_quarters),
        }
        log.info(
            "threshold=%.0f%%: raw_dn=%d (%.3f%%) deb_dn=%d (%.1f/quarter) | raw_up=%d (%.3f%%) deb_up=%d (%.1f/quarter)",
            th * 100, n_raw_dn,
            empirical_per_th[f"th_{th}"]["raw_drawdown_rate_pct"],
            n_deb_dn, per_q_dn,
            n_raw_up,
            empirical_per_th[f"th_{th}"]["raw_pump_rate_pct"],
            n_deb_up, per_q_up,
        )
    out["lesson34_empirical_per_threshold"] = empirical_per_th

    # Per-threshold 4-quadrant SNT at primary hold
    per_th_results: dict = {}
    for th in THRESHOLD_SWEEP:
        log.info("=== threshold = %.0f%% (4-quadrant SNT @ hold=%dh) ===",
                 th * 100, PRIMARY_HOLD_BARS)
        emp = empirical_per_th[f"th_{th}"]
        per_th_results[f"th_{th}"] = {
            "threshold": float(th),
            "n_debounced_drawdown": emp["n_debounced_drawdown"],
            "n_debounced_pump": emp["n_debounced_pump"],
            "debounced_drawdown_per_quarter": emp["debounced_drawdown_per_quarter"],
            "debounced_pump_per_quarter": emp["debounced_pump_per_quarter"],
            "lesson11_drawdown_pass": bool(emp["debounced_drawdown_per_quarter"] >= 30),
            "lesson11_pump_pass": bool(emp["debounced_pump_per_quarter"] >= 30),
        }

        if not per_th_results[f"th_{th}"]["lesson11_drawdown_pass"]:
            log.warning(
                "threshold=%.0f%% Lesson #11 SKIP — debounced drawdown %.1f/quarter < 30",
                th * 100, emp["debounced_drawdown_per_quarter"],
            )
            per_th_results[f"th_{th}"]["skip_reason"] = "lesson11_sample_density_fail_drawdown"
            continue

        dn_mask_per_sym = masks_per_th[th]["dn"]
        up_mask_per_sym = masks_per_th[th]["up"]

        # 4-quadrant SNT
        quadrants = {}
        quadrants["A_focus_drawdown_LONG"] = compute_quadrant(
            f"A_focus_drawdown_LONG_th{th}",
            dn_mask_per_sym,
            fwd_primary,
            dir_long,
            PRIMARY_HOLD_BARS,
            DEBOUNCE_BARS,
            FEE_PER_TRADE,
            pool_long_primary,
        )
        quadrants["A_mirror_drawdown_SHORT"] = compute_quadrant(
            f"A_mirror_drawdown_SHORT_th{th}",
            dn_mask_per_sym,
            fwd_primary,
            dir_short,
            PRIMARY_HOLD_BARS,
            DEBOUNCE_BARS,
            FEE_PER_TRADE,
            pool_short_primary,
        )
        if per_th_results[f"th_{th}"]["lesson11_pump_pass"]:
            quadrants["B_same_sign_pump_SHORT"] = compute_quadrant(
                f"B_same_sign_pump_SHORT_th{th}",
                up_mask_per_sym,
                fwd_primary,
                dir_short,
                PRIMARY_HOLD_BARS,
                DEBOUNCE_BARS,
                FEE_PER_TRADE,
                pool_short_primary,
            )
            quadrants["B_mirror_pump_LONG"] = compute_quadrant(
                f"B_mirror_pump_LONG_th{th}",
                up_mask_per_sym,
                fwd_primary,
                dir_long,
                PRIMARY_HOLD_BARS,
                DEBOUNCE_BARS,
                FEE_PER_TRADE,
                pool_long_primary,
            )
        per_th_results[f"th_{th}"]["quadrants"] = quadrants

        # Lesson #39 symmetric mirror diagnostic
        a_focus_gross = quadrants["A_focus_drawdown_LONG"].get("obs_mean_gross_bp", 0.0)
        a_mirror_gross = quadrants["A_mirror_drawdown_SHORT"].get("obs_mean_gross_bp", 0.0)
        sum_abs_mirror = abs(a_focus_gross + a_mirror_gross)
        per_th_results[f"th_{th}"]["lesson39_symmetry"] = {
            "A_focus_gross_bp": a_focus_gross,
            "A_mirror_gross_bp": a_mirror_gross,
            "sum_abs_bp": float(sum_abs_mirror),
            "is_perfect_mirror": bool(sum_abs_mirror < 1.0),
        }

        # Log summary
        a = quadrants["A_focus_drawdown_LONG"]
        log.info(
            "  A_focus n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci=[%.2f,%.2f] 3gate=%s conc=%s edge=%.2f%% trades/yr=%.0f lc4=%s",
            a.get("n_trades", 0),
            a.get("obs_mean_gross_bp", 0),
            a.get("obs_mean_net_bp", 0),
            a.get("signal_t_excess", float("nan")) if a.get("signal_t_excess") is not None and not (isinstance(a.get("signal_t_excess"), float) and np.isnan(a.get("signal_t_excess"))) else -999,
            a.get("ci_lower_bp", 0),
            a.get("ci_upper_bp", 0),
            a.get("gate_3_pass"),
            a.get("gate_concentration_pass"),
            a.get("life_changing_4dim", {}).get("per_trade_edge_pct", 0),
            a.get("life_changing_4dim", {}).get("trades_per_year", 0),
            a.get("life_changing_4dim", {}).get("pass_all_4_dim"),
        )

    out["per_threshold_results"] = per_th_results

    # Hold sweep on PRIMARY threshold A_focus
    primary_key = f"th_{PRIMARY_THRESHOLD}"
    sweep_results = []
    if primary_key in per_th_results and "skip_reason" not in per_th_results[primary_key]:
        log.info("=== hold sweep on primary threshold %.0f%% A_focus_drawdown_LONG ===",
                 PRIMARY_THRESHOLD * 100)
        dn_mask_primary = masks_per_th[PRIMARY_THRESHOLD]["dn"]

        for h in HOLD_SWEEP_BARS:
            if h == PRIMARY_HOLD_BARS:
                primary_quadrant = per_th_results[primary_key]["quadrants"]["A_focus_drawdown_LONG"]
                sweep_results.append({**primary_quadrant, "is_primary_hold": True})
                continue
            fwd_h = fwd_per_sym_by_hold[h]
            pool_h = np.concatenate([f.dropna().values for f in fwd_h.values()])
            try:
                res = compute_quadrant(
                    f"A_focus_drawdown_LONG_th{PRIMARY_THRESHOLD}_h{h}",
                    dn_mask_primary,
                    fwd_h,
                    dir_long,
                    h,
                    DEBOUNCE_BARS,
                    FEE_PER_TRADE,
                    pool_h,
                )
                res["is_primary_hold"] = False
                sweep_results.append(res)
                log.info(
                    "  hold=%dh n=%d gross=%.2fbp net=%.2fbp sigex=%.2f edge=%.2f%% lc4=%s",
                    h,
                    res.get("n_trades", 0),
                    res.get("obs_mean_gross_bp", 0),
                    res.get("obs_mean_net_bp", 0),
                    res.get("signal_t_excess", -999) if res.get("signal_t_excess") is not None and not (isinstance(res.get("signal_t_excess"), float) and np.isnan(res.get("signal_t_excess"))) else -999,
                    res.get("life_changing_4dim", {}).get("per_trade_edge_pct", 0),
                    res.get("life_changing_4dim", {}).get("pass_all_4_dim"),
                )
            except Exception as e:
                log.warning("hold sweep h=%d fail: %s", h, e)

    out["hold_sweep_primary_threshold_A_focus"] = sweep_results

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

    out["lesson37_sweep_scan"] = {
        "n_full_pass_cells": len(sweep_full_pass_cells),
        "n_narrow_scope_edge_pass_cells": len(sweep_narrow_scope_cells),
        "full_pass_cells": sweep_full_pass_cells,
        "narrow_scope_edge_pass_cells": sweep_narrow_scope_cells,
    }

    # ─── Verdict ──────────────────────────────────────────────────────────
    best_th = None
    best_focus_gross = -np.inf  # signed max
    best_focus_gross_abs = 0.0
    any_full_pass_th = None
    any_narrow_scope_th = None
    n_three_gate_pass_total = 0
    n_quadrants_negative_gross = 0
    n_quadrants_total = 0
    max_quadrant_gross_any = -np.inf

    for th in THRESHOLD_SWEEP:
        key = f"th_{th}"
        if "skip_reason" in per_th_results.get(key, {}):
            continue
        quadrants = per_th_results[key].get("quadrants", {})
        for qname, q in quadrants.items():
            n_quadrants_total += 1
            g = q.get("obs_mean_gross_bp", 0.0)
            if g < 0:
                n_quadrants_negative_gross += 1
            if g > max_quadrant_gross_any:
                max_quadrant_gross_any = g
            if q.get("gate_3_pass"):
                n_three_gate_pass_total += 1
        A_focus = quadrants.get("A_focus_drawdown_LONG", {})
        ag = A_focus.get("obs_mean_gross_bp", -np.inf)
        if ag > best_focus_gross:
            best_focus_gross = ag
            best_th = th
        a_g3 = A_focus.get("gate_3_pass", False)
        a_gc = A_focus.get("gate_concentration_pass", False)
        a_lc = A_focus.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
        a_edge_pass = A_focus.get("life_changing_4dim", {}).get("pass_edge_2pct", False)
        if a_g3 and a_gc and a_lc:
            any_full_pass_th = th
        elif a_g3 and a_gc and a_edge_pass and not a_lc:
            any_narrow_scope_th = th

    if sweep_full_pass_cells:
        any_full_pass_th = any_full_pass_th if any_full_pass_th is not None else "from_sweep"
    if sweep_narrow_scope_cells and any_narrow_scope_th is None:
        any_narrow_scope_th = "from_sweep"

    out["best_threshold"] = best_th
    out["best_focus_gross_bp"] = float(best_focus_gross) if best_focus_gross != -np.inf else None
    out["max_quadrant_gross_any_bp"] = float(max_quadrant_gross_any) if max_quadrant_gross_any != -np.inf else None
    out["n_three_gate_pass_total"] = n_three_gate_pass_total
    out["n_quadrants_total"] = n_quadrants_total
    out["n_quadrants_negative_gross"] = n_quadrants_negative_gross

    if any_full_pass_th is not None:
        verdict = "PASS_R1_FULL"
        verdict_reason = (
            f"At threshold={any_full_pass_th}, A_focus drawdown→LONG (or "
            f"hold-sweep cell) PASS 3-gate + Concentration + life-changing "
            f"4-dim (edge≥2%/trade hard-block satisfied). Capitulation "
            f"mean-reversion mechanism viable."
        )
        next_action = "propose_R2_user_approval"
    elif any_narrow_scope_th is not None:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = (
            f"At threshold={any_narrow_scope_th}, A_focus PASS 3-gate + "
            f"Concentration + edge≥2% BUT other life-changing dims fail. "
            f"5th NARROW_SCOPE_LIFE_CHANGING_FAIL dogfood."
        )
        next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL_graveyard"
    else:
        # Triage: direction inversion vs broad falsified vs fee floor
        a_focus_gross_at_best = best_focus_gross if best_focus_gross != -np.inf else 0.0
        # Inspect best primary A_focus directly
        best_key = f"th_{best_th}" if best_th is not None else None
        a_focus_at_best = (
            per_th_results.get(best_key, {}).get("quadrants", {}).get("A_focus_drawdown_LONG", {})
            if best_key else {}
        )
        a_focus_obs_t = a_focus_at_best.get("obs_t", 0.0)
        a_focus_ci_upper = a_focus_at_best.get("ci_upper_bp", 0.0)

        # All quadrants gross
        if n_quadrants_total > 0 and n_quadrants_negative_gross == n_quadrants_total:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                f"All {n_quadrants_total} quadrants × thresholds produced "
                f"non-positive gross mean. Capitulation does NOT mean-revert "
                f"in 4h; if anything continuation dominates (best A_focus "
                f"drawdown→LONG gross {a_focus_gross_at_best:.2f}bp). "
                f"Mean-reversion bounce hypothesis falsified at this hold scale."
            )
        elif a_focus_gross_at_best < 0 and a_focus_obs_t < -1.5:
            # A_focus is the hypothesis-relevant direction; significantly negative
            verdict = "BROAD_FALSIFIED_DIRECTION_INVERTED"
            verdict_reason = (
                f"A_focus drawdown→LONG (the hypothesis cell) gross "
                f"{a_focus_gross_at_best:.2f}bp obs_t {a_focus_obs_t:.2f} — "
                f"significantly negative. Capitulation continues (momentum "
                f"continuation in alts) rather than reverting. The MIRROR "
                f"direction (A_mirror drawdown→SHORT) is the directionally "
                f"correct side, but cross-fee viability requires separate "
                f"verification."
            )
        elif max_quadrant_gross_any > 0 and max_quadrant_gross_any < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"Best gross across quadrants {max_quadrant_gross_any:.2f}bp "
                f"< 16bp fee floor. Mechanism may have weak directional bias "
                f"but does not clear round-trip fee in 4h hold."
            )
        else:
            verdict = "BROAD_FALSIFIED_NO_THREE_GATE"
            verdict_reason = (
                f"No quadrant cleared 3-gate (signal_t_excess≥2 + CI_lower>0 "
                f"+ perm_p≤0.10). Max quadrant gross {max_quadrant_gross_any:.2f}bp. "
                f"Noisy or absent directional alpha."
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
        "Best threshold: %s @ A_focus gross %.2f bp | max-quadrant gross any: %.2f bp",
        best_th,
        best_focus_gross if best_focus_gross != -np.inf else 0,
        max_quadrant_gross_any if max_quadrant_gross_any != -np.inf else 0,
    )
    log.info("Total 3-gate quadrants pass: %d / %d quadrants total",
             n_three_gate_pass_total, n_quadrants_total)
    log.info("Sweep full-pass cells: %d, narrow-scope edge-pass: %d",
             len(sweep_full_pass_cells), len(sweep_narrow_scope_cells))
    log.info("Wall clock: %.2f min", out["wall_clock_minutes"])
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
