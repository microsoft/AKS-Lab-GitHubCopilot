"""Function tools for orchestrator A2A specialist delegation."""

from __future__ import annotations

from agent_framework import FunctionTool, tool

from src.shared.settings import Settings

from .a2a import SpecialistClient

_settings = Settings()
_client = SpecialistClient(settings=_settings)


@tool(name="ask_inventory", description="Delegate a stock question to the inventory specialist.")
async def ask_inventory(goal: str) -> str:
    """Forward the goal verbatim to the inventory specialist.

    Args:
        goal: The goal text to forward.
    Returns:
        The specialist plain-text output field.
    """

    return await _client.invoke(name="inventory", url=_settings.inventory_a2a_url, goal=goal)


@tool(name="ask_supplier", description="Delegate a replenishment question to the supplier specialist.")
async def ask_supplier(goal: str) -> str:
    """Forward the goal verbatim to the supplier specialist.

    Args:
        goal: The goal text to forward.
    Returns:
        The specialist plain-text output field.
    """

    return await _client.invoke(name="supplier", url=_settings.supplier_a2a_url, goal=goal)


@tool(name="ask_logistics", description="Delegate a shipment question to the logistics specialist.")
async def ask_logistics(goal: str) -> str:
    """Forward the goal verbatim to the logistics specialist.

    Args:
        goal: The goal text to forward.
    Returns:
        The specialist plain-text output field.
    """

    return await _client.invoke(name="logistics", url=_settings.logistics_a2a_url, goal=goal)


@tool(name="ask_pricing", description="Delegate a price question to the pricing specialist.")
async def ask_pricing(goal: str) -> str:
    """Forward the goal verbatim to the pricing specialist.

    Args:
        goal: The goal text to forward.
    Returns:
        The specialist plain-text output field.
    """

    return await _client.invoke(name="pricing", url=_settings.pricing_a2a_url, goal=goal)


TOOLS: list[FunctionTool] = [ask_inventory, ask_supplier, ask_logistics, ask_pricing]
