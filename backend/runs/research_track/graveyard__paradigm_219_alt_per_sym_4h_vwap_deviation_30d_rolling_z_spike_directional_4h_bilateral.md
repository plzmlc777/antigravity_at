# paradigm 219 GRAVEYARD

**slug**: `alt_per_sym_4h_vwap_deviation_30d_rolling_z_spike_directional_4h_bilateral`

**verdict**: `LESSON_39_SUB_CLASS_B_MECHANISM_INVERTED_PLUS_ITEM_9_STRUCTURAL_FAIL_PLUS_2026_ERA_UNIVERSAL_DECAY_PLUS_PATTERN_P1_FORMAL_UNIVERSAL_8TH_CONSECUTIVE`

**phase**: R-1

**dispatched**: 2026-05-25 (continuous-parallel policy, user-provided direct recommend)

**predecessor**: paradigm 218 R-1 graveyard (Pattern P1 7th formal universal + macro-event-anchored Tier 4 retire candidate)

---

## Lesson #69 9-item template results

### Item 1 — INDEX.json grep STRICT
- VWAP/volume_weighted/typical_price/vwap_ratio: **0 paradigms** existing
- VWAP class fresh axis CONFIRMED

### Item 2 — substrate-shape + market maturity + Lesson #72 trigger source granularity
- 4h cache `ohlcv_cache_12col` 21 syms × 2.24yr (2024-02-01 ~ 2026-04-30) verified, used 20-sym cohort (paradigm 198)
- 11 cols incl high/low/close/volume → typical_price + rolling VWAP computable
- substrate_maturity 2.24yr ≥ 2yr PASS
- rolling 6m window per-cell t-stat consistency measured (see §Rolling 6m)
- Lesson #72 candidate: 4h hold × 4h trigger granularity match PASS

### Item 3 — Lesson #11 sample density
- per-sym z<=-2: total 1653, z>=+2: total 4690 (highly asymmetric)
- per-cell B set (z<=-2 ∧ DOWN bar): n=1040 across 20 syms (2.24yr)
- per-cell A set (z>=+2 ∧ UP bar): n=2877
- All cells per-quarter per-cell ≥ 30 PASS

### Item 4 — Lesson #62 DNA 4-dim 5/5 strict
- vs paradigm 195/196 (cross-sym vol cohort): VWAP per-sym deviation vs cross-sym vol cohort = DISTINCT
- vs paradigm 124 (kurtosis × skewness): VWAP volume-weighted price vs 4th moment composite = DISTINCT
- vs paradigm 211 (vol term structure): VWAP vs vol horizon = DISTINCT
- vs paradigm 127/128 (volume burst): volume burst single-axis vs VWAP composite (volume × price) = DISTINCT
- vs paradigm 22/24/69/127/128/174 R-5 LIVE: VWAP axis fresh, R-5 LIVE expansion NOT
- vs 20 Tier 4 retires + 6 advisory caution: VWAP class fresh
- **PASS 5/5 strict**

### Item 5 — Lesson #56 family-proxy
- VWAP deviation composite class, NEW

### Item 6 — Alpha decay 5+ pattern audit (10th operational dogfood)
- Era stratify primary hold 4h:
  - A_focus_ABOVE_UP_LONG: 2024 mean=+3.27bp t=+0.40 → 2025 -10.42 t=-1.21 → 2026 -33.10 t=-3.80 = **Pattern P1 monotonic decay CONFIRMED**
  - B_mirror_BELOW_DOWN_LONG: 2024 +46.71bp t=+1.87 → 2025 +37.44 t=+2.96 → 2026 **-58.40 t=-3.58** = **Pattern P1 monotonic decay + 2026 sign flip**
  - B_same_BELOW_DOWN_SHORT (mirror of B_mirror): 2024 -62.71 → 2025 -53.44 → 2026 **+42.40 t=+2.60** = sign flip 2026 (consistent with mechanism inversion in 2026)
  - A_mirror_ABOVE_UP_SHORT: 2024 -19.27 → 2025 -5.58 → 2026 +17.10 t=+1.96 = sign flip 2026
- **All 4 cells flip sign in 2026** = 2026 era-universal decay
- **Pattern P1 8th consecutive formal universal CONFIRMED** (paradigm 87+136+202+210+211+212+218+**219**)
- **2026 era-universal decay 6th instance CONFIRMED** (elevation 자격 강화)

