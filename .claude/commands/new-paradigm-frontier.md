---
description: 51 graveyards / 4 retired families / 20 lessons 메타 상황에서 진정 NOVEL paradigm 발굴. multi-axis novelty matrix + 새 paradigm class 적극 제안 + R-1 분리 모드 dispatch.
---

# /new-paradigm-frontier — 진정 novel paradigm 발굴 (frontier scout)

기존 `/new-paradigm`은 retired family 회피 정도의 single-axis novelty만 강제. 본 명령은 **5-axis novelty matrix** + **51 graveyards 전체 카탈로그 분석** + **진정 새 paradigm class 적극 제안**으로 frontier 극소화 메타 상황(5% PASS rate)에서도 의미 있는 candidate 발굴.

**자동 거부 패턴**:
- z-score 변형 only (lookback / threshold만 다름)
- 기존 mechanism + new data source (single-axis novelty)
- Retired family direct extension (taker / cross-asset corr / geometric path / funding × OI joint / OI×premium joint z-level)
- 단순 sign-conditional split만 추가

**필수 통과 조건**: 5-axis 중 최소 **2 axes**에서 novel이어야 dispatch 진행.

---

## Step 0 — 컨텍스트 자동 로드 (새 세션 self-contained)

다음을 순서대로 Read:

1. `/home/hcpark/antigravity/.claude/plans/paradigm_architect_handoff.json` — 메타 상태 (turn 5 기준 51 R-1 graveyards, 4 retired families, 20 lessons, 8 R-5 시드, 5% PASS rate)
2. `/home/hcpark/antigravity/backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.2 (20 lessons) + §6.4 (Tier 4 retired families)
3. `/home/hcpark/antigravity/backend/runs/research_track/INDEX.md` — 시드 8개 + 51 graveyards 전체 카탈로그
4. `/home/hcpark/antigravity/.claude/plans/new_paradigm_session_primer.md` — 운영 원칙 + DNA 매트릭스 + 게이트 기준
5. memory `MEMORY.md` — Q3 paradigm 관련 인덱스 (특히 `project_paradigm_*` entries)

---

## Step 1 — Paradigm space 카탈로그 분석 (Mint SSH)

```bash
# 51 graveyards 전체 list
ssh mint@183.99.228.81 "ls ~/auto_trading/backend/runs/research_track/_graveyard/ | sort | nl"

# 시드 8개 + 일부 graveyard 요약
ssh mint@183.99.228.81 "cat ~/auto_trading/backend/runs/research_track/INDEX.md | grep -E 'R-5 paper seeded|✅|graveyard' | head -80"

