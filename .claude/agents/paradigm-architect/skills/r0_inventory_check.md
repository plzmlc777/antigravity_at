# Skill: R-0 Inventory Check + Decomposition + Registration

> Parent agent: `paradigm-architect`
> Purpose: Pre-flight checks before generating R-1 code
> Tools: Bash, Read, Write

## Step 0 — Inventory check (mandatory, no exceptions)

Before generating ANY code, run:
```bash
PYTHONPATH=. python3 -m scripts.research.paradigm_index list
```

Halt conditions:
- Hypothesis overlaps existing R-1+ paradigm (same data dimension AND same decision mode) → STOP, report duplication
- Partial overlap (e.g., new SL grid on existing source) → refer user to `strategy-evolver`

Then list active paper sessions:
```bash
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

### Other Tier 4 retired families (cross-reference)
- Funding single-signal sub-class (paradigm 73/79/96/97/98/99 — 6 graveyards) — see `lesson_prescreen_checklist.md` §Family retire Funding
- KR equity DART entry-side family (paradigm 92/93/100/101/102 — 5 graveyards 4 axes exhausted) — see same skill §Family retire DART
- Cross-asset volume share single-side simple-z 1d-hold (paradigm 94/95) — see same skill §Family retire Volume share
- Cross-exchange funding family (paradigm 103) — see [[project_paradigm_103_cross_exchange_funding_spread]]
- OHLCV magnitude-confluence × directional-follow family (paradigm 78/84/85 etc) — see `lesson_prescreen_checklist.md` Earlier lessons #25
- Geometric path metrics alone (paradigm 78) — see `lesson_prescreen_checklist.md`
- Taker-side aggressive volume family (paradigm 23/60/72) — see `lesson_prescreen_checklist.md`

## Reference
- `.claude/plans/research_track_master.md` §0 — 8-paradigm DNA matrix
- `.claude/plans/day30_decision_protocol.md` §2 트랙 L — lifecycle cohort methodology + variant baselines
- `backend/scripts/research/paradigm_index.py`
- Lesson #11 (Q3 sample-density prescreen)
- Lesson #41 DIFFUSE_POSITIVE_CONCENTRATION_FAIL verdict (2026-05-20 confirmed-with-amendment) — see `lesson_prescreen_checklist.md`
