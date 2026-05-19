# R-1 Spec — paradigm 95 `cross_asset_volume_share_high_alt_long_1d`

## Dispatch
- **Mode**: ad_hoc_user_explicit_mint_full_data
- **Date**: 2026-05-19 KST
- **Phase**: R-1 PoC only (R-2/R-3/R-4 미진행 — paradigm-architect spec halt)
- **Trigger**: User explicit dispatch following paradigm 94 R-1 BROAD_FALSIFIED_DIRECTION_INVERTED (commit fc61755f)

## Hypothesis (single sentence)
BTC daily USD-volume share (= `BTC_vol_usd / sum(14-sym vol_usd)`) 30d rolling z-score **>= +1.5** (BTC volume share peak = BTC dominance momentum / bull regime confirmation) → LONG 13 alts at next-day open, hold +1d (24h), exit at close.

## Re-framing as independent paradigm (Lesson #8 mirror antipattern)
paradigm 94 R-1 Mint full-data rerun produced strong mirror evidence (sigex +6.86, gross +96.97bp, ci_lower +59.77bp on n=702 trades), but Lesson #8 + paradigm 70 mirror antipattern catalog mandates that mirror metrics **do not auto-promote** — they require an independent paradigm with its own R-1 batch, separate codepath, separate candidate pool, separate name + directory. paradigm 95 fulfills this requirement.

## Hypothesis mechanism
- BTC volume share 30d z peak (z ≥ +1.5) = BTC dominance momentum / risk-on regime confirmation
- alts experience +1d catch-up rally / bull rotation cascade
- 시간 척도: 1d trigger → 1d hold

## Cross-proxy track (Lesson #29)
- obs proxy = volume share fraction z (transform)
- fund proxy = BTC absolute USD-volume 30d z (raw flow)
- Both must independently three-gate PASS

## Symmetric Negative Test (Lesson #19)
- focus: share_z >= +1.5 LONG (BTC dominance peak)
- mirror: share_z <= -1.5 LONG (= paradigm 94 focus, already BROAD_FALSIFIED in paradigm 94 R-1)

## Lesson #20 narrow-scope 4-cond
- a. 4-gate (sigex>=2 AND ci_lo>0 AND perm_p<=0.10 AND 50bp stress sigex>=2)
- b. Held-out 50/50 replication by trigger date — both halves three-gate PASS independently
- c. Bonferroni-adjusted min per-sym p × n_sym <= 0.10
- d. Hold sweep 1d/2d/3d — all 3 nets > 0 AND >= 2/3 three-gate PASS

## Life-changing 4-dim (memory `feedback_life_changing_strategy_criterion`)
- trades/yr >= 12 (sparse trigger antipattern)
- per-trade edge >= +2.0% (50bp fee stress)
- capital utilization >= 30% (trigger_day_frac × sym_alloc_frac)
- annualized sharpe >= 1.5

## Universe
- BTC + 13 alts (paradigm 69 validated): ADA AVAX BCH BNB DOGE ETH FIL LINK LTC NEAR SOL WIF XRP
- 12 EXTRA boost syms (AXS/HBAR/LDO/COMP/UNI/PYTH/TON/ETC/ICP/JUP/WLD/1000LUNC) Mint joblib cache 부재 → omitted
- Mint joblib OHLCV cache 2.4yr (2024-01-19 ~ 2026-05-12, 845 common days, 816 share_z usable)

## Family-distinct check
- 5m microstructure single-domain: different (daily)
- KR equity post-earnings: different (crypto perp)
- geometric path metrics: different (volume share, not path)
- funding/OI joint squeeze: different (volume only)
- BTC/ETH 5m corr breakdown: different (daily, no corr)
- paradigm 94 LOW-share compression: different direction class (HIGH vs LOW); same statistic family but distinct mechanism + paradigm 94 R-1 was already BROAD_FALSIFIED_DIRECTION_INVERTED
- Verdict: `family_distinct_inverted_direction_independent`

## Output
- `r1_metrics.json` — full metrics
- `r1_spec.md` — this file
- `r1_summary.md` — verdict + executive summary
- `r1_script.py` — foreground synchronous

## Expected verdict candidates
- PASS_R1
- FAIL_THREE_GATE
- BROAD_FALSIFIED
- BROAD_FALSIFIED_FEE_FLOOR
- CONCENTRATED_R1_PASS (Lesson #16 + #20 4-cond not all pass)
- NARROW_SCOPE_CANDIDATE (Lesson #20 4-cond ALL PASS + Concentration FAIL marginal)
- NARROW_SCOPE_LIFE_CHANGING_FAIL (narrow-scope statistical evidence + life-changing 4-dim FAIL)
- SINGLE_PROXY_TRAP_OBS_ONLY / SINGLE_PROXY_TRAP_REDUNDANT
