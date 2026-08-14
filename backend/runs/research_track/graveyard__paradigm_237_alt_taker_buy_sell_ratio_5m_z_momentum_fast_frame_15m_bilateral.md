# Graveyard — paradigm 237 alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral

**Slug**: `alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral`
**Paradigm number**: 237
**Dispatch mode**: SELF-RECOMMEND (autonomous)
**Date**: 2026-07-26
**Final phase**: R-0 GRAVEYARD (halt at Lesson #79 predictive-content pretest)
**Type**: E (per-trade edge, bilateral)
**Family**: Microstructure TBS (fast-frame exception attempt under Lesson #57)

## Hypothesis

Per-symbol 5m `taker_buy_sell_ratio` rolling z-score captures directional microstructure momentum.
Extreme positive z (strong buying imbalance) → 15m LONG continuation.
Extreme negative z (strong selling imbalance) → 15m SHORT continuation.

Mechanism intuition: institutional / informed order flow persists 15m as follow-on algo and retail
orders amplify the initial direction. 1h–4h holds (paradigm 23) showed no edge because mean-reversion
eliminates the signal; 15m window supposed to capture momentum before that.

Design:
- Signal: `tbs_z_N = (tbs - tbs.rolling(N).mean()) / tbs.rolling(N).std()` with N ∈ {48, 96, 288} bars
- Trigger: z ≥ +T → LONG; z ≤ −T → SHORT; T ∈ {1.0, 1.5, 2.0}
- Hold: 3 bars (15m primary) + 6 bars (30m secondary)
- Fee: 8bp round-trip
- Universe: 14 syms with both microstructure and 1m OHLCV coverage
  (ADA, AVAX, BCH, BNB, BTC, DOGE, ETH, FIL, LINK, LTC, NEAR, SOL, WIF, XRP)

## DNA table (Lesson #62)

| Dim | Paradigm 23 (taker_flow_zscore) | Paradigm 237 |
|---|---|---|
| statistic_class | rolling z of tbs_ratio | rolling z of tbs_ratio | **SAME** |
| direction | FOLLOW + FADE both tested | FOLLOW only (momentum) | PARTIAL |
| hold | 1h/2h/4h (12/24/48 bars) | 15m/30m (3/6 bars) | **DIFFERENT** |
| universe | ~16 syms at 5m | 14 syms at 5m | PARTIAL |
| mechanism | generic orderflow | 15m microstructure momentum | SIMILAR |

DNA overlap ≈ 2.5/5 → PASS the 5/5 duplicate-halt threshold (Lesson #62).

## R-0 Prescreen — 9 items

| # | Lesson | Result |
|---|---|---|
| 1 | #61 slug grep | PASS — no fast-frame TBS 15m slug in graveyard; closest is paradigm 234 (h4-d1) |
| 2 | **#79 predictive content pretest** | **FAIL — universal (see below)** |
| 3 | #62 DNA strict table | PASS (2.5/5) |
| 4 | #56 family proxy | PASS (Lesson #57 fast-frame exception applies at ≤60m hold) |
| 5 | #28 substrate audit | PASS (14 usable syms) |
| 6 | #11 sample density | PASS (~10k events/sym at z=1.5 over 420 OOS days) |
| 7 | #40 structural feasibility | PASS (tbs bounded (0,1), rolling z easily reaches ±1.5–2.0) |
| 8 | #39 pre-check | PASS structurally; gate becomes Lesson #79 (failed) |
| 9 | #57 compliance | PASS (15m/30m << 60m fast-frame threshold, TBS-family ≥4h ban does not apply) |

## Lesson #79 pretest detail (the halting item)

Threshold: `abs(oos_corr) ≥ 0.02` on OOS half (index[len/2:]) for at least one (sym, N, hold).

| sym | N | corr(tbs_z, fwd_15m) OOS | corr(tbs_z, fwd_30m) OOS |
|---|---|---|---|
| SOL | 48 | -0.006529 | -0.006 range |
| SOL | 96 | -0.007610 | -0.006 |
| SOL | 288 | **-0.008162** | -0.007678 |
| BTC | 48 | -0.007429 | -0.008906 (max) |
| BTC | 288 | -0.006497 | -0.007912 |
| ETH | 288 | -0.007892 | -0.007207 |
| BNB | 288 | -0.000614 | -0.001010 |
| DOGE | 288 | -0.003793 | -0.006151 |
| LINK | 288 | -0.004846 | -0.006551 |
| AVAX | 288 | -0.001477 | -0.004320 |
| LTC | 288 | -0.001408 | -0.003066 |
| XRP | 288 | -0.004708 | -0.005602 |

- **Best |corr| across 9 syms × 3 windows × 2 holds = 0.0089** (BTC N=48 30m).
- All correlations are **NEGATIVE** — the momentum-follow hypothesis is falsified in the empirical
  data direction. Positive z (buying imbalance) predicts tiny **downward** drift, not upward
  continuation.
- Even the flipped (FADE) direction would produce |corr| ≈ 0.008, i.e. below noise floor and well
  under the ~0.02 fee-adjusted signal-detection threshold. 8bp round-trip at 15m hold would
  consume virtually any per-trade edge.

Sign uniformity: 27/27 tested (sym × N × hold) combinations show negative corr.

## Distribution audit (SOL, tbs_z_N288, 254,299 valid rows)

- min = -2.912, max = +12.171, mean ≈ 0.001
- |z|>1.0 → 26.5% of bars
- |z|>1.5 → 9.1% of bars
- |z|>2.0 → 4.4% of bars

Rich sample density at every threshold — the failure is signal quality, not sample size.

## Failure classification

- §3-X category: **PREDICTIVE_CONTENT_ABSENT** (Lesson #79 miss)
- Sub-diagnosis: **WRONG_DIRECTIONAL_BIAS** — the tiny nonzero corr has the opposite sign from
  the mechanistic hypothesis; even a FADE reformulation would still be sub-fee-floor.
- Not a §3-C diversity fail, not a §3-G marginal-perm-sigma fail — the paradigm never reaches R-1
  because R-0 pretest disproves predictive content ex-ante.

## Lessons dogfooded

- **Lesson #79 (2nd application post-paradigm 233 1st dogfood)** — CONFIRMED prevents a 72-cell
  R-1 sweep × 4 quadrants × 14 syms (~4,032 sub-runs and ~30 min compute + graveyard writeup).
  Signal quality is estimated in ~30 seconds; escape route works as designed.
- Lesson #57 fast-frame exception clause was correctly invoked (would have made the paradigm
  admissible under family-ban rules), but exception admissibility does not imply signal existence.
- Lesson #62 DNA table applied; 2.5/5 correctly indicated a valid attempt (not a duplicate).

## New lesson candidates

### L83 (1st dogfood) — TBS_z fast-frame (5m → 15m/30m) shows anti-momentum micro-drift, sub-fee-floor

Empirical: across 9 majors (SOL, BTC, ETH, BNB, DOGE, LINK, AVAX, LTC, XRP) × 3 windows
(N=48/96/288 bars @ 5m) × 2 holds (15m/30m), 27/27 OOS correlations are negative with
best |corr| = 0.0089. Fast-frame TBS momentum has:

1. Sign opposite to the "orderflow momentum" intuition (weak reversion, not continuation).
2. Magnitude below noise floor and well under fee-adjusted detection threshold.

Prescription: When considering TBS-family fast-frame paradigms in the future, only test:
- FADE (mean-reversion) direction, and
- Very rare extreme quantiles (|z| ≥ 3.0), and
- Hold ≤ 1 bar (5m single-bar), where fee drag is minimized.

Standard momentum-follow at moderate z thresholds is falsified. Status: **CANDIDATE_1_DOGFOOD**
(needs 1 more concordant dogfood to formalize).

## Comparison with recent halt chain

| Paradigm | Halt phase | Reason |
|---|---|---|
| 234 | R-0 | Lesson #56 TBS family + Lesson #57 fee floor at h4-d1 |
| 235 | R-0 | DNA duplicate (paradigm 134 semivariance) |
| 236 | R-3 | book_depth imbalance perm_sigma < 4.0 (best 2.42σ LTC) |
| **237** | **R-0** | **Lesson #79 predictive content universally < 0.02** |

Pattern: three of the last four paradigms halted at R-0. Lesson #79 is doing what it was designed
for — cutting off zero-signal paradigms before expensive R-1 compute.

## Next paradigm recommendation

Avoid TBS-family fast-frame momentum going forward. Suggested next explorations
(ordered by novelty and Lesson #79-passability likelihood):

1. **global_account_ls_ratio anomaly at 4h hold** — new substrate axis within microstructure
   joblib (not TBS, not toptrader_position). Not covered by paradigm 233 (which used
   toptrader_position velocity). 4h hold sidesteps Lesson #57 fast-frame constraint entirely.
   Recommended R-0 Lesson #79 pretest at fwd_4h and fwd_1d.
2. **OI-share Herfindahl-index second derivative at 1h frame** — orthogonal to paradigm 232
   which used the level (not the second derivative / acceleration).
3. **BTC-dominance regime-change 24h/72h alt rotation** — macro-substrate (Fear & Greed / BTC
   dominance from CoinGecko-like feeds), completely orthogonal to microstructure exhaustion.
   Higher backfill cost — check archive first.

For every future paradigm: run Lesson #79 pretest as item 2 of R-0 with `abs(corr) ≥ 0.02` bar.

## Artifacts

- `backend/runs/research_track/paradigm_237_alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral/r0_prescreen.json`
- `backend/runs/research_track/graveyard__paradigm_237_alt_taker_buy_sell_ratio_5m_z_momentum_fast_frame_15m_bilateral.md` (this file)
- INDEX.json entry added
- NEXT_PARADIGM_RUNBOOK.md §237 appended