# 보유 데이터 인벤토리 (백필 ETA 판단용)
ssh mint@183.99.228.81 "ls ~/auto_trading/backend/runs/ | head -20; ls ~/auto_trading/backend/runs/microstructure/ | head -3; ls ~/auto_trading/backend/runs/premium_index/ | head -5"
```

---

## Step 2 — 5-axis novelty 매트릭스 구축

각 시드/graveyard paradigm을 5-axis로 분류 후 검증된 combinations 매트릭스 작성:

| Axis | 검증된 categories (회피해야 할) | 미탐색 영역 (novelty 가능) |
|---|---|---|
| **Data source** | OHLCV / premium 1d, 5m / funding 1d, 5m / OI 1d, 5m / LSR / taker_buy_sell_ratio | book_depth (WS only) / liquidation_snapshot (issue #337 blocked) / on-chain (free API) / mark vs index separate legs |
| **Statistic** | z-score level / z-score velocity / rolling correlation / rank rotation / dispersion z / regime breakout | sequence pattern / CUSUM change-point / Bayesian anomaly / embedding cluster / multi-resolution composite / stateful event |
| **Time scale** | 1m / 5m / 30m / 1h / 1d / weekly / monthly | sub-minute (tick-level, no data) / multi-resolution joint (5m + 1h + 1d sequential) / event-relative (X bars before/after funding boundary) |
| **Universe** | single-sym / 13-alt cross-sym / pairwise BTC↔ETH / cohort listing date | rotational cluster (top-K by feature) / lifecycle-stratified (new vs established alts) / regime-stratified universe |
| **Mechanism** | mean-reversion / momentum continuation / breakout follow / cascade fade / decoupling rebound / regime filter | liquidation prediction proxy / behavioral FOMO proxy / order flow archeology / cross-resolution lead-lag / stateful change-point / latent regime classification |

**Strict rule**: 후보 paradigm은 5 axes 중 **최소 2 axes**에서 미탐색 영역에 위치해야 함.

---

## Step 3 — 새 paradigm class 후보 라이브러리 (생각의 출발점)

전통 z-score 변형이 아닌 **새 mechanism class**:

### Class A — Stateful event detection
- **CUSUM premium z-score change-point**: 누적 합 기반 structural break 감지 (level z-score와 다른 statistic dimension)
- **Bayesian online change-point** (premium / funding / OI 시계열에서)
- **Anomaly detection (isolation forest / autoencoder reconstruction error)**: multi-feature joint anomaly score

### Class B — Multi-resolution joint
- **5m + 1h + 1d 신호 sequential dependency**: 1d trend 확정 → 1h regime confirm → 5m entry trigger (cascade gate)
- **Cross-resolution lead-lag**: 1m → 5m → 30m predictive lag analysis (cross_symbol_lead_lag와 다른 axis)

### Class C — Behavioral proxies
- **FOMO indicator**: (5m return × volume × prior 1h momentum) joint extreme — paradigm 1 wick_reversal과 다른 mechanism
- **Ladder cascade**: 연속 N개 5m breakout 또는 funding flip 누적
- **Capitulation proxy**: high volume × max drawdown depth × low premium (sell exhaustion)

### Class D — Latent regime
- **HMM beyond**: 2-3 state regime detection이 아닌 더 풍부한 latent space (UMAP/PCA embedding → k-means or DBSCAN cluster)
- **Multi-feature joint regime**: premium + funding + OI 5m 동시 z를 latent space로 → regime별 returns

### Class E — Cross-domain proxy
- **mark vs index separate legs momentum**: premium = (mark-index)/index decomposition. mark 단독 momentum or index 단독 momentum (joint 아님, paradigm 80 OI×premium joint와 다른 axis)
- **funding × OI velocity sign-conditional asymmetry** (paradigm 71/73/79 family와 다른 mechanism — joint event 아닌 conditional 분리)

### Class F — Pre-event / post-event microstructure
- **Pre-funding window dynamics**: 8h funding boundary 30-60min 전 5m bars premium/OI behavior — funding_window_anomaly graveyard와 다른 mechanism (window 직전 traders flow timing)
- **Post-listing decay**: 신상 alts D+1 / D+7 / D+30 행동 (lifecycle_pump_decay R-5 시드 variant가 아닌 stratified universe split)

---

## Step 4 — Top 3 candidates 사용자에게 제시 (보고 1회)

각 candidate에 대해 다음 6항목 한꺼번에 보고:

```
## Candidate N — {paradigm_name}
- 가설 한 문장
- 5-axis novelty: [axis1: NOVEL / axis2: known / axis3: NOVEL / axis4: ... / axis5: ...]
  → novelty score: X/5 axes (최소 2 통과 필수)
- 기존 51 graveyards와 거리: 가장 가까운 graveyard {name} + 차이 명시 (어떤 axis가 다른지)
- 데이터 가용성: 이미 보유 / 백필 필요 (ETA 추정)
- 기대 시드 가능성: 5% PASS rate 메타 대비 추정 (예: paradigm class novelty 고려 시 10-15%)
- 최대 약점: 어떤 §3 antipattern과 borderline (§3-A rare-event / §3-D directional bias / §3-F calendar / §3-G family-extension / §3-M reference-price / §3-N etc.)
- ROI 평가: ⭐ (높음) / ⭐⭐ (중간) / ⭐⭐⭐ (낮음, 시도 가치)
```

사용자 select 받기 (1-3 중 하나 또는 "다른 방향 brainstorm").

---

## Step 5 — paradigm-architect R-1 분리 모드 dispatch

기존 `/new-paradigm`과 동일한 R-1 ONLY halt 규칙 + lesson #19/#20 통합:

**필수 prompt 제약**:
> "Execute R-1 PoC ONLY. Halt after R-1 completion regardless of PASS/FAIL/borderline. Do NOT proceed to R-2 without explicit follow-up invocation. Do NOT spawn background tasks for R-2/R-3 perm tests. R-1 PoC must complete in foreground within 15 min.
> 
> Mandatory: 20 lessons (Q3 §6.2) 회피 + 4 retired families 회피 + 5-axis novelty 명시 (Step 4 보고 시 식별된 NOVEL axes 재확인). joint-trigger paradigm이면 Lesson #19 Symmetric Negative Test 4-quadrant 의무. sign-conditional 4-cell partial-PASS이면 Lesson #20 narrow-scope 자격 정책."

호출 형식:
```
Agent({
  subagent_type: "paradigm-architect",
  description: "<paradigm_name> R-1 only",
  prompt: "...전체 가설 + 20 lessons checklist + 5-axis novelty 재확인 + R-1 ONLY halt..."
})
```

---

## Step 6 — Background 잔여 검증 (필수)

R-1 종료 보고 받은 직후:
```bash
# 1. Mint process 확인 — 살아있으면 kill
ssh mint@183.99.228.81 "ps -ef | grep -E 'python3.*research' | grep -v grep || echo NONE"

