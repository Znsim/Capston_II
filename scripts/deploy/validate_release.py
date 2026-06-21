"""운영 환경 파일의 자리표시자와 필수값을 배포 전에 차단한다."""

import re

from dotenv import dotenv_values

from app.core.config import settings


def main() -> None:
    if settings.ENVIRONMENT != "production":
        raise RuntimeError("release_environment_must_be_production")

    environment = dotenv_values(settings.model_config["env_file"])
    required = ["ADMIN_PASSWORD", "SESSION_SECRET", "REACT_APP_KIOSK_DEVICE_ID"]
    for name in required:
        value = str(environment.get(name) or "")
        if not value or "replace-with" in value.lower():
            raise RuntimeError(f"production_value_not_configured: {name}")

    device_id = str(environment["REACT_APP_KIOSK_DEVICE_ID"])
    if not re.fullmatch(r"[A-Z]+_\d+", device_id):
        raise RuntimeError("invalid_production_device_id")
    if any("example.com" in str(origin) for origin in settings.ALLOWED_ORIGINS):
        raise RuntimeError("production_origin_still_uses_example_domain")

    print(
        f"Release environment valid: origins={settings.ALLOWED_ORIGINS}, "
        f"device={device_id}, database={'mysql' if settings.DB_NAME else 'sqlite'}"
    )


if __name__ == "__main__":
    main()
