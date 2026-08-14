# paradigm 224 GRAVEYARD (root pointer)

See canonical:
`backend/runs/research_track/paradigm_224_alt_binance_liq_asymmetry_forced_deleveraging_reversal_4h/GRAVEYARD.md`

## Executive summary

- **Verdict**: `R0_HALT_BY_SUBSTRATE_DISPATCH_IMPOSSIBLE_LESSON_28_MARKETWIDE_FORCED_LIQUIDATION_HISTORICAL_UNAVAILABLE_FREE_TIER`
- **Phase**: R-0 SUBSTRATE AUDIT HALT
- **Cause**: No free-tier path reaches ≥2yr historical market-wide Binance perp forced-liquidation event stream with per-side USD volume.
  - `/fapi/v1/forceOrders` — user-scoped only (HTTP 401)
  - `/fapi/v1/allForceOrders` — deprecated (HTTP 404)
  - `data.binance.vision daily/` — no liquidation prefix
  - WS `!forceOrder@arr` — real-time only, no retrospective rewind
  - backend cache — zero coverage
  - third-party paid — blocked by `[[feedback-no-freemium-trial]]`
  - aggTrades proxy — invalid substrate (no forced-order flag)
- **Compute avoided**: R-1 batch (~40 min) not dispatched.

## Infrastructure task 224.1 filed

Recommend a **WS `!forceOrder@arr` recorder daemon** to be seeded next session for a 60–90d accumulation window enabling paradigm 224 re-dispatch at **2026-09-10 or 2026-10-10**. Zero-cost infrastructure. See canonical doc for full spec.

## Lesson dogfoods
- Lesson #28 — 6th operational CONFIRMED (R-0 halt by substrate)
- Lesson #77 candidate ESCAPE 조건 2 (non-OHLCV substrate) — DEFERRED (untestable free-tier this session)
- Lesson #61 slug uniqueness — PASS
- Lesson #62 DNA 4-dim — PASS (0 overlaps)
- Lesson #30 ADA exclusion — complied

## Next paradigm 225 recommendation

1. Bybit/OKX funding cross-venue spread (substrate CONFIRMED)
2. OI velocity × premium index joint (substrate CONFIRMED)
3. KR-hour × BTC funding boundary compound (substrate CONFIRMED)

Timestamp: 2026-07-12 KST
