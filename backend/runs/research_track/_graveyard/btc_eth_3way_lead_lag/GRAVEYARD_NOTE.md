# btc_eth_3way_lead_lag — Graveyard Note (2026-05-06, 48th graveyard, 56th paradigm overall)

## 설계
Q3 #8 — cross_symbol_lead_lag (DOGE seeded, BTC-only) 의 3-way extension. BTC AND ETH 동시 강한 directional move + agreement → target alt catch-up direction trade. 가설: 3-way agreement는 macro-driven move 더 신뢰하므로 BTC-only보다 강한 signal.

Entry rule:
- |R_btc| > thresh AND |R_eth| > thresh AND sign(R_btc) == sign(R_eth)
- target lagged: |R_alt| < follow_ratio × avg(|R_btc|,|R_eth|) OR sign 다름
- side = sign(R_btc)

§3-J 회피 의도: BTC/ETH 둘 다 follow-leader 이므로 seeded fade joint 아님.
§3-H 회피 의도: AND structure는 paradigm 자체 (per §3-L wick_reversal binary AND essential discriminator).

## R-1 SOL sweep (108 specs)
**11/108 PASS** alpha+sharpe ≥ 0.

Top by sharpe:
| Spec | alpha | sharpe | trades |
|---|---|---|---|
| lb=6/lt=0.012/fr=0.7/h=6 | 44.52 | **0.98** | **30** | (§3-A rare risk) |
| lb=12/lt=0.008/fr=0.7/h=12 | 44.89 | 0.56 | 291 | (dense, picked for R-2) |
| lb=12/lt=0.008/fr=0.3/h=6 | 35.60 | 0.32 | 62 |

vs cross_symbol_lead_lag DOGE seeded (sharpe **1.83** with R-3 perm_p=0.005), 3-way is significantly weaker.

## R-2 multi-symbol (10종, lb=12 lt=0.008 fr=0.7 h=12)
- alpha pos: 10/10 (perfect)
- **sharpe pos: 3/10 (BELOW 4/10 fail-fast cutoff)**
- alpha mean: 29.82
- **sharpe mean: -0.68 NEGATIVE**
- trades_total: 3779

| Sym | alpha | sharpe |
|---|---|---|
| LINK | +38.22 | +0.07 |
| SOL | +44.89 | +0.56 |
| DOGE | +48.05 | +0.09 |
| AVAX | +39.51 | -0.55 |
| ETC | +26.26 | -1.06 |
| HBAR | +28.29 | -0.80 |
| AXS | +18.46 | -1.09 |
| COMP | +17.56 | -0.76 |
| UNI | +25.36 | -0.80 |
| LDO | +11.60 | -2.46 |

7/10 negative sharpe. Per fail-fast tree §3-E paradigm-level weak.

## R-3 SKIPPED — paradigm-level fail
sharpe pos < 4/10 cutoff. Continuing to perm test would only confirm weakness.

## Verdict — §3-H 4th confirmation: filter even on NEW signals can degrade
Pattern emerging:
1. premium_oi_correlation_regime (Q2 #3): premium signal + OI corr filter → graveyard
2. premium_oi_joint_filter (Q2 #13): premium + OI direction agreement → graveyard
3. oi_funding_corr_regime (Q3 #1): OI × funding regime → §3-D §3-J graveyard
4. wick_reversal_volume (Q3 #3): wick + volume z filter → §3-H 3rd confirm
5. **btc_eth_3way_lead_lag (this Q3 #8)**: BTC lead-lag + ETH agreement filter → §3-H 4th confirm

**Universal rule strengthened**: Even when both components are NEW (BTC and ETH both follow-leader, neither seeded as fade), AND-agreement structure narrows trade set without improving per-trade alpha quality. The 2-way (BTC alone, cross_symbol_lead_lag) captured most of the signal — 3-way agreement filters add no orthogonal info.

**§3-N 신규 antipattern**: Multi-source agreement (3-way leader confirmation) filtering on top of seeded paradigm structure → pure narrowing without alpha quality improvement. **Voting (joint_3signal_ensemble = 3-of-3 majority)는 marginal value 가능했지만, 단순 N-way AND agreement는 항상 약화**.

## Lesson — cross_symbol_lead_lag is local optimum
2-way BTC-only is the right formulation for cross-symbol info flow. Adding ETH agreement (§3-H AND) destroys signal quality. cross_symbol_lead_lag DOGE seeded (sharpe 1.83) is captured well by 2-way; 3-way doesn't help.

For cross-symbol paradigm extension, need ORTHOGONAL angle:
- Different leaders (large-cap dominant: BTC vs sector-specific: top-DEX-coin)
- Different timeframes (5m vs 1h cross-correlation)
- Cross-asset (crypto vs equity vs commodity macro proxies)
- Sector-rotation (DeFi vs Layer1 vs meme as 3 baskets)

But these are all higher-cost paradigms.

56th paradigm graveyard. Q3 큐 8/8 graveyard, 1 NEW dim POSITIVE 3σ (#2) + 1 SOL 4σ (#4). Cross-symbol family confirmed: 2-way local optimum.

## Q3 status update (8/8 graveyard)
| # | Paradigm | Outcome | Lesson |
|---|---|---|---|
| 1 | oi_funding_corr_regime | §3-D §3-J | two-seeded fade joint |
| 2 | wick_reversal | POSITIVE 3σ | NEW dim shape proven |
| 3 | wick_reversal_volume | §3-H 3rd | filter monotonic degrade |
| 4 | wick_reversal_multibar | POSITIVE SOL 4.49σ | §3-C single-symbol |
| 5 | range_expansion | §3-K | shape > magnitude |
| 6 | wick_prior_joint | §3-L | binary AND ≠ filter |
| 7 | vwap_deviation | §3-D §3-M | reference-price = trend |
| 8 | btc_eth_3way_lead_lag | §3-H §3-N 4th | N-way AND degrades |
