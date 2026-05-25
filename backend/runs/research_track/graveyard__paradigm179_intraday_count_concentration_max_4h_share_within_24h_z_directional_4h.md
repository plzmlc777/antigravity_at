# Graveyard — paradigm 179 intraday_count_concentration_max_4h_share_within_24h_z_directional_4h

**Verdict**: `NARROW_SCOPE_LIFE_CHANGING_FAIL`
**Phase reached**: R-2 walk-forward
**Date graveyarded**: 2026-05-22 KST
**Host**: local paradigm-architect agent
**Counter increment**: paradigm 179 (R-2 graveyard)

## Reason

Lesson #20 4-cond audit conds 1-3 PASS (three-gate full-cohort + Concentration full-cohort + WF n_folds_pass 3/5 zero-margin), cond4 life-changing 4-dim FAIL both modes:
- Sparse-strict: per-trade edge 0.39% (target ≥ 2%) + capital_util 5.25% (target ≥ 30%) FAIL
- High-freq diffuse: util 5.25% FAIL (portfolio_alpha 23.77% PASS, sharpe 2.59 PASS)

## Lesson Reference

- **Lesson #20** narrow-scope sign-cond 4-cond all-PASS (statistically achieved here at 7-deep narrow cohort, mechanism gated by cond4)
- **Lesson #26** temporal WF n_folds_pass ≥ 3/5 (met exactly at 3/5, zero margin — fold 4 universal 2026Q1+ failure)
- **NARROW_SCOPE_LIFE_CHANGING_FAIL verdict category** ([[feedback-narrow-scope-life-changing-fail-verdict]]) — 3rd CONFIRMED dogfood (paradigm 95, 99, 179)
- **[[feedback-life-changing-strategy-criterion]]** dual-mode evaluation — both modes blocked by structural capital_util limit
- **Potential Lesson #71 candidate** (not yet confirmed; requires 4th dogfood): "High-freq sparse-trigger paradigms structurally cap capital utilization at ~5-7%"

## Key metrics

```
universe: 7 deep-sym (BTC/ETH/SOL/XRP/DOGE/BNB/LINK)
cell: B_same_sign 8h | trigger |z|>=2 max_share rolling-90d
n_total = 796, span 2024-05-06 -> 2026-04-28 (1.98 yr)

walk-forward 5-fold (chronological):
  fold 0 (2024-05 -> 2024-11): n=159 +53.5bp sigex +3.06 — three-gate PASS
  fold 1 (2024-11 -> 2025-02): n=159 +44.7bp sigex +1.77 — FAIL
  fold 2 (2025-02 -> 2025-08): n=159 +56.4bp sigex +3.80 — three-gate + conc PASS
  fold 3 (2025-08 -> 2025-12): n=159 +66.2bp sigex +4.00 — three-gate + conc PASS
  fold 4 (2025-12 -> 2026-04): n=160 -25.7bp sigex -1.45 — FAIL (0/7 syms ci_pos)

n_folds_pass = 3/5 (Lesson #26 PASS, zero margin)

life-changing 4-dim dual-mode:
  sparse_strict: 2/4 gates PASS (trades_yr 403 + sharpe 2.59 PASS; edge 0.39% + util 5.25% FAIL)
  high_freq_diffuse: 2/3 gates PASS (alpha 23.77% + sharpe 2.59 PASS; util 5.25% FAIL)
  any_mode_pass = FALSE → cond4 FAIL → graveyard
```

## Implication

- mechanism (max_share concentration + DOWN bar → SHORT continuation 8h) statistically real and validated 2 of 3 chronological halves
- recent 2026Q1+ regime hostile, universal 7/7 syms negative
- structural capital_util limit ~5% for 8h hold × 1-2/wk trigger per sym blocks life-changing classification
- mechanism inversion (Option β LOW z<=-2) blocked by Lesson #40 structural threshold infeasibility on bounded non-negative statistic

## Artifacts

- R-1 script: `backend/scripts/research/paradigm179_..._r1.py`
- R-1 stratify: `backend/scripts/research/paradigm179_..._r1_stratify.py`
- R-2 script: `backend/scripts/research/paradigm179_..._r2.py`
- R-1 metrics: `backend/runs/research_track/paradigm179_.../r1__metrics.json`
- R-1 supplement: `backend/runs/research_track/paradigm179_.../r1__stratify_supplement.json`
- R-2 metrics: `backend/runs/research_track/paradigm179_.../r2__metrics.json`
- R-1 verdict: `backend/runs/research_track/paradigm179_.../r1_verdict.md`
- R-2 verdict: `backend/runs/research_track/paradigm179_.../r2_verdict.md`
- INDEX.json entry: `paradigm_179_..._narrow_scope_life_changing_fail` (renamed from `..._concentrated_r1_pass`)
