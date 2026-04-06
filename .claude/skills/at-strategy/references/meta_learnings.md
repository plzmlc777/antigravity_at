# Meta-Learnings Knowledge Base

> This file is maintained by the `meta-learner` agent.
> Each entry captures a discovered pattern with evidence, actionable rules, and confidence.
> Entries below 0.7 confidence are excluded. Stale entries should be reviewed and invalidated over time.

## Schema

Each discovery entry follows this structure:

```
## [YYYY-MM-DD] <Discovery Title>
- **ID**: D<NNN>
- **Type**: temporal_pattern | parameter_sensitivity | cross_strategy | failure_signature | edge_decay | regime_shift | anomaly
- **Impact**: critical | high | medium | low
- **Confidence**: 0.00 ~ 1.00
- **Sample Size**: <N trades / sessions>
- **Date Range**: <start> ~ <end>
- **Pattern**: <description>
- **Evidence**: <metrics, session IDs, statistics>
- **Actionable Rule**:
  - Condition: <when>
  - Action: <what to do>
  - Anti-condition: <when NOT>
  - Anti-action: <what to avoid>
- **Status**: active | invalidated | under_review
```

## Discoveries

<!-- New discoveries will be appended below this line -->

## Invalidated / Archived

<!-- Stale or disproven patterns go here for historical record -->
