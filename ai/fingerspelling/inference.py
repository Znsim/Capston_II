"""
지문자 실시간 인식 (PyTorch 모델)
====================================
실행: python inference.py

realtime_inference.py 의 PyTorch 대안.
정규화된 랜드마크로 PyTorch MLP 모델을 사용합니다.
한글 조합이 필요하다면 realtime_inference.py 를 사용하세요.

조작:
  q : 종료
  c : 예측 기록 초기화
"""

import sys
from pathlib import Path
from collections import deque, Counter

import cv2
import numpy as np
import torch
import mediapipe as mp
import joblib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ai.preprocess import extract_landmarks
from ai.model import MLPClassifier
from utils import put_text_kr

# ── 설정 ──────────────────────────────────────────────────────────────────
CONF_THRESHOLD = 0.80
SMOOTH_WINDOW  = 12
PANEL_WIDTH    = 280
# ───────────────────────────────────────────────────────────────────────────


def load_model(models_dir: Path):
    paths = {
        "config":  models_dir / "model_config.pkl",
        "label":   models_dir / "label2idx.pkl",
        "weights": models_dir / "fingerspelling_model.pt",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(f"모델 파일 없음: {missing}")
        print("먼저 train.py 를 실행하세요.")
        sys.exit(1)

    config    = joblib.load(str(paths["config"]))
    label2idx = joblib.load(str(paths["label"]))
    idx2label = {v: k for k, v in label2idx.items()}

    model = MLPClassifier(input_size=config["input_size"],
                          num_classes=config["num_classes"])
    model.load_state_dict(torch.load(str(paths["weights"]), map_location="cpu"))
    model.eval()
    return model, idx2label


def predict(model, arr: np.ndarray, idx2label: dict):
    tensor = torch.from_numpy(arr).unsqueeze(0)
    with torch.no_grad():
        probs = torch.softmax(model(tensor), dim=1)[0]
    conf, pred_idx = probs.max(0)
    k    = min(3, len(idx2label))
    top3 = [(idx2label[i.item()], v.item())
            for i, v in zip(*probs.topk(k))]
    return idx2label[pred_idx.item()], conf.item(), top3


def draw_panel(panel: np.ndarray, smooth: str, conf: float,
               top3: list, detected: bool) -> np.ndarray:
    panel[:] = (30, 30, 30)
    h = panel.shape[0]

    panel = put_text_kr(panel, smooth, (20, 20), font_size=110,
                         color=(0, 255, 80) if smooth != "-" else (100, 100, 100))

    conf_color = (0, 220, 0) if conf >= CONF_THRESHOLD else (60, 60, 200)
    panel = put_text_kr(panel, f"신뢰도  {conf:.0%}", (15, 145),
                         font_size=30, color=conf_color)

    cv2.line(panel, (10, 190), (PANEL_WIDTH - 10, 190), (80, 80, 80), 1)
    panel = put_text_kr(panel, "Top 3", (15, 200), font_size=26, color=(160, 160, 160))

    for i, (lbl, p) in enumerate(top3):
        c = (0, 255, 80) if i == 0 else (180, 180, 180)
        panel = put_text_kr(panel, f"{lbl}   {p:.0%}",
                             (15, 235 + i * 48), font_size=36, color=c)

    if not detected:
        panel = put_text_kr(panel, "손 미감지", (15, h - 80),
                             font_size=28, color=(60, 60, 220))

    panel = put_text_kr(panel, "q=종료  c=초기화", (10, h - 40),
                         font_size=24, color=(100, 100, 100))
    return panel


def main():
    model, idx2label = load_model(ROOT / "models")
    print(f"모델 로드 완료. 클래스: {list(idx2label.values())}")

    mp_hands = mp.solutions.hands
    mp_draw  = mp.solutions.drawing_utils
    hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1,
                           min_detection_confidence=0.7, min_tracking_confidence=0.5)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("카메라를 열 수 없습니다.")
        sys.exit(1)

    history: deque = deque(maxlen=SMOOTH_WINDOW)
    label, conf, top3 = "-", 0.0, []

    print("조작: [q]=종료  [c]=기록 초기화")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]

        result   = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        detected = result.multi_hand_landmarks is not None

        if detected:
            lm = result.multi_hand_landmarks[0]
            mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)
            arr           = extract_landmarks(lm)   # 정규화된 (63,)
            label, conf, top3 = predict(model, arr, idx2label)
            if conf >= CONF_THRESHOLD:
                history.append(label)

        smooth = Counter(history).most_common(1)[0][0] if history else "-"

        panel  = np.zeros((h, PANEL_WIDTH, 3), dtype=np.uint8)
        panel  = draw_panel(panel, smooth, conf, top3, detected)
        canvas = np.hstack([panel, frame])

        cv2.imshow("지문자 인식 (PyTorch)", canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("c"):
            history.clear()
            label, conf, top3 = "-", 0.0, []

    cap.release()
    cv2.destroyAllWindows()
    hands.close()


if __name__ == "__main__":
    main()
