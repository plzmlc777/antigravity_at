# Graveyard — btc_fear_greed_extreme_contrarian_alt_perp_bilateral_3d_5d (paradigm #254)

**Date**: 2026-08-12 KST
**Phase reached**: R-0
**Verdict**: `R0_HALT_DNA_DUPLICATE_PARADIGM_226`
**Dispatched by**: SELF_RECOMMEND_DAILY_CRON (paradigm-architect agent, headless)
**Paradigm number note**: Prompt requested #253 but slot 253 is occupied by `cboe_vix_extreme_regime_alt_bilateral_7d` (graveyard). Reassigned to next free slot #254.

## Hypothesis (proposed)

Alternative.me BTC Fear & Greed Index (0-100 daily composite) extreme values predict CONTRARIAN 3-5d directional moves in Binance USDT-M alt perps. Extreme Fear (fgi < T_lo, T_lo ∈ {20,25,30}) → LONG alts. Extreme Greed (fgi > T_hi, T_hi ∈ {70,75,80}) → SHORT alts. SOLUSDT primary (single-symbol tier3 judgment), bilateral 4-quadrant SNT.

## R-0 halt reason — hard DNA duplicate

Paradigm **226** (`alt_fear_greed_index_extreme_contrarian_bilateral_1d`, graveyard 2026-07-14) tested this exact substrate and mechanism 29 days ago with verdict `DIFFUSE_POSITIVE_CONCENTRATION_FAIL_LIFE_CHANGING_FAIL_LESSON_41_4TH_DOGFOOD`.

### DNA overlap 5/6 identical (Lesson #62 requires ≥4/6 distinct)

| Dimension | Paradigm 226 (graveyard) | Paradigm 254 (proposed) | Distinct? |
|---|---|---|---|
| Data source | Alternative.me F&G daily 0-100 composite | Alternative.me F&G daily 0-100 composite | NO |
| Statistic class | bounded 0-100 raw threshold (≤25 / ≥75) | bounded 0-100 raw threshold (superset sweep 20/25/30 / 70/75/80) | NO (superset) |
| Trigger topology | bilateral 4-quadrant threshold cross | bilateral 4-quadrant threshold cross | NO |
| Mechanism narrative | retail crowd sentiment contrarian mean-reversion | retail crowd sentiment contrarian mean-reversion | NO |
| Hold horizon | 24h / 48h / 72h | 1d / 2d / 3d / 5d / 7d | boundary (3d=72h overlaps; 5d/7d extension does not change class) |
| Universe | 13 Binance USDT-M alt perps (SOL included) | SOLUSDT single symbol primary | narrower subset (SOL already in 226 pool) |

**Distinct dimensions: 1/6 (boundary hold only) — HARD DUPLICATE.**

