# Graveyard: cross_exchange_funding_spread_binance_bitget_alt_directional_8h_illiquid_venue

- **Paradigm number**: 105
- **Phase halted**: R-0 substrate prescreen (R-1 NOT executed)
- **Verdict**: DISPATCH_IMPOSSIBLE
- **Date**: 2026-05-19 KST
- **Host**: WSL local (Mint operating server — staged for orchestrator commit)

## One-sentence

Bitget/Gate.io public funding history substrate insufficient (Bitget V2 hard-capped 100 rows / 33d; Gate.io auth-gated; OKX ~90d) to construct ≥1y Binance−Bitget alt-perp funding spread series — cross-exchange family path #1 (illiquid venue mid-tier arbitrage hypothesis) falsified at substrate layer before R-1 dispatch.

## Family-distinct exception axis exercised

Per paradigm 103 graveyard verdict §"향후 family-distinct path #1": Bitget is ~5-15x smaller than Binance on alt perp volume → if Bitget public funding history available ≥1y → spread persistence test viable. **Public Bitget endpoint substrate test FAIL — path #1 falsified pre-execution.**

## 5-axis novelty matrix (reconfirmed)

| Axis | Status | Note |
|---|---|---|
| Data source | NOVEL | Bitget V2 untested in 104 paradigms |
| Statistic | known | spread + z-score |
| Time scale | known | 8h cycle |
| Universe | NOVEL | mid-liquidity venue pairing |
| Mechanism | NOVEL | inefficient venue arb → spread persistence |

3/5 NOVEL passed. **Novelty did not protect against substrate failure** — Lesson #28 5-axis-NOVEL is independent of substrate availability (confirmed pattern from paradigms 84/85/89 substrate halts).

## Substrate audit summary

| Venue | Endpoint | Max window | Auth required | Verdict |
|---|---|---|---|---|
| Bitget V2 | `/api/v2/mix/market/history-fund-rate` | **33 days / 100 rows hard-cap** | No | INSUFFICIENT |
| Bitget V1 | `/api/mix/v1/market/history-fundRate` | (decommissioned) | – | UNUSABLE |
| Gate.io V4 | `/api/v4/futures/usdt/funding_rate/{c}` | n/a | **Yes (HTTP 401)** | BLOCKED freemium policy |
| OKX V5 | `/api/v5/public/funding-rate-history` | ~90 days | No | INSUFFICIENT |

All four exhausted via pageSize/pageNo/endTime/startTime/idLessThan/after-cursor probes. Bitget V2 `endTime` parameter accepted but **ignored** (always returns 100 most-recent rows regardless of value). OKX after-cursor walk-back functional but window terminates ~90d back.

## Lesson #11 sample density projection (if forced 33d run)

- universe = 7 syms
- cycles = 3/day × 33d × 7 = 693 total
- expected triggers @ p90 = ~69
- 4-quadrant × 4-quarter split = 16 cells → 4.3 per cell ≪ Lesson #11 cutoff 30

**Pre-execution Lesson #11 FAIL.**

## Lesson #30 data window ratio

- Bitget overlap window: 33d
- Binance funding full window: ~912d (2.5y)
- Ratio: **3.6% ≪ 30% advisory threshold**

**Even if executed, verdict would be advisory-only and non-actionable** for Tier 4 retire decision.

## Empirical |spread_bp| distribution prescreen (Lesson #34) — NOT MEASURED

Substrate fail blocks measurement. Cannot verify whether illiquid venue premise (p99 ≥ 16bp) holds or falsifies. **Premise remains untestable via public no-auth feeds.**

## Cross-paradigm comparison table (cross-exchange family complete)

| Paradigm | Venue pair | Axis | Substrate result | R-1 verdict | Fail mode |
|---|---|---|---|---|---|
| 103 | Binance × Bybit | funding rate spread | Both 2y available | BROAD_FALSIFIED | fee-trap (p99=3bp ≪ 16bp fee floor; top-tier arb compression) |
| 104 | Binance × Bybit | OI delta spread | Both 2y available | BROAD_FALSIFIED | **classified: fee-trap (Lesson #35 candidate 1st application — gross < fee for all 4 quadrants)** |
| **105** | **Binance × Bitget** | **funding rate spread** | **Bitget hard-cap 33d** | **DISPATCH_IMPOSSIBLE** | **substrate-time-dimension absent (Lesson #28)** |

**Cross-exchange family coverage: 3/3 attempts fail. Tier 4 formal retire justified.**

## Lesson #28 5th dogfood (paradigms 89/100/105 + lesson #27 amendment 4th in stablecoin_mint 90)

Substrate-availability prescreen catalog event — independent of mechanism novelty / statistic novelty / universe novelty. Lesson #28 amendment refined: substrate-time-dimension (historical depth) is independent failure mode from substrate-existence-dimension (data exists at event time). Paradigm 89 was substrate-existence-FAIL. Paradigm 105 is substrate-time-FAIL. Both DISPATCH_IMPOSSIBLE category.

## Lesson #35 candidate (proposed in paradigm 104) — NOT TESTABLE here

Paradigm 105 substrate FAIL means R-1 was never executed → Lesson #35 fee-trap/pool-drift/both/neither triage not applicable. **Lesson #35 remains candidate (1 dogfood from paradigm 104 only — needs 2nd application before confirmation).**

## Family retire recommendation

**Cross-exchange funding/OI spread family — Tier 4 formal retire**:
- 3 paradigm attempts: 103 (rate top-tier), 104 (OI top-tier), 105 (rate mid-tier substrate)
- 3 distinct fail modes covered (fee-trap × 2, substrate × 1)
- Only remaining unexplored axis = paid feed (Kaiko/Amberdata) for ≥1y Bitget/Gate.io/OKX history → **BLOCKED by freemium policy**
- Bitget WS recorder forward-collection (similar to paradigm 80 5m premium delta) would require **60+ days accumulation before re-testable** → not actionable in 2026 Q2/Q3 campaign window

Family retire effective immediately. Re-open trigger: paid feed policy change OR Bitget public endpoint depth restored to ≥1y OR forward-WS-collection ≥1y matured.

## Lessons stamped

- **Lesson #11**: sample-density prescreen — projected 4.3/cell ≪ 30 cutoff (8th confirmed application)
- **Lesson #28**: substrate-time-dimension audit (5th dogfood — refined w/ amendment for historical depth)
- **Lesson #30**: data window ratio 3.6% ≪ 30% advisory cutoff (3rd dogfood application)

## Cross-references

- Parent: paradigm 103 graveyard (Binance×Bybit rate) — path #1 hypothesis source
- Sibling: paradigm 104 graveyard (Binance×Bybit OI) — Lesson #35 candidate seed
- Family-graveyard predecessor pattern: paradigm 89 (listing_pre_announce substrate-existence) + paradigm 90 (stablecoin_mint Lesson #27 amendment)

## Next action

1. **Orchestrator**: commit substrate_audit JSON + this graveyard MD to Mint repo
2. **PARADIGM_QUEUE_2026Q3.md** §6.2 lessons: stamp Lesson #28 5th dogfood + Lesson #11 8th + Lesson #30 3rd
3. **INDEX.json**: register paradigm 105 → graveyard / DISPATCH_IMPOSSIBLE
4. **Family retire log**: append cross-exchange family Tier 4 with the 3-attempt audit table above
5. **Campaign next**: Lesson #35 still needs 2nd dogfood (paradigm 104 only application so far) — defer confirmation until next non-cross-exchange family dispatch triages a FAIL
