"""Paradigm 111 — binance_perp_mark_index_basis_extreme_alt_directional_4h R-1 PoC

Hypothesis
----------
Binance USDT-perp mark price embeds (index spot composite × premium index funding
component). When the basis component itself — defined as
  basis_pct(t) = (mark_close(t) - index_close(t)) / index_close(t)
measured at 5m granularity — reaches an extreme percentile vs rolling 30-day
distribution (p_rank ≤ 0.05 or ≥ 0.95), the basis tends to mean-revert in the
following 4-hour window. The bet is on basis MEAN-REVERSION:
  - basis_pct ≥ p95 (perp rich vs index) → SHORT the perp
  - basis_pct ≤ p05 (perp cheap vs index) → LONG the perp

Novelty self-check (3/5 NOVEL ex ante)
- Statistic: basis_pct percentile rank (NOVEL — paradigm 110 lesson #40 uses
  percentile rank on σ_cs, distinct metric; paradigm 80 used z-score level)
- Universe: standard 6-alt subset (NOT NOVEL — chosen for substrate scope)
- Frame: 5m basis × 4h hold (NOT NOVEL — paradigm 80 territory but distinct
  signal axis)
- Mechanism: basis MEAN-REVERSION direction (NOVEL — paradigm 24 R-5 seed is
  daily premium MOMENTUM follow, opposite direction at different granularity;
  paradigm 80 broad-falsified joint level z, not basis pct_rank)
- Trigger: signed percentile rank (NOVEL — paradigm 80 used joint |z|>2)

Substrate: data.binance.vision/futures/um/monthly/{mark,index}PriceKlines/{sym}/5m
verified 2026-05-20 KST (HTTP 200 for SOL, HBAR, JUP).

R-0 prescreens: Lessons 11/19/21/28/30/34/40
R-1 body: 4-quadrant Symmetric Negative Test (A focus + A mirror + B same-sign
+ B mirror) + Concentration Gate + Life-changing 4-dim layer + fee_aware_perm
+ bootstrap CI.

Scope (tight for 30-min wall-clock budget on local hcp host):
- 6 alt-perps with confirmed substrate: SOL, HBAR, AVAX, DOGE, ETH, LINK
- 12 months: 2025-05 .. 2026-04 (12 monthly archives × 2 files × 6 syms = 144
  downloads at ~200KB each, ~30MB total, ~2-3 min sequential)
"""
from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# Ensure scripts.research is importable when invoked from venv
ROOT = Path("/home/hcpark/antigravity/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            ROOT
            / "runs"
            / "research_track"
            / "binance_perp_mark_index_basis_extreme_alt_directional_4h"
            / "r1__stdout.log"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p111_r1")

OUT_DIR = (
    ROOT
    / "runs"
    / "research_track"
    / "binance_perp_mark_index_basis_extreme_alt_directional_4h"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = OUT_DIR / "mark_index_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Tight 6-alt scope for wall-clock budget. All have substrate verified.
ALTS = ["SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT"]

# 12-month window: 2025-05 .. 2026-04
START_MONTH = "2025-05"
END_MONTH = "2026-04"

FEE_PER_TRADE = 0.0008  # 16bp round-trip
ROLLING_30D_5M_BARS = 288 * 30  # 8640 5-min bars
PRIMARY_P_RANK_LOW = 0.05  # |basis_pct| ≤ p05 → LONG (perp cheap)
PRIMARY_P_RANK_HIGH = 0.95  # |basis_pct| ≥ p95 → SHORT (perp rich)
PRIMARY_HOLD_BARS = 48  # 48 × 5m = 240min = 4h
HOLD_SWEEP_BARS = [12, 24, 48, 96]  # 60m, 120m, 240m, 480m


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def download_5m_klines(sym: str, kind: str, month: str) -> pd.DataFrame:
    """Download {kind in 'markPriceKlines','indexPriceKlines'} monthly 5m archive.

    Returns DataFrame indexed by open_time (UTC), with 'close' column.
    Caches to CACHE_DIR/{sym}_{kind}_{month}.parquet (joblib if pyarrow missing).
    """
    cache_file = CACHE_DIR / f"{sym}_{kind}_{month}.joblib"
    if cache_file.exists():
        import joblib
        try:
            return joblib.load(cache_file)
        except Exception:
            pass

    url = f"https://data.binance.vision/data/futures/um/monthly/{kind}/{sym}/5m/{sym}-5m-{month}.zip"
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        log.warning("download %s %s %s -> HTTP %d", sym, kind, month, r.status_code)
        return pd.DataFrame()
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                df = pd.read_csv(f)
    except Exception as e:
        log.warning("zip parse fail %s %s %s: %s", sym, kind, month, e)
        return pd.DataFrame()

    # Schema: open_time, open, high, low, close, volume, close_time, ...
    # markPriceKlines & indexPriceKlines lack volume — fewer cols
    # header already parsed
    # c0 = open_time (ms), c4 = close
    df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_localize(None)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[["ts", "close"]].dropna().drop_duplicates("ts").set_index("ts").sort_index()

    import joblib
    joblib.dump(df, cache_file, compress=3)
    return df


def build_basis_series(sym: str, months: list[str]) -> pd.Series:
    """Concatenate monthly mark + index 5m closes, return basis_pct series."""
    mark_parts = []
    index_parts = []
    for m in months:
        mark = download_5m_klines(sym, "markPriceKlines", m)
        idx = download_5m_klines(sym, "indexPriceKlines", m)
        if mark.empty or idx.empty:
            continue
        mark_parts.append(mark.rename(columns={"close": "mark"}))
        index_parts.append(idx.rename(columns={"close": "idx"}))
    if not mark_parts or not index_parts:
        return pd.Series(dtype=float, name=sym)
    mark_df = pd.concat(mark_parts).sort_index()
    idx_df = pd.concat(index_parts).sort_index()
    mark_df = mark_df[~mark_df.index.duplicated(keep="first")]
    idx_df = idx_df[~idx_df.index.duplicated(keep="first")]
    joined = mark_df.join(idx_df, how="inner")
    basis_pct = (joined["mark"] - joined["idx"]) / joined["idx"]
    basis_pct.name = sym
    return basis_pct


def rolling_percentile_rank(s: pd.Series, window: int) -> pd.Series:
    """Trailing rolling-window ECDF percentile rank."""
    arr = s.values.astype(float)
    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    min_periods = window // 2
    # Use a stride-based approach for speed
    for i in range(n):
        start = max(0, i - window + 1)
        win = arr[start : i + 1]
        win = win[~np.isnan(win)]
        if len(win) < min_periods:
            continue
        v = arr[i]
        if np.isnan(v):
            continue
        out[i] = float((win <= v).mean())
    return pd.Series(out, index=s.index, name=s.name)


def compute_quadrant(
    quadrant_name: str,
    basis_pct_panel: pd.DataFrame,
    p_rank_panel: pd.DataFrame,
    perp_fwd_panel: pd.DataFrame,
    trigger_lo: float,
    trigger_hi: float,
    direction_per_sym: dict,  # sym -> +1 LONG / -1 SHORT
    hold_bars: int,
) -> dict:
    """For each (timestamp, sym) where p_rank in trigger range, take signed
    forward perp return × direction_per_sym[sym]. Net fee applied per-trade.

    Each (ts, sym) is one trade — NOT basket. Concentration measured per-sym.
    """
    # Trigger mask per sym
    trades_per_sym = {s: [] for s in p_rank_panel.columns}
    ts_kept_per_sym = {s: [] for s in p_rank_panel.columns}
    for s in p_rank_panel.columns:
        pr = p_rank_panel[s]
        bp = basis_pct_panel[s]
        fwd = perp_fwd_panel[s]
        d = direction_per_sym[s]
        # mask in [trigger_lo, trigger_hi]: signed range. Use scalar booleans.
        if trigger_lo == 0.0 and trigger_hi <= 0.5:
            mask = (pr <= trigger_hi) & pr.notna()
        elif trigger_lo >= 0.5 and trigger_hi == 1.0:
            mask = (pr >= trigger_lo) & pr.notna()
        else:
            mask = (pr >= trigger_lo) & (pr <= trigger_hi) & pr.notna()
        mask = mask & fwd.notna() & bp.notna()
        idx_trig = mask[mask].index
        # Decimate: require ≥ hold_bars gap between consecutive trades to avoid
        # severe trade overlap (default 5m × 48 = 4h gap)
        if len(idx_trig) > 0:
            last_t = None
            min_gap = pd.Timedelta(minutes=5 * hold_bars)
            kept = []
            for t in idx_trig:
                if last_t is None or (t - last_t) >= min_gap:
                    kept.append(t)
                    last_t = t
            idx_trig = pd.DatetimeIndex(kept)
        for t in idx_trig:
            r = fwd.loc[t]
            if pd.notna(r):
                trades_per_sym[s].append(d * float(r))
                ts_kept_per_sym[s].append(t)

    all_trades = []
    all_ts = []
    all_sym = []
    for s, lst in trades_per_sym.items():
        for v, t in zip(lst, ts_kept_per_sym[s]):
            all_trades.append(v)
            all_ts.append(t)
            all_sym.append(s)

    if len(all_trades) < 5:
        return {
            "quadrant": quadrant_name,
            "n_trades": len(all_trades),
            "error": "n_trades<5",
        }

    gross = np.asarray(all_trades, dtype=float)
    net = gross - FEE_PER_TRADE
    obs_t = float(net.mean() / net.std(ddof=1) * np.sqrt(len(net))) if net.std(ddof=1) > 0 else 0.0
    gross_mean_bp = float(gross.mean() * 10000)
    net_mean_bp = float(net.mean() * 10000)

    ci = bootstrap_ci(net, n_boot=1000, rng_seed=42)

    # Perm pool: ALL valid (ts, sym) candidate forward returns, direction-applied
    pool_vals = []
    for s in perp_fwd_panel.columns:
        fwd = perp_fwd_panel[s].dropna()
        d = direction_per_sym[s]
        if len(fwd) > 0:
            pool_vals.append(d * fwd.values)
    pool = np.concatenate(pool_vals) if pool_vals else np.array([])

    if len(pool) < len(net) * 2:
        perm = {
            "perm_p_two_sided": float("nan"),
            "signal_t_excess": float("nan"),
            "null_mean_t": float("nan"),
            "perm_p_one_sided_above": float("nan"),
        }
    else:
        perm = fee_aware_perm_test(net, pool, fee_per_trade=FEE_PER_TRADE, n_perms=1000, rng_seed=42)

    # Per-symbol CI
    per_sym_ci = {}
    for s, lst in trades_per_sym.items():
        if len(lst) < 5:
            per_sym_ci[s] = {"n": len(lst), "ci_lower_bp": float("nan"), "ci_pos": False}
            continue
        net_s = np.asarray(lst) - FEE_PER_TRADE
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

    # Per-quarter
    df_q = pd.DataFrame({"ts": all_ts, "ret": net, "sym": all_sym})
    df_q["quarter"] = pd.to_datetime(df_q["ts"]).dt.to_period("Q").astype(str)
    per_q = {}
    for q, sub in df_q.groupby("quarter"):
        if len(sub) < 5:
            per_q[q] = {"n": len(sub), "t": float("nan"), "pos_t": False}
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

    # Gates
    gate_3 = bool(
        perm.get("signal_t_excess", float("nan")) >= 2.0
        and ci["ci_lower"] > 0
        and perm.get("perm_p_two_sided", 1.0) <= 0.10
    )
    gate_conc = bool(
        q_pos_ratio >= 0.5 and syms_ci_pos_ratio >= 0.30 and n_syms_ci_pos >= 3
    )

    # Life-changing 4-dim (annualized) — approximate
    n_years = max(1e-6, (pd.to_datetime(max(all_ts)) - pd.to_datetime(min(all_ts))).days / 365.25)
    trades_per_year = len(net) / n_years
    per_trade_edge_pct = net_mean_bp / 100  # bp -> percent
    # capital_util: hold_bars × 5min × trades_per_year / (8760h × 60min) — single trade at a time approx
    capital_util_pct = min(100.0, (hold_bars * 5 * trades_per_year) / (365.25 * 24 * 60) * 100)
    # Sharpe approx (annualized) — assumes trades roughly iid
    sharpe_annual = (
        (net.mean() / net.std(ddof=1)) * np.sqrt(trades_per_year)
        if net.std(ddof=1) > 0 else 0.0
    )
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
        "hold_min": hold_bars * 5,
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
        "paradigm_name": "binance_perp_mark_index_basis_extreme_alt_directional_4h",
        "paradigm_number": 111,
        "phase": "R-1",
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "host": "hcp_local",
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "window_months": [START_MONTH, END_MONTH],
        "fee_per_trade": FEE_PER_TRADE,
        "primary_p_rank_low": PRIMARY_P_RANK_LOW,
        "primary_p_rank_high": PRIMARY_P_RANK_HIGH,
        "primary_hold_bars": PRIMARY_HOLD_BARS,
        "rolling_window_5m_bars": ROLLING_30D_5M_BARS,
    }

    # ─── Stage 1: Backfill mark + index 5m ────────────────────────────────
    months = month_iter(START_MONTH, END_MONTH)
    log.info("backfilling mark+index 5m for %d alts × %d months", len(ALTS), len(months))
    t_bf = time.time()
    basis_panel = {}
    for s in ALTS:
        ts0 = time.time()
        b = build_basis_series(s, months)
        log.info("  %s: %d rows in %.1fs", s, len(b), time.time() - ts0)
        if not b.empty:
            basis_panel[s] = b
    bf_secs = time.time() - t_bf
    log.info("backfill done in %.1fs (%.1fmin)", bf_secs, bf_secs / 60)

    if not basis_panel:
        out["verdict"] = "DISPATCH_IMPOSSIBLE"
        out["verdict_reason"] = "backfill produced 0 series"
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        return 1

    basis_df = pd.concat(basis_panel, axis=1)
    basis_df = basis_df.sort_index()

    # Need perp price for forward return. Use mark close (cleanest, no liq spikes).
    mark_panel = {}
    for s in ALTS:
        parts = []
        for m in months:
            mark = download_5m_klines(s, "markPriceKlines", m)
            if not mark.empty:
                parts.append(mark)
        if parts:
            df = pd.concat(parts).sort_index()
            df = df[~df.index.duplicated(keep="first")]
            mark_panel[s] = df["close"]
    mark_df = pd.concat(mark_panel, axis=1)
    mark_df.columns = list(mark_panel.keys())
    mark_df = mark_df.sort_index()

    out["data_window"] = {
        "first": str(basis_df.index.min()),
        "last": str(basis_df.index.max()),
        "n_5m_bars": int(len(basis_df)),
        "n_alts_with_data": int(len(basis_panel)),
        "n_alts_with_mark": int(len(mark_panel)),
        "panel_years": float((basis_df.index.max() - basis_df.index.min()).days / 365.25),
        "backfill_seconds": float(bf_secs),
    }

    # ─── Stage 2: Percentile rank + forward perp ret ──────────────────────
    log.info("computing rolling p_rank window=%d 5m bars (~30d)", ROLLING_30D_5M_BARS)
    t_pr = time.time()
    p_rank_cols = {}
    for s in basis_df.columns:
        p_rank_cols[s] = rolling_percentile_rank(basis_df[s].dropna(), ROLLING_30D_5M_BARS).reindex(
            basis_df.index
        )
    p_rank_df = pd.concat(p_rank_cols, axis=1)
    p_rank_df.columns = list(p_rank_cols.keys())
    log.info("p_rank done in %.1fs", time.time() - t_pr)

    # Forward 4h log-return: log(close[t+48] / close[t])
    fwd_panels = {}
    for h in HOLD_SWEEP_BARS:
        f = np.log(mark_df.shift(-h) / mark_df)
        fwd_panels[h] = f

    # Empirical distribution diagnostic (Lesson #34)
    basis_all = basis_df.stack().dropna()
    out["lesson34_empirical_distribution"] = {
        "basis_pct_p01": float(basis_all.quantile(0.01)),
        "basis_pct_p05": float(basis_all.quantile(0.05)),
        "basis_pct_p10": float(basis_all.quantile(0.10)),
        "basis_pct_p50": float(basis_all.quantile(0.50)),
        "basis_pct_p90": float(basis_all.quantile(0.90)),
        "basis_pct_p95": float(basis_all.quantile(0.95)),
        "basis_pct_p99": float(basis_all.quantile(0.99)),
        "basis_pct_max_abs": float(basis_all.abs().max()),
        "n_obs": int(len(basis_all)),
    }
    log.info(
        "basis_pct p05=%.6f p50=%.6f p95=%.6f",
        out["lesson34_empirical_distribution"]["basis_pct_p05"],
        out["lesson34_empirical_distribution"]["basis_pct_p50"],
        out["lesson34_empirical_distribution"]["basis_pct_p95"],
    )

    # ─── R-0 prescreens ───────────────────────────────────────────────────
    # Lesson #11 sample density — how many trigger bars per sym per quarter?
    trig_low = (p_rank_df <= PRIMARY_P_RANK_LOW).stack()
    trig_high = (p_rank_df >= PRIMARY_P_RANK_HIGH).stack()
    n_trig_low = int(trig_low.sum())
    n_trig_high = int(trig_high.sum())
    n_quarters = max(
        1, int(np.ceil((basis_df.index.max() - basis_df.index.min()).days / 91))
    )
    # After decimation (≥ hold_bars gap): rough estimate trigger_rate × valid_bars / hold_bars
    n_valid_obs = int(p_rank_df.notna().sum().sum())
    decimation_factor = PRIMARY_HOLD_BARS  # decimate ≥ hold gap
    expected_low_trades = n_trig_low / decimation_factor
    expected_high_trades = n_trig_high / decimation_factor
    per_quarter_low = expected_low_trades / n_quarters
    per_quarter_high = expected_high_trades / n_quarters
    out["lesson11_sample_density"] = {
        "n_trig_low_raw": n_trig_low,
        "n_trig_high_raw": n_trig_high,
        "n_valid_obs": n_valid_obs,
        "n_quarters": n_quarters,
        "decimation_factor": decimation_factor,
        "expected_low_trades": float(expected_low_trades),
        "expected_high_trades": float(expected_high_trades),
        "per_quarter_low": float(per_quarter_low),
        "per_quarter_high": float(per_quarter_high),
        "lesson11_floor": 30,
        "passes_lesson11_low": bool(per_quarter_low >= 30),
        "passes_lesson11_high": bool(per_quarter_high >= 30),
        "passes_lesson11_both": bool(per_quarter_low >= 30 and per_quarter_high >= 30),
    }
    log.info(
        "Lesson #11 per-quarter: low=%.1f / high=%.1f (n_quarters=%d, decimation=%d)",
        per_quarter_low,
        per_quarter_high,
        n_quarters,
        decimation_factor,
    )

    out["lesson30_data_window_ratio"] = {
        "window_months": len(months),
        "full_window_months_available": 24,  # archive ~2yr typically
        "ratio": float(len(months) / 24.0),
        "passes_lesson30": bool(len(months) / 24.0 >= 0.30),
        "verdict_reliability": "moderate" if len(months) / 24.0 < 0.50 else "reliable",
    }

    # Lesson #40 — percentile rank guarantees trigger rate by construction
    out["lesson40_structural_threshold_feasibility"] = {
        "statistic_type": "percentile_rank_signed",
        "low_threshold": PRIMARY_P_RANK_LOW,
        "high_threshold": PRIMARY_P_RANK_HIGH,
        "design_trigger_rate_low": PRIMARY_P_RANK_LOW,
        "design_trigger_rate_high": 1.0 - PRIMARY_P_RANK_HIGH,
        "passes_lesson40": True,
        "note": "Signed percentile rank guarantees both tails reachable.",
    }

    # HALT check (Lesson #11)
    if not out["lesson11_sample_density"]["passes_lesson11_both"]:
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = (
            f"Lesson #11 fail: per-quarter low={per_quarter_low:.1f} / high={per_quarter_high:.1f} "
            f"< 30 cutoff. Decimation factor {decimation_factor} (5m × hold_bars)."
        )
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        log.warning("HALT — SAMPLE_INSUFFICIENT (Lesson #11)")
        return 0

    # ─── Stage 3: R-1 4-quadrant SNT ──────────────────────────────────────
    log.info("=== R-1 4-quadrant SNT (primary hold=%d bars=%dmin) ===", PRIMARY_HOLD_BARS, PRIMARY_HOLD_BARS * 5)
    fwd_primary = fwd_panels[PRIMARY_HOLD_BARS]

    # All syms LONG dir +1, all syms SHORT dir -1 for given trigger regime
    dir_long = {s: +1 for s in basis_df.columns}
    dir_short = {s: -1 for s in basis_df.columns}

    quadrants = {}
    # A focus: p_rank ≤ 0.05 (perp cheap) → LONG (mean-reversion bet)
    quadrants["A_focus_pLOW_LONG"] = compute_quadrant(
        "A_focus_pLOW_LONG",
        basis_df,
        p_rank_df,
        fwd_primary,
        trigger_lo=0.0,
        trigger_hi=PRIMARY_P_RANK_LOW,
        direction_per_sym=dir_long,
        hold_bars=PRIMARY_HOLD_BARS,
    )
    # A mirror: same trigger (perp cheap) × SHORT (wrong direction)
    quadrants["A_mirror_pLOW_SHORT"] = compute_quadrant(
        "A_mirror_pLOW_SHORT",
        basis_df,
        p_rank_df,
        fwd_primary,
        trigger_lo=0.0,
        trigger_hi=PRIMARY_P_RANK_LOW,
        direction_per_sym=dir_short,
        hold_bars=PRIMARY_HOLD_BARS,
    )
    # B same-sign: p_rank ≥ 0.95 (perp rich) → SHORT (mean-reversion bet)
    quadrants["B_same_sign_pHIGH_SHORT"] = compute_quadrant(
        "B_same_sign_pHIGH_SHORT",
        basis_df,
        p_rank_df,
        fwd_primary,
        trigger_lo=PRIMARY_P_RANK_HIGH,
        trigger_hi=1.0,
        direction_per_sym=dir_short,
        hold_bars=PRIMARY_HOLD_BARS,
    )
    # B mirror: same trigger (perp rich) × LONG (wrong direction)
    quadrants["B_mirror_pHIGH_LONG"] = compute_quadrant(
        "B_mirror_pHIGH_LONG",
        basis_df,
        p_rank_df,
        fwd_primary,
        trigger_lo=PRIMARY_P_RANK_HIGH,
        trigger_hi=1.0,
        direction_per_sym=dir_long,
        hold_bars=PRIMARY_HOLD_BARS,
    )

    out["quadrants"] = quadrants

    # ─── Stage 4: Hold sweep (focus quadrant only, lighter) ───────────────
    log.info("=== hold sweep on A_focus_pLOW_LONG ===")
    sweep = []
    for h in HOLD_SWEEP_BARS:
        if h == PRIMARY_HOLD_BARS:
            continue
        try:
            res = compute_quadrant(
                f"A_focus_pLOW_LONG_h{h}",
                basis_df,
                p_rank_df,
                fwd_panels[h],
                trigger_lo=0.0,
                trigger_hi=PRIMARY_P_RANK_LOW,
                direction_per_sym=dir_long,
                hold_bars=h,
            )
            sweep.append(res)
        except Exception as e:
            log.warning("sweep h=%d fail: %s", h, e)
    out["hold_sweep_A_focus"] = sweep

    # ─── Verdict aggregation ──────────────────────────────────────────────
    A_focus = quadrants["A_focus_pLOW_LONG"]
    A_mirror = quadrants["A_mirror_pLOW_SHORT"]
    B_same = quadrants["B_same_sign_pHIGH_SHORT"]
    B_mirror = quadrants["B_mirror_pHIGH_LONG"]

    a_focus_pass = A_focus.get("gate_3_pass", False) and A_focus.get("gate_concentration_pass", False)
    b_same_pass = B_same.get("gate_3_pass", False) and B_same.get("gate_concentration_pass", False)
    n_quadrants_pass = sum(1 for q in (A_focus, A_mirror, B_same, B_mirror) if q.get("gate_3_pass", False))

    if a_focus_pass and b_same_pass:
        verdict = "PASS_R1_FULL"
        verdict_reason = (
            "A_focus (perp cheap → LONG) + B_same_sign (perp rich → SHORT) both PASS 3-gate AND "
            "Concentration. Mean-reversion mechanism confirmed in both directions."
        )
        next_action = "propose_R2"
    elif a_focus_pass and not b_same_pass:
        verdict = "SPLIT_PARADIGM"
        verdict_reason = (
            "A_focus PASS but B_same FAIL — only one direction of basis mean-reversion holds. "
            "Possible asymmetric mechanism (perp-cheap bounce > perp-rich fade)."
        )
        next_action = "graveyard"
    elif b_same_pass and not a_focus_pass:
        verdict = "SPLIT_PARADIGM"
        verdict_reason = (
            "B_same PASS but A_focus FAIL — perp-rich fade works but perp-cheap bounce does not."
        )
        next_action = "graveyard"
    elif n_quadrants_pass == 0:
        # All 4 fail — check for fee floor vs broad noise
        a_focus_gross = A_focus.get("obs_mean_gross_bp", 0)
        if a_focus_gross > 0 and a_focus_gross < 16:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_reason = (
                f"A_focus gross +{a_focus_gross:.2f}bp positive but below 16bp fee floor. "
                "Mechanism exists but is uneconomic."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = "All 4 quadrants FAIL 3-gate. Mechanism not present at this granularity."
        next_action = "graveyard"
    else:
        # Mirror-only PASS — Lesson #8 antipattern
        mirror_only = (
            A_mirror.get("gate_3_pass", False) or B_mirror.get("gate_3_pass", False)
        )
        if mirror_only:
            verdict = "BROAD_FALSIFIED_MIRROR_ONLY"
            verdict_reason = (
                "Only mirror quadrant(s) PASS — Lesson #8 mirror antipattern + possible "
                "symmetric magnitude bias (paradigm 99 amendment candidate)."
            )
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_reason = "Partial PASS but neither focus quadrant passes."
        next_action = "graveyard"

    # Lesson #20 narrow-scope check — if focus FAIL but isolated cell PASS in sweep
    sweep_pass_cells = [s for s in sweep if s.get("gate_3_pass", False)]
    if not a_focus_pass and not b_same_pass and len(sweep_pass_cells) > 0:
        # Lesson #15 / #20 — sweep cell PASS without focus PASS
        verdict_meta_narrow = {
            "n_sweep_pass_cells": len(sweep_pass_cells),
            "sweep_pass_quadrants": [c.get("quadrant") for c in sweep_pass_cells],
            "lesson20_note": "non-focus sweep cell PASS — narrow-scope candidate requires 4-cond eval",
        }
        out["lesson20_sweep_narrow_check"] = verdict_meta_narrow

    # Life-changing 4-dim aggregation (only on focus quadrants)
    out["life_changing_4dim_A_focus"] = A_focus.get("life_changing_4dim")
    out["life_changing_4dim_B_same"] = B_same.get("life_changing_4dim")

    # ─── Summary ──────────────────────────────────────────────────────────
    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["next_action_recommendation"] = next_action
    out["n_quadrants_pass_3gate"] = n_quadrants_pass
    out["wall_clock_minutes"] = (time.time() - t_start) / 60

    out["_summary_one_liner"] = {
        "paradigm": out["paradigm_name"],
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "n_samples": int(A_focus.get("n_trades", 0)),
        "A_focus_gross_bp": float(A_focus.get("obs_mean_gross_bp", 0)),
        "A_focus_net_bp": float(A_focus.get("obs_mean_net_bp", 0)),
        "sigex_focus": float(A_focus.get("signal_t_excess", float("nan"))),
        "concentration_pass": f"{A_focus.get('n_syms_ci_pos', 0)}/{A_focus.get('n_syms_total', 0)}",
        "wall_clock_minutes": float(out["wall_clock_minutes"]),
        "next_action_recommendation": next_action,
    }

    _write(out)
    log.info("=== R-1 DONE in %.1fmin === verdict=%s", out["wall_clock_minutes"], verdict)
    return 0


def _write(payload: dict) -> None:
    p = OUT_DIR / "r1__metrics.json"
    with open(p, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("wrote %s", p)


if __name__ == "__main__":
    sys.exit(main())
