from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schema.schema_ import ErrorResponse, HealthStatus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    summary="시스템 연결 상태 점검",
    response_model=HealthStatus,
    tags=["System"],
    responses={
        503: {"model": ErrorResponse, "description": "시스템 준비 안 됨"},
    },
)
async def health_check(
    request: Request,
    db: Session = Depends(get_db),
):
    db_status = "disconnected"
    ai_status = "not_loaded"

    try:
        db.execute(text("SELECT 1")).scalar()
        db_status = "connected"
    except SQLAlchemyError as e:
        logger.error("데이터베이스 상태 확인 실패: %s", str(e))
        db_status = "error"
    except Exception:
        logger.exception("데이터베이스 상태 확인 중 알 수 없는 오류 발생")
        db_status = "unknown_error"

    try:
        model = getattr(request.app.state, "model", None)
        if model is not None:
            ai_status = "loaded"
        else:
            logger.warning("app.state에서 AI 모델을 찾을 수 없습니다.")
    except Exception:
        logger.exception("AI 모델 상태 확인 중 오류 발생")
        ai_status = "error"

    all_ready = db_status == "connected" and ai_status == "loaded"

    kst = timezone(timedelta(hours=9))
    current_time = datetime.now(kst).isoformat()

    status_data = {
        "database": db_status,
        "ai_model": ai_status,
        "all_systems_ready": all_ready,
        "timestamp": current_time,
    }

    if not all_ready:
        logger.warning("시스템 상태 점검 실패: %s", status_data)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "system_not_ready",
                "details": status_data,
            },
        )

    return HealthStatus(**status_data)