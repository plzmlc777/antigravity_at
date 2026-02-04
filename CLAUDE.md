# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Antigravity Auto Trading System - A comprehensive automated trading platform for the Korean stock market, integrating with the Kiwoom Securities API. The system supports manual trading, simple automated bots, advanced strategy backtesting/optimization, and live trading with real-time data feeds.

**Current Version**: v0.9.9.57

## Common Commands

### Process Management (PM2)
All commands should be run from the `auto_trading/` directory:

```bash
# Start both backend and frontend
./deploy_with_pm2.sh

# PM2 management (using local tools)
npm run status      # List all processes
npm run logs        # View logs
npm run monit       # Monitor processes
npm run restart     # Restart all
npm run stop        # Stop all
npm run delete      # Delete all processes

# WSL 환경 (Git Bash 등 Windows에서 실행 시)
wsl -e bash -c "cd /home/hcpark/antigravity && pm2 status"
wsl -e bash -c "cd /home/hcpark/antigravity && pm2 logs"
wsl -e bash -c "cd /home/hcpark/antigravity && pm2 restart all"
wsl -e bash -c "cd /home/hcpark/antigravity && pm2 stop all"
wsl -e bash -c "cd /home/hcpark/antigravity && ./deploy_with_pm2.sh"  # Full restart
```

### Backend Development
```bash
cd backend

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend directly (without PM2)
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Database migrations (manual scripts in backend/)
python migrate_*.py
```

### Frontend Development
```bash
cd frontend

# Install dependencies
npm install

# Run dev server (without PM2)
npm run dev         # Starts on port 5173

# Build for production
npm run build

# Lint
npm run lint
```

### Database Access
```bash
# PostgreSQL connection details are in .env files
# Backend: auto_trading/backend/.env
# Root: auto_trading/.env

# Direct PostgreSQL access
psql -h localhost -U [POSTGRES_USER] -d [POSTGRES_DB]
```

## Architecture Overview

### System Architecture

The system follows a **three-tier architecture** with clear separation of concerns:

```
Frontend (React/Vite)
    ↕ HTTP/REST + WebSocket
Backend (FastAPI)
    ↕ SQLAlchemy ORM
Database (PostgreSQL)
    ↕ Adapter Pattern
Kiwoom API (Korean Stock Exchange)
```

### Backend Architecture Patterns

#### 1. Adapter Pattern (Exchange Integration)
- **Interface**: `ExchangeInterface` - Abstract base class for exchange connectors
- **Implementations**:
  - `KiwoomRealAdapter` - Real trading with actual API calls
  - `KiwoomMockAdapter` - Simulation mode for testing without real money
  - `KiwoomBaseAdapter` - Shared token management and caching
- **Dependency Injection**: `get_exchange_adapter()` in endpoints selects adapter based on `TRADING_MODE` env var

#### 2. Strategy Pattern (Pluggable Trading Algorithms)
- **Base Class**: `BaseStrategy` with `initialize()` and `on_data()` lifecycle hooks
- **Context Interface**: `IContext` abstracts buy/sell operations across backtest and live modes
- **Registry**: `StrategyRegistry` dynamically loads strategy classes by name
- **Implementations**:
  - `RSIStrategy` - Classic RSI indicator-based trading
  - `TimeMomentumStrategy` - Time-based entry with trailing stops
  - `DipMartingaleStrategy` - Multi-level pyramid entries with martingale position sizing

#### 3. Manager Pattern (Singleton Services)
- `LiveManager` - Singleton managing all live trading sessions, restored from DB on startup
- `BotManager` - Legacy simple bot orchestrator
- `KiwoomTokenManager` - Token lifecycle and refresh management
- `AccountCache` - In-memory credential caching with active account selection
- `HttpClientManager` - Global async HTTP client for API calls

#### 4. Execution Contexts
- `BacktestContext` - Simulates trading with historical data, no real orders
- `LiveContext` - Executes actual orders via Kiwoom API
- Both implement `IContext` interface for strategy portability

### Live Trading Data Flow

