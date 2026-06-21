"""검증된 모델 아티팩트를 운영 경로에 원자적으로 배치한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import joblib


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("deployment/models"))
    parser.add_argument("--target", type=Path, default=Path("app/ai/models"))
    parser.add_argument("--manifest", type=Path, default=Path("deployment/model_manifest.json"))
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    artifacts: dict[str, str] = manifest["artifacts"]
    for filename, expected_hash in artifacts.items():
        source = args.source / filename
        if not source.is_file():
            raise FileNotFoundError(f"model_artifact_missing: {source}")
        actual_hash = sha256(source)
        if actual_hash.lower() != expected_hash.lower():
            raise RuntimeError(f"model_hash_mismatch: {filename}: {actual_hash}")

    estimator = joblib.load(args.source / "gesture_model.pkl")
    encoder = joblib.load(args.source / "label_encoder.pkl")
    if int(getattr(estimator, "n_features_in_", -1)) != int(manifest["input_features"]):
        raise RuntimeError("model_feature_count_mismatch")
    if len(getattr(encoder, "classes_", [])) != int(manifest["class_count"]):
        raise RuntimeError("encoder_class_count_mismatch")
    if len(getattr(estimator, "classes_", [])) != len(encoder.classes_):
        raise RuntimeError("model_encoder_class_count_mismatch")

    for filename in artifacts:
        atomic_copy(args.source / filename, args.target / filename)

    print(
        f"Placed model {manifest['model_version']} in {args.target} "
        f"({manifest['input_features']} features, {manifest['class_count']} classes)."
    )


if __name__ == "__main__":
    main()
