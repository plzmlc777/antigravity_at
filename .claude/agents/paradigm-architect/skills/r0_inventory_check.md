# Skill: R-0 Inventory Check + Decomposition + Registration

> Parent agent: `paradigm-architect`
> Purpose: Pre-flight checks before generating R-1 code
> Tools: Bash, Read, Write
> Last sync: 2026-05-21 22:09 KST — Lesson #69 CONFIRMED 5-item strict template 영구 자산화 + Lesson #61 amendment PERMANENT ASSET ELEVATION + Lesson #28 amendment CONFIRMED + 15 formal Tier 4 family retires

## Step 0 — Lesson #69 CONFIRMED 5-item strict template (PERMANENT ASSET, 영구 의무)

**Every R-0 prescreen MUST execute all 5 items before R-1 dispatch consideration.** (CONFIRMED 2026-05-21, 4 post-CONFIRMED SUCCESSes paradigm 164/165/166/167 + 1 pre-CONFIRMED paradigm 163)

### Item 1 — Lesson #61 amendment slug grep (PERMANENT ASSET ELEVATED 2026-05-21, 8-streak)

```bash
ls /home/hcpark/antigravity/backend/runs/research_track/ | grep -iE "<keyword1>|<keyword2>|<keyword3>"
```

Report results explicitly. Cross-reference with all prior paradigms (graveyards + R-2+/R-3+/R-4/R-5 entries). Halt conditions:
- DNA 6/6 axis match with prior paradigm → R0_HALT_BY_DNA_DUPLICATE
- Algebraic equivalent (sign-convention flip + normalization re-labeling) → R0_HALT_BY_DNA_DUPLICATE (paradigm 166 vs paradigm 104 precedent)
- Family duplicate ≥ 4 prior graveyards → R0_HALT_BY_FAMILY_PROXY

§next-action recommendation when writing must include slug grep execution output. **Stale recommendation chain ≥2 consecutive triggers ratification of permanent-asset elevation status.**

### Item 2 — Lesson #28 amendment substrate-shape audit (CONFIRMED 2026-05-21, 4 dogfoods)

Endpoint reachability (existence) ≠ data structure dimension match (shape). Separate verification mandatory:

**Substrate-existence**: HTTP endpoint reachable? Free unlimited (`[[feedback-no-freemium-trial]]` compliant)?

**Substrate-shape**: 
- Data dimension matches hypothesis (e.g., multi-tenor term structure ≠ single-tenor index)
- Historical coverage ≥ 2.25yr
- Frame frequency matches hypothesis frame
- Aggregation possible across hypothesis universe

Fatal precedent: paradigm 164 Deribit DVOL endpoint PASS + shape FAIL (single-tenor 30d forward IV ≠ multi-tenor term structure). Halt with `R0_HALT_BY_SUBSTRATE_SHAPE_MISMATCH`.

### Item 3 — Lesson #11 sample density (per-quarter n ≥ 30 cutoff)

```
expected_n_per_cell = total_windows × universe_size × trigger_rate
expected_n_per_quarter = expected_n_per_cell / 9_quarters
```

Halt if `expected_n_per_quarter < 30` cutoff. Particularly strict for joint-trigger paradigms (4-quadrant SNT cell count multiplier).

### Item 4 — Lesson #62 CONFIRMED DNA 4-dim audit table (11 boundary dogfoods)

Tabulate vs all proximate prior paradigms:

| Dim | Prior paradigm X | Candidate | Strict? |
|---|---|---|---|
| Statistic class | ... | ... | ✓/✗/partial |
| Universe scope | ... | ... | ✓/✗/partial |
| Entry-side class | ... | ... | ✓/✗/partial |
| Mechanism alpha | ... | ... | ✓/✗/partial |
| Hold timescale | ... | ... | ✓/✗/partial |

Halt conditions:
- Strict count 0-1/5 → R0_HALT_BY_DNA_DUPLICATE
- Strict count 2/5 boundary case → boundary dispatch with explicit Lesson #62 dogfood logging
- Retiming reframe only (1 strict dim change) → Lesson #62 retiming-reframe HALT

### Item 5 — Lesson #56 CONFIRMED family-proxy OUTCOME-LEVEL cross-reference table (17+ instances cumulative)

Tabulate all family-proxy intersections:

| Family | Status | Cumulative members | OUTCOME-LEVEL prediction |
|---|---|---|---|
| <family A> | Tier 4 retire | n=X graveyards | fee-floor sub-threshold |
| <family B> | advisory caution | n=Y | per-trade edge sub-2% |

