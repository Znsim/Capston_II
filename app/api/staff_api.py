import logging
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_staff_session
from app.model.db_model import ConversationStatus
from app.schema.schema_ import (
    StaffReply,
    StaffReplyResponse,
    WaitingListResponse,
)
from app.services.staff_service import (
    complete_conversation,
    get_waiting_conversations,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/staff",
    tags=["Staff"],
    dependencies=[Depends(require_staff_session)],
)
KST = timezone(timedelta(hours=9))
UTC = timezone.utc


def to_kst(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(KST)


@router.get("/list", response_model=WaitingListResponse, summary="답변 대기 대화 조회")
async def waiting_list(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> WaitingListResponse:
    try:
        total, conversations = get_waiting_conversations(
            db, skip=(page - 1) * limit, limit=limit
        )
        return WaitingListResponse(
            total=total,
            page=page,
            limit=limit,
            total_pages=(total + limit - 1) // limit if total else 0,
            items=[
                {
                    "conversation_id": item.conversation_id,
                    "device_id": item.device_id,
                    "station_name": item.device.station_name,
                    "location": item.device.location,
                    "question_text": item.question_text,
                    "status": item.status.value,
                    "created_at": to_kst(item.created_at),
                }
                for item in conversations
            ],
        )
    except Exception:
        logger.exception("staff_waiting_list_failed")
        raise HTTPException(status_code=500, detail="waiting_list_error")


@router.post("/reply", response_model=StaffReplyResponse, summary="역무원 답변 등록")
async def reply(data: StaffReply, db: Session = Depends(get_db)) -> StaffReplyResponse:
    try:
        conversation, completed = complete_conversation(
            db, data.conversation_id, data.reply
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        if not completed and conversation.status == ConversationStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="reply_already_completed")
        if not completed and conversation.status == ConversationStatus.CANCELLED:
            raise HTTPException(status_code=400, detail="conversation_cancelled")
        if not completed:
            raise HTTPException(status_code=409, detail="conversation_not_waiting")

        logger.info(
            "staff_reply_completed | conversation_id=%s | device=%s",
            conversation.conversation_id,
            conversation.device_id,
        )
        return StaffReplyResponse(
            message="답변이 등록되었습니다.",
            conversation_id=conversation.conversation_id,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("staff_reply_failed | conversation_id=%s", data.conversation_id)
        raise HTTPException(status_code=500, detail="reply_save_error")
