import hmac
import logging
import os
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.model.db_model import CommunicationStatus
from app.schema.schema_ import (
    ErrorResponse,
    StaffReply,
    StaffReplyResponse,
    WaitingListResponse,
)
from app.services.staff_service import (
    get_log_for_reply,
    get_waiting_logs,
)

logger = logging.getLogger(__name__)

# 운영 환경 변수로 주입 (settings/config 모듈이 있다면 그쪽으로 옮기는 것을 권장)
STAFF_API_KEY = os.environ.get("STAFF_API_KEY")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> None:
    # 키가 설정되지 않았으면 열린 채로 두지 않고 막아버린다 (fail-closed)
    if not STAFF_API_KEY:
        logger.error("STAFF_API_KEY 미설정 - 인증을 적용할 수 없음")
        raise HTTPException(status_code=500, detail="staff_auth_not_configured")

    # hmac.compare_digest로 타이밍 공격 방지
    if not api_key or not hmac.compare_digest(api_key, STAFF_API_KEY):
        raise HTTPException(status_code=401, detail="invalid_api_key")


# 라우터 레벨에 의존성을 걸어 /list, /reply 전부를 한 번에 보호한다.
router = APIRouter(
    prefix="/staff",
    tags=["Staff"],
    dependencies=[Depends(verify_api_key)],
)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

KST = timezone(timedelta(hours=9))
UTC = timezone.utc


def to_kst(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(KST)


@router.get(
    "/list",
    summary="답변 대기 목록 조회",
    response_model=WaitingListResponse,
    responses={
        401: {"model": ErrorResponse, "description": "인증 실패"},
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
)
async def waiting_list(
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="페이지당 개수",
    ),
    db: Session = Depends(get_db),
) -> WaitingListResponse:
    try:
        skip = (page - 1) * limit
        total_count, logs = get_waiting_logs(db, skip=skip, limit=limit)
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0

        return WaitingListResponse(
            status="success",
            total=total_count,
            page=page,
            limit=limit,
            total_pages=total_pages,
            items=[
                {
                    "log_id": log.log_id,
                    "device_id": log.device_id,
                    "label_id": log.label_id,
                    "recognized_word": log.recognized_word,
                    "communication_status": log.status.value,
                    "created_at": to_kst(log.created_at),
                }
                for log in logs
            ],
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("답변 대기 목록 조회 중 오류 발생")
        raise HTTPException(status_code=500, detail="waiting_list_error")


@router.post(
    "/reply",
    summary="역무원 답변 등록",
    response_model=StaffReplyResponse,
    responses={
        400: {"model": ErrorResponse, "description": "잘못된 입력값"},
        401: {"model": ErrorResponse, "description": "인증 실패"},
        404: {"model": ErrorResponse, "description": "대상 로그 없음"},
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
)
async def reply(
    data: StaffReply,
    db: Session = Depends(get_db),
) -> StaffReplyResponse:
    try:
        log = get_log_for_reply(db, data.log_id)

        if not log:
            raise HTTPException(status_code=404, detail="log_not_found")

        if log.status == CommunicationStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="reply_already_completed")

        log.staff_reply = data.reply
        log.status = CommunicationStatus.COMPLETED

        db.commit()
        db.refresh(log)

        logger.info("역무원 답변 등록 완료 | log_id=%s, device=%s", log.log_id, log.device_id)

        return StaffReplyResponse(
            message="답변이 등록되었습니다.",
            log_id=log.log_id,
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("역무원 답변 저장 중 오류 발생")
        raise HTTPException(status_code=500, detail="reply_save_error")