# paradigm 182 GRAVEYARD — `alt_per_sym_30d_risk_adjusted_sharpe_z_continuous_weighted_long_only_daily_rebal`

**Phase**: R-1
**Verdict**: `PORTFOLIO_ALPHA_INSIGNIFICANT`
**Date**: 2026-05-22
**Reason (one-line)**: Sharpe-z statistic class shift (vol normalization) on paradigm 181 axis fails to recover alpha — z_excess +0.17 < 2.0, sharpe_excess +0.075, perm_p 0.436 essentially identical to paradigm 181 raw-return-z result. **0/6 negative syms recovered**, hypothesis "vol-noisy syms produce false signal" falsified.

## Hypothesis (re-cap)

- Universe: 14 alts standard cohort (BTC + 13 alts)
- **Statistic class shift from paradigm 181**: per-sym 30d cumulative return / 30d realized vol → Sharpe-like ratio → 90d rolling z-score
- Weight rule: clip(sharpe_z, +0.5, +3) where z >= +0.5 → LONG weighted; else cash. Normalize so sum <= 1.
- Rebalance: daily
- Direction: long-only
- Fee: 8bp one-way (16bp round-trip) on turnover

## Lesson #70 corollary scope prescreen (CRITICAL gate, executed FIRST)

**Decision branch**:
- (a) spec-adaptive expansion of paradigm 181 — HALT_LESSON_70_COROLLARY_SPEC_ADAPTIVE_BAN
- (b) statistic class shift NEW paradigm class — proceed

**VERDICT: (b) PROCEED_NEW_STATISTIC_CLASS**

Rationale:
1. paradigm 181 = **R-1 GRAVEYARD** (NOT R-5 LIVE survivor). Lesson #70 corollary applies to R-5 LIVE narrow-cohort expansion (paradigm 22/24 dogfood scope), NOT to graveyard paradigm follow-ups.
2. Sharpe ratio = **Sharpe 1966 finance literature classical separate statistic class**, NOT parameter tweak.
3. vol normalization **fundamentally changes signal interpretation**: raw return = pure momentum / Sharpe = risk-adjusted momentum (heteroscedasticity-corrected).
4. Lesson #70 corollary explicitly permits "spec-adaptive (per-sym parameter optimization) expansion" — statistic class shift exceeds this scope (different statistic, not different parameter).

## R-1 Result Summary

### Portfolio-level metrics (n=701 days, 2024-05-30 ~ 2026-04-30)

| Metric | Portfolio (Net) | Eq-Weight Benchmark | BTC B&H |
|---|---|---|---|
| Ann. Return | **-22.62%** | -0.60% | +18.50% |
| Ann. Vol | 57.78% | 71.46% | 46.43% |
| Sharpe | **-0.444** | -0.008 | **+0.366** |
| Sortino | -0.578 | -0.012 | +0.548 |
| Max DD | -82.74% | -68.41% | -49.56% |
| Total Return (cumul.) | -55.65% | -39.58% | +12.73% |

**Alpha vs Eq-Weight**: ann -22.15%, Sharpe -0.483, IR -0.483, TE 51.82%
**Alpha vs BTC**: ann -34.71%, Sharpe -0.875, max DD -74.87%

### Permutation Test (n_perm=1000)

| Field | Value |
|---|---|
| Obs Sharpe | -0.4436 |
| Null Mean Sharpe | -0.5188 |
| Null Std | 0.4478 |
| Sharpe Excess | +0.0753 |
| z_excess | **+0.17** (≪ 2.0 strict gate) |
| perm_p | **0.436** (≫ 0.10 strict gate) |

### Lesson #71 corollary path C ESCAPE verification (SUCCESS, 2nd dogfood)

| Field | Value | PASS? |
|---|---|---|
| is_state_machine | False | OK |
| is_continuous_weighting | True | OK |
| multi_position_simultaneous | True | OK |
| signal_intensity_proportional | True | OK |
| util_pct_capital_deployed_avg | **68.42%** (>=30% target) | OK |
| util_pct_days_active | 71.04% | OK |
| avg_active_syms | 4.83 / 14 | OK |

ESCAPE 메커니즘은 paradigm 181 (util 71.01%)과 거의 동일, 구조적으로 정확히 작동.

### Life-changing 4-dim audit (dual-mode)

| Dimension | Value | PASS? |
|---|---|---|
| trades/yr effective | 1763.0 | OK |
| per-trade edge | -1.25bp (vs >=200bp = 2%) | FAIL |
| capital util | **68.42%** (>=30%) | OK |
| sharpe | **-0.444** (>=1.5) | FAIL |

