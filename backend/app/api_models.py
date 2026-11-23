"""OpenAPI request and response models for the HoneyGraph REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(ApiModel):
    username: str
    password: str


class TokenResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: Literal["analyst", "admin"]


class PageResponse(ApiModel):
    items: list[dict[str, Any]]
    page: int
    pageSize: int
    total: int


class StatusRequest(ApiModel):
    status: Literal["triaged", "closed"]


class RuleDocument(ApiModel):
    ruleId: str
    name: str
    stage: str
    severity: int = Field(ge=1, le=10)
    type: Literal["windowed", "distinct", "sequence", "baseline", "allowlist"]
    window: dict[str, Any]
    pipeline: list[dict[str, Any]]
    active: bool = True
    trigger: dict[str, Any] = Field(default_factory=dict)
    cooldownSeconds: int = Field(default=300, gt=0)
    baselineMultiplier: float | None = None


class EnableRequest(ApiModel):
    active: bool


class UserCreate(ApiModel):
    username: str = Field(min_length=3)
    password: str = Field(min_length=8)
    role: Literal["analyst", "admin"]


class UserActive(ApiModel):
    active: bool


class IntegrityRequest(ApiModel):
    deviceId: str | None = None


class TamperRequest(ApiModel):
    action: Literal["edit", "delete", "swap"]
    eventIds: list[str] = Field(min_length=1, max_length=2)


class ScenarioRequest(ApiModel):
    name: Literal["mirai_bruteforce", "recon", "credential_stuffing", "mqtt_abuse", "lateral_movement", "exfil_burst", "log_tamper"]
    seed: int = 42
    deferCorrelation: bool = Field(default=False, description="Presentation mode: inspect real events and alerts before explicitly building incidents.")

