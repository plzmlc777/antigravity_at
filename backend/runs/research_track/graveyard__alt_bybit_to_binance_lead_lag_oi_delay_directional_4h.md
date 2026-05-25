# Paradigm 147 — `alt_bybit_to_binance_lead_lag_oi_delay_directional_4h` GRAVEYARD

**Verdict**: `INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION` (R-0 inventory prescreen, R-1 not executed)
**Date**: 2026-05-21 13:50 KST
**Phase**: R-0 prescreen (pre-execution halt)
**Sequence**: 147 (v2 — time-shift dimension pivot after v1 same-bar inventory-halt with DNA 6/6 duplicate paradigm 104)
**Compute avoided**: ~35 min total (15-30 min Bybit/Binance OI backfill + ~5 min R-1 compute)

## TL;DR

paradigm 147 v2 proposed time-shift dimension (Δ ∈ {15,30,60,120}min lead-lag) as novel substantive pivot from v1 same-bar variant (which inventory-halted DNA 6/6 duplicate paradigm 104). R-0 substantive family-distinct gate analysis reveals the hypothesis is a **composite of two already-falsified mechanism families**:

1. **Trigger axis** (`|Bybit_OI_velocity_z|>2.0`) = identical mechanism to **paradigm 71** graveyard — single-exchange OI velocity z trigger proven anti-alpha (BTC OI z=2.5 → -12.62bp), OI velocity carries NO directional information.
2. **Substrate composition** (cross-exchange OI Bybit↔Binance) = identical mechanism family to **paradigm 104** graveyard — candidate-pool upward-bias trap at primary 4h hold (gross +25.70bp but perm_p=0.988 structurally inescapable).
3. **Time-shift Δ axis** = refinement filter, NOT novel mechanism class. Lesson #56 4-instance formal CONFIRMED criterion: "statistic reformulation of confirmed-falsified family does not constitute mechanism class novelty; 6th-instance trap indicator". paradigm 147 v2 IS the 6th-instance trap dogfood.

Per Lesson #54 (axis stacking sub-finding, 3 dogfoods CONFIRMED) + Lesson #21 confirmed bidirectional (6 dogfoods): axis stacking does NOT synthesize alpha from zero-information trigger axis. Sign-alignment-at-t+Δ filter cannot rescue a falsified trigger.

**HALT decision**: substantive R-0 family-distinct gate FAIL precedes substrate backfill commitment — 0 seconds compute committed, ~35 min compute avoided.

## R-0 substantive family-distinct gate (the binding constraint)

### Claim under test
Time-shift dimension (Δ>0) constitutes genuine mechanism class novelty separating paradigm 147 from paradigm 104 (Δ=0) and paradigm 71 (single-exchange OI velocity).

### Counter-analysis

| Component | paradigm 147 v2 element | Already-falsified by | Verdict |
|---|---|---|---|
| Trigger statistic | `\|Bybit_OI_velocity_z\| > 2.0` | **paradigm 71** (BTC OI velocity z=2.5 → -12.62bp anti-alpha) — OI velocity contains no directional info | FAIL |
| Substrate composition | Cross-exchange Binance↔Bybit OI | **paradigm 104** (oi_diff_z primary 4h hold perm_p=0.988 upward-bias trap, structural pool drift) | FAIL |
| Refinement axis | Sign-alignment at t+Δ (Bybit_sign == Binance_sign) | Lesson #54 + #21 — axis stacking does not synthesize alpha from zero-info trigger | FAIL |
| Time-shift Δ | {15,30,60,120}min lead-lag sweep | Lesson #56 4-instance CONFIRMED — statistic reformulation antipattern | FAIL |

### Asian-retail-front-running mechanism premise audit
The hypothesis cites "Bybit retail flow leads Binance institutional flow" as the alpha mechanism. Pre-execution audit:
- **Unverified ex ante**: no prior paradigm has substantiated cross-exchange retail-vs-institutional lead-lag in this universe.
- **Wrong substrate channel**: if the premise is real, the alpha would manifest first in PRICE lead-lag (Bybit price t leads Binance price t+Δ), then OI as second-derivative lagging indicator. OI velocity lead-lag is double-derivative — any embedded signal compressed below fee floor by the time it materializes.
- **Pool drift unchanged**: paradigm 104's candidate-pool perm_p trap operates on forward returns regardless of which exchange's OI triggered selection. Narrowing the trigger subset via time-shift filter does NOT de-correlate observed returns from pool drift. perm_p will remain >> 0.10 at 4h hold (structural).

## Substrate audit (Lesson #28)
- Binance OI 1h cache: **MISSING locally** (paradigm 104 graveyard reports as Mint server permanent asset; local agent env stale per [paradigm-architect local context] memory)
- Bybit OI 1h cache: **MISSING locally** (Bybit V5 REST openInterest cursor pagination not yet local-backfilled)
- OHLCV 1m cache: present
- Backfill ETA local: 15-30 min (borderline halt threshold but feasible)
- **Substrate availability is NOT the binding constraint** — substantive R-0 family-distinct gate FAIL precedes compute commitment

