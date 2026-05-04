# Research Track Gate Evaluation — COMPUSDT

- **Paradigm**: `funding_carry`
- **Spec**: `COMPUSDT_z2.5_lb30_mh15_full1y`
- **Evaluated**: 2026-05-04T11:37:28.959786+00:00
- **Verdict**: **❌ FAIL**

## Quantitative cutoffs (5 AND)

| Metric | Status | Threshold |
|---|---|---|
| alpha_pct | FAIL (92.2) | >= 150.0 |
| sharpe_ann | FAIL (1.19) | >= 2.0 |
| max_dd_pct | PASS (10.3) | <= 28.0 |
| win_rate_pct | PASS (51.9) | >= 50.0 |
| profit_factor | PASS (2.00) | >= 2.0 |

## Robustness (4 AND)

| Check | Status | Threshold |
|---|---|---|
| perm_test | PASS (p=0.000) | p <= 0.05 |
| walk_forward | PASS (5/6) | >= total-1 / total |
| vf_dependency | SKIP (missing) | <= 30% |
| n_trades | FAIL (27) | >= 30 |
| oos_days | FAIL (355d) | >= 365 |

## Failures

- alpha=92.2 < 150.0
- sharpe=1.19 < 2.0
- n_trades=27 < 30
- oos_days=355 < 365
