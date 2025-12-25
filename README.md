# Auto Trading System

A comprehensive automated trading system with Python FastAPI backend and React frontend.

## 🏗 Architecture

- **Backend**: Python 3 (FastAPI, Uvicorn)
- **Frontend**: React (Vite)
- **Process Management**: PM2 (Standardized for both Local & Server)

## 🚀 Getting Started

We use a unified script for local development and server deployment.

### 1. Start System
Run the following command in the project root:
```bash
./deploy_with_pm2.sh
```
This script will:
- Install/Update `pm2` automatically (using local tools if needed).
- Install dependencies (Python & Node).
- Start Backend (Port 8001) and Frontend (Port 5173).

### 2. Access Dashboard
- **Local**: http://localhost:5173
- **Server**: http://[YOUR_SERVER_IP]:5173

## 📂 Project Structure
- `backend/`: API Server and Trading Logic using Kiwoom API.
- `frontend/`: React Dashboard.
- `tools/`: Local Node.js binaries for portable execution.
- `deploy/`: Deployment resources (Systemd scripts are DEPRECATED).
