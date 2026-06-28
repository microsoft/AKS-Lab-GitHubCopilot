"""Unit tests for the ZavaShop supplier specialist agent."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from src.agents.supplier.agent import build_agent
from src.agents.supplier.prompts import SYSTEM_PROMPT
from src.shared.settings import Settings
from tests.agents._mock import MockChatClient, captured_options


def _mcp_servers(options: Mapping[str, object]) -> Mapping[str, object]:
    servers = options.get("mcp_servers")
    if not isinstance(servers, Mapping):
        raise AssertionError("mcp_servers was not configured")
    return cast("Mapping[str, object]", servers)


@pytest.mark.asyncio
async def test_supplier_agent_uses_supplier_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"sku":"ZS-1042","store_id":"store-101","po_view":"PO-ZS1042-STORE101"}'])
    monkeypatch.setattr("src.agents.supplier.agent.GitHubCopilotAgent", MockChatClient)

    settings = Settings(supplier_mcp_url="http://supplier.local/mcp")
    agent = await build_agent(settings)
    response = await agent.run("Draft a purchase order for SKU ZS-1042 at store-101.")
    options = captured_options()
    mcp_servers = _mcp_servers(options)

    assert "PO-ZS1042-STORE101" in response.output_text
    assert "supplier" in mcp_servers
    assert "gpt-5.5" == options.get("model")
    assert settings.copilot_timeout_seconds == options.get("timeout")


@pytest.mark.asyncio
async def test_supplier_agent_refuses_shipping_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    MockChatClient.reset(responses=['{"refuse":"shipment quotes belong to logistics"}'])
    monkeypatch.setattr("src.agents.supplier.agent.GitHubCopilotAgent", MockChatClient)

    agent = await build_agent(Settings())
    response = await agent.run("Quote shipment for PO-ZS1042-STORE101.")

    assert "refuse" in response.output_text
    assert "shipment" in SYSTEM_PROMPT
    assert "Never invent" in SYSTEM_PROMPT
