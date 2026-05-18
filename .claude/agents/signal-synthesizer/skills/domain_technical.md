# Skill: Domain 1 — Technical Indicators

> Parent agent: `signal-synthesizer`
> Purpose: Domain 1 — technical indicators from candle data
> Tools: Bash (curl + python analyze_candles.py), Read

## Step 1.1: Data Fetch

### Option A — Direct API
```bash
curl -s "<API_URL>/api/v1/live/session/<SESSION_ID>/candles?limit=200"
```

### Option B — analyze_candles.py wrapper
```bash
cd /home/hcpark/antigravity
python3 .claude/skills/at-live-signal/scripts/analyze_candles.py \
  --api-url <API_URL> --session-id <SESSION_ID> --json
```

## Step 1.2: Indicator Extraction

Extract the following:

| Indicator | Bullish signal | Bearish signal |
|---|---|---|
| **RSI** | <30 (oversold reversal) or >50 trending up | >70 (overbought) or <50 trending down |
| **EMA Cross** | short EMA crosses above long EMA (golden) | short EMA crosses below long EMA (death) |
| **MACD Histogram** | rising or positive divergence | falling or negative divergence |
| **Bollinger Band** | touch lower band + reversal | touch upper band + reversal |
| **Volume Trend** | rising on green candles | rising on red candles |
| **Support/Resistance** | bounce off support | reject at resistance |

## Step 1.3: Domain Score (-1.0 to +1.0)

Weighted average of 6 indicators (each ±1.0):
- All 6 bullish → +1.0
- 4-5 bullish → +0.5 to +0.8
- mixed (3:3) → ~0.0
- 4-5 bearish → -0.5 to -0.8
- All bearish → -1.0

## Step 1.4: Output JSON sub-block

```json
"technical": {
  "score": 0.7,
  "weight": 0.30,
  "details": {
    "rsi": {"value": 28, "signal": "oversold", "score": 0.8},
    "ema_cross": {"status": "bearish", "score": -0.3},
    "macd": {"histogram": "converging_bullish", "score": 0.6},
    "bollinger": {"position": "lower_band", "score": 0.7},
    "volume_trend": {"direction": "decreasing_selling", "score": 0.8}
  },
  "summary": "Korean 1-2 문장 — 결정적 indicator 인용"
}
```

## Reference
- [[feedback_no_stock_guess]] — 모든 indicator 값은 API 원본만 사용
- Anthropic 차용 패턴: skill bundle per signal domain
