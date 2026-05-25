# Graveyard — paradigm 164 `alt_bvol_implied_vol_term_structure_inversion_directional_4h`

**Verdict**: `R0_HALT_DISPATCH_IMPOSSIBLE_SUBSTRATE_SHAPE_MISMATCH_PLUS_FALLBACK_FAMILY_PROXY`
**Phase**: R-0 (prescreen halt — R-1 not dispatched, fallback also halted)
**Executed at KST**: 2026-05-21 21:22
**Host**: hcp_local
**Counter**: 163 → 164 (non-PASS streak 34: 130–164 excluding R-5 LIVE promotions)

---

## Hypothesis

BTC/ETH implied volatility (IV) term structure inversion event × per-asset 4h directional, sign-conditional bilateral 4-quadrant SNT.

- **Trigger**: Deribit IV front-month vs 3-month ratio crosses inversion threshold (front > back)
- **Mechanism**: forward-looking trader-stress indicator → 4h price MR (LONG capitulation reversion) or continuation (SHORT vol cascade)
- **Universe**: 2 syms (BTCUSDT + ETHUSDT)
- **Substrate proposed**: Deribit public free API (DVOL or options chain `mark_iv`)

---

## R-0 Findings (R-1 not dispatched)

### Step 0 — Lesson #69 §next-action factual audit obligation (1st post-candidate dogfood)

