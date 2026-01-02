#!/bin/bash

# Update code
echo "Updating code from git..."
git pull

# Add local tools to PATH if they exist
export PATH="$(pwd)/tools/node/bin:$PATH"

# Function to install Node.js locally
install_node() {
    echo "⬇️  Installing Node.js v20.10.0..."
    rm -rf tools/node
    mkdir -p tools/node
    # Download and extract (requires tar and xz)
    if curl -L https://nodejs.org/dist/v20.10.0/node-v20.10.0-linux-x64.tar.xz | tar xJ -C tools/node --strip-components=1; then
        echo "✅ Node.js installed successfully."
    else
        echo "❌ Failed to install Node.js."
        exit 1
    fi
    export PATH="$(pwd)/tools/node/bin:$PATH"
}

# Check for npm health
if ! command -v npm &> /dev/null || ! npm --version &> /dev/null; then
    echo "⚠️  npm is corrupted or missing. Attempting auto-repair..."
    install_node
fi

# Check and Install python3-pip
if ! python3 -m pip --version &> /dev/null; then
    echo "python3-pip not found. Installing..."
    sudo apt update && sudo apt install -y python3-pip
fi

# Check and Install PostgreSQL & libpq-dev (Idempotent)
echo "Checking PostgreSQL and libraries..."
if ! dpkg -s postgresql >/dev/null 2>&1 || ! dpkg -s libpq-dev >/dev/null 2>&1; then
    echo "Installing PostgreSQL and libpq-dev..."
    sudo apt update && sudo apt install -y postgresql postgresql-contrib libpq-dev
else
    echo "PostgreSQL and libpq-dev are already installed."
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
echo "Updating backend dependencies (pip)..."
python3 -m pip install -r backend/requirements.txt --break-system-packages 2>/dev/null || python3 -m pip install -r backend/requirements.txt

echo "Updating frontend dependencies (npm)..."
(cd frontend && npm install) || { echo "❌ Frontend install failed"; exit 1; }

# Start/Restart PM2
echo "Restarting services with PM2..."
# Delete old processes to ensure new ecosystem config (interpreter change) is applied
pm2 delete all || true
pm2 start ecosystem.config.cjs
pm2 save

# Show status
pm2 status
