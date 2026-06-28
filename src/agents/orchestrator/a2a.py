"""A2A HTTP client for orchestrator-to-specialist calls."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.shared.server import InvokeRequest, InvokeResponse
from src.shared.settings import Settings


class SpecialistOutputs(BaseModel):
    """Outputs returned by all specialists for one stock-out plan."""

    model_config = ConfigDict(frozen=True)

    inventory: str
    supplier: str
    logistics: str
    pricing: str


@dataclass(frozen=True)
class SpecialistClient:
    """HTTP client for invoking ZavaShop specialist agents."""

    settings: Settings

    async def invoke(self, *, name: str, url: str, goal: str, run_id: str | None = None) -> str:
        request = InvokeRequest(run_id=run_id or uuid4().hex, goal=goal, context={"caller": "orchestrator"})
        timeout = httpx.Timeout(self.settings.copilot_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=request.model_dump())
            response.raise_for_status()
        envelope = InvokeResponse.model_validate(response.json())
        return envelope.output


class SpecialistInvoker(Protocol):
    """Protocol for specialist invokers used by production code and tests."""

    @property
    def settings(self) -> Settings:
        """Settings used to resolve specialist endpoint URLs."""

        ...

    async def invoke(self, *, name: str, url: str, goal: str, run_id: str | None = None) -> str: ...


class FanOutGoals(BaseModel):
    """Specialist goals generated for one stock-out request."""

    model_config = ConfigDict(frozen=True)

    inventory: str = Field(min_length=1)
    supplier: str = Field(min_length=1)
    logistics: str = Field(min_length=1)
    pricing: str = Field(min_length=1)


def build_specialist_goals(*, sku: str, store_id: str, supplier_quantity: int = 80) -> FanOutGoals:
    """Build deterministic specialist goals for a stock-out response plan."""

    po_hint = f"PO candidate for {sku} at {store_id}"
    return FanOutGoals(
        inventory=f"Check stock risk for SKU {sku} at {store_id}; include nearby store and warehouse options.",
        supplier=f"List suppliers and draft a purchase order for SKU {sku} at {store_id} quantity {supplier_quantity}.",
        logistics=f"Quote shipment for {po_hint} to {store_id} quantity {supplier_quantity}.",
        pricing=f"Recommend price for SKU {sku} at {store_id} with high demand signal and critical stock risk.",
    )


async def call_specialists(*, client: SpecialistInvoker, sku: str, store_id: str) -> SpecialistOutputs:
    """Invoke all specialists through A2A HTTP."""

    goals = build_specialist_goals(sku=sku, store_id=store_id)
    async with asyncio.TaskGroup() as task_group:
        inventory_task = task_group.create_task(
            client.invoke(name="inventory", url=client.settings.inventory_a2a_url, goal=goals.inventory)
        )
        supplier_task = task_group.create_task(
            client.invoke(name="supplier", url=client.settings.supplier_a2a_url, goal=goals.supplier)
        )
        logistics_task = task_group.create_task(
            client.invoke(name="logistics", url=client.settings.logistics_a2a_url, goal=goals.logistics)
        )
        pricing_task = task_group.create_task(
            client.invoke(name="pricing", url=client.settings.pricing_a2a_url, goal=goals.pricing)
        )
    return SpecialistOutputs(
        inventory=inventory_task.result(),
        supplier=supplier_task.result(),
        logistics=logistics_task.result(),
        pricing=pricing_task.result(),
    )
