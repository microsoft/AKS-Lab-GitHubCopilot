"""Schema and seeded-data checks for the five golden eval scenarios."""

from __future__ import annotations

import json

from tests.evals.run_evals import SCENARIOS_PATH, EvalScenario

EXPECTED_SCENARIO_COUNT = 5
REQUIRED_FIELDS = {
    "id",
    "goal",
    "sku",
    "store_id",
    "must_mention",
    "must_call",
    "forbid_call",
    "max_latency_s",
}
EXPECTED_SCENARIO_PREFIXES = {"S1", "S2", "S3", "S4", "S5"}


def test_five_golden_scenarios_cover_required_business_cases() -> None:
    lines = [line for line in SCENARIOS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]
    assert all(set(record) == REQUIRED_FIELDS for record in records)
    scenarios = [EvalScenario.model_validate_json(line) for line in lines]

    assert len(scenarios) == EXPECTED_SCENARIO_COUNT
    assert {scenario.id.split("-")[0] for scenario in scenarios} == EXPECTED_SCENARIO_PREFIXES
    for scenario in scenarios:
        assert scenario.sku == "ZS-1042"
        assert scenario.store_id == "store-101"
        assert scenario.goal
        assert scenario.max_latency_s > 0
        assert scenario.must_call
        assert scenario.forbid_call == []

    scenarios_by_id = {scenario.id.split("-")[0]: scenario for scenario in scenarios}
    assert "84" in scenarios_by_id["S2"].must_mention
    assert "420" in scenarios_by_id["S2"].must_mention
    assert "Fabrikam RapidShip" in scenarios_by_id["S3"].must_mention

    for scenario_id in ("S4", "S5"):
        mentions = scenarios_by_id[scenario_id].must_mention
        assert "39.99" in mentions
        assert "34.99" not in mentions
