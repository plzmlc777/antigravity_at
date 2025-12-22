---
description: Standard protocol for deploying changes to local and remote servers using PM2
---

# Deployment Protocol

This workflow defines the standard operating procedure for developing, testing, and deploying the Auto Trading application.

## 1. Local Development & Testing

1.  **Start Services**:
    Always use PM2 to manage services locally to match the server environment.
    ```bash
    pm2 start ecosystem.config.cjs
    ```

2.  **Verify Status**:
    ```bash
    pm2 status
    ```
    Ensure `at-backend` and `at-frontend` are 'online'.

3.  **Apply Changes**:
    When code is changed, PM2 usually auto-reloads the backend (python).
    For frontend, Vite HMR handles it. If issues arise:
    ```bash
    pm2 restart all
    ```

4.  **Check Logs**:
    ```bash
    pm2 logs
    ```

## 2. Pushing Changes

Once local verification is complete:

1.  **Commit & Push**:
    ```bash
    git add .
    git commit -m "Description of changes"
    git push
    ```

## 3. Remote Server Deployment

On the remote server:

1.  **Execute Deployment Script**:
    The strictly standardized way to deploy is running the provided script. Do not manually pull or restart services piecemeal unless debugging.
    ```bash
    ./deploy_with_pm2.sh
    ```
    
    **What this script does:**
    - `git pull`: Fetches latest code.
    - Checks/Installs `pm2`.
    - Installs Python dependencies (`requirements.txt`).
    - Installs Node dependencies (`npm install`).
    - `pm2 start ecosystem.config.cjs` & `pm2 save`: Restarts services and saves state.

## 4. Configuration Standards

- **Backend**: Uses `/usr/bin/python3` (System Python), NOT venv. Dependencies are installed with `--break-system-packages` or globally as per environment support.
- **Frontend**: Runs via `npm run dev` (Vite) managed by PM2.
- **Ports**:
    - Frontend: 5173
    - Backend: 8001
- **PM2 Config**: Always maintained in `ecosystem.config.cjs`.
