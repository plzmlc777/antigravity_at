# Graveyard — paradigm 245 `alt_cross_exchange_funding_rate_dispersion_binance_okx_bybit_percentile_bilateral_4h`

**Date**: 2026-08-05 (KST)
**Mode**: user-provided hypothesis via runbook §12 (paradigm 242 §Next-paradigm recommendations item 1 PREFERRED)
**Phase halted**: R-0 prescreen (R-1 not dispatched)
**Verdict**: `R0_HALT_COMPOUND_LESSON_61_SLUG_GREP_LESSON_62_DNA_5_OF_6_DUPLICATE_LESSON_56_OUTCOME_FAMILY_PROXY_LESSON_28_OKX_90D_HARD_CAP_LESSON_30_WINDOW_RATIO_LESSON_11_SAMPLE_DENSITY_INSUFFICIENT`

---

## 1. Hypothesis (rejected at R-0)

Cross-venue funding rate dispersion signal: when Binance USDT-M perp 8h funding significantly exceeds (or lags) the contemporaneous OKX + Bybit peer-venue mean, cross-exchange arbitrage pressure creates 4h directional continuation/mean-reversion on Binance perps.

- `dispersion_z = (binance_rate - mean(okx_rate, bybit_rate)) / rolling_30d_std(dispersion)`
- Direction: SHORT Binance when dispersion_z > +T (overpremium closure), LONG Binance when dispersion_z < −T (underpremium closure)
- Hold: 4h/8h/1d, T ∈ {1.0, 1.5, 2.0}, 4-quadrant SNT bilateral

The dispatch brief explicitly cited this as the FIRST cross-VENUE (same-symbol, different-exchange) funding signal and claimed orthogonality to the seeded `funding_dispersion` (ETC, cross-SYMBOL same-exchange) paradigm.

---

## 2. R-0 findings — compound halt

### 2.1 Lesson #61 slug grep — DIRECT HIT (11th cumulative dogfood)

Two direct-relevance predecessors surfaced by `grep -rl "cross_exchange_funding"`:

| Predecessor | Date | Verdict | Location |
|---|---|---|---|
| `cross_exchange_funding_spread_binance_bybit_alt_directional_8h` (paradigm 103) | 2026-05-19 | **BROAD_FALSIFIED_FEE_FLOOR** | `backend/runs/research_track/cross_exchange_funding_spread_binance_bybit_alt_directional_8h/r1/r1__verdict.md` |
| `cross_exchange_funding_spread_binance_bitget_alt_directional_8h_illiquid_venue` (paradigm 105) | 2026-05-19 | **DISPATCH_IMPOSSIBLE** | `backend/runs/research_track/cross_exchange_funding_spread_binance_bitget_alt/substrate_audit__bitget_v2.json` |

Paradigm 103 tested the identical mechanism (Binance vs Bybit spread) on the identical hold-horizon set (60m/240m/480m/1440m — includes 240m=4h). Result: gross +10 to +30 bp per event fee-annihilated by the 16 bp round-trip fee floor.

Paradigm 105 explicitly documented that OKX ccxt funding history is capped at ~90d, independently confirmed today (2026-08-05) — still true after 2.5 months.

### 2.2 Lesson #62 DNA 5-dim overlap — HARD FAIL 5/6 vs paradigm 103 (13th cumulative dogfood)

| Dim | paradigm 103 | paradigm 245 | Match |
|---|---|---|---|
| Data columns | Binance funding_rate + Bybit funding_rate | Binance + OKX + Bybit funding_rate | **PARTIAL YES** (2/3 identical, OKX added) |
| Substrate | funding_rate 8h + OHLCV 1m | Same | **YES** |
| Universe | 7-sym alt cohort (AVAX/BCH/BNB/DOGE/LINK/SOL/XRP) | 10-sym paper-pool (superset) | **YES** |
| Direction axis | signed spread / signed z | signed dispersion_z | **YES** |
| Hold horizon | 60m/240m/480m/1440m | 4h(240m)/8h(480m)/1d(1440m) | **YES** (identical 240/480/1440) |
| Statistic transform | spread bp + rolling 90d z | dispersion_z from 3-venue mean-of-peers | **NO** (only variation) |

