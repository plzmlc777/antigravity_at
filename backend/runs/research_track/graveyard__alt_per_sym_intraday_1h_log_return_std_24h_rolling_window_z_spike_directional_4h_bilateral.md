# GRAVEYARD — paradigm 201 alt_per_sym_intraday_1h_log_return_std_24h_rolling_window_z_spike_directional_4h_bilateral

**Date**: 2026-05-22 16:15 KST
**Phase**: R-0 (R-1 not dispatched)
**Verdict**: `R0_HALT_DNA_DUPLICATE_PRIOR_GRAVEYARD`
**Host**: hcp_local
**Paradigm Number**: 201
**Cumulative graveyards after this entry**: paradigm 200 precedes (16:13 KST same day) → paradigm 201 = 4th consecutive R-0 inventory halt

## Hypothesis (proposed)

- Slug: `alt_per_sym_intraday_1h_log_return_std_24h_rolling_window_z_spike_directional_4h_bilateral`
- Mechanism: per-sym 1h log-return의 24h rolling window standard deviation (intraday vol smoother). 30d rolling z-score → |z|≥+2 spike trigger. 4h forward window directional bilateral 4-quadrant SNT
- Frame: 1h granularity (claimed "frame class shift" from paradigm 69 1d aggregate)
- Universe: 20 alts (paradigm 198 expanded cohort)
- Hold: 4h primary + sweep
- Direction: sign-conditional bilateral 4-quadrant SNT

## Halt mechanism — Lesson #61 amendment slug grep 4th post-confirmation success

