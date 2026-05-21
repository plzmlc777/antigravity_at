# paradigm 175 (paradigm 24 R-5 narrow-scope expansion screening — cross-family Lesson #70 verification)

**Slug**: `paradigm_24_r5_narrow_scope_expansion_screening_deep_univ_cross_family_lesson_70_verification`
**Dispatch**: 2026-05-21 KST
**Track classification**: R-5 expansion screening (paradigm counter NOT increased)
**Source**: paradigm 24 R-5 LIVE (DOGEUSDT 9.0σ / SOLUSDT 5.4σ / LDOUSDT 5.7σ seeded 2026-05-06, **track 최강 R-5 시드**)
**Universe**: 17 syms expansion (paradigm 173 deep 10 minus SOL + paradigm 174 mid-cap 10 minus DOGE/LDO)
**Goal**: identify expansion-eligible syms across paradigm 24 cohort + Lesson #70 cross-family generalization verification (3rd dogfood)

## Canonical paradigm 24 R-5 spec (replicated exactly from `gate_eval__3_seeds.md`)

```
zwin           = 30        # 30-day rolling premium z-score
entry_z        = 2.0
hold_days      = 5         # 5-day hold
sl_pct         = 0.05      # 5% stop loss
fee_rate       = 0.0004    # per side (8 bp round-trip)
capital        = 1_000_000
train_frac     = 0.5       # paradigm 24 used 50/50 train-test; screening uses full window (R-5 expansion screening pattern from paradigm 173/174)
mode           = follow    # momentum follow (NOT mean-revert) — premium high → LONG, premium low → SHORT
```

**Source DB**: `runs/premium_index/{symbol}_premium.joblib` (1d aggregated premium klines, 2.19yr coverage)
**Price source**: `ohlcv` DB table, `time_frame='1m'` → resample 1d UTC last (paradigm 24 source pattern)

## R-0 inventory prescreen (Lesson #69 5-item strict template, **10th post-CONFIRMED dogfood**)

