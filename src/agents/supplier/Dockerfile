ARG BASE_IMAGE=zavashop-base:dev
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/kinfey/AKS-Lab-GitHubCopilot"

EXPOSE 8000

CMD ["uvicorn", "src.agents.supplier.server:app", "--host", "0.0.0.0", "--port", "8000"]
