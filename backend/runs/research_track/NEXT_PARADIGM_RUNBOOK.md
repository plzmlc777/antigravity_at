# Research Track — Next Paradigm Runbook (2026-05-06 — mtf_alignment_consensus 20번째 graveyard, cross-TF momentum at 5m FALSE)

> **본 문서 목적**: 새 Claude Code 세션이 컨텍스트 잃지 않고 다음 paradigm을 즉시 시도할 수 있도록 self-contained 운영 가이드.
>
> **새 세션 지시 명령** (사용자 → Claude):
> ```
> Read /home/hcpark/antigravity/backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md 후 다음 paradigm 진행해줘
> ```

---

## 0. TL;DR — 한 화면 요약

| 항목 | 값 |
|---|---|
| **현 시점** | 2026-05-06 |
| **시도 완료 paradigms** | 24 (20 graveyard + **4 시드** + 1 데이터 누적 중) |
| **시드된 paradigms** | `funding_carry` (HBAR/AXS/COMP), `autocorr_regime` (LINK/UNI), `funding_dispersion` (ETC), `cross_symbol_lead_lag` (DOGE ⭐) |
| **최근 폐기 (2026-05-06)** | `mtf_alignment_consensus` — 5m crypto에서 cross-TF momentum 가설 catastrophic FAIL (alpha 0/10, mdd 90-100%) |
| **2개 도메인 saturation** | Funding 5 시도(2/5) + Cross-section price/vol 3 시도(1/3) — 두 도메인 모두 saturated. Cross-TF (5m) 도 추가됨 |
| **다음 마일스톤** | 2026-05-11 Day 7 (5종) + 2026-05-12 Day 7 (ETC + DOGE), 2026-06-03/06-04 Day 30 |
| **외부 비용 후보** | 모두 제거됨 (Glassnode/Claude API/NewsAPI 등) |
| **다음 paradigm 추천** | `time_of_day_seasonality` (1순위, funding_dispersion R-5 결정 후) |

---

## 1. 새 세션 시작 시 Context Load 순서

```bash
# 1. 본 runbook (이 문서)
Read /home/hcpark/antigravity/backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md

# 2. paradigm 진행 인덱스
Read /home/hcpark/antigravity/backend/runs/research_track/INDEX.md

# 3. 트랙 마스터 plan
Read /home/hcpark/antigravity/.claude/plans/research_track_master.md

# 4. 시드 sessions 운영 상태
cd backend && ./venv/bin/python -m scripts.paper_session_cli status
./venv/bin/python -m scripts.milestone_check --research-only
```

---

## 2. 다음 paradigm 후보 (ranked, 외부 비용 0)

### 2-A. 즉시 시도 가능 (1y OHLCV + funding rate 사용)

