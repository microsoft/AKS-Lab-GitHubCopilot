# Skill: Pydantic Contracts (process boundary)

Any data crossing HTTP, A2A, MCP, or a queue is a frozen Pydantic v2 model.

## A2A envelope (in `src/shared/server.py`)

```python
from pydantic import BaseModel, ConfigDict, Field


class InvokeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str = Field(min_length=1, max_length=64)
    goal: str = Field(min_length=1, max_length=4000)
    context: dict[str, str] = Field(default_factory=dict)


class InvokeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    output: str
    tool_calls: list[str] = Field(default_factory=list)
```

## Orchestrator workflow contracts

```python
class Goal(BaseModel):
    model_config = ConfigDict(frozen=True)
    goal: str
    sku: str | None = None
    store_id: str | None = None


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)
    stock_view: str
    price_view: str
    po_view: str
    shipping_view: str
    summary: str
```

## Per-agent tool inputs

Each agent's `tools.py` defines its own pair. Examples:

```python
class StockQuery(BaseModel):
    model_config = ConfigDict(frozen=True)
    sku: str
    locations: list[str]


class LocationStock(BaseModel):
    model_config = ConfigDict(frozen=True)
    location: str
    on_hand: int
    reorder_point: int


class StockReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    sku: str
    items: list[LocationStock]
```

## Rules

- `extra="forbid"` on all request models.
- `frozen=True` on **all** models — agents and tools should never mutate inputs.
- No bare `dict` / `Any` in tool signatures. `# noqa: ANN401` only with a written reason.
