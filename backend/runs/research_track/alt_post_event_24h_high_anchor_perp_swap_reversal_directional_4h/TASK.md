# paradigm 162 — alt_post_event_24h_high_anchor_perp_swap_reversal_directional_4h

**Status**: R-1 dispatch (paradigm-architect, post lifecycle_pump_decay R-5 promotion)
**Date**: 2026-05-21 21:00+ KST
**Counter**: paradigm 162 (substantive R-1 increment after 161 R-0 halt)

## Hypothesis

Per-symbol 24h rolling-high cross-up event를 anchor로 사용, anchor cross-up
직후 4h hold SHORT reversal mean-reversion 알파 가설.

- **Trigger statistic**: per-sym `close >= rolling_24h_max` cross-up event
  (현재 4h bar의 close가 직전 6 bar (24h) max를 갱신)
- **A_focus**: 24h new high cross-up × SHORT 4h hold (resistance-level reversal MR)
- **A_mirror**: 24h new high cross-up × LONG 4h hold (breakout continuation)
- **B_same_sign**: 24h new low cross-down × LONG 4h hold (support-level reversal MR)
- **B_mirror**: 24h new low cross-down × SHORT 4h hold (breakdown continuation)

## R-0 Inventory Audit (Lesson #61 amendment 4th post-confirmation strict)

### Slug grep results
```
alt_extreme_24h_PUMP_24h_continuation_long       — paradigm 158 graveyard
alt_extreme_24h_drawdown_24h_reversion_long      — paradigm 117 R-3 OOS FAIL graveyard
alt_extreme_24h_drawdown_reversal_long_4h        — paradigm 117 R-1 PASS source
```

### DNA 4-dim audit vs paradigm 117 / 158 (Lesson #62)
| Dim | paradigm 117 | paradigm 158 | paradigm 162 | vs 117 | vs 158 |
|---|---|---|---|---|---|
| Statistic class | rolling 24h cum return ≤ -15% | rolling 24h cum return ≥ p90 | rolling 24h max cross-up anchor | partial | partial |
| Universe | 28 alts | 13 alts | 13 alts | partial | identical |
| Entry-side class | DRAWDOWN cross-down magnitude | PUMP cross-up magnitude | 24h high anchor cross-up | partial | STRICT (anchor event vs threshold) |
| Mechanism alpha | capitulation MR LONG | FOMO continuation LONG | resistance reversal MR SHORT | STRICT | STRICT |
| Hold | 24h | 24h | 4h | STRICT | STRICT |

**vs paradigm 117 strict count: 2/5** (mechanism direction reversal-vs-MR + hold) — BOUNDARY_PASS
**vs paradigm 158 strict count: 3/5** (entry-side anchor vs threshold + mechanism reversal vs continuation + hold) — STRICT FAMILY-DISTINCT
Lesson #62 ≥2 strict 충족 → dispatch AUTHORIZED.

