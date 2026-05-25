# Graveyard — paradigm 211 `alt_per_sym_realized_vol_term_structure_slope_30d_vs_7d_ratio_z_spike_directional_4h_bilateral`

**Verdict**: `PRIMARY_FALSIFIED_PLUS_PATTERN_P1_MONOTONIC_DECAY_5TH_INSTANCE_LESSON_69_ITEM_6_7TH_DOGFOOD`
**Phase**: R-1 (R-2 blocked — primary cell 0/4 PASS at 4h, single off-primary PASS at 24h = pure temporal artifact)
**Executed at KST**: 2026-05-22 18:42
**Host**: hcp_local (WSL2)
**Counter**: 210 → 211 (post-paradigm-203 MEMORIAL agent-mode switch)

---

## Hypothesis

Per-symbol realized vol **term structure slope** = log(30d vol / 7d vol), 90d rolling z-score, |z|≥2 spike trigger × bar direction signed × 4-quadrant SNT × 4h primary + 8h/12h/24h sweep × 21-sym universe (paradigm 198 cohort) × 2.25yr.

- **Statistic class**: log(rv30/rv7), 90d z-score (vol horizon ratio, **first-use**)
- **Sign source**: ratio internal (z>0 = recent contraction, z<0 = recent expansion)
- **Cells (disjoint trigger sets, Item 7)**:
  - A focus: z≥+2 × bar UP × LONG continuation
  - A mirror: z≥+2 × bar UP × SHORT reversal
  - B same: z≤-2 × bar DOWN × SHORT continuation (disjoint from A)
  - B mirror: z≤-2 × bar DOWN × LONG reversal (Lesson #42 17th dogfood)

---

## Lesson #69 8-item template

| Item | Reference | Verdict | Detail |
|---|---|---|---|
| 1 | Lesson #61 INDEX.json + filesystem slug grep | **PASS** | INDEX hits 0; FS hits 3 (paradigm 164 bvol IV / paradigm 169 perp swap basis / funding term structure 8h_vs_3d) — all DIFFERENT statistic class (implied vol / basis carry / funding cycle vs realized vol ratio from klines). 5/6 DNA distinct confirmed |
| 2 | Lesson #28 substrate-shape + market maturity | **PASS** | 21 syms × 4920 bars × 2.25yr (2024-02-01..2026-04-30). substrate_maturity ≥ 2yr, market maturity decay risk LOW ex ante (but actual alpha decay observed post-hoc) |
| 3 | Lesson #11 sample density | **PASS** | trigger total z≥+2 = 2654 / z≤-2 = 3107 / 88,200 candidate pool. Per-cell n=1337-1555, per-quarter n=12-402 (mostly >30) |
| 4 | Lesson #62 DNA 4-dim 5/5 strict | **PASS** | statistic NEW (log(rv30/rv7) z-score), universe established (paradigm 198), entry sparse-event class, mechanism vol horizon inversion (NEW), hold sweep |
| 5 | Lesson #56 family-proxy | **PASS** | vol term structure slope = first-use axis (paradigm 86 streak boundary / 136 RV intraday / 195/196 cross-sym vol / 204 Hurst persistence all different statistic class) |
| 6 | alpha decay 5-pattern audit (paradigm 210 6th dogfood) | **FAIL — Pattern P1 monotonic decay 5th consecutive instance** | B_mirror 24h aggregate PASS is pure 2024 alpha; 2024 t=+10.04 / 2025 t=-3.59 / 2026 t=-5.26. Per-sym ci_pos: 2024 = 15/19 (79%) → 2025+2026 = **0/21 (0%)**. Complete sign inversion + alpha annihilation |
| 7 | SNT structural integrity cross-set asymmetric | **PARTIAL FAIL — exact tautology** | A_focus/A_mirror exact pair n=1338 each (sum = -16bp = -2×fee). B_same/B_mirror exact pair n=1555 each (B_same 24h 2024 t=-10.71 / B_mirror 24h 2024 t=+10.04 = pure mirror identity). asymmetry_ratio A/B = 0.86 (cell A trigger set smaller). Mirror pair tautology = **Lesson #39 sub-class A signature** |
| 8 | Concentration + Temporal Independence (A_focus continuation primary 4h) | **FAIL** | A_focus 4h: n=1338, sigex +0.64, three-gate FAIL. sym_ci_pos_ratio 0/21 = 0.0. quarter_pos_t_ratio 3/8 = 0.375 < 0.5. temporal_cluster_ratio = 1.0 (4h hold ≥ 4h spacing tautologically). B_mirror 24h aggregate PASS: per-sym all-era ci_pos 4/21 = 19% < 30% (FAIL) |

---

## R-1 Key numbers (4-quadrant × hold sweep)

| Hold | Cell | n | mean_bp | obs_t | sigex | ci_lower_bp | perm_p_1s | 3-gate |
|---|---|---:|---:|---:|---:|---:|---:|:--:|
| **4h** | A_focus (z+ UP LONG) | 1338 | -4.06 | -0.94 | **+0.64** | -12.20 | 0.268 | FAIL |
| 4h | A_mirror (z+ UP SHORT) | 1338 | -11.94 | -2.77 | -1.19 | -20.36 | 0.130 | FAIL |
| 4h | B_same (z- DOWN SHORT) | 1555 | -20.68 | -3.04 | -1.28 | -34.62 | 0.107 | FAIL |
| 4h | B_mirror (z- DOWN LONG) | 1555 | +4.68 | +0.69 | **+2.44** | -8.38 | 0.009 | FAIL (ci_lo<0) |
| 8h | A_focus | 1338 | -11.08 | -1.69 | -0.47 | -23.58 | 0.689 | FAIL |
| 8h | B_mirror | 1555 | +2.98 | +0.32 | +1.60 | -15.59 | 0.051 | FAIL |
| 12h | A_focus | 1338 | -16.79 | -2.04 | -1.00 | -33.08 | 0.831 | FAIL |
| 12h | B_mirror | 1555 | +11.70 | +1.04 | +2.21 | -10.51 | 0.018 | FAIL (ci_lo<0) |
| 24h | A_focus | 1337 | -4.77 | -0.39 | +0.46 | -27.26 | 0.324 | FAIL |
| 24h | A_mirror | 1337 | -11.23 | -0.92 | -0.07 | -34.10 | 0.480 | FAIL |
| 24h | B_same (z- DOWN SHORT) | 1555 | **-50.99** | -3.25 | -2.27 | -81.30 | 0.008 | FAIL (anti) |
| **24h** | **B_mirror (z- DOWN LONG)** | **1555** | **+34.99** | **+2.23** | **+3.21** | **+4.00** | **0.000** | **PASS (off-primary, artifact)** |

**Primary 4h cell 0/4 PASS**. Single 24h B_mirror PASS = **temporal artifact** (see Item 6).

---

## Alpha decay 5-pattern taxonomy assignment — Pattern P1 monotonic decay

B_mirror 24h era stratify:
- **2024**: n=656, mean_bp=+239.04, t=**+10.04**
- **2025**: n=620, mean_bp=-84.10, t=**-3.59**
- **2026**: n=279, mean_bp=-180.14, t=**-5.26**

Quarter breakdown:
- 2024Q3: n=250, +255bp, t=+8.29
- 2024Q4: n=402, +229bp, t=+6.81
- 2025Q1: n=57, -258bp, t=-2.29
- 2025Q2: n=76, -193bp, t=-3.26
- 2025Q3: n=120, -184bp, t=-4.06
- 2025Q4: n=367, -2bp, t=-0.07
- 2026Q1: n=275, -173bp, t=-5.02

Per-sym ci_pos:
- All-era: 4/21 = 19%
- 2024-only: **15/19 = 79%** (broad alpha)
- 2025+2026-only: **0/21 = 0%** (complete annihilation + sign inversion)

**Classification**: Pattern P1 monotonic decay, identical to paradigm 87 binance_delisting / paradigm 136 RV intraday / paradigm 202 RV intraday cross-family / paradigm 210. **5th consecutive Pattern P1 instance** = vol-axis 알파 decay 정형화 입증.

**Lesson #69 Item 6 7th operational dogfood**: alpha decay 5-pattern audit prescreen 의무 reinforce.

---

## Lesson #39 sub-class A signature confirmed

A pair (z+, bar UP): A_focus + A_mirror, n=1338 each, sums = -8.00bp/trade × 2 = -16bp/pair = exact 2×fee, perfect mirror.
B pair (z-, bar DOWN): B_same + B_mirror, n=1555 each:
- 4h: B_same -20.68bp + B_mirror +4.68bp = -16.00bp (exact -2×fee)
- 24h: B_same -50.99bp + B_mirror +34.99bp = -16.00bp (exact -2×fee)

**Sub-class A tautology** (Lesson #39 formal universal) — log(rv30/rv7) z-spike + bar direction adds **zero directional information** above unconditional bar continuation/reversal at the chosen hold. Mirror pair sums to -2×fee mechanically.

The 24h B_mirror PASS is not signal-from-trigger; it is **2024 bar-DOWN-reversal regime alpha (~+240bp)** that the trigger merely re-shapes per-period. The trigger does not select better trades than unconditional bar-down LONG in 2024.

---

## Lesson #42 17th dogfood — B_mirror cell verdict

paradigm 117/158/162/179/193/194/195/196/197/198/204/205/206/207/208/210 chain → paradigm 211 = **17th expected event**.

- 4h B_mirror: FAIL (sigex +2.44 / ci_lo<0)
- 8h B_mirror: FAIL (sigex +1.60)
- 12h B_mirror: FAIL (sigex +2.21 / ci_lo<0)
- **24h B_mirror: AGGREGATE 3-gate PASS** but era stratify = Pattern P1 monotonic decay artifact + Concentration FAIL (19% ci_pos) + Lesson #39 sub-class A tautology (-16bp mirror pair sum)

**Verdict**: B_mirror 17th dogfood = **CONFIRMED — surface PASS, artifact at decomposition**. Lesson #42 chain extends but `PASS_AS_ARTIFACT` annotation needed.

---

## Item 7 cross-set asymmetric magnitude verdict

paradigm 206 1.83x / paradigm 207 2.79x / paradigm 210 3.36x reference.

paradigm 211: |A z+ trigger set| / |B z- trigger set| = 2676/3110 = **0.86x** (cell A smaller, near-symmetric).

asymmetry_ratio 0.86 vs 3.36 (paradigm 210) → **paradigm 211 trigger set near-symmetric** = vol horizon ratio z-score 분포 quasi-symmetric (log transform 결과 양방향 비슷한 occurrence). 정보량 측면 differential 거의 없음 — cell A/B 둘 다 broad-uniform-negative at primary 4h.

---

## Lesson #67/#68/#70 verification

- **Lesson #67 ESCAPE (CONFIRMED)**: per-sym idiosyncratic vol term structure, cross-asset broadcast 부재. ✓
- **Lesson #68 ESCAPE (CONFIRMED)**: continuous rolling window, session-boundary anchor 부재. ✓
- **Lesson #70 ESCAPE (CONFIRMED)**: NEW vol term structure slope class (paradigm 69 R-5 LIVE = BTC-anchored cross-asset filter, paradigm 211 = per-sym horizon ratio). ✓

3/3 ESCAPE PASS — paradigm 211 가설 자체는 fresh, family-distinct strict 5/5 PASS. 실패는 **mechanism 부재 + 2024 alpha decay**.

---

## Final verdict

**PRIMARY_FALSIFIED**:
- Primary 4h cell 0/4 three-gate PASS
- A_focus continuation primary 4h: sigex +0.64 / ci_lo -12.20 / per-sym ci_pos 0/21 / quarter_pos_t 3/8 / per-quarter inconsistent

**Off-primary B_mirror 24h aggregate PASS = ARTIFACT**:
- Era stratify: 2024 t=+10.04 → 2026 t=-5.26 (Pattern P1 monotonic decay)
- Per-sym ci_pos all-era: 4/21 (19%) < 30% Concentration Gate FAIL
- Per-sym ci_pos 2025+2026: 0/21 (0%) — complete annihilation
- Lesson #39 sub-class A tautology: B_same + B_mirror sum = -16bp = -2×fee mechanically

**Decay rationale (post-hoc)**: vol horizon ratio z-spike at 30d/7d resolution captures multi-day vol regime transitions. 2024 crypto market had distinct bar-down × short-term-vol-expansion (z≤-2) → 24h LONG reversal regime (post-capitulation snapback). 2025+ market matured + leverage discipline = same trigger produces continuation not reversal. **Mechanism alpha is regime-specific, not structural** — substrate_maturity threshold ≥ 2yr did NOT prevent 2024-era-only alpha (Item 2 prescreen needed amendment to detect intra-window decay).

---

## State machine update

- counter: 210 → 211 (graveyard)
- Tier 4 family retires: unchanged (vol term structure slope not formally retired — single instance, but reinforced advisory caution for vol-axis multi-day-horizon paradigms)
- R-5 LIVE: unchanged
- Lesson dogfoods:
  - Lesson #11 PASS (sample density)
  - Lesson #19 PASS (4-quadrant SNT)
  - Lesson #28 amendment PASS but **needs intra-window decay sub-check** (substrate_maturity threshold ≥ 2yr ≠ within-window alpha persistence)
  - Lesson #39 sub-class A CONFIRMED (mirror pair -16bp tautology, 4th-class dogfood)
  - Lesson #42 17th instance (B_mirror artifact PASS)
  - Lesson #56 PASS (no proxy)
  - Lesson #61 PASS (slug grep)
  - Lesson #62 PASS (DNA 5/5)
  - Lesson #67/#68/#70 ESCAPE all PASS
  - **Lesson #69 Item 6 7th operational dogfood — Pattern P1 monotonic decay 5th consecutive**

---

## NEW Lesson candidate strengthening

**Lesson candidate market maturity decay** (paradigm 210 1st → paradigm 211 2nd dogfood):
- substrate_maturity ≥ 2yr threshold (Item 2 amendment) detects **substrate availability** but NOT **intra-window alpha persistence decay**
- paradigm 210 6th dogfood Pattern P1 + paradigm 211 7th dogfood Pattern P1 = 2 consecutive Pattern P1 in vol-axis multi-day paradigms
- Proposed amendment: Item 6 prescreen should require **rolling 6m window per-cell t-stat consistency check** before aggregate verdict. If aggregate 2.25yr PASS but rolling 6m windows show >50% sign-flip, declare ALPHA_DECAY_ARTIFACT not signal.
- 자격 status: 1 dogfood → 2 dogfoods = CONFIRMED 자격 (1 more needed for formal CONFIRMED)

---

## paradigm 212 next-action recommendation

vol-axis multi-day-horizon paradigms now 2 consecutive Pattern P1 monotonic decay (paradigm 210 + paradigm 211). Direct recommend:

**Direction A (HIGHEST priority)**: Switch paradigm axis class entirely.
  - **paradigm 212 candidate**: cross-asset funding correlation (NOT vol family). Substrate: binance_funding_rate DB (paradigm 170 asset 10 deep syms × 2.25yr). Statistic: funding rate cross-sym correlation matrix dispersion (eigenvalue-1 dominance ratio over rolling 30d). Funding family Tier 4 retired but cross-sym correlation structure axis NOT explored (paradigm 22 R-5 LIVE = per-sym carry; paradigm 73/79/96/97/98/99 retired = per-sym single-signal). Cross-sym correlation structure = NEW axis.
  - 5/5 DNA distinct candidate (cross-sym correlation matrix structure vs all retired single-signal funding paradigms).

**Direction B (defer)**: vol-axis 추가 시도 = paradigm 210 + paradigm 211 = 2 consecutive Pattern P1, vol-axis multi-day-horizon 사실상 소진. Tier 4 advisory caution 강화 권고.

**Direction C (defer)**: per-sym idiosyncratic shape statistic (skewness/kurtosis Lesson #67 ESCAPE class) — paradigm 65/66 skewness graveyard precedent, sub-fee floor 위험.

**Direct recommendation**: **Direction A — cross-sym funding correlation matrix dispersion** (NEW axis, R-5 LIVE paradigm 22 family-adjacent but different statistic class, substrate ready, fresh).

---

응답 생성: 2026-05-22 KST
