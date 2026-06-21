"""동적 수어 단어 데이터 수집 스크립트

MediaPipe Holistic으로 4초 동안 녹화 후 45프레임으로 균등 샘플링하여
word_data/<수집자>/<단어>/<단어_XXXX.npy> 형태로 저장합니다.

데이터 형식: (45, 201) float32  — 정규화 좌표 (0~1)
  [0:75]    Pose 25 landmarks  (lm.x, lm.y, visibility)
  [75:138]  Left Hand 21 landmarks (lm.x, lm.y, 1.0)
  [138:201] Right Hand 21 landmarks (lm.x, lm.y, 1.0)

  ※ 픽셀 좌표가 아닌 MediaPipe 정규화 좌표 사용
     → 해상도·카메라 무관, 팀원 PC 간 일관성 보장

FPS 처리:
  4초 동안 최대한 캡처 후 45프레임으로 균등 샘플링
  → 팀원 PC 성능 차이에 상관없이 동일한 시간 구간 표현

조작:
  a / d    : 이전 / 다음 단어
  SPACE    : 3초 카운트다운 후 4초 녹화 시작
  r        : 마지막 저장 샘플 삭제 (실수 수정)
  q        : 종료
"""

import csv
import time
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from PIL import ImageFont, ImageDraw, Image

# ── 설정 ──────────────────────────────────────────────────────
FEATURE_DIM     = 201
NUM_FRAMES      = 45       # 저장할 프레임 수 (균등 샘플링 목표)
RECORD_DURATION = 4.0      # 녹화 시간(초) — PC 성능 무관하게 고정
COUNTDOWN       = 3        # 녹화 전 카운트다운(초)
MIN_CAPTURE     = 30       # 최소 캡처 프레임 (이 이하면 저장 안 함)
DATA_ROOT       = Path(__file__).resolve().parent / "word_data"
FONT_PATH       = "C:/Windows/Fonts/malgun.ttf"

VOCABULARY = [
    '가다', '감사', '건너다', '고장', '공항',
    '기차', '내리다', '도움', '맞다', '매표소',
    '버스', '시간', '어디', '엘리베이터', '여기',
    '역', '오른쪽', '왼쪽', '잃어버리다', '정류장',
    '지하철', '찾다', '카드', '타다', '택시', '화장실',
]

font_sm = ImageFont.truetype(FONT_PATH, 20)
font_md = ImageFont.truetype(FONT_PATH, 30)
font_lg = ImageFont.truetype(FONT_PATH, 44)

mp_holistic = mp.solutions.holistic
mp_drawing  = mp.solutions.drawing_utils

# ── 헬퍼 함수 ─────────────────────────────────────────────────

