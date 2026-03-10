#!/bin/bash
# Check status of OVH AI Deploy model server
# Usage: ./ovh-status.sh

set -e

APP_NAME="model-server"

echo "=== OVH AI Deploy Status ==="

APPS=$(ovhai app list --output json 2>/dev/null | python3 -c "
import sys, json
apps = json.load(sys.stdin)
for a in apps:
    if a.get('spec',{}).get('name') == '$APP_NAME':
        state = a.get('status',{}).get('state','?')
        url = a.get('status',{}).get('url','?')
        print(f\"{a['id']}  {state}  {url}\")
" 2>/dev/null || true)

if [ -z "$APPS" ]; then
    echo "No app found. Start with: ./ovh-start.sh"
    exit 0
fi

echo "$APPS"
echo ""

# If running, show model status
URL=$(echo "$APPS" | grep RUNNING | awk '{print $3}' | head -1)
if [ -n "$URL" ]; then
    echo "=== Model Status ==="
    curl -s "$URL/models" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for name, info in data.items():
    dl = info.get('download', {}).get('status', '?')
    loaded = 'LOADED' if info.get('loaded') else ''
    print(f'  {name:20s} {dl:15s} {loaded}')
"
fi
