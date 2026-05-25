# Graveyard — paradigm 192 `alt_per_sym_30d_hour_of_day_seasonality_z_spike_directional_4h_bilateral`

- **Date**: 2026-05-22 KST
- **Phase reached**: R-1 (R-1 ONLY mode per dispatch directive)
- **Verdict**: `BROAD_FALSIFIED`
- **Wall clock**: ~1 sec
- **Script**: `backend/scripts/research/paradigm192_alt_per_sym_30d_hour_of_day_seasonality_z_spike_directional_4h_bilateral_r1.py`
- **Metrics**: `backend/runs/research_track/alt_per_sym_30d_hour_of_day_seasonality_z_spike_directional_4h_bilateral/r1__metrics.json`

## Hypothesis

For each (sym, UTC_hour ∈ {00,04,08,12,16,20}), compute rolling 30d mean return
at that hour (`mu_hour`, ~30 observations). Compare to sym's overall 30d
rolling distribution (`mu_all`, ~180 obs) via:
  z = (mu_hour − mu_all) / (sigma_all / sqrt(30))

Trigger: z ≥ +2 means the current bar's hour has developed statistically
abnormal **outperformance** vs the sym's recent distribution. Sign-condition
on **current 4h bar direction** (UP/DOWN) gives 4-quadrant bilateral SNT
(continuation vs reversal × bar direction).

## Substrate

- `backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib` × 14 syms × 4920 bars
- 2024-02-01 .. 2026-04-30 (~2.25 yr × 14 syms)
- Zero backfill, full archive-direct compliance
- Helpers: `_perm_utils.fee_aware_perm_test` + `bootstrap_ci`

## R-0 prescreens (all PASS, dispatch justified)

| Lesson | Check | Result |
|---|---|---|
| #11 sample density | per-quadrant n=308/325 (cutoff 30) 10x cushion | PASS |
| #19 SNT mandatory | 4-quadrant in single batch | APPLIED |
| #20 narrow-scope | sparse-strict LC4dim layer ahead of narrow-scope eligibility | APPLIED |
| #21 axis stacking | single derived axis (per-sym × per-hour z-score), NOT stacking | PASS |
| #28 substrate availability | joblib 4h cache verified | PASS |
| #30 data window ratio | 2.25yr = 100% universe full-window | PASS |
| #34 empirical distribution | z_p99 ≈ 1.7-2.2 (parametric expectation 2.33) — slightly fat left tail BUT |z|≥2 reachable | PASS |
| #40 structural threshold feasibility | signed z, |z|≥2 reachable on signed return statistic | PASS |
| #42 prediction | B_mirror cell prepared for 5th dogfood verify | APPLIED |
| #61 slug grep | paradigm 113 `intraday_hour_of_day_anchor_alt_directional_2h` adjacency — distinct trigger class (anchor+|z| vs seasonality-z) | NOTED |
| #62 family-distinct (5/5 strict) | statistic class NEW + universe std + entry sparse 4h + mechanism NEW (time-of-day seasonality) + hold standard | PASS |
| #67/#68/#70 ESCAPE | per-sym×per-hour idiosyncratic + continuous rolling NOT session-anchor + NEW paradigm class | PASS |

## Empirical trigger diagnostics

| metric | value |
|---|---:|
| valid z observations | 66,360 |
| pos trig (z ≥ +2) | 634 (**0.96%** — vs prescreen assumption 5%, **5.2x under**) |
| neg trig (z ≤ −2) | 575 (0.87%) |

Lesson #34 partial dogfood: parametric N(0,1) gives ~2.27% tail at |z|≥2,
empirical only 0.96-0.87%. Per-hour rolling mean estimator is more
conservative than parametric assumption (correlated samples within hour
class). Despite under-shoot, per-cell n=308/325 ≫ 30 cutoff (Lesson #11
sample density PASS substantially).

## R-1 — 4-quadrant SNT (z ≥ +2 trigger, primary hold = 4h)

| Quadrant | n | gross_bp | net_bp | sigex | CI_bp | perm_p_above | 3-gate | concentration |
|---|---:|---:|---:|---:|---|---:|:---:|:---:|
| **A focus** (z+ × UP × LONG) | 308 | **−20.19** | −28.19 | −1.85 | [−50.2, …] | 0.971 | FAIL | 0/14 syms; q_pos 4/9 |
| A mirror (z+ × UP × SHORT) | 308 | **+20.19** | +12.19 | +1.88 | [−9.8, …] | 0.030 | FAIL (sigex<2.0, CI≤0) | 2/14 (14%) |
| **B same-sign** (z+ × DOWN × SHORT) | 325 | **+19.19** | +11.19 | +1.58 | [−15.7, …] | 0.059 | FAIL (sigex<2.0, CI≤0) | 0/14; q_pos 4/10 |
| B mirror (z+ × DOWN × LONG) | 325 | **−19.19** | −27.19 | −1.20 | [−55.7, …] | 0.886 | FAIL | 0/14 |

