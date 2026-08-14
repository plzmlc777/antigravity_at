# GRAVEYARD — paradigm 249

**Name**: `249_btc_onchain_transfer_value_adjusted_z_spike_alt_bilateral_24h`
**Date**: 2026-08-08
**Final phase**: GRAVEYARD
**Verdict**: `R0_HALT_BY_SUBSTRATE_UNAVAILABLE_LESSON_28`

## One-line
CoinMetrics `TxTfrValAdjUSD` 1d is a Pro-tier metric. Community API returns `403 forbidden`. Community tier gives only 31 metrics for BTC (transfer/tx-related: only `TxCnt`, `TxTfrCnt`). Paid APIs are blacklisted by CLAUDE.md. The only community-tier reformulation lands on an on-chain-count family that was already falsified by predecessor `btc_onchain_active_address_regime_alt_bilateral_24h` (R1 BROAD_FALSIFIED Lesson #39 sub-class A).

## G0 substrate probe (empirical)

```
GET https://community-api.coinmetrics.io/v4/timeseries/asset-metrics
    ?assets=btc&metrics=TxTfrValAdjUSD&frequency=1d&start_time=2024-01-01&end_time=2026-08-07

→ HTTP 200
{
  "error": {
    "type": "forbidden",
    "message": "Requested metric 'TxTfrValAdjUSD' with frequency '1d' for asset 'btc'
                is not available with supplied credentials."
  }
}
```

Community catalog for BTC (`/v4/catalog-v2/asset-metrics?assets=btc`) returns 31 metrics.
Filtering by `Tfr | TxCnt | TxTfr` yields exactly two: `TxCnt`, `TxTfrCnt`. No value-denominated
transfer metric exists in community tier.

## Why not just swap to TxCnt / TxTfrCnt

DNA overlap vs immediate predecessor `btc_onchain_active_address_regime_alt_bilateral_24h`:

| dim | predecessor (AdrActCnt) | reformulation (TxCnt) | verdict |
|---|---|---|---|
| substrate | CoinMetrics community | CoinMetrics community | PARTIAL (same API) |
| statistic | rolling 30d regime percentile | rolling 30d z-score | DIFFERENT |
| mechanism | retail-engagement-breadth | tx-activity-count | PARTIAL (both count-based) |
| universe | 3-alt pool (SOL/DOGE/ETH) | 13-alt perp | SAME family |
| direction | bilateral | bilateral | SAME |
| hold | 24h/48h | 24h/48h | SAME |

Strict 5/6 DNA-duplicate rule not triggered (only 4/6 partial-or-same). But this is exactly
the failure-family that Lesson #61 warns about — a mechanism-proxy on an already-falsified
family is a Lesson #55 prescription out-of-scope (spatial fix ≠ mechanism fix). Predecessor
died with `BROAD_FALSIFIED_LESSON39_SUBCLASS_A`: SNT quadrants showed focus+mirror ≈ −2×fee_RT
deterministically → trigger carries **zero directional information**. Count metrics on the same
chain are strongly correlated (typ 0.7–0.9 daily) with active-address counts because more
active addresses drive more transactions. Same failure mode expected.

## Where the dispatch went wrong

The runbook asserted:
> "No paid data: CoinMetrics community API is free, no auth required ✓"

This is true of the API *host* but not of the specific metric. `TxTfrValAdjUSD` is
explicitly gated to Pro-tier per CoinMetrics' own catalog. The G0 checklist in the dispatch
contained a compliance assertion but **no empirical substrate-availability probe**. Adding
an empirical curl probe at the very top of G0 catches this in seconds; reasoning about
API tier lists does not.

## Lesson references (existing)

- **#28 substrate availability prescreen** — target metric must be *actually queryable* at
  run-time with allowed credentials, not merely listed on the vendor's marketing page.
- **#61 predecessor monotonic decay** — a proxy on an already-falsified family is a
  Lesson #55 prescription out-of-scope.
- **CLAUDE.md paid-API rule** — CoinMetrics Pro is a paid tier; not allowed.

## Lesson candidate (new — for Q3 index consideration)

**Lesson #83 candidate (2026-08-08 paradigm 249)**: *Vendor-tier metric availability must be
empirically probed at G0 top before writing signal code.* Free-tier availability of a *host*
does not imply free-tier availability of a *specific metric*. Runbook substrate compliance
assertions like "API is free" are insufficient — G0 must fire an actual query against the
target endpoint and inspect the response. Cost: this paradigm went from queued to graveyard
in one curl; had we started writing the signal pipeline first we'd have wasted an hour.

## Artefacts

- `r0_prescreen.json` — full audit with API response bodies.
- (no r1 / r2 / r3 / trades / gate — halted at substrate probe)

## Next-step recommendation

Do not re-queue any on-chain-count derived signal on the BTC → alt-24h family. The
falsified predecessor's diagnosis (zero directional information at the trigger) applies
across the count family. To open the on-chain axis at all, either:
1. Acquire allowed on-chain **value-denominated** substrate (e.g. Blockchain.com free
   endpoints for on-chain volume USD if terms allow; Glassnode/CryptoQuant are paid → NO),
   or
2. Move to a non-BTC on-chain source where the count-family falsification does not carry
   (e.g. ETH gas-price percentile as a MEV-cost-regime signal — different mechanism), or
3. Pivot the whole axis away from on-chain to a different substrate the queue has not
   burned yet.
