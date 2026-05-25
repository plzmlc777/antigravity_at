# paradigm 157 — `alt_session_boundary_NY_close_21UTC_anchored_directional_4h`

**Dispatch ts**: 2026-05-21 KST
**Phase**: R-1 only (R-2 자동 진행 STRICT 금지)
**Substrate**: 14 syms (BTC + 13 alts) × 4h klines 12-col joblib cache (영구 자산)

---

## Hypothesis

**Mechanism**: 시간대 session boundary anchor (archetype C) — NY close (≈21 UTC) 시점 4h bar (16-20 UTC) close-to-close 부호 + magnitude → 직후 4h window (20-24 UTC, Asia open transition) directional momentum/reversal alpha.

- **Trigger statistic**: 20:00 UTC closing bar (16-20 UTC bar)의 close-to-close return sign (BTC + 13 alts 모두 동일 anchor 공유).
- **Direction story**:
  - **A focus (Continuation)**: NY close UP × alt LONG / NY close DOWN × alt SHORT
  - **A mirror (Reversal)**: NY close UP × alt SHORT
  - **B focus same-sign**: NY close DOWN × alt SHORT
  - **B mirror**: NY close DOWN × alt LONG
- **Forward window**: +4h (20:00 UTC → 00:00 UTC next day close).

---

## 4h cache anchor reality check (CRITICAL)

