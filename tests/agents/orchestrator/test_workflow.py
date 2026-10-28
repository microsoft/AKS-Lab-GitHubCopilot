"""Regression tests for the deterministic orchestrator MAF Workflow."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from json import JSONDecodeError

import pytest

from src.agents.orchestrator.contracts import Goal
from src.agents.orchestrator.workflow import build_plan_workflow, execute_plan
from src.shared.settings import Settings

_PO_DRAFT = {
    "po_id": "PO-REAL-ZS1042-101",
    "sku": "ZS-1042",
    "store_id": "store-101",
    "supplier_id": "sup-northstar",
    "quantity": 73,
    "estimated_total": 1368.75,
    "eta_days": 4,
    "status": "draft",
}
_GOAL = Goal(
    goal="Recover stock-out for SKU ZS-1042 at store-101.",
    sku="ZS-1042",
    store_id="store-101",
)


def _new_outputs() -> dict[str, str]:
    return {}


def _new_errors() -> dict[str, Exception]:
    return {}


def _new_calls() -> list[tuple[str, str, str]]:
    return []


def _new_names() -> set[str]:
    return set()


@dataclass
class MockA2AClient:
    """Record mocked A2A calls while supplying specialist outputs."""

    settings: Settings = field(default_factory=Settings)
    supplier_output: str = field(default_factory=lambda: json.dumps({"purchase_order": _PO_DRAFT}))
    outputs: dict[str, str] = field(default_factory=_new_outputs)
    errors: dict[str, Exception] = field(default_factory=_new_errors)
    calls: list[tuple[str, str, str]] = field(default_factory=_new_calls)
    started: set[str] = field(default_factory=_new_names)
    completed: set[str] = field(default_factory=_new_names)
    initial_started: asyncio.Event | None = None
    release_initial: asyncio.Event | None = None

    async def invoke(self, *, name: str, url: str, goal: str, run_id: str | None = None) -> str:
        self.calls.append((name, url, goal))
        if name == "supplier":
            assert {"inventory", "pricing"} <= self.completed
            return self.supplier_output
        if name == "logistics":
            return self.outputs.get(name, "actual shipping quote")

        self.started.add(name)
        if self.initial_started is not None:
            self.initial_started.set()
        if self.release_initial is not None:
            await asyncio.wait_for(self.release_initial.wait(), timeout=1.0)
        error = self.errors.get(name)
        self.completed.add(name)
        if error is not None:
            raise error
        return self.outputs.get(name, f"verified {name} result")


def _valid_po(**changes: str | int | float) -> dict[str, str | int | float]:
    return {**_PO_DRAFT, **changes}


async def _run(client: MockA2AClient):
    return await execute_plan(workflow=build_plan_workflow(client), goal=_GOAL)


@pytest.mark.asyncio
async def test_workflow_runs_inventory_and_pricing_concurrently_then_chains_po_and_shipping() -> None:
    initial_started = asyncio.Event()
    release_initial = asyncio.Event()
    client = MockA2AClient(initial_started=initial_started, release_initial=release_initial)
    run = asyncio.create_task(_run(client))
    try:
        await asyncio.wait_for(initial_started.wait(), timeout=1.0)
        for _ in range(100):
            if client.started == {"inventory", "pricing"}:
                break
            await asyncio.sleep(0.005)
        assert client.started == {"inventory", "pricing"}
        initial_calls = {name for name, _, _ in client.calls}
        assert initial_calls == {"inventory", "pricing"}
        release_initial.set()
        plan = await asyncio.wait_for(run, timeout=2.0)
    finally:
        release_initial.set()
        if not run.done():
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run

    names = [name for name, _, _ in client.calls]
    assert names[:2] in (["inventory", "pricing"], ["pricing", "inventory"])
    assert names[2:] == ["supplier", "logistics"]
    logistics_goal = client.calls[-1][2]
    for key, value in _PO_DRAFT.items():
        assert f'"{key}": {json.dumps(value)}' in logistics_goal
    assert "actual shipping quote" in plan.shipping_view


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("supplier_output", "expected_message"),
    [
        ("{}", "valid PurchaseOrderDraft"),
        ("not json", "valid purchase-order JSON object"),
        (
            json.dumps({"purchase_order": _valid_po(sku="ZS-9999")}),
            "did not match the requested SKU and store",
        ),
        (
            json.dumps({"refuse": "Supplier refuses", "purchase_order": _PO_DRAFT}),
            "refused",
        ),
    ],
    ids=["missing-po", "malformed-po", "mismatched-po", "refusal-with-po"],
)
async def test_invalid_or_refused_supplier_result_skips_logistics(supplier_output: str, expected_message: str) -> None:
    client = MockA2AClient(supplier_output=supplier_output)

    plan = await _run(client)

    assert expected_message in plan.po_view
    assert "Shipping skipped" in plan.shipping_view
    assert "logistics" not in {name for name, _, _ in client.calls}
    assert plan.summary.startswith("Partial recovery plan")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_name", "exception", "empty_output", "expected_view", "expected_text"),
    [
        ("inventory", TimeoutError(), False, "stock_view", "timed out"),
        ("pricing", JSONDecodeError("invalid", "{", 0), False, "price_view", "not valid JSON"),
        ("inventory", None, True, "stock_view", "empty response"),
    ],
    ids=["timeout", "a2a-invalid-json", "whitespace-output"],
)
async def test_specialist_failures_return_truthful_partial_plan(
    failure_name: str,
    exception: Exception | None,
    empty_output: bool,
    expected_view: str,
    expected_text: str,
) -> None:
    errors = {failure_name: exception} if exception is not None else {}
    outputs = {failure_name: " \n\t "} if empty_output else {}
    client = MockA2AClient(errors=errors, outputs=outputs)

    plan = await _run(client)

    assert plan.summary.startswith("Partial recovery plan")
    assert expected_text in getattr(plan, expected_view)
    assert "Shipping skipped" not in plan.shipping_view
