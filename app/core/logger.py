import contextvars
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional
from uuid import uuid4

# ========================
# 환경 설정
# ========================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "logs")
ENABLE_REQUEST_ID = os.getenv("ENABLE_REQUEST_ID", "false").lower() == "true"

if not LOG_DIR:
    LOG_DIR = "logs"

if not os.path.isabs(LOG_DIR):
    LOG_DIR = os.path.abspath(LOG_DIR)

# request id 기본값 (None 권장)
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id",
    default=None
)

# logger 초기화 플래그
_logger_initialized = False


# ========================
# 민감 정보 필터
# ========================

class SensitiveFilter(logging.Filter):
    """로그에서 민감 정보 마스킹"""

    COMPILED_PATTERNS = [
        re.compile(r"(password\s*=\s*)(\S+)", re.IGNORECASE),
        re.compile(r"(token\s*=\s*)(\S+)", re.IGNORECASE),
        re.compile(r"(api_key\s*=\s*)(\S+)", re.IGNORECASE),
        re.compile(r"(secret\s*=\s*)(\S+)", re.IGNORECASE),
        re.compile(r"(bearer\s+)(\S+)", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:

        try:
            msg = str(record.msg)

            for pattern in self.COMPILED_PATTERNS:
                msg = pattern.sub(r"\1***", msg)

            record.msg = msg

            if record.args:
                record.args = self._mask_args(record.args)

        except Exception as e:
            sys.stderr.write(f"SensitiveFilter error: {e}\n")

        return True

    def _mask_args(self, args):

        if isinstance(args, dict):
            return {k: self._mask_value(v) for k, v in args.items()}

        if isinstance(args, (list, tuple)):
            return type(args)(self._mask_value(a) for a in args)

        return args

    def _mask_value(self, value):

        try:
            value_str = str(value)

            for pattern in self.COMPILED_PATTERNS:
                if pattern.search(value_str):
                    return "***"

        except (TypeError, ValueError):
            pass

        return value


# ========================
# Context Formatter
# ========================

class ContextualFormatter(logging.Formatter):
    """Request ID 등 컨텍스트 정보 추가"""

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get() or "no-id"
        return super().format(record)


# ========================
# 로그 포맷
# ========================

def get_log_format(
    include_function: bool = True,
    include_request_id: bool = False
) -> str:
    """
    로그 포맷 문자열 생성
    
    Args:
        include_function: 함수명과 라인번호 포함 여부
        include_request_id: 요청 ID 포함 여부
    
    Returns:
        로그 포맷 문자열
    """
    parts = []

    if include_request_id:
        parts.append("[%(request_id)s]")

    parts.extend([
        "%(asctime)s.%(msecs)03d",
        "%(levelname)-8s",
        "%(name)s"
    ])

    if include_function:
        parts.append("%(funcName)s:%(lineno)d")

    parts.append("%(message)s")

    return " | ".join(parts)


# ========================
# 검증 함수
# ========================

def _validate_log_level(level: str) -> str:
    """로그 레벨 검증"""
    level = level.upper()

    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    if level not in valid_levels:
        sys.stderr.write(f"Invalid log level '{level}', using INFO\n")
        return "INFO"

    return level


def _ensure_log_dir() -> bool:
    """로그 디렉토리 생성 및 검증"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        return True

    except OSError as e:
        sys.stderr.write(f"Failed to create log directory '{LOG_DIR}': {e}\n")
        return False


# ========================
# Logger 설정
# ========================

def setup_logger(
    level: Optional[str] = None,
    enable_request_id: Optional[bool] = None
) -> None:
    """
    프로젝트 전체 Logger 초기화
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_request_id: 요청 ID 추적 활성화 여부
    
    Example:
        >>> setup_logger(level="DEBUG", enable_request_id=True)
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    global _logger_initialized

    if _logger_initialized:
        logging.getLogger().debug("Logger already initialized")
        return

    if not _ensure_log_dir():
        return

    log_level = _validate_log_level(level or LOG_LEVEL)

    if enable_request_id is None:
        enable_request_id = ENABLE_REQUEST_ID

    root_logger = logging.getLogger()

    # 기존 handler 제거
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    root_logger.setLevel(log_level)

    log_format = get_log_format(
        include_function=True,
        include_request_id=enable_request_id
    )

    formatter_class = (
        ContextualFormatter if enable_request_id else logging.Formatter
    )

    formatter = formatter_class(
        log_format,
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ========================
    # 콘솔 로그
    # ========================

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SensitiveFilter())

    root_logger.addHandler(console_handler)

    # ========================
    # 일반 로그 파일
    # ========================

    try:
        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "app.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )

        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SensitiveFilter())

        root_logger.addHandler(file_handler)

    except OSError as e:
        sys.stderr.write(f"Failed to create file handler: {e}\n")

    # ========================
    # 에러 로그 파일
    # ========================

    try:
        error_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "error.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )

        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        error_handler.addFilter(SensitiveFilter())

        root_logger.addHandler(error_handler)

    except OSError as e:
        sys.stderr.write(f"Failed to create error handler: {e}\n")

    # ========================
    # 외부 라이브러리 로그 조정
    # ========================

    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.getLogger("fastapi").setLevel(logging.INFO)

    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _logger_initialized = True

    root_logger.info(
        "✅ Logger initialized | Level=%s | RequestID=%s | Directory=%s",
        log_level,
        enable_request_id,
        LOG_DIR
    )


# ========================
# Logger 반환
# ========================

def get_logger(name: str) -> logging.Logger:
    """
    모듈별 Logger 반환
    
    Args:
        name: 로거 이름 (일반적으로 __name__)
    
    Returns:
        logging.Logger 인스턴스
    
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Message")
    """
    return logging.getLogger(name)


# ========================
# Request ID 관리
# ========================

def set_request_id(request_id: Optional[str] = None) -> str:
    """
    요청 ID 설정
    
    Args:
        request_id: 요청 ID (없으면 UUID 생성)
    
    Returns:
        설정된 요청 ID
    
    Example:
        >>> rid = set_request_id()
        >>> logger.info("Processing")  # [uuid] 형태로 로그됨
    """
    if request_id is None:
        request_id = str(uuid4())

    request_id_var.set(request_id)

    return request_id


def get_request_id() -> Optional[str]:
    """
    현재 요청 ID 반환
    
    Returns:
        현재 context의 요청 ID (없으면 None)
    
    Example:
        >>> rid = get_request_id()
    """
    return request_id_var.get()