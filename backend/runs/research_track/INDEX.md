# Research Track INDEX — Paradigm 진행 상태

> **본 트랙**: paradigm-agnostic elite gate (`.claude/plans/research_track_master.md`).
> 이 인덱스는 paradigm 후보별 진행 상태와 산출물 위치를 한 화면에서 추적.

**마지막 갱신**: 2026-05-04

---

## 진행 중 paradigm

| Paradigm | 상태 | 현재 Phase | 시작일 | 다음 액션 |
|---|---|---|---|---|
| `funding_carry` | **✅ R-5 paper seeded** (3 sessions) | R-5 사용자 승인 완료 | 2026-05-04 | Day 7 점검 (2026-05-11), Day 30 검증 (2026-06-03) |

**Paper 시드 sessions (2026-05-04, user approved)**:
| Session ID | Symbol | Spec | backtest alpha (train_frac=0.5 OOS 6mo) |
|---|---|---|---|
| 472fafc0-65a | HBARUSDT | HBARUSDT_funding_carry_paper_seed | **+82.6 / sharpe 1.57 / PF 9.45** |
| accc65a5-e27 | AXSUSDT | AXSUSDT_funding_carry_paper_seed | +67.0 / sharpe 0.58 / PF 1.81 |
| f4c8ee87-a76 | COMPUSDT | COMPUSDT_funding_carry_paper_seed | +66.7 / sharpe 0.92 / PF 2.72 |

**Cron 통합**: `binance-paper-cycle` (daily 09:30 KST, 00:30 UTC). funding rate backfill 추가됨 (`scripts/binance/run_binance_paper_cycle.sh`).

**구현 산출물 (paper 시드 통합)**:
- `app/composer_framework/sources/binance_funding_zscore_source.py` (신규)
- `app/composer_framework/composers/passthrough_composer.py` (신규 NegationPassthroughComposer)
- `app/composer_framework/policy.py` (FundingReversalPolicy 추가)
- `app/composer_framework/pipeline_spec.py` (3개 register 추가)
- `scripts/paper_session_cli.py` (bn_funding_zscore runtime data 주입)
- `scripts/backtest_paper_specs.py` (binance_funding_df 자동 로드)
- `scripts/binance/run_binance_paper_cycle.sh` (funding backfill 통합)
- `configs/paper_sessions/{AXS,HBAR,COMP}USDT_funding_carry.json` (3 specs)

---

## R-5 시드 완료 paradigm (paper 풀 운영 중)

| Paradigm | 시드일 | Sessions | 상태 |
|---|---|---|---|
| `funding_carry` | 2026-05-04 | HBARUSDT, AXSUSDT, COMPUSDT (3) | active — Day 30 검증 2026-06-03 |

→ 본 트랙의 첫 R-5 시드 완료. 5 paradigm 폐기 후 6번째 시도에서 진짜 신호 검증 (perm p=0.000 / WF 5-6/6).

---

## 폐기된 paradigm

| Paradigm | 폐기일 | 이유 | 위치 |
|---|---|---|---|
| `ai_native_raw_1m` | 2026-05-04 | R-2 mini 5종 평균 alpha +8.94, sharpe>0 1/5, cutoff 0/5 통과 | `_graveyard/ai_native_raw_1m/` |
| `multi_symbol_portfolio` | 2026-05-04 | best alpha +73 / sharpe +0.81, cutoff 2/5 (mdd/wr) 통과, alpha/sharpe/PF 큰 격차 | `_graveyard/multi_symbol_portfolio/` |
| `cross_asset_meta` | 2026-05-04 | macro features 추가가 baseline 대비 모든 metric 악화 (alpha 73→26, sharpe 0.81→0.01). 18 macro features overfit + 14종 lookback에 이미 implicit 반영 | `_graveyard/cross_asset_meta/` |
| `mean_reversion` | 2026-05-04 | rule-based z-score reversal sweep 4 variants. best (z=2.0 lb=48) aggregate alpha +29 mean, sharpe pos 5/14. 우월하지 않음. per-symbol best (TON +90 / sharpe 0.73) cutoff 2/5만 통과 | `_graveyard/mean_reversion/` |
| `pairs_trading` | 2026-05-04 | 13/91 pair cointegrated. aggregate return -13.44%, return pos 4/13. β drift + cointegration breakdown OOS. best pair (PYTH/JUP +61%) cutoff 1/5만 통과 | `_graveyard/pairs_trading/` |

---

## Phase 진행 표

