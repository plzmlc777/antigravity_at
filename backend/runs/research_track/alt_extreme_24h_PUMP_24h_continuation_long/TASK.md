# paradigm 158 — alt_extreme_24h_PUMP_24h_continuation_long

## Mechanism
Alt 24h extreme PUMP (rolling 24h return ≥ per-symbol p90 threshold)
→ 24h hold LONG continuation (FOMO momentum follow).

Direct test of paradigm 117 R-3 caveat 1 — mechanism CLASS asymmetric
finding (only capitulation bounce confirmed, not euphoria correction).
Now testing PUMP × continuation at 24h scale (paradigm 117 only measured
B_same_sign PUMP × SHORT at 4h scale sigex +0.28 sub-fee).

## Reframe vs paradigm 117 (4-dim strict audit — Lesson #62)
| Dimension | paradigm 117 | paradigm 158 | Strict |
|---|---|---|---|
| Statistic class | rolling 24h cum log_ret ≤ −15% DOWN | rolling 24h cum return ≥ per-sym p90 UP | partial (same statistic, opposite direction) |
| Universe | 28 alts | 14 alts (12-col cache subset) | partial |
| Entry-side class | extreme DRAWDOWN cross-down event | extreme PUMP cross-up event | STRICT (direction class opposite) |
| Mechanism alpha | capitulation MR | FOMO continuation | STRICT (class opposite) |
| Hold | 24h | 24h | identical |

Strict count: 2/5 (entry-side direction + mechanism alpha) → Lesson #62 ≥2 boundary PASS

## Substrate
- 4h klines 12-col joblib cache (영구 자산 14 syms × 2.25yr ~4920 bars)
- `backend/runs/ohlcv_cache_12col/{SYM}_4h.joblib` (14 syms verified)
- Rolling 24h return computed from 6 × 4h bars

## R-1 protocol
- Per-symbol p90 threshold (avoids cross-asset broadcast — Lesson #67 ESCAPE)
- 4-quadrant Symmetric Negative Test (Lesson #19):
  - A focus: 24h PUMP ≥ p90 × LONG (primary)
  - A mirror: 24h PUMP ≥ p90 × SHORT
  - B same-sign: 24h DUMP ≤ p10 × SHORT
  - B mirror: 24h DUMP ≤ p10 × LONG (paradigm 117 A_focus reproduction)
- Debounce 24h between consecutive triggers per sym
- Hold sweep 12h / 24h primary / 48h
- Threshold sweep p85 / p90 primary / p95
- Fee 16bp (24h hold round-trip)

## Gates
- 3-gate: signal_t_excess ≥ 2.0 + ci_lower > 0 + perm_p ≤ 0.10
- Concentration: q_pos ≥ 0.5 + syms_ci_pos ≥ 0.30 + n_syms ≥ 3
- Life-changing 4-dim: trades/yr ≥ 12 + edge ≥ 2%/trade + util ≥ 30% + sharpe ≥ 1.5

## Memory policy
- continuous-parallel campaign (no pause)
- R-1 only (R-2 hard-block)
- Lesson #8/#42 candidate verify
