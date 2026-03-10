#!/bin/bash
# Start OVH AI Deploy model server
# Usage: ./ovh-start.sh [IDLE_TIMEOUT_MIN] [MAX_UPTIME_MIN]
# Example: ./ovh-start.sh 30 480   (30min idle, 8h max)
# Example: ./ovh-start.sh 60 120   (1h idle, 2h max)

set -e

APP_NAME="model-server"
IMAGE="ghcr.io/panroot/ovh-deploy:latest"
FLAVOR="l40s-1-gpu"
HF_TOKEN="${HF_TOKEN:-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}"
IDLE_TIMEOUT="${1:-30}"    # domyslnie 30 min
MAX_UPTIME="${2:-480}"     # domyslnie 8h (480 min)

echo "=== Starting OVH AI Deploy: $APP_NAME ==="
echo "Auto-shutdown: idle=${IDLE_TIMEOUT}min, max=${MAX_UPTIME}min"

# Check if already running
RUNNING_ID=$(ovhai app list --output json 2>/dev/null | python3 -c "
import sys, json
apps = json.load(sys.stdin)
for a in apps:
    if a.get('spec',{}).get('name') == '$APP_NAME' and a.get('status',{}).get('state') in ('RUNNING','SCALING','QUEUED','INITIALIZING'):
        print(a['id'])
        break
" 2>/dev/null || true)

if [ -n "$RUNNING_ID" ]; then
    URL=$(ovhai app get "$RUNNING_ID" --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['url'])")
    echo "Already running: $URL"
    echo "App ID: $RUNNING_ID"
    exit 0
fi

# Check if STOPPED instance exists - just start it
STOPPED_ID=$(ovhai app list -s STOPPED,FAILED --output json 2>/dev/null | python3 -c "
import sys, json
apps = json.load(sys.stdin)
for a in apps:
    if a.get('spec',{}).get('name') == '$APP_NAME':
        print(a['id'])
        break
" 2>/dev/null || true)

if [ -n "$STOPPED_ID" ]; then
    echo "Found stopped instance: $STOPPED_ID"
    echo "Starting..."
    ovhai app start "$STOPPED_ID"

    for i in $(seq 1 60); do
        STATE=$(ovhai app get "$STOPPED_ID" --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['state'])")
        if [ "$STATE" = "RUNNING" ]; then
            URL=$(ovhai app get "$STOPPED_ID" --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['status']['url'])")
            echo "App is RUNNING!"
            echo "URL: $URL"
            echo "App ID: $STOPPED_ID"
            exit 0
        fi
        echo "  State: $STATE (waiting...)"
        sleep 5
    done
    echo "Timeout. Check: ovhai app get $STOPPED_ID"
    exit 1
fi

# No existing app - create new one
echo "Creating new app with persistent storage..."
ovhai app run \
    --name "$APP_NAME" \
    --flavor "$FLAVOR" \
    --gpu 1 \
    --default-http-port 8080 \
    --unsecure-http \
    --env "HF_TOKEN=$HF_TOKEN" \
    --env "IDLE_TIMEOUT=$IDLE_TIMEOUT" \
    --env "MAX_UPTIME=$MAX_UPTIME" \
    --volume ai-models@GRA:/workspace/models:rw:cache \
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
        echo "Models ready. Check: curl $APP_URL/models"
        exit 0
    fi
    echo "  State: $STATE (waiting...)"
    sleep 5
done

echo "Timeout waiting for app to start. Check: ovhai app get $APP_ID"
