"""
지문자 데이터 수집 (영상 녹화 방식)
======================================
실행: python collect_data.py

사용법:
  1. 수집할 자모가 화면에 표시됨
  2. r 키를 누르면 카운트다운 후 자동 녹화 시작
  3. 녹화 중 손이 인식되는 매 프레임이 자동 저장됨
  4. 녹화 완료 후 r 을 반복해 샘플 추가 가능

조작:
  r      : 녹화 시작 (3초 자동 녹화)
  n      : 다음 자모로 이동
  b      : 이전 자모로 이동
  q      : 종료

저장 위치: dataset/<자모>/landmarks_npy/<수집자>_<자모>_XXXX.npy
저장 포맷: (21, 3) float32  ─  MediaPipe 21개 랜드마크 raw 좌표
"""

import sys
import time
import cv2
import numpy as np
import mediapipe as mp
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ai.preprocess import extract_landmarks_raw
from utils import put_text_kr

# ── 설정 ──────────────────────────────────────────────────────────────────
LABELS = [
    "ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
    "ㅏ", "ㅑ", "ㅓ", "ㅕ", "ㅗ", "ㅛ", "ㅜ", "ㅠ", "ㅡ", "ㅣ",
]
RECORD_SECS   = 3      # 한 번 녹화 시간 (초)
COUNTDOWN     = 3      # 녹화 시작 전 카운트다운 (초)
MIN_SAMPLES   = 100    # 권장 최소 샘플 수 (강제 아님)
# ──────────────────────────────────────────────────────────────────────────


def npy_dir(label: str) -> Path:
    return ROOT / "dataset" / label / "landmarks_npy"


def count_existing(label: str, collector: str) -> int:
    d = npy_dir(label)
    if not d.exists():
        return 0
    return len(list(d.glob(f"{collector}_*.npy")))


def next_index(label: str, collector: str) -> int:
    """저장할 다음 인덱스 번호 반환 (기존 파일 이어쓰기)."""
    d = npy_dir(label)
    if not d.exists():
        return 0
    existing = list(d.glob(f"{collector}_*.npy"))
    if not existing:
        return 0
    nums = []
    for f in existing:
        try:
            nums.append(int(f.stem.split("_")[-1]))
        except ValueError:
            pass
    return max(nums) + 1 if nums else 0


def draw_ui(frame, label, label_idx, count, collecting, countdown_val,
            rec_elapsed, rec_total, saved_this_round, detected):
    """매 프레임 UI를 그린다."""
    h, w = frame.shape[:2]

    # 상단 검은 배경
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 115), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    # 자모 이름
    frame = put_text_kr(frame, f"자모: {label}  ({label_idx+1}/{len(LABELS)})",
                         (10, 5), font_size=38, color=(0, 255, 0))

    # 수집된 샘플 수
    cnt_color = (0, 255, 100) if count >= MIN_SAMPLES else (0, 200, 255)
    frame = put_text_kr(frame, f"저장됨: {count}개  (권장 {MIN_SAMPLES}개)",
                         (10, 55), font_size=30, color=cnt_color)

    if collecting:
        # ── 녹화 중 UI ────────────────────────────────────────────────
        remain = max(0.0, rec_total - rec_elapsed)

        # 진행 바
        bar_w = int((w - 20) * (rec_elapsed / rec_total))
        cv2.rectangle(frame, (10, h - 30), (w - 10, h - 10), (60, 60, 60), -1)
        cv2.rectangle(frame, (10, h - 30), (10 + bar_w, h - 10), (0, 0, 220), -1)

        frame = put_text_kr(frame, f"녹화 중...  {remain:.1f}초  이번 저장: {saved_this_round}프레임",
                             (10, h - 75), font_size=30, color=(0, 80, 255))

        # 손 미감지 경고
        if not detected:
            frame = put_text_kr(frame, "손 인식 안됨 ─ 손을 화면에 보이세요",
                                 (10, h - 115), font_size=28, color=(0, 80, 255))
    else:
        # ── 대기 중 UI ────────────────────────────────────────────────
        if not detected:
            frame = put_text_kr(frame, "손이 인식되지 않습니다",
                                 (10, h - 75), font_size=30, color=(0, 80, 255))
        else:
            frame = put_text_kr(frame, "r=녹화시작  n=다음  b=이전  q=종료",
                                 (10, h - 75), font_size=28, color=(200, 200, 200))

    return frame


