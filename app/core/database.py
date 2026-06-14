import logging
from typing import Generator

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

logger = logging.getLogger(__name__)

# MySQL 연결 URL 예시: mysql+pymysql://user:password@localhost:3306/dbname
DATABASE_URL = settings.DATABASE_URL

# 엔진 설정
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # 연결 유효성 사전 체크
    pool_size=10,         # 기본 커넥션 수
    max_overflow=20,      # 초과 허용 커넥션 수
    pool_recycle=3600,    # 1시간마다 커넥션 재연결
)

# MySQL 세션 타임존을 UTC로 고정
# 저장은 UTC 기준으로 하고, 화면/API 응답에서 KST로 변환하여 표시하는 방식
@event.listens_for(engine, "connect")
def set_mysql_timezone(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET time_zone = '+00:00'")
        cursor.close()
    except Exception as e:
        logger.error(f"MySQL 세션 타임존(UTC) 설정 실패: {str(e)}")


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


def init_db():
    """테이블 초기 생성 (순환 참조 방지를 위해 함수 내부 import)"""
    try:
        import app.model.db_model  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("데이터베이스 테이블 생성 완료")
    except Exception as e:
        logger.error(f"데이터베이스 테이블 생성 중 오류 발생: {str(e)}", exc_info=True)
        raise


def check_db_health() -> bool:
    """DB 연결 상태 확인 유틸리티"""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            return result == 1
    except Exception as e:
        logger.error(f"데이터베이스 연결 상태 확인 실패: {str(e)}", exc_info=True)
        return False


def close_db():
    """앱 종료 시 커넥션 풀 정리"""
    try:
        engine.dispose()
        logger.info("데이터베이스 커넥션 풀 정리 완료")
    except Exception as e:
        logger.error(f"데이터베이스 엔진 종료 중 오류 발생: {str(e)}", exc_info=True)