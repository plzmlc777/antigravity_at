# Skill: Domain 4 — Volume & Liquidity Analysis

> Parent agent: `signal-synthesizer`
> Purpose: Domain 4 — volume profile + selling/buying exhaustion + abnormal spikes
> Tools: (uses candle data already fetched in Domain 1, no extra API call)

## Step 4.1: Candle-Derived Metrics

From the same candle data fetched in Domain 1:

### Volume Confirmation
- Rising volume + rising price → trend strength (bullish confirmation)
- Rising volume + falling price → selling pressure (bearish confirmation)
- Falling volume + rising price → weak rally (potential reversal)
- Falling volume + falling price → selling exhaustion (potential bottom)

### Selling/Buying Volume Ratio
Estimate from candle body vs wick:
- Green candle, body > 70% of range → strong buying
- Red candle, body > 70% of range → strong selling
- Long upper wick → rejection at top (sellers stepped in)
- Long lower wick → rejection at bottom (buyers stepped in)

### Abnormal Volume Spike
- Volume > 2σ above recent 20-bar mean → notable spike
- Spike on green candle + breakout → bullish
- Spike on red candle + breakdown → bearish

## Step 4.2: Domain Score

| Volume signal | Score |
|---|---|
| Selling exhaustion + rejection wick (low) | +0.5 to +0.8 |
| Buying confirmation on breakout | +0.7 to +1.0 |
| Weak rally (low volume) | -0.2 to -0.4 |
| Distribution pattern (selling on rallies) | -0.5 to -0.7 |
| Selling capitulation (high vol red breakdown) | -0.7 to -1.0 OR +0.5 (contrarian capitulation) |

## Step 4.3: Output JSON sub-block

```json
"volume_liquidity": {
  "score": 0.6,
  "weight": 0.20,
  "details": {
    "volume_confirmation": true,
    "selling_exhaustion": true,
    "abnormal_spike": false
  },
  "summary": "Korean 1-2 문장"
}
```

## Reference
- Domain 1 candle data 재사용 — 별도 API 호출 0
- [[feedback_no_stock_guess]] — 볼륨 수치는 candle data 원본 산출만 사용
