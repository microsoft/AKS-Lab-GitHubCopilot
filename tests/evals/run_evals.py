"""Golden eval runner for the deployed ZavaShop orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import cast

import httpx
from pydantic import BaseModel, ConfigDict, Field

SCENARIOS_PATH = Path(__file__).with_name("scenarios.jsonl")
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"token|secret|password|credential|authorization|api[_-]?key|access[_-]?key|private[_-]?key|headers?|env(?:ironment)?(?:[_-]?vars?)?",
    re.I,
)
_SENSITIVE_TEXT = (
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(
        r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b"
    ),
)
_SENSITIVE_KEY_VALUE = re.compile(
    r"(?i)\b([A-Z_]*(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY)[A-Z_]*)\b(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


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
    """Result and optional safe diagnostic details for one eval scenario."""

    model_config = ConfigDict(frozen=True)

    id: str
    passed: bool
    latency_s: float
    missing_mentions: list[str]
    notes: list[str]
    response_body: object = None
    recorded_calls: list[str] | None = None
    status_code: int | None = None
    errors: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    """Diagnostic report for one complete eval run."""

    model_config = ConfigDict(frozen=True)

    total: int
    failures: int
    scenarios: list[EvalResult]


def _load_scenarios() -> list[EvalScenario]:
    scenarios: list[EvalScenario] = []
    for line in SCENARIOS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            scenarios.append(EvalScenario.model_validate_json(line))
    return scenarios


def _flatten_response(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).lower()


def _sanitize_text(value: str) -> str:
    sanitized = value
    for pattern in _SENSITIVE_TEXT:
        sanitized = pattern.sub(_REDACTED, sanitized)
    return _SENSITIVE_KEY_VALUE.sub(lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}", sanitized)


def _sanitize_json(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in cast("dict[object, object]", value).items():
            if isinstance(key, str):
                sanitized[key] = _REDACTED if _SENSITIVE_KEY.search(key) else _sanitize_json(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_json(item) for item in cast("list[object]", value)]
    if isinstance(value, str):
        return _sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize_text(str(value))


def _recorded_calls(payload: object) -> list[str] | None:
    if not isinstance(payload, dict):
        return None
    payload_dict = cast("dict[object, object]", payload)
    calls = payload_dict.get("recorded_calls", payload_dict.get("tool_calls"))
    if not isinstance(calls, list):
        return None
    return [_sanitize_text(call) for call in cast("list[object]", calls) if isinstance(call, str)]


async def run_one(client: httpx.AsyncClient, scenario: EvalScenario) -> EvalResult:
    started = time.perf_counter()
    try:
        response = await client.post(
            "/plan",
            json={"goal": scenario.goal, "sku": scenario.sku, "store_id": scenario.store_id},
            timeout=httpx.Timeout(scenario.max_latency_s + 30),
        )
    except httpx.RequestError as exc:
        latency_s = time.perf_counter() - started
        return EvalResult(
            id=scenario.id,
            passed=False,
            latency_s=latency_s,
            missing_mentions=list(scenario.must_mention),
            notes=[],
            errors=[type(exc).__name__],
        )
    latency_s = time.perf_counter() - started
    errors: list[str] = []
    if response.is_error:
        errors.append(f"HTTP {response.status_code}")
    try:
        raw_payload: object = response.json()
    except ValueError:
        raw_payload = response.text
        errors.append("Response body was not valid JSON")
    payload = _sanitize_json(raw_payload)
    flattened = _flatten_response(raw_payload)
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
    passed = not errors and not missing_mentions and all("exceeded" not in note for note in notes)
    return EvalResult(
        id=scenario.id,
        passed=passed,
        latency_s=latency_s,
        missing_mentions=missing_mentions,
        notes=notes,
        response_body=payload,
        recorded_calls=_recorded_calls(payload),
        status_code=response.status_code,
        errors=errors,
    )


async def write_diagnostic_report(path: Path, report: EvalReport) -> None:
    """Write the sanitized eval report without blocking the event loop."""

    serialized = report.model_dump_json(indent=2) + "\n"
    await asyncio.to_thread(path.write_text, serialized, encoding="utf-8")


async def run(diagnostic_output: Path | None = None) -> int:
    endpoint = os.environ.get("ZAVA_ENDPOINT", "http://localhost:8000").rstrip("/")
    scenarios = _load_scenarios()
    failures = 0
    results: list[EvalResult] = []
    timeout = httpx.Timeout(max(scenario.max_latency_s for scenario in scenarios) + 30)
    async with httpx.AsyncClient(base_url=endpoint, timeout=timeout) as client:
        readiness = await client.get("/readyz")
        readiness.raise_for_status()
        warmup = await client.post(
            "/plan",
            json={"goal": "Warm up the plan endpoint.", "sku": "ZS-1042", "store_id": "store-101"},
        )
        warmup.raise_for_status()
        for scenario in scenarios:
            result = await run_one(client, scenario)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"{status} {result.id} latency={result.latency_s:.2f}s")
            if result.missing_mentions:
                print(f"  missing_mentions={result.missing_mentions}")
            for note in result.notes:
                print(f"  note={note}")
            for error in result.errors:
                print(f"  error={error}")
            failures += int(not result.passed)
    print(f"failures={failures} total={len(scenarios)}")
    if diagnostic_output is not None:
        report = EvalReport(total=len(scenarios), failures=failures, scenarios=results)
        await write_diagnostic_report(diagnostic_output, report)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the five ZavaShop golden eval scenarios.")
    parser.add_argument("--diagnostic-output", type=Path, help="Write a sanitized per-scenario JSON report.")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(diagnostic_output=args.diagnostic_output)))


if __name__ == "__main__":
    main()
