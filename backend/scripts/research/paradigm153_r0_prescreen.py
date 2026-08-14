"""paradigm 153 R-0 prescreen — alt_range_volume_divergence_percentile_rank_directional_4h.

Lesson #40 reformulate first STRUCTURED dogfood (paradigm 152 sub-class D detection
→ percentile rank reformulate). paradigm 110 was 1st natural reformulate (z→pct),
paradigm 153 is 1st structured dogfood after Lesson #40 sub-class D formal detection.

Mechanism (paradigm 152 same underlying)
----------------------------------------
- substrate: 12-col klines 4h cache (paradigm 142/152 reuse, no new infra)
- range = (high - low) / close
- vol = quote_volume
- range_z / vol_z = per-sym 30d rolling z-score (180 bars @ 4h)
- divergence = range_z - vol_z (same as paradigm 152)
- **Trigger reformulation**: percentile rank of divergence over 30d rolling window
  - rank ∈ [0, 1], distribution-agnostic
  - trigger: rank > 0.95 OR < 0.05 (top/bottom 5%, structurally attainable both sides)

Prescreen suite
---------------
- Lesson #40 reformulate fix verification: rank > 0.95 AND rank < 0.05 both attainable
  (TRIVIALLY True by construction; verify empirical trigger counts both sides)
- Lesson #11 sample density: 14 syms × ~820d × 6/day × 5% per side = ~3,400 events/side
  expected per-cell (4 quadrants × ~9 quarters) ≈ 95 → safe
- Lesson #58 candidate xref (paradigm 152 PASS confirmed: corr 0.65-0.78 healthy zone)
- Lesson #44 amendment 37th xref family-distinct:
  - paradigm 152 (z-score subtraction) GRAVEYARD R-0 sub-class D
  - paradigm 110 (funding z → pct rank precedent, NOTE mechanism direction inverted)
  - paradigm 116/129/137/142/144 range/volume family distinct
- Lesson #30 data_window_ratio: full window (uniform cache 4741 bars/sym)
- Lesson #54 same-bar same-substrate (subtraction not ratio, identical to 152)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p153_r0")

CACHE_DIR = Path("/home/hcpark/antigravity/backend/runs/ohlcv_cache_12col")
OUT_DIR = Path("/home/hcpark/antigravity/backend/runs/research_track/alt_range_volume_divergence_percentile_rank_directional_4h")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALT_SYMBOLS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]  # 13 alts (BTC excluded as universe-baseline, identical to p152)

LOOKBACK_BARS = 180  # 30d at 4h cadence (identical to p152)
RANK_LOOKBACK_BARS = 180  # 30d rolling rank window (paradigm 110 precedent)
RANK_UPPER = 0.95
RANK_LOWER = 0.05


def load_sym(sym: str) -> pd.DataFrame | None:
    fp = CACHE_DIR / f"{sym}_4h.joblib"
    if not fp.exists():
        return None
    df = joblib.load(fp)
    df = df[["high", "low", "close", "quote_volume"]].copy()
    df = df.dropna()
    return df


def compute_divergence_with_pct_rank(df: pd.DataFrame) -> pd.DataFrame:
    range_ = (df["high"] - df["low"]) / df["close"]
    vol = df["quote_volume"]
    range_z = (range_ - range_.rolling(LOOKBACK_BARS).mean()) / range_.rolling(LOOKBACK_BARS).std()
    vol_z = (vol - vol.rolling(LOOKBACK_BARS).mean()) / vol.rolling(LOOKBACK_BARS).std()
    div = range_z - vol_z

    # percentile rank over RANK_LOOKBACK_BARS window (paradigm 110 precedent)
    # pandas rolling.rank requires version >=1.4; use apply fallback if needed
    try:
        pct_rank = div.rolling(RANK_LOOKBACK_BARS, min_periods=60).rank(pct=True)
    except (TypeError, AttributeError):
        pct_rank = div.rolling(RANK_LOOKBACK_BARS, min_periods=60).apply(
            lambda x: (x.argsort().argsort()[-1] + 1) / len(x), raw=False
        )

    out = pd.DataFrame({
        "range": range_,
        "volume": vol,
        "range_z": range_z,
        "volume_z": vol_z,
        "divergence": div,
        "pct_rank": pct_rank,
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
        feat = compute_divergence_with_pct_rank(df)
        feat_valid = feat.dropna(subset=["divergence", "pct_rank"])
        per_sym[sym] = feat_valid
        full_windows.append((sym, feat_valid.index[0], feat_valid.index[-1], len(feat_valid)))

    # Lesson #30 data_window_ratio
    per_sym_window = []
    for sym, s, e, n in full_windows:
        per_sym_window.append({"sym": sym, "start": str(s), "end": str(e), "n": n})

    # Lesson #40 reformulate fix VERIFICATION:
    # percentile rank is bounded [0,1] by construction → top/bottom 5% always
    # attainable IF data exists. Verify empirical trigger counts per side.
    trigger_records = []
    for sym, feat in per_sym.items():
        pr = feat["pct_rank"]
        n = len(pr)
        n_top5 = int((pr > RANK_UPPER).sum())
        n_bot5 = int((pr < RANK_LOWER).sum())
        trigger_records.append({
            "sym": sym,
            "n": n,
            "pr_min": float(pr.min()),
            "pr_max": float(pr.max()),
            "pr_p01": float(pr.quantile(0.01)),
            "pr_p99": float(pr.quantile(0.99)),
            "n_top_gt_p95": n_top5,
            "n_bot_lt_p05": n_bot5,
            "rate_top": float(n_top5 / n) if n else 0.0,
            "rate_bot": float(n_bot5 / n) if n else 0.0,
        })

    total_n = sum(t["n"] for t in trigger_records)
    total_top = sum(t["n_top_gt_p95"] for t in trigger_records)
    total_bot = sum(t["n_bot_lt_p05"] for t in trigger_records)
    rate_top = total_top / total_n if total_n else 0.0
    rate_bot = total_bot / total_n if total_n else 0.0

    # Lesson #11 per-cell projection (4 quadrants × ~9 quarters)
    n_quarters = 9
    per_cell_top = total_top / n_quarters
    per_cell_bot = total_bot / n_quarters
    per_cell_min = min(per_cell_top, per_cell_bot)

    # Lesson #40 reformulate fix: rank [0,1] always attainable both sides IF data exists
    # Symmetry check: top side count vs bottom side count (paradigm 152 issue was
    # asymmetric attainability; here both sides should have ~equal frequency)
    asymmetry_ratio = (total_top / total_bot) if total_bot > 0 else float("inf")
    lesson40_reformulate_pass = (total_top > 0 and total_bot > 0
                                  and 0.5 <= asymmetry_ratio <= 2.0)

    # Per-sym attainability: every sym must have both top and bottom triggers
    syms_with_both_sides = sum(1 for t in trigger_records
                                if t["n_top_gt_p95"] > 0 and t["n_bot_lt_p05"] > 0)
    lesson40_per_sym_pass = syms_with_both_sides == len(trigger_records)

    # Lesson #11 sample density (≥30 per cell)
    lesson11_pass = per_cell_min >= 30

    halt_reasons = []
    if not lesson40_reformulate_pass:
        halt_reasons.append(
            f"L40_reformulate_asymmetric_attainability total_top={total_top} "
            f"total_bot={total_bot} ratio={asymmetry_ratio:.2f}"
        )
    if not lesson40_per_sym_pass:
        halt_reasons.append(
            f"L40_per_sym_both_sides {syms_with_both_sides}/{len(trigger_records)}"
        )
    if not lesson11_pass:
        halt_reasons.append(
            f"L11_sample_density per_cell_min={per_cell_min:.1f} < 30"
        )

    verdict = "PASS_R0" if not halt_reasons else "HALT_R0"

    result = {
        "paradigm": "alt_range_volume_divergence_percentile_rank_directional_4h",
        "paradigm_id": 153,
        "phase": "R-0",
        "verdict": verdict,
        "halt_reasons": halt_reasons,
        "substrate": "binance_klines_4h_12col (paradigm 142/152 cache reuse)",
        "universe": ALT_SYMBOLS,
        "n_syms": len(per_sym),
        "lookback_bars": LOOKBACK_BARS,
        "rank_lookback_bars": RANK_LOOKBACK_BARS,
        "rank_upper": RANK_UPPER,
        "rank_lower": RANK_LOWER,
        "per_sym_window": per_sym_window,
        "lesson40_reformulate_fix_verification": {
            "fix_type": "percentile rank top/bottom 5% (paradigm 110 precedent)",
            "rationale": "paradigm 152 z-score subtraction asymmetric distribution (p99<2 13/13) → pct rank bounded [0,1] both sides structurally attainable by construction",
            "records": trigger_records,
            "total_top": total_top,
            "total_bot": total_bot,
            "rate_top": rate_top,
            "rate_bot": rate_bot,
            "asymmetry_ratio": asymmetry_ratio,
            "syms_with_both_sides": syms_with_both_sides,
            "n_syms": len(trigger_records),
            "pass_balanced_attainability": lesson40_reformulate_pass,
            "pass_per_sym_both_sides": lesson40_per_sym_pass,
        },
        "lesson11_sample_density": {
            "total_n_bars": total_n,
            "total_top_gt_p95": total_top,
            "total_bot_lt_p05": total_bot,
            "rate_top": rate_top,
            "rate_bot": rate_bot,
            "n_quarters_est": n_quarters,
            "per_cell_top_est": per_cell_top,
            "per_cell_bot_est": per_cell_bot,
            "per_cell_min": per_cell_min,
            "pass": lesson11_pass,
        },
        "lesson58_corr_xref_paradigm152": {
            "status": "paradigm 152 PASS confirmed (corr 0.65-0.78 healthy zone), identical substrate, no rerun needed",
            "n_healthy_prior": 13,
        },
        "lesson44_37th_xref": {
            "paradigm_110_funding_neg_z_pct_rank": "1st natural reformulate precedent (z→pct rank structural fix SUCCESS, BUT mechanism direction inverted graveyard — direction inversion risk for p153)",
            "paradigm_152_range_vol_divergence_z": "1st sub-class D dogfood (z subtraction asymmetric distribution graveyard) — paradigm 153 structured reformulate response",
            "paradigm_116_volume_confirmed_atr_breakout": "distinct: ATR breakout (continuation) vs range-volume regime classifier",
            "paradigm_129_parkinson_range_vol": "distinct: single-axis raw range vs joint divergence + pct rank",
            "paradigm_137_yang_zhang_close_ratio": "distinct: vol-of-vol close ratio vs range-volume joint",
            "paradigm_142_quote_vol_imbalance": "distinct: taker_buy filter on quote_vol vs range_z-vol_z+pct rank",
            "paradigm_144_quote_vol_count_ratio": "distinct: avg_trade_size ratio vs range × volume joint",
            "axis_genuinely_new_vs_p152": True,
            "axis_distinct_from_p152": "trigger formulation (pct rank vs z-score), same underlying mechanism (thin/consolidation regime)",
        },
        "lesson54_same_bar_check": {
            "type": "subtraction not ratio (range_z - vol_z) → pct rank",
            "same_bar": True,
            "independent_mechanism_story": "thin/consolidation regime classifier (range-volume joint state) reformulated trigger",
            "note": "identical to p152, no change",
        },
        "paradigm_110_direction_inversion_risk": {
            "warning": "paradigm 110 (funding neg z → pct rank ≤0.10) structural reformulate SUCCESS but mechanism direction inverted graveyard. paradigm 153 must validate mechanism direction in R-1 (top pct rank → MR vs continuation; bottom pct rank → continuation vs MR). 4-quadrant SNT mandatory.",
        },
    }

    out_fp = OUT_DIR / "r0_prescreen.json"
    out_fp.write_text(json.dumps(result, indent=2, default=str))
    log.info("R-0 verdict: %s", verdict)
    log.info("  L40 reformulate fix: balanced_attainability=%s per_sym_both=%s",
             lesson40_reformulate_pass, lesson40_per_sym_pass)
    log.info("  total triggers: top=%d bot=%d ratio=%.2f", total_top, total_bot, asymmetry_ratio)
    log.info("  L11 per-cell: top=%.0f bot=%.0f (cutoff 30)", per_cell_top, per_cell_bot)
    log.info("  halt_reasons: %s", halt_reasons or "[]")
    log.info("written: %s", out_fp)


if __name__ == "__main__":
    main()
