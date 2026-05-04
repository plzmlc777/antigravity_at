# Research Track Gate Evaluation — HBARUSDT

- **Paradigm**: `funding_carry`
- **Spec**: `HBARUSDT_z2.5_lb30_mh15_full1y`
- **Evaluated**: 2026-05-04T11:37:28.896936+00:00
- **Verdict**: **❌ FAIL**

## Quantitative cutoffs (5 AND)

| Metric | Status | Threshold |
|---|---|---|
| alpha_pct | FAIL (97.2) | >= 150.0 |
| sharpe_ann | FAIL (1.50) | >= 2.0 |
| max_dd_pct | PASS (8.2) | <= 28.0 |
| win_rate_pct | PASS (68.4) | >= 50.0 |
| profit_factor | PASS (2.58) | >= 2.0 |

## Robustness (4 AND)

| Check | Status | Threshold |
|---|---|---|
| perm_test | PASS (p=0.000) | p <= 0.05 |
| walk_forward | PASS (5/6) | >= total-1 / total |
| vf_dependency | SKIP (missing) | <= 30% |
| n_trades | FAIL (19) | >= 30 |
| oos_days | FAIL (355d) | >= 365 |

## Failures

- alpha=97.2 < 150.0
- sharpe=1.50 < 2.0
- n_trades=19 < 30
- oos_days=355 < 365
