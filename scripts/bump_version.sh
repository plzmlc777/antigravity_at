#!/bin/bash
# Version Bump Script - Updates version in all locations
# Usage: ./scripts/bump_version.sh 0.9.8.7

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 0.9.8.7"
    exit 1
fi

NEW_VERSION="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Version Bump: $NEW_VERSION ==="

# 1. Update backend/app/core/config.py
echo "[1/4] Updating backend config.py..."
sed -i "s/PROJECT_VERSION: str = \".*\"/PROJECT_VERSION: str = \"$NEW_VERSION\"/" "$ROOT_DIR/backend/app/core/config.py"

# 2. Update frontend/package.json
echo "[2/4] Updating frontend package.json..."
sed -i "s/\"version\": \".*\"/\"version\": \"$NEW_VERSION\"/" "$ROOT_DIR/frontend/package.json"

# 3. Update DB (system_configs table)
echo "[3/4] Updating DB version..."
cd "$ROOT_DIR"
source .env 2>/dev/null || true
PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_SERVER -U $POSTGRES_USER -d $POSTGRES_DB -c \
    "UPDATE system_configs SET value = '$NEW_VERSION', updated_at = NOW() WHERE key = 'app_version';"

# 4. Git commit and tag
echo "[4/4] Creating git commit and tag..."
cd "$ROOT_DIR"
git add backend/app/core/config.py frontend/package.json
git commit -m "$(cat <<EOF
v$NEW_VERSION: Version bump

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
git tag "v$NEW_VERSION"

echo ""
echo "=== Done! ==="
echo "Version updated to: $NEW_VERSION"
echo ""
echo "Next steps:"
echo "  git push origin master --tags"
echo ""
