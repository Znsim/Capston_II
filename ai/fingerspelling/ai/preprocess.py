import numpy as np


def extract_landmarks_raw(hand_landmarks) -> np.ndarray:
    """MediaPipe hand_landmarks → raw (21, 3) float32 배열.

    train_classifier.py / realtime_inference.py (sklearn) 에서 사용.
    """
    return np.array(
        [[lm.x, lm.y, lm.z] for lm in hand_landmarks.landmark],
        dtype=np.float32,
    )


def normalize_landmarks(arr: np.ndarray) -> np.ndarray:
    """(21, 3) raw 배열 → 손목 기준 정규화된 (63,) 배열.

    train.py / inference.py (PyTorch) 에서 사용.
    손목(0번) 기준 상대 좌표 변환 후 최대 거리로 스케일 정규화.
    """
    pts = arr.copy()
    pts -= pts[0]
    scale = np.max(np.linalg.norm(pts, axis=1)) + 1e-8
    pts /= scale
    return pts.flatten()


def extract_landmarks(hand_landmarks) -> np.ndarray:
    """MediaPipe hand_landmarks → 정규화된 (63,) float32 배열 (PyTorch 모델용)."""
    return normalize_landmarks(extract_landmarks_raw(hand_landmarks))


def augment(arr: np.ndarray) -> np.ndarray:
    """정규화된 (63,) 배열에 가벼운 증강 적용 (PyTorch 학습 전용)."""
    pts = arr.reshape(21, 3).copy()

    # 미세 노이즈
    pts += np.random.normal(0, 0.005, pts.shape).astype(np.float32)

    # 스케일 변화
    pts *= 1.0 + np.random.uniform(-0.05, 0.05)

    # 2D 회전
    angle = np.random.uniform(-10, 10) * np.pi / 180
    c, s = np.cos(angle), np.sin(angle)
    xy = pts[:, :2].copy()
    pts[:, 0] = c * xy[:, 0] - s * xy[:, 1]
    pts[:, 1] = s * xy[:, 0] + c * xy[:, 1]

    return pts.flatten().astype(np.float32)
