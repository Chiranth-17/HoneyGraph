"""Validation and safe placeholder substitution for stored rule pipelines."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

ALLOWED_STAGES = {
    "$match",
    "$group",
    "$project",
    "$sort",
    "$limit",
    "$count",
    "$addFields",
    "$set",
    "$unwind",
}
FORBIDDEN_OPERATORS = {"$out", "$merge", "$function", "$where", "$accumulator", "$lookup"}
PLACEHOLDER = re.compile(r"^\{\{(srcIp|deviceId|ts|eventId)\}\}$")


class RuleValidationError(ValueError):
    """Raised when a rule could mutate data or escape its collection."""


def _reject_forbidden(value: Any, path: str = "pipeline") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_OPERATORS:
                raise RuleValidationError(f"forbidden operator {key} at {path}")
            _reject_forbidden(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_forbidden(nested, f"{path}[{index}]")


def validate_pipeline(pipeline: Any) -> list[dict[str, Any]]:
    if not isinstance(pipeline, list) or not pipeline:
        raise RuleValidationError("pipeline must be a non-empty array")
    if len(pipeline) > 32:
        raise RuleValidationError("pipeline cannot contain more than 32 stages")
    for index, stage in enumerate(pipeline):
        if not isinstance(stage, dict) or len(stage) != 1:
            raise RuleValidationError(f"pipeline stage {index} must contain exactly one operator")
        operator = next(iter(stage))
        if operator not in ALLOWED_STAGES:
            raise RuleValidationError(f"stage {operator} is not allowed")
        _reject_forbidden(stage, f"pipeline[{index}]")
    return pipeline


def validate_rule(rule: dict[str, Any]) -> dict[str, Any]:
    required = {"ruleId", "name", "stage", "severity", "type", "window", "pipeline", "active"}
    missing = sorted(required - rule.keys())
    if missing:
        raise RuleValidationError(f"missing rule fields: {', '.join(missing)}")
    if rule["type"] not in {"windowed", "distinct", "sequence", "baseline", "allowlist"}:
        raise RuleValidationError(f"unsupported rule type: {rule['type']}")
    if not isinstance(rule["severity"], int) or not 1 <= rule["severity"] <= 10:
        raise RuleValidationError("severity must be an integer from 1 through 10")
    window = rule["window"]
    if not isinstance(window, dict) or not isinstance(window.get("seconds"), int) or window["seconds"] <= 0:
        raise RuleValidationError("window.seconds must be a positive integer")
    validate_pipeline(rule["pipeline"])
    return rule


def substitute_placeholders(value: Any, context: dict[str, Any]) -> Any:
    """Return a deep substituted copy; only complete placeholder strings change."""
    if isinstance(value, str):
        match = PLACEHOLDER.match(value)
        return context[match.group(1)] if match else value
    if isinstance(value, dict):
        return {key: substitute_placeholders(nested, context) for key, nested in value.items()}
    if isinstance(value, list):
        return [substitute_placeholders(nested, context) for nested in value]
    return deepcopy(value)

