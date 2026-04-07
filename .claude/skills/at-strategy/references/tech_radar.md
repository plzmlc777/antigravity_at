# Tech Radar — Antigravity Auto Trading System

tech-scout 에이전트가 주간 갱신. 본 문서는 시스템 개선에 적용 가능한 신기술의 지속 추적 레이더.

**운영 규칙**
- 매주 월요일 cron 실행 (tech-scout 에이전트)
- 각 항목은 status 전이 시 기록 (watching → evaluating → recommended → adopted/rejected)
- 중복 항목 금지 — 신규 발견 시 반드시 기존 리스트 조회
- 모든 `evaluating`/`recommended` 항목은 failure_mode 필수

## Status Overview

| Status | 의미 | 필수 필드 |
|--------|------|---------|
| watching | 관심 대상, 행동 불필요 | - |
| evaluating | POC 필요 | failure_mode, next_action |
| recommended | 도입 계획 확정 | failure_mode, rollback_path, next_action |
| adopted | 프로덕션 배포 완료 | 인간 설정 |
| rejected | 평가 실패 | reason |

---

## Active Items

## [2026-04-07] TS-20260407-001: Binance Futures 레거시 WebSocket URL 2026-04-23 폐기 — **해당 없음 (verified)**

- **Domain**: exchange
- **Status**: rejected (not-applicable after verification)
- **Confidence**: 0.95 (verification 후)
- **Source**: https://developers.binance.com/docs/derivatives/change-log (2026-04-02 entry)
- **Verification (2026-04-07)**: `backend/app/adapters/binance_websocket.py:22` 에서 사용 중인 `wss://fstream.binance.com/ws` 는 Binance 공식 changelog에서 **현재 표준 엔드포인트**로 확인됨. 폐기 대상(legacy URL)과 다름. 2026-04-23 decommissioning은 별도 "Important WebSocket Change Notice" 문서의 다른 레거시 URL 집합에 해당.
- **Original claim**: "레거시 WebSocket URL 4/23 폐기 → 라이브 세션 중단 위험" (recommended, conf 0.90)
- **Why rejected**: tech-scout가 deadline은 정확히 포착했으나 **어떤 URL이 폐기 대상인지 primary source에서 구체적으로 확인하지 않은 채** recommended로 올림. 우리 URL은 피해 대상 아님.
- **Lesson**: D-021 (specificity rule) 생성 — deprecation 보고 시 영향받는 정확한 URL/엔드포인트/심볼을 primary source에서 명시적으로 식별하지 못하면 `watching` 상한.
- **Next action**: 없음 — 우리 시스템 영향 없음. 기록만 유지.

## [2026-04-07] TS-20260407-002: Claude Agent SDK Python — get_context_usage() + 1M context beta — **해당 없음 (verified)**

- **Domain**: claude-sdk
- **Status**: rejected (architecture mismatch)
- **Confidence**: 0.95 (verification 후)
- **Source**: https://github.com/anthropics/claude-agent-sdk-python/blob/main/CHANGELOG.md

