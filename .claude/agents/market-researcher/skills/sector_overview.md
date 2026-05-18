# Skill: Sector Overview & Regime Assessment

> Parent agent: `market-researcher`
> Purpose: Stage 1 — macro 환경 평가 + regime 판단
> Tools: WebSearch

## Step 1.1: Macro Search Queries

**English (crypto 우선)**:
- "crypto market outlook 2026"
- "FOMC interest rate decision"
- "global macro economic news today"

**Korean (KR equities 우선)**:
- "비트코인 시장 전망"
- "연준 금리 결정"
- "코스피 시황"

**Maximum 3 macro queries**. Use the most relevant 2-3 based on input symbols (crypto-only → English 우선, KR-only → Korean 우선, mixed → 양쪽 각 1-2회).

## Step 1.2: Regime Grid

| Regime | macro tone | price direction | policy stance | sentiment |
|---|---|---|---|---|
| **bullish** | 긍정 | 상승 | 완화/유지 | risk-on |
| **bearish** | 부정 | 하락 | 긴축 | risk-off |
| **sideways** | 중립 | 횡보 | 무변 | 혼조 |
| **volatile** | 불확실 | 급변 | event-driven | 불안정 |

### Confidence scoring
- 4/4 indicator 일치 → confidence ≥ 0.8
- 3/4 일치 → 0.6 ~ 0.8
- 2/4 일치 → 0.4 ~ 0.6
- < 2/4 → regime = `volatile` 또는 `sideways`, confidence ≤ 0.4

## Step 1.3: Output Fields

Populate the following JSON fields in parent agent's output:
- `regime`: enum (bullish/bearish/sideways/volatile)
- `regime_confidence`: float [0.0, 1.0]
- `regime_rationale`: Korean 1-2 문장, 4 indicator 중 결정적 근거 명시

## Reference

- Anthropic 차용 패턴: `anthropics/financial-services/plugins/agent-plugins/market-researcher/skills/` (Apache-2.0)
- 절대 금지: paid/freemium source (Bloomberg/Refinitiv/FnGuide 등) — [[feedback_no_freemium_trial]]
- 절대 금지: 종목/가격 fabrication — [[feedback_no_stock_guess]]