**2/2 §next-action errors caught pre-dispatch**:
1. **Sample density miscalculation**: 2 syms × 2.25yr × ~5% event rate ≈ 200 events, per-quarter n ≈ 13.7 < 30 (Lesson #11 borderline violation, not acknowledged in §next-action).
2. **Substrate-shape misclassification**: "BVOL/DVOL term structure" claim implies multi-tenor IV history. Empirical verification:
   - `get_volatility_index_data` returns **single-tenor 30d forward IV** (Deribit's single VIX-equivalent index), 200 OK 2.4yr+ historical ✓ — but NOT a term structure
   - `get_book_summary_by_currency` returns options-chain snapshot `mark_iv` per instrument — usable to compute term structure NOW but no historical chain endpoint free
   - History-files (`.tar.gz` archives) require non-trivial scraping infrastructure + bandwidth >30min (CRITICAL halt condition in agent spec) + freemium-grey area

### Step 1 — Lesson #61 inventory PASS
- Slug grep `bvol|implied_vol|term_structure|deribit|dvol|option|vol_index` → **0 hits** in 163-deep history
- Zero prior implied-vol paradigms — strong novelty confirmed

### Step 2 — Lesson #28 substrate availability — **FATAL FAIL (shape mismatch)**

**Substrate-existence**: PASS (Deribit DVOL endpoint 200 OK, public, free, 2.4yr+ depth)
**Substrate-shape**: **FAIL** — single-tenor 30d ≠ multi-tenor term structure required by hypothesis.

**Verified empirically**:
- `https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp=1672531200000&end_timestamp=1672617600000&resolution=3600` → 200 OK, 25 hourly bars 2023-01-01, single OHLC series
- `https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=ETH&start_timestamp=1700000000000&end_timestamp=1700010000000&resolution=3600` → 200 OK, ETH DVOL available
- `https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option` → 200 OK, ~400KB response, snapshot only with per-instrument `mark_iv`, NO timestamp-range parameter for historical
- `https://www.deribit.com/api/v2/public/get_index_price?index_name=btc_dvol` → 400 "invalid index" (direct index price endpoint not exposed — only via volatility_index_data with OHLC shape)

**Paid alternatives violate [[feedback-no-freemium-trial]]**: Tardis (paid), Amberdata (paid), Kaiko (paid). Deribit history-files freemium-grey + bandwidth halt.

### Step 3 — Lesson #11 sample density borderline VIOLATION
- 2 syms × 2.25yr × 5% inversion event rate ≈ 200 events
- 4-quadrant × 9 quarters → per-cell n ≈ 13.7 < 30 cutoff
- Would block dispatch even if substrate worked

### Step 4 — Family-distinct strict 4-dim PASS
| Dimension | paradigm 164 | DNA distance |
|---|---|---|
| Statistic class | forward IV term structure ratio | NEW |
| Universe | 2 syms BTC+ETH | DIFFERENT (13-alt majority) |
| Entry-side class | IV ratio cross-up event | DIFFERENT |
| Mechanism alpha | forward-looking trader stress | NEW (forward-looking IV vs all-backward statistic prior) |

4/4 NOVEL (Lesson #62 strong PASS — but academic since §2 fatal)

### Step 5 — Lesson #19 SNT design valid but un-executable
- A focus: IV inversion × LONG (Lesson #42 capitulation MR class)
- A mirror: IV inversion × SHORT
- B same-sign: steep contango × SHORT
- B mirror: steep contango × LONG

---

## Fallback Path — `alt_perp_swap_basis_term_structure_8h_funding_vs_3m_calendar_carry_differential_directional_4h`

**Fallback HALT — double family-proxy violation (Lesson #56 OUTCOME-LEVEL)**:

| Family | Status | Cumulative graveyards | Verdict |
|---|---|---|---|
| Funding axis | Tier 4 retire (Lesson #54 candidate post-confirmation) | 11 (73/79/96/97/98/99/103/132/134/135 + boundary subfamily); paradigm 22 R-5 exception only | Family-proxy violation |
| Basis axis | 3 prior graveyards: `alt_basis_spike`, `binance_perp_mark_index_basis_extreme`, `hmm_realized_vol_state_x_markprice_basis_extreme` | 3 cumulative | Advisory caution |
| Calendar futures (USDT-margined) | Substrate-limited (Binance has minimal USDT calendar futures vs coin-margined) | n/a | Substrate audit deferred |

Fallback not eligible without explicit Lesson #56 escape mechanism → second R-0 HALT confirmed.

---

## Lesson Updates

### Lesson #69 candidate — 1st post-candidate dogfood
- 2/2 §next-action factual errors caught pre-dispatch
- Strong support for confirmed-자격 status (recommend ratification after 2nd consecutive successful dogfood)
- Refined definition: paradigm-architect §next-action recommendations must include explicit factual audit of each load-bearing claim (substrate-shape, per-quarter n, DNA 4-dim table, slug grep)

### Lesson #28 amendment candidate — substrate-shape vs substrate-existence
- New candidate amendment: substrate availability prescreen must distinguish between substrate-existence (endpoint reachable + public + free) and substrate-shape (data structure matches hypothesis dimension)
- Case study: Deribit DVOL substrate-existence PASS + substrate-shape FAIL (single-tenor ≠ term structure)
- Refinement: Lesson #28 prescreen must include "minimum viable data shape" specification matching hypothesis dimension

### Lesson #61 amendment — 6th post-confirmation SUCCESS
- 6 consecutive post-amendment dispatches with explicit slug grep + DNA 4-dim audit table
- 영구 자산화 strengthened

### Lesson #56 OUTCOME-LEVEL family proxy — 16th instance
- Fallback funding × basis composite blocked by double family-proxy violation
- Consistent with confirmed status (15+ prior instances)

### Lesson #62 — 9th boundary dogfood
- 4/4 NOVEL family-distinct count computed and documented (academic since §2 fatal)

---

## paradigm 165 Next-Action

**1순위 권고**: candidate C (OI decay × taker-imbalance event compound statistic) — compound statistic likely 4/5 novel, both substrates verified prior, OI/taker families not jointly Tier 4 retire.

**Lesson #69 strict factual audit obligation for paradigm 165 R-0**:
1. Slug grep (Lesson #61)
2. Substrate-existence + substrate-shape audit (Lesson #28 + amendment candidate)
3. Per-quarter n calculation (Lesson #11)
4. DNA 4-dim table (Lesson #62)
5. Family-proxy cross-reference (Lesson #56 OUTCOME-LEVEL)

Forward-collection of options-chain snapshots may unblock implied-vol family at 2026-07-22+ (60d depth from today).

---

**KST**: 2026-05-21 21:22 KST
