"""In-process A2A integration tests using the real orchestrator workflow."""

from __future__ import annotations

from contextlib import AsyncExitStack
from http import HTTPStatus
from typing import Any, ClassVar, cast
from urllib.parse import urlsplit

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Response

from src.agents.inventory.server import app as inventory_app
from src.agents.logistics.server import app as logistics_app
from src.agents.orchestrator import a2a as orchestrator_a2a
from src.agents.orchestrator.contracts import Plan
from src.agents.orchestrator.server import create_app
from src.agents.pricing.server import app as pricing_app
from src.agents.supplier.server import app as supplier_app
from src.shared.server import InvokeResponse
from src.shared.settings import Settings
from tests.agents._mock import MockAgentResponse, MockChatClient

_PO = {
    "po_id": "PO-INTEGRATION-1042-101",
    "sku": "ZS-1042",
    "store_id": "store-101",
    "supplier_id": "sup-northstar",
    "quantity": 80,
    "estimated_total": 1500.0,
    "eta_days": 4,
    "status": "draft",
}
_RESPONSES = {
    "inventory": '{"sku":"ZS-1042","store_id":"store-101","risk_level":"critical",'
    '"target":{"on_hand":6},"nearby_locations":[{"location_id":"store-202","on_hand":84},'
    '{"location_id":"wh-east","on_hand":420}],"recommendation":"transfer stock from store-202"}',
    "pricing": '{"sku":"ZS-1042","store_id":"store-101","current_price":39.99,'
    '"recommended_price":42.79,"rationale":"seasonal apparel price recommendation"}',
    "supplier": '{"sku":"ZS-1042","store_id":"store-101","supplier_view":"seeded supplier draft",'
    '"po_view":"draft created","recommended_supplier":"sup-northstar",'
    '"next_action":"review the purchase order","purchase_order":'
    '{"po_id":"PO-INTEGRATION-1042-101","sku":"ZS-1042","store_id":"store-101",'
    '"supplier_id":"sup-northstar","quantity":80,"estimated_total":1500.0,"eta_days":4,"status":"draft"}}',
    "logistics": '{"po_id":"PO-INTEGRATION-1042-101","carrier":"Fabrikam RapidShip",'
    '"eta_days":1,"shipping_view":"Fabrikam RapidShip expedited ETA 1 day"}',
    "orchestrator": '{"answer":"Free-form recovery response for SKU ZS-1042 at store-101."}',
}


def _mock_copilot_client() -> object:
    return object()


def _chat_client_for(output: str) -> type[MockChatClient]:
    class FixedResponseChatClient(MockChatClient):
        async def run(self, message: str) -> MockAgentResponse:
            self.__class__.messages.append(message)
            return MockAgentResponse(text=output)

    return FixedResponseChatClient


class RoutingA2AClient(httpx.AsyncClient):
    """Route real A2AClient HTTP posts to in-process specialist ASGI apps."""

    apps: ClassVar[dict[str, Any]] = {}
    requests: ClassVar[list[tuple[str, dict[str, Any]]]] = []

    async def post(self, url: str | httpx.URL, **kwargs: Any) -> Response:
        target = str(url)
        parsed = urlsplit(target)
        if parsed.hostname is None or parsed.hostname not in self.apps:
            raise AssertionError(f"No in-process ASGI route for {target}")
        payload = kwargs.get("json")
        if not isinstance(payload, dict):
            raise AssertionError("A2A request did not contain a JSON envelope")
        request_payload = cast("dict[str, Any]", payload)
        self.__class__.requests.append((parsed.hostname, request_payload))
        async with AsyncClient(
            transport=ASGITransport(app=self.apps[parsed.hostname]),
            base_url=f"{parsed.scheme}://{parsed.netloc}",
        ) as routed_client:
            return await routed_client.post(target, **kwargs)


@pytest.mark.asyncio
async def test_plan_and_invoke_use_real_workflow_and_loopback_a2a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apps = {
        "inventory": inventory_app,
        "supplier": supplier_app,
        "logistics": logistics_app,
        "pricing": pricing_app,
    }
    RoutingA2AClient.apps = apps
    RoutingA2AClient.requests = []
    agent_outputs = {
        "inventory": _RESPONSES["inventory"],
        "supplier": _RESPONSES["supplier"],
        "logistics": _RESPONSES["logistics"],
        "pricing": _RESPONSES["pricing"],
        "orchestrator": _RESPONSES["orchestrator"],
    }
    for name, output in agent_outputs.items():
        module = f"src.agents.{name}.agent"
        monkeypatch.setattr(f"{module}.GitHubCopilotAgent", _chat_client_for(output))
        monkeypatch.setattr(f"{module}.build_copilot_client", _mock_copilot_client)

    monkeypatch.setattr(orchestrator_a2a.httpx, "AsyncClient", RoutingA2AClient)
    settings = Settings(
        inventory_a2a_url="http://inventory/invoke",
        supplier_a2a_url="http://supplier/invoke",
        logistics_a2a_url="http://logistics/invoke",
        pricing_a2a_url="http://pricing/invoke",
    )
    orchestrator_app = create_app(settings=settings)

    async with AsyncExitStack() as stack:
        for app in (*apps.values(), orchestrator_app):
            await stack.enter_async_context(app.router.lifespan_context(app))
        async with AsyncClient(transport=ASGITransport(app=orchestrator_app), base_url="http://orchestrator") as client:
            plan_response = await client.post(
                "/plan",
                json={
                    "goal": "Recover critical stock risk for SKU ZS-1042 at store-101.",
                    "sku": "ZS-1042",
                    "store_id": "store-101",
                },
            )
            invoke_response = await client.post(
                "/invoke",
                json={"run_id": "lab04-freeform", "goal": "Build a free-form recovery summary for ZS-1042."},
            )

    assert plan_response.status_code == HTTPStatus.OK
    plan = Plan.model_validate(plan_response.json())
    assert plan.sku == "ZS-1042"
    assert plan.store_id == "store-101"
    assert "critical" in plan.stock_view
    assert "42.79" in plan.price_view
    assert "PO-INTEGRATION-1042-101" in plan.po_view
    assert "Fabrikam RapidShip" in plan.shipping_view
    assert plan.summary
    assert plan.next_actions

    assert invoke_response.status_code == HTTPStatus.OK
    invoke = InvokeResponse.model_validate(invoke_response.json())
    assert invoke.run_id == "lab04-freeform"
    assert "ZS-1042" in invoke.output
    assert invoke.tool_calls == []

    assert {host for host, _ in RoutingA2AClient.requests} == set(apps)
    for host, payload in RoutingA2AClient.requests:
        assert payload["run_id"]
        assert payload["context"] == {"caller": "orchestrator"}
        assert "ZS-1042" in payload["goal"]
        assert "store-101" in payload["goal"]
        if host == "logistics":
            assert "PO-INTEGRATION-1042-101" in payload["goal"]
