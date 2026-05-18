# Skill: R-4 Automated Elite Gate Evaluation

> Parent agent: `paradigm-architect`
> Purpose: Step 6 — automated 4-dim freq gate after R-3 PASS
> Tools: Bash, Read

## Step 6.1 — Run Gate Evaluator

```bash
PYTHONPATH=. python3 -m scripts.research.eval_research_gate \
  --metrics backend/runs/research_track/{paradigm_name}/r3__metrics.json \
  --paradigm-name {paradigm_name} --type E
```

Read exit code:
- **0 (PASS)**: promote to R-4, generate `gate_eval__{paradigm_name}.md`, alert user
- **1 (FAIL)**: attach gate_eval to index, do NOT promote past R-3

## Step 6.2 — Elite Gate Dimensions (4-dim freq)

The gate evaluator checks these 4 dimensions simultaneously:

| Dimension | Criterion | Typical threshold |
|---|---|---|
| **trades/yr** | annualized event count | ≥ 12 for life-changing scope |
| **edge per trade** | mean_bp after fees | ≥ +2% (200bp) for life-changing |
| **capital utilization** | % of capital deployed | ≥ 30% sustained |
| **sharpe / sortino** | risk-adjusted return | ≥ 1.5 (R-2 baseline) |

For full criteria see `eval_research_gate.py` (function `evaluate_e_new` for `_perm_utils` schema).

## Step 6.3 — Promote to R-4

If gate PASS:
```bash
PYTHONPATH=. python3 -m scripts.research.paradigm_index promote \
  {paradigm_name} --to-phase R-4 \
  --metrics backend/runs/research_track/{paradigm_name}/r3__metrics.json
```

Generate Korean summary `gate_eval__{paradigm_name}.md`:
- 4-dim gate result table
- 결정적 강점 / 약점
- 다음 단계 권장 (R-5 시드 vs 추가 robustness)

## Reference
- `backend/scripts/research/eval_research_gate.py` — gate evaluator
- `.claude/plans/research_track_master.md` — elite gate definition
- [[feedback_life_changing_strategy_criterion]] — 4-dim 기준 (trades/yr<12 또는 edge<2%/trade 자동 graveyard)
