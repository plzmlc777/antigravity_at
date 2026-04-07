# GCP Operational State

> Last updated: 2026-04-07 (KST 17:00)

## Active Live Sessions

| session_id | symbol | strategy | mode | initial | started |
|---|---|---|---|---|---|
| 643f2dd0-3e2c-4c81-8642-dba1842e8987 | 091160 (LG생활건강) | rsi_martingale | paper | 2,000,000 | 2026-04-07 16:59 KST |
| 47a57c9e-9fee-4af5-a9aa-ef825375a68c | 105560 (KB금융) | rsi_martingale | paper | 2,000,000 | 2026-04-07 16:59 KST |

**Account**: id=1 키움 ISA 2000 (plzmlc@outlook.com)
**Selection rationale**: 2026-04-07 symbol-select 검증 결과 상위 2개 (run_id 20260407T033843Z)

## Active Cron Jobs

| schedule (UTC) | KST | script | purpose |
|---|---|---|---|
| `*/30 * * * *` | 매 30분 | cron_ops_monitor.sh | 세션 헬스체크 (ops-monitor 에이전트) |
| `0 7 * * 1-5` | 평일 16:00 | cron_daily_review.sh | 일간 CIO 풀 사이클 (장 마감 후) |

## 24-Hour Verification Plan

| When (KST) | Expected Behavior | Verify By |
|---|---|---|
| 2026-04-07 17:00~ | 세션 RUNNING idle (장 마감), Kiwoom WS 연결 유지 | ops-monitor 30분 cron |
| 2026-04-08 09:00 | 장 시작, 실시간 틱 수신 시작, 전략 사이클 활성화 | engine logs, equity 변화 |
| 2026-04-08 16:00 | daily-review cron 첫 실행 (CIO 풀 사이클) | verification_logs/*_daily_review.md |
| 2026-04-08 17:00 (T+24h) | 24h 무인 운영 검증 완료, 결과 평가 | OPERATIONAL_STATE 갱신 |

## Verification Logs Location

```
.claude/verification_logs/
├── OPERATIONAL_STATE.md          ← 이 파일 (현재 상태)
├── 20260407T033843Z_*.md         ← 첫 검증 배치 (symbol-select, evolver, searcher)
├── YYYYMMDDTHHMMSSZ_daily_review.md  ← daily-review cron 결과
```

## Local Sync

```bash
# 로컬에서 GCP 결과 동기화
cd /home/hcpark/antigravity
git pull origin master
ls .claude/verification_logs/
```

## How to Stop / Modify

```bash
# 세션 중지
ssh hcpark@35.202.214.187
cd ~/auto_trading
# (mint JWT first, then)
curl -X POST -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/v1/live/stop/<session_id>

# cron 비활성화
crontab -e   # 해당 라인 주석처리
```

## Known Limitations

- **Binance**: GCP US IP로 차단 → 한국 주식만 운영
- **SSH key in ops-monitor**: 에이전트가 SSH로 PM2 직접 조회하려고 시도하나 키 없음 → API로 우회 (정상 동작)
- **494120 7주 long**: id=1 계정에 이전 세션 잔여분, 페이퍼 세션과 무관 (수동 처리 대기)