| Rank | 후보 | 차원 | 직교성 | sparsity 위험 | 추천도 |
|---|---|---|---|---|---|
| ~~~~ | ~~`cross_symbol_correlation_regime`~~ | ~~14종 cross-correlation matrix~~ | (2026-05-05 폐기 — perm_p 0.170/0.395/0.225 FAIL) | ~~낮음~~ | 🪦 |
| ✅ | ~~`funding_dispersion`~~ ETC | 14종 funding rate cross-section z-score | (2026-05-05 R-5 시드 완료 — d2640960-52b) | n/a | 시드 완료 |
| ~~~~ | ~~`time_of_day_seasonality`~~ | ~~Asian/EU/US 세션 hour bias~~ | (2026-05-05 폐기 — R-2 sharpe pos 1/10, in-sample optimization 안티패턴 §3-F) | ~~낮음~~ | 🪦 |
| ~~~~ | ~~`partial_autocorr_regime`~~ (lag-2 PACF) | ~~autocorr family 확장~~ | (2026-05-05 폐기 — ETC perm 0.025 PASS but 4/9 gate, lag-1 시드의 weak residual. **family-extension 안티패턴 §3-G**) | ~~낮음~~ | 🪦 |
| ~~~~ | ~~`information_entropy_regime`~~ | ~~Shannon entropy of binned returns~~ | (2026-05-05 폐기 — LDO perm 0.060 borderline FAIL, entropy ≈ log(vol) Gaussian dominance) | ~~낮음~~ | 🪦 |
| ~~~~ | ~~`vol_of_vol_regime`~~ | ~~vol 변동성 (2차 도함수)~~ | (vol_regime_breakout/skewness/entropy 모두 graveyard — moments family 전체 weak-signal cluster, **family-extension 안티패턴 §3-G**으로 시도 권장 안됨) | ~~낮음~~ | ⊘ skipped |
| ~~~~ | ~~`cross_symbol_lead_lag`~~ | ~~BTC leader → alt catch-up~~ | (2026-05-05 폐기 — BTC 1m coverage 5개월만, §3-B variant. ETH leader 1y full sharpe 1/10) | ~~중~~ | 🪦 |
| ⏸ | `funding_oi_divergence` | funding rate × OI 결합 | OI 데이터 30일치만 backfill (1y 부족) — paradigm 보류, OI 1y backfill 또는 positioning 60d 누적(2026-07-03) 후 시도 | 낮음 (dense) | ⏸ 데이터 대기 |
| ⏸ | `cross_symbol_transfer_entropy` | symbol_i → symbol_j information flow at lag k | 강 직교, but compute heavy. BTC dependency 시 §3-B variant 위험 — ETH/alt만 사용 가능 | 중 (compute) | ⭐⭐ |
| ~~~~ | ~~`funding_acceleration`~~ | ~~funding rate Δ (1차 도함수)~~ | (2026-05-05 폐기 — COMP perm 0.095 fail, §3-G 2nd confirmation. funding 도메인 saturation) | ~~낮음~~ | 🪦 |
| ~~~~ | ~~`cross_symbol_dispersion_breakout`~~ | ~~cross-section vol regime~~ | (2026-05-05 폐기 — alpha 0/10 catastrophic fail. Cross-section price/vol family saturated) | ~~중~~ | 🪦 |
| **1** | `BTC backfill 후 lead_lag 재시도` | 1y BTCUSDT 1m backfill 후 §3-B variant 회피하고 재시도 | 강 (이미 결과 패턴 봤음, BTC leader가 진짜 신호 있는지 1y로 검증) | 데이터 backfill 시간 비용 (Binance API 1y klines fetch) | ⭐⭐ |
| **2** | `realized_skew_intraday` | intraday hourly realized return skewness aggregation | 직교 (skewness graveyard는 instantaneous, 본 paradigm은 hourly cycle) but §3-G family-extension 우려 | 낮음 | ⭐ |
| **3** | OI 1y backfill (별도 task) | OI 1d 또는 5m 1y backfill via Binance API → funding_oi_divergence 진행 가능 | 강 (새 데이터 도메인) | 데이터 backfill | ⭐⭐⭐ |

### 2-B. 데이터 누적 대기 (~2026-07-03 시작 가능)

- **`positioning_dynamics` (3-I)**: OI 5m + LSR + taker 60일치 누적 후 R-1 가능. Forward-collection 진행 중 (`fetch_binance_metrics.py` daily cron).

### 2-C. 시간 비용 큼 (자체 수집)

- `3-F RL 정책 학습`: 14종 OHLCV 사용, 매우 어려움
- `3-G L2 Microstructure deep`: websocket 자체 수집 1주+

### 2-D. 제거된 후보 (외부 비용 발생)

- ~~3-C On-chain native~~ (Glassnode/CryptoQuant 월 $30-150)
- ~~3-D Sentiment + LLM~~ (NewsAPI/Claude API 외부 비용)

---

## 3. Anti-patterns — 자동 graveyard 조건

