---
applyTo: "src/**/*.py,tests/**/*.py"
---

# Python coding conventions

## Project setup
- `uv` is the only package manager. Add deps with `uv add <pkg>` and dev deps with `uv add --dev <pkg>`.
- `pyproject.toml` is the source of truth. Do not maintain a `requirements.txt`.

## Style
- Line length **120**. Ruff rules: `E,F,I,B,UP,N,ASYNC,PL,RUF` with `PLR0913` ignored.
- Use `from __future__ import annotations` at top of every module.
- Module docstring required for every file under `src/`.

## Async
- Every public function in an agent module is `async def`.
- Use `asyncio.TaskGroup` (3.11+) for concurrent fan-out, not `asyncio.gather` unless cancellation semantics matter.
- Always pass a `timeout` to network calls. Use `anyio.fail_after()` or `httpx.Timeout`.

## Typing
- `pyright --strict` clean. `Any` requires a `# noqa: ANN401 — <reason>` comment.
- Prefer `Protocol` for duck-typed dependencies in tests.

## Pydantic
- v2 only. Models that cross process boundaries are `frozen=True`.
- Use `Field(..., description=...)` — descriptions are exposed to the LLM as schema metadata.

## Logging
- `structlog.get_logger(__name__)` at module top.
- Bind `agent_name`, `run_id` early: `log = log.bind(agent_name="inventory", run_id=run_id)`.
- Log levels: `debug` for tool calls, `info` for run start/end, `warning` for retried failures, `error` for unrecoverable.

## Tests
- File pattern: `tests/test_<module>.py`. One test class per public function under test.
- Use `pytest.mark.asyncio` markers. Fixtures live in `tests/conftest.py`.
- Mock chat clients with `agent_framework.testing.MockChatClient`. Never call a real model in unit tests.
