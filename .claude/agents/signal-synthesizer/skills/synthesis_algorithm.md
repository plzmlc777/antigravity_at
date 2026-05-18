# Skill: Synthesis Algorithm

> Parent agent: `signal-synthesizer`
> Purpose: Fuse 5 domain scores into unified signal + confidence
> Tools: (synthesis only, no external calls)

## Step S.1: Domain Score Normalization

Each domain returns `score ∈ [-1.0, +1.0]`:
- -1.0 = strongly bearish
-  0.0 = neutral
- +1.0 = strongly bullish

## Step S.2: Weighted Sum

| Domain | Weight | Rationale |
|---|---|---|
| Technical | 0.30 | Quantitative, objective |
| Volume/Liquidity | 0.20 | Confirms or denies price action |
| Cross-Market | 0.20 | Macro context |
| Sentiment | 0.15 | Leading indicator but noisy |
| Temporal | 0.15 | Statistical edge from meta-learner |

```
raw_score = (technical × 0.30)
          + (volume × 0.20)
          + (cross_market × 0.20)
          + (sentiment × 0.15)
          + (temporal × 0.15)
```

## Step S.3: Alignment Factor

Count domains agreeing with raw_score sign:
- All 5 same direction → alignment_factor = 1.0
- 4/5 same direction → 0.85
- 3/5 same direction → 0.65
- Mixed/conflicting (2/5 or worse) → 0.4

## Step S.4: Data Quality

- All 5 domains have valid data → data_quality = 1.0
- 1 domain missing → 0.9
- 2+ domains missing → 0.7

## Step S.5: Confidence

```
confidence = alignment_factor × data_quality
```

Range: 0.28 (worst) to 1.0 (best).

## Step S.6: Signal Generation

| Condition | Signal |
|---|---|
| raw_score > +0.3 AND confidence > 0.5 | BUY |
| raw_score < -0.3 AND confidence > 0.5 | SELL |
| Otherwise | HOLD (no action) |

## Step S.7: Signal Strength

- `strong`: conviction > 0.7 AND confidence > 0.7
- `moderate`: conviction > 0.5 AND confidence > 0.5
- `weak`: conviction > 0.3 AND confidence > 0.5
- `none`: below thresholds

## Step S.8: Sizing Suggestion

Position size scales with conviction:
- conviction 0.5 → 50% of normal size
- conviction 0.7 → 70% of normal size
- conviction 0.9 → 90% of normal size

## Step S.9: Synthesis Rationale (CRITICAL field)

Generate Korean 2-3 문장 explaining:
- Which domains aligned (and which dissented)
- Why the conviction level is what it is
- Decisive single domain (if any)
- Caveats / risk factors

**Most important field** — caller (trade-executor / risk-manager) reads this to understand the "why".

## Reference
- Anthropic 차용 패턴: agent.yaml orchestrator with handoff_request — fusion 패턴 응용
- [[feedback_no_stock_guess]] — rationale은 도메인 데이터 인용만 (의견 추가 가능하나 fact-base 명시)
