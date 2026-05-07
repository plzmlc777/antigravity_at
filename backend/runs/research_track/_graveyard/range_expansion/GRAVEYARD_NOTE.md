# range_expansion — Graveyard Note (2026-05-06, 45th graveyard, 53rd paradigm overall)

## 설계
Q3 #5 — wick rabbit hole 벗어나 truly new dimension 시도. Single-bar 5m HIGH-LOW range z-score를 volatility shock event 신호로 사용.
- range = high - low
- log_range = log(range)
- range_z = (log_range - rolling288_mean) / rolling288_std
- entry: range_z > entry_z (vol shock) AND prior_ret > +/- pm threshold → mean-reversion direction

vs vol_regime_breakout (graveyard, close-to-close std rolling): single-bar HL range vs rolling C2C std — distinct mechanism.
vs wick_reversal (Q3 #2 POSITIVE 3σ): MAGNITUDE vs SHAPE.

## R-1 SOL sweep (36 specs)
**6/36 PASS** alpha+sharpe ≥ 0, all with pm=0.03 only:
| Spec | alpha | sharpe | trades | mdd |
|---|---|---|---|---|
| ez=2.5/pm=0.03/h=24 | +41.68 | +0.38 | 103 | 30.5 |
| ez=2.5/pm=0.03/h=12 | +34.34 | +0.21 | 105 | 31.5 |
| ez=2.5/pm=0.03/h=6 | +34.42 | +0.21 | 116 | 32.3 |
| ez=3.0/pm=0.03/h=24 | +31.62 | +0.15 | 72 | 32.6 |

vs Q3 #2 wick_reversal best SOL alpha 59.60/sharpe **1.51**/mdd 10 — range_expansion is **structurally weaker**:
- alpha 30-40% lower
- sharpe 4-5x lower (0.38 vs 1.51)
- MDD 3x higher (30 vs 10)

## R-2 multi-symbol (10종, ez=2.5 pm=0.03 h=24)
- alpha pos: 8/10 (vs Q3 #2 wick 10/10)
- sharpe pos: 8/10
- alpha mean: 34.33 (Q3 #2 wick 58.36)
- sharpe mean: 0.323 (Q3 #2 wick 0.595)
- **MDD catastrophic 50-77%** (Q3 #2 wick mdd 9-44%)

| Symbol | alpha | sharpe | mdd | trades |
|---|---|---|---|---|
| HBAR | +66.76 | +0.58 | **55.2** | 107 |
| AXS | -9.65 | -0.46 | **73.6** | 193 |
| COMP | +60.79 | +0.63 | **57.3** | 125 |
| LINK | +38.30 | +0.46 | **60.4** | 112 |
| UNI | -16.65 | -0.04 | **75.7** | 196 |
| ETC | +39.28 | +0.23 | **53.7** | 103 |
| LDO | +20.79 | +0.43 | **77.3** | 198 |
| AVAX | +22.57 | +0.33 | 70.1 | 123 |
| SOL | +41.68 | +0.38 | 30.5 | 103 |
| DOGE | +79.43 | +0.69 | 64.1 | 138 |

**MDD 70%+ on 4 symbols** — paradigm-level structural failure. holding through such drawdowns is unviable.

## R-3 perm test ABORTED — perm method broken
SOL R-3 produced impossible result: random_alpha_std = 0.00, sigma 8850. Investigation: shuffle high/low + body clipping (max(shuffled_high, body_top), min(shuffled_low, body_bot)) caused EVERY iteration to produce identical alpha because:
- body_top = max(open, close) is fixed per bar
- shuffled high < body_top → clipped to body_top
- range becomes |close - open| (body size, fixed) for most bars
- All 200 shuffles yield same range distribution → identical alpha 32.83

The perm test method (which works for wick_reversal) is degenerate for range_expansion because range is dominated by body size, not wick. Need different perm method (e.g., shuffle range_z column directly), but given paradigm-level weakness (sharpe 0.38, MDD 77%), R-3 not worth fixing.

## Verdict — paradigm-level structural failure
1. **R-2 MDD catastrophic** (50-77% on 4/10 syms) — not a usable signal even if alpha positive
2. **alpha/sharpe systemically weaker** than wick_reversal (~50%/25% relative)
3. R-3 perm method degenerate, but paradigm fails before perm test matters

## Lesson — intra-bar MAGNITUDE alone doesn't carry directional signal
Range_expansion captures pure VOLATILITY MAGNITUDE without directional info. Direction comes entirely from prior_ret. Q3 #2 wick_reversal worked because intra-bar SHAPE (asymmetric wick) added directional component. Pure magnitude shock + prior direction logic is too weak to overcome noise — MDD wipes out alpha.

**Pattern**: Intra-bar info dimensions split into MAGNITUDE (range) and SHAPE (wick asymmetry). Only SHAPE carries reliable directional info. MAGNITUDE alone needs additional directional source (e.g., asymmetric volume, premium decoupling) to be tradable.

**Future direction (intra-bar dimension)**:
- ✗ range_expansion: pure magnitude, no direction info → graveyard
- ✓ wick_reversal: shape asymmetry → POSITIVE 3σ
- ✓ wick_reversal_multibar: shape + sequence → SOL 4σ POSITIVE single-symbol
- ? range × wick joint: magnitude + shape composite → potentially complementary
- ? range × volume × prior_ret JOINT: magnitude + flow + direction triple → high §3-H risk

53rd paradigm graveyard. Q3 #5. Confirms intra-bar SHAPE > MAGNITUDE for directional info extraction.