**Lesson #39 sub-class A perfect-mirror signature**:
- A_focus gross −20.19bp ≡ −A_mirror gross +20.19bp (exact ±)
- B_same gross +19.19bp ≡ −B_mirror gross −19.19bp (exact ±)
- Both A_focus AND B_same gross-direction are inconsistent with continuation
  hypothesis (positive-z hour + UP should LONG, but gross is NEGATIVE; positive-z
  hour + DOWN should SHORT, but gross is also lukewarm +19.19bp ≤ fee floor 16bp
  net after 8bp roundtrip = ~+11.19bp net, sigex 1.58 < 2.0 strict).
- Mirror Concentration: A_mirror 2/14 (14%), B_mirror 0/14 — **NO symbol-cluster
  carve-out → sub-class A (broad-uniform-negative trigger, zero directional info)**
  NOT sub-class B (mechanism-inverted).

**Conclusion**: per-sym per-hour seasonality z-spike trigger carries near-zero
directional information; mirror symmetry is by construction (gross flips sign
exactly when direction flips), and the small gross magnitudes (~20bp) are
overwhelmed by 16bp round-trip fee floor.

## Per-hour contribution (HOLD 4h)

### A_focus (z+ × UP × LONG)

| UTC hour | n | mean_bp | t | pos_t |
|---:|---:|---:|---:|:---:|
| 00 | 102 | −19.36 | −1.55 | ✗ |
| 04 | 14 | −62.09 | −1.27 | ✗ |
| 08 | 31 | −65.96 | −1.45 | ✗ |
| 12 | 55 | **−82.12** | **−2.64** | ✗ |
| 16 | 47 | **+25.57** | +1.44 | ✓ |
| 20 | 59 | −8.11 | −0.24 | ✗ |

Only UTC16h positive, t=+1.44 marginal. UTC12h (US morning) strong negative
t=−2.64 (anti-momentum). No coherent per-hour alpha layer.

### B_same_sign (z+ × DOWN × SHORT)

| UTC hour | n | mean_bp | t | pos_t |
|---:|---:|---:|---:|:---:|
| 00 | 97 | +6.48 | +0.48 | ✓ |
| 04 | 23 | −81.83 | −1.25 | ✗ |
| 08 | 21 | −72.86 | −1.04 | ✗ |
| 12 | 67 | **+44.90** | **+2.00** | ✓ |
| 16 | 58 | +58.76 | +1.02 | ✓ |
| 20 | 59 | +0.06 | 0.00 | ✓ |

UTC12h SHORT continuation +44.90bp t=+2.00 marginal (mirror of A_focus UTC12h
LONG −82.12 — same hour, same trigger, opposite direction → exact symmetric).
**No mechanism, just direction-bet on hours that happened to drift on average**.

## Per-sym contribution (HOLD 4h, A_focus)

0/14 syms ci_pos (LINK/LTC/ETH/BCH show ci_upper<0 = significant negative,
broad-uniform anti-pattern). Mirror A_mirror cherry-picks ETH/LTC ci_pos 2/14
= insufficient for narrow-scope (Lesson #20 4-cond not satisfied: focus FAIL,
isolated cell PASS, BUT Concentration FAIL n_syms<3).

## Per-quarter robustness (A_focus, 9 quarters)

| Quarter | n | mean_bp | t | pos_t |
|---|---:|---:|---:|:---:|
| 2024Q1 | 13 | +83.90 | +0.67 | ✓ |
| 2024Q2 | 30 | −70.34 | −2.06 | ✗ |
| 2024Q3 | 37 | −61.58 | −2.39 | ✗ |
| 2024Q4 | 73 | −53.10 | −3.70 | ✗ |
| 2025Q1 | 46 | −71.48 | −1.62 | ✗ |
| 2025Q2 | 12 | +68.33 | +2.30 | ✓ |
| 2025Q3 | 48 | +7.69 | +0.39 | ✓ |
| 2025Q4 | 30 | +18.97 | +0.86 | ✓ |
| 2026Q1 | 15 | −8.13 | −0.30 | ✗ |

q_pos_t_ratio = 4/9 = 0.44 (< 0.5 Concentration threshold). **2024 entire year
negative, 2025+ marginal positive** = temporal regime instability,
non-stationary seasonality (hour patterns drift over time).

