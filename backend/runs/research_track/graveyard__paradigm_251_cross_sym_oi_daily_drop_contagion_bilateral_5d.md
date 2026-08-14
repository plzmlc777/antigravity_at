# Graveyard: cross_sym_oi_daily_drop_event_contagion_bilateral_5d

- **Paradigm number**: 251
- **Slug**: `cross_sym_oi_daily_drop_event_contagion_bilateral_5d`
- **Date**: 2026-08-08 KST
- **Dispatch mode**: autonomous SELF-RECOMMEND (오케스트레이터 제안)
- **Verdict**: **G1_FAIL** (Lesson #74 event-level authoritative + tier3 time-weighted decay)
- **Final phase**: `GRAVEYARD_G1`

## Hypothesis

바이낸스 USDT-M 14종 유니버스에서 임의 심볼의 일별 OI %변화 z-score가
±2.0 을 초과하면(대형 OI 이벤트) 나머지 13개 심볼이 이후 5일(7,200분)간
방향성 편향을 보인다는 가설. 4-사분면 SNT:

- A_focus:  OI z<-2 → 다른 알트 SHORT (contagion)
- A_mirror: OI z<-2 → 다른 알트 LONG  (rotation)
- B_focus:  OI z>+2 → 다른 알트 LONG  (momentum)
- B_mirror: OI z>+2 → 다른 알트 SHORT (crowding reversal)

## G0 통과 근거

- **Lesson #61 slug uniqueness**: 신규 (`grep` 미검출) ✓
- **Lesson #28 substrate audit**: 14 syms 전부 microstructure OI + OHLCV 커버 ✓
- **Lesson #62 DNA 5-dim**: 기존 OI 계열 (paradigm 21/71/240) 대비 overlap ≤ 3/5 ✓
- **Lesson #11 sample density**: A_focus 468, B_focus 720+ per (quadrant-quarter) ✓
- **Lesson #79 OOS predictive content**: A(z<-2) OOS t=-4.76, B(z>+2) OOS t=-3.95 ✓
  (부호 반전 후 net edge > 0 잠재)

## R-1 결과 (4-quadrant 전체 실행)

| Quadrant  | n_trades | n_events | trade_mean_bp | event_mean_bp | signal_t_excess | ci_trade_lower_bp | ci_event_lower_bp | event_t | 3-gate | conc | event_pos |
|-----------|----------|----------|--------------|--------------|-----------------|-------------------|-------------------|---------|--------|------|-----------|
| A_focus   | 2,782    | 214      | -18.33       | -18.33       | -2.762          | -56.33            | -130.40           | -0.33   | ✗      | ✗    | ✗         |
| A_mirror  | 2,782    | 214      | +2.33        | +2.33        | -1.697          | -34.52            | -113.35           | +0.04   | ✗      | ✗    | ✗         |
| B_focus   | 4,654    | 358      | +73.95       | +73.95       | +2.181          | +42.16            | **-13.07**        | +1.65   | ✓      | ✗    | ✗         |
| B_mirror  | 4,654    | 358      | -89.95       | -89.95       | -7.707          | -122.72           | -180.84           | ✗      | ✗    | ✗         |

### 주요 판정 근거

**1. Lesson #74 event-level bootstrap 는 authoritative**
- 같은 trigger day 의 13 target sym 수익률은 강한 regime 상관 → trade-level 부트스트랩은
  독립성을 과대평가한다.
- B_focus 는 trade-level three-gate PASS 이지만 event-level bootstrap 에서
  `ci_event_lower = -13.07bp` 로 신뢰구간이 0 을 포함 → 이벤트 IID 관점에서 유의하지 않음.

**2. Lesson #39 sub-class B 대칭성 진단**
- A_focus vs A_mirror: -18.33 vs +2.33 (~2×fee=16bp gap ✓, 둘 다 broad-negative)
- B_focus vs B_mirror: +73.95 vs -89.95 (~16bp gap ✓)
- A 축은 sub-class A (broad-uniform-negative, 방향성 정보 없음) 패턴.
- B 축은 sub-class B 후보였으나 event-level 로 잘리며 fee-floor 문제로 종결.

**3. Concentration Gate FAIL (Lesson #16)**
- B_focus: `n_sym_ci_pos = 0/14` (target sym 중 어느 것도 5% α 신뢰하한이 양수 아님)
- 겉으로 보이는 +73.95bp 는 소수 심볼(예: DOGE +229.87bp)에 의존한 concentrated bet.

**4. tier3_gate.py G1 시간가중 decay (결정적)**
`trades_B_focus_DOGEUSDT.json` (n=330):
- 단순 엣지 +2.30% / 시간가중 엣지 **-0.40%** (halflife 90d)
- 최근 1/3 엣지 **-1.22%** / 과거 1/3 엣지 +10.14%
- decay_ratio **-0.12** (부호 반전, 알파 소멸 확진)

**5. G2 실행가능성** — 통과
- lookahead_clean=true (T+1 open 진입, T+6 open 청산; 트리거는 T 종가만 사용)
- edge_after_1bar (T+2 진입 지연) = +1.4466% → net_headroom 18.08x
- cycle_margin 5.0x (hold 7200min / cycle 1440min)
- 즉, 실행 인프라 자체는 문제 없음. **알파가 없다는 것이 문제.**

## 근본 원인 (재발의 금지 사유)

1. **Cross-sym OI 이벤트는 regime proxy 지 alpha source 가 아니다.**
   OI 대형 이벤트는 broad-market 리스크 국면의 결과이며, "다른 심볼로의 정보 전파"
   자체는 시장에 이미 반영돼 있다. 5일 forward window 에서 순수 이벤트-특이적 엣지는
   fee floor (8bp round-trip) 를 넘지 못한다.

2. **B_focus 관측치의 alpha decay 는 표본 창 (2024-11-07 → 2026-05-02) 초반 강세장
   드리프트 잔재.** 최근 1/3 (~2025-11 이후) 에서는 부호 반전.

3. **Lesson #74 warning**: cross-sym joint-trigger 패러다임은 반드시 event-level
   authoritative — 본 케이스처럼 trade-level 만으로 판정하면 R-2 로 넘겨 리소스 낭비.

## Lessons applied

- **#11** sample density prescreen (통과했으나 무의미)
- **#16** Concentration Gate (FAIL — 14/14 target sym 중 0 CI-positive)
- **#19** 4-quadrant SNT 단일 배치 (의무 준수)
- **#28** substrate availability audit
- **#39** sub-class A/B 대칭성 진단 (A 축 broad-negative, B 축 fee-bound)
- **#56** outcome-level family proxy (paradigm 21 시드와 mechanism 중복 아님 확인)
- **#61** slug uniqueness
- **#62** DNA 5-dim
- **#69** R-0 5-item template
- **#74** event-level bootstrap authoritative (본 결과의 결정적 판정 근거)
- **#77 corollary** trigger + direction 축 모두 non-OHLCV (OI z-score 트리거,
  cross-sym forward return 는 이벤트로부터 도출 → 통과)
- **#79** OOS predictive content pretest (통과했으나 개별 이벤트에는 alpha 없음)

## 새 lesson 후보

**Lesson #82 candidate — cross-sym event-anchored 패러다임은 event-level +
trade-level 이중 통과 필수, trade-level 단독 PASS 는 R-2 승격 금지**

paradigm_251 B_focus 는 trade-level three-gate PASS 이지만 event-level CI 는
음수. 만약 event-level 을 후검사로 처리했다면 R-2 로 넘어가 대량 리소스 낭비.
Lesson #74 강화판: cross-sym / cross-target 확산 패러다임은 아예 R-1 evaluator
안에서 event-level 이 primary, trade-level 이 secondary 로 판정 순서를 뒤집는다.

## 산출물

- Script:  `backend/scripts/research/paradigm_251_cross_sym_oi_daily_drop_contagion_bilateral_5d_r1.py`
- Metrics: `backend/runs/research_track/paradigm_251_cross_sym_oi_daily_drop_contagion_bilateral_5d/r1__metrics.json`
- Trades:  `backend/runs/research_track/paradigm_251_cross_sym_oi_daily_drop_contagion_bilateral_5d/trades_B_focus_DOGEUSDT.json`
- G1/G2:   `backend/runs/research_track/paradigm_251_cross_sym_oi_daily_drop_contagion_bilateral_5d/tier3_gate__DOGEUSDT.json`

## 재발의 금지 조건

- OI daily drop / spike z-trigger + cross-sym forward-hold family (본 DNA)
- 특히 5-day 이상 forward window (alpha decay 노출)
- 재시도 시: (a) 이벤트를 규모/속도 축으로 재분해, (b) event-level 판정 primary,
  (c) 표본을 recency-weighted 로 재검증 후에만 발의.
