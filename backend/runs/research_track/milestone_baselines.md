# Milestone Baselines — 5 newly-seeded research_track sessions

> 생성일: 2026-05-04 / 다음 마일스톤: **2026-05-11 (Day 7)**, 2026-05-18 (Day 14), 2026-06-03 (Day 30)
>
> 자동 점검: `cd backend && ./venv/bin/python -m scripts.milestone_check --research-only`

---

## Sessions (5)

| Session ID | Symbol | Paradigm | seeded_at | spec |
|---|---|---|---|---|
| `472fafc0-65a` | HBARUSDT | funding_carry | 2026-05-04 | `HBARUSDT_funding_carry_paper_seed` |
| `accc65a5-e27` | AXSUSDT | funding_carry | 2026-05-04 | `AXSUSDT_funding_carry_paper_seed` |
| `f4c8ee87-a76` | COMPUSDT | funding_carry | 2026-05-04 | `COMPUSDT_funding_carry_paper_seed` |
| `694e4f47-369` | LINKUSDT | autocorr_regime | 2026-05-04 | `LINKUSDT_autocorr_regime_paper_seed` |
| `469a7a29-9be` | UNIUSDT | autocorr_regime | 2026-05-04 | `UNIUSDT_autocorr_regime_paper_seed` |

---

## Backtest Baseline Metrics (R-3 robustness 검증값)

### funding_carry (v4 best, perm_p = 0.000)

| Symbol | alpha (1y) | sharpe | mdd | wr | PF | trades (1y) | perm_p |
|---|---|---|---|---|---|---|---|
| HBARUSDT | 107.68 | 1.87 | 9.6 | 68.4 | 3.06 | 19 | 0.000 |
| AXSUSDT | 148.62 | 1.48 | 14.5 | 63.2 | 2.53 | 38 | 0.000 |
| COMPUSDT | 118.43 | 1.67 | 5.5 | 53.6 | 2.75 | 28 | 0.000 |

### autocorr_regime (rev_only, perm_p = 0.000)

| Symbol | alpha (1y) | sharpe | mdd | wr | PF | trades (1y) | perm_p |
|---|---|---|---|---|---|---|---|
| LINKUSDT | 116.18 | 1.25 | 9.4 | 55.6 | 3.33 | 84 | 0.000 |
| UNIUSDT | 120.27 | 1.10 | 8.9 | 53.4 | 2.70 | 88 | 0.000 |

---

## 마일스톤 별 기대 진척도

### Day 7 (2026-05-11)

선형 외삽 기준 (실제는 paradigm sparseness/시장 regime에 따라 변동):

| Session | 기대 trades (Day 7) | 5% lower bound | drawdown 임계 |
|---|---|---|---|
| HBAR funding_carry | ~0.4 (≈19/365×7) | 0 (sparse OK) | -15% |
| AXS funding_carry | ~0.7 | 0 | -15% |
| COMP funding_carry | ~0.5 | 0 | -15% |
| LINK autocorr_regime | ~1.6 (≈84/365×7) | 0~1 | -15% |
| UNI autocorr_regime | ~1.7 (≈88/365×7) | 0~1 | -15% |

**Day 7 액션**:
- funding_carry sessions: trades 0건 정상 (paradigm 본질이 sparse 8h funding extreme z 기다림)
- autocorr_regime sessions: trades 1+ 기대. 0건이면 acorr threshold 점검
- 모든 session drawdown > -15%면 pause + regime 분석

### Day 14 (2026-05-18)

| Session | 기대 trades (Day 14) | 50% lower bound | alpha 부호 검증 |
|---|---|---|---|
| HBAR funding_carry | ~0.7 | 0 | 양수 (R-3 baseline +107.68) |
| AXS funding_carry | ~1.5 | 1 | 양수 (+148.62) |
| COMP funding_carry | ~1.1 | 0 | 양수 (+118.43) |
| LINK autocorr_regime | ~3.2 | 2 | 양수 (+116.18) |
| UNI autocorr_regime | ~3.4 | 2 | 양수 (+120.27) |

**Day 14 액션**:
- paper alpha 부호 ≠ backtest alpha 부호 시 BTC/SPX trend regime 영향 분리 분석
- funding_carry sessions trades 0~1건이면 `entry_threshold 2.5 → 2.0` 검토
- HBAR funding_carry alpha 음수 시 eval_freq=240 vs PoC 8h granularity mismatch 가능성 점검

### Day 30 (2026-06-03)

| Session | 기대 trades (Day 30) | alpha 재현 임계 (±20%) | prod 격상 후보 |
|---|---|---|---|
| HBAR funding_carry | ~1.6 | 86 ~ 129 (annualized) | PF 3.06 재현 시 strong |
| AXS funding_carry | ~3.1 | 119 ~ 178 | sharpe 1.48 재현 시 |
| COMP funding_carry | ~2.3 | 95 ~ 142 | mdd 5.5 재현 시 |
| LINK autocorr_regime | ~6.9 | 93 ~ 139 | PF 3.33 재현 시 strong |
| UNI autocorr_regime | ~7.2 | 96 ~ 144 | PF 2.70 재현 시 |

**Day 30 액션**:
- alpha 재현 ±20% 통과 + perm_p 0.000 robust signal → prod 격상 후보 (실거래 검토)
- alpha 재현 미달 → paper 유지 또는 terminate 결정 (원인 분석 우선)
- 동시에 positioning_dynamics 데이터 누적 ~60d 도달 → paradigm 3-I R-1 시작 가능

---

## 의사결정 트리 (Day 30 검증 후)

```
alpha 재현 ratio (paper / backtest):
  > 0.8: paper 통과 — prod 격상 검토
  0.5 ~ 0.8: 차이 분석 — eval_freq / fee 차이 / regime 가능
  0.0 ~ 0.5: paper 유지 + 추가 관찰 (90d?)
  < 0.0 (alpha 부호 반대): terminate + paradigm 재검토
```

**중요 제약**: paper 시드 시점 시장 regime이 backtest train 시점과 다를 수 있음. 단순 ratio 비교만으론 판단 불가, 시장 trend 분리 분석 필요.

---

## Cross-reference

- `paper_pool_master.md §5-D` — Day 7/14 체크리스트
- `paper_pool_master.md §4-E` — 27-spec trade-sim baseline
- `research_track_master.md §8` — funding_carry / autocorr_regime 시드 근거
- `INDEX.md` — paradigm 진행 상태

---

## Run 명령어

```bash
# Day 7/14/30 자동 점검
cd backend && ./venv/bin/python -m scripts.milestone_check --research-only

# 전체 paper 풀 점검 (다른 22 sessions 포함)
./venv/bin/python -m scripts.milestone_check

# 특정 시점 이후 sessions만
./venv/bin/python -m scripts.milestone_check --since 2026-05-04

# 특정 session 상세
./venv/bin/python -m scripts.paper_session_cli show --id <session_id>
```