새 paradigm 시도 시 다음 패턴 감지 시 **즉시 graveyard**, 더 시간 투입 금지.

### 3-A. Rare-event paradigm (Hurst trap)

**증상**: extreme threshold로 7-15 trades에서 sharpe 1.5+ 매력적 → threshold 낮추면 sharpe 음수
**검증 방법**: R-1 PoC sweep에서 threshold lowering → sharpe 유지하지 못하면 small-sample 우연
**예시 graveyard**: `hurst_regime` (10 trades sharpe 2.24 → 145 trades sharpe -0.94), `return_volume_xcorr` (7 trades sharpe 1.63 → 2534 trades sharpe -4.13)

### 3-B. Truncation 편향 (max-bars trap + data-coverage asymmetry variant)

**증상**: `--max-bars 50000`로 PoC 빨리 → 매력적, 전체 데이터로 검증하면 정반대
**검증 방법**: **항상 full data로 1차 검증 필수**. truncation은 절대 사용 금지
**예시 graveyard**: `hurst_regime` truncated 50k sharpe 2.24 → full 230k sharpe -0.94

**Variant: data-coverage asymmetry (2026-05-05 NEW)**
**증상**: 여러 symbol/data source의 inner-join이 짧은 source의 coverage로 silently truncate. 명시적 max-bars 안 써도 truncation 발생
**검증 방법**: paradigm 시작 전 모든 사용 symbol/source의 timestamp coverage 확인. min(coverage)이 1y 미달이면 paradigm 보류 또는 backfill 우선
**예시 graveyard**: `cross_symbol_lead_lag` BTC leader 사용 시 BTCUSDT 1m 5개월(200k)만 → ETH/alt 1y와 inner-join → OOS 73 days만. sharpe 1.39 매력적이었으나 ETH leader 1y full data로 sharpe 1/10 만 → §3-B variant 명확

### 3-C. Single-moment 안티패턴 (3차 local optimum 확인)

**증상**: 1차/2차/4차 모멘트 paradigm은 모두 perm test fail
**3차(skewness)가 OHLCV 통계 paradigm의 local optimum** (perm_p 0.060) — 더 이상 시도 무의미
**예시 graveyard**: `mean_reversion`, `vol_regime_breakout`, `kurtosis_regime`

### 3-D. ML on flattened OHLCV (3 graveyard 확인)

**증상**: 단순 lgbm/xgb로 raw 1m OHLCV → 모두 overfit graveyard
**예시 graveyard**: `ai_native_raw_1m`, `multi_symbol_portfolio`, `cross_asset_meta`

### 3-E. Multi-symbol consistency ≠ robustness (4 graveyard 확인)

**증상**: 10-14종 R-2에서 alpha pos N/N + sharpe pos N/N (systematic-looking) but R-3 perm test fails
**검증 방법**: alpha 10/10 양수 + sharpe 10/10 양수도 perm_p ≤ 0.05 필수. multi-symbol 일관성은 robustness가 아니라 OOS 약세장 fade의 downside-protection artifact일 수 있음
**예시 graveyard**: `funding_window_anomaly` (perm 0.095), `vol_regime_breakout` (0.115-0.135), `funding_flip` (0.125+), `cross_symbol_correlation_regime` (0.17-0.40)

### 3-F. In-sample optimization paradigm (1 graveyard 확인, 2026-05-05 NEW)

**증상**: train period에서 bias map / parameter set 추정 후 OOS 적용 → multiple-testing inflation으로 R-1/R-2 즉시 실패
**검증 방법**: 만약 paradigm 설계가 "train에서 best parameter 선정 → test에서 적용" 패턴이면 즉시 회피. 시드된 3 paradigm (funding_carry, autocorr_regime, funding_dispersion) 모두 **데이터 자체에 내재된 신호** (rolling z-score, lagged autocorr, cross-section z) — 추정된 parameter 없음
**예시 graveyard**: `time_of_day_seasonality` (R-1 SOL 16 sweeps 모두 sharpe<0, R-2 sharpe pos 1/10)
**범위**: time-of-day, day-of-week, calendar event, 종목별 best parameter 추정 등 모든 table-lookup paradigm 적용 안됨

