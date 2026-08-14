# Graveyard — paradigm 250 `funding_rate_90d_percentile_extreme_contrarian_short_7d`

- **Paradigm number**: 250
- **Slug**: `funding_percentile_extreme_short_7d`
- **Registered**: 2026-08-08 (autonomous SELF-RECOMMEND daily cron)
- **Verdict phase**: R-0
- **Final verdict**: `R0_HALT_COMPOUND` — blocked by Lesson #56 (outcome family proxy) + Lesson #62 (DNA 5/6 overlap vs paradigm 243) + Lesson #39 (mathematical mirror antipattern predicted)

---

## Hypothesis

Per-symbol Binance USDT-M perp 8h funding rate rolling 90d percentile rank; when `pct_rank >= 0.80` (top-20% of own recent history), take a **SHORT 7-day** position. Mechanism claim: extreme funding rate creates extreme carry cost that reverses long positioning over 7 days.

- **Substrate**: `binance_funding_rate` DB (non-OHLCV, per Lesson #77)
- **Statistic**: per-sym rolling 90d percentile rank of 8h funding rate
- **Trigger**: `pct_rank >= 0.80` (A_focus SHORT) with 4-quadrant SNT per Lesson #19
- **Hold**: 7 calendar days = 10,080 min (G2 cycle_margin OK)
- **Fee**: 8bp one-side / 16bp round-trip

---

## R-0 prescreen — HALT at compound blockers

### Lesson #61 slug grep (no direct hit, but semantic family scan required)

Direct slug pattern grep produced no exact matches. However, downstream family scan (Lesson #56) revealed **5 falsified paradigms in the identical mechanism family**:

| # | Slug | Verdict | Key finding |
|---|---|---|---|
| 79 | `funding_extreme z-score level` | graveyard | extreme z-score level filter x direction (referenced in 96/99 docs) |
| 96 | `funding_rate_sign_flip_event_alt_long_4h` | BROAD_FALSIFIED | "funding is lagging positioning marker, not reversal trigger" |
| 99 | `funding_cycle_8h_differential_velocity_per_sym` | BROAD_FALSIFIED_MIRROR_ONLY | 3/4 quadrant FAIL on per-sym rolling z of Δfunding |
| 156 | `btc_funding_rate_p90_regime_alt_directional_4h` | BROAD_FALSIFIED | 4/4 quadrant FAIL; 0/52 symbol-cells ci_pos; **"funding regime carries near-zero directional information for alts"** |
| 243 | `funding_skewness_bilateral 1-4d` | BROAD_FALSIFIED_FEE_FLOOR_MECHANISM_INVERTED | **mathematical proof**: focus+mirror = −2×fee for ALL (T,h) → zero directional info |

### Lesson #62 DNA 5/6 dimension overlap vs paradigm 243

| Dimension | paradigm 243 | paradigm 250 | Match |
|---|---|---|---|
| data columns | binance_funding_rate per-sym 8h | binance_funding_rate per-sym 8h | ✅ YES |
| substrate | funding DB + OHLCV daily | same | ✅ YES |
| universe | 14 syms deep pool | 13–14 syms same pool | ✅ YES |
| direction axis | bilateral 4-quadrant SNT | same 4-quadrant SNT | ✅ YES |
| hold horizon | 1d / 3d / 4d | 7d | ⚠️ PARTIAL_YES (same continuous axis, extended) |
| statistic transform | rolling 90-period skewness | rolling 90d percentile rank | ❌ NO (surface) / ⚠️ MECHANISM-EQUIVALENT |

**Overlap: 5/6 dimensions** (5 hard-YES, 1 mechanism-equivalent transform variation). Paradigm-architect DNA duplicate ceiling triggered — same rule that halted paradigm 242 and paradigm 245.

### Lesson #56 outcome family proxy — HARD FAIL

Family definition: **per-sym funding-rate own-history extreme × directional bet**. 5 falsified members with a consistent finding: **the transform on funding own-history contains no directional information beyond long-drift baseline**, and gross edge sits at or below the fee floor.

Paradigm 250's percentile-rank transform is monotone-equivalent to a z-score / skewness / level transform *for the purpose of detecting extreme own-history position*. Per the Lesson #56 amendment codified in paradigm 245 (2026-08-05): **a monotone-equivalent noise-reduction transform of a family-saturated substrate does NOT restore predictive content**.

### Lesson #39 mathematical mirror antipattern — STRONG PREDICTED HIT

Paradigm 243 demonstrated the exact-symmetric identity:

```
focus_mean_bp + mirror_mean_bp = -16.0 bp = -2 × fee    (holds for ALL T, ALL h)
```

This is a **mathematical identity** of the 4-quadrant SNT construction on any per-sym directional bet against a single forward-return realization — the two sides differ only by `(−r − fee)` vs `(+r − fee)`. Paradigm 250 uses the identical construction on the identical substrate. **The identity WILL hold at R-1.**

Even if the percentile-rank trigger produces a partially different trigger-event set than the skewness trigger, the identity applies within each set, and the underlying "long-drift baseline" that drove paradigm 243's spurious A_mirror pass will drive the identical spurious pattern in paradigm 250.

### Hold-extension rescue attempt — INSUFFICIENT

The user hypothesis proposes hold = 7d (paradigm 243 tested 1d/3d/4d). But paradigm 243's failure mode is at the **trigger level (zero directional info)**, not at the horizon level. Extending hold only amplifies the long-drift baseline:

- paradigm 243 A_mirror T=1.5 h=4d = **+202.7bp** (looks impressive; is pure long-drift capture, not signal)
- extrapolation: paradigm 250 A_mirror h=7d would produce ~+350–450bp, again from long-drift not from any percentile-rank alpha

Horizon extension cannot rescue a zero-information trigger.

---

## Why R-1 was NOT dispatched

Running R-1 would produce a fully predictable result (Lesson #39 mathematical identity + Lesson #56 family prior + Lesson #62 DNA 5/6 overlap all point to the same failure mode). Dispatching would:

1. Waste ~30 min of compute on a predetermined BROAD_FALSIFIED outcome
2. Add noise to the paradigm registry (250th paradigm becomes "family duplicate" instead of a genuine falsification)
3. Violate Lesson #56 amendment codified in paradigm 245's R-0 halt

**Correct action per current lesson prescreen protocol: halt at R-0 with compound blocker verdict, no R-1 dispatch.**

---

## What would rescue this family?

The falsified family is characterized by:
- **Substrate**: per-sym funding_rate own-history
- **Transform**: any monotone position-within-distribution statistic
- **Mechanism claim**: extreme own-history funding → contrarian directional forward return

To escape this family, a new paradigm would need at least ONE of:

1. **Different substrate axis** — e.g. cross-exchange funding *convergence* (not dispersion, which is already tested and family-adjacent), or funding-rate *forecast error* against a term-structure model (novel: model-implied vs realized funding delta as innovation signal).
2. **Non-directional mechanism** — e.g. volatility-of-funding as a *volatility-regime detector* input to a separate directional trigger (funding stops being the direction signal and becomes a regime filter, breaking the family membership).
3. **Absolute-threshold coupling with a distinct co-trigger** — funding extreme + independent orderflow imbalance + independent OI velocity (compound event with substrate-independent co-triggers), where each co-trigger has its own falsification history; but Lesson #21 axis-stacking caution applies and Lesson #83 saturation applies if the compound-family is itself saturated.
4. **Non-perpetual venue** — futures term-structure funding-analog (basis vs perp funding) on spot vs quarterly futures spread, which is a distinct microstructure (already tested — paradigm 171 — also graveyard).

The user is advised: **the "funding own-history extreme predicts direction" hypothesis space is exhausted** on the available crypto perp substrate.

---

## Reference paradigms cited

- paradigm 79 (funding extreme z-score level) — graveyard, referenced in 96/99 docs
- paradigm 96 (`funding_rate_sign_flip_event_alt_long_4h`) — `backend/runs/research_track/funding_rate_sign_flip_event_alt_long_4h/r1/r1_spec.md`
- paradigm 99 (`funding_cycle_8h_differential_velocity_per_sym`) — `backend/runs/research_track/graveyard__funding_cycle_8h_differential_velocity_per_sym.md`
- paradigm 156 (`btc_funding_rate_p90_regime_alt_directional_4h`) — `backend/runs/research_track/graveyard__btc_funding_rate_p90_regime_alt_directional_4h.md`
- paradigm 243 (`funding_skewness_bilateral 1-4d`) — `backend/runs/research_track/graveyard__paradigm_243_alt_funding_rate_30d_rolling_skewness_bilateral_1d_to_4d.md`
- paradigm 245 (`cross_exchange_funding_percentile bilateral 4h`) — Lesson #56 amendment codification, `backend/runs/research_track/paradigm_245_alt_cross_exchange_funding_rate_dispersion_binance_okx_bybit_percentile_bilateral_4h/r0_prescreen.json`

## Lesson candidate — no new lesson

This halt is a straightforward application of existing Lessons #56, #62, #39, #61. No new lesson emerges. The graveyard adds one more datapoint to Lesson #56's family-saturation prior for the funding own-history substrate.

## Provenance

- Autonomous SELF-RECOMMEND dispatch (Mint host, daily cron `paradigm-dispatch-daily`, 2026-08-08 03:30 KST)
- Runbook document: user-provided task specification at conversation start
- R-0 prescreen: `backend/runs/research_track/paradigm_250_funding_percentile_extreme_short_7d/r0_prescreen.json`
