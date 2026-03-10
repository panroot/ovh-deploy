#!/bin/bash
set -e

echo "=== OVH AI Deploy - Multi-Model Server ==="
echo "Model directory: ${MODEL_DIR:-/workspace/models}"
echo "GPU info:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "No GPU detected"

# Start nginx
echo "Starting nginx..."
nginx

# Start FastAPI
echo "Starting API server on port 8000 (nginx proxy on 8080)..."
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --timeout-keep-alive 600 \
    --log-level info