### 3-G. Family-extension paradigm (1 graveyard 확인, 2026-05-05 NEW)

**증상**: 시드된 paradigm의 family 내 next-order extension (lag-1 → lag-2/3 PACF; mean → variance → skew → kurt; rolling z → z² → z³) 시도 시 weak residual signal로 cutoff 미달
**검증 방법**: paradigm이 시드된 paradigm의 "변형" 또는 "확장"인지 검토. 같은 statistical family 안의 다음 차수는 첫 항이 잡은 dominant effect 빼고 남는 잔여 → 약함. **새 차원**(cross-section vs time-series; price vs funding vs OI; 분포 모양 vs 분포 spread vs 분포 transform)이 진짜 직교
**예시 graveyard**: `partial_autocorr_regime` (lag-2 PACF after autocorr_regime lag-1 시드: ETC perm 0.025 PASS but Hard Gate 4/9, autocorr LINK 시드 5/8 vs 약 70% magnitude). 모멘트 family에서도 동일: skewness 0.060 → kurtosis R-2 fail (kurt이 skew의 weak extension)
**범위**: lag-3+ PACF, 5차 이상 모멘트, rolling z의 power-transform, 시드된 source의 다른 timeframe 변형 등 동일 family 확장은 권장 안됨

---

## 4. Paradigm 표준 워크플로 (R-1 → R-5)

### Phase R-1: PoC (1 종목)

**스크립트**: `backend/scripts/poc_<paradigm_name>.py` (기존 paradigm script template으로 사용 가능)
- 좋은 template: `scripts/poc_autocorr_regime.py` (rolling correlation 기반)
- 좋은 template: `scripts/poc_funding_carry.py` (funding rate 기반)

**실행**:
```bash
cd backend && ./venv/bin/python -m scripts.poc_<name> --symbols SOLUSDT
```

**PASS criterion**: alpha 양수 + sharpe 양수 → R-2 진행. Borderline 시 hyperparameter sweep 1회.

### Phase R-2: Multi-symbol (10~14 종목)

```bash
./venv/bin/python -m scripts.poc_<name> --symbols HBARUSDT AXSUSDT COMPUSDT DOGEUSDT LDOUSDT SOLUSDT AVAXUSDT LINKUSDT UNIUSDT ETCUSDT --tag r2_best
```

**PASS criterion**: 종목 중 ≥ 1 spec이 cutoff 5/5 후보면 R-3 진행. 그렇지 않으면 graveyard.

### Phase R-3: Robustness (perm test n=200)

**스크립트**: `backend/scripts/poc_<name>_r3.py` (template: `poc_autocorr_regime_r3.py`)

**필수 진단**:
1. Permutation test (n=200): shuffle 후 random alpha distribution 측정 → perm_p
2. Walk-forward 6-fold (선택, multi-period robustness)

**PASS criterion**: **perm_p ≤ 0.05 (필수)**. 0.05 < perm_p < 0.10 borderline은 사용자 결정.

### Phase R-4: Elite Gate Evaluation

**Hard cutoff (5개 모두 AND)**:
- alpha ≥ +150 (1y trade-sim)
- sharpe ≥ 2.0
- max_dd ≤ 28%
- win_rate ≥ 50%
- profit_factor ≥ 2.0

**Robustness (4개 모두 AND)**:
- perm_p ≤ 0.05
- WF folds ≥ 5/6 양수
- vol filter 미의존
- n_trades ≥ 30

**자동 PASS** (5/5 + 4/4) → R-5 진행. **사용자 승인 게이트** (5/8 이상 + perm_p=0.000 robust) → R-5 conditional.

