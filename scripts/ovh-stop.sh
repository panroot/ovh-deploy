#!/bin/bash
# Stop OVH AI Deploy model server (saves costs)
# Usage: ./ovh-stop.sh

set -e

APP_NAME="model-server"

echo "=== Stopping OVH AI Deploy: $APP_NAME ==="

# Find running apps
APPS=$(ovhai app list --output json 2>/dev/null | python3 -c "
import sys, json
apps = json.load(sys.stdin)
for a in apps:
    if a.get('spec',{}).get('name') == '$APP_NAME' and a.get('status',{}).get('state') not in ('STOPPED','DELETED','FAILED'):
        print(a['id'])
" 2>/dev/null || true)

if [ -z "$APPS" ]; then
    echo "No running app found with name '$APP_NAME'"
    exit 0
fi

for APP_ID in $APPS; do
    echo "Stopping app: $APP_ID"
    ovhai app delete "$APP_ID"
    echo "Stopped: $APP_ID"
done

echo ""
echo "All instances stopped. No more costs."
echo "To start again: ./ovh-start.sh"
