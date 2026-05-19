# R-1 Summary — paradigm 95 `cross_asset_volume_share_high_alt_long_1d`

## Final Verdict
**`NARROW_SCOPE_LIFE_CHANGING_FAIL`** — 통계적으로 narrow-scope candidate 자격 (lesson #20 4-cond ALL PASS + mirror strict 3-gate FAIL via ci_lo<0 + direction isolated), BUT **life-changing 4-dim FAIL** (edge 0.47% << 2% AND capital util 6.39% << 30%) → sparse-trigger graveyard per `feedback_life_changing_strategy_criterion`.

R-2 미진행. paradigm 95 graveyard. ad-hoc R-1 종료.

## Dispatch
- 2026-05-19 KST Mint commit base fc61755f
- foreground synchronous, wall-clock 0.10 min (6초)
- Mint joblib OHLCV cache 14 syms × 845 common days × 2.4yr

## Data window
- common: 2024-01-19 ~ 2026-05-12 (845 days)
- share_z usable: 2024-02-17 ~ 2026-05-12 (816 rows)
- focus trigger (z>=+1.5): 54 trigger days × 13 alts = 702 trades
- mirror trigger (z<=-1.5): 65 trigger days × 13 alts = 845 trades (= paradigm 94 focus)

## Three-gate (focus z>=+1.5 LONG)
| Metric | Value | Gate | Pass |
|---|---|---|---|
| signal_t_excess | **+6.86** | >= 2.0 | ✓ |
| bootstrap_ci_lower_bp | **+59.77** | > 0 | ✓ |
| perm_p_one_sided_above | **0.000** | <= 0.10 | ✓ |
| gross_mean_bp | **+96.97** | >= 16 (fee floor) | ✓ |
| 50bp stress sigex | **+6.27** | >= 2.0 | ✓ |

**three_gate_pass: TRUE**

## Mirror (z<=-1.5 LONG, = paradigm 94 focus)
| Metric | Value | Strict 3-gate |
|---|---|---|
| signal_t_excess | +2.64 | >= 2.0 ✓ |
| bootstrap_ci_lower_bp | **−4.60** | > 0 ✗ |
| perm_p_one_sided_above | 0.003 | <= 0.10 ✓ |
| gross_mean_bp | +37.18 | — |

**mirror strict 3-gate: FALSE (ci_lo < 0)** — direction isolated. paradigm 94 R-1 conclusion (LOW-side BROAD_FALSIFIED) confirmed in this R-1 too (mirror ci_lo음수).

Note: script original criteria checked `mirror_fails_or_inverted = sigex<2.0` only (not ci_lo>0). This caused initial verdict `BROAD_FALSIFIED` which was over-pessimistic. Re-derived verdict accounts for strict 3-gate definition.

## Concentration Gate (focus)
| Metric | Value | Gate | Pass |
|---|---|---|---|
| q_pos_t_ratio | 0.700 (7/10) | >= 0.50 | ✓ |
| sym_ci_pos_ratio | **0.231 (3/13)** | >= 0.30 | ✗ |
| n_sym_ci_pos | 3 (AVAX/BCH/LTC) | >= 3 | ✓ |

**Concentration gate: FAIL marginal** (sym_ci_pos 3/13 — exact match to paradigm 94 R-1 mirror evidence)

## Per-quarter focus
- 7/10 quarters positive t (2024Q1/Q2/Q3 / 2025Q2/Q3/Q4 / 2026Q1)
- 3/10 negative (2024Q4 -112bp / 2025Q1 -52bp / 2026Q2 -21bp)
- **NOT quarter-concentrated** (well distributed across 2.4yr)

## Per-symbol (3/13 ci_pos)
- AVAX: mean +114.49bp t=+2.07 ci_lo +6.78 ci_pos ✓
- BCH: mean +164.74bp t=+2.88 ci_lo +62.26 ci_pos ✓
- LTC: mean +89.31bp t=+2.18 ci_lo +9.75 ci_pos ✓
- 10 others: positive mean but ci_lo<0 (insufficient per-sym power at n=54 each)

## Cross-proxy (Lesson #29)
| Proxy | sigex | ci_lo_bp | perm_p | strict 3-gate |
|---|---|---|---|---|
| obs (share_z) | +6.86 | +59.77 | 0.000 | ✓ |
| fund (btc_vol_z) | +3.86 | (not shown) | — | ✓ |
| jaccard overlap | 0.179 (54∩19, fund=71) | non-redundant | — | — |

**Both obs + fund 3-gate PASS + jaccard 0.179 << 0.7 → Lesson #29 PASS (non-redundant)**

## Lesson #20 narrow-scope 4-cond
| Cond | Detail | Pass |
|---|---|---|
| a. 4-gate | sigex+6.86 / ci+59.77 / p=0 / 50bp_sigex+6.27 | ✓ |
| b. held-out 50/50 | first 27 trig (sigex+6.25 ci+71.98 p=0) / last 27 trig (sigex+3.69 ci+22.97 p=0) — both 3-gate PASS | ✓ |
| c. Bonferroni | min_p=0 × n=13 → p_adj=0.0 | ✓ |
| d. hold sweep 1/2/3d | 3/3 positive, 2/3 three-gate PASS (1d/2d ✓ / 3d ci_lo<0) | ✓ |

**ALL 4-cond PASS** → narrow-scope candidate 자격 충족

## Life-changing 4-dim (memory `feedback_life_changing_strategy_criterion`)
| Metric | Value | Gate | Pass |
|---|---|---|---|
| trades_per_yr | **303.4** | >= 12 | ✓ |
| per_trade_edge_pct (50bp net) | **0.47%** | >= 2.0% | **✗** |
| capital_util_pct | **6.39%** | >= 30% | **✗** |
| annualized_sharpe | **3.54** | >= 1.5 | ✓ |

**life_changing_gate_pass: FALSE** — sparse-trigger paradigm 즉시 탈락 카테고리 외.

자세히 해부:
- trigger 54일 / 845일 = 6.4% trigger frequency
- 각 trigger 시 13/13 alts 동시 LONG → cells_per_day = 13 → sym_alloc_frac = 100%/13 = 7.69% per sym
- capital util = 6.4% × 100%/13 → 6.4% × 7.69% / 7.69% = 6.4% (전체 portfolio 6.4% only deployed)
- per-trade edge net of 50bp fee = 0.47% (gross 0.97% - 0.50% fee = 0.47%) — 인생 바꿀 결과 임계 2% 미달

## paradigm 94 mirror evidence consistency check
| Metric | paradigm 94 R-1 mirror | paradigm 95 R-1 focus | match |
|---|---|---|---|
| n_trades | 702 | 702 | ✓ |
| gross_mean_bp | +96.97 | +96.97 | ✓ |
| signal_t_excess | +6.86 | +6.86 | ✓ |
| ci_lower_bp | +59.77 | +59.77 | ✓ |
| sym_ci_pos | 3/13 (AVAX/BCH/LTC) | 3/13 (AVAX/BCH/LTC) | ✓ |

완벽히 일치. paradigm 94 mirror metric은 evidence-grade reliable. paradigm 95 independent re-test로 정식 검증 완료.

## Family-distinct verdict
- `family_distinct_inverted_direction_independent` — paradigm 94 (LOW share compression) 와 다른 direction class (HIGH share peak), 같은 statistic family but distinct mechanism

## Verdict 결정 트리
1. focus strict 3-gate PASS (✓)
2. mirror strict 3-gate FAIL (ci_lo음수) → direction isolated (✓)
3. Concentration gate FAIL (sym_ci_pos 3/13 marginal)
4. Lesson #20 4-cond ALL PASS → narrow-scope candidate
5. **life-changing 4-dim FAIL** (edge 0.47% + util 6.39%) → **sparse-trigger graveyard**

## Final verdict
**`NARROW_SCOPE_LIFE_CHANGING_FAIL`**

## R-2 미진행 사유
사용자 메모리 `feedback_life_changing_strategy_criterion`:
> 궁극 목표 = "인생 바꿀 결과". trades/yr<12 또는 capital util<30% 또는 edge<+2%/trade이면 통계적 유효성 무관 카테고리 외. sparse-trigger paradigm 즉시 탈락 판정.

paradigm 95는 edge 0.47% + util 6.39% 두 dimension 동시 미달. 통계적 evidence 강력 (sigex +6.86) 하지만 capital deployment 측면에서 인생 바꿀 결과 카테고리 외. R-2 walk-forward 진행해도 4-dim gate 회복 불가 (univ × hold × edge 본질적 cap).

graveyard report 별도 작성. paradigm 94 family (cross-asset volume share)는 LOW + HIGH 양 방향 측정 완료 — LOW broad-falsified + HIGH narrow-scope-life-changing-fail. 다른 transform (volume CONCENTRATION across non-BTC 13 alts? top-3 alt share?) 별도 paradigm으로 발의 가능.

## 산출물
- script: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_script.py`
- metrics: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_metrics.json`
- spec: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_spec.md`
- summary: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_summary.md` (this)
- graveyard: `backend/runs/research_track/graveyard__cross_asset_volume_share_high_alt_long_1d.md` (separate)
