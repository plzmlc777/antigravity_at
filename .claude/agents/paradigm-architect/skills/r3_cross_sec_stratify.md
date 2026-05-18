# Skill: R-3 Robustness — Cross-Sectional + Regime Stratification

> Parent agent: `paradigm-architect`
> Purpose: Step 5 — R-3 robustness checks after R-2 PASS
> Tools: Bash, Read, Write

## Step 5.1 — R-3 Script Coverage

Generate `{paradigm_name}_r3.py` covering:

### Regime Stratification
Categorize trades by:
- **BTC trend regime**: bull / bear / sideways / volatile (1d MA slope + vol)
- **Vol regime**: low / mid / high (BTC 30d realized vol p33/p67 split)
- **Listing density**: new-listing-heavy period vs steady period
- **Funding regime**: high/low funding rate environment

For each regime cell, compute:
- n_trades, mean_bp, t_stat, ci_lower_bp, ci_pos
- Mark cells with n < 30 as `skip: insufficient_sample`

### Grid Search
Sweep strategy parameters:
- SL × hold × entry threshold (typically 3-4 grid points each)
- Identify plateau: contiguous parameter neighborhood where edge holds (>1.5σ)
- Single-point peak = overfit warning

### Correlation Check vs Existing Paradigms
For each active paper paradigm in `research_track_master.md`:
- Compute cosine similarity of signal series (trigger events × time)
- `> 0.7` = reject as duplicate, recommend variant scoping instead

Persist to `r3__metrics.json`.

## Step 5.2 — Sign-Conditional 4-Cell Stratify (Lesson #20)

If paradigm involves sign-conditional triggers (e.g., BTC up-trigger LONG vs BTC down-trigger SHORT), stratify into 4 cells:
- Cell 1: focus_sign × focus_direction
- Cell 2: focus_sign × mirror_direction
- Cell 3: mirror_sign × focus_direction
- Cell 4: mirror_sign × mirror_direction

If focus FAIL but non-focus cell PASS three-gate isolated → Concentration FAIL (paradigm 81 precedent: cell 4 sigex +2.52 but 3/13 alts only). Halt with `NARROW_SCOPE_CANDIDATE` verdict — do NOT auto-dispatch narrow variant.

## Step 5.3 — R-3 PASS Criteria

- **Regime robustness**: ≥ 3 of 4 BTC trend regimes have ci_lower_bp > 0 (low vol regime may be exempt with note)
- **Plateau**: at least one 3×3 parameter neighborhood with all cells signal_t_excess >= 1.5
- **Correlation**: max paradigm-similarity < 0.7

If R-3 FAIL: graveyard with reason.

## Reference
- Q3 Lesson #20 — sign-cond 4-cell stratify (paradigm 81 precedent)
- `lifecycle_phase_r3.py` — R-3 exemplar
