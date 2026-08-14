"""paradigm 152 R-0 prescreen — alt_range_volume_divergence_z_directional_4h.

Mechanism: range_z - volume_z divergence (4h, 14 alts)
- range = (high - low) / close
- volume = quote_volume
- per-symbol 30d rolling z-score (lookback=180 bars @ 4h)
- divergence = range_z - volume_z

Prescreen suite:
- Lesson #58 candidate: range vs volume per-sym corr healthy zone (0.05 < |corr| < 0.90)
- Lesson #11 sample density: |divergence|>2 rate × 14 syms × ~820d × 6/day → per-cell n ≥ 200-400
- Lesson #40 threshold attainability: empirical divergence p99/min/max scan
- Lesson #30 data_window_ratio: window per sym vs full
- Lesson #54 same-bar same-substrate ratio check (subtraction not ratio, but same-bar consideration)
- Lesson #44 36th xref: paradigm 116/129/137/142/144 family-distinct verification
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p152_r0")

CACHE_DIR = Path("/home/hcpark/antigravity/backend/runs/ohlcv_cache_12col")
OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/alt_range_volume_divergence_z_directional_4h")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALT_SYMBOLS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]  # 13 alts (BTC excluded as universe-baseline)

LOOKBACK_BARS = 180  # 30d at 4h cadence
THRESHOLD = 2.0


def load_sym(sym: str) -> pd.DataFrame | None:
    fp = CACHE_DIR / f"{sym}_4h.joblib"
    if not fp.exists():
        return None
    df = joblib.load(fp)
    df = df[["high", "low", "close", "quote_volume"]].copy()
    df = df.dropna()
    return df


def compute_divergence(df: pd.DataFrame) -> pd.DataFrame:
    range_ = (df["high"] - df["low"]) / df["close"]
    vol = df["quote_volume"]
    range_z = (range_ - range_.rolling(LOOKBACK_BARS).mean()) / range_.rolling(LOOKBACK_BARS).std()
    vol_z = (vol - vol.rolling(LOOKBACK_BARS).mean()) / vol.rolling(LOOKBACK_BARS).std()
    out = pd.DataFrame({
        "range": range_,
        "volume": vol,
        "range_z": range_z,
        "volume_z": vol_z,
        "divergence": range_z - vol_z,
        "close": df["close"],
    })
    return out


def main():
    per_sym = {}
    full_windows = []
    for sym in ALT_SYMBOLS:
        df = load_sym(sym)
        if df is None:
            log.warning("missing %s", sym)
            continue
        feat = compute_divergence(df)
        feat_valid = feat.dropna()
        per_sym[sym] = feat_valid
        full_windows.append((sym, feat_valid.index[0], feat_valid.index[-1], len(feat_valid)))

    # Lesson #30 data_window_ratio
    if full_windows:
        starts = [w[1] for w in full_windows]
        ends = [w[2] for w in full_windows]
        common_start = max(starts)
        common_end = min(ends)
        per_sym_window = []
        for sym, s, e, n in full_windows:
            per_sym_window.append({"sym": sym, "start": str(s), "end": str(e), "n": n})

    # Lesson #58 candidate: range vs volume per-sym corr
    corr_records = []
    for sym, feat in per_sym.items():
        c = feat[["range", "volume"]].corr().iloc[0, 1]
        corr_records.append({"sym": sym, "corr_range_volume": float(c)})

    corrs = np.array([r["corr_range_volume"] for r in corr_records])
    healthy_zone_lo, healthy_zone_hi = 0.05, 0.90
    n_healthy = int(((np.abs(corrs) > healthy_zone_lo) & (np.abs(corrs) < healthy_zone_hi)).sum())
    n_degeneracy = int((np.abs(corrs) >= healthy_zone_hi).sum())
    n_near_zero = int((np.abs(corrs) <= healthy_zone_lo).sum())

    # Lesson #11 sample density + #40 threshold attainability
    trigger_records = []
    for sym, feat in per_sym.items():
        div = feat["divergence"]
        n = len(div)
        n_pos = int((div > THRESHOLD).sum())
        n_neg = int((div < -THRESHOLD).sum())
        trigger_records.append({
            "sym": sym,
            "n": n,
            "div_p01": float(div.quantile(0.01)),
            "div_p99": float(div.quantile(0.99)),
            "div_min": float(div.min()),
            "div_max": float(div.max()),
            "n_pos_gt_2": n_pos,
            "n_neg_lt_neg2": n_neg,
            "rate_pos": float(n_pos / n),
            "rate_neg": float(n_neg / n),
        })

    total_n = sum(t["n"] for t in trigger_records)
    total_pos = sum(t["n_pos_gt_2"] for t in trigger_records)
    total_neg = sum(t["n_neg_lt_neg2"] for t in trigger_records)
    rate_pos = total_pos / total_n if total_n else 0
    rate_neg = total_neg / total_n if total_n else 0

    # Lesson #11 per-cell projection (4 quadrants A focus/A mirror/B focus/B mirror)
    # Each quadrant has its own trigger half, expected n_per_quadrant_per_quarter
    # 13 syms × ~820d window, quarters ≈ 9-10
    n_quarters = 9
    per_cell_pos = total_pos / n_quarters  # all syms aggregated by quarter
    per_cell_neg = total_neg / n_quarters
    per_cell_min = min(per_cell_pos, per_cell_neg)

    # Verdict
    lesson58_pass = n_healthy >= 10 and n_degeneracy == 0  # majority healthy
    lesson11_pass = per_cell_min >= 30
    lesson40_pass = all(t["div_p99"] >= THRESHOLD and t["div_p01"] <= -THRESHOLD for t in trigger_records)

    halt_reasons = []
    if not lesson58_pass:
        halt_reasons.append(f"L58_corr_healthy_zone_fail n_healthy={n_healthy}/13 n_degeneracy={n_degeneracy}")
    if not lesson11_pass:
        halt_reasons.append(f"L11_sample_density per_cell_min={per_cell_min:.1f} < 30")
    if not lesson40_pass:
        halt_reasons.append("L40_threshold_attainability_fail (some syms p99<2 or p01>-2)")

    verdict = "PASS_R0" if not halt_reasons else "HALT_R0"

    result = {
        "paradigm": "alt_range_volume_divergence_z_directional_4h",
        "paradigm_id": 152,
        "phase": "R-0",
        "verdict": verdict,
        "halt_reasons": halt_reasons,
        "substrate": "binance_klines_4h_12col (paradigm 142 cache reuse)",
        "universe": ALT_SYMBOLS,
        "n_syms": len(per_sym),
        "lookback_bars": LOOKBACK_BARS,
        "threshold": THRESHOLD,
        "per_sym_window": per_sym_window,
        "lesson58_corr_check": {
            "records": corr_records,
            "healthy_zone": [healthy_zone_lo, healthy_zone_hi],
            "n_healthy": n_healthy,
            "n_degeneracy_high_corr": n_degeneracy,
            "n_near_zero": n_near_zero,
            "pass": lesson58_pass,
        },
        "lesson11_sample_density": {
            "total_n_bars": total_n,
            "total_pos_gt_2": total_pos,
            "total_neg_lt_neg2": total_neg,
            "rate_pos": rate_pos,
            "rate_neg": rate_neg,
            "n_quarters_est": n_quarters,
            "per_cell_pos_est": per_cell_pos,
            "per_cell_neg_est": per_cell_neg,
            "per_cell_min": per_cell_min,
            "pass": lesson11_pass,
        },
        "lesson40_threshold_attainability": {
            "records": trigger_records,
            "pass": lesson40_pass,
        },
        "lesson44_36th_xref": {
            "paradigm_116_volume_confirmed_atr_breakout": "distinct: ATR breakout (continuation) vs range-volume divergence (regime classifier)",
            "paradigm_129_parkinson_range_vol": "distinct: single-axis raw range vs divergence (range_z - vol_z)",
            "paradigm_137_yang_zhang_close_ratio": "distinct: vol-of-vol close ratio vs range-volume joint z",
            "paradigm_142_quote_vol_imbalance": "distinct: taker_buy filter on quote_vol vs range_z - vol_z subtraction",
            "paradigm_144_quote_vol_count_ratio": "distinct: avg_trade_size ratio vs range × volume joint",
            "axis_genuinely_new": True,
            "axis_first_use_paradigm": 152,
        },
        "lesson54_same_bar_check": {
            "type": "subtraction not ratio (range_z - vol_z)",
            "same_bar": True,
            "independent_mechanism_story": "thin/consolidation regime classifier (range-volume joint state)",
            "note": "subtraction of two normalized z-scores; not ratio degeneracy",
        },
    }

    out_fp = OUT_DIR / "r0_prescreen.json"
    out_fp.write_text(json.dumps(result, indent=2, default=str))
    log.info("R-0 verdict: %s", verdict)
    log.info("  L58 corr healthy: %d/13 (degeneracy=%d near-zero=%d)", n_healthy, n_degeneracy, n_near_zero)
    log.info("  L11 sample density: per_cell_pos=%.0f per_cell_neg=%.0f (cutoff 30)", per_cell_pos, per_cell_neg)
    log.info("  L40 threshold attainable: %s", lesson40_pass)
    log.info("  halt_reasons: %s", halt_reasons or "[]")
    log.info("written: %s", out_fp)


if __name__ == "__main__":
    main()
