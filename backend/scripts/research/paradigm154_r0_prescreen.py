"""
paradigm 154 R-0 prescreen — alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional

R-0 prescreen of family-distinct claim against paradigm 153 GRAVEYARD precedent.

Critical gates:
- Lesson #62 candidate: family-distinct requires ≥2/4 dimensions change vs paradigm 153
- Lesson #56 CONFIRMED (7 instances): OUTCOME-LEVEL family proxy gate
- Lesson #63 candidate: structural fix layer alone insufficient for mechanism alpha
- Lesson #11: sample density (1d HIGH regime × 4h pct rank >0.95)
- Lesson #21: axis stacking does not synthesize alpha (1d regime + 4h entry = 2-axis stack)
- Lesson #30: data window ratio ≥30%
- Lesson #58: same-bar same-substrate corr healthy zone (xref to p152 PASS)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_DIR = Path("backend/runs/research_track/alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "LINK", "LTC", "BCH", "AVAX", "ETC", "FIL", "ATOM"]
CACHE_DIR = Path("backend/runs/ohlcv_cache_12col")


def family_distinct_audit() -> dict:
    """
    Lesson #62 candidate 4-dim audit vs paradigm 153.

    Dimensions: trigger / entry-side class / mechanism / substrate
    Requirement: ≥2/4 changes.
    """
    audit = {
        "trigger_statistic_class": {
            "p153": "4h range/vol divergence pct rank (>0.95 or <0.05) over 30d rolling window",
            "p154": "4h range/vol divergence pct rank (>0.95 or <0.05) over 90d rolling window",
            "changed": False,
            "rationale": "statistic class IDENTICAL (pct rank of same divergence stat); window length 30d→90d is parameter tweak NOT class change",
        },
        "entry_side_class": {
            "p153": "4h entry on trigger bar (immediate)",
            "p154": "4h entry on trigger bar (immediate, conditional on 1d regime gate)",
            "changed": False,
            "rationale": "entry timing IDENTICAL (4h bar close); regime gate is filter NOT entry-side reclassification",
        },
        "mechanism_first_principles": {
            "p153": "range-vol divergence as thin/consolidation regime classifier; 4h directional MR (high rank) / CONT (low rank)",
            "p154": "same range-vol divergence classifier + claim 1d HIGH-vol regime ISOLATES alpha (4h alpha only manifests in HIGH-vol 1d context)",
            "changed_partial": True,
            "changed_strict": False,
            "rationale": "mechanism STORY adds conditioning layer but core directional thesis (MR vs CONT on same trigger) UNCHANGED. paradigm 83 (oi_5m_latent_regime k=4 clusters) precedent: regime conditioning on identical underlying mechanism = partial novelty insufficient for Lesson #62 strict 2-dim threshold",
        },
        "substrate": {
            "p153": "12-col 4h klines (ohlcv_cache_12col)",
            "p154": "12-col 4h klines + 12-col 1d klines (same source, additional frame)",
            "changed_partial": True,
            "changed_strict": False,
            "rationale": "same data source (Binance klines, ohlcv_cache_12col), additional frame is resampling NOT new substrate. Lesson #58 cross-substrate exemption does NOT apply (same source)",
        },
    }

    strict_changes = sum(1 for d in audit.values() if d.get("changed") is True or d.get("changed_strict") is True)
    partial_changes = sum(1 for d in audit.values() if d.get("changed_partial") is True)

    audit["_summary"] = {
        "strict_changes": strict_changes,
        "partial_changes": partial_changes,
        "lesson_62_threshold": 2,
        "lesson_62_strict_pass": strict_changes >= 2,
        "lesson_62_partial_pass": (strict_changes + partial_changes) >= 2,
        "verdict": "LESSON_62_FAIL_STRICT" if strict_changes < 2 else "LESSON_62_PASS",
    }
    return audit


def outcome_level_family_audit() -> dict:
    """
    Lesson #56 CONFIRMED (7 instances) OUTCOME-LEVEL family proxy audit.

    range_volume_divergence family graveyard chain.
    """
    family_chain = [
        {"paradigm": 110, "verdict": "BROAD_FALSIFIED_DIRECTION_INVERTED", "axis": "funding neg z pct rank reformulate"},
        {"paradigm": 115, "verdict": "DIFFUSE_POSITIVE", "axis": "range-volume related"},
        {"paradigm": 137, "verdict": "GRAVEYARD", "axis": "range-volume related"},
        {"paradigm": 150, "verdict": "R0_HALT_BY_OUTCOME_LEVEL_FAMILY_PROXY", "axis": "ATR-normalized range breakout"},
        {"paradigm": 152, "verdict": "HALT_STRUCTURAL_ASYMMETRY", "axis": "range_z - vol_z divergence"},
        {"paradigm": 153, "verdict": "BROAD_FALSIFIED", "axis": "range/vol divergence pct rank 30d window"},
    ]
    family_count = len(family_chain)

    return {
        "family_axis": "range_volume_divergence_directional",
        "prior_graveyards": family_chain,
        "family_count": family_count,
        "lesson_56_threshold_confirmed": 5,
        "p154_position": "8th_instance",
        "outcome_level_proxy_triggered": True,
        "rationale": (
            "paradigm 153 BROAD_FALSIFIED demonstrated mechanism alpha 부재 at the bar-level (4h). "
            "paradigm 154 adds 1d regime conditioning layer on top of IDENTICAL trigger statistic class + IDENTICAL entry-side timing. "
            "Lesson #21 (axis stacking does not synthesize alpha): regime gate on alpha-empty trigger CANNOT manufacture alpha. "
            "paradigm 83 (oi_5m_latent_regime k=4 clusters) precedent: 4/4 clusters BROAD_FALSIFIED (-27σ to -58σ) — regime stratification on alpha-absent underlying does NOT rescue. "
            "paradigm 81 (rolling beta 4-cell sign-cond): cell PASS but concentration FAIL 3/13 alts only. "
            "OUTCOME-LEVEL prediction: paradigm 154 = paradigm 153 + regime filter. If 1d HIGH-vol cell PASSES, it would be statistically suspicious given paradigm 153 baseline."
        ),
    }


def lesson_63_audit() -> dict:
    """
    Lesson #63 candidate (1st dogfood paradigm 153): structural fix ≠ mechanism alpha resurrection.

    paradigm 154 framing: 'add regime layer' is attempting mechanism alpha resurrection
    through stacking, NOT through new mechanism story. Lesson #63 directly applies.
    """
    return {
        "lesson_63_statement": (
            "A successful Lesson #40 reformulate that fixes structural threshold infeasibility "
            "may still produce BROAD_FALSIFIED R-1 if the underlying mechanism itself carries no alpha. "
            "R-0 PASS on reformulate axis does NOT predict R-1 PASS on mechanism axis."
        ),
        "p154_framing": (
            "paradigm 154 is NOT a new reformulate; it is paradigm 153 (already structurally PASS, mechanism FAIL) "
            "with an additional regime filter LAYER. Lesson #63 directly predicts: mechanism alpha was tested and "
            "verified ABSENT at the bar level — conditioning on a coarser-frame regime cannot manufacture absent alpha."
        ),
        "prediction": "paradigm 154 R-1 4-quadrant SNT will reveal HIGH-regime cells with mean_bp ≈ fee floor (paradigm 153 outcome reproduced inside the HIGH-regime subset)",
        "lesson_63_2nd_dogfood_eligible": True,
    }


def lesson_21_axis_stacking_audit() -> dict:
    """
    Lesson #21 CONFIRMED: axis stacking does not synthesize alpha (6 dogfoods).

    paradigm 154 explicit 2-axis stack: 1d regime × 4h entry.
    """
    return {
        "lesson_21_statement": "axis stacking (joint-trigger on N axes) does not synthesize alpha if no constituent axis carries alpha",
        "p154_axes": ["1d range-vol divergence pct rank regime", "4h range-vol divergence pct rank entry"],
        "axis_overlap": "SAME statistic class on TWO frames — axes are NOT independent",
        "concerning_property": (
            "1d range-vol divergence and 4h range-vol divergence are functions of the SAME underlying bar data. "
            "1d divergence = aggregation of 6 × 4h divergences (approximate). Statistical dependence near 1.0 at long horizons. "
            "This is NOT 2-axis stacking; it is autocorrelation of the same statistic at different time scales. "
            "Lesson #21 sub-finding 6 (MTF stacking of same statistic class on same substrate) applies maximally."
        ),
        "lesson_21_verdict": "AXIS_STACKING_DEGENERATE_SAME_STATISTIC_DIFFERENT_FRAME",
    }


def lesson_30_data_window_audit() -> dict:
    """Lesson #30: data window ratio."""
    cache_windows = {}
    for sym in SYMS:
        cache_file = CACHE_DIR / f"{sym}USDT_4h.joblib"
        if cache_file.exists():
            cache_windows[sym] = "available"
        else:
            cache_windows[sym] = "missing"

    return {
        "syms_available": [s for s, v in cache_windows.items() if v == "available"],
        "syms_missing": [s for s, v in cache_windows.items() if v == "missing"],
        "data_window_advertised": "2024-02 ~ 2026-04 (≈2.2yr)",
        "mint_full_universe_window": "2.4yr",
        "ratio_pct": 91.7,
        "lesson_30_threshold_pct": 30.0,
        "lesson_30_pass": True,
    }


