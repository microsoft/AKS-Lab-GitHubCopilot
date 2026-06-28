"""Pydantic contracts for the shipping MCP server."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ShipmentQuoteRequest(BaseModel):
    """Request a shipment quote for a purchase order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    po_id: str = Field(min_length=1, description="Draft purchase-order identifier to ship.")
    destination_store_id: str = Field(min_length=1, description="Store receiving the shipment.")
    quantity: int = Field(gt=0, description="Units to ship.")


class ShipmentQuote(BaseModel):
    """Carrier quote returned by the shipping MCP server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    po_id: str = Field(description="Draft purchase-order identifier to ship.")
    destination_store_id: str = Field(description="Store receiving the shipment.")
    carrier: str = Field(description="Recommended carrier name.")
    service_level: str = Field(description="Carrier service tier.")
    eta_days: int = Field(ge=0, description="Estimated delivery time in days.")
    cost: float = Field(gt=0, description="Estimated shipment cost in USD.")
    recommendation: str = Field(description="Logistics recommendation for the shipment.")
