# Graveyard: paradigm 151 `alt_token_unlock_cliff_entry_side_immediate_demand_directional_24h`

**Phase**: R-0 (pre-dispatch substrate + mechanism prescreen)
**Verdict**: `SUBSTRATE_INFEASIBLE_FREEMIUM_BLOCKED_AND_SAMPLE_INSUFFICIENT` + `LESSON_27_AMENDMENT_RECLASSIFY_NOT_FAMILY_DISTINCT`
**Dispatch ts (KST)**: 2026-05-21 14:35:54
**Counter**: 150 → 151 (counter-incrementing R-0, substantive prescreen + 3-lesson dogfood)

---

## 1. 가설 원문

- **Trigger**: 토큰 unlock cliff event (≥10% supply 일시 unlock) within Binance Futures USDS-M perp listed alts
- **Direction**: immediate demand mechanism (Lesson #27 amendment compliant 주장) — unlock_ts ±1h window forced sell pressure → SHORT
- **Forward hold**: 24h directional SHORT
- **Universe**: ~26 tokens with known unlock schedule (paradigm 88 cryptorank precedent universe 재활용)
- **Family-distinct claim**: paradigm 88 entry-side delayed/indirect (T-72h pre-positioning, FAIL_SCOPE) vs paradigm 151 immediate demand (unlock_ts ±1h)

---

## 2. R-0 3-layer halt 근거

### Layer 1: Lesson #28 substrate availability (column-axis FAIL)

**Freemium blacklist 5th cumulative confirmation**:

| Source | Access | Memory rule violation | Verdict |
|---|---|---|---|
| TokenUnlocks.app | commercial freemium (paid upgrade pressure) | `feedback_no_freemium_trial` | BLOCKED |
| CryptoRank.io public `/vesting` | partial scrape, isAuthProtected=True | 1 allocation cohort per coin only | PARTIAL_PASS (paradigm 88 precedent) |
| CoinMarketCap unlock | freemium | `feedback_no_freemium_trial` | BLOCKED |
| Tokenomist.ai | Next.js RSC + auth-gated API | — | BLOCKED for value comparison |
| Etherscan vesting trace | paid trace API | `feedback_no_freemium_trial` (paradigm 90 precedent) | BLOCKED |
| Solana / Tron trace | paid | `feedback_no_freemium_trial` (paradigm 90 precedent) | BLOCKED |
| DefiLlama unlocks ($300/mo) | paid | `feedback_no_freemium_trial` | BLOCKED |
| Binance announcements RSS/HTML | public | coverage <30% universe, irregular | AMBIGUOUS — low quality |
| Project whitepaper manual | person-day scale | out of scope | OUT_OF_SCOPE |

**유일한 viable substrate** = CryptoRank public partial. paradigm 88 precedent에서 이미 26 tokens × 206 events 추출 완료, 그 중 cliff_only ≥10% = **9 events / 2.4yr** (95% 분포 linear monthly emission).

### Layer 2: Lesson #11 + #26 sample density 자동 FAIL

```
expected_n_per_cell = 9 events / 7 quarters / 2 quadrants (focus + mirror) ≈ 0.64
Lesson #11 cutoff: per-cell ≥ 30 → FAIL (47x 미달)
Lesson #26 cutoff: n_measurable_quarters ≥ 4/7 → FAIL (0/7)
```

Mathematically unrecoverable under cliff-only ≥10% trigger semantics.

### Layer 3: Lesson #27 amendment first-principles reclassification

paradigm 151의 **"immediate demand" claim**을 first-principles로 평가:

| 차원 | 본 paradigm 151 (claim) | 실제 mechanism (first-principles) | Lesson #27 amendment 분류 |
|---|---|---|---|
| Cohort 신규성 | 신규 supply entry (claim) | **기존 vesting cohort liquidity status 전환** (lock → liquid) | EXIT-SIDE-like |
| 시장 anticipation | 즉시 forced sell | unlock schedule **공개됨** (CryptoRank/Tokenomist/project blog months ahead) | EXIT-SIDE-like |
| Recipient 행동 | 즉시 매도 강제 | recipient discretion (HODL 비율 / OTC / 분산 매도) | EXIT-SIDE-like |
| Smart money 사전 hedging | 부재 (immediate window) | unlock_ts 이전 days-weeks SHORT pre-hedging 활성 | EXIT-SIDE-like, alpha 사전 소진 |

⇒ **paradigm 151 = paradigm 88 retiming reframe**. Lesson #27 amendment 정확 적용 시 둘 다 delayed/indirect (exit-side fragility pattern) 동일 family. **NOT family-distinct**.

---

## 3. Family lineage 7-paradigm 누적

| Counter | Paradigm | Mechanism | R-0 verdict |
|---|---|---|---|
| 87 | binance_delisting_announce_short_alt | delisting forced-exit | R-1 PASS_R1_FULL → R-2 FRAGILE_TEMPORAL_WF_FAIL (lesson #26 origin) |
| 88 | token_unlock_cliff_short_alt (T-72h pre) | unlock entry delayed/indirect | FAIL_SCOPE (sample + Lesson #27 amendment) |
| 89 | listing_pre_announce_leak_long_alt | pre-listing leak | DISPATCH_IMPOSSIBLE (Lesson #28 substrate time-axis 부재) |
| 90 | stablecoin_mint_event_long_alt_24h | USDT/USDC mint | HALT (SAMPLE + freemium + Lesson #27 amendment 3 modes) |
| 100 | (entry-side family xref) | — | — |
| 103 | cross_exchange_funding_spread | cross-ex funding | BROAD_FALSIFIED_FEE_FLOOR |
| **151** | **alt_token_unlock_cliff_entry_side_immediate_demand_directional_24h** | **immediate demand reframe (=88 retiming)** | **SUBSTRATE_INFEASIBLE + LESSON_27_AMENDMENT_RECLASSIFY** |

**Entry-side external event paradigm family**: 7개 누적 모두 R-0/R-2 halt. lifecycle pump-decay만이 유일하게 4-dim (entry-side + immediate demand + substrate available + sample density) 모두 충족하는 R-5 seeded mechanism으로 입증됨.

---

## 4. Lesson dogfood 가치 (3건 + 1 family-distinct 패턴 강화)

### Lesson #27 amendment (6th dogfood)
- Claim "immediate demand"이 first-principles 평가에서 EXIT-SIDE-like로 reclassify된 첫 사례
- 향후 unlock/airdrop/staking-end/cliff-derivative 가설 발의 시 "immediate" claim은 4 차원 audit 의무 (cohort 신규성 + 시장 anticipation + recipient 행동 + sophisticated pre-hedging 가능성)

### Lesson #28 (13th dogfood)
- Column-axis sub-class: 동일 trigger semantics에 대해 free public source가 schema-mismatched (95% linear / 5% cliff) 일 때 substrate availability는 false-PASS (source 존재 ≠ trigger feasibility)
- 향후 prescreen은 substrate availability + trigger granularity intersection을 모두 verify 의무

### Lesson #44 amendment (35th xref dogfood)
- entry-side external event family 7-paradigm precedent chain 확립
- 향후 entry-side claim에는 7-paradigm precedent 명시 reference 의무

### Family-distinct 패턴 강화
- **"retiming reframe ≠ family-distinct"** 원칙 1차 dogfood
- 동일 trigger × 다른 entry timing은 mechanism이 first-principles로 동질이면 동일 family. Reframe만으로 family-distinct 주장 불가
- 향후 family-distinct claim은 4 차원 (trigger / entry-side class / mechanism / substrate) 중 ≥2 차원 변화 의무

---

## 5. Counter 결정 (150 → 151 increment)

[project_paradigm_97_funding_dispersion_inventory_halt] memory policy:
- **Inventory-halt (counter-static)**: DNA 5/6 overlap, novel 작업 0
- **Substantive R-0 (counter-increment)**: substrate verification 작업 수행 + novel lesson dogfood

paradigm 151은 후자 — 8 substrate source freemium evaluation + 3 Lesson dogfood + Layer 2 first-principles mechanism reclassification 모두 substantive work. **Counter 150 → 151 increment**.

---

## 6. 다음 candidate 권고

**21-streak non-PASS (129-151) 지속 중**. 메모리 [Persistence over efficiency] amendment 준수 지속 dispatch.

권장 axis (entry-side family 회피):

**Option α** — **post-event continuation paradigm family** (lifecycle pump-decay 유일 R-5 seed 동질 mechanism 확장):
- Candidate: `alt_post_listing_first_5min_directional_5m` (lifecycle pump-decay sub-spec 변형) — 단 lifecycle paradigm 22 직접 중복 위험, R-0 family-distinct 차원 ≥2 의무 통과 필요

**Option β** — **macro proxy paradigm family** (substrate항상 가용):
- Candidate: `btc_realized_vol_p90_alt_directional_4h_resume` — paradigm 69 mechanism 재활성화 (Mint 60d forward 데이터 누적 후 재검증)

**Option γ** — **NEW frontier paradigm family** (5-axis NOVEL prescreen):
- Candidate: `binance_perp_oi_velocity_per_sym_independent_4h_directional` — paradigm 71 mechanism × per-sym independence reframe (universe 정의 차원 변경)

**권장**: **Option β** (paradigm 69 macro proxy resume) — substrate 항상 가용 + paradigm 69 R-5 seed의 본질 mechanism (HIGH-vol p90 cascade) 시간 robust 검증 자체 가치. D-Day D-13까지 8-10 dispatches 가능 예산 내.

---

## 7. 산출물

- `backend/runs/research_track/alt_token_unlock_cliff_entry_side_immediate_demand_directional_24h/r0_prescreen.json`
- `backend/runs/research_track/graveyard__alt_token_unlock_cliff_entry_side_immediate_demand_directional_24h.md` (본 문서)
- INDEX.json paradigm 151 entry 등록 (다음 step)
- PARADIGM_QUEUE_2026Q3.md §6.48 entry (다음 step)

---

KST 2026-05-21 14:36