| Paradigm | R-1 PoC | R-2 multi | R-3 robust | R-4 gate | R-5 paper |
|---|---|---|---|---|---|
| ~~`ai_native_raw_1m`~~ | borderline | mini 5/5 폐기 | - | - | - |
| ~~`multi_symbol_portfolio`~~ | sweep cutoff 2/5 폐기 | - | - | - | - |
| ~~`cross_asset_meta`~~ | baseline 대비 악화 폐기 | - | - | - | - |
| ~~`mean_reversion`~~ | sweep 4 variants 폐기 | - | - | - | - |
| ~~`pairs_trading`~~ | 13/91 cointegrated, agg return -13.44% 폐기 | - | - | - | - |
| `funding_carry` | 14종 alpha pos 13/14 | (R-1=R-2, per-symbol) | **AXS 6/6 perm 0.000 / HBAR/COMP 5/6 perm 0.000** | AXS 6/8 / HBAR-COMP 5/8 (alpha 150 미달) | 사용자 결정 |

---

## R-1 PoC 결과 요약

### `ai_native_raw_1m` (2026-05-04, SOLUSDT)

**설계**: 1m OHLCV → 120-bar lookback flatten (360 features: log_return, hl_range, log_vol × 120) → lgbm regressor → fwd 60-bar log return target → LongShort threshold simulation.

**Hyperparameters**: lookback=120, fwd=60, entry_threshold=0.002, sl=0.06, tp=0.15, max_hold=60, fee=0.0004, train_frac=0.5.

**결과** (`poc__SOLUSDT__metrics.json`):
- Alpha: **+13.64%** (BH -33.6% / strategy -19.95% — 약세장 downside protection)
- Trades: 739 / 397 OOS days
- Sharpe(ann): -0.21, MDD: 43.08%, WR: 47.23%, PF: 0.974
- IC Pearson: 0.018, **RankIC: 0.003 (p=0.022, 유의)**
- Decile top-bottom: 3.35bps (매우 약한 spread)
- Top features: `hl_1/hl_2/hl_3/hl_4` + `v_1/v_3/v_4/v_6` — **단기 volatility + volume expansion 학습**

**해석**:
- 양수 alpha + 유의한 RankIC = paradigm에서 신호 존재 ✅
- 신호 강도 매우 약함 (RankIC 0.003 vs 일반 cutoff 0.02) ❌
- 학습된 신호의 본질이 "vol expansion"으로 현 풀의 `V` source와 도메인 중복 가능 (직교성 약함)
- Elite gate 5개 cutoff 모두 큰 격차 — 통과 가능성 낮음

**R-1 결정 기준** (research_track_master.md): "alpha 양수 + Sharpe > 0 → R-2 진행, 아니면 폐기"
- alpha +13.64 ✅ / sharpe -0.21 ❌ → **borderline, R-2 mini-validation으로 generalize 검증**

### R-2 mini-validation (2026-05-04, 5 symbols)

`r2_mini_summary.csv`:

| Symbol | Alpha% | Sharpe | RankIC | RankIC p | Trades |
|---|---|---|---|---|---|
| SOLUSDT | +13.64 | -0.21 | 0.003 | 0.022 | 739 |
| HBARUSDT | **+60.16** | **+0.46** | -0.002 | 0.116 | 371 |
| AXSUSDT | -29.93 | -1.54 | **0.020** ⭐ | 0.000 | 1828 |
| DOGEUSDT | -14.94 | -2.21 | 0.006 | 0.000 | 395 |
| PYTHUSDT | +15.75 | -0.46 | 0.005 | 0.000 | 1609 |

**검증 종합**:
- alpha 양수: 3/5 (60%), sharpe 양수: 1/5 (20%, HBAR only)
- 평균 alpha: +8.94% (elite gate cutoff 150의 6%)
- RankIC 종목별 비일관 (0.003 ~ 0.020 범위)
- AXSUSDT RankIC 0.020 강력 ↔ alpha -30 — 모델은 학습하나 simulation hyperparameter가 alpha 추출 실패
- HBARUSDT RankIC -0.002 ↔ alpha +60 — 우연한 entry/exit timing

**Paradigm verdict**: **폐기 권장**
- 다종목 일관성 부족 (sharpe>0 1/5)
- Elite gate cutoff(150) 격차 너무 큼 (best alpha HBAR +60 = cutoff의 40%)
- 학습 신호 본질이 vol expansion (V source 도메인 중복)
- 추가 hyperparameter tuning이 paradigm 본질 변경 못함 → cutoff 도달 불가능 추정

**보존 노트**: AXSUSDT RankIC 0.020은 미래 paradigm 후보 (예: AXS 단일종 native vol-event paradigm 또는 simulation logic 재설계).

---

