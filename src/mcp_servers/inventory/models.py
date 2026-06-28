"""Pydantic contracts for the inventory MCP server."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StockQuery(BaseModel):
    """Request stock status for one SKU at one store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(min_length=1, description="ZavaShop SKU to inspect.")
    store_id: str = Field(min_length=1, description="Target store location ID.")


class StockLocation(BaseModel):
    """Stock position at one store or warehouse."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    location_id: str = Field(description="Store or warehouse location ID.")
    on_hand: int = Field(ge=0, description="Units physically on hand.")
    reserved: int = Field(ge=0, description="Units already reserved for orders.")
    reorder_point: int = Field(ge=0, description="Threshold that triggers replenishment.")
    days_until_stockout: int = Field(ge=0, description="Estimated days until stock reaches zero.")


class StockReport(BaseModel):
    """Inventory view returned to specialist agents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(description="ZavaShop SKU that was inspected.")
    store_id: str = Field(description="Target store location ID.")
    target: StockLocation = Field(description="Stock position for the requested store.")
    nearby_locations: list[StockLocation] = Field(description="Nearby stores or warehouses with related stock.")
    risk_level: str = Field(description="Stock-out risk level for the target store.")
    recommendation: str = Field(description="Inventory action recommendation.")
