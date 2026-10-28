"""Direct contract tests for the shipping MCP tool."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_servers.shipping.models import ShipmentQuoteRequest
from src.mcp_servers.shipping.server import quote_shipment

UNKNOWN_DESTINATION_FALLBACK_ETA = 7


@pytest.mark.asyncio
async def test_quote_shipment_returns_seeded_expedited_carrier() -> None:
    quote = await quote_shipment(
        ShipmentQuoteRequest(po_id="PO-TEST-1042", destination_store_id="store-101", quantity=80)
    )

    assert quote.po_id == "PO-TEST-1042"
    assert quote.destination_store_id == "store-101"
    assert quote.carrier == "Fabrikam RapidShip"
    assert quote.eta_days == 1
    assert quote.cost > 0
    assert "store-101" in quote.recommendation


@pytest.mark.asyncio
async def test_quote_shipment_preserves_unknown_destination_fallback() -> None:
    quote = await quote_shipment(
        ShipmentQuoteRequest(po_id="PO-MANUAL", destination_store_id="store-unknown", quantity=1)
    )

    assert quote.carrier == "Manual Dispatch Desk"
    assert quote.service_level == "exception-review"
    assert quote.eta_days == UNKNOWN_DESTINATION_FALLBACK_ETA


def test_shipment_request_rejects_empty_ids_and_nonpositive_quantity() -> None:
    with pytest.raises(ValidationError):
        ShipmentQuoteRequest(po_id="", destination_store_id="store-101", quantity=1)
    with pytest.raises(ValidationError):
        ShipmentQuoteRequest(po_id="PO-1", destination_store_id="store-101", quantity=0)
