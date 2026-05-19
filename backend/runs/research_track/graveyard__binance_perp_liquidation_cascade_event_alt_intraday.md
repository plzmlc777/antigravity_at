# Graveyard — paradigm 100 (candidate) `binance_perp_liquidation_cascade_event_alt_intraday`

- **Verdict**: `DISPATCH_IMPOSSIBLE`
- **Phase halted**: R-0 substrate availability verification (R-1 not dispatched, zero resources consumed)
- **Date**: 2026-05-19 KST (Day 7 baseline binding mode, ad-hoc R-1 channel)
- **Lesson reference**: #28 (Entry-side event paradigm requires measurement substrate availability prescreen) — 5th dogfood

## Hypothesis (recap)

Binance USDS-M perp 14-sym fast-track sub-universe, 5min liquidation notional volume spike (top decile per-sym 30d rolling z) → 4-quadrant cascade-direction (long_liq×LONG bounce / long_liq×SHORT continuation / short_liq×LONG squeeze / short_liq×SHORT normalize), hold sweep 5/15/60/240m.

## R-0 substrate verification — three independent failure modes

### Mode 1 — `data.binance.vision` (CRITICAL primary source)

Probed `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/um/daily/`. The complete subdirectory tree:

```
data/futures/um/daily/aggTrades/
data/futures/um/daily/bookDepth/
data/futures/um/daily/bookTicker/
data/futures/um/daily/indexPriceKlines/
data/futures/um/daily/klines/
data/futures/um/daily/markPriceKlines/
data/futures/um/daily/metrics/
data/futures/um/daily/premiumIndexKlines/
data/futures/um/daily/trades/
```

**No `liquidationSnapshot/` directory exists.** Initial `HTTP/2 200` for the prefix URL was the bucket's default index page (Cloudfront-cached HTML, 2591 bytes, `last-modified: 2024-03-07`); the actual S3 prefix listing returns `<IsTruncated>false</IsTruncated>` with zero `<Prefix>` children.

Confirmed via the official binance-public-data README — futures section enumerates only `klines`, `trades`, `aggTrades`, `bookTicker`, `bookDepth`, `metrics`, `markPriceKlines`, `indexPriceKlines`, `premiumIndexKlines`, monthly `fundingRate`. **No liquidation feed at any cadence.**

### Mode 2 — `metrics/` archive does NOT contain liquidation columns

Inspected an actual `BTCUSDT-metrics-2025-12-01.csv` (288 5min rows). Full schema (8 columns):

```
create_time, symbol, sum_open_interest, sum_open_interest_value,
count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
count_long_short_ratio, sum_taker_long_short_vol_ratio
```

OI + L/S ratios + taker buy/sell ratio only. No liquidation notional, no forced-liquidation count, no forceOrder events at any aggregation level. This is the same schema documented in `backend/app/microstructure/archive_downloader.py:1-15` and used by paradigms 22 / 24 / 69 / 71 / 72 etc — all of which proxy liquidation pressure via taker-skew + OI-drop combinations rather than measuring it directly.

### Mode 3 — REST `allForceOrders` deprecated; WebSocket `!forceOrder@arr` is live-only

```
GET https://fapi.binance.com/fapi/v1/allForceOrders?symbol=BTCUSDT&limit=5
→ {"code":400,"msg":"The endpoint has been out of maintenance"}
```

The historical public `allForceOrders` endpoint is permanently retired. Remaining account-scoped endpoints (`/fapi/v1/forceOrders`) require API authentication and are limited to the calling account's own forced liquidations (worthless for market-wide cascade research).

WebSocket stream `wss://fstream.binance.com/ws/!forceOrder@arr` ("All Market Liquidation Order Streams") emits market-wide forced market orders but is **live-only with no historical replay**. To use it for a 2.4yr R-1 cohort the project would need a WS recorder running for the full 2.4yr backlook period — which is structurally impossible from a 2026-05-19 starting point.

### Mode 4 — Mint infrastructure has no pre-existing recorder

`ssh mint` audit (clean state, 0 research processes running):
- `find /home/hcpark /opt -name '*.py' | xargs grep -l 'forceOrder\|liquidation_recorder\|!forceOrder'` → empty
- `pm2 list | grep -iE 'liquid|force|cascade|recorder'` → empty
- `ps -ef | grep -iE 'recorder|forceorder'` → empty

No ambient forceOrder WS recorder exists on Mint that could be retroactively backfilled.

## Why this is `DISPATCH_IMPOSSIBLE` (not `SAMPLE_INSUFFICIENT`)

Per lesson #28 (`project_paradigm_listing_pre_announce` precedent — BILLUSDT pre-onboard HTTP 404 verified, paradigm 89), substrate-absence at the entry-side event time is categorically distinct from sample-density failure. The hypothesis is well-formed and the universe is well-defined; the issue is that **no measurement substrate exists at any historical timestamp** for the liquidation event itself. Lesson #11 prescreen is moot when n_substrate_observable = 0 by construction.

