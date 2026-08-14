# R-1 GRAVEYARD: hmm_per_symbol_latent_regime_alt_directional_4h

**Date**: 2026-05-20 KST (Mint host execution)
**Verdict**: `BROAD_FALSIFIED`
**Phase**: R-1 (halted)
**Counter**: paradigm 119 (post-paradigm-118 sequence)

## Hypothesis (recap)

Per-symbol 3-state Gaussian HMM fit on alt 1h log-returns over rolling 90d window → posterior probability of each latent state. Trigger when one state's posterior > 0.8:
- HIGH-vol state → 4h forward SHORT (mean-revert)
- LOW-vol state → 4h forward LONG (continuation)
- NEUTRAL state → no trade (sanity baseline)

## R-1 evaluation summary (4-quadrant Symmetric Negative Test, Lesson #19)

| Quadrant | n_obs | mean_net_bp | mean_gross_bp | sigex | ci_lower_bp | perm_p | three_gate | concentration | fee_floor |
|---|---|---|---|---|---|---|---|---|---|
| **A_focus** HIGH×SHORT | 4,150 | -15.10 | -7.10 | -0.59 | -27.42 | 0.274 | FAIL | FAIL | FAIL (gross < 16bp) |
| **A_mirror** HIGH×LONG | 4,150 | +14.88 | +22.88 | +4.58 | +2.74 | 0.411 | FAIL (perm_p) | FAIL | PASS |
| **B_focus** LOW×LONG | 12,353 | -7.66 | +0.34 | -1.58 | -10.59 | 0.054 | FAIL | FAIL | FAIL |
| **B_mirror** LOW×SHORT | 12,353 | -5.78 | +2.22 | -0.83 | -8.56 | 0.207 | FAIL | FAIL | FAIL |

**4-quadrant verdict**: `BROAD_FALSIFIED` (0/4 three-gate PASS).

## Key diagnostic findings

