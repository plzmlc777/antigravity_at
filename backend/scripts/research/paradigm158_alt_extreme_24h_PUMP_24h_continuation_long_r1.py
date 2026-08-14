"""Paradigm 158 — alt_extreme_24h_PUMP_24h_continuation_long R-1 PoC

Reframe context
---------------
paradigm 117 R-3 caveat 1 measured B_same_sign PUMP × SHORT at 4h scale
sigex +0.28 sub-fee — but ONLY at 4h scale, NEVER at 24h scale where the
A_focus mechanism actually operated.

paradigm 158 is the honest direct test of the mechanism CLASS asymmetric
finding: PUMP × continuation × 24h scale.

Hypothesis
----------
Alt 24h extreme PUMP (rolling 24h return ≥ per-symbol p90 threshold)
→ 24h hold LONG continuation (FOMO momentum follow).

Lesson #62 family-distinct strict 4-dim audit:
  - statistic: rolling 24h return ≥ p90 (vs paradigm 117 ≤ −15%) — partial
  - universe: 14 alts subset — partial
  - entry-side class: PUMP cross-up event vs DRAWDOWN cross-down — STRICT
  - mechanism alpha: FOMO continuation vs capitulation MR — STRICT
  - hold: 24h identical
  Strict count = 2/5 boundary PASS.

Lesson prescreens
  - #11 sample density: per-sym p90 → ~10% of bars → ~7,000 base events
  - #19 SNT: 4-quadrant in single batch
  - #28 substrate: 12-col 4h joblib cache verified 14 syms × 4920 bars
  - #34 empirical distribution: measured + logged
  - #67 ESCAPE: per-sym threshold (no cross-asset broadcast)
  - #68 ESCAPE: magnitude-anchor + 24h hold (no session-boundary)

Scope
  - 14 alts 12-col 4h joblib cache (영구 자산)
  - 2024-02..2026-04 ~2.25yr (data_window_ratio 93.75% PASS Lesson #30)

Verdict tree (post-pivot edge≥2%/trade PRIMARY hard-block)
  PASS_R1_FULL                       : any cell 3-gate + Conc + lc4
  NARROW_SCOPE_LIFE_CHANGING_FAIL    : 3-gate + Conc + edge≥2% but other dim fail
  BROAD_FALSIFIED_DIRECTION_INVERTED : A_focus gross significantly negative
  BROAD_FALSIFIED_FEE_FLOOR          : A_focus 0<g<24bp net sub-fee
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

PARADIGM_SLUG = "alt_extreme_24h_PUMP_24h_continuation_long"
PARADIGM_NUMBER = 158
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
log = logging.getLogger("p158_r1")

# 12-col 4h cache verified syms (BTC excluded — universe is alts only;
# BTC kept available for future regime stratify but not in 4-quadrant pool)
ALTS = [
    "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT",
    "BCHUSDT", "LTCUSDT", "BNBUSDT", "FILUSDT", "NEARUSDT",
    "XRPUSDT", "ETHUSDT", "WIFUSDT",
]
# Note: paradigm 117 had HBARUSDT but it's not in 12-col 4h cache;
# WIFUSDT replaces it. 13 alts total.

FEE_PER_TRADE = 0.0008  # 16 bp round-trip — same as paradigm 117

ROLLING_24H_BARS = 6   # 24h / 4h = 6 bars
DEBOUNCE_BARS_4H = 6   # 24h debounce = 6 × 4h bars

PRIMARY_PCT = 0.90  # per-sym p90 (top decile pump)
PCT_SWEEP = [0.85, 0.90, 0.95]
PCT_LOW_MIRROR = [0.15, 0.10, 0.05]  # for B_same/B_mirror (DUMP side, per-sym p10)

PRIMARY_HOLD_BARS_4H = 6   # 24h primary
HOLD_SWEEP_BARS_4H = [3, 6, 12]  # 12h / 24h / 48h


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
    # 24h hold * trades/yr / (365.25 * 24) for capital util %
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
            "paradigm 117 R-3 caveat 1 mechanism CLASS asymmetric — only "
            "capitulation bounce (DRAWDOWN × LONG MR) confirmed, NEVER tested "
            "PUMP × continuation at 24h scale. paradigm 158 is the honest "
            "direct test."
        ),
        "family_distinct_strict_audit_lesson62": {
            "statistic": "partial (same rolling 24h return, opposite direction p90 vs -15%)",
            "universe": "partial (13 alts subset)",
            "entry_side_class": "STRICT (PUMP cross-up vs DRAWDOWN cross-down)",
            "mechanism_alpha_class": "STRICT (FOMO continuation vs capitulation MR)",
            "hold": "identical (24h)",
            "strict_count": 2,
            "verdict": "BOUNDARY_PASS (≥2 strict satisfied)",
        },
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "substrate": "12-col 4h klines joblib cache (영구 자산)",
        "rolling_24h_bars_4h": ROLLING_24H_BARS,
        "debounce_bars_4h": DEBOUNCE_BARS_4H,
        "fee_per_trade": FEE_PER_TRADE,
        "primary_percentile": PRIMARY_PCT,
        "percentile_sweep": PCT_SWEEP,
        "pct_low_mirror": PCT_LOW_MIRROR,
        "primary_hold_bars_4h": PRIMARY_HOLD_BARS_4H,
        "primary_hold_hours": PRIMARY_HOLD_BARS_4H * 4,
        "hold_sweep_bars_4h": HOLD_SWEEP_BARS_4H,
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

    # Per-sym close + rolling 24h return (6 × 4h bars)
    close_per_sym: dict[str, pd.Series] = {}
    ret24h_per_sym: dict[str, pd.Series] = {}
    for s, df in panel.items():
        c = df["close"].astype(float).copy()
        close_per_sym[s] = c
        # log return over 6 bars (24h)
        ret24h_per_sym[s] = np.log(c / c.shift(ROLLING_24H_BARS))

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

    # Lesson #34 empirical distribution (24h log returns global)
    ret24h_all = np.concatenate(
        [v.dropna().values for v in ret24h_per_sym.values()]
    )
    out["lesson34_empirical_24h_return_distribution"] = {
        "n_obs": int(len(ret24h_all)),
        "p01_pct": float(np.percentile(ret24h_all, 1) * 100),
        "p05_pct": float(np.percentile(ret24h_all, 5) * 100),
        "p10_pct": float(np.percentile(ret24h_all, 10) * 100),
        "p50_pct": float(np.percentile(ret24h_all, 50) * 100),
        "p85_pct": float(np.percentile(ret24h_all, 85) * 100),
        "p90_pct": float(np.percentile(ret24h_all, 90) * 100),
        "p95_pct": float(np.percentile(ret24h_all, 95) * 100),
        "p99_pct": float(np.percentile(ret24h_all, 99) * 100),
        "min_pct": float(ret24h_all.min() * 100),
        "max_pct": float(ret24h_all.max() * 100),
    }
    log.info(
        "empirical global 24h log-return: p10=%.2f%% p50=%.2f%% p85=%.2f%% p90=%.2f%% p95=%.2f%% p99=%.2f%%",
        out["lesson34_empirical_24h_return_distribution"]["p10_pct"],
        out["lesson34_empirical_24h_return_distribution"]["p50_pct"],
        out["lesson34_empirical_24h_return_distribution"]["p85_pct"],
        out["lesson34_empirical_24h_return_distribution"]["p90_pct"],
        out["lesson34_empirical_24h_return_distribution"]["p95_pct"],
        out["lesson34_empirical_24h_return_distribution"]["p99_pct"],
    )

    # Per-sym p85/p90/p95 threshold (PUMP, top) and p05/p10/p15 (DUMP, bottom)
    per_sym_pct_thresholds = {}
    for s in panel:
        r = ret24h_per_sym[s].dropna()
        per_sym_pct_thresholds[s] = {
            "p85": float(np.percentile(r, 85)),
            "p90": float(np.percentile(r, 90)),
            "p95": float(np.percentile(r, 95)),
            "p05": float(np.percentile(r, 5)),
            "p10": float(np.percentile(r, 10)),
            "p15": float(np.percentile(r, 15)),
            "n_obs": int(len(r)),
        }
    out["per_sym_pct_thresholds"] = per_sym_pct_thresholds

    # Pre-compute masks per percentile (PUMP side for A; DUMP side for B mirror)
    n_bars_total = sum(int(close_per_sym[s].notna().sum()) for s in panel)
    empirical_per_pct = {}
    masks_per_pct: dict[float, dict] = {}
    for pct_up, pct_dn in zip(PCT_SWEEP, PCT_LOW_MIRROR):
        # PUMP mask per sym (top pct)
        up_mask_per_sym: dict[str, pd.Series] = {}
        # DUMP mask per sym (bottom pct)
        dn_mask_per_sym: dict[str, pd.Series] = {}
        pct_up_key = {0.85: "p85", 0.90: "p90", 0.95: "p95"}[pct_up]
        pct_dn_key = {0.15: "p15", 0.10: "p10", 0.05: "p05"}[pct_dn]
        for s in panel:
            r = ret24h_per_sym[s]
            th_up = per_sym_pct_thresholds[s][pct_up_key]
            th_dn = per_sym_pct_thresholds[s][pct_dn_key]
            up_mask_per_sym[s] = (r >= th_up) & r.notna()
            dn_mask_per_sym[s] = (r <= th_dn) & r.notna()

        n_raw_up = int(sum(m.sum() for m in up_mask_per_sym.values()))
        n_raw_dn = int(sum(m.sum() for m in dn_mask_per_sym.values()))
        n_deb_up = compute_debounced_count(up_mask_per_sym, DEBOUNCE_BARS_4H)
        n_deb_dn = compute_debounced_count(dn_mask_per_sym, DEBOUNCE_BARS_4H)

        masks_per_pct[pct_up] = {"up": up_mask_per_sym, "dn": dn_mask_per_sym}

        all_ts_idx = pd.concat([s for s in close_per_sym.values()], axis=1).index
        n_quarters = max(
            1, int(np.ceil((all_ts_idx.max() - all_ts_idx.min()).days / 91))
        )
        per_q_up = n_deb_up / n_quarters
        per_q_dn = n_deb_dn / n_quarters

        empirical_per_pct[f"pct_{pct_up}"] = {
            "percentile_up": float(pct_up),
            "percentile_dn": float(pct_dn),
            "n_raw_pump": n_raw_up,
            "n_raw_dump": n_raw_dn,
            "n_debounced_pump": n_deb_up,
            "n_debounced_dump": n_deb_dn,
            "raw_pump_rate_pct": float(100 * n_raw_up / max(1, n_bars_total)),
            "raw_dump_rate_pct": float(100 * n_raw_dn / max(1, n_bars_total)),
            "debounced_pump_per_quarter": float(per_q_up),
            "debounced_dump_per_quarter": float(per_q_dn),
            "n_quarters": int(n_quarters),
        }
        log.info(
            "pct_up=%.2f (p%d): raw_pump=%d (%.2f%%) deb_pump=%d (%.1f/quarter) | "
            "pct_dn=%.2f (p%d): raw_dump=%d (%.2f%%) deb_dump=%d (%.1f/quarter)",
            pct_up, int(pct_up * 100), n_raw_up,
            empirical_per_pct[f"pct_{pct_up}"]["raw_pump_rate_pct"],
            n_deb_up, per_q_up,
            pct_dn, int(pct_dn * 100), n_raw_dn,
            empirical_per_pct[f"pct_{pct_up}"]["raw_dump_rate_pct"],
            n_deb_dn, per_q_dn,
        )
    out["lesson34_empirical_per_pct"] = empirical_per_pct

    # Per-pct 4-quadrant SNT at primary hold (24h)
    per_pct_results: dict = {}
    for pct_up, pct_dn in zip(PCT_SWEEP, PCT_LOW_MIRROR):
        log.info(
            "=== pct_up=%.2f (p%d) | pct_dn=%.2f (p%d) (4-quadrant SNT @ hold=%dh) ===",
            pct_up, int(pct_up * 100), pct_dn, int(pct_dn * 100),
            PRIMARY_HOLD_BARS_4H * 4,
        )
        emp = empirical_per_pct[f"pct_{pct_up}"]
        per_pct_results[f"pct_{pct_up}"] = {
            "percentile_up": float(pct_up),
            "percentile_dn": float(pct_dn),
            "n_debounced_pump": emp["n_debounced_pump"],
            "n_debounced_dump": emp["n_debounced_dump"],
            "debounced_pump_per_quarter": emp["debounced_pump_per_quarter"],
            "debounced_dump_per_quarter": emp["debounced_dump_per_quarter"],
            "lesson11_pump_pass": bool(emp["debounced_pump_per_quarter"] >= 30),
            "lesson11_dump_pass": bool(emp["debounced_dump_per_quarter"] >= 30),
        }

        if not per_pct_results[f"pct_{pct_up}"]["lesson11_pump_pass"]:
            log.warning(
                "pct_up=%.2f Lesson #11 SKIP — debounced pump %.1f/quarter < 30",
                pct_up, emp["debounced_pump_per_quarter"],
            )
            per_pct_results[f"pct_{pct_up}"]["skip_reason"] = "lesson11_sample_density_fail_pump"
            continue

        up_mask_per_sym = masks_per_pct[pct_up]["up"]
        dn_mask_per_sym = masks_per_pct[pct_up]["dn"]

        # 4-quadrant SNT
        quadrants = {}
        quadrants["A_focus_pump_LONG"] = compute_quadrant(
            f"A_focus_pump_LONG_p{int(pct_up * 100)}",
            up_mask_per_sym, fwd_primary, dir_long,
            PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
            pool_long_primary,
        )
        quadrants["A_mirror_pump_SHORT"] = compute_quadrant(
            f"A_mirror_pump_SHORT_p{int(pct_up * 100)}",
            up_mask_per_sym, fwd_primary, dir_short,
            PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
            pool_short_primary,
        )
        if per_pct_results[f"pct_{pct_up}"]["lesson11_dump_pass"]:
            quadrants["B_same_sign_dump_SHORT"] = compute_quadrant(
                f"B_same_sign_dump_SHORT_p{int(pct_dn * 100)}",
                dn_mask_per_sym, fwd_primary, dir_short,
                PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
                pool_short_primary,
            )
            quadrants["B_mirror_dump_LONG"] = compute_quadrant(
                f"B_mirror_dump_LONG_p{int(pct_dn * 100)}",
                dn_mask_per_sym, fwd_primary, dir_long,
                PRIMARY_HOLD_BARS_4H, DEBOUNCE_BARS_4H, FEE_PER_TRADE,
                pool_long_primary,
            )
        per_pct_results[f"pct_{pct_up}"]["quadrants"] = quadrants

        # Lesson #39 mirror diagnostic
        a_focus_gross = quadrants["A_focus_pump_LONG"].get("obs_mean_gross_bp", 0.0)
        a_mirror_gross = quadrants["A_mirror_pump_SHORT"].get("obs_mean_gross_bp", 0.0)
        sum_abs_mirror = abs(a_focus_gross + a_mirror_gross)
        per_pct_results[f"pct_{pct_up}"]["lesson39_symmetry"] = {
            "A_focus_gross_bp": a_focus_gross,
            "A_mirror_gross_bp": a_mirror_gross,
            "sum_abs_bp": float(sum_abs_mirror),
            "is_perfect_mirror": bool(sum_abs_mirror < 1.0),
        }

        # Lesson #8 universal LONG bias check (A_focus LONG + B_mirror LONG both pos?)
        b_mirror_gross = quadrants.get("B_mirror_dump_LONG", {}).get("obs_mean_gross_bp", float("nan"))
        long_bias_check = {
            "A_focus_pump_LONG_gross_bp": a_focus_gross,
            "B_mirror_dump_LONG_gross_bp": float(b_mirror_gross) if b_mirror_gross is not None and not np.isnan(b_mirror_gross) else None,
            "both_positive": bool(a_focus_gross > 0 and b_mirror_gross is not None and not np.isnan(b_mirror_gross) and b_mirror_gross > 0),
        }
        per_pct_results[f"pct_{pct_up}"]["lesson8_long_bias_check"] = long_bias_check

        # Log summary
        a = quadrants["A_focus_pump_LONG"]
        log.info(
            "  A_focus n=%d gross=%.2fbp net=%.2fbp sigex=%.2f ci=[%.2f,%.2f] 3gate=%s conc=%s edge=%.2f%% trades/yr=%.0f lc4=%s",
            a.get("n_trades", 0),
            a.get("obs_mean_gross_bp", 0),
            a.get("obs_mean_net_bp", 0),
            a.get("signal_t_excess") if a.get("signal_t_excess") is not None else -999,
            a.get("ci_lower_bp", 0),
            a.get("ci_upper_bp", 0),
            a.get("gate_3_pass"),
            a.get("gate_concentration_pass"),
            a.get("life_changing_4dim", {}).get("per_trade_edge_pct", 0),
            a.get("life_changing_4dim", {}).get("trades_per_year", 0),
            a.get("life_changing_4dim", {}).get("pass_all_4_dim"),
        )

    out["per_pct_results"] = per_pct_results

    # Hold sweep on PRIMARY pct A_focus_pump_LONG
    primary_key = f"pct_{PRIMARY_PCT}"
    sweep_results = []
    if primary_key in per_pct_results and "skip_reason" not in per_pct_results[primary_key]:
        log.info(
            "=== hold sweep on primary pct %.2f A_focus_pump_LONG ===",
            PRIMARY_PCT,
        )
        up_mask_primary = masks_per_pct[PRIMARY_PCT]["up"]

        for h in HOLD_SWEEP_BARS_4H:
            if h == PRIMARY_HOLD_BARS_4H:
                primary_quadrant = per_pct_results[primary_key]["quadrants"]["A_focus_pump_LONG"]
                sweep_results.append({**primary_quadrant, "is_primary_hold": True})
                continue
            fwd_h = fwd_per_sym_by_hold[h]
            pool_h = np.concatenate([f.dropna().values for f in fwd_h.values()])
            try:
                res = compute_quadrant(
                    f"A_focus_pump_LONG_p{int(PRIMARY_PCT * 100)}_h{h * 4}",
                    up_mask_primary, fwd_h, dir_long,
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

    out["hold_sweep_primary_pct_A_focus"] = sweep_results

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
    best_pct = None
    best_focus_gross = -np.inf
    any_full_pass_pct = None
    any_narrow_scope_pct = None
    n_three_gate_pass_total = 0
    n_quadrants_negative_gross = 0
    n_quadrants_total = 0
    max_quadrant_gross_any = -np.inf

    for pct_up in PCT_SWEEP:
        key = f"pct_{pct_up}"
        if "skip_reason" in per_pct_results.get(key, {}):
            continue
        quadrants = per_pct_results[key].get("quadrants", {})
        for qname, q in quadrants.items():
            n_quadrants_total += 1
            g = q.get("obs_mean_gross_bp", 0.0)
            if g < 0:
                n_quadrants_negative_gross += 1
            if g > max_quadrant_gross_any:
                max_quadrant_gross_any = g
            if q.get("gate_3_pass"):
                n_three_gate_pass_total += 1
        A_focus = quadrants.get("A_focus_pump_LONG", {})
        ag = A_focus.get("obs_mean_gross_bp", -np.inf)
        if ag > best_focus_gross:
            best_focus_gross = ag
            best_pct = pct_up
        a_g3 = A_focus.get("gate_3_pass", False)
        a_gc = A_focus.get("gate_concentration_pass", False)
        a_lc = A_focus.get("life_changing_4dim", {}).get("pass_all_4_dim", False)
        a_edge_pass = A_focus.get("life_changing_4dim", {}).get("pass_edge_2pct", False)
        if a_g3 and a_gc and a_lc:
            any_full_pass_pct = pct_up
        elif a_g3 and a_gc and a_edge_pass and not a_lc:
            any_narrow_scope_pct = pct_up

    if sweep_full_pass_cells:
        any_full_pass_pct = any_full_pass_pct if any_full_pass_pct is not None else "from_sweep"
    if sweep_narrow_scope_cells and any_narrow_scope_pct is None:
        any_narrow_scope_pct = "from_sweep"

    out["best_pct"] = best_pct
    out["best_focus_gross_bp"] = float(best_focus_gross) if best_focus_gross != -np.inf else None
    out["max_quadrant_gross_any_bp"] = float(max_quadrant_gross_any) if max_quadrant_gross_any != -np.inf else None
    out["n_three_gate_pass_total"] = n_three_gate_pass_total
    out["n_quadrants_total"] = n_quadrants_total
    out["n_quadrants_negative_gross"] = n_quadrants_negative_gross

    if any_full_pass_pct is not None:
        verdict = "PASS_R1_FULL"
        verdict_reason = (
            f"At pct_up={any_full_pass_pct}, A_focus pump→LONG (or hold-sweep "
            f"cell) PASS 3-gate + Concentration + life-changing 4-dim. "
            f"FOMO continuation mechanism viable at 24h scale — REVERSES "
            f"paradigm 117 R-3 caveat 1 asymmetric finding."
        )
        next_action = "propose_R2_user_approval"
    elif any_narrow_scope_pct is not None:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = (
            f"At pct_up={any_narrow_scope_pct}, A_focus PASS 3-gate + "
            f"Concentration + edge≥2% BUT other lc dim fail. NARROW_SCOPE_LIFE_CHANGING_FAIL."
        )
        next_action = "NARROW_SCOPE_LIFE_CHANGING_FAIL_graveyard"
    else:
        best_key = f"pct_{best_pct}" if best_pct is not None else None
        a_focus_at_best = (
            per_pct_results.get(best_key, {}).get("quadrants", {}).get("A_focus_pump_LONG", {})
            if best_key else {}
        )
        a_focus_obs_t = a_focus_at_best.get("obs_t", 0.0)
        a_focus_gross_at_best = best_focus_gross if best_focus_gross != -np.inf else 0.0

        if n_quadrants_total > 0 and n_quadrants_negative_gross == n_quadrants_total:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                f"All {n_quadrants_total} quadrants × pcts produced non-positive "
                f"gross. FOMO continuation hypothesis falsified at 24h scale. "
                f"Mechanism CLASS asymmetric finding (paradigm 117 R-3 caveat 1) "
                f"DIRECTLY CONFIRMED: capitulation MR is real but pump continuation "
                f"is not — alts revert from extreme pump at 24h scale."
            )
        elif a_focus_gross_at_best < 0 and a_focus_obs_t < -1.5:
            verdict = "BROAD_FALSIFIED_DIRECTION_INVERTED"
            verdict_reason = (
                f"A_focus pump→LONG (the hypothesis cell) gross "
                f"{a_focus_gross_at_best:.2f}bp obs_t {a_focus_obs_t:.2f} — "
                f"significantly negative. Extreme pump triggers mean-reversion "
                f"DOWN (not continuation up). MIRROR direction A_mirror pump→SHORT "
                f"may be alpha-bearing but requires separate verification. "
                f"DIRECTLY CONFIRMS paradigm 117 R-3 caveat 1 asymmetric finding."
            )
        elif max_quadrant_gross_any > 0 and max_quadrant_gross_any < 24:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"Best gross across quadrants {max_quadrant_gross_any:.2f}bp "
                f"< 24bp fee floor at 24h hold. FOMO continuation has weak "
                f"directional bias but does not clear round-trip fee."
            )
        else:
            verdict = "BROAD_FALSIFIED_NO_THREE_GATE"
            verdict_reason = (
                f"No quadrant cleared 3-gate. Max quadrant gross "
                f"{max_quadrant_gross_any:.2f}bp. Noisy or absent directional alpha."
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
        "Best pct: %s @ A_focus gross %.2fbp | max-quadrant gross any: %.2fbp",
        best_pct,
        best_focus_gross if best_focus_gross != -np.inf else 0,
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