### Phase R-5: Paper Seed (사용자 명시적 승인 필수)

**작업**:
1. Source class 작성 (`app/composer_framework/sources/<name>_source.py`)
2. Composer 신규 또는 재사용 (`composers/passthrough_composer.py` 등)
3. Policy 신규 또는 재사용 (`long_short_threshold` / `funding_reversal`)
4. `pipeline_spec.py`에 register
5. `configs/paper_sessions/<symbol>_<paradigm>.json` 작성
6. `paper_session_cli create`로 session 생성
7. `paper_session_cli run --id <id>`로 dry-run 검증
8. `runs/research_track/INDEX.md` + `master_plan` + memory 갱신
9. `scripts/milestone_check.py` `BASELINE_METRICS` dict에 entry 추가

**자동 통합**: cron `binance-paper-cycle`이 다음 09:30 KST에 자동 picks-up. PM2 재시작 불요.

---

## 5. 기존 시드 운영 점검

```bash
# 5 시드 sessions Day 7/14/30 자동 점검
cd backend && ./venv/bin/python -m scripts.milestone_check --research-only

# 전체 paper 풀 상태
./venv/bin/python -m scripts.paper_session_cli status

# 특정 session 상세
./venv/bin/python -m scripts.paper_session_cli show --id <session_id>
```

**baseline 참조**: `backend/runs/research_track/milestone_baselines.md`

---

## 6. 산출물 위치

| 데이터 | 경로 |
|---|---|
| 본 runbook | `backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md` |
| Paradigm 인덱스 | `backend/runs/research_track/INDEX.md` |
| 트랙 마스터 plan | `.claude/plans/research_track_master.md` |
| Milestone baselines | `backend/runs/research_track/milestone_baselines.md` |
| Milestone check 스크립트 | `backend/scripts/milestone_check.py` |
| Paradigm PoC 스크립트 | `backend/scripts/poc_<paradigm>.py` |
| R-3 robustness 스크립트 | `backend/scripts/poc_<paradigm>_r3.py` |
| Paper seed spec | `backend/configs/paper_sessions/<spec>.json` |
| Source class | `backend/app/composer_framework/sources/<source>.py` |
| Graveyard | `backend/runs/research_track/_graveyard/<paradigm>/` |

---

## 7. 시드된 paradigm baseline (참조용)

### funding_carry (perm_p = 0.000)
- HBARUSDT: alpha 107.68 / sharpe 1.87 / PF 3.06 / mdd 9.6 / wr 68.4
- AXSUSDT: alpha 148.62 / sharpe 1.48 / PF 2.53 / mdd 14.5 / wr 63.2
- COMPUSDT: alpha 118.43 / sharpe 1.67 / PF 2.75 / mdd 5.5 / wr 53.6

### autocorr_regime (perm_p = 0.000, rev_only)
- LINKUSDT: alpha 116.18 / sharpe 1.25 / PF 3.33 / mdd 9.4 / wr 55.6
- UNIUSDT: alpha 120.27 / sharpe 1.10 / PF 2.70 / mdd 8.9 / wr 53.4

---

## 8. 새 paradigm 시작 시 자기 점검 체크리스트

작업 전 다음 5가지 점검 후 진행:

- [ ] Anti-pattern 회피? (rare-event / truncation / single-moment / ML-flatten)
- [ ] 1y OHLCV + funding rate로 즉시 가능? (외부 비용 0)
- [ ] 모든 graveyard와 직교? (단순 변종 아님)
- [ ] dense signal? (n_trades ≥ 30 자연스럽게 달성 가능)
- [ ] 사용자가 승인한 후보 리스트 (§2-A)에 있음?

5가지 모두 ✅이면 R-1 PoC 진행. 하나라도 ❌면 paradigm 재고려.

---

**END** — 본 문서로 새 세션이 다음 paradigm 시도부터 paper 시드까지 즉시 진행 가능.
