#!/bin/bash
set -e

# Must be run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

echo "Installing services..."
cp deploy/backend.service /etc/systemd/system/auto_trading_backend.service
cp deploy/frontend.service /etc/systemd/system/auto_trading_frontend.service

systemctl daemon-reload

echo "Enabling and starting services..."
systemctl enable --now auto_trading_backend
systemctl enable --now auto_trading_frontend

echo "Services installed and started!"
systemctl status auto_trading_backend --no-pager
systemctl status auto_trading_frontend --no-pager
