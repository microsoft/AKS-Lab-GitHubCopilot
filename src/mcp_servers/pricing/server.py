"""FastMCP entrypoint for the pricing MCP server."""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import PriceRecommendation, PricingQuery
from .store import recommend_price_for

log = structlog.get_logger(__name__).bind(service="pricing-mcp")
mcp = FastMCP("pricing-mcp", host="0.0.0.0", port=8080, streamable_http_path="/mcp")


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    """Return process health for container probes."""

    return JSONResponse({"status": "ok"})


@mcp.tool()
async def recommend_price(query: PricingQuery) -> PriceRecommendation:
    """Recommend a price for one SKU at one store.

    Args:
        query: SKU, store, demand signal, and stock risk level to price.
    Returns:
        PriceRecommendation with current price, recommended price, margin impact, and rationale.
    """

    log.info(
        "tool.recommend_price",
        sku=query.sku,
        store_id=query.store_id,
        demand_signal=query.demand_signal,
        stock_risk_level=query.stock_risk_level,
    )
    return await recommend_price_for(query)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
