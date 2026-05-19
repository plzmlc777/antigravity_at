# R-1 Spec — cross_asset_volume_concentration_alt_long_1d (Mint full-data re-run)

**Paradigm ID**: 94
**Run**: r1_mint_rerun
**Dispatch**: 2026-05-19 ad-hoc user-explicit (Mint full-data re-execution)
**Prior local run**: 2026-05-18 (72-day intersection, BROAD_FALSIFIED_FEE_FLOOR)

## Hypothesis (focus)

BTC daily USD-volume share z(30d) <= -1.5 (BTC volume share compression
= alt rotation leading indicator) -> LONG 13 alts at next-day 00:00 UTC
open, hold +1d (24h), exit at close.

## Symmetric Negative Test (Lesson #19)

- **focus**: share_z <= -1.5 LONG (concentration -> rotation)
- **mirror**: share_z >= +1.5 LONG (BTC dominance -> alt suppression hypothesis flipped)

Both quadrants reported in single batch.

## Cross-proxy track (Lesson #29)

- **obs proxy**: volume share fraction z (transform)
- **fund proxy**: BTC absolute USD-volume 30d z (raw flow magnitude)

Both must three-gate PASS independently to satisfy cross-proxy strict.

## Universe

- **trigger asset**: BTCUSDT (signal source, not traded)
- **direction (LONG)**: 13 alts paradigm 69 validated cohort:
  ADA, AVAX, BCH, BNB, DOGE, ETH, FIL, LINK, LTC, NEAR, SOL, WIF, XRP
- **denominator universe**: 14 syms = BTC + 13 alts
- **12 EXTRA boost syms** (AXS/HBAR/LDO/COMP/UNI/PYTH/TON/ETC/ICP/JUP/WLD/1000LUNC)
  not present in Mint joblib ohlcv_cache; load-from-DB cost prohibitive within
  R-1 budget. 14-sym denominator matches paradigm 69 validated cohort, which
  the campaign already accepts as a robust LONG cohort. Sample density (Lesson
  #11) restored via 12x window vs prior local 72-day intersection.

## Statistic class

Single-axis z-score on volume share fraction (rolling 30d). Stateless rolling
transform; not joint-event, not stateful (Lesson #21/#22/#24 N/A).

## Cutoff fallback trail

`[-1.5, -1.2, -1.0]` — first cutoff yielding n_trig * n_alts >= 30 chosen.

## Data window

- Mint joblib cache 1m: 2024-01-02 ~ 2026-05-12 (~862 days BTC, 845 with WIF
  intersection)
- After 30d z warmup: 816 usable z observations (2024-02-17 ~ 2026-05-12)
- vs prior local run: 72 days (2026-01-21 ~ 2026-04-02)

## Output files

- `r1_metrics.json` — full quadrant metrics + criteria + verdict
- `r1_summary.md` — diagnosis + comparison to prior local R-1
- `r1_script.py` — frozen copy of the R-1 script
- `r1_spec.md` — this file