**5/6 overlap = DNA duplicate ceiling per paradigm-architect halt rule.** Same 5/6 ratio that triggered paradigm 242 R-0 halt vs paradigm 22.

### 2.3 Lesson #56 outcome-level family proxy FAIL (21st cumulative)

Paradigm 103 R-1 empirical result at `bp=1.0 focus`:
- 4/4 quadrants net-negative (A_focus −4.17bp, A_mirror −27.83bp, B_focus −1.67bp, B_mirror −30.33bp)
- Gross A_focus +11.83bp, B_focus +14.33bp — both **below the 16 bp fee floor**
- 0/7 syms with ci_pos in any quadrant
- Temporal instability: 2024 positive, 2025 reversal (esp. B_focus 2025Q2 t=−1.02)
- Lesson candidate #34 proposed: *"Cross-exchange single-statistic spread on liquid pairs is fee-floor bound."*

Adding OKX as a 3rd venue to construct `mean(okx, bybit)` only affects the noise term in the peer-mean; the underlying microstructure equilibration mechanism is unchanged. The 3-venue mean-of-peers is a monotone-equivalent noise-reduction transform vs the 2-venue direct spread — same information ceiling per Lesson #83 candidate (paradigm 242 R-0 halt).

### 2.4 Lesson #28 substrate audit — OKX 90d hard cap CONFIRMED (2026-08-05)

Fresh ccxt 4.5.71 probe today:

| `since` param | rows returned | oldest available | newest available |
|---|---|---|---|
| 60d back | 100 | 2026-06-06T00:00Z | 2026-07-09T00:00Z |
| 90d back | 100 | 2026-05-07T00:00Z | 2026-06-09T00:00Z |
| 120d back | 100 | 2026-05-04T16:00Z | 2026-06-06T16:00Z |
| 180d back | 100 | 2026-05-04T16:00Z | 2026-06-06T16:00Z |
| 270d back | 100 | 2026-05-04T16:00Z | 2026-06-06T16:00Z |
| 365d back | 100 | 2026-05-03T16:00Z | 2026-06-05T16:00Z |

OKX hard-floor at ~92 days regardless of `since` parameter. Identical behavior to paradigm 105 (2026-05-19). No pagination workaround available.

### 2.5 Lesson #30 data window ratio FAIL

If anchored to OKX-available window: 92 / 912 = **10.1%** ≪ 30% advisory cutoff.

### 2.6 Lesson #11 sample density FAIL under OKX-anchored window