### Item 1: Lesson #61 amendment slug grep
- Existing artifacts in `runs/research_track/premium_index_zscore/`: full R-1 sweep (z=1.0/1.5/2.0/2.5 × h=3/5/10), R-2 z=1.5+2.0 h=5 multi-symbol, R-3 AVAX follow z=2.0 h=5, gate_eval__3_seeds.md (DOGE/SOL/LDO 5/5 strict)
- Existing paper sessions: `configs/paper_sessions/{DOGE,SOL,LDO}USDT_premium_index_zscore.json` (paradigm 24 R-5 LIVE)
- Existing R-5 expansion screening artifacts (paradigm 22 funding_carry): paradigm 173 (10 deep) + paradigm 174 (10 mid-cap) both NO_EXPANSION_ELIGIBLE
- **No prior paradigm 24 expansion screening artifact** — first dispatch on this paradigm
- This is R-5 LIVE survivor extension (Lesson #61 amendment: family-distinct exempt for cohort expansion track)

### Item 2: Lesson #28 amendment substrate-shape audit (**10th dogfood**)
- **Substrate-existence (premium joblib)**: 17/17 PASS — all targets in `runs/premium_index/` with 2.19yr coverage (Feb 2024 → May 2026, n=798-800 days each)
- **Substrate-existence (1m ohlcv DB)**: 15/17 STRONG PASS (2024-02-23 → 2026-05-01/02), **2/17 PARTIAL** — BTCUSDT and ADAUSDT have only ~5 months 1m data (2025-12-22 → 2026-05-13) → OOS shorter for these
- **Substrate-shape (zwin=30 warm-up)**: PASS — 800-30 ≈ 770 valid daily bars per sym
- **Verdict**: STRONG PASS for 15 syms / ADVISORY (Lesson #30 short-window) for BTCUSDT/ADAUSDT

### Item 3: Lesson #11 sample density
- paradigm 24 R-5 baseline: DOGE 17 / SOL 17 / LDO 13 trades in ~395d OOS (50/50 split of 800d) at z=2.0 h=5
- Screening will use **full 770d window** (~2x OOS days) → expected n_trades per sym: 25-35 (paradigm 173 funding precedent: 41-75; paradigm 24 sparse: 13-17)
- |z|≥2.0 trigger rate empirical ≈ 4-5% (z=2.0 normal tail ≈ 4.6%)
- Per-sym n ≥ 30 cutoff: borderline — paradigm 24 is fundamentally **sparse-trigger paradigm** (1d daily granularity, 23-30 days per trigger average)
- **Verdict**: ADVISORY PASS (sparse but consistent with paradigm 24 R-5 native frequency — life-changing 4-dim trades/yr ≥ 12 should still pass given DOGE 17 trades / ~395d ≈ 15.7/yr)

### Item 4: Lesson #62 DNA 4-dim audit table vs paradigm 24 R-5

| Dimension | paradigm 24 R-5 | paradigm 175 screening | Diff |
|---|---|---|---|
| Statistic class | per-sym 30d premium z, |z|≥2.0 momentum | per-sym 30d premium z, |z|≥2.0 momentum | SAME |
| Universe | DOGE/SOL/LDO narrow | 17 syms expansion (9 deep + 8 mid-cap) | NEW |
| Entry-side | own premium z trigger | own premium z trigger | SAME |
| Mechanism | follow momentum | follow momentum | SAME |
| Hold | 5d | 5d | SAME |

- Strict count: **1/5 (universe only)** — Lesson #62 ≥2 strict FAIL **if** treated as R-1 retry
- **Self-classification**: R-5 expansion screening track (separate lane) — Lesson #62 family-distinct exemption applies per paradigm-architect spec (R-5 LIVE survivor cohort expansion ≠ R-1 retry, paradigm 173/174 precedent)

### Item 5: Lesson #56 family-proxy OUTCOME-LEVEL cross-reference
- Funding family Tier 4 retire = 11 cumulative graveyards (premium family DISTINCT from funding family per `gate_eval__3_seeds.md` §3-G caveat: 1d raw premium ≠ 8h settled clamped funding)
- paradigm 24 R-5 = premium_index family **exception PRESERVED** (3-seed all 5/5 strict cutoff, perm σ track 최강)
- paradigm 175 = exception extension within same R-5 LIVE paradigm cohort hypothesis (same DNA, broader cohort)
- **Verdict**: NEUTRAL (no advisory — same logic as paradigm 173/174 cohort expansion)

## Lesson #70 cross-family verification design

**Lesson #70 (CONFIRMED 자격, 2 funding-family dogfoods)**: *"R-5 LIVE survivor narrow-cohort alpha does NOT transfer to a broader cohort sym-by-sym at the same spec — cohort selection itself is part of the alpha."*

**paradigm 175 = 3rd dogfood, cross-family**:
- If 0/17 eligible → Lesson #70 **CONFIRMED universal property** (cross-family generalizes, paradigm-architect skill 영구 자산화 강화)
- If 1+ eligible → Lesson #70 **funding-family-specific** (paradigm 24 broader subfamily head candidate, expansion candidates for R-5 seed proposal)

## Track classification (self-decision)
**Option A: R-5 expansion screening track** (chosen, paradigm 173/174 precedent)
- paradigm counter NOT increased (cumulative graveyards stays at 170)
- Output: per-sym PASS list → R-5 seed proposal candidates (if any)
- HALT before R-5 deployment (user approval gate STRICT)

## Execution plan
- script: `backend/scripts/research/paradigm_24_r5_narrow_scope_expansion_screening_deep_univ_cross_family_lesson_70_verification.py`
- output: this directory
- runtime expected: ~30s (1m DB pull × 17 syms × ~1.15M rows each → 1d resample → join premium joblib)
