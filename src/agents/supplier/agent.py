"""GitHub Copilot SDK factory for the ZavaShop supplier specialist agent."""

from __future__ import annotations

from dataclasses import dataclass

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.generated.rpc import PermissionDecisionApproved
from copilot.session import PermissionRequestResult

from src.shared.settings import Settings

from .prompts import SYSTEM_PROMPT
from .tools import TOOLS


def _approve_all(_request: object, _context: dict[str, str]) -> PermissionRequestResult:
    return PermissionDecisionApproved()


@dataclass
class _AgentRunResult:
    output_text: str


@dataclass(frozen=True)
class _RunnableAgent:
    """Adapter satisfying the shared make_app runnable protocol."""

    agent: GitHubCopilotAgent

    async def run(self, message: str, /) -> _AgentRunResult:
        response = await self.agent.run(message)
        return _AgentRunResult(output_text=response.text)


async def build_agent(settings: Settings) -> _RunnableAgent:
    agent = GitHubCopilotAgent(
        instructions=SYSTEM_PROMPT,
        name="supplier",
        description="ZavaShop supplier specialist for replenishment and purchase-order drafts.",
        tools=list(TOOLS),
        default_options=GitHubCopilotOptions(
            model=settings.copilot_model,
            timeout=settings.copilot_timeout_seconds,
            on_permission_request=_approve_all,
            mcp_servers={
                "supplier": {
                    "type": "http",
                    "url": settings.supplier_mcp_url,
                    "tools": ["*"],
                    "timeout": int(settings.copilot_timeout_seconds),
                },
            },
        ),
    )
    return _RunnableAgent(agent=agent)
