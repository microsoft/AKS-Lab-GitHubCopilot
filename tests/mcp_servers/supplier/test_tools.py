"""Direct contract tests for supplier MCP tools."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_servers.supplier.models import PurchaseOrderRequest, SupplierQuery
from src.mcp_servers.supplier.server import draft_po, list_suppliers

SEEDED_SUPPLIER_COUNT = 3
SEEDED_PO_QUANTITY = 80
SEEDED_PO_TOTAL = 1500.0
SEEDED_PO_ETA_DAYS = 4


@pytest.mark.asyncio
async def test_list_suppliers_returns_seeded_ranked_options() -> None:
    result = await list_suppliers(SupplierQuery(sku="ZS-1042"))

    assert len(result.suppliers) == SEEDED_SUPPLIER_COUNT
    assert result.suppliers[0].supplier_id == "sup-northstar"
    assert result.suppliers[1].supplier_id == "sup-contoso-textiles"
    assert result.suppliers[2].supplier_id == "sup-fabrikam-rapid"


@pytest.mark.asyncio
async def test_list_suppliers_preserves_unknown_sku_empty_fallback() -> None:
    result = await list_suppliers(SupplierQuery(sku="UNKNOWN-SKU"))

    assert result.sku == "UNKNOWN-SKU"
    assert result.suppliers == []


@pytest.mark.asyncio
async def test_draft_po_returns_complete_seeded_purchase_order() -> None:
    result = await draft_po(
        PurchaseOrderRequest(sku="ZS-1042", store_id="store-101", supplier_id="sup-northstar", quantity=80)
    )

    assert result.sku == "ZS-1042"
    assert result.store_id == "store-101"
    assert result.supplier_id == "sup-northstar"
    assert result.quantity == SEEDED_PO_QUANTITY
    assert result.estimated_total == SEEDED_PO_TOTAL
    assert result.eta_days == SEEDED_PO_ETA_DAYS
    assert result.status == "draft"
    assert result.po_id.startswith("PO-")


def test_supplier_contracts_reject_empty_sku_and_nonpositive_quantity() -> None:
    with pytest.raises(ValidationError):
        SupplierQuery(sku="")
    with pytest.raises(ValidationError):
        PurchaseOrderRequest(sku="ZS-1042", store_id="store-101", supplier_id="sup-northstar", quantity=0)
    with pytest.raises(ValidationError):
        PurchaseOrderRequest(sku="ZS-1042", store_id="store-101", supplier_id="", quantity=1)
