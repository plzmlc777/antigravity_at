# Skill: Domain 2 — Market Sentiment

> Parent agent: `signal-synthesizer`
> Purpose: Domain 2 — news sentiment + Fear&Greed + social buzz
> Tools: WebSearch

## Step 2.1: Search Queries

```
WebSearch: "<SYMBOL> sentiment analysis"
WebSearch: "<종목명> 투자 심리 전망"
```

**KR equities**: Korean queries 우선. Crypto: English + Korean.

**Quick mode**: 1 WebSearch / **Deep mode**: 2 WebSearch.

## Step 2.2: Sentiment Extraction

For each search result:
- **Overall news tone**: positive / negative / neutral
- **Fear & Greed equivalent**: extreme_fear / fear / neutral / greed / extreme_greed
- **Social buzz level**: low / medium / high
- **Institutional positioning**: accumulating / distributing / unclear

## Step 2.3: Domain Score

| Tone | Buzz | Score |
|---|---|---|
| positive + greed | high | +0.7 to +1.0 |
| positive + neutral | medium | +0.3 to +0.6 |
| neutral | any | -0.2 to +0.2 |
| negative + fear | low | -0.3 to -0.6 |
| negative + extreme_fear | high | **-0.7 to -1.0 OR +0.5 to +0.7 (contrarian!)** |

**Contrarian rule**: Extreme fear with high volume often = capitulation = reversal opportunity. Mark with `contrarian: true` flag and assign positive score.

## Step 2.4: Output JSON sub-block

```json
"sentiment": {
  "score": -0.4,
  "weight": 0.15,
  "details": {
    "news_tone": "negative",
    "fear_greed": "fear",
    "social_buzz": "low",
    "contrarian": false
  },
  "summary": "Korean 1-2 문장"
}
```

## Reference
- [[feedback_no_freemium_trial]] — paid sentiment API 금지
- [[feedback_no_stock_guess]] — 검색 결과 없으면 score=0 + data_quality 감소
