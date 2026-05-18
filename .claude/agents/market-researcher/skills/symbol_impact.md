# Skill: Symbol Impact Assessment

> Parent agent: `market-researcher`
> Purpose: Stage 3 — per-symbol impact + confidence + trading implications
> Tools: (synthesis only, no external calls)

## Step 3.1: Impact Taxonomy

| Impact | 정의 |
|---|---|
| **positive** | News/conditions favorable for the trading strategy |
| **negative** | News/conditions unfavorable, increased risk |
| **neutral** | No significant impact expected |
| **uncertain** | Conflicting signals, need to monitor closely |

## Step 3.2: Confidence Scoring

| Confidence | 근거 |
|---|---|
| 0.8 ~ 1.0 | regime + 3+ news article + event_risk 모두 동방향 |
| 0.6 ~ 0.8 | regime + 1-2 news article 동방향, event_risk 무관 |
| 0.4 ~ 0.6 | 신호 혼재, 단일 강력 source |
| 0.0 ~ 0.4 | uncertain — 추가 모니터링 필요 |

## Step 3.3: Per-Symbol Rationale

Korean 1-2 문장. 다음 요소 포함:
- 결정적 news article 또는 event_risk 인용
- regime context와의 정합성
- 단기 (1-3일) vs 중기 (1-2주) 전망 명시

## Step 3.4: Trading Implications

`trading_implications.overall`: portfolio-level Korean 1-2 문장.
`trading_implications.specific[]`: per-symbol Korean 권고 (포지션 조정 / 진입 / 청산).

**Tone rule**: 권고 (recommend) 만 — 명령(order) 금지. Final decision = risk-manager + user.

## Step 3.5: Output Fields

- `symbol_impacts.{SYMBOL}`: {impact, confidence, rationale}
- `trading_implications`: {overall, specific[]}
- `recommendations[]`: empty unless 3일 이내 high-impact event detected (그 경우 Korean alert string)

## Reference

- Decision authority: risk-manager VETO + user override
- No guarantee phrasing — "권고" / "전망" / "가능성"만 허용
- No fabrication [[feedback_no_stock_guess]]
