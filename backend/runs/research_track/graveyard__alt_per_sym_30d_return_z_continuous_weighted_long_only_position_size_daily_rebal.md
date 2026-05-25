# paradigm 181 GRAVEYARD — `alt_per_sym_30d_return_z_continuous_weighted_long_only_position_size_daily_rebal`

**Phase**: R-1
**Verdict**: `PORTFOLIO_ALPHA_INSIGNIFICANT`
**Date**: 2026-05-22
**Reason (one-line)**: z_excess +0.20 < 2.0 (sharpe_excess +0.09 / perm_p 0.414), Lesson #71 corollary path C ESCAPE 자체는 성공 (util 71%) but continuous-weighting context에서 per-sym 30d return z-score signal이 portfolio Sharpe 알파 미생성.

## Hypothesis (re-cap)

- Universe: 14 alts standard cohort (BTC + 13 alts)
- Statistic: per-sym 30d return → 90d rolling z-score
- Weight rule: clip(z, +0.5, +3) where z ≥ +0.5 → LONG weighted; else cash. Normalize so sum ≤ 1.
- Rebalance: daily
- Direction: long-only
- Fee: 8bp one-way (16bp round-trip) on turnover

## R-1 Result Summary

### Portfolio-level metrics (n=701 days, 2024-05-30 ~ 2026-04-30)

| Metric | Portfolio (Net) | Eq-Weight Benchmark | BTC B&H |
|---|---|---|---|
| Ann. Return | **-22.53%** | -0.60% | +18.50% |
| Ann. Vol | 60.42% | 71.46% | 46.43% |
| Sharpe | **-0.422** | -0.008 | **+0.366** |
| Sortino | -0.554 | -0.012 | +0.548 |
| Max DD | -81.33% | -68.41% | -49.56% |
| Total Return (cumul.) | -56.88% | -39.58% | +12.73% |

**Alpha vs Eq-Weight**: ann -22.06%, Sharpe -0.488, IR -0.488, TE 51.05%

### Permutation Test (n_perm=1000)

| Field | Value |
|---|---|
| Obs Sharpe | -0.422 |
| Null Mean Sharpe | -0.511 |
| Null Std | 0.435 |
| Sharpe Excess | +0.089 |
| z_excess | **+0.20** (≪ 2.0 strict gate) |
| perm_p | **0.414** (≫ 0.10 strict gate) |

### Lesson #71 corollary path C ESCAPE verification (SUCCESS)

| Field | Value | PASS? |
|---|---|---|
| is_state_machine | False | ✓ |
| is_continuous_weighting | True | ✓ |
| multi_position_simultaneous | True | ✓ |
| signal_intensity_proportional | True | ✓ |
| util_pct_capital_deployed_avg | **71.01%** (≥30% target) | ✓ |
| util_pct_days_active | 73.32% | ✓ |
| avg_active_syms | 4.95 / 14 | ✓ |

**ESCAPE 성공**: Lesson #71 corollary path C (continuous-weighting overlapping ALT pattern) 구조적 ESCAPE는 정확히 작동. capital util 71% (paradigm 99 NSLC FAIL 6.39% 대비 ~11x 상승), 4-dim capital_util pass.

### Life-changing 4-dim audit

| Dimension | Value | PASS? |
|---|---|---|
| trades/yr effective | 1806.4 | ✓ |
| per-trade edge | -1.21bp (vs ≥200bp = 2%) | ✗ |
| capital util | **71.01%** (≥30%) | ✓ |
| sharpe | **-0.422** (≥1.5) | ✗ |

**2/4 dim PASS** (capital util + trades/yr) — 알파가 음수이므로 per-trade edge + sharpe FAIL 본질.

### 9-Quarter breakdown (portfolio_net vs eq_basket)

