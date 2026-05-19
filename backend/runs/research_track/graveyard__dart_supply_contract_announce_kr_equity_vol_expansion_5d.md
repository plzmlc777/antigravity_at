# GRAVEYARD — paradigm 102 (proposed index)

`dart_supply_contract_announce_kr_equity_vol_expansion_5d`

- **Verdict**: `BROAD_FALSIFIED`
- **Phase**: R-1
- **Date**: 2026-05-19 KST
- **Hypothesis**: KR equity 단일판매·공급계약체결 공시 → +1d open / +5d hold 동안
  realized vol expansion magnitude (direction-blind, straddle-payoff).

## Headline numbers (5d hold, 100bp straddle round-trip fee)

| Quadrant | n | gross\|abs\|_bp | net_bp | t_obs | sig_t_excess | CI_lower_bp | perm_p_above | mean_vol_ratio | pass_3g |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **A focus** announce × vr≥1.5 | 311 | 1087.1 | 987.1 | 15.45 | **1.95** | 868.4 | 0.073 | 1.99 | **FAIL** (sig_t_ex < 2.0) |
| A mirror announce × vr<1.0 | 1211 | 524.6 | 424.6 | 31.62 | 5.63 | 398.4 | 0.000 | 0.64 | PASS |
| **B baseline** non_announce × vr≥1.5 | 4118 | 1173.1 | **1073.1** | 54.25 | **6.52** | 1034.8 | 0.000 | 2.15 | PASS |
| B baseline non_announce × vr<1.0 | 19058 | 500.2 | 400.2 | 117.86 | nan† | 393.8 | nan† | 0.62 | n/a |
| A focus stress @ 200bp | 311 | 1087.1 | 887.1 | 13.88 | 2.93 | 768.4 | 0.000 | 1.99 | PASS (stress) |

† nan = `fee_aware_perm_test` returns NaN when `n_pool < 2 × n_obs` (helper protection); not a bug.

## Why BROAD_FALSIFIED — the universe-conditioning artifact

This is a textbook **Lesson #32 universe-baseline-coherent A_focus trap variant** —
but at the **conditioning level**, not the level-of-vol_ratio level.

1. **Lesson #32 vol_ratio level passes trivially**: A_focus mean vol_ratio = 1.99 ≫
   B_baseline universe mean = 0.96 (excess +1.03, 5% threshold cleared 20×).
   Announcement DOES correlate with high vol_ratio.

2. **But the straddle payoff in A_focus is LOWER than in B_baseline_expand**:
   - A focus: 987 bp/trade, sig_t_ex = 1.95
   - B baseline (vr≥1.5): **1073 bp/trade, sig_t_ex = 6.52**
   - When you randomly sample non-announce days that *happen* to have post-5d
     vol_ratio ≥ 1.5, you get **+86 bp more straddle payoff** than when you
     condition on an announcement triggering the same vol_ratio.

3. **Mechanism interpretation**: `|fwd_ret_5d|` is mechanically correlated with
   `vol_ratio` (high realized post-5d vol ⇒ at least one of the 5 daily moves
   was large ⇒ likely |cumulative ret| is large). Selecting on `vr ≥ 1.5` is
   essentially selecting on `|fwd_ret|` being large. The announcement adds **no**
   incremental signal beyond this conditioning — in fact it slightly attenuates
   the payoff (announcement noise may dampen the magnitude effect).

4. **A_mirror PASS confirms the artifact**: announce × vr<1.0 also yields
   positive payoff (+424bp) with sig_t_ex 5.63 — but this is **contraction**
   scenarios with positive straddle payoff. Mechanically explained because
   B_baseline_contract is also +400bp. The "payoff" is the universe baseline
   |fwd_ret| floor, not event-driven vol expansion alpha.

5. **The three-gate near-miss (sig_t_ex 1.95) is not a "narrow miss" worth
   re-running with tweaked thresholds** — it's diagnostic of the conditioning
   structure. Adjusting threshold (1.3 / 2.0 / etc.) will only further widen the
   gap between A_focus and B_baseline_expand because B is always denser.

