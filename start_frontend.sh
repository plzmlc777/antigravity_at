#!/bin/bash
# Script to start the React Frontend

cd frontend
npm install # Ensure dependencies are installed
npm run dev -- --host 0.0.0.0