## R-1~R-4 결과 — `funding_carry` (2026-05-04, 진행 중) ⭐

**설계**: per-symbol funding rate z-score reversal. funding rate가 ±2.5σ 이상 이탈 시 반대 방향 진입 (extreme positioning이 가격 reversal 예측). exit at z near 0, SL 5%, max hold 15 funding periods (~5일). rule-based, ML 없음. 14 paper-pool 종목 모두 1년 funding rate backfill 완료.

**R-1 PoC + sweep (14종, full 1y OOS, z=2.5)**:
- Alpha pos **13/14** (93% 일관)
- Sharpe pos 6/14
- MDD mean **12.15%** (cutoff 28의 절반)
- per-symbol best: HBAR/AXS/COMP/ETC가 cutoff 3-4/5 통과

**R-3 robustness (full 1y, train_frac=0.0)**:

| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades | WF | Perm p | 통과 |
|---|---|---|---|---|---|---|---|---|---|
| **AXSUSDT** | **+137.97** | 1.349 | **13.80** ✅ | **63.16** ✅ | **2.24** ✅ | **38** ✅ | **6/6** ✅ | **0.000** ✅ | **6/8** ⭐ |
| HBARUSDT | +97.24 | 1.499 | 8.17 ✅ | 68.42 ✅ | 2.578 ✅ | 19 | 5/6 ✅ | 0.000 ✅ | 5/8 |
| COMPUSDT | +92.16 | 1.186 | 10.34 ✅ | 51.85 ✅ | 2.003 ✅ | 27 | 5/6 ✅ | 0.000 ✅ | 5/8 |
| ETCUSDT | +73.36 | 0.693 | 14.86 ✅ | 57.69 ✅ | 1.530 | 26 | 4/6 | 0.015 ✅ | 3/8 |

**eval_research_gate 결과**: 자동 PASS 0종, 그러나 AXSUSDT 6/8 (alpha 138 vs 150, sharpe 1.35 vs 2.0, oos 355 vs 365 미달).

**핵심 발견**:
1. **Permutation test p=0.000 (3/4 종목)** — random shuffle 200회 중 real alpha 능가 0회. paradigm은 통계적으로 매우 강한 진짜 신호 ✅
2. **Walk-forward 6/6 (AXS)** — regime robust ✅
3. **AXSUSDT가 paper 풀 AXS_V spec을 모든 metric 압도**:
   - Alpha: 82 → **138** (1.7배)
   - Sharpe: 0.64 → **1.35** (2.1배)
   - MDD: 54.3 → **13.8** (1/4)
   - WR: 33.7 → **63.2** (1.9배)
   - PF: 1.18 → **2.24** (1.9배)

**Alpha 150 cutoff 미달 분석**:
- 본 paradigm은 mean-reversion 본질로 작은 alpha 다수 누적 → cutoff 150 도달 어려움
- 그러나 ALL 다른 metric (sharpe, MDD, WR, PF, perm test, WF) 통과 + paper 풀 baseline 압도
- **R-5 사용자 명시적 승인 게이트 candidate** (research_track_master.md §5-B)

**R-1 ~ R-4 산출물**:
- `runs/research_track/funding_carry/14paper_z2.5_lb30_mh15__metrics.json` (R-1 sweep)
- `runs/research_track/funding_carry/r3_robust__{AXSUSDT,HBARUSDT,COMPUSDT,ETCUSDT}.json` (R-3 robustness)
- `runs/research_track/funding_carry/gate_eval__{...}.md` (R-4 gate 평가, v0)
- `runs/research_track/funding_carry/gate_eval_v4__{...}.md` (R-4 gate 평가, v4 best)
- `runs/research_track/funding_carry/paper_seed_proposal__{AXSUSDT,HBARUSDT,COMPUSDT}.json` (R-5 proposal)
- `scripts/poc_funding_carry.py` + `scripts/poc_funding_carry_r3.py`

**v4 best variant sweep 결과 (z=2.5 / exit=0.5 / max_hold=7 / sl=0.03)**:

| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades | WF | Perm p | Gate |
|---|---|---|---|---|---|---|---|---|---|
| **AXSUSDT** | **148.62** | 1.48 | 14.45 | 63.16 | **2.53** | **38** | **6/6** | **0.000** | **6/8** |
| HBARUSDT | 107.68 | **1.865** | 9.57 | 68.42 | **3.06** | 19 | 5/6 | 0.000 | 5/8 |
| COMPUSDT | 118.43 | 1.674 | 5.47 | 53.57 | **2.75** | 28 | 5/6 | 0.000 | 5/8 |

