# paradigm 164 — `alt_bvol_implied_vol_term_structure_inversion_directional_4h`

**Status**: R-0 HALT — Lesson #28 substrate mismatch + Lesson #11 sample density borderline + Lesson #69 §next-action factual audit catches misclassification

**Counter**: 163 → 164 (non-PASS streak 34)
**Host**: hcp_local
**Executed at KST**: 2026-05-21 21:22 KST

---

## Hypothesis (as proposed)

- **Statistic**: Deribit implied volatility (IV) term structure — front-month (e.g., 30d) vs back-month (e.g., 90d/180d) IV ratio
  - Normal: contango (front < back, ratio < 1.0)
  - Inversion: backwardation (front > back, ratio > 1.0)
- **Mechanism**: Term-structure inversion = short-term trader stress → 4h price LONG (capitulation reversion) OR SHORT (vol cascade continuation), sign-conditional bilateral
- **Universe**: BTCUSDT + ETHUSDT (2 syms, Deribit liquid options coverage)
- **Hold**: 4h primary + 8h/12h sweep
- **Substrate**: Deribit public free API (DVOL/BVOL or options chain `mark_iv`) + Binance Futures klines for entry/exit
- **R-1 design**: 4-quadrant Symmetric Negative Test (Lesson #19)

---

## R-0 Inventory Audit (Lesson #61 amendment 6th post-confirmation strict + Lesson #69 candidate 1st post-candidate application)

### Step 0 — Lesson #69 §next-action factual audit obligation (1st post-candidate dogfood)

| §next-action claim | Verification method | Empirical result | Verdict |
|---|---|---|---|
| "zero prior implied-vol paradigm" | `ls research_track/ \| grep -iE 'bvol\|implied_vol\|term_structure\|deribit\|dvol\|option\|vol_index'` | **0 hits** in entire paradigm history (1–163) | **CONFIRMED ✓** |
| "Deribit BVOL public free API compliant" | `curl https://www.deribit.com/api/v2/public/get_volatility_index_data` × {BTC, ETH} × {2023-01-01, 2023-11-15, current} | DVOL endpoint = 200 OK, public, no auth, no API key, 2.4yr+ historical depth ✓ | **CONFIRMED ✓** for single-tenor DVOL only |
| "4/5 STRICT family-distinct" | DNA dimension audit (see §1.b below) | 4 dims novel (statistic / universe / entry / mechanism) | **CONFIRMED ✓** |
| "2 syms BTC+ETH sample density" | 2 syms × 2.25yr × 5% event rate = 200 events / 4-quadrant × 4 quarters = per-cell ~12 | per-quarter n=12 < 30 cutoff | **VIOLATION** Lesson #11 (borderline) |
| **IMPLICIT**: "front-month vs 3-month IV ratio is historically measurable from Deribit free API" | DVOL endpoint inspection + options chain endpoint inspection | DVOL = single-tenor 30d index ONLY. Options chain `get_book_summary_by_currency` returns snapshot `mark_iv` per instrument, but NO historical-chain free endpoint exists (Deribit history-files require paid tier or scraping). Cannot reconstruct historical term structure from free API. | **REFUTED ✗** Lesson #28 substrate fatal |

**Lesson #69 (1st post-candidate dogfood) catches 2 §next-action errors**:
1. **Sample density borderline** (per-quarter n=12, would warrant Lesson #11 halt even if substrate worked)
2. **Fundamental substrate misclassification**: DVOL is NOT a term structure but a single forward-30d index. Free Deribit endpoint does not provide historical multi-tenor IV. The stated mechanism cannot be measured historically without paid data feed (Deribit history-files, Tardis, or similar — all violate [[feedback-no-freemium-trial]]).

**Lesson #69 candidate verdict — 2/2 errors caught pre-dispatch** → strong dogfood support for confirmed-자격 status.

### Step 1 — Lesson #61 amendment INVENTORY CHECK (6th post-amendment dogfood)

#### 1.a Slug grep result
```
ls research_track/ | grep -iE "bvol|implied_vol|term_structure|deribit|dvol|option|vol_index"
→ 0 hits (zero prior implied-vol/options/term-structure paradigms in 163-deep history)
```

#### 1.b DNA 4-dim audit table

| Dimension | paradigm 164 (proposed) | Closest prior | DNA distance |
|---|---|---|---|
| Statistic class | IV term structure ratio (forward-looking options) | (none — first options-derived paradigm) | NEW |
| Universe | 2 syms (BTC+ETH only, Deribit liquid coverage) | 13-14 alts (paradigm 134/135 etc) | DIFFERENT |
| Entry-side class | IV ratio cross-up event (front/back > 1.0) | funding cross-up, oi cross-up, premium z | DIFFERENT statistic source |
| Mechanism alpha | Forward-looking trader-stress signal → MR or continuation | RV (realized backward), funding (carry), OI (positioning) | NEW (forward-looking IV) |

**Strict family-distinct count: 4/4 NOVEL** → Lesson #62 strong PASS (8 boundary dogfoods reinforced).

#### 1.c Prior R-3+ verdict
- Zero implied-vol/options paradigms in entire 163-deep history
- No R-3+ promotions in IV/options class to cross-reference
- No family-proxy violations expected

### Step 2 — Lesson #28 substrate availability STRICT (CRITICAL — **FATAL FAIL**)

**Substrate verification matrix**:

| Endpoint | Status | Coverage | Data shape | Sufficient for hypothesis? |
|---|---|---|---|---|
| `public/get_volatility_index_data` (DVOL) | 200 OK ✓ | BTC + ETH × 2.4yr+ × 1h resolution | **single-tenor 30d forward IV** (OHLC) | **NO — single tenor only** |
| `public/get_historical_volatility` | 200 OK ✓ | BTC × full history × hourly | realized vol (backward) | **NO — backward-looking, not IV** |
| `public/get_book_summary_by_currency` | 200 OK ✓ | All BTC/ETH options snapshot | `mark_iv` per instrument | **NO — snapshot only, no historical chain endpoint free** |
| `public/get_instruments` | 200 OK ✓ | Active + expired option contracts | metadata only | **NO — no IV history** |
| Deribit history-files (`.tar.gz` archives) | Public listing exists but per-file scraping required | Hour-level granularity ~5-10 GB per currency per year | full options chain replay | **POTENTIALLY VIOLATES [[feedback-no-freemium-trial]]** — requires non-trivial scraping infrastructure + bandwidth >30min ETA (CRITICAL halt condition in agent spec) |

**Lesson #28 verdict**: **DISPATCH_IMPOSSIBLE_SUBSTRATE_SHAPE_MISMATCH**. The DVOL index, while public/free/2.4yr+/historical, is a **single 30d forward tenor**, not a multi-tenor term structure. The stated hypothesis ("front-month vs 3-month IV ratio") cannot be measured historically from any free Deribit endpoint. Reconstructing term structure would require:
- (a) Deribit history-files paid/manual scraping (bandwidth + freemium concerns)
- (b) Third-party paid feeds (Tardis, Amberdata — both paid, violate [[feedback-no-freemium-trial]])
- (c) Forward-collection of options-chain snapshots starting today (no historical depth, ~60d minimum to begin testing, deferred per Frontier Scout meta decline path)

**Freemium audit**: Deribit core API is fully free, public, unlimited within rate-limit. DVOL/historical_volatility/options-chain-snapshot all PASS [[feedback-no-freemium-trial]]. ONLY the history-file archives blur the line (technically public listing, but operationally paid-tier convenience). Conservative interpretation: **the data we CAN access is shape-mismatched; data we WOULD need is freemium-grey**. R-0 HALT.

### Step 3 — Lesson #11 sample density (would be borderline even if substrate worked)

- Universe: 2 syms (BTC + ETH)
- Window: 2.25yr / 2.4yr = 93.75% (Lesson #30 PASS)
- Estimated event rate: ~5% (term-structure inversion is rare; in equity, VIX term structure inverts ~5-10% of trading days)
- Total events: 2 × 2.25yr × 365d × 6 (4h bars/day) × 0.05 ≈ 493 events theoretical max
- Per-quadrant (4-quadrant SNT) × per-quarter (9 quarters in 2.25yr): **per-cell n ≈ 493 / 4 / 9 ≈ 13.7** < 30 cutoff

**Lesson #11 verdict**: borderline VIOLATION at per-quarter granularity. Concentration Gate would likely flag insufficient per-quarter-positive ratio. Would warrant R-0 HALT even if substrate were available.

### Step 4 — Family-distinct strict 4-dim audit (Lesson #62 CONFIRMED, 8 boundary dogfoods reinforced)

See §1.b table — 4/4 dimensions NOVEL → strong family-distinct PASS. (Would qualify for dispatch IF substrate were viable.)

### Step 5 — Lesson #19 Symmetric Negative Test 4-quadrant design (deferred)

- A focus: IV inversion × LONG (capitulation reversion)
- A mirror: IV inversion × SHORT (volatility cascade continuation)
- B same-sign: IV steep contango × SHORT (mean reversion from extreme)
- B mirror: IV steep contango × LONG
- **Design valid but un-executable due to §2 substrate fatal**

### Step 6 — Lesson #30 data window ratio
- 2.25yr / 2.4yr = 93.75% ✓ PASS (if substrate existed)

### Step 7 — Lesson #62 retiming reframe family-distinct
- See §1.b — 4/4 NOVEL strong PASS

### Step 8 — Lesson #56 OUTCOME-LEVEL family proxy
- IV/options family graveyards: 0 → strong OUTCOME-LEVEL escape (if substrate existed)

### Step 9 — Lesson #21 axis stacking
- Single axis (IV term-structure ratio) × single mechanism — no axis stacking → PASS

### Step 10 — Lesson #58 same-bar same-substrate
- IV signal (Deribit options) + price (Binance perp) = cross-substrate exemption #21 → PASS

### Step 11 — Mirror hypothesis antipattern
- Sign-conditional bilateral 4-quadrant SNT in single batch → exemption PASS

### Step 12 — Lesson #67 candidate ESCAPE
- Per-asset IV (BTC self vs ETH self), no cross-asset broadcast → ESCAPE

### Step 13 — Lesson #68 candidate ESCAPE
- Per-asset IV inversion event, no session-boundary universe anchor → ESCAPE

### Step 14 — Lesson #42 CONFIRMED cross-reference
- paradigm 164 A focus = IV inversion × LONG (capitulation reversion) ∈ Lesson #42 prediction class
- Mechanism class compatible with capitulation MR alpha-side prediction (would warrant Concentration check on A focus side if executable)

---

## Fallback Path Audit — `alt_perp_swap_basis_term_structure_8h_funding_vs_3m_calendar_carry_differential_directional_4h`

**Cross-reference table**:

| Family | Tier 4 retire? | Cumulative graveyards | Eligible for new variant? |
|---|---|---|---|
| Funding axis | YES (Lesson #54 candidate post-confirmation) | 11 cumulative (73/79/96/97/98/99/103/132/134/135 + boundary subfamily) — paradigm 22 exception only | NO (family-proxy violation, Lesson #56) |
| Basis axis | Not formal Tier 4 but 3 prior graveyards: `alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h`, `binance_perp_mark_index_basis_extreme_alt_directional_4h`, `hmm_realized_vol_state_x_markprice_basis_extreme_alt_directional_4h` | 3 cumulative | Borderline — Lesson #56 OUTCOME-LEVEL family proxy advisory |
| Calendar futures (Binance USDT-margined quarterly) | Substrate-limited (Binance has limited USDT calendar futures vs coin-margined) | n/a | Substrate audit required |

**Fallback verdict**: Funding + basis composite = **double family-proxy violation** (Lesson #56 OUTCOME-LEVEL). Fallback not eligible without explicit Lesson #56 escape mechanism (which would need novel statistical class outside both retired families). Calendar substrate audit deferred — no Binance USDT-margined calendar futures with sufficient 2.25yr historical depth confirmed.

**Fallback HALT verdict**: Second R-0 HALT confirmed. Fallback path also blocked.

---

## R-0 Final Verdict — DISPATCH_IMPOSSIBLE_SUBSTRATE_SHAPE_MISMATCH + FALLBACK_FAMILY_PROXY_VIOLATION

**R-1 NOT DISPATCHED** for either original or fallback. Reasons:

1. **Original (BVOL term structure)**: Deribit DVOL is single-tenor 30d index, not multi-tenor structure. Free API does not expose historical options-chain term structure. Paid alternatives violate [[feedback-no-freemium-trial]]. Lesson #28 substrate-shape mismatch (substrate exists but data shape ≠ hypothesis requirement).

2. **Fallback (perp swap basis × funding × calendar carry)**: Funding family Tier 4 retire (11 cumulative) + basis family advisory (3 cumulative) = Lesson #56 OUTCOME-LEVEL double family-proxy violation.

3. **Sample density secondary** (would block even if §1 substrate worked): per-quarter n=13.7 < 30 Lesson #11 borderline violation.

---

## Lesson Updates

### Lesson #69 candidate — §next-action factual audit obligation
**Status upgrade**: 1st post-candidate dogfood → **2/2 errors caught pre-dispatch** (sample density miscalculation + substrate-shape misclassification). Strong support for confirmed-자격 status. Recommend ratification after 2nd consecutive dogfood.

**Lesson #69 candidate definition (refined)**:
> Paradigm-architect §next-action recommendations must include explicit factual audit verification of each load-bearing claim:
> - **Substrate claim**: not just "API exists" but "data shape matches hypothesis requirement" (single-tenor vs term structure, snapshot vs history, etc.)
> - **Sample density claim**: per-quarter n calculation, not just total n
> - **Family-distinct count claim**: explicit DNA dimension table
> - **Prior paradigm claim**: explicit slug grep result
> Failure to verify any load-bearing claim → R-0 HALT with audit failure documented.

### Lesson #28 amendment candidate — substrate-shape vs substrate-existence distinction
**New candidate**: substrate availability prescreen must distinguish between:
- **Substrate-existence**: endpoint reachable, data accessible, public, free (Lesson #28 original scope)
- **Substrate-shape**: data structure matches hypothesis dimension (e.g., single-tenor index ≠ term structure; snapshot ≠ historical chain; realized vol ≠ implied vol)

Deribit DVOL case study: substrate-existence PASS (endpoint, free, 2.4yr depth) + substrate-shape FAIL (single-tenor ≠ multi-tenor term structure). Both checks required.

**Refinement to Lesson #28**: prescreen must include "minimum viable data shape" specification matching hypothesis dimension.

### Lesson #56 OUTCOME-LEVEL family proxy — 16th instance
- Fallback path (funding × basis) blocked by double family-proxy violation.
- Total OUTCOME-LEVEL escape failures: 16 cumulative (consistent with Lesson #56 CONFIRMED status, 15+ instances pre-paradigm-164).

### Lesson #61 amendment — 6th post-confirmation SUCCESS
- 6 consecutive post-amendment dispatches with explicit slug grep + DNA 4-dim audit table.
- Lesson #61 영구 자산화 strengthened.

### Lesson #62 — 9th boundary dogfood
- 4/4 NOVEL family-distinct count successfully computed and documented (would qualify for dispatch if substrate viable).

---

## paradigm 165 Next-Action Recommendation (Lesson #69 strict factual audit)

**1순위 권고**: defer further IV/options/term-structure paradigm dispatches until **forward-collection of options-chain snapshots** accumulates ≥60d depth, OR **paid options data tier** policy decision by user (currently blocked by [[feedback-no-freemium-trial]]).

**Alternative axes for paradigm 165** (each requires fresh R-0 audit; below claims are pre-audit hypotheses, not verified):

| Candidate axis | Statistic class | Universe | Substrate hypothesis (NOT YET VERIFIED) | Estimated family-distinct count |
|---|---|---|---|---|
| **A**: Liquidation cluster magnitude × forward 1h (intraday microburst) | Aggregated liquidation USD notional 1m spike | 13 alts | Binance Futures liquidation stream (forced-liquidations API or Coinglass-free, both freemium-audit required) | Likely 3/5 (liquidation family has paradigm 76 prior — would need slug grep) |
| **B**: BTC funding pay × ETH funding pay differential (cross-coin funding spread) | BTC funding × ETH funding ratio z-score | 2 syms (BTC+ETH) | Binance funding rate DB (verified ✓) | Likely 2/5 (funding family Tier 4 retire — likely REJECTED) |
| **C**: Open interest decay after large taker-imbalance event | OI(t+1h) / OI(t-1h) ratio post taker-imbalance spike | 13 alts | Binance OI 5m archive (verified prior) + aggTrade (substrate available) | Likely 4/5 (compound statistic novel) |
| **D**: Volume-weighted price (VWAP) deviation cross-quarterly anchor | Per-sym VWAP_1d - close_now / ATR | 13 alts | OHLCV (verified ✓) | Likely 3/5 (anchor variants need audit) |

**Lesson #69 strict factual audit obligation for paradigm 165**: each candidate above requires explicit:
1. Slug grep (Lesson #61)
2. Substrate-existence + substrate-shape audit (Lesson #28 + amendment candidate)
3. Per-quarter n calculation (Lesson #11)
4. DNA 4-dim table (Lesson #62)
5. Family-proxy cross-reference (Lesson #56 OUTCOME-LEVEL)

**Default recommendation if no clear leader**: candidate C (OI decay × taker-imbalance) — compound statistic likely 4/5 novel, both substrates verified prior, OI/taker families not Tier 4 retire (separately, only when joint).

---

## Artifacts

- `TASK.md` — this file
- INDEX.json entry: paradigm 164 `R-0_HALT_DISPATCH_IMPOSSIBLE_SUBSTRATE_SHAPE_MISMATCH_PLUS_FALLBACK_FAMILY_PROXY`
- PARADIGM_QUEUE_2026Q3.md §6.62 entry: paradigm 164 R-0 HALT + Lesson #69 2nd dogfood + Lesson #28 amendment candidate
- Graveyard report: `graveyard__alt_bvol_implied_vol_term_structure_inversion_directional_4h.md` (generated)

---

**KST**: 2026-05-21 21:22 KST
