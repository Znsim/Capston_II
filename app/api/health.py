from datetime import datetime, timezone
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
    summary="시스템 준비 상태 확인",
    response_model=HealthStatus,
    tags=["System"],
    responses={503: {"model": ErrorResponse, "description": "시스템 준비 안 됨"}},
)
async def health_check(request: Request, db: Session = Depends(get_db)):
    database_status = "disconnected"
    model_status = "not_loaded"

    try:
        database_status = "connected" if db.execute(text("SELECT 1")).scalar() == 1 else "error"
    except SQLAlchemyError:
        logger.exception("health_check_database_failed")
        database_status = "error"
    except Exception:
        logger.exception("health_check_database_unexpected_error")
        database_status = "error"

    model = getattr(request.app.state, "model", None)
    if (
        model is not None
        and getattr(model, "estimator", None) is not None
        and getattr(model, "label_encoder", None) is not None
    ):
        model_status = "loaded"
    elif model is not None:
        logger.error("health_check_model_bundle_invalid")
        model_status = "error"

    all_ready = database_status == "connected" and model_status == "loaded"
    status_data = {
        "database": database_status,
        "ai_model": model_status,
        "all_systems_ready": all_ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not all_ready:
        logger.warning(
            "health_check_not_ready | database=%s | ai_model=%s",
            database_status,
            model_status,
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "system_not_ready",
                "details": status_data,
            },
        )
    return HealthStatus(**status_data)
