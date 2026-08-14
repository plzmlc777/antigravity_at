"""R-0 prescreen for paradigm #248 btc_onchain_active_address_regime_alt_bilateral_24h.

Hypothesis
----------
BTC daily active address count (AdrActCnt from CoinMetrics community API, free)
reveals retail engagement cycles. 30d rolling percentile rank of AdrActCnt:
- HIGH regime (>p80): peak network utility → alts exhibit BTC-sign-conditional continuation
- LOW regime (<p20): network slump → potential mean-reversion
4-quadrant SNT + 24h hold. Universe: 13 Binance USDT-M perp alts.

R-0 checks
----------
1. CoinMetrics API availability: fetch BTC AdrActCnt daily 2024-01-01 to present.
2. Empirical trigger rates at multiple percentile thresholds (p20/p25/p30 LOW; p70/p75/p80 HIGH).
3. Compute expected n_per_cell (4 quadrant × 4 quarter cells) for each threshold.
4. Fee floor prescreen: measure median |24h alt return| in sample vs 16bp fee.
5. Lesson #40 structural threshold feasibility (percentile-rank statistic — bounded [0,1], no infeasibility).
6. Verify 1d OHLCV substrate density from 1m cache.

Output: r0_prescreen.json + verdict (PASS or specific halt cause).
"""
from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p248_r0")

PARADIGM = "btc_onchain_active_address_regime_alt_bilateral_24h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

CM_URL_TMPL = (
    "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    "?assets=btc&metrics=AdrActCnt,TxCnt&frequency=1d"
    "&start_time={start}&end_time={end}"
    "&page_size=10000"
)


def fetch_coinmetrics(start: str, end: str) -> pd.DataFrame:
    url = CM_URL_TMPL.format(start=start, end=end)
    log.info("Fetching CoinMetrics AdrActCnt/TxCnt %s → %s", start, end)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
    rows = data.get("data", [])
    if not rows:
        raise RuntimeError("empty CoinMetrics response")
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None)
    df["AdrActCnt"] = pd.to_numeric(df["AdrActCnt"], errors="coerce")
    df["TxCnt"] = pd.to_numeric(df["TxCnt"], errors="coerce")
    df = df.rename(columns={"time": "date"}).set_index("date").sort_index()
    return df[["AdrActCnt", "TxCnt"]]


def build_daily_alt_returns(sym: str) -> pd.Series:
    """Load 1m OHLCV, resample to daily UTC close-to-close returns."""
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    # index is UTC datetime
    daily = df["close"].resample("1D").last().dropna()
    ret = daily.pct_change().dropna()
    return ret


