#!/bin/bash
# Script to start the React Frontend

# Add local node to PATH
export PATH=$PWD/tools/node/bin:$PATH

cd frontend
npm install # Ensure dependencies are installed
npm run dev -- --host 0.0.0.0
