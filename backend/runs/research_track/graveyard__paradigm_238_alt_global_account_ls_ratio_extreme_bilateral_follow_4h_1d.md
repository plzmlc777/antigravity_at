# Graveyard — paradigm_238_alt_global_account_ls_ratio_extreme_bilateral_follow_4h_1d

**Paradigm number**: 238
**Halt phase**: R-0 (before R-1 dispatch)
**Verdict**: `R0_HALT_LESSON_79_ZERO_PREDICTIVE_CONTENT`
**Halt timestamp KST**: 2026-07-27

## Hypothesis (verbatim)

Binance Futures `global_account_ls_ratio` (ALL-accounts aggregate L/S ratio, distinct from toptrader_account_ls_ratio and toptrader_position_ls_ratio previously tested) rolling 30d z-score at |z| >= T predicts near-term directional (FOLLOW or CONTRARIAN, bilateral 4-quadrant SNT) alpha at 4h and 1d hold. Direction axis = sign(ratio_z); T in {1.5, 2.0, 2.5}; hold in {4h, 1d}.

## DNA

| Dim | Value |
|---|---|
| substrate | `global_account_ls_ratio` (Binance Futures 5m microstructure, ALL accounts aggregate) |
| statistic | log(ratio) rolling 30d mean / std z-score |
| trigger | \|z\| >= T (extreme) |
| direction axis | sign(z) both FOLLOW and CONTRARIAN branches, 4-quadrant SNT |
| hold | 4h (96 5m bars), 1d (288 5m bars) |
| universe | 14-sym microstructure cohort (all had column) |

## R-0 prescreen results

### PASS items
- **Lesson #61 slug grep**: no verbatim duplicate. Runbook line 804 explicitly proposes `alt_global_account_ls_ratio_anomaly_directional_4h` as untested candidate; this attempt executes that proposal.
- **Lesson #28 substrate**: 14/14 syms have the column, 155k-255k 5m bars each.
- **Lesson #62 DNA 5-dim**: 3/5 novel vs paradigm 16 (column swap + FOLLOW branch added), 3/5 novel vs paradigm 233 (column swap + statistic-class swap).
- **Lesson #39 axis**: direction = sign(z), not bar_direction. Genuine self-signaling.
- **Lesson #40 structural threshold**: empirical z distribution near-normal; thresholds 1.5/2.0/2.5 feasible bilaterally.

### FAIL item — Lesson #79 zero predictive content (MANDATORY position-2 pretest)

Method: OOS half (post 50% of joblib intersection) on SOLUSDT + BTCUSDT; compute Pearson corr(z, fwd_pct_change(hold_bars)) full-sample.

| Symbol | OOS n | hold 4h corr | hold 1d corr |
|---|---:|---:|---:|
| SOLUSDT | 113712 | +0.00845 | +0.01188 |
| BTCUSDT | 75581 | -0.01527 | -0.01467 |

**Max absolute correlation = 0.01527 < 0.02 rule threshold across ALL 4 (sym × hold) cells.**

Per pre-registered R-0 rule (self-recommend prompt Item 2):

> If max |corr| < 0.02 for ALL syms AND holds → R-0 HALT with verdict `R0_HALT_LESSON_79_ZERO_PREDICTIVE_CONTENT`.

Rule triggered; no R-1 dispatch.

### Supplementary confirmation — extreme-subset + autocorrelation-corrected analysis

To validate the halt is not a false-positive-rejection of a real subset signal, I additionally checked whether the |z| >= T subsets would show real signal under proper non-overlapping event sampling (entry cooldown = hold_bars, mirroring how paper deployment would trade).

