# TASK — paradigm 165 R-0 HALT_BY_FAMILY_PROXY_AXIS_STACKING_COMPOUND

**Paradigm**: `alt_oi_decay_post_taker_imbalance_spike_compound_directional_4h`
**Counter**: 165
**Phase reached**: R-0 (pre-dispatch halt)
**Verdict**: `HALT_BY_FAMILY_PROXY_AXIS_STACKING_COMPOUND` (Lesson #56 OUTCOME-LEVEL FAMILY PROXY 16th instance + Lesson #21 axis stacking compound)
**Run date**: 2026-05-21 21:30 KST
**Dispatch mode**: continuous_parallel ([[feedback-paradigm-campaign-continuous-parallel]])

## Hypothesis

Large taker imbalance |z|≥2 spike (positioning event) → OI ratio compound (t+1h/t-1h) decay/surge → 4h directional continuation. 4 base cells × decay/surge bifurcation = 8 extended quadrants.

## Lesson #69 5-item strict template (2nd post-candidate dogfood)

### Item 1: Lesson #61 amendment slug grep — RESULT
- `grep -iE "oi_decay|taker_imb|compound|joint|positioning"` exact-slug match: 0
- Broader OI + taker family slug match:
  - `alt_taker_buy_quote_vol_imbalance_z_directional_4h` (paradigm 142-v2 graveyard) — DIRECT family
  - `alt_taker_buy_quote_vol_percentile_rank_directional_8h` (paradigm 143 graveyard) — DIRECT family
  - `taker_buy_volume_5m_zscore_signcond` (paradigm 72 directory) — Tier 4 retire family
  - `btc_oi_velocity_regime_alt_long_240m` (paradigm 71 graveyard) — DIRECT family
  - `btc_oi_activity_regime_x_alt_oi_velocity_decomp_long_4h` (paradigm 86 graveyard) — DIRECT family
  - `alt_funding_z_neg1_x_oi_z_neg2_4h_relaxed_universe15_short` (graveyard) — funding × OI joint
- Verdict: **HEAVY family overlap on both trigger axes**

### Item 2: Substrate-existence + substrate-shape audit (Lesson #28 amendment 2nd dogfood)
- **Substrate-existence**: PASS (Binance OI 5m archive + aggTrade taker-imbalance both prior-verified free unlimited)
- **Substrate-shape**: PASS (OI 5m ≥ 2.25yr coverage prior-verified; aggTrade taker buy/sell quote_volume per-symbol per-5m aggregation prior-verified via 12-col klines cache from paradigm 142-v2)
- **Lesson #28 amendment 2nd dogfood verdict**: NEUTRAL (substrate fine, halt cause is upstream family proxy not substrate shape)

### Item 3: Per-quarter n calculation (Lesson #11)
- 13 alts × 2.25yr × 5m bars = ~3.4M base obs
- taker imbalance |z|≥2 filter ~5% = ~170k events
- OI ratio decay/surge filter ~20% (decay <0.95 ∪ surge >1.05) = ~34k events
- 4-quadrant SNT per-cell n ≈ 8.5k, per-quarter ≈ 944
- Lesson #11 strong PASS expected — **but moot due to upstream halt**

### Item 4: DNA 4-dim audit table (Lesson #62)
| Comparator | Statistic | Universe | Entry-side | Mechanism | strict |
|---|---|---|---|---|---|
| paradigm 142-v2 (taker imbalance z 4h) | 1/2 same (taker imbalance z) | same 13 alts | same |z| anchor | continuation vs decay-reveals-trapped (1/2 distinct) | 2/5 strict (FAIL Lesson #62) |
| paradigm 143 (taker imbalance pct rank 8h) | 1/2 same axis | same | same | 1/2 distinct | 2/5 strict (FAIL Lesson #62) |
| paradigm 71/86 (OI velocity directional) | 1/2 same OI axis | same | same |z| anchor | OI compound ratio (≈ 2h OI velocity reframed) vs OI velocity (≈ identical) | 1/5 strict (HARD FAIL) |
| paradigm 23/60/72 (taker family Tier 4) | 1/2 same | same | same | same | 1/5 strict (HARD FAIL) |
| paradigm 87 funding × OI joint 4h | 0/2 trigger overlap (OI) | same | distinct | distinct | 3/5 strict (Lesson #62 borderline PASS) |

**Verdict**: 2/5 strict against direct family members (paradigm 142-v2 + 143) — Lesson #62 FAIL.

### Item 5: Family-proxy cross-reference (Lesson #56 OUTCOME-LEVEL, 16th instance)
- **taker_buy_vol family Tier 4 retire** (paradigm 23/60/72) — paradigm 165 trigger axis 1 = taker imbalance z spike → **OUTCOME-LEVEL family proxy VIOLATION**.
- **Lesson #57 candidate** (2 dogfoods, retire eligible) — paradigm 142-v2 + 143 BROAD_FALSIFIED. paradigm 165 same axis = **3rd dogfood → formal Lesson #57 CONFIRMED + family Tier 4 retire formal elevation**.
- **OI velocity directional family Tier 4 retire** (paradigm 71/86) — paradigm 165 trigger axis 2 = OI ratio compound (essentially OI 2h velocity ratio reframe) → **OUTCOME-LEVEL family proxy VIOLATION**.
- **Lesson #21 axis stacking does not synthesize alpha** (paradigm 83 axis stacking lesson) — paradigm 165 = (Lesson #57-family-retired axis) × (Lesson #56-retired OI velocity axis) = stacked compound of two retired families → **Lesson #21 VIOLATION**.

**Total cumulative Lesson #56 OUTCOME-LEVEL family proxy instances**: 16th instance.

## Halt verdict reasoning

paradigm 165 dispatch would constitute **3rd dogfood of Lesson #57 candidate** (z-score 142-v2 → percentile rank 143 → compound 165). Both prior dogfoods BROAD_FALSIFIED with identical fee-saturation mechanism (aggressive taker flow info-leaks during bar, 4h forward = residual noise dominated by 16bp fee floor).

Compounding with OI ratio (axis 2 = retired OI velocity family) is **Lesson #21 axis stacking** — two retired families joined into compound feature does not synthesize alpha. paradigm 83 (oi_5m_latent_regime k-means k=4) established Lesson #21 precedent: stacking weak/null axes does not produce alpha.

R-0 halt protects:
- ~30 min compute (R-1 execution avoided)
- Confirms Lesson #69 candidate 5-item strict template 2nd post-candidate dogfood SUCCESS (1st = paradigm 164 substrate-shape, 2nd = paradigm 165 family-proxy axis stacking)
- Lesson #57 escalation: 2 dogfoods → retire eligible (not yet formally elevated). paradigm 165 R-0 halt CONFIRMS the family pattern WITHOUT requiring 3rd full R-1.

## Lesson dogfoods

### Lesson #69 candidate 5-item strict template — 2nd post-candidate dogfood SUCCESS
- 1st (paradigm 164): substrate-shape mismatch caught pre-dispatch (Lesson #28 amendment)
- 2nd (paradigm 165): family-proxy axis stacking caught pre-dispatch (Lesson #56 + #21)
- 2 consecutive successful dogfoods → Lesson #69 CONFIRMED-eligible at next campaign ratification batch.

### Lesson #56 OUTCOME-LEVEL FAMILY PROXY — 16th instance
- Direct double family-proxy violation (taker imbalance + OI velocity axes both retired families)
- Compound trigger = sum-of-retired-families ≠ novel axis synthesis

### Lesson #57 candidate — escalation via R-0 halt (NOT a 3rd full dogfood, but R-0 confirmation)
- paradigm 142-v2 (z 4h) + 143 (pct rank 8h) + 165 (compound 4h R-0 halt) = pattern thrice-confirmed including pre-dispatch detection
- **Recommend formal elevation: Lesson #57 candidate → CONFIRMED, taker imbalance directional family Tier 4 retire formal** at next ratification batch.

### Lesson #21 — axis stacking does not synthesize alpha (paradigm 83 precedent)
- paradigm 165 = 2-axis stacking of (taker imbalance × OI velocity), both component axes BROAD_FALSIFIED in prior single-axis form
- Stacked compound does NOT recover signal — paradigm 83 (OI k-means k=4) precedent applies

### Lesson #28 amendment candidate — substrate-shape vs substrate-existence
- 1st dogfood (paradigm 164): DETECT substrate-shape mismatch (Deribit DVOL ≠ term structure)
- 2nd dogfood (paradigm 165): NEUTRAL (substrate fine; halt cause is upstream family proxy, not substrate)
- Amendment confirms: substrate-shape audit is necessary but not sufficient — family-proxy + axis-stacking audits remain upstream gates.

### Lesson #62 DNA 4-dim audit — 9th boundary dogfood (CONFIRMED-class)
- 2/5 strict vs paradigm 142-v2 + 143 = HARD FAIL
- 1/5 strict vs paradigm 71/86 = HARD FAIL
- Lesson #62 CONFIRMED-class 9 cumulative boundary dogfoods successful

### Lesson #61 amendment — 6th consecutive post-confirmation slug-grep SUCCESS
- Slug grep correctly surfaced family members BEFORE R-1 dispatch
- 7th-eligible permanent asset status confirmed

## Output artifacts
- `backend/runs/research_track/alt_oi_decay_post_taker_imbalance_spike_compound_directional_4h/TASK.md` (this file)

No R-1 script generated (R-0 halt).

## Next paradigm 166 recommendation

paradigm-architect spec memory + Lesson #57+#56+#21+#28amend+#62+#69 all strict apply. Next axis selection MUST avoid:
- taker_buy_vol family (Tier 4 retire, Lesson #57 retire-eligible)
- OI velocity directional family (Tier 4 retire)
- funding family (Tier 4 retire, paradigm 22+funding_dispersion exception only)
- positioning ratios family (Tier 4 retire)
- magnitude-confluence family (Tier 4 retire)
- 5m microstructure single-domain advisory caution (paradigm 80/82/83/85)
- KR equity post-earnings family (Tier 4 retire)
- Listing forced-exit subclass (paradigm 87+88+90 graveyards)
- volume_share family (Tier 4 retire)

paradigm-architect 1순위 권고 axis: **fresh substrate domain not yet attempted** — candidates:
- **Cross-asset divergence event** (BTC×ETH × alt N-min decoupling, not yet R-1 dispatched in 165 graveyards)
- **Funding payment t+0 boundary mean reversion** (NOT pre-boundary — pre-boundary paradigm 22 R-5 LIVE exception. t+0 boundary post-payment direct flow distinct mechanism)
- **Cross-exchange OI divergence** (Bybit OI substrate prior-verified paradigm 103 — Bybit OI vs Binance OI divergence as fresh axis NOT yet R-1 dispatched, paradigm 103 was funding spread not OI divergence)

Among these, **cross-exchange OI divergence** = lowest family-proxy risk + substrate verified + Lesson #62 strict ≥ 4/5 expected. **권고 1순위**.
