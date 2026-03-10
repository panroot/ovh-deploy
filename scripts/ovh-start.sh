#!/bin/bash
# Start OVH AI Deploy model server
# Usage: ./ovh-start.sh

set -e

APP_NAME="model-server"
IMAGE="ghcr.io/panroot/ovh-deploy:latest"
FLAVOR="l40s-1-gpu"
HF_TOKEN="${HF_TOKEN:-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}"

echo "=== Starting OVH AI Deploy: $APP_NAME ==="

# Check if already running
EXISTING=$(ovhai app list --output json 2>/dev/null | python3 -c "
import sys, json
apps = json.load(sys.stdin)
for a in apps:
    if a.get('spec',{}).get('name') == '$APP_NAME' and a.get('status',{}).get('state') in ('RUNNING','SCALING','QUEUED','INITIALIZING'):
        print(a['id'])
        break
" 2>/dev/null || true)

if [ -n "$EXISTING" ]; then
    URL=$(ovhai app get "$EXISTING" --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['url'])")
    echo "Already running: $URL"
    echo "App ID: $EXISTING"
    exit 0
fi

# Create new app
echo "Creating new app..."
ovhai app run \
    --name "$APP_NAME" \
    --flavor "$FLAVOR" \
    --gpu 1 \
    --default-http-port 8080 \
    --unsecure-http \
    --env "HF_TOKEN=$HF_TOKEN" \
    "$IMAGE" \
    --output json > /tmp/ovh-app-result.json

APP_ID=$(python3 -c "import json; d=json.load(open('/tmp/ovh-app-result.json')); print(d['id'])")
APP_URL=$(python3 -c "import json; d=json.load(open('/tmp/ovh-app-result.json')); print(d['status']['url'])")

echo "App created!"
echo "ID:  $APP_ID"
echo "URL: $APP_URL"
echo ""
echo "Waiting for RUNNING state..."

for i in $(seq 1 60); do
    STATE=$(ovhai app get "$APP_ID" --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['state'])")
    if [ "$STATE" = "RUNNING" ]; then
        echo "App is RUNNING!"
        echo "URL: $APP_URL"
        echo "Models downloading in background. Check: curl $APP_URL/models"
        exit 0
    fi
    echo "  State: $STATE (waiting...)"
    sleep 10
done

echo "Timeout waiting for app to start. Check: ovhai app get $APP_ID"