Halt conditions:
- ≥ 2 family intersections → R0_HALT_BY_COMPOSITE_FAMILY_FALSIFICATION
- ≥ 4 cumulative graveyards in same family + same axis-class → OUTCOME-LEVEL family-proxy 17th+ instance prediction → R0_HALT_BY_OUTCOME_PROXY

### Inventory check additional commands (cross-cutting)

```bash
PYTHONPATH=. python3 -m scripts.research.paradigm_index list
cd backend && source venv/bin/activate && PYTHONPATH=. python3 -m scripts.paper_session_cli status
```

Paradigm must be **paradigm-agnostic-novel** vs current paper sessions (different data, different decision mode, different time scale). If duplicates → STOP.

## Step 1 — Decomposition

Parse hypothesis into:
1. **DNA dimensions** (data source, decision mode, time scale, universe shape)
2. **Sub-hypotheses** (a/b/c — testable independently)
3. **Data dependencies** (DB tables, joblib files, external APIs)
4. **Falsification criteria** — what observation would refute each sub-hypothesis

Cross-check DNA against current paper pool's 8-paradigm DNA matrix (see `research_track_master.md` §0). If new paradigm shares 5/6 dimensions with an existing one → STOP, not novel enough.

## Step 2 — Register

```bash
PYTHONPATH=. python3 -m scripts.research.paradigm_index register \
  <paradigm_name> --hypothesis "..." --data-deps "..." --type E
```

## Lesson #11 prescreen (mandatory)

Before dispatching R-1, estimate sample density:
```
expected_n_per_cell = total_windows × universe_size × trigger_rate
```

If `expected_n_per_cell < 30` → halt at R-0, request sample-density expansion (universe widen or threshold relax) before proceeding.

## Family retire blocklist (mandatory R-0 halt)

Before generating R-1 code, cross-check the hypothesis against the following retired families. **Any match → HALT_BEFORE_R1 without dispatch**. Exceptions are enumerated explicitly.

### Listing event family — Tier 4 retire [2026-05-20]
**Scope retired**: Binance Futures USDS-M perp listing/delisting announcement, pre-announce leak, on-chain mint, token unlock cliff, and analog external lifecycle entry/exit events used as directional trigger × R-1 dispatch.

**Evidence (4 graveyards + 1 substrate-blocked)**:
- paradigm 87 `binance_delisting_announce_short_alt` — R-1 PASS_R1_FULL but R-2 FRAGILE_TEMPORAL_WF_FAIL (1/5 TS-CV PASS, 2025Q4 single-quarter cluster artifact)
- paradigm 88 `token_unlock_cliff_short_alt` — Phase 1 FAIL_SCOPE prescreen halt (cliff sparse 9:195 vs linear, exit-side fragility)
- paradigm 89 `listing_pre_announce_leak_long_alt` — Phase 0 DISPATCH_IMPOSSIBLE (pre-onboard substrate HTTP 404)
- paradigm 90 `stablecoin_mint_event_long_alt_24h` — Phase 1 HALT (3 independent fail modes including [[feedback_no_freemium_trial]] + delayed/indirect entry)
- paradigm 100 candidate `binance_perp_liquidation_cascade_event_alt_intraday` — DISPATCH_IMPOSSIBLE (4 substrate fail modes incl. forceOrders REST 폐기)