| Quarter | n | Port Return | Eq Return | Alpha | Port Sharpe | Util | Active Syms |
|---|---|---|---|---|---|---|---|
| 2024Q2 | 32 | -12.0% | -17.0% | **+5.0%** | -3.86 | 0.59 | 1.31 |
| 2024Q3 | 92 | -6.6% | -2.4% | -4.1% | -0.25 | 0.68 | 4.99 |
| 2024Q4 | 92 | **+98.2%** | +56.4% | **+41.9%** | +3.89 | 0.88 | 8.58 |
| 2025Q1 | 90 | -30.5% | -34.6% | **+4.1%** | -2.99 | 0.36 | 1.11 |
| 2025Q2 | 91 | +25.7% | +15.4% | **+10.3%** | +1.69 | 0.77 | 6.79 |
| 2025Q3 | 92 | -3.7% | +31.0% | **-34.7%** | +0.09 | 0.87 | 4.23 |
| 2025Q4 | 92 | -56.4% | -37.1% | -19.2% | -4.52 | 0.70 | 2.16 |
| 2026Q1 | 90 | -30.3% | -26.7% | -3.6% | -2.86 | 0.66 | 6.63 |
| 2026Q2 | 30 | +3.3% | +4.6% | -1.3% | +1.01 | 0.97 | 9.20 |

- Quarters portfolio positive: **4/9** (44%)
- Quarters alpha positive: **4/9** (44%, 단 단일 quarter 2024Q4 +41.9% 압도적 견인)
- Without 2024Q4 outlier: 3/8 quarters alpha positive → 37.5% (≪ 50%)

**Temporal verdict**: highly fragile — 2024Q4 bull-run 단일 quarter가 cumulative alpha의 대부분을 만들고, 2025Q3 (eq +31% / port -3.7%) 역방향 trend-follow trap이 시그널 본질을 입증.

### Per-Sym contribution (14 syms, alpha bp 누적)

**Positive (8 syms, 57%)**: XRP +4224bp, DOGE +2487bp, AVAX +931bp, ETH +783bp, SOL +667bp, ADA +652bp, WIF +211bp, BTC +90bp
**Negative (6 syms, 43%)**: FIL -5979bp, LINK -2605bp, BCH -1630bp, NEAR -1538bp, BNB -1066bp, LTC -450bp

- Concentration cond2 PASS (8/14 = 57% > 50%)
- 그러나 **net 누적은 음수** (positive 9,148bp vs negative -13,267bp)
- FIL/LINK/BCH 3종이 alpha를 전부 갉아먹음 — 30d momentum z trigger에서 LONG 진입 후 mean reversion 당함

### Turnover diagnostics

| Field | Value |
|---|---|
| Avg daily turnover | 30.0% |
| Median daily turnover | 17.6% |
| Max daily turnover | 147.1% |
| Total fee drag | -16.80% (cumulative) |
| Avg daily fee | 2.40bp |

**Fee drag 16.8% on 56.9% total loss = 30%의 손실 기여**. Gross/net 격차 큼.

## 4-cond audit final

| Cond | Result | Detail |
|---|---|---|
| 1 three-gate | **FAIL** | z_excess +0.20 < 2.0, perm_p 0.414 > 0.10 |
| 2 concentration | PASS | 8/14 syms positive (57%) |
| 3 temporal | FAIL (revised 9q) | 4/9 quarters port positive (44%) |
| 4 life-changing 4-dim | FAIL | sharpe + edge 음수 |

**all_4_cond_pass: False**

## Mechanism diagnosis (qualitative)

1. **30d momentum z LONG = trend-follow paradigm**
   - 2024Q4 bull-run (alts 동시 상승) 에 강력 작동 → +98% quarterly return
   - 2025Q3 (eq basket +31%) 에서는 -3.7% (lookback 30d window 시점 차이 → 시그널 not aligned w/ regime shift)
   - 2025Q4/2026Q1 bear regime에서 LONG-only 본질적 손실

2. **Per-sym z-score는 cross-sectional rank rotation과 다른 axis**
   - paradigm 64 (cross-sec weekly MR) 와 family-distinct ✓ — 그러나 결과적으로 alts 트렌드 동조 시기 = 다른 syms도 함께 LONG → diversification illusion (실제 효과는 시장 베타 노출)
   - alpha vs equal-weight = -0.488 sharpe = z-weighting이 dumb basket보다 못함

3. **Continuous-weighting ESCAPE 메커니즘은 성공**
   - util 71%, paradigm 99 NSLC 6.39%의 ~11x
   - 4-dim capital_util + trades/yr dim 모두 PASS
   - 그러나 **신호 자체가 미존재** → util만 높여도 알파 없음