def main() -> None:
    start_iso = "2024-01-01T00:00:00Z"
    end_iso = pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    t0 = time.time()
    cm = fetch_coinmetrics(start_iso, end_iso)
    log.info("CoinMetrics rows=%d span=%s→%s in %.1fs",
             len(cm), cm.index.min().date(), cm.index.max().date(), time.time() - t0)

    if len(cm) < 500:
        result = {
            "paradigm": PARADIGM,
            "verdict": "DATA_INFRASTRUCTURE_IMPOSSIBLE",
            "reason": f"CoinMetrics only returned {len(cm)} rows; need >=500 daily for 4-quarter split",
            "coinmetrics_n_rows": len(cm),
        }
        (OUT_DIR / "r0_prescreen.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        return

    # Compute 30d rolling percentile rank of AdrActCnt
    aac = cm["AdrActCnt"].dropna()
    log.info("AdrActCnt stats: min=%.0f p50=%.0f p95=%.0f max=%.0f",
             aac.min(), aac.median(), aac.quantile(0.95), aac.max())

    # 30-day rolling percentile rank (position within trailing 30d)
    def pct_rank_30d(s: pd.Series) -> pd.Series:
        # rolling apply: rank of the current value within trailing 30d window
        return s.rolling(30, min_periods=20).apply(
            lambda w: (w < w.iloc[-1]).sum() / (len(w) - 1) if len(w) > 1 else np.nan,
            raw=False,
        )

    t1 = time.time()
    pct30 = pct_rank_30d(aac)
    log.info("30d pct-rank computed in %.1fs; valid_n=%d", time.time() - t1, pct30.notna().sum())

    # Load BTC daily returns as regime sign
    btc_ret_daily = build_daily_alt_returns("BTCUSDT")
    log.info("BTC daily ret rows=%d span=%s→%s", len(btc_ret_daily),
             btc_ret_daily.index.min().date(), btc_ret_daily.index.max().date())

    # Align on-chain regime with BTC direction (BOTH indexed at midnight UTC)
    # Trigger date is D: use AdrActCnt on D, BTC return over D→D+1 (24h), alt return D→D+1.
    # Actually: AdrActCnt for day D is observed at ~D 23:59 UTC (end-of-day count).
    # To avoid look-ahead: use AdrActCnt(D-1) → trigger at D 00:00 UTC → hold 24h to D+1 00:00.
    aac_lag1 = aac.shift(1)   # yesterday's active-address count is knowable at today's open
    pct30_lag1 = pct30.shift(1)

    # Standardize dates to naive UTC-day at midnight
    pct30_lag1.index = pd.to_datetime(pct30_lag1.index).normalize()
    btc_ret_daily.index = pd.to_datetime(btc_ret_daily.index).normalize()

    aligned = pd.DataFrame({
        "pct30_lag1": pct30_lag1,
        "btc_ret_24h": btc_ret_daily,
    }).dropna()
    log.info("Aligned pct30_lag1 × btc_ret_24h: n=%d", len(aligned))

    # ---- Multiple threshold sweep ----
    threshold_pairs = [
        (0.20, 0.80),
        (0.25, 0.75),
        (0.30, 0.70),
        (0.15, 0.85),
    ]

    threshold_results = {}
    for lo, hi in threshold_pairs:
        low_mask = aligned["pct30_lag1"] < lo
        high_mask = aligned["pct30_lag1"] > hi
        btc_up = aligned["btc_ret_24h"] > 0
        btc_dn = aligned["btc_ret_24h"] < 0

        # 4 quadrants
        Q_hi_up = (high_mask & btc_up).sum()
        Q_hi_dn = (high_mask & btc_dn).sum()
        Q_lo_up = (low_mask & btc_up).sum()
        Q_lo_dn = (low_mask & btc_dn).sum()

        # Approximate n per (quadrant × alt-symbol × quarter):
        # Each trigger date fires for ALL alt symbols simultaneously (regime is BTC-derived).
        # So a per-cell count = triggers_per_quadrant / 4_quarters (all 13 alts pooled).
        # Lesson #11: need >=30 per (quadrant × quarter × per-symbol) if we split by symbol,
        # but pool-wide analysis needs (triggers × 13 alts) / 4 quarters per quadrant.

        # For 3-alt PoC scope (SOL/DOGE/ETH), per-symbol per-quarter check:
        min_q_trig = min(Q_hi_up, Q_hi_dn, Q_lo_up, Q_lo_dn)
        # 4 quarters per year × 2.6 years span ≈ 10 quarters; use 4 for simplicity
        n_per_quadrant_per_quarter = min_q_trig / 4
        # For 3-alt PoC (SOL/DOGE/ETH), same trigger fires for all 3, so events per cell
        # = triggers_per_quadrant × 3_alts / 4_quarters (pooled analysis)
        n_events_3alt_pool_per_quarter = n_per_quadrant_per_quarter * 3

        threshold_results[f"lo{lo:.2f}_hi{hi:.2f}"] = {
            "low_threshold_pct": lo,
            "high_threshold_pct": hi,
            "n_low_regime": int(low_mask.sum()),
            "n_high_regime": int(high_mask.sum()),
            "Q_high_btcup": int(Q_hi_up),
            "Q_high_btcdn": int(Q_hi_dn),
            "Q_low_btcup": int(Q_lo_up),
            "Q_low_btcdn": int(Q_lo_dn),
            "min_quadrant_triggers": int(min_q_trig),
            "n_per_quadrant_per_quarter_pool": round(n_per_quadrant_per_quarter, 1),
            "n_events_3alt_pool_per_quadrant_per_quarter": round(n_events_3alt_pool_per_quarter, 1),
        }

    # ---- Fee floor prescreen: median |24h alt return| across universe ----
    fee_bp_roundtrip = 16.0  # 8bp per side
    fee_floor = 0.0016

    fee_check = {}
    for sym in ["SOLUSDT", "DOGEUSDT", "ETHUSDT"]:
        r = build_daily_alt_returns(sym)
        if r.empty:
            continue
        r = r.loc[r.index >= pd.Timestamp("2024-01-01")]
        fee_check[sym] = {
            "n_days": len(r),
            "median_abs_ret_24h_bp": round(r.abs().median() * 10000, 1),
            "p75_abs_ret_24h_bp": round(r.abs().quantile(0.75) * 10000, 1),
            "p95_abs_ret_24h_bp": round(r.abs().quantile(0.95) * 10000, 1),
            "fee_floor_bp": fee_bp_roundtrip,
            "fee_headroom_p75_bp": round(r.abs().quantile(0.75) * 10000 - fee_bp_roundtrip, 1),
        }

    # ---- Verdict logic (Lesson #11) ----
    # Choose threshold with highest min_quadrant_triggers, but require >=30 pool events per cell (3-alt PoC).
    best_key = None
    best_min_pool = -1
    for k, v in threshold_results.items():
        if v["n_events_3alt_pool_per_quadrant_per_quarter"] > best_min_pool:
            best_min_pool = v["n_events_3alt_pool_per_quadrant_per_quarter"]
            best_key = k

    lesson11_pass = best_min_pool >= 30
    lesson40_pass = True  # percentile rank is bounded [0,1] and does not have structural infeasibility
    fee_headroom_pass = all(v["fee_headroom_p75_bp"] > 0 for v in fee_check.values())

    if not lesson11_pass:
        verdict = "SAMPLE_INSUFFICIENT_LESSON11"
        halt_reason = f"best threshold {best_key} yields only {best_min_pool} 3-alt pooled events per quadrant×quarter (<30)"
    elif not fee_headroom_pass:
        verdict = "FEE_FLOOR_INSUFFICIENT"
        halt_reason = f"|24h alt return| p75 <= 16bp fee floor for one or more focus symbols"
    else:
        verdict = "R0_PASS"
        halt_reason = None

    result = {
        "paradigm": PARADIGM,
        "verdict": verdict,
        "halt_reason": halt_reason,
        "chosen_threshold_key": best_key,
        "chosen_threshold_stats": threshold_results.get(best_key),
        "all_thresholds": threshold_results,
        "fee_check": fee_check,
        "adr_act_cnt_stats": {
            "n_days": int(aac.notna().sum()),
            "start": str(aac.index.min().date()),
            "end": str(aac.index.max().date()),
            "min": float(aac.min()),
            "p25": float(aac.quantile(0.25)),
            "p50": float(aac.quantile(0.50)),
            "p75": float(aac.quantile(0.75)),
            "p95": float(aac.quantile(0.95)),
            "max": float(aac.max()),
        },
        "aligned_n": int(len(aligned)),
        "aligned_start": str(aligned.index.min().date()),
        "aligned_end": str(aligned.index.max().date()),
        "lesson_checks": {
            "lesson11_sample_density": lesson11_pass,
            "lesson40_structural_feasibility": lesson40_pass,
            "lesson77_non_ohlcv_substrate": True,  # CoinMetrics AdrActCnt is on-chain, not OHLCV
            "fee_headroom_p75": fee_headroom_pass,
        },
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    log.info("R-0 prescreen written to %s", out_path)
    log.info("VERDICT: %s", verdict)
    print(json.dumps({"paradigm": PARADIGM, "verdict": verdict,
                      "best_threshold": best_key,
                      "best_min_pool_per_quadrant_per_quarter": best_min_pool}))


if __name__ == "__main__":
    main()