## Sub-findings

- **Cross-proxy (Lesson #29) FAIL on fundamental**: |gap| top33 (1367bp) > bot33
  (813bp) — observable proxy coherent (surprise magnitude correlates with vol
  expansion). BUT frequency proxy INVERTED: freq_top33 (1114bp) > freq_bot33
  (994bp) — *frequent announcers produce LARGER vol expansion payoff*, opposite
  of the "info shock" hypothesis. Reading: frequent announcer = high-beta stock
  → larger absolute moves mechanically.

- **Concentration Gate PASS (mechanically)**: 10/10 quarters t>0 (1.00), 15/15
  ci_pos symbols (1.00). This is **artifact-consistent** — when payoff is
  universe-baseline-driven, every stock × every quarter shows the same pattern.
  Strong concentration PASS reinforces "this is not event alpha" diagnosis.

- **4-dim life-changing trivially PASS**: 137 trades/yr, +9.87% edge, sharpe 10.3,
  capital util 68%. These numbers are **mechanically inherited from universe
  baseline conditioning** (B_baseline_expand sharpe would be ~10× higher),
  NOT event-driven.

- **Stress @ 200bp PASS**: A_focus sig_t_ex 2.93 (stricter fee, the baseline
  shifts more so the gap narrows). Robust to fee level but still
  conditioning-driven.

## Lesson #33 candidate (NEW) — magnitude-as-outcome-equals-conditioning-trap

When the **outcome metric** (here `|fwd_ret_5d|`) is mathematically correlated
with the **trigger filter** (here `vol_ratio = vol_post_5d / vol_pre_30d`), the
A_focus three-gate evaluation must additionally check
**`signal_t_excess(A_focus) > signal_t_excess(B_baseline_with_same_filter)`**,
not just `> 0` vs raw universe pool.

The current Lesson #32 dogfood compares `A_focus vol_ratio` vs `B_baseline
all-universe vol_ratio` — but the trap is at the **post-conditioning payoff
level**, not the vol_ratio level. Concrete patch:

**Lesson #33 prescreen rule**: For paradigms where the trigger and outcome share
mechanical correlation (vol-ratio trigger × |return| outcome; rank trigger × top-N
rank outcome; momentum trigger × momentum outcome), the R-1 4-quadrant must add
a 5th cell `B_baseline_same_filter` and the verdict requires
`A_focus_sig_t_excess ≥ B_baseline_same_filter_sig_t_excess + delta` (delta ≥ 1.0).

This paradigm would have been pre-screened HALT at R-0 with this rule
(saving ~3 sec actual but diagnostic infrastructure cost).

## Family verdict update

KR equity DART entry-side family retire amendment (2026-05-19):
- 4 directional/mean-reversion graveyards (92+93+100+101): direction axis exhausted.
- **paradigm 102 (this)**: non-directional vol-magnitude axis — **also FAIL** at
  conditioning-artifact level. Different mechanism, same end state.
- **Remaining family-distinct paths**: external-event paradigms (non-DART), or
  paradigms that combine DART events with a **decorrelated outcome** (e.g.,
  cross-stock spillover, sector rotation triggered by but not measured on same
  ticker), or **non-announcement event types** (volume shock, foreign-buy
  ratio change). Vol-expansion magnitude on the announcing stock itself = retired.

## Output artifacts

- `backend/scripts/research/dart_supply_contract_vol_expansion_r1.py` (script)
- `backend/runs/research_track/dart_supply_contract_announce_kr_equity_vol_expansion_5d/`
  - `vol_expansion_events_cache.joblib` (1,987 events × 16 cols, ~330KB)
  - `r1_metrics.json` (full output)
- `backend/runs/research_track/graveyard__dart_supply_contract_announce_kr_equity_vol_expansion_5d.md`
  (this file)

## Background process hygiene

`ps -ef | grep python3.*research` post-run: 0 rows (local). Mint host: not used
(local DART cache reused). cloudflared tunnel: not invoked.

— end —