R-0 prescreen Step 0 (Lesson #61 amendment slug grep) hit prior paradigm directory:
```
ls backend/runs/research_track/ | grep -iE "intraday_1h|1h_log_return|24h_rolling|intraday_vol_smoother|1h_vol_std|hourly_vol_std"
→ alt_intraday_1h_log_return_std_24h_window_z_directional_4h  (paradigm 136 R-0 graveyard 2026-05-21)
→ graveyard__alt_intraday_1h_log_return_std_24h_window_z_directional_4h.md
```

## DNA overlap analysis — paradigm 136 (predecessor R-0 graveyard 2026-05-21 11:29 KST)

| DNA dimension | paradigm 136 (predecessor) | paradigm 201 (proposed) | Match |
|---|---|---|---|
| Statistic class | 24h rolling std of per-sym 1h log-return, 30d z-score | 24h rolling std of per-sym 1h log-return, 30d z-score | **IDENTICAL** |
| Frame | 1h granularity intraday | 1h granularity intraday | **IDENTICAL** |
| Trigger | \|z\|≥+2 spike | \|z\|≥+2 spike | **IDENTICAL** |
| Direction | 4-quadrant SNT bilateral (z-sign as primary direction) | 4-quadrant SNT bilateral (bar UP/DOWN × LONG/SHORT) | **IDENTICAL** (both bilateral 4-quad SNT) |
| Hold | 4h primary + debounce 8h | 4h primary + 8h/12h/24h sweep | **IDENTICAL** (4h primary same) |
| Universe | 12 alts (paradigm 133/134 cohort) | 20 alts (paradigm 198 cohort, expansion) | EQUIVALENT (universe expansion only — paradigm 199 dogfood already established expansion does NOT recover failed paradigms) |

**Overlap score**: **6/6 strict dimensions** — every DNA dimension identical except universe size (which expansion alone has been shown in paradigm 199 dogfood to not recover BROAD_FALSIFIED predecessor signals).

## Frame-class-shift claim audit

User prompt claims:
> "intraday 1h vol smoother — short-window vol estimate using fine-grained 1h returns within 24h window"
> "1h granularity frame (paradigm 69 R-5 LIVE 1d frame과 differentiation, paradigm 195/198 daily aggregate와도 differentiation)"

**Audit**: paradigm 136 (predecessor graveyard 2026-05-21) **already executed the 1h frame class shift**:
- paradigm 136 statistic = "Per-symbol 1h close-to-close log_ret → 24h rolling window std of log_ret_1h (24 obs) → per-symbol 30d (720h) rolling z-score"
- paradigm 201 statistic = "per-sym 1h log-return의 24h rolling window standard deviation → 30d rolling z-score"

**These are word-for-word equivalent formulations**. The "frame class shift" was already attempted and graveyarded at paradigm 136. paradigm 201 is NOT a fresh frame-class shift; it is a verbatim repeat dispatch of paradigm 136 with universe expansion 12→20.

**Distinction from paradigm 182/184/199 precedent** (cited in user prompt as justification for path (b) "frame class shift NEW paradigm class"):
- paradigm 182: Sharpe-z statistic class — DIFFERENT statistic from vol-std
- paradigm 184: direction class shift — DIFFERENT direction mechanism
- paradigm 199: semivariance asymmetry — DIFFERENT decomposition (up/down split)
- paradigm 201 vs 136: SAME statistic + SAME frame + SAME trigger + SAME direction + SAME hold — universe expansion only

## paradigm 136 predecessor findings (key takeaways)

**Asymmetric z-distribution** (Lesson #34 prescreen, n=60000):
- z>+2: 4.16% empirical
- z<-2: 0.30% empirical
- **13.9x asymmetry** (non-negative std aggregate floor)

**Per-quarter density** (Lesson #11):
- Pos z>+2: 9/10 quarters ≥ 30
- **Neg z<-2: 0/10 quarters ≥ 30** (max 22, structural failure)

**Stratified A focus measurement** (n=147 across 4 quarters):
- A focus (z>+2 LONG): gross +88.77bp, t +4.13, 4/4 quarters positive
- **CRITICAL temporal decay**: 2024Q1 +267.28bp → 2026Q2 +1.34bp (200x compression)
- Recent quarter (2026Q2) effectively zero net of fee

**Mechanism overlap caution** (paradigm 69 R-5 LIVE BTC RV highvol):
- paradigm 69 = HIGH vol → 13 alts LONG continuation (1d frame, BTC universal trigger)
- paradigm 136 = per-sym HIGH 1h-intraday vol → same-sym 4h LONG
- Frame-distinct but **directional alpha mechanism is same family** — paradigm 136 A side strength likely re-discovery of paradigm 69 on per-sym 1h

## Universe expansion (12→20) recovery infeasibility

Claim: 20-sym paradigm 198 cohort recovers B-side density.

**Verdict**: FALSE. Reasoning:

1. **Structural asymmetry persists**: z<-2 = 0.30% empirical is property of non-negative std distribution (lower bound 0). Universe expansion does not change z-distribution shape.
2. **Density projection** with 20 syms: 20 × 0.30% × 2.25yr × 24h × 365 = ~11,826 z<-2 trigger obs → 4 quadrants × 9 quarters = 36 cells → per-cell ~36, marginally above 30 cutoff.
3. **Temporal decay invalidates fresh dispatch**: paradigm 136 stratified measurement already showed 2024Q1 +267bp → 2026Q2 +1.34bp on A side. Adding 8 more syms to a decayed signal does not reset temporal decay; if anything, recent-quarter universe additions exacerbate it.
4. **paradigm 199 dogfood precedent**: 8 universe expansion 12→20 caught at R-0 same week — `paradigm 134 finding: 0/12 syms ci_pos UNIVERSAL absence of mechanism across ALL 4 quadrants — universe expansion 8 syms 추가로 회복 불가능`. Lesson #44 17th dogfood + Lesson #54 1st dogfood confirmed. Same precedent applies here.

## Lessons applied at R-0

- **Lesson #61 amendment slug grep** — HIT predecessor `alt_intraday_1h_log_return_std_24h_window_z_directional_4h`, 4th consecutive post-confirmation success
- **Lesson #44 amendment xref** — 21st dogfood SUCCESS (DNA 6/6 overlap caught pre-dispatch)
- **Lesson #54 family-reduction** — 4th consecutive R-0 halt dogfood (paradigm 199/200/201 universe-expansion/formula-refinement antipattern reinforced)
- **paradigm-architect spec halt rule** — "Halt on DNA duplicate (5/6 dim overlap)" triggered at 6/6

## Lesson #71 candidates (carried from paradigm 200 R-0 graveyard)

paradigm 201 = 4th consecutive post-confirmation Lesson #61 success → reinforces Lesson #71 candidate evidence.

## Continuous-parallel campaign next dispatch recommendation

Per [Persistence over efficiency] memory policy: dispatch continues unabated.

**Avoid**:
- Universe expansion of any paradigm 136/198/199 family entry (asymmetric z + temporal decay double bind)
- Single-statistic non-negative aggregate z-spike with symmetric 4-quadrant SNT (Lesson #55 candidate reinforced — paradigm 136 1st dogfood)
- VRP / RV-family axis (paradigm 200 family reduction)

**Pivot candidates**:
1. **Microstructure non-vol axis** — per-sym taker_buy_volume_ratio z-spike, per-sym orderbook imbalance, cross-section taker imbalance (NOT vol-derived)
2. **Cross-substrate fusion that does NOT collapse to RV** — e.g., funding sign × OI velocity sign joint conditioning (already attempted in paradigm 96-99 funding family Tier 4 retire, but specific sub-mechanisms may still be unexplored)
3. **paradigm 134 §6.31 Rank 3+ pending candidates** — review queue file `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.31 for Rank 3-5 unexamined axis families

**Halt streak**: 12-streak non-PASS (paradigm 190-201). R-5 yield: 10/201 = 4.97%.
**D-Day baseline measurement**: 2026-06-03 D-12 / paradigm 127+128 Day 7 baseline 2026-05-28 D-6.

## Artifacts

- `backend/runs/research_track/alt_per_sym_intraday_1h_log_return_std_24h_rolling_window_z_spike_directional_4h_bilateral/r0_prescreen.json` (R-0 inventory halt metrics)
- `backend/runs/research_track/INDEX.json` (paradigm 201 entry, R0_HALT_DNA_DUPLICATE)
- backup: `backend/runs/research_track/INDEX.json.bak_paradigm201`

## Predecessor reference (paradigm 136)

- `backend/runs/research_track/alt_intraday_1h_log_return_std_24h_window_z_directional_4h/r0_prescreen.json`
- `backend/runs/research_track/graveyard__alt_intraday_1h_log_return_std_24h_window_z_directional_4h.md`
- `backend/scripts/research/paradigm136_r0_prescreen.py`
