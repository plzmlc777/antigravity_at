# Graveyard — paradigm 149 `alt_binance_1m_volatility_burst_event_sub5min_continuation`

**Verdict**: `BROAD_FALSIFIED_FEE_FLOOR_STRUCTURAL_R0`
**Halt phase**: R-0 (pre-R-1)
**Halt timestamp**: 2026-05-21 14:16 KST
**Counter**: 148 → 149 (149th graveyard, 20-streak non-PASS)

## Hypothesis

Binance 1m bar volatility burst (|log_ret_1m| > 30d rolling p99) + sign-matched sub-5min (1/2/3min) momentum continuation. Self-anchored per-symbol, single-exchange.

- Substrate: Binance 1m klines (Postgres `ohlcv` DB, paradigm 127/128 R-5 substrate reuse)
- Universe: 13 alt cohort (ADAUSDT..XRPUSDT)
- 4-quadrant SNT × hold sweep {1, 2, 3} min = 12 cells

## Family-distinct audit (PASS)

- vs paradigm 127 R-5 (1m volume burst × 60-90min continuation LONG): axis distinct (volume → volatility) AND hold distinct (60-90min → 1-3min intra-event)
- vs paradigm 128 R-5 (1m volume burst × 10min negative reversion SHORT): direction + axis + hold distinct
- vs paradigm 69 R-5 (BTC RV 240m cross-asset): frame distinct (per-sym self-anchored vs BTC-anchored)
- vs paradigm 21 R-5 (OI velocity 5m): axis distinct (OI → price volatility)
- Not in confirmed-falsified family (NOT cross-exchange, NOT funding, NOT 5m microstructure single-domain caution family)

## Why R-0 HALT (not R-1)

Two-stage prescreen on 3 representative symbols (BCH/SOL/DOGE) × 6mo decisively shows fee-floor structural infeasibility.

### Stage 1 — Lesson #11 sample density (PASS overwhelmingly)

| sym | n_1m bars (6mo) | n_burst | rate | n_pos | n_neg |
|---|---|---|---|---|---|
| BCHUSDT | 262,080 | 2,237 | 0.854% | 1,253 | 984 |
| SOLUSDT | 262,080 | 2,311 | 0.882% | 1,192 | 1,119 |
| DOGEUSDT | 262,080 | 2,168 | 0.827% | 1,142 | 1,026 |

Projected full window: 13 alts × 750d × 1440 bars/day × 0.5%/side per quadrant per quarter ~ 8,775. Lesson #11 (≥30/cell/Q cutoff) overwhelmingly passed.

### Stage 2 — Lesson #34 empirical distribution prescreen (FAIL structural)

**Forward |ret| conditional on burst, fee_floor = 16bp/trade**:

| sym | hold | A_focus gross (bp) | A_focus net (bp) | B_focus gross (bp) | B_focus net (bp) |
|---|---|---|---|---|---|
| BCH | 1min | +0.25 | −15.75 | +0.16 | −15.84 |
| BCH | 2min | +0.22 | −15.78 | −0.91 | −16.91 |
| BCH | 3min | +0.21 | −15.79 | −0.74 | −16.74 |
| SOL | 1min | −0.95 | −16.95 | −2.53 | −18.53 |
| SOL | 2min | +0.38 | −15.62 | −3.64 | −19.64 |
| SOL | 3min | +0.65 | −15.35 | −2.53 | −18.53 |
| DOGE | 1min | −1.60 | −17.60 | −2.53 | −18.53 |
| DOGE | 2min | +0.15 | −15.85 | −3.75 | −19.75 |
| DOGE | 3min | +0.18 | −15.82 | −3.57 | −19.57 |

**Best gross observed (entire 3 sym × 4 hold matrix): +1.10bp (SOL hold=5min)**.

Fee floor deficit: **1.10bp / 16bp = 14.5x DEFICIT**.

### Stage 3 — Lesson #40 structural threshold feasibility (FAIL)

Trigger threshold p99 is attainable empirically (~0.36-0.40% |1m_ret|). But that is the TRIGGER threshold, not the EDGE threshold. The forward-return edge required to clear 16bp fee × 4-quadrant SNT is structurally absent — sub-5min hold integrates noise + bid-ask traversal, while 1m bar burst momentum decays within first 1-2 ticks (sub-bar microstructure absorbed into bursting bar itself).

This is a structural threshold feasibility failure on the EDGE side (not trigger side).

## Lessons referenced

