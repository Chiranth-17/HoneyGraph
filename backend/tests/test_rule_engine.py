"""Phase 4 safety tests for stored aggregation rules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.rule_validator import RuleValidationError, substitute_placeholders, validate_pipeline, validate_rule


def valid_rule() -> dict:
    return {
        "ruleId": "TEST-1",
        "name": "test",
        "stage": "discovery",
        "severity": 5,
        "type": "windowed",
        "window": {"seconds": 60},
        "pipeline": [{"$match": {"srcIp": "{{srcIp}}"}}, {"$group": {"_id": "$srcIp", "count": {"$sum": 1}}}, {"$limit": 1}],
        "active": True,
    }


def test_allowed_read_only_pipeline_and_placeholders() -> None:
    rule = validate_rule(valid_rule())
    timestamp = datetime.now(timezone.utc)
    substituted = substitute_placeholders(rule["pipeline"], {"srcIp": "192.0.2.10", "deviceId": "d1", "ts": timestamp, "eventId": "id"})
    assert substituted[0]["$match"]["srcIp"] == "192.0.2.10"
    assert rule["pipeline"][0]["$match"]["srcIp"] == "{{srcIp}}"


@pytest.mark.parametrize("operator", ["$out", "$merge", "$function", "$where", "$accumulator", "$lookup"])
def test_forbidden_operator_is_rejected(operator: str) -> None:
    with pytest.raises(RuleValidationError, match="forbidden|not allowed"):
        validate_pipeline([{operator: "danger"}])


def test_nested_forbidden_operator_is_rejected() -> None:
    with pytest.raises(RuleValidationError, match=r"\$function"):
        validate_pipeline([{"$project": {"computed": {"$function": {"body": "", "args": [], "lang": "js"}}}}])


def test_unlisted_stage_is_rejected() -> None:
    with pytest.raises(RuleValidationError, match="not allowed"):
        validate_pipeline([{"$facet": {"branch": [{"$match": {}}]}}])
