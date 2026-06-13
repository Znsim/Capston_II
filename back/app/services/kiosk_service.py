from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.ai.inference import predict_sign
from app.model.db_model import (
    AILabelMap,
    CommunicationLog,
    CommunicationStatus,
    TrainingDataLog,
)


def _resolve_word(label_id: int, db: Session) -> str | None:
    row = db.query(AILabelMap).filter(AILabelMap.label_id == label_id).first()
    return row.word_name if row else None


def run_inference_and_save(
    model, keypoints, device_id: str, db: Session
) -> tuple[CommunicationLog, float] | None:
    result = predict_sign(model, keypoints)

    # none / 저신뢰도 → 정상 흐름. 로그 남기지 않고 재시도 신호(None) 반환
    if not result["recognized"]:
        return None

    label_id = result["label_id"]
    word = _resolve_word(label_id, db)
    if not word:
        # 인식은 됐는데 매핑이 없다 = 진짜 설정 오류
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="label_not_mapped",
        )

    new_log = CommunicationLog(
        device_id=device_id,
        label_id=label_id,
        recognized_word=word,
        status=CommunicationStatus.WAITING,
    )
    db.add(new_log)
    db.flush()

    db.add(TrainingDataLog(log_id=new_log.log_id, raw_json_data=keypoints))

    db.commit()
    db.refresh(new_log)
    return new_log, result["confidence"]


def get_latest_log_for_device(
    db: Session, device_id: str
) -> CommunicationLog | None:
    """특정 디바이스의 가장 최근 대화 로그 1건 조회 (폴링용)."""
    return (
        db.query(CommunicationLog)
        .filter(CommunicationLog.device_id == device_id)
        .order_by(CommunicationLog.created_at.desc())
        .first()
    )