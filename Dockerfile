FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV MODEL_DIR=/workspace/models
ENV HF_HOME=/workspace/hf_cache
ENV TRANSFORMERS_CACHE=/workspace/hf_cache

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    curl \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Install pip
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11

# Python dependencies
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Application code
COPY app/ /app/
COPY scripts/ /scripts/
RUN chmod +x /scripts/*.sh

# Writable dirs for non-root (OVH uid 42420)
RUN mkdir -p ${MODEL_DIR} ${HF_HOME} \
    && chmod -R 777 ${MODEL_DIR} ${HF_HOME} /app /scripts

WORKDIR /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["/scripts/start.sh"]
