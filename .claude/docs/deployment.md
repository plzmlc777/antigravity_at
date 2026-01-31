---
description: Standard protocol for deploying changes to local and remote servers using PM2
---

# Deployment Protocol

This workflow defines the standard operating procedure for developing, testing, and deploying the Auto Trading application.

## 1. Local Development & Testing

모든 명령은 `auto_trading/` 디렉토리에서 실행:

1.  **Start Services (Unified Script)**:
    ```bash
    ./deploy_with_pm2.sh
    ```

2.  **Verify Status**:
    ```bash
    npm run status
    # 또는: pm2 status
    ```
    Ensure `at-backend` and `at-frontend` are 'online'.

3.  **Apply Changes / Restart**:
    ```bash
    npm run restart
    # 또는: pm2 restart all

    # 개별 재시작
    ./tools/node/bin/pm2 restart at-backend
    ./tools/node/bin/pm2 restart at-frontend
    ```

4.  **Check Logs**:
    ```bash
    npm run logs
    # 또는: pm2 logs
    ```

## 2. Checkpoints & Pushing Changes

**CRITICAL RULE**: Before starting *any* new major task or after completing a significant feature/fix, YOU MUST CREATE A GIT TAG.

1.  **Commit Changes**:
    ```bash
    git add .
    git commit -m "Description of changes"
    ```

2.  **Create Tag (Rollback Point)**:
    ```bash
    # Format: v[Major].[Minor].[Patch]-[feature]-[status]
    git tag -a v1.x.x-feature-name -m "Validated checkpoint"
    ```

3.  **Push Code & Tags**:
    ```bash
    git push origin master
    git push --tags
    ```

## 3. Remote Server Deployment (SSH Direct)

> [!IMPORTANT]
> 로컬에서 SSH로 직접 리모트 서버에 접속하여 배포합니다.

### Remote Server Info

| 항목 | 값 |
|------|-----|
| Host | 121.183.229.140 |
| User | mint |
| Path | ~/auto_trading |
| PM2 | /usr/local/bin/pm2 (global) |

### Quick Deploy (One-liner)

```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pm2 restart at-backend at-frontend && pm2 status"
```

### Step-by-Step Deploy

1. **Pull Latest Code**:
    ```bash
    ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master"
    ```

2. **Restart Services**:
    ```bash
    ssh mint@121.183.229.140 "pm2 restart at-backend at-frontend"
    ```

3. **Verify Status**:
    ```bash
    ssh mint@121.183.229.140 "pm2 status"
    ```

4. **Check Logs (if needed)**:
    ```bash
    ssh mint@121.183.229.140 "pm2 logs --lines 50"
    ```

### Full Deploy (with dependencies)

Dependencies가 변경된 경우:

```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git pull origin master && pip3 install -r requirements.txt && npm install && pm2 restart at-backend at-frontend"
```

## 4. Configuration Standards

- **Backend**: Uses `/usr/bin/python3` (System Python)
- **Frontend**: Runs via `npm run dev` (Vite) managed by PM2
- **Ports**:
    - Frontend: 5173
    - Backend: 8001
- **PM2 Config**: `ecosystem.config.cjs`

## 5. Auto-Start Configuration

| 이벤트 | 자동 시작 | 방식 |
|--------|----------|------|
| 시스템 재부팅 | ✅ | systemd (pm2-admin-ubuntu.service) |
| 로그아웃/로그인 | ✅ | ~/.bashrc (pm2 resurrect) |

```bash
# 현재 프로세스 목록 저장 (설정 변경 후 필수)
pm2 save

# 저장된 프로세스 파일: ~/.pm2/dump.pm2
```

## 6. Troubleshooting

### SSH 접속 실패

SSH 키가 등록되어 있어야 합니다:
```bash
# 로컬 공개키 확인
cat ~/.ssh/id_ed25519.pub

# 리모트에 등록 (최초 1회)
ssh mint@121.183.229.140 "mkdir -p ~/.ssh && echo 'YOUR_PUBLIC_KEY' >> ~/.ssh/authorized_keys"
```

### 서비스 상태 확인

```bash
ssh mint@121.183.229.140 "pm2 status && pm2 logs --lines 20"
```

### 브랜치 불일치

리모트 서버는 항상 `master` 브랜치를 사용합니다:
```bash
ssh mint@121.183.229.140 "cd ~/auto_trading && git branch && git status"
```
