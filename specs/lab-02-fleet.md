# ZavaShop stock-out response fleet

## Goal

Build a local, role-scoped ZavaShop fleet that resolves a single stock-out incident for one SKU at one store. The orchestrator accepts a structured stock-out goal, fans out to the inventory, supplier, logistics, and pricing specialists through A2A HTTP calls, and returns a structured `Plan` with narrative views and next actions. This lab preserves the existing repo contracts and keeps all external I/O in MCP servers without implementing Lab 03 functionality.

## Non-goals

- Do not replace GitHub Copilot with another model provider.
- Do not store production secrets or cloud credentials in checked-in files.
- Do not persist business state outside in-memory MCP fixtures for this local lab.
- Do not add cross-region or multi-store orchestration beyond a single `(sku, store_id)` request.
- Do not implement deployment, Helm, Bicep, or later workflow automation in this step.
- Do not move supplier, stock, pricing, or shipping logic into agent code; those concerns stay in MCP servers.

## Personas

- Store manager: needs a clear recovery plan when a store is at risk of stock-out.
- Supply planner: needs supplier and PO guidance grounded in available stock and replenishment timing.
- Logistics coordinator: needs a shipment or transfer recommendation with ETA and cost tradeoffs.
- Pricing analyst: needs a demand-aware price recommendation that reflects stock risk.
- Platform engineer: needs the fleet contract to remain consistent with the repo's orchestrator and MCP models.

## Affected agents

- [x] `orchestrator` — accepts the stock-out goal, orchestrates the specialist calls, and assembles the final `Plan`.
- [x] `inventory` — interprets stock posture and nearby inventory using the inventory MCP server.
- [x] `supplier` — evaluates available suppliers and drafts a purchase-order recommendation.
- [x] `logistics` — evaluates shipment and transfer options with ETA and cost reasoning.
- [x] `pricing` — recommends a price that reflects demand pressure and stock risk.
- [x] MCP server `inventory` — exposes `check_stock(StockQuery) -> StockReport` and stores in-memory inventory data.
- [x] MCP server `supplier` — exposes supplier lookup and purchase-order drafting contracts.
- [x] MCP server `shipping` — exposes shipment quoting and logistics recommendations.
- [x] MCP server `pricing` — exposes price recommendation logic for a given SKU/store context.
- [x] A2A `/invoke` envelope — shares the local agent-call contract used by the shared FastAPI server factory.

## New / changed contracts

The repo distinguishes the agent `/invoke` A2A envelope from the structured business contract used by the orchestrator. The A2A envelope carries run metadata and a natural-language goal; the business contract carries the typed `(sku, store_id)` stock-out information and the final summary view.

```python
from pydantic import BaseModel, ConfigDict, Field


class InvokeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=64, description="Caller-provided run identifier.")
    goal: str = Field(min_length=1, max_length=4000, description="Goal text for the agent.")
    context: dict[str, str] = Field(default_factory=dict, description="Optional string context for the run.")


class InvokeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(description="Run identifier copied from the request.")
    output: str = Field(description="Agent output text.")
    tool_calls: list[str] = Field(default_factory=list, description="Tool names observed during the run.")
```

```python
from pydantic import BaseModel, ConfigDict, Field


class Goal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str = Field(min_length=1, description="Natural-language stock-out recovery goal.")
    sku: str = Field(min_length=1, description="SKU to recover.")
    store_id: str = Field(min_length=1, description="Target store identifier.")


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str
    store_id: str
    stock_view: str
    price_view: str
    po_view: str
    shipping_view: str
    summary: str
    next_actions: list[str]
```

```python
from pydantic import BaseModel, ConfigDict, Field


class StockQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(min_length=1, description="ZavaShop SKU to inspect.")
    store_id: str = Field(min_length=1, description="Target store location ID.")


class StockLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    location_id: str = Field(description="Store or warehouse location ID.")
    on_hand: int = Field(ge=0, description="Units physically on hand.")
    reserved: int = Field(ge=0, description="Units already reserved for orders.")
    reorder_point: int = Field(ge=0, description="Threshold that triggers replenishment.")
    days_until_stockout: int = Field(ge=0, description="Estimated days until stock reaches zero.")


class StockReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(description="ZavaShop SKU that was inspected.")
    store_id: str = Field(description="Target store location ID.")
    target: StockLocation = Field(description="Stock position for the requested store.")
    nearby_locations: list[StockLocation] = Field(description="Nearby stores or warehouses with related stock.")
    risk_level: str = Field(description="Stock-out risk level for the target store.")
    recommendation: str = Field(description="Inventory action recommendation.")
```

