"""Optional async hydration of runtime secrets from Azure Key Vault."""

from __future__ import annotations

import os

from azure.identity.aio import DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient

from .settings import Settings

_SECRET_ENVIRONMENT_MAPPINGS = (
    ("GITHUB-TOKEN", "GITHUB_TOKEN"),
    ("INVENTORY-MCP-URL", "ZAVA_INVENTORY_MCP_URL"),
    ("SUPPLIER-MCP-URL", "ZAVA_SUPPLIER_MCP_URL"),
    ("SHIPPING-MCP-URL", "ZAVA_SHIPPING_MCP_URL"),
    ("PRICING-MCP-URL", "ZAVA_PRICING_MCP_URL"),
)


async def hydrate_from_keyvault(*, settings: Settings | None = None) -> None:
    """Populate missing runtime environment variables from optional Key Vault secrets.

    Args:
        settings: Optional explicit settings override. When omitted, the vault URL
            is read from the current ``ZAVA_KV_URL`` environment variable.

    Raises:
        Exception: Propagates credential, client, or secret retrieval failures.
    """

    vault_url = settings.kv_url if settings is not None else os.environ.get("ZAVA_KV_URL")
    if not vault_url:
        return

    credential = DefaultAzureCredential()
    try:
        client = SecretClient(vault_url=vault_url, credential=credential)
        try:
            for secret_name, environment_name in _SECRET_ENVIRONMENT_MAPPINGS:
                if environment_name in os.environ:
                    continue
                secret = await client.get_secret(secret_name)
                if secret.value is None:
                    raise ValueError(f"Key Vault secret {secret_name!r} has no value")
                os.environ[environment_name] = secret.value
        finally:
            await client.close()
    finally:
        await credential.close()
