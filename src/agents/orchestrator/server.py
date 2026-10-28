"""FastAPI entrypoint for the ZavaShop orchestrator agent."""

from __future__ import annotations

from fastapi import FastAPI

from src.shared.server import make_app
from src.shared.settings import Settings

from .a2a import A2AClient, SpecialistInvoker
from .agent import build_agent
from .contracts import Goal, Plan
from .workflow import build_plan_workflow, execute_plan


def create_app(settings: Settings | None = None, specialist_client: SpecialistInvoker | None = None) -> FastAPI:
    """Create the orchestrator app with /invoke and /plan endpoints."""

    app_settings = settings if settings is not None else Settings()
    app = make_app(name="orchestrator", build=build_agent, settings=settings)
    client = specialist_client or A2AClient(settings=app_settings)
    workflow = build_plan_workflow(client)

    @app.post("/plan", response_model=Plan)
    async def plan(goal: Goal) -> Plan:
        return await execute_plan(workflow=workflow, goal=goal)

    app.state.plan_endpoint = plan

    return app


app = create_app()
