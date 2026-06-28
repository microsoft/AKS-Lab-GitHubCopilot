"""In-memory inventory store for the inventory MCP server."""

from __future__ import annotations

import asyncio

from .models import StockLocation, StockQuery, StockReport

CRITICAL_STOCKOUT_DAYS = 2
HIGH_STOCKOUT_DAYS = 5
MIN_TRANSFER_UNITS = 40

# TODO: replace with Cosmos DB
_INVENTORY: dict[str, dict[str, StockLocation]] = {
    "ZS-1042": {
        "store-101": StockLocation(
            location_id="store-101",
            on_hand=6,
            reserved=4,
            reorder_point=24,
            days_until_stockout=2,
        ),
        "store-202": StockLocation(
            location_id="store-202",
            on_hand=84,
            reserved=9,
            reorder_point=30,
            days_until_stockout=16,
        ),
        "wh-east": StockLocation(
            location_id="wh-east",
            on_hand=420,
            reserved=65,
            reorder_point=150,
            days_until_stockout=30,
        ),
    },
    "ZS-2048": {
        "store-101": StockLocation(
            location_id="store-101",
            on_hand=38,
            reserved=3,
            reorder_point=20,
            days_until_stockout=12,
        ),
        "store-202": StockLocation(
            location_id="store-202",
            on_hand=22,
            reserved=2,
            reorder_point=18,
            days_until_stockout=9,
        ),
        "wh-east": StockLocation(
            location_id="wh-east",
            on_hand=160,
            reserved=20,
            reorder_point=80,
            days_until_stockout=25,
        ),
    },
}


async def lookup_stock(query: StockQuery) -> StockReport:
    """Look up stock for a SKU and target store."""

    await asyncio.sleep(0)
    sku_locations = _INVENTORY.get(query.sku)
    if sku_locations is None:
        return StockReport(
            sku=query.sku,
            store_id=query.store_id,
            target=StockLocation(
                location_id=query.store_id,
                on_hand=0,
                reserved=0,
                reorder_point=0,
                days_until_stockout=0,
            ),
            nearby_locations=[],
            risk_level="unknown",
            recommendation=f"No inventory record exists for SKU {query.sku}; escalate to supply planning.",
        )

    target = sku_locations.get(
        query.store_id,
        StockLocation(
            location_id=query.store_id,
            on_hand=0,
            reserved=0,
            reorder_point=0,
            days_until_stockout=0,
        ),
    )
    nearby_locations = [stock for location_id, stock in sku_locations.items() if location_id != query.store_id]
    available = max(target.on_hand - target.reserved, 0)
    risk_level = _risk_level(
        available=available,
        reorder_point=target.reorder_point,
        days_until_stockout=target.days_until_stockout,
    )

    return StockReport(
        sku=query.sku,
        store_id=query.store_id,
        target=target,
        nearby_locations=nearby_locations,
        risk_level=risk_level,
        recommendation=_recommendation(
            query=query,
            available=available,
            risk_level=risk_level,
            nearby_locations=nearby_locations,
        ),
    )


def _risk_level(*, available: int, reorder_point: int, days_until_stockout: int) -> str:
    if available == 0 or days_until_stockout <= CRITICAL_STOCKOUT_DAYS:
        return "critical"
    if available < reorder_point or days_until_stockout <= HIGH_STOCKOUT_DAYS:
        return "high"
    if available < reorder_point * 2:
        return "moderate"
    return "low"


def _recommendation(
    *,
    query: StockQuery,
    available: int,
    risk_level: str,
    nearby_locations: list[StockLocation],
) -> str:
    transfer_source = next(
        (stock for stock in nearby_locations if stock.on_hand - stock.reserved >= MIN_TRANSFER_UNITS),
        None,
    )
    if transfer_source is not None and risk_level in {"critical", "high"}:
        return (
            f"{query.store_id} has {available} sellable units of {query.sku}; prioritize a transfer from "
            f"{transfer_source.location_id} and draft supplier replenishment as backup."
        )
    if risk_level in {"critical", "high"}:
        return f"{query.store_id} has {available} sellable units of {query.sku}; draft supplier replenishment now."
    return f"{query.store_id} has {available} sellable units of {query.sku}; monitor before ordering."
