import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schema.schema_ import (
    ErrorResponse,
    InferenceResponse,
    PollAnswerResponse,
    SignRequest,
)
from app.services.kiosk_service import (
    get_latest_log_for_device,
    run_inference_and_save,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Kiosk"])


@router.post(
    "/inference",
    response_model=InferenceResponse,
    summary="수어 입력 추론 및 로그 저장",
    responses={
        400: {"model": ErrorResponse, "description": "잘못된 입력값"},
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
        503: {"model": ErrorResponse, "description": "AI 모델 미로드"},
    },
)
async def inference(
    request_data: SignRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> InferenceResponse:
    model = getattr(request.app.state, "model", None)
    if model is None:
        logger.error("app.state에서 AI 모델을 찾을 수 없습니다.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ai_model_not_loaded",
        )

    try:
        result = run_inference_and_save(
            model=model,
            keypoints=request_data.keypoints,
            device_id=request_data.device_id,
            db=db,
        )

        # none / 저신뢰도 → 200 OK, recognized_word="none", confidence=0.0
        # (프론트의 'confidence < 0.75 무시' 정책과 자연스럽게 맞물림)
        if result is None:
            return InferenceResponse(
                log_id=0,
                recognized_word="none",
                confidence=0.0,
            )

        new_log, confidence = result
        return InferenceResponse(
            log_id=new_log.log_id,
            recognized_word=new_log.recognized_word,
            confidence=confidence,
        )

    except HTTPException:
        raise

    except SQLAlchemyError:
        logger.exception("추론 결과 데이터베이스 저장 중 오류 발생")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="database_save_error",
        )

    except Exception:
        logger.exception("추론 처리 중 알 수 없는 오류 발생")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="inference_process_error",
        )


@router.get(
    "/poll/answer",
    response_model=PollAnswerResponse,
    summary="역무원 답변 폴링",
    responses={
        422: {"model": ErrorResponse, "description": "잘못된 device_id 형식"},
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
)
async def poll_answer(
    device_id: str = Query(
        ...,
        pattern=r"^[A-Z]+_\d+$",
        examples=["SEOUL_01"],
        description="키오스크 기기 ID",
    ),
    db: Session = Depends(get_db),
) -> PollAnswerResponse:
    try:
        log = get_latest_log_for_device(db, device_id)

        # 대화 기록이 없으면 WAITING으로 응답 (프론트 분기 단순화)
        if log is None:
            return PollAnswerResponse(status="WAITING", staff_reply=None)

        return PollAnswerResponse(
            status=log.status.value,
            staff_reply=log.staff_reply,
        )

    except HTTPException:
        raise

    except SQLAlchemyError:
        logger.exception("답변 폴링 DB 조회 중 오류 발생")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="database_query_error",
        )

    except Exception:
        logger.exception("답변 폴링 중 알 수 없는 오류 발생")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="poll_answer_error",
        )