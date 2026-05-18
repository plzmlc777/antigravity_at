# Skill: Domain 3 — Cross-Market Correlation

> Parent agent: `signal-synthesizer`
> Purpose: Domain 3 — macro context + relative strength + correlation breakdown
> Tools: Bash (other session candle fetch), WebSearch

## Step 3.1: Multi-Asset Data

### Option A — Sibling session monitor
```bash
curl -s "<API_URL>/api/v1/live/monitor/sessions"
```
Extract other active session prices for relative strength.

### Option B — WebSearch macro indicators
```
WebSearch: "BTC ETH price today" (crypto relative strength)
WebSearch: "USD DXY today" (dollar strength)
WebSearch: "US 10-year treasury yield today" (rate environment)
WebSearch: "VIX volatility index today" (risk environment)
```

**Quick mode**: skip macro WebSearch (Option A only).
**Deep mode**: A + B (max 2 WebSearch).

## Step 3.2: Correlation Assessment

For target symbol:
- **Relative strength**: target outperforming peers? (+) or underperforming? (-)
- **Correlation breakdown**: target diverging from BTC/SPX/macro?
- **Divergence type**:
  - Positive: target rising while peers falling → **strength signal**
  - Negative: target falling while peers rising → **weakness signal**

## Step 3.3: Macro Lens

| Macro | Bullish for crypto | Bearish for crypto |
|---|---|---|
| DXY | falling | rising |
| 10Y yield | falling | rising |
| VIX | falling | rising spike |
| Risk-on equities | rising | falling |

For KR equities, reverse some (e.g., KRW strength vs USD).

## Step 3.4: Domain Score

- Asset positive divergence + favorable macro → +0.5 to +1.0
- Asset positive divergence + neutral macro → +0.3 to +0.6
- Asset moving with peers (no divergence) → ±0.2 (noise)
- Asset negative divergence + unfavorable macro → -0.5 to -1.0

## Step 3.5: Output JSON sub-block

```json
"cross_market": {
  "score": 0.3,
  "weight": 0.20,
  "details": {
    "btc_eth_ratio": "ETH relative strength",
    "dxy": "weakening",
    "correlation": "asset diverging positively"
  },
  "summary": "Korean 1-2 문장"
}
```

## Reference
- [[feedback_no_stock_guess]] — 다른 자산 가격도 API/검색 원본만 인용
