# CLAUDE.md

Antigravity Auto Trading System — 한국 주식(키움) + 바이낸스 선물 자동매매 플랫폼.

**Version**: v0.9.9.57 | **Stack**: FastAPI + React/Vite + PostgreSQL

## Commands

```bash
./deploy_with_pm2.sh                    # Start all (backend + frontend)
npm run status / logs / restart / stop  # PM2 management

# Backend
cd backend && source venv/bin/activate && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd frontend && npm run dev              # port 5173

# Syntax check (코드 수정 후 필수)
python3 -m py_compile <file.py>
cd frontend && npm run lint
```

## Key Rules

- **Trading Safety**: `is_paper=True` default, `TRADING_MODE` env var = MOCK/REAL
- **DB**: 절대 DROP/RESET 금지. 마이그레이션은 `.claude/references/protocols.md` 참조
- **Git**: .env, venv/, node_modules/, *.log 커밋 금지
- **Code Style**: async/await, FastAPI Depends(), HTTPException, logging (not print)
- **Frontend**: PascalCase components, api/client.js (not raw fetch), Tailwind dark theme

## Version Bump

> "버전업"/"배포"/"Version Up" 요청 시

```bash
bash scripts/bump_version.sh X.Y.Z     # 올인원 (커밋+태그+푸시+PM2 재시작)
bash scripts/bump_version.sh --restart  # 재시작만
```
config.py/package.json 수동 수정 금지! 상세: `.claude/references/protocols.md`

## Frontend Regression

`frontend/src/**` 수정 시 반드시 `frontend-tester` 서브에이전트 호출.
PASS 증거 없이 "완료" 보고 금지. 텍스트만 변경 시 생략 가능.

## Deploy (리모트)

> 사용자 명시적 요청 시에만. 실거래 세션 확인 필수.
> 상세: `.claude/references/deploy.md`

## Strategy Development

새 전략: `strategy-builder` 에이전트 사용 (`.claude/agents/strategy-builder.md`)
수동: BaseStrategy 상속 → PARAMETER_SCHEMA → StrategyRegistry 등록 → migrate → py_compile → 백테스트

## Reference Docs (필요시 Read)

- `.claude/references/deploy.md` — 서버 배포 (민트/GCP/우분투)
- `.claude/references/architecture.md` — 시스템 아키텍처 상세
- `.claude/references/protocols.md` — DB 마이그레이션, 롤백, 버전 릴리즈
- `.claude/docs/release_protocol.md` — 릴리즈 상세 절차
