# Graveyard — paradigm 142 (paradigm 142-v2)

**Paradigm**: `alt_taker_buy_quote_vol_imbalance_z_directional_4h`
**Counter**: 142
**Phase reached**: R-1
**Verdict**: **BROAD_FALSIFIED**
**Run date**: 2026-05-21 KST 13:05

## Hypothesis
4h `taker_buy_quote_volume / quote_volume` imbalance ratio centered at 0.5, per-symbol 30d rolling z-score on (imbalance - 0.5). |z|>2.0 trigger → 4h continuation in trigger direction (pos→LONG / neg→SHORT). 14 alts × 820d × Binance perp.

## Key result (4-quadrant SNT)
| Quadrant | n | mean_bp | sigex | perm_p | ci_lo_bp | 3-gate |
|---|---|---|---|---|---|---|
| A focus pos×LONG | 1859 | -7.83 | -0.759 | 0.230 | -15.40 | FAIL |
| A mirror pos×SHORT | 1859 | -8.17 | +0.204 | 0.580 | -15.67 | FAIL |
| B focus neg×SHORT | 1872 | -1.69 | +1.822 | 0.972 | -8.86 | FAIL |
| B mirror neg×LONG | 1872 | -14.31 | -2.409 | 0.008 | -22.08 | FAIL |

→ 0/4 quadrants 3-gate PASS. B-side asymmetric weak signal (neg trigger biased downward) but sub-fee-floor at 4h hold. 12h hold extends B_focus_SHORT to sigex +3.43 but perm_p still 0.33 + ci_lower marginally negative.

## Failure mechanism
Aggressive USD taker imbalance leaks **during** the 4h bar; by close the price has absorbed the directional information. 4h forward return is residual noise dominated by 16bp fee floor. Same pattern previously documented in paradigm 72 (5m taker_buy_vol BROAD_FALSIFIED) and paradigm 140 (CVD ratio BROAD_FALSIFIED — *xref family completion*).

## Lesson #44 amendment 25th xref check
- paradigm 72 (5m taker_buy_vol family) — same family pattern reconfirmed.
- paradigm 127/128 (volume burst 30m R-5 LIVE) — distinct from 142-v2 (burst spike vs continuous z-imbalance), R-5 unaffected.
- paradigm 140 (CVD ratio) — same family, both fail at 4h frame.
- Funding family (22/132/138-141) — distinct axis, no impact.

## NEW Lesson #57 candidate (1st dogfood)
**Aggressive taker quote-volume imbalance z-score → 4h directional continuation BROAD_FALSIFIED**. Combined with paradigm 72 + 140 = 3rd consecutive failure of taker-side aggressive flow as 4h directional alpha. Provisional family pattern: aggressive taker flow info-leaks during the bar, residual 4h forward return dominated by fee. Recommend escalation after 1 more same-axis dogfood.

## Infrastructure (permanent assets — preserved)
- `backend/scripts/binance/backfill_12col_klines.py` — 12-col kline archive downloader + cache helper.
- `backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib` × 14 syms (3.4MB total, 2024-02-01 → 2026-04-30).
- Reusable for any paradigm requiring `quote_volume` / `taker_buy_quote_volume` / `count` axes.

## Output artifacts
- `backend/scripts/research/paradigm142v2_r0_prescreen.py` (R-0 prescreen PASS)
- `backend/scripts/research/paradigm142v2_r1.py` (R-1 4-quadrant SNT + hold sweep + Lesson #16/19/37/39/40/44/46 instrumentation)
- `backend/runs/research_track/alt_taker_buy_quote_vol_imbalance_z_directional_4h/r0_prescreen.json`
- `backend/runs/research_track/alt_taker_buy_quote_vol_imbalance_z_directional_4h/r1__metrics.json`
- `backend/runs/research_track/alt_taker_buy_quote_vol_imbalance_z_directional_4h/gate_eval__r1.md`

## Verdict
**BROAD_FALSIFIED**. 4-quadrant 0/4 PASS at primary 4h hold. Hold sweep to 12h gives 1/3 gates on B_focus only — insufficient. Both life-changing 4-dim sides FAIL (negative edge/sharpe). Family pattern with paradigms 72/140 strengthens.