Binance Futures 4h klines align to UTC 0/4/8/12/16/**20** (verified via cache inspection).

User hypothesis specifies **21:00 UTC** but the 4h cache bars close at 20:00 UTC. The closest principled anchor:

| Option | Anchor | Rationale | Substrate |
|---|---|---|---|
| **Adopted** | **20:00 UTC bar close** | NY equities close = 20:00 UTC EDT (~7 months/yr, dominant period). Maps to actual market-microstructure boundary directly. | 4h cache (영구 자산, zero infra cost) |
| Rejected | 21:00 UTC exact | 1m cache load required for non-bar-aligned anchor, adds infra cost + Lesson #28 substrate friction without mechanism gain | 1m cache |

**Decision**: 20:00 UTC bar close (16-20 UTC bar) as "NY close session boundary anchor". This is the **structural temporal anchor** — the hypothesis is about session-boundary macro flow rebalancing, which is microstructurally located at NY equities close (20 UTC EDT ≈ 21 UTC EST). The 20 UTC bar boundary is the closest 4h-aligned anchor to the actual structural event.

---

## R-0 10-axis prescreen verdict (all PASS, dispatch authorized)

| # | Axis | Verdict | Notes |
|---|---|---|---|
| 1 | Family-distinct strict 4-dim (Lesson #62 CONFIRMED) | ✅ 4/4 STRICT | statistic = bar-sign on session-anchor bar (NEW class); universe = 14 syms (BTC+alts, structural anchor shared); entry-side = time-of-day cycle anchor (NEW class); mechanism = session boundary macro flow rebalancing (NEW class) |
| 2 | Substrate availability (Lesson #28) | ✅ 4h klines 12-col cache | 14 syms × 4920 bars × 2.25yr 영구 자산 verified |
| 3 | Sample density (Lesson #11) | ✅ ~820 NY anchors × 14 syms = ~11,480 events; per-cell at 4q × ~9 quarters = ~318 | far above 30 cutoff |
| 4 | SNT 4-quadrant (Lesson #19) | ✅ A_LONG/A_SHORT/B_LONG/B_SHORT 의무 implemented | 모든 quadrant 동일 anchor, sign-cond bilateral |
| 5 | Data window ratio (Lesson #30) | ✅ 1.00 full uniform | 4h cache 2024-02-01 → 2026-04-30 uniform |
| 6 | Retiming reframe (Lesson #62 CONFIRMED) | ✅ NOT retiming | NEW anchor class (time-of-day vs funding 8h cycle or volatility regime) |
| 7 | OUTCOME-LEVEL family proxy (Lesson #56) | ✅ ESCAPE | session boundary anchor 전무 (paradigm 85 pre_session_open_oi 부분 reference but 다른 anchor time + sample-insufficient halt only, R-1 outcome 없음) |
| 8 | Axis stacking (Lesson #21) | ✅ single axis × single mechanism | session anchor bar-sign single trigger |
| 9 | Same-bar same-substrate (Lesson #58) | ✅ EXEMPT | single bar-sign single substrate base case (paradigm 152 exemption) |
| 10 | Mirror antipattern | ✅ N/A | sign-cond bilateral = core hypothesis structure |
| 11 | Lesson #67 candidate avoidance | ✅ ESCAPE | structural temporal anchor (모든 sym 동일 boundary 공유), NOT macro single-asset signal broadcast |
| 12 | Intraday incompatibility (memory) | ✅ EXEMPT | 4h hold (NOT sub-5min), fee floor 충족 가능 영역 |

**Verdict**: R-0 PASS, R-1 dispatch authorized.

---

## R-1 protocol

1. **Universe**: 14 syms (BTC + 13 alts). Per Lesson #62 strict family-distinct dim "universe scope", BTC is INCLUDED in this paradigm because the NY close anchor is a structural global event affecting BTC equally (NOT a BTC-only trigger broadcast to alts).
2. **Anchor selection**: For each calendar day, identify the 20:00 UTC bar (close_time 20:00 UTC). The bar's sign = sign(close_20UTC / close_16UTC - 1).
3. **Forward hold**: 4h (primary) — exit at 00:00 UTC next-day close.
4. **Hold sweep**: 4h (primary) / 8h (1 bar = 00 UTC) / 12h (04 UTC) for Lesson #37 full sweep scan.
5. **3-gate evaluation per quadrant** (Lesson #19 mandatory):
   - signal_t_excess ≥ 2.0 AND ci_lower_bp > 0 AND perm_p ≤ 0.10
6. **Concentration Gate** (Lesson #16): per-quarter t-ratio ≥ 0.5 AND per-symbol ci_pos ratio ≥ 0.30 AND n_syms_ci_pos ≥ 3.
7. **Life-changing 4-dim** (per [[feedback-life-changing-strategy-criterion]]): trades/yr ≥ 12 + edge ≥ +2%/trade + capital_util ≥ 30% + sharpe ≥ 1.5.
8. **Lesson #39 sub-class detection**: A_mirror dominates A_focus by ≥1.5σ → sub-class B (mechanism inverted); all 4 sigex < -2 → sub-class A (broad-uniform-negative).
9. **Lesson #46 stratified sign-flip warning** per focus side.
10. **Verdict tree**: BROAD_FALSIFIED / PASS_R1_FULL / NARROW_SCOPE_LIFE_CHANGING_FAIL / CONCENTRATED_R1_PASS / sub-class A or B variants.

---

## R-1 only constraint (STRICT)

- **R-2 자동 진행 절대 금지**. R-1 verdict 보고 후 사용자 명시적 승인 대기.
- Per [[feedback-agent-long-background-polling]] R-1만 먼저.

---

## Memory policy strict compliance

- [[feedback-no-freemium-trial]] — 4h cache 내부 substrate only, 외부 API 호출 없음
- [[feedback-life-changing-strategy-criterion]] — 4-dim gate 통합
- [[feedback-direct-recommendation]] — R-1까지 자율 진행 + 분기점 직접 선택
- [[feedback-paradigm-campaign-continuous-parallel]] — 일시정지 권고 금지
- [[project-life-changing-campaign-session1-halt]] — sub-5min intraday signal incompatibility 회피 (4h hold)
- [[project-paradigm-btc-rv-highvol-short]] — mirror antipattern 인지 (paradigm 157은 sign-cond bilateral core 구조이지 단방향 mirror 시도가 아님, exemption)
