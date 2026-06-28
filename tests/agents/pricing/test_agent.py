"""Unit tests for the ZavaShop pricing specialist agent."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from src.agents.pricing.agent import build_agent
from src.agents.pricing.prompts import SYSTEM_PROMPT
from src.shared.settings import Settings
from tests.agents._mock import MockChatClient, captured_options


def _mcp_servers(options: Mapping[str, object]) -> Mapping[str, object]:
    servers = options.get("mcp_servers")
    if not isinstance(servers, Mapping):
        raise AssertionError("mcp_servers was not configured")
    return cast("Mapping[str, object]", servers)


@pytest.mark.asyncio
async def test_pricing_agent_uses_pricing_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"sku":"ZS-1042","store_id":"store-101","price_view":"hold price"}'])
    monkeypatch.setattr("src.agents.pricing.agent.GitHubCopilotAgent", MockChatClient)

    settings = Settings(pricing_mcp_url="http://pricing.local/mcp")
    agent = await build_agent(settings)
    response = await agent.run("Recommend price for SKU ZS-1042 at store-101 with high stock risk.")
    options = captured_options()
    mcp_servers = _mcp_servers(options)

    assert "ZS-1042" in response.output_text
    assert "pricing" in mcp_servers
    assert "gpt-5.5" == options.get("model")
    assert settings.copilot_timeout_seconds == options.get("timeout")


@pytest.mark.asyncio
async def test_pricing_agent_refuses_supplier_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"refuse":"purchase-order drafting belongs to supplier"}'])
    monkeypatch.setattr("src.agents.pricing.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())
    response = await agent.run("Draft a purchase order for ZS-1042 at store-101.")

    assert "refuse" in response.output_text
    assert "purchase-order" in SYSTEM_PROMPT
    assert "Never invent" in SYSTEM_PROMPT