```
Kiwoom WebSocket (Real-time Ticks)
    ↓
LiveManager._on_tick(symbol, tick_data)
    ↓
LiveTradingEngine.process_realtime_tick()
    ↓
CandleRealAggregator (1m/5m/1h aggregation)
    ↓
Strategy.on_data(ohlcv)  [Signal Generation]
    ↓
LiveContext.buy() / sell()  [Order Execution]
    ↓
LiveTradeExecution  [DB Logging: slippage, fees, PnL]
```

### Frontend Architecture

#### State Management
- **Global Context**:
  - `AuthContext` - User authentication, JWT token management, persistent login
  - `MarketDataContext` - Real-time balance, holdings, system status (5s polling)
- **Server State**: React Query v5 for caching (configured in `main.jsx`)
- **Local State**: Custom hooks (`useManualTrade`, `useConfigPersistence`)

#### Routing & Pages
- `/` - Dashboard (watchlist, market overview, flow visualization)
- `/manual` - Manual trading with limit/market orders and conditional orders
- `/auto` - Simple auto trading (legacy RSI bots)
- `/strategies` - **Most complex page**: Advanced backtesting, optimization, live trading
- `/settings` - Mode toggle (paper/real), account config
- `/admin` - System management (admin-only)

#### API Integration
- **Client**: `api/client.js` - Axios instance with interceptors
- **Schema**: `api/schema.js` - Auto-generated normalizers from backend OpenAPI
- **Proxy**: Vite dev server proxies `/api` to backend (`http://127.0.0.1:8001`)

### Database Schema (Key Tables)

- **live_bot_sessions** - Active/historical trading sessions with strategy config
- **live_trade_executions** - Execution records (signal → fill, slippage, fees)
- **ohlcv** - Candlestick data with unique constraint on (symbol, timestamp, timeframe)
- **strategy_configs** - User strategy configurations (JSON parameters)
- **exchange_accounts** - Encrypted Kiwoom credentials (Fernet cipher)
- **strategy_results** - Backtest and optimization result storage

## Important Notes

### Kiwoom API Limitations
- **Intraday Data**: Only ~1 year (4000 candles) available for minute/hour intervals - this is a Kiwoom API policy, not a bug
- **Daily+ Data**: 10+ years available for daily/weekly/monthly candles
- **Token Expiration**: Tokens expire and need refresh - handled by `KiwoomTokenManager`
- **Rate Limits**: Be careful with rapid API calls, use mock adapter for testing

### Trading Safety
- **Paper Trading Default**: `is_paper=True` by default in live sessions
- **Order Toggle**: `orders_enabled` flag allows signal generation without execution
- **Mode Selection**: `TRADING_MODE` env var controls real vs mock adapter
- **Never commit**: Do NOT commit `.env` files or Kiwoom credentials

### Process Management
- **PM2 Only**: Do NOT use systemd alongside PM2 - choose one
- **Local Tools**: System uses bundled Node.js in `tools/` directory for portability
- **Ecosystem Config**: `ecosystem.config.cjs` defines both backend and frontend processes

### Configuration Management
Environment variables are loaded from multiple sources (priority order):
1. `.env` (project root) — **메인 설정 파일**
2. `backend/.env` — Python 전용 (`PYTHONDONTWRITEBYTECODE` 만)
3. System environment variables

**Key Variables**:
- `TRADING_MODE` - "MOCK" or "REAL" (selects adapter)
- `BACKEND_PORT` - Default 8001
- `FRONTEND_PORT` - Default 5173
- `POSTGRES_SERVER`, `POSTGRES_USER`, `POSTGRES_DB` - Database connection
- `SECRET_KEY` - JWT signing key
- `KIWOOM_*` - API credentials (keep secret!)

### Version Management

> ⚠️ **MEMORY: 버전업 요청 시 반드시 이 섹션을 따를 것!**

버전은 **코드 2곳**만 수정하면 됨 (DB 저장 없음):
- `backend/app/core/config.py` — `PROJECT_VERSION` (백엔드 API 반환)
- `frontend/package.json` — `version` (Vite 빌드 시 주입)

