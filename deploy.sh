#!/bin/bash
# deploy.sh

echo "Deploying updates..."

# 1. Restart Backend (FastAPI)
echo "Restarting Backend..."
pkill -f "uvicorn app.main:app" || true
# Wait for port release
sleep 2
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
echo "Backend restarted on port 8000"

# 2. Restart Frontend (React)
echo "Restarting Frontend..."
# Usually frontend is served via npm start or build+serve.
# Assuming dev mode for now per context.
cd frontend
# Check if node is running
pkill -f "react-scripts start" || true
sleep 2
nohup npm start > frontend.log 2>&1 &
echo "Frontend restarted on port 3000"

echo "Deployment Complete."
