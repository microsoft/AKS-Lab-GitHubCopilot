"""Unit tests for the ZavaShop inventory specialist agent."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from src.agents.inventory.agent import build_agent
from src.agents.inventory.prompts import SYSTEM_PROMPT
from src.shared.settings import Settings
from tests.agents._mock import MockChatClient, captured_options


def _mcp_servers(options: Mapping[str, object]) -> Mapping[str, object]:
    servers = options.get("mcp_servers")
    if not isinstance(servers, Mapping):
        raise AssertionError("mcp_servers was not configured")
    return cast("Mapping[str, object]", servers)


@pytest.mark.asyncio
async def test_inventory_agent_happy_path_uses_inventory_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(
        responses=[
            '{"sku":"ZS-1042","store_id":"store-101","stock_view":"stock at risk",'
            '"risk_level":"high","nearby_locations":["store-202","wh-east"],'
            '"recommendation":"transfer stock"}'
        ]
    )
    monkeypatch.setattr("src.agents.inventory.agent.GitHubCopilotAgent", MockChatClient)

    settings = Settings(inventory_mcp_url="http://inventory.local/mcp")
    agent = await build_agent(settings)
    response = await agent.run("Check stock for SKU ZS-1042 at store-101.")
    options = captured_options()
    mcp_servers = _mcp_servers(options)

    assert "ZS-1042" in response.output_text
    assert "store-101" in response.output_text
    assert "stock" in response.output_text
    assert "inventory" in mcp_servers
    assert "gpt-5.5" == options.get("model")
    assert settings.copilot_timeout_seconds == options.get("timeout")
    assert MockChatClient.messages == ["Check stock for SKU ZS-1042 at store-101."]


@pytest.mark.asyncio
async def test_inventory_agent_refuses_out_of_scope_supplier_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(
        responses=[
            '{"refuse":"supplier and purchase order requests belong to the supplier specialist","redirect":"supplier"}'
        ]
    )
    monkeypatch.setattr("src.agents.inventory.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())
    response = await agent.run("Draft a purchase order for supplier replenishment of ZS-1042.")

    assert "refuse" in response.output_text
    assert "supplier" in response.output_text
    assert "purchase-order" in SYSTEM_PROMPT
    assert "Never invent" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_inventory_agent_surfaces_tool_error_once(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(errors=[RuntimeError("inventory MCP unavailable")])
    monkeypatch.setattr("src.agents.inventory.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())

    with pytest.raises(RuntimeError, match="inventory MCP unavailable"):
        await agent.run("Check stock for SKU ZS-1042 at store-101.")

    assert MockChatClient.messages == ["Check stock for SKU ZS-1042 at store-101."]
