FROM python:3.11-slim

WORKDIR /app

# Install system dependencies. ffmpeg runs as a bounded decoder subprocess;
# native ASR/ML libraries remain excluded from the API image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy only the API runtime dependency set. Native BGE/FAISS/Torch packages
# live in requirements-ml.txt and must run in a separately scanned worker.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy application
RUN addgroup --system icoder && adduser --system --ingroup icoder icoder
COPY --chown=icoder:icoder . .

# Create data directory
RUN mkdir -p /app/data && chown -R icoder:icoder /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

USER icoder

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
