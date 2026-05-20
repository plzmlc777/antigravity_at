# Graveyard — paradigm 122 (candidate, INVENTORY_HALT no counter increment) `liquidation_cascade_post_capitulation_alt_directional_30m_x_45m`

- **Verdict**: `DISPATCH_IMPOSSIBLE_DUPLICATE_PARADIGM_100`
- **Phase halted**: R-0 substrate availability + R-0 inventory duplicate check (R-1 not dispatched, ~2 min wall-clock, 0 LOC, 0 MB)
- **Date**: 2026-05-20 19:32 KST (continuous-parallel policy, D-13 to Day 30 baseline)
- **Counter**: INVENTORY_HALT (counter remains 121, paradigm 122 slot available for next dispatch — per [[project_paradigm_97_funding_dispersion_inventory_halt]] precedent)
- **Lesson reference**: #28 (substrate availability prescreen) — **6th dogfood**; #44 (R-0 inventory check vs graveyards) — should-have-caught miss

## Hypothesis (recap)

BTC perp 5min liquidation notional cluster (>50M USD) with LONG_USD/total > 60% directional dominance (capitulation marker) → 30min cooloff window → 13 alt cohort 45min LONG (mean-revert hypothesis), 4-quadrant SNT (A focus capitulation revert / A mirror continuation / B squeeze continuation / B revert).

## R-0 substrate verification — three independent failure modes (identical to paradigm 100)

### Mode 1 — `data.binance.vision` daily archive does NOT publish liquidation feed

Probed `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data/futures/um/daily/&delimiter=/`. Complete subdirectory tree:

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

**No `liquidationSnapshot/` or `forceOrders/` directory exists.** Both `HEAD https://data.binance.vision/data/futures/um/daily/liquidationSnapshot/BTCUSDT/BTCUSDT-liquidationSnapshot-2025-05-15.zip` and `HEAD .../forceOrders/...` return `HTTP/2 404`.

### Mode 2 — Monthly archive also lacks liquidation feed

`https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?prefix=data/futures/um/monthly/&delimiter=/`:

```
aggTrades, bookTicker, fundingRate, indexPriceKlines, klines,
markPriceKlines, premiumIndexKlines, trades
```

Monthly `fundingRate/` exists (paradigm 22 substrate) but no liquidation aggregation at any cadence.

### Mode 3 — REST `allForceOrders` permanently retired; WS `!forceOrder@arr` live-only

```
GET https://fapi.binance.com/fapi/v1/allForceOrders?symbol=BTCUSDT&limit=10
→ HTTP 200 with body: {"code":400,"msg":"The endpoint has been out of maintenance"}
```

Identical to paradigm 100 finding (2026-05-19). The historical public `allForceOrders` endpoint is permanently deprecated. WebSocket `!forceOrder@arr` is live-only — 2.4yr backlook from 2026-05-20 start is structurally impossible.

### Mode 4 — `metrics/` archive does NOT contain liquidation columns

Schema unchanged from paradigm 100 verification (2026-05-19): 8 columns are OI + L/S ratios + taker buy/sell ratio only. No liquidation notional, no forced-liquidation count.

## Duplicate paradigm check (Lesson #44 R-0 inventory gap)

paradigm 100 `binance_perp_liquidation_cascade_event_alt_intraday` was already DISPATCH_IMPOSSIBLE on 2026-05-19 KST (T-1 day) with **identical substrate diagnostics**.

| DNA dimension | paradigm 100 (2026-05-19) | paradigm 122 (2026-05-20) | Overlap |
|---|---|---|---|
| Trigger substrate | BTC perp liquidation notional 5min cluster | BTC perp liquidation 5min cluster >50M | **identical** |
| Universe | 14-sym fast-track sub-universe | 13 alt cohort (paradigm 119/120 universe) | **near-identical** |
| Decision mode | 4-quadrant SNT (long_liq×LONG / SHORT / short_liq×LONG / SHORT) | 4-quadrant SNT (capitulation revert / continuation / squeeze / revert) | **identical** |
| Data dependency | forceOrders / liquidationSnapshot | forceOrders / liquidationSnapshot | **identical** |
| Time scale | 5min trigger × hold sweep 5/15/60/240m | 5min trigger × 30min cooloff × 45min hold | **near-identical (parameter variant only)** |
| Paradigm DNA | 6/6 substrate-class match | 6/6 substrate-class match | **exact duplicate substrate-class** |

The 30min cooloff + 45min hold parameter variation does NOT address the fundamental substrate absence. The cooloff window cannot be applied to non-existent data.

## Why this is `DISPATCH_IMPOSSIBLE_DUPLICATE_PARADIGM_100` (not standalone DISPATCH_IMPOSSIBLE)

