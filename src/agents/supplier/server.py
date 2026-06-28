"""FastAPI entrypoint for the ZavaShop supplier specialist agent."""

from __future__ import annotations

from src.shared.server import make_app

from .agent import build_agent

app = make_app(name="supplier", build=build_agent)
