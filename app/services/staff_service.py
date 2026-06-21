from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.model.db_model import Conversation, ConversationStatus


def get_waiting_conversations(db: Session, skip: int, limit: int):
    total_count = (
        db.query(func.count(Conversation.conversation_id))
        .filter(Conversation.status == ConversationStatus.WAITING)
        .scalar()
    ) or 0

    conversations = (
        db.query(Conversation)
        .options(joinedload(Conversation.device))
        .filter(Conversation.status == ConversationStatus.WAITING)
        .order_by(Conversation.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total_count, conversations


def complete_conversation(
    db: Session, conversation_id: int, reply: str
) -> tuple[Conversation | None, bool]:
    updated = (
        db.query(Conversation)
        .filter(
            Conversation.conversation_id == conversation_id,
            Conversation.status == ConversationStatus.WAITING,
        )
        .update(
            {
                Conversation.staff_reply: reply,
                Conversation.status: ConversationStatus.COMPLETED,
            },
            synchronize_session=False,
        )
    )
    if updated == 1:
        db.commit()
        return db.get(Conversation, conversation_id), True

    db.rollback()
    return db.get(Conversation, conversation_id), False
