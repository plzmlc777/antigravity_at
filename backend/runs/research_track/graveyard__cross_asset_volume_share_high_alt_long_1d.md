# Graveyard — paradigm 95 `cross_asset_volume_share_high_alt_long_1d`

- **Paradigm #**: 95
- **Date**: 2026-05-19 KST
- **Phase**: R-1 (R-2 미진행)
- **Verdict**: `NARROW_SCOPE_LIFE_CHANGING_FAIL`
- **Mint commit**: see paradigm-architect bundle commit

## Hypothesis
BTC daily USD-volume share z(30d) >= +1.5 → LONG 13 alts entry next-day open, hold 1d, exit close. Mechanism: BTC dominance peak / bull regime confirmation → alt catch-up rotation cascade.

## Dispatch context
- paradigm 94 R-1 Mint full-data rerun (commit fc61755f, 2026-05-19) produced strong mirror evidence (sigex +6.86, gross +96.97bp, ci_lo +59.77bp on n=702 trades).
- Lesson #8 + paradigm 70 mirror antipattern catalog 적용 → mirror metrics auto-promote 금지, 별도 independent R-1 의무
- 본 paradigm 95 R-1은 paradigm 94의 mirror evidence를 독립 paradigm으로 정식 검증

## Result summary
| Layer | Result | Pass |
|---|---|---|
| focus strict 3-gate | sigex +6.86 / ci +59.77 / perm_p 0.0 | ✓ |
| mirror strict 3-gate | sigex +2.64 / ci **−4.60** (음수) / perm_p 0.003 | ✗ → direction isolated |
| 50bp stress 4-gate | sigex +6.27 | ✓ |
| Concentration Gate | sym_ci_pos 3/13 (0.231 < 0.30) AVAX/BCH/LTC | ✗ marginal |
| q_pos_t_ratio | 7/10 (0.70 well-distributed) | ✓ |
| Cross-proxy (Lesson #29) | obs+fund both 3-gate PASS, jaccard 0.179 | ✓ |
| Lesson #20 a (4-gate) | sigex+6.86 / ci+59.77 / p=0 / 50bp+6.27 | ✓ |
| Lesson #20 b (held-out 50/50) | first 3-gate / last 3-gate | ✓ |
| Lesson #20 c (Bonferroni) | p_adj 0.0 | ✓ |
| Lesson #20 d (hold 1d/2d/3d) | 3/3 pos, 2/3 three-gate | ✓ |
| **Lesson #20 ALL 4-cond** | **PASS** | ✓ |
| **Life-changing 4-dim** | edge 0.47% + util 6.39% | **✗** |

## Why graveyard
사용자 메모리 `feedback_life_changing_strategy_criterion` 기준:
- per-trade edge (50bp net) = **0.47%** << 2% (4.3x 미달)
- capital utilization = **6.39%** << 30% (4.7x 미달)
- → sparse-trigger paradigm "통계적 유효성 무관 카테고리 외"

paradigm 95는 통계적으로는 narrow-scope candidate 자격 (Lesson #20 a/b/c/d ALL PASS + mirror strict FAIL + cross-proxy non-redundant), 그러나 인생 바꿀 결과 4-dim gate 동시 두 dimension 미달 → R-2 walk-forward 진행해도 fundamental cap (cells_per_day × trigger_frequency × hold_days = 13 × 6.4% × 1d / 14 universe = 6.4% util) 회복 불가.

## Lessons applied + new evidence
- **Lesson #8 dogfood**: paradigm 94 mirror auto-promote 차단 + independent R-1 의무 → 정상 작동
- **Lesson #16 Concentration Gate**: marginal sym_ci_pos 3/13 정확 검출 → narrow-scope branch 정상 작동
- **Lesson #19 Symmetric Negative**: 2-quadrant 단일 batch, mirror direction isolation 정확 검출
- **Lesson #20 narrow-scope 4-cond**: a/b/c/d ALL PASS 검출 → 신규 verdict `NARROW_SCOPE_CANDIDATE` 자격 부여 (그러나 life-changing 4-dim layer로 graveyard)
- **Lesson #29 cross-proxy**: obs + fund both 3-gate + jaccard 0.179 non-redundant → 정상 작동
- **NEW lesson candidate**: Lesson #20 narrow-scope candidate 자격 + life-changing 4-dim FAIL 동시 발생 패턴 → `NARROW_SCOPE_LIFE_CHANGING_FAIL` 별도 graveyard 카테고리 도입 의무. paradigm-architect verdict tree에 life-changing 4-dim layer 정식 통합 권고

## paradigm 94 family verdict (LOW + HIGH 통합)
- paradigm 94 (LOW share z<=-1.5 → alt LONG): `BROAD_FALSIFIED_DIRECTION_INVERTED` — focus 3-gate fail, fee floor 미달
- paradigm 95 (HIGH share z>=+1.5 → alt LONG): `NARROW_SCOPE_LIFE_CHANGING_FAIL` — focus 3-gate PASS but capital deployment cap

→ **cross-asset volume share family**: LOW direction broad-falsified + HIGH direction narrow-scope-life-changing-fail. **single-side simple z trigger family Tier 4 retire 권고 보류** — narrow-scope (3 alt subset AVAX/BCH/LTC) sub-mechanism은 미해명 (paradigm 94 같이 broad-fail 아닌 narrow signal). 그러나 1d hold + 14-sym universe capital cap 본질적이므로 같은 backbone 변형 (hold 변경, universe 확장, sym 선별 subset)으로 life-changing 4-dim 회복 어려움.

가능한 후속 hypothesis (추후 재발의):
1. AVAX+BCH+LTC subset only — 3-sym narrow paradigm, sym_alloc_frac × trigger_frac × edge 재계산 필요
2. Volume share momentum (z 변화 속도) — 다른 transform class
3. Top-3 alt cohort vol_share concentration (BTC 제외) — different mechanism

## Family-distinct
- paradigm 94 LOW: 다른 direction class
- 5m microstructure single-domain: different
- KR equity post-earnings: different
- geometric path metrics: different
- funding/OI joint squeeze: different
- BTC/ETH 5m corr breakdown: different
- Verdict: family_distinct_inverted_direction_independent

## Verdict 권고
**graveyard. R-2 미진행.** ad-hoc R-1 종료. paradigm 94 mirror evidence reliable but 그 자체로 life-changing strategy 부적합. 새 sub-paradigm 발의 시 universe + hold dimension fundamental redesign 필요.

## Output
- code: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_script.py`
- metrics: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_metrics.json`
- summary: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_summary.md`
- spec: `backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/r1_spec.md`
- this graveyard: `backend/runs/research_track/graveyard__cross_asset_volume_share_high_alt_long_1d.md`
