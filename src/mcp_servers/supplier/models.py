"""Pydantic contracts for the supplier MCP server."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SupplierQuery(BaseModel):
    """Request available suppliers for one SKU."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(min_length=1, description="ZavaShop SKU to source.")


class SupplierOption(BaseModel):
    """Supplier capacity and commercial terms for one SKU."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supplier_id: str = Field(description="Stable supplier identifier.")
    name: str = Field(description="Supplier display name.")
    available_qty: int = Field(ge=0, description="Units currently available to order.")
    unit_cost: float = Field(gt=0, description="Unit wholesale cost in USD.")
    lead_time_days: int = Field(ge=0, description="Expected lead time in days.")
    reliability_score: float = Field(ge=0, le=1, description="Historical fulfillment reliability from 0 to 1.")


class SupplierList(BaseModel):
    """Supplier list returned to specialist agents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(description="ZavaShop SKU that was sourced.")
    suppliers: list[SupplierOption] = Field(description="Ranked supplier options for the SKU.")


class PurchaseOrderRequest(BaseModel):
    """Request to draft a replenishment purchase order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str = Field(min_length=1, description="ZavaShop SKU to order.")
    store_id: str = Field(min_length=1, description="Store receiving the replenishment.")
    supplier_id: str = Field(min_length=1, description="Chosen supplier identifier.")
    quantity: int = Field(gt=0, description="Units to order.")


class PurchaseOrderDraft(BaseModel):
    """Draft purchase order returned by the supplier MCP server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    po_id: str = Field(description="Stable draft purchase-order identifier.")
    sku: str = Field(description="ZavaShop SKU to order.")
    store_id: str = Field(description="Store receiving the replenishment.")
    supplier_id: str = Field(description="Chosen supplier identifier.")
    quantity: int = Field(gt=0, description="Units to order.")
    estimated_total: float = Field(gt=0, description="Estimated purchase-order total in USD.")
    eta_days: int = Field(ge=0, description="Estimated arrival time in days.")
    status: str = Field(description="Draft status for the purchase order.")
