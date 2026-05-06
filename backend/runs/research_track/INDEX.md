# Research Track INDEX — Paradigm 진행 상태

> **본 트랙**: paradigm-agnostic elite gate (`.claude/plans/research_track_master.md`).
> 이 인덱스는 paradigm 후보별 진행 상태와 산출물 위치를 한 화면에서 추적.

**마지막 갱신**: 2026-05-06 (mtf_alignment_consensus 20번째 graveyard — 5m crypto에서 cross-TF momentum 가설 catastrophic FAIL)

> 🚀 **새 세션 시작 시**: `Read backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md`

---

## 진행 중 paradigm

| Paradigm | 상태 | 현재 Phase | 시작일 | 다음 액션 |
|---|---|---|---|---|
| `funding_carry` | **✅ R-5 paper seeded** (3 sessions) | R-5 사용자 승인 완료 | 2026-05-04 | Day 7 점검 (2026-05-11), Day 30 검증 (2026-06-03) |
| `autocorr_regime` | **✅ R-5 paper seeded** (2 sessions) | R-5 사용자 승인 완료 | 2026-05-04 | Day 7 (2026-05-11), Day 30 (2026-06-03) |
| `funding_dispersion` ⭐ | **✅ R-5 paper seeded** (1 session) | R-5 사용자 승인 완료 2026-05-05 | 2026-05-05 | Day 7 (2026-05-12), Day 30 (2026-06-04) |
| `cross_symbol_lead_lag` ⭐ | **✅ R-5 paper seeded** (1 session, RESURRECTED) | R-5 사용자 승인 옵션 A 2026-05-05 | 2026-05-05 | Day 7 (2026-05-12), Day 30 (2026-06-04) |
| `positioning_dynamics` (3-I) | 🔄 **데이터 누적 중** (option A) | Pre-R-1 (data accumulation) | 2026-05-04 | ~2026-07-03 (60d 누적 후 R-1 시작) |

**cross_symbol_lead_lag Paper 시드 sessions (2026-05-05, RESURRECTED)**:
| Session ID | Symbol | Spec | backtest baseline (BTC 1y full data) |
|---|---|---|---|
| b5041367-5a6 | DOGEUSDT | DOGEUSDT_cross_symbol_lead_lag_paper_seed | alpha 69.79 / sharpe 1.829 / mdd **2.99 BEST** / wr 58.82 / PF 3.032 / 34 trades / perm_p 0.005 |

**구현 산출물 (cross_symbol_lead_lag 시드)**:
- `app/composer_framework/sources/binance_cross_lead_lag_source.py` (신규 BinanceCrossLeaderLagSource — BTC leader 5m vs target alt)
- `app/composer_framework/orchestrator.py` (RuntimeBundle.leader_ohlcv_eval 필드 추가)
- `app/composer_framework/pipeline_spec.py` (`bn_cross_lead_lag` source register)
- `scripts/paper_session_cli.py` (BTCUSDT 1y leader 자동 로드 + bundle 주입)
- `scripts/backtest_paper_specs.py` (leader runtime 자동 로드)
- `scripts/milestone_check.py` (BASELINE_METRICS + RESEARCH_TRACK_SEEDS cross_symbol_lead_lag)
- `configs/paper_sessions/DOGEUSDT_cross_symbol_lead_lag.json` (PassthroughComposer + LongShortThresholdPolicy 재사용)
- 첫 dry-run: `pred=+0.0000 action=hold side=flat equity=1,000,000` (BTC strong move 없음 — 정상)
- **사전 BTC 800-day backfill**: `scripts.backfill_ohlcv_archive --symbols BTCUSDT --days 800 --parallel 16` (28초, 210k → 1.15M rows)

**funding_dispersion Paper 시드 sessions (2026-05-05, user approved)**:
| Session ID | Symbol | Spec | backtest baseline (PoC ez=0.8/xz=0.1/mh=6) |
|---|---|---|---|
| d2640960-52b | ETCUSDT | ETCUSDT_funding_dispersion_paper_seed | alpha 138.00 / sharpe 3.504 / PF 3.723 / mdd 6.07 / wr 70.27 / perm_p 0.000 |

**구현 산출물 (funding_dispersion 시드, 2026-05-05)**:
- `app/composer_framework/sources/binance_funding_dispersion_source.py` (신규 BinanceFundingDispersionSource — 14종 funding rate cross-section z-score)
- `app/composer_framework/orchestrator.py` (RuntimeBundle.binance_funding_universe_df 필드 + runtime_data 주입 추가)
- `app/composer_framework/pipeline_spec.py` (`bn_funding_dispersion` source register)
- `scripts/paper_session_cli.py` (FUNDING_DISPERSION_UNIVERSE 14종 + load_binance_funding_universe wide loader + bundle 주입)
- `scripts/backtest_paper_specs.py` (binance_funding_universe_df runtime 자동 로드)
- `scripts/milestone_check.py` (BASELINE_METRICS + RESEARCH_TRACK_SEEDS funding_dispersion 추가)
- `configs/paper_sessions/ETCUSDT_funding_dispersion.json` (NegationPassthroughComposer + FundingReversalPolicy 재사용 with bnfd_xs_z input)
- 첫 dry-run 결과: `pred=-0.4386 action=hold side=flat equity=1,000,000` (정상)
- 산출물: `runs/research_track/funding_dispersion/{gate_eval__ETCUSDT.md, paper_seed_proposal__ETCUSDT.json, r3_robust__ETCUSDT.json}`

