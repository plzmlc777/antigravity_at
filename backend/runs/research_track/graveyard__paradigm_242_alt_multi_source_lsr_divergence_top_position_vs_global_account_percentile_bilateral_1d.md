# paradigm 242 — alt_multi_source_lsr_divergence_top_position_vs_global_account_percentile_bilateral_1d

**Phase reached**: R-0 (pre-R-1 halt)
**Verdict**: `R0_HALT_BY_COMPOUND_LESSON_61_56_62_80A_11_DNA_DUPLICATE_FAMILY_PROXY`
**Timestamp KST**: 2026-08-01
**Compute saved**: ~4-6 hr R-1 sweep (14 syms × 3 T × 3 hold × 4 quadrant = 504 sub-runs) + R-2 multi-symbol expansion

---

## Hypothesis

`div = rolling_pct90(toptrader_position_ls_ratio) − rolling_pct90(global_account_ls_ratio)` at |div|≥T predicts 1d–4d directional alpha via information asymmetry between smart-money (top-trader) and crowd (all-account) positioning. Standard 4-quadrant SNT bilateral.

## Data sources

- `backend/runs/microstructure/{SYM}_full_metrics.joblib` — `toptrader_position_ls_ratio` + `global_account_ls_ratio`, 5m frequency, 155k–256k rows per sym.
- `backend/runs/ohlcv_cache/{SYM}_1m.joblib` — close resample.
- Universe: 14-sym microstructure cohort (SOL primary tested).

## Halt cause — compound R-0 gate

### 1. Lesson #61 slug grep — DIRECT HIT (dispatch-brief mandatory item 1)

`grep -rl "top_global_lsr\|multi_source_lsr\|lsr_divergence" backend/runs/research_track/` returned:

- `backend/runs/research_track/_graveyard/top_global_lsr_divergence/` — **paradigm 22 (2026-05-06)**, 21 metrics files + GRAVEYARD_NOTE.md.

Prior paradigm 22 tested precisely `top - global` LSR divergence on the same substrate, same 10-sym cohort (SOL/AVAX/ETC/LINK/COMP/AXS/UNI/LDO/HBAR/DOGE), same bilateral direction structure (follow_top / fade_top), same hold horizon family (12/24/48h ⊇ 1d/2d/4d).

### 2. Lesson #62 DNA 5-dim overlap vs paradigm 22 — HARD FAIL (5/6 overlap ≥ duplicate threshold)

| Dim | paradigm 22 (top_global_lsr_divergence) | paradigm 242 | Overlap |
|---|---|---|---|
| Data columns | `toptrader_position_ls_ratio` + `global_account_ls_ratio` | Same 2 columns | **MATCH** |
| Substrate | microstructure joblib 5m | Same | **MATCH** |
| Universe | 10-sym alt cohort | 14-sym includes same 10 | **MATCH (superset)** |
| Direction axis | Bilateral (follow / fade) | Bilateral 4-quadrant SNT | **MATCH** |
| Hold horizon | 12h / 24h / 48h | 1d / 2d / 4d | **MATCH (overlapping)** |
| Statistic transform | z(top − global, 288-bar rolling) | pct90(top) − pct90(global) | Different transform |

**5/6 dims overlap. paradigm-architect.md halt rule: "Halt on DNA duplicate (5/6 dim overlap)" is triggered.**

The dispatcher brief's DNA table (compared vs paradigms 16/233/238) omitted paradigm 22, which is the closest DNA match by a wide margin.

### 3. Lesson #56 outcome-level family proxy — 20th cumulative dogfood

paradigm 22 prior R-2 result on the same 10-sym cohort (`ft_z2.5_h48` best cell that borderline-passed R-1):

| Symbol | Alpha% | Sharpe | Verdict |
|---|---|---|---|
| AVAXUSDT | +86.7 | +0.84 | best (still short of gate) |
| SOLUSDT | +30.6 | +0.11 | R-1 anchor |
| ETCUSDT | -0.8 | -1.35 | fail |
| LINKUSDT | -12.1 | -1.13 | fail |
| COMPUSDT | -17.1 | -1.89 | fail |
| AXSUSDT | -27.2 | -1.68 | fail |
| UNIUSDT | -27.7 | -1.25 | fail |
| LDOUSDT | -32.6 | -1.18 | fail |
| HBARUSDT | -36.9 | -2.51 | fail |
| DOGEUSDT | -51.2 | -3.08 | fail |