Distinction from sibling paradigms that *do* dispatch:
- paradigm 22 funding carry → funding rate has daily history archive (`monthly/fundingRate/`) ✅
- paradigm 24 premium z-score → `premiumIndexKlines/` ✅
- paradigm 69 BTC RV highvol → 1m OHLCV joblib cache ✅
- `binance_cascade_reversal_source.py` → proxies cascade via taker_skew × OI_chg × ret_std (not real liquidation feed) — composer source layer, not paradigm-grade measurement

Paradigm 100 candidate as scoped (real liquidation notional event, 4-quadrant direction split) requires a substrate that the public Binance data ecosystem does not expose historically.

## Mirror-hypothesis antipattern check (lesson #8)

This is not a paradigm 22 / 69 / 87 mirror swap — it is a substrate-class new candidate. Antipattern not triggered. The DISPATCH_IMPOSSIBLE verdict is a substrate finding, not a mirror reflexive trial.

## Family-distinct claim — was it valid?

The "immediate forced flow" lesson #27 amendment classification holds in principle (margin liquidation IS immediate, distinct from delisting forced-exit lag). The hypothesis was not class-degenerate. **Family-distinct ≠ dispatchable** — lesson #28 substrate availability is an independent prescreen orthogonal to lesson #27 entry-side timing class.

## Recommended follow-ups (not auto-dispatched — user gate)

Three pathways exist for resurrecting this hypothesis. All require user approval before any compute commitment:

1. **Forward-collection (lesson-#28-compliant)**: Stand up a Mint PM2 service to record `!forceOrder@arr` WS into Postgres (table schema: `ts, symbol, side, qty, price, notional_usdt`). After 60-90d accumulation, run R-1 on the recorded cohort. Forward-only, no historical claim. Trade-off: 60+d wait, sub-universe coverage if WS reconnect gaps.

2. **Proxy-paradigm scope-shift**: Reframe as "synthetic cascade detection" — the existing `binance_cascade_reversal_source.py` heuristic (ret < -2σ AND OI_chg < -1.5σ AND taker_skew < -0.3) is already deployed as a composer source. Promoting this to paradigm-grade would require treating it as an independent paradigm (different DNA: no liquidation source, instead multi-axis confluence). This is composer-source axis-stacking (lesson #21 cautionary) and a separate hypothesis, not a rescue of paradigm 100 candidate.

3. **Third-party paid feed**: Coinglass / Hyblock / Laevitas all sell aggregated liquidation history. **Blocked by `[[feedback_no_freemium_trial]]`** — all three are freemium upgrade-pressure platforms. Not pursuable under current policy.

Option 1 is the only family-distinct, policy-compliant pathway. It is a 60-90d infrastructure investment, not a 2026-05-19 dispatch.

## Lesson grid postmortem

| Lesson | Status |
|---|---|
| #11 sample density | Moot — substrate absence dominates |
| #16 Concentration Gate | Not measured (R-1 not dispatched) |
| #19 Symmetric Negative Test | Defined in spec, not measured |
| #20 narrow-scope | N/A |
| #21 axis stacking | N/A (was single-axis) |
| #22 stateful CP frame freq | N/A |
| #23 boundary cycle sparse | N/A |
| #24 horizon density | N/A |
| #26 temporal WF | N/A |
| #27 amendment immediate vs delayed | Passed in classification |
| **#28 substrate availability** | **FAIL — 4 independent failure modes (vision archive / metrics schema / REST deprecated / Mint no recorder). 5th dogfood of lesson #28 (precedents: paradigm 89 listing_pre_announce + paradigm 90 stablecoin_mint sub-mode). Decisive prescreen** |
| #29 cross-proxy | N/A (single-axis) |
| #30 short-data verdict | N/A |
| #31 DNA inventory | Passed (no prior liquidation paradigm in INDEX) |

## Artifact paths

- This graveyard: `backend/runs/research_track/graveyard__binance_perp_liquidation_cascade_event_alt_intraday.md`
- No R-1 script generated (R-0 halt)
- No metrics.json (R-1 not run)
- Cleanup: 0 mint research processes running (verified `ssh mint "ps -ef | grep python3.*research" | wc -l` → `0`)

## Recommended Q3 queue update (informational, user-gated)

Q3 §1 #1 "liquidation cascade event paradigm" entry should be annotated:
> Substrate-blocked at R-0 (lesson #28 5th dogfood). Public Binance feed has no historical liquidation data at any cadence. Forward-collection (option 1 above) is the only compliant resurrection path — 60-90d WS recorder accumulation required before re-dispatch. Not a 2026-Q2/Q3 candidate.

This is a meta-finding: among the "Q3 §1 top candidates", the strongest-claim entry (liquidation cascade) is structurally undispatchable on current public infrastructure. This concentrates Day 7 / Day 30 baseline-mode commitment further (no high-confidence alternative R-1 candidate readily available pre-2026-05-21).
