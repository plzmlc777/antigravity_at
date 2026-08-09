# Remote Server Deployment Guide

> 배포 요청 시 Claude가 읽는 참조 문서.

## Safety Rules

- 배포 전 반드시 라이브 세션 확인: `is_paper = f` 실거래 존재 시 사용자 승인 필수
- 배포 전 DB 백업 필수 (최근 2개만 유지)
- 리모트 배포는 사용자 명시적 요청 시에만

## Servers

### 민트 서버 (Real)
> 실거래 운영 + SAS 파이프라인. REAL 모드.
> Claude Code CLI 설치됨 (Max 플랜 인증).

| 항목 | 값 |
|------|-----|
| **접속** | **`ssh mint`** (별칭 전용 — 아래 경고 참조) |
| User | mint |
| Path | ~/auto_trading (= /home/mint/auto_trading) |
| Mode | REAL |
| PM2 | at-backend, at-frontend + 크론 잡 다수 |

> ⚠️ **접속은 `ssh mint` 별칭 하나뿐이다. IP 를 직접 치지 말 것.**
> `~/.ssh/config` 의 `Host mint` 가 cloudflared ProxyCommand 로 `mint.n7n.uk` 를
> 경유한다. `ssh mint@183.99.228.81` 은 그 규칙에 매칭되지 않아 프록시를 안 타고,
> **응답 없이 멈춘다** (2026-08-09 실측: ping 0.8ms 정상 · 포트 22 OPEN 인데도 무응답).
> 서버는 멀쩡한데 접속만 안 되므로 **Mint 장애로 오진하기 쉽다.**
> `ssh mint` 가 실패하면 그때는 cloudflared/터널 문제이지 서버 문제가 아니다 —
> `/home/hcpark/.cloudflared/mint-ssh.env` 와 `cloudflared` 바이너리를 먼저 확인한다.

```bash
# 라이브 세션 확인
ssh mint 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db -c "SELECT id, symbol, status, is_paper FROM live_bot_sessions WHERE status = '\''RUNNING'\'';"'

# DB 백업
ssh mint 'PGPASSWORD=antigravity_password pg_dump -U antigravity_user -h localhost antigravity_db > ~/db_backup_$(date +%Y%m%d_%H%M%S).dump && ls -t ~/db_backup*.dump | tail -n +3 | xargs -r rm -v'

# Quick Deploy
ssh mint "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"

# Full Deploy (with SAS agents)
ssh mint "cd ~/auto_trading && git pull origin master && cd backend && python3 -m migrations.run_migrations && cd .. && ENABLE_AGENTS=1 pm2 restart ecosystem.config.cjs"

# Verify
ssh mint "curl -s http://localhost:8001/api/v1/system/version"

# 세션 복원 확인
ssh mint 'pm2 logs at-backend --lines 30 --nostream 2>&1 | grep -i "restore\|session\|RUNNING"'
```

> **긴 쿼리는 ssh 인라인으로 돌리지 말 것.** Mint 의 `ohlcv` 는 24GB 라
> `GROUP BY symbol` 류 전체 스캔이 9분을 넘겨 죽는다. 인덱스
> `ohlcv_symbol_tf_ts_uniq (symbol, time_frame, timestamp)` 를 타도록 종목별
> `WHERE symbol=:s` 로 나누고, 오래 걸리는 조사는
> `ssh mint 'nohup ... > /tmp/out 2>&1 &'` 로 띄운 뒤 파일을 읽는다.

### 우분투 서버 (Test: 172.30.1.60)
> 테스트 전용. MOCK 모드. 사설IP (공유기 내부). 실거래 세션 체크 불필요.
>
> ⚠️ **2026-08-09 확인: 도달 불가** (ping 100% loss, 포트 22 `No route to host`).
> 전원이 꺼져 있거나 네트워크에서 빠진 상태다. 배포 전에 도달 여부부터 확인할 것.
> 배포 대상은 민트다 (메모리 `feedback_deploy_mint`).

| 항목 | 값 |
|------|-----|
| Host | 172.30.1.60 (ssh config 별칭 없음 — `ssh ubuntu@172.30.1.60`) |
| User | ubuntu |
| Path | ~/auto_trading |
| Mode | MOCK |
| PM2 | at-backend, at-frontend만 |

```bash
# 도달 확인 (먼저)
ping -c 2 -W 2 172.30.1.60

# Quick Deploy
ssh ubuntu@172.30.1.60 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend"

# Verify
ssh ubuntu@172.30.1.60 "curl -s http://localhost:8001/api/v1/system/version"
```

## Emergency Recovery

```bash
# 세션 복원 실패 시 백엔드 재시작
ssh <server> 'pm2 restart at-backend && sleep 5 && pm2 logs at-backend --lines 50 --nostream'

# DB 복구
ssh <server> 'ls -la ~/db_backup*.dump'
ssh <server> 'PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost antigravity_db < ~/db_backup_<timestamp>.dump'
```

## Troubleshooting

> `<server>` 자리에 민트는 **`mint`** 를 넣는다 (IP 아님).

```bash
# SSH host key 오류 — 민트는 이 방법이 안 통한다.
# 민트는 cloudflared 프록시 경유라 ssh-keyscan 대상이 아니고, ssh config 에
# StrictHostKeyChecking=accept-new 가 이미 걸려 있다. 아래는 우분투 등 직결 호스트용.
ssh-keyscan -H <host> >> ~/.ssh/known_hosts

# WSL Git credential
git config --global credential.helper '/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe'

# 서비스 상태
ssh <server> "pm2 status && pm2 logs --lines 20"
```
