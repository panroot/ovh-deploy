#!/bin/bash
# Stop OVH AI Deploy model server (saves costs, keeps config)
# Usage: ./ovh-stop.sh
#        ./ovh-stop.sh --delete   (full delete, not just stop)

set -e

APP_NAME="model-server"
DELETE_MODE="${1:-}"

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
    if [ "$DELETE_MODE" = "--delete" ]; then
        echo "Deleting app: $APP_ID"
        ovhai app delete "$APP_ID" --force
        echo "Deleted: $APP_ID"
    else
        echo "Stopping app: $APP_ID"
        ovhai app stop "$APP_ID"
        echo "Stopped: $APP_ID (use ovh-start.sh to resume)"
    fi
done

echo ""
echo "GPU costs stopped."
echo "To start again: ./ovh-start.sh"