## Hold sweep verdict scan (Lesson #37)

| hold | A_focus | A_mirror | B_same | B_mirror | any PASS? |
|---|:---:|:---:|:---:|:---:|:---:|
| 4h | FAIL | FAIL | FAIL | FAIL | NO |
| 8h | FAIL | FAIL | FAIL | FAIL | NO |
| 12h | FAIL | FAIL | FAIL | FAIL | NO |

**0/12 cells three-gate PASS**. Lesson #37 dogfood: comprehensive sweep
confirms no off-primary cell escape.

## Sparse-strict Life-Changing 4-dim audit (primary 4h)

| Quadrant | trades/yr | edge% | util% | sharpe | 4/4 pass |
|---|---:|---:|---:|---:|:---:|
| A_focus | 137.1 | −0.28% | 0.45% | −1.68 | ✗ |
| A_mirror | 137.1 | +0.12% | 0.45% | +0.73 | ✗ |
| B_same_sign | 144.7 | +0.11% | 0.47% | +0.53 | ✗ |
| B_mirror | 144.7 | −0.27% | 0.47% | −1.28 | ✗ |

**ALL 4 quadrants FAIL** every dimension except trades/yr. Per-trade edge max
+0.12% << 2.0% target. Util 0.45% << 30% target. Even if statistical gate had
passed, the trigger is **structurally too sparse** for sparse-strict mode
life-changing economics (1209 events / 14 syms / 2.25yr = ~38/sym/yr or
~3/sym/month).

## Lesson #42 (5th dogfood B mirror) verdict

| check | value |
|---|---|
| B_mirror three-gate pass | FALSE |
| B_same_sign three-gate pass | FALSE |
| B_mirror concentration pass | FALSE |
| B_mirror LC4dim pass | FALSE |
| Lesson #42 5th dogfood pattern (B_mirror PASS / B_same FAIL) | **FALSE** |
| Lesson #42 5th dogfood full PASS | **FALSE** |

**Lesson #42 5th dogfood: NOT TRIGGERED**. Capitulation MR pattern absent in
hour-of-day seasonality class. Dogfood count remains at 4 (paradigm 117/158/162/179).

## Lesson #61 (hour-of-day axis class) — 2nd consecutive falsification

- **paradigm 113** (`intraday_hour_of_day_anchor_alt_directional_2h`,
  2026-05-20): anchor hour {00,07,13,21} × |z|≥1 prior 1h return joint
  trigger → BROAD_FALSIFIED, Lesson #39 sub-class A.
- **paradigm 192** (this, 2026-05-22): per-sym × per-hour 30d seasonality z
  → BROAD_FALSIFIED, Lesson #39 sub-class A.

**Both paradigms: exact-symmetric mirrors, broad-uniform-negative, NO mirror
concentration**. Two distinct trigger formulations on the hour-of-day axis
both produce identical pathology: trigger has zero directional info, mirror
is forced by construction, gross magnitudes are sub-fee.

**Family-retire status**: Following the precedent of paradigm 113 graveyard
note ("Single instance does NOT warrant family retire. … Hour-of-day axis
combined with NON-momentum signals (e.g., volume z, OI z, premium z at
anchor hr) might retain hypothesis space but is paradigm-distinct."), this
2nd dogfood now satisfies the 2-paradigm threshold for **hour-of-day directional
momentum/seasonality sub-class** Tier 4 retire candidacy.

**Tier 4 retire scope** (proposed):
- **RETIRED**: hour-of-day axis × (price-magnitude z OR price-return z OR
  per-sym per-hour return seasonality z) directional momentum/reversal on
  any hold ∈ {1h, 2h, 4h, 8h, 12h}, any universe size, any z threshold.
- **RETAINED hypothesis space** (paradigm-distinct):
  - Hour-of-day × NON-price signals (volume z / OI z / funding z / premium z
    / liquidation z at anchor hr) — substrate availability subject to
    Lesson #28 + #11 prescreen.
  - Hour-of-day × cross-asset signal (BTC dominance flip at specific UTC).
  - Hour-of-day × order-flow microstructure (taker buy ratio at anchor
    hour) — Family `taker_buy_vol` already retired (paradigm 23/60/72),
    advisory cross-block applies.

## Lesson candidates

- **Lesson #39 sub-class A**: 4th dogfood (paradigm 108 + 113 + 192 +
  ad-hoc). Symmetric construction trigger → identical pathology each time.