4. **단순 momentum z-score의 cumulative weakness**
   - 30d return z trigger는 "이미 오른 종목 따라잡기" — entry timing이 이미 mean-reversion 진입점
   - FIL/LINK/BCH 등 -1600~-6000bp 손실은 spike-after-trigger reversal 본질

## Lessons learned

### Lesson #72 candidate: "Continuous-weighting ESCAPE 자체는 alpha 보장 안 함"

**Lesson #71 corollary path C** (continuous-weighting overlapping)는 **구조적 4-dim util gate 통과만 보장**하고, **signal alpha 본질을 보장하지 않음**.

paradigm 181이 첫 dogfood로 입증:
- util 71% (paradigm 99 NSLC 6.39% 대비 11x)
- 그러나 signal Sharpe excess +0.09 (perm null과 indistinguishable)
- continuous-weighting context에서도 underlying statistic이 alpha 없으면 portfolio Sharpe < benchmark

**implication**: paradigm 182+ continuous-weighting 변형은 statistic 선정에서 strong prior alpha 입증된 axis로 한정 필요 (e.g., paradigm 22 funding_carry-style mean-reversion, paradigm 69 vol regime conditional 등).

### Lesson #72 amendment candidate: "Long-only momentum z-trend follow family fee-floor + regime-dependence"

3 family inflation evidence:
1. paradigm 64 cross-sec weekly MR graveyard (rank rotation FAIL)
2. paradigm 65 cross-sec 30d momentum graveyard (Carhart FAIL)
3. paradigm 181 per-sym 30d return z continuous weighting (this graveyard)

**Family verdict**: "per-sym OR cross-sec price return z-score LONG continuous-mode-or-discrete" 전체 **2024Q4 single-quarter outlier에 의존**, 그 외 8 quarters 음수 alpha. KR equity Jegadeesh와 동일 mean-reversion regime (Carhart momentum 적용 안 됨).

### Memory compliance check

- [[feedback-no-freemium-trial]]: ✓ joblib OHLCV cache only, zero backfill
- [[feedback-life-changing-strategy-criterion]]: ✓ dual-mode 4-dim 명시적 audit
- [[feedback-persistence-over-efficiency]]: ✓ failure 정상, axis exhaustion framing 미사용
- [[feedback-paradigm-campaign-continuous-parallel]]: ✓ dispatch 지속

## Artifacts

- Code: `backend/scripts/research/paradigm181_continuous_weighted_r1.py` (505 lines)
- Metrics: `backend/runs/research_track/alt_per_sym_30d_return_z_continuous_weighted_long_only_position_size_daily_rebal/r1__metrics.json`
- Time series: `r1__timeseries.csv` (701 days × 8 columns)
- Graveyard report: this file

## Next-action 권고 (paradigm 182)

**Path A (1순위 권장)**: Lesson #72 candidate 확립을 위한 **continuous-weighting + strong-prior-alpha axis** 결합. 예: paradigm 22 funding_carry (8h funding z 평균회귀) signal을 **14 alts continuous-weighting daily rebal long-only**로 재포팅 (state-machine 1-at-a-time → continuous z-proportional). 본질 다름: paradigm 22 R-5 LIVE statistic은 mean-reversion 검증된 alpha 존재 → continuous-weighting ESCAPE × strong-signal axis 첫 결합.

**Path B**: paradigm 181 inverse (per-sym 30d return z **NEGATIVE** continuous-weighting short-only OR mean-reversion long z≤-0.5). 단 [[feedback-life-changing-strategy-criterion]] funding drag 회피 = short-only 비추, long mean-reversion (z<-0.5 LONG)로 reverse trigger 검증. **단 paradigm 99 mirror antipattern catalog 적용** — 별도 R-1 의무.

**Path C**: continuous-weighting class를 다른 statistic class에 적용 — paradigm 69 vol regime conditional × continuous-weighting (HIGH vol p90 syms × z-weighted long). 단 4 sym universe만 자격 (BTC vol-aligned syms) → 14 sym universe 가설 inappropriate.

**권고**: Path A 1순위 (paradigm 22 confirmed alpha × Lesson #71 corollary ESCAPE 결합, 미검증 NEW class).
