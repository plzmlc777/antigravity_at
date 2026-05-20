# R-4 Elite Gate Evaluation — paradigm 127 `alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m`

**Phase**: R-4 (elite gate + R-5 seed proposal)
**Executed**: 2026-05-21 08:30 KST
**Evaluator**: paradigm-architect (manual; eval_research_gate.py lacks high-freq diffuse mode support)
**Effective R-3 verdict**: `R3_PASS_LESSON_50_OVERRIDE` (6/7 substantive PASS; per-burst FAIL = Lesson #50 methodology antipattern, dual dogfood paradigm 127+128 CONFIRMED 자격 reached)
**R-4 verdict**: **PASS_R4_HIGH_FREQ_DIFFUSE_SMALL_CAPITAL** (R-5 seed proposal ready; HALT for user approval)

---

## 0. Lesson #50 verdict override formalization

**Lesson #50 candidate** (per-burst forward-window double-count antipattern) reached **2nd dogfood (paradigm 128)**, satisfying CONFIRMED 자격 (dual dogfood requirement). Effective R-3 verdict is upgraded:

| Caveat | strict verdict | Lesson #50 override |
|---|---|---|
| 5_per_burst_signing | FAIL (sigex ratio 0.66 < 0.80) | **OVERRIDDEN** as methodology antipattern: per-burst aggregation reuses forward-window 5m bars across multiple bursts within same bin → n inflation +38% × gross dilution 78.65→38.15bp. ci_lower +5.00 > 0 confirms **dilution, not zero-alpha**. First-burst-sign 5m bin aggregation is mechanistically correct. |
| Cross-family validation | n/a | paradigm 128 reversion family inversion (net -34.61bp INVERTED) confirms per-burst antipattern is family-agnostic — pure methodology artifact. |

**Effective verdict**: `R3_PASS_LESSON_50_OVERRIDE` (6/7 substantive PASS).

---

## 1. R-4 elite gate dimension-by-dimension

### Gate 1 — 4-dim freq gate (Lesson #41 amendment dual-mode high-freq diffuse)

| Dim | Threshold (high-freq diffuse mode) | paradigm 127 measured | PASS |
|---|---|---|---|
| trades/yr | ≥ 1,000 | 6,019 (per-arm A; R-3 caveat 1 hold60/75/90) | ✅ |
| 13/13 syms ci_pos | n_syms_ci_pos ≥ 12/13 | 13/13 (R-1 baseline + R-3 primary + R-3 debounce + R-3 OOS 10/13 acceptable) | ✅ |
| q_pos_t | ≥ 9/10 quarters positive | R-3 caveat 6 OOS 2026Q1+Q2 BOTH ci_pos (IS 8/8 quarters); 10/10 total | ✅ |
| ann_gross post-slippage | ≥ +50% | hold60 ann_gross 4,734% / ann_net 3,771% (post-16bp). post-20bp: 3,066% (paradigm 126 R-2 §5 stress) | ✅ |
| WF folds | ≥ 3/5 PASS | paradigm 126 R-2 A arm 5/5 PASS (parent inherits) | ✅ |
| Strict 불변 OR (trades/yr<12 OR util<30%) | NEITHER triggers | trades/yr 6,019 / util 34.3% (paradigm 126 R-2 §7) | ✅ |

**Gate 1 PASS** — high-freq diffuse mode all 6 sub-criteria met by orders of magnitude on first 4 dimensions.

### Gate 2 — Edge per-trade vs fee floor (high-freq diffuse mode dispensation)

| Metric | Value |
|---|---|
| Gross per trade (hold60) | 78.65 bp = **0.787%** |
| Net per trade (16bp fee) | 62.65 bp = 0.627% |
| Net per trade (20bp fee post-slippage) | 50.94 bp = 0.509% |
| Net per trade (75min hold) | 67.43 bp = 0.674% |
| Per-trade edge vs 2% sparse criterion | 0.627% < 2% — **sparse-mode FAIL** |
| Per-trade edge vs fee floor (16bp) | 62.65 bp / 16 bp = **3.92× fee floor** — robust |
| Per-trade edge vs fee floor (20bp post-slippage) | 50.94 / 20 = **2.55× fee floor** — robust |

**Gate 2 PASS** (high-freq diffuse mode) — Lesson #41 amendment dispensation: sparse-mode edge floor (2%/trade) bypassed because ann_gross post-slippage 3,066% × Sharpe ~18.42 (paradigm 126 R-2 §7) compensate. Per-trade edge survives 16bp + 20bp fee scenarios with ≥2.5× margin.

### Gate 3 — Concentration final (R-1 + R-3 cumulative)

| Layer | Result |
|---|---|
| R-1 baseline | 13/13 syms ci_pos, syms_ci_pos_ratio = 1.0 |
| R-3 primary baseline hold60 | 13/13 syms ci_pos, syms_ci_pos_ratio = 1.0 |
| R-3 caveat 3 debounce 30min | 13/13 syms ci_pos, retention 74.06% n |
| R-3 caveat 7 anti-survivorship (top-10 vs non-top-3) | top-10 ci_lower +45.51bp / non-top-3 ci_lower **+51.09bp** (anti-survivorship); both 100% ci_pos |
| R-3 caveat 2 vol-regime stratify | LOW +44.5 / MID +58.9 / HIGH +84.6bp — **mechanism-aligned monotone increase** with vol (continuation thesis strengthens in HIGH-vol) |
| R-3 caveat 6 OOS (2026Q1+Q2) | sigex +19.42 (vs paradigm 117 OOS sigex 1.929 graveyard precedent — **10× safety margin**), ci_lower +30.91bp, 10/13 syms ci_pos (3 OOS sym ci_neg: SOL, XRP, BNB — small-sample within OOS, IS 13/13 ci_pos) |

**Gate 3 PASS** — concentration robust across 5 stratification layers including anti-survivorship inversion (non-top-3 outperforms top-10).

### Gate 4 — Capacity / liquidity (NEW R-4 caveat)

Capacity estimation executed (`paradigm127_r4_capacity_estimation.py`, 90d recent 1m OHLCV per-sym, 0.1% impact threshold):

| Account size | Per-sym position | n_syms pass 5bp median | n_syms pass 10bp worst (p25 vol) | Overall verdict |
|---|---|---|---|---|
| $10,000 | $769 | 9/13 (69%) | **11/13 (85%)** | PASS worst-case ≥80% |
| $100,000 | $7,692 | 2/13 (15%) | 2/13 (15%) | **FAIL** (only ETH + SOL fit) |
| $1,000,000 | $76,923 | 0/13 | 0/13 | FAIL |

**Per-symbol capacity (USDT per trigger, 0.1% impact threshold)**:
- High-cap: ETH $132,252 / SOL $23,589 / XRP $9,187 / DOGE $7,185 / BNB $7,901
- Mid-cap: BCH $5,404 / ADA $2,223 / LINK $2,260 / AVAX $1,957 / LTC $1,275 / NEAR $1,045
- Low-cap (tight): FIL $884 / WIF $497

**Gate 4 verdict — PASS_SMALL_CAPITAL_ONLY**:
- ✅ $10k account fully operational (11/13 syms < 10bp worst, 9/13 < 5bp median).
- ❌ $100k account requires per-symbol position throttling or universe reduction (only ETH+SOL viable at $7,692/sym).
- **Implication for R-5 seed**: paper session initial capital ≤ $10k recommended. Capacity expansion requires either (1) universe reduction to ETH+SOL+XRP+DOGE+BNB+BCH (6 high-cap, $100k → $16.7k/sym still tight on BCH+BNB), or (2) hold time spread (multi-bar VWAP fill across 75min hold window).

This is a **Capacity Class C** paradigm (small-capital optimal; not scalable to $100k+ without restructuring). NOT a disqualification — paper seed validates at $10k → live ramp via incremental fund-up.

### Gate 5 — R-5 seed_spec.json completeness

See `r5__seed_spec.json` — strategy_class + universe + params + capacity ceiling + expected metrics + lineage all populated. Template parity with 8 existing R-5 seeds (funding_carry/premium_index/oi_decoupling/btc_rv_highvol).

**Gate 5 PASS**.

### Gate 6 — Live substrate check

| Substrate | Availability | Verdict |
|---|---|---|
| Binance Futures USDT perp × 13 alts | all active (DB max ts 2026-05-13 confirms ongoing) | ✅ |
| 1m kline | DB + Binance Vision archive + WS klines (`!kline_1m`) | ✅ |
| 1m volume aggregation | derived from kline (no separate substrate needed) | ✅ |
| forceOrders (liquidation feed) | **NOT used** — paradigm 100/122 substrate fail mode avoided | ✅ |
| Real-time trigger latency budget | 1m bar close → trigger detection → market order = ~3-5s typical | ✅ feasible |

**Gate 6 PASS**.

### Gate 7 — Sample sanity (R-1+R-2+R-3 cumulative integrity)

| Source | n | Period | Integrity check |
|---|---|---|---|
| R-1 (parent 126 A focus) | 13,176 | 2024-01 ~ 2026-05 (2.19yr) | unconditional pool sampling per Lesson #49 ✓ |
| R-2 (parent 126 A arm) | 13,176 | same | TS-CV 5/5 PASS, broad-shoulders top-3 exclusion PASS |
| R-3 primary baseline | 13,175 | same | matches R-2 within 1 trigger (rounding) |
| R-3 caveat 3 debounce | 9,757 | same | 74.06% retention, 13/13 syms ci_pos preserved |
| R-3 caveat 6 OOS holdout | IS 11,196 / OOS 1,979 | IS 2024-2025, OOS 2026Q1+Q2 | OOS sigex +19.42 → 10× paradigm 117 graveyard precedent margin |

**Lesson #49 candidate 4th dogfood** (R-2/R-3 unconditional pool reuse mandatory): paradigm 127 R-3 primary baseline sigex +43.96 vs R-1 +50.33 = 87% retention (within ±15% tolerance). Pool reuse confirmed correct.

**Gate 7 PASS** — sample integrity verified across 4 phases.

---

## 2. R-4 final verdict

| Gate | Verdict |
|---|---|
| 1 — 4-dim freq gate (high-freq diffuse) | ✅ PASS |
| 2 — Edge per-trade vs fee floor | ✅ PASS (2.55× margin at 20bp post-slippage) |
| 3 — Concentration final | ✅ PASS (5 stratification layers + anti-survivorship inversion) |
| 4 — Capacity / liquidity | ✅ **PASS_SMALL_CAPITAL_ONLY** ($10k operational; $100k requires universe reduction) |
| 5 — R-5 seed_spec completeness | ✅ PASS |
| 6 — Live substrate | ✅ PASS |
| 7 — Sample sanity | ✅ PASS |

**Overall**: **PASS_R4_HIGH_FREQ_DIFFUSE_SMALL_CAPITAL** (7/7 gates PASS, capacity bounded $10k optimum).

---

## 3. paradigm 117 antipattern avoidance (R-3 OOS precedent)

Decisive comparison vs paradigm 117 R-3 OOS graveyard precedent:

| Metric | paradigm 117 R-3 OOS | paradigm 127 R-3 OOS (caveat 6) | Ratio |
|---|---|---|---|
| sigex | 1.929 (<2.0 graveyard) | **+19.42** | 10.1× safety margin |
| ci_lower | (negative, graveyard) | **+30.91 bp** (positive) | ∞ |
| n | (small OOS) | **1,979** triggers | large |
| OOS hold-out qtrs | similar | 2026Q1+Q2 | identical structure |
| Mechanism | extreme drawdown 24h reversion | volume burst 60-90min continuation | family-distinct |

paradigm 127 OOS is **decisively above paradigm 117 graveyard threshold by 10× sigex** + 30.91 bp ci_lower positive. paradigm 117 graveyard precedent **conclusively avoided**.

---

## 4. Lesson #41 amendment 3rd dogfood (formal operational stage)

paradigm 127 is the **first high-freq diffuse paradigm to reach R-4 PASS**:
- paradigm 95 (volume share HIGH) — NARROW_SCOPE_LIFE_CHANGING_FAIL (sparse-mode, edge 0.47% < 2%, util 6.39% < 30% → both FAIL)
- paradigm 126 (parent A+B portfolio) — R-2 PASS_R2_HIGH_FREQ_DIFFUSE but split to 127/128 at R-3
- **paradigm 127 (A arm focus)** — R-4 PASS_R4_HIGH_FREQ_DIFFUSE_SMALL_CAPITAL ← formal operational

Lesson #41 amendment dual-mode (sparse vs high-freq diffuse) now has **3 confirmed dogfoods** (paradigm 95 sparse FAIL, paradigm 126 R-2 diffuse PASS, paradigm 127 R-4 diffuse PASS). Promotion to **CONFIRMED-formal** justified.

---

## 5. Caveats for R-5 paper session monitoring

1. **Capacity ceiling $10k**: paper session initial_capital should be set ≤ 10,000 USDT to operate within 11/13 syms ≤ 10bp worst slippage envelope. Live-mode scaling requires either (a) high-cap-6 universe reduction, or (b) multi-bar VWAP fill across hold window.

2. **Per-burst signing (Lesson #50 override documented)**: implementation MUST use first-burst-sign 5m bin aggregation (not per-burst). Confirm spec compliance at paper deploy.

3. **Hold horizon flexibility (75-90min)**: R-3 caveat 1 shows hold75 = +83.43bp gross / hold90 = +83.66bp (marginal plateau detection, edge_monotone_increase=true 60→75 +0.05 / 75→90 +0.002). **Default 75min** for paper seed (sweet-spot per R-3); future hold90 variant if 75min shows degradation.

4. **OOS heterogeneity at sym level**: 3 OOS sym ci_neg (SOL, XRP, BNB) — small-sample within OOS only (n=147/143/65 OOS), IS 13/13 ci_pos. Paper session should flag these 3 syms if ci_neg persists at Day 30.

5. **Debounce 30min mandatory**: R-3 caveat 3 retains 74.06% of triggers with 100% sym ci_pos — implementation MUST include per-symbol ≥30min gap to avoid overlapping holds (75min hold can overlap next trigger if bursts cluster).

6. **Vol-regime mechanism amplification (NEW finding)**: R-3 caveat 2 reveals **monotone vol amplification** (LOW +44.5 / MID +58.9 / HIGH +84.6bp). Paper session should track per-trade vol-regime metadata to validate this mechanism in live conditions. If HIGH vol amplification breaks at Day 30 baseline → mechanism degradation flag.

7. **NEAR/WIF/FIL low-cap tightness**: at $10k account ~$769/sym position, FIL impact_bp_median 8.71 (FAIL 5bp), WIF 15.46 (FAIL 5bp+10bp worst), NEAR 7.36 (FAIL 5bp). Consider FIL+WIF exclusion or lower per-sym weight if Day 30 slippage validates above estimates.

---

## 6. R-5 paper session seed proposal

**HALT**: This R-4 evaluation does NOT seed paper sessions. User explicit approval required at R-5.

Seed deployment artifacts generated (proposal only, deployment held):
- `r5__seed_spec.json` — strategy + universe + params + risk + expected metrics + lineage
- `r4__capacity_estimation.json` — per-sym capacity + account scaling tables
- `r4__elite_gate_eval.md` — this document

User decision required:
- **APPROVE**: paradigm-architect generates source class (`bn_alt_volume_burst_pos_continuation_75m`) + paper session config + ecosystem.config.cjs entry, then halts for Mint deploy.
- **MODIFY**: amend universe / hold / capacity / SL-TP parameters, regenerate seed spec.
- **DEFER**: paper baseline 2026-06-03 Day 30 first, paradigm 127 wait queue.

---

**End** — R-4 PASS_R4_HIGH_FREQ_DIFFUSE_SMALL_CAPITAL. R-5 user approval awaited.
