from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.kiosk_api import router as kiosk_router
from app.api.staff_api import router as staff_router
from app.api.auth_api import router as auth_router
from app.api.device_api import router as device_router

api_router = APIRouter()

# 시스템 상태 점검 API
api_router.include_router(health_router)

# 키오스크 사용자용 API
api_router.include_router(kiosk_router)

api_router.include_router(auth_router)
api_router.include_router(device_router)

# 역무원용 API
api_router.include_router(staff_router)