### Finding 1 — HMM fit infrastructure healthy
- 14/14 syms HMM fit succeeded
- 1,482/1,482 fits converged (100% convergence rate)
- 1,462/1,482 fits had balanced state distribution (only 20 fits showed >85% dominant state)
- Per-sym state dist: LOW 45-49%, NEUTRAL 44-48%, HIGH 2-10% — 3-state hypothesis structurally valid
- Empirical HIGH posterior >0.8 trigger rate: 1.3-7.5% per sym (above Lesson #11 floor)
- Elapsed 162.8s wall-clock — well within 20min foreground budget
- HMM as paradigm statistic class is implementable, but underlying mechanism does NOT produce alpha

### Finding 2 — A_mirror HIGH×LONG sigex +4.58 is mathematical-mirror artifact (NOT real signal)
- A_focus mean_gross_bp = -7.10; A_mirror mean_gross_bp = +22.88; spread ~ 30bp ~ +/-16bp fee floor swing
- Both have identical n_obs = 4,150 (same trigger set, opposite direction)
- A_mirror sigex +4.58 is high BUT perm_p = 0.411 (fee-aware null also drifts up) → not statistically rare
- 0/14 syms ci_pos (Concentration Gate hard FAIL)
- Diffuse_pos_candidate = False (per-sym CI all negative on lower bound)
- Per-quarter: 6/9 quarters positive t, but with 2025Q4-2026Q1 sign flip (regime instability)
- Lesson #41 DIFFUSE_POSITIVE not triggered (sigex < +4.0 cutoff after concentration eval)
- Interpretation: HIGH-vol state windows have a slight upward gross drift (after fee, +14.88bp net) — but this drift is structurally indistinguishable from random-anchor windows of comparable HIGH-vol periods (perm_p 0.41). This is a survival bias / regime artifact, NOT a HMM-discovered mechanism.

### Finding 3 — LOW-state alpha is structurally zero
- B_focus LOW×LONG mean_gross_bp = +0.34 (essentially zero gross alpha)
- B_mirror LOW×SHORT mean_gross_bp = +2.22 (also near-zero)
- BOTH FAIL fee floor (gross < 16bp)
- LOW state = high-frequency "calm" continuation pool but with no directional excess → fee drag dominates
- 12,353 obs each — sample size not the issue, signal absence is structural

### Finding 4 — Sweep verdict scan (Lesson #37 full-sweep) — 0/32 cells PASS
- 32 sweep cells (4 posterior thresholds × 4 hold horizons × 2 focus directions)
- 0/32 three-gate PASS
- Top sigex by cell:
  - LOW dir+1 thr=0.9 hold=24h: sigex +1.76 (ci_lower -2.96bp, perm_p 0.107) — closest to PASS but FAIL on ci_lower AND fee
  - Most HIGH×SHORT and LOW×LONG cells cluster around sigex -0.5 to -4.0 (anti-momentum direction = systematic fee drag)
- Strongest negative sigex: LOW dir+1 thr=0.6 hold=2h n=73,024 sigex -5.47 — fee-floor demonstration cell (massive sample, gross ~ +0.18bp, net ~ -7.82bp, structural -8bp fee impact)

### Finding 5 — Mechanism CLASS asymmetry (Lesson #42 diagnostic) — NOT applicable here
- A_focus sigex -0.59 (HIGH×SHORT fails)
- B_focus sigex -1.58 (LOW×LONG fails)
- `asymmetric_mechanism_flag` = False (both directions FAIL — no asymmetric mechanism to rescue)
- Lesson #42 anti-pattern (PUMP-mirror absence) does NOT apply because this paradigm is not "extreme magnitude → mean-revert" class

### Finding 6 — Universe drift (Lesson #32 LEVEL coherence)
- A_focus excess vs no-event baseline: -9.53bp (A_focus is WORSE than baseline drift)
- B_focus excess vs no-event baseline: -1.05bp (B_focus barely above baseline)
- `drift_artifact_risk` = False (universe drift not the cause; signal genuinely absent)

### Finding 7 — Per-quarter regime change (HIGH state, A_mirror direction)
- 2024Q2-Q3: A_mirror +54/+16bp positive (early period)
- 2024Q4: +36bp positive
- 2025Q1: ~ 0 (transition)
- 2025Q2-Q3: +28/+50bp positive (continued positive)
- 2025Q4-2026Q1: SIGN FLIP to -35/-30bp negative
- 2026Q2: +80bp positive (small n=85)
- Lesson #26 amendment: 6/9 quarters positive t-ratio passes, BUT sign-flip in last 2 quarters indicates regime instability that perm test correctly catches via wide null distribution. Even if R-2 walk-forward were attempted, the temporal instability would force `FRAGILE_TEMPORAL_WF_FAIL`.

## Verdict tree resolution

- Three-gate FAIL all 4 quadrants → `BROAD_FALSIFIED` (not `BROAD_FALSIFIED_FEE_FLOOR` since A_mirror passes fee floor)
- No DIFFUSE_POSITIVE candidate (sigex < +4.0 cutoff after concentration eval, syms_ci_pos = 0 across all cells)
- No NARROW_SCOPE_LIFE_CHANGING_FAIL pathway (no three-gate PASS achieved)
- No CONCENTRATED_R1_PASS (no three-gate PASS)
- No MIRROR_ONLY_BROAD_FALSIFIED (A_mirror perm_p FAIL despite sigex)

## Family classification & lessons

### Family attribution
- Per-symbol latent-regime via HMM — new statistic class, did NOT subsume into existing Tier 4 retired families
- Adjacent to paradigm 83 (k-means latent regime) but mechanistically distinct (time-dependent Markov vs snapshot clustering)
- Outcome supports paradigm 83 finding that latent-regime decomposition alone does not synthesize alpha (Lesson #21 amendment)

### Lessons reinforced
- Lesson #21 (axis stacking does not synthesize alpha): HMM's 3-state decomposition is a more sophisticated form of regime axis stacking. Result: same broad-falsified outcome as k-means. Statistical decomposition layer (regime detection) alone insufficient — needs orthogonal mechanism (fundamental data axis: funding, OI, premium, liquidation cascade, listing event) to produce alpha.
- Lesson #18 (mechanical vs substantive verdict): A_mirror sigex +4.58 BUT perm_p 0.411 — the fee-aware permutation null correctly catches the "mechanical mirror" artifact. Bootstrap CI ci_lower +2.74bp barely positive — also borderline. Without perm gate, this paradigm would falsely qualify.
- Lesson #16 Concentration Gate: 0/14 syms ci_pos on every quadrant — pool-level positive drift on A_mirror is broadly diffuse and individually non-significant, exactly the antipattern Lesson #16 was designed to catch.

### NEW lesson candidate (1 dogfood) — Statistical decomposition without mechanism

**Trigger**: R-1 hypothesis statistic class = unsupervised regime decomposition (HMM, k-means, mixture model, GMM, change-point detection) applied to ENDOGENOUS price returns alone (no external/orthogonal information).

**Check**: empirical evidence that endogenous-only decomposition recovers visible regimes (HMM converges, state distribution balanced, posterior distribution non-degenerate) but state-conditional forward returns show no directional alpha after fee + Concentration Gate.

**Action**: at R-0, halt before R-1 dispatch if hypothesis statistic = unsupervised decomposition × endogenous-only feature. Require orthogonal external axis (funding / OI / liquidation / listing event / volume) joined with decomposition to recover meaningful alpha. Pure regime detection is a describing tool, not a predicting tool.

**Why candidate (1 dogfood — paradigm 119 HMM today)**:
- HMM 100% convergence + balanced 3-state + 0/14 ci_pos in every quadrant
- Adjacent to paradigm 83 (k-means latent regime BROAD_FALSIFIED_FEE_FLOOR, Lesson #21 sub-class)
- Generalizes paradigm 83's finding from snapshot clustering to time-dependent Markov chain — same conclusion holds
- Cumulative pattern: endogenous-only decomposition statistic class consistently fails

**Family retire path**: if 1 more dogfood (next unsupervised decomposition × endogenous-only paradigm) FAIL → formally retire `unsupervised_decomposition_endogenous_only` family at Tier 4.

## Cumulative paradigm count

- This is paradigm 119 in the BROAD_FALSIFIED graveyard sequence
- Cumulative graveyards: 119+
- Track 4 retired families: 8 (listing event / KR DART entry-side / funding single-signal / volume share single-side / cross-exchange funding / 5m microstructure single-domain / book_depth daily / taker-side aggressive volume)
- Track 4 advisory caution: 5m microstructure single-domain (4 graveyards approaching formal retire)
- Confirmed lessons: #11-#34 + #41 (confirmed-with-amendment)
- Candidate lessons: #21-sub / #30 / #32 / #33 / #42 / #43 / #44 / NEW: #45 unsupervised decomposition without orthogonal mechanism

## Files

- script: `backend/scripts/research/hmm_per_symbol_latent_regime_alt_directional_4h_r1.py` (Mint, ~570 lines)
- metrics: `backend/runs/research_track/hmm_per_symbol_latent_regime_alt_directional_4h/r1__metrics.json`
- stdout log: `backend/runs/research_track/hmm_per_symbol_latent_regime_alt_directional_4h/r1__stdout.log`
- this report: `backend/runs/research_track/hmm_per_symbol_latent_regime_alt_directional_4h/r1_FAIL.md`
- INDEX update: `paradigm_index promote --to-phase graveyard hmm_per_symbol_latent_regime_alt_directional_4h`

## Infrastructure deltas (permanent assets)

- hmmlearn 0.3.3 installed on Mint venv (first-use). Compatible with numpy 2.2.6, scipy 1.17.0, scikit-learn 1.8.0.
- HMM walk-forward fit pattern (~10s per 14-sym × 1,482 total fits) validated. Future paradigms requiring HMM/GMM/mixture models can reuse this skeleton.
- Per-symbol state-label series + posterior-max time series construction methodology documented for downstream paradigms (regime conditioning as feature for future hypotheses).

## Recommended next action

1. Document new Lesson #45 candidate (unsupervised decomposition × endogenous-only insufficient) in `lesson_prescreen_checklist.md` after 1 more dogfood
2. DO NOT auto-dispatch any HMM/k-means/GMM × endogenous-only-feature variant as next paradigm — explicit mechanism orthogonal-axis injection required
3. Continue continuous parallel campaign with mechanism-grade external-axis paradigms (paradigm-architect closing rate snapshot 2026-05-19 axis selection guide)
4. Halt at R-1. Await user instruction for next paradigm dispatch.
