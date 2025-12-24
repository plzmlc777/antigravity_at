#!/bin/bash
set -e

# Must be run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

# Detect actual user (who ran sudo)
TARGET_USER=${SUDO_USER:-$USER}
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
PROJECT_ROOT=$(pwd)

echo "=== Deployment Configuration ==="
echo "Detected User: $TARGET_USER"
echo "Detected Home: $TARGET_HOME"
echo "Project Root : $PROJECT_ROOT"
echo "================================"

echo "Installing services..."

# Function to generate and install service file
install_service() {
    SRC=$1
    DEST=$2
    
    echo "Processing $SRC -> $DEST"
    
    # Use sed to replace hardcoded paths and users
    # 1. Replace Project Root (longer path first)
    # 2. Replace Home Directory
    # 3. Replace Username
    
    # We use | as delimiter to avoid conflicting with path slashes
    sed -e "s|/home/admin-ubuntu/ai/antigravity/auto_trading|$PROJECT_ROOT|g" \
        -e "s|/home/admin-ubuntu|$TARGET_HOME|g" \
        -e "s|User=admin-ubuntu|User=$TARGET_USER|g" \
        "$SRC" > "$DEST"
        
    # Heuristic: If venv exists, try to adjust python paths if they look like system paths
    if [ -d "$PROJECT_ROOT/venv" ]; then
        echo "  - venv detected. Adjusting ExecStart to prefer venv..."
        # Replace .local/bin/uvicorn with venv/bin/uvicorn
        sed -i "s|$TARGET_HOME/.local/bin/uvicorn|$PROJECT_ROOT/venv/bin/uvicorn|g" "$DEST"
        # Also generic python3
        sed -i "s|/usr/bin/python3|$PROJECT_ROOT/venv/bin/python3|g" "$DEST"
    fi

    # Heuristic: Fix npm path (Frontend)
    # Check if the hardcoded local path exists. If not, use system npm.
    if [[ "$DEST" == *"frontend"* ]]; then
        # Check standard system npm location for the target user
        # We can't easily run 'which' for the target user specifically without sudo complexity,
        # so we check common locations.
        DEFAULT_NPM=$(which npm || echo "/usr/bin/npm")
        
        # If the script refers to the 'tools/node' path and it doesn't exist, replace with system npm
        if ! [ -f "$PROJECT_ROOT/tools/node/bin/npm" ]; then
             echo "  - Custom node path not found. Replacing with system npm: $DEFAULT_NPM"
             # Escape slashes for sed
             ESCAPED_NPM=$(echo "$DEFAULT_NPM" | sed 's|/|\\/|g')
             # Replace the specific local path pattern we know
             sed -i "s|.*npm |$ESCAPED_NPM |g" "$DEST"
        fi
    fi
}

install_service "deploy/backend.service" "/etc/systemd/system/auto_trading_backend.service"
install_service "deploy/frontend.service" "/etc/systemd/system/auto_trading_frontend.service"

systemctl daemon-reload

echo "Enabling and starting services..."
systemctl enable --now auto_trading_backend
systemctl enable --now auto_trading_frontend

echo "Services installed and started!"
echo "--- Backend Status ---"
systemctl status auto_trading_backend --no-pager
echo "--- Frontend Status ---"
systemctl status auto_trading_frontend --no-pager
