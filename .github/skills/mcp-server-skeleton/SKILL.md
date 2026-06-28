# Skill: MCP Server Skeleton (FastMCP, streamable-http)

## Reference layout

```
src/mcp_servers/<name>/
├── __init__.py
├── models.py
├── store.py
├── server.py
└── Dockerfile
```

## `server.py` template

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import StockQuery, StockReport
from .store import lookup_stock

log = structlog.get_logger("<name>-mcp")
mcp = FastMCP("<name>-mcp", host="0.0.0.0", port=8080, streamable_http_path="/mcp")


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    """Return process health for container probes."""

    return JSONResponse({"status": "ok"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readyz(_request: Request) -> JSONResponse:
    """Return readiness for ACA ingress probes."""

    return JSONResponse({"status": "ready", "name": "<name>-mcp"})


@mcp.tool()
async def check_stock(query: StockQuery) -> StockReport:
    """Return on-hand stock and reorder point for each requested location.

    Args:
        query: SKU and list of location IDs.
    Returns:
        StockReport with one LocationStock per requested location.
    """
    log.info("tool.check_stock", sku=query.sku, locations=query.locations)
    return await lookup_stock(query)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

## `models.py` rules

- Every request / response is a Pydantic v2 model with `model_config = ConfigDict(frozen=True)`.
- Field names are snake_case; alias to camelCase only if an external API requires it.

## `store.py` rules

- In-memory `dict` keyed by primary key. Leave the marker:
  ```python
  # TODO: replace with Cosmos DB (see specs/storage.md)
  ```
- Seed with at least: SKU `ZS-1042`; locations `store-101`, `store-202`, `wh-east`.

## Acceptance

```bash
uv run python -m src.mcp_servers.<name>.server &
sleep 1 && curl -fsS http://localhost:8080/healthz
curl -fsS http://localhost:8080/readyz
kill %1
```