## Lesson grid application

| Lesson | Status | Note |
|---|---|---|
| #11 sample density | would-PASS | 7 syms × 2.5yr × |z|>2(~5%) × align(~50%) ≈ 3000-5000 events/variant ≥ 30/cell |
| #19 4-quadrant SNT × Δ sweep | would-apply | 16 cells total (4 quadrants × 4 Δ) |
| #21 axis stacking | **FAIL detection** | Trigger axis (paradigm 71 falsified) + alignment filter = stacking on zero-info base |
| #28 substrate audit | borderline | Backfill feasible but not binding |
| #30 data window ratio | =1.000 | Full overlap window |
| #40 threshold attainability | would-PASS | |z|>2 attainable bidirectional |
| #44 amendment 31st xref | **DOGFOOD** | paradigms 71+103+104+21 family enforced |
| #46 stratified n=50×4q | would-apply | But blocked by upstream Lesson #56 detection |
| #54 axis stacking sub-finding | **FAIL detection** | 3 dogfoods CONFIRMED — sign-align filter cannot synthesize alpha |
| #56 statistic reformulation 6th-instance | **FAIL detection** | 4 instances CONFIRMED formal; paradigm 147 v2 IS the 6th-instance trap dogfood |
| #58 cross-substrate exemption | NOT APPLICABLE | Exemption is for OI-vs-PRICE class (paradigm 21), not OI-vs-OI same-substrate-different-venue |

## Cross-paradigm 71 + 104 + 21 R-5 distinction enforcement

| Paradigm | Mechanism class | Outcome | Distinguishing axis vs paradigm 147 v2 |
|---|---|---|---|
| 71 (`btc_oi_velocity`) | Single-exchange OI velocity z trigger | Graveyard (anti-alpha) | None — paradigm 147 trigger axis identical mechanism |
| 103 (`cross_exchange_funding_spread`) | Cross-exchange funding spread | Graveyard (fee floor) | Different statistic axis (funding not OI), same family-falsified outcome |
| 104 (`cross_exchange_oi_level_differential`) | Cross-exchange OI level differential same-bar | Graveyard (upward-bias trap perm_p=0.988) | None — paradigm 147 same substrate, just time-shift refinement |
| 21 (`oi_price_decoupling`) R-5 LIVE | Single-exchange OI-vs-PRICE 5m decoupling | R-5 seeded exception | Single-exchange (not cross), OI-vs-PRICE (not OI-vs-OI), 5m frame (not 1h) — paradigm 147 inherits NONE of these distinguishing features |

## Verdict tree applied

```
R-0 substrate audit
  └─ backfill feasible (15-30min within halt limit) → continue evaluation
       └─ R-0 substantive family-distinct gate
            ├─ Trigger axis = paradigm 71 family → FAIL
            ├─ Substrate composition = paradigm 104 family → FAIL  
            ├─ Refinement (Δ shift) = Lesson #56 6th-instance trap → FAIL
            └─ Composite verdict: INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION
                 → R-1 dispatch BLOCKED
                 → counter 147 advanced (substantive attempt warrants graveyard entry, distinct from v1 DNA-duplicate inventory-halt)
                 → compute committed: 0s
                 → compute avoided: ~35 min (backfill 15-30 + R-1 ~5)
```

## Lessons confirmed/observed in this R-0

### Lesson #56 5th-instance formal CONFIRMED (statistic reformulation 6th-instance trap)
paradigm 147 v2 is the **5th formal instance** of the "statistic reformulation of confirmed-falsified family" antipattern after the 4 instances that earned Lesson #56 formal CONFIRMED 자격. With this 5th instance, Lesson #56 advances from "4 instances CONFIRMED 자격" to **formal CONFIRMED — 5 instances cumulative**. Recommend formal status promotion in Q3 lesson index.

Refinement axes that DO NOT count as mechanism class novelty:
- Time-shift Δ on already-falsified trigger axis (paradigm 147 v2 dogfood)
- Threshold relaxation (z=2.0 instead of z=2.5)
- Universe expansion (deep-7 → deep-14) on falsified composite
- Hold-period sweep on perm-trapped substrate
- Sign-alignment filter on zero-info trigger axis

### Lesson #54 4th dogfood (axis stacking sub-finding bidirectional)
3 dogfoods previously CONFIRMED bidirectional. paradigm 147 v2 = **4th dogfood** — stacking (Bybit OI velocity z trigger) + (sign-alignment-at-t+Δ filter) cannot synthesize alpha from a zero-info trigger axis. Particularly when the trigger axis is identically the paradigm 71 graveyard mechanism on a different venue.

### Lesson #44 31st cross-reference xref dogfood (cumulative)
Cross-reference grid: paradigm 71 (BTC OI velocity anti-alpha) + paradigm 103 (cross-exchange funding fee floor) + paradigm 104 (cross-exchange OI same-bar upward-bias trap) + paradigm 21 R-5 (single-exchange OI-vs-PRICE decoupling exception). 31st xref enforces family-distinct gate BEFORE R-1 compute commitment — saves ~35 min wall-clock.

