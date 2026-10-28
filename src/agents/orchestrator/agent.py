"""GitHub Copilot SDK factory for the ZavaShop orchestrator agent."""

from __future__ import annotations

from dataclasses import dataclass

from agent_framework import tool
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.generated.rpc import PermissionDecisionApproveOnce
from copilot.session import PermissionRequestResult

from src.shared.copilot import build_copilot_client
from src.shared.settings import Settings

from .a2a import A2AClient
from .prompts import SYSTEM_PROMPT


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
    a2a_client = A2AClient(settings=settings)

    @tool(name="ask_inventory", description="Delegate a stock question to the inventory specialist.")
    async def ask_inventory(goal: str) -> str:
        """Forward the goal to the inventory specialist.

        Args:
            goal: The goal text to forward.
        Returns:
            The specialist plain-text output.
        """

        return await a2a_client.invoke(name="inventory", url=settings.inventory_a2a_url, goal=goal)

    @tool(name="ask_supplier", description="Delegate a replenishment question to the supplier specialist.")
    async def ask_supplier(goal: str) -> str:
        """Forward the goal to the supplier specialist.

        Args:
            goal: The goal text to forward.
        Returns:
            The specialist plain-text output.
        """

        return await a2a_client.invoke(name="supplier", url=settings.supplier_a2a_url, goal=goal)

    @tool(name="ask_logistics", description="Delegate a shipment question to the logistics specialist.")
    async def ask_logistics(goal: str) -> str:
        """Forward the goal to the logistics specialist.

        Args:
            goal: The goal text to forward.
        Returns:
            The specialist plain-text output.
        """

        return await a2a_client.invoke(name="logistics", url=settings.logistics_a2a_url, goal=goal)

    @tool(name="ask_pricing", description="Delegate a price question to the pricing specialist.")
    async def ask_pricing(goal: str) -> str:
        """Forward the goal to the pricing specialist.

        Args:
            goal: The goal text to forward.
        Returns:
            The specialist plain-text output.
        """

        return await a2a_client.invoke(name="pricing", url=settings.pricing_a2a_url, goal=goal)

    agent = GitHubCopilotAgent(
        client=build_copilot_client(),
        instructions=SYSTEM_PROMPT,
        name="orchestrator",
        description="ZavaShop orchestrator for single-store stock-out response planning.",
        tools=[ask_inventory, ask_supplier, ask_logistics, ask_pricing],
        default_options=GitHubCopilotOptions(
            model=settings.copilot_model,
            timeout=settings.copilot_timeout_seconds,
            on_permission_request=_approve_all,
        ),
    )
    return _RunnableAgent(agent=agent)
