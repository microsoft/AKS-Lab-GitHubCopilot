"""Regression tests for optional Key Vault startup hydration."""

from __future__ import annotations

import pytest

from src.shared import keyvault


@pytest.mark.asyncio
async def test_unset_keyvault_url_skips_credentials_and_secret_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZAVA_KV_URL", raising=False)

    def fail_if_constructed() -> None:
        pytest.fail("Azure credentials must not be constructed when Key Vault is unconfigured")

    monkeypatch.setattr(keyvault, "DefaultAzureCredential", fail_if_constructed)
    monkeypatch.setattr(keyvault, "SecretClient", fail_if_constructed)

    await keyvault.hydrate_from_keyvault()
