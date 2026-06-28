FROM python:3.11-slim AS builder

ENV UV_SYSTEM_PYTHON=1
RUN python -m pip install --no-cache-dir uv
RUN uv pip install --system mcp pydantic structlog

FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/kinfey/AKS-Lab-GitHubCopilot"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd -m -u 10001 zava
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY src /app/src

USER zava
EXPOSE 8080

CMD ["python", "-m", "src.mcp_servers.inventory.server"]