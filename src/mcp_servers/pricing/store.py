"""In-memory pricing store for the pricing MCP server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .models import PriceRecommendation, PricingQuery


@dataclass(frozen=True, slots=True)
class PriceRow:
    """Internal price row for deterministic pricing recommendations."""

    current_price: float
    unit_cost: float
    floor_price: float
    ceiling_price: float
    category: str


# TODO: replace with Cosmos DB
_PRICES: dict[tuple[str, str], PriceRow] = {
    ("ZS-1042", "store-101"): PriceRow(
        current_price=39.99,
        unit_cost=18.75,
        floor_price=34.99,
        ceiling_price=44.99,
        category="seasonal apparel",
    ),
    ("ZS-1042", "store-202"): PriceRow(
        current_price=38.49,
        unit_cost=18.75,
        floor_price=33.99,
        ceiling_price=43.99,
        category="seasonal apparel",
    ),
    ("ZS-2048", "store-101"): PriceRow(
        current_price=24.99,
        unit_cost=12.40,
        floor_price=21.99,
        ceiling_price=29.99,
        category="home basics",
    ),
}


async def recommend_price_for(query: PricingQuery) -> PriceRecommendation:
    """Return a deterministic price recommendation for a SKU and store."""

    await asyncio.sleep(0)
    row = _PRICES.get(
        (query.sku, query.store_id),
        PriceRow(
            current_price=29.99,
            unit_cost=15.0,
            floor_price=24.99,
            ceiling_price=34.99,
            category="manual review",
        ),
    )
    adjustment = _price_adjustment(demand_signal=query.demand_signal, stock_risk_level=query.stock_risk_level)
    recommended_price = _clamp(
        round(row.current_price * (1 + adjustment), 2),
        floor_price=row.floor_price,
        ceiling_price=row.ceiling_price,
    )
    return PriceRecommendation(
        sku=query.sku,
        store_id=query.store_id,
        current_price=row.current_price,
        recommended_price=recommended_price,
        margin_impact=_margin_impact(row=row, recommended_price=recommended_price),
        rationale=_rationale(query=query, row=row, adjustment=adjustment, recommended_price=recommended_price),
    )


def _price_adjustment(*, demand_signal: str, stock_risk_level: str) -> float:
    demand = demand_signal.lower()
    risk = stock_risk_level.lower()
    adjustment = 0.0
    if any(term in demand for term in ("spike", "surge", "high", "hot")):
        adjustment += 0.04
    if any(term in demand for term in ("soft", "low", "decline")):
        adjustment -= 0.03
    if risk in {"critical", "high"}:
        adjustment += 0.03
    if risk == "low":
        adjustment -= 0.01
    return adjustment


def _clamp(value: float, *, floor_price: float, ceiling_price: float) -> float:
    return min(max(value, floor_price), ceiling_price)


def _margin_impact(*, row: PriceRow, recommended_price: float) -> str:
    current_margin = row.current_price - row.unit_cost
    recommended_margin = recommended_price - row.unit_cost
    delta = recommended_margin - current_margin
    direction = "increase" if delta >= 0 else "decrease"
    return f"Estimated unit margin {direction} of ${abs(delta):.2f}."


def _rationale(*, query: PricingQuery, row: PriceRow, adjustment: float, recommended_price: float) -> str:
    if adjustment > 0:
        posture = "protect scarce inventory and margin"
    elif adjustment < 0:
        posture = "support sell-through while staying above floor price"
    else:
        posture = "hold current price because demand and stock risk are balanced"
    return (
        f"For {row.category} SKU {query.sku} at {query.store_id}, {posture}; "
        f"recommend ${recommended_price:.2f} based on demand signal '{query.demand_signal}' "
        f"and stock risk '{query.stock_risk_level}'."
    )
