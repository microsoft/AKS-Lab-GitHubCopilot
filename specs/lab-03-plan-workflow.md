# Lab 03 deterministic stock-out plan workflow

## Goal

Build a deterministic Microsoft Agent Framework (MAF) Workflow for one SKU at one store while preserving the existing A2A and domain contracts. Run inventory and pricing in parallel, then supplier/PO and logistics/shipping in sequence, reconcile only actual specialist results into `Plan`, and make Key Vault hydration optional for a complete local nine-service Compose fleet.

## Non-goals

- Do not change the existing `Goal`, `Plan`, or shared `/invoke` request/response contracts.
- Do not replace GitHub Copilot in specialist agents; only `/plan` orchestration is deterministic and does not call an orchestrator LLM.
- Do not call MCP servers directly from the orchestrator workflow; specialist calls use A2A and specialists retain MCP access.
- Do not fabricate stock, supplier, purchase-order, shipment, price, or recovery data when an agent refuses, times out, or returns invalid data.
- Do not seed Key Vault, create Azure resources, deploy the fleet, or run live model evaluations in this iteration.
- Do not implement Lab 04 testing workflows or later deployment/automation work.

## Personas

- Store managers need an actionable, honest response to a single-store stock-out.
- Supply planners need a traceable path from stock and price signals to a real purchase-order draft and shipping recommendation.
- Supplier and logistics coordinators need refusals and unavailable data surfaced clearly rather than presented as completed work.
- Local developers need to run the complete fleet without Azure Key Vault access.

## Affected agents

- [x] `orchestrator` — deterministic `/plan` MAF Workflow, A2A calls, and result reconciliation; retain free-form `/invoke`.
- [x] `inventory` — startup Key Vault hydration wiring only; stock decisions remain in its specialist and inventory MCP.
- [x] `supplier` — startup hydration wiring and a parseable actual PO result for the workflow; sourcing and PO drafting remain in the specialist and supplier MCP.
- [x] `logistics` — startup hydration wiring only; shipment decisions remain in its specialist and shipping MCP.
- [x] `pricing` — startup hydration wiring only; pricing decisions remain in its specialist and pricing MCP.
- [x] MCP server `inventory` — optional startup hydration wiring; retain inventory operations in this MCP.
- [x] MCP server `supplier` — optional startup hydration wiring; retain supplier and PO operations in this MCP.
- [x] MCP server `shipping` — optional startup hydration wiring; retain shipment operations in this MCP.
- [x] MCP server `pricing` — optional startup hydration wiring; retain pricing operations in this MCP.

All specialist-to-specialist boundaries remain A2A HTTP. The orchestrator does not import specialist modules or perform MCP/business-system I/O directly.

## New / changed contracts

The existing `Goal` and `Plan` definitions below are reproduced exactly from `src/agents/orchestrator/contracts.py`; do not rename, widen, or otherwise change them. `/plan` accepts `Goal` and returns `Plan`. The existing shared `/invoke` remains the free-form A2A envelope (`run_id`, `goal`, optional string `context` in; `run_id`, output text, and tool-call names out); it is not replaced by the workflow API.

```python
from pydantic import BaseModel, ConfigDict, Field


class Goal(BaseModel):
    """Structured stock-out goal accepted by the /plan endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str = Field(min_length=1, description="Natural-language stock-out recovery goal.")
    sku: str = Field(min_length=1, description="SKU to recover.")
    store_id: str = Field(min_length=1, description="Target store identifier.")


class Plan(BaseModel):
    """Stock-out response plan assembled by the orchestrator."""

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

The supplier specialist's text in the existing A2A `InvokeResponse.output` must include an actual purchase-order object that validates against the existing supplier MCP contract. The workflow must not synthesize or guess these fields. This is content within the existing string response, not a change to the A2A envelope.

```python
from pydantic import BaseModel, ConfigDict, Field


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

Workflow topology (each specialist is invoked over its A2A `/invoke`; its own MCP access remains behind that specialist):

```text
                         +--> inventory specialist (A2A) --+
Goal --> MAF Workflow --|                                 |--> join both results
                         +--> pricing specialist (A2A) ----+         |
                                                                     v
                                                supplier specialist (A2A; draft PO)
                                                                     |
                                                validated actual PurchaseOrderDraft
                                                                     |
                                                                     v
                                                logistics specialist (A2A; quote shipping)
                                                                     |
                                                                     v
                                                  reconcile existing Plan and return
```

The inventory and pricing nodes run concurrently and both complete before the supplier node starts. The supplier node receives the original `Goal` and available inventory/pricing findings, and requests a single real draft through the supplier specialist. Only a complete, valid `PurchaseOrderDraft` for the same `sku` and `store_id` may unlock shipping. Pass the actual PO details (`po_id`, `sku`, `store_id`, `supplier_id`, `quantity`, `estimated_total`, `eta_days`, and `status`) to the logistics specialist in its A2A goal; the logistics specialist uses the shipping MCP contract. Reconcile results into the unchanged `Plan` fields.