2/4 dim PASS — sharpe + edge 음수 본질.

### 9-Quarter breakdown (portfolio_net vs eq_basket)

| Quarter | n | Port % | Eq % | Alpha % | Port Sharpe | Util % | Active Syms |
|---|---|---|---|---|---|---|---|
| 2024Q2 | 32 | -13.8% | -17.0% | **+2.7%** | -4.50 | 59.6 | 1.50 |
| 2024Q3 | 92 | -8.5% | -2.4% | -11.2% | -0.40 | 68.3 | 5.03 |
| 2024Q4 | 92 | **+118.0%** | +56.4% | **+38.3%** | +4.47 | 85.9 | 8.35 |
| 2025Q1 | 90 | -22.3% | -34.6% | **+3.4%** | -2.04 | 32.1 | 1.28 |
| 2025Q2 | 91 | **+28.5%** | +15.4% | **+8.5%** | +1.84 | 80.7 | 6.74 |
| 2025Q3 | 92 | -11.1% | +31.0% | -34.2% | -0.57 | 75.2 | 4.17 |
| 2025Q4 | 92 | -59.9% | -37.1% | -41.9% | -6.04 | 65.3 | 1.99 |
| 2026Q1 | 90 | -31.3% | -26.7% | -12.9% | -3.01 | 65.1 | 6.30 |
| 2026Q2 | 30 | **+5.4%** | +4.6% | **+1.2%** | +1.37 | 95.0 | 8.17 |

- Quarters portfolio positive: **3/9 (33%)** vs paradigm 181 4/9 (44%) — **WORSE**
- Quarters alpha positive: **5/9 (56%)** vs paradigm 181 4/9 (44%) — **BETTER**
- Without 2024Q4 outlier: 4/8 quarters alpha positive (50%) — 여전히 fragile, 단일 outlier 의존

**Temporal verdict**: alpha-direction quarter ratio는 paradigm 181 대비 약간 개선 (44% → 56%), 그러나 absolute return은 더 악화. Sharpe-z가 outperformance frequency는 높였지만 magnitude는 못 키움 — 본질적으로 same regime dependency.

### Per-Sym contribution — paradigm 181 vs 182 comparison (가설 검증 핵심)

| Sym | p181 bp | p182 bp | Δ bp | p181 pos | p182 pos | Status |
|---|---|---|---|---|---|---|
| BTCUSDT | +90 | +156 | +65 | OK | OK | still_pos |
| ETHUSDT | +783 | +949 | +167 | OK | OK | still_pos |
| BNBUSDT | -1066 | -1271 | -205 | FAIL | FAIL | **still_neg** |
| SOLUSDT | +667 | +798 | +131 | OK | OK | still_pos |
| XRPUSDT | +4224 | +4293 | +69 | OK | OK | still_pos |
| ADAUSDT | +652 | +837 | +185 | OK | OK | still_pos |
| DOGEUSDT | +2487 | +2313 | -175 | OK | OK | still_pos |
| AVAXUSDT | +931 | +673 | -259 | OK | OK | still_pos |
| LINKUSDT | -2605 | -1807 | +798 | FAIL | FAIL | **still_neg** |
| LTCUSDT | -450 | -506 | -56 | FAIL | FAIL | **still_neg** |
| BCHUSDT | -1630 | -573 | +1057 | FAIL | FAIL | **still_neg** |
| NEARUSDT | -1538 | -1551 | -13 | FAIL | FAIL | **still_neg** |
| FILUSDT | -5979 | -7310 | -1330 | FAIL | FAIL | **still_neg** |
| WIFUSDT | +211 | -175 | -387 | OK | FAIL | **LOST** |

**가설 falsification 결정적**:
- **RECOVERED (negative → positive): 0/6 syms**
- **LOST (positive → negative): 1/8 syms (WIF)**
- Positive syms: paradigm 181 **8/14** → paradigm 182 **7/14** (감소)
- Net sum: paradigm 181 **-3,220.8bp** → paradigm 182 **-3,173.7bp** (실질 동일)

가설 "vol-noisy syms (FIL/LINK/BCH/NEAR/BNB/LTC)는 raw return z에서 false signal, Sharpe-z가 vol normalization으로 정제" — **completely falsified**. Sharpe-z는 단순히 같은 6 syms의 손실 크기를 재분배할 뿐, 어느 sym도 sign-flip 일으키지 못함. FIL은 오히려 -5,979bp → -7,310bp 악화.

