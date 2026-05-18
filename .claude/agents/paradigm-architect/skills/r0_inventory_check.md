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

## Reference
- `.claude/plans/research_track_master.md` §0 — 8-paradigm DNA matrix
- `backend/scripts/research/paradigm_index.py`
- Lesson #11 (Q3 sample-density prescreen)