# 2. Local task 파일 확인
ls -la /tmp/claude-1000/-home-hcpark-antigravity/*/tasks/ 2>/dev/null

# 3. Mint INDEX 업데이트 확인
ssh mint@183.99.228.81 "head -30 ~/auto_trading/backend/runs/research_track/INDEX.md"
```

살아있는 background process 발견 시 즉시 kill + 이유 보고.

---

## Step 7 — R-1 결과별 분기 + Q3 §6.2 lesson 통합

| R-1 결과 | 액션 |
|---|---|
| **PASS** (three-gate + Concentration Gate + diversity all PASS) | 사용자에게 "R-2 진행 승인 요청 — 별도 호출로 multi-symbol expand할까요?" 묻기 |
| **FAIL** (three-gate 1+ FAIL) | INDEX graveyard 등록 + lesson 한 줄 보고 (Q3 §6.2에 통합 후보) + Q3 §6.5 row 추가 |
| **BROAD_FALSIFIED** (Symmetric Negative Test 4-variant 모두 FAIL) | family retire 검토 + lesson #19 precedent 인용 |
| **CONCENTRATED_R1_PASS** (3-gate PASS + Concentration FAIL) | lesson #16 적용 + narrow scope 자격 4-cond 검토 (lesson #20) — auto-promote 금지 |
| **PARTIAL_PASS** (focus FAIL + single non-focus cell PASS + Concentration FAIL) | lesson #20 적용 — narrow scope variant 자격 자동 부여 아님, 사용자 결정 |

R-1 결과 후 자동:
1. INDEX.md graveyard 또는 PASS 등록
2. PARADIGM_QUEUE_2026Q3.md §6.2 lesson 후보 통합 (필요시)
3. PARADIGM_QUEUE_2026Q3.md §6.5 schedule row 추가
4. handoff JSON turn 6 summary 추가
5. memory file `project_paradigm_{name}.md` + MEMORY.md 인덱스 추가
6. commit (architect + orchestrator 2-commit pattern)

---

## 중요 규칙 (frontier scout 강제)

- **51 graveyards 전체 분석 의무** — Step 1 Mint SSH로 전체 list 추출 후 Step 2 매트릭스 작성. 명시된 retired families만 회피로는 부족.
- **5-axis novelty strict 적용** — Step 4 후보 보고 시 각 candidate의 axes 명시. 최소 2 axes 통과 필수.
- **새 paradigm class 우선** — Step 3 class A-F 또는 사용자 brainstorm. 전통 z-score 변형 자동 거부.
- **frontier 극소화 메타 인정** — 5% PASS rate. 모든 candidate "기대 시드 가능성" 솔직하게 추정 (10-15% 정도).
- **R-1 분리 모드 의무** — paradigm-architect는 R-1 ONLY halt. R-2 자동 진행 금지 (lesson [[agent-long-background-polling]]).
- **데이터 백필 30분+ ETA STOP** — 이미 확보된 데이터 우선. 새 데이터 도메인은 별도 사용자 승인 필요.
- **Lesson #19/#20 strict 적용** — joint-trigger paradigm 4-quadrant 의무, sign-conditional partial-PASS narrow-scope 자격 검토.

---

## 사용 예시 (간단 invocation)

```
/new-paradigm-frontier
```

→ Step 0~7 자동 진행. 사용자 interaction은 Step 4 (candidate 선택) 1회 + Step 7 (R-2 진행 여부) 1회만.

새 세션에서도 Step 0의 5개 파일 자동 Read로 메타 상태 완전 복원 가능.
