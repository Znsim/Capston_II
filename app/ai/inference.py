from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

# 가이드 모델 스펙: MediaPipe 손 랜드마크 21개 x 3좌표(x, y, z) = 63 features
EXPECTED_FEATURES = 63

# 신뢰도가 이 값 미만이면 인식 실패로 처리한다.
DEFAULT_CONFIDENCE_THRESHOLD = 0.80


class InferenceError(RuntimeError):
    """추론 처리 중 발생하는 도메인 예외."""


@dataclass
class ModelBundle:
    """추론에 필요한 아티팩트 묶음.

    Attributes:
        estimator: 학습된 MLPClassifier 등 sklearn estimator.
        label_encoder: 인덱스 -> 한글 변환기 (필수 LabelEncoder).
    """

    estimator: Any
    label_encoder: Any

# =========================================================
# 모델 로딩
# =========================================================
def load_model(
    model_path: Optional[str] = None,
    encoder_path: Optional[str] = None,
) -> ModelBundle:
    """학습된 모델과 라벨 인코더를 디스크에서 메모리로 적재한다.

    서버 시작 시 1회만 호출한다. (요청마다 로드하면 느림)

    Args:
        model_path:   gesture_model.pkl 경로. 미지정 시 settings.MODEL_PATH 사용.
        encoder_path: label_encoder.pkl 경로. 미지정 시 settings.LABEL_ENCODER_PATH 사용.

    Returns:
        ModelBundle(estimator, label_encoder)

    Raises:
        FileNotFoundError: 모델 파일이 없을 때.
        InferenceError: 역직렬화 실패 시.
    """
    m_path = Path(model_path or settings.MODEL_PATH)
    if not m_path.exists():
        raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {m_path}")

    try:
        estimator = joblib.load(m_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("모델 역직렬화 실패: %s", m_path)
        raise InferenceError("model_load_failed") from exc

    # 예측 번호를 실제 자모로 변환하는 encoder는 모델의 필수 구성요소다.
    e_path_raw = encoder_path or getattr(settings, "LABEL_ENCODER_PATH", None)
    if not e_path_raw:
        raise InferenceError("label_encoder_path_missing")
    e_path = Path(e_path_raw)
    if not e_path.exists():
        raise FileNotFoundError(f"라벨 인코더 파일을 찾을 수 없습니다: {e_path}")
    try:
        label_encoder = joblib.load(e_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("라벨 인코더 역직렬화 실패: %s", e_path)
        raise InferenceError("label_encoder_load_failed") from exc

    model_classes = np.asarray(getattr(estimator, "classes_", []))
    encoder_classes = np.asarray(getattr(label_encoder, "classes_", []))
    if model_classes.size != encoder_classes.size:
        raise InferenceError("model_encoder_class_count_mismatch")

    logger.info(
        "AI 모델 적재 완료 | model=%s | encoder=%s | device=%s",
        m_path,
        e_path_raw,
        getattr(settings, "MODEL_DEVICE", "cpu"),
    )
    return ModelBundle(estimator=estimator, label_encoder=label_encoder)


# =========================================================
# 내부 유틸
# =========================================================
def _to_feature_array(keypoints: List[float]) -> np.ndarray:
    """keypoints 를 (1, 63) float32 배열로 변환하고 형태를 검증한다.

    가이드: 배열 길이가 63이 아니면 400 에러로 이어진다.
    """
    try:
        arr = np.asarray(keypoints, dtype=np.float32).reshape(1, -1)
    except (ValueError, TypeError) as exc:
        raise InferenceError("invalid_keypoints_format") from exc

    if arr.shape != (1, EXPECTED_FEATURES):
        raise InferenceError(
            f"invalid_keypoints_shape: expected (1, {EXPECTED_FEATURES}), "
            f"got {arr.shape}"
        )
    return arr


def predict_sign(
    model: ModelBundle,
    keypoints: List[float],
    confidence_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """keypoints 로 지문자 라벨을 추론한다.

    글자(word) 변환은 하지 않는다. label_id 만 반환하고,
    상위 서비스가 DB(ai_label_map)에서 글자를 조회한다. (단일 출처)

    Returns:
        {"label_id": int, "confidence": float, "recognized": bool}
    """
    if model is None or getattr(model, "estimator", None) is None:
        raise InferenceError("model_not_loaded")

    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else getattr(settings, "CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD)
    )

    features = _to_feature_array(keypoints)
    estimator = model.estimator

    try:
        pred = estimator.predict(features)
        label_id = int(np.asarray(pred).reshape(-1)[0])
        label = str(model.label_encoder.inverse_transform([label_id])[0])

        if hasattr(estimator, "predict_proba"):
            proba = np.asarray(estimator.predict_proba(features))
            confidence = float(proba.reshape(proba.shape[0], -1)[0].max())
        else:
            confidence = 1.0
    except Exception as exc:  # noqa: BLE001
        logger.exception("모델 추론 실행 실패")
        raise InferenceError("model_predict_failed") from exc

    recognized = label != "none" and confidence >= threshold

    logger.debug(
        "추론 완료 | label_id=%s | confidence=%.4f | recognized=%s",
        label_id,
        confidence,
        recognized,
    )

    return {
        "label_id": label_id,
        "label": label,
        "confidence": confidence,
        "recognized": recognized,
    }
