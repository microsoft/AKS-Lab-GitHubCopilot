# Skill: A2A Loopback Tests

Use this skill in `test-author` mode when writing integration tests that exercise multiple agents without Docker.

## The fixture

```python
# tests/integration/conftest.py
import httpx
import pytest
from httpx import ASGITransport
from agent_framework.testing import MockChatClient

from src.agents.inventory.server import app as inventory_app
from src.agents.supplier.server import app as supplier_app
# ...orchestrator etc.


@pytest.fixture
async def fleet(monkeypatch):
    # 1. Patch GitHubCopilotAgent at every agent's import site so the
    #    real SDK / bundled Node CLI never starts.
    fake = MockChatClient()  # exposes async .run(message) -> AgentResponse[None]
    for mod in (
        "src.agents.inventory.agent",
        "src.agents.supplier.agent",
        "src.agents.logistics.agent",
        "src.agents.pricing.agent",
        "src.agents.orchestrator.agent",
    ):
        monkeypatch.setattr(f"{mod}.GitHubCopilotAgent", lambda **_: fake)

    # 2. Mount each FastAPI app behind ASGITransport.
    clients = {
        "inventory": httpx.AsyncClient(transport=ASGITransport(app=inventory_app),
                                       base_url="http://inventory"),
        # ... etc
    }
    yield clients
    for c in clients.values():
        await c.aclose()
```

## Rules

1. **Never** import `GitHubCopilotAgent` directly in a test — always patch its import site so the real SDK / Node CLI never runs.
2. **Never** start a real network server (no `uvicorn.run`). ASGITransport only.
3. Do **not** patch `MCPStreamableHTTPTool` — it is not used in this repo. MCP wiring lives inside `GitHubCopilotOptions(mcp_servers={...})`; the agent is already mocked at step 1, so MCP is short-circuited automatically.
4. Assert structure (`response.json()["tool_calls"]`) and keyword presence (`"store-101" in response.json()["output"]`). No exact string equality.
5. Mark every test `pytest.mark.asyncio` (or rely on `asyncio_mode = "auto"` in `pyproject.toml`).

## Eval runner shape

```python
# tests/evals/run_evals.py
async def run() -> int:
    failures = 0
    async with httpx.AsyncClient(base_url=os.environ.get("ZAVA_ENDPOINT", "http://localhost:8000")) as c:
        for line in scenarios_path.read_text().splitlines():
            sc = json.loads(line)
            r = (await c.post("/invoke", json={"run_id": sc["id"], "goal": sc["goal"]})).json()
            failures += not all(kw in r["output"] for kw in sc["must_mention"])
            failures += not set(sc["must_call"]).issubset(set(r["tool_calls"]))
    return failures
```
