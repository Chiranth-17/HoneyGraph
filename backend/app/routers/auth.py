from fastapi import APIRouter, HTTPException, Request

from app.api_models import LoginRequest, TokenResponse
from app.auth import authenticate, create_token

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request) -> TokenResponse:
    user = authenticate(request.app.state.db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenResponse(access_token=create_token(user), role=user["role"])
