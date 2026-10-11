FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy only the application sources and package metadata. Runtime data is mounted
# as a volume by Compose and is intentionally excluded from the build context.
COPY pyproject.toml README.md ./
COPY app ./app
COPY scripts ./scripts

RUN python -m pip install --upgrade pip && python -m pip install .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# Binding to all interfaces is required inside the container. Compose publishes
# the container port only on the host loopback interface.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
