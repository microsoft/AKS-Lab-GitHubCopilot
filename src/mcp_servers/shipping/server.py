"""FastMCP entrypoint for the shipping MCP server."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import ShipmentQuote, ShipmentQuoteRequest
from .store import quote_shipment as quote_shipment_from_store

log = structlog.get_logger(__name__).bind(service="shipping-mcp")
mcp = FastMCP("shipping-mcp", host="0.0.0.0", port=8080, streamable_http_path="/mcp")


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    """Return process health for container probes."""

    return JSONResponse({"status": "ok"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readyz(_request: Request) -> JSONResponse:
    """Return readiness for ACA ingress probes."""

    return JSONResponse({"status": "ready", "name": "shipping-mcp"})


@mcp.tool()
async def quote_shipment(request: ShipmentQuoteRequest) -> ShipmentQuote:
    """Quote shipment cost and ETA for one purchase order.

    Args:
        request: Purchase order, destination store, and quantity to ship.
    Returns:
        ShipmentQuote with carrier, service level, ETA, cost, and recommendation.
    """

    log.info(
        "tool.quote_shipment",
        po_id=request.po_id,
        destination_store_id=request.destination_store_id,
        quantity=request.quantity,
    )
    return await quote_shipment_from_store(request)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
