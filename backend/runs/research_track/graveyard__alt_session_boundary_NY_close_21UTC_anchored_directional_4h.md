# GRAVEYARD — paradigm 157 `alt_session_boundary_NY_close_21UTC_anchored_directional_4h`

**Verdict**: `BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED_LESSON39B`
**Phase halted**: R-1 (clean dispatch, R-0 10 axes all PASS)
**Dispatch**: 2026-05-21 KST (paradigm 156 §next-action Option α explicit recommendation)
**Wall clock**: 3.3s

---

## R-1 4-quadrant Symmetric Negative Test (Lesson #19)

Anchor: NY close = 20:00 UTC bar close (16-20 UTC 4h bar, NY equities close 20:00 UTC EDT dominant period).

| Quadrant | label | n | net_mean_bp | sigex | perm_p | ci_lower_bp | 3-gate | Conc |
|---|---|---|---|---|---|---|---|---|
| **Q1** | UP_LONG_focus_CONT | 5792 | **+0.79** | +2.984 | 0.996 | −3.62 | FAIL (ci_lower<0) | FAIL |
| **Q2** | UP_SHORT_mirror_REV | 5792 | **−16.79** | −3.654 | 0.000 | −21.53 | FAIL | FAIL |
| **Q3** | DOWN_SHORT_focus_CONT | 5650 | **−15.38** | −2.206 | 0.004 | −20.33 | FAIL | FAIL |
| **Q4** | DOWN_LONG_mirror_REV | 5650 | **−0.62** | +2.297 | 0.996 | −5.86 | FAIL (ci_lower<0) | FAIL |

**4/4 quadrants 3-gate FAIL**.

### Lesson #39 sub-class B detection (mechanism inverted)

| Comparison | Δ sigex | Direction |
|---|---|---|
| Q1 (UP_LONG focus CONT) sigex +2.98 vs Q2 (UP_SHORT mirror REV) sigex −3.65 | +6.64σ | UP focus dominates Q2 mirror → focus direction correct on UP side |
| Q3 (DOWN_SHORT focus CONT) sigex −2.21 vs Q4 (DOWN_LONG mirror REV) sigex +2.30 | **Q4 dominates Q3 by 4.51σ** | DOWN side mechanism **INVERTED** (reversal beats continuation) |

**Q4 dominates Q3 by ≥1.5σ → Lesson #39 sub-class B trigger** → `BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED_LESSON39B`.

---

## Hold sweep (Lesson #37)

| Hold | UP_LONG_CONT n | UP_LONG_CONT bp | UP sigex | DOWN_SHORT_CONT n | DOWN_SHORT_CONT bp | DOWN sigex |
|---|---|---|---|---|---|---|
| 4h | 5792 | +0.79 | +2.98 | 5650 | −15.38 | −2.21 |
| 8h | 5789 | +3.65 | +2.72 | 5639 | −22.49 | −3.17 |
| 12h | 5789 | +0.35 | +0.42 | 5639 | −29.43 | −3.23 |

All hold cells FAIL 3-gate (ci_lower<0 universally on UP, sigex negative on DOWN). UP side peaks at 8h (+3.65 bp gross, but still sub-fee adjusted), DOWN side worsens monotonically with hold — confirming **DOWN side momentum-continuation hypothesis is wrong**; the underlying flow is reversion.

---

## Life-changing 4-dim (focus sides only, primary hold 4h)

| Side | trades/yr | edge%/trade | util% | sharpe | dims PASS |
|---|---|---|---|---|---|
| UP_LONG_CONT | 2580.4 | +0.008% | 100.0% | +0.23 | 2/4 (trades + util PASS; edge -1.99% short, sharpe -1.27 short) |
| DOWN_SHORT_CONT | 2517.2 | −0.154% | 100.0% | −3.85 | 2/4 (trades + util PASS; edge + sharpe FAIL) |

Neither focus side life-changing.

---

## Lesson #46 stratified sign-flip warning

| Side | q_meas | n_pos_q | n_neg_q | flips | max_flips | strong_alt? |
|---|---|---|---|---|---|---|
| UP_LONG_CONT | 10 | 5 | 5 | 7 | 9 | False (just below threshold) |
| DOWN_SHORT_CONT | 10 | 2 | 8 | 3 | 9 | False (dominant negative regime) |

