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
# ⚠️ VSCode 확장 터미널에서는 $PATH가 불완전하여 PM2를 못 찾음
# 반드시 wsl -e bash -c 로 감싸서 실행할 것!

# 버전업 + 커밋 + 태그 + 푸시 + PM2 재시작 (올인원)
wsl -e bash -c "cd /home/hcpark/antigravity && bash scripts/bump_version.sh 0.9.9.14"

# 재시작만 (버전 변경 없이)
wsl -e bash -c "cd /home/hcpark/antigravity && bash scripts/bump_version.sh --restart"

# 현재 버전 확인
wsl -e bash -c "cd /home/hcpark/antigravity && bash scripts/bump_version.sh"
```

**Claude 버전업 체크리스트** (이 순서대로 실행):
1. ✅ `.claude/docs/release_protocol.md` 읽기 (상세 절차 확인)
2. ✅ 커밋되지 않은 변경사항이 있으면 먼저 커밋
3. ✅ Change Log Report 생성 (User Ordered / Self-Initiated / Modified Files)
4. ✅ `wsl -e bash -c "cd /home/hcpark/antigravity && bash scripts/bump_version.sh <새버전>"` 실행 (절대 수동 편집 금지!)
5. ✅ 사용자에게 결과 보고

**Claude에게 요청 시:**
- "버전업 해줘" / "배포해줘" / "Version Up" → 위 체크리스트 실행
- "재시작 해줘" → `bump_version.sh --restart` 실행
- 수동으로 config.py, package.json 수정하지 말 것!

### Real-time WebSocket Endpoints
- `/api/v1/live/ws/{session_id}` - Live session feed (signals, orders, PnL)
- `/api/v1/live/ws/watch/{symbol}` - Real-time symbol quotes

### Strategy Development

**새 전략 생성 시 커스텀 에이전트 사용:**
- `strategy-builder` 에이전트가 `.claude/agents/strategy-builder.md`에 정의됨
- 대화를 통해 전략 설계 → 코드 생성 → 등록 → 검증까지 자동화
- 에이전트가 BaseStrategy/MartingaleBase 패턴, PARAMETER_SCHEMA 규칙, StrategyRegistry 등록 절차를 모두 숙지

**수동 생성 시 체크리스트:**
1. `backend/app/strategies/<id>.py` 생성 (BaseStrategy 또는 MartingaleBase 상속)
2. `PARAMETER_SCHEMA` 정의 (UI 자동 생성용)
3. `backend/app/core/strategy_registry.py`에 등록
4. `backend/migrate_add_<id>.py` 마이그레이션 스크립트로 strategy_info DB 삽입
5. `py_compile`로 문법 검증
6. 백테스트 → 모의투자 → 실거래 순서로 테스트

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

## Remote Server Deployment — 민트 서버 (Real: 121.183.229.140)

> ⚠️ **CRITICAL: 배포 전 반드시 라이브 세션 확인!**

### 1. 라이브 세션 확인 (필수)

**모든 배포 전에 반드시 실행:**
```bash
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'
```

| 상황 | 조치 |
|------|------|
| `is_paper = f` (실거래) 존재 | **배포 금지!** 사용자에게 "라이브 실거래 세션이 실행 중입니다. 정말 배포를 진행하시겠습니까?" 확인 필수 |
| `is_paper = t` (모의거래)만 존재 | 주의하여 진행. 모의 세션 중단 안내 |
| RUNNING 세션 없음 | 안전하게 배포 가능 |

### 2. DB 백업 (필수)

**배포 전 반드시 백업 + 오래된 백업 정리 (최근 2개만 유지):**
```bash
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password pg_dump -U antigravity_user -h localhost antigravity_db > ~/db_backup_$(date +%Y%m%d_%H%M%S).dump && echo "DB backup done" && ls -t ~/db_backup*.dump | tail -n +3 | xargs -r rm -v'
```

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

### Post-Deployment: 라이브 세션 복원 확인

**PM2 재시작 후 세션 복원 확인:**
```bash
# 세션 복원 로그 확인
ssh mint@121.183.229.140 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore\|session\|RUNNING"'

# DB에서 RUNNING 세션 확인
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'
```

### Emergency: 세션 복원 실패 시

```bash
# 1. 백엔드 재시작 (세션 자동 복원 트리거)
ssh mint@121.183.229.140 'pm2 restart at-backend && sleep 5 && pm2 logs at-backend --lines 50 --nostream'

# 2. 복원 확인
ssh mint@121.183.229.140 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore"'

