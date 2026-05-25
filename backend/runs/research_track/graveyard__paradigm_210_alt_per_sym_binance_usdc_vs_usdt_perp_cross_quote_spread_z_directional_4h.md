# Graveyard — paradigm 210 alt_per_sym_binance_usdc_vs_usdt_perp_cross_quote_spread_z_directional_4h

**Phase**: R-1 GRAVEYARD
**Verdict**: `GRAVEYARD_PRIMARY_FALSIFIED_HOLD_SWEEP_PASS_ALPHA_DECAY_P1`
**Date**: 2026-05-22 KST
**Counter**: 112th paradigm registered

## Hypothesis

Same-exchange (Binance Futures), same-base-asset, different-quote (USDC vs USDT) perp price spread z-score spike to |z| ≥ 2 over 30d rolling window mean-reverts within 4h. Trade the USDT-quoted contract.

**Mechanism (proposed)**: Cross-quote stablecoin liquidity arbitrage path dislocation. When USDC-quoted perp deviates from USDT-quoted perp on the same exchange, arbers route through stablecoin pair (USDT-USDC on Curve/Uniswap V3 + CEX OTC) to close the gap, typically resolving within hours → mean reversion.

## Novelty (Item 1-5 prescreen)

- **Item 1 INDEX grep**: 0 prior art for `usdc / cross_quote / quote_asset / inter_quote` in INDEX.json + research_track/ ✅
- **Item 2 substrate**: Binance Futures REST archive (no freemium, no auth) ✅
- **Item 3 sample density**: 10 syms × ~5000 bars × ~3% trigger rate = 1500-2400 events per quadrant ≫ 30/cell ✅
- **Item 4 DNA 5/5 distinct**: vs funding family, vs cross-exchange, vs cross-venue OI, vs mark-index basis, vs spot-perp basis — all 5/5 distinct ✅
- **Item 5 family-proxy**: no structural proxy in basis family graveyards ✅

This was the **first same-exchange cross-quote (USDC vs USDT) paradigm** ever dispatched. Substrate: Binance Futures 38 USDC-quoted perp pairs (top 10 used: BTC/ETH/BNB/SOL/XRP/DOGE/LINK/SUI/ORDI/1000PEPE), 2024-01-15 to 2026-05-20 = ~860 days = 5048 4h bars/symbol.

## R-1 protocol

- 4h bars, 30d rolling z window (180 bars min_periods=90)
- Trigger: `|spread_z| >= 2.0` where `spread = (USDC_close - USDT_close) / USDT_close`
- Hold sweep: 4h / 8h / 12h / 24h
- Fee: 16 bps round-trip
- 4-quadrant SNT: A_focus (z+ SHORT) / A_mirror (z- LONG) / B_same (z+ LONG) / B_mirror (z- SHORT)

## Primary 4h verdict — 4/4 FAIL (mean-reversion hypothesis FALSIFIED)

| Quadrant | n | obs_mean_bp | sig_t_ex | perm_p | ci_lower_bp | 3gate |
|---|---|---|---|---|---|---|
| A_focus z+ SHORT (focus) | 1513 | **−37.74** | **−2.63** | 0.003 | −50.73 | FAIL |
| A_mirror z− LONG | 2357 | −11.23 | +1.61 | 0.945 | −20.26 | FAIL |
| B_same z+ LONG | 1513 | +5.74 | +4.07 | 0.984 | −6.59 | FAIL |
| B_mirror z− SHORT | 2357 | −20.77 | −0.40 | 0.359 | −30.12 | FAIL |

**Critical**: A_focus 3-gate FAIL with `sig_t_ex = −2.63` (observed t below null mean) and `perm_p=0.003 in WRONG direction` — at 4h horizon, the spread |z|>=2 event is followed by **CONTINUATION not reversion**, the opposite of the hypothesized mechanism. Per-symbol concentration: **0/10 ci_pos**, per-quarter: 2/10 pos_t. Mean-reversion hypothesis decisively falsified.

## Hold sweep PASS cells (Lesson #37 dogfood — non-primary PASS scan)

Two non-primary cells passed three-gate:

### hold_3_bars_12h :: B_same_z_pos_LONG (continuation at 12h)