def countdown_screen(cap, hands, mp_hands, mp_draw, label, label_idx, countdown):
    """녹화 전 카운트다운을 보여준다. 손 랜드마크도 계속 표시."""
    for sec in range(countdown, 0, -1):
        deadline = time.time() + 1.0
        while time.time() < deadline:
            ret, frame = cap.read()
            if not ret:
                return
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if result.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, result.multi_hand_landmarks[0],
                                       mp_hands.HAND_CONNECTIONS)

            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, 115), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

            frame = put_text_kr(frame, f"자모: {label}  ({label_idx+1}/{len(LABELS)})",
                                 (10, 5), font_size=38, color=(0, 255, 0))
            frame = put_text_kr(frame, f"녹화 시작까지  {sec}초",
                                 (w // 2 - 120, h // 2 - 50),
                                 font_size=65, color=(0, 200, 255))

            cv2.imshow("지문자 데이터 수집", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return


def main():
    collector = input("수집자 이름 (영문): ").strip()
    if not collector:
        print("이름을 입력하세요.")
        sys.exit(1)

    mp_hands = mp.solutions.hands
    mp_draw  = mp.solutions.drawing_utils
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("카메라를 열 수 없습니다.")
        sys.exit(1)

    label_idx = 0
    print("조작: [r]=녹화시작  [n]=다음자모  [b]=이전자모  [q]=종료")

    while 0 <= label_idx < len(LABELS):
        label    = LABELS[label_idx]
        save_dir = npy_dir(label)
        save_dir.mkdir(parents=True, exist_ok=True)

        # ── 대기 루프 ────────────────────────────────────────────────
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)

        result   = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        detected = result.multi_hand_landmarks is not None
        if detected:
            mp_draw.draw_landmarks(frame, result.multi_hand_landmarks[0],
                                   mp_hands.HAND_CONNECTIONS)

        count = count_existing(label, collector)
        frame = draw_ui(frame, label, label_idx, count,
                        collecting=False, countdown_val=0,
                        rec_elapsed=0, rec_total=RECORD_SECS,
                        saved_this_round=0, detected=detected)

        cv2.imshow("지문자 데이터 수집", frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("n"):
            label_idx += 1
            continue
        elif key == ord("b") and label_idx > 0:
            label_idx -= 1
            continue
        elif key != ord("r"):
            continue

        # ── r 키: 카운트다운 → 녹화 ─────────────────────────────────
        countdown_screen(cap, hands, mp_hands, mp_draw, label, label_idx, COUNTDOWN)

        idx            = next_index(label, collector)
        saved_round    = 0
        rec_start      = time.time()

        while True:
            elapsed = time.time() - rec_start
            if elapsed >= RECORD_SECS:
                break

            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)

            result   = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            detected = result.multi_hand_landmarks is not None

            if detected:
                mp_draw.draw_landmarks(frame, result.multi_hand_landmarks[0],
                                       mp_hands.HAND_CONNECTIONS)
                arr   = extract_landmarks_raw(result.multi_hand_landmarks[0])  # (21, 3)
                fname = save_dir / f"{collector}_{label}_{idx:04d}.npy"
                np.save(str(fname), arr)
                idx         += 1
                saved_round += 1

            frame = draw_ui(frame, label, label_idx,
                            count_existing(label, collector),
                            collecting=True, countdown_val=0,
                            rec_elapsed=elapsed, rec_total=RECORD_SECS,
                            saved_this_round=saved_round, detected=detected)

            cv2.imshow("지문자 데이터 수집", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                cap.release()
                cv2.destroyAllWindows()
                hands.close()
                print("수집 종료.")
                return

        total = count_existing(label, collector)
        print(f"[{label}] 이번 녹화: {saved_round}프레임  누적: {total}개")

    cap.release()
    cv2.destroyAllWindows()
    hands.close()
    print("수집 종료.")


if __name__ == "__main__":
    main()
