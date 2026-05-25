# R-1 Gate Evaluation — paradigm 143

**paradigm_name**: `alt_taker_buy_quote_vol_percentile_rank_directional_8h`
**paradigm_id**: 143
**phase**: R-1
**run_ts**: 2026-05-21 04:15:31 UTC (13:15:31 KST)
**wall_clock**: 3.0s
**dispatch_mode**: continuous_parallel

## Verdict

**`BROAD_FALSIFIED`** (143번째 graveyard)

## Trigger Counts (Lesson #11 PASS)

- pos (rank > 0.95) n = **3577** — per-cell q10 ≈ 358 (≫30)
- neg (rank < 0.05) n = **3516** — per-cell q10 ≈ 352 (≫30)
- expected_n_per_cell prescreen PASS

## 4-quadrant SNT (primary hold 8h)

| Quadrant | n | mean_bp | sigex | perm_p | ci_lo_bp | 3gate | conc |
|---|---|---|---|---|---|---|---|
| A focus pos LONG | 3577 | -3.88 | +0.327 | 0.638 | -11.91 | FAIL | FAIL |
| A mirror pos SHORT | 3577 | -12.12 | -0.792 | 0.185 | -19.56 | FAIL | FAIL |
| B focus neg SHORT | 3516 | -8.39 | +0.264 | 0.617 | -16.99 | FAIL | FAIL |
| B mirror neg LONG | 3516 | -7.61 | -0.515 | 0.300 | -15.60 | FAIL | FAIL |

**All 4 quadrants broadly negative drift, no axis synthesis.**

## Hold sweep (Lesson #37 full scan)

| Hold | A_focus_LONG mean_bp / sigex / 3gate | B_focus_SHORT mean_bp / sigex / 3gate |
|---|---|---|
| 4h | -10.08 / -1.78 / FAIL | -10.39 / -0.55 / FAIL |
| **8h (primary)** | -3.88 / +0.33 / FAIL | -8.39 / +0.26 / FAIL |
| 12h | -7.05 / -0.66 / FAIL | -5.73 / **+1.01** / FAIL |

- B_focus 12h sigex +1.01 only marginally positive but still gate-fail
- **off-primary scan**: any_off_primary_3gate_pass_A=False, any_off_primary_3gate_pass_B=False

## Lesson #39 sub-class detection

- sub_class_A_broad_uniform_negative: **False** (no quadrant sigex < -2)
- sub_class_B_mechanism_inverted: **False** (no mirror dominance ≥1.5 over focus)
  - A focus +0.33 vs A mirror -0.79 (gap -1.12, focus wins marginally)
  - B focus +0.26 vs B mirror -0.52 (gap -0.78, focus wins marginally)
- General `BROAD_FALSIFIED` category (no sub-class signature)

## Life-changing 4-dim

| Side | trades/yr | edge_net_% | util_% | sharpe | all_pass |
|---|---|---|---|---|---|
| A focus LONG 8h | 1593.6 | -0.039 | 100.0 | -0.64 | False |
| B focus SHORT 8h | 1566.4 | -0.084 | 100.0 | -1.31 | False |

- trades/yr + util saturate PASS (high frequency, long hold = capacity-bound)
- edge + sharpe FAIL (negative drift × negative sharpe)

## Lesson #46 sign-flip diagnostic

- A focus: 10 quarters / pos:neg = 2:8 / flips 3/9 / strong_alt False
- B focus: 10 quarters / pos:neg = 6:4 / flips 4/9 / strong_alt False
- No strong-alternating WARNING

## Lesson #57 dogfood result — **2nd POSITIVE dogfood**

**Family**: quote_vol axis directional continuation 4h+ hold

| sub-class | paradigm | verdict |
|---|---|---|
| z-score 4h primary | 142-v2 | `BROAD_FALSIFIED` (2026-05-21 13:09 KST) |
| **percentile rank 8h primary** | **143** | **`BROAD_FALSIFIED` (2026-05-21 13:15 KST)** |

**2 consecutive BROAD_FALSIFIED with completely different normalization schemes (z-score parametric vs percentile rank non-parametric) + different primary holds (4h vs 8h) + full hold sweep (4h/8h/12h) all FAIL** → quote_vol imbalance axis 4h+ directional continuation **family Tier 4 retire eligible**.

## Lesson #55 candidate dogfood result — **3rd dogfood, prescription FAIL**

percentile rank distribution-agnostic prescription tested as alternative to z-score asymmetry trap:
- z-score 142-v2 B_focus 4h sigex +1.82 → percentile rank 143 B_focus 8h sigex +0.26 (worse, not better)
- z-score 142-v2 B_focus 12h hint sigex +3.43 → percentile rank 143 B_focus 12h sigex +1.01 (regression -2.4σ)
- **Distribution normalization scheme not the root cause** — underlying signal is genuinely absent (or fee-saturated)

Lesson #55 candidate **CONFIRMED-elevation impeded** (3rd dogfood is FAIL, not TRUE POSITIVE).

## Lesson #44 amendment 26th xref

All 6 prior family members ratified distinct:
- paradigm 72 (5m raw): distinct via 4h frame + percentile rank
- paradigm 127/128 (volume burst 30m): distinct via continuous percentile + 4h/8h hold
- paradigm 140 (CVD ratio cumulative): distinct via percentile rank + per-bar imbalance (not cumulative)
- paradigm 142-v2 (z-score 4h): distinct via percentile rank (non-parametric) + 8h primary
- funding family: distinct axis entirely

## R-0 prescreen retrospective verification

| Lesson | check | result |
|---|---|---|
| #11 sample density | expected per-cell ≥30 | **PASS** (actual ~350/q) |
| #19 4-quadrant SNT | applied | PASS |
| #30 data_window_ratio | 1.00 | PASS |
| #40 structural threshold | N/A (percentile [0,1] bounded) | N/A |
| #44 amendment 26th xref | 6 family members ratified | PASS |
| #45 no HMM | deterministic percentile | PASS |
| #46 stratified + sign flip | strong_alt False both sides | PASS |
| #16 concentration strict | tested both focus | gate FAIL (downstream) |

## Decision

- **Verdict**: `BROAD_FALSIFIED`
- **Halt**: R-1 only (per user directive)
- **Family retire candidate**: quote_vol axis 4h+ directional continuation — Lesson #57 2nd dogfood passed, formal elevation to family Tier 4 retire eligible upon next paradigm campaign review
- **No R-2 promotion**