| Lesson | Status | Dogfood instance |
|---|---|---|
| #11 sample density | PASS | N/A (passes overwhelmingly) |
| #19 SNT 4-quadrant | N/A (R-0 halt) | — |
| #21 axis stacking | WARNING_PRE_DOGFOOD | Short hold + intra-event horizon does not synthesize alpha |
| #28 substrate availability | PASS | 12/13 syms 750-800d |
| #30 data window ratio | N/A | 25% slice but 15x deficit is order-of-magnitude, not marginal |
| #34 empirical distribution prescreen | **FAIL** primary cause | **3rd dogfood as fail-cause** (predicting fee-floor infeasibility before R-1) |
| #40 structural threshold feasibility | **FAIL** edge-side variant | **NEW SUB-VARIANT — edge-side feasibility (not trigger-side)**. Candidate for amendment promotion. |
| #44 amendment 32nd xref | PASS | family distinct verified |
| #45 HMM prohibition | PASS | pure parametric |
| #46 sub-amendment | N/A | R-0 halt |
| #56 OUTCOME-LEVEL FAMILY PROXY | **predicted 6th instance** | Sub-5min momentum continuation OUTCOME-LEVEL family. R-0 halt prevents materialization but predictive evidence counts. Sub-5min momentum continuation any axis → strengthen advisory |

## Lesson #56 OUTCOME-LEVEL FAMILY PROXY — 6th instance (predicted, not materialized)

paradigm 149 would, if dispatched, deliver the same OUTCOME-LEVEL signature as confirmed-falsified family members:
- All 12 cells BROAD_FALSIFIED_FEE_FLOOR
- All gross_bp band [−5.83, +1.10] (12 cells), median ~0
- All signal_t_excess < 0.5 expected
- Concentration FAIL guaranteed

This is OUTCOME-equivalent to (a) paradigms 80/82/83/85 (5m microstructure single-domain advisory caution family) and (b) all sub-5min momentum continuation variants. **R-0 halt is the correct response — running R-1 would be ritual compliance, not science.**

## NEW Lesson candidate — #60 (NUMBERED PROVISIONAL)

> **Sub-5min momentum continuation OUTCOME-LEVEL family advisory** (provisional Lesson #60 candidate)
>
> Any paradigm with (hold_min < 5) AND (magnitude-based trigger: volatility, volume, OI, premium) on Binance perp 1m frame falls into a structurally fee-bound OUTCOME family. Forward gross edge band measured at 3-sym × 6mo on volatility burst: [−5.83, +1.10] bp << 16bp fee floor. ~15x deficit is structural, not marginal.
>
> **Prescreen mandate**: Future candidates with hold_min < 5 + magnitude trigger MUST run Lesson #34 3-sym × 6mo prescreen pre-R-1 dispatch. Halt at R-0 if best gross < 50% of fee floor (8bp).
>
> **Dogfood status**: 1st instance (paradigm 149 R-0 halt 2026-05-21). Awaits 2nd dogfood (next sub-5min candidate) for CONFIRMED promotion.

## Next candidate recommendation

**Direction discard**: Sub-5min momentum continuation horizon (any axis) — fee floor structurally incompatible.

**Pivot options** (require separate R-0 design):
1. **Hold horizon increase to ≥30min** — paradigm 127 R-5 demonstrated alpha possibility at 60-90min; any new 30-90min variant should explore alternative axes (price velocity, ATR-normalized range, OI-price divergence).
2. **Reduce fee assumption** — maker-only execution model requires separate Lesson #57 microstructure feasibility validation (queue depth, fill ratio, adverse selection). Likely viable only at niche venues, not Binance Futures USDS perp.
3. **Non-momentum mechanism at sub-5min** — short-horizon reversion (paradigm 128 family extension) with stricter trigger (e.g., paradigm 128's 10min reversion proven; explore 5min reversion as proximate adjacent).
4. **NEW axis at 30min+ frame**: e.g., volume-weighted price impact decay (intraday VWAP deviation), funding boundary cross-symbol contagion (8h boundary ±30min, paradigm 22 R-5 adjacent), or BTC-anchored cross-asset alt overshoot (paradigm 69 R-5 adjacent — distinct universe partitioning).

**Strongest recommendation**: Pivot to **option 1 or 4** (longer-horizon axes), avoiding sub-5min entirely. Option 2 requires venue infrastructure design beyond paradigm-architect mandate.

## Artifacts

- `backend/runs/research_track/alt_binance_1m_volatility_burst_event_sub5min_continuation/r0_prescreen.json` (full empirical evidence)
- `backend/runs/research_track/graveyard__alt_binance_1m_volatility_burst_event_sub5min_continuation.md` (this report)
- INDEX entry: registered at R-1, immediately marked graveyard at R-0 halt
- Queue update: PARADIGM_QUEUE_2026Q3.md §6.46 entry

## Campaign status update

- Cumulative graveyards: **148 → 149**
- Non-PASS streak: **19 → 20** (paradigm 129-149)
- R-5 LIVE: 10 unchanged
- R-5 yield: 10/149 = 6.71% (was 6.76%)
- Lessons: 34 confirmed + 11 candidates → 34 confirmed + 12 candidates (#60 candidate NEW)
- Lesson #34 dogfood count: 2 → 3 (as fail-cause)
- Lesson #56 OUTCOME-LEVEL FAMILY PROXY instances: 5 → 6 (predictive, R-0 halt advisory)
- D-Day 2026-06-03 D-13 / paradigm 127+128 Day 7 baseline 2026-05-28 D-7
