"""운영 Uvicorn 진입점. ENV_FILE은 import 전에 설정해야 한다."""

import uvicorn

from app.core.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.BIND_HOST,
        port=settings.PORT,
        workers=settings.UVICORN_WORKERS,
        proxy_headers=True,
        forwarded_allow_ips=settings.FORWARDED_ALLOW_IPS,
        access_log=False,
    )
