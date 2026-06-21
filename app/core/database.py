import logging
from typing import Generator

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

logger = logging.getLogger(__name__)

DATABASE_URL = settings.DATABASE_URL
_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite는 pool_size/max_overflow 미지원
_engine_kwargs: dict = {"pool_pre_ping": True}
if not _is_sqlite:
    _engine_kwargs.update({"pool_size": 10, "max_overflow": 20, "pool_recycle": 3600})

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# SQLite 운영 정책: 외래키, WAL, 잠금 대기 시간을 연결마다 적용한다.
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

# MySQL 전용: 세션 타임존 UTC 고정
else:
    @event.listens_for(engine, "connect")
    def set_mysql_timezone(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("SET time_zone = '+00:00'")
            cursor.close()
        except Exception:
            logger.exception("database_timezone_setup_failed")


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성 주입용 DB 세션 생성기"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()  # 작업 중 오류 발생 시 세션 보호를 위해 롤백
        raise
    finally:
        db.close()


def seed_db():
    """초기 기초 데이터 삽입 (이미 있으면 건너뜀)"""
    from app.model.db_model import AILabelMap, DeviceInfo

    # label_encoder.classes_ 순서와 동일하게 맞춘 자모 매핑
    LABEL_MAP = [
        (0, "none"), (1, "ㄱ"), (2, "ㄴ"), (3, "ㄷ"), (4, "ㄹ"),
        (5, "ㅁ"), (6, "ㅂ"), (7, "ㅅ"), (8, "ㅇ"), (9, "ㅈ"),
        (10, "ㅊ"), (11, "ㅋ"), (12, "ㅌ"), (13, "ㅍ"), (14, "ㅎ"),
        (15, "ㅏ"), (16, "ㅐ"), (17, "ㅑ"), (18, "ㅒ"), (19, "ㅓ"),
        (20, "ㅔ"), (21, "ㅕ"), (22, "ㅖ"), (23, "ㅗ"), (24, "ㅚ"),
        (25, "ㅛ"), (26, "ㅜ"), (27, "ㅟ"), (28, "ㅠ"), (29, "ㅡ"),
        (30, "ㅢ"), (31, "ㅣ"),
    ]

    db = SessionLocal()
    try:
        if db.query(AILabelMap).count() == 0:
            db.bulk_save_objects([
                AILabelMap(label_id=lid, word_name=word)
                for lid, word in LABEL_MAP
            ])
            logger.info("ai_label_map 기초 데이터 삽입 완료 (%d개)", len(LABEL_MAP))

        if db.query(DeviceInfo).filter_by(device_id="SEOUL_01").first() is None:
            db.add(DeviceInfo(device_id="SEOUL_01", station_name="서울역", location="1번 창구"))
            logger.info("device_info SEOUL_01 삽입 완료")

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("database_seed_failed")
    finally:
        db.close()


def validate_ai_label_mapping(encoder_classes) -> None:
    """서버 시작 시 label_encoder와 DB 라벨 순서가 정확히 같은지 검증한다."""
    from app.model.db_model import AILabelMap

    expected = [(index, str(label)) for index, label in enumerate(encoder_classes)]
    db = SessionLocal()
    try:
        rows = db.query(AILabelMap).order_by(AILabelMap.label_id.asc()).all()
        actual = [(row.label_id, row.word_name) for row in rows]
        if actual != expected:
            raise RuntimeError("ai_label_mapping_mismatch")
    finally:
        db.close()


def check_db_health() -> bool:
    """DB 연결 상태 확인 유틸리티"""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            return result == 1
    except Exception:
        logger.exception("database_health_check_failed")
        return False


def close_db():
    """앱 종료 시 커넥션 풀 정리"""
    try:
        engine.dispose()
        logger.info("데이터베이스 커넥션 풀 정리 완료")
    except Exception:
        logger.exception("database_engine_close_failed")
