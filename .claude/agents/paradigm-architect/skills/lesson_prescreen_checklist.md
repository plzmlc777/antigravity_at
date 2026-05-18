# Skill: Q3 Lesson Prescreen Checklist

> Parent agent: `paradigm-architect`
> Purpose: Pre-flight grid covering all 29 Q3 cumulative lessons — block paradigm dispatch when applicable
> Tools: Read

> Last sync: 2026-05-18 KST 22:13 (lessons #1-#29 inclusive, lesson #29 promoted candidate → confirmed via paradigm 92+93 dual dogfood). Refresh from `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.2 if newer lessons exist.

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

### #26 — Aggregate R-1 PASS ≠ regime-robust (temporal WF mandatory)
**Trigger**: R-1 aggregate PASS at three-gate + Concentration.
**Check**: R-2 must include walk-forward 5-fold TS-CV + per-quarter strict ratio
**Action**: at R-2, if `n_folds_pass < 3/5` → FRAGILE_TEMPORAL_WF_FAIL graveyard. (Paradigm 87 precedent)

### #27 — Entry-side vs exit-side mechanism pre-classification
**Trigger**: paradigm proposes external event as decision driver.
**Check**: is event entry-side (immediate demand pull) or exit-side (forced liquidation)?
**Action**: exit-side events have fragility (post-event price action 분산 큼). 사전 분류 필수, exit-side는 R-2 robustness 통과 어려움 경고. (Paradigm 87+88 precedent)

#### #27 amendment — immediate vs delayed/indirect entry
Entry-side 분류만으로 부족. Immediate-demand vs delayed/indirect 추가 분류 필수:
- Immediate: 시장 onboarding listing announcement, ETF inflow event 등 (즉시 매수 압력)
- Delayed/indirect: stablecoin mint (실수요 시점 분산), token unlock (vesting cliff 후 매도 압력 분산) — paradigm 87 fragility 동형

### #28 — Entry-side external event paradigm은 measurement substrate 시간 차원 존재 prescreen 의무
**Trigger**: R-0 진입 시점에 external event 데이터 substrate 가용성 미확인.
**Check**: substrate가 event 시점 전후 N hours/days 측정 가능한가? (예: Binance Futures perp onboardDate 이전은 HTTP 404)
**Action**: substrate 부재 시 DISPATCH_IMPOSSIBLE halt. R-0 단계에서 차단. (Paradigm 89 precedent)

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

### Family retire — KR equity post-earnings/guidance directional momentum [CONFIRMED 2026-05-18]
**Trigger**: 한국 주식 (KOSPI/KOSDAQ) earnings/guidance 발표 후 directional drift momentum hypothesis 발의 시도.
**Check**: paradigm 92 (H1 잠정실적) + paradigm 93 (H2 가이던스) 이중 graveyard 누적 입증. Family-wide 사전 차단.
**Action**: 다음 sub-mechanism 모두 `HALT_BEFORE_R1` 사전 차단 — (a) 잠정실적 directional momentum (b) 가이던스 변경 directional momentum (c) 사업/반기/분기 보고서 directional momentum (d) 컨센서스 surprise (Naver IR 추정치) momentum (e) 모든 hold period (1d~30d) × universe size 변형. **Family-distinct hypothesis만 R-1 dispatch 가능** — mean-reversion 방향 (단 fee floor / sigex 2.0 사전 통과 필수) / 비-directional event (vol expansion, pair trade, sector rotation) / 외부 event (lesson #27 amendment 추가 prescreen). 재검토 2026-11-18. ([[feedback_family_retire_kr_post_earnings]] 참조)

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
| 8 | Mirror antipattern | paradigm X mirror Y 자동 시도 금지, 별도 R-1 의무 |
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
2. For each lesson #11-#28, check if applicable to current hypothesis
3. If any prescreen fails → halt at R-0 with specific lesson cited
4. If all pass → proceed to r1_protocol.md execution

## Reference
- `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.2 — authoritative lesson index
- `.claude/plans/paradigm_architect_handoff.json` — recent session deltas
- 86 graveyard precedents — `backend/runs/research_track/graveyard__*.md`
