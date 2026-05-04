# Research Track Gate Evaluation — ETCUSDT

- **Paradigm**: `funding_carry`
- **Spec**: `ETCUSDT_z2.5_lb30_mh15_full1y`
- **Evaluated**: 2026-05-04T11:37:28.990094+00:00
- **Verdict**: **❌ FAIL**

## Quantitative cutoffs (5 AND)

| Metric | Status | Threshold |
|---|---|---|
| alpha_pct | FAIL (73.4) | >= 150.0 |
| sharpe_ann | FAIL (0.69) | >= 2.0 |
| max_dd_pct | PASS (14.9) | <= 28.0 |
| win_rate_pct | PASS (57.7) | >= 50.0 |
| profit_factor | FAIL (1.53) | >= 2.0 |

## Robustness (4 AND)

| Check | Status | Threshold |
|---|---|---|
| perm_test | PASS (p=0.015) | p <= 0.05 |
| walk_forward | FAIL (4/6) | >= total-1 / total |
| vf_dependency | SKIP (missing) | <= 30% |
| n_trades | FAIL (26) | >= 30 |
| oos_days | FAIL (355d) | >= 365 |

## Failures

- alpha=73.4 < 150.0
- sharpe=0.69 < 2.0
- pf=1.53 < 2.0
- wf 4/6 < 5/6
- n_trades=26 < 30
- oos_days=355 < 365