def put_kr(frame, text, pos, font, color):
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    ImageDraw.Draw(img).text(pos, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def extract_features(result) -> np.ndarray:
    """MediaPipe Holistic 결과 → 201차원 어깨 중점 기준 상대 좌표 벡터
    기준점: 왼쪽 어깨(11)와 오른쪽 어깨(12)의 중점 (cx, cy)
    → 위치·거리가 달라져도 수어 모양 자체는 동일하게 유지됨
    """
    feat = np.zeros(FEATURE_DIM, dtype=np.float32)

    # 어깨 중점 계산 (포즈 미검출 시 화면 중앙 fallback)
    cx, cy = 0.5, 0.5
    if result.pose_landmarks:
        lm11 = result.pose_landmarks.landmark[11]
        lm12 = result.pose_landmarks.landmark[12]
        cx = (lm11.x + lm12.x) / 2
        cy = (lm11.y + lm12.y) / 2

    if result.pose_landmarks:
        for i in range(25):
            lm = result.pose_landmarks.landmark[i]
            feat[i*3 : i*3+3] = [lm.x - cx, lm.y - cy, lm.visibility]
    offset_lh = 75
    if result.left_hand_landmarks:
        for i in range(21):
            lm = result.left_hand_landmarks.landmark[i]
            feat[offset_lh + i*3 : offset_lh + i*3+3] = [lm.x - cx, lm.y - cy, 1.0]
    offset_rh = 138
    if result.right_hand_landmarks:
        for i in range(21):
            lm = result.right_hand_landmarks.landmark[i]
            feat[offset_rh + i*3 : offset_rh + i*3+3] = [lm.x - cx, lm.y - cy, 1.0]
    return feat


def sample_frames(all_feats: list, n: int) -> np.ndarray:
    """균등 샘플링: len(all_feats) 프레임 → n 프레임"""
    indices = np.round(np.linspace(0, len(all_feats) - 1, n)).astype(int)
    return np.array([all_feats[i] for i in indices], dtype=np.float32)


def draw_hol(frame, result):
    if result.pose_landmarks:
        mp_drawing.draw_landmarks(frame, result.pose_landmarks, mp_holistic.POSE_CONNECTIONS)
    if result.left_hand_landmarks:
        mp_drawing.draw_landmarks(frame, result.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
    if result.right_hand_landmarks:
        mp_drawing.draw_landmarks(frame, result.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)


def count_samples(word_dir: Path, word: str) -> int:
    return len(list(word_dir.glob(f"{word}_*.npy")))


def save_sample(word_dir: Path, word: str, seq: np.ndarray, counter: int) -> Path:
    path = word_dir / f"{word}_{counter:04d}.npy"
    np.save(str(path), seq)
    return path


def update_manifest(speaker_dir: Path, word: str, filename: str, captured: int):
    manifest = speaker_dir / "manifest.csv"
    write_header = not manifest.exists()
    with open(manifest, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(['word', 'filename', 'captured_frames', 'timestamp'])
        w.writerow([word, filename, captured, time.strftime('%Y-%m-%d %H:%M:%S')])


def remove_last_sample(word_dir: Path, word: str, counter: int) -> bool:
    if counter == 0:
        return False
    path = word_dir / f"{word}_{counter - 1:04d}.npy"
    if path.exists():
        path.unlink()
        return True
    return False


# ── 메인 ──────────────────────────────────────────────────────

def main():
    speaker = input("수집자 이름을 입력하세요 (예: 홍길동_1): ").strip()
    if not speaker:
        speaker = "unknown_1"

    speaker_dir = DATA_ROOT / speaker
    for word in VOCABULARY:
        (speaker_dir / word).mkdir(parents=True, exist_ok=True)

    counters = {word: count_samples(speaker_dir / word, word) for word in VOCABULARY}
    word_idx = 0

    # model_complexity=0 (LITE): CPU에서 더 빠름 → FPS 확보에 유리
    holistic = mp_holistic.Holistic(
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("카메라를 열 수 없습니다.")
        return

    print(f"\n[{speaker}] 수집 시작  (정규화 좌표, {RECORD_DURATION:.0f}초 녹화)")
    print("a/d: 단어 변경  |  SPACE: 녹화  |  r: 마지막 샘플 삭제  |  q: 종료")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        result = holistic.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        display = frame.copy()
        draw_hol(display, result)

        word = VOCABULARY[word_idx]
        cnt  = counters[word]

        display = put_kr(display, f"[ {word} ]   수집: {cnt}개", (10, 6), font_lg, (0, 255, 0))

        # 우측 단어 목록
        for i in range(-2, 3):
            vi  = (word_idx + i) % len(VOCABULARY)
            col = (255, 255, 0) if i == 0 else (140, 140, 140)
            fn  = font_md if i == 0 else font_sm
            display = put_kr(display, VOCABULARY[vi], (w - 140, h // 2 + i * 34), fn, col)

        display = put_kr(display, "a/d: 단어변경  SPACE: 녹화  r: 삭제  q: 종료",
                         (10, h - 28), font_sm, (160, 160, 160))

        cv2.imshow("단어 수집", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('a'):
            word_idx = (word_idx - 1) % len(VOCABULARY)
        elif key == ord('d'):
            word_idx = (word_idx + 1) % len(VOCABULARY)
        elif key == ord('r'):
            if remove_last_sample(speaker_dir / word, word, counters[word]):
                counters[word] -= 1
                print(f"삭제됨: {word}_{counters[word]:04d}.npy  (남은 {counters[word]}개)")
            else:
                print("삭제할 샘플이 없습니다.")

        elif key == ord(' '):
            word     = VOCABULARY[word_idx]
            word_dir = speaker_dir / word

            # ── 카운트다운 ────────────────────────────────────
            for cd in range(COUNTDOWN, 0, -1):
                t_end = time.time() + 1.0
                while time.time() < t_end:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame = cv2.flip(frame, 1)
                    h, w = frame.shape[:2]
                    result = holistic.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    display = frame.copy()
                    draw_hol(display, result)
                    display = put_kr(display, f"준비: {cd}초",
                                     (w // 2 - 70, h // 2 - 30), font_lg, (0, 200, 255))
                    cv2.imshow("단어 수집", display)
                    cv2.waitKey(1)

            # ── 시간 기반 녹화 (RECORD_DURATION 초) ──────────
            all_feats = []
            t_start = time.time()

            while time.time() - t_start < RECORD_DURATION:
                ret, frame = cap.read()
                if not ret:
                    break
                frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                result = holistic.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                all_feats.append(extract_features(result))

                elapsed  = time.time() - t_start
                progress = min(elapsed / RECORD_DURATION, 1.0)
                remaining = max(RECORD_DURATION - elapsed, 0.0)

                display = frame.copy()
                draw_hol(display, result)
                bw = int((w - 40) * progress)
                cv2.rectangle(display, (20, h - 30), (w - 20, h - 10), (40, 40, 40), -1)
                cv2.rectangle(display, (20, h - 30), (20 + bw, h - 10), (0, 0, 220), -1)
                display = put_kr(display,
                                 f"녹화 중 [{word}]  {remaining:.1f}초 남음  ({len(all_feats)}f)",
                                 (10, 6), font_md, (0, 0, 255))
                cv2.imshow("단어 수집", display)
                cv2.waitKey(1)

            # ── 균등 샘플링 후 저장 ───────────────────────────
            captured = len(all_feats)
            if captured >= MIN_CAPTURE:
                seq  = sample_frames(all_feats, NUM_FRAMES)   # (45, 201)
                path = save_sample(word_dir, word, seq, counters[word])
                update_manifest(speaker_dir, word, path.name, captured)
                counters[word] += 1
                print(f"저장됨: {path}  (캡처 {captured}f → {NUM_FRAMES}f 샘플링, 총 {counters[word]}개)")
            else:
                print(f"프레임 부족 ({captured}/{MIN_CAPTURE}) — 저장 안 됨. 카메라/속도 확인.")

    cap.release()
    holistic.close()
    cv2.destroyAllWindows()
    print("수집 종료")


if __name__ == "__main__":
    main()
