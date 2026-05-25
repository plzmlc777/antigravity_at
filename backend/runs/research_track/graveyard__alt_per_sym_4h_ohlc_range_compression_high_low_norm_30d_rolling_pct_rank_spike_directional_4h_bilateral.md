# GRAVEYARD — paradigm 221 alt_per_sym_4h_ohlc_range_compression_high_low_norm_30d_rolling_pct_rank_spike_directional_4h_bilateral

**Verdict**: `BROAD_FALSIFIED_FEE_FLOOR_OR_NO_ALPHA`  
**Phase**: R-1  
**Date**: 2026-05-25 (KST)

## Hypothesis
Lesson #40 prescription 2nd 처방 (paradigm 220 R-0 HALT structural threshold infeasibility reformulation).
- statistic: `(high-low)/(high+low)` bounded [0,1]
- trigger: rolling 30d percentile rank ≥ 0.95 (A wide) / ≤ 0.05 (B compressed)
- direction: signed bilateral 4-quadrant SNT (cell A bar UP × LONG / cell B bar DOWN × SHORT disjoint)
- hold: 4h primary + 8h/12h/24h sweep
- universe: 20 alts (paradigm 198 cohort)

## R-1 Primary (4h) Results

| Quadrant | n | mean_bp | obs_t | sig_t_excess | ci_lower_bp | three_gate | Concentration | Concentration_Gate |
|---|---|---|---|---|---|---|---|---|
| A_focus wide UP LONG | 2714 | +17.95 | +2.90 | +4.13 | +5.81 | **PASS** | q=7/10 sym=1/20 | **FAIL** (sym_ci_pos 5%) |
| A_mirror wide UP SHORT | 2714 | -33.95 | -5.48 | -2.70 | -46.01 | FAIL | q=2/10 sym=0/20 | FAIL |
| B_same compressed DOWN SHORT | 2925 | +2.67 | +0.98 | +2.64 | -2.83 | FAIL (ci_lower<0) | q=7/10 sym=1/20 | FAIL |
| B_mirror compressed DOWN LONG | 2925 | -18.67 | -6.84 | -4.48 | -24.14 | FAIL | q=0/10 sym=0/20 | FAIL |

**Hold sweep (8h/12h/24h)**: 0 sweep PASS cells (Lesson #37 full scan executed, none).

## Failure Mechanism — A_focus 3-gate PASS Concentration FAIL

A_focus_wide_UP_LONG cleared 3-gate (sig_t_ex +4.13, ci_lower +5.81bp, perm_p_above 0.000) but Concentration Gate FAILED:
- per-quarter t-stat: 7/10 positive (q_pos_t_ratio 0.70 PASS) ✓
- per-symbol bootstrap ci_pos: **1/20 (DOTUSDT only)** — sym_ci_pos_ratio 0.05 ≪ 0.30 threshold FAIL
- top-5 means (DOGE +53, WLD +49, DOT +42, ADA +40, XRP +37) — concentrated breadth, but only DOT ci_lower > 0 due to per-sym n ≈ 130-150

Aggregate signal is **panel-pooled artifact**: cross-section averages to +18bp, but no single alt (except DOT) reliably reproduces alpha.

## Lesson #69 9-Item Template Verdicts

- **Item 1 DNA grep**: `range_compression_directional_break_alt_30m_240m` 1 hit BUT distinct (30m tortuosity z on 14-sym 1m cache, vs 4h bounded ratio pct_rank on 20 alts 4h cache). DNA 5/6 distinct PASS.
- **Item 2 substrate**: 21 syms × 4h × 2.24yr cache verified at `runs/ohlcv_cache_12col/{sym}_4h.joblib`. Lesson #72 4h hold × 4h granularity match PASS.
- **Item 3 sample density**: 5% pct_rank rate × 20 syms × 4920 bars ≈ 5609 events/cell (A) / 5797 (B). Lesson #11 PASS (paradigm 220 cell B infeasibility avoided — Lesson #40 prescription verified).
- **Item 4 DNA 5/5 strict**: vs paradigm 220 distinct via bounded normalization + pct rank (Lesson #40 reformulation). vs paradigm 124/211/195+196/219/127+128 all distinct.
- **Item 5 family-proxy**: bounded range compression + percentile rank composite class (new).
- **Item 6 alpha decay 11th operational**: **A_focus 2024 +15bp → 2025 +30bp → 2026 -12bp monotonic decay CONFIRMED**. Pattern P1 (2026 era-universal decay) **9th consecutive instance** + **2026 era-universal 7th instance** → elevation to formal-universal-2026-era candidate strengthened.
- **Item 7 cross-set asymmetry**: |A|=5609 |B|=5797 ratio 0.968 SYMMETRIC (paradigm 220 R-0 HALT cell B infeasibility cleanly resolved). Lesson #39 sub-class A test: a_symmetric=True b_symmetric=True BUT all_negative=False (A_focus +17.95, B_same +2.67) → sub-class A **NOT triggered** (9th cross-set measurement, paradigm 206/207/210/211/212/215/218/219/220 ratio family + 221).
- **Item 8 Concentration + Temporal Independence**: A_focus_continuation only sym_ci_pos 1/20 = 5% — Concentration Gate FAIL.
- **Item 9 Life-changing 4-dim STRUCTURAL prescreen 5th operational**: util_pct_estimate **2.90%** ≪ 30% threshold STRUCTURAL FAIL risk **CONFIRMED ex ante** AND verified ex post (A_focus per-trade edge +0.18% × util ~3% × 20 syms diversified = NOT life-changing 4-dim). paradigm 215+218+219 sparse-trigger 4h bilateral util ceiling pattern **5th instance** — STRUCTURAL FAIL prescreen pattern PROMOTION 자격 STRENGTHENED.

## Lesson #39 sub-class B (mechanism-inverted) check

Unconditional baseline (all bars × LONG @ 4h): n=98,380 mean_bp **-7.17 t=-10.61** — strong universe-wide negative drift in 4h LONG. A_focus +17.95bp gross vs uncond -7.17bp = **+25.12bp differential** indicates genuine wide-bar-up continuation signal vs baseline, NOT mechanism inversion (paradigm 110 sub-class B excluded).

## Lesson #42 22nd dogfood (B_mirror cell)

B_mirror compressed DOWN LONG: n=2925 mean_bp **-18.67** vs uncond -7.17bp = -11.50bp incremental NEGATIVE — Lesson #42 12th NEGATIVE instance (running 10 CONFIRMED / 12 NEGATIVE / 1 PASS_AS_ARTIFACT post-update). Compressed bar DOWN LONG reversal hypothesis broadly rejected.

## Lesson #40 prescription 2nd 처방 — partial functional

paradigm 220 R-0 HALT (structural threshold infeasibility on non-negative aggregate). Reformulation with bounded ratio + percentile rank successfully:
- ✓ Restored cell B feasibility (5797 events vs paradigm 220 0)
- ✓ Symmetric cross-set ratio 0.968
- ✓ 4-quadrant SNT executed without structural blocker
- ✗ Underlying mechanism (bounded range compression as directional alpha) NOT alpha-bearing at panel level
- ✗ A_focus aggregate PASS confounded by single-symbol DOTUSDT carry

**Lesson #40 prescription = functional (1st paradigm 215 CONFIRMED) but 2nd 처방 partial: enables R-1 dispatch but does not synthesize panel alpha. Prescription methodologically validated, mechanism scope independently constrained.**

## Pattern P1 — 2026 era-universal decay 7th instance

A_focus: 2024 t=+1.59 / 2025 t=+3.08 / 2026 t=-0.94 — monotonic decay through 2026 (alpha decay confirmed). 7th 2026-era universal decay instance. paradigm 87/136/202/198 series cross-family pattern.

**Elevation 자격 STRENGTHENED**: 2026 era-universal decay 7 confirmed → recommend formal-universal-2026 promotion at 8+ instances.

## paradigm 222 권고

- Lesson #40 prescription 2nd 처방 = methodologically functional but mechanism non-alpha at panel scope
- bounded range compression + percentile rank composite class advisory (1/1 dispatch broad-falsified)
- **DOTUSDT-only carry** suggests single-symbol idiosyncratic mechanism — Lesson #67 ESCAPE per-sym idiosyncratic candidate (Lesson #67 chain extension)
- Item 9 STRUCTURAL prescreen: sparse-trigger 4h bilateral util ceiling **5 operational instances** (paradigm 215+218+219+220 R-0 HALT + 221) → promotion 자격 자격 자격 reinforced
- Pattern P1 2026-era universal decay 7/8 → next dispatch 8th instance crosses elevation threshold
- 다음 권고: **non-4h-hold class** (1h intraday execution / multi-day swing) OR **non-bilateral-SNT class** (single-direction strict event) — sparse-trigger 4h util ceiling 회피 의무

## 산출물

- code: `backend/scripts/research/alt_per_sym_4h_ohlc_range_compression_high_low_norm_30d_rolling_pct_rank_spike_directional_4h_bilateral_r1.py`
- metrics: `backend/runs/research_track/alt_per_sym_4h_ohlc_range_compression_high_low_norm_30d_rolling_pct_rank_spike_directional_4h_bilateral/r1__metrics.json`
- graveyard: this file
