# Skill: R-1 PoC Protocol (Three-Gate + Concentration + Symmetric Negative Test)

> Parent agent: `paradigm-architect`
> Purpose: Step 3 — R-1 PoC execution with mandatory stat suite
> Tools: Bash (script execution), Read, Write (script generation)

## Step 3.1 — R-1 Script Generation

Generate `backend/scripts/research/{paradigm_name}_r1.py` following the skeleton (see `lifecycle_phase_poc.py` for exemplar):

1. Load required data (DB ohlcv / metrics joblib / external)
2. Compute the test statistic per cohort/event
3. Output JSON to `backend/runs/research_track/{paradigm_name}/r1__metrics.json`
4. Print summary stats

Deploy to mint, execute, capture output, parse metrics.

## Step 3.2 — Mandatory R-1 Stat Suite

**CRITICAL**: Use `scripts.research._perm_utils` for ALL R-1 statistical tests.

The naive perm test (shuffle trigger anchors, recompute t-stat) is a known **fee-drag trap**: with 8 bp round-trip fee × 1000+ trade pool, the perm null itself has mean t ≈ −5 to −8 σ even when there is no signal. Five paradigms (2026-05-14) graveyarded because observed t was indistinguishable from this fee-saturated null. Don't repeat the mistake.

```python
from scripts.research._perm_utils import (
    fee_aware_perm_test,      # observed-vs-fee-saturated-null comparison
    block_permutation_test,   # within-symbol block shuffle, preserves autocorr
    bootstrap_ci,             # CI on observed mean — model-free pass signal
)

# observed = per-trade NET returns at actual triggers (post-fee)
# candidate_pool = per-trade GROSS returns over ALL possible entry windows
fee_result = fee_aware_perm_test(observed_net_returns=observed,
                                  candidate_pool_returns=candidate_pool,
                                  fee_per_trade=0.0008, n_perms=1000)
# REPORT: obs_t, null_mean_t, signal_t_excess, perm_p_two_sided

ci_result = bootstrap_ci(observed, n_boot=2000, block_size=hold_window)
# REPORT: mean, ci_lower, ci_upper, prob_positive
```

## Step 3.3 — R-1 PASS Criteria (Three-Gate)

A sub-hypothesis passes R-1 only if ALL three hold simultaneously:
- `fee_result.signal_t_excess >= 2.0` — observed t ≥ 2σ above fee-drift null mean
- `ci_result.ci_lower > 0` — 95% block-bootstrap CI on observed net mean excludes zero
- `fee_result.perm_p_two_sided <= 0.10` — observation is rare under fee-aware null

Older "loose" gate `|t| ≥ 2 OR perm_p ≤ 0.10` is **deprecated**.

Also report (mandatory, for diagnostic transparency):
- `n_signals` (total trade events)
- `n_candidate_pool` (universe of non-trigger windows)
- per-symbol consistency (≥8/14 syms direction-consistent for cross-sym pooled paradigms)

If R-1 FAIL on three-gate: graveyard with reason citing which gate failed.

## Step 3.4 — Lesson #16 Concentration Diagnostics (mandatory)

Aggregate three-gate PASS can still hide cherry-pick (alpha concentrated in 1-2 quarters or 1-2 symbols). Paradigm 77 R-1 4-gate ALL PASS but R-2 FAIL because alpha was BNB+WIF only and 2/4 quarters negative. Catch at R-1, not R-2.

**Required additional fields in `r1__metrics.json`** (auto-emit):

