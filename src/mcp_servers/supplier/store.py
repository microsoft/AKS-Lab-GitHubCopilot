"""In-memory supplier store for the supplier MCP server."""

from __future__ import annotations

import asyncio
import hashlib

from .models import PurchaseOrderDraft, PurchaseOrderRequest, SupplierList, SupplierOption, SupplierQuery

# TODO: replace with Cosmos DB
_SUPPLIERS: dict[str, list[SupplierOption]] = {
    "ZS-1042": [
        SupplierOption(
            supplier_id="sup-northstar",
            name="Northstar Apparel Manufacturing",
            available_qty=900,
            unit_cost=18.75,
            lead_time_days=4,
            reliability_score=0.97,
        ),
        SupplierOption(
            supplier_id="sup-contoso-textiles",
            name="Contoso Textiles Direct",
            available_qty=500,
            unit_cost=17.95,
            lead_time_days=6,
            reliability_score=0.91,
        ),
        SupplierOption(
            supplier_id="sup-fabrikam-rapid",
            name="Fabrikam Rapid Replenishment",
            available_qty=240,
            unit_cost=20.10,
            lead_time_days=2,
            reliability_score=0.88,
        ),
    ],
    "ZS-2048": [
        SupplierOption(
            supplier_id="sup-contoso-textiles",
            name="Contoso Textiles Direct",
            available_qty=320,
            unit_cost=12.40,
            lead_time_days=5,
            reliability_score=0.91,
        ),
    ],
}


async def find_suppliers(query: SupplierQuery) -> SupplierList:
    """Return ranked supplier options for a SKU."""

    await asyncio.sleep(0)
    suppliers = sorted(
        _SUPPLIERS.get(query.sku, []),
        key=lambda supplier: (-supplier.reliability_score, supplier.lead_time_days, supplier.unit_cost),
    )
    return SupplierList(sku=query.sku, suppliers=suppliers)


async def create_purchase_order(request: PurchaseOrderRequest) -> PurchaseOrderDraft:
    """Create a deterministic purchase-order draft for a supplier and SKU."""

    await asyncio.sleep(0)
    supplier = _supplier_for(request.sku, request.supplier_id)
    quantity = min(request.quantity, supplier.available_qty)
    po_id = _po_id(request=request, quantity=quantity)
    return PurchaseOrderDraft(
        po_id=po_id,
        sku=request.sku,
        store_id=request.store_id,
        supplier_id=supplier.supplier_id,
        quantity=quantity,
        estimated_total=round(quantity * supplier.unit_cost, 2),
        eta_days=supplier.lead_time_days,
        status="draft",
    )


def _supplier_for(sku: str, supplier_id: str) -> SupplierOption:
    for supplier in _SUPPLIERS.get(sku, []):
        if supplier.supplier_id == supplier_id:
            return supplier
    return SupplierOption(
        supplier_id=supplier_id,
        name="Manual Review Supplier",
        available_qty=0,
        unit_cost=1.0,
        lead_time_days=14,
        reliability_score=0.0,
    )


def _po_id(*, request: PurchaseOrderRequest, quantity: int) -> str:
    digest = hashlib.sha1(
        f"{request.sku}:{request.store_id}:{request.supplier_id}:{quantity}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:10]
    return f"PO-{digest.upper()}"