- 92d × 3 cycles/day × 7 syms = 1,932 total funding cycles
- Empirical trigger rate at |z|≥1.5 (Lesson #79 pretest) = 12.9%
- Expected total triggers = 249
- Distributed across 4 quadrants × 4 quarters = 16 cells
- **Expected per cell = 15.6 ≪ 30 cutoff (2x below)**

### 2.7 Lesson #79 predictive-content pretest — PASS-in-letter but FAIL-in-spirit

Pretest run using existing Bybit funding cache (7 syms × 2.5yr) + Binance funding SQL (dispersion computed as Binance vs Bybit only since OKX only has 92d).

| Sym | n_oos | corr_z | corr_spread | L#79 pass |
|---|---|---|---|---|
| SOLUSDT | 920 | **+0.0426** | +0.0229 | PASS |
| AVAXUSDT | 921 | −0.0001 | +0.0871 | FAIL |
| BCHUSDT | 921 | **+0.1149** | +0.0873 | PASS |
| BNBUSDT | 921 | **+0.0748** | +0.0785 | PASS |
| DOGEUSDT | 920 | **+0.0275** | +0.0054 | PASS |
| LINKUSDT | 921 | +0.0196 | +0.0191 | FAIL |
| XRPUSDT | 921 | +0.0008 | +0.0277 | FAIL |

- **4/7 syms clear 0.02 threshold** (BCH 0.115, BNB 0.075, SOL 0.043, DOGE 0.028)
- **6/7 syms POSITIVE sign** → FOLLOW/continuation direction, OPPOSITE to hypothesized mean-reversion mechanism
- Max |corr|=0.115 (BCH) sits **INSIDE paradigm 239's dogfooded [0.05, 0.15] fee-bound zone** at multi-hour holds with 8-16 bp fees

Paradigm 239's Lesson #79-follow-up candidate stated: *"Lesson #79 pretest at corr ≥ 0.02 is NECESSARY but NOT SUFFICIENT for cross-asset regime paradigms at daily holds + 8bp fees. Cross-asset spread paradigms with corr ∈ [0.05, 0.15] on 1-3d holds will fee-symmetric BROAD_FALSIFY at R-1 because effect size falls below fee floor."*

This paradigm's 4h hold with 16bp fee requires |corr| ≥ ~0.15 to break even. The best sym (BCH 0.115) barely reaches the boundary.

### 2.8 Items 8-9 — L39 direction-axis + L77 corollary — PASS-in-letter

Both direction axes are non-OHLCV (Binance funding + peer funding). Satisfies L77 corollary letter but is NECESSARY-BUT-NOT-SUFFICIENT per paradigm 238 (L79 4th dogfood, 1st L80-A dogfood) and paradigm 231 (1st NEGATIVE L77 dogfood).

---

## 3. Compute saved

- Estimated R-1 dispatch: ~5-10 min (7 syms × 108 cells)
- Estimated R-2 expansion: ~15-20 min (10 syms × top cell × 5-fold WF)
- OKX cache backfill for 10 syms (paradigm 105 wasted attempt already): ~2 min discouraged
- **Total compute saved: ~22-32 min + zero backfill bytes**

---

## 4. Lesson updates

### Lesson #83 candidate (joint-multi-source rescue of family-saturated substrate) → 2nd dogfood (from candidate 1st dogfood at paradigm 242)

Original statement (paradigm 242): *"When two data columns each individually fail Lesson #79 (or belong to a family-retired substrate under Lesson #80-A), their joint transforms (divergence, ratio, log-ratio, percentile-difference) do NOT restore predictive content beyond the individual columns' baseline. The joint transform preserves the underlying substrate's information ceiling."*

**Paradigm 245 amendment**: extends the candidate scope from "family-retired substrate" (paradigm 242 LSR) to "empirically-falsified 2-way spread substrate" (paradigm 245 cross-venue funding). The 3-venue mean-of-peers construction is a naive noise-reduction extension of the same substrate that paradigm 103 empirically retired.

**Elevates to CONFIRMED-eligible at next Q3 ratification batch** (2 dogfoods).

### Lesson #61 slug grep positive functional dogfood — 11th cumulative

Direct-substring hit on `cross_exchange_funding_spread` matched paradigm 103 verbatim. The dispatch brief acknowledged this predecessor exists ("cross-VENUE ... different from cross-SYMBOL funding_dispersion") but claimed sufficient differentiation via OKX addition + z-score normalization — both of which the DNA-overlap analysis proved insufficient.

### Lesson #56 outcome-family proxy positive functional dogfood — 21st cumulative

Direct-substrate empirical falsification (paradigm 103) was propagated correctly through mechanism-invariance argument. The added OKX venue does not alter the fee-floor location.

### Lesson #28 OKX endpoint substrate reconfirmation — 2nd dogfood on same substrate

Paradigm 105 (2026-05-19) → paradigm 245 (2026-08-05). OKX ccxt free-tier funding history remains hard-capped at ~92 days across 2.5 months of stability. Recommend adding to permanent BANNED list for future Q3+ dispatch: any cross-venue paradigm requiring OKX historical funding depth >90 days.

---

## 5. Next paradigm (246) recommendations

Ranked by novelty × Lesson-#79-passability × substrate-family diversification:

1. **`alt_perp_index_price_deviation_from_spot_index_percentile_bilateral_4h`** — mark price vs spot index deviation z-score. Novel substrate family (perp-index basis, distinct from funding/LSR/OI/TBS graveyard families). Data available via existing binance spot + perp OHLCV or `mark_price_kline` endpoint. High L79-pass likelihood because basis deviations reflect exchange-specific arbitrage friction that DOES persist at short horizons (unlike cross-venue funding which equilibrates fee-bound).

2. **`alt_orderbook_liquidity_asymmetry_top10_depth_bid_ask_ratio_bilateral_1d`** — L2 book snapshot bid/ask depth ratio at daily frequency. Requires book_depth substrate audit for coverage ≥180 days (per §3 line 22 book_depth 365d already available for 6 syms). Distinct from LSR family (top-10 depth ≠ account positioning).

3. **`alt_binance_perp_daily_settlement_time_reversion_15m`** — UTC 00:00 daily boundary reversion window. Zero substrate overlap with cross-venue/LSR/funding graveyard families. Fast-frame per Lesson #57 exception. Paradigm 234 §Option B forward candidate.

### BANNED for paradigm 246+ (updated)

- **NEW**: Any additional cross-exchange funding rate spread/dispersion transformation on OKX (permanent — 90d hard cap confirmed unchanged since 2026-05-19, ~2.5 months of stability).
- **NEW**: Any additional Binance vs Bybit funding spread reformulation (paradigm 103 empirically retired at BROAD_FALSIFIED_FEE_FLOOR).
- **NEW**: Any joint-multi-source rescue of a substrate that already has direct-substrate empirical falsification (Lesson #83 candidate reinforced — LSR family paradigm 22→242 and now cross-venue funding paradigm 103→245).
- All prior TIER 4 retires + TBS-family fast-frame momentum + single-column LSR rolling-z (§N+2, §N+3).
- All event × bar_direction joint triggers (§13.5).

---

## 6. Meta-observation

Paradigm 245 is the **2nd L83 dogfood** (candidate → CONFIRMED-eligible), the **11th L61 slug-grep dogfood**, the **13th L62 DNA 5-dim dogfood**, and the **21st L56 outcome-family-proxy dogfood**. It closes the loop on cross-exchange funding rate substrate at the paradigm-family level:

- Paradigm 103 (Binance vs Bybit 2-way, 2.5yr history): R-1 BROAD_FALSIFIED_FEE_FLOOR — direct falsification
- Paradigm 105 (Binance vs Bitget/OKX illiquid, ≤90d): R-0 DISPATCH_IMPOSSIBLE — substrate absent
- Paradigm 245 (Binance vs OKX+Bybit 3-way, hobbled by OKX 90d cap): R-0 DNA duplicate + family proxy + substrate cap

**Cross-exchange funding rate spread substrate is now exhausted across all tested formulations under the paradigm-architect halt rules.** Future proposals in this family require either (a) paid feed access (blocked per [[feedback_no_freemium_trial]]), or (b) a genuinely different mechanism axis not merely a peer-venue count variation.

The dispatch pattern where paradigm 245 was recommended by paradigm 242's forward-recommendation queue exposes a gap: the queue items should be prescreened against direct-substrate empirical falsifications (paradigm 103 in this case) BEFORE being listed as PREFERRED. Recommend adding a queue-prescreen step to the paradigm 242 §Next-paradigm process in future graveyard closures.

---

## 7. Artifacts

- Graveyard doc (this file): `backend/runs/research_track/graveyard__paradigm_245_alt_cross_exchange_funding_rate_dispersion_binance_okx_bybit_percentile_bilateral_4h.md`
- R-0 prescreen JSON: `backend/runs/research_track/paradigm_245_alt_cross_exchange_funding_rate_dispersion_binance_okx_bybit_percentile_bilateral_4h/r0_prescreen.json`
- INDEX.json entry: `paradigm_245_alt_cross_exchange_funding_rate_dispersion_binance_okx_bybit_percentile_bilateral_4h`
- No R-1 code written, no OHLCV/funding backfill triggered.
- Prior paradigm 103 verdict (referenced): `backend/runs/research_track/cross_exchange_funding_spread_binance_bybit_alt_directional_8h/r1/r1__verdict.md`
- Prior paradigm 105 substrate audit (referenced): `backend/runs/research_track/cross_exchange_funding_spread_binance_bitget_alt/substrate_audit__bitget_v2.json`