**반드시 `bump_version.sh` 스크립트를 사용할 것:**
```bash
# 버전업 + 커밋 + 태그 + 푸시 + PM2 재시작 (올인원)
./scripts/bump_version.sh 0.9.9.14

# 재시작만 (버전 변경 없이)
./scripts/bump_version.sh --restart

# 현재 버전 확인
./scripts/bump_version.sh
```

**Claude 버전업 체크리스트** (이 순서대로 실행):
1. ✅ `.claude/docs/release_protocol.md` 읽기 (상세 절차 확인)
2. ✅ 커밋되지 않은 변경사항이 있으면 먼저 커밋
3. ✅ Change Log Report 생성 (User Ordered / Self-Initiated / Modified Files)
4. ✅ `./scripts/bump_version.sh <새버전>` 실행 (절대 수동 편집 금지!)
5. ✅ 사용자에게 결과 보고

**Claude에게 요청 시:**
- "버전업 해줘" / "배포해줘" / "Version Up" → 위 체크리스트 실행
- "재시작 해줘" → `bump_version.sh --restart` 실행
- 수동으로 config.py, package.json 수정하지 말 것!

### Real-time WebSocket Endpoints
- `/api/v1/live/ws/{session_id}` - Live session feed (signals, orders, PnL)
- `/api/v1/live/ws/watch/{symbol}` - Real-time symbol quotes

### Strategy Development
When adding new strategies:
1. Inherit from `BaseStrategy` in `backend/app/strategies/base.py`
2. Implement `initialize()` and `on_data()` methods
3. Register in `StrategyRegistry` in `backend/app/core/strategy_registry.py`
4. Add parameter schema for frontend auto-generation
5. Test in mock mode before using real money

### Session Lifecycle
- `RUNNING` - Active live trading
- `PAUSED` - Suspended, can be resumed
- `STOPPED` - Manually stopped by user
- `ERROR` - Encountered exception during execution

## Critical Conventions

### Backend Code Style
- **Async/Await**: Use async functions for I/O operations
- **Dependency Injection**: Use FastAPI's `Depends()` for database sessions and adapters
- **Error Handling**: Raise `HTTPException` with appropriate status codes
- **Logging**: Use Python's logging module, not print statements

### Frontend Code Style
- **File Naming**: PascalCase for components (`LiveStrategyPanel.jsx`)
- **API Calls**: Always use `api/client.js` axios instance, never raw fetch
- **Error Handling**: Try/catch with user-friendly error messages
- **Styling**: Tailwind CSS classes, dark theme (`bg-[#0a0a0f]`)

### Git Workflow
- Do NOT commit `*.log`, `*.sql`, `*.db`, `.env`, `venv/`, `node_modules/`
- Use descriptive commit messages
- Test in mock mode before committing live trading changes

## Development Workflow

1. **Start System**: `./deploy_with_pm2.sh` (handles everything)
2. **Check Logs**: `npm run logs` or check `backend.log` / `frontend.log`
3. **Database Changes**: Write migration script, test locally, then deploy
4. **Strategy Changes**: Test with mock adapter, then backtest, then paper trade, finally real trade
5. **Frontend Changes**: Hot reload via Vite, verify API integration
6. **Deploy**: Run `./deploy_with_pm2.sh` on server (handles git pull + restart)

## Access Points

- **Frontend**: http://localhost:5173 (or server IP)
- **Backend API**: http://localhost:8001
- **API Docs**: http://localhost:8001/docs (FastAPI auto-generated Swagger UI)
- **Health Check**: http://localhost:8001/api/v1/status

---

## Remote Server Deployment

### Server Info

| 항목 | 값 |
|------|-----|
| Host | 121.183.229.140 |
| User | mint |
| Path | ~/auto_trading |

### Quick Deploy (코드만 변경된 경우)
```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"
```

### Full Deploy with DB Migration
```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && cd backend && python3 -m migrations.run_migrations && cd .. && pm2 restart at-backend at-frontend"
```

### Verify Deployment
```bash
ssh mint@121.183.229.140 "curl -s http://localhost:8001/api/v1/system/version"
```

---

## Version Release Protocol

