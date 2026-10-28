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


@pytest.mark.asyncio
async def test_orchestrator_agent_handles_refusal_response(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"refusal":"outside the ZavaShop supply-chain scope"}'])
    monkeypatch.setattr("src.agents.orchestrator.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())
    response = await agent.run("Write a poem unrelated to ZavaShop.")

    assert "refusal" in response.output_text
    assert "outside" in response.output_text


@pytest.mark.asyncio
async def test_orchestrator_agent_surfaces_tool_error_once(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(errors=[RuntimeError("A2A tool unavailable")])
    monkeypatch.setattr("src.agents.orchestrator.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())

    with pytest.raises(RuntimeError, match="A2A tool unavailable"):
        await agent.run("Build a plan for SKU ZS-1042 at store-101.")
    assert MockChatClient.messages