The prompt's own DNA novelty check (§2 item 4) omitted paradigm 226 from comparison — it checked against paradigms 60, 247, 248, 251b only. The self-recommend prompt's DNA novelty pass was incorrect; slug grep (Lesson #61 amendment) caught the true precedent.

## Precedent — paradigm 226 R-1 results (reference)

Data window 2024-01-02 → 2026-05-12 (861 days), fee 8bp round-trip, 13-sym pool.

- **Pool three-gate PASS** (A_focus FEAR≤25 × LONG × 24h): edge +30.4bp, signal_t_excess +2.89, ci_lower +10.68bp, perm_p 0.000.
- **Concentration Gate universal FAIL**: syms_ci_pos = **0/13** across ALL 12 cells (4 quadrants × 3 holds). Per-symbol n ≈ 159 too shallow for individual bootstrap CI to exclude fee-adjusted zero.
- **Life-changing 4-dim FAIL**: per-trade edge estimate 0.30%/trade << 2%/trade floor. Fee-floor-bound structural ceiling.
- **Direction-asymmetric mechanism**: FEAR side signal real (LONG), GREED side null (SHORT signal_t_excess -0.64). Lesson #42 candidate 2nd dogfood cross-reference (paradigm 117 capitulation-LONG-works / PUMP-SHORT-null identical class).

## Why paradigm 254's single-symbol pivot does not rescue

The prompt argued that "single-symbol judgment" (SOLUSDT only per tier3 redesign) is a novel dispatch mode. Wrong for this substrate:

1. **SOL was inside paradigm 226's 13-sym pool.** Paradigm 226 measured per-symbol bootstrap CI for all 13 including SOL and got 0/13 CI-positive. SOL alone was already failing per-sym bootstrap CI in 226's own decomposition.
2. **Universe-aggregate scalar statistic problem** (Lesson #41 family): F&G is a single BTC-market-wide composite. Every symbol receives the same trigger on the same day. Per-symbol edge is the aggregate edge minus symbol-specific noise. Reducing to 1 symbol does not create new information; it destroys statistical power (smaller n, same underlying alpha) while retaining the same fee-floor-bound per-trade ceiling.
3. **Life-changing per-trade floor unchanged.** Paradigm 226 per-trade edge 0.30%. Tier3 gate on SOL alone would inherit the same edge distribution (or worse due to smaller n) — G1 recent_edge and edge_after_1bar would be near or below friction 7bp.

## Family-level compounding — Lesson #41 4-dogfood retire threshold

`universe_aggregate_scalar_statistic_family` accumulated dogfoods:
- paradigm 115 (avg pairwise correlation)
- paradigm 116 (universe volume share aggregate)
- paradigm 118 (universe RV aggregate)
- **paradigm 226 (F&G composite sentiment) — 4th CONFIRMED dogfood 2026-07-14**

Paradigm 226 graveyard explicitly stated: *"다음 dogfood (5th 누적) 시 formal Tier 4 family retire 기준 도달"*. Dispatching paradigm 254 as another F&G attempt would be the 5th dogfood and trigger formal family retire — meaning the family is closed to future dispatch. Running paradigm 254 forward would consume compute for a known negative outcome.

## Retired-families §7 note

The prompt's §7 retired-families list does NOT explicitly mention F&G. This is an oversight in the SELF-RECOMMEND prompt. Slug grep (Lesson #61) and INDEX inspection remain the authoritative deduplication path.

## New lesson candidate — SELF-RECOMMEND prompt self-validation

**Candidate lesson (post-#81)**: SELF-RECOMMEND prompts constructed by the daily cron should include a mandatory precheck that greps INDEX + graveyard files for the proposed substrate keyword BEFORE the prompt is dispatched. The current cron dispatched a hypothesis whose exact substrate (Alternative.me F&G) has an INDEX entry and a graveyard document from 29 days ago. The prompt's own §2 item 4 "DNA novelty check" enumerated 4 unrelated paradigms (60, 247, 248, 251b) and missed paradigm 226. Slug-grep-first (Lesson #61 amendment) must run before hypothesis composition, not just before R-1 dispatch.

**Prescription**: `run_paradigm_dispatch.sh` should pipe the proposed substrate keyword through `grep INDEX.json` and abort composition if the keyword hits any entry. Delegating this check to the agent's R-0 step is redundant — cheaper and safer to reject upstream at the shell wrapper.

## Lessons dogfooded (in the sense of "correctly enforced R-0 halt")

- **Lesson #61 (slug grep, 3rd+ dogfood)**: caught duplicate that Lesson #62 4/6 DNA check in the prompt missed. Slug grep remains the authoritative first-pass duplicate detector.
- **Lesson #62 (4/6 distinct DNA)**: 5/6 identical, 1/6 boundary → HARD DUPLICATE verdict enforced.
- **Lesson #41 (universe-aggregate scalar statistic family, 4-dogfood confirmed)**: family retire threshold already reached in paradigm 226; a 5th instance would be counterproductive.
- **Lesson #56 (family proxy)**: universe-aggregate scalar statistic family failure pattern (pool-strong + concentration-fail + fee-floor-bound) applies transparently to composite sentiment indexes; single-symbol pivot does not escape.
- **Lesson #77 (non-OHLCV substrate)**: F&G IS non-OHLCV compliant; this does not rescue a DNA duplicate. Non-OHLCV compliance is necessary but not sufficient.

## References

- **Precedent graveyard**: `backend/runs/research_track/graveyard__alt_fear_greed_index_extreme_contrarian_bilateral_1d.md` (paradigm 226, 2026-07-14)
- **Precedent code**: `backend/scripts/research/paradigm226_alt_fear_greed_index_extreme_contrarian_bilateral_1d_r1.py`
- **Precedent metrics**: `backend/runs/research_track/alt_fear_greed_index_extreme_contrarian_bilateral_1d/r1__metrics.json`
- **R-0 prescreen record**: `backend/runs/research_track/paradigm_254_btc_fear_greed_extreme_contrarian_alt_perp_bilateral_3d_5d/r0_prescreen.json`
- **Family precedent (Lesson #41)**: paradigm 115 (avg corr), 116 (vol share), 118 (RV aggregate), 226 (F&G) — 4-dogfood family retire threshold
- **Direction-asymmetric MR precedent (Lesson #42)**: paradigm 117 (capitulation LONG works, PUMP SHORT null) + paradigm 226 (FEAR LONG works, GREED SHORT null)

## Outcome

- No R-1 script written.
- No backtest executed.
- No trades JSON.
- No tier3_gate.py invocation.
- No paper spec.
- No enqueue.
