"""Unit tests for the ZavaShop orchestrator agent."""

from __future__ import annotations

import pytest

from src.agents.orchestrator.agent import build_agent
from src.shared.settings import Settings
from tests.agents._mock import MockChatClient, captured_options


async def test_orchestrator_agent_uses_copilot_with_a2a_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"summary":"ok"}'])
    monkeypatch.setattr("src.agents.orchestrator.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())
    response = await agent.run("Build a plan for SKU ZS-1042 at store-101.")
    options = captured_options()

    assert "summary" in response.output_text
    assert "gpt-5.5" == options.get("model")
    assert "mcp_servers" not in options
    assert MockChatClient.messages == ["Build a plan for SKU ZS-1042 at store-101."]
