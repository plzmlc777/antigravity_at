# Graveyard — paradigm 156 `btc_funding_rate_p90_regime_alt_directional_4h`

**Date**: 2026-05-21 15:33 KST
**Phase**: R-1 PoC (4-quadrant SNT) — R-2 NOT DISPATCHED
**Verdict**: **BROAD_FALSIFIED**
**Counter**: 155 → 156 (substantive R-1 increment)
**Provenance (Lesson #61)**: paradigm 155 §next-action Option β (paradigm-architect agent 1순위 권고 2026-05-21 15:20 KST) + user explicit dispatch 2026-05-21 15:26 KST

## Hypothesis recap

**Mechanism**: BTC funding rate가 cross-asset macro leverage skew signal로 작동하는지 검증.
- A: BTC funding ≥ p90 (extreme bullish positioning) × 13 alts directional LONG (continuation) / SHORT (reversal)
- B: BTC funding ≤ p10 (extreme bearish positioning) × 13 alts directional LONG (reversal) / SHORT (continuation)

## R-0 prescreen result (all 10 axes PASS)

| Axis | Verdict | Detail |
|---|---|---|
| 1. Family-distinct strict 4-dim (Lesson #62) | ✅ 4/4 STRICT | statistic class + universe scope + entry-side class + mechanism alpha 모두 변경 |
| 2. Substrate (Lesson #28) | ✅ PASS | BTC funding DB 1095 rows × 364d |
| 3. Sample density (Lesson #11) | ✅ PASS | 89-115/cell @ 4q × 4q split |
| 4. SNT 4-quadrant (Lesson #19) | ✅ implemented | A LONG / A SHORT / B LONG / B SHORT 의무 |
| 5. Data window ratio (Lesson #30) | ✅ PASS | BTC funding 99.7% full window |
| 6. Retiming reframe (Lesson #62 CONFIRMED) | ✅ PASS | 4/4 strict, NOT a retiming |
| 7. OUTCOME-LEVEL family proxy (Lesson #56) | ✅ ESCAPE | 4/4 strict ≥3 dimensions distinct |
| 8. Axis stacking (Lesson #21) | ✅ PASS | single trigger × single mechanism |
| 9. Same-bar same-substrate (Lesson #58) | ✅ EXEMPT | cross-substrate (funding DB vs klines) |
| 10. Mirror antipattern | ✅ N/A | sign-cond bilateral is core hypothesis, not auto-mirror |

R-0 PASS → R-1 dispatch authorized.

## R-1 results — 4-quadrant Symmetric Negative Test

| Quadrant | n | gross_mean_bp | net_mean_bp | sigex | perm_p | ci_lower_bp | syms_ci_pos | q_pos_t/q_meas | 3-gate | Conc |
|---|---|---|---|---|---|---|---|---|---|---|
| **A_LONG_focus** (BTC p90 × LONG) | 1702 | +2.13 | **−5.87** | −0.445 | 0.320 | −14.12 | **0/13** | 1/4 (0.25) | FAIL | FAIL |
| **A_SHORT_mirror** (BTC p90 × SHORT) | 1702 | −2.13 | **−10.13** | −0.126 | 0.466 | −18.32 | **0/13** | 1/4 (0.25) | FAIL | FAIL |
| **B_LONG_mirror** (BTC p10 × LONG) | 1279 | +1.37 | **−6.63** | −0.828 | 0.201 | −14.44 | **0/13** | 2/5 (0.40) | FAIL | FAIL |
| **B_SHORT_same_sign** (BTC p10 × SHORT) | 1279 | −1.37 | **−9.37** | −0.442 | 0.325 | −16.77 | **0/13** | 1/5 (0.20) | FAIL | FAIL |

**4/4 quadrants 3-gate FAIL**. **0/52 (cumulative) symbol-quadrant cells ci_lower > 0**. Complete homogeneous negative.

### Hold sweep A LONG (focus)

| hold | n | mean_bp | sigex | 3-gate |
|---|---|---|---|---|
| 240m | 1702 | −5.87 | −0.445 | FAIL |
| 480m | 1702 | **−14.78** | **−2.392** | FAIL |
| 720m | 1702 | −0.82 | −0.015 | FAIL |

Hold sweep all negative; 480m worst (Lesson #15 non-focus PASS 조건 부재).

### Life-changing 4-dim (focus A LONG)

| dim | value | gate |
|---|---|---|
| trades/yr | 840.3 | ✅ PASS (≥12) |
| per-trade edge | **−0.059%** | ❌ FAIL (need ≥+2%) |
| capital util | 38.3% | ✅ PASS (≥30%) |
| ann sharpe | **−0.99** | ❌ FAIL (need ≥1.5) |
| **all_pass** | **False** | 2/4 |

## Mechanism diagnosis

### Finding 1: BTC funding regime carries NEAR-ZERO directional information for alts

Symmetric pair separation analysis (Lesson #39 framework):
- A focus (LONG) mean_bp = −5.87
- A mirror (SHORT) mean_bp = −10.13
- **Mirror-pair separation: 4.26 bp** (LONG outperforms SHORT by 4.26 bp gross at BTC p90)
- Fee floor: 16 bp round-trip

The 4.26 bp gap is **far below fee floor (16 bp)**. Per Lesson #39 sub-class A (broad-uniform-negative both sides), trigger has effectively zero directional information at the bar/4h level. The marginal LONG advantage (+4.26 bp) is consistent with the general unconditional alt LONG bias documented in Lesson #8 amendment candidate (paradigm 99 family) — NOT a paradigm-specific alpha signal.

### Finding 2: BTC funding p90/p10 is a LAGGING positioning marker, not a leading macro driver

- BTC funding measures **already-accrued leverage skew at the cycle close**, not forward demand
- By the time BTC funding hits p90, the bullish positioning is already priced into alts (cross-asset spillover already complete)
- 4h hold window captures only random walk after the trigger
- This mirrors paradigm 96 funding sign flip finding ("lagging marker, not reversal trigger")

### Finding 3: B same-sign (BTC p10 × alt SHORT) quarter concentration WORST (1/5 = 0.20)

Even the directionally most-aligned quadrant (B SHORT, fear-cascade hypothesis) shows quarter concentration at the bottom (1/5 quarters positive t). This rules out a "hidden BTC-bearish-spillover" mechanism that paradigm 70 (BTC RV p90 SHORT) might have hinted at.

## Family-distinct strict 4-dim audit verification (Lesson #62 CONFIRMED, dogfood #4)

| Dimension | paradigm 156 vs funding family (96-99) | Strict change? |
|---|---|---|
| Statistic class | BTC-only macro regime vs per-sym statistics | ✅ STRICT |
| Universe scope | BTC-trigger × 13-alt fan-out vs per-sym self-cond | ✅ STRICT |
| Entry-side class | regime filter continuous vs event boundary | ✅ STRICT |
| Mechanism alpha | macro leverage spillover vs micro funding axis | ✅ STRICT |

**4/4 strict — Lesson #62 successfully PASSED R-0**, and R-1 BROAD_FALSIFIED at the **mechanism level** (not at the family-distinct artifact level). This is a "clean" family-distinct dogfood: the cross-asset macro mechanism was genuinely tested and genuinely falsified — not blocked by retiming reframe issues.

## Funding family Tier 4 retire — extension

paradigm 156 = **7th funding-axis graveyard** (73 + 79 + 96 + 97 + 98 + 99 + 103 + 104 + 147 + 148 + **156**). The 4-dim family-distinct passing did **NOT** rescue the underlying axis: even cross-asset macro reframing of funding regime cannot generate alpha.

**Funding axis exhaustion catalog updated**:
- Per-sym funding statistic (z-score / sign flip / cs velocity / regime stratify): 6 graveyards (73/79/96/97/98/99)
- Cross-exchange funding spread (Binance↔Bybit / Bybit illiquid venue): 2 graveyards (103/104)
- Lead-lag funding delay (cross-exchange OI / cross-exchange OI funding): 2 graveyards (147/148)
- **Macro regime cross-asset (BTC-only funding p90/p10 broadcast)**: 1 graveyard (**156**, NEW sub-class)

paradigm 22 R-5 (per-sym funding z-score MR continuous transform) remains the only funding-axis exception. Macro regime variant **explicitly ruled out**.

## Lessons impact

### Lesson #56 CONFIRMED 9th instance (OUTCOME-LEVEL family proxy)

paradigm 156 passed R-0 OUTCOME-LEVEL family proxy audit (4/4 strict dims), but R-1 outcome converges with funding family graveyard pattern (broad-falsified fee-floor sub-threshold). This reinforces Lesson #56: passing R-0 family-distinct strict 4-dim audit ≠ outcome guarantee — when underlying **alpha axis** is exhausted, even ≥3 strict dimensional changes cannot rescue mechanism. Lesson #56 escalation: even ≥4 strict reformulation (full overhaul) can outcome-converge.

### Lesson #39 sub-class A 4th dogfood (broad-uniform-negative both sides, near-zero directional info)

paradigm 156 4-quadrant pattern fits Lesson #39 sub-class A:
- A_focus −5.87 + A_mirror −10.13 = sum **−15.99 bp ≈ −2 × fee (−16 bp)**
- Mirror separation **4.26 bp ≪ 16 bp fee floor**
- Trigger carries near-zero directional info, paradigm is pure direction-bet + fee drag

This is the 4th paradigm 156 + (108 + 110 prior + paradigm 99 candidate) instance of sub-class A — formal CONFIRMED 자격 reached.

### Lesson #61 (R-0 next-action provenance audit) 3rd dogfood post-confirmation

paradigm 155 §next-action Option β explicitly recommended paradigm 156. R-0 prescreen authorized dispatch (all 10 axes PASS). R-1 BROAD_FALSIFIED with clean attribution to funding-axis exhaustion + cross-asset macro spillover absence. **Provenance chain functioned as intended**: candidate authored by previous agent → R-0 authorization → R-1 substantive test → clean falsification.

### NEW Lesson #67 candidate (1st dogfood) — "macro single-asset trigger × cross-asset broadcast antipattern"

**Hypothesis**: A macro single-asset (BTC) trigger broadcasting to cross-asset universe (alts) absorbs all directional info via cross-asset correlation; conditional alpha cannot survive when correlation > 0.5 (typical for BTC-alt pairs).
- 1st dogfood: paradigm 156 (BTC funding p90/p10 → 13 alts)
- Prior implicit evidence: paradigm 69 (BTC RV p90 × 13 alts — succeeded, but with vol-magnitude filter not regime threshold), paradigm 70 (BTC RV p90 mirror SHORT — failed), paradigm 64 (cross-sec 30d mom — failed)
- Distinguishing factor: paradigm 69's success used **magnitude-conditional volatility regime** + **directional sign filter** + **specific hold (270m)** — a 3-axis specification. paradigm 156 used **regime threshold only** (no magnitude/sign/hold refinement). Single-axis macro broadcast antipattern.
- Required for promotion: 1 more dogfood (e.g., BTC OI velocity regime × cross-asset) or independent macro signal variant.

## Verdict & next action

### Verdict
**BROAD_FALSIFIED** — 4/4 quadrants 3-gate FAIL, 0/52 sym-quadrant ci_pos, mirror separation < fee floor.

### Family classification update
- **Funding axis Tier 4 retire**: 11 cumulative (7 sub-classes), now including macro-cross-asset variant. paradigm 22 R-5 exception only.
- **Lesson #67 candidate (NEW)**: macro single-asset × cross-asset broadcast antipattern (1st dogfood, requires 1 more for CONFIRMED 자격)

### Counter
153 (paradigm 153 R-1 BROAD_FALSIFIED) → 154 (R-0 halt substantive) → 155 (R-0 halt substantive) → **156 (R-1 BROAD_FALSIFIED substantive)** = 27-streak non-PASS, R-5 yield 6.41% (10 R-5 / 156 cumulative).

### Next paradigm 157 recommendation

Given funding axis Tier 4 11-cumulative exhaustion + macro-broadcast antipattern (Lesson #67 candidate) + 27-streak non-PASS:

| Option | Hypothesis | Note |
|---|---|---|
| **α (⭐⭐⭐ 권고)** | `alt_session_boundary_NY_close_anchored_reversal_4h` (NY close 21:00 UTC × 13 alts directional) | **NEW axis class** (time-of-day session boundary), zero substrate cost, paradigm 69-like mechanism reframe with structural anchor (NY close = global de-risking pivot). Family-distinct from funding (different axis class entirely). Memory [[project-life-changing-paradigm-discovery]] archetype C (session boundary) — direct test |
| β | `alt_realized_corr_breakdown_eth_per_pair_directional_4h` (ETH-pair corr breakdown × directional 4h) | INDEX R-0 untried entry. Tests cross-asset breakdown as alpha signal (vs spillover) — opposite of paradigm 156 broadcast mechanism |
| γ | `alt_extreme_24h_drawdown_24h_reversion_long` (overnight reversion of extreme drawdown) | Single-axis mean-reversal post-cascade. Family-distinct from funding (price-only) |

**메타 권고 1순위**: **Option α** — NY close session boundary 21:00 UTC anchor × 13 alts directional 4h. Archetype C (session boundary) memory plan에 명시된 5 archetype 중 untouched 항목. Lesson #67 candidate (cross-asset broadcast antipattern)를 회피하기 위해 trigger 자체가 **time-anchored event** (single global event) — broadcast이지만 macro signal (funding/RV/OI 같은) 아닌 **structural global de-risking pivot**. funding family Tier 4 cross-reference 무관 (axis class 전혀 다름).

⚠️ **CAVEAT**: NY close × 13 alts 변형은 메모리 [[project-life-changing-campaign-session1-halt]]에서 intraday signal incompatibility 경험 있음. **4h hold (sub-5min 아님)** 조건으로 dispatch — fee floor 충족 가능 영역.

## Output artifacts

- code: `backend/scripts/research/paradigm156_r1.py`
- metrics: `backend/runs/research_track/btc_funding_rate_p90_regime_alt_directional_4h/r1__metrics.json`
- task: `backend/runs/research_track/btc_funding_rate_p90_regime_alt_directional_4h/TASK.md`
- graveyard: this file

**END 2026-05-21 15:33 KST paradigm 156 R-1 BROAD_FALSIFIED (4/4 quadrants 3-gate FAIL, 0/52 sym-quadrant ci_pos, mirror separation 4.26bp < fee floor 16bp). Funding axis Tier 4 retire 11 cumulative (7 sub-classes, +macro-cross-asset variant 1st dogfood paradigm 156). NEW Lesson #67 candidate "macro single-asset × cross-asset broadcast antipattern" 1st dogfood. Lesson #39 sub-class A 4th dogfood formal CONFIRMED 자격 reached. Lesson #56 CONFIRMED 9th instance (R-0 4/4 strict family-distinct + R-1 BROAD_FALSIFIED outcome convergence). Lesson #61 3rd dogfood post-confirmation. Counter 155→156 substantive R-1 increment. 27-streak non-PASS. R-5 yield 6.41%. Next paradigm 157 recommendation Option α NY close session boundary 21:00 UTC anchor × 13 alts directional 4h (archetype C, untouched axis class, Lesson #67 antipattern avoidance via structural time anchor not macro signal broadcast).**
