"""FastMCP entrypoint for the inventory MCP server."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import StockQuery, StockReport
from .store import lookup_stock

log = structlog.get_logger(__name__).bind(service="inventory-mcp")
mcp = FastMCP("inventory-mcp", host="0.0.0.0", port=8080, streamable_http_path="/mcp")


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    """Return process health for container probes."""

    return JSONResponse({"status": "ok"})


@mcp.tool()
async def check_stock(query: StockQuery) -> StockReport:
    """Check current stock and stock-out risk for one SKU at one store.

    Args:
        query: SKU and target store location.
    Returns:
        StockReport with target stock, nearby locations, risk, and recommendation.
    """

    log.info("tool.check_stock", sku=query.sku, store_id=query.store_id)
    return await lookup_stock(query)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
