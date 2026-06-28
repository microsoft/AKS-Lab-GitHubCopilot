"""Unit tests for the ZavaShop logistics specialist agent."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from src.agents.logistics.agent import build_agent
from src.agents.logistics.prompts import SYSTEM_PROMPT
from src.shared.settings import Settings
from tests.agents._mock import MockChatClient, captured_options


def _mcp_servers(options: Mapping[str, object]) -> Mapping[str, object]:
    servers = options.get("mcp_servers")
    if not isinstance(servers, Mapping):
        raise AssertionError("mcp_servers was not configured")
    return cast("Mapping[str, object]", servers)


@pytest.mark.asyncio
async def test_logistics_agent_uses_shipping_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"po_id":"PO-ZS1042-STORE101","shipping_view":"use expedited carrier"}'])
    monkeypatch.setattr("src.agents.logistics.agent.GitHubCopilotAgent", MockChatClient)

    settings = Settings(shipping_mcp_url="http://shipping.local/mcp")
    agent = await build_agent(settings)
    response = await agent.run("Quote shipment for PO-ZS1042-STORE101 to store-101 quantity 80.")
    options = captured_options()
    mcp_servers = _mcp_servers(options)

    assert "PO-ZS1042-STORE101" in response.output_text
    assert "shipping" in mcp_servers
    assert "gpt-5.5" == options.get("model")
    assert settings.copilot_timeout_seconds == options.get("timeout")


@pytest.mark.asyncio
async def test_logistics_agent_refuses_pricing_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"refuse":"pricing strategy belongs to pricing"}'])
    monkeypatch.setattr("src.agents.logistics.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())
    response = await agent.run("Recommend price for ZS-1042 at store-101.")

    assert "refuse" in response.output_text
    assert "pricing" in SYSTEM_PROMPT
    assert "Never invent" in SYSTEM_PROMPT
