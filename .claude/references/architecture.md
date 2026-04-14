# Architecture Overview

> 코드 구조 파악 시 참조. CLAUDE.md에서 분리된 상세 아키텍처 문서.

## System Architecture

```
Frontend (React/Vite, port 5173)
    ↕ HTTP/REST + WebSocket
Backend (FastAPI, port 8001)
    ↕ SQLAlchemy ORM
Database (PostgreSQL)
    ↕ Adapter Pattern
Kiwoom API / Binance API
```

## Backend Patterns

### Adapter Pattern (Exchange Integration)
- `ExchangeInterface` → `KiwoomRealAdapter` / `KiwoomMockAdapter`
- `get_exchange_adapter()`: `TRADING_MODE` env var로 선택

### Strategy Pattern
- `BaseStrategy` → `initialize()` + `on_data()` lifecycle
- `IContext`: buy/sell 추상화 (BacktestContext / LiveContext)
- `StrategyRegistry`: 이름으로 동적 로딩

### Manager Pattern (Singletons)
- `LiveManager` — 라이브 세션 관리, DB에서 복원
- `KiwoomTokenManager` — 토큰 갱신
- `AccountCache` — 계정 캐싱

### Live Trading Data Flow
```
Kiwoom WebSocket → LiveManager._on_tick()
→ CandleRealAggregator (1m/5m/1h)
→ Strategy.on_data(ohlcv)
→ LiveContext.buy()/sell()
→ LiveTradeExecution (DB logging)
```

## Frontend Architecture

### State: AuthContext, MarketDataContext, React Query v5
### Routes: / (Dashboard), /manual, /auto, /strategies, /settings, /admin
### API: api/client.js (Axios), Vite proxy /api → :8001

## Key DB Tables
- `live_bot_sessions` — 트레이딩 세션
- `live_trade_executions` — 체결 기록
- `ohlcv` — 캔들 데이터 (symbol, timestamp, timeframe unique)
- `strategy_configs` — 전략 설정 (JSON)
- `exchange_accounts` — 암호화된 계정 정보
