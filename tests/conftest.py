"""Shared pytest configuration for ZavaShop tests."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mock_copilot_client() -> object:
    return object()


@pytest.fixture(autouse=True)
def mock_copilot_import_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from constructing a real Copilot client or agent."""

    mock_chat_client = cast("type[Any]", importlib.import_module("tests.agents._mock").MockChatClient)
    agent_modules = (
        "src.agents.inventory.agent",
        "src.agents.supplier.agent",
        "src.agents.logistics.agent",
        "src.agents.pricing.agent",
        "src.agents.orchestrator.agent",
    )
    for module_name in agent_modules:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, "GitHubCopilotAgent", mock_chat_client)
        monkeypatch.setattr(module, "build_copilot_client", _mock_copilot_client)
