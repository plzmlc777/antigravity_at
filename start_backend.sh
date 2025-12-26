#!/bin/bash
# Script to start the backend server
# Make sure you have edited .env file first!

cd backend

# Ensure .env exists for the backend
cp ../.env .env

# Source env vars to get BACKEND_PORT
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PORT=${BACKEND_PORT:-8001}

# Add user-site bin to PATH to# Run Uvicorn directly (dependencies installed globally/user-wide)
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload > ../backend.log 2>&1 &
