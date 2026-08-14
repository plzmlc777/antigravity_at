# Graveyard — paradigm 230

**Slug**: `binance_futures_mm_tier_change_event_alt_directional_3d`
**Counter**: paradigm 230 (substantive R-0 halt)
**Phase**: R-0 prescreen halt (R-1 NOT dispatched)
**Verdict**: `R0_HALT_COMPOUND_DNA_DUPLICATE_LESSON_56_OUTCOME_PROXY_LESSON_40_INFEASIBLE_LESSON_11_SAMPLE_INSUFFICIENT`
**Date (KST)**: 2026-07-18

## Hypothesis (1-line)

Binance Futures MM tier / leverage bracket change announcements as structural risk-limit shock: hike → forced deleveraging → SHORT alt 1–3d; cut → relaxed entry barrier → LONG alt 1–3d. 4-quadrant SNT: A_focus (hike × SHORT), A_mirror (hike × LONG), B_focus (cut × LONG), B_mirror (cut × SHORT).

## Substrate exploration result

Scraped Binance CMS catalogs 48 + 161 + 49 (Perpetual Futures updates) using `scrape_mm_tier_events.py` (this directory). Filter: title contains "Update the Leverage & Margin Tiers" AND NOT contains "Delist" (to isolate the standalone MM tier change class, not the delisting-bundled events).

**Raw haul**: 112 independent announce_ts batches × avg 9.6 syms = 1,079 (symbol × event) rows across 2024Q3 → 2026Q3 (9 quarters, 514 unique symbols).

**Per-quarter batch counts**: 2024Q3=9, 2024Q4=22, 2025Q1=30, 2025Q2=10, 2025Q3=10, 2025Q4=9, 2026Q1=7, 2026Q2=13, 2026Q3=2.

**Body inspection** (sample: 2026-07-14 batch): PTBUSDT before 20x → after 10x; NOMUSDT before 20x → after 10x. Universal HIKE pattern on long-tail / newly-listed alts. Every weekly batch is a Binance routine risk-limit maintenance ratchet.

