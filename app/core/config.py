import json
import os
from typing import Any, Literal, Optional
from urllib.parse import quote_plus

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    청각 장애인 교통 수어 키오스크 프로젝트 환경 설정
    - 로컬 개발 / Docker 배포 / 실무 운영 대응
    """

    # =========================
    # 1. 기본 앱 정보
    # =========================
    APP_NAME: str = "Sign Language Traffic Kiosk"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    # Windows/개발 도구가 사용하는 전역 DEBUG 환경변수와 충돌하지 않도록
    # 프로젝트 전용 이름을 사용한다.
    APP_DEBUG: bool = False

    # =========================
    # 2. 서버 설정
    # =========================
    PORT: int = 8000
    BIND_HOST: str = "127.0.0.1"
    UVICORN_WORKERS: int = Field(default=1, ge=1, le=4)
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"
    ADMIN_PASSWORD: Optional[str] = None
    SESSION_SECRET: Optional[str] = None
    SESSION_TTL_SECONDS: int = Field(default=28800, ge=300, le=86400)
    MAX_REQUEST_BODY_BYTES: int = Field(default=1048576, ge=1024, le=10485760)

    # =========================
    # 3. 데이터베이스 설정
    # MySQL: DB_USER / DB_PASSWORD / DB_HOST / DB_NAME 모두 설정 시 MySQL 사용
    # 미설정 시 SQLite(kiosk.db) 자동 사용
    # =========================
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: Optional[str] = None
    SQLITE_PATH: str = "kiosk.db"

    # =========================
    # 4. CORS 설정
    # 팀원이 프론트 주소를 .env에 작성. 아래 두 형식 모두 허용됨:
    #   ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173   (콤마 구분)
    #   ALLOWED_ORIGINS=["http://localhost:3000"]                     (JSON 배열)
    #
    # NoDecode가 핵심: pydantic-settings는 list[str] 같은 복합 타입을
    # validator보다 먼저 json.loads로 디코딩하려 시도한다. 콤마 문자열은
    # 유효한 JSON이 아니라서 그 단계에서 SettingsError가 난다.
    # NoDecode로 자동 디코딩을 끄고 아래 validator에서 직접 파싱한다.
    # =========================
    ALLOWED_ORIGINS: Any = Field(
        default_factory=list,
        description="허용할 프론트엔드 Origin 목록 (콤마 구분 또는 JSON 배열)",
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, v: object) -> list[str]:
        # 환경변수 미설정/None -> 빈 목록
        if v is None:
            return []
        # 이미 리스트(코드에서 직접 주입한 경우 등)면 그대로 사용
        if isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            # JSON 배열 형식
            if v.startswith("["):
                return json.loads(v)
            # 콤마 구분 형식
            return [item.strip() for item in v.split(",") if item.strip()]
        # 그 외 타입은 pydantic 기본 검증에 맡김
        return v

    @model_validator(mode="after")
    def _validate_production_security(self):
        using_mysql = bool(self.DB_USER and self.DB_PASSWORD and self.DB_NAME)
        if not using_mysql and self.UVICORN_WORKERS != 1:
            raise ValueError("sqlite_requires_single_worker")
        if self.ENVIRONMENT == "production":
            if not self.ADMIN_PASSWORD or len(self.ADMIN_PASSWORD) < 12:
                raise ValueError("production_admin_password_required")
            if not self.SESSION_SECRET or len(self.SESSION_SECRET) < 32:
                raise ValueError("production_session_secret_required")
            if not self.ALLOWED_ORIGINS or "*" in self.ALLOWED_ORIGINS:
                raise ValueError("production_cors_origins_required")
            if any(not str(origin).startswith("https://") for origin in self.ALLOWED_ORIGINS):
                raise ValueError("production_cors_must_use_https")
        return self

    # =========================
    # 5. AI 모델 설정
    # MODEL_DEVICE는 GPU 없으면 cpu 유지
    # =========================
    MODEL_PATH: str = "app/ai/models/gesture_model.pkl"
    LABEL_ENCODER_PATH: str = "app/ai/models/label_encoder.pkl"
    MODEL_DEVICE: Literal["cpu", "cuda"] = "cpu"
    # 지문자 실시간 추론 데모와 동일한 기준
    CONFIDENCE_THRESHOLD: float = Field(default=0.80, description="추론 신뢰도 임계값")

    # =========================
    # 6. 로깅 설정
    # =========================
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # =========================
    # 7. DB URL 조합
    # =========================
    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        if self.DB_USER and self.DB_PASSWORD and self.DB_NAME:
            encoded_password = quote_plus(self.DB_PASSWORD)
            return (
                f"mysql+pymysql://{self.DB_USER}:{encoded_password}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        return f"sqlite:///{self.SQLITE_PATH}"

    # =========================
    # 8. Pydantic Settings 설정
    # =========================
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
