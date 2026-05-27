# ============================================================
# Backend Dockerfile — AI Landing Page Generator
# Python 3.11 + PyTorch (CUDA) + ML dependencies
# ============================================================

# ------------------------------------
# Stage 1: Builder — install dependencies
# ------------------------------------
FROM python:3.11-slim AS builder

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create and activate a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip

# ------------------------------------
# Install PyTorch with CUDA 12.1 support
# (matches RTX 4090 / A100 / H100 requirements from design doc)
# ------------------------------------
RUN pip install --no-cache-dir \
    torch==2.2.2+cu121 \
    torchvision==0.17.2+cu121 \
    torchaudio==2.2.2+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# ------------------------------------
# Install ML / AI dependencies
# ------------------------------------
RUN pip install --no-cache-dir \
    # HuggingFace ecosystem
    transformers==4.40.2 \
    peft==0.10.0 \
    accelerate==0.29.3 \
    datasets==2.19.1 \
    tokenizers==0.19.1 \
    huggingface-hub==0.23.0 \
    # Quantization (QLoRA support)
    bitsandbytes==0.43.1 \
    # Sentence embeddings (NLP Engine)
    sentence-transformers==2.7.0 \
    # LangChain (NLP Engine orchestration)
    langchain==0.1.20 \
    langchain-community==0.0.38 \
    # JSON schema validation (Model Engine)
    jsonschema==4.22.0

# ------------------------------------
# Install API / web dependencies
# ------------------------------------
RUN pip install --no-cache-dir \
    # FastAPI + ASGI server
    fastapi==0.111.0 \
    uvicorn[standard]==0.29.0 \
    # Async task queue
    celery[redis]==5.3.6 \
    redis==5.0.4 \
    # Database
    sqlalchemy==2.0.30 \
    alembic==1.13.1 \
    asyncpg==0.29.0 \
    psycopg2-binary==2.9.9 \
    # Pydantic v2 + settings
    pydantic==2.7.1 \
    pydantic-settings==2.2.1 \
    # Authentication
    python-jose[cryptography]==3.3.0 \
    passlib[bcrypt,argon2]==1.7.4 \
    # HTTP client
    httpx==0.27.0 \
    # HTML sanitization (OWASP allowlist)
    nh3==0.2.17 \
    bleach==6.1.0 \
    # CSS minification
    csscompressor==0.9.5 \
    # Multipart form data
    python-multipart==0.0.9

# ------------------------------------
# Install Vector Database clients
# ------------------------------------
RUN pip install --no-cache-dir \
    qdrant-client==1.9.1 \
    chromadb==0.5.0 \
    weaviate-client==4.6.1

# ------------------------------------
# Install testing dependencies
# ------------------------------------
RUN pip install --no-cache-dir \
    pytest==8.2.0 \
    pytest-asyncio==0.23.6 \
    pytest-cov==5.0.0 \
    hypothesis==6.100.2 \
    httpx==0.27.0

# ============================================================
# Stage 2: Runtime image
# ============================================================
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # CUDA / PyTorch settings
    CUDA_VISIBLE_DEVICES=0 \
    TORCH_DTYPE=float16

# Install Python 3.11 and runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-distutils \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create non-root user for security
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Create application directories
RUN mkdir -p /app /models/adapters /models/checkpoints \
    && chown -R appuser:appgroup /app /models

WORKDIR /app

# Copy application source code
COPY --chown=appuser:appgroup . .

# Switch to non-root user
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: run FastAPI with uvicorn
# Override in docker-compose for Celery workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