### 4-cond audit final

| Cond | Result | Detail |
|---|---|---|
| 1 three-gate | **FAIL** | z_excess +0.17 < 2.0, perm_p 0.436 > 0.10 |
| 2 concentration | OK | 7/14 syms positive (50%) — paradigm 181 8/14 (57%)보다 약함 |
| 3 temporal | OK (3/9 port positive but 5/9 alpha positive) | borderline |
| 4 life-changing 4-dim | **FAIL** | sharpe + edge 음수 |

**all_4_cond_pass: False**

### Turnover diagnostics

| Field | Value |
|---|---|
| Avg daily turnover | 31.2% (paradigm 181 30.0%) |
| Median daily turnover | 16.4% |
| Max daily turnover | 161.0% |
| Total fee drag | -17.48% (cumulative, paradigm 181 -16.80%) |
| Avg daily fee | 2.49bp (paradigm 181 2.40bp) |

Turnover는 paradigm 181과 거의 동일 — Sharpe-z가 raw return z 대비 신호 안정성도 못 키움.

## Mechanism diagnosis (qualitative)

1. **Sharpe-z normalization은 absolute signal magnitude만 재조정, signal direction은 동일**
   - cum_return / realized_vol = same-sign-as-cum_return (vol는 항상 양수)
   - 그러므로 sign 변화 없이 magnitude만 squash — z-score 변환 후 ranking이 완전히 동일하지는 않으나 substantively 동일
   - FIL/LINK/BCH의 raw return z LONG entry는 Sharpe-z LONG entry와 거의 같은 timing

2. **paradigm 181 정성적 진단 그대로 적용**
   - 30d momentum z LONG = trend-follow paradigm
   - 2024Q4 bull-run single quarter outlier dependence (Port +118% / Eq +56% / Alpha +38%)
   - 2025Q3 trend-shift trap (Eq +31% / Port -11%) — vol normalization으로도 회복 불가

3. **Lesson #72 candidate 결정적 강화 (2nd dogfood)**
   - paradigm 181 1st dogfood: continuous-weighting ESCAPE structural success + signal alpha 부재
   - paradigm 182 2nd dogfood: vol normalization도 동일 결과 → **continuous-weighting 변형 axis 자체가 alpha-bearing 어려움 입증**

4. **6 negative syms의 본질 = pure mean-reversion 종목, momentum z trigger는 진입 점에서 reversal 당함**
   - vol normalization으로 entry signal sensitivity를 조정해도 underlying mean-reversion regime은 불변
   - 이는 KR equity Jegadeesh reversal regime과 동일 (paradigm 64/65 graveyard 누적 family pattern)

## Lessons learned

### Lesson #72 CONFIRMED 자격 (2 dogfoods)

**Statement (CONFIRMED 자격, 2 dogfoods × 2 statistic classes)**:
> "Lesson #71 corollary path C (continuous-weighting overlapping) ESCAPE mechanism guarantees structural 4-dim util gate pass (~70% util), but does NOT guarantee signal alpha. Continuous-weighting variant axes are intrinsically alpha-resistant in 14-sym alt cohort daily-rebal context. Statistic class shift within continuous-weighting framework (raw return z → Sharpe-z) does NOT recover alpha; underlying mean-reversion regime in 6/14 syms (FIL/LINK/BCH/NEAR/BNB/LTC) dominates regardless of statistic transformation."

**Dogfood log**:
- 1st (paradigm 181, raw return z, 2026-05-22): obs_sharpe -0.422, sharpe_excess +0.089, perm_p 0.414, util 71.01%
- 2nd (paradigm 182, Sharpe-z, 2026-05-22): obs_sharpe -0.4436, sharpe_excess +0.075, perm_p 0.436, util 68.42%
- **Cumulative**: 0/2 alpha PASS, 0/12 negative syms recovered (FIL/LINK/BCH/NEAR/BNB/LTC × 2 statistic classes)

**CONFIRMED 자격 trigger conditions met**:
- 2 distinct statistic classes (raw return vs Sharpe-like ratio)
- Same Lesson #71 corollary path C ESCAPE mechanism
- Same universe (14 alts standard cohort)
- Identical negative-sym set persists across statistic class shift

