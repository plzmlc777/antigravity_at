# Skill: News Synthesis & Event Risk

> Parent agent: `market-researcher`
> Purpose: Stage 2 — symbol-specific news + upcoming event risk
> Tools: WebFetch (Naver JSON 1순위), WebSearch (폴백), Read (cached results)

## Step 2.1: Source Priority Rules

### KR stocks (6-digit code or 종목명):
**1순위 — Naver JSON API via WebFetch** (per [[feedback_kr_market_naver_priority]]):
- 기사: `WebFetch("https://m.stock.naver.com/api/news/stock/{code}", "최근 7일 기사 제목+요약+날짜 추출")`
- 토론방: `WebFetch("https://stock.naver.com/api/community/discussion/posts/by-item?itemId={code}", "최근 토론 sentiment 추출")`
- 메타: `WebFetch("https://stock.naver.com/api/stock/{code}/integration", "종목 메타 정보 추출")`

**2순위 — WebSearch Korean queries** (Naver JSON empty 또는 error 시):
- `WebSearch: "{종목명} 주가 뉴스 전망"`
- `WebSearch: "{종목명} 실적 분석"`

### Crypto (USDT-margin perp):
- WebSearch only (Naver crypto coverage 한계)
- English + Korean 양방향 (각 1회씩)

## Step 2.2: Per-Symbol Search Queries

For each symbol in input:
```
# Crypto
WebSearch: "{SYMBOL} {coin name} 뉴스 전망"
WebSearch: "{coin name} price analysis news"

# KR stocks (Naver JSON exhausted 후만)
WebSearch: "[종목명] 주가 뉴스 전망"
WebSearch: "[종목명] 실적 분석"
```

**Constraint**: 최근 7일 (last 7 days) only. Stale news = discarded.

## Step 2.3: Event Risk Identification

Identify upcoming events that could impact each symbol:
- **Central bank**: FOMC, ECB, BOK 결정
- **Earnings**: 추적 KR stock 분기 실적 발표일
- **Regulatory**: crypto 규제 / 무역 정책
- **Geopolitical**: 분쟁 / 제재 / 선거
- **Technical (crypto)**: halving / upgrade / fork

For each event:
- `event`: Korean 명칭
- `date`: ISO `YYYY-MM-DD`
- `days_until`: integer (negative = past, 무시)
- `impact_level`: high / medium / low
- `expected_impact`: Korean 1-2 문장

**3일 이내 high-impact**: 별도 강조 (output `recommendations[]`에 alert).

## Step 2.4: Output Fields

- `news_articles[]`: array of {title, source, date, relevance, summary, symbols_affected, impact}
- `event_risks[]`: array of {event, date, days_until, impact_level, expected_impact}

## Reference

- Naver JSON 1순위 [[feedback_kr_market_naver_priority]]
- No paid sources [[feedback_no_freemium_trial]]
- No fabrication [[feedback_no_stock_guess]] — 모든 article 실제 검색 결과만 인용
