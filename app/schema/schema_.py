from datetime import datetime
from typing import Any, List, Literal, Optional
import re

from pydantic import BaseModel, Field, field_validator
import math

DEVICE_ID_PATTERN = re.compile(r"^[A-Z]+_\d+$")
ConversationStatusLiteral = Literal["WAITING", "COMPLETED", "CANCELLED"]


def _validate_device_id(value: str) -> str:
    if not DEVICE_ID_PATTERN.fullmatch(value):
        raise ValueError("invalid_device_id_format")
    return value


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    message: str
    details: Optional[Any] = None


class SignRequest(BaseModel):
    device_id: str = Field(..., examples=["SEOUL_01"])
    keypoints: List[float] = Field(..., description="21개 손 랜드마크의 63차원 좌표")

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        return _validate_device_id(value)

    @field_validator("keypoints")
    @classmethod
    def validate_keypoints(cls, value: List[float]) -> List[float]:
        if len(value) != 63:
            raise ValueError("invalid_feature_length")
        if not all(math.isfinite(point) for point in value):
            raise ValueError("keypoints_must_be_finite")
        return value


class InferenceResponse(BaseModel):
    recognized_word: str = Field(..., examples=["ㅏ"])
    confidence: float = Field(..., ge=0.0, le=1.0, examples=[0.95])


class ConversationCreateRequest(BaseModel):
    device_id: str = Field(..., examples=["SEOUL_01"])
    question_text: str = Field(..., examples=["화장실이 어디예요?"])

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        return _validate_device_id(value)

    @field_validator("question_text")
    @classmethod
    def validate_question_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("question_text_required")
        if len(text) > 500:
            raise ValueError("question_text_too_long")
        return text


class ConversationCreateResponse(BaseModel):
    conversation_id: int
    status: ConversationStatusLiteral


class ConversationResponse(BaseModel):
    conversation_id: int
    status: ConversationStatusLiteral
    staff_reply: Optional[str] = None


class StaffReply(BaseModel):
    conversation_id: int
    reply: str

    @field_validator("reply")
    @classmethod
    def validate_reply(cls, value: str) -> str:
        reply = value.strip()
        if not reply:
            raise ValueError("reply_required")
        if len(reply) > 500:
            raise ValueError("reply_too_long")
        return reply


class WaitingItem(BaseModel):
    conversation_id: int
    device_id: str
    station_name: str
    location: Optional[str] = None
    question_text: str
    status: ConversationStatusLiteral
    created_at: datetime


class WaitingListResponse(BaseModel):
    status: Literal["success"] = "success"
    total: int
    page: int
    limit: int
    total_pages: int
    items: List[WaitingItem]


class StaffReplyResponse(BaseModel):
    message: str
    conversation_id: int


class AdminLoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


class AuthStatusResponse(BaseModel):
    authenticated: bool


class DeviceCreateRequest(BaseModel):
    device_id: str = Field(..., examples=["SEOUL_01"])
    station_name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=100)

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, value: str) -> str:
        return _validate_device_id(value.strip())

    @field_validator("station_name")
    @classmethod
    def validate_station_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("station_name_required")
        return cleaned

    @field_validator("location")
    @classmethod
    def validate_location(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None


class DeviceUpdateRequest(BaseModel):
    station_name: str = Field(..., min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=100)

    @field_validator("station_name")
    @classmethod
    def validate_station_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("station_name_required")
        return cleaned

    @field_validator("location")
    @classmethod
    def validate_location(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None


class DeviceResponse(BaseModel):
    device_id: str
    station_name: str
    location: Optional[str] = None


class HealthStatus(BaseModel):
    database: str
    ai_model: str
    all_systems_ready: bool
    timestamp: str
