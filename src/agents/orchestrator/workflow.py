"""Deterministic MAF workflow for a single-store stock-out plan."""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Literal, Never, cast

import httpx
from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel, ConfigDict, ValidationError

from src.agents.orchestrator.a2a import SpecialistInvoker, build_specialist_goals
from src.agents.orchestrator.contracts import Goal, Plan
from src.mcp_servers.supplier.models import PurchaseOrderDraft


class _SpecialistResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Literal["inventory", "pricing", "supplier", "logistics"]
    goal: Goal
    output: str
    failure: str | None = None


class _PlanState(BaseModel):
    model_config = ConfigDict(frozen=True)

    goal: Goal
    inventory: _SpecialistResult
    pricing: _SpecialistResult
    supplier: _SpecialistResult
    purchase_order: PurchaseOrderDraft | None
    logistics: _SpecialistResult | None = None


class _Start(Executor):
    @handler(input=Goal, output=Goal)
    async def dispatch(self, goal: Goal, ctx: WorkflowContext[Goal]) -> None:
        await ctx.send_message(goal)


class _Inventory(Executor):
    def __init__(self, client: SpecialistInvoker) -> None:
        super().__init__(id="inventory")
        self._client = client

    @handler(input=Goal, output=_SpecialistResult)
    async def invoke_inventory(self, goal: Goal, ctx: WorkflowContext[_SpecialistResult]) -> None:
        specialist_goals = build_specialist_goals(sku=goal.sku, store_id=goal.store_id)
        result = await _invoke_specialist(
            client=self._client,
            name="inventory",
            url=self._client.settings.inventory_a2a_url,
            goal=specialist_goals.inventory,
            request=goal,
        )
        await ctx.send_message(result)


class _Pricing(Executor):
    def __init__(self, client: SpecialistInvoker) -> None:
        super().__init__(id="pricing")
        self._client = client

    @handler(input=Goal, output=_SpecialistResult)
    async def invoke_pricing(self, goal: Goal, ctx: WorkflowContext[_SpecialistResult]) -> None:
        specialist_goals = build_specialist_goals(sku=goal.sku, store_id=goal.store_id)
        result = await _invoke_specialist(
            client=self._client,
            name="pricing",
            url=self._client.settings.pricing_a2a_url,
            goal=(
                f"{specialist_goals.pricing} Original stock-out goal: {goal.goal}. "
                "Use only verified facts; refuse if demand signal or stock risk is unavailable."
            ),
            request=goal,
        )
        await ctx.send_message(result)


class _Supplier(Executor):
    def __init__(self, client: SpecialistInvoker) -> None:
        super().__init__(id="supplier")
        self._client = client

    @handler(input=list[_SpecialistResult], output=_PlanState)
    async def invoke_supplier(self, results: list[_SpecialistResult], ctx: WorkflowContext[_PlanState]) -> None:
        by_name = {result.name: result for result in results}
        inventory = by_name["inventory"]
        pricing = by_name["pricing"]
        goal = inventory.goal
        supplier_goal = (
            f"For SKU {goal.sku} at store {goal.store_id}, evaluate suppliers and draft one purchase order. "
            f"Original request: {goal.goal}. Verified inventory result: {inventory.output}. "
            f"Verified pricing result: {pricing.output}. Use only these results and supplier MCP data; "
            "if required data is unavailable, refuse rather than infer a quantity or commercial term. "
            "Return the complete actual PurchaseOrderDraft as a JSON object in a purchase_order field."
        )
        supplier = await _invoke_specialist(
            client=self._client,
            name="supplier",
            url=self._client.settings.supplier_a2a_url,
            goal=supplier_goal,
            request=goal,
        )
        purchase_order, po_failure = _parse_purchase_order(supplier.output, goal)
        if supplier.failure is not None:
            po_failure = supplier.failure
        elif _is_refusal(supplier.output):
            po_failure = "supplier specialist refused the purchase-order request"
        if po_failure is not None:
            purchase_order = None
        supplier = supplier.model_copy(update={"failure": po_failure})
        await ctx.send_message(
            _PlanState(
                goal=goal,
                inventory=inventory,
                pricing=pricing,
                supplier=supplier,
                purchase_order=purchase_order,
            )
        )


class _Logistics(Executor):
    def __init__(self, client: SpecialistInvoker) -> None:
        super().__init__(id="logistics")
        self._client = client

    @handler(input=_PlanState, output=_PlanState)
    async def invoke_logistics(self, state: _PlanState, ctx: WorkflowContext[_PlanState]) -> None:
        purchase_order = state.purchase_order
        if state.supplier.failure is not None or purchase_order is None:
            logistics = _SpecialistResult(
                name="logistics",
                goal=state.goal,
                output="Shipping skipped because no valid actual purchase order is available.",
                failure="shipping skipped: purchase order unavailable",
            )
        else:
            po_details = json.dumps(purchase_order.model_dump(), sort_keys=True)
            logistics = await _invoke_specialist(
                client=self._client,
                name="logistics",
                url=self._client.settings.logistics_a2a_url,
                goal=(
                    f"Quote shipping for this actual validated purchase order; do not alter its details: {po_details}"
                ),
                request=state.goal,
            )
            if _is_refusal(logistics.output):
                logistics = logistics.model_copy(update={"failure": "logistics specialist refused the request"})
        await ctx.send_message(state.model_copy(update={"logistics": logistics}))


class _Reconcile(Executor):
    @handler(input=_PlanState, workflow_output=Plan)
    async def reconcile(self, state: _PlanState, ctx: WorkflowContext[Never, Plan]) -> None:
        plan = _reconcile(state)
        await ctx.yield_output(plan)