### Verification (2026-04-07)
- `pip show anthropic claude-agent-sdk` → **둘 다 미설치**
- 우리 백엔드는 Claude **CLI 서브프로세스**로만 호출 ([backend/app/core/analysis_scheduler.py:399-400](backend/app/core/analysis_scheduler.py#L399))
- `claude_path = get_claude_cli_path()` → `subprocess` 실행 후 stdout 파싱
- Python SDK 통합 진입점 0건 — `get_context_usage()` 호출할 곳이 없음

### Why Rejected
- `get_context_usage()`는 `ClaudeSDKClient` 인스턴스 메서드. 우리는 SDK를 import하지 않음.
- 적용하려면 CLI 호출부를 SDK 호출부로 전면 마이그레이션 필요 — 4-6시간이 아닌 **수일~수주** 작업이며, CLI로 잘 동작 중이라 ROI 없음.
- 1M context beta도 동일 — SDK 옵션이라 CLI 경로에는 적용 불가.

### Original Claim
"4-6시간 작업으로 컨텍스트 사용량 모니터링 추가" — tech-scout가 우리 아키텍처를 verify 없이 SDK 사용을 가정.

### Lesson
D-022 (architecture verification rule) 생성 — tech-scout가 `evaluating` 이상 부여 전 통합 진입점이 코드베이스에 실제 존재하는지 확인 의무.

### Alternative (별건)
컨텍스트 사용량 추적이 정말 필요해지면 CLI stdout에서 토큰 카운트를 파싱하거나, Claude CLI 자체의 향후 `--show-usage` 같은 플래그 도입을 watching list에 올릴 것.

## [2026-04-07] TS-20260407-003: TimesFM 2.5 — 200M 파라미터 / 16K 컨텍스트 / 공변량 복원

- **Domain**: ml
- **Status**: evaluating
- **Confidence**: 0.55
- **Source**: https://github.com/google-research/timesfm
- **Problem solved**: 종목 선정/시장 상태 분류에 사용할 수 있는 zero-shot 시계열 예측 기반 신호. 기존 RSI/모멘텀 룰 기반 진입 필터 옆에 '다음 N봉 분포' 확률 신호를 추가하면 DipMartingale 진입 타이밍 리스크 저감 가능. 16K 컨텍스트는 1분봉 약 11일치 입력 가능.
- **Integration cost**: 1-2일 — HuggingFace `google/timesfm-2.5-200m-pytorch` 로드, `backend/app/ai/` 내 forecast adapter 1개 + 백테스트에서 shadow 모드로 예측 기록(실주문 X), 결과 비교.
- **Failure mode**: (1) 해외/미국 주식 중심 프리트레인 → 한국 주식/암호화폐 도메인 쉬프트로 zero-shot 정확도 저조 가능 (2) 200M 파라미터 추론이 매 틱마다는 불가능 — 봉 마감 시점만 가능하고 이는 지연으로 작용 (3) GPU 없으면 CPU 추론 레이턴시가 전략 사이클 내 미납입 (4) 모델 출력을 신호화하는 규칙이 과적합 우려
- **Rollback path**: forecast adapter flag off → 전략 경로에서 분기 제거. 파일 단일 모듈 삭제로 복구. 실주문에 영향 안 주도록 shadow 모드로만 도입하면 롤백 불필요.
- **Next action**: 2026-04-21까지 shadow 모드 POC — 과거 1개월 백테스트에서 우리 보유 종목 5개에 대해 forecast vs 실제 비교 리포트 1장. 결과가 나쁘면 reject.

## [2026-04-07] TS-20260407-004: FastAPI 0.135 — strict Content-Type + Python 3.10 최소

- **Domain**: infra
- **Status**: evaluating (verified — gap larger than initial estimate)
- **Confidence**: 0.85 (verification 후)
- **Source**: https://fastapi.tiangolo.com/release-notes/

### Verification (2026-04-07, local-only)
- **Python**: 3.12.3 ✓ (FastAPI 0.135 요구사항 3.10+ 충족, 마진 충분)
- **현재 FastAPI**: 0.104.1 (2023-10 릴리즈) — **31 minor versions 뒤처짐**
- **현재 pydantic**: 2.5.2, **starlette**: 0.27.0, **uvicorn**: 0.24.0
- **Lifespan 패턴**: 이미 modern `@asynccontextmanager` 사용 중 ([backend/app/main.py:21-53](backend/app/main.py#L21-L53)). `@app.on_event` 레거시 0건 — **마이그레이션 가장 큰 risk 항목 통과**
- **리모트 서버 미점검**: 사용자 제약 (로컬 우선) — 별도 승인 후 진행 예정

### Revised Cost Estimate
- **원래 추산**: 0.5일 (tech-scout 첫 보고)
- **수정 추산**: **3-5일** (31 minor versions의 누적 변경 검토 + 회귀 테스트 필요)
- **추산 오차 원인**: tech-scout가 현재 버전을 verify 없이 "최신에 가까움"으로 가정. 실제는 2.5년 차이.

### Problem Solved
장기적으로 FastAPI 업그레이드 필요. 0.104 → 0.135 사이 누적 보안 패치 + Python 3.10+ 강제로 인한 에코시스템 호환성. 단, 0.104도 현재 정상 동작 중이므로 긴급도는 낮음.

### Failure Mode
1. Pydantic 2.5 → 2.x 최신 마이그레이션 (BaseModel 동작 변경 잠재)
2. FastAPI 0.104→0.135 사이 dependency injection 패턴 변경 (`Annotated` 권장)
3. starlette 0.27→0.40+ middleware/lifespan 동작 변경
4. 우리 백엔드는 라이브 트레이딩 운영 중 — 회귀 발생 시 직접 손실 가능

### Rollback Path
`pip install fastapi==0.104.1 pydantic==2.5.2 starlette==0.27.0 uvicorn==0.24.0` + PM2 재시작 5분. DB 스키마 변경 없음. 단, 라이브 세션 중단 후 작업 권장.

### Next Action (revised)
- **단기 (불필요)**: 0.104.1 정상 동작, 즉시 업그레이드 부담 ≫ 이득. 보안 CVE 발생 시 재평가.
- **중기 (2026-Q3)**: 단계적 업그레이드 계획 수립 — 0.104 → 0.110 → 0.120 → 0.135 식으로 나눠서 회귀 격리
- **차기 tech-scout 런**: TS-004 처리 보류, 보안 CVE 모니터링만 유지

## [2026-04-07] TS-20260407-005: MCP 2026 로드맵 — agent-to-agent 통신 Q3 / Registry Q4

- **Domain**: claude-sdk
- **Status**: watching
- **Confidence**: 0.35
- **Source**: http://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/
- **Problem solved**: 장기적으로 strategy-builder가 tech-scout를 MCP 툴로 호출하는 등 서브에이전트 간 수평 호출이 공식화되면 현재 커스텀 `.claude/agents/` 구조를 더 표준화 가능.
- **Integration cost**: (로드맵 단계) — 아직 스펙 미확정
- **Failure mode**: *(로드맵 단계로 failure_mode 불요, watching only)*
- **Rollback path**: -
- **Next action**: 2026-07 Q3 릴리즈 임박 시 재평가. 현재는 관찰만.

## [2026-04-07] TS-20260407-006: Binance Mark-Price-Stream 신규 필드 `ap` (이동평균 마크가) — 미사용 스트림

- **Domain**: exchange
- **Status**: watching
- **Confidence**: 0.40
- **Source**: https://developers.binance.com/docs/derivatives/change-log
- **Verification (2026-04-07)**: D-022 적용. Grep 결과 우리는 `markPrice`/`mark_price` 값을 **REST 포지션 조회**(`backend/app/adapters/binance_futures.py:202` `pos.get("markPrice")`) 에서만 소비함. WebSocket `!markPrice@arr` 스트림은 구독하지 않음 (`binance_websocket.py` 에 markPrice 핸들러 0건). 따라서 신규 필드 `ap` 의 즉시 통합 진입점이 없음.
- **Problem solved (potential)**: 향후 청산 모니터(`futures_monitor.py`)가 마크가 이동평균을 활용하면 청산가 거리 측정 노이즈 감소 가능. 현재는 가설.
- **Integration cost**: 미정 — 먼저 mark-price WebSocket 구독 인프라부터 추가 필요 (1-2일 작업)
- **Failure mode**: *(watching only — failure_mode 면제)* 다만 구독 추가 시 기존 REST 폴링 경로와 이중 소스 불일치 가능.
- **Rollback path**: -
- **Next action**: 청산 모니터 노이즈가 실제 문제로 보고되면 그때 재평가. 현재는 관찰만.

---

## Rejected / Archive

### [2026-04-07] Colab MCP Server — 스택 무관
- **Reason**: Google Colab은 우리 개발/운영 워크플로우와 무관. 백테스트/라이브 트레이딩은 WSL/민트/GCP 서버에서 실행됨.

### [2026-04-07] TimescaleDB v2.25 hypertables — 현재 스택 아님
- **Reason**: 현재 PostgreSQL 일반 테이블 사용 중. TimescaleDB 전환은 OHLCV 2700만 건 마이그레이션 동반 대공사로 7일 스캔 범위를 벗어남. 향후 백테스트 속도 이슈가 구체화되면 별건으로 재평가.

### [2026-04-07] VectorBT 2026-03-26 최신 릴리즈 — 증거 부족
- **Reason**: PyPI에 릴리즈는 확인되나 실제 changelog 내용을 1차 소스에서 확인 불가. 최소 증거 기준 미달.

### [2026-04-07] Claude Code Bedrock 마법사 / /powerup — 스택 무관
- **Reason**: AWS Bedrock 사용 안 함. /powerup은 교육용 UX로 시스템 개선과 무관.

### [2026-04-07 run#2] Binance forceOrders 90일 데이터 한도 (changelog 2026-04-06) — 미사용 엔드포인트
- **Reason**: D-022 검증. `forceOrders|force_orders|forceOrder` grep 결과 0건. `/fapi/v1/forceOrders` 를 호출하지 않음. 우리 청산 추적은 포지션 REST + balance 폴링 기반. 영향 없음.
- **Source**: https://developers.binance.com/docs/derivatives/change-log

### [2026-04-07 run#2] MCP Tool Poisoning Attack (Invariant Labs, 2026-04-01) — MCP 서버 미사용
- **Reason**: D-022 검증. `.mcp.json` / `mcpServers` 설정 0건. 우리는 MCP 서버를 구성하지 않으며 Claude Code 내장 툴만 사용. 공격 표면 없음. 향후 MCP 도입 시 재평가 필수.
- **Source**: https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks

### [2026-04-07 run#2] Polars 1.39.3 / 2.0 논의 — 현재 스택 아님
- **Reason**: D-022 검증. `import polars` grep 0건. 우리는 pandas 사용 (`backend/app/ml/{feature_engine,trainer,predictor}.py`). polars 도입은 새 의존성 추가이며 백테스트/ML 파이프라인 재작성이 동반되는 대공사. 7일 스캔 범위 초과.
- **Source**: https://github.com/pola-rs/polars/releases

### [2026-04-07 run#2] Claude Code 4월 릴리즈 (forceRemoteSettingsRefresh / /cost breakdown / Write tool 60% diff 가속) — 트레이딩 무관 UX 개선
- **Reason**: 정책/UX/터미널 개선 위주. 트레이딩 코드 경로와 통합 진입점 없음. /cost breakdown은 흥미롭지만 인간 모니터링용이며 백엔드 자동화에 통합할 항목 아님. Bedrock 마법사는 이미 run#1에서 reject.
- **Source**: https://code.claude.com/docs/en/changelog

### [2026-04-07 run#2] kiwoom-rest-api PyPI 패키지 업데이트 — 자체 어댑터 사용
- **Reason**: 우리는 `KiwoomRealAdapter`/`KiwoomMockAdapter` 자체 구현. 제3자 wrapper 라이브러리 미사용. D-022 — 통합 진입점 없음.

---

## History

| Date | Items Added | Items Updated | Scanned Candidates | Final Reports |
|------|-------------|---------------|--------------------|--------------:|
| 2026-04-07 | 5 | 0 | 12 | 5 |
| 2026-04-07 (run#2) | 1 (watching) | 0 | 8 | 1 |
