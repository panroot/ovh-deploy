#!/bin/bash
# Standalone model download script - run inside container or as part of build
# Usage: ./download_models.sh [model_name|all]

set -e

MODEL_DIR="${MODEL_DIR:-/workspace/models}"
mkdir -p "$MODEL_DIR"

declare -A MODELS
MODELS[llava-13b]="llava-hf/llava-1.5-13b-hf"
MODELS[flux-schnell]="black-forest-labs/FLUX.1-schnell"
MODELS[flux-klein-4b]="freepik/flux.1-lite-8B-alpha"
MODELS[flux-vae]="black-forest-labs/FLUX.1-schnell"
MODELS[sdxl-base]="stabilityai/stable-diffusion-xl-base-1.0"
MODELS[sd-1.5]="stable-diffusion-v1-5/stable-diffusion-v1-5"
MODELS[birefnet]="ZhengPeng7/BiRefNet"
MODELS[qwen-2.5-14b]="Qwen/Qwen2.5-14B-Instruct"
MODELS[qwen-2.5-32b]="Qwen/Qwen2.5-32B-Instruct"
MODELS[qwen-2.5-72b]="Qwen/Qwen2.5-72B-Instruct"

download_model() {
    local name=$1
    local repo=${MODELS[$name]}

    if [ -z "$repo" ]; then
        echo "ERROR: Unknown model: $name"
        echo "Available: ${!MODELS[*]}"
        return 1
    fi

    local dest="$MODEL_DIR/$name"
    if [ -d "$dest" ] && [ "$(ls -A "$dest" 2>/dev/null)" ]; then
        echo "SKIP: $name already exists at $dest"
        return 0
    fi

    echo "DOWNLOADING: $name from $repo ..."
    huggingface-cli download "$repo" \
        --local-dir "$dest" \
        --exclude "*.md" "*.txt" ".gitattributes"
    echo "DONE: $name"
}

TARGET=${1:-all}

if [ "$TARGET" = "all" ]; then
    echo "=== Downloading ALL models ==="
    for name in "${!MODELS[@]}"; do
        download_model "$name" || true
    done
    echo "=== All downloads complete ==="
else
    download_model "$TARGET"
fi
