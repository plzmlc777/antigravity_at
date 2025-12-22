#!/bin/bash
# Script to start the backend server
# Make sure you have edited .env file first!

cd backend

# Ensure .env exists for the backend
cp ../.env .env

# Add user-site bin to PATH to ensure uvicorn is found
export PATH=$PATH:$HOME/.local/bin

# Run Uvicorn using python3 (user installed packages)
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
