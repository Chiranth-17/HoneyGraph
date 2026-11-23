"""Pydantic request schemas for event ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeoPoint(ClosedModel):
    type: Literal["Point"]
    coordinates: tuple[float, float]


class AuthPayload(ClosedModel):
    user: str
    attempts: int = Field(ge=0)


class MqttPayload(ClosedModel):
    topic: str
    clientId: str
    action: str


class HttpPayload(ClosedModel):
    method: str
    path: str
    username: str
    status: int


class CoapPayload(ClosedModel):
    uri: str
    code: str | int


class TelemetryPayload(ClosedModel):
    bytesOut: int = Field(ge=0)
    bytesIn: int = Field(ge=0)


Payload = Annotated[AuthPayload | MqttPayload | HttpPayload | CoapPayload | TelemetryPayload, Field(union_mode="smart")]


class IngestEvent(ClosedModel):
    ts: datetime
    deviceId: str = Field(min_length=1)
    protocol: Literal["mqtt", "coap", "http", "ssh", "telnet"]
    eventType: str = Field(min_length=1)
    srcIp: str = Field(min_length=1)
    geo: GeoPoint
    payload: Payload

    @field_validator("ts")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset")
        return value

    @model_validator(mode="after")
    def protocol_matches_payload(self) -> "IngestEvent":
        expected = {
            "mqtt": MqttPayload,
            "coap": CoapPayload,
            "http": HttpPayload,
            "ssh": AuthPayload,
            "telnet": AuthPayload,
        }
        if isinstance(self.payload, TelemetryPayload):
            return self
        if not isinstance(self.payload, expected[self.protocol]):
            raise ValueError(f"payload shape does not match protocol '{self.protocol}'")
        return self

