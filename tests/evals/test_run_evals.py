"""Offline tests for safe diagnostics in the golden eval runner."""

from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from tests.evals.run_evals import EvalReport, EvalResult, EvalScenario, run_one, write_diagnostic_report

SAMPLE_LATENCY_S = 12.5


def _scenario(*, must_mention: list[str] | None = None) -> EvalScenario:
    return EvalScenario(
        id="S3-diagnostic-test",
        goal="Check the requested stock plan.",
        sku="ZS-1042",
        store_id="store-101",
        must_mention=must_mention or [],
        must_call=["inventory", "logistics"],
        max_latency_s=180,
    )


@pytest.mark.asyncio
async def test_run_one_records_response_and_observed_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZAVA_EVAL_LATENCY_BUDGET", raising=False)
    response_body = {
        "summary": "Fabrikam RapidShip ETA is one day.",
        "tool_calls": ["inventory", "logistics"],
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=response_body))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_one(client, _scenario(must_mention=["Fabrikam RapidShip", "ETA"]))

    assert result.passed
    assert result.response_body == response_body
    assert result.recorded_calls == ["inventory", "logistics"]
    assert result.status_code == HTTPStatus.OK
    assert result.errors == []
    assert result.missing_mentions == []
    assert result.latency_s >= 0


@pytest.mark.asyncio
async def test_run_one_preserves_missing_mention_failure_and_marks_calls_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZAVA_EVAL_LATENCY_BUDGET", raising=False)
    response_body = {"summary": "The expedited shipment arrives soon."}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=response_body))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_one(client, _scenario(must_mention=["Fabrikam RapidShip", "ETA"]))

    assert not result.passed
    assert result.missing_mentions == ["Fabrikam RapidShip", "ETA"]
    assert result.response_body == response_body
    assert result.recorded_calls is None


@pytest.mark.asyncio
async def test_run_one_records_http_error_and_sanitized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZAVA_EVAL_LATENCY_BUDGET", raising=False)
    response_body = {
        "message": "Backend unavailable",
        "authorization": "Bearer hidden-value",
        "headers": {"authorization": "hidden-value"},
        "env": {"LOCAL_SETTING": "hidden-value"},
        "details": "token=hidden-value",
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(502, json=response_body))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_one(client, _scenario())

    assert not result.passed
    assert result.status_code == HTTPStatus.BAD_GATEWAY
    assert result.errors == ["HTTP 502"]
    assert result.response_body == {
        "message": "Backend unavailable",
        "authorization": "[REDACTED]",
        "headers": "[REDACTED]",
        "env": "[REDACTED]",
        "details": "token=[REDACTED]",
    }
    assert "hidden-value" not in json.dumps(result.model_dump())


@pytest.mark.asyncio
async def test_run_one_records_request_failure_without_exception_details() -> None:
    def fail_request(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed with hidden-value")

    transport = httpx.MockTransport(fail_request)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_one(client, _scenario(must_mention=["Fabrikam RapidShip"]))

    assert not result.passed
    assert result.errors == ["ConnectError"]
    assert result.response_body is None
    assert result.missing_mentions == ["Fabrikam RapidShip"]


@pytest.mark.asyncio
async def test_write_diagnostic_report_serializes_all_scenario_details(tmp_path: Path) -> None:
    result = EvalResult(
        id="S3-diagnostic-test",
        passed=False,
        latency_s=SAMPLE_LATENCY_S,
        missing_mentions=["Fabrikam RapidShip"],
        notes=["latency within budget"],
        response_body={"summary": "Missing carrier"},
        recorded_calls=None,
        status_code=HTTPStatus.OK,
        errors=[],
    )
    report = EvalReport(total=1, failures=1, scenarios=[result])
    output_path = tmp_path / "eval-diagnostic.json"

    await write_diagnostic_report(output_path, report)

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    saved_result = saved["scenarios"][0]
    assert saved["total"] == 1
    assert saved["failures"] == 1
    assert saved_result["response_body"] == {"summary": "Missing carrier"}
    assert saved_result["missing_mentions"] == ["Fabrikam RapidShip"]
    assert saved_result["recorded_calls"] is None
    assert saved_result["latency_s"] == SAMPLE_LATENCY_S
    assert saved_result["status_code"] == HTTPStatus.OK
    assert saved_result["errors"] == []


@pytest.mark.asyncio
async def test_run_one_checks_original_body_but_only_reports_sanitized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZAVA_EVAL_LATENCY_BUDGET", raising=False)
    response_body = {"summary": "token=example-not-a-credential"}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=response_body))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await run_one(client, _scenario(must_mention=["token=example-not-a-credential"]))

    assert result.passed
    assert result.missing_mentions == []
    assert result.response_body == {"summary": "token=[REDACTED]"}