### Composite-family-falsification verdict class formalization
**NEW verdict category candidate**: `INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION` — distinct from:
- `INVENTORY_HALT` (DNA 5/6 or 6/6 single-paradigm duplicate, counter NOT advanced)
- `BROAD_FALSIFIED` (R-1 executed, all 4 quadrants net<0)
- `SAMPLE_INSUFFICIENT` (Lesson #11 prescreen)
- `DISPATCH_IMPOSSIBLE` (Lesson #28 substrate absent)

**Distinguishing feature**: hypothesis is a NEW composite combination (not a single-paradigm duplicate) but the COMPONENTS are individually already-falsified families. Counter IS advanced (substantive attempt warrants graveyard entry for future cross-reference) but R-1 compute is NOT committed (composite-falsification verdict structurally precedes pool/perm artifact analysis).

Recommend formal verdict category addition to paradigm-architect spec. First dogfood: paradigm 147 v2.

## Cross-exchange OI family Tier 4 strengthening recommendation

After paradigms 103 + 104 + 147 v1 (DNA-duplicate inventory-halt) + 147 v2 (composite-family-falsification), the cross-exchange OI/funding axis is **structurally exhausted at 1h+ frame, deep-7 universe**:

| Sub-path | Outcome | Status |
|---|---|---|
| Path #1 (illiquid venue funding arb) | Untouched | Cross-exchange family Tier 4 advisory caution, untested |
| Path #2 (lead-lag funding rate) | paradigm 103 graveyard | BROAD_FALSIFIED_FEE_FLOOR |
| Path #3 (OI level differential same-bar) | paradigm 104 graveyard | BROAD_FALSIFIED_PRIMARY_HOLD (perm trap) |
| Path #4 (OI level same-bar refinement) | paradigm 147 v1 | INVENTORY_HALT_DNA_DUPLICATE |
| Path #5 (OI velocity lead-lag time-shift) | paradigm 147 v2 (this graveyard) | INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION |

**Recommendation**: Cross-exchange OI/funding family **formal Tier 4 retire** with documented exception only for paradigm 21 R-5 (single-exchange OI-vs-PRICE class, structurally distinct). Future Bybit-substrate hypotheses must be genuinely new mechanism class (e.g. cross-exchange PRICE lead-lag with axis-stacking warning, cross-exchange liquidation cascade with substrate prescreen) — NOT refinements on OI/funding base.

## Resources committed
- **R-0 prescreen artifact**: `backend/runs/research_track/alt_bybit_to_binance_lead_lag_oi_delay_directional_4h/r0_prescreen.json`
- **Graveyard report**: this file
- **R-1 script**: NOT generated (substantive R-0 verdict precedes script generation)
- **Substrate backfill**: NOT executed (~35 min compute avoided)
- **Wall-clock R-0 analysis**: ~3 min

## Next-action recommendation

1. **HALT paradigm 147 v2 at R-0** with formal `INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION` verdict.
2. **Counter advance**: 146 → 147 (substantive attempt warrants graveyard entry distinct from v1 inventory-halt).
3. **Lesson #56 formal CONFIRMED promotion**: 4 → 5 instances cumulative. Update Q3 lesson index.
4. **Cross-exchange OI/funding family formal Tier 4 retire** with paradigm 21 R-5 exception only.
5. **NEW verdict category**: `INVENTORY_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION` formal addition to paradigm-architect spec verdict tree. First dogfood paradigm 147 v2.
6. **Priority pivot**: Day 7 baseline 2026-05-28 (D-7) for paradigm 127+128 Mint deploy measurement. Continued R-1 dispatch on composite-falsified candidates lower expected value than active R-5 LIVE measurement.

## Next candidate recommendation

Given persistent composite-family-falsification pattern in the cross-exchange axis (4 cumulative graveyards 103+104+147v1+147v2), recommend pivoting candidate selection to **genuinely-unexplored axes** for paradigm 148:

**Option A (recommended)**: Liquidation cascade single-exchange Binance — paradigm 21 R-5 family but with liquidation event as anchor (not OI level). Liquidation substrate available locally (forceOrders archive). Single-exchange (no cross-venue trap), event-anchored (substrate availability bounded, Lesson #28 prescreen needed).

**Option B**: Cross-exchange PRICE lead-lag (NOT OI lead-lag) — Bybit price velocity z[t] → Binance price velocity z[t+Δ]. Different substrate axis than paradigm 147 v2 (price not OI), tests Asian-retail-front-running premise directly. Lesson #21 axis stacking warning still applies — must be SINGLE axis.

**Option C** (lower priority): 4h candle session boundary anomalies (06/12/18/00 UTC) — distinct from paradigm 85 5min boundary (different substrate frame), distinct from paradigm 104 substrate (OHLCV not OI). May qualify as substrate-distinct without composite trap.

Pivot rationale: 18-streak non-PASS (paradigms 129-147) confirms diminishing returns on R-1 dispatch in heavily-explored axes. paradigm 148 candidate selection should explicitly target axes with ≤2 prior graveyards.
