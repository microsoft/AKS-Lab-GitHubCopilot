"""Direct contract tests for the inventory MCP tool."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_servers.inventory.models import StockLocation, StockQuery
from src.mcp_servers.inventory.server import check_stock

SEEDED_TARGET_ON_HAND = 6


@pytest.mark.asyncio
async def test_check_stock_returns_seeded_target_and_nearby_locations() -> None:
    report = await check_stock(StockQuery(sku="ZS-1042", store_id="store-101"))

    assert report.sku == "ZS-1042"
    assert report.target.location_id == "store-101"
    assert report.target.on_hand == SEEDED_TARGET_ON_HAND
    assert report.risk_level == "critical"
    assert {row.location_id for row in report.nearby_locations} == {"store-202", "wh-east"}
    assert "store-202" in report.recommendation


@pytest.mark.asyncio
async def test_check_stock_preserves_unknown_sku_fallback() -> None:
    report = await check_stock(StockQuery(sku="UNKNOWN-SKU", store_id="store-101"))

    assert report.risk_level == "unknown"
    assert report.target.on_hand == 0
    assert report.nearby_locations == []
    assert "No inventory record" in report.recommendation


def test_stock_contract_rejects_empty_identifiers_and_negative_counts() -> None:
    with pytest.raises(ValidationError):
        StockQuery(sku="", store_id="store-101")
    with pytest.raises(ValidationError):
        StockQuery(sku="ZS-1042", store_id="")
    with pytest.raises(ValidationError):
        StockLocation(location_id="store-101", on_hand=-1, reserved=0, reorder_point=1, days_until_stockout=0)
