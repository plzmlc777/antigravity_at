# Skill: R-2 Multi-Symbol Expansion + Walk-Forward

> Parent agent: `paradigm-architect`
> Purpose: Step 4 — R-2 expansion after R-1 PASS
> Tools: Bash (script execution), Read, Write (script generation)

## Step 4.1 — R-2 Cohort Expansion

If R-1 promising, expand:
- For **E-type (event-study)**: cohort to ≥ 100 samples (backfill new symbols as needed)
- For **T-type (time-series)**: ≥ 5 symbols, 1-year OOS

## Step 4.2 — R-2 Script Generation

Generate `{paradigm_name}_r2.py` with:
- Full simulation including SL/TP/hold parameters
- Permutation test (n ≥ 200)
- Bootstrap CI on key statistic (n ≥ 1000)
- Quarterly / regime fold breakdown
- Persist to `r2__metrics.json`

## Step 4.3 — Temporal Walk-Forward Mandatory

**Lesson #26 (2026-05-18, paradigm 87 fallout)**: aggregate R-1 PASS ≠ regime-robust. WF + 5-fold TS-CV obligatory.

```python
# Walk-forward split
n_splits = 5
splits = TimeSeriesSplit(n_splits=n_splits, gap=hold_window)

per_fold_records = []
for train_idx, test_idx in splits.split(events_df):
    train_subset = events_df.iloc[train_idx]
    test_subset = events_df.iloc[test_idx]
    # fit params on train, eval on test
    # record per-fold: n_test_trades, t_stat, mean_bp, ci_lower_bp, pass_3gate
    per_fold_records.append({...})

metrics["walk_forward"] = {
    "n_splits": n_splits,
    "per_fold": per_fold_records,
    "n_folds_pass": sum(1 for r in per_fold_records if r["pass_3gate"]),
}
```

## Step 4.4 — Small-Sample Blind Spot Warning

If `n_quarters_measurable < 4` or `total_n < 100`: per-quarter Concentration Gate may give false positive (single outlier quarter dominates). Apply stricter rule:
- Require `n_folds_pass >= 3/5` OR `n_quarters_pos_t_strict >= ⌈0.7 × n_q_measurable⌉`

## Step 4.5 — R-2 PASS Criteria

- For **E-type**: `median_ret ≥ 15%` AND `win_rate ≥ 55%` AND `perm_p ≤ 0.05` AND bootstrap `ci_lower > 0`
- For **T-type**: `alpha ≥ 100%` AND `sharpe ≥ 1.5` AND `perm_p ≤ 0.05`

Additional WF gate (mandatory after Lesson #26):
- `n_folds_pass >= 3/5` — at least 3 of 5 TS-CV folds pass 3-gate

If R-2 FAIL: graveyard with reason (e.g., "sharpe pos but median CI crosses zero", or "WF 1/5 folds pass — single-fold artifact"). STOP.

## Reference
- Q3 Lesson #26 — temporal WF mandatory (paradigm 87 precedent)
- `lifecycle_phase_r2.py` — R-2 exemplar
