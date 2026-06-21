import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schema.schema_ import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationResponse,
    ErrorResponse,
    InferenceResponse,
    SignRequest,
)
from app.services.kiosk_service import (
    create_conversation,
    get_conversation,
    run_inference,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Kiosk"])


@router.post(
    "/inference",
    response_model=InferenceResponse,
    summary="수어 자모 추론",
    responses={503: {"model": ErrorResponse, "description": "AI 모델 미로드"}},
)
async def inference(request_data: SignRequest, request: Request) -> InferenceResponse:
    model = getattr(request.app.state, "model", None)
    if model is None:
        logger.warning("inference_rejected_model_not_loaded")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ai_model_not_loaded",
        )

    try:
        result = run_inference(model, request_data.keypoints)
        if not result["recognized"]:
            return InferenceResponse(recognized_word="none", confidence=0.0)
        return InferenceResponse(
            recognized_word=result["label"],
            confidence=result["confidence"],
        )
    except Exception:
        logger.exception("inference_failed")
        raise HTTPException(status_code=500, detail="inference_process_error")


@router.post(
    "/conversations",
    response_model=ConversationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="완성 문장 전송",
)
async def submit_conversation(
    data: ConversationCreateRequest,
    db: Session = Depends(get_db),
) -> ConversationCreateResponse:
    try:
        conversation = create_conversation(db, data.device_id, data.question_text)
        if conversation is None:
            raise HTTPException(status_code=404, detail="device_not_found")
        logger.info(
            "conversation_created | conversation_id=%s | device=%s",
            conversation.conversation_id,
            conversation.device_id,
        )
        return ConversationCreateResponse(
            conversation_id=conversation.conversation_id,
            status=conversation.status.value,
        )
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("conversation_create_database_failed | device=%s", data.device_id)
        raise HTTPException(status_code=500, detail="conversation_save_error")


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="대화 답변 조회",
)
async def read_conversation(
    conversation_id: int,
    device_id: str = Query(..., pattern=r"^[A-Z]+_\d+$"),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    try:
        conversation = get_conversation(db, conversation_id, device_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        return ConversationResponse(
            conversation_id=conversation.conversation_id,
            status=conversation.status.value,
            staff_reply=conversation.staff_reply,
        )
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("conversation_read_database_failed | conversation_id=%s", conversation_id)
        raise HTTPException(status_code=500, detail="conversation_query_error")
