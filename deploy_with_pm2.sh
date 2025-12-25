#!/bin/bash

# Update code
echo "Updating code from git..."
git pull

# Add local tools to PATH if they exist
export PATH="$(pwd)/tools/node/bin:$PATH"

# Check for npm
if ! command -v npm &> /dev/null; then
    echo "Error: npm is not installed. Please install Node.js and npm."
    exit 1
fi

# Check for python3-pip
if ! python3 -m pip --version &> /dev/null; then
    echo "Error: python3-pip is not installed."
    echo "Please run: sudo apt update && sudo apt install -y python3-pip"
    exit 1
fi

# Check for libpq-dev (Required for psycopg2)
if ! dpkg -s libpq-dev >/dev/null 2>&1; then
    echo "Error: libpq-dev is not installed."
    echo "Please run: sudo apt install -y libpq-dev"
    exit 1
fi

# Install PM2 globally if not installed
if ! command -v pm2 &> /dev/null; then
    echo "PM2 not found. Installing global PM2..."
    # Try with sudo, fallback to local if sudo fails or not needed
    if [ "$EUID" -ne 0 ]; then
        echo "Trying to install PM2 with sudo..."
        sudo npm install -g pm2 || npm install -g pm2
    else
        npm install -g pm2
    fi
fi

# Install dependencies if needed (optional but good practice)
echo "Installing backend dependencies..."
# Backend: system python
python3 -m pip install -r backend/requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r backend/requirements.txt

echo "Installing frontend dependencies..."
cd frontend && npm install && cd ..

# Start PM2
echo "Starting services with PM2..."
pm2 start ecosystem.config.cjs
pm2 save

# Show status
pm2 status
