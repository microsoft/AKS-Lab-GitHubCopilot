"""FastAPI entrypoint for the ZavaShop logistics specialist agent."""

from __future__ import annotations

from src.shared.server import make_app

from .agent import build_agent

app = make_app(name="logistics", build=build_agent)
