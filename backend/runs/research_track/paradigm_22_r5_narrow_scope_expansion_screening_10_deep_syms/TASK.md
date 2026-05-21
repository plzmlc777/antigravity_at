# paradigm 22 R-5 narrow-scope expansion screening — 10 deep syms

**Slug**: `paradigm_22_r5_narrow_scope_expansion_screening_10_deep_syms`
**Dispatch date**: 2026-05-21 KST
**Track classification**: R-5 expansion screening (paradigm counter NOT increased)
**Source**: paradigm 22 R-5 LIVE survivor (HBARUSDT/AXSUSDT/COMPUSDT seeded 2026-05-04)
**Universe**: paradigm 170 funding DB asset (10 deep syms × 2.25yr × 24,660 funding records)
**Goal**: identify expansion-eligible syms among BTCUSDT/ETHUSDT/SOLUSDT/LINKUSDT/ADAUSDT/DOTUSDT/XRPUSDT/BNBUSDT/BCHUSDT/LTCUSDT

## Canonical paradigm 22 R-5 v4 spec (replicated exactly)
- `lookback_funding_periods = 30` (30 × 8h = 10 days)
- `entry_z = 2.5`
- `exit_z = 0.5`  ← (per actual `paper_seed_proposal__{HBAR,AXS,COMP}USDT.json`, NOT 1.0 from task brief)
- `max_hold_funding_periods = 7` (~56h)
- `sl_pct = 0.03`
- `fee_rate = 0.0004` per side (8 bp round-trip)
- Mode: mean-reversion (z>+2.5 SHORT / z<−2.5 LONG)
- Source: `binance_funding_rate` DB

## R-0 inventory prescreen (Lesson #69 5-item strict, 8th post-CONFIRMED dogfood)

### Item 1: Lesson #61 amendment slug grep
- Existing `funding_carry/` artifacts: paper_seed_proposal__{HBAR,AXS,COMP}USDT.json, full sweep CSVs/metrics, gate_eval_v4__{HBAR,AXS,COMP}.md
- Existing `funding_dispersion/` artifacts: paper_seed_proposal__ETCUSDT.json (cross-sectional level z, separate paradigm)
- No prior paradigm 22 expansion screening artifact for 10 deep syms — first dispatch
- This is R-5 LIVE survivor extension (Lesson #61 amendment: family-distinct exempt for cohort expansion track)

### Item 2: Lesson #28 amendment substrate-shape audit (8th dogfood)
- **Substrate-existence**: PASS (paradigm 170 DB verified — 10 syms × 2466 funding records each, 2024-02-19 → 2026-05-21)
- **Substrate-shape**: PASS (30-period rolling z computable for each sym; warm-up = 30 periods ≈ 10d, valid window 2,436 / sym)
- **Verdict**: STRONG PASS

### Item 3: Lesson #11 sample density
- Per-sym n_trades empirical (post-screening): 41~75 / sym × 2.25yr
- Per-sym per-year trades 18~34 (above per-cell ≥30 cutoff at full window)
- **Verdict**: PASS (sample density sufficient for sym-by-sym screening)

### Item 4: Lesson #62 DNA 4-dim audit table vs paradigm 22 R-5
| Dimension | paradigm 22 R-5 | paradigm 173 screening | Diff |
|---|---|---|---|
| Statistic class | per-sym 30d funding z |z|≥2.5 MR | per-sym 30d funding z |z|≥2.5 MR | SAME |
| Universe | HBAR/AXS/COMP narrow | 10 deep syms expansion | NEW |
| Entry-side | own funding z exit | own funding z exit | SAME |
| Mechanism | MR carry harvest | MR carry harvest | SAME |
| Hold | 7×8h = 56h max | 7×8h = 56h max | SAME |

- Strict count: 1/5 (universe only) — Lesson #62 ≥2 strict FAIL **if** treated as R-1 retry
- **Self-classification**: R-5 expansion screening track (separate lane) — Lesson #62 family-distinct exemption applies per paradigm-architect spec (R-5 LIVE survivor cohort expansion ≠ R-1 retry)

### Item 5: Lesson #56 family-proxy OUTCOME-LEVEL cross-reference
- Funding family Tier 4 retire: 11 cumulative (73/79/96/97/98/99/103/141/...)
- paradigm 22 R-5 = funding family **exception PRESERVED**
- paradigm 173 = exception extension (same DNA, broader cohort) ≠ family-proxy violation
- **Verdict**: NEUTRAL (no advisory)

## Track classification (self-decision)
**Option A: R-5 expansion screening track** (chosen)
- paradigm counter NOT increased (cumulative graveyards stays at 170)
- Output: per-sym PASS list → R-5 seed proposal candidates (if any)
- HALT before R-5 deployment (user approval gate STRICT per `feedback_credentials_in_db.md` / R-5 deploy protocol)

## Execution
- script: `backend/scripts/research/paradigm_22_r5_narrow_scope_expansion_screening_10_deep_syms.py`
- output: this directory
- runtime: ~0.5s (DB asset already cached, simple per-sym sweep)

## Result summary
- n_syms_evaluated: 10
- n_three_gate_pass: **0**
- n_life_changing_pass: **0**
- n_r5_expansion_eligible: **0**
- Verdict: **NO_R5_EXPANSION_ELIGIBLE_SYMS**

See `screening_verdict.md` for detail interpretation.