| sym | thr | hold | non-overlap n | follow mean bp | t-stat | per-quarter behavior |
|---|---:|---:|---:|---:|---:|---|
| SOL | 2.0 | 4h | 154 | +15.4 | 1.04 | 25Q3=−5.8 → 25Q4=+47.6 (sign flip) |
| SOL | 2.0 | 1d | 71 | +8.6 | 0.24 | −89.1 → +173.6 → +86.4 → +19.0 (wild) |
| SOL | 2.5 | 4h | 53 | +40.7 | 1.49 | 25Q3=−1.5 → 25Q4=+111.1 (sign flip) |
| SOL | 2.5 | 1d | 26 | +90.9 | 1.24 | 25Q4=+280.7 → 26Q1=−45.5 (sign flip) |
| BTC | 2.0 | 4h | 93 | +0.2 | 0.02 | 25Q3=+42.0 → 25Q4=−21.4 (sign flip) |
| BTC | 2.0 | 1d | 44 | +14.0 | 0.52 | 25Q3=+86.1 → 25Q4=−51.2 (sign flip) |
| BTC | 2.5 | 4h | 18 | — | — | INSUFFICIENT (Lesson #11) |
| BTC | 2.5 | 1d | 9 | — | — | INSUFFICIENT (Lesson #11) |

Contrast with **naive overlapping-bar t-stats** (which the raw pretest also showed): BTC thr=2.5 h=1d overlapping n=1334 gave t=11.36 — this is pure autocorrelation inflation. The same event pool sampled non-overlapping yields n=9 and cannot be tested.

**Conclusion**: All cells fail three-gate concurrently (t < 2.0, no per-quarter stability, insufficient n at strong thresholds). Even if the formal Lesson #79 corr < 0.02 rule had marginally missed (e.g., 0.021), the R-1 would have hit three-gate FAIL + Lesson #16 concentration FAIL + Lesson #26 walk-forward fragility deterministically. The rule correctly saves the R-1 compute budget.

## Lessons applied

- **Lesson #61**: slug grep clean — proceed.
- **Lesson #79** (position 2, MANDATORY): triggered HALT. This is the primary halt cause. Records **3rd LSR-family Lesson #79 halt** (paradigm 16 was pre-#79 era but retrospectively fits; paradigm 233 tested velocity variant; paradigm 238 tested aggregate column). Directly saves R-1 compute.
- **Lesson #28**: substrate coverage validated — orthogonal PASS.
- **Lesson #62**: DNA distinctness validated — this was genuinely a novel column swap, not a slug-relabel duplicate.
- **Lesson #56 (soft warning)**: LSR family now 2/2 confirmed graveyards (16 + 233); paradigm 238 R-0 halt makes 3/3 across the family. Column swap alone did not escape.
- **Lesson #16 / #11 / #26 (supplementary confirmation)**: non-overlap event analysis confirms the halt is not over-rejection.

## New lesson candidates (1st dogfood)

**Candidate #80-A (1st dogfood)**: **"LSR-family universal Lesson #79 failure across substrate variants"** — All three L/S ratio column variants exposed by Binance Futures microstructure (toptrader_account, toptrader_position, global_account) have now failed either Lesson #79 pretest or downstream R-1/R-2 broad-falsification. Together with paradigm 16 (2024 era LSR contrarian BROAD_FALSIFIED) and paradigm 233 (velocity z BROAD_FALSIFIED) this establishes a family-level empirical prior: **rolling z-score of any single-source L/S positioning ratio, on its own, has near-zero linear predictive content for forward returns at 4h-1d horizons in this asset class**. Future L/S-family attempts should require either (a) joint multi-source divergence (positioning gap between column-A and column-B, e.g., top_position vs global_account, which is separate slug space) or (b) conditioning on external context (funding, volatility regime, open interest change) rather than the ratio z alone. **CANDIDATE**, promotes to CONFIRMED on 2nd dogfood.

**Candidate #80-B (1st dogfood)**: **"Naive overlapping-bar t-inflation as autocorrelation artifact for slow rolling-z signals"** — When the trigger is a rolling z-score with long window (30d = 8640 5m bars), consecutive |z|>=T bars are highly serially correlated (typical run length: several bars to hours). Naive bar-level t-stats over event pool can inflate 5-10x relative to non-overlapping-event t-stats. Pretests should either (a) enforce non-overlapping event sampling with cooldown = hold_bars, or (b) apply block-permutation with block size >= autocorrelation length. Concrete example: BTC thr=2.5 h=1d naive t=11.36 collapsed to n=9 non-overlap (untestable) — a factor of ~150x n reduction. **CANDIDATE**, promotes to CONFIRMED on 2nd dogfood.

## Next direction

- Add note to §6.2 of the paradigm queue: **LSR-family single-column exhausted; skip further single-column LSR level/velocity/percentile/change variants** unless proposing a joint multi-source formulation.
- Runbook §804 candidate "alt_global_account_ls_ratio_anomaly_directional_4h" is now retired via paradigm 238 R-0 halt.
- Preserve joint-multi-source LSR candidate (runbook §629 divergence paradigm) as distinct family; requires its own R-0.
- SELF-RECOMMEND queue next candidate should be OFF the positioning-ratio family entirely (Lesson #77 substrate-diversity principle).

## Artifacts

- `backend/runs/research_track/paradigm_238_alt_global_account_ls_ratio_extreme_bilateral_follow_4h_1d/r0__prescreen_metrics.json`
- `backend/runs/research_track/graveyard__paradigm_238_alt_global_account_ls_ratio_extreme_bilateral_follow_4h_1d.md` (this file)
