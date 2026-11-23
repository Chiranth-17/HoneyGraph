"""JWT authentication and application-role authorization."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

PASSWORDS = CryptContext(schemes=["bcrypt"], deprecated="auto")
BEARER = HTTPBearer(auto_error=False)


def create_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["username"], "role": user["role"], "iat": now,
        "exp": now + timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "60"))),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=os.getenv("JWT_ALGORITHM", "HS256"))


def authenticate(db: Any, username: str, password: str) -> dict[str, Any] | None:
    user = db.users.find_one({"username": username, "active": True})
    return user if user and PASSWORDS.verify(password, user["passwordHash"]) else None


def current_user(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER)]
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    try:
        payload = jwt.decode(credentials.credentials, os.environ["JWT_SECRET"], algorithms=[os.getenv("JWT_ALGORITHM", "HS256")])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc
    user = request.app.state.db.users.find_one({"username": payload.get("sub"), "active": True})
    if not user:
        raise HTTPException(status_code=401, detail="user is inactive or missing")
    return {"username": user["username"], "role": user["role"]}


def require_role(*roles: str) -> Callable[..., dict[str, str]]:
    def dependency(user: Annotated[dict[str, str], Depends(current_user)]) -> dict[str, str]:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="insufficient role")
        return user
    return dependency


CurrentUser = Annotated[dict[str, str], Depends(current_user)]
AdminUser = Annotated[dict[str, str], Depends(require_role("admin"))]
