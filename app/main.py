import re
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

from app.ai.inference import load_model
from app.api.router import api_router
from app.core.config import settings
from app.core.database import (
    check_db_health,
    close_db,
    seed_db,
    validate_ai_label_mapping,
    _is_sqlite,
)
from app.core.migrate import upgrade_database
from app.core.logger import get_logger, set_request_id, setup_logger
from app.core.security import (
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)

setup_logger(enable_request_id=True)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("서버 시작 중...")

    try:

        if _is_sqlite:
            upgrade_database()
            seed_db()
            logger.info("SQLite DB 마이그레이션 완료 (kiosk.db)")
        elif check_db_health():
            logger.info("DB 연결 성공")
        else:
            logger.warning("DB 연결 실패")

        # =========================
        # AI 모델 로드
        # =========================
        try:
            model = load_model()
            validate_ai_label_mapping(model.label_encoder.classes_)
            app.state.model = model
            logger.info("AI 모델 로드 완료")
        except Exception as exc:
            app.state.model = None
            logger.error(
                "ai_model_load_failed | exception_type=%s",
                type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

        logger.info("애플리케이션 시작 완료")
        yield

    finally:
        logger.info("서버 종료 중.")
        close_db()
        logger.info("애플리케이션 종료 완료")


app = FastAPI(
    title="Sign Language Traffic Kiosk API",
    description="청각 장애인을 위한 교통 안내 수어 키오스크 백엔드",
    version="1.0.0",
    lifespan=lifespan,
)

allowed_origins = settings.ALLOWED_ORIGINS
allow_all_origins = "*" in allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_BYTES)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    SecurityHeadersMiddleware,
    production=settings.ENVIRONMENT == "production",
)
if settings.ENVIRONMENT == "production":
    app.add_middleware(HTTPSRedirectMiddleware)

_VALID_RID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID")
    if incoming and not _VALID_RID.match(incoming):
        incoming = None
    rid = set_request_id(incoming)

    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "validation_error",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    details = exc.detail if isinstance(exc.detail, dict) else None
    message = exc.detail if isinstance(exc.detail, str) else "http_error"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": message,
            "details": details,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_server_error | exception_type=%s",
        type(exc).__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "internal_server_error",
            "details": None,
        },
    )


app.include_router(api_router, prefix="/api")

frontend_dir = Path(os.getenv("SIGNKIOSK_ASSET_DIR", "build")).resolve()
frontend_enabled = settings.SERVE_FRONTEND and (frontend_dir / "index.html").is_file()
if frontend_enabled and (frontend_dir / "static").is_dir():
    app.mount("/static", StaticFiles(directory=frontend_dir / "static"), name="frontend-static")


@app.get("/")
async def root():
    if frontend_enabled:
        return FileResponse(frontend_dir / "index.html")
    return {
        "status": "success",
        "message": "service_running",
    }


@app.get("/info")
async def info():
    return {
        "status": "success",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "model_loaded": getattr(app.state, "model", None) is not None,
    }


@app.get("/{frontend_path:path}", include_in_schema=False)
async def frontend_fallback(frontend_path: str):
    if not frontend_enabled:
        raise HTTPException(status_code=404, detail="not_found")
    requested = (frontend_dir / frontend_path).resolve()
    try:
        requested.relative_to(frontend_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="not_found")
    if requested.is_file():
        return FileResponse(requested)
    return FileResponse(frontend_dir / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        port=settings.PORT,
        reload=True,
    )
