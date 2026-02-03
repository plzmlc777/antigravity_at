# 전략 파라미터 버저닝 시스템

## 개요
거래 실행 시점의 전략 파라미터를 기록하여, 어떤 파라미터 설정에서 성과가 좋았는지 분석 가능하게 함.

## 구현 단계

### Phase 1: 거래 데이터에 설정 스냅샷 저장 (MVP)
**목표**: 각 거래 실행 시 현재 전략 파라미터를 함께 저장

**변경 사항**:
1. `live_trade_executions` 테이블에 `config_snapshot` (JSON) 컬럼 추가
2. 거래 실행 시 현재 설정을 스냅샷으로 저장
3. 기존 데이터는 null 허용

**파일**:
- `backend/app/models/live_trading.py` - 모델에 컬럼 추가
- `backend/app/core/live_engine.py` - 거래 기록 시 스냅샷 포함

### Phase 2: 파라미터별 성과 분석 API
**목표**: config_snapshot 기반으로 그룹핑하여 성과 비교

**변경 사항**:
1. 설정 해시 생성 함수 (동일 설정 그룹핑용)
2. 파라미터별 승률/PnL 집계 API
3. 프론트엔드 분석 UI

**API**:
- `GET /live/parameter-analysis?symbol=000660` - 파라미터별 성과 반환

### Phase 3: 명시적 버전 관리 (선택)
**목표**: 사용자가 버전에 이름을 붙이고 복원 가능

**변경 사항**:
1. `strategy_parameter_versions` 테이블 신규 생성
2. 버전 저장/복원 API
3. 버전 비교 UI

---

## Phase 1 상세 구현

### 1.1 DB 마이그레이션

```sql
ALTER TABLE live_trade_executions
ADD COLUMN config_snapshot JSONB;

COMMENT ON COLUMN live_trade_executions.config_snapshot IS
'거래 실행 시점의 전략 파라미터 스냅샷';
```

### 1.2 모델 수정 (live_trading.py)

```python
class LiveTradeExecution(Base):
    # ... 기존 필드들 ...
    config_snapshot = Column(JSON, nullable=True)  # 추가
```

### 1.3 엔진 수정 (live_engine.py)

거래 기록 시 현재 설정 포함:
```python
async def _record_execution(self, signal, ...):
    execution = LiveTradeExecution(
        # ... 기존 필드들 ...
        config_snapshot=self.current_config  # 추가
    )
```

### 1.4 스냅샷 내용 예시

```json
{
    "strategy_id": "dip_martingale",
    "symbol": "000660",
    "params": {
        "initial_investment": 500000,
        "max_levels": 4,
        "target_dip": 0.015,
        "take_profit": 0.008,
        "trailing_trigger": 0.003,
        "trailing_stop": 0.002
    },
    "snapshot_at": "2026-01-29T23:00:00"
}
```

---

## 예상 효과

1. **성과 귀인**: "target_dip 1.5%일 때 승률 86%, 2.0%일 때 72%"
2. **최적화 근거**: 데이터 기반 파라미터 튜닝
3. **변경 추적**: 언제 어떤 설정으로 거래했는지 기록

---

## 작업 체크리스트

- [x] Phase 1.1: DB 컬럼 추가 (ALTER TABLE) - 2026-01-29 완료
- [x] Phase 1.2: 모델에 config_snapshot 필드 추가 - 2026-01-29 완료
- [x] Phase 1.3: 거래 기록 시 스냅샷 저장 로직 - 2026-01-29 완료
- [x] Phase 1.4: 테스트 및 검증 - 2026-01-29 완료
- [x] Phase 2.1: config_snapshot 해시 생성 함수 구현 - 2026-01-29 완료
- [x] Phase 2.2: 파라미터별 성과 분석 API 구현 - 2026-01-29 완료
- [x] Phase 2.3: 테스트 및 검증 - 2026-01-29 완료
- [x] Phase 3.1: strategy_parameter_versions 테이블 생성 - 2026-01-29 완료
- [x] Phase 3.2: 버전 저장/복원 API 구현 - 2026-01-29 완료
- [x] Phase 3.3: 프론트엔드 버전 관리 UI - 2026-01-29 완료
- [x] Phase 3.4: 테스트 및 검증 - 2026-01-29 완료

---

## 변경된 파일 (Phase 1)

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/models/live_trading.py` | `config_snapshot` 컬럼 추가 |
| `backend/app/core/live_context.py` | `set_config_snapshot()` 메서드 및 저장 로직 |
| `backend/app/core/live_engine.py` | 전략 실행 전 스냅샷 설정 호출 |

## 검증

```sql
-- 기존 데이터 (스냅샷 없음)
SELECT id, config_snapshot IS NOT NULL as has_snapshot
FROM live_trade_executions LIMIT 5;
-- 결과: has_snapshot = false

