FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-ml.txt requirements-ml-worker.txt ./
RUN pip install --no-cache-dir -r requirements-ml-worker.txt

RUN addgroup --system icoder-ml && adduser --system --ingroup icoder-ml icoder-ml \
    && mkdir -p /tmp/icoder-ml/huggingface \
    && chown -R icoder-ml:icoder-ml /tmp/icoder-ml
COPY --chown=icoder-ml:icoder-ml . .

ENV MEDCODER_INDEX_DIR=/app/data/medcoder \
    MEDCODER_WORKER_WARMUP=1 \
    MEDCODER_BGE_REVISION=5617a9f61b028005a4858fdac845db406aefb181 \
    MEDCODER_BGE_LOCAL_FILES_ONLY=1 \
    HF_HOME=/tmp/icoder-ml/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:8100/readyz || exit 1

USER icoder-ml

CMD ["uvicorn", "ml_worker.retrieval_app:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