- **Lesson #34 partial**: empirical |z|≥2 rate 0.96% (vs parametric 2.27%)
  for per-sym×per-hour rolling mean estimator on correlated samples —
  consistent with "rolling-mean z is conservative on autocorrelated panels"
  (no new lesson, existing Lesson #34 covers).
- **NEW Lesson #71 candidate** (already lifecycle Lesson #71 corollary): per-trade
  edge << 2.0% target on sparse-trigger 4h trades is structural, not signal-quality
  issue — at 1209 events/2.25yr/14 syms, even ±50bp gross would yield
  ~0.45% util and ~3.5% trades/yr edge under sparse-strict criterion (still
  below 2.0%). Hour-of-day axis class cannot satisfy sparse-strict
  life-changing 4-dim by construction.
- **NEW Lesson candidate (informal)**: "Hour-of-day axis on 4h frame is
  econometrically structurally challenged" — 6 hours × 4h bars per day =
  1 observation per hour per day per sym. 30d rolling per-hour mean has
  only 30 samples and high noise. Statistical power for detecting hour-of-day
  alpha at |z|≥2 cutoff on 14 syms × 2.25yr is fundamentally limited.

## Cumulative counters (post-graveyard 192)

- **192nd paradigm** registered.
- **Family retires (proposed +1)**: 8 → **9** (pending user acknowledge hour-of-day
  directional Tier 4 retire). Existing 8 retires unchanged.
- **Lessons confirmed**: 40 (no new; Lesson #39 sub-class A 4th dogfood
  reinforces existing).
- **Continuous-parallel policy maintained** ([[feedback-paradigm-campaign-continuous-parallel]]
  + [[feedback-persistence-over-efficiency]]) — no dispatch pause.

## Next action — paradigm 193 next-action 권고

Per [[feedback-persistence-over-efficiency]] (지속 dispatch가 본질, 실패 누적이
정상) and [[feedback-paradigm-campaign-continuous-parallel]] (closing rate 무관
dispatch 지속):

**Top candidate axis classes (untested or under-explored, conditioned on
recent family retires)**:

1. **Cross-asset BTC dominance regime flip × alt rotation** (Phase B candidate
   memory item still untested as paradigm). Substrate: 4h close BTC + 13
   alts, BTC.D proxy via BTC/(BTC+alt_sum). Trigger: BTC.D 30d z reversal
   (momentum→MR or vice versa). Directional bet on alt rotation timing.

2. **Per-sym 4h volume share rotation within asset cluster** — relative volume
   spike within a sub-cluster (e.g., L1: ETH/SOL/AVAX/NEAR; meme:
   DOGE/WIF/SHIB). NOT funding/OI (retired). NOT cross-exchange share
   (retired paradigm 94/95). Sub-cluster relative dispersion z.

3. **Realized vol regime CHANGE-point** (NOT level, paradigm 69 R-5 LIVE).
   Page-Hinkley CUSUM on 4h RV but on 4h frame (Lesson #22 PASS — 4h has
   adequate frame-grade frequency, unlike daily aggregate book_depth which
   was Lesson #22 fail). Vol-up-shift OR vol-down-shift change event ×
   alt directional response.

4. **Inter-symbol correlation breakdown event** — when 4h rolling correlation
   matrix drops a cluster (e.g., ETH-SOL ρ goes from +0.9 to +0.2), trigger
   long the lagging name (mean-reversion of correlation). Cross-sectional
   axis, NOT funding family.

**Recommended for paradigm 193**: option **3 (RV change-point CUSUM 4h)** —
- Distinct from paradigm 69 (level-conditional vol-LONG vs change-point trigger)
- Lesson #22 escape (4h frame ≠ daily aggregate)
- 5/5 family-distinct candidate (statistic = CUSUM change-point detector;
  universe = standard 14; entry sparse 4h spike; mechanism = vol regime
  transition; hold standard 4h)
- Substrate ready (4h joblib already available)

User may override with options 1/2/4 or new hypothesis. Per memory policy,
agent does not request user decision — paradigm 193 dispatch will proceed
with option 3 unless directed otherwise.

## Files

- Script: `backend/scripts/research/paradigm192_alt_per_sym_30d_hour_of_day_seasonality_z_spike_directional_4h_bilateral_r1.py`
- Metrics: `backend/runs/research_track/alt_per_sym_30d_hour_of_day_seasonality_z_spike_directional_4h_bilateral/r1__metrics.json`
- Graveyard report: `backend/runs/research_track/graveyard__alt_per_sym_30d_hour_of_day_seasonality_z_spike_directional_4h_bilateral.md`
- INDEX.json updated: 100 → 101 paradigms (paradigm 192 entry added)
