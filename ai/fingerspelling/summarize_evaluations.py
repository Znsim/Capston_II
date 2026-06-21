"""여러 실시간 평가 세션을 조건별로 합산해 Markdown/JSON 보고서를 만든다."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]
EVALUATION_DIR = BASE_DIR / "evaluation"
MODEL_PATH = PROJECT_DIR / "app" / "ai" / "models" / "gesture_model.pkl"
DEFAULT_OUTPUT = PROJECT_DIR / "docs" / "fingerspelling_model_evaluation.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="지문자 모델 평가 세션 통합 보고서")
    parser.add_argument("--sessions", nargs="+", required=True, help="evaluation 아래 세션 폴더명")
    parser.add_argument("--threshold", type=float, default=0.80)
    parser.add_argument("--model-version", default="fingerspelling-mlp-2026.06.19-v2")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--independent-evaluator",
        choices=["yes", "no", "unknown"],
        default="unknown",
        help="평가자가 학습 데이터 수집에 참여하지 않았는지 여부",
    )
    parser.add_argument(
        "--condition-alias",
        action="append",
        default=[],
        metavar="SESSION=CONDITION",
        help="부분 재평가 세션을 기존 조건에 합칠 때 사용",
    )
    return parser.parse_args()


def load_rows(
    session_names: list[str], threshold: float, aliases: dict[str, str]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for session_name in session_names:
        result_path = EVALUATION_DIR / session_name / "results.csv"
        if not result_path.exists():
            raise FileNotFoundError(result_path)
        with result_path.open(encoding="utf-8-sig") as file:
            for source in csv.DictReader(file):
                confidence = float(source["confidence"])
                raw_prediction = source["predicted_label"]
                recognized = raw_prediction != "none" and confidence >= threshold
                effective = raw_prediction if recognized else "none"
                rows.append({
                    "session": session_name,
                    "evaluator": source["evaluator"],
                    "condition": aliases.get(session_name, source["condition"]),
                    "target": source["target_label"],
                    "raw_prediction": raw_prediction,
                    "effective_prediction": effective,
                    "confidence": confidence,
                    "recognized": recognized,
                    "raw_correct": raw_prediction == source["target_label"],
                    "correct": effective == source["target_label"],
                    "handedness": source.get("handedness", ""),
                })
    return rows


def metrics_for(rows: list[dict[str, object]]) -> dict[str, object]:
    total = len(rows)
    recognized_rows = [row for row in rows if row["recognized"]]
    # 일반 자모는 원시 분류 정확도를, none은 임계값 적용 후 안전한 거부 여부를 본다.
    evaluated_correct = sum(
        bool(row["correct"]) if row["target"] == "none" else bool(row["raw_correct"])
        for row in rows
    )
    recognized_correct = sum(
        row["raw_prediction"] == row["target"] for row in recognized_rows
    )
    per_label: dict[str, dict[str, object]] = {}
    for label in sorted({str(row["target"]) for row in rows}):
        label_rows = [row for row in rows if row["target"] == label]
        hand_counts = Counter(str(row["handedness"]) for row in label_rows if row["handedness"])
        per_label[label] = {
            "samples": len(label_rows),
            "evaluation_accuracy": sum(
                bool(row["correct"]) if label == "none" else bool(row["raw_correct"])
                for row in label_rows
            ) / len(label_rows),
            "average_confidence": sum(float(row["confidence"]) for row in label_rows) / len(label_rows),
            "handedness": dict(hand_counts),
        }
    confusions = Counter(
        (str(row["target"]), str(row["effective_prediction"]))
        for row in rows
        if not row["correct"]
    )
    return {
        "samples": total,
        "evaluation_accuracy": evaluated_correct / total if total else 0.0,
        "recognition_coverage": len(recognized_rows) / total if total else 0.0,
        "recognized_accuracy": recognized_correct / len(recognized_rows) if recognized_rows else 0.0,
        "per_label": per_label,
        "confusions": [
            {"target": target, "prediction": prediction, "count": count}
            for (target, prediction), count in confusions.most_common()
        ],
    }


def write_markdown(path: Path, report: dict[str, object]) -> None:
    lines = [
        "# 지문자 모델 평가 보고서",
        "",
        f"- 모델 버전: `{report['model_version']}`",
        f"- 모델 SHA-256: `{report['model_sha256']}`",
        f"- 평가 임계값: `{report['threshold']:.2f}`",
        f"- 독립 평가자 확인: `{report['independent_evaluator']}`",
        f"- 생성 시각: `{report['generated_at']}`",
        "",
        "## 목표 기준",
        "",
        "- 전체 운영 정확도 95% 이상",
        "- 자모별 정확도 85% 이상",
        "- 인식된 결과 정확도 98% 이상",
        "",
        "## 조건별 결과",
        "",
        "| 조건 | 샘플 | 평가 정확도 | 인식률 | 인식 결과 정확도 |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition, result in report["conditions"].items():
        lines.append(
            f"| {condition} | {result['samples']} | "
            f"{result['evaluation_accuracy']:.2%} | "
            f"{result['recognition_coverage']:.2%} | "
            f"{result['recognized_accuracy']:.2%} |"
        )

    lines.extend(["", "## 자모별 결과", "", "| 조건 | 자모 | 샘플 | 평가 정확도 | 평균 신뢰도 | 사용 손 |", "|---|---|---:|---:|---:|---|"])
    for condition, result in report["conditions"].items():
        for label, label_result in result["per_label"].items():
            hands = ", ".join(f"{key}:{value}" for key, value in label_result["handedness"].items()) or "-"
            lines.append(
                f"| {condition} | {label} | {label_result['samples']} | "
                f"{label_result['evaluation_accuracy']:.2%} | "
                f"{label_result['average_confidence']:.2%} | {hands} |"
            )

    lines.extend(["", "## 판정", "", report["verdict"], ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    aliases: dict[str, str] = {}
    for item in args.condition_alias:
        if "=" not in item:
            raise ValueError(f"invalid_condition_alias: {item}")
        session, condition = item.split("=", 1)
        aliases[session] = condition

    rows = load_rows(args.sessions, args.threshold, aliases)
    by_condition: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_condition[str(row["condition"])].append(row)

    condition_metrics = {
        condition: metrics_for(condition_rows)
        for condition, condition_rows in sorted(by_condition.items())
    }
    conditions_pass = all(
        result["evaluation_accuracy"] >= 0.95
        and result["recognized_accuracy"] >= 0.98
        and all(label["evaluation_accuracy"] >= 0.85 for label in result["per_label"].values())
        for result in condition_metrics.values()
    )
    complete_conditions = {"normal", "dim", "near", "far"}.issubset(condition_metrics)
    independent = args.independent_evaluator == "yes"
    passed = conditions_pass and complete_conditions and independent

    report = {
        "model_version": args.model_version,
        "model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "threshold": args.threshold,
        "independent_evaluator": args.independent_evaluator,
        "sessions": args.sessions,
        "generated_at": datetime.now().astimezone().isoformat(),
        "conditions": condition_metrics,
        "verdict": (
            "PASS - 정의한 정확도, 독립 평가자, 네 가지 촬영 조건을 모두 충족했습니다."
            if passed
            else "PENDING - 정확도 기준, 독립 평가자 확인, normal/dim/near/far 조건 중 하나 이상이 미충족입니다."
        ),
    }

    write_markdown(args.output, report)
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"보고서: {args.output}")
    print(report["verdict"])


if __name__ == "__main__":
    main()