```python
obs_df = pd.DataFrame({"ts": entry_timestamps, "symbol": symbols, "net_return": net_returns})

# Per-quarter t-stat distribution
obs_df["quarter"] = obs_df["ts"].dt.to_period("Q").astype(str)
per_q = obs_df.groupby("quarter").agg(
    n_trades=("net_return", "size"),
    mean_bp=("net_return", lambda s: s.mean() * 10000),
    t_stat=("net_return", lambda s: float(s.mean() / s.std(ddof=1) * (len(s) ** 0.5)) if len(s) >= 3 and s.std(ddof=1) > 0 else float("nan")),
).reset_index()

# Per-symbol bootstrap CI
per_sym_records = []
for sym, sub in obs_df.groupby("symbol"):
    if len(sub) < 10:
        per_sym_records.append({"symbol": sym, "n_trades": len(sub), "skip": "n<10"})
        continue
    ci = bootstrap_ci(sub["net_return"].values, n_boot=2000, block_size=1)
    per_sym_records.append({"symbol": sym, "n_trades": len(sub),
                            "mean_bp": float(sub["net_return"].mean() * 10000),
                            "ci_lower_bp": ci["ci_lower"] * 10000,
                            "ci_upper_bp": ci["ci_upper"] * 10000,
                            "ci_lower_pos": ci["ci_lower"] > 0})

metrics["concentration"] = {
    "per_quarter_t_stats": per_q.to_dict(orient="records"),
    "n_quarters_measurable": int((per_q["n_trades"] >= 10).sum()),
    "n_quarters_pos_t": int(((per_q["t_stat"] > 0) & (per_q["n_trades"] >= 10)).sum()),
    "quarter_pos_t_ratio": ...,
    "per_symbol_bootstrap": per_sym_records,
    "n_symbols_measurable": ...,
    "n_symbols_ci_pos": ...,
    "symbol_ci_pos_ratio": ...,
}
```

**Concentration Gate** (applied AFTER three-gate PASS):
- `quarter_pos_t_ratio >= 0.5` — ≥half measurable quarters t > 0
- `symbol_ci_pos_ratio >= 0.30` AND `n_symbols_ci_pos >= 3`

If three-gate PASS but Concentration Gate FAIL → verdict = `CONCENTRATED_R1_PASS`, halt at R-1, do NOT auto-promote.

## Step 3.5 — Lesson #19 Symmetric Negative Test (joint-trigger paradigms)

Joint-trigger paradigms (logical AND of two+ z-scores/threshold events) admit multiple directional interpretations. Test all 4 sign-quadrants in ONE R-1 batch:

1. **Mechanism A focus** — full three-gate + concentration
2. **Mechanism A mirror** (LONG/SHORT swapped) — min `mean_net_bp`, `signal_t_excess`, `ci_lower_bp`, `perm_p_two_sided`
3. **Mechanism B same-sign joint** (continuation if A is reversal) — full eval
4. **Mechanism B mirror** — derive by symmetry unless promising

Report in `r1__metrics.json` under `symmetric_variants`:
```python
metrics["symmetric_variants"] = {
    "mechanism_A_focus": {...},
    "mechanism_A_mirror": {...},
    "mechanism_B_same_sign": {...},
    "mechanism_B_mirror": {...},
}
```

**Verdict resolution**:
- All 4 variants 3-gate FAIL → **broad-falsified**, graveyard, no follow-up R-1
- One variant 3-gate PASS, others FAIL → that variant becomes paradigm
- Multiple variants PASS → halt, sub-paradigm split candidate

## Step 3.6 — Lesson #15 Non-focus PASS 4-Condition Promotion Policy

If focus threshold FAILS three-gate but non-focus threshold in same sweep PASSES, do NOT auto-promote. Spawn separate paradigm only if ALL four hold:
- (a) all 4 R-1 gates pass (three-gate + diversity ≥ 7/12 alts)
- (b) **separate R-1 replication** on held-out adjacent sample (window shift +30d), result within ±10% of focus
- (c) **Bonferroni-adjusted p-value** ≤ 0.10 (perm_p × total sweep tests)
- (d) hold-window sweep sign consistency (60m/120m/240m/480m all same direction)

Even when (a)-(d) all met: treat as R-2 candidate, not R-1 PASS.

## Reference
- `backend/scripts/research/_perm_utils.py` — fee-aware perm + bootstrap CI
- `backend/scripts/research/lifecycle_phase_poc.py` — exemplar
- Q3 Lessons #11 / #15 / #16 / #19 (see `lesson_prescreen_checklist.md`)
- 5 paradigms graveyard 2026-05-14 — fee-drag trap precedent
