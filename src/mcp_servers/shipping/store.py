"""In-memory shipping quote store for the shipping MCP server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .models import ShipmentQuote, ShipmentQuoteRequest

EXPEDITED_ETA_DAYS = 2


@dataclass(frozen=True, slots=True)
class CarrierRate:
    """Internal carrier-rate row for deterministic quote generation."""

    carrier: str
    service_level: str
    base_cost: float
    per_unit_cost: float
    eta_days: int
    destination_store_ids: frozenset[str]


# TODO: replace with Cosmos DB
_CARRIER_RATES: tuple[CarrierRate, ...] = (
    CarrierRate(
        carrier="Northwind Freight",
        service_level="priority-truckload",
        base_cost=180.0,
        per_unit_cost=0.42,
        eta_days=2,
        destination_store_ids=frozenset({"store-101", "store-202"}),
    ),
    CarrierRate(
        carrier="Blue Yonder Logistics",
        service_level="standard-ltl",
        base_cost=95.0,
        per_unit_cost=0.28,
        eta_days=4,
        destination_store_ids=frozenset({"store-101", "store-202", "wh-east"}),
    ),
    CarrierRate(
        carrier="Fabrikam RapidShip",
        service_level="same-day-expedite",
        base_cost=360.0,
        per_unit_cost=0.75,
        eta_days=1,
        destination_store_ids=frozenset({"store-101"}),
    ),
)


async def quote_shipment(request: ShipmentQuoteRequest) -> ShipmentQuote:
    """Return the best deterministic shipment quote for a request."""

    await asyncio.sleep(0)
    rate = _best_rate(request.destination_store_id)
    cost = round(rate.base_cost + request.quantity * rate.per_unit_cost, 2)
    return ShipmentQuote(
        po_id=request.po_id,
        destination_store_id=request.destination_store_id,
        carrier=rate.carrier,
        service_level=rate.service_level,
        eta_days=rate.eta_days,
        cost=cost,
        recommendation=_recommendation(request=request, rate=rate, cost=cost),
    )


def _best_rate(destination_store_id: str) -> CarrierRate:
    destination_rates = [rate for rate in _CARRIER_RATES if destination_store_id in rate.destination_store_ids]
    if not destination_rates:
        return CarrierRate(
            carrier="Manual Dispatch Desk",
            service_level="exception-review",
            base_cost=500.0,
            per_unit_cost=1.25,
            eta_days=7,
            destination_store_ids=frozenset({destination_store_id}),
        )
    return min(destination_rates, key=lambda rate: (rate.eta_days, rate.base_cost + rate.per_unit_cost * 100))


def _recommendation(*, request: ShipmentQuoteRequest, rate: CarrierRate, cost: float) -> str:
    if rate.eta_days <= EXPEDITED_ETA_DAYS:
        return (
            f"Use {rate.carrier} {rate.service_level} for PO {request.po_id}; ETA {rate.eta_days} days "
            f"to {request.destination_store_id} at estimated cost ${cost:.2f}."
        )
    return (
        f"Use {rate.carrier} {rate.service_level} for PO {request.po_id}; delivery is economical but slower "
        f"at {rate.eta_days} days and estimated cost ${cost:.2f}."
    )
