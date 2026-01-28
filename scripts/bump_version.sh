#!/bin/bash
# Version Bump + Deploy Script
# Updates version in both backend & frontend, commits, pushes, and restarts services.
#
# Usage:
#   ./scripts/bump_version.sh 0.9.9.8           # bump + commit + push + restart
#   ./scripts/bump_version.sh 0.9.9.8 --no-push # bump + commit + restart (no push)
#   ./scripts/bump_version.sh --restart          # restart services only (no version change)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PM2="$ROOT_DIR/tools/node/bin/pm2"

# --restart flag: just restart PM2 services, no version change
if [ "$1" = "--restart" ]; then
    echo "=== PM2 Restart Only ==="
    "$PM2" restart at-backend at-frontend
    "$PM2" list
    echo "Done."
    exit 0
fi

if [ -z "$1" ]; then
    # No version given: show current version and usage
    CURRENT=$(grep 'PROJECT_VERSION' "$ROOT_DIR/backend/app/core/config.py" | sed 's/.*"\(.*\)"/\1/')
    echo "Current version: $CURRENT"
    echo ""
    echo "Usage:"
    echo "  $0 <new_version>           # bump + commit + push + restart"
    echo "  $0 <new_version> --no-push # bump + commit + restart (skip push)"
    echo "  $0 --restart               # restart services only"
    exit 0
fi

NEW_VERSION="$1"
NO_PUSH=false
[ "$2" = "--no-push" ] && NO_PUSH=true

echo "=== Version Bump: $NEW_VERSION ==="

# 1. Update backend config.py
echo "[1/5] Updating backend config.py..."
sed -i "s/PROJECT_VERSION: str = \".*\"/PROJECT_VERSION: str = \"$NEW_VERSION\"/" "$ROOT_DIR/backend/app/core/config.py"

# 2. Update frontend package.json
echo "[2/5] Updating frontend package.json..."
sed -i "s/\"version\": \".*\"/\"version\": \"$NEW_VERSION\"/" "$ROOT_DIR/frontend/package.json"

# 3. Git commit + tag
echo "[3/5] Git commit + tag..."
cd "$ROOT_DIR"
git add backend/app/core/config.py frontend/package.json
git commit -m "v$NEW_VERSION: Version bump"
git tag -f "v$NEW_VERSION"

# 4. Git push
if [ "$NO_PUSH" = true ]; then
    echo "[4/5] Skipping push (--no-push)"
else
    echo "[4/5] Pushing to origin..."
    git push origin master --tags
fi

# 5. PM2 restart
echo "[5/5] Restarting PM2 services..."
"$PM2" restart at-backend at-frontend
"$PM2" list

echo ""
echo "=== v$NEW_VERSION deployed ==="