> ⚠️ **트리거 키워드**: "버전업", "배포", "Version Up"

### Pre-Release
1. 커밋되지 않은 변경사항 확인 및 커밋
2. Change Log Report 생성:
   - **User Ordered Changes**: 사용자 요청 변경
   - **Self-Initiated Changes**: 자체 개선
   - **Modified Files**: 수정된 파일 목록

### Apply Version Bump
```bash
# 버전업 + 커밋 + 태그 + 푸시 + PM2 재시작 (올인원)
./scripts/bump_version.sh X.Y.Z

# 재시작만
./scripts/bump_version.sh --restart
```

### Post-Release
1. PM2 재시작: `pm2 restart all`
2. UI 버전 확인
3. Change Log Report 사용자에게 보고

> ⚠️ **리모트 배포는 사용자가 명시적으로 요청할 때만 수행!**
> "리모트 배포 해줘", "원격 서버에도 배포해줘" 등 요청이 있을 때만 Quick Deploy 실행

### 금지 사항
- ❌ `backend/app/core/config.py` 수동 수정
- ❌ `frontend/package.json` 수동 수정
- ❌ 스크립트 없이 git tag 생성
- ❌ **사용자 요청 없이 리모트 배포 금지**

---

## Database Migration Protocol

> **CRITICAL**: 절대 DB를 DROP하거나 RESET하지 말 것. 데이터 손실은 용납되지 않음.

### Pre-Migration
1. 중요 데이터 확인:
   ```bash
   psql -h localhost -U antigravity_user -d antigravity_db -c "SELECT count(*) FROM exchange_accounts;"
   ```
2. 백업 생성:
   ```bash
   pg_dump -h localhost -U antigravity_user antigravity_db > backups/db_backup_$(date +%Y%m%d_%H%M%S).sql
   ```

### Migration Script (권장)
```python
# backend/migrate_add_new_column.py
from app.db.session import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'your_table'
        """))
        existing = {row[0] for row in result}

        if 'new_column' not in existing:
            conn.execute(text("ALTER TABLE your_table ADD COLUMN new_column VARCHAR(255)"))
            print("Added: new_column")
        conn.commit()

if __name__ == "__main__":
    migrate()
```

### Post-Migration Verification
```bash
psql -h localhost -U antigravity_user -d antigravity_db -c "\d your_table"
```

### Emergency Recovery
```bash
pm2 stop all
psql -h localhost -U antigravity_user -d antigravity_db < backups/db_backup_YYYYMMDD.sql
pm2 restart all
```

---

## Rollback Protocol

> **Default**: DB 롤백 없이 Git 롤백만 수행. DB 롤백은 명시적 요청 시에만.

### Procedure
```bash
# 1. 서비스 중지
pm2 stop all

# 2. 코드 롤백
git stash
git checkout <version_tag_or_hash>

# 3. (선택) DB 롤백 - 요청 시에만
PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost -d antigravity_db < backups/db_backup_XXXX.sql

# 4. 서비스 재시작
pm2 restart all
```

---

## Syntax Check Protocol

> 코드 수정 후 반드시 문법 검사 실행

### Python Files
```bash
python3 -m py_compile <file_path>
```
- Exit Code 0: PASS
- Exit Code != 0: 즉시 수정 필요

### JavaScript/React Files
```bash
cd frontend && npm run lint
```

---

## Troubleshooting

### SSH 접속 실패

**Host key verification failed:**
```bash
ssh-keyscan -H 121.183.229.140 >> ~/.ssh/known_hosts
```

**SSH 키 인증 실패:**
```bash
cat ~/.ssh/id_ed25519.pub
ssh mint@121.183.229.140 "mkdir -p ~/.ssh && echo 'YOUR_PUBLIC_KEY' >> ~/.ssh/authorized_keys"
```

### WSL Git Push 실패

**Credential 문제:**
```bash
git config --global credential.helper '/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe'
```

### 서비스 상태 확인
```bash
# 로컬
pm2 status && pm2 logs --lines 20

# 리모트
ssh mint@121.183.229.140 "pm2 status && pm2 logs --lines 20"
```
