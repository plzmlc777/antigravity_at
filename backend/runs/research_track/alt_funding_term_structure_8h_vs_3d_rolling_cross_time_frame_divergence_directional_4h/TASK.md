# paradigm 172 — alt_funding_term_structure_8h_vs_3d_rolling_cross_time_frame_divergence_directional_4h

**Status**: R-0 INVENTORY HALT (3rd in row: paradigm 169 → 171 → 172)
**Date (KST)**: 2026-05-21 22:36 KST
**Phase**: R-0 (R-1 NOT DISPATCHED)
**Verdict**: `R0_INVENTORY_HALT_LESSON_62_DNA_COLLISION_LESSON_56_FAMILY_PROXY_OUTCOME`

## Hypothesis (proposed Option γ2 from paradigm 171 next-action)

Per-symbol funding rate cross-time-frame divergence: (current 8h funding) - (3-day rolling
mean funding, 24-bar lookback at 4h cadence ≈ 9 funding cycles at 8h cadence).
|z| >= 2.0 outlier → directional alpha 4h hold.

- A focus: current > 3d_mean + 2σ (acceleration) → SHORT continuation (leverage build-up
  → correction)
- A mirror: current > 3d_mean + 2σ × LONG (continuation)
- B same-sign: current < 3d_mean - 2σ (deceleration) → LONG continuation (leverage unwind
  → bounce)
- B mirror: current < 3d_mean - 2σ × SHORT (continuation)

Universe: 10 deep syms (paradigm 170 funding DB cohort)
Hold: 4h primary + 8h/12h sweep
Substrate: paradigm 170 binance_funding_rate DB (10 syms × 2.25yr × 24,660 rows verified)

## R-0 Lesson #69 5-item strict template (7th post-CONFIRMED dogfood)

### Item 1: Lesson #61 amendment PERMANENT slug grep
**Result**: PASS (no slug match)
- `ls research_track/ | grep -iE "funding_term_structure|cross_time_frame"` → 0 matches
- Adjacent slugs found (NOT 5/6 DNA duplicates):
  - `funding_cycle_8h_differential_velocity_per_sym` (paradigm 99 graveyard)
  - `funding_velocity_cross_section_dispersion` (paradigm 97 graveyard)
  - `funding_carry` (paradigm 22 R-5 LIVE)

### Item 2: Lesson #28 amendment substrate-shape audit (7th dogfood)
**Result**: PASS STRONG
- Substrate-existence: `binance_funding_rate` DB (paradigm 170 asset, 10 syms × 2.25yr ×
  24,660 records verified)
- Substrate-shape:
  - 8h funding cadence × 3-day rolling = 9-bar lookback feasibility PASS
  - Per-sym time-frame divergence (current - rolling_mean) computation straightforward
  - 24,660 records / 10 syms / 2.25yr ≈ 2,466 cycles/sym = adequate density
- Single-source paradigm 170 DB only (no quarterly substrate dependency, no external API)

