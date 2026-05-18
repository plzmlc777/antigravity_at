# Skill: Domain 5 — Temporal Context

> Parent agent: `signal-synthesizer`
> Purpose: Domain 5 — session/day-of-week + event proximity + meta-learner patterns
> Tools: Read (meta-learner findings)

## Step 5.1: Session Detection

Convert current UTC to KST:
- Asian session: 09:00 ~ 16:00 KST
- European session: 16:00 ~ 22:00 KST
- US session: 22:00 ~ 06:00 KST

**Crypto**: 24h market but session-based volume patterns exist.
**KR equities**: Korean market hours 09:00~15:30 KST only.

## Step 5.2: Day-of-Week

- Monday: gap risk from weekend news
- Tue-Thu: highest volume, trend continuation
- Friday: position reduction, low volume
- Weekend (crypto only): thin liquidity, manipulation risk

## Step 5.3: Event Proximity

Distance to known events:
- FOMC: ±1 day → high volatility expected
- Earnings (KR equities): ±2 days
- Crypto halving: progressive impact ±3 months
- Major contract expiry: ±1 day

**Risk-off proximity (≤3 days to high-impact event)**: reduce conviction.
**Post-event clarity (1-2 days after event)**: increased confidence.

## Step 5.4: Meta-Learner Temporal Patterns

```bash
# Read meta-learner temporal findings
cat /home/hcpark/antigravity/.claude/skills/at-strategy/references/meta_learnings.md 2>/dev/null
```

Examples of meta-learner findings:
- "D001: RSI 전략 아시아 시간대 승률 64% (vs 51% 평균)"
- "D012: 월요일 BTC 갭 fade 패턴 67% (last 12mo)"

Apply matching findings to current context.

## Step 5.5: Domain Score

| Temporal context | Score |
|---|---|
| Favorable session + favorable DoW + post-event + meta-pattern match | +0.7 to +1.0 |
| Favorable 2/3 + meta-match | +0.4 to +0.6 |
| Neutral context | -0.1 to +0.1 |
| Pre-event proximity (≤3d high impact) | -0.3 to -0.5 (reduce conviction) |
| Adverse session + DoW + no meta-match | -0.5 to -0.7 |

## Step 5.6: Output JSON sub-block

```json
"temporal": {
  "score": 0.5,
  "weight": 0.15,
  "details": {
    "session": "asian",
    "day_of_week": "monday",
    "meta_pattern": "RSI 전략 아시아 시간대 승률 우위 (meta-learner D001)"
  },
  "summary": "Korean 1-2 문장"
}
```

## Reference
- [[meta-strategy-multi-symbol]] — meta-learner 동적 패턴 발견 baseline
- [[feedback_no_stock_guess]] — temporal pattern은 meta-learner 출력 또는 실제 시간 인용만
