"""Golden eval runner for the deployed ZavaShop orchestrator."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

SCENARIOS_PATH = Path(__file__).with_name("scenarios.jsonl")


class EvalScenario(BaseModel):
    """One golden scenario for the live orchestrator endpoint."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    must_mention: list[str] = Field(default_factory=list)
    must_call: list[str] = Field(default_factory=list)
    forbid_call: list[str] = Field(default_factory=list)
    max_latency_s: float = Field(default=180, gt=0)


class EvalResult(BaseModel):
    """Result for one eval scenario."""

    model_config = ConfigDict(frozen=True)

    id: str
    passed: bool
    latency_s: float
    missing_mentions: list[str]
    notes: list[str]


def _load_scenarios() -> list[EvalScenario]:
    scenarios: list[EvalScenario] = []
    for line in SCENARIOS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            scenarios.append(EvalScenario.model_validate_json(line))
    return scenarios


def _flatten_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).lower()


async def _run_one(client: httpx.AsyncClient, scenario: EvalScenario) -> EvalResult:
    started = time.perf_counter()
    response = await client.post(
        "/plan",
        json={"goal": scenario.goal, "sku": scenario.sku, "store_id": scenario.store_id},
    )
    latency_s = time.perf_counter() - started
    response.raise_for_status()
    payload = response.json()
    flattened = _flatten_response(payload)
    missing_mentions = [term for term in scenario.must_mention if term.lower() not in flattened]
    notes: list[str] = []
    if scenario.must_call:
        notes.append(f"expected specialists: {','.join(scenario.must_call)}")
    if scenario.forbid_call:
        notes.append(f"forbidden specialists recorded for review: {','.join(scenario.forbid_call)}")
    if latency_s > scenario.max_latency_s:
        notes.append(f"latency {latency_s:.2f}s exceeded scenario budget {scenario.max_latency_s:.2f}s")
    budget = float(os.environ.get("ZAVA_EVAL_LATENCY_BUDGET", "0"))
    if budget > 0 and latency_s > budget:
        notes.append(f"latency {latency_s:.2f}s exceeded global budget {budget:.2f}s")
    passed = not missing_mentions and all("exceeded" not in note for note in notes)
    return EvalResult(
        id=scenario.id,
        passed=passed,
        latency_s=latency_s,
        missing_mentions=missing_mentions,
        notes=notes,
    )


async def run() -> int:
    endpoint = os.environ.get("ZAVA_ENDPOINT", "http://localhost:8000").rstrip("/")
    scenarios = _load_scenarios()
    failures = 0
    timeout = httpx.Timeout(240.0)
    async with httpx.AsyncClient(base_url=endpoint, timeout=timeout) as client:
        for scenario in scenarios:
            result = await _run_one(client, scenario)
            status = "PASS" if result.passed else "FAIL"
            print(f"{status} {result.id} latency={result.latency_s:.2f}s")
            if result.missing_mentions:
                print(f"  missing_mentions={result.missing_mentions}")
            for note in result.notes:
                print(f"  note={note}")
            failures += int(not result.passed)
    print(f"failures={failures} total={len(scenarios)}")
    return failures


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
