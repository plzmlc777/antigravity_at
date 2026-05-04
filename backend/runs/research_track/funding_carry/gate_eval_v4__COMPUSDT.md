# Research Track Gate Evaluation — COMPUSDT

- **Paradigm**: `funding_carry`
- **Spec**: `COMPUSDT_funding_carry_v4`
- **Evaluated**: 2026-05-04T11:47:03.549285+00:00
- **Verdict**: **❌ FAIL**

## Quantitative cutoffs (5 AND)

| Metric | Status | Threshold |
|---|---|---|
| alpha_pct | FAIL (118.4) | >= 150.0 |
| sharpe_ann | FAIL (1.67) | >= 2.0 |
| max_dd_pct | PASS (5.5) | <= 28.0 |
| win_rate_pct | PASS (53.6) | >= 50.0 |
| profit_factor | PASS (2.75) | >= 2.0 |

## Robustness (4 AND)

| Check | Status | Threshold |
|---|---|---|
| perm_test | PASS (p=0.000) | p <= 0.05 |
| walk_forward | PASS (5/6) | >= total-1 / total |
| vf_dependency | SKIP (missing) | <= 30% |
| n_trades | FAIL (28) | >= 30 |
| oos_days | FAIL (355d) | >= 365 |

## Failures

- alpha=118.4 < 150.0
- sharpe=1.67 < 2.0
- n_trades=28 < 30
- oos_days=355 < 365