A refusal, timeout, or malformed specialist result is a distinct unsuccessful stage, not a successful empty result. Populate required Plan string fields with a truthful unavailable/refused/timed-out explanation, disclose partial completion in `summary`, and include only safe follow-up actions in `next_actions`. Skip shipping when a valid actual PO is unavailable. Never invent PO identifiers, quantities, prices, ETAs, carriers, or other specialist findings. Continue independent or safe later stages where possible and return a valid `Plan` with the original `sku` and `store_id`.

Key Vault startup contract: when `ZAVA_KV_URL` is set, use async `azure.keyvault.secrets.aio.SecretClient` with async `DefaultAzureCredential` to hydrate `GITHUB_TOKEN` from `GITHUB-TOKEN` and `ZAVA_INVENTORY_MCP_URL`, `ZAVA_SUPPLIER_MCP_URL`, `ZAVA_SHIPPING_MCP_URL`, and `ZAVA_PRICING_MCP_URL` from their correspondingly named `*-MCP-URL` secrets. Preserve every already-set environment value. Close the secret client and close the credential in `finally`, including error paths; surface hydration failures rather than silently reporting successful startup. Invoke hydration before each server consumes its final settings. When `ZAVA_KV_URL` is unset, skip Key Vault and use environment variables without creating credentials or a network client.

## Acceptance criteria

1. The orchestrator constructs and executes a real MAF `Workflow` with inventory and pricing A2A calls running in parallel, followed by the supplier/PO step, logistics/shipping step, and final reconciliation in that order. The workflow topology and dependency ordering are inspectable and deterministic.
2. `POST /plan` accepts the existing frozen `Goal` shape and returns the existing frozen `Plan` shape without an orchestrator model call or contract changes. Specialist calls are A2A-only. The shared `make_app` endpoints remain available, and `POST /invoke` continues to run the free-form Copilot orchestrator path.
3. Shipping receives all actual fields from the validated supplier `PurchaseOrderDraft`, including its real `po_id` and `quantity`. Refusal, timeout, and invalid-response cases are surfaced in the corresponding Plan view and summary; shipping is skipped without a valid PO, the endpoint still returns a contract-valid partial Plan, and no missing domain fact is fabricated.
4. Optional Key Vault hydration uses async `SecretClient` and async `DefaultAzureCredential`, preserves environment values already present, and closes the credential in `finally` on success and failure. With `ZAVA_KV_URL` unset it uses environment settings and performs no Key Vault access. All nine server entrypoints (five agents and four MCP servers) call the startup helper before consuming hydrated settings; local Compose does not require Key Vault.
5. Docker Compose defines exactly nine services: orchestrator, inventory, supplier, logistics, pricing, inventory MCP, supplier MCP, shipping MCP, and pricing MCP. Each service healthcheck calls `/healthz`; the host `GITHUB_TOKEN` is passed through with fail-fast behavior; Copilot timeout is 120 seconds; and the shared runtime uses non-root UID 10001 with writable `/home/zava` and `/home/zava/.cache` (`HOME=/home/zava`, `XDG_CACHE_HOME=/home/zava/.cache`) owned by that user. Compose runs without `ZAVA_KV_URL` or a Key Vault dependency.
6. At least the two JSONL scenarios below validate against `EvalScenario` in `tests/evals/run_evals.py`, including seeded SKU/store data and all required fields. `must_call` and `forbid_call` remain review metadata in the current runner; they are not represented as a live-evaluation pass gate by this specification.

## Eval scenarios

```jsonl
{"id":"lab03-stockout-zs1042-store101","goal":"Store 101 will stock out of SKU ZS-1042 by Friday. Build a recovery plan for store-101.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","stock","purchase","shipping","price"],"must_call":["inventory","pricing","supplier","logistics"],"forbid_call":[],"max_latency_s":180}
{"id":"lab03-price-protection-zs1042-store101","goal":"SKU ZS-1042 at store-101 has high demand and critical stock risk. Recommend a recovery plan with price protection.","sku":"ZS-1042","store_id":"store-101","must_mention":["ZS-1042","store-101","42.79","critical","Fabrikam RapidShip"],"must_call":["inventory","pricing","supplier","logistics"],"forbid_call":[],"max_latency_s":180}
```

## Out of scope for this iteration

- Manually seeding or rotating Key Vault secrets (Lab 03 Step 5 operations).
- Starting services, making live Copilot calls, or running live eval scenarios (Lab 03 Step 7).
- Azure resource provisioning, AKS/ACA deployment, or production secret rotation.
- Changing the existing `Goal`, `Plan`, shared `/invoke` envelope, or specialist MCP business contracts.
- Implementing workflows or features from later labs.

## Handoff

Hand off to `orchestrator-architect` with:

```text
Implement specs/lab-03-plan-workflow.md for Lab 03. Preserve Goal, Plan, and
shared /invoke contracts exactly. Implement the deterministic MAF Workflow
and /plan acceptance criteria #1-#3 first, using A2A specialists and passing
the validated actual PurchaseOrderDraft fields to logistics. Then implement
optional async Key Vault hydration and startup wiring for all nine servers
(acceptance #4), followed by the nine-service local Compose and writable
non-root runtime requirements (acceptance #5). Keep local Compose independent
of Key Vault. Run the required checks; do not seed Key Vault or run live model
evaluations until those steps are explicitly requested.
```
