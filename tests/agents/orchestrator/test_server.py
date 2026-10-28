"""API tests for the orchestrator /plan endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

from src.agents.orchestrator.server import create_app
from src.shared.settings import Settings

PO_ID = "PO-TEST-1042-101"
PO_SUPPLIER_ID = "sup-test"
PO_QUANTITY = 80
PO_DRAFT = {
    "po_id": PO_ID,
    "sku": "ZS-1042",
    "store_id": "store-101",
    "supplier_id": PO_SUPPLIER_ID,
    "quantity": PO_QUANTITY,
    "estimated_total": 1500.0,
    "eta_days": 3,
    "status": "draft",
}


def _new_calls() -> list[tuple[str, str, str]]:
    return []


@dataclass
class FakeSpecialistClient:
    settings: Settings
    calls: list[tuple[str, str, str]] = field(default_factory=_new_calls)

    async def invoke(self, *, name: str, url: str, goal: str, run_id: str | None = None) -> str:
        self.calls.append((name, url, goal))
        if name == "supplier":
            return json.dumps({"purchase_order": PO_DRAFT})
        if name == "logistics":
            return "logistics output with actual PO"
        return f"{name} output for {goal} via {url}"


@pytest.mark.asyncio
async def test_plan_endpoint_returns_frozen_plan() -> None:
    settings = Settings(
        inventory_a2a_url="http://inventory.local/invoke",
        supplier_a2a_url="http://supplier.local/invoke",
        logistics_a2a_url="http://logistics.local/invoke",
        pricing_a2a_url="http://pricing.local/invoke",
    )
    specialist_client = FakeSpecialistClient(settings=settings)
    app = create_app(settings=settings, specialist_client=specialist_client)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/plan",
            json={
                "goal": "Store 101 will stock out of SKU ZS-1042 by Friday.",
                "sku": "ZS-1042",
                "store_id": "store-101",
            },
        )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["sku"] == "ZS-1042"
    assert body["store_id"] == "store-101"
    assert "inventory output" in body["stock_view"]
    assert "PO-TEST-1042-101" in body["po_view"]
    assert "logistics output" in body["shipping_view"]
    assert "pricing output" in body["price_view"]
    assert body["next_actions"]
    call_names = [name for name, _, _ in specialist_client.calls]
    call_urls = [url for _, url, _ in specialist_client.calls]
    assert set(call_names[:2]) == {"inventory", "pricing"}
    assert call_names[2:] == ["supplier", "logistics"]
    assert set(call_urls[:2]) == {settings.inventory_a2a_url, settings.pricing_a2a_url}
    assert call_urls[2:] == [settings.supplier_a2a_url, settings.logistics_a2a_url]
    logistics_goal = specialist_client.calls[-1][2]
    assert f'"po_id": "{PO_ID}"' in logistics_goal
    assert f'"quantity": {PO_QUANTITY}' in logistics_goal
    assert f'"supplier_id": "{PO_SUPPLIER_ID}"' in logistics_goal
