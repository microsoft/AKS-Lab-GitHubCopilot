"""API tests for the ZavaShop orchestrator /plan endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

from src.agents.orchestrator.server import create_app
from src.shared.settings import Settings


@dataclass(frozen=True)
class FakeSpecialistClient:
    settings: Settings

    async def invoke(self, *, name: str, url: str, goal: str, run_id: str | None = None) -> str:
        return f"{name} output for {goal} via {url}"


@pytest.mark.asyncio
async def test_plan_endpoint_returns_frozen_plan() -> None:
    settings = Settings(
        inventory_a2a_url="http://inventory.local/invoke",
        supplier_a2a_url="http://supplier.local/invoke",
        logistics_a2a_url="http://logistics.local/invoke",
        pricing_a2a_url="http://pricing.local/invoke",
    )
    app = create_app(settings=settings, specialist_client=FakeSpecialistClient(settings=settings))
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
    assert "supplier output" in body["po_view"]
    assert "logistics output" in body["shipping_view"]
    assert "pricing output" in body["price_view"]
    assert body["next_actions"]
