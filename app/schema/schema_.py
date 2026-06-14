from datetime import datetime
from typing import Any, List, Literal, Optional
import re

from pydantic import BaseModel, Field, field_validator

DEVICE_ID_PATTERN = re.compile(r"^[A-Z]+_\d+$")


# =========================
# Common Response Schemas
# =========================

class SuccessResponse(BaseModel):
    status: Literal["success"] = Field(default="success", description="요청 처리 상태")


class ErrorResponse(BaseModel):
    status: Literal["error"] = Field(default="error", description="요청 처리 상태")
    message: str = Field(..., description="오류 코드 또는 메시지")
    details: Optional[Any] = Field(default=None, description="오류 상세 정보")


# =========================
# Kiosk API
# =========================

class SignRequest(BaseModel):
    """키오스크 수어 추론 요청 스키마"""
    device_id: str = Field(
        ...,
        examples=["SEOUL_01"],
        description="키오스크 기기 ID",
    )
    keypoints: List[float] = Field(
        ...,
        description="수어 인식용 keypoints (63개 피처)",
    )

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        if not DEVICE_ID_PATTERN.fullmatch(v):
            raise ValueError("invalid_device_id_format")
        return v

    @field_validator("keypoints")
    @classmethod
    def validate_keypoints(cls, v: List[float]) -> List[float]:
        if not v:
            raise ValueError("keypoints_required")

        if len(v) != 63:
            raise ValueError("invalid_feature_length")

        return v


class InferenceResponse(BaseModel):
    """수어 추론 응답 스키마"""
    log_id: int = Field(..., examples=[1], description="생성된 대화 로그 ID (미인식 시 0)")
    recognized_word: str = Field(..., examples=["ㅏ"], description="AI가 인식한 자모 (미인식 시 'none')")
    confidence: float = Field(..., examples=[0.95], description="추론 신뢰도 (0.0 ~ 1.0)")


class PollAnswerResponse(BaseModel):
    """역무원 답변 폴링 응답 스키마"""
    status: Literal["WAITING", "COMPLETED"] = Field(
        ..., examples=["WAITING"], description="현재 대화 상태"
    )
    staff_reply: Optional[str] = Field(default=None, description="역무원 답변 내용 (WAITING 시 null)")


# =========================
# Staff API
# =========================

class StaffReply(BaseModel):
    """역무원 답변 등록 요청 스키마"""
    log_id: int = Field(..., examples=[1], description="답변할 대화 로그 ID")
    reply: str = Field(
        ...,
        examples=["화장실은 오른쪽 20m 앞에 있습니다."],
        description="역무원 답변 내용",
    )

    @field_validator("reply")
    @classmethod
    def validate_reply(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("reply_required")
        if len(value) > 500:
            raise ValueError("reply_too_long")
        return value


class WaitingItem(BaseModel):
    """답변 대기 목록의 개별 항목"""
    log_id: int = Field(..., examples=[1], description="대화 로그 ID")
    device_id: str = Field(..., examples=["SEOUL_01"], description="키오스크 기기 ID")
    label_id: int = Field(..., examples=[3], description="AI 라벨 ID")
    recognized_word: str = Field(..., examples=["출구"], description="인식된 단어")
    communication_status: Literal["WAITING", "COMPLETED"] = Field(
        ..., examples=["WAITING"], description="현재 대화 상태"
    )
    created_at: datetime = Field(..., description="로그 생성 시간")


class WaitingListResponse(BaseModel):
    """답변 대기 목록 조회 응답 스키마"""
    status: Literal["success"] = Field(default="success", examples=["success"], description="요청 처리 상태")
    total: int = Field(..., examples=[25], description="전체 대기 건수")
    page: int = Field(..., examples=[1], description="현재 페이지 번호")
    limit: int = Field(..., examples=[20], description="페이지당 항목 수")
    total_pages: int = Field(..., examples=[2], description="전체 페이지 수")
    items: List[WaitingItem] = Field(..., description="대기 중인 대화 목록")


class StaffReplyResponse(BaseModel):
    """역무원 답변 등록 응답 스키마"""
    message: str = Field(..., examples=["답변이 등록되었습니다."], description="결과 메시지")
    log_id: int = Field(..., examples=[1], description="답변이 등록된 대화 로그 ID")


# =========================
# Health API
# =========================

class HealthStatus(BaseModel):
    """시스템 상태 점검 응답 스키마"""
    database: str = Field(..., examples=["connected"], description="데이터베이스 연결 상태")
    ai_model: str = Field(..., examples=["loaded"], description="AI 모델 로드 상태")
    all_systems_ready: bool = Field(..., examples=[True], description="전체 시스템 준비 여부")
    timestamp: str = Field(..., examples=["2026-03-27T19:30:00+09:00"], description="상태 점검 시각")