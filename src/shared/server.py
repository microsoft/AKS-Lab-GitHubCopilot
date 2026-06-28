"""Reusable FastAPI server factory for ZavaShop agents."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Protocol
from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from structlog.contextvars import bind_contextvars, clear_contextvars

from .settings import Settings
from .telemetry import setup_tracing

log = structlog.get_logger(__name__)


class InvokeRequest(BaseModel):
    """A2A request envelope for invoking one agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=64, description="Caller-provided run identifier.")
    goal: str = Field(min_length=1, max_length=4000, description="Goal text for the agent.")
    context: dict[str, str] = Field(default_factory=dict, description="Optional string context for the run.")


class InvokeResponse(BaseModel):
    """A2A response envelope returned by one agent."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(description="Run identifier copied from the request.")
    output: str = Field(description="Agent output text.")
    tool_calls: list[str] = Field(default_factory=list, description="Tool names observed during the run.")


class HealthResponse(BaseModel):
    """Health probe response."""

    model_config = ConfigDict(frozen=True)

    status: str


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    model_config = ConfigDict(frozen=True)

    status: str
    name: str


class _RunResult(Protocol):
    output_text: str


class _Runnable(Protocol):
    async def run(self, message: str, /) -> _RunResult: ...


AgentBuilder = Callable[[Settings], Awaitable[_Runnable]]


def make_app(*, name: str, build: AgentBuilder, settings: Settings | None = None) -> FastAPI:
    """Create a reusable FastAPI app for a ZavaShop agent.

    Args:
        name: Service name used in logs and readiness output.
        build: Async factory that constructs a runnable agent from settings.
        settings: Optional settings override for tests.
    Returns:
        FastAPI app exposing /healthz, /readyz, and /invoke.
    """

    app_settings = settings or Settings()
    agent: _Runnable | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        nonlocal agent
        setup_tracing(service_name=name)
        log.info("agent.startup.begin", agent_name=name)
        agent = await build(app_settings)
        log.info("agent.startup.end", agent_name=name)
        yield

    app = FastAPI(title=f"ZavaShop {name}", lifespan=lifespan)

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/readyz", response_model=ReadinessResponse)
    async def readyz() -> ReadinessResponse:
        if agent is None:
            raise HTTPException(status_code=503, detail="agent not ready")
        return ReadinessResponse(status="ready", name=name)

    @app.post("/invoke", response_model=InvokeResponse)
    async def invoke(request: InvokeRequest) -> InvokeResponse:
        if agent is None:
            raise HTTPException(status_code=503, detail="agent not ready")
        span_id = uuid4().hex[:16]
        bind_contextvars(agent_name=name, run_id=request.run_id, span_id=span_id)
        try:
            log.info("agent.run.begin", goal=request.goal)
            result = await agent.run(request.goal)
            log.info("agent.run.end")
            return InvokeResponse(run_id=request.run_id, output=result.output_text)
        except Exception as exc:
            log.error("agent.run.error", error=str(exc))
            raise HTTPException(status_code=502, detail="agent run failed") from exc
        finally:
            clear_contextvars()

    app.state.healthz_endpoint = healthz
    app.state.readyz_endpoint = readyz
    app.state.invoke_endpoint = invoke

    return app
