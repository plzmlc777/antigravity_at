# Skill: Promotion to R-5 + Graveyard Report Format

> Parent agent: `paradigm-architect`
> Purpose: Step 7 — R-5 AUTO-SEED + graveyard report convention
> Tools: Read, Write

## Step 7.1 — R-5 승격 큐 등록 (2026-07-11 리그 모델)

3군→2군 승격은 tier-governor 리그(24석, 매달 1일 3↓/3↑, 공석 즉시 충원)가 집행한다.
Architect는 직접 시드하지 않고 **큐에 등록**한다. On R-4 PASS:

1. R-3 per-symbol 지표 상위 **3개 심볼** 선정, 심볼별 paper spec JSON 작성:
   `backend/configs/paper_sessions/{paradigm_name}_{symbol}.json`
   (**paper mode ONLY, never live/real**, R-3 optimum SL/hold, 127/128 spec 패턴)
2. `backend/configs/tier_promotion_queue.json` `.queue`에 append:
   `{"name", "spec"(backend 상대경로), "paradigm", "symbol", "gate_score", "enqueued_at"}`
   — gate_score는 R-4 gate composite (governor가 내림차순 우선 시드).
3. `backend/runs/research_track/{paradigm_name}/r5_seed_proposal.md` 저장 (기록 유지).
4. Print one-line summary:
```
✅ paradigm-architect: R-5 ENQUEUED — {paradigm_name}, {n} symbols, queue depth {q}.
   gate_eval: backend/runs/research_track/{paradigm_name}/gate_eval__{paradigm_name}.md
```

이후 시드/판정/강등 전부 tier-governor 자동. **1군(live) 진입만 대표님 수동 승인**.

## Step 7.2 — Graveyard Report Format

For any paradigm graveyarded at any phase (R-0 prescreen / R-1 / R-2 / R-3 / R-4 FAIL), generate `graveyard__{paradigm_name}.md`:

```markdown
# Graveyard — {paradigm_name} (paradigm #{N})

**Date**: {YYYY-MM-DD KST}
**Phase reached**: {R-0_prescreen / R-1 / R-2 / R-3 / R-4}
**Verdict**: {SAMPLE_INSUFFICIENT / FEE_DRAG_TRAP / CONCENTRATED_R1_PASS / BROAD_FALSIFIED / FRAGILE_TEMPORAL_WF_FAIL / 3-gate FAIL / DNA_DUPLICATE / DISPATCH_IMPOSSIBLE}

## Hypothesis
{Korean 한 줄}

## DNA dimensions
- Data source: ...
- Decision mode: ...
- Time scale: ...
- Universe shape: ...

## Phase results
- R-0 inventory: PASS/FAIL/halt reason
- R-1: signal_t_excess=... / ci_lower_bp=... / perm_p=... / concentration verdict
- (R-2 / R-3 if reached) ...
- Symmetric Negative Test (if joint-trigger): {A focus / A mirror / B same-sign / B mirror} verdict

## Reason
{2-3 Korean 문장 — 결정적 fail mode 인용 + 어느 lesson에 해당하는지 명시 (#11/#15/#16/#19/#20/#21/#22/#23/#24/#26/#27/#28)}

## Lessons learned
- (if novel) 새로운 lesson 후보: ...
- (if existing) 적용된 기존 lesson: ...

## References
- code: backend/scripts/research/{paradigm_name}_r1.py
- metrics: backend/runs/research_track/{paradigm_name}/r1__metrics.json
- precedent: paradigm #{X} (graveyard__{X}.md)
```

## Step 7.3 — Update Q3 Lesson Index (if new lesson)

If graveyard reveals novel failure mode not covered by lessons #11-#28:
1. Add to `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.2
2. Update `lesson_prescreen_checklist.md` (this skill bundle)
3. Note in commit message: "lesson #N {description}"

## Reference
- Existing graveyard reports: `backend/runs/research_track/graveyard__*.md` (~86개)
- Q3 lesson index: `backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md` §6.2
- handoff: `.claude/plans/paradigm_architect_handoff.json`
