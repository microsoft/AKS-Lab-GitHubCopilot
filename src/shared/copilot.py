"""GitHub Copilot SDK client helpers."""

from __future__ import annotations

import os

from copilot.client import CopilotClient


def build_copilot_client() -> CopilotClient:
    """Build a Copilot SDK client using the mounted GitHub token when present."""

    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        return CopilotClient(github_token=github_token, use_logged_in_user=False)
    return CopilotClient()
