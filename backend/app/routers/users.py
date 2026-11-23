from fastapi import APIRouter, HTTPException, Request

from app.api_models import UserActive, UserCreate
from app.auth import AdminUser, PASSWORDS
from app.serializers import json_value

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[dict])
def users(request: Request, user: AdminUser) -> list[dict]:
    return json_value(list(request.app.state.db.users.find({}, {"passwordHash": 0}).sort("username", 1)))


@router.post("", status_code=201, response_model=dict)
def create(body: UserCreate, request: Request, user: AdminUser) -> dict:
    if request.app.state.db.users.find_one({"username": body.username}): raise HTTPException(409, "username already exists")
    item = {"username": body.username, "passwordHash": PASSWORDS.hash(body.password), "role": body.role, "active": True}
    request.app.state.db.users.insert_one(item)
    return {"username": body.username, "role": body.role, "active": True}


@router.patch("/{username}", response_model=dict)
def active(username: str, body: UserActive, request: Request, user: AdminUser) -> dict:
    if username == user["username"] and not body.active: raise HTTPException(409, "cannot disable current administrator")
    result = request.app.state.db.users.update_one({"username": username}, {"$set": {"active": body.active}})
    if not result.matched_count: raise HTTPException(404, "user not found")
    return {"username": username, "active": body.active}