**HALT_BEFORE_R1 sub-mechanisms**:
1. Binance Futures perp delisting announcement directional any hold
2. Binance Futures perp pre-onboard window any direction (substrate 부재)
3. Token unlock cliff / vesting boundary exit-side directional
4. Stablecoin mint event delayed/indirect entry cross-asset cascade
5. Liquidation cascade event without WS recorder substrate accumulation
6. Any "listing announcement → forced supply/demand" variant lacking immediate-demand classification (lesson #27 amendment)

**Exception (single-allowed lifecycle paradigm)**:
- **`lifecycle_pump_decay`** (R-4 seeded, R-3 baseline cohort `runs/research_track/lifecycle_phase/r3__metrics.json`): post-onboard substrate available + entry-side immediate-demand + per-listing 30-day forward window + sample density via DAILY cron lifecycle-spawner. Day 30 baseline evaluation 2026-06-03+ via cohort methodology (variant-aware h30 ≥ +17.3% / h21 ≥ +19.2% / earlyexit_d14 ≥ +18.7% medians per `.claude/plans/day30_decision_protocol.md` §2 트랙 L).
- Listing event family R-1 변형 발의는 lifecycle Day-30 결과 메타학습 (2026-06-04+) 이후 family-distinct 새 sub-mechanism (예: cross-listing front-run, cross-exchange listing arbitrage, hard-fork pre-event) 발의 시에만 재검토 가능. 동일 mechanism class 단순 변형은 자원 낭비 차단.

**Reference**: PARADIGM_QUEUE_2026Q3.md §6.2 #25–#28 + [[project_paradigm_binance_delisting]] + [[project_paradigm_token_unlock_cliff]] + [[project_paradigm_listing_pre_announce]] + [[project_paradigm_stablecoin_mint]]

### Tier 4 formal retired families — 15 cumulative (2026-05-21 sync, ratified §6.66 paradigm 168 META RATIFICATION BATCH + prior commits)

**Auto-halt R-0 on hypothesis match. Exceptions explicitly enumerated.**

1. **Listing event family** (paradigm 87/88/89/90/100 — 4 graveyards + 1 substrate-blocked) — exception `lifecycle_pump_decay` R-5 LIVE 2026-05-21
2. **Funding single-signal sub-class** (paradigm 73/79/96/97/98/99 — 6 graveyards) — exception paradigm 22 R-5 + funding_dispersion R-5 ETCUSDT
3. **KR equity DART entry-side family** (paradigm 92/93/100/101/102 — 5 graveyards 4 axes exhausted)
4. **Cross-asset volume share single-side simple-z 1d-hold** (paradigm 94/95)
5. **Cross-exchange family** (paradigm 103/104/105 illiquid/147v1/147v2/148/160 — 7 cumulative, paradigm 166 R-0 halt 8th blocked) — OI axis decisively closed (paradigm 166 R0_HALT_BY_DNA_DUPLICATE_PARADIGM_104)
6. **OHLCV magnitude-confluence × directional-follow** (paradigm 78/84/85 등)
7. **Geometric path metrics alone** (paradigm 78)
8. **Taker-side aggressive volume family** (paradigm 23/60/72 — 3 graveyards)
9. **Taker imbalance directional family** (paradigm 142v2/143/165 — 3 dogfoods, Lesson #57 CONFIRMED formal, 12th cumulative ratified 2026-05-21)
10. **Range_volume_divergence family** (paradigm 110/115/137/150/152/153/154 — 7 graveyards, ratified 2026-05-21 commit 45e20e5b)
11. **btc_rv_p90_alts_directional family** (paradigm 62/67/68/70/155 — 5 graveyards + paradigm 69 R-5 LONG 270m unidirectional exception, ratified 2026-05-21)
12. **Magnitude-event family** (paradigm 117/158/162 — 3 reformulations 24h drawdown / 24h PUMP / 24h high anchor, ratified 2026-05-21 + lifecycle_pump_decay R-5 protection 외 sub-axis 차단)
13. **Basis/markPrice 4h MR sub-axis** (paradigm 105/111/121/131/167 — 5 cumulative blocked, ratified 2026-05-21 §6.66) — exception paradigm 22/24 R-5 daily follow momentum + term structure cross-tenor variant (paradigm 169 Option η path)
14. **HMM unsupervised decomposition family** (paradigm 119/121 — 2 graveyards, ratified 2026-05-21 §6.66) — exception supervised regime classifier (paradigm 69 BTC RV p90 threshold) + ground-truth event anchor (paradigm 22 funding cycle 8h)
15. **Liquidity-microstructure single-domain 4h-frame conjunction** (paradigm 105/111/121/131 — 4 graveyards, ratified 2026-05-21 §6.66) — exception microstructure 5m frame (paradigm 21/24/127/128 R-5 active) + multi-domain conjunction

### Advisory caution families (not yet Tier 4, ≥2 dogfoods)
- ATR-normalized magnitude breakout (paradigm 115 R-1 + paradigm 150 R-0)
- 5m microstructure single-domain (paradigm 80/82/83/85 — 4 cumulative, formal retire 직전)
- Universe-aggregate scalar statistic (paradigm 115/116/118 — 3 dogfoods, NARROW_SCOPE_LIFE_CHANGING_FAIL 일관)
- Calendar/clock-anchor 4h cross-asset (paradigm 113/157 — Lesson #68 candidate)
- CVD/orderflow imbalance single-domain (paradigm 138/139/140/141/142/143/163 — 7 cumulative)

## Reference
- `.claude/plans/research_track_master.md` §0 — 8-paradigm DNA matrix
- `.claude/plans/day30_decision_protocol.md` §2 트랙 L — lifecycle cohort methodology + variant baselines
- `backend/scripts/research/paradigm_index.py`
- Lesson #11 (Q3 sample-density prescreen)
- Lesson #41 DIFFUSE_POSITIVE_CONCENTRATION_FAIL verdict (2026-05-20 confirmed-with-amendment) — see `lesson_prescreen_checklist.md`