- n=1513, obs_mean=**+41.66bp**, t=+3.77, sig_t_ex=+5.58, perm_p=0.022, ci=[+20.81, +63.32]bp, prob_pos=1.000
- **Three-gate PASS**
- Concentration Gate: sym 3/10 (0.30) + quarter 6/10 (0.60) + n_syms_ci_pos=3 → **PASS technically (min threshold)**
- Driver symbols: XRP +52bp, DOGE +99bp, 1000PEPE +200bp (3/10 only — meme/alt concentration)

### hold_6_bars_24h :: B_same_z_pos_LONG (continuation at 24h)

- n=1513, obs_mean=**+71.20bp**, t=+4.64, sig_t_ex=+5.91, perm_p=0.001, ci=[+42.27, +100.75]bp, prob_pos=1.000
- **Three-gate PASS**
- Concentration Gate: sym 3/10 (0.30) + quarter 5/10 (0.50) + n_syms_ci_pos=3 → **PASS at threshold boundary**
- Same 3 driver symbols at higher magnitude (XRP +142bp, DOGE +148bp, 1000PEPE +278bp)

## Item 6 alpha decay 5-pattern taxonomy — 6th operational dogfood, **Pattern P1 DETECTED**

Era stratify on hold sweep PASS cells:

| hold | 2024 t-stat | 2025 t-stat | 2026 t-stat | Pattern |
|---|---|---|---|---|
| 12h B_same | **+4.81** | +0.27 | **−1.75** | **P1 monotonic decay to negative** |
| 24h B_same | **+5.74** | −0.20 | −0.95 | **P1 monotonic decay to negative** |

Mean magnitude per era (12h):
- 2024: +94.86bp (n=700)
- 2025: +3.49bp (n=666)
- 2026: −38.69bp (n=147)

Mean magnitude per era (24h):
- 2024: +162.92bp (n=700)
- 2025: −3.21bp (n=666)
- 2026: −28.41bp (n=147)

**Verdict**: The alpha exists historically (2024 only, when USDC/USDT spread arbitrage was less efficient), but has decayed to **negative** by 2026. The mechanism is **informationally learned away** — arbers have closed the cross-quote spread efficiency gap. This is identical to:
- paradigm 87 delisting alpha decay (informational)
- paradigm 136/202 RV intraday cross-family pattern
- 5 consecutive post-paradigm-188 alpha decay reinforce events

This is the **6th operational dogfood of Item 6** and meets the failure protocol criterion:
> "Predecessor monotonic temporal decay documented (alpha decay informational learning) → R0_HALT_BY_INFORMATIONAL_DECAY_LESSON_55_PRESCRIPTION_OUT_OF_SCOPE"

But detected POST-R-1 (the prior-art audit at R-0 had no precedent because cross-quote was novel substrate).

## Item 7 Cross-set asymmetry

- A_focus |mean|=37.74bp vs A_mirror |mean|=11.23bp
- **Asymmetry ratio: 3.36x** (NOT 1.0x mirror tautology)
- Unconditional |bar return|=124.74bp (4h)
- Conditional/unconditional ratio: A_focus 0.30x, A_mirror 0.09x (both quadrants have signal *less* than baseline noise — trigger is uninformative at 4h)
- **Lesson #39 sub-class A check FAIL**: not exact mirror, real asymmetry
- **Lesson #39 sub-class B check FAIL**: both quadrants broad-uniform-negative (0/10 sym ci_pos in both A_focus AND A_mirror), no real concentration in mirror
- Conclusion: **NOT a sub-class A/B fee-floor artifact** — the 4h signal is genuinely directionally information-bearing but in the OPPOSITE direction of the hypothesis (continuation, not reversion), AND that continuation alpha has decayed to negative by 2026

## Item 8 Concentration + Temporal Independence

- 12h B_same: Concentration Gate PASS at threshold boundary (3 syms, exactly 30% sym ratio, 60% quarter ratio)
- BUT **temporal independence FAILS via alpha decay** — 2024 quarters: 3/4 pos_t (Q2 negative outlier); 2025 quarters: 2/4 pos_t (Q3 strongly negative); 2026 quarters: 0/2 pos_t
- 24h B_same: similar pattern (3 syms, 30% sym, 50% quarter)
- **Per-quarter pos_t pattern is era-concentrated 2024-only** — temporal independence violated

## Lesson #42 17th dogfood — NEGATIVE (no event)

Test condition: B mirror cell PASS + B same-sign FAIL.