**autocorr_regime Paper 시드 sessions (2026-05-04, user approved)**:
| Session ID | Symbol | Spec | backtest baseline (rev_only, train_frac=0.5) |
|---|---|---|---|
| 694e4f47-369 | LINKUSDT | LINKUSDT_autocorr_regime_paper_seed | alpha 116.18 / sharpe 1.25 / PF 3.33 / mdd 9.45 / wr 55.64 |
| 469a7a29-9be | UNIUSDT | UNIUSDT_autocorr_regime_paper_seed | alpha 120.27 / sharpe 1.10 / PF 2.70 / mdd 8.90 / wr 53.41 |

**구현 산출물 (autocorr_regime 시드)**:
- `app/composer_framework/sources/binance_autocorr_regime_source.py` (신규 BinanceAutocorrRegimeSource)
- `app/composer_framework/composers/passthrough_composer.py` (PassthroughComposer 추가, no negation)
- `app/composer_framework/pipeline_spec.py` (`bn_autocorr_regime` source + `passthrough` composer register 추가)
- `configs/paper_sessions/{LINK,UNI}USDT_autocorr_regime.json` (2 specs)
- 정책: 기존 `long_short_threshold` (entry=0.5, sl=0.02, tp=1.0, max_hold=24)

**Positioning 데이터 인프라 (2026-05-04 active)**:
- Migration 007: `binance_positioning_metric` 테이블 신규 (PRIMARY (symbol, timestamp, period, metric_type))
- 4 metric types: `top_long_short_account`, `top_long_short_position`, `global_long_short_account`, `taker_buy_sell`
- 추가 OI 5m: `binance_open_interest_hist` (interval_str='5m')
- Initial 30-day backfill (2026-05-04): 14 paper-pool 종목 × 5m granularity → ~520k rows positioning + 121k rows OI
- Daily forward-collection: `scripts/binance/run_binance_paper_cycle.sh` (00:30 UTC = 09:30 KST)
- 60일치 데이터 누적 후 (~2026-07-03) paradigm R-1 가능

**Paper 시드 sessions (2026-05-04, user approved)**:
| Session ID | Symbol | Spec | backtest alpha (train_frac=0.5 OOS 6mo) |
|---|---|---|---|
| 472fafc0-65a | HBARUSDT | HBARUSDT_funding_carry_paper_seed | **+82.6 / sharpe 1.57 / PF 9.45** |
| accc65a5-e27 | AXSUSDT | AXSUSDT_funding_carry_paper_seed | +67.0 / sharpe 0.58 / PF 1.81 |
| f4c8ee87-a76 | COMPUSDT | COMPUSDT_funding_carry_paper_seed | +66.7 / sharpe 0.92 / PF 2.72 |

**Cron 통합**: `binance-paper-cycle` (daily 09:30 KST, 00:30 UTC). funding rate backfill 추가됨 (`scripts/binance/run_binance_paper_cycle.sh`).

**Milestone 점검 도구 (2026-05-04 추가)**:
- `scripts/milestone_check.py` — 5 시드 sessions Day 7/14/30 자동 점검 (선형 외삽 vs baseline + alert)
- `runs/research_track/milestone_baselines.md` — baseline 메트릭 + 마일스톤별 의사결정 트리
- 사용법: `cd backend && ./venv/bin/python -m scripts.milestone_check --research-only`

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
| `autocorr_regime` | 2026-05-04 | LINKUSDT, UNIUSDT (2) | active — Day 30 검증 2026-06-03 |
| `funding_dispersion` ⭐ | 2026-05-05 | ETCUSDT (1) | active — Day 30 검증 2026-06-04 |
| `cross_symbol_lead_lag` ⭐ (RESURRECTED) | 2026-05-05 | DOGEUSDT (1) | active — Day 30 검증 2026-06-04 |

→ 본 트랙의 두 번째 R-5 시드. 11 graveyard 후 13번째 시도. funding_carry와 직교한 신호(시계열 의존성 vs 펀딩 레이트 분포). perm_p=0.000 (n=200).

---

## 폐기된 paradigm