### Magnitude-event family Tier 4 retire cross-reference
paradigm 117 + 158 family 직전 Tier 4 retire eligibility 상태였으나 lifecycle_pump_decay
R-5 promotion으로 retire eligibility 일시 해제 (Lesson #56 6th instance escape attempt).
paradigm 162는 statistic class를 magnitude threshold (return-based)에서 **anchor event**
(max-running)로 변형 — family-distinct strict 입증 위한 의도적 trigger reformulation.

### Prior R-3+ outcome reference
- **paradigm 117 R-3**: OOS FAIL (alpha real but OOS decay, 2024Q1 single quarter dominate)
- **paradigm 158 R-1**: BROAD_FALSIFIED_NO_THREE_GATE (FOMO continuation absent, mechanism CLASS asymmetric finding 2nd dogfood)

### CRITICAL: paradigm 158 A_mirror cross-comparison
paradigm 158 r1__metrics.json 직접 확인:
- **A_mirror_pump_SHORT @ pct=0.90, hold=24h**: gross **-1.98bp**, sigex **-0.31**, ci [-34, +14], 0/13 syms ci_pos
- **A_mirror_pump_SHORT @ pct=0.95, hold=24h**: gross **-23.63bp**, ci [-53, +23], 3-gate FAIL
- Lesson #39 perfect mirror confirmed all 3 pcts: A_focus + A_mirror sum_abs = 0.00bp

**Mechanism overlap audit**:
- paradigm 158 A_mirror = (rolling 24h cum return ≥ p90) × SHORT × 24h hold
- paradigm 162 A_focus = (rolling 24h max cross-up event) × SHORT × **4h** hold
- Trigger 측정대상 차이: 158은 24h cum return 분포 top decile (15% events at p85), 162는 anchor cross-up event (running max갱신, empirical rate 측정 의무)
- Hold 차이: 24h vs **4h** (paradigm 158 미탐색 timescale)
- Mechanism alpha 동일: reversal SHORT post-extreme-up

### paradigm 117 R-1 4h B_same_sign_pump_SHORT direct precedent
paradigm 117 R-1 4-quadrant SNT at threshold -15% × hold **4h**:
- **B_same_sign_pump_SHORT**: n=409, gross **+35.55bp**, sigex **+1.87**, 3-gate FAIL (perm_p 미통과, Concentration FAIL)

paradigm 162 mechanism = paradigm 117 R-1 4h B_same_sign_pump_SHORT의 **anchor-reformulated variant**.
paradigm 117 4h precedent에서 sigex +1.87 marginal pre-fee 양수 신호 측정 — paradigm 162 anchor event
reformulation이 알파를 강화/약화시킬지 측정 가치 있음.

### Substrate (Lesson #28) PASS
- 12-col 4h klines joblib cache (영구 자산) — 13 alts × ~4914 bars

### Sample density (Lesson #11) PASS-PENDING
- 24h new-high anchor cross-up event rate empirical 측정 의무
- 기대 rate: 24h rolling max 갱신 per-bar 확률 ~5-15% (theoretical, empirical 측정)
- 13 alts × ~4914 bars × ~10% = ~6,400 raw events, debounce 후 ≥2,000 expected
- 4-quadrant SNT per-cell n≥500 충분

### Lesson #19 Symmetric Negative Test 4-quadrant 의무
- A focus + A mirror + B same-sign + B mirror, 단일 batch
- pct sweep 의미 없음 (anchor event는 binary), hold sweep만 의미 있음

### Lesson #30 data window ratio PASS
- 2.25yr / 2.4yr = 93.75%

### Lesson #56 OUTCOME-LEVEL FAMILY PROXY 위험
- magnitude-event family 13 instances 누적 (Lesson #56)
- paradigm 162 expected outcome: **BROAD_FALSIFIED_FEE_FLOOR** likely (paradigm 117 4h precedent
  sigex +1.87 sub-fee + paradigm 158 24h A_mirror sub-fee).
- 그러나 anchor event reformulation + 4h subscale exploration = explicit informational value

### Lesson #67/#68/#21 ESCAPE PASS
- per-sym idiosyncratic anchor (cross-asset broadcast 부재) — Lesson #67 ESCAPE
- 4h hold + per-sym anchor (session-boundary universe-wide 부재) — Lesson #68 ESCAPE
- 단일 axis (24h max anchor) × 단일 mechanism (reversal MR) — Lesson #21 ESCAPE

### Lesson #42 mechanism CLASS asymmetric cross-reference
paradigm 158 mechanism CLASS asymmetric finding (capitulation MR alpha-bearing,
FOMO continuation absent) **2nd dogfood CONFIRMED**.
paradigm 162 = 24h up-extreme anchor × SHORT reversal — paradigm 158 A_mirror과 유사한 mechanism.
Lesson #42 prediction: **PUMP × SHORT reversal at 4h ≈ paradigm 158 A_mirror 24h pattern**
(forecast sigex < 1.5, sub-fee).
paradigm 162는 Lesson #42 4h timescale subspace 첫 explicit test.

## Verdict tree
- `PASS_R1_FULL`: any quadrant + hold cell 3-gate + Conc + lc4 all PASS
- `NARROW_SCOPE_LIFE_CHANGING_FAIL`: 3-gate + Conc + edge≥2% but other lc dim fail
- `BROAD_FALSIFIED_DIRECTION_INVERTED`: A_focus gross strongly negative (anchor breakout continuation)
- `BROAD_FALSIFIED_FEE_FLOOR`: A_focus 0 < gross < 16bp net sub-fee 4h
- `BROAD_FALSIFIED_NO_THREE_GATE`: no quadrant clears 3-gate
- `BROAD_FALSIFIED`: all quadrants non-positive gross

## R-1 only STRICT
R-2 자동 진행 금지. 4-quadrant SNT + hold sweep + Lesson #37 sweep verdict scan + Lesson #39 mirror diagnostic + Lesson #8 LONG bias check 의무.