### Item 3: Lesson #11 sample density
**Result**: PASS expected
- 10 syms × 2.25yr × 3 funding cycles/day = 24,660 base events
- |z| ≥ 2.0 cross-time-frame trigger at ~5% rate (typical for per-sym z) = ~1,233 events
- 4-quadrant SNT per-cell: n ≈ 308 (well above Lesson #11 floor 30)
- Per-quarter n_measurable: 9 quarters × 34 ≈ adequate (above Lesson #26 floor 4 measurable)

### Item 4: Lesson #62 DNA 4-dim audit table (CRITICAL FAIL)

| Axis | paradigm 172 (proposed) | paradigm 99 (BROAD_FALSIFIED_MIRROR_ONLY) | strict distinct? |
|---|---|---|---|
| 1. Data domain | binance_funding_rate DB | binance_funding_rate DB | **SAME** |
| 2. Statistic class | per-sym `current - rolling_mean_3d` (current vs short rolling baseline) | per-sym `Δfunding(t)=funding(t)-funding(t-8h)` rolling z over 30d (90-cycle rolling) | **PROXY-SAME**: both measure "per-sym self-relative funding deviation magnitude over a recent window" |
| 3. Trigger threshold | \|z\|≥2.0 | \|z\|≥2.0 | **SAME** |
| 4. Universe | 10 deep syms (ADA/BCH/BNB/BTC/DOT/ETH/LINK/LTC/SOL/XRP) | 14 syms (incl. ADA/BCH/BNB/BTC/DOGE/ETH/FIL/LINK/LTC/NEAR/SOL/WIF/XRP/AVAX) | **OVERLAP**: 9/10 paradigm 172 syms ∈ paradigm 99 (only DOT new); 64% universe overlap |
| 5. Entry-side | per-sym z trigger per 4h bar (8h funding cycle aligned) | per-sym z trigger per 8h funding cycle | **PROXY-SAME**: triggered by same per-sym z-outlier construct |
| 6. Mechanism | leverage acceleration/deceleration → MR | leverage velocity outlier → MR fade | **PROXY-SAME**: identical mechanism story (per-sym leverage-shift extreme → reversal) |

**Strict distinct count: 0/6 → HARD FAIL of Lesson #62 boundary (≥3/5 strict required)**

**Distinguishing claim audit**:
- User's stated distinction: "paradigm 99 = 30d rolling velocity z, paradigm 172 = 3d rolling
  mean comparison — different time-frame window, different statistic"
- Technical truth: both compute `(per-sym instantaneous deviation) / (per-sym local
  std)`-style z-score. The functional form `current - rolling_mean(W)` differs from
  `Δfunding rolling-z(W)` only in:
  - reference baseline: 3-day mean (paradigm 172) vs 8h prior-cycle (paradigm 99 Δ)
  - normalization window: 24-bar (paradigm 172) vs 90-cycle (paradigm 99)
  - lag structure: 0-lag rolling mean vs 1-cycle Δ
- Empirically, when funding rates exhibit persistence (which they do — paradigm 22 R-5
  exploits this), `current - mean_3d` is **highly correlated** with the integrated path of
  `Δfunding` over the last 9 cycles. Both statistics fire on the **same underlying
  events**: per-sym funding rate deviation from its recent self.
- Under Lesson #56 OUTCOME-LEVEL family-proxy rule, this is the **same axis**. Different
  technical form ≠ different mechanism.

**Verdict**: paradigm 172 statistic is a **near-isomorphic proxy** of paradigm 99 statistic.

### Item 5: Lesson #56 family-proxy OUTCOME-LEVEL cross-reference (CRITICAL FAIL — 18th instance candidate)

**Funding family Tier 4 retire (12 cumulative formal sub-class graveyards)**:

| # | Paradigm | Sub-class | Verdict |
|---|---|---|---|
| 1 | 22 | per-sym funding 30d z-score MR (single-frame point) | **R-5 LIVE** (narrow 3-sym HBAR/AXS/COMP exception) |
| 2 | 73 | funding × OI joint bipolar | BROAD_FALSIFIED |
| 3 | 79 | funding extreme level retry | BROAD_FALSIFIED |
| 4 | 96 | funding sign flip | BROAD_FALSIFIED (anti-direction structural) |
| 5 | 97 | funding velocity cross-section dispersion (cs Δf z) | BROAD_FALSIFIED (fee floor) |
| 6 | 98 | funding regime stratify dispersion | BROAD_FALSIFIED |
| 7 | **99** | **per-sym Δfunding 30d history z-score (velocity z)** | **BROAD_FALSIFIED_MIRROR_ONLY** (LC edge 0.24%, 0/13 syms ci_pos) |
| 8 | 103 | cross-exchange funding spread (Bybit×Binance) | BROAD_FALSIFIED_FEE_FLOOR |
| 9 | 132 | funding × OI × magnitude triple confirm | BROAD_FALSIFIED |
| 10 | 138 | funding raw ±bp | R0_HALT_LESSON_40 structural threshold infeasible |
| 11 | 139 | funding 30d z-score × CVD divergence | R0_HALT_LESSON_40 asymmetric bound inheritance |
| 12 | 141 | funding 30d z-score NEG-only SHORT continuation | BROAD_FALSIFIED (paradigm 22 mirror) |
| 13 | 167 | cross-exchange funding spread Bitget×Binance | (illiquid venue graveyard) |

**OUTCOME-LEVEL family proxy evidence for paradigm 172**:

The closest precedent is **paradigm 99** which tested per-sym velocity z (≈ first-difference
form of paradigm 172's `current - mean_3d` statistic). Outcomes:

- A focus high LONG: n=1,295 mean +12.44bp **sigex +2.03** but ci_lower **-4.31** (three-gate
  FAIL at ci) — exactly fee-floor adjacent, marginal evidence.
- B mirror low LONG: n=1,304 mean +24.00bp **sigex +3.19 ci_lower +5.88 perm_p 0.028
  3-gate PASS** BUT
  - Symmetric LONG bias (both A LONG + B LONG positive → directional drift artifact, NOT
    mechanism alpha — Lesson #8 amendment candidate)
  - Concentration FAIL: 0/13 syms ci_pos
  - Life-changing FAIL: per-trade edge **0.24% (gate ≥ 2.0%, 8x deficit)**

**Family-proxy verdict**: paradigm 99's outcome predicts paradigm 172 outcome with HIGH
confidence:
- 3-gate marginal at best on focus cell (ci just barely fails or marginally passes)
- Concentration likely FAIL (per-sym variance dominates)
- Life-changing FAIL: per-trade edge in the 0.2-0.5% range << 2% gate (paradigm 22 R-5 itself
  passes life-changing only because of narrow 3-sym cohort selection + 8h hold; broad-cohort
  10-sym variants consistently fail life-changing — see paradigm 141)

**Mechanism story analysis**: "current vs 3d rolling mean divergence" tells the same story
as paradigm 99's "Δfunding velocity outlier" — both describe **per-sym leverage shifting
extreme from recent baseline → expected reversal**. Both have been falsified at broad
cross-symbol 4h-hold scope. paradigm 22 R-5 survives ONLY at:
- narrow 3-sym selection (HBAR/AXS/COMP)
- explicit exit-z=1.0 mean-reversion endpoint (not directional hold)
- 8h hold (funding cycle alignment), not 4h

paradigm 172 violates all three of these conditions (broad 10-sym, 4h hold, no exit-z).

**18th Lesson #56 instance candidate**: if executed, paradigm 172 would extend the
family-proxy evidence count from 17 to 18, with the 12th funding family graveyard. The
funding-axis single-signal sub-class space was declared **functionally exhausted** at
paradigm 99 (5th independent falsification) — paradigm 172 is the 7th retry within an
already-retired family.

## Halt verdict

`R0_INVENTORY_HALT_LESSON_62_DNA_COLLISION_LESSON_56_FAMILY_PROXY_OUTCOME`

**Joint failure modes**:
1. **Lesson #62 HARD FAIL 0/6 strict vs paradigm 99** — statistic class is near-isomorphic
   proxy of paradigm 99's velocity z; 9/10 universe overlap; identical trigger threshold
   |z|≥2; identical mechanism story (per-sym self-relative leverage shift extreme → MR).
2. **Lesson #56 OUTCOME-LEVEL family proxy** — 11 cumulative funding family Tier 4 retire
   sub-class graveyards (paradigm 22 R-5 narrow-cohort exception only). Closest precedent
   paradigm 99 explicitly NARROW_SCOPE_LIFE_CHANGING_FAIL (per-trade edge 0.24% << 2% gate)
   + Concentration FAIL (0/13 syms ci_pos) + symmetric LONG bias artifact.
3. **Lesson #11/#23 robust** but moot — sample density adequate but mechanism predicted
   falsified at family-proxy level.

**Not graveyarded** — this is an R-0 inventory halt, NOT a mechanism falsification (no R-1
empirical evidence collected). Counter strategy follows paradigm 171 pattern (substantive
+1 counter increment as separate entry, distinct halt class from paradigm 99).

## paradigm 22 R-5 baseline vs paradigm 172 cross-comparison

| Dimension | paradigm 22 R-5 LIVE (funding_carry) | paradigm 172 proposed |
|---|---|---|
| Statistic | per-sym 30d rolling z(funding) — level z | per-sym current - 3d rolling mean |
| Trigger | \|z\|≥2.5 (also 2.0 sweep) | \|z\|≥2.0 |
| Universe | HBAR/AXS/COMP (3 syms narrow) | 10 deep syms broad |
| Hold | 8h (funding cycle) | 4h (sub-cycle) |
| Exit | exit_z=1.0 (mean-reversion endpoint) | 4h time-based (no mean-reversion exit) |
| LC edge | passes (narrow-cohort selection) | predicted FAIL (paradigm 99 broad-cohort 0.24%) |
| Outcome | R-5 LIVE | predicted BROAD_FALSIFIED_MIRROR_ONLY (paradigm 99 family-proxy) |

paradigm 22 R-5 LIVE is preserved as the lone funding-family R-5 exception. paradigm 172's
broad-cohort 4h-hold configuration directly maps to the falsified broad variants (paradigm
73/79/96/97/98/99/103/132/138/139/141/167), not to paradigm 22's narrow-cohort 8h-MR
configuration.

## paradigm 99 vs paradigm 172 cross-comparison (CRITICAL)

| Dimension | paradigm 99 (BROAD_FALSIFIED_MIRROR_ONLY) | paradigm 172 (proposed) |
|---|---|---|
| Statistic class | per-sym Δfunding(t)=f(t)-f(t-8h) rolling 30d z | per-sym current - 3d rolling mean (functionally: integrated Δfunding over 9 cycles) |
| Time-frame relation | 1-step velocity z over 90-cycle window | 0-lag rolling mean differential over 9-cycle window |
| Mathematical relation | both compute per-sym self-relative funding deviation magnitude | **PROXY-ISOMORPHIC**: when funding has persistence (it does), the two statistics fire on highly correlated events |
| Universe | 14 syms (paradigm 172 universe is subset) | 10 syms (9/10 ⊂ paradigm 99 universe) |
| Trigger | \|z(Δf)\|>2 | \|z(current-mean_3d)\|≥2 |
| Mechanism story | leverage velocity extreme → MR fade | leverage acceleration extreme → MR continuation/bounce |
| Outcome (paradigm 99 actual) | A focus sigex +2.03 ci_lower -4.31 3-gate FAIL; B mirror LONG 3-gate PASS but LC edge 0.24% NARROW_SCOPE_LIFE_CHANGING_FAIL; Concentration 0/13 syms ci_pos | predicted same (per Lesson #56 family-proxy) |

**Verdict**: paradigm 172 is a Lesson #61 amendment **retry-without-substrate-change** of
paradigm 99 with cosmetic statistic-form variation (window size and reference-frame
substitution) but identical underlying mechanism and identical predicted outcome.

## Lesson dogfoods (this halt)

- **Lesson #62 (DNA 4-dim audit table) 12th boundary case** — HARD FAIL 0/6 strict vs
  paradigm 99 captured pre-R-1. Without rigorous proxy-isomorphism analysis, the user's
  surface-level "3d vs 30d window difference" claim could have been accepted; the audit
  correctly classified the two statistics as proxy-same family.
- **Lesson #56 (OUTCOME-LEVEL family proxy) 18th instance candidate** — funding family
  Tier 4 retire 11 cumulative graveyards (paradigm 22 R-5 narrow exception only) predict
  paradigm 172 outcome with HIGH confidence. Closest precedent paradigm 99 (per-sym
  velocity z) explicitly NARROW_SCOPE_LIFE_CHANGING_FAIL.
- **Lesson #61 amendment PERMANENT** retry-exemption analysis — paradigm 172 ≠ paradigm
  99 retry (no substrate change argument); it's a **statistical form variant** of an
  already-falsified mechanism. Lesson #61 amendment retry-exemption applies only to
  substrate-blocked retries (paradigm 171 = paradigm 169 retry after paradigm 170
  unblock), NOT to mechanism-variant retries.
- **Lesson #69 (5-item strict template) 7th post-CONFIRMED dogfood** — caught DNA
  collision before R-1 dispatch. Item 4 (Lesson #62 4-dim audit) was the decisive gate.

## Funding family Tier 4 retire reinforcement (12th sub-class graveyard analogue)

This R-0 halt extends the funding family Tier 4 retire pattern to include **functional-form
variants** (3d rolling mean comparison, in addition to velocity z / sign flip / cross-
section dispersion / regime stratify / per-sym 30d z×CVD / direction inversion). Total
exhausted sub-class space:

1. paradigm 22 (R-5 narrow exception): per-sym 30d level z + 8h MR endpoint exit
2. paradigm 73: funding × OI joint bipolar
3. paradigm 79: extreme level retry
4. paradigm 96: sign flip
5. paradigm 97: cross-section velocity dispersion
6. paradigm 98: regime stratify dispersion
7. paradigm 99: per-sym velocity z
8. paradigm 103: cross-exchange spread (Bybit)
9. paradigm 132: funding × OI × magnitude triple
10. paradigm 138: raw ±bp threshold
11. paradigm 139: per-sym z × CVD
12. paradigm 141: per-sym 30d z NEG-only SHORT continuation
13. paradigm 167: cross-exchange spread (Bitget)
14. **paradigm 172 (this halt): cross-time-frame divergence (current - rolling mean)**

The funding axis variant space (single-source paradigm 170 DB) is now **structurally
exhausted** for single-signal mechanism testing. paradigm 22 R-5 LIVE remains the lone
exception, sustained by narrow-cohort selection + MR endpoint exit (not directional 4h
hold).

## Counter

- Graveyards: 170 unchanged (R-0 halt, not graveyard)
- Non-PASS streak: 39 → **40** (R-0 halt increments streak counter per paradigm 171 pattern)
- Paradigm counter: 171 → **172**
- R-5 LIVE: 11 unchanged
- R-5 yield: 11/172 = **6.40%**
- Tier 4 family retires: 15 unchanged (funding family retire already in effect, no new
  retire)
- **NEW family-proxy advisory**: "funding single-source single-signal cross-time-frame
  variant: paradigm 99 family-proxy + funding Tier 4 retire pattern predicts narrow-scope
  LC FAIL; do not retry within paradigm 170 DB single-source unless paradigm 22 R-5
  narrow-cohort + MR endpoint exit configuration reproduced"

## paradigm 173 next-action 권고

**1순위 Option κ (recommended)**: **paradigm 22 R-5 narrow-scope expansion**.
- paradigm 22 R-5 LIVE is the lone funding-family survivor. Test whether the narrow-cohort
  + MR endpoint exit configuration extends to other deep syms (BTC/ETH/SOL/LINK/ADA/DOT
  from paradigm 170 DB).
- Configuration: per-sym 30d funding z |z|≥2.5, exit_z=1.0 (paradigm 22 spec), 8h hold,
  sym-by-sym screening. Find which subset of 10-sym paradigm 170 cohort sustains paradigm
  22-style narrow MR alpha.
- DNA 4-dim audit: 3/5 strict distinct vs paradigm 22 R-5 (universe expansion is core new
  axis). Lesson #62 boundary PASS expected.
- Family-proxy: paradigm 22 R-5 LIVE direct extension — not a retire-violating retry.

**2순위 Option μ**: **substrate-distinct paradigm dispatch** — exit funding axis entirely.
- WS recorder forward-collection candidates (book_depth, trade tape) — 2026-07-15+ data
  maturity
- Microstructure DB-bound axis (taker_buy_ratio variants, OI velocity sub-axis) — paradigm
  72/127/128 family-proxy advisory caution applies
- Recommend: brainstorm new substrate axis with explicit Lesson #56 family-proxy audit

**3순위 Option ν**: **paper baseline measurement priority transition** — Day 7 baseline
2026-05-28 (D-7) / Day 30 2026-06-03 (D-13) — focus on existing R-5 LIVE 11 paradigm
diagnostics rather than continued R-1 dispatch within exhausted axis spaces.

## 메모리 정책 strict 준수 confirmation

- [[feedback-no-freemium-trial]] — paradigm 170 DB only, no external API
- [[feedback-life-changing-strategy-criterion]] — Lesson #56 family-proxy predicts LC FAIL
  (per-trade edge 0.24% << 2% gate per paradigm 99)
- [[feedback-direct-recommendation]] — R-0 halt with single recommended next-action (Option κ)
- [[feedback-paradigm-campaign-continuous-parallel]] — no pause recommendation, just
  dispatch redirect to paradigm 173 Option κ
- [[feedback-persistence-over-efficiency]] — 40-streak milestone unaffected; halt is
  pre-execution audit catch, not policy pause

**END 2026-05-21 22:36 KST paradigm 172 R-0 INVENTORY HALT** — Lesson #62 HARD FAIL 0/6
strict vs paradigm 99 (statistic class proxy-isomorphic) + Lesson #56 OUTCOME-LEVEL family
proxy 18th instance candidate (funding family Tier 4 retire 11 cumulative graveyards,
closest precedent paradigm 99 NARROW_SCOPE_LIFE_CHANGING_FAIL). Counter 171 → 172,
non-PASS streak 39 → 40. paradigm 173 권고: Option κ paradigm 22 R-5 narrow-scope
expansion (or substrate-distinct pivot Option μ).
