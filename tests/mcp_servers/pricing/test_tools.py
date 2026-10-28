"""Direct contract tests for the pricing MCP tool."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_servers.pricing.models import PricingQuery
from src.mcp_servers.pricing.server import recommend_price

SEEDED_CURRENT_PRICE = 39.99
SEEDED_RECOMMENDATION = 42.79
UNKNOWN_SKU_FALLBACK_PRICE = 29.99


@pytest.mark.asyncio
async def test_recommend_price_uses_seeded_stockout_data() -> None:
    result = await recommend_price(
        PricingQuery(
            sku="ZS-1042",
            store_id="store-101",
            demand_signal="demand spike",
            stock_risk_level="critical",
        )
    )

    assert result.sku == "ZS-1042"
    assert result.store_id == "store-101"
    assert result.current_price == SEEDED_CURRENT_PRICE
    assert result.recommended_price == SEEDED_RECOMMENDATION
    assert "seasonal apparel" in result.rationale
    assert "demand spike" in result.rationale


@pytest.mark.asyncio
async def test_recommend_price_preserves_unknown_sku_fallback() -> None:
    result = await recommend_price(
        PricingQuery(sku="UNKNOWN-SKU", store_id="store-101", demand_signal="steady", stock_risk_level="low")
    )

    assert result.current_price == UNKNOWN_SKU_FALLBACK_PRICE
    assert "manual review" in result.rationale


def test_pricing_query_rejects_empty_required_signals() -> None:
    with pytest.raises(ValidationError):
        PricingQuery(sku="", store_id="store-101", demand_signal="steady", stock_risk_level="low")
    with pytest.raises(ValidationError):
        PricingQuery(sku="ZS-1042", store_id="", demand_signal="steady", stock_risk_level="low")
    with pytest.raises(ValidationError):
        PricingQuery(sku="ZS-1042", store_id="store-101", demand_signal="", stock_risk_level="low")
