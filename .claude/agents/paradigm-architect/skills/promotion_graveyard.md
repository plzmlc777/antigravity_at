# Skill: Promotion to R-5 + Graveyard Report Format

> Parent agent: `paradigm-architect`
> Purpose: Step 7 — R-5 AUTO-SEED + graveyard report convention
> Tools: Read, Write

## Step 7.1 — R-5 Auto-Seed (2026-07-11 자동화 지시)

3군→2군 승격은 자동이다. On R-4 PASS:

1. **Slot check**: read `backend/runs/tier_governor/state.json` → `.slots.used` / `.slots.max` (8).
   - Slots full → seed proposal artifacts만 생성 후 STOP:
     `⏸ R-4 PASS — {paradigm_name}, 2군 slots full ({used}/8). seed queued.`
2. **Seed** (slots available): draft `backend/configs/paper_sessions/{paradigm_name}.json`
   spec (per-symbol, R-3 optimum SL/hold), then create sessions via
   `paper_session_cli create` — **paper mode ONLY, never live/real**.
   Follow paradigm 127/128 seeding pattern.
3. Save `backend/runs/research_track/{paradigm_name}/r5_seed_proposal.md` (기록 목적 유지).
4. Print one-line summary:
```
✅ paradigm-architect: R-5 AUTO-SEEDED — {paradigm_name}, {n} sessions, slots {used}/8.
   gate_eval: backend/runs/research_track/{paradigm_name}/gate_eval__{paradigm_name}.md
```

Day-30 이후 판정(CONTINUE/TERMINATE/RESEED/PROMOTE 후보)은 tier-governor cron이
자동 집행. **1군(live) 진입만 대표님 수동 승인** — 절대 자동 실행 금지.

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
