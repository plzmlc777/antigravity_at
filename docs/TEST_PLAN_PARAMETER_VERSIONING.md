# 전략 파라미터 버저닝 - 장 개장 테스트 계획

## 테스트 환경
- **날짜**: 2026-01-31 (금)
- **장 시간**: 09:00 ~ 15:30
- **모드**: Paper 거래 권장 (안전한 테스트)

---

## Phase 1 테스트: 설정 스냅샷 저장 확인

**목적**: 거래 실행 시 `config_snapshot`이 정상적으로 저장되는지 확인

### 테스트 절차

1. **거래 전 DB 상태 확인**
```bash
psql -U postgres antigravity_db -c "
SELECT COUNT(*) as total,
       COUNT(config_snapshot) as with_snapshot
FROM live_trade_executions
WHERE created_at > '2026-01-30';"
```

2. **전략 실행** (장 시작 후)
   - StrategyView에서 전략 선택 (예: dip_martingale)
   - Paper 모드로 실행
   - 매수 신호 발생까지 대기

3. **거래 후 스냅샷 확인**
```bash
psql -U postgres antigravity_db -c "
SELECT id, symbol, trade_type, config_snapshot
FROM live_trade_executions
WHERE config_snapshot IS NOT NULL
ORDER BY created_at DESC LIMIT 3;"
```

**예상 결과**: `config_snapshot`에 전략 파라미터가 JSON으로 저장됨

---

## Phase 2 테스트: 파라미터 성과 분석 API

**목적**: 거래 데이터 기반 파라미터별 성과 분석 확인

### 테스트 절차

1. **API 호출** (거래 발생 후)
```bash
curl "http://localhost:8001/api/v1/live/parameter-analysis?mode=paper"
```

2. **특정 종목 필터**
```bash
curl "http://localhost:8001/api/v1/live/parameter-analysis?symbol=005930&mode=paper"
```

**예상 결과**:
```json
{
  "mode": "paper",
  "total_configs": 1,
  "data": [{
    "config_hash": "abc123...",
    "key_params": {...},
    "cycles": N,
    "win_rate": XX.X,
    "total_pnl": XXXXX
  }]
}
```

**주의**: 거래가 없으면 `"data": []` 반환 (정상)

---

## Phase 3 테스트: 버전 관리 UI

**목적**: 프론트엔드에서 파라미터 버전 저장/복원 기능 확인

### 테스트 절차

1. **StrategyView 접속**
   - 브라우저에서 전략 설정 페이지 열기
   - 전략 선택 (예: dip_martingale)

2. **버전 저장 테스트**
   - 파라미터 설정 영역 아래 "파라미터 버전 관리" 패널 확장
   - 버전 이름 입력 (예: "테스트 v1")
   - "저장" 버튼 클릭
   - 목록에 새 버전 표시 확인

3. **파라미터 변경**
   - `target_dip` 값 변경 (예: 0.015 → 0.02)

4. **버전 복원 테스트**
   - 저장된 "테스트 v1" 버전의 "복원" 버튼 클릭
   - 파라미터가 원래 값으로 복원되는지 확인

5. **버전 삭제 테스트**
   - "삭제" 버튼 클릭
   - 목록에서 제거 확인

### API 직접 테스트 (선택)
```bash
# 목록 조회
curl "http://localhost:8001/api/v1/live/parameter-versions?strategy_id=dip_martingale"

# 저장
curl -X POST "http://localhost:8001/api/v1/live/parameter-versions" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id":"dip_martingale","symbol":"005930","version_name":"API Test","params":{"target_dip":0.015}}'
```

---

## 체크리스트

| # | 항목 | 확인 |
|---|------|------|
| 1 | 거래 실행 시 config_snapshot 저장됨 | ☐ |
| 2 | config_snapshot에 전략 파라미터 포함 | ☐ |
| 3 | `/parameter-analysis` API 정상 응답 | ☐ |
| 4 | 파라미터 버전 저장 성공 | ☐ |
| 5 | 파라미터 버전 복원 성공 | ☐ |
| 6 | 파라미터 버전 삭제 성공 | ☐ |

---

## 문제 발생 시 로그 확인

```bash
# 백엔드 로그
cd /home/admin-ubuntu/ai/antigravity/auto_trading
npm run logs

# 또는 직접
./tools/node/lib/node_modules/pm2/bin/pm2 logs at-backend --lines 100
```

---

## 관련 문서

- [STRATEGY_PARAMETER_VERSIONING.md](./STRATEGY_PARAMETER_VERSIONING.md) - 구현 상세
