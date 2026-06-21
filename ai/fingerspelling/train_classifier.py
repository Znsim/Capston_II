"""지문자 MLP 모델을 시간 순서 holdout으로 학습하고 평가한다.

각 라벨/수집 묶음에서 파일 번호가 앞선 80%는 학습, 마지막 20%는
평가에 사용한다. 기존 운영 모델은 덮어쓰지 않고 models/candidate에
후보 모델과 평가 결과를 저장한다.

실행:
  python ai/fingerspelling/train_classifier.py
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dataset"
OUTPUT_DIR = BASE_DIR / "models" / "candidate"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CONSONANTS = [
    "ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ", "none"
]
VOWELS = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅚ", "ㅛ", "ㅜ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"
]
LABELS = CONSONANTS + VOWELS
TEST_RATIO = 0.2


def _sequence_key(path: Path) -> tuple[str, int, str]:
    """파일명의 마지막 숫자를 촬영 순서로 사용한다."""
    prefix, separator, suffix = path.stem.rpartition("_")
    if separator and suffix.isdigit():
        return prefix, int(suffix), path.name
    return path.stem, 0, path.name


def split_label_files(label: str) -> tuple[list[Path], list[Path]]:
    """한 라벨의 각 수집 묶음에서 앞 80%/마지막 20%를 분리한다."""
    source = DATA_DIR / label / "landmarks_npy"
    groups: dict[str, list[Path]] = defaultdict(list)

    for path in source.glob("*.npy"):
        group, _, _ = _sequence_key(path)
        groups[group].append(path)

    train_files: list[Path] = []
    test_files: list[Path] = []
    for paths in groups.values():
        ordered = sorted(paths, key=_sequence_key)
        test_count = max(1, math.ceil(len(ordered) * TEST_RATIO))
        if test_count >= len(ordered):
            raise ValueError(f"not_enough_samples: label={label}, count={len(ordered)}")
        train_files.extend(ordered[:-test_count])
        test_files.extend(ordered[-test_count:])

    return train_files, test_files


def load_samples(paths: list[Path], label: str) -> tuple[list[np.ndarray], list[str]]:
    features: list[np.ndarray] = []
    labels: list[str] = []
    for path in paths:
        landmarks = np.load(path, allow_pickle=False)
        if landmarks.shape != (21, 3):
            raise ValueError(f"invalid_shape: path={path}, shape={landmarks.shape}")
        features.append(landmarks.astype(np.float32, copy=False).reshape(63))
        labels.append(label)
    return features, labels


def save_split_manifest(rows: list[dict[str, object]]) -> None:
    with (OUTPUT_DIR / "split_summary.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["label", "train_count", "test_count"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    x_train: list[np.ndarray] = []
    y_train: list[str] = []
    x_test: list[np.ndarray] = []
    y_test: list[str] = []
    split_rows: list[dict[str, object]] = []

    for label in LABELS:
        train_files, test_files = split_label_files(label)
        label_x_train, label_y_train = load_samples(train_files, label)
        label_x_test, label_y_test = load_samples(test_files, label)
        x_train.extend(label_x_train)
        y_train.extend(label_y_train)
        x_test.extend(label_x_test)
        y_test.extend(label_y_test)
        split_rows.append({
            "label": label,
            "train_count": len(train_files),
            "test_count": len(test_files),
        })

    save_split_manifest(split_rows)
    print(f"학습 샘플: {len(x_train):,} / 평가 샘플: {len(x_test):,}")

    encoder = LabelEncoder()
    encoder.fit(LABELS)
    y_train_encoded = encoder.transform(y_train)
    y_test_encoded = encoder.transform(y_test)

    model = MLPClassifier(
        hidden_layer_sizes=(256, 128, 64),
        activation="relu",
        max_iter=500,
        random_state=42,
        verbose=False,
    )
    model.fit(np.asarray(x_train), y_train_encoded)

    predictions = model.predict(np.asarray(x_test))
    class_ids = np.arange(len(encoder.classes_))
    report = classification_report(
        y_test_encoded,
        predictions,
        labels=class_ids,
        target_names=encoder.classes_,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(y_test_encoded, predictions, labels=class_ids)
    accuracy = accuracy_score(y_test_encoded, predictions)

    joblib.dump(model, OUTPUT_DIR / "gesture_model.pkl")
    joblib.dump(encoder, OUTPUT_DIR / "label_encoder.pkl")
    with (OUTPUT_DIR / "metrics.json").open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    np.savetxt(OUTPUT_DIR / "confusion_matrix.csv", matrix, fmt="%d", delimiter=",")

    print(f"평가 정확도: {accuracy:.4%}")
    print(f"후보 모델 및 평가 결과 저장: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