- **alpha pos: 2/10 (20%)** — catastrophic vs Lesson #16 concentration gate (need ≥30%)
- **alpha_mean: -8.82** — negative average across cohort
- Prior explicit graveyard-note conclusion: "LSR data is noisy; top vs global gap is not a systematic signal; classical smart-money-vs-retail intuition NOT confirmed at 5m microstructure granularity."

**Under Lesson #56, monotone-equivalent statistical transforms on the same cross-stream, same substrate, same cohort produce the same outcome family**. Pct90 differencing vs 288-bar-z of raw difference are both "extract cross-stream divergence in a normalized frame" — the family outcome is falsified.

### 4. Lesson #80-A (paradigm 238 candidate, 1st dogfood) — LSR-family universal Lesson #79 failure

paradigm 238 (2026-07-27) documented the emerging lesson: `LSR-family universal Lesson #79 failure across all substrate column variants (toptrader_account, toptrader_position, global_account)`. The joint-multi-source formulation combines two proven-dead columns. paradigm 242 is the 2nd dogfood of Lesson #80-A — confirming that joint combinations of L80-A-retired columns inherit family retirement (percentile-differencing does not resurrect predictive content).

### 5. Lesson #79 predictive-content empirical pretest — MIXED (1d FAIL, 4d nominal pass but insufficient)

Executed per dispatch-brief mandatory item 2:

**Overlapping-bar corr (naïve, autocorrelation-inflated)**:
| Sym | Hold | n_oos | corr |
|---|---|---|---|
| SOLUSDT | 1d | 121,515 | +0.0125 |
| SOLUSDT | 4d | 121,083 | +0.0903 |
| BTCUSDT | 1d | 71,269 | +0.0347 |
| BTCUSDT | 4d | 70,837 | +0.0183 |

Max |corr| = 0.0903 nominally PASS 0.02 gate — but this is the naïve autocorrelation-inflated statistic per candidate Lesson #80-B (paradigm 238).

**Non-overlap sampled corr (block every 1152 bars = 4d, truly IID)**:
| Sym | Hold | n_iid | corr | t (IID) |
|---|---|---|---|---|
| SOLUSDT | 1d | 422 | +0.008 | +0.16 |
| SOLUSDT | 4d | 106 | +0.127 | +1.31 |

Under IID sampling: 1d FAIL (0.008 < 0.02); 4d nominal above threshold (0.127) but t=1.31 < 2 (not significant).

**4-quadrant net edge at T=0.3 (SOL non-overlap, 4d)**:

| Quadrant | n | gross bp | net bp | t |
|---|---|---|---|---|
| A_focus LONG (div≥+0.3) | 27 | +76.4 | +60.4 | +0.52 |
| A_mirror SHORT (div≥+0.3) | 27 | -76.4 | -92.4 | -0.79 |
| B_focus SHORT (div≤-0.3) | 27 | +117.0 | +101.0 | +0.66 |
| B_mirror LONG (div≤-0.3) | 27 | -117.0 | -133.0 | -0.88 |

**Per-cell n=27 fails Lesson #11 cutoff of 30 events/cell. All 4 quadrant t-stats < 2 (no signal_t_excess ≥ 2 possible). Further partitioning into 4 quarters would yield ~1.7 events/quarter/quadrant — 18× below cutoff.**

### 6. Lesson #11 sample density prescreen — FAIL at meaningful T threshold

On SOL non-overlap 4d at T=0.3: n_per_cell=27 (< 30). Lowering T to expand sample would drown the divergence-extreme mechanism (median |div| ~0.15 across full distribution). Expected per-cell-per-quarter density ≪ 30.

### 7. Fee floor prescreen — INDISTINGUISHABLE FROM PARADIGM 22 EMPIRICAL

paradigm 22 R-1 anchor cell (ft_z2.5_h48 SOL): alpha 30.6% sharpe 0.11 n=428 — passed R-1 borderline yet R-2 collapsed. paradigm 242 SOL 4d non-overlap best cell: net +101bp n=27 t=+0.66 — much thinner sample, more marginal significance than paradigm 22's R-1 anchor. Under Lesson #56 family proxy, expected R-2 outcome ≈ paradigm 22's R-2 (alpha 2/10, alpha_mean negative).

---

## Compound halt verdict

