"""독립 사용자용 지문자 모델 실시간 평가 수집기.

각 자모를 화면에 표시하고 사용자가 Space를 누를 때마다 다음을 저장한다.
- 정답 자모와 모델 예측
- 신뢰도 및 0.80 통과 여부
- MediaPipe가 판단한 사용 손과 점수
- 모델 입력과 동일한 (21, 3) float32 원시 랜드마크

평가 데이터는 학습 데이터와 분리된 evaluation/ 아래에만 저장한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import joblib
import mediapipe as mp
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from utils import put_text_kr

warnings.filterwarnings(
    "ignore",
    message=r"SymbolDatabase\.GetPrototype\(\) is deprecated.*",
    category=UserWarning,
)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]
MODEL_DIR = PROJECT_DIR / "app" / "ai" / "models"
EVALUATION_DIR = BASE_DIR / "evaluation"
CONFIDENCE_THRESHOLD = 0.80

LABELS = [
    "ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅚ", "ㅛ", "ㅜ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
    "none",
]


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", value.strip())
    return cleaned.strip("_") or "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="지문자 모델 독립 사용자 실시간 평가")
    parser.add_argument("--evaluator", required=True, help="평가자 구분 이름")
    parser.add_argument("--condition", default="normal", help="normal/dim/near/far 등 촬영 조건")
    parser.add_argument("--samples-per-label", type=int, default=20, help="자모별 수집 개수")
    parser.add_argument("--camera", type=int, default=0, help="웹캠 장치 번호")
    parser.add_argument("--start-label", choices=LABELS, help="이 자모부터 평가 시작")
    parser.add_argument("--only-label", choices=LABELS, help="이 자모 하나만 평가")
    args = parser.parse_args()
    if args.samples_per_label < 1:
        parser.error("--samples-per-label은 1 이상이어야 합니다.")
    return args


def predict(model, encoder, landmarks: np.ndarray) -> tuple[str, float]:
    features = landmarks.reshape(1, 63)
    label_id = int(model.predict(features)[0])
    confidence = float(model.predict_proba(features)[0].max())
    label = str(encoder.inverse_transform([label_id])[0])
    return label, confidence


def save_reports(session_dir: Path, rows: list[dict[str, object]], encoder) -> None:
    if not rows:
        return

    result_path = session_dir / "results.csv"
    with result_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    targets = [str(row["target_label"]) for row in rows]
    predictions = [str(row["effective_label"]) for row in rows]
    class_names = [str(label) for label in encoder.classes_]
    report = classification_report(
        targets,
        predictions,
        labels=class_names,
        output_dict=True,
        zero_division=0,
    )
    report["captured_samples"] = len(rows)
    report["accuracy"] = accuracy_score(targets, predictions)
    report["threshold_coverage"] = sum(bool(row["accepted"]) for row in rows) / len(rows)

    handedness_map: dict[str, dict[str, object]] = {}
    for label in LABELS:
        hands = [
            str(row["handedness"])
            for row in rows
            if row["target_label"] == label and row["handedness"]
        ]
        if hands:
            counts = Counter(hands)
            majority, count = counts.most_common(1)[0]
            handedness_map[label] = {
                "majority": majority,
                "agreement": count / len(hands),
                "counts": dict(counts),
            }

    report["handedness_by_label"] = handedness_map
    with (session_dir / "metrics.json").open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    matrix = confusion_matrix(targets, predictions, labels=class_names)
    np.savetxt(session_dir / "confusion_matrix.csv", matrix, fmt="%d", delimiter=",")


def main() -> None:
    args = parse_args()
    model = joblib.load(MODEL_DIR / "gesture_model.pkl")
    encoder = joblib.load(MODEL_DIR / "label_encoder.pkl")

    if model.n_features_in_ != 63 or len(encoder.classes_) != 32:
        raise RuntimeError("incompatible_fingerspelling_model")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"{timestamp}_{safe_name(args.evaluator)}_{safe_name(args.condition)}"
    session_dir = EVALUATION_DIR / session_name

    mp_hands = mp.solutions.hands
    drawer = mp.solutions.drawing_utils
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        model_complexity=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        hands.close()
        raise RuntimeError("camera_open_failed")

    # Windows에서는 브라우저 등 다른 프로그램이 카메라를 점유해도
    # isOpened()가 True이고 read()만 계속 실패할 수 있다.
    first_frame = None
    for _ in range(40):
        ok, frame = camera.read()
        if ok and frame is not None:
            first_frame = frame
            break
        time.sleep(0.05)
    if first_frame is None:
        camera.release()
        hands.close()
        raise RuntimeError(
            "camera_frame_read_failed: 브라우저/화상회의 앱의 카메라 사용을 종료한 뒤 다시 실행하세요."
        )

    session_dir.mkdir(parents=True, exist_ok=False)

    rows: list[dict[str, object]] = []
    evaluation_labels = [args.only_label] if args.only_label else LABELS
    if args.start_label and args.start_label not in evaluation_labels:
        raise ValueError("start_label_not_in_evaluation_labels")
    label_index = evaluation_labels.index(args.start_label) if args.start_label else 0
    count_for_label = 0
    current_landmarks: np.ndarray | None = None
    current_prediction = "-"
    current_confidence = 0.0
    current_hand = ""
    current_hand_score = 0.0

    print("Space: 샘플 저장 | n: 다음 자모 | b: 이전 자모 | q: 종료")
    try:
        while 0 <= label_index < len(evaluation_labels):
            if first_frame is not None:
                frame = first_frame
                first_frame = None
                ok = True
            else:
                ok, frame = camera.read()
            if not ok:
                print("카메라 프레임을 읽지 못했습니다. 카메라를 사용하는 다른 앱을 확인하세요.")
                time.sleep(0.1)
                continue

            # 학습 데이터와 같은 좌우 반전 좌표계.
            frame = cv2.flip(frame, 1)
            result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            target = evaluation_labels[label_index]
            current_landmarks = None
            current_prediction = "-"
            current_confidence = 0.0
            current_hand = ""
            current_hand_score = 0.0

            if result.multi_hand_landmarks:
                hand_landmarks = result.multi_hand_landmarks[0]
                current_landmarks = np.asarray(
                    [[point.x, point.y, point.z] for point in hand_landmarks.landmark],
                    dtype=np.float32,
                )
                current_prediction, current_confidence = predict(
                    model, encoder, current_landmarks
                )
                drawer.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                if result.multi_handedness:
                    classification = result.multi_handedness[0].classification[0]
                    current_hand = classification.label
                    current_hand_score = float(classification.score)

            # 백엔드와 같은 정책: none 또는 0.80 미만은 자모 입력으로 인정하지 않는다.
            accepted = (
                current_prediction != "none"
                and current_confidence >= CONFIDENCE_THRESHOLD
            )
            effective_prediction = current_prediction if accepted else "none"
            frame = put_text_kr(
                frame,
                f"정답 동작: {target}  ({label_index + 1}/{len(evaluation_labels)})",
                (15, 10),
                font_size=38,
                color=(0, 255, 0),
            )
            frame = put_text_kr(
                frame,
                f"저장: {count_for_label}/{args.samples_per_label}",
                (15, 58),
                font_size=28,
                color=(255, 255, 255),
            )
            frame = put_text_kr(
                frame,
                f"예측: {current_prediction}  {current_confidence * 100:.1f}%  손: {current_hand or '-'}",
                (15, 96),
                font_size=28,
                color=(0, 255, 0) if accepted else (255, 180, 0),
            )
            guidance = (
                "none: 손을 보이되 어떤 자모도 아닌 중립 자세"
                if target == "none"
                else "동작을 조금씩 바꿔가며 Space로 저장"
            )
            frame = put_text_kr(frame, guidance, (15, 134), font_size=22, color=(220, 220, 220))
            frame = put_text_kr(
                frame,
                "Space 저장 | n 다음 | b 이전 | q 종료",
                (15, frame.shape[0] - 42),
                font_size=22,
                color=(220, 220, 220),
            )

            cv2.imshow("Fingerspelling Independent Evaluation", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("n"):
                label_index += 1
                count_for_label = 0
                continue
            if key == ord("b") and label_index > 0:
                label_index -= 1
                count_for_label = sum(
                    row["target_label"] == evaluation_labels[label_index] for row in rows
                )
                continue
            if key != 32 or current_landmarks is None:
                continue

            label_dir = session_dir / target
            label_dir.mkdir(exist_ok=True)
            sample_path = label_dir / f"sample_{count_for_label:04d}.npy"
            np.save(sample_path, current_landmarks)
            rows.append({
                "evaluator": args.evaluator,
                "condition": args.condition,
                "target_label": target,
                "sample_index": count_for_label,
                "predicted_label": current_prediction,
                "effective_label": effective_prediction,
                "confidence": round(current_confidence, 6),
                "accepted": accepted,
                "raw_correct": current_prediction == target,
                "correct": effective_prediction == target,
                "handedness": current_hand,
                "handedness_score": round(current_hand_score, 6),
                "file": str(sample_path.relative_to(session_dir)),
            })
            count_for_label += 1

            if count_for_label >= args.samples_per_label:
                label_index += 1
                count_for_label = 0
    finally:
        camera.release()
        hands.close()
        cv2.destroyAllWindows()
        save_reports(session_dir, rows, encoder)

    print(f"평가 샘플: {len(rows)}개")
    print(f"결과 저장: {session_dir}")
    if rows:
        print(
            "운영 기준 정확도: "
            f"{accuracy_score([r['target_label'] for r in rows], [r['effective_label'] for r in rows]):.2%}"
        )


if __name__ == "__main__":
    main()