# 3. 실패 시 백업에서 복구
ssh mint@121.183.229.140 'ls -la ~/db_backup*.dump'
ssh mint@121.183.229.140 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db < ~/db_backup_<timestamp>.dump'
```

---

## Remote Server Deployment — 우분투 서버 (Test: 121.183.229.170)

> 테스트 전용 서버. `TRADING_MODE=MOCK`으로 설정됨. 실거래 세션 체크 불필요.

### Server Info

| 항목 | 값 |
|------|-----|
| Host | 121.183.229.170 |
| User | ubuntu |
| Path | ~/auto_trading |
| Mode | MOCK (테스트 전용) |
| Web | http://121.183.229.170:5173 |
| API | http://121.183.229.170:8001 |

### Quick Deploy
```bash
ssh ubuntu@121.183.229.170 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"
```

### Full Deploy with DB Migration
```bash
ssh ubuntu@121.183.229.170 "cd ~/auto_trading && git pull origin master && cd backend && python3 -m migrations.run_migrations && cd .. && pm2 restart at-backend at-frontend"
```

### Verify Deployment
```bash
ssh ubuntu@121.183.229.170 "curl -s http://localhost:8001/api/v1/system/version"
```

### Logs
```bash
ssh ubuntu@121.183.229.170 "pm2 logs at-backend --lines 50 --nostream"
```

---

## Remote Server Deployment — GCP 서버 (Temp: 34.64.87.89)

> 민트 서버 이사 기간(~2026-04-24) 임시 운영 서버. `TRADING_MODE=REAL` 실거래 운영.
> 키움 API 지정단말기 + Binance IP 화이트리스트에 등록 완료.
> 2026-04-07 us-central1-c (35.202.214.187) → asia-northeast3-a (34.64.87.89) 이전 — Binance API 접속을 위해.

### Server Info

| 항목 | 값 |
|------|-----|
| Host | 34.64.87.89 |
| User | hcpark |
| Instance | at-asia |
| Path | ~/auto_trading |
| Branch | master (기본 브랜치가 아님, 반드시 master 사용) |
| Mode | REAL (실거래) |
| Web | http://34.64.87.89:5173 |
| API | http://34.64.87.89:8001 |
| Spec | 2 vCPU, 4GB RAM, 50GB disk (asia-northeast3-a, 서울) |

### 1. 라이브 세션 확인 (필수)

```bash
ssh hcpark@34.64.87.89 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'
```

### 2. Quick Deploy

```bash
ssh hcpark@34.64.87.89 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"
```

### 3. Full Deploy with Frontend Rebuild

```bash
ssh hcpark@34.64.87.89 "cd ~/auto_trading && git pull origin master && cd frontend && npm run build && cd .. && pm2 restart at-backend at-frontend"
```

### 4. Verify Deployment

```bash
ssh hcpark@34.64.87.89 "curl -s http://localhost:8001/api/v1/status"
```

### 5. 세션 복원 확인

```bash
ssh hcpark@34.64.87.89 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore\|session\|RUNNING"'
```

### Logs

```bash
ssh hcpark@34.64.87.89 "pm2 logs at-backend --lines 50 --nostream"
```

### 주의사항
- Git clone 기본 브랜치가 `antigravity_auto_trading`이므로 반드시 `master` 브랜치 확인
- 대규모 백테스트/최적화 비권장 (2 vCPU / 4GB RAM)
- GCP 외부 IP 변경 시 키움 API 지정단말기 재등록 필요
- 임시 서버이므로 이사 완료 후 민트 서버로 DB 역마이그레이션 필요

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
# ⚠️ VSCode 확장 터미널에서는 반드시 wsl -e bash -c 로 실행!

# 버전업 + 커밋 + 태그 + 푸시 + PM2 재시작 (올인원)
wsl -e bash -c "cd /home/hcpark/antigravity && bash scripts/bump_version.sh X.Y.Z"

# 재시작만
wsl -e bash -c "cd /home/hcpark/antigravity && bash scripts/bump_version.sh --restart"
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
- ❌ **실거래 라이브 세션 확인 없이 리모트 배포 금지** (반드시 라이브 세션 체크 먼저!)

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

## Frontend Regression Protocol

> ⚠️ **트리거**: `frontend/src/**` 또는 `frontend/tests/**` 파일을 수정한 모든 작업

### 규약
프론트엔드 코드를 수정한 직후 반드시 **`frontend-tester` 서브에이전트**를 호출해 회귀 검증을 받는다. 객관적인 증거(Playwright 결과 + 콘솔 에러 + 스크린샷 경로) 없이 "수정 완료"를 사용자에게 보고하지 않는다.

### 호출 방법
Task 도구로 `subagent_type: "frontend-tester"` 지정. 호출 시 프롬프트에 **이번에 어떤 화면/컴포넌트를 바꿨는지**를 한 줄로 전달.

### 호출 시점
- 단일 컴포넌트 수정 후
- 라우트 추가/삭제 후
- API 클라이언트 변경 후
- 빌드/번들 관련 변경 후
- 버전업 직전 (사용자 보고용 증거 확보)

### 보고 처리
- ✅ PASS: 사용자에게 "frontend-tester 통과 (X tests, Ys)" 한 줄 첨부 후 다음 단계 진행
- ❌ FAIL: 보고서의 root cause + 스크린샷/트레이스 경로를 사용자에게 그대로 전달하고, 수정 → 재호출 사이클로 진입. 절대 실패를 무시하고 진행하지 않는다.

### 예외
- 텍스트만 변경 (주석/한글 라벨 1-2자) — 호출 생략 가능
- 백엔드만 수정 — 호출 불필요
- frontend-tester 자체를 수정 — 직접 `npx playwright test` 1회 실행으로 대체

### 금지 사항
- ❌ frontend-tester 호출 없이 프론트엔드 수정을 "완료"로 보고
- ❌ 실패 보고서를 받고도 사용자 승인 없이 재시도/우회
- ❌ frontend-tester가 KillSwitch를 클릭하거나 운영 세션을 변경하도록 지시

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
