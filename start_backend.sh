#!/bin/bash
# Script to start the backend server
# Make sure you have edited .env file first!

cd backend
# Use the local pip/python if venv is missing, or activate venv if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Ensure .env exists for the backend
cp ../.env .env

# Run Uvicorn
/home/admin-ubuntu/.local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
