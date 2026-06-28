ARG GIT_SHA
FROM zavashop-base:${GIT_SHA}

LABEL org.opencontainers.image.source="https://github.com/kinfey/AKS-Lab-GitHubCopilot"

EXPOSE 8000

CMD ["uvicorn", "src.agents.orchestrator.server:app", "--host", "0.0.0.0", "--port", "8000"]