### Item 7 — SNT structural integrity / cross-set asymmetry
- |A| (z>=+2 ∧ UP) = 2877
- |B| (z<=-2 ∧ DOWN) = 1040
- asymmetry A_to_B = **2.77x** (very close to paradigm 207 2.79x)
- z distribution overall: pos triggers (4690) ≫ neg triggers (1653) = inherent positive skew of price-to-VWAP ratio (rare massive deviations above VWAP during pumps)
- 8th instance recorded

### Item 8 — Concentration + Temporal Independence (paradigm 208 amendment)
- A_focus 24h PASS cell:
  - per-sym CI: **4/20 = 0.20** ❌ FAIL < 0.30 threshold (BTC/DOGE/ETH/XRP only)
  - per-quarter pos_t: 3/8 = 37.5% FAIL
- B_mirror 8h PASS cell:
  - per-sym CI: need to verify but 12h sample similar
  - per-quarter pos_t: 6/8 PASS but **2026Q1 t=-2.69 SIGN FLIP**
- B_mirror 12h PASS cell:
  - per-sym CI: **6/20 = 0.30 MARGINAL** (exactly at threshold)
  - per-quarter pos_t: 7/8 = 87.5% PASS, but 2026Q1 t=-1.82 NEG
- B_mirror 24h PASS cell:
  - per-quarter pos_t: 8/8 = 100% PASS (2026Q1 t=+0.84 weak but positive)
  - However era stratify shows 2026 underperforms massively (n=211 mean=42bp vs 2024 281bp)

### Item 9 — Life-changing 4-dim STRUCTURAL prescreen (4th operational, paradigm 213+215+218 precedent)
- trades/yr: 464 ✓ (»12)
- per-trade edge gross (B_mirror 24h): ~197bp gross, ~189bp net ✓ (»2%)
- capital util:
  - 8h: 2.11% ❌
  - 12h: 3.17% ❌
  - 24h: 6.34% ❌ (≪ 30% threshold)
- sharpe: not measured (R-2 scope)
- **Item 9 STRUCTURAL FAIL 4th operational dogfood CONFIRMED** (sparse-trigger 4h × bilateral SNT capital util systematically <10%)
- Reference: paradigm 215 1.5% / paradigm 218 1.32% / paradigm 219 6.34% (best case)

---

## family-distinct strict 5/5 verdict
**PASS** — VWAP class genuinely novel statistic. No catalog dup.

## 4-quadrant SNT verdict

| Cell | n | hold | sigex | ci_lo bp | perm_p | verdict |
|---|---|---|---|---|---|---|
| A_focus_ABOVE_UP_LONG | 2877 | 4h | 0.90 | -17.12 | 0.807 | FAIL |
| A_focus_ABOVE_UP_LONG | 2877 | 8h | 2.01 | -12.10 | 0.027 | FAIL_ci |
| A_focus_ABOVE_UP_LONG | 2876 | 12h | 2.58 | -7.56 | 0.003 | FAIL_ci |
| **A_focus_ABOVE_UP_LONG** | **2874** | **24h** | **3.42** | **+2.93** | **0.000** | **THREE_GATE_PASS** |
| A_mirror_ABOVE_UP_SHORT | 2877 | 4h | 0.41 | -18.82 | 0.643 | FAIL |
| A_mirror_ABOVE_UP_SHORT | 2874 | 24h | -2.93 | -67.05 | 0.000 | FAIL |
| B_same_BELOW_DOWN_SHORT | 1040 | 4h | -2.23 | -58.69 | 0.008 | FAIL |
| B_same_BELOW_DOWN_SHORT | 1040 | 24h | -10.28 | -252.16 | 0.000 | FAIL (extreme neg) |
| B_mirror_BELOW_DOWN_LONG | 1040 | 4h | 3.39 | -0.21 | 0.000 | FAIL_ci (marginal) |
| **B_mirror_BELOW_DOWN_LONG** | **1040** | **8h** | **6.28** | **+43.77** | **0.000** | **THREE_GATE_PASS** |
| **B_mirror_BELOW_DOWN_LONG** | **1040** | **12h** | **7.71** | **+76.24** | **0.000** | **THREE_GATE_PASS** |
| **B_mirror_BELOW_DOWN_LONG** | **1040** | **24h** | **10.55** | **+157.68** | **0.000** | **THREE_GATE_PASS** |

