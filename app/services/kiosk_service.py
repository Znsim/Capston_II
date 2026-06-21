from sqlalchemy.orm import Session

from app.ai.inference import predict_sign
from app.model.db_model import Conversation, ConversationStatus, DeviceInfo


def run_inference(model, keypoints) -> dict:
    """추론만 수행하며 좌표나 결과는 DB에 저장하지 않습니다."""
    return predict_sign(model, keypoints)


def create_conversation(
    db: Session, device_id: str, question_text: str
) -> Conversation | None:
    if db.get(DeviceInfo, device_id) is None:
        return None

    conversation = Conversation(
        device_id=device_id,
        question_text=question_text,
        status=ConversationStatus.WAITING,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(
    db: Session, conversation_id: int, device_id: str
) -> Conversation | None:
    return (
        db.query(Conversation)
        .filter(
            Conversation.conversation_id == conversation_id,
            Conversation.device_id == device_id,
        )
        .first()
    )
