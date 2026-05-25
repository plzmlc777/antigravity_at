# Graveyard — paradigm 141 (alt_funding_per_sym_30d_zscore_NEG_ONLY_alone_SHORT_continuation_4h)

**Verdict**: BROAD_FALSIFIED
**Phase**: R-1
**Date (KST)**: 2026-05-21 12:24 KST
**Wall clock**: 48.5s
**Cumulative graveyards**: 141

## Hypothesis

Per-symbol funding rate 30d rolling z-score <= -2.0 (extreme LONG-crowded
condition) triggers 4h SHORT continuation as cascade unwind — paradigm 22 R-5
SEEDED MIRROR DIRECTION TEST (paradigm 22 = LONG mean-reversion; paradigm 141 =
SHORT continuation, opposite direction mechanism family).

## 1-sided SNT 2-quadrant (Lesson #19 exception)

| Quadrant | n | mean_bp | sigex | perm_p | ci_lower_bp | 3-gate | concentration |
|---|---|---|---|---|---|---|---|
| **A_focus SHORT** (paradigm 22 mirror) | 530 | −6.37 | +0.423 | 0.690 | −23.78 | FAIL | FAIL |
| **A_mirror LONG** (paradigm 22 alignment baseline) | 530 | −9.63 | −0.250 | 0.439 | −27.23 | FAIL | FAIL |

**1-sided justification**: B-side substrate empirically absent (pos2 rate 0.20% / 6 of 10 syms zero pos2 events) — Lesson #40 sub-class C asymmetric inheritance from paradigm 139 verified.

## Hold sweep (Lesson #37 full scan)

| hold_min | SHORT mean_bp | SHORT sigex | LONG mean_bp | LONG sigex |
|---|---|---|---|---|
| 120m | −5.11 | +0.603 | −10.89 | −0.019 |
| 240m | −6.37 | +0.423 | −9.63 | −0.250 |
| 480m | −21.98 | −0.823 | **+5.98** | **+1.073** |

- 4h SHORT focus 최소 negative이지만 sub-fee
- 8h LONG positive sigex +1.073 (paradigm 22 alignment 약한 신호 잔존 but sub-fee, sigex<2.0)
- **Off-primary 3-gate PASS: 0 cells** (full sweep 6 cells 모두 FAIL)

## paradigm 22 mirror direction test 결과

- A_focus_sigex (SHORT): +0.423
- A_mirror_sigex (LONG paradigm 22 alignment): −0.250
- mirror_dominance_pass = True (ratio criterion 통과 by sign asymmetry)

**그러나 본질적 해석**: A_focus 양수 sigex 아니라 둘 다 0 근처 negative cell. mirror가 더 negative라서 focus가 "상대적으로 덜 나쁘다" 뿐 — 실제 alpha 부재.

## Life-changing 4-dim (focus SHORT)

- trades/yr: 525.3 (PASS)
- per-trade edge net: **−0.096% FAIL**
- capital util: **24.0% FAIL** (cutoff 30%)
- ann sharpe: **−1.06 FAIL**
- n_dims_pass: **1/4 FAIL**

## Lesson #46 stratified + sub-amendment sign-flip

- n_quarters_measurable: 5
- n_pos_quarters: 4
- n_neg_quarters: 1
- n_sign_flips: 1/4
- strong_alternating: False → no WARNING

Stratified pos:neg = 4:1로 양 quarter 우세하나 raw mean negative — magnitude effect (1 large negative quarter dominates).

## Failure mode 진단

1. **paradigm 22 MR mechanism이 paradigm 141 setting (30d rolling z / 4h hold / 10-sym 확장)에서 사라짐**
   - paradigm 22: 6-sym z2.0/lb30/mh15 + 8h hold MR → alpha 29.89% mean
   - paradigm 141: 10-sym z<=-2.0/lb30/4h hold continuation → −6.37bp focus / sub-fee mirror
   - 가설: paradigm 22 alpha = 8h funding cycle alignment exit (`exit_z=0.5` mean-reversion 도달) 핵심, 4h directional hold는 mechanism 약화

2. **SHORT continuation 가설 결정적 부정**: 0/3 SHORT hold cells positive sigex >= 1.0
3. **LONG alignment 8h sub-grade survival**: paradigm 22 R-5 mechanism 약한 잔존 but +5.98bp < fee floor 8bp
4. **Funding family Tier 4 retire 11th sub-class 강화** — direction inversion variant 추가 fail (73/79/96/97/98/99/103/138/139/140 + 141)

## Lessons triggered

- **Lesson #11**: per-cell n=144 PASS (사전 측정 정확)
- **Lesson #19 exception**: 1-sided SNT B-side justification VALID
- **Lesson #40 sub-class C 4th dogfood**: asymmetric substrate inheritance from paradigm 139 정확 적용
- **Lesson #46 sub-amendment**: stratified n=50×4q + sign-flip detection 13th dogfood (no warning case)
- **Lesson #37**: full hold sweep scan 의무 적용, off-primary PASS 0 cells 확인
- **Lesson #55 candidate 3rd dogfood**: 1-sided substrate justification PASS (asymmetry 0.96)
- **NEW candidate lesson #56**: "successful paradigm direction inversion fails by default" — paradigm 22 R-5 mirror direction 가설은 mechanism story 그럴듯하나 empirical alpha 부재. paradigm 70 mirror SHORT (graveyard 70), paradigm 96 sign flip (graveyard 96), paradigm 141 (now) → **3 dogfoods** 누적, formal candidate elevation. "R-5 seeded paradigm의 direction-inversion 변형은 R-1 dispatch 전 별도 mechanism-distinct justification 의무"

## 산출물

- R-0: `backend/runs/research_track/alt_funding_per_sym_30d_zscore_NEG_ONLY_alone_SHORT_continuation_4h/r0_prescreen.json`
- R-1: `backend/runs/research_track/alt_funding_per_sym_30d_zscore_NEG_ONLY_alone_SHORT_continuation_4h/r1__metrics.json`
- script: `backend/scripts/research/paradigm141_funding_neg_z_short_continuation_r1.py`

## 다음 권고

- **13-streak non-PASS** (129-141) 누적, funding family direction variant 공간 사실상 소진
- 옵션 A (1순위): substrate distinct paradigm — book_depth WS 60일+ 누적 (2026-07-15)/microstructure DB 필요한 새 axis
- 옵션 B: Lesson #56 candidate 정식 검증 — paradigm 71/127/128 direction-inversion 변형 사전 차단 prescreen 추가
- 옵션 C: paper baseline 2026-05-28 (D-7) / 2026-06-03 (D-13) 데이터 우선 모드 전환
