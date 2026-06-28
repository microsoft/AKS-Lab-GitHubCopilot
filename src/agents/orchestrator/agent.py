"""GitHub Copilot SDK factory for the ZavaShop orchestrator agent."""

from __future__ import annotations

from dataclasses import dataclass

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.generated.rpc import PermissionDecisionApproveOnce
from copilot.session import PermissionRequestResult

from src.shared.copilot import build_copilot_client
from src.shared.settings import Settings

from .prompts import SYSTEM_PROMPT
from .tools import TOOLS


def _approve_all(_request: object, _context: dict[str, str]) -> PermissionRequestResult:
    return PermissionDecisionApproveOnce()


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
        client=build_copilot_client(),
        instructions=SYSTEM_PROMPT,
        name="orchestrator",
        description="ZavaShop orchestrator for single-store stock-out response planning.",
        tools=list(TOOLS),
        default_options=GitHubCopilotOptions(
            model=settings.copilot_model,
            timeout=settings.copilot_timeout_seconds,
            on_permission_request=_approve_all,
        ),
    )
    return _RunnableAgent(agent=agent)