**v0 → v4 개선**:
- AXS: alpha 138 → 148.62, sharpe 1.35 → 1.48 (alpha cutoff 99.1% 도달)
- HBAR: alpha 97 → 107.68, sharpe 1.50 → **1.87** (sharpe cutoff 93.2% 도달)
- COMP: alpha 92 → 118.43, sharpe 1.19 → 1.67

**R-5 paper 시드 proposal 작성 완료** (3종 — `paper_seed_proposal__*.json`). 사용자 명시적 승인 + 구현 코드 통합 결정 대기.

**구현 통합 옵션**:
1. **BinanceFundingZScoreSource** (새 source class) — 기존 composer/policy 인프라 재사용
2. **funding_carry BaseStrategy subclass** — paradigm 본질 그대로
3. **별도 cron + script** — paper_session_cli 우회

---

## R-1 PoC 결과 — `multi_symbol_portfolio` (3-E, 2026-05-04)

**설계**: 14 Binance 종목 daily resample (server-side from 1m DB) → 종목별 features (return_t-{1,3,5,10,20,30}, vol_{5,10,20}d, cross-section ranks) → lgbm regressor (long-format date×symbol panel) → 매 rebalance day cross-section ranking → long top-K / short bottom-K equal-weight market-neutral portfolio.

**핵심 발견 (1차 시도)**:
- Naive (no demean, daily rebalance): alpha **-31.45%** ❌
- 진단: `xs_rank_ic_daily_mean = -0.036` (강한 wrong direction), `pooled rank_ic = +0.026` (Simpson's paradox)
- 모델이 "level effect" (종목 baseline) 학습 — 진짜 cross-section relative 학습 못함
- Turnover 305%/day → fee bleeding 30%/year

**Cross-section demean + weekly rebalance 적용 후 sweep**:

| Spec | TopK | Rebal | Alpha% | Sharpe | MDD% | WR% | PF | Turnover% |
|---|---|---|---|---|---|---|---|---|
| topK=3 weekly | 3 | 5d | +32.10 | +0.21 | 39.34 | 53.0 | 1.04 | 60.75 |
| topK=1 weekly | 1 | 5d | -19.42 | -0.21 | 78.24 | 50.9 | 0.96 | 71.02 |
| **topK=5 weekly** | **5** | **5d** | **+73.35** | **+0.81** | **25.35** | **53.0** | **1.17** | **50.03** |
| topK=3 daily | 3 | 1d | -15.54 | -0.78 | 55.56 | 49.4 | 0.87 | 291.12 |

**Best variant**: `topK=5 weekly demean`. xs_rank_icir_ann = 0.755 (양수, 약함).

**Elite gate 통과 현황** (cutoff: alpha 150 / sharpe 2.0 / mdd 28 / wr 50 / pf 2.0):
- alpha 73 < 150 ❌ (cutoff의 49%)
- sharpe 0.81 < 2.0 ❌
- **mdd 25.35 < 28** ✅
- **wr 53 ≥ 50** ✅
- pf 1.17 < 2.0 ❌
- **2/5 통과** (이전 paradigm 0/5보다 진전)

**R-1 결정 기준** (alpha 양수 + sharpe > 0): **통과 ✅**

**Paradigm verdict**:
- ai_native_raw_1m보다 명확히 진전 (best alpha 73 vs 60, MDD/WR cutoff 통과)
- 그러나 alpha/sharpe/PF cutoff 큰 격차 — paradigm 본질적 신호 강도 한계 (ICIR 0.76)
- 추가 hyperparameter sweep으로 cutoff 도달 가능성 추정 낮음
- HBAR (풀 alpha 1위, +454)와 비교 시 격차 6배

**결정 옵션**:
1. **R-3 robustness 진행** — walk-forward + perm test로 paradigm 신뢰도 검증
2. **추가 1회 sweep** — score-weighted variants, top-K 7
3. **폐기 → 다음 paradigm (3-B Cross-asset 메타)**

---

## 산출물 인덱스

```
backend/runs/research_track/
├── INDEX.md                                      ← 본 문서
├── ai_native_raw_1m/                             ← Paradigm 3-A
│   └── (R-1 PoC 진행 중)
└── _graveyard/                                   ← 폐기 paradigm 이력 보존
```

---

## Cross-reference

- `.claude/plans/research_track_master.md` — 본 트랙 마스터 plan
- `.claude/plans/paper_pool_master.md` — 현 paper 풀 baseline (gate 비교 기준)
- `backend/scripts/eval_research_gate.py` — gate 자동 평가 스크립트
- `backend/runs/paper_spec_backtest.csv` — 현 풀 24-spec trade-sim baseline
