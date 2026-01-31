# 서비스 재시작 매뉴얼 (PM2)

## 로컬 서버

모든 명령은 `auto_trading/` 디렉토리에서 실행:

```bash
cd /home/admin-ubuntu/ai/antigravity/auto_trading

# 전체 재시작
npm run restart

# 상태 확인
npm run status

# 로그 확인
npm run logs

# 개별 재시작
./tools/node/bin/pm2 restart at-backend
./tools/node/bin/pm2 restart at-frontend
```

## 리모트 서버 (121.183.229.140)

### Quick Deploy (권장)

```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend && pm2 status"
```

### 개별 명령

```bash
# 상태 확인
ssh mint@121.183.229.140 "pm2 status"

# 재시작만
ssh mint@121.183.229.140 "pm2 restart at-backend at-frontend"

# 로그 확인
ssh mint@121.183.229.140 "pm2 logs --lines 50"
```

## 자동 시작 설정

| 이벤트 | 자동 시작 | 방식 |
|--------|----------|------|
| 시스템 재부팅 | ✅ | systemd (pm2-admin-ubuntu.service) |
| 로그아웃/로그인 | ✅ | ~/.bashrc (pm2 resurrect) |

```bash
# 현재 프로세스 목록 저장 (변경 후 필수)
pm2 save
```

## 설정 파일

- PM2 설정: `ecosystem.config.cjs`
- 저장된 프로세스: `~/.pm2/dump.pm2`