| Item | Lesson | Result |
|---|---|---|
| 1 | #61 slug grep | HIT `top_global_lsr_divergence` |
| 2 | #79 predictive content | 1d FAIL / 4d nominal pass but insufficient sample |
| 3 | #28 substrate audit | PASS (both cols present 14 syms) |
| 4 | #62 DNA 5-dim vs paradigm 22 | **HARD FAIL 5/6 overlap** |
| 5 | #56 outcome-level family proxy | **FAIL** (paradigm 22 R-2 catastrophic 2/10) |
| 6 | #11 sample density at T=0.3 4d | **FAIL** (n=27 < 30 per-cell, ~1.7 per quarter-quadrant) |
| 7 | #40 structural threshold feasibility | PASS (|div| spans ±1) |
| 8 | #39 direction-axis pre-check | PASS (non-OHLCV both axes) |
| 9 | Fee floor prescreen | FAIL (per Lesson #56 inference from paradigm 22 R-2 collapse) |
| 10 | L80-A LSR-family universal Lesson #79 failure | 2nd dogfood — joint formulation from L80-A retired family |

**R-0 HALT**: The dispatch brief's novelty argument ("percentile divergence is a new statistic transform") is invalidated because (a) 5/6 DNA overlap with paradigm 22 exceeds the DNA-duplicate ceiling regardless of statistic transform, and (b) Lesson #56 governs outcome equivalence over statistic transforms within the same substrate + universe + direction + hold family.

---

## Lessons dogfooded

1. **Lesson #61 slug grep** — post-confirmation asset dogfood (~30th cumulative). Success: verbatim substring `lsr_divergence` matched `top_global_lsr_divergence` graveyard tree.
2. **Lesson #62 DNA 5-dim check** — HARD FAIL 5/6 overlap on primary duplicate. Dispatch brief's DNA table (vs 16/233/238) omitted the closest predecessor (paradigm 22).
3. **Lesson #56 outcome-level family proxy** — 20th cumulative instance. Percentile-of-each vs z-of-difference of same two microstructure columns → same outcome family.
4. **Lesson #79 predictive-content pretest** — mixed empirical (1d FAIL, 4d nominal pass but sample-thin). Not the primary halt cause; superseded by #61 + #56 + #62.
5. **Lesson #80-A (candidate)** — 2nd dogfood. LSR-family joint-formulation inherits family retirement.
6. **Lesson #80-B (candidate)** — non-overlap sampling reveals the naïve corr on 4d (0.09) is autocorrelation-inflated; IID t=1.31 is not significant.
7. **Lesson #11 sample density** — at meaningful T=0.3, per-cell n=27 fails 30-event floor.

## New lesson candidate

**Lesson candidate #83 — "joint multi-source rescue of family-saturated substrate"**: When two data columns each individually fail Lesson #79 (or belong to a family-retired substrate under Lesson #80-A), their divergence / percentile-difference / ratio / log-ratio combinations do NOT restore predictive content beyond the individual columns' baseline. The joint transform preserves the underlying substrate's information ceiling. **1st dogfood at paradigm 242**. Prescription: before proposing joint-multi-source formulations, verify that at least ONE component column has a documented Lesson #79 PASS in isolation.

## Next-paradigm recommendation

The LSR family is exhausted across all tested formulations:
- Single-column level z (paradigm 238) → L79 FAIL
- Single-column velocity (paradigm 233) → graveyard
- Contrarian level (paradigm 16) → live but stale
- Cross-stream difference z (paradigm 22) → R-2 collapse
- Cross-stream percentile difference (paradigm 242) → R-0 duplicate

**Recommend Tier 4 retire of LSR-family substrate at next ratification batch** (paradigm 16 R-5 LIVE grandfathered exception only).

Suggested next slug: **out-of-LSR-family substrate**. Options ranked by novelty × Lesson #77 non-OHLCV compliance:
1. **`alt_cross_exchange_funding_rate_dispersion_binance_okx_bybit_percentile_bilateral_4h`** — funding-rate dispersion across 3 CEX (Binance, OKX, Bybit) via ccxt free tier; genuine cross-venue microstructure axis; no overlap with any tested paradigm; L80-A does not apply (funding rate ≠ LSR family). Substrate: `binance_funding_rate` + ccxt/OKX + ccxt/Bybit funding endpoints (free, rate-limited).
2. **`alt_perp_index_price_deviation_from_spot_index_percentile_bilateral_4h`** — perp mark price vs spot index deviation z (uses `binance_futures_premium_index` if present, else compute from spot vs perp mark); untested family; distinct from LSR and funding.
3. **`alt_orderbook_liquidity_asymmetry_top10_depth_bid_ask_ratio_bilateral_1d`** — L2 book snapshot bid/ask depth ratio; requires book snapshot substrate (check if `binance_book_ticker_snapshot` table exists).

Preferred: option 1 (funding rate dispersion) — highest novelty score, lowest infrastructure risk, cleanly outside all retired families.