| Paradigm | 폐기일 | 이유 | 위치 |
|---|---|---|---|
| `ai_native_raw_1m` | 2026-05-04 | R-2 mini 5종 평균 alpha +8.94, sharpe>0 1/5, cutoff 0/5 통과 | `_graveyard/ai_native_raw_1m/` |
| `multi_symbol_portfolio` | 2026-05-04 | best alpha +73 / sharpe +0.81, cutoff 2/5 (mdd/wr) 통과, alpha/sharpe/PF 큰 격차 | `_graveyard/multi_symbol_portfolio/` |
| `cross_asset_meta` | 2026-05-04 | macro features 추가가 baseline 대비 모든 metric 악화 (alpha 73→26, sharpe 0.81→0.01). 18 macro features overfit + 14종 lookback에 이미 implicit 반영 | `_graveyard/cross_asset_meta/` |
| `mean_reversion` | 2026-05-04 | rule-based z-score reversal sweep 4 variants. best (z=2.0 lb=48) aggregate alpha +29 mean, sharpe pos 5/14. 우월하지 않음. per-symbol best (TON +90 / sharpe 0.73) cutoff 2/5만 통과 | `_graveyard/mean_reversion/` |
| `pairs_trading` | 2026-05-04 | 13/91 pair cointegrated. aggregate return -13.44%, return pos 4/13. β drift + cointegration breakdown OOS. best pair (PYTH/JUP +61%) cutoff 1/5만 통과 | `_graveyard/pairs_trading/` |
| `funding_window_anomaly` | 2026-05-04 | 5min return seasonality at 8h funding boundaries (00/08/16 UTC). R-2 best (z=2.5/pre=24/hold=12) 14종 alpha 10/10 양수 (+45 mean), COMP 4/5 cutoff (sharpe 2.30 / PF 3.07 / mdd 6.0 / wr 65, alpha 78.8 = 53%). R-3 perm_p: COMP 0.095 (borderline), AVAX/SOL/LINK/UNI 0.24~0.39 (random). WF 2/5만 5/6. funding_carry perm_p=0.000과 결정적 격차 — 신호는 noise + downside avoidance 결합. | `_graveyard/funding_window_anomaly/` |
| `volume_absorption` | 2026-05-04 | High-vol(z>2.5/3.0) + small body(<0.3) candle을 absorption signal로 사용 → prior trend 반대 방향 entry. SOL alpha -20.3/sharpe -2.44 (reversal), -1.5/-1.39 (continuation 반대 가설). 4 paper-pool 종목 vz=3.0: alpha 2/4 양수 (mean +14.5), sharpe 1/4 (COMP 0.08). PF 모두 < 1.01. R-1 결정 기준(alpha+sharpe ≥ 0) 다종목 충족 못함. 빠른 폐기. | `_graveyard/volume_absorption/` |
| `funding_flip` | 2026-05-04 | 펀딩레이트 부호 전환(pos↔neg) 이벤트 기반. continuation 가설 우세 (alpha 5/5 양수 vs reversal 4/5). best (mag=0.0001/hold=6) LINK alpha 91.6/sharpe 1.89/PF 1.65, full series alpha **157.3** (cutoff 통과!) sharpe 1.84. 14종 alpha 10/10 양수 (+33 mean), 그러나 R-3 perm_p **LINK 0.125 / COMP 0.17 / HBAR 0.31** 모두 >0.05 FAIL. random shuffle alpha mean 49 (random도 양수 alpha 자주 생성) — 신호 noise와 구분 불가. funding_carry perm_p=0.000 vs 0.125+ 결정적 격차. | `_graveyard/funding_flip/` |
| `vol_regime_breakout` | 2026-05-04 | 24h vol 30d 분포 하위 10% (compression regime) + 72-bar range breakout → fade(reverse-sign) 가설. R-1 SOL best (rev p=0.1 bl=72 h=72) alpha +49 sharpe +0.67 PASS. R-2 14종: alpha 10/10 양수 (mean +26), best COMP alpha 65.3/sharpe 1.12/PF 1.25 mdd 13.2 wr 53.6 (cutoff 2/5). R-3 perm test (n=200): COMP perm_p **0.135** / SOL **0.115** 모두 FAIL. random_alpha_mean -16/-25 (random은 보통 음수) 라 양수 real alpha는 어떤 구조적 유리는 있으나 통계적으로 robust 아님. | `_graveyard/vol_regime_breakout/` |
| `skewness_regime` | 2026-05-04 | 5min log return의 60-bar(5h) skewness rolling. extreme positive skew(상위 95%) → LONG continuation(euphoria momentum). R-1 SOL alpha +41 sharpe +0.35 PASS. R-2 14종 (cont, pos-skew only, h=72): alpha **10/10 양수** (mean +51), sharpe **8/10 양수** (이전 graveyard 최선), best UNI alpha 89.8/sharpe 1.01/PF 1.26/mdd 18.2. R-3 perm test (n=200): **UNI perm_p 0.060** ⭐ (본 세션 5 paradigm 최저 = 진짜 신호 차원에 가까움) / LDO 0.125 / AVAX 0.180. UNI는 borderline FAIL이지만 alpha 60% / sharpe 50% cutoff 달성으로 paper 시드 자격 미달. **3차 모멘트(asymmetry)는 1-2차 모멘트보다 robust signal 차원이지만 cutoff 미달**. | `_graveyard/skewness_regime/` |
| `kurtosis_regime` | 2026-05-04 | 5min return의 60-bar 4차 모멘트(kurtosis) percentile + recent N-bar return sign으로 direction. "higher moment = better" 가설 검증. R-1 SOL: alpha +38 sharpe +0.33 (rev best) borderline PASS. R-2 14종: alpha **6/10 양수만** (mean +0.6 ≈ 0), sharpe 6/10, MDD mean 71% — skewness보다 명백히 약함. **R-3 불필요**, R-2에서 즉시 폐기. **lesson**: "higher moment = better" 가설 FALSE. kurtosis는 sign-less라 direction 신호 별도 필요, recent return sign으론 부족. **3차 모멘트(skewness)가 OHLCV 통계 paradigm의 local optimum**. | `_graveyard/kurtosis_regime/` |
| `hurst_regime` | 2026-05-04 | Hurst exponent (장기 기억성) 24h 윈도우 R/S method. trend_only t=0.20 (H>0.7) entry. SOL truncated 50k bars: alpha 21 sharpe **2.24** wr 80 PF 2.46 (10 trades) — 매력적이었지만. 4종 full data 100k+ bars: **sharpe 0/4 양수** (mean -1.01), trades 100~150. **small-sample 편향이 원인** — truncation 50k → last 6mo가 우연히 favorable 구간. R-2 즉시 폐기. **lesson**: max_bars truncation은 PoC speedup으로 위험. 항상 full data로 1차 검증 필요. | `_graveyard/hurst_regime/` |
| `return_volume_xcorr` | 2026-05-04 | return × volume(lag=k) cross-correlation 24h 윈도우. extreme xcorr (>±0.20) → informed flow detection → continuation entry. SOL t=0.20 lag=3 h=24: 7 trades alpha 35 sharpe **1.63** PF 5.76 — 매력적. **Hurst trap 재발생**: t=0.15 → 133 trades sharpe -1.68 / t=0.10 → 761 trades sharpe -0.48 / t=0.05 → 2534 trades sharpe -4.13. lower threshold로 갈수록 신호 명백히 noise. **rare-event class 안티패턴 재확인** (Hurst, return_volume_xcorr 동일 패턴). | `_graveyard/return_volume_xcorr/` |
| `cross_symbol_correlation_regime` | 2026-05-05 | 10종 paper-pool 5min 평균 pairwise correlation rolling 288-bar regime + recent direction fade. avg_corr 분포 mean 0.715 / q10 0.555 / q90 0.85 — 시장 항상 동조 움직임. R-2 fade hi_only extreme(hi=0.90) 10종 alpha **10/10 양수** (mean +55), sharpe **10/10 양수** (mean 0.48), best LDO alpha 91/sharpe 0.75/PF 2.05 (cutoff 2/5: PF+WR), MDD 모두 >50%. R-3 perm test (n=200): LDO **0.170** / UNI **0.395** / DOGE **0.225** 모두 >0.05 FAIL. random_alpha_mean 34/19/-19 — 실제 신호 본질은 약세장 fade-direction의 downside protection. funding_window_anomaly와 동일 패턴. | `_graveyard/cross_symbol_correlation_regime/` |
| `time_of_day_seasonality` | 2026-05-05 | 24h hour-of-day bias map (train_frac=0.5 IS mean forward N-bar log return per hour) → OOS entry by bias[h] sign vs threshold. SOL bias_max 6.59 bps. SOL 16 sweeps 모두 sharpe < 0 (best ez=6bps/h=36 sharpe -1.84). R-2 10종 ez=6bps/h=12: alpha pos **2/10**, sharpe pos **1/10** (AVAX 0.19만), alpha mean -18.85%. funding_window_anomaly 패턴(alpha 10/10)조차 안 됨. R-3 perm test SKIPPED (R-1+R-2 결정적). **In-sample optimization 안티패턴 §3-F (NEW)**: train period bias map 추정 후 OOS 적용은 multiple-testing inflation으로 일관성 없음. | `_graveyard/time_of_day_seasonality/` |
| `partial_autocorr_regime` | 2026-05-05 | rolling 288-bar lag-2 PACF = (ρ_2-ρ_1²)/(1-ρ_1²) regime + recent direction fade. SOL 27 sweeps Hurst-trap signal (낮은 threshold sharpe 음수). R-2 10종 rev_only t=0.15 h=72: alpha **9/10**, sharpe **9/10** (mean 0.38), best ETC alpha 94.03/sharpe 0.774/PF 1.55/wr 48.23/mdd 22.85 (cutoff 2/5: mdd+trades). R-3 perm: **ETC perm_p 0.025 PASS**(보) / UNI 0.105 / LINK 0.395. ETC Hard Gate **4/9** (정량 1/5 + robustness 3/4) — autocorr_regime LINK 시드(5/8, alpha 116/sharpe 1.25) 대비 약 70% magnitude. **Family-extension 안티패턴 §3-G (NEW)**: lag-1 ACF 시드 후 lag-2 PACF는 weak residual. autocorr family 추가 확장 무의미. | `_graveyard/partial_autocorr_regime/` |
| `information_entropy_regime` | 2026-05-05 | rolling 288-bar Shannon entropy of binned 5m returns. Low entropy regime continuation + high entropy regime reversal. SOL Hurst-trap (p=0.05/h=72 sharpe 0.16, 145 trades). R-2 10종 low_only p=0.05/h=72: alpha **9/10**, sharpe 5/10 (mean -0.26), best LDO alpha **117.98**/sharpe **1.28**/PF 1.37/mdd 23.91 (cutoff 1/5). R-3 perm: **LDO perm_p 0.0600 borderline FAIL** (skewness UNI 0.060과 동급 weak class) / UNI 0.16 FAIL. LDO Hard Gate **4/9** — partial_autocorr ETC와 동일 weak-signal cluster. **Lesson**: 실용 discrete entropy ≈ log(σ) for Gaussian returns → vol_regime_breakout(graveyard) + skewness(graveyard) family와 부분 겹침. 시드된 paradigms (perm 0.000, PF≥2.5) vs weak cluster (perm 0.025-0.10, PF~1.4) 결정적 격차. | `_graveyard/information_entropy_regime/` |
| ~~`cross_symbol_lead_lag` (RESURRECTED 2026-05-05)~~ | (originally graveyard'd 2026-05-05 due to BTC 1m 5개월 coverage §3-B variant. **BTC 1y backfill 후 R-5 시드 (b5041367-5a6 DOGEUSDT)** — RESURRECTION_NOTE.md 참조) | (active R-5 시드) |
| `funding_acceleration` | 2026-05-05 | per-symbol Δfunding (1차 도함수) z-score reversal. funding rate가 빠르게 +/- 변하는 시점은 over-leveraged crowd → squeeze 가설. R-1+R-2 10종 ez=2.0 alpha **10/10**, sharpe 6/10 (mean 0.003), best COMP alpha 54/sharpe **1.524**/PF **1.916**/mdd 8.63/wr 50/20 trades (cutoff 3/5). R-3 perm: COMP **0.095** / SOL 0.105 / ETC 0.165 모두 FAIL. random_mean 31-46 (real alpha 54-58의 2/3) — funding rate distribution noise가 같은 신호 만듦. **§3-G family-extension 2nd confirmation**: funding_carry HBAR(시드, perm 0.000, sharpe 1.87, PF 3.06) → funding_acceleration COMP(graveyard, perm 0.095, sharpe 1.52, PF 1.92) — 1차 도함수는 명백한 weak residual. **Funding 도메인 saturation 선언**: 5 paradigms 시도 (level/dispersion 시드, timing/flip/acceleration graveyard) — 향후 funding 도메인 확장 권장 안됨, 다른 데이터 도메인 우선. | `_graveyard/funding_acceleration/` |
| `cross_symbol_dispersion_breakout` | 2026-05-05 | 10종 cross-section vol std percentile rank regime. low pct(compression) breakout continuation + high pct(expansion) reversal. R-1+R-2 baseline (p_low=0.20/p_high=0.80): alpha **0/10**, sharpe -2~-3, trades 35k-43k (overactive). Extreme threshold sweep (pl=0.05/ph=0.95): best both alpha 4/10 sharpe 5/10 sharpe_mean -0.028 (borderline noise). 일관 paradigm-level FAIL. R-3 SKIPPED. **Cross-section family saturation 선언**: 3 paradigms 시도 — funding_dispersion(시드) + corr_regime(graveyard) + dispersion_breakout(graveyard). cross-section price/vol은 BTC dominance/systemic 영향으로 individual-symbol prediction 정보 없음. funding rate domain만 robust. | `_graveyard/cross_symbol_dispersion_breakout/` |
| `mtf_alignment_consensus` | 2026-05-06 | sign(R_5m) + sign(R_1h) + sign(R_4h) ∈ {-3..+3} consensus signal. |align|≥3 follow/fade. align distribution dense (|±3|=19%). SOL 16 sweeps 모두 sharpe -2~-14, mdd 90-100%. R-2 10종 best spec: alpha **0/10**, sharpe **0/10**, mdd 90-98%. R-3 SKIPPED. **Decisive lesson**: 5m crypto에서 multi-TF momentum continuation 가설 명백히 FALSE. 19% bars |align|=3 → over-trading + fee bleeding + mdd wipeout. neither continuation NOR fade direction에서도 fail. cross-TF consensus paradigm at 5m granularity 부적합. daily timeframe paradigm으로만 향후 시도 가치 있음. | `_graveyard/mtf_alignment_consensus/` |

---

## Phase 진행 표

| Paradigm | R-1 PoC | R-2 multi | R-3 robust | R-4 gate | R-5 paper |
|---|---|---|---|---|---|
| ~~`ai_native_raw_1m`~~ | borderline | mini 5/5 폐기 | - | - | - |
| ~~`multi_symbol_portfolio`~~ | sweep cutoff 2/5 폐기 | - | - | - | - |
| ~~`cross_asset_meta`~~ | baseline 대비 악화 폐기 | - | - | - | - |
| ~~`mean_reversion`~~ | sweep 4 variants 폐기 | - | - | - | - |
| ~~`pairs_trading`~~ | 13/91 cointegrated, agg return -13.44% 폐기 | - | - | - | - |
| ~~`funding_window_anomaly`~~ | SOL alpha+26 sharpe-0.81 (sweep best +36 / +0.10) | 14종 alpha pos 10/10, COMP 4/5 cutoff (sharpe 2.30/PF 3.07) | **COMP perm_p 0.095 / 4종 0.24~0.39, WF 2/5만 5/6** | - 폐기 | - |
| ~~`volume_absorption`~~ | SOL alpha -20 sharpe -2.44 / 4sym alpha 2/4 sharpe 1/4 폐기 | - | - | - | - |
| ~~`funding_flip`~~ | 5sym continuation alpha 5/5 양수 (mean +46) | 10종 alpha 10/10 양수, LINK best alpha 91.6/sharpe 1.89/PF 1.65 (full alpha 157.3 cutoff 통과!) | **LINK perm_p 0.125 / COMP 0.17 / HBAR 0.31 모두 >0.05 FAIL** | - 폐기 | - |
| ~~`vol_regime_breakout`~~ | SOL alpha+49 sharpe+0.67 (rev p=0.1 bl=72 h=72) | 14종 alpha 10/10 양수, COMP best 2/5 cutoff (alpha 65/sharpe 1.12/PF 1.25) | **COMP perm_p 0.135 / SOL 0.115 모두 >0.05 FAIL** | - 폐기 | - |
| ~~`skewness_regime`~~ | SOL alpha+41 sharpe+0.35 (cont pos-skew only h=72) | 14종 alpha 10/10 양수 sharpe 8/10 양수, UNI best (alpha 89.8/sharpe 1.01/PF 1.26) | **UNI perm_p 0.060** (best of session, but borderline FAIL) / LDO 0.125 / AVAX 0.18 | - 폐기 (alpha cutoff 60%) | - |
| ~~`kurtosis_regime`~~ | SOL alpha+38 sharpe+0.33 borderline | 14종 alpha **6/10**만 양수 (mean ~0), MDD mean 71% — skewness보다 명백히 약함 | (R-3 불필요, R-2에서 폐기) | - 폐기 | - |
| `autocorr_regime` ⭐ | SOL alpha+64 sharpe+1.39 (t=0.2 r=0.2 h=72) | 14종 rev-only filter alpha **10/10 양수** sharpe **9/10**, LINK/UNI 3/5 cutoff (PF 3.33/2.70) | **LINK/UNI/LDO 모두 perm_p 0.000** (n=200, funding_carry급) | LINK 5/8 / UNI 5/8 (alpha 77-80%, sharpe 55-62%) | **✅ 사용자 승인 시드** |
| ~~`hurst_regime`~~ | SOL truncated 50k alpha+21 sharpe+2.24 (10 trades, **small-sample**) | 4종 full data 145+ trades, **sharpe 0/4 양수** (mean -1.01) — truncation 편향이 원인 | (R-2 즉시 폐기) | - 폐기 | - |
| ~~`return_volume_xcorr`~~ | SOL t=0.20 7 trades alpha 35 sharpe **1.63** PF 5.76 — Hurst trap | t=0.15→0.05 sweep으로 trades 133/761/2534 모두 sharpe 음수 (rare-event class anti-pattern) | (R-2 sweep 결정적) | - 폐기 | - |
| ~~`cross_symbol_correlation_regime`~~ | SOL fade hi_only sharpe -0.38 baseline FAIL | 10종 fade hi_only extreme alpha **10/10 양수** (mean +55) sharpe **10/10 양수** (mean 0.48), best LDO alpha 91/sharpe 0.75/PF 2.05 (cutoff 2/5) MDD 모두 >50% | **LDO perm_p 0.170 / UNI 0.395 / DOGE 0.225** 모두 >0.05 FAIL. random_alpha_mean 34/19/-19 (downside-protection artifact) | - 폐기 | - |
| ~~`time_of_day_seasonality`~~ | SOL 16 sweeps 모두 sharpe<0 (best ez=6bps/h=36 sharpe -1.84), bias_max 6.59 bps (작은 effect) | 10종 ez=6bps/h=12 alpha pos 2/10 sharpe pos **1/10** (AVAX 0.19만) alpha mean -18.85% | (R-3 SKIPPED — R-1+R-2 결정적) | - 폐기 | - |
| ~~`partial_autocorr_regime`~~ | SOL 27 sweeps Hurst-trap (best rev_only t=0.15 h=72 alpha 41/sharpe 0.39, 100 trades) | 10종 rev_only t=0.15/h=72 alpha **9/10**, sharpe **9/10** (best ETC alpha 94/sharpe 0.77/PF 1.55, cutoff 2/5) | **ETC perm_p 0.025 PASS** / UNI 0.105 / LINK 0.395 — ETC만 통계적 신호 | ETC 4/9 (정량 1/5 + robustness 3/4) — autocorr_regime LINK(5/8) 대비 약 70% | - 폐기 |
| ~~`information_entropy_regime`~~ | SOL Hurst-trap (p=0.05/h=72 alpha 28.5/sharpe 0.16, 145 trades) | 10종 low_only p=0.05/h=72 alpha 9/10 sharpe 5/10 (best LDO alpha 118/sharpe 1.28/PF 1.37, cutoff 1/5) | **LDO perm_p 0.060 borderline FAIL** / UNI 0.16 FAIL | LDO 4/9 (정량 1/5 + robustness 3/4) — entropy ≈ log(vol) for Gaussian → vol/moments family와 겹침 | - 폐기 |
| `cross_symbol_lead_lag` ⭐ **RESURRECTED** | (BTC 5개월 truncated) lb=1 sharpe mean 1.387 → §3-B variant fail | **(BTC 1y backfilled)** alpha 10/10 (mean +45.66), best DOGE alpha 70/sharpe 1.83/mdd **2.99**/PF 3.03 | **DOGE perm_p 0.005 / ETC 0.000** (random_mean -82/-17, 강력한 directional signal) | DOGE 6/9 (정량 3/5 + robustness 3/4) — autocorr_regime LINK(5/8) 동급 | **✅ DOGE 사용자 승인 시드** (b5041367-5a6) |
| ~~`funding_acceleration`~~ | 10종 ez=2.0 alpha 10/10 (mean +42), sharpe 6/10 best COMP sharpe 1.52 PF 1.92 (cutoff 3/5) | (R-1=R-2 multi-symbol) | **COMP perm_p 0.095 / SOL 0.105 / ETC 0.165 모두 FAIL** | COMP 3/9 — partial_autocorr/info_entropy 보다 약함 | - 폐기 (§3-G 2nd confirmation, funding 도메인 saturation) |
| ~~`cross_symbol_dispersion_breakout`~~ | 10종 baseline alpha 0/10 sharpe -2~-3, extreme sweep best sharpe_mean -0.028 (4/10 sharpe pos) | (R-1=R-2 multi-symbol) | (R-3 SKIPPED — paradigm-level catastrophic fail) | - 폐기 | - (cross-section price/vol family saturation) |
| ~~`mtf_alignment_consensus`~~ | SOL 16 sweeps 모두 sharpe -2~-14 mdd 90-100% (catastrophic) | 10종 align=3 fade h=48 alpha 0/10 sharpe 0/10 mdd 90-98% | (R-3 SKIPPED) | - 폐기 (cross-TF momentum at 5m crypto FALSE) | - |
| `funding_dispersion` ⭐ | SOL ez=1.5 alpha 54/sharpe -0.04 (Hurst trap concern), z=0.5→2.0 sweep으로 SOL은 rare-event trap 확인 | 14종 ez=1.0 alpha 13/14 sharpe 6/14, ETC outlier alpha 87/sharpe 1.98/PF 2.15 (4/5 cutoff). ETC ez=0.8 best alpha **138**/sharpe **3.50**/PF **3.72**/mdd 6.07/wr 70 (37 trades) 4/5 cutoff (alpha 92%) | **ETC perm_p 0.0000** (200/200, random_mean 22 vs real 138, 6× ratio). UNI 0.16 / LDO 0.20 FAIL (per-symbol 1:1 fit) | ETC 7/9 (alpha 미달, WF 미실행) | **✅ 사용자 승인 시드 (d2640960-52b)** |
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

## R-1~R-3 결과 — `funding_window_anomaly` (2026-05-04, 폐기) 🪦

**설계**: Binance 8h funding boundaries (00:00 / 08:00 / 16:00 UTC)에서 5min OHLCV의 pre-window return seasonality. 가설: 펀딩 시각 직전 극단적 방향 이동 시 (z-score > threshold) 펀딩 직후 reversal — 펀딩 페이먼트 헤지 + 포지션 unwind flow exhaustion. 1m → 5m 리샘플 후 boundary t에서 pre-window 누적 return의 z-score 산출.

**Hyperparameters (R-2 best)**: pre_bars=24 (2h), hold_bars=12 (1h), entry_z=2.5, lookback=90 (30일 funding cycles), sl_pct=0.03, fee=0.0004, train_frac=0.5.

**구별점**: funding_carry (8h funding rate level z-score, 1-5일 hold)와 직교 — 본 paradigm은 funding TIMING의 intraday seasonality, 1h hold.

**R-1 PoC + sweep** (SOLUSDT 1y OOS):
- baseline (z=1.5, pre=12, hold=12): alpha +26 / sharpe **-0.81** / pf 0.82
- best sweep (z=1.5, pre=24, hold=12): alpha **+36** / sharpe **+0.10** / pf 1.02
- → R-1 borderline (alpha+sharpe ≥ 0 만족)

**R-2 multi-symbol** (10 paper-pool 종목, z=2.5/pre=24/hold=12):

| Symbol | Alpha | Sharpe | MDD | WR | PF | Trades | Cutoff |
|---|---|---|---|---|---|---|---|
| **COMPUSDT** | **+78.8** | **+2.30** | **6.0** | **65.0** | **3.07** | 40 | **4/5** |
| AVAXUSDT | +66.2 | +1.14 | 6.2 | 55.3 | 1.61 | 38 | 2/5 |
| LINKUSDT | +39.3 | +0.32 | 9.0 | 57.1 | 1.14 | 42 | 2/5 |
| SOLUSDT | +39.5 | +0.49 | 6.7 | 55.9 | 1.25 | 34 | 2/5 |
| UNIUSDT | +42.9 | +0.38 | 10.8 | 48.7 | 1.18 | 39 | 1/5 |
| ETCUSDT | +39.1 | -0.54 | 14.4 | 51.5 | 0.77 | 33 | 1/5 |
| LDOUSDT | +41.8 | -0.56 | 13.7 | 51.1 | 0.80 | 45 | 1/5 |
| HBARUSDT | +41.4 | -0.78 | 9.1 | 47.2 | 0.71 | 36 | 0/5 |
| AXSUSDT | +32.7 | -0.54 | 12.1 | 46.1 | 0.78 | 39 | 0/5 |
| DOGEUSDT | +32.3 | -1.47 | 18.4 | 37.0 | 0.56 | 46 | 0/5 |

- **alpha pos: 10/10 (100%)** ✅ — paradigm은 systemic 양수 alpha 생성
- **sharpe pos: 5/10**
- **best cutoff (COMP): 4/5** — alpha만 미달 (78.8/150 = 53%)

**R-3 robustness** (n_perm=200, top 5 후보):

| Symbol | Alpha | Sharpe | WF | perm_p | random_alpha_mean |
|---|---|---|---|---|---|
| COMPUSDT | 78.8 | 2.30 | **5/6** ✅ | **0.095** ⚠️ | -0.886 |
| AVAXUSDT | 66.2 | 1.14 | 4/6 ❌ | 0.365 ❌ | 33.078 |
| SOLUSDT | 39.5 | 0.50 | 4/6 ❌ | 0.240 ❌ | -10.123 |
| LINKUSDT | 39.3 | 0.32 | 5/6 ✅ | 0.385 ❌ | 3.916 |
| UNIUSDT | 42.9 | 0.38 | 4/6 ❌ | 0.360 ❌ | -11.016 |

**핵심 진단**:
1. **COMP perm_p = 0.095** — 200회 random shuffle 중 19회가 real alpha 능가. p > 0.05 → 통계적 유의 부족 (borderline FAIL)
2. **다른 4종 perm_p = 0.24~0.39** — random shuffle과 명백히 구분 불가 (noise)
3. **WF 5/6 통과는 2종만** — generalization 빈약
4. funding_carry **perm_p = 0.000** (200/200 random 능가 0회)와 결정적 격차

**Paradigm verdict**: **🪦 graveyard**
- alpha 10/10 양수처럼 보였지만 본질은 "downside avoidance + 우연" 결합
- COMP의 sharpe 2.30 / PF 3.07 / mdd 6.0은 매력적이나 perm_p 0.095는 random과 통계적으로 구분 안됨
- alpha 150 cutoff 대비 best 53% 격차 — funding_carry (99%) 대비 너무 큼
- 신호 본질적 약함: 14종 일관성은 있으나 generalize 못함 (perm test 통과 0종)

**보존 노트**: COMPUSDT의 sharpe 2.30 / PF 3.07은 기록할 만하지만, 이는 funding boundary 자체가 아니라 z-score 2.5+ 극단 entry의 selectivity 효과. 본 paradigm 재시도 가치 낮음.

**산출물**: `_graveyard/funding_window_anomaly/` (PoC + sweep 14개 + R-3 5개 perm test JSON 포함)
**스크립트**: `scripts/poc_funding_window.py` + `scripts/poc_funding_window_r3.py`

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