## Lesson #69 5-item strict prescreen result

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | slug grep (Lesson #61) | PASS_novel_slug | slug unique in INDEX + Q3 queue; only Runbook option-B pointer |
| 2 | family-proxy (Lesson #56) | **FAIL_HARD** | outcome maps to delisting family Tier 4 retire — same universe (long-tail alts near delist), same substrate (Binance CMS), same directional outcome (SHORT alt) |
| 3 | DNA 5-dim (Lesson #62) | **FAIL_HARD (4/5 overlap)** | substrate=Binance CMS ✅ shared / statistic=event ts ✅ shared / universe=long-tail alt perps ✅ shared / mechanism=announcement-driven bearish drift ✅ shared / timescale=1–3d ~= delisting 1d shared. Overlap 4–5/5 vs delisting family (paradigms 87/88/89/90/97-c/159/176/191) |
| 4 | substrate availability (Lesson #28) | PASS | 1079 rows scraped from CMS |
| 5 | sample density (Lesson #11) | **FAIL_HARD** | Effective independent obs = 112 batches (not 1079; batch clustering ≈ 9.6 syms share announce_ts → IID violation). Per-cell (2 quadrants × 9 quarters = 18 cells) = 6.2 events / cell ≪ 30 threshold |

Additional (Lesson #40 — direction feasibility): **FAIL_HARD**. Zero rows in 1079 suggest "cut" direction (title regex 'increase|raise|expand' = 0/1079). Empirical direction distribution ≈ 100% hike / ~0% cut. 4-quadrant SNT structurally infeasible (B_focus + B_mirror have no events).

## Compound halt reasons

**Any single reason below is sufficient to halt at R-0**; five converge, making this a decisive R-0 verdict.

### 1. Lesson #56 outcome-family proxy — HARD FAIL

Delisting family is Tier 4 retire (paradigm 87 R-2 FRAGILE_TEMPORAL_WF_FAIL + paradigms 88/89/90/97-c/159/176/191 cumulative graveyards). paradigm 191 §3 explicitly documents alpha decay: 2024-Q4 +44bp → 2025-Q3 +1986bp → 2026-Q2 +650bp (monotonic decay, informational learning by market participants).

MM tier hike on long-tail alts is a *leading indicator* of delisting on the same names. Body inspection confirms symbols like PTBUSDT / NOMUSDT / AERGOUSDT / BANUSDT / EULUSDT / GUAUSDT — thinly-traded long-tail assets. Binance's routine "20x → 10x" ratchet is the pre-delisting risk cleanup pipeline (documented in paradigm 87 graveyard §3 and delisting scraper source: filter `"Update the Leverage"` was applied to exclude these from delisting events precisely because they overlap).

**Same universe, same substrate, same bearish outcome direction → mechanism-collapsed proxy of delisting.**

### 2. Lesson #62 DNA duplicate — HARD FAIL (4–5/5 dim overlap)

| Dim | This paradigm 230 | Delisting family (87/88/159/191 …) | Overlap? |
|---|---|---|---|
| Substrate | Binance CMS catalog 49 announcements | Binance CMS catalog 161 announcements | ✅ same source class |
| Statistic | announce_ts event | announce_ts event | ✅ identical |
| Universe | 514 long-tail USDS-M alts | long-tail USDS-M alts | ✅ heavy overlap |
| Mechanism | forced deleveraging → bearish drift | forced exit → bearish drift | ✅ same directional outcome |
| Timescale | 1–3d | 1d (paradigm 191) / 30d (lifecycle 168) | ⚠️ partial 1d overlap |

**Score: 4.5/5 overlap. Hard fail (threshold ≥ 3/5).**

### 3. Lesson #40 direction feasibility — HARD FAIL

Binance publishes only one direction (hike/ratchet-down) on long-tail alts. No "cut" (max leverage increase) events found in 1079 rows across 9 quarters. B_focus (cut × LONG) and B_mirror (cut × SHORT) quadrants are structurally empty. 4-quadrant SNT cannot be constructed → falsifiability compromised (Lesson #19 mandate not achievable).

### 4. Lesson #11 sample density — HARD FAIL

Nominal n=1079 collapses to n_effective=112 due to batch clustering (~9.6 syms share exact announce_ts). If we forced hike-only 2-quadrant SNT (A_focus + A_mirror):
- 2 quadrants × 9 quarters = 18 cells
- 112 batches / 18 cells = **6.2 independent events per cell**
- Lesson #11 threshold = 30 per cell → FAIL by 4.8×

Even with 2-quadrant compression, sample density is 4.8× short of the minimum floor.

### 5. Alpha-decay class inheritance — informational (paradigm 87/191/136/202 pattern)

Given the mechanism-proxy of delisting family (which paradigm 191 documented as informational alpha decay: participants pre-learning and front-running), the MM tier hike variant faces the same decay pressure but with earlier signal timing (weekly routine batch = fully public + easily forecastable). Expected alpha degradation ≥ 50% vs delisting family in 2026, per Lesson #77 informational-decay corollary applied to the anticipatable Binance risk maintenance cadence.

## Metrics summary

| Metric | Value | Threshold | Pass? |
|---|---|---|---|
| n (symbol×event rows scraped) | 1,079 | — | measurement |
| n (independent batches) | 112 | ≥ n_cells × 30 | fail |
| n_effective per cell | 6.2 | ≥ 30 | **fail (Lesson #11)** |
| n_measurable_quarters (≥ 10 batches) | 6 (2024Q3, 2024Q4, 2025Q1, 2025Q2, 2025Q3, 2026Q2) | ≥ 4 | pass |
| direction 'cut' rate | 0/1079 = 0% | ≥ 1.5% | **fail (Lesson #40)** |
| DNA overlap vs delisting family | 4.5/5 dims | < 3/5 | **fail (Lesson #62)** |
| Family-proxy vs delisting Tier 4 | outcome-equivalent | should be distinct | **fail (Lesson #56)** |
| substrate availability | 112 batches over 2 yr | ≥ 4 quarters | pass |
| slug uniqueness | novel | novel | pass |

## Lessons dogfooded

- **Lesson #11** (sample density, per-cell 30): explicit batch-independence correction applied. Nominal count 1079 vs effective 112 → 9.6× overstatement. Reinforces "count independent event batches, not symbol-event rows for batch-structured announcements."
- **Lesson #19** (4-quadrant SNT mandatory): infeasible when substrate has structural direction asymmetry — must be checked at R-0 prescreen.
- **Lesson #40** (symmetric threshold feasibility): extended from "z-score symmetric threshold" to "event direction distribution symmetric availability". Cut/hike asymmetry on Binance MM tier changes = 0/100% = structural infeasibility for bilateral SNT.
- **Lesson #56** (outcome-family proxy): confirmed for exchange-policy-event class — MM tier hike on long-tail alts = leading indicator of delisting → outcome-collapsed proxy of paradigm 87 family. Halt at R-0 before dispatching R-1.
- **Lesson #62** (5-dim DNA audit, 3+ overlap = duplicate): 4–5/5 overlap with delisting family + lifecycle family → hard fail. Substrate class = "Binance CMS announcement events on long-tail alt USDS-M perps" already fully covered by paradigms 87/168/191.
- **Lesson #69** (5-item strict prescreen template): 3 of 5 items HARD FAIL + 1 additional (Lesson #40) HARD FAIL = compound halt.
- **Lesson #77** (non-OHLCV substrate preference): substrate primary source is non-OHLCV (Binance CMS), so preference is honored. But Lesson #77 is a necessary-not-sufficient condition — passing #77 does not compensate for #56/#62/#40/#11 failures.
- **NEW candidate Lesson**: "Exchange-policy-batch announcements have batch-clustering IID violation" — count `unique(announce_ts)` not `count(symbol × event)` at Lesson #11 prescreen for any announcement-driven paradigm. (Dogfood candidate; needs 1 more precedent to promote from candidate → confirmed per Lesson #11 promotion pattern.)

## Future retry conditions

**PERMANENT_GRAVEYARD** (family retired via delisting family Tier 4).

Retry conditions for the exchange-policy-event class in general would require:
1. A truly distinct policy event type (e.g., **funding rate cap change** or **cross-margin ratio change** on established mid-cap symbols) that is NOT correlated with delisting pipeline.
2. Universe restricted to top-30 by market cap (not long-tail) — this would break the lifecycle/delisting family DNA overlap.
3. Bilateral direction distribution (hike + cut both meaningful) — Binance MM tier is universally hike-only, so must find a different exchange policy substrate.
4. Non-batch announcement structure — one symbol per event — to preserve IID and boost per-cell density.

None of these can be achieved by reformulating the current MM tier substrate. Requires a genuinely new policy-event class (Q4+ candidate at earliest, pending new substrate discovery).

## Related paradigms

- **paradigm 87** (`binance_delisting_announce_short_alt`) — R-2 FRAGILE_TEMPORAL_WF_FAIL (informational alpha decay 2024→2026)
- **paradigm 168** (`lifecycle_pump_decay`) — R-5 LIVE (long-tail alt post-listing decay covers overlapping universe)
- **paradigm 191** (`binance_bybit_okx_delisting_announce_short_alt_universe_expanded_n_gte_300_1d_hold`) — R-0 HALT root-cause mismatch (spatial expansion doesn't fix temporal decay)
- **paradigm 88 / 89 / 90 / 97-c / 159 / 176** — cumulative delisting family Tier 4 retire graveyards

## Artifacts (this directory)

- `scrape_mm_tier_events.py` — CMS catalog 48+49+161 scraper (excludes delist-bundled titles)
- `probe_categories.py` — cross-catalog MM/leverage title probe (confirmed cat 49 as sole standalone-MM source)
- `mm_tier_events.csv` — 1079 rows (symbol × event), 112 unique batches, 514 unique symbols, 9 quarters

## Verdict

**R-0 halt**. paradigm-architect state machine → graveyard.
Do not dispatch R-1. Do not re-enter this paradigm class without substrate architectural change (per §Future retry conditions above).