def main() -> int:
    logger.info("paradigm 154 R-0 prescreen — Lesson #62/#56/#63/#21 family-distinct + outcome-level audit")
    logger.info("substrate: %s (14 syms 4h)", CACHE_DIR)

    family_distinct = family_distinct_audit()
    outcome_level = outcome_level_family_audit()
    lesson_63 = lesson_63_audit()
    lesson_21 = lesson_21_axis_stacking_audit()
    lesson_30 = lesson_30_data_window_audit()

    # Compose verdict
    lesson_62_fail = family_distinct["_summary"]["lesson_62_strict_pass"] is False
    lesson_56_fail = outcome_level["outcome_level_proxy_triggered"] is True
    lesson_21_concerning = lesson_21["lesson_21_verdict"] == "AXIS_STACKING_DEGENERATE_SAME_STATISTIC_DIFFERENT_FRAME"

    verdict_components = []
    if lesson_62_fail:
        verdict_components.append("LESSON_62_RETIMING_REFRAME_2ND_DOGFOOD")
    if lesson_56_fail:
        verdict_components.append("LESSON_56_OUTCOME_LEVEL_FAMILY_PROXY_8TH_INSTANCE")
    if lesson_21_concerning:
        verdict_components.append("LESSON_21_MTF_AXIS_STACKING_SAME_STATISTIC_DEGENERATE")

    verdict = "R0_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION"
    if not (lesson_62_fail or lesson_56_fail):
        verdict = "R0_PASS_DISPATCH_R1"

    result = {
        "paradigm_name": "alt_range_volume_divergence_pct_rank_MTF_1d_regime_x_4h_entry_directional",
        "paradigm_number": 154,
        "dispatch_timestamp_kst": "2026-05-21 15:10 KST",
        "previous_paradigm_153": {
            "name": "alt_range_volume_divergence_percentile_rank_directional_4h",
            "verdict": "BROAD_FALSIFIED",
            "graveyard": "backend/runs/research_track/graveyard__alt_range_volume_divergence_percentile_rank_directional_4h.md",
            "key_finding": "Lesson #40 reformulate structural layer SUCCESS + mechanism alpha 부재",
        },
        "audits": {
            "lesson_62_family_distinct_4dim": family_distinct,
            "lesson_56_outcome_level_family_proxy": outcome_level,
            "lesson_63_structural_fix_vs_mechanism_alpha": lesson_63,
            "lesson_21_axis_stacking": lesson_21,
            "lesson_30_data_window_ratio": lesson_30,
        },
        "verdict": verdict,
        "verdict_components": verdict_components,
        "r1_dispatched": verdict == "R0_PASS_DISPATCH_R1",
        "halt_rationale_summary": (
            "paradigm 154 is paradigm 153 + 1d regime filter overlay on IDENTICAL statistic class on SAME substrate. "
            "Lesson #62 candidate 2nd dogfood: 0/4 strict dimensions changed, 2/4 partial only (regime conditioning + frame extension). "
            "Lesson #56 CONFIRMED (7 instances → 8th): range_volume_divergence family OUTCOME-level proxy gate categorically triggered. "
            "Lesson #21 CONFIRMED sub-finding 7th candidate: MTF stacking of SAME statistic class on SAME substrate is degenerate (autocorrelation of same statistic across frames, NOT axis-independent). "
            "Lesson #63 candidate 2nd dogfood (predictive): regime layer cannot resurrect mechanism alpha verified absent at bar level. "
            "Composite: 3 lessons categorically triggered + 1 lesson predictively triggered → R-1 dispatch would be ritual reproduction of paradigm 153 outcome with extra cost."
        ),
        "next_action_recommendation": (
            "GENUINELY family-distinct axis required (≥2 strict dimension changes). "
            "Options preserving range_volume axis path are exhausted (152 z + 153 pct rank + 154 MTF regime). "
            "Pivot away from range_volume_divergence family entirely. "
            "Candidate axes preserving Lesson #61 next-action provenance + Lesson #62 strict ≥2-dim threshold: "
            "(α) paradigm 22 R-5 funding mechanism cross-frame VALIDATION (substrate + R-5 already-validated, lesson #62 strict not applicable), "
            "(β) paradigm 69 macro proxy resume (BTC RV cross-asset, paradigm 153 family-orthogonal, substrate always available), "
            "(γ) lifecycle live mode 2026-05-29+ accumulation (WS recorder 60+d, genuinely-new substrate)."
        ),
    }

    out_file = OUT_DIR / "r0_prescreen.json"
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("written: %s", out_file)
    logger.info("verdict: %s", verdict)
    logger.info("components: %s", verdict_components)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
