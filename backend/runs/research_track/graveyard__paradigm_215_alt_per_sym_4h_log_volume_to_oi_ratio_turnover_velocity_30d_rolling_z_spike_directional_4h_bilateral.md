# paradigm 215 GRAVEYARD — R-1 CONCENTRATED_R1_PASS + Pattern P3 alpha decay

**Slug**: `alt_per_sym_4h_log_volume_to_oi_ratio_turnover_velocity_30d_rolling_z_spike_directional_4h_bilateral`
**Counter**: 215
**Phase**: R-1 (R-2 NOT dispatched — STRICT halt per Lesson #16 + concentration severe FAIL)
**Halt timestamp**: 2026-05-22 19:24 KST
**Verdict**: `CONCENTRATED_R1_PASS_2_OF_20_SYMS_CI_POS_PLUS_2026_ALPHA_DECAY`

## Hypothesis (spec)

Paradigm 214 R-0 HALT (Lesson #40 STRUCTURAL THRESHOLD INFEASIBILITY) reformulation per Lesson #40 prescription Option A:

- statistic: per-sym 4h `log(volume + 1e-9) / log(30d-mean-OI + 1e-9)` → 30d rolling z-score
- triggers: |z| >= 2 bilateral spike, disjoint trigger sets
  - A_focus:  z >= +2 AND bar UP   × LONG  (HIGH log-turnover continuation)
  - A_mirror: z >= +2 AND bar UP   × SHORT (mirror direction same trigger)
  - B_same:   z <= -2 AND bar DOWN × SHORT (LOW log-turnover continuation, symmetric ±2 feasibility restored)
  - B_mirror: z <= -2 AND bar DOWN × LONG  (Lesson #42 19th dogfood)
- hold: 4h primary + 8h + 12h + 24h sweep
- universe: 20 alts (paradigm 198 cohort)
- substrate: 4h cache 819d + OI 5min cache 541-801d aggregated to 4h mean

## Lesson #40 prescription verification (1st 처방 사례) — PASS

Log-transform restored symmetric ±2 z-bilateral feasibility.

| sym | z.min | z.p01 | z.p99 | z.max | n(z≤-2) | n(z≥+2) |
|---|---|---|---|---|---|---|
| BTC | -3.10 | (~-2.4) | (~3.0) | +3.77 | **59** | 70 |
| ETH | -3.13 | (~-2.5) | (~3.0) | +4.0  | **113** | 111 |
| SOL | -2.77 | (~-2.3) | (~2.8) | +3.5  | **77** | 133 |
| BNB | -3.21 | (~-2.5) | (~3.1) | +4.2  | **92** | 156 |
| XRP | -3.12 | (~-2.4) | (~3.1) | +4.3  | **80** | 154 |
| DOGE | -3.24 | (~-2.5) | (~3.0) | +4.1 | **55** | 164 |
| ADA | -2.59 | (~-2.3) | (~3.0) | +3.8  | **62** | 148 |
| AVAX | -2.99 | (~-2.4) | (~3.0) | +3.7 | **86** | 141 |
| LINK | -2.83 | (~-2.4) | (~3.0) | +4.1 | **56** | 162 |
| LTC | -3.04 | (~-2.4) | (~3.0) | +4.1  | **75** | 169 |
| ... 10 more syms | similar | similar | similar | similar | similar | similar |

**Aggregate**:
- 20/20 syms produce non-zero z ≤ -2 triggers (vs paradigm 214: 0/20)
- Universe total z ≤ -2: **1,420** (vs paradigm 214: **0**)
- Universe total z ≥ +2: **3,050** (vs paradigm 214: ~3,986)
- **Lesson #40 prescription compliance: log-transform 1st 처방 사례 CONFIRMED FUNCTIONAL** — symmetric ±2 feasibility fully restored, B-side cells now evaluable

## R-1 results — primary hold 4h

| Cell | n_trig | n_syms | mean_gross_bp | mean_net_bp | sigex | ci_lower_bp | ci_upper_bp | perm_p | verdict |
|---|---|---|---|---|---|---|---|---|---|
| A_focus HIGH UP LONG  | 1441 | 20 | **+47.77** | +39.77 | **+6.16** | +23.13 | +56.89 | 0.000 | **THREE_GATE_PASS** |
| A_mirror HIGH UP SHORT | 1441 | 20 | -47.77 | -55.77 | -4.89 | -72.89 | -39.13 | 0.000 | FAIL |
| B_same LOW DOWN SHORT  | 671  | 20 | +7.86  | -0.14  | +0.92 | -8.29  | +8.36  | 0.821 | FAIL fee-floor |
| B_mirror LOW DOWN LONG | 671  | 20 | -7.86  | -15.86 | -2.45 | -24.36 | -7.71  | 0.012 | FAIL |

## Hold sweep — A_focus three-gate sigex by hold

| Hold | sigex | ci_lower_bp | ci_upper_bp | perm_p | verdict |
|---|---|---|---|---|---|
| 4h  | +6.16 | +23.13 | +56.89 | 0.000 | THREE_GATE_PASS |
| 8h  | +4.50 | +18.11 | +67.10 | 0.000 | THREE_GATE_PASS |
| 12h | +3.92 | +14.33 | +72.02 | 0.000 | THREE_GATE_PASS |
| 24h | +2.33 | -11.10 | +76.41 | 0.016 | FAIL_ci_lower<=0 |

Sigex monotonically decays with hold horizon — alpha is short-horizon momentum (4h-12h sweet spot). 24h FAIL by CI lower (still positive sigex+perm).

## Sensitivity at |z| >= 1.5 (primary 4h)

- A_focus: n=3209 sigex=+6.81 ci=[+12.85, +33.65]bp perm_p=0.000 **THREE_GATE_PASS** (broader trigger preserves sigex, narrower mean)
- B_same: n=2893 sigex=+0.65 ci=[-7.30, +1.44]bp perm_p=0.738 FAIL

A_focus signal robust across z thresholds.

## Lesson #16 Concentration Gate — CRITICAL FAIL

### Per-symbol bootstrap CI (A_focus 4h)

| sym | n | mean_bp | ci_lower_bp | ci_pos |
|---|---|---|---|---|
| **DOT**  | 71 | +92.84 | **+26.18** | **YES** |
| **NEAR** | 68 | +91.21 | **+3.48** | **YES** |
| WIF | 72 | +89.63 | -15.39 | NO |
| ADA | 71 | +76.87 | -9.00 | NO |
| FIL | 68 | +62.89 | -70.11 | NO |
| ETH | 40 | +51.59 | -15.60 | NO |
| SOL | 57 | +50.00 | -25.49 | NO |
| XRP | 84 | +48.44 | -15.68 | NO |
| BCH | 89 | +44.47 | -2.10 | NO |
| DOGE | 85 | +43.68 | -19.28 | NO |
| ETC | 87 | +38.28 | -16.50 | NO |
| LINK | 81 | +35.28 | -20.59 | NO |
| UNI | 83 | +29.06 | -38.84 | NO |
| LTC | 87 | +23.82 | -21.69 | NO |
| BTC | 25 | +18.68 | -24.14 | NO |
| BNB | 71 | +14.18 | -24.85 | NO |
| WLD | 79 | +8.19 | -88.61 | NO |
| PYTH | 90 | +5.16 | -67.16 | NO |
| AVAX | 66 | +0.73 | -51.98 | NO |
| JUP | 67 | -24.30 | -110.67 | NO |

**Verdict: 2/20 syms ci_lower > 0 (10%) ≪ 30% threshold → CONCENTRATION FAIL SEVERE**

The +39.77bp mean net is driven by 2 outliers (DOT + NEAR ~+90bp). 18 of 20 syms have CI crossing zero, signaling sigex is concentration artifact even with 1,441 triggers.

### Per-quarter t (A_focus 4h)

| Quarter | n | t | mean_bp | pos_t |
|---|---|---|---|---|
| 2024Q2 | 118 | +2.29 | +66.10 | YES |
| 2024Q3 | 180 | -1.62 | -30.97 | NO  |
| 2024Q4 | 246 | +0.83 | +17.09 | YES |
| 2025Q1 | 195 | **+4.14** | +118.61 | YES |
| 2025Q2 | 187 | +2.21 | +48.17 | YES |
| 2025Q3 | 170 | +0.29 | +7.18  | YES |
| 2025Q4 | 170 | **+3.41** | +112.06 | YES |
| 2026Q1 | 119 | +0.33 | +8.78  | YES |
| 2026Q2 | 56  | -1.57 | -45.86 | NO  |

**Quarter pos_t ratio: 7/9 = 0.78 (PASS Lesson #16 quarter threshold ≥ 0.5)**

But cross-cell combination: per-quarter PASS + per-symbol FAIL → **per-symbol concentration is the dominant failure mode**.

## Item 6 Alpha Decay 5-pattern audit (era stratify)

### A_focus_HIGH_UP_LONG era stratify

| Era | n | t | mean_bp | pos_t |
|---|---|---|---|---|
| 2024 | 544 | +0.91 | +11.82  | YES (weak) |
| 2025 | 722 | **+5.31** | **+72.59** | YES (PEAK) |
| 2026 | 175 | -0.43 | -8.70   | NO  |

**Pattern P3 inverted-U classification**:
- 2024 weak signal (t<2 below confirmation)
- 2025 PEAK alpha (t=+5.3, mean +72.6bp)
- 2026 alpha DECAY (t=-0.43, mean -8.7bp, mid-quarter point)

**NOT Pattern P1 monotonic decay** (paradigm 87/136/202/210/211/212): paradigm 215 shows BUILD → PEAK → DECAY (inverted-U), not LINEAR DECAY.

**Pattern P1 6 consecutive streak status: NOT incremented to 7** — paradigm 215 era pattern is P3-class (inverted-U), distinct from P1 monotonic decay. P1 streak remains at 6 consecutive. The [[feedback-broad-cross-class-alpha-decay-hypothesis]] formal universal promotion criterion (7 consecutive P1) is **NOT triggered**.

However, 2026 decay observed independently — **cross-class 2026 alpha decay informational learning** evidence accumulates (paradigm 87 delisting + 136/202 RV intraday + paradigm 215 log-turnover all show 2026 underperformance). This is candidate Pattern P5 "era-2026-universal-decay" sub-pattern, distinct from P1 monotonic. **Lesson candidate**: "2026 era universally lower alpha across structurally different paradigms" — requires 1-2 more dogfoods to elevate.

### Other cells

| Cell | 2024 | 2025 | 2026 |
|---|---|---|---|
| A_mirror_HIGH_UP_SHORT | -2.15 / -27.8bp | -6.48 / -88.6bp | -0.36 / -7.3bp | All negative (expected mirror) |
| B_same_LOW_DOWN_SHORT  | -1.25 / -10.0bp | +0.11 / +0.6bp | +1.97 / +18.0bp | Inverted P2 pattern (build) |
| B_mirror_LOW_DOWN_LONG | -0.74 / -6.0bp  | -2.73 / -16.6bp | -3.72 / -34.0bp | Linear decay (mirror to A_focus build) |

## Lesson #42 19th dogfood — B_mirror cell

B_mirror (LOW turnover z- × bar DOWN × LONG reversal) verdict: **NEGATIVE**
- n=671 sigex=-2.45 ci=[-24.36, -7.71]bp perm_p=0.012 (significant in WRONG direction — bar DOWN continuation, not reversal)
- LOW log-turnover bars showing DOWN direction CONTINUE downward; LONG reversal trade is anti-alpha
- Chain 3-tier classification: **NEGATIVE** (B_mirror produces real anti-alpha signal, not noise/null)
- Lesson #42 dogfood count: 18 confirmed + paradigm 215 19th NEGATIVE confirmed

## Item 7 Cross-set |A| vs |B| asymmetry — 2.15x

- |A| (z≥+2 AND bar UP): 1441
- |B| (z≤-2 AND bar DOWN): 671
- A/B ratio: **2.15x**
- z>=+2 total: 3,048 / z<=-2 total: 1,405 (raw z-distribution skew ratio 2.17x)
- AND-filter retention: A side 47.3%, B side 47.8% (nearly identical)
- Conclusion: **asymmetry inherited from log-z distribution right-skew, NOT from price-direction joint filter**

Comparison to predecessors:
- paradigm 206: 1.83x
- paradigm 207: 2.79x
- paradigm 210: 3.36x
- paradigm 211: 0.86x
- paradigm 212: 1.143x
- **paradigm 215: 2.15x** (mid-range, no anomaly)

## Item 8 Temporal Independence (paradigm 208 amendment) — A_focus continuation only

A_focus mean +39.77bp net at 4h hold reflects momentum continuation (z>=+2 + bar UP → LONG = ride the trend after spike). Per-quarter spread shows volatility (2024Q3 -31bp single down quarter, 2026Q2 -46bp small-n outlier) but 7/9 quarters positive — temporal stationarity in mean. However per-symbol concentration (2/20) dominates verdict.

## Item 9 Life-changing 4-dim STRUCTURAL prescreen (2nd operational, paradigm 213 1st)

Estimate (A_focus 4h):
- **trades/yr**: 1441 events / 2.15yr ≈ **670/yr** ≫ 12 PASS
- **per-trade edge**: +39.77bp net = +0.40% PASS marginal (well above +0.2% fee floor) but BELOW +2% life-changing threshold
- **capital util**: 4h hold × 20 syms × 670 events/yr → ~ 670 × 4h / (8760h × 20) = **1.5%** EXTREME FAIL ≪ 30%
- **sharpe**: t_obs=+4.52 on n=1441, daily sharpe ≈ 4.52/sqrt(2.15) ≈ 3.09 PASS marginal

**Life-changing 4-dim verdict: FAIL on capital util (1.5% ≪ 30%) and edge (0.40% < 2%)**.

Even if Concentration Gate were marginal-PASS, this paradigm fails life-changing 4-dim STRUCTURAL prescreen on TWO of FOUR dimensions. Per [[feedback-narrow-scope-life-changing-fail-verdict]]: NARROW_SCOPE_LIFE_CHANGING_FAIL category applicable if Lesson #20 4-cond ALL PASS would also fail this.

Item 9 STRUCTURAL prescreen 2nd operational dogfood **CONFIRMS** that per-trade edge + capital util cross-filter blocks even three-gate-PASS sigex>+6 paradigms.

## Lesson #69 9-item template results

| Item | Description | Verdict |
|---|---|---|
| 1 | INDEX.json + dir grep STRICT (turnover/log_volume/volume_to_oi/active_rotation/passive_stake/rotational_flow) | **PASS** — 0 matches (paradigm 214 R-0 HALT predecessor only, distinct via log-transform) |
| 2 | Substrate-shape + market maturity ≥2yr | **PASS** — 20 syms × 2.15yr universe mean, 4h cache 819d + OI 541-801d |
| 3 | Sample density (paradigm 214 SAMPLE_INSUFFICIENT B-side avoid) | **PASS** — 1,420 z≤-2 + 3,050 z≥+2, per-cell all ≥ 30 |
| 4 | DNA 4-dim 5/5 strict (vs paradigm 214 log distinct, vs 73/79/104/127-128/196 + funding 9 sub-class) | **PASS** — fresh log-turnover composite class |
| 5 | Family-proxy (log-turnover velocity composite class) | NEW class |
| 6 | Alpha decay 5-pattern audit 9th operational dogfood | **Pattern P3 inverted-U** (BUILD-PEAK-DECAY, NOT P1 monotonic). P1 streak NOT incremented (remains 6) |
| 7 | SNT structural integrity (|A|/|B| asymmetric) | A/B = 2.15x (mid-range vs 0.86-3.36x precedents) |
| 8 | Concentration + Temporal Independence (A_focus continuation only sym_ci_pos) | **FAIL** — 2/20 syms ci_pos (10% ≪ 30%) |
| 9 | Life-changing 4-dim STRUCTURAL prescreen (2nd operational) | **FAIL** — capital util 1.5% + edge 0.40% < 2% |

## Verdict chain

1. **Lesson #40 prescription verification**: PASS — log-transform restored symmetric ±2 feasibility (1st 처방 사례 CONFIRMED FUNCTIONAL)
2. **R-1 three-gate**: A_focus 4h/8h/12h PASS, all other cells FAIL
3. **Lesson #16 Concentration Gate**: FAIL — only 2/20 syms ci_lower>0
4. **Lesson #39 sub-class verification**: NOT triggered (A_focus and A_mirror differ by direction only, expected; A_focus vs unconditional LONG baseline shows +48bp differential)
5. **Item 6 alpha decay**: Pattern P3 inverted-U with 2026 negative — alpha quality concern even before concentration FAIL
6. **Item 9 life-changing 4-dim STRUCTURAL prescreen**: FAIL on 2 of 4 dimensions (capital util 1.5%, edge 0.40% < 2%)

**Final verdict**: `CONCENTRATED_R1_PASS_2_OF_20_SYMS_CI_POS_PLUS_2026_ALPHA_DECAY_PLUS_LIFE_CHANGING_4DIM_FAIL`

R-2 NOT promoted per Lesson #16 confirmed protocol (concentration severe FAIL) AND Item 9 life-changing 4-dim STRUCTURAL prescreen FAIL. R-1 STRICT halt mandated.

## Lesson status updates

- **Lesson #40 (CONFIRMED FORMAL 3rd dogfood)**: 1st prescription dogfood executed — log-transform on volume/OI multiplicative composite RESTORED feasibility. **Lesson #40 prescription compliance confirmed functional**. Prescription path documented as working.
- **Lesson #16 (CONFIRMED)**: 16th+ dogfood — per-symbol concentration overrides per-quarter homogeneity. Per-quarter 7/9 pos_t was misleading.
- **Lesson #42 (CONFIRMED)**: 19th dogfood NEGATIVE chain entry (B_mirror cell). Cumulative count: 18 confirmed + 1 NEGATIVE.
- **Lesson #39 (CONFIRMED 자격)**: Not triggered (A_focus ≠ A_mirror exact-symmetric vs baseline).
- **Item 9 STRUCTURAL prescreen (2nd operational dogfood)**: CONFIRMED FUNCTIONAL — blocks three-gate-PASS sigex>+6 paradigms on capital util + edge dimensions.
- **Pattern P1 streak**: remains at 6 consecutive (paradigm 87/136/202/210/211/212). Paradigm 215 is Pattern P3 (inverted-U), NOT P1. **[[feedback-broad-cross-class-alpha-decay-hypothesis]] formal universal NOT promoted** (P1 streak intact, not 7).
- **2026 era-universal decay candidate observation**: 4th independent paradigm class shows 2026 underperformance vs prior eras (87 delisting / 136 RV intraday / 202 RV cross-family / 215 log-turnover). Candidate sub-lesson "2026 era cross-class headwind" — requires 1-2 more independent class dogfoods to elevate from observation to lesson candidate.

## Memory policy compliance

- [[feedback-persistence-over-efficiency]]: R-1 graveyard normal failure mode, dispatch continues
- [[feedback-paradigm-campaign-continuous-parallel]]: paradigm 216 dispatch ready, no pause
- [[feedback-direct-recommendation]]: paradigm 216 candidate directly recommended below
- [[feedback-no-freemium-trial]]: zero backfill, joblib cache only
- [[feedback-life-changing-strategy-criterion]]: Item 9 STRUCTURAL prescreen 2nd operational dogfood confirmed effective
- [[feedback-narrow-scope-life-changing-fail-verdict]]: Item 9 4-dim FAIL → graveyard verdict aligned

## Artifacts

- `backend/scripts/research/paradigm_215_log_turnover_velocity_r1.py` — R-1 PoC script (py_compile PASS)
- `backend/runs/research_track/paradigm_215_alt_per_sym_4h_log_volume_to_oi_ratio_turnover_velocity_30d_rolling_z_spike_directional_4h_bilateral/r1__metrics.json` — full metrics with all 4 holds × 4 cells SNT + sensitivity + era + concentration
- this file — formal graveyard report

## paradigm 216 next-action recommendation

**Direct recommendation** (per [[feedback-direct-recommendation]] + [[feedback-paradigm-campaign-continuous-parallel]] + [[feedback-persistence-over-efficiency]]):

Paradigm 215 demonstrates log-turnover concentration in 2 syms (DOT + NEAR) + 2025 peak alpha + 2026 decay. The mechanism (volume burst relative to OI = active rotation signal) is **partially valid for specific symbols** but does not survive 20-sym broad-scope validation.

**Paradigm 216 candidate**: shift away from log-turnover composite axis entirely — **next direct paradigm 216 hypothesis** should be a structurally distinct DNA not in the "z-score on rolling normalized aggregate" family (which now has cumulative paradigm 109 + 110 + 214 + 215 evidence of either structural infeasibility or concentration FAIL across 4 dogfoods).

Recommended next class: **regime-conditional event paradigm** (not pure z-score axis), e.g., **funding 8h boundary × OI direction divergence with explicit regime stratify (BTC vol p80+ filter)** — combines paradigm 22 (funding R-5 success) framework + paradigm 69 (vol regime R-5 success) framework. Family-distinct from any single z-score statistic class.

Alternative: continue paradigm 216 in a NEW substrate axis (e.g., on-chain derived flow proxies, top-trader L/S ratio dynamics not yet exploited) — but per [[feedback-no-freemium-trial]] only Binance-native sources allowed.

## Pattern P1 streak status — UNCHANGED at 6

paradigm 215 Pattern P3 inverted-U does NOT increment P1 streak. P1 streak remains at 6 consecutive (paradigm 87/136/202/210/211/212). Next P1-class candidate evaluation pending paradigm 216 result.
