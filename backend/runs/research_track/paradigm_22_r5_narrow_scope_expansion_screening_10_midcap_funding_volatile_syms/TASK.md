# paradigm 22 R-5 narrow-scope expansion screening — 10 mid-cap funding-volatile syms

**Slug**: `paradigm_22_r5_narrow_scope_expansion_screening_10_midcap_funding_volatile_syms`
**Dispatch date**: 2026-05-21 KST
**Track classification**: R-5 expansion screening (paradigm counter NOT increased — paradigm 174 = Option α 2nd dogfood lane)
**Source**: paradigm 22 R-5 LIVE survivor (HBARUSDT/AXSUSDT/COMPUSDT seeded 2026-05-04)
**Universe**: 10 mid-cap funding-volatile syms (DOGE/LDO/UNI/ETC/AVAX/NEAR/FIL/WLD/JUP/PYTH)
**Goal**: identify expansion-eligible syms among the mid-cap funding-volatile cohort
**Lesson #70 candidate 2nd dogfood**: confirm/refute narrow-cohort alpha non-transferability hypothesis

## Background — Lesson #70 candidate (from paradigm 173 1st dogfood)
- paradigm 173 (10 deep syms BTC/ETH/SOL/LINK/ADA/DOT/XRP/BNB/BCH/LTC) → **0/10 eligible**
- Hypothesis: paradigm 22 alpha is **cohort-specific** — mid-cap funding-volatile syms have funding crowdedness inefficiency (smaller capital, less arbitraged) → MR carry harvest premium real, while deep majors have well-arbitraged efficient funding → no inefficiency
- This dispatch (paradigm 174) tests the **mid-cap cohort** with same canonical paradigm 22 R-5 v4 spec

## Canonical paradigm 22 R-5 v4 spec (replicated exactly)
- `lookback_funding_periods = 30`
- `entry_z = 2.5`
- `exit_z = 0.5` (per actual `paper_seed_proposal__{HBAR,AXS,COMP}USDT.json`)
- `max_hold_funding_periods = 7`
- `sl_pct = 0.03`
- `fee_rate = 0.0004` per side (8 bp round-trip)
- Mode: mean-reversion (z>+2.5 SHORT / z<−2.5 LONG)
- Source: `binance_funding_rate` DB

## R-0 inventory prescreen (Lesson #69 5-item strict, 9th post-CONFIRMED dogfood)

### Item 1: Lesson #61 amendment slug grep
- paradigm 22 R-5 + paradigm 173 R-5 expansion (10 deep syms) cross-reference
- paradigm 173 verdict: NO_R5_EXPANSION_ELIGIBLE_SYMS (deep-liquid cohort) — paradigm 174 = mid-cap cohort 2nd dogfood
- No prior paradigm 174 mid-cap expansion screening artifact — first dispatch
- R-5 LIVE survivor extension (Lesson #61 amendment: family-distinct exempt for cohort expansion track)

### Item 2: Lesson #28 amendment substrate-shape audit (9th dogfood)
- **Substrate-existence post-backfill**: PASS (10/10 syms × 2,466 (8h) or 4,932 (4h) funding records each, 2024-02-19 → 2026-05-21)
- **Substrate-shape per-sym**:
  - 8/10 (DOGE/LDO/UNI/ETC/AVAX/NEAR/FIL/WLD): 8h funding cycle, n=2466 (clean)
  - 2/10 (JUP/PYTH): **4h funding cycle, n=4932** (double cadence — common for newer listings)
- **4h cycle handling**: paradigm 22 R-5 v4 spec preserves period-count semantics (lookback=30 periods, max_hold=7 periods) → JUP/PYTH effective windows scale to 4h (lookback=5d vs 10d on 8h syms; max_hold=28h vs 56h)
- **Verdict**: STRONG PASS with JUP/PYTH cycle-frequency flag noted

### Item 3: Lesson #11 sample density
- Per-sym expected events: ~25-75 (paradigm 173 empirical precedent across similar liquidity tier)
- 8/10 sym 2466 periods × ~1% |z|≥2.5 → ~25 expected triggers
- 2/10 (JUP/PYTH) 4932 periods × ~1% → ~50 expected triggers
- **Verdict**: PASS (sample density sufficient per-sym)

### Item 4: Lesson #62 DNA 4-dim audit table

| Dimension | paradigm 22 R-5 | paradigm 173 screening | paradigm 174 (this) | Diff vs paradigm 22 |
|---|---|---|---|---|
| Statistic class | per-sym 30d funding z |z|≥2.5 MR | same | same | SAME |
| Universe | HBAR/AXS/COMP narrow | 10 deep syms | 10 mid-cap funding-volatile | NEW |
| Entry-side | own funding z exit | same | same | SAME |
| Mechanism | MR carry harvest | same | same | SAME |
| Hold | 7×8h | 7×8h | 7×8h (JUP/PYTH 7×4h) | SAME (period-count) |

- Strict count: 1/5 (universe only) — R-5 expansion screening track family-distinct exemption applies
- Self-classification: **R-5 expansion screening track** (paradigm 173 precedent), counter NOT increased

### Item 5: Lesson #56 family-proxy OUTCOME-LEVEL cross-reference
- paradigm 22 R-5 = funding family **exception PRESERVED**
- paradigm 174 = exception extension within same R-5 LIVE paradigm cohort hypothesis (mid-cap variant)
- **Verdict**: NEUTRAL (same as paradigm 173)

## Track classification (self-decision)
**R-5 expansion screening track** (Option A, paradigm 173 lane continued)
- paradigm counter NOT increased (stays at 172, cumulative graveyards stays at 170)
- Output: per-sym PASS list → R-5 seed proposal candidates (if any)
- HALT before R-5 deployment (user approval gate STRICT)

## Lesson #70 candidate 2nd dogfood outcomes

| Outcome | Lesson #70 verdict |
|---|---|
| 0/10 mid-cap syms eligible | **Lesson #70 CONFIRMED 자격** — narrow-cohort alpha non-transferable to any broader cohort sym-by-sym at same spec, regardless of liquidity tier |
| 1+ mid-cap syms eligible | **Partial refutation** — mid-cap cohort transferability demonstrated, narrow-cohort alpha cohort-specific BUT extends to similar liquidity tier; paradigm 22 R-5 expansion candidates discovered |

## Execution

- Substrate backfill (Step 1): `python3 fetch_binance_metrics.py --source funding --funding-days 822 --symbols DOGEUSDT,LDOUSDT,UNIUSDT,ETCUSDT,AVAXUSDT,NEARUSDT,FILUSDT,WLDUSDT,JUPUSDT,PYTHUSDT` — **completed in ~10s**, 29,592 funding records inserted/upserted
- Screening script (Step 2): `backend/scripts/research/paradigm_22_r5_narrow_scope_expansion_screening_10_midcap_funding_volatile_syms.py`
- Output dir: this directory
- Expected runtime: ~1-2s (DB asset ready, simple per-sym sweep)
