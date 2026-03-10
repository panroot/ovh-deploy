#!/bin/bash
set -e

echo "=== OVH AI Deploy - Model Server ==="
echo "Model directory: ${MODEL_DIR:-/workspace/models}"
echo "GPU info:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "No GPU detected"

# Start FastAPI directly on 8080
echo "Starting model server on port 8080..."
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --workers 1 \
    --timeout-keep-alive 600 \
    --log-level info