-- 새 거래부터 스냅샷 저장됨
```

---

## Phase 2 상세 구현

### 2.1 해시 생성 함수

```python
def _create_config_hash(config_snapshot: dict) -> str:
    """
    Create a deterministic hash from config params for grouping.
    Only uses 'params' key to ignore timestamp differences.
    """
    if not config_snapshot:
        return "no_config"
    params = config_snapshot.get("params", config_snapshot)
    params_str = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(params_str.encode()).hexdigest()[:12]
```

### 2.2 주요 파라미터 추출 함수

```python
def _extract_key_params(config_snapshot: dict) -> dict:
    """Extract key parameters for display (human-readable summary)."""
    # 전략별로 중요한 파라미터만 추출
    # dip_martingale: target_dip, take_profit, max_levels, trailing_*
    # time_momentum: target_percent, direction, start_time, stop_time
```

### 2.3 성과 분석 API

```
GET /api/v1/live/parameter-analysis?symbol=000660&mode=paper
```

**응답 예시**:
```json
{
    "mode": "paper",
    "symbol": "000660",
    "total_configs": 2,
    "data": [
        {
            "config_hash": "a1b2c3d4e5f6",
            "symbol": "000660",
            "key_params": {
                "strategy_id": "dip_martingale",
                "target_dip": 0.015,
                "take_profit": 0.008
            },
            "full_config": {...},
            "cycles": 15,
            "total_trades": 30,
            "win_rate": 86.7,
            "total_pnl": 125000,
            "avg_pnl": 8333,
            "max_pnl": 25000,
            "min_pnl": -5000
        }
    ]
}
```

### 변경된 파일 (Phase 2)

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/api/live_trading.py` | `_create_config_hash()`, `_extract_key_params()`, `/parameter-analysis` 엔드포인트 추가 |

### Phase 2 검증

```bash
# API 테스트
curl "http://localhost:8001/api/v1/live/parameter-analysis?mode=paper"

# 데이터가 없으면:
# {"message": "No trades with config_snapshot found", "data": []}

# 새 거래 후 데이터 있으면:
# {"mode": "paper", "symbol": "all", "total_configs": N, "data": [...]}
```

---

## Phase 3 상세 구현

### 3.1 DB 테이블 생성

```sql
CREATE TABLE strategy_parameter_versions (
    id VARCHAR PRIMARY KEY,
    strategy_id VARCHAR NOT NULL,
    symbol VARCHAR,
    version_name VARCHAR NOT NULL,
    description VARCHAR,
    params JSONB NOT NULL,
    config_hash VARCHAR(12),
    performance_stats JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_spv_strategy_id ON strategy_parameter_versions(strategy_id);
CREATE INDEX idx_spv_symbol ON strategy_parameter_versions(symbol);
CREATE INDEX idx_spv_config_hash ON strategy_parameter_versions(config_hash);
```

### 3.2 버전 관리 API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/live/parameter-versions` | 버전 목록 조회 |
| POST | `/live/parameter-versions` | 새 버전 저장 |
| GET | `/live/parameter-versions/{id}` | 특정 버전 조회 |
| PUT | `/live/parameter-versions/{id}` | 버전 수정 |
| DELETE | `/live/parameter-versions/{id}` | 버전 삭제 (soft delete) |
| POST | `/live/parameter-versions/{id}/restore` | 버전 복원 |
| POST | `/live/parameter-versions/{id}/update-stats` | 성과 통계 업데이트 |

**버전 저장 요청 예시**:
```json
{
    "strategy_id": "dip_martingale",
    "symbol": "005930",
    "version_name": "Conservative v1",
    "description": "Lower risk settings",
    "params": {
        "target_dip": 0.015,
        "take_profit": 0.008,
        "max_levels": 3
    },
    "is_default": false
}
```

### 3.3 프론트엔드 UI

- **ParameterVersionManager 컴포넌트**: 접이식 패널로 전략 설정 영역에 통합
- 기능: 버전 저장, 목록 조회, 복원, 삭제
- 위치: `frontend/src/components/ParameterVersionManager.jsx`

### 변경된 파일 (Phase 3)

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/models/live_trading.py` | `StrategyParameterVersion` 모델 추가 |
| `backend/app/api/live_trading.py` | 버전 관리 API 엔드포인트 추가 |
| `frontend/src/api/client.js` | 버전 관리 API 클라이언트 함수 추가 |
| `frontend/src/components/ParameterVersionManager.jsx` | 버전 관리 UI 컴포넌트 (신규) |
| `frontend/src/views/StrategyView.jsx` | ParameterVersionManager 통합 |

### Phase 3 검증

```bash
# 버전 목록 조회
curl "http://localhost:8001/api/v1/live/parameter-versions?strategy_id=dip_martingale"

# 새 버전 저장
curl -X POST "http://localhost:8001/api/v1/live/parameter-versions" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id": "dip_martingale", "version_name": "Test v1", "params": {"target_dip": 0.02}}'

# 버전 복원
curl -X POST "http://localhost:8001/api/v1/live/parameter-versions/{id}/restore"
```
