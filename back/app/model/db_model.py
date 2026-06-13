import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, JSON, func, Index
from sqlalchemy.orm import relationship

from app.core.database import Base

class CommunicationStatus(str, enum.Enum):
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"

class DeviceInfo(Base):
    __tablename__ = "device_info"

    device_id = Column(String(50), primary_key=True, index=True)
    station_name = Column(String(100), nullable=False)
    location = Column(String(100), nullable=True)

    # 역참조 추가: 해당 디바이스에서 발생한 로그들
    logs = relationship("CommunicationLog", back_populates="device")


class AILabelMap(Base):
    __tablename__ = "ai_label_map"

    label_id = Column(Integer, primary_key=True, index=True)
    word_name = Column(String(10), nullable=False)
    description = Column(String(255), nullable=True)

    # 역참조 추가: 특정 라벨에 해당하는 로그들
    logs = relationship("CommunicationLog", back_populates="label")


class CommunicationLog(Base):
    __tablename__ = "communication_log"

    log_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(
        String(50),
        ForeignKey("device_info.device_id"),
        nullable=False,
        index=True,  # ← 추가
    )
    label_id = Column(
        Integer,
        ForeignKey("ai_label_map.label_id"),
        nullable=False,
        index=True,  # ← 추가
    )

    recognized_word = Column(String(50), nullable=False)
    staff_reply = Column(Text, nullable=True)

    # native_enum=False는 MySQL에서 내부 Enum 대신 VARCHAR를 사용하게 하여 유연성을 높입니다.
    status = Column(
        Enum(CommunicationStatus, native_enum=False),
        default=CommunicationStatus.WAITING,
        nullable=False,
        index=True,  # ← 추가
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,  # ← 추가
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # ← 추가 (INSERT 시 NULL 방지)
        onupdate=func.now(),
    )

    # 관계 설정
    device = relationship("DeviceInfo", back_populates="logs")
    label = relationship("AILabelMap", back_populates="logs")
    training_data = relationship(
        "TrainingDataLog",
        back_populates="communication",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # 복합 인덱스: "이 디바이스의 WAITING 로그"처럼 자주 나오는 조합 쿼리용
    __table_args__ = (
        Index("ix_comm_log_device_status", "device_id", "status"),
    )


class TrainingDataLog(Base):
    __tablename__ = "training_data_log"

    data_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    log_id = Column(Integer, ForeignKey("communication_log.log_id"), nullable=False, unique=True)
    raw_json_data = Column(JSON, nullable=False)

    communication = relationship("CommunicationLog", back_populates="training_data")