# CrimeCity3K - Container Image
# Self-contained deployment with Python 3.13, application code, and data

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - curl: for container health checks
# - ca-certificates: for HTTPS connections (DuckDB extensions, external APIs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for Python dependency management
RUN pip install --no-cache-dir uv==0.4.30

# Copy project files
COPY pyproject.toml README.md config.toml ./
COPY crimecity3k/ ./crimecity3k/
COPY static/ ./static/

# Copy data files (PMTiles, events parquet, event type mappings)
COPY data/tiles/pmtiles/ ./data/tiles/pmtiles/
COPY data/events.parquet ./data/
COPY data/event_types.toml ./data/

# Install Python dependencies
# Use uv to install from pyproject.toml without creating a virtualenv
# (we're in a container, no need for isolation)
RUN uv pip install --system --no-cache -e .

# Expose application port
EXPOSE 8000

# Health check: verify API is responding and healthy
# Runs every 30 seconds, 3 second timeout, 3 retries before marking unhealthy
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI application with uvicorn
# --host 0.0.0.0: bind to all interfaces (required for container networking)
# --port 8000: application port
# --proxy-headers: read X-Forwarded-For headers from reverse proxy (Caddy)
# --forwarded-allow-ips '*': trust all proxy IPs (safe since bound to 127.0.0.1)
CMD ["uvicorn", "crimecity3k.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