```python
from pydantic import BaseModel, ConfigDict, Field


class SupplierQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(min_length=1, description="ZavaShop SKU to source.")


class SupplierOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supplier_id: str = Field(description="Stable supplier identifier.")
    name: str = Field(description="Supplier display name.")
    available_qty: int = Field(ge=0, description="Units currently available to order.")
    unit_cost: float = Field(gt=0, description="Unit wholesale cost in USD.")
    lead_time_days: int = Field(ge=0, description="Expected lead time in days.")
    reliability_score: float = Field(ge=0, le=1, description="Historical fulfillment reliability from 0 to 1.")


class SupplierList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(description="ZavaShop SKU that was sourced.")
    suppliers: list[SupplierOption] = Field(description="Ranked supplier options for the SKU.")


class PurchaseOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(min_length=1, description="ZavaShop SKU to order.")
    store_id: str = Field(min_length=1, description="Store receiving the replenishment.")
    supplier_id: str = Field(min_length=1, description="Chosen supplier identifier.")
    quantity: int = Field(gt=0, description="Units to order.")


class PurchaseOrderDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    po_id: str = Field(description="Stable draft purchase-order identifier.")
    sku: str = Field(description="ZavaShop SKU to order.")
    store_id: str = Field(description="Store receiving the replenishment.")
    supplier_id: str = Field(description="Chosen supplier identifier.")
    quantity: int = Field(gt=0, description="Units to order.")
    estimated_total: float = Field(gt=0, description="Estimated purchase-order total in USD.")
    eta_days: int = Field(ge=0, description="Estimated arrival time in days.")
    status: str = Field(description="Draft status for the purchase order.")
```

```python
from pydantic import BaseModel, ConfigDict, Field


class ShipmentQuoteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    po_id: str = Field(min_length=1, description="Draft purchase-order identifier to ship.")
    destination_store_id: str = Field(min_length=1, description="Store receiving the shipment.")
    quantity: int = Field(gt=0, description="Units to ship.")


class ShipmentQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    po_id: str = Field(description="Draft purchase-order identifier to ship.")
    destination_store_id: str = Field(description="Store receiving the shipment.")
    carrier: str = Field(description="Recommended carrier name.")
    service_level: str = Field(description="Carrier service tier.")
    eta_days: int = Field(ge=0, description="Estimated delivery time in days.")
    cost: float = Field(gt=0, description="Estimated shipment cost in USD.")
    recommendation: str = Field(description="Logistics recommendation for the shipment.")
```

```python
from pydantic import BaseModel, ConfigDict, Field


class PricingQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(min_length=1, description="ZavaShop SKU to price.")
    store_id: str = Field(min_length=1, description="Store where the price applies.")
    demand_signal: str = Field(min_length=1, description="Observed demand signal for the SKU.")
    stock_risk_level: str = Field(min_length=1, description="Inventory stock-out risk level.")


class PriceRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(description="ZavaShop SKU that was priced.")
    store_id: str = Field(description="Store where the price applies.")
    current_price: float = Field(gt=0, description="Current shelf price in USD.")
    recommended_price: float = Field(gt=0, description="Recommended shelf price in USD.")
    margin_impact: str = Field(description="Expected margin impact summary.")
    rationale: str = Field(description="Reasoning behind the recommendation.")
```

## Acceptance criteria

1. Given a `Goal` with `goal="Store out of stock"`, `sku="ZS-1042"`, and `store_id="store-101"`, the orchestrator returns a `Plan` that includes `sku`, `store_id`, `stock_view`, `price_view`, `po_view`, `shipping_view`, `summary`, and `next_actions`.
2. The `Plan` model is frozen and forbids unknown fields, matching the repo contract in `src/agents/orchestrator/contracts.py`.
3. The inventory specialist can query the inventory MCP server with `StockQuery(sku="ZS-1042", store_id="store-101")` and produce a `StockReport` with `target` and `nearby_locations: list[StockLocation]`.
4. The supplier specialist can call the supplier MCP server to list vendors for `ZS-1042` and draft a purchase-order recommendation with supplier, quantity, ETA, and total.
5. The logistics specialist can quote shipment for the drafted PO and return a `ShipmentQuote` with carrier, service level, ETA, cost, and recommendation.
6. The pricing specialist can produce a `PriceRecommendation` for `ZS-1042` at `store-101` using demand signal and stock-risk level, without mutating store inventory state.
7. The orchestrator invokes specialist agents through A2A HTTP calls only and does not import specialist Python modules directly.
8. All external I/O remains in the MCP servers; agent modules do not contain direct DB, supplier, shipping, or pricing side effects.
9. The fleet contains exactly five MAF agents (`orchestrator`, `inventory`, `supplier`, `logistics`, `pricing`) and four MCP servers (`inventory`, `supplier`, `shipping`, `pricing`).
10. A single stock-out eval scenario for `ZS-1042` at `store-101` validates against `EvalScenario` and includes all required fields: `id`, `goal`, `sku`, `store_id`, `must_mention`, `must_call`, `forbid_call`, and `max_latency_s`.

## Eval scenarios

```jsonl
{"id":"stockout-zs1042-store101","goal":"Store 101 will stock out of SKU ZS-1042 by Friday. Build a recovery plan for store-101.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","stock","purchase order","shipping","price"],"must_call":["inventory","supplier","logistics","pricing"],"forbid_call":[],"max_latency_s":120}
```

## Out of scope for this iteration

- Persistent DB-backed inventory, supplier, pricing, or shipping state.
- Real ERP, supplier API, carrier API, or pricing-engine integrations.
- Multi-region or multi-store orchestration beyond one `(sku, store_id)` request.
- Automated PO submission or shipping dispatch.
- Deployment manifests or Lab 03 workflow functionality.

## Handoff

Hand off to `orchestrator-architect` with:

```text
Implement Lab 02 Step 2 from specs/lab-02-fleet.md:
- build the shared server plumbing in src/shared/server.py, settings, and telemetry if needed
- implement the orchestrator scaffolding and A2A flow around the Goal/Plan contracts
- keep the MCP contracts aligned with the repo models for inventory, supplier, shipping, and pricing
- do not implement Lab 03 workflow functionality or later deployment work
```