**Confirmation gate (정식 CONFIRMED 승급)**:
3rd dogfood on third statistic class (e.g., Lesson #62-distinct momentum factor like Carhart 12-2 vs paradigm 65 single 30d) within continuous-weighting framework → 3 dogfoods × 3 statistic classes → formal CONFIRMED universal property of continuous-weighting on 14-alt cohort.

### Lesson #70 corollary scope prescreen 1st dogfood

paradigm-architect skill amendment 권고: Lesson #70 corollary scope prescreen은 R-5 LIVE survivor 대상으로 명시 — R-1 graveyard paradigm 후속 statistic class shift는 NEW class path 허용. paradigm 182가 첫 prescreen application case로 (b) PROCEED 채택 → 결과적으로 알파 부재 confirmed → 통계적으로 (a) HALT 채택과 동일한 결과 but 절차적으로 statistic-class-shift exploration capability 보존.

### Lesson #61 slug grep audit 11th dogfood (PASS, zero match)

`sharpe_z|risk_adjusted_return|vol_normalized_z|return_vol_z|sharpe_ratio|risk_adjusted_momentum` 사전 grep 통과, paradigm 182 = fresh slug.

### Memory compliance check

- [[feedback-no-freemium-trial]]: ✓ joblib OHLCV cache only, zero backfill
- [[feedback-life-changing-strategy-criterion]]: ✓ dual-mode 4-dim 명시적 audit
- [[feedback-persistence-over-efficiency]]: ✓ failure 정상, axis exhaustion framing 미사용
- [[feedback-paradigm-campaign-continuous-parallel]]: ✓ dispatch 지속

## Artifacts

- Code: `backend/scripts/research/paradigm182_sharpe_z_continuous_weighted_r1.py` (433 lines)
- Quarter recompute helper: `backend/scripts/research/paradigm182_quarter_recompute.py`
- Metrics: `backend/runs/research_track/alt_per_sym_30d_risk_adjusted_sharpe_z_continuous_weighted_long_only_daily_rebal/r1__metrics.json`
- Quarter breakdown fixed: `r1__quarter_breakdown_fixed.json`
- Time series: `r1__timeseries.csv` (701 days × 8 columns)
- Graveyard report: this file

## Counter

- Graveyards: **171** (170 + paradigm 181 + paradigm 182, paradigm 181 was unregistered in INDEX; now both registered)
- Non-PASS streak: **42+** (paradigm 182 adds to streak)
- Paradigm counter: **174** (172 + paradigm 181 + paradigm 182, R-1 graveyard track)
- R-5 LIVE: 11 unchanged
- R-5 yield: 6.32% (11/174)
- New artifact: Lesson #72 CONFIRMED 자격 (2 dogfoods, 2 statistic classes)

## paradigm 183 next-action 권고

**1순위 Option α (recommended, lesson META)** — **Lesson #72 formal upgrade to CONFIRMED 정식**. paradigm-architect skill amendment (`lesson_prescreen_checklist.md`)에 Lesson #72 strict prescreen item 추가: "14-sym alt cohort daily-rebal continuous-weighting framework에서 momentum / mean-reversion z-score statistic class shift (raw return, Sharpe-z, IR-z, modified momentum 등)는 presumptively HALT — underlying 6 syms (FIL/LINK/BCH/NEAR/BNB/LTC) pure mean-reversion regime 우세로 alpha 구조적 부재. Continuous-weighting framework에서 strong-prior-alpha axis (paradigm 22 funding_carry, paradigm 24 premium_index, paradigm 69 vol regime conditional 등 R-5 LIVE survivor statistic)만 발의 가능." Lightweight permanent asset.

**2순위 Option β** — continuous-weighting framework × **strong-prior-alpha axis 결합** (paradigm 181 next-action 권고 Path A 재시도, paradigm 182 결과로 Path A 시급성 상승). 예: paradigm 22 R-5 funding z signal × 14 alts continuous-weighting daily rebal. 단 universe issue (paradigm 22 cohort = HBAR/AXS/COMP narrow, 14 alts 적용은 Lesson #70 corollary 위반 가능성) 사전 검토 의무.

**3순위 Option γ** — **6 negative syms 제거 9-sym sub-cohort**로 paradigm 181 OR 182 변형 (FIL/LINK/BCH/NEAR/BNB/LTC 제외). 단 post-hoc cherry-pick 위험, OOS validation 의무 + look-ahead bias prescreen.

**4순위 Option δ** — normal new-paradigm DNA dispatch (paradigm 183 = new DNA, counter increases). [[feedback-persistence-over-efficiency]] default 모드.

**1순위 권고**: **Option α + Option δ simultaneous** — Lesson #72 lightweight formal upgrade (minimal cost) + paradigm 183 new DNA dispatch (default mode, persistence-over-efficiency). Option β/γ는 추후 reconsider.
