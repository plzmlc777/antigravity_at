# Decision Log

> This file is maintained by the `cio` workflow (writes decisions) and `self-critic` agent (writes audits).
> Each decision captures who decided what, why, what was expected, and what actually happened.
> Audits are written separately and reference decision IDs.

## Decision Schema

```
## [YYYY-MM-DD] CIO-<YYYYMMDD>-<NNN>: <One-line action title>
- **Workflow**: daily-review | symbol-select | emergency | new-session | learn-evolve-reflect | ai-signal
- **Session**: <session_id> (or "n/a" for system-wide)
- **Symbol**: <SYMBOL> | n/a
- **Action**: <what was decided>
- **Trigger**: <ASSESS findings that prompted action>
- **Process**:
  - ops-monitor: <key finding>
  - market-researcher: <key finding>
  - strategy-advisor: <recommendation> (confidence: <0.00-1.00>)
  - backtest-analyst: <return/MDD/sharpe> (overfit: <ratio>)
  - risk-manager: approved | rejected — <rationale>
- **Executed**: yes | no | dry-run
- **Expected**: <return %, MDD %, win rate %, time horizon>
- **Outcome (filled in later)**:
  - At <T+1d/T+7d/T+30d>: <actual metrics>
  - Variance vs expected: <delta>
  - Counterfactual: <what would have happened with no-action>
- **Status**: pending_outcome | confirmed | falsified
```

## Audit Schema (self-critic entries)

```
## [YYYY-MM-DD] AUDIT-<YYYYMMDD>-<NNN>: <Audit summary>
- **Period audited**: <start> ~ <end>
- **Decisions reviewed**: <count> (refs: CIO-..., CIO-...)
- **Overall grade**: A | B | C | D | F
- **Bias detected**: confirmation | recency | overconfidence | action | anchoring | sunk_cost
- **Severity**: low | medium | high | critical
- **Calibration**:
  - strategy-advisor: stated <X>, actual <Y>, delta <Z>
  - backtest-analyst: expected return <X>, realized <Y>
- **Improvement directives** (refs: D-001, D-002, ...):
  - <agent>: <directive>
- **Health score**: 0-100
- **Status**: open | applied | obsolete
```

## Decisions

<!-- New decisions will be appended below this line -->

## Audits

<!-- Self-critic audit reports go here -->

## Improvement Directives Tracker

| ID | Date | Target Agent | Directive | Priority | Status | Applied |
|----|------|--------------|-----------|----------|--------|---------|
<!-- Directives from self-critic accumulate here for cross-reference -->