UP side: 7/9 sign flips quarterly = near-strong alternating (not formally triggered) → noise-dominated.
DOWN side: 8/10 quarters negative = persistent regime → mechanism systematically wrong direction.

---

## R-0 10-axis prescreen (all PASS — dispatch clean)

| # | Axis | Verdict |
|---|---|---|
| 1 | Family-distinct strict 4-dim (Lesson #62) | ✅ 4/4 STRICT |
| 2 | Substrate availability (Lesson #28) | ✅ 4h cache verified |
| 3 | Sample density (Lesson #11) | ✅ 11,442 events / 14 syms |
| 4 | SNT 4-quadrant (Lesson #19) | ✅ implemented |
| 5 | Data window ratio (Lesson #30) | ✅ 1.00 uniform |
| 6 | Retiming reframe (Lesson #62) | ✅ NOT retiming (NEW anchor class) |
| 7 | OUTCOME-LEVEL family proxy (Lesson #56) | ✅ ESCAPE (NEW archetype C axis class) |
| 8 | Axis stacking (Lesson #21) | ✅ single axis × single mechanism |
| 9 | Same-bar same-substrate (Lesson #58) | ✅ EXEMPT |
| 10 | Mirror antipattern | ✅ N/A (sign-cond bilateral) |
| 11 | Lesson #67 candidate avoidance | ✅ ESCAPE (structural global anchor, not macro broadcast) |
| 12 | Intraday incompatibility (memory) | ✅ EXEMPT (4h hold) |

---

## Mechanism diagnosis

**Finding 1**: NY close session boundary carries near-zero LONG-side directional info on UP days. UP_LONG_CONT gross ≈ +0.87% (16-bp net + 8-bp fee) but per-trade edge net +0.79 bp is sub-fee — the +16-bp gross is purely fee-recovery, no alpha.

**Finding 2**: DOWN days exhibit **systematic reversal** (Q4 LONG-on-DOWN beats Q3 SHORT-on-DOWN by 14.76 bp gross). This matches the well-documented "buy-the-dip 4h-window" pattern in crypto perps. **But the reversal is itself sub-fee** (Q4 LONG net -0.62 bp). The continuation mechanism hypothesis is decisively wrong on DOWN side.

**Finding 3**: General **LONG bias** persists (Q1 LONG +0.79 bp, Q4 LONG -0.62 bp; Q2 SHORT -16.79 bp, Q3 SHORT -15.38 bp). LONG sides average ~+0 bp, SHORT sides average ~-16 bp = 2 × fee. **Lesson #8 universal LONG bias 4th candidate dogfood eligible** (after paradigm 99 + 156 + 148-related).

**Finding 4 (mechanism failure)**: The hypothesized "NY close macro flow rebalancing → directional continuation" is **not the dominant microstructure**. The actual structure:
- UP days: LONG-bias drift continues (sub-fee, near-zero info)
- DOWN days: REVERSAL (buy-the-dip), but sub-fee

The session-boundary anchor is a **shared structural microstructure event** (R-0 prescreen correct, Lesson #67 ESCAPE valid), but the mechanism alpha at this scale × this universe is fee-saturated either direction.

---

## Lesson impact

### Lesson #39 sub-class B 2nd dogfood
- 1st instance: paradigm 110 funding pct rank → mechanism direction inverted
- **2nd instance: paradigm 157 NY close session anchor → DOWN-side mechanism inverted (continuation hypothesized, reversal observed)**
- Sub-class B catalog growth: 2 confirmed dogfoods. CONFIRMED 자격 requires 1 more (3 dogfoods threshold for sub-class confirmation).
- Pattern signature: focus 3-gate FAIL + mirror sigex > focus sigex + 1.5σ → mechanism direction was hypothesized backward.

### Lesson #56 CONFIRMED 10th instance (OUTCOME-LEVEL family proxy)
- R-0 4/4 strict family-distinct PASS, NEW archetype C axis class (session boundary anchor, entirely untouched in prior 156 paradigms) → R-1 BROAD_FALSIFIED with mechanism-inverted antipattern.
- Even NEW axis class CANNOT rescue when fee floor (16 bp round-trip) > mechanism gross alpha (max 16-bp gross both sides, exactly fee-recovery zero edge).
- **Reinforces**: alpha axis exhaustion is fee-floor-bound, not exploration-bound. NEW axis classes can be explored cheaply (paradigm 157 R-1 wall-clock 3.3s) but must clear fee floor to be life-changing.

### Lesson #61 4th dogfood post-confirmation (R-0 next-action provenance audit)
- paradigm 156 §6.53 Next paradigm 157 recommendation Option α explicitly recommended this dispatch
- R-0 authorized 10/10, R-1 substantively executed, BROAD_FALSIFIED with clean Lesson #39 sub-class B attribution
- Provenance chain functioned as intended — agent-authored candidate → agent-authorized R-0 → R-1 clean falsification

### Lesson #67 candidate ESCAPED (and reinforced)
- paradigm 157 was explicitly designed to ESCAPE the Lesson #67 antipattern ("macro single-asset broadcast")
- ESCAPE verified: structural global anchor shared by all 14 syms (BTC + 13 alts)
- However R-1 still BROAD_FALSIFIED — confirming **Lesson #67 ESCAPE alone does not guarantee mechanism alpha**. The antipattern is **necessary** to avoid but not **sufficient** for alpha.

### NEW Lesson #68 candidate (1st dogfood)
**"Session-boundary anchor × 4h hold cross-asset = fee-floor-bound mechanism-inverted antipattern"**:
- Hypothesis: Time-of-day session boundary anchors (NY close, London close, Asia open) operate on **microstructure scale (seconds to minutes)** but bleed into adjacent 4h bars only as **shared cross-asset directional drift**, NOT as conditional alpha. The 8-bp round-trip fee floor is too high relative to the structural-anchor 4h-window gross (~16 bp = pure fee recovery, no net edge).
- Required for CONFIRMED 자격: 1+ more dogfood (e.g., London close 16 UTC anchor, Asia open 00 UTC anchor with similar 4h × cross-asset structure)
- Distinguishing factor: paradigm 22 R-5 funding 8h boundary survives because (a) it's a **forced cash-flow event** (funding payment) not a soft microstructure shift, (b) it has per-sym threshold conditioning + magnitude conditioning, NOT just sign × cross-asset broadcast.

---

## Funding axis Tier 4 cross-reference
**N/A** — paradigm 157 is NOT a funding-axis paradigm. Family-distinct 4/4 strict satisfied. Funding family Tier 4 retire remains at 11 cumulative graveyards (paradigm 22 R-5 exception only).

## Archetype C session boundary axis class status
- paradigm 157 = **1st R-1 outcome** for archetype C session-boundary anchor class (memory plan archetype C).
- paradigm 85 pre_session_open_oi was sample-insufficient halt only (no R-1 outcome).
- Archetype C single-asset session anchor × cross-asset: **1 fail, family retire NOT eligible yet** (needs ≥2 graveyards per Tier 4 family-retire rule).
- **NEW Lesson #68 candidate** opens the door to session-boundary family Tier 4 retire after 1 more dogfood (London close 16 UTC or Asia open 00 UTC).

---

## Campaign 진행 상태 갱신 (2026-05-21 paradigm 157 R-1 graveyard 이후)

- 누적 graveyards: 156 → **157**
- R-5 LIVE: **10** (unchanged)
- Non-PASS streak: 27 → **28**
- R-5 yield: 10/157 = **6.37%**
- Lessons: 34 confirmed + 19 candidates → **34 confirmed + 20 candidates** (Lesson #68 candidate NEW 1st dogfood, Lesson #39 sub-class B 2nd dogfood, Lesson #56 10th instance, Lesson #67 ESCAPE reinforced)
- Funding axis Tier 4: 11 cumulative (unchanged — paradigm 157 is NOT funding family)
- **NEW**: Archetype C session boundary anchor class — 1 graveyard (paradigm 157), family-retire NOT yet eligible (need ≥2)
- D-Day 2026-06-03 D-13