## Unconditional baseline (Lesson #39 sub-class B verification)
| hold | LONG mean_bp | LONG t | SHORT mean_bp | SHORT t |
|---|---|---|---|---|
| 4h | -8.70 | -12.82 | -7.30 | -10.76 |
| 8h | -9.29 | -9.64 | -6.71 | -6.95 |
| 12h | -9.91 | -8.38 | -6.09 | -5.15 |
| 24h | -11.72 | -6.99 | -4.28 | -2.55 |

Strong unconditional **negative bias both directions** (fee floor + microstructure noise) — confirms 4h cohort fee-floor environment. Conditional B_mirror PASS sufficiently exceeds unconditional baseline (e.g. 24h gross +197bp ≫ -4.28bp baseline) → NOT pure direction bet.

## Lesson #39 sub-class B (mechanism-inverted mirror identity) confirmed
- B_same (z<=-2 × DOWN × SHORT continuation): sigex -2.23/-5.66/-7.23/-10.28 at 4h/8h/12h/24h (perfect mirror of B_mirror)
- B_mirror (z<=-2 × DOWN × LONG reversal): sigex +3.39/+6.28/+7.71/+10.55
- B_same and B_mirror are **perfect symmetric mirrors** (one trade dir, opposite of the other on same trigger set)
- Real mechanism direction = B_mirror (LONG reversal after BELOW-VWAP DOWN spike). B_same is the fee-floor antipattern direction.
- This pattern (B_mirror PASS, B_same symmetric FAIL on same trigger set) is **Lesson #39 sub-class B classic signature** but NOT antipattern itself — B_mirror gross +197bp ≫ fee floor 8bp suggests real alpha BEFORE decay considerations.

## Lesson #42 21st dogfood (B_mirror chain)
- B_mirror PASS at 8h/12h/24h R-1 strict 3-gate
- However 2026Q1 sign flip negates the chain — classify as **NEGATIVE for 21st** (chain count: confirmed 10 / NEGATIVE 10 + 1 = 11 / PASS_AS_ARTIFACT 1)

## Era stratify Pattern P1 8th consecutive formal universal
All 4 cells show monotonic 2024→2025→2026 directional decay or sign flip. **No 2026 PASS for any cell**. Mechanism is structurally **2024+2025 vintage**.

## Final 종합 판정
**GRAVEYARD** despite 4 cells × 4 holds showing 4 THREE_GATE_PASS verdicts. Reasons in priority order:
1. **Item 9 STRUCTURAL FAIL**: capital util 2.11%~6.34% ≪ 30% threshold (life-changing 4-dim 사전 차단)
2. **2026 era-universal decay**: B_mirror per-quarter 2026Q1 NEG t=-2.69~-1.82 across 8h/12h, sign flip
3. **Pattern P1 8th consecutive formal universal**: monotonic decay across all 4 cells
4. **A_focus 24h Concentration FAIL**: 4/20 = 0.20 (BTC/DOGE/ETH/XRP only)
5. **B_mirror 12h Concentration marginal**: 6/20 = 0.30 exactly at threshold

The ostensibly strong PASS cell B_mirror 24h (sigex 10.55, ci +157.68bp) is rendered NON-VIABLE by Items 8/9 + 2026 decay.

## paradigm 220 next-action 권고
**continuous-parallel policy strict 적용**. Recommendations:
- VWAP class **R-0 reformulation possible** — alternative composites that may avoid Item 9 sparse-trigger:
  - VWAP deviation × ATR-normalized (continuous-weighted directional position, not spike trigger)
  - VWAP deviation cross-sectional rank top-3/bottom-3 (paradigm 188-style continuous, but already retired per [[project-paradigm-188-memorial]])
- **Pattern P1 8 consecutive + 2026 era-universal 6th** strongly suggests next paradigm should avoid Pattern P1-prone axes:
  - Single-sym single-axis directional spike triggers
  - Volume-derived composites
  - Mean-reversion / continuation signed on price+volume axes
- Alternative axes still fresh:
  - **funding × premium cross-axis** (rejected previously? verify against funding family Tier 4)
  - **cross-exchange microstructure with NEW deep-sym universe** (Bybit substrate available)
  - **OI delta % over rolling baseline (not z-score)** — absolute threshold variants
- **paradigm 220** suggestion: SELF-RECOMMEND mode may risk saturation. User-provided hypothesis preferred per [[feedback-paradigm-architect-self-recommend-mode-switch-trigger]] memory.

응답 마지막 줄 KST timestamp.