- 12h: B_same PASS (sig_t_ex +5.58) + B_mirror FAIL (sig_t_ex −1.34) — **NOT Lesson #42 dogfood event** (B_same passed, not B_mirror)
- 24h: B_same PASS (sig_t_ex +5.91) + B_mirror FAIL (sig_t_ex −2.20) — **NOT Lesson #42 dogfood event**

Lesson #42 dogfood 17 deferred to next paradigm.

## Item 8 unconditional baseline

n=49568 4h forward returns, |mean|=124.74bp, long_gross +1.32bp (t=+1.50). General upward drift weak; A_focus −37.74bp and A_mirror −11.23bp are both well below the +1.32bp unconditional long drift, confirming the trigger filters into negatively-selected return regimes (consistent with continuation hypothesis: spread spikes precede directional continuation in BOTH directions, so trading the contrary direction yields negative selection).

## Final verdict logic

1. **Primary 4h mean-reversion hypothesis 4/4 FAIL** → decisive falsification of the proposed mechanism.
2. **Hold sweep identifies non-primary continuation alpha at 12h/24h** (sig_t_ex +5.58 / +5.91, three-gate PASS, Concentration at minimum threshold).
3. **BUT era stratify reveals Pattern P1 monotonic alpha decay**: 2024 alpha → 2025 zero → 2026 negative. The cross-quote stablecoin liquidity inefficiency arbitrage was real in 2024 (when USDC perp pairs were newly listed and liquidity was thin) but has been **informationally learned away** by 2026.
4. **NARROW_SCOPE_LIFE_CHANGING_FAIL qualification ineligible**: Lesson #20 narrow-scope requires Lesson #15 4-cond ALL PASS for narrow variant promotion. Here B_same hold-sweep PASS is at primary symbol set (10 syms), not a narrow variant. AND alpha decay disqualifies seeded R-5 candidacy regardless.

**GRAVEYARD verdict**: `GRAVEYARD_PRIMARY_FALSIFIED_HOLD_SWEEP_PASS_ALPHA_DECAY_P1` — primary mean-reversion hypothesis falsified; hold-sweep non-primary continuation PASS shows alpha decay Pattern P1 (informational learning). No R-2 promotion.

## Family addition

Add to retired/advisory caution catalog:
- **Cross-quote (USDC vs USDT same-exchange) family — advisory caution** (1 instance, novel substrate)
- Mechanism class: cross-quote stablecoin liquidity arbitrage
- Decay reason: arber efficiency closes spread gap as USDC perp market matures (2024 onboard → 2026 efficient)

## Lesson candidates emerging

- **Lesson #71 candidate (post-paradigm-177 corollary continued)**: novel substrate first-use paradigm should pre-test for "market maturity decay" — if substrate was newly listed within the R-1 window (USDC perp pairs onboarded 2024-01-03 to 2024-03-07, mid-R-1 window), 2024 alpha may be transient market-microstructure inefficiency that learns away. Era stratify mandatory; if 2024-only PASS + 2026 negative → DECAYED_BY_MARKET_MATURITY classification.

## Artifacts

- code: `backend/scripts/research/paradigm_210_r1.py`
- metrics: `backend/runs/research_track/paradigm_210_alt_per_sym_binance_usdc_vs_usdt_perp_cross_quote_spread_z_directional_4h/r1__metrics.json`
- index: `backend/runs/research_track/INDEX.json` (registered with `phase: R-1_GRAVEYARD`)

## Next paradigm 211 recommendation

Three viable paths post paradigm 210:

1. **Token-economics direct event** (validator slashing / governance vote on-chain) — leverages public RPC (Ethereum mainnet / Solana) with non-freemium tier. Substrate verification + rate-limit prescreen required. New axis vs all prior paradigms.

2. **Hour-of-day session-anchor variant** outside the retired family scope — Lesson #69 8-item template-compliant pre-screen. But hour-of-day family is already retired (paradigm 108/192), so this would need Lesson #20-style narrow-scope variant approach.

3. **Cross-quote variant in different statistic** (USDC quote_vol share vs USDT quote_vol share z-spike) — same substrate but different statistic class. Risk: Lesson #56 family-proxy concern (mechanism may decay through same maturity mechanism). Recommend skip in favor of path 1.

**Direct recommendation**: path 1 — validator slashing/governance-vote on-chain event-anchored paradigm using public RPC. Novel substrate, novel statistic class, family-distinct from all 14 retired families.
