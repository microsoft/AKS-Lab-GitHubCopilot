"""Shared runtime settings for ZavaShop services."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings shared by agents and MCP servers."""

    model_config = SettingsConfigDict(env_prefix="ZAVA_", frozen=True, extra="ignore")

    copilot_model: str = Field(default="gpt-5.5", description="GitHub Copilot model name.")
    copilot_timeout_seconds: float = Field(default=120.0, gt=0, description="LLM and MCP timeout budget.")

    inventory_mcp_url: str = Field(default="http://inventory-mcp:8080/mcp", description="Inventory MCP URL.")
    supplier_mcp_url: str = Field(default="http://supplier-mcp:8080/mcp", description="Supplier MCP URL.")
    shipping_mcp_url: str = Field(default="http://shipping-mcp:8080/mcp", description="Shipping MCP URL.")
    pricing_mcp_url: str = Field(default="http://pricing-mcp:8080/mcp", description="Pricing MCP URL.")

    inventory_a2a_url: str = Field(default="http://inventory:8000/invoke", description="Inventory A2A URL.")
    supplier_a2a_url: str = Field(default="http://supplier:8000/invoke", description="Supplier A2A URL.")
    logistics_a2a_url: str = Field(default="http://logistics:8000/invoke", description="Logistics A2A URL.")
    pricing_a2a_url: str = Field(default="http://pricing:8000/invoke", description="Pricing A2A URL.")

    kv_url: str | None = Field(default=None, description="Optional Azure Key Vault URL for secret hydration.")
