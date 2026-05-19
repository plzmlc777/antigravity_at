# Research Track INDEX — Paradigm 진행 상태

> **본 트랙**: paradigm-agnostic elite gate (`.claude/plans/research_track_master.md`).
> 이 인덱스는 paradigm 후보별 진행 상태와 산출물 위치를 한 화면에서 추적.

**마지막 갱신**: 2026-05-19 (**paradigm 103 cross_exchange_funding_spread_binance_bybit_alt_directional_8h** BROAD_FALSIFIED_FEE_FLOOR — first dispatch under continuous-parallel policy. Bybit V5 substrate verified 7/7 deep-syms × 2.5yr (joblib cache 영구 자산, future cross-exchange paradigm 재사용 가능). Initial 50bp 가정 vs 실측 p99=3bp 1-2 orders 어긋남 → recalibrated bp=1.0. 4-quadrant SNT: A_focus gross +11.83bp/sigex +1.94 / B_focus +14.33bp/sigex +2.87 — focus direction GROSS-positive (메커니즘 정성적 정확) BUT 16bp fee floor 압축 모두 net < 0. Concentration Gate 전 cell FAIL 0/7 ci_pos. Hold sweep mechanism-revealing 비대칭: A_focus 240→1440m 단조 개선 (−4 → +24bp long-side slow continuation drift) vs B_focus 단조 악화. **NEW lesson #34 candidate**: cross-exchange single-statistic spread on liquid USDT perps is fee-floor bound by venue arbitrage efficiency — Binance↔Bybit liquid perp pair는 8h cycle spread differential을 venue arb가 fee-tolerance까지 평활화. **Funding family Tier 4 retire 강화 입증** — memory snapshot §3 cross-exchange axis exception 1회 invoke + falsify. 향후 family-distinct path 후보 3개 (less liquid venue pair / lead-lag delay study / cross-exchange OI divergence). 103번째 graveyard.)

**이전 갱신**: 2026-05-06 (**wick_reversal_multibar SOL R-5 seed 8th paradigm** — Q3 #4 (4.49σ POSITIVE single-symbol)을 사용자 승인하여 single-symbol exception R-5 시드. Session ID `99107ad5-edd` SOLUSDT 등록 완료. composer source `binance_wick_reversal_multibar_source.py` (BinanceWickReversalMultibarSource, signal {-1,0,+1}) + pipeline_spec `bn_wick_reversal_multibar` register + session JSON `SOLUSDT_wick_reversal_multibar.json` (PassthroughComposer + LongShortThresholdPolicy, eval_freq_minutes=5) + milestone_check 등록. 첫 dry-run `pred=+0.0000 action=hold side=flat equity=1,000,000` (정상 — extreme wick 신호 희소). Day 7 (2026-05-13), Day 30 (2026-06-05) 검증. **§3-C reservation**: 1/4 multi-symbol consistency (SOL 4.49σ만 PASS), 사용자 승인 single-symbol exception. **8 시드 paradigms 누적**: funding_carry/autocorr/dispersion/cross_lead_lag/oi_decoupling/premium_index/premium_velocity + wick_reversal_multibar.)

**이전 갱신**: 2026-05-06 (realized_vol_asymmetry **Q3 #9** graveyard — skewness_regime cousin (return distribution 비대칭). upside_vol vs downside_vol 분리, asymmetry z-score fade/follow modes. R-1 SOL 36 specs (2 modes × 18 configs) **1/36 PASS only**, best fade_vw288_ez2.5_h24 alpha 21.94/sharpe **0.03**/721 trades — essentially zero signal. R-2/R-3 SKIP. **§3-G strong: distribution-moment family fully saturated** (skewness graveyard + kurtosis + info_entropy + vol_asymmetry). Crypto 5m returns 너무 noisy하여 distribution moments에서 directional info 추출 안 됨. 57th paradigm graveyard. Q3 큐 9/9 graveyard.)

**이전 갱신**: 2026-05-06 (btc_eth_3way_lead_lag **Q3 #8** graveyard — cross_symbol_lead_lag (DOGE seeded BTC-only) 의 3-way ETH agreement extension. R-1 SOL 108 specs **11/108 PASS**, best dense lb=12/lt=0.008/fr=0.7/h=12 alpha 44.89/sharpe **0.56**/291 trades (cross_symbol_lead_lag DOGE seeded sharpe **1.83** 대비 결정적 약화). R-2 10종 alpha **10/10** but **sharpe 3/10 BELOW cutoff 4/10**, mean sharpe **-0.68 NEGATIVE** (LINK/SOL/DOGE만 positive). R-3 SKIP §3-E paradigm-level fail. **§3-H §3-N 4th confirmation**: 두 NEW signal (BTC follow + ETH follow, 둘 다 seeded fade 아님) AND-agreement도 narrowing without quality improvement. 2-way BTC-only (cross_symbol_lead_lag seeded) 가 local optimum, 3-way ETH agreement filter는 orthogonal info 안 더하고 trade 줄임. **§3-N 신규 antipattern**: Multi-source N-way AND agreement filter는 항상 약화 (voting majority만 marginal value). 56th paradigm graveyard. **Q3 큐 8/8 graveyard, cross-symbol family 확인**: 2-way local optimum, 다른 angle 필요 (sector rotation, multi-TF, macro proxy 등 높은 비용 paradigm만 남음).)

**이전 갱신**: 2026-05-06 (vwap_deviation **Q3 #7** graveyard — Volume-weighted average price (VWAP) deviation z-score, NEW dim (institutional reference price) 시도. R-1 SOL fade 0/36 PASS catastrophic (trending market에서 fade 잘못된 방향), follow 2/36 PASS best vw=144/ez=3.0/h=24 alpha **+48.04/sharpe 0.62**. R-2 10종 alpha **10/10** sharpe 4/10 cutoff borderline, **mean sharpe -0.306 NEGATIVE**, AXS 0.98~HBAR -1.60 spread huge. R-3 perm n=200 (shuffle volume): **AXS sigma -0.43σ §3-D 결정적** (random_mean 107.81 > real 97.01, volume shuffle이 더 높은 alpha) / SOL 2.26σ weak single-symbol (4번째 SOL borderline pattern). **§3-M 신규 antipattern**: Reference-price paradigms (VWAP, SMA, EWMA) deviation z는 mostly close-price trend 포착이고 reference-specific info 미미, permutation도 비슷한 alpha 생성. Volume timing 추출하려면 timing-dependent 신호 (volume burst at intra-bar event) 필요. 55th paradigm graveyard. **Q3 큐 7/7 graveyard, 1 NEW dim POSITIVE 3σ (#2 wick_reversal) + 1 SOL 4.49σ (#4)**.)

**이전 갱신**: 2026-05-06 (wick_prior_joint **Q3 #6** graveyard — Q3 #4 graveyard note 권장한 continuous JOINT TRANSFORM. composite = (lwf - uwf) × (-prior_ret), composite_z extreme 진입, 방향 = sign(wick_imbalance). 가설: continuous metric noise 줄여 4σ+ multi-symbol elevation. R-1 SOL **0/36 PASS** catastrophic — ALL specs negative sharpe (-1.48~-3.41), MDD 70-85%, trades **700-1100** (Q3 #2 binary 84 trades 대비 8-13x 폭증). **진단**: Q3 #2 binary AND이 essential noise filter였음. Continuous composite z는 wick_imbalance가 거의 0인 약한 신호도 prior_ret heavy-tail에 곱해지면 z extreme 발화 → 방향 신호 noise-dominated. R-2/R-3 SKIP. **§3-L 신규 antipattern**: bounded asymmetric metric × heavy-tailed metric의 continuous composite는 binary gate 없이 noise-dominated, 더 많은 trades but 약한 signal. **결론**: Q3 #2 binary AND 구조가 local optimum. wick paradigm family saturated — 변형 4번 모두 elevation 실패. 54th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (range_expansion **Q3 #5** graveyard — wick rabbit hole 벗어나 truly new dimension 시도. 5m HIGH-LOW intra-bar range z-score를 vol shock event 신호로 활용 (vs vol_regime_breakout graveyard rolling C2C std와 mechanism 다름). R-1 SOL 36 specs: 6/36 PASS only with pm=0.03, best ez=2.5/pm=0.03/h=24 alpha 41.68/**sharpe 0.38**/103 trades — Q3 #2 wick (0.59 vs 0.32 sharpe) 대비 4-5x 약함, MDD 3x 높음 (30 vs 10). R-2 10종 alpha 8/10 sharpe 8/10 mean alpha 34/sharpe 0.32 (Q3 #2 wick 58/0.59) but **MDD catastrophic 50-77% on 4/10 symbols** — paradigm-level 구조적 결함. R-3 perm method degenerate (high/low shuffle + body clipping → all 200 iter identical alpha → random_std=0). R-3 ABORTED, paradigm-level fail이라 결과 무관. **Lesson**: intra-bar MAGNITUDE alone은 directional 정보 없음 (direction은 prior_ret 의존), pure magnitude shock + prior direction logic 너무 약해 MDD가 alpha 압도. Q3 #2 wick은 SHAPE 비대칭이 directional info 추가했기 때문에 worked. **intra-bar SHAPE > MAGNITUDE for directional extraction** 결정적 lesson. 53rd paradigm graveyard.)

**이전 갱신**: 2026-05-06 (wick_reversal_multibar **Q3 #4 ⭐ POSITIVE 4σ+ SOL single-symbol** graveyard — Q3 #2 wick_reversal POSITIVE 3σ의 §2-A0 second-priority extension. 가설: multi-bar rolling avg → random_std 감소 → 4σ+ elevation. R-1 SOL n=2/wt=0.35/h=12 alpha **+61.94/sharpe 1.41/122 trades** (n≥3 monotonic degradation 즉 wick는 instantaneous signal, sequence가 아님). R-2 alpha **10/10** sharpe 7/10 mean +50.66 (Q3 #2 single-bar 58.36 대비 약화). R-3 perm n=200: **SOL 4.49σ PASS ✅ perm_p=0.0** (random_std 12.91 → 10.30 -20%, alpha 59.60 → 61.94 +4%) / AVAX 3.16σ borderline / DOGE 1.94σ FAIL / HBAR 1.30σ FAIL. **1/4 multi-symbol consistency** (seeded paradigms 3-4/4 PASS). **§3-C single-symbol-fit** + §3-G family extension of Q3 #2. **POSITIVE 의의**: multi-bar averaging의 random_std 감소 mechanism은 clean-signal symbols (SOL, HBAR)에서만 작동, AVAX/DOGE는 inherently noisy. R-5 SKIP (multi-symbol consistency 미달). **3rd single-symbol-fit pattern** (#8 SOL 3.1σ, #9 ETC 3.98σ, this SOL 4.49σ). 다음 wick 시도는 aggTrades domain switch 또는 joint metric transform 필요. 52nd paradigm graveyard.)

**이전 갱신**: 2026-05-06 (wick_reversal_volume **Q3 #3** graveyard — Q3 #2 wick_reversal POSITIVE 3σ의 §2-A0 first-priority extension. 가설: volume z-score filter로 random_std 억제 → 4σ+ elevation. R-1 SOL volume_thresh sweep: vt=0 alpha 59.82/sharpe 1.62 (baseline 동일), vt=0.5 50.7/1.20, vt=1.0 38.5/0.46, vt=1.5 37.5/0.39, vt=2.0 31.3/**-0.07**. **Monotonic degradation** — volume_thresh ↑ → sharpe ↓. R-2/R-3 SKIP. **§3-H filter mechanism antipattern 3rd confirmation** (premium_oi_corr / premium_oi_joint / oi_funding_corr 와 동일 패턴, NEW dim에서도 발현). **Universal lesson 강화**: AND filter on seeded paradigm component → 95%+ degradation, voting만 marginal value 가능. 51st paradigm graveyard.)

**이전 갱신**: 2026-05-06 (wick_reversal **Q3 #2 ⭐ POSITIVE 3σ borderline** graveyard — **50th paradigm**, NEW DIMENSION 첫 시도 (intra-bar OHLC wick shape, 49 paradigm 중 close-to-close 외 처음). 5m candle lower_wick_frac > wick_thresh AND prior 1h drop > pm_thresh → LONG (long-side liq cleared, reversal up); upper_wick + prior rally → SHORT. R-1 SOL 81 specs sweep **12 PASS**, best wt=0.5/pl=12/pm=0.03/h=12 alpha **+59.60/sharpe 1.51/PF 1.64/84 trades**. §3-A clean: relax wick 0.7→0.5 sharpe 0.53→1.51 (relax IMPROVES). R-2 10종 alpha **10/10** sharpe **8/10** mean **+58.36** trades **1515** (HBAR 71.5/0.79, AVAX 69.2/0.87, ETC 69.6/0.66, DOGE 63.8/0.82, SOL 59.6/1.51 best). R-3 perm n=200 (shuffle high/low pair, preserve open/close): **SOL 3.34σ perm_p=0.0** / **AVAX 2.99σ perm_p=0.0** / DOGE 1.51σ p=0.055 / HBAR 1.23σ p=0.12. **0/200 random beat real for SOL/AVAX** — 신호 실제이나 random_std (12.9~30.6) 커서 4σ cutoff 미달. random_mean이 real의 14-49% (§3-D threshold 55-85% 대비 깨끗). **POSITIVE 의의**: NEW dimension 입증 — intra-bar wick shape는 close-to-close 외 directional 정보 carry. R-5 SKIP (4σ 미달). 향후 wick × volume / multi-bar wick aggregation / aggTrades backfill 후 재시도 가치 있음. 50th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (oi_funding_corr_regime **PARADIGM_QUEUE_2026Q3 #1** graveyard — Round 2 큐 첫 시도. 8h frame d_OI z + funding-rate z 결합 + rolling 30-period correlation regime filter (시드된 두 강력 도메인 OI flow + funding carry 결합 가설). 5m 첫 시도는 forward-fill funding step function으로 corr 0%, 8h 정렬 frame으로 재설계. R-1 SOL fade ez=1.5 efz=0.5 ct=0.0 h=6 alpha **+69.7/sharpe 4.04/12 trades**, ez=1.0 ez=0.5 h=6 alpha 75.95/sharpe 2.51/21 trades, robust across params (§3-A pass). R-2 10종 alpha **10/10** sharpe **7/10** mean +50.23 (DOGE 94/3.58, SOL 76/2.51, UNI 70/0.90, HBAR 50/0.20). R-3 perm n=200 **all 4 FAIL §3-D directional bias**: DOGE 0.73σ (real 94 vs random_mean ~80) / SOL 0.65σ (random ~58) / UNI -0.01σ / HBAR -0.23σ. **random_mean이 real의 55-85%** — funding-fade alone (시드된 funding_carry) 신호가 alpha 대부분 설명, OI alignment filter는 trade 수만 줄이고 quality 개선 없음. **§3-G filter mechanism + §3-D directional bias 동시 발현**. **Lesson 보강**: 시드된 두 fade signal의 joint/corr filter 조합은 §3-D high risk, fail-fast 결정 트리에 추가 권장. 49th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (funding_oi_premium_3sigma_event **#16 PARADIGM_QUEUE_2026Q2** graveyard — funding/premium/OI z 3개 동시 ±sigma 같은 sign rare-event composite. **0 trades at sigma 3.0/2.0/1.5**, sigma 1.0 lenient에서도 9 trades total across 10 syms (1/symbol/year). §3-A rare-event 결정적 — funding 366d 데이터로 본질적 검증 불가능. R-2/R-3 SKIP. funding 2y+ 누적 후 재시도 가치. 48th paradigm graveyard. **🎯 PARADIGM_QUEUE_2026Q2 COMPLETED 16/16: 1 R-5 시드 (#10 premium_velocity AVAX+HBAR) + 15 graveyard (4 borderline + 2 POSITIVE)**.)

**이전 갱신**: 2026-05-06 (multi_zwin_ensemble_premium **#15 PARADIGM_QUEUE_2026Q2** graveyard — premium 15d/30d/60d z 동시 같은 sign + |sum|>5 → follow direction. R-1 SOL zsum=5 alpha 132/sharpe 2.07/17 trades (premium_index_zscore SOL 17 trades 거의 동일). R-2 alpha 9/10 sharpe **5/10** mean 0.098 약함. R-3 perm n=200: **SOL 4.03σ PASS** (간신히, premium_index_zscore SOL 5.4σ 대비 약화 — ensemble 정보 손실), LDO 3.47σ borderline, AVAX 2.72σ FAIL. **§3-G timeframe ensemble = component보다 약함** (premium_index_zscore zwin=30 single이 multi-timeframe sum보다 강함). 47th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (weekday_DoW_combined **#14 PARADIGM_QUEUE_2026Q2** graveyard ⭐ POSITIVE — premium z>1.5 + DoW ∈ {Thu, Fri, Sat} 3일 cluster + follow direction. R-2 10종 alpha **10/10** sharpe **9/10** mean **+143.10 (큐 alpha mean 최고)**, **DOGE alpha 319/sharpe 3.0/PF 37.19/wr 86.7**, **SOL alpha 214/sharpe 3.72/PF 14.47**, **LDO alpha 220/sharpe 3.15/PF 9.12** — multiple 5/5 strict cutoffs! R-3 perm n=200: **DOGE 9.09σ / SOL 8.75σ / LDO 4.35σ / AVAX 4.33σ ALL PASS 4σ+** (4/5), UNI 2.02σ borderline. **그러나 §3-G strong**: DOGE/SOL/LDO 모두 premium_index_zscore 시드 (9.0/5.4/5.7σ), AVAX는 #10 premium_velocity 6.86σ 시드 — **모든 PASS 종목 이미 다른 paradigm으로 시드됨**. trade count 비교 (DOGE: premium_index 17 trades vs DoW 15 trades) → Thu/Fri/Sat이 premium z extreme의 **95% 포착**, 사실상 동일 신호의 calendar 재라벨링. R-5 SKIPPED. **POSITIVE 의의**: weekend_drift_premium 본가설 검증 — pre-weekend cluster가 premium 신호의 대부분 담는다는 것 확인 (3/7 days = 95% alpha). 46th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (premium_oi_joint_filter **#13 PARADIGM_QUEUE_2026Q2** graveyard — premium z fires + OI z direction agrees → confirmation entry. R-1 SOL: pez=2.0 oiz=0 (filter 없음) = baseline alpha 82/sharpe 1.35 정상. **모든 oi filter 적용 (oiz>0) sharpe ≤ 0** — filter는 trade 줄이고 새 alpha 못 더함. R-2 SKIP. **§3-G filter mechanism**: #3 premium_oi_correlation_regime와 동일 패턴, joint_3signal_ensemble과 동일 family. 45th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (bid_ask_concentration_regime **#12 PARADIGM_QUEUE_2026Q2** graveyard — book_depth top1_concentration_mean 30d z, prior-return direction. R-1 SOL fade ez=2.0 alpha 47/sharpe 0.71 (10 trades only). R-2 6 종 alpha **6/6** sharpe **5/6** mean +50.89, BTC sharpe 3.18/PF 8.15 매우 인상적이나 6 trades only. R-3 perm n=200 all 4σ 미달: ETH 1.94σ borderline / BTC 1.41σ / DOGE 0.48σ / SOL 0.60σ. **§3-A rare-event 결정적** (6-10 trades per symbol, 365d data), book_depth_imbalance graveyard family. 44th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (garman_klass_vol_premium **#11 PARADIGM_QUEUE_2026Q2** graveyard — Garman-Klass vol estimator on premium OHLC z-score, prior-return direction. R-1 SOL follow ez=1.0 rl=5 alpha 190/sharpe 2.65/PF 3.52/wr 63 (5/5 cutoff!). R-2 alpha **10/10** sharpe **8/10** mean +71.41, **그러나 SOL 외 distinct from #10**: AVAX 46/0.15 (vs #10 366/2.42), HBAR 47/0.24 (vs #10 279/2.14). SOL/UNI/LDO만 의미. R-3 perm n=200: **SOL 5.4σ PASS** 단독, UNI 3.51σ borderline, LDO 1.31σ FAIL. **SOL single-symbol fit + §3-G premium domain saturation 5번째 확인**: premium_index_zscore SOL 5.4σ (시드)와 같은 종목 같은 도메인 — GK는 SOL premium 신호의 변환만, 새 정보 없음. premium의 vol-of-basis 3번째 paradigm 모두 graveyard (#1 range, #7 range/median, #11 GK-vol). 43rd paradigm graveyard.)

**이전 갱신**: 2026-05-06 (premium_velocity_zscore **#10 PARADIGM_QUEUE_2026Q2** ⭐ **R-5 CANDIDATE → SEEDED 옵션 A (AVAX e4bff252-84a + HBAR 8d70b971-0ec)** 큐 첫 break-through. premium 1d 1차 derivative z-score (Δ premium 30d z). R-1 SOL follow ez=1.0 alpha **184/sharpe 1.87/46 trades 25L 21S balanced**. R-2 10종 alpha **8/10** sharpe **6/10** mean +**121.60** (큐 최고!). R-3 perm n=200 10 syms: **AVAX 6.86σ ✅** (큐 최강) / **HBAR 5.25σ ✅** / **SOL 4.88σ ✅** / UNI 3.54σ borderline / ETC 1.88σ / LDO 0.28σ / LINK 0.27σ / DOGE -0.44σ / AXS -1.12σ / COMP -1.31σ. **3/10 PASS at 4σ+** = 시드된 paradigms (premium_index_zscore 4/4 / oi_price_decoupling 4/4) 다음 가는 robustness. **Diversity 검토**: AVAX (이전 oi_price_decoupling 시드, 다른 도메인 premium velocity는 새 차원) ✓ / HBAR (이전 funding_carry 시드, 다른 도메인) ✓ / SOL (이전 premium_index_zscore 시드, 같은 도메인 level→velocity §3-G family-extension) ✗. **사용자 승인 게이트 도착 — AVAX/HBAR 시드 권장, SOL 제외 또는 단독 검토**. 42nd paradigm — 큐 첫 break-through.)

**이전 갱신**: 2026-05-06 (oi_change_acceleration_squeeze **#9 PARADIGM_QUEUE_2026Q2** graveyard — daily OI 2nd derivative (acceleration) z-score, follow_accel direction. R-1 SOL alpha 94/sharpe 1.07 (42 trades 21L 21S balanced). R-2 alpha **9/10** sharpe **7/10** mean +79.14, ETC alpha **161/sharpe 1.53/PF 1.80/mdd 28/wr 59/44 trades** (5/5 strict cutoff!). R-3 perm n=200 7 symbols: **ETC 3.98σ (perm_p 0.0!)** ← 큐 best signal but **4σ에 1bp 미달**. LINK 2.01σ borderline. **SOL/LDO/AVAX/UNI/DOGE 모두 -0.7~+1.7σ = 5/7 random**. **ETC single-symbol fit** — paradigm 일반화 안 됨. oi_price_decoupling (시드, 4/4 perm 3.7-6.7σ) 대비 결정적 약함. **§3-G family extension**: 2nd derivative은 1st derivative보다 약함. 41st paradigm graveyard.)

**이전 갱신**: 2026-05-06 (funding_premium_spread_zscore **#8 PARADIGM_QUEUE_2026Q2** graveyard — spread_z = funding_daily_z - premium_daily_z. R-1 SOL fade ez=1.0 alpha 46/sharpe 0.59 (다른 sweep 모두 sharpe ≤ 0). R-2 alpha **7/10** sharpe **4/10** mean -1.092 약함. R-3 perm n=200 **SOL 3.10σ borderline** (perm_p 0.005, 큐 best과 동급) but **ETC 0.08σ = random** — SOL outlier, single-symbol fit. **§3-D + §3-G**. funding 데이터 366일 한계도 영향. 40th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (premium_intraday_range_zscore **#7 PARADIGM_QUEUE_2026Q2** graveyard — premium daily range / 30d median(range) ratio z-score, direction from prior 5d return. fade 가설 invalid. follow R-1 SOL ez=1.5 rl=5 alpha 122/sharpe 1.71/22 trades 10L 12S balanced. R-2 10종 alpha **10/10** sharpe **8/10** mean +55.26 SOL 4/5 cutoff. R-3 perm n=200 SOL **2.88σ borderline FAIL**/LDO 1.73σ/DOGE 1.03σ/UNI 0.96σ. **#1 SOL(2.17σ)보다 약간 강함** (median normalization + prior-return direction logic 차이). **§3-G premium domain + volume_absorption family**. 39th paradigm graveyard.)

**이전 갱신**: 2026-05-06 (cross_section_funding_rotation **#6 PARADIGM_QUEUE_2026Q2** graveyard — rule-based 14종 funding rate rank portfolio rotation. modes: `carry` (long top-K most negative funding, short top-K most positive) / `reverse` (opposite). R-1 sweep 18 configs: **reverse mode가 carry보다 우월** (가설 INVERTED). best k=1 h=14 reverse alpha **168.85**/sharpe 1.73/total 120/mdd 5.4/wr 75/PF 7.87 (12 rebalances). bh=-48.78% bear OOS. R-3 perm n=200 (shuffle funding within row): k=1 h=14 reverse perm_p 0.015 **3.01σ borderline** (real 168.85 vs random_mean 48.88, ratio 3.4×) / k=3 h=14 1.53σ / k=1 h=7 1.28σ. **§3-A rare-event** (12 rebalances) + **§3-G multi_symbol_portfolio family** (rule-based version of ML portfolio graveyard). 3σ borderline 본 큐 5 candidates 중 첫 비교적 강한 signal이지만 4σ 미달 + small sample. funding 데이터 2y+ 누적 후 재시도 가치 있음. R-5 SKIPPED. **38th paradigm graveyard**.)

**이전 갱신**: 2026-05-06 (monthly_premium_seasonality **#5 PARADIGM_QUEUE_2026Q2** graveyard — premium z 마지막 N일 of 매월 calendar mask follow_eom (fade_eom 가설 invalid sharpe ≤ 0). R-1 SOL nd=7 ez=0.5 alpha 88/sharpe 1.37/26 trades. R-2 10종 alpha **9/10** sharpe **4/10** mean +36.77, SOL/UNI/DOGE 의미 있음. R-3 perm n=200 SOL **1.89σ borderline FAIL**/DOGE 0.74σ/UNI 0.71σ. random_mean 40 vs real 66-88 (50% noise floor) — **weekend_drift_premium(1.9-3.9σ)보다 약함**. **§3-F calendar bias** (time_of_day_seasonality graveyard 패밀리) + **§3-G premium domain saturation**. 37th paradigm graveyard. **Lesson**: monthly seasonality은 weekly (Friday) seasonality보다 더 sparse하며 effect 약함. premium 도메인의 calendar restriction은 모두 weak residual.)

**이전 갱신**: 2026-05-06 (funding_oi_phase_lag **#4 PARADIGM_QUEUE_2026Q2** graveyard — daily funding mean + daily OI change z-score, rolling 30d lead-lag phase indicator. phase = corr(funding_z[t], oi_z[t-1]) - corr(funding_z[t-1], oi_z[t]). R-1 SOL: phase 73% positive (OI consistently leads funding). best `oi_leads_follow_oi` ez=1.0 pt=0.05 alpha 104.84 sharpe **3.134** PF **6.08** 10 trades. R-2 10종 매우 강함: alpha **9/10** sharpe **8/10** mean +49.59, **SOL 5/5 strict cutoff**, UNI/LINK 4/5. R-3 perm n=200 catastrophic: SOL **1.60σ borderline FAIL** / UNI 0.76σ / LINK 0.79σ / AVAX 0.54σ. **random_mean이 real의 80%** (SOL 80/105, LINK 62/86) → phase filter는 trade 30% 줄이지만 quality 개선 marginal. **§3-G family extension** (oi_price_decoupling daily aggregation extension) + **filter mechanism**. 36th paradigm graveyard. funding 데이터 366일 한계로 R-2 OOS ~6mo small-sample 수준.)

**이전 갱신**: 2026-05-06 (premium_oi_correlation_regime **#3 PARADIGM_QUEUE_2026Q2** graveyard — daily premium z + daily OI change z, rolling 30d corr regime filter on premium signal. R-1 SOL baseline (no filter = premium_index_zscore replication) sharpe **2.155** ✅ 정상. high_corr_follow ez=1.5 ct=0.2 SOL 3 trades sharpe -2.15, low_corr_fade SOL 8 trades sharpe -1.02. R-2 quick 5종: high_corr_follow alpha 5/5/sharpe **3/5**/mean -0.012/31 trades (DOGE alpha 166/sharpe 1.97/12 trades 만 의미), low_corr_fade sharpe **0/5**/mean -3.76. **시드 premium_index_zscore DOGE (17 trades sharpe 3.15 alpha 348) 명백히 약화** — filter는 trade 빈도 죽이고 새 alpha 못 더함. R-3 SKIP, **§3-G filter mechanism** (joint_3signal_ensemble과 동일 패턴). **35th paradigm graveyard**.)

**이전 갱신**: 2026-05-06 (cross_asset_premium_spread **#2 PARADIGM_QUEUE_2026Q2** graveyard — alt premium z 마이너스 BTC premium z 후 30d z-score, fade=spread extreme alt mean-revert 가설. R-2 10종 fade ez=1.5 alpha **9/10** sharpe **9/10** mean +125.86, ETC 236/sharpe 3.08/PF 4.15/wr 70 (4/5 cutoff!). 그러나 R-3 perm n=200 fail-fast catastrophic: **AVAX random_mean 127.79 vs real 89.54 (-0.59σ)**, **UNI random_mean 167.20 vs real 65.18 (-0.82σ)**. ETC만 2.49σ borderline. **§3-D directional bias 결정적** (alt fade against bear OOS) + §3-G premium domain saturation. **34th paradigm graveyard**. premium_volatility_regime(#1, SOL 2.17σ, today)와 동일 패턴 — paper-pool 14종 × 5 seeded paradigms saturation 재재재확인.)

**이전 갱신**: 2026-05-06 (premium_volatility_regime #1 PARADIGM_QUEUE_2026Q2 graveyard — daily premium high-low range 30d z-score. R-2 follow ez=2.0 alpha 8/10 sharpe 6/10 mean +40.92. R-3 best SOL 2.17σ borderline. random_mean 31-40 → §3-D directional bias.)

> 🚀 **새 세션 시작 시**: `Read backend/runs/research_track/NEXT_PARADIGM_RUNBOOK.md`
>
> 📋 **2026-Q2 (Day 30 대기 기간) paradigm 발굴 큐**: `Read backend/runs/research_track/PARADIGM_QUEUE_2026Q2.md` (16 candidates 우선순위, 일별 schedule, fail-fast 결정 트리)

---

## 진행 중 paradigm

| Paradigm | 상태 | 현재 Phase | 시작일 | 다음 액션 |
|---|---|---|---|---|
| `funding_carry` | **✅ R-5 paper seeded** (3 sessions) | R-5 사용자 승인 완료 | 2026-05-04 | Day 7 점검 (2026-05-11), Day 30 검증 (2026-06-03) |
| `autocorr_regime` | **✅ R-5 paper seeded** (2 sessions) | R-5 사용자 승인 완료 | 2026-05-04 | Day 7 (2026-05-11), Day 30 (2026-06-03) |
| `funding_dispersion` ⭐ | **✅ R-5 paper seeded** (1 session) | R-5 사용자 승인 완료 2026-05-05 | 2026-05-05 | Day 7 (2026-05-12), Day 30 (2026-06-04) |
| `cross_symbol_lead_lag` ⭐ | **✅ R-5 paper seeded** (1 session, RESURRECTED) | R-5 사용자 승인 옵션 A 2026-05-05 | 2026-05-05 | Day 7 (2026-05-12), Day 30 (2026-06-04) |
| `positioning_dynamics` (3-I) | 🔄 **데이터 누적 중** (option A) | Pre-R-1 (data accumulation) | 2026-05-04 | ~2026-07-03 (60d 누적 후 R-1 시작) |
| `oi_price_decoupling` ⭐ | **✅ R-5 paper seeded** (1 session) | R-5 사용자 승인 완료 2026-05-06 | 2026-05-06 | Day 7 (2026-05-13), Day 30 (2026-06-05) |
| `premium_index_zscore` ⭐⭐⭐ | **✅ R-5 paper seeded** (3 sessions, **track 최강**) | R-5 사용자 승인 옵션 B 2026-05-06 | 2026-05-06 | Day 7 (2026-05-13), Day 30 (2026-06-05) |
| `premium_velocity_zscore` ⭐ | **✅ R-5 paper seeded** (2 sessions, **큐 첫 break-through**) | R-5 사용자 승인 옵션 A 2026-05-06 | 2026-05-06 | Day 7 (2026-05-13), Day 30 (2026-06-05) |
| `wick_reversal_multibar` ⭐ | **✅ R-5 paper seeded** (1 session, **single-symbol exception**) | R-5 사용자 승인 single-sym 2026-05-06 | 2026-05-06 | Day 7 (2026-05-13), Day 30 (2026-06-05) |

**wick_reversal_multibar Paper 시드 sessions (2026-05-06, user approved single-symbol exception)**:
| Session ID | Symbol | Spec | backtest baseline (PoC R-3 n=2/wt=0.35/h=12, 5m) |
|---|---|---|---|
| **99107ad5-edd** ⭐ | SOLUSDT | SOLUSDT_wick_reversal_multibar_paper_seed | alpha **61.94** / sharpe **1.41** / mdd 11.2 / wr 51.6 / PF 1.45 / 122 trades / **perm_p 0.000 4.49σ** (Q3 큐 첫 4σ+ POSITIVE, NEW dim 입증) |

**구현 산출물 (wick_reversal_multibar 시드, 2026-05-06)**:
- `app/composer_framework/sources/binance_wick_reversal_multibar_source.py` (신규 BinanceWickReversalMultibarSource — 5m intra-bar OHLC SHAPE asymmetry rolling 2-bar avg + prior_ret JOINT, signal {-1,0,+1})
- `app/composer_framework/pipeline_spec.py` (`bn_wick_reversal_multibar` source register)
- `app/composer_framework/sources/__init__.py` (export 추가)
- `scripts/milestone_check.py` (RESEARCH_TRACK_SEEDS + BASELINE_METRICS wick_reversal_multibar 1 session)
- `configs/paper_sessions/SOLUSDT_wick_reversal_multibar.json` (PassthroughComposer + LongShortThresholdPolicy 재사용, eval_freq_minutes=5)
- 첫 dry-run: `pred=+0.0000 action=hold side=flat equity=1,000,000` (extreme wick 신호 본질적 희소, 정상)

**Paradigm 설계**: 5m candle intra-bar OHLC SHAPE asymmetry. lower_wick_frac/upper_wick_frac rolling 2-bar mean + prior_ret 12-bar lookback (1h). lwf_mean > 0.35 + prior_ret < -3% → LONG (sustained lower wick + drop = liquidation reversal). uwf_mean > 0.35 + prior_ret > +3% → SHORT (climax). Hold 12 bars (1h), SL 2%. **Diversity**: SOL은 premium_index_zscore (premium 1d 도메인) 시드 — wick_reversal_multibar는 intra-bar OHLC 5m 도메인 (다른 도메인 + 다른 timeframe) → diversity ✓. **§3-C reservation**: 1/4 multi-symbol consistency (SOL 4.49σ PASS / AVAX 3.16σ borderline / DOGE 1.94σ / HBAR 1.30σ). 사용자 승인 single-symbol seed exception. NEW dim 입증 — multi-bar averaging이 random_std 12.91→10.30 (-20%) 감소 + alpha boost 4% 결합으로 Q3 #2 wick_reversal 3.34σ → 4.49σ 상승.

**premium_velocity_zscore Paper 시드 sessions (2026-05-06, user approved 옵션 A 2종)**:
| Session ID | Symbol | Spec | backtest baseline (PoC R-3 follow ez=1.0 h=5, daily) |
|---|---|---|---|
| **e4bff252-84a** ⭐ | AVAXUSDT | AVAXUSDT_premium_velocity_zscore_paper_seed | alpha **365.86** / sharpe **2.42** / mdd 46.6 / wr **64.0** / PF 2.25 / 50 trades / **perm_p 0.000 6.86σ (큐 최강)** |
| 8d70b971-0ec | HBARUSDT | HBARUSDT_premium_velocity_zscore_paper_seed | alpha **279.34** / sharpe **2.143** / mdd 25.81 / wr 61.5 / PF 2.29 / 52 trades / perm_p 0.000 5.25σ |

**구현 산출물 (premium_velocity_zscore 시드, 2026-05-06)**:
- `app/composer_framework/sources/binance_premium_velocity_zscore_source.py` (신규 BinancePremiumVelocityZScoreSource — daily premium close 1차 diff 30d z-score, follow signal {-1,0,+1})
- `app/composer_framework/pipeline_spec.py` (`bn_premium_velocity_zscore` source register)
- `app/composer_framework/sources/__init__.py` (export 추가)
- `scripts/paper_session_cli.py` (`bn_premium_velocity_zscore` to premium_df load condition)
- `scripts/milestone_check.py` (RESEARCH_TRACK_SEEDS + BASELINE_METRICS premium_velocity_zscore 2 sessions 추가)
- `configs/paper_sessions/{AVAX,HBAR}USDT_premium_velocity_zscore.json` (2 specs, PassthroughComposer + LongShortThresholdPolicy 재사용, eval_freq_minutes=1440)
- 첫 dry-run: 2 sessions 모두 `pred=+0.0000 action=hold side=flat equity=1,000,000` (extreme velocity z 신호 본질적으로 희소, 정상)

**Paradigm 설계**: Daily premium velocity = premium_close[t] - premium_close[t-1] (1st derivative). Rolling 30-day z-score of velocity. **follow mode**: vel_z > +1.0 → LONG (premium accelerating up = momentum), vel_z < -1.0 → SHORT. Hold 5 days, SL 5%. premium_index_zscore (level paradigm)와 timing 차이 — velocity는 trend 시작 더 빨리 포착. **Diversity**: AVAX/HBAR는 시드 안 됐던 종목들로 premium_velocity 통해 처음 시드, **다른 도메인 시드와 직교**: AVAX (oi_price_decoupling 시드, microstructure 5m) ↔ premium velocity 1d / HBAR (funding_carry 시드, 8h funding) ↔ premium velocity 1d. R-3 3/10 PASS at 4σ+ (premium_index_zscore 4/4 / oi_price_decoupling 4/4 다음 가는 robustness).

**premium_index_zscore Paper 시드 sessions (2026-05-06, user approved 옵션 B 3종)**:
| Session ID | Symbol | Spec | backtest baseline (PoC R-3 follow z=2.0 h=5, daily) |
|---|---|---|---|
| **07934d53-b9d** ⭐⭐⭐ | DOGEUSDT | DOGEUSDT_premium_index_zscore_paper_seed | alpha **348.17** / sharpe **3.15** / mdd 8.8 / wr 76.5 / PF **11.76** / 17 trades / **perm_p 0.000 9.0σ** (track 최강) |
| f99ca950-931 | SOLUSDT | SOLUSDT_premium_index_zscore_paper_seed | alpha 166.52 / sharpe 2.62 / mdd 8.7 / wr 70.6 / PF 6.31 / 17 trades / perm_p 0.000 5.4σ |
| a2f423ae-2ce | LDOUSDT | LDOUSDT_premium_index_zscore_paper_seed | alpha 290.07 / sharpe 2.66 / mdd **6.0 BEST** / wr 76.9 / PF **12.00** / 13 trades / perm_p 0.000 5.7σ |

**구현 산출물 (premium_index_zscore 시드, 2026-05-06)**:
- `app/composer_framework/sources/binance_premium_index_zscore_source.py` (신규 BinancePremiumIndexZScoreSource — daily premium close rolling 30d z-score, follow-momentum signal {-1,0,+1})
- `app/composer_framework/pipeline_spec.py` (`bn_premium_index_zscore` source register with premium_df runtime)
- `app/composer_framework/sources/__init__.py` (export 추가)
- `scripts/paper_session_cli.py` (`bn_premium_index_zscore` to premium_df load condition)
- `scripts/milestone_check.py` (BASELINE_METRICS + RESEARCH_TRACK_SEEDS premium_index_zscore 3 sessions 추가)
- `configs/paper_sessions/{DOGE,SOL,LDO}USDT_premium_index_zscore.json` (3 specs, PassthroughComposer + LongShortThresholdPolicy 재사용, eval_freq_minutes=1440)
- 첫 dry-run: 3 sessions 모두 `pred=+0.0000 action=hold side=flat equity=1,000,000` (extreme z 신호 본질적으로 희소, 정상)

**Paradigm 설계**: Daily premium index = (mark - index)/index, 1d kline aggregation from data.binance.vision archive. Rolling 30-day z-score of close. **follow mode**: z > +2.0 → LONG (sustained premium = bullish hedger demand momentum), z < -2.0 → SHORT. Hold 5 days, SL 5%. funding_carry(8h settled clamped reversal)와 직교 — premium은 1d real-time raw basis with momentum direction (fade가 아닌 follow). 4/4 perm test PASS at perm_p ≤ 0.02 (DOGE 9.0σ는 본 트랙 최강 perm σ).

**oi_price_decoupling R-3 perm test 결과 (n=100, 2026-05-06)**:
| Symbol | Mode | Alpha | Sharpe | MDD | WR | PF | Trades | perm_p | σ above random |
|---|---|---|---|---|---|---|---|---|---|
| **AVAXUSDT** ⭐ | **confirm** | **145.65** | **1.73** | **27.9** | 49.3 | 1.26 | 523 | **0.0000** | **6.7σ** |
| UNIUSDT | confirm | 101.12 | 1.19 | 41.1 | 48.7 | 1.19 | 522 | 0.0000 | 4.8σ |
| AXSUSDT | invert_decouple | 77.73 | 0.65 | 23.5 | 47.5 | 1.29 | 177 | 0.0000 | 3.7σ |
| LINKUSDT | invert_decouple | 71.21 | 1.17 | 16.3 | 48.4 | 1.32 | 159 | 0.0000 | 5.2σ |
| HBARUSDT | invert_decouple | 58.47 | 0.55 | 12.5 | 45.8 | 1.15 | 155 | 0.0000 | 4.5σ |

**oi_price_decoupling Paper 시드 sessions (2026-05-06, user approved)**:
| Session ID | Symbol | Spec | backtest baseline (PoC R-3 confirm z=2.0 h=24) |
|---|---|---|---|
| 2555033d-308 | AVAXUSDT | AVAXUSDT_oi_price_decoupling_paper_seed | alpha 145.65 / sharpe 1.73 / mdd 27.9 / wr 49.32 / PF 1.257 / 523 trades / perm_p 0.000 (6.7σ above random) |

**구현 산출물 (oi_price_decoupling 시드, 2026-05-06)**:
- `app/composer_framework/sources/binance_oi_price_decoupling_source.py` (신규 BinanceOIPriceDecouplingSource — 5m close + open_interest joint z-score signal)
- `app/composer_framework/pipeline_spec.py` (`bn_oi_price_decoupling` source register)
- `app/composer_framework/sources/__init__.py` (export 추가)
- `scripts/paper_session_cli.py` (`bn_oi_price_decoupling` to needs_metrics_5m source list)
- `scripts/milestone_check.py` (BASELINE_METRICS + RESEARCH_TRACK_SEEDS oi_price_decoupling 추가)
- `configs/paper_sessions/AVAXUSDT_oi_price_decoupling.json` (PassthroughComposer + LongShortThresholdPolicy 재사용)
- 첫 dry-run 결과: `pred=+0.0000 action=hold side=flat equity=1,000,000` (extreme z 신호 본질적으로 희소, 정상)
- backtest_paper_specs.py 한계 확인: 1d 강제 resample로 5m paradigm baseline 측정 불가능 (autocorr_regime LINK도 동일 0 trades). PoC R-3 결과가 canonical baseline.

**Paradigm 설계**: 5m close + open_interest (microstructure joblib 2y backfill 활용). Rolling 288-bar(24h) z-score of log_return AND ΔOI/OI. Two modes per symbol (perm 검증):
- `confirm` (price·OI 같은 부호 extreme): trend confirmation, follow price (AVAX/UNI)
- `invert_decouple` (price·OI 반대 부호 extreme, but follow price): OI fade signal continuation (LINK/AXS/HBAR)

**핵심 발견**: 본 paradigm은 runbook §2-A에서 `funding_oi_divergence` ⏸ "OI 30d 부족"으로 보류되어 있었으나, **microstructure joblib(2y 5m OI/LSR/TBS)** 존재 확인됨. positioning_dynamics 트랙 60d 대기 불필요. 즉시 R-1~R-3 가능.

**구현 산출물 (2026-05-06)**:
- `scripts/poc_oi_price_decoupling.py` (R-1+R-2 PoC, 3 modes: decouple/invert_decouple/confirm)
- `scripts/poc_oi_price_decoupling_r3.py` (R-3 perm test, n=100, shuffle returns AND OI deltas independently)
- `runs/research_track/oi_price_decoupling/{r1,r2,r3,gate_eval,paper_seed_proposal}__*.{json,csv,md}`
- 5/5 perm_p=0.0000 (AVAX 6.7σ best)


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
| `oi_price_decoupling` ⭐ | 2026-05-06 | AVAXUSDT confirm (1) | active — Day 30 검증 2026-06-05. 4 backup 후보(UNI/AXS/LINK/HBAR) 모두 perm 0.000 — Day 30 후 추가 시드 결정 |
| `premium_index_zscore` ⭐⭐⭐ | 2026-05-06 | DOGE/SOL/LDO follow (3) | **active — track 최강** Day 30 검증 2026-06-05. 모두 5/5 strict cutoff. AVAX backup 후보 perm 0.020. |

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
| `top_global_lsr_divergence` | 2026-05-06 | top_position_LSR − global_account_LSR rolling 288-bar z-score. follow_top mode (smart money 따라가기) SOL R-1 best z=2.5 h=48 alpha+30 sharpe+0.11 (borderline PASS), fade_top 전 sweep catastrophic. R-2 10종 follow_top z=2.5 h=48: alpha **2/10** (AVAX +87/SOL +30 only) sharpe **2/10**, alpha mean -8.82, 8/10 catastrophic 음수. funding_window_anomaly(alpha 10/10) §3-E 패턴조차 안 됨. R-3 SKIPPED. 보조: top_account vs top_position size disparity 5종 quick — fade_size 3-4/5 weak (DOGE +75/AVAX +34/HBAR +17), best PF 1.14. **Lesson**: LSR positioning state는 종목별 microstructure 특성이 크게 다름. "Smart money vs retail" classic 가설 5m granularity 입증 안 됨. oi_price_decoupling(OI flow, perm 0.000 6.7σ) 대비 결정적 격차 — flow vs state 차이 결정적. | `_graveyard/top_global_lsr_divergence/` |
| `taker_flow_zscore` | 2026-05-06 | 5m taker_buy_sell_ratio rolling 288-bar log(TBS) z-score (raw TBS heavily right-skewed → log 변환 후 symmetric). fade/follow 모드 모두 SOL sweep 진행. fade z=2.5 h=24 SOL alpha+35/sharpe+0.20/mdd 26.7 R-1 marginal PASS, follow 모든 sweep catastrophic. R-2 10종 fade z=2.5 h=24: alpha **3/10** (SOL +35만 의미) sharpe **1/10**, alpha mean -7.0. top_global_lsr_divergence와 동일 패턴 — SOL outlier. 보조: TBS×Price joint signal 7종 quick — confirm alpha 4/7 sharpe 0/7 best AXS sharpe+0.27 (oi_price_decoupling AVAX 145/1.73의 2-6× 약함). R-3 SKIPPED. **Lesson**: OI는 microstructure 데이터의 unique 강한 signal. TBS/LSR 단일 z-score는 noisy하고 sticky. 다음 시도 방향: 새 데이터 도메인 (book_depth, premium_index) 또는 OI × Funding × Price 3-feature combo (§3-G 위험). microstructure joblib 단일 컬럼 paradigm 추가 시도 권장 안 됨. | `_graveyard/taker_flow_zscore/` |
| `book_depth_imbalance_zscore` | 2026-05-06 | 1d LOB imbalance_mean rolling 30d z-score, fade/follow 모드 테스트 (6 종 only: LINK/AVAX/SOL/DOGE/BTC/ETH, 1y data). R-1 SOL fade z=1.0 h=5 alpha+80/sharpe+1.89/PF 1.79/wr 64/mdd 18.4 (25 trades) — 3/5 cutoff borderline. R-2 6종: **alpha 6/6 ✅** 양수 (mean +42), sharpe 3/6 (ETH/SOL/BTC), best ETH alpha 62/sharpe 1.83/PF 1.88/mdd 14.8/wr 71. R-3 perm n=200 fade z=1.0 h=5: ETH **0.035 2.2σ PASS**, SOL **0.050 1.8σ borderline PASS**, BTC **0.275 FAIL**, DOGE **0.360 FAIL** — **2/4 perm PASS only**. 시드된 paradigms (premium_index 9.0σ / oi_price_decoupling 6.7σ / autocorr_regime strong perm) 대비 결정적 격차. ETH gate 5/9 (2/5 strict + 3/4 robustness, n_trades 21<30). **Lesson**: LOB-level passive imbalance signal 존재 (4× random_mean ratio for ETH)이지만 magnitude 약함, 1y/6 symbols 데이터로 paradigm robustness 입증 불충분. **22 LSR / 23 TBS / 25 LOB 모두 graveyard → state/passive-pressure signals weak; commitment(OI)/basis(premium)/flow(funding) signals strong**. book_depth 2y+ + 14종 확장 후 재평가 가능. | `_graveyard/book_depth_imbalance_zscore/` |
| `premium_dispersion` | 2026-05-06 | 14종 daily premium close cross-section z-score (funding_dispersion 8h analog at 1d). fade z=0.5 h=10 R-1 SOL alpha+122/sharpe+1.19. R-2 10종 alpha **5/10 only** (DOGE +226/SOL +122 outlier만), funding_dispersion 13/14와 결정적 격차. R-3 perm DOGE 0.040 2.2σ PASS / SOL 0.275 FAIL — **1/2 perm PASS, DOGE 2.2σ vs premium_index_zscore DOGE 9.0σ 결정적 약함**. **§3-G family-extension 확인**: premium_index_zscore (24th seeded, DOGE 9σ) 가 같은 DOGE premium signal의 95% 정보 포착, premium_dispersion은 weak residual. cross-section dispersion paradigm은 measurement type 의존 — funding rate(clamped/settled)에서만 강함, premium(raw/real-time)에서 약함. R-5 SKIPPED. **결론**: premium/funding/OI 도메인 saturated, 다음 paradigm 시도는 새 데이터 도메인 또는 multi-domain joint signal 필요. | `_graveyard/premium_dispersion/` |
| `joint_3signal_ensemble` ⭐ POSITIVE | 2026-05-06 | premium_index_zscore + oi_price_decoupling + funding_carry 신호 daily voting (require_2 mode). R-1 SOL require_2 h=3 alpha+95/sharpe+2.76/PF 6.37 4/5 strict. **unanimous mode 0 firings → 3 paradigms uncorrelated 검증** ✅. R-2 10종 require_2 h=3: alpha **9/10** mean +103, sharpe 8/10, **3 syms 5/5 strict** (DOGE+309/sharpe2.85, LDO+179, COMP+151) — premium_index_zscore와 사실상 동급. R-3 perm n=200 **4/4 PASS perm_p≤0.04**: DOGE **9.6σ 본 트랙 31 paradigms 중 최고 기록 ⭐**, COMP 4.4σ, LDO 3.7σ, AVAX 1.8σ borderline. **§3-G 명백**: 모든 4 strong candidates 이미 시드됨 (DOGE TRIPLE redundant premium+lead_lag, LDO premium, COMP funding_carry, AVAX oi_price_decoupling). ensemble = component signals filter quality 개선 (premium DOGE 9.0σ→ensemble 9.6σ +10%) but 새 alpha source 없음. R-5 SKIPPED. **POSITIVE 의의**: voting mechanism 검증 + uncorrelated alpha sources 입증. **Code 보존** (poc_joint_3signal_ensemble.py + r3) 향후 live trading confidence filter (size×1.5/2) 또는 portfolio-level ensemble strategy 발전 시 활용. | `_graveyard/joint_3signal_ensemble/` |
| `funding_oi_premium_3sigma_event` | 2026-05-06 | **#16 PARADIGM_QUEUE_2026Q2** §3-A rare-event 결정적 — 3 시드 paradigm 데이터 동시 ±σ 같은 sign rare-event composite. **0 trades at sigma 3.0/2.0/1.5** (3-way 동시 발화 자체 없음), sigma 1.0 lenient에서도 9 trades total (1/symbol/year). 가설 자체는 흥미롭지만 funding 366d + 30d zwin 후 OOS ~6mo 데이터로 paradigm 본질적 검증 불가능. R-2/R-3 SKIP. **funding 2y+ 누적 후 재시도 가치** (정말 super-rare 3-way agreement은 매우 strong signal일 수 있음). | `_graveyard/funding_oi_premium_3sigma_event/` |
| `multi_zwin_ensemble_premium` | 2026-05-06 | **#15 PARADIGM_QUEUE_2026Q2** §3-G timeframe ensemble — premium 15d/30d/60d z-score 동시 같은 sign + |z_sum| > thresh → follow z_sum direction. R-1 SOL: zsum=5 alpha 131.99/sharpe 2.07/PF 4.34/wr 76.5/17 trades (premium_index_zscore SOL 17 trades와 동일 — 사실상 같은 events 포착). R-2 10종 alpha 9/10 sharpe **5/10** mean 0.098 (premium_index_zscore보다 약화), best LDO alpha 198/sharpe 1.62/PF 2.54, AVAX 137/1.64. R-3 perm n=200: **SOL perm_p 0.0 4.03σ PASS** (4σ에 간신히), LDO 0.005 3.47σ borderline, AVAX 0.02 2.72σ. **§3-G timeframe ensemble**: premium_index_zscore SOL **5.4σ** (시드, zwin=30 single) → ensemble (15d+30d+60d) **4.03σ** = 명백한 정보 손실. **Lesson**: timeframe ensemble은 voting보다 약함, single optimal zwin이 우월. premium 도메인의 timeframe variation은 모두 weak residual saturation. R-5 SKIPPED. | `_graveyard/multi_zwin_ensemble_premium/` |
| `weekday_DoW_combined` ⭐ POSITIVE | 2026-05-06 | **#14 PARADIGM_QUEUE_2026Q2** — premium z>1.5 + DoW ∈ {Thu(3), Fri(4), Sat(5)} 3일 cluster filter, follow premium direction. R-1 SOL 강함. R-2 10종 alpha **10/10** mean **+143.10** sharpe **9/10** mean **1.83 (큐 최고)**: **DOGE alpha 319.09/sharpe 3.00/PF 37.19/wr 86.7/mdd 3.2/15 trades**, **SOL alpha 214.16/sharpe 3.72/PF 14.47/wr 76.5/mdd 2.5/17 trades**, **LDO alpha 220.59/sharpe 3.15/PF 9.12/wr 78.6/14 trades**, **AVAX alpha 176.81/sharpe 2.67/PF 4.64/wr 71.4/21 trades**, UNI alpha 121/sharpe 1.80, ETC/LINK/HBAR/COMP/AXS borderline-positive. R-3 perm n=200: **DOGE 9.09σ / SOL 8.75σ / LDO 4.35σ / AVAX 4.33σ ALL PASS 4σ+** (4/5), UNI 2.02σ borderline. **§3-G strong**: 모든 4 PASS 종목 이미 다른 paradigm으로 시드 — DOGE/SOL/LDO premium_index_zscore (9.0/5.4/5.7σ), AVAX premium_velocity (6.86σ #10). DOGE trade count 비교: premium_index 17 trades vs DoW combined 15 trades → **Thu/Fri/Sat이 premium z extreme events의 95% 포착** = 같은 신호의 calendar 재라벨링, 새 alpha 없음. R-5 SKIPPED. **POSITIVE 의의**: weekend_drift_premium 가설 (Friday filter 1.9-3.9σ borderline) 정확한 확장 형태 발견 — **pre-weekend 3-day cluster**가 premium 신호의 95% concentration. **Lesson**: premium 신호의 시간 분포가 강한 calendar bias 보임 (Thu-Sat 75%, Mon-Wed 25%). live trading position management에서 premium signal은 Thu/Fri/Sat에 entry 우선 가치 있음 (filter overhead 없이도). | `_graveyard/weekday_DoW_combined/` |
| `premium_oi_joint_filter` | 2026-05-06 | **#13 PARADIGM_QUEUE_2026Q2** §3-G filter mechanism — premium z fire (|prem_z|>2) + OI z direction agree (sign match + |oi_z|>oi_min_z) → confirmation entry, follow premium direction. R-1 SOL sweep: **oiz=0 (filter 없음 = premium_index_zscore baseline)** alpha 82/sharpe 1.35 정상. **모든 oi filter 적용 (oiz=0.5/1.0): sharpe ≤ 0** (alpha 12-20, sharpe -0.8 to -1.96). R-2 SKIPPED. **§3-G filter mechanism 4번째 확인**: #3 premium_oi_correlation_regime와 동일 패턴 (filter는 trade sparsifier, 새 alpha 못 더함), joint_3signal_ensemble과 동일 family (POSITIVE 의의는 voting mechanism, 단순 filter는 정보 손실). **Lesson 강화**: 시드된 component signal에 또 다른 시드 signal로 filter 적용은 항상 약화. ensemble voting (3-signal majority)만 marginal value 있음, simple AND filter는 정보 손실. | `_graveyard/premium_oi_joint_filter/` |
| `bid_ask_concentration_regime` | 2026-05-06 | **#12 PARADIGM_QUEUE_2026Q2** — book_depth top1_concentration_mean 30d z (top of book size 비율 = single-actor concentration measure), prior-return direction. R-1 SOL fade ez=2.0 alpha 46.54/sharpe 0.71/PF 1.45/mdd 9.3/wr 70 (10 trades only). R-2 6 종 fade ez=2.0 (book_depth 365d 한정 6 syms): alpha **6/6** mean +50.89, sharpe **5/6** mean 1.29. **BTC sharpe 3.18/PF 8.15/mdd 1.4/wr 67** (5/5 cutoff!), **ETH sharpe 2.51/PF 4.75/wr 83** (5/5 cutoff!), DOGE/SOL/LINK weaker. **그러나 trades 6-10 per symbol** = §3-A rare-event extreme. R-3 perm n=200: ETH **1.94σ borderline FAIL** / BTC 1.41σ / DOGE 0.48σ / SOL 0.60σ — 모두 4σ 미달. R-5 SKIPPED. **§3-A rare-event 결정적** (sample size 미달) + **book_depth_imbalance(graveyard 25th) family**. **Lesson**: book_depth 365d 데이터 + 30d zwin → 약 240 OOS days로 strict z>2.0 events는 6-10건 발생, paradigm robustness 입증 본질적으로 불가. **2y+ book_depth backfill 후 재시도 가치 있음** (BTC/ETH의 5/5 cutoff은 진짜 신호일 가능성 시사). | `_graveyard/bid_ask_concentration_regime/` |
| `garman_klass_vol_premium` | 2026-05-06 | **#11 PARADIGM_QUEUE_2026Q2** — Garman-Klass vol estimator on premium OHLC (vol²_proxy = 0.5(H-L)² - (2ln2-1)(C-O)²) z-score, direction from prior 5d return. fade 모든 sweep catastrophic, follow 작동. R-1 SOL follow ez=1.0 rl=5 alpha **190.26/sharpe 2.65/PF 3.52/mdd 13.1/wr 63 (5/5 strict cutoff!)** 27 trades 15L 12S balanced. R-2 10종 alpha **10/10** sharpe **8/10** mean +71.41. **그러나 #10 premium_velocity_zscore와 distinct**: AVAX 46/0.15 (vs #10 366/2.42), HBAR 47/0.24 (vs #10 279/2.14) — vol과 velocity는 별개 신호이지만 GK는 #11에서 SOL 외 약함. R-3 perm n=200 (shuffle premium OHLC rows): **SOL perm_p 0.0 5.4σ PASS** 단독, UNI 0.005 3.51σ borderline, LDO 0.115 1.31σ FAIL. **SOL single-symbol fit** — premium_index_zscore SOL (시드 5.4σ)와 같은 종목·도메인의 변환만, 새 정보 없음. R-5 SKIPPED. **§3-G premium domain saturation 5번째 확인**: premium의 vol-of-basis 3 paradigm 모두 graveyard (#1 range simple z / #7 range/median ratio / #11 GK estimator) — measurement variation은 모두 weak residual. **Lesson**: SOL은 premium 도메인의 거의 모든 변환에서 강한 신호 보임 (level 5.4 / velocity 4.88 / GK-vol 5.4σ). 이는 SOL의 premium structure가 정보적이라는 단일 사실을 다른 metric으로 측정한 것. SOL premium "single-symbol composite" strategy로 별도 보존 가치 있을 수 있음 (premium_index_zscore SOL 이미 시드). | `_graveyard/garman_klass_vol_premium/` |
| `oi_change_acceleration_squeeze` | 2026-05-06 | **#9 PARADIGM_QUEUE_2026Q2** ⚠ §3-G 매우 강함 — daily OI pct change 2nd derivative (acceleration) z-score. modes: follow_oi/fade_oi/follow_accel/fade_accel. fade modes 모두 catastrophic (sharpe -1 to -4). best **follow_accel ez=1.0**: R-1 SOL alpha 94.67/sharpe 1.073 (42 trades 21L 21S **perfectly balanced** — directional bias 없음). R-2 10종: alpha **9/10** sharpe **7/10** mean +79.14, **ETC alpha 161.17/sharpe 1.53/PF 1.80/mdd 28.3/wr 59.1/44 trades (5/5 strict cutoff!)**, LINK 110/1.22 (4/5), SOL 94/1.07 (3/5), LDO 76/0.63 (3/5). R-3 perm n=200 7 symbols: **ETC perm_p 0.0 (200/200) sigma 3.98σ ← 큐 best signal, 4σ에 1bp 미달**, LINK perm_p 0.04 sigma 2.01σ borderline, SOL 0.075 1.66σ, LDO 0.13 0.74σ, **AVAX 0.39σ / UNI -0.69σ / DOGE -0.24σ = 5/7 random**. **ETC outlier single-symbol fit** — paradigm robustness 입증 불충분. random_mean for ETC ~52 vs real 161 (3.1× ratio = significant for ETC alone). 시드된 oi_price_decoupling 5m AVAX 6.7σ + UNI 4.8σ + LINK 5.2σ + AXS 3.7σ (4/4 strong) 대비 결정적 약함. R-5 SKIPPED. **§3-G family-extension confirmed**: 2nd derivative (acceleration)은 1st derivative (decoupling)보다 약함. **Lesson**: derivatives 위계 — 0차(level: premium_index_zscore 9σ) > 1차(velocity: oi_price_decoupling 6.7σ) > 2차(acceleration: 3.98σ outlier). 더 높은 차원 paradigm 시도 권장 안 됨. ETC 단일 종목은 별도 strategy 가치 검토 가능. | `_graveyard/oi_change_acceleration_squeeze/` |
| `funding_premium_spread_zscore` | 2026-05-06 | **#8 PARADIGM_QUEUE_2026Q2** ⚠ §3-G strong (두 시드 결합) — spread_z = funding_daily_z - premium_daily_z. modes: fade/follow on spread_z. R-1 SOL: fade ez=1.0 alpha **46.64/sharpe 0.587** (20 trades) 만 통과, follow 모든 sweep sharpe negative. R-2 10종 fade ez=1.0: alpha **7/10** (mean +10.75) 가까스로 6/10 통과, sharpe **4/10** (mean -1.092) 매우 약함, SOL/ETC 만 의미 있음. R-3 perm n=200: **SOL perm_p 0.005 3.10σ borderline** (큐 best와 동급, real 46 vs random_mean 30), **ETC perm_p 0.41 0.08σ = random** (real 44 vs random_mean 41). **SOL outlier, single-symbol fit** — generalization 안 됨. R-5 SKIPPED. **§3-G strong 확인** (component signals 더 강함: funding_carry HBAR 6/6 perm 0.000, premium_index_zscore DOGE 9.0σ) + **§3-D directional bias** (ETC random은 fade 자체가 noise) + funding 366일 데이터 한계. **Lesson**: 두 시드 paradigm의 spread는 noise filter가 아닌 noise residual. ensemble (joint_3signal_ensemble POSITIVE)이 voting으로 정보 추가하는 반면, simple spread는 정보 손실. | `_graveyard/funding_premium_spread_zscore/` |
| `premium_intraday_range_zscore` | 2026-05-06 | **#7 PARADIGM_QUEUE_2026Q2** — premium daily range / 30d rolling median(range) ratio, then 30d z-score. Direction = prior N-day return sign. modes: fade (extreme range + prior up → short) / follow. **fade 가설 invalid** (R-1 SOL fade ez=2.5 rl=5 alpha -5/sharpe -2.94). follow R-1 SOL best ez=1.5 rl=5 alpha **122.06/sharpe 1.708**/22 trades **10L 12S balanced** (#1 premium_volatility_regime와 달리 directional bias 없음). R-2 10종 follow ez=1.5 rl=5: alpha **10/10** sharpe **8/10** mean +55.26 sharpe mean 0.229. SOL alpha 122/sharpe 1.71/PF 2.34/mdd 13.1 (4/5 cutoff), LDO alpha 98/sharpe 0.86/PF 1.58 (3/5), DOGE alpha 60/sharpe 0.53. R-3 perm n=200 (shuffle premium high/low rows): SOL **perm_p 0.01 2.88σ borderline FAIL** (random_mean ~38 vs real 122, 3.2×) / LDO 0.085 1.73σ / DOGE 0.175 1.03σ / UNI 0.15 0.96σ. **SOL 2.88σ는 #1 premium_volatility_regime SOL(2.17σ)보다 약간 강함** (median 정규화 + prior-return direction이 #1의 close-premium-sign direction보다 미묘하게 우월) — but still 4σ 미달. R-5 SKIPPED. **§3-G premium domain saturation** (premium_index_zscore 9σ 상한 정보 흡수) + **volume_absorption family** (range-based event paradigm). **Lesson**: premium range-based signal은 close-level signal보다 약함. premium 도메인의 모든 derived metric (level/range/spread/dispersion/seasonality)이 모두 weak residual인 saturation 4번째 확인. | `_graveyard/premium_intraday_range_zscore/` |
| `cross_section_funding_rotation` | 2026-05-06 | **#6 PARADIGM_QUEUE_2026Q2** — rule-based 14종 daily funding rank portfolio rotation. modes: `carry` (long top-K most negative funding, short top-K most positive) / `reverse` (opposite). R-1 sweep 18 configs (k∈{1,3,5}, h∈{3,7,14}, mode∈{carry,reverse}): **가설 INVERTED — reverse mode 우월**. best **k=1 h=14 reverse alpha 168.85/sharpe 1.73/total 120/mdd 5.4/wr 75/PF 7.87 (12 rebalances)**, bh OOS -48.78% (heavy bear). 다른 strong configs: k=1 h=7 reverse alpha 113.82/sharpe 1.67/24 rebal, k=3 h=14 reverse alpha 79.98/sharpe 1.61/mdd 2.7/PF 4.13. R-3 perm n=200 (shuffle funding within row, preserve marginal): **k=1 h=14 reverse perm_p 0.015 3.01σ borderline FAIL** / k=3 h=14 reverse 1.53σ / k=1 h=7 reverse 1.28σ. random_mean 48.88 (bear OOS에서 random rotation도 자연스럽게 양수 alpha) → real signal의 added value ≈ 120% magnitude. **3.01σ는 큐 첫 5 candidates 중 best signal**이지만 4σ 미달 + **§3-A rare-event** (12 rebalances small sample) + **§3-G multi_symbol_portfolio family** (graveyard ML version). R-5 SKIPPED. **Lesson**: cross-section funding rank은 1y/12 rebalances 데이터로 paradigm robustness 입증 불충분. 2y+ funding accumulation 후 재시도 가치 있음 — 본 트랙 첫 "potentially-real but underpowered" 결과. | `_graveyard/cross_section_funding_rotation/` |
| `monthly_premium_seasonality` | 2026-05-06 | **#5 PARADIGM_QUEUE_2026Q2** — premium daily 30d z-score on calendar mask (last N days of month or first N days). modes: fade_eom (mean-revert 가설) / follow_eom (momentum) / fade_bom. **fade_eom 가설 invalid** (R-1 SOL 모든 sweep sharpe ≤ 0). R-1 SOL follow_eom best nd=7 ez=0.5 alpha 88.21/sharpe 1.37/PF 2.05/26 trades 11L 15S. R-2 10종 follow_eom nd=7 ez=0.5: alpha **9/10** mean +36.77 PASS sparse-rule, sharpe pos **4/10** mean -0.196 weak. SOL alpha 88/sharpe 1.37/PF 2.05 (3/5), UNI 66/0.88, DOGE 74/0.96. R-3 perm n=200 (shuffle premium): SOL **perm_p 0.035 1.89σ borderline FAIL** / DOGE 0.205 0.74σ / UNI 0.205 0.71σ. random_mean 40 vs real 66-88 (50% noise floor) — **weekend_drift_premium(R-3 5/5 PASS at 1.9-3.9σ)보다 약함**. R-5 SKIPPED. **§3-F calendar bias 강함** (time_of_day_seasonality graveyard 패밀리) + **§3-G premium domain saturation**. **Lesson**: monthly seasonality은 weekly Friday filter보다 더 sparse, effect 더 약함. premium 도메인의 calendar restriction은 모두 weak residual로 saturated. | `_graveyard/monthly_premium_seasonality/` |
| `funding_oi_phase_lag` | 2026-05-06 | **#4 PARADIGM_QUEUE_2026Q2** — daily funding mean (3 cycles/day aggregated) + daily OI last value, rolling 30d lead-lag phase indicator. phase = corr(funding_z[t], oi_z[t-1]) − corr(funding_z[t-1], oi_z[t]). >0 = OI leads (smart), <0 = funding leads (retail). R-1 SOL: phase 73% positive mean +0.141 (SOL OI consistently leads funding). best `oi_leads_follow_oi` ez=1.0 pt=0.05 alpha **104.84/sharpe 3.134/PF 6.08/mdd 10.3/wr 60/10 trades** (5/5 strict cutoff). R-2 10종 매우 강함: alpha **9/10** sharpe **8/10** mean +49.59, SOL 5/5/UNI 4/5 (alpha 86/sharpe 2.38/PF 3.81)/LINK 4/5 (alpha 86/sharpe 2.27/PF 2.61). R-3 perm n=200 (shuffle funding only, preserve OI): SOL **perm_p 0.065 1.60σ borderline FAIL**, UNI 0.225 0.76σ, LINK 0.20 0.79σ, AVAX 0.28 0.54σ. **random_mean의 real에 대한 비율 80%** (SOL 80/105, LINK 62/86, AVAX 46/56) → **OI direction 신호 자체가 alpha source의 대부분**, phase filter는 trade 30% 줄이지만 quality 개선 marginal. R-5 SKIPPED. **§3-G family-extension**: oi_price_decoupling 5m AVAX 6.7σ → daily aggregation은 weak residual. **§3-G filter mechanism**: phase filter는 information-theoretic gain 거의 없음. funding 데이터 366일 한계로 OOS ~6mo small-sample 수준 — 더 긴 funding 데이터로 재시도 가치는 없음 (signal 본질이 daily OI direction). | `_graveyard/funding_oi_phase_lag/` |
| `premium_oi_correlation_regime` | 2026-05-06 | **#3 PARADIGM_QUEUE_2026Q2** — daily premium z + daily OI change z, rolling 30d correlation as regime filter on premium signal. modes: `high_corr_follow` / `low_corr_fade` / `baseline`(no filter). R-1 SOL: **baseline sharpe 2.155 alpha 135.95 (15 trades)** ✅ premium_index_zscore 재현 정상 — 데이터 setup 검증. filter 모드 catastrophic: high_corr_follow ez=1.5/ct=0.2 SOL **3 trades sharpe -2.15**, low_corr_fade SOL 8 trades sharpe -1.02. R-2 quick 5종 high_corr_follow ez=1.5/ct=0.2: alpha 5/5 (mean 66.79) sharpe **3/5** (mean -0.012) **31 trades total**, DOGE만 alpha 166/sharpe 1.97/12 trades 의미 — 시드 premium_index_zscore DOGE (17 trades sharpe 3.15 alpha 348) **명백히 약화**. low_corr_fade alpha 5/5 sharpe **0/5** mean -3.76, LINK 0 trades. R-3 SKIP. **§3-G filter mechanism**: joint_3signal_ensemble (POSITIVE 의의로 보존)과 동일 패턴이지만 single-component filter는 magnitude 더 약함. **Lesson**: correlation regime은 새 차원이지만 sparse → trade count 1-12로 collapse → component signal보다 약화. premium 도메인은 premium_index_zscore 단일 z-score로 정보 95% 흡수 결론 재확인. | `_graveyard/premium_oi_correlation_regime/` |
| `cross_asset_premium_spread` | 2026-05-06 | **#2 PARADIGM_QUEUE_2026Q2** — bilateral alt-vs-BTC premium spread paradigm. alt_z - BTC_z (each rolling 30d), then 30d z-score of spread. fade extreme spread → alt mean-revert. R-1 SOL: ez=1.5 follow alpha 64.89 sharpe 0.628 (17L 13S balanced direction!). R-2 10종 fade ez=1.5 매우 인상적: alpha **9/10** sharpe **9/10** mean +125.86, **ETC alpha 236.61/sharpe 3.08/PF 4.15/mdd 21.8/wr 70/30 trades (4/5 strict cutoff)**, LINK 161/1.89, AVAX 89/0.85, LDO/UNI/DOGE/HBAR 양수. 그러나 R-3 perm n=200 catastrophic: ETC perm_p 0.02 **2.49σ borderline**, LINK 0.08 1.46σ, **AVAX random_mean 127.79 > real 89.54 (-0.59σ)**, **UNI random_mean 167.20 > real 65.18 (-0.82σ)**. random shuffled BTC-spread도 양수 alpha 흔하게 생성 → **§3-D directional bias 결정적** (alt premium 자체의 raw signal이 fade-against-bear에 묻혀 spread 차원의 새 정보 무) + §3-G premium domain saturation. 시드된 funding_dispersion(ETC 6× ratio, perm 0.0000) 대비 결정적 약함. R-5 SKIPPED. **Lesson**: bilateral cross-asset spread는 cross-section dispersion보다 약하며, premium 데이터 자체의 노이즈를 BTC reference로 줄이는 효과 있으나 새로운 alpha source 아님. **§3-D 강한 케이스 (UNI/AVAX random > real)**: 단방향 directional 시그널이 fade 모드에서도 random과 구분 불가하게 됨. | `_graveyard/cross_asset_premium_spread/` |
| `premium_volatility_regime` | 2026-05-06 | **#1 PARADIGM_QUEUE_2026Q2** — daily premium (high-low) range 30d z-score, direction from close premium sign. R-1 SOL follow ez=2.5 alpha 105/sharpe 1.78/PF 3.5 매력적이지만 진입 12/12 모두 SHORT. R-2 10종 follow ez=2.0: alpha **8/10** (mean +40.92), sharpe 6/10 (mean 0.085), best SOL alpha 87.89/sharpe 1.22, LDO 85/AVAX 70/LINK 55. R-3 perm n=200 4 best: SOL **perm_p 0.03 sigma 2.17σ borderline**, LDO 0.14 1.07σ FAIL, AVAX 0.24 0.63σ FAIL, LINK 0.23 0.76σ FAIL. **random_mean 31-40 매우 높음** → 직관과 일치하는 결론: short-skewed 진입 + OOS bear period가 random alpha까지 양수로 만들어 real signal 묻힘. **§3-D directional bias 강함 + §3-G premium domain saturation**. premium_dispersion(DOGE 2.2σ borderline graveyard)와 동일 패턴. R-5 SKIPPED. **Lesson**: vol-of-basis는 level-of-basis(premium_index_zscore)의 약 25% 정보만 담고 있으며, 그조차 short-bias로 인해 perm test 통과 못함. premium 도메인 추가 paradigm 시도 권장 안 됨. | `_graveyard/premium_volatility_regime/` |
| `weekend_drift_premium` | 2026-05-06 | Daily premium 30d z-score Friday entry follow momentum (가설: weekend institutional 부재로 premium drift mean-revert — 검증 결과 **fade 모드 catastrophic**, follow가 작동, 가설 자체 wrong). R-1 SOL DoW comparison: Thu/Fri/Sat "pre-weekend cluster" 강함, Mon/Sun 약함. R-2 10종 Friday follow z=1.5 h=3: alpha **10/10**, sharpe 9/10, mean +83.75, top: HBAR/LDO 116/AXS 101/UNI 92/DOGE 85 (4/5 strict cutoff for AXS/UNI/DOGE). R-3 perm n=200 **5/5 PASS** at perm_p≤0.04 but **moderate σ (1.9-3.9σ vs premium_index_zscore 5-9σ)**. **§3-G family-extension**: same data + same direction + Friday filter only. **Random_mean 37-51 base alpha leak 큼** (premium 데이터 자체에서 leak). real/random 1.8-3.9× ratio (premium_index_zscore DOGE 12× 대비 결정적 약함) → weekend filter는 premium의 **30% 정보**. **§3-E 모든 5 candidates 이미 시드** (HBAR/AXS funding_carry, LDO premium, UNI autocorr, DOGE premium+lead_lag). R-5 SKIPPED. **Lesson**: §3-G 유형 정리 — power transform / calendar restriction / ensemble은 모두 weak residual. 새 alpha = 새 데이터 도메인 또는 진짜 새 차원. | `_graveyard/weekend_drift_premium/` |
| `cross_asset_volume_concentration_alt_long_1d` (paradigm 94) | 2026-05-18 | **ad-hoc R-1 user explicit dispatch** (campaign 휴면 모드 예외). BTC daily USD-volume share z(30d)<=-1.5 → 13 alts LONG +1d. Local DB 1m OHLCV BTC+ADA 143 days only (binding constraint) → common dates 101 → 30d warmup 후 usable 72d. Focus z<=-1.5 only 1 trigger day, fallback z<=-1.2 → 5 days/62 trades. **Focus 8bp: gross +11.28bp < 16bp fee floor (BROAD_FALSIFIED_FEE_FLOOR primary)**. **Mirror z>=+1.5 LONG: 4 days/52 trades, net +222bp, sigex +2.76, perm_p 0.002, CI lower +74bp = three-gate ALL PASS but n=4 sparse (DIRECTION_INVERTED_MIRROR_PASS_SPARSE secondary side discovery)**. Concentration FAIL (sym_ci_pos 0/13, Q1 +69bp / Q2 -109bp opposite signs). Cross-proxy fund track (BTC absolute vol z) both quadrants negative → SINGLE_PROXY_TRAP_OBS_MIRROR_ONLY. Family-distinct new transform class (cross-asset volume share boundary z, retired/cautioned 5 families 모두 회피 확인). Lesson #11 prescreen dogfooded (per-sym n=4-5 CI uninformative). **Lesson #30 candidate**: short-data ad-hoc R-1 mirror PASS는 graveyard 아닌 side discovery 처리, 데이터 확장 후 별도 R-1 의무 (trigger-swap antipattern 보완). **Lesson #31 candidate**: fee floor 16bp gate 가 three-gate 우선 적용. Wall-clock 1.49 min foreground. HALT confirmed (R-2 미진행). | `cross_asset_volume_concentration_alt_long_1d/` |
| `cross_asset_volume_share_high_alt_long_1d` (paradigm 95) | 2026-05-19 | **ad-hoc R-1 user explicit dispatch — paradigm 94 mirror evidence independent re-test** (Lesson #8 mirror antipattern). BTC daily USD-volume share z(30d)>=+1.5 (HIGH side, BTC dominance peak) -> 13 alts LONG +1d, Mint joblib 14-sym 845d. Focus n=702 (54 trigger x 13 alts), **gross +96.97bp / sigex +6.86 / ci_lo +59.77 / perm_p 0.000 - focus strict 3-gate PASS**. 50bp stress sigex +6.27 PASS. **Mirror z<=-1.5 (= paradigm 94 focus) sigex +2.64 but ci_lo -4.60 -> mirror strict 3-gate FAIL (direction isolated, paradigm 94 LOW-side broad-falsified 확인)**. Concentration: q_pos_t 7/10 (0.70) PASS, **sym_ci_pos 3/13 (0.231) FAIL marginal - AVAX/BCH/LTC만** (paradigm 94 mirror evidence와 완전 일치). Cross-proxy obs+fund both 3-gate PASS, jaccard 0.179 non-redundant (Lesson #29 PASS). **Lesson #20 narrow-scope 4-cond ALL PASS** (a 4-gate / b held-out 50/50 split first 3-gate+last 3-gate / c Bonferroni p_adj=0.0 / d hold sweep 1d/2d/3d sign 3/3 three-gate 2/3). **Life-changing 4-dim FAIL** (trades/yr 303 PASS / **edge 0.47% << 2% FAIL** / **util 6.39% << 30% FAIL** / sharpe 3.54 PASS) -> `feedback_life_changing_strategy_criterion` sparse-trigger 즉시 탈락. **Verdict: NARROW_SCOPE_LIFE_CHANGING_FAIL** (statistical narrow-scope candidate but capital deployment cap). paradigm 94+95 family verdict: LOW direction broad-falsified + HIGH direction narrow-scope-life-changing-fail. Single-side simple z trigger 1d-hold variant capital cap 본질적. **Lesson #20 dogfood 첫 ALL PASS 성공** (paradigm-architect spec 정상 작동). **NEW verdict 카테고리 NARROW_SCOPE_LIFE_CHANGING_FAIL** 도입: paradigm-architect spec life-changing 4-dim layer 정식 통합 권고. Wall-clock 0.10 min foreground. HALT confirmed (R-2 미진행). | `cross_asset_volume_share_high_alt_long_1d/` |
| `funding_rate_sign_flip_event_alt_long_4h` (paradigm 96) | 2026-05-19 | **ad-hoc R-1 user explicit dispatch** — paradigm 94+95 family Tier 4 retire 직후 family-distinct candidate. Funding rate categorical SIGN FLIP boundary event at 8h cycle: sub-trigger A (pos→neg, long-positioning unwind) + B (neg→pos, short squeeze ignition), 13 alts LONG, hold 4h primary + 4h/8h/12h sweep, Mint funding DB 2.5yr (911d) + OHLCV joblib cache 860d. **Family-distinct DNA 입증**: paradigm 22 (z-score MR continuous) / 73 (joint funding×OI event) / 79 (extreme level filter)와 모두 distinct transform class (categorical boundary event = NEW). Lesson #11 prescreen PASS abundantly (6,934 events, 3470A + 3464B, ~289/sym ~347/quarter). Lesson #19 4-quadrant Symmetric Negative Test dispatched. **Verdict: BROAD_FALSIFIED — 0/4 quadrants three-gate PASS**. A LONG focus n=3,448 **gross -16.47bp / obs_t -4.77 / sigex -3.15 / perm_p 0.000 / ci_lo -23.71bp** = structurally anti-alpha. A SHORT mirror sigex +3.22 but ci_lo -6.26 + perm_p 1.000 = fee floor saturation. B LONG/SHORT essentially zero signal (sigex ±0.1-0.35). Hold sweep 4h/8h/12h monotonic -16bp (mechanism robustly anti-alpha across horizon). Concentration A LONG: q_pos_t 2/10 (0.20) FAIL + sym_ci_pos **0/12** (0.00) FAIL — uniformly negative. Cross-proxy (lesson #29): obs (sign category n=3448) + fund (|mag_z|≥1.0 n=1638) both 3-gate FAIL independently, jaccard 0.475. Life-changing 4-dim: trades/yr 1463 PASS + util 66.8% PASS / **edge -0.165% FAIL + sharpe -3.11 FAIL** (n_dims_pass 2/4). Mechanism reading: pos→neg flip is **lagging confirmation of weakness**, not bounce trigger — price continues drift -16bp/4-12h. funding sign-flip categorical transform class graveyard (no Tier 4 retire — paradigm 22 R-5 seed active + paradigm 79 variants). Wall-clock 15.3s foreground. HALT confirmed (R-2 미진행). | `funding_rate_sign_flip_event_alt_long_4h/r1/` |

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

## Paradigm 94 — cross_asset_volume_concentration_alt_long_1d (R-1 mint rerun, 2026-05-19)

ad-hoc R-1 re-execution on Mint full 2.4yr joblib cache (2024-01-02 ~ 2026-05-12, 845 days)
following Mint hostname tunnel resolution. Prior local R-1 (2026-05-18, 72-day intersection)
verdict was BROAD_FALSIFIED_FEE_FLOOR; mirror n=4 sparse PASS was inconclusive.

**Verdict**: BROAD_FALSIFIED_DIRECTION_INVERTED

- Focus (share_z <= -1.5 LONG): n=845 gross +37.18bp sigex +2.64 perm_p 0.003 BUT
  ci_lower -4.60bp (3-gate 2/3) + Concentration FAIL (4/10 quarters, 0/13 syms ci_pos).
- Mirror (share_z >= +1.5 LONG): n=702 gross +96.97bp sigex **+6.86** perm_p 0.000
  ci_lower **+59.77bp** (3-gate 4/4) + Concentration marginal (7/10 quarters, 3/13 syms
  ci_pos = 0.231 < 0.30 sym threshold).
- Fund (BTC abs vol_usd z): focus FAIL (sigex +0.41), mirror PASS (sigex +3.86). Cross-proxy
  jaccard 0.084 = non-redundant.

**Implication**: hypothesis direction inverted. BTC volume share HIGH (not LOW)
is the alt LONG +1d signal carrier. Per Lesson #8 + paradigm 70 mirror antipattern,
mirror direction is **not** auto-promoted — separate R-1 dispatch required for
cross_asset_volume_share_high_alt_long_1d (proposed name).

**Artifacts**: backend/runs/research_track/cross_asset_volume_concentration_alt_long_1d/r1_mint_rerun/
{r1_spec.md, r1_metrics.json, r1_summary.md, r1_script.py}

---

## Cross-reference

- `.claude/plans/research_track_master.md` — 본 트랙 마스터 plan
- `.claude/plans/paper_pool_master.md` — 현 paper 풀 baseline (gate 비교 기준)
- `backend/scripts/eval_research_gate.py` — gate 자동 평가 스크립트
- `backend/runs/paper_spec_backtest.csv` — 현 풀 24-spec trade-sim baseline
