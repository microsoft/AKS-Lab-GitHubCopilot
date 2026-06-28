"""FastMCP entrypoint for the supplier MCP server."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import PurchaseOrderDraft, PurchaseOrderRequest, SupplierList, SupplierQuery
from .store import create_purchase_order, find_suppliers

log = structlog.get_logger(__name__).bind(service="supplier-mcp")
mcp = FastMCP("supplier-mcp", host="0.0.0.0", port=8080, streamable_http_path="/mcp")


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    """Return process health for container probes."""

    return JSONResponse({"status": "ok"})


@mcp.custom_route("/readyz", methods=["GET"])
async def readyz(_request: Request) -> JSONResponse:
    """Return readiness for ACA ingress probes."""

    return JSONResponse({"status": "ready", "name": "supplier-mcp"})


@mcp.tool()
async def list_suppliers(query: SupplierQuery) -> SupplierList:
    """List ranked suppliers that can replenish one SKU.

    Args:
        query: SKU to source from supplier inventory.
    Returns:
        SupplierList with available quantities, cost, lead time, and reliability.
    """

    log.info("tool.list_suppliers", sku=query.sku)
    return await find_suppliers(query)


@mcp.tool()
async def draft_po(request: PurchaseOrderRequest) -> PurchaseOrderDraft:
    """Draft a replenishment purchase order for one SKU and store.

    Args:
        request: SKU, receiving store, chosen supplier, and quantity to order.
    Returns:
        PurchaseOrderDraft with a stable PO ID, estimated total, ETA, and status.
    """

    log.info(
        "tool.draft_po",
        sku=request.sku,
        store_id=request.store_id,
        supplier_id=request.supplier_id,
        quantity=request.quantity,
    )
    return await create_purchase_order(request)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