paradigm 100 graveyard from 2026-05-19 explicitly enumerates 4 independent substrate failure modes. paradigm 122 candidate hypothesis depends on the **same substrate** (BTC perp forced-liquidation notional, historical) which remains unavailable as of 2026-05-20 (T+1 day, no architectural change to Binance public data ecosystem). The candidate should have been pre-filtered at R-0 inventory check (Lesson #44).

This is a **Lesson #44 R-0 inventory check miss** — the candidate-dispatch upstream (PM-track) failed to cross-reference paradigm 100 graveyard before promoting paradigm 122 to R-1 queue. Substrate-class duplicates within 1-day window represent a triage gap.

## Counter assignment policy

Per [[project_paradigm_97_funding_dispersion_inventory_halt]] precedent (paradigm 97 candidate funding_term_structure_cross_sym_dispersion R-0 inventory halt 2026-05-19, counter not incremented, slot reassigned to next family-distinct batch P1):

- paradigm counter remains **121** (paradigm 121 `hmm_realized_vol_state_x_markprice_basis_extreme` 2026-05-20 17:21 KST BROAD_FALSIFIED_LESSON39_SYMMETRIC)
- paradigm 122 slot **available** for next family-distinct candidate (NOT a liquidation substrate-class re-dispatch)

## Lesson #28 — 6th confirmed dogfood

Prior dogfoods:
1. paradigm 87 `binance_delisting_announce_short_alt` — initial Lesson #28 development context (2026-05-18)
2. paradigm 89 `listing_pre_announce` — DISPATCH_IMPOSSIBLE BILLUSDT pre-onboard 404 (2026-05-18)
3. paradigm 90 `stablecoin_mint` — multi-mode HALT including substrate (2026-05-18)
4. paradigm 100 `binance_perp_liquidation_cascade_event_alt_intraday` — DISPATCH_IMPOSSIBLE (2026-05-19)
5. paradigm 103 `cross_exchange_funding_spread` — substrate verified PASS but BROAD_FALSIFIED_FEE_FLOOR (Bybit V5, 2026-05-19, partial dogfood — substrate prescreen succeeded but R-1 failed downstream)
6. **paradigm 122 (this) — substrate-class duplicate of paradigm 100, 6th confirmed dogfood with explicit duplicate-detection sub-finding**

## Lesson #44 — R-0 inventory check candidate strengthening

Lesson #44 (CONFIRMED 자격 from earlier dogfoods) is dogfooded again here with a **negative case sub-finding**: even when Lesson #44 is in the active prescreen checklist, candidate-dispatch upstream layer (PM-track) can still emit substrate-duplicate candidates within 1-day window. The fix is upstream:

- **Proposed amendment**: candidate-dispatch upstream MUST scan `backend/runs/research_track/graveyard__*.md` for substrate-class keyword overlap (`liquidation`, `forceOrders`, `book_depth`, etc.) within last 30 days before promoting a candidate to R-1 queue.
- **Trigger condition**: substrate string match + DNA dimension overlap ≥4/6 → auto-decline at candidate-emission layer, not at architect R-0 layer.

This is a candidate strengthening of Lesson #44 (not a new lesson), pending §6.18 queue update.

## Mirror-hypothesis antipattern check (Lesson #8)

paradigm 122 is NOT a mirror of paradigm 100 — both candidates are LONG-side (capitulation mean-revert hypothesis in both). This is substrate-class identity, not direction-mirror. Lesson #8 antipattern not triggered.

## Resource cost

- **Wall-clock**: ~2 minutes (4 substrate probes + duplicate check)
- **LOC written**: 0 (R-1 script not generated)
- **Data downloaded**: 0 MB
- **Permanent assets created**: 0 (no new substrate verified, no cache populated)

Cost-efficient halt confirms Lesson #28 + #44 architectural value.

## Next candidate recommendation (1 candidate, family-distinct from liquidation substrate-class)

### Recommendation: `intraday_session_open_alt_oi_acceleration_directional_30m`

- **Trigger**: 13 alt cohort 5min OI velocity z-score top-decile at **CME equity close window (21:00 UTC ±15min)** AND BTC funding-cycle anchor (00:00/08:00/16:00 UTC ±5min wrap)
- **Mechanism**: dual-anchor temporal liquidity transition + OI velocity confirmation, alt cohort 30min hold directional matched to OI velocity sign
- **Substrate**: 100% archive-direct (klines + metrics OI columns, both verified abundant in paradigm 22/24/69/71 history)
- **Family-distinct verification**:
  - Lesson #45 invalidation: NO HMM / unsupervised decomposition — explicit anchor windows
  - Funding family Tier 4 retire: anchor uses **timing** of funding cycle (boundary clock), not funding rate magnitude/sign (paradigm 73/79/96-99 retire axis) — orthogonal
  - 5m microstructure single-domain advisory caution: dual-anchor (temporal CME-close × funding clock) is cross-domain (calendar × cycle), not single-domain microstructure
  - paradigm 85 `pre_session_open_oi` reference: that was DAILY 00:00 UTC × 5min OI velocity 1-2% trigger rate SAMPLE_INSUFFICIENT. This candidate dual-anchors (CME close + funding) which compounds liquidity transition signal, AND empirical OI velocity top-decile (not absolute level threshold) which targets ~10% trigger rate.
- **Lesson #11 prescreen estimate**: 2.4yr × 365d × 3 funding cycles × 5min CME-close window × 13 alts × top-decile OI velocity ≈ 2.4 × 365 × 3 × 0.1 × 13 ≈ 3,400 events. Per-cell n ≥ 200 expected.
- **Lesson #44 inventory cross-check**: NOT a duplicate of paradigm 85 (single-anchor daily) or paradigm 22 (funding magnitude). Cross-check vs paradigm 119/120/121 axes (BTC RV / markprice basis / HMM RV state) — all distinct.

This candidate would be the immediate next dispatch slot **after** PM-track confirms candidate-dispatch upstream Lesson #44 strengthening is applied OR user explicitly approves bypass.

---

**Bottom line**: paradigm 122 candidate is a substrate-class exact duplicate of paradigm 100 (T-1 day, same substrate absence, same 4-quadrant SNT scope). 2-minute R-0 inventory halt, no counter increment, slot remains 122 available. Lesson #28 6th dogfood + Lesson #44 candidate-dispatch upstream strengthening identified.
