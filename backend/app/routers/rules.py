from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from app.api_models import EnableRequest, RuleDocument
from app.auth import AdminUser, CurrentUser
from app.rule_validator import RuleValidationError, validate_rule
from app.serializers import json_value

router = APIRouter(prefix="/api/rules", tags=["rules"])


def validated(body: RuleDocument) -> dict:
    rule = body.model_dump(exclude_none=True)
    try: return validate_rule(rule)
    except RuleValidationError as exc: raise HTTPException(422, detail=str(exc)) from exc


@router.get("", response_model=list[dict])
def list_rules(request: Request, user: CurrentUser) -> list[dict]:
    hits = {row["_id"]: row["hits"] for row in request.app.state.db.alerts.aggregate([{"$group": {"_id": "$ruleId", "hits": {"$sum": 1}}}])}
    items = list(request.app.state.db.rules.find())
    for item in items: item["hitCount"] = hits.get(item["ruleId"], 0)
    return json_value(items)


@router.post("", status_code=201, response_model=dict)
def create(body: RuleDocument, request: Request, user: AdminUser) -> dict:
    rule = validated(body)
    try: request.app.state.rule_db.rules.insert_one(rule)
    except DuplicateKeyError as exc: raise HTTPException(409, "ruleId already exists") from exc
    return json_value(rule)


@router.put("/{rule_id}", response_model=dict)
def replace(rule_id: str, body: RuleDocument, request: Request, user: AdminUser) -> dict:
    rule = validated(body)
    if rule["ruleId"] != rule_id: raise HTTPException(422, "path and body ruleId differ")
    result = request.app.state.rule_db.rules.replace_one({"ruleId": rule_id}, rule)
    if not result.matched_count: raise HTTPException(404, "rule not found")
    return json_value(rule)


@router.delete("/{rule_id}", status_code=204)
def delete(rule_id: str, request: Request, user: AdminUser) -> None:
    if not request.app.state.rule_db.rules.delete_one({"ruleId": rule_id}).deleted_count: raise HTTPException(404, "rule not found")


@router.patch("/{rule_id}/enabled", response_model=dict)
def enable(rule_id: str, body: EnableRequest, request: Request, user: AdminUser) -> dict:
    item = request.app.state.rule_db.rules.find_one_and_update({"ruleId": rule_id}, {"$set": {"active": body.active}}, return_document=True)
    if not item: raise HTTPException(404, "rule not found")
    return json_value(item)
