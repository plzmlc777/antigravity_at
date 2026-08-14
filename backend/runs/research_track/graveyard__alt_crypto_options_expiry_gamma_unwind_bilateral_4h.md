# Graveyard — alt_crypto_options_expiry_gamma_unwind_bilateral_4h

**Registered**: 2026-07-31 (SELF-RECOMMEND cron dispatch)
**Terminated at phase**: R-1
**Verdict**: `BROAD_FALSIFIED_WITH_MIRROR_CONTINUATION_ASYMMETRY`
**Type**: E (event-study)

## Hypothesis
Weekly Deribit options expiry (Friday 08:00 UTC) delta-hedge unwind causes a
REVERSAL of the pre-expiry 8h trend in the 4-8h post-expiry window.

- A_focus: pre_UP → SHORT (reversal down)
- B_focus: pre_DOWN → LONG (reversal up)

## R-1 Design
- 14-symbol cohort (BTC + 13 alts, all with 1m OHLCV cache 2024-01 to 2026-05)
- 123 weekly Friday 08:00 UTC expiries in coverage window
- pre_window = 8h, post_hold = 4h (primary), 8h swept
- Fee = 8 bp round-trip
- 4-quadrant Symmetric Negative Test (Lesson #19) mandatory

## Results (r1__metrics.json)

| Quadrant | n | obs_t | signal_t_excess | ci_lower_bp | perm_p (above) | verdict |
|---|---|---|---|---|---|---|
| A_focus (pre_UP → SHORT) | 958 | -2.05 | **-0.60** | -28.00 | 0.714 | FAIL |
| B_focus (pre_DOWN → LONG) | 760 | +1.62 | +2.86 | **-3.13** | 0.001 | FAIL (CI) |
| A_mirror (pre_UP → LONG) | 958 | -0.23 | +1.22 | -14.92 | 0.124 | FAIL |
| B_mirror (pre_DOWN → SHORT) | 760 | -3.76 | **-2.51** | -42.92 | 0.995 | FAIL |
| Bilateral pooled | 1718 | +1.14 | +1.37 | -12.84 | 0.089 | FAIL |

## Interpretation

**Reversal hypothesis is broadly falsified.** Two independent failure modes:

1. **A_focus fails outright** (signal_t_excess = -0.60, wrong sign relative to reversal). On days with pre_UP into expiry, the post-expiry 4h return does NOT reverse — if anything, it continues upward (A_mirror signal_t_excess = +1.22 > A_focus). This is exactly the anti-pattern the delta-hedge-unwind story predicted against.

2. **B_focus passes signal_t_excess (+2.86) and perm_p (0.001), but bootstrap CI lower is -3.13 bp** → three-gate FAIL. The point estimate is favorable but the CI cannot exclude zero at 95% given the small per-trade edge and sample noise. Concentration was not evaluated for this quadrant because three-gate did not pass first.

3. **B_mirror (pre_DOWN → SHORT) shows -2.51 signal excess and perm_p 0.995** → confirms pre_DOWN days DO tend to bounce up (opposite of continuation). This is real but weak: it's consistent with an unconditional post-Friday overnight bull drift bias, not with a delta-hedge unwind mechanism.

4. **Regime bias**: median pre_ret_8h is POSITIVE across all 14 symbols (e.g., LINKUSDT +0.48%, WIFUSDT +0.70%, FILUSDT +0.48%, BCHUSDT +0.35%). The 2024-2026 sample is dominated by up-trending Fridays. The "A/B" split is not balanced regime-wise; A_focus is over-represented (958 vs 760). The signal is not gamma-unwind — it's an unconditional Friday-drift bias with fee drag.

5. **Bilateral pooled mean = -2.68 bp per trade** (net after fee). Total edge sign is negative once fees are paid. This paradigm cannot make money as a contrarian reversal strategy in the observed epoch.

## Lesson Contribution (candidate — needs 2 dogfoods for CONFIRMED)

Candidate Lesson #82 (dogfood #1):

> **Structural derivatives expiry ≠ automatic reversal.** Weekly options expiry
> gamma-unwind is a plausible market-microstructure story, but empirically the
> post-expiry 4-8h window does not reverse the pre-expiry trend on average.
> Instead: (a) pre_UP days tend to continue up mildly; (b) pre_DOWN days tend
> to bounce up (unconditional drift). This is consistent with the epoch being
> a bull-market regime where Friday 12:00-16:00 UTC is a US-morning bullish
> flow window, and gamma dynamics are dominated by that flow.
>
> **Prescription for future expiry-related paradigms**: (1) split by regime
> (bull vs bear year) before running SNT; (2) require the pre_UP:pre_DOWN
> event count to be within [40%, 60%] balance or apply a bull-drift baseline
> control; (3) consider max-pain-conditional entry (only trade when spot is
> >2σ from max_pain), not raw pre-ret sign.

## Lesson #77 status
Substrate was non-OHLCV (options-expiry calendar structural event). Complied.

## Lesson #40 status
Signal was signed return (can be positive or negative); no non-negative
statistic prescreen failure. Complied.

## Lesson #11 status
n per cell was 760-958 » 30 floor. Complied.

## Lesson #19 status
4-quadrant SNT executed in single R-1 batch. Complied.

## Data / Compute
- 14 sym × 1m OHLCV loaded from joblib cache (no download)
- ~578k candidate 4h forward-return pool for fee-drift null
- Wall time: ~15s

## Files
- Code: `backend/scripts/research/alt_crypto_options_expiry_gamma_unwind_bilateral_4h_r1.py`
- Metrics: `backend/runs/research_track/alt_crypto_options_expiry_gamma_unwind_bilateral_4h/r1__metrics.json`
