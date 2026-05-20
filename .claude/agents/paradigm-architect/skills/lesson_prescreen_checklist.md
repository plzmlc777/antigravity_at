# Skill: Q3 Lesson Prescreen Checklist

> Parent agent: `paradigm-architect`
> Purpose: Pre-flight grid covering all cumulative Q3 lessons — block paradigm dispatch when applicable
> Tools: Read

> Last sync: 2026-05-20 KST 15:38 (lessons #1-#33 + Lesson #21 sub-finding "axis-redundancy via primary-condition saturation" candidate paradigm 116 dogfood + **Lesson #41 DIFFUSE_POSITIVE_CONCENTRATION_FAIL confirmed-with-amendment 2 dogfoods (paradigm 115 + 116)** + **Lesson #42 PUMP-mirror absence / mechanism CLASS asymmetry candidate 1 dogfood (paradigm 117)** + **Lesson #43 R-3 OOS holdout mandatory candidate 1 dogfood (paradigm 117)** + **Lesson #44 survivorship cohort probe candidate 1 dogfood (paradigm 117)** + NARROW_SCOPE_LIFE_CHANGING_FAIL verdict 4 dogfoods (95+99+104+115)). Refresh from `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.2 + §6.8 + §6.9 + §6.10 + §6.11 + §6.12 + §6.13 + paradigm 115/116/117 graveyards if newer lessons exist.

## Critical Lessons (mandatory R-0 / R-1 prescreen halt grid)

For each lesson below, check applicability **before** generating R-1 code. If applicable, apply the gate action.

### #11 — Sample-density prescreen
**Trigger**: any R-1 with strict |z|>2 threshold + small universe.
**Check**: `expected_n_per_cell = windows × universe × trigger_rate < 30`
**Action**: halt at R-0, request universe widen or threshold relax. Do NOT dispatch.

### #15 — Non-focus PASS 4-condition promotion
**Trigger**: focus threshold FAILS three-gate but sweep reveals non-focus PASS.
**Check**: all 4 of (a) 4-gate pass (b) held-out R-1 replication ±10% (c) Bonferroni p ≤ 0.10 (d) hold-sweep sign consistency
**Action**: even if all 4 hold, treat as R-2 candidate, not R-1 PASS.

### #16 — Concentration Gate (mandatory at R-1)
**Trigger**: every R-1 PASS at three-gate.
**Check**: `quarter_pos_t_ratio >= 0.5` AND `symbol_ci_pos_ratio >= 0.30` AND `n_symbols_ci_pos >= 3`
**Action**: if Concentration FAIL → `CONCENTRATED_R1_PASS` halt, no auto-promote. (Paradigm 77 precedent)

### #19 — Symmetric Negative Test (joint-trigger)
**Trigger**: R-1 trigger condition = logical AND of two+ z-scores/threshold events.
**Check**: 4-quadrant evaluation (A focus + A mirror + B same-sign + B mirror) in single R-1 batch.
**Action**: all 4 FAIL → `BROAD_FALSIFIED` graveyard, no follow-up R-1. (Paradigm 80 precedent)

### #20 — Sign-conditional 4-cell partial PASS narrow-scope
**Trigger**: R-3 sign-cond stratify with focus FAIL + non-focus cell PASS three-gate isolated.
**Check**: Concentration on isolated cell (e.g., 3/13 alts only)
**Action**: halt `NARROW_SCOPE_CANDIDATE`. Do NOT auto-dispatch narrow variant. (Paradigm 81 precedent)

### #21 — Axis stacking does not synthesize alpha
**Trigger**: R-1 paradigm proposes combining 2+ feature axes (multi-feature k-means or composite z).
**Check**: per-cluster obs_t fully negative + max |gross| < fee floor (16bp)
**Action**: stacking alone insufficient. Need mechanism-grade signal, not statistical combine. (Paradigm 83 precedent)

#### #21 sub-finding — Axis-redundancy via primary-condition saturation [CANDIDATE 2026-05-20, 1 dogfood paradigm 116]
**Trigger**: R-1 paradigm proposes secondary axis on top of an existing primary trigger (e.g. ATR breakout + volume confirmation).
**Check**: empirical `retention = P(secondary_trigger | primary_trigger)` on prior cache. If retention ≥ 95% → secondary axis carries no orthogonal information.
**Action**: halt at R-0 + reformulate (either relax primary so secondary becomes informative, or seek truly orthogonal third axis — funding rate sign / BTC dominance regime / hour-of-day etc.).
**Why candidate**: paradigm 116 `alt_volume_confirmed_atr_breakout_continuation_long_2h` 1st dogfood — volume p80 overlay at k=1.5 retained 100% of paradigm 115 events, did NOT amplify pool sigex (+4.28 identical), syms_ci_pos 0/13 unchanged → `AXIS_REDUNDANT_NO_SYNTHESIS` verdict. Statement: amplification scales not just with each axis independent alpha but with **mutual information** between conditions.

### #22 — Stateful change-point detectors require frame-grade source frequency
**Trigger**: R-1 uses CUSUM / Page-Hinkley / Bayesian change-point on daily-frame source.
**Check**: source frame frequency vs detector minimum sample requirement
**Action**: daily aggregation → detector needs hourly+ frame. Halt + recommend re-frame. (Paradigm 84 precedent)

### #23 — Event-anchored low-frequency cycle × strict |z|>2 sparse trap
**Trigger**: R-1 anchored at daily cycle boundary (e.g., 00:00 UTC) × strict |z|>2 threshold.
**Check**: empirical trigger rate often 1-2% (not assumed 5%), per-cell < 30
**Action**: halt SAMPLE_INSUFFICIENT, relax threshold or widen window. (Paradigm 85 precedent)

### #24 — Boundary-event statistic class horizon-bound density
**Trigger**: R-1 uses streak/regime-transition/level-crossing as single boundary event.
**Check**: 2.4yr universe admits only 5-10 boundaries (1-2 orders of magnitude < spike trigger)
**Action**: halt SAMPLE_INSUFFICIENT, no threshold/length relaxation recovers. (Paradigm 86 precedent)

### #26 — Aggregate R-1 PASS ≠ regime-robust (temporal WF mandatory) [3 dogfoods 2026-05-19 amendment]
**Trigger**: R-1 aggregate PASS at three-gate + Concentration.
**Check**: R-2 must include walk-forward 5-fold TS-CV + per-quarter strict ratio. **Amendment 2026-05-19**: R-0 prescreen at substrate audit also — `n_measurable_quarters ≥ 4` auto-FAIL precondition.
**Action**: at R-2, if `n_folds_pass < 3/5` → FRAGILE_TEMPORAL_WF_FAIL graveyard. **At R-0**, if `n_measurable_quarters < 4` (prior-paradigm cache audit available) → SAMPLE_INSUFFICIENT_TEMPORAL_CONCENTRATION halt before R-1.

**Dogfood 누적 (3 confirmed 2026-05-19)**:
1. paradigm 87 binance_delisting — R-2 적발 FRAGILE_TEMPORAL_WF_FAIL (small-sample Concentration Gate per-quarter blind spot 적발)
2. paradigm 88 + 90 — Phase 1 prescreen halt (n_measurable_quarters < 4 사전 차단)
3. **paradigm 100 dart_h2_guidance_mean_reversion_neg_long_20d** (2026-05-19) — R-0 prescreen halt via paradigm 93 cache audit (자원 0 소모). EARNINGS_GUIDANCE_AMEND substrate Q1-clustered 99.5% (KR annual-results disclosure cycle), n_measurable_quarters=3 < 4. hold-extension/direction-flip/threshold-tweak 무력.

### #27 — Entry-side vs exit-side mechanism pre-classification
**Trigger**: paradigm proposes external event as decision driver.
**Check**: is event entry-side (immediate demand pull) or exit-side (forced liquidation)?
**Action**: exit-side events have fragility (post-event price action 분산 큼). 사전 분류 필수, exit-side는 R-2 robustness 통과 어려움 경고. (Paradigm 87+88 precedent)

#### #27 amendment — immediate vs delayed/indirect entry [4 dogfoods 2026-05-19]
Entry-side 분류만으로 부족. Immediate-demand vs delayed/indirect 추가 분류 필수:
- Immediate: 시장 onboarding listing announcement, ETF inflow event, **liquidation cascade margin call forced market order** (paradigm 100 candidate liquidation_cascade lesson #27 amendment 통과 사례) 등 (즉시 매수/매도 압력)
- Delayed/indirect: stablecoin mint (실수요 시점 분산), token unlock (vesting cliff 후 매도 압력 분산), **KR equity 자기주식 취득 결정 공시** (이사회 승인 + future 매입 권한, 분기 분산 VWAP 분할, [`disclosure_parser.py:60-62`](../../../backend/app/services/disclosure_parser.py#L60-L62) `Side.ENTRY_DELAYED` 사전 분류 명시) — paradigm 87 fragility 동형

**Dogfood 누적 (4 confirmed)**:
1. paradigm 87 binance_delisting — R-2 FRAGILE_TEMPORAL_WF_FAIL (confirmed)
2. paradigm 88 token_unlock_cliff — Phase 1 prescreen halt
3. paradigm 90 stablecoin_mint — Phase 1 prescreen halt
4. **paradigm 100 candidate dart_treasury_share_repurchase** (2026-05-19) — R-0 codebase classification halt (disclosure_parser.py 사전 분류 + Track 3 design doc §11.4 H3 차단 결정)

### #28 — Entry-side external event paradigm은 measurement substrate 시간 차원 존재 prescreen 의무 [5 dogfoods 2026-05-19]
**Trigger**: R-0 진입 시점에 external event 데이터 substrate 가용성 미확인.
**Check**: substrate가 event 시점 전후 N hours/days 측정 가능한가? (예: Binance Futures perp onboardDate 이전은 HTTP 404, liquidation history archive 부재)
**Action**: substrate 부재 시 DISPATCH_IMPOSSIBLE halt. R-0 단계에서 차단.

**Dogfood 누적 (5 effective)**:
1. paradigm 89 listing_pre_announce — pre-onboard HTTP 404 (BILLUSDT verified)
2. paradigm 90 stablecoin_mint — multi-chain freemium violation + sample insufficient
3. paradigm 100 candidate dart_treasury_share_repurchase — codebase pre-classification (#27 amendment direct)
4. **paradigm 100 candidate `binance_perp_liquidation_cascade_event_alt_intraday`** (2026-05-19) — **4 independent substrate fail modes**: (a) `data.binance.vision/.../liquidationSnapshot/` 트리 부재 (HTML cache only, S3 prefix empty), (b) `metrics/` csv 8칼럼 (OI + 4 L/S + taker buy/sell) liquidation 미포함, (c) REST `allForceOrders` 영구 폐기 ("out of maintenance"), `/fapi/v1/forceOrders` 계정 scoped, WS `!forceOrder@arr` live-only, (d) Mint forceOrder/liquidation recorder 사전 누적 0건. Q3 큐 §1 #1 ⭐⭐⭐ 최강 후보가 구조적 undispatchable
5. implicit precedents: paradigm 84 book_depth_cusum (frame frequency) + paradigm 85 pre_session_open_oi (event-anchored sample)

**메타 함의**: Q3 큐 §1 top candidates 중 가장 강한 claim (liquidation cascade)이 public 인프라에서 구조적 undispatchable. WS recorder 60-90d forward-collection (`!forceOrder@arr` stand-up) 또는 paid feed (Coinglass/Hyblock/Laevitas, [[feedback_no_freemium_trial]] 차단) 외 R-1 dispatch 불가.

### #29 — Cross-proxy strict (observable + fundamental both PASS) [CONFIRMED 2026-05-18]
**Trigger**: R-1 paradigm 발의 시 trigger가 관측 가능한 sentiment-driven proxy (gap, pre-event ret 등) 또는 fundamental signal (true YoY surprise, realized magnitude 등) 단일 차원.
**Check**: 동일 mechanism family에서 observable proxy + fundamental signal 두 트랙 독립 측정 가능한가? 두 트랙 모두 R-1 본체에 4-quadrant Symmetric Negative Test 한 batch 측정 의무.
**Action**:
- 두 트랙 모두 PASS 시: `PASS_R1_CROSS_PROXY_PROMOTE_R2` (진정한 paradigm)
- 한 트랙만 PASS 시: `SINGLE_PROXY_TRAP_{FUND|OBS}_ONLY` halt — paradigm-grade 아님 (paradigm 92 H1 gap proxy R-1 PASS but R-2c true YoY 0/5 동형 trap 입증)
- 두 트랙 모두 FAIL 시: `BROAD_FALSIFIED` graveyard
- 두 트랙이 opposite directional alignment 시: mean-reversion regime 진단, family advisory caution 권고

**Why CONFIRMED**:
1. Paradigm 92 (H1 KR equity 잠정실적 momentum) — gap proxy R-1 PASS_R1 (sigex +3.67) but R-2c true YoY 0/5 fold PASS, sentiment continuation ≠ fundamental momentum 입증
2. Paradigm 93 (H2 KR equity 가이던스 ±30% momentum) — cross-proxy strict 강제 R-1, fund pos×LONG sigex -0.97 + obs pos_pre_ret×LONG sigex +1.34 < 2.0, strict gate가 single-proxy marginal artifact 정확 차단

**Implementation**: R-1 protocol spec에 observable_track_quadrants + fundamental_track_quadrants 양 측정 의무화. 각 트랙 별 4-quadrant + Concentration Gate + three-gate eval, cross_proxy_verdict 자동 산출.

### Family retire — KR equity DART entry-side family [CONFIRMED 2026-05-18, 강화 2026-05-19 — 5 graveyards 누적 4 axes exhausted]
**Trigger**: 한국 주식 (KOSPI/KOSDAQ) DART entry-side directional/mean-reversion/immediate-event/non-directional-magnitude hypothesis 발의 시도.
**Check**: **5 graveyards 누적, 4 axes 모두 exhausted** — paradigm 92 (H1 잠정실적 directional) + paradigm 93 (H2 가이던스 cross-proxy directional) + paradigm 100 (H2 가이던스 mean-reversion 20d) + paradigm 101 (단일판매·공급계약 entry-side immediate 5d) + **paradigm 102 (단일판매·공급계약 non-directional vol expansion 5d 2026-05-19 15:40)**. Family-wide 모든 axis 결정적 폐기.
**Action**: 다음 sub-mechanism 모두 `HALT_BEFORE_R1` 사전 차단 — (a) 잠정실적 directional momentum (b) 가이던스 변경 directional momentum (c) 사업/반기/분기 보고서 directional momentum (d) 컨센서스 surprise momentum (e) 가이던스 mean-reversion direction (paradigm 100) (f) 단일판매·공급계약 entry-side immediate directional (paradigm 101) (g) **단일판매·공급계약 non-directional vol magnitude (paradigm 102)** (h) 모든 hold period (1d~30d) × universe size 변형.

**Family-distinct hypothesis 가능 path 정밀화 (2026-05-19 강화 amendment, 5 graveyards 후)**:
- ~~mean-reversion 방향 (paradigm 100 차단)~~
- ~~DART year-round filing entry-side immediate directional (paradigm 101 universe-drift artifact 차단)~~
- ~~비-directional volatility event paradigm (paradigm 102 conditioning trap 차단)~~
- **(a) external-event non-DART (NEW 잔존 path 2026-05-19)** — KIND / FRED / ECOS 정부 source 외부 event paradigm
- **(b) DART event + decorrelated outcome (NEW)** — cross-stock spillover / 섹터 rotation. announce stock 자체가 아닌 영향받는 다른 stocks vol / return 측정. paradigm 101 universe-drift + paradigm 102 conditioning trap 둘 다 회피 가능
- **(c) non-announcement event types (NEW)** — volume shock (일일 거래량 z-score +3σ) / 외국인 매수 비율 변화 등 공시 외 trading data trigger
- 외부 event 잔존 위험 — 자기주식/합병/분할은 lesson #27 amendment + paradigm 101/102 동형 trap risk

재검토 2026-11-18. ([[feedback_family_retire_kr_post_earnings]] + [[project_paradigm_100_dart_guidance_mean_reversion_milestone]] + [[project_paradigm_101_dart_supply_contract_universe_drift]] + [[project_paradigm_102_vol_expansion_conditioning_trap]] 참조)

### Family retire — Cross-asset volume share single-side simple-z 1d-hold [CONFIRMED 2026-05-19]
**Trigger**: BTC 24h volume share (또는 단일 sym volume share) simple z-score × single direction × 1d hold × 13-14 sym universe variant 발의 시도.
**Check**: paradigm 94 (LOW share BROAD_FALSIFIED_DIRECTION_INVERTED) + paradigm 95 (HIGH share NARROW_SCOPE_LIFE_CHANGING_FAIL) 양 방향 graveyard 누적 입증. 1d hold × 6.4% trigger frequency × 14 universe → per-trade edge / capital util 본질적 capped.
**Action**: 다음 sub-mechanism 모두 `HALT_BEFORE_R1` 사전 차단 — (a) BTC volume share simple z LOW/HIGH (b) 단일 sym volume share simple z (c) 1d hold × small universe (≤25) 변형. **Family-distinct hypothesis만 R-1 dispatch 가능** — multi-day persistence variant (3d/7d streak) / sector분할 (DeFi/L2/AI/메이저 alts spread) / multi-feature transform (z + persistence + sector composite) / universe 250 expand 후 capital util 회복 시도. ([[project_paradigm_volume_share_family]] 참조)

### Family retire — Funding single-signal sub-class [CONFIRMED 2026-05-19, 결정적 강화 2026-05-19 12:00 batch P1/P2/P3]
**Trigger**: funding rate 단일 신호 (any variant: z-score / threshold / categorical sign / momentum / extreme level / **cross-section dispersion / cross-section velocity / regime stratify / per-sym history velocity**) × single-axis (funding only) × 1-24h hold × 14-sym universe variant 발의 시도.
**Check**: 6 consecutive single-signal falsifications 누적 입증 — paradigm 73 (joint funding×OI) + paradigm 79 (extreme level retry) + paradigm 96 (sign flip categorical) + **paradigm 97 (cs velocity)** + **paradigm 98 (regime stratify dispersion)** + **paradigm 99 (per-sym history velocity)**. **Exception**: paradigm 22 funding_carry R-5 seeded (3-sym HBAR/AXS/COMP narrow-scope basis) + funding_dispersion R-5 seeded ETCUSDT (cs level z, per-symbol 1:1, R-2 non-ETC sharpe_pos 5/13 부분 falsified).
**Action**: 다음 sub-mechanism 모두 `HALT_BEFORE_R1` 사전 차단:
1. funding z-score / threshold / level / extreme level 단일 신호 any direction
2. funding categorical boundary (sign flip / persistence break / rate change)
3. funding joint with single non-funding axis (OI alone / volume alone — paradigm 73/79 동형)
4. funding momentum / trend filter (slope / acceleration)
5. **funding cross-section dispersion** (z of level vs universe) — funding_dispersion R-5 seeded + paradigm 97 candidate inventory halt 영역
6. **funding cross-section velocity** (z of Δ vs universe) — paradigm 97 정식 graveyard
7. **funding regime stratify dispersion** (BTC funding regime × cs z level) — paradigm 98 정식 graveyard
8. **funding per-sym history velocity** (z of Δ vs sym history) — paradigm 99 정식 graveyard

**Family-distinct hypothesis만 R-1 dispatch 가능** (정밀화 2026-05-19):
- per-sym specific carry narrow-scope (paradigm 22 model 확장, 추가 sym 검증)
- **funding term structure 진정한 family-distinct** — (a) multi-tenor funding curve slope (Binance 단일 8h tenor → 불가능) 또는 (b) funding cycle 시점 간 differential / velocity (8h-to-8h delta velocity, 미측정 valid path)
- funding × multi-axis composite (e.g., funding × vol regime × time-of-day) — paradigm 98 regime stratify single-axis 변형 차단
- funding × external event (e.g., funding pre/post major price event)
- **cross-exchange funding spread** (Binance vs Bybit Δfunding, NEW data axis 도입 시) — 본 family retire 외 새 differentiation 차원

**재검토 시점**: 2027-05-19 또는 새 funding-specific data axis (cross-exchange funding spread) 도입 시. ([[project_paradigm_96_funding_sign_flip_family_retire]] + [[project_paradigm_97_98_99_funding_family_completion]] 참조)

### Lesson — R-0 substrate quarterly distribution audit 의무 [CONFIRMED 자격 충족 2026-05-19, 2 dogfoods 양방향]
**Trigger**: paradigm 발의 시 prior-paradigm cache가 있거나 새 substrate scan 시 R-1 실행 전 substrate quarter distribution 사전 audit.
**Check**: paradigm_index에서 동일 substrate (DART 공시 type / Binance event class / universe etc.) prior paradigm cache audit 또는 신규 substrate scan. n_measurable_quarters 사전 측정.
**Action**:
- `n_measurable_quarters < 4` → lesson #26 amendment auto-FAIL precondition halt before R-1 (SAMPLE_INSUFFICIENT_TEMPORAL_CONCENTRATION verdict)
- `n_measurable_quarters ≥ 4` (year-round distribution) → GO_R1 정식 진행

**Why CONFIRMED 자격 (2 dogfoods 양방향 입증)**:
1. paradigm 100 dart_h2_guidance_mean_reversion_neg_long_20d — paradigm 93 cache audit (자원 0), n_measurable_quarters=3 → SAMPLE_INSUFFICIENT halt
2. **paradigm 101 dart_supply_contract_announce_long_5d (2026-05-19 14:56)** — DART 신규 scan ~54분, 2,421 events / 10/10 quarters year-round PASS → GO_R1 정식 실행 (paradigm 100 trap 회피 정확 입증)

**Implementation**: paradigm-architect agent r0_inventory_check skill에 "substrate quarterly distribution audit" sub-step 정식 추가. prior-paradigm cache 발견 시 자동 audit + 신규 substrate 시 scan-then-audit + n_measurable_quarters 측정 + lesson #26 amendment auto-FAIL precondition cross-check.

### Lesson #32 candidate — Universe-baseline-coherent A_focus trap (LEVEL coherence) [CANDIDATE 2026-05-19, 2 dogfoods paradigm 101 + 102]
**Trigger**: R-1 Symmetric Negative Test 4-quadrant 측정 시 A focus three-gate `t_obs ≥ 2.0 PASS` but `signal_t_excess < 2.0` AND `B_baseline_net ≥ A_focus_net`.
**Check**: A_focus가 universe baseline drift artifact인지 LEVEL coherence sanity check — A focus vs B baseline net 차이 측정 의무.
**Action**: `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` verdict 발급. mechanism reject.

**Why dogfood (2 양면)**:
1. paradigm 101 dart_supply_contract_announce_long_5d — A focus net +52.9bp / t_obs +2.49 PASS but signal_t_excess -0.75 + B baseline +68.4bp ≥ A focus → universe drift dominance 진단. cross-proxy inverse + per-symbol concentration FAIL 동반.
2. **paradigm 102 dart_supply_contract_announce_vol_expansion_5d** — Lesson #32 LEVEL coherence (vol_ratio level metric)에서 A focus 1.99 vs B baseline 0.96 = excess +1.03 (20× threshold) **PASS**. 그러나 별개 Lesson #33 POST-CONDITIONING payoff coherence에서 FAIL (paradigm 102 graveyard 사유).

**Implementation**: paradigm-architect R-1 verdict tree에 `BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT` 정식 추가. Symmetric Negative Test 4-quadrant 결과 비교 시 A focus vs B baseline net (또는 trigger metric LEVEL) 차이 측정 의무화.

### NEW Lesson #33 candidate — Magnitude-as-outcome equals conditioning trap (POST-CONDITIONING payoff coherence) [CANDIDATE 2026-05-19, 1 dogfood paradigm 102]

**Trigger**: trigger filter (magnitude-based: vol_ratio / range_ratio / volume_ratio 등)와 outcome metric (magnitude-based: |return| / realized vol / drawdown 등)이 수학적 상관 시.

**Check**: R-1 4-quadrant에 **5번째 cell `B_baseline_same_filter`** 추가 의무 — 동일 filter 적용 universe baseline의 outcome 측정.

**Action verdict 분기**:
- `A_focus_sig_t_excess ≥ B_baseline_same_filter_sig_t_excess + delta(≥1.0)` 충족 시 → valid signal
- 미충족 시 → `BROAD_FALSIFIED_CONDITIONING_TRAP` (NEW verdict candidate)

**Distinct from Lesson #32**:
- Lesson #32: **LEVEL coherence** — trigger metric (vol_ratio) 자체에서 A focus vs B baseline 비교
- Lesson #33: **POST-CONDITIONING payoff coherence** — outcome metric (|return|) 측면에서 A focus vs B baseline_same_filter 비교
- 두 trap이 별개 차원 — paradigm 102가 #32 PASS + #33 FAIL로 입증

**Why CANDIDATE (1 dogfood)**:
- paradigm 102 dart_supply_contract_announce_vol_expansion_5d (2026-05-19) — vol_ratio≥1.5 filter (magnitude trigger) + |fwd_ret_5d| outcome (magnitude outcome) 수학적 상관. A focus 987bp < B baseline_same_filter (vr≥1.5) 1,073bp = universe baseline mechanics로 explained, announce 정보 incremental alpha 0. threshold tweak (1.3/2.0/2.5) 복구 불가능.

**Implementation**: paradigm-architect agent `r0_inventory_check` skill + `lesson_prescreen_checklist.md` 양 영역 hook 의무. trigger metric × outcome metric mechanical correlation prescreen rule.

### Lesson #41 — DIFFUSE_POSITIVE_CONCENTRATION_FAIL verdict branch [confirmed-with-amendment 2026-05-20, 2 dogfoods paradigm 115 + 116]
**Trigger**: R-1 produces pool-level signal_t_excess ≥ +4σ AND ci_lower > 0 (strong pool evidence) but Concentration Gate fails on per-symbol leg (syms_ci_pos 0–2/13, syms_pos_mean 50–70% positive but individually non-significant) AND per-sym n < 100.
**Check**: small-cohort universe (≤13 sym) per-symbol bootstrap CI tightness scales with per-sym n. Pool-level alpha may be real but diffused across symbols too thinly to satisfy Concentration leg.
**Action**:
- DO NOT auto-graveyard — instead promote to R-2 with **universe expansion** (25+ sym Binance Futures perp tier 1+2) to test whether per-sym n ≥ 150 recovers syms_ci_pos.
- **Amendment (paradigm 115 R-2 dogfood)**: even if expansion validates diffuse alpha (paradigm 115 R-2 expanded 29-sym pool sigex +6.96, ci_lower +14.84bp, syms_ci_pos 3/29), if `per_trade_edge_net < 2%` life-changing 4-dim hard-blocker → graveyard verdict `confirmed_but_narrow_scope_life_changing_fail`. Pool-level mechanism real but operationally moot — DO NOT seed R-5.

**Why confirmed-with-amendment (2 paradigm-level dogfoods)**:
1. paradigm 115 `alt_atr_normalized_range_breakout_continuation_long_2h` — k=1.5 4h hold pool sigex +4.28 / ci_lower +5.58bp / 0/13 syms_ci_pos / 9/13 syms_pos_mean. R-2 universe expansion (16 added alts) recovered 3/29 syms_ci_pos + amplified pool sigex +63%, but per-trade edge 0.27% < 2% → R2_FAIL_LIFE_CHANGING.
2. paradigm 116 `alt_volume_confirmed_atr_breakout_continuation_long_2h` — k=1.5 vol_p60 4h cell mechanically identical (100% event retention via volume p80 overlay) → ci_lower +5.58bp identical to paradigm 115, syms_ci_pos 0/13 reproduced. Same DIFFUSE_POSITIVE mode at smaller n confirmed prediction.

**Implementation**: paradigm-architect R-1 verdict tree新規 분기 `DIFFUSE_POSITIVE_CONCENTRATION_FAIL` 정식 추가. Pool-evidence-strong + concentration-fail + per-sym n<100 + per_trade_edge ≥ 2% candidate 시 R-2 universe expansion 자동 권고. per_trade_edge < 2% 동반 시 graveyard `confirmed_but_narrow_scope_life_changing_fail`.

### Lesson #42 — Mechanism CLASS asymmetry undetectable in R-1/R-2 single-axis measurement (PUMP-mirror absence) [CANDIDATE 2026-05-20, 1 dogfood paradigm 117]
**Trigger**: R-1 framed as "extreme magnitude → mean-revert" class paradigm where mathematical mirror (A_focus = +X, A_mirror = −X by identity) does NOT test the symmetric mechanism class. Examples: drawdown × LONG (capitulation mean-reversion) vs PUMP × SHORT (euphoria correction).
**Check**: R-1/R-2 4-quadrant SNT is mathematical-mirror only — `A_mirror = −A_focus` is identity, not an orthogonal test. The TRUE mechanism class test requires an **orthogonal trigger** (PUMP-trigger × SHORT-direction, not drawdown-trigger × SHORT-direction).
**Action**: at R-3, mandatory caveat for any "extreme magnitude → mean-revert" class paradigm — measure `B_same_sign_orthogonal` cell (PUMP × SHORT for drawdown × LONG paradigm; or symmetric pre-trigger from opposite tail). If B_same_sign sigex < +1.0 while A_focus sigex ≥ +2.0 → mechanism is direction-asymmetric, NOT a symmetric "magnitude → mean-revert" class. Narrative must be rewritten ("fear-driven capitulation → bounce", not "extreme magnitude → mean-revert").

**Why candidate (1 dogfood)**: paradigm 117 `alt_extreme_24h_drawdown_24h_reversion_long` Caveat 1 — A_focus (drawdown × LONG) sigex +8.71 ✓ / A_mirror (drawdown × SHORT) −8.71 (math mirror identity, sanity check) / **B_same_sign (PUMP × SHORT) sigex +0.28** ✗ null / B_mirror_real (PUMP × LONG) sigex +1.20 null. Mechanism is asymmetric — capitulation triggers forced-deleveraging cycle (liquidation cascade + funding flip + late-short cover), euphoria does NOT have the orthogonal forced-buy pressure.

**Implementation**: paradigm-architect R-3 caveat suite에 `mechanism_class_orthogonal_mirror_test` 추가. Extreme-magnitude → mean-revert class hypothesis 식별 시 orthogonal trigger (opposite tail × opposite direction) measurement 의무. B_same_sign sigex < +1.0 시 mechanism narrative 재구성 + paradigm scope 좁힘.

### Lesson #43 — R-2 broad-shoulders + monotone + TS-CV all-pass does NOT predict R-3 OOS PASS [CANDIDATE 2026-05-20, 1 dogfood paradigm 117]
**Trigger**: R-2 5 gates all GREEN (pool-drift OK, TS-CV ≥3/5, threshold monotone, broad-shoulders top-3 PASS, lc4 4/4) → graduate to R-3.
**Check**: R-2 GREEN gates can coexist with substantive temporal decay over OOS holdout. Decay enough to drop net edge below life-changing 2%/trade floor even with otherwise healthy stats (sigex still > 3, perm_p ≤ 0.01, direction positive).
**Action**: holdout OOS must be checked at R-3 with strict edge_ratio criteria:
- `train_edge / oos_edge ≤ 0.30 decay` (i.e. edge_ratio ≥ 0.70) AND
- life-changing 4-dim independently re-evaluated on OOS subset only (not pooled Train+OOS) AND
- if edge_ratio ∈ (0.50, 0.70) → marginal, document but do not auto-pass; ratio < 0.50 → auto-graveyard

**Why candidate (1 dogfood)**: paradigm 117 — Train (2024-05-30 ~ 2025-06-30) n=288 / edge +2.978%/trade / sigex +8.12 / lc4 4/4. OOS (2025-07-01 ~ 2026-04-30) n=118 / edge +1.929%/trade / sigex +3.51 / **lc4 3/4 (edge dim fails 2%)**. Edge ratio 0.65 (35% decay). Signal still statistically real on OOS but decayed past life-changing 2%/trade threshold.

**Implementation**: paradigm-architect R-3 caveat suite에 `holdout_oos_decay_audit` 추가 — strict edge_ratio ≥ 0.70 cutoff + OOS-only life-changing 4-dim 의무. R-2 PASS는 R-3 진행 자격이지 R-3 통과 보장 아님 명시.

### Lesson #44 — Survivorship cohort probe via quality-tier-lower still-listed weakness [CANDIDATE 2026-05-20, 1 dogfood paradigm 117]
**Trigger**: R-3 paradigm with implicit tier-1 liquid-major universe (e.g. 28-alt cohort hand-picked for liquidity). Question: does mechanism generalize beyond tier-1 cohort?
**Check**: Binance Vision archive does NOT preserve full history for symbols delisted before late 2023 (true survivorship cohort sample insufficient). Substitute: probe **still-listed weak-tier alts** (BAKEUSDT, CTSIUSDT, FTMUSDT class — lower liquidity tier still in current universe) for same trigger. If extended-tier probe shows opposite-direction result → mechanism's broad-cohort generalization at risk = **cohort-tier selection bias** (NOT classical survivorship but equally disabling).
**Action**: at R-3 mandatory probe — measure conservative R-5 edge = (50% surviving + 50% extended-tier cohort) edge. If conservative edge < life-changing 2%/trade floor → graveyard regardless of tier-1-only PASS.

**Why candidate (1 dogfood)**: paradigm 117 — tier-1 28-alt universe R-2 PASS edge +1.93%/trade. Extended-tier probe: BAKEUSDT (n=30) **-7.93%/trade**, CTSIUSDT (n=20) -0.91%, FTMUSDT (n=11) +0.14% — weak-tier alts show **continuation** (NOT reversion) after −15% drawdowns. Pooled extended n=63 edge **-3.86%/trade**. Conservative R-5 edge (50% surviving + 50% extended) = **-0.59%/trade << 2%** → fail.

**Implementation**: paradigm-architect R-3 caveat suite에 `survivorship_cohort_tier_probe` 추가. tier-1 universe 가설 발의 시 R-3 단계에서 quality-tier-lower (paradigm 117 BAKEUSDT/CTSIUSDT/FTMUSDT class) extended probe 의무 + conservative R-5 edge 계산.

### NEW verdict — BROAD_FALSIFIED_CONDITIONING_TRAP candidate (Lesson #33 dogfood)

**Trigger condition**: trigger metric × outcome metric magnitude-based 수학적 상관 + A focus outcome ≤ B baseline_same_filter outcome.

**Halt criteria**:
- `A_focus_sig_t_excess < B_baseline_same_filter_sig_t_excess + 1.0`
- 4-dim PASS는 universe baseline conditioning inheritance artifact (paradigm 101 + 102 동형 false-positive)

**Action**: mechanism reject, R-2 미진행, graveyard 등재.

### NEW verdict — BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT [정식 추가 2026-05-19]
**Trigger condition**: A_focus signal positive but B_baseline (non-event universe drift) outperforms or ≥ A_focus.
**Halt criteria** (any one):
- signal_t_excess < 2.0 despite t_obs PASS
- 4-dim PASS는 universe drift artifact false-positive (paradigm 95 동형)
- cross-proxy inverse 동반 시 (Lesson #29 strict 강화)
**Action**: mechanism reject, R-2 미진행, graveyard 등재.

### #31 — Cross-section dispersion family R-5 점유 inventory prescreen [CONFIRMED 2026-05-19, 2 dogfoods]

**Trigger**: R-1 paradigm 발의 시 statistic axis = cross-section dispersion (sym i feature vs universe mean/std/median z-score) family.

**Check**: paradigm_index에서 기존 seeded paradigm DNA 6-dim cross-check — (1) substrate (2) statistic (3) direction (4) mechanism axis-level (5) universe scope (6) threshold-or-hold.

**Action**:
- DNA cutoff ≥ 5/6 일치 (parametric variant only) → `FAIL_FAMILY_SUBSUMED` R-0 inventory halt, R-1 dispatch 차단
- DNA 4/6 이하 → 다음 차원 (시간 frame / event anchor / regime conditioning) 새 dimension 결합 시 valid family-distinct, R-1 dispatch 가능

**Why CONFIRMED**:
1. dogfood 1 — paradigm 97 candidate `funding_term_structure_cross_sym_dispersion` (DNA 5/6 with funding_dispersion R-5 seeded ETCUSDT, parametric variant only) → inventory halt 사전 차단으로 R-1 자원 + paper pool noise 회피
2. dogfood 2 — batch P1/P2/P3 paradigm 97/98/99 (DNA ≤ 4/6 cross-check 통과) → dispatch 정상, family-distinct 검증 자동화 정상 작동

**Implementation**: paradigm-architect agent r0_inventory_check skill에 cross-section dispersion family-aware DNA 6-dim cross-check 의무 포함. paradigm 96 graveyard §family-distinct path 정의 모호성 해소 후속 dispatch 의무. ([[project_paradigm_97_funding_dispersion_inventory_halt]] + [[project_paradigm_97_98_99_funding_family_completion]] 참조)

### #30 — Short-data ad-hoc R-1 verdict reliability caution [CANDIDATE 2026-05-19, 1 dogfood]
**Trigger**: ad-hoc R-1 실행 시 data window가 universe full-window의 ≤ 30%.
**Check**: r0_inventory_check에서 `data_window_ratio = ad_hoc_window_days / full_universe_window_days` 측정. 
- ratio ≥ 0.50: verdict reliable
- 0.30 ≤ ratio < 0.50: verdict moderate, caution flag in summary
- ratio < 0.30: verdict **advisory only**, full-window 재실행 의무, 본 R-1 verdict 신뢰 금지
**Action**: ratio < 0.30 시 paradigm-architect r0 단계에서 caution flag + full-window 재실행 prerequisite dispatch 의무. paradigm 94 dogfood: local 72d (8.5% slice) → BROAD_FALSIFIED_FEE_FLOOR / Mint 845d (full) → BROAD_FALSIFIED_DIRECTION_INVERTED 진단 격차. ([[feedback_lesson_30_short_data_verdict]] 참조)

### Verdict — NARROW_SCOPE_LIFE_CHANGING_FAIL [CONFIRMED 2026-05-19, 4 dogfoods 2026-05-20]
**Trigger**: R-1 결과 Lesson #20 narrow-scope 4-cond (a 4-gate / b held-out / c Bonferroni / d hold sweep) ALL PASS 자격 충족, 또는 mirror-only PASS 시 (lesson #8 antipattern).
**Check**: life-changing 4-dim gate 측정 의무 — trades/yr ≥ 12 / per_trade_edge_net ≥ 2.0% / capital_util ≥ 30% / annualized_sharpe ≥ 1.5
**Action**:
- 4/4 PASS → `NARROW_SCOPE_CANDIDATE` (R-2 진행 가능, lesson #20 정상 verdict)
- any FAIL → `NARROW_SCOPE_LIFE_CHANGING_FAIL` (graveyard, R-2 미진행)
- mirror-only PASS + 4-dim any FAIL → `BROAD_FALSIFIED_MIRROR_ONLY` (paradigm 99 dogfood, lesson #8 mirror antipattern + 4-dim FAIL 결합)

**Why CONFIRMED**:
1. dogfood 1 — paradigm 95 `cross_asset_volume_concentration_alt_long_1d` 통계 4-cond ALL PASS but per-trade edge 0.47% (4.3x deficit) + capital util 6.39% (4.7x deficit). 1d hold × 6.4% trigger frequency × 14 universe capital cap 본질로 R-2 회복 불가.
2. dogfood 2 — paradigm 99 `funding_cycle_8h_differential_velocity_per_sym` B mirror cell 3-gate PASS (sigex +3.19 / ci +5.88) but per-trade edge **0.24% (8x deficit)**, 3/4 dim PASS only (trades/yr 548.7 / util 0.50 / sharpe 1.68 PASS, edge FAIL). Concentration 0/13 ci_pos (mirror-only PASS preempts narrow-scope promotion). lesson #8 mirror antipattern + 4-dim FAIL 결합 verdict.
3. dogfood 3 — paradigm 104 `cross_exchange_oi_differential` extended hold 480m/1440m edge 0.26-0.77% per-trade range. Hourly-scale crypto continuation paradigm class 일관 sub-1%/trade ceiling 입증.
4. dogfood 4 — paradigm 115 `alt_atr_normalized_range_breakout_continuation_long_2h` R-2 universe expansion (29 alts) 후 pool sigex +6.96 / ci_lower +14.84bp / WF 3/5 PASS / 2/3 deep ci_95_pos but per-trade edge 0.27% << 2% → mechanism CONFIRMED real but operationally moot. Lesson #41 DIFFUSE_POSITIVE 우주 확장 path도 life-changing hard-block 우선 적용 입증.

**Implementation**: paradigm-architect R-1 verdict tree에 life-changing 4-dim layer를 Lesson #20 narrow-scope 자격 부여 **직전** 분기로 통합 의무. mirror-only PASS 케이스도 동일 측정 의무 (B mirror cell 4-dim 통과 시 narrow-scope-mirror candidate 자격 부여). ([[feedback_narrow_scope_life_changing_fail_verdict]] + [[project_paradigm_97_98_99_funding_family_completion]] 참조)

## Earlier Lessons (#1-#10 condensed)

| # | Theme | One-line gate |
|---|---|---|
| 1 | Fee saturation | observed t vs fee-saturated null mean — 8 bp × 1000 trades → null t ≈ -5σ |
| 2 | Mock vs real | mocked tests can hide real divergence — paper baseline measurement obligatory |
| 3 | Source frequency | daily aggregation cannot support 5m frame hypothesis |
| 4 | Universe size | sparse universe (≤14 alts) + cross-sec rank → fee/sample 제약 막힘 |
| 5 | Cross-sectional MR | crypto perp 5d MR FAIL (vs equity Jegadeesh 1990) — continuation regime |
| 6 | 30d momentum | Carhart 30d FAIL on crypto perp 49wk sample |
| 7 | Skewness sign-split | 1h 3rd moment both directions sub-fee |
| 8 | Mirror antipattern | paradigm X mirror Y 자동 시도 금지, 별도 R-1 의무. **2026-05-19 amendment candidate** (paradigm 99): mirror-only PASS 케이스에서 (a) 정통 mirror antipattern (cross-direction asymmetry) vs (b) symmetric magnitude bias ("leverage shock magnitude → general upward bias", A high LONG + B mirror low LONG 모두 양수) 사전 분류 의무 |
| 9 | sign-split conditional | BTC up-trigger / down-trigger 분리 시 강한 contagion 가능 |
| 10 | Taker-side family fee floor | taker_buy_vol family 60m hold fee floor 미달, family retire |

## #12 - #14, #17 - #18, #25 (cumulative)

- **#12** book_depth daily aggregates는 paradigm-grade 알파 부족
- **#13** BTC RV unsigned trigger LONG fail / sign-split rescue 가능
- **#14** vol regime stratify에서 aggregate PASS 반증 가능
- **#17** _perm_utils production-ready (fee_aware + bootstrap + block_perm 통합)
- **#18** mechanical vs substantive verdict — perm null 음수 편향 trap
- **#25** 4-dim gate × intraday signal incompatibility — life-changing campaign 1차 session halt 사유

## How to use this checklist

Before generating R-1 code:
1. Read this skill file (Read tool)
2. For each lesson #11-#30, check if applicable to current hypothesis
3. r0_inventory_check 단계에서 data_window_ratio (Lesson #30) 측정
4. If any prescreen fails → halt at R-0 with specific lesson cited
5. If all pass → proceed to r1_protocol.md execution

R-1 verdict 분기 시 (Lesson #20 narrow-scope candidate 자격 충족 case):
- life-changing 4-dim gate 측정 의무 → NARROW_SCOPE_CANDIDATE (4/4) vs NARROW_SCOPE_LIFE_CHANGING_FAIL (any FAIL)

## Reference
- `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.2 — authoritative lesson index
- `.claude/plans/paradigm_architect_handoff.json` — recent session deltas
- 95 graveyard precedents — `backend/runs/research_track/graveyard__*.md`