def build_plan_workflow(client: SpecialistInvoker) -> Workflow:
    """Build the real MAF Workflow graph for deterministic plan execution."""

    start = _Start(id="start")
    inventory = _Inventory(client)
    pricing = _Pricing(client)
    supplier = _Supplier(client)
    logistics = _Logistics(client)
    reconcile = _Reconcile(id="reconcile")
    return (
        WorkflowBuilder(start_executor=start, output_from=[reconcile])
        .add_fan_out_edges(start, [inventory, pricing])
        .add_fan_in_edges([inventory, pricing], supplier)
        .add_chain([supplier, logistics, reconcile])
        .build()
    )


async def execute_plan(*, workflow: Workflow, goal: Goal) -> Plan:
    """Execute the MAF workflow and return its reconciled Plan output."""

    result = await workflow.run(goal)
    outputs = result.get_outputs()
    if len(outputs) != 1:
        raise RuntimeError(f"Expected exactly one Plan output, received {len(outputs)}")
    return Plan.model_validate(outputs[0])


async def _invoke_specialist(
    *,
    client: SpecialistInvoker,
    name: Literal["inventory", "pricing", "supplier", "logistics"],
    url: str,
    goal: str,
    request: Goal,
) -> _SpecialistResult:
    try:
        output = await client.invoke(name=name, url=url, goal=goal)
    except (TimeoutError, httpx.TimeoutException):
        return _SpecialistResult(name=name, goal=request, output="", failure=f"{name} specialist timed out")
    except httpx.HTTPError:
        return _SpecialistResult(name=name, goal=request, output="", failure=f"{name} specialist unavailable")
    except JSONDecodeError:
        return _SpecialistResult(name=name, goal=request, output="", failure=f"{name} response was not valid JSON")
    except ValidationError:
        return _SpecialistResult(name=name, goal=request, output="", failure=f"{name} response was invalid")
    if not output.strip():
        return _SpecialistResult(
            name=name,
            goal=request,
            output="",
            failure=f"{name} specialist returned an empty response",
        )
    return _SpecialistResult(name=name, goal=request, output=output)


def _parse_purchase_order(output: str, goal: Goal) -> tuple[PurchaseOrderDraft | None, str | None]:
    try:
        payload: object = json.loads(output)
    except JSONDecodeError:
        return None, "supplier response did not contain a valid purchase-order JSON object"

    if isinstance(payload, dict):
        payload_dict = cast("dict[str, object]", payload)
        for key in ("purchase_order", "purchase_order_draft", "po_draft", "po"):
            if key in payload_dict:
                payload = payload_dict[key]
                break
    try:
        purchase_order = PurchaseOrderDraft.model_validate(payload)
    except ValidationError:
        return None, "supplier response did not contain a valid PurchaseOrderDraft"
    if purchase_order.sku != goal.sku or purchase_order.store_id != goal.store_id:
        return None, "supplier PurchaseOrderDraft did not match the requested SKU and store"
    return purchase_order, None


def _is_refusal(output: str) -> bool:
    normalized = output.casefold()
    return any(
        marker in normalized
        for marker in ('"refuse"', '"refusal"', "i refuse", "i cannot help", "i can't help", "outside my scope")
    )


def _specialist_view(result: _SpecialistResult, specialist: str) -> str:
    if result.failure is not None:
        return f"Unavailable: {result.failure}."
    if _is_refusal(result.output):
        return f"Unavailable: {specialist} specialist refused the request."
    return result.output


def _reconcile(state: _PlanState) -> Plan:
    stock_view = _specialist_view(state.inventory, "inventory")
    price_view = _specialist_view(state.pricing, "pricing")
    po_view = _supplier_view(state)
    shipping_view = _logistics_view(state.logistics)
    next_actions = _next_actions(state)
    results = [state.inventory, state.pricing, state.supplier, state.logistics]
    complete = all(result is not None and _specialist_succeeded(result) for result in results)
    status = "completed" if complete else "partial"
    summary = f"{status.title()} recovery plan for {state.goal.sku} at {state.goal.store_id}."
    return Plan(
        sku=state.goal.sku,
        store_id=state.goal.store_id,
        stock_view=stock_view,
        price_view=price_view,
        po_view=po_view,
        shipping_view=shipping_view,
        summary=summary,
        next_actions=next_actions,
    )


def _supplier_view(state: _PlanState) -> str:
    if state.supplier.failure is not None:
        return f"Unavailable: {state.supplier.failure}."
    if state.purchase_order is None:
        return "Unavailable: supplier response contained no validated purchase order."
    return state.supplier.output


def _logistics_view(logistics: _SpecialistResult | None) -> str:
    if logistics is None:
        return "Unavailable: logistics stage did not produce a result."
    if logistics.failure == "shipping skipped: purchase order unavailable":
        return "Shipping skipped because no valid actual purchase order was available."
    return _specialist_view(logistics, "logistics")


def _next_actions(state: _PlanState) -> list[str]:
    actions: list[str] = []
    if state.purchase_order is not None:
        actions.append("Review the actual draft purchase order before approval.")
    else:
        actions.append("Resolve supplier data gaps before creating a purchase order.")
    if state.logistics is not None and state.logistics.failure is None:
        actions.append("Review the shipment quote before booking.")
    if state.inventory.failure is None and not _is_refusal(state.inventory.output):
        actions.append("Review inventory risk and available nearby stock.")
    if state.pricing.failure is None and not _is_refusal(state.pricing.output):
        actions.append("Review the price recommendation before applying it.")
    return actions


def _specialist_succeeded(result: _SpecialistResult) -> bool:
    return result.failure is None and not _is_refusal(result.output)


__all__ = ["build_plan_workflow", "execute_plan"]
