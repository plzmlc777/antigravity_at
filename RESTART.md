# 서비스 재시작 매뉴얼 (PM2)

## 빠른 재시작 (권장)

```bash
cd /home/admin-ubuntu/ai/antigravity/auto_trading
./scripts/bump_version.sh --restart
```

## PM2 명령어

모든 명령은 `auto_trading/` 디렉토리에서 실행:

```bash
cd /home/admin-ubuntu/ai/antigravity/auto_trading

# 전체 재시작
npm run restart

# 상태 확인
npm run status

# 로그 확인
npm run logs

# 모니터링
npm run monit

# 전체 중지
npm run stop
```

## 개별 재시작

```bash
cd /home/admin-ubuntu/ai/antigravity/auto_trading

# 백엔드만 재시작
./tools/node/bin/pm2 restart at-backend

# 프론트엔드만 재시작
./tools/node/bin/pm2 restart at-frontend
```

## 버전업과 함께 재시작

```bash
# 버전업 + 커밋 + 태그 + 푸시 + PM2 재시작
./scripts/bump_version.sh 0.9.9.32
```

## 자동 시작 설정

서비스는 다음 상황에서 자동으로 시작됩니다:

| 이벤트 | 자동 시작 | 방식 |
|--------|----------|------|
| 시스템 재부팅 | ✅ | systemd (pm2-admin-ubuntu.service) |
| 로그아웃/로그인 | ✅ | ~/.bashrc (pm2 resurrect) |

```bash
# 현재 프로세스 목록 저장 (변경 후 필수)
pm2 save

# 자동 시작 설정 확인
systemctl status pm2-admin-ubuntu

# 자동 시작 제거 (필요시)
pm2 unstartup systemd
```

## 설정 파일

- PM2 설정: `ecosystem.config.cjs`
- 저장된 프로세스: `~/.pm2/dump.pm2`
