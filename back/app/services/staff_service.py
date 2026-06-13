from sqlalchemy import func
from sqlalchemy.orm import Session

from app.model.db_model import CommunicationLog, CommunicationStatus


def get_waiting_logs(db: Session, skip: int, limit: int):
    total_count = (
        db.query(func.count(CommunicationLog.log_id))
        .filter(CommunicationLog.status == CommunicationStatus.WAITING)
        .scalar()
    ) or 0

    logs = (
        db.query(CommunicationLog)
        .filter(CommunicationLog.status == CommunicationStatus.WAITING)
        .order_by(CommunicationLog.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return total_count, logs


def get_log_for_reply(db: Session, log_id: int):
    return (
        db.query(CommunicationLog)
        .filter(CommunicationLog.log_id == log_id)
        .with_for_update()
        .first()
    )