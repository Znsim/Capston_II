"""BiLSTM 기반 수어 단어 실시간 추론

사전 조건 (ai/train_bilstm.py 실행 후 생성됨):
  new_word/models/dynamic_gesture_model.pt
  new_word/models/model_config.pkl
  new_word/models/label_encoder_dynamic.pkl
  new_word/models/norm_stats.pkl

캡처 방식:
  collect_word_data.py 와 동일하게 4초 녹화 후 45프레임 균등 샘플링
  → 학습 데이터와 시간 축 표현 일치

조작:
  SPACE  : 4초 캡처 시작 → 자동 추론
  b      : 마지막 인식 단어 삭제
  c      : 문장 초기화
  q      : 종료
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import joblib
import torch
import mediapipe as mp
mp_holistic = mp.solutions.holistic
mp_drawing  = mp.solutions.drawing_utils
from PIL import ImageFont, ImageDraw, Image

BASE_DIR  = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / 'ai'))
from model_bilstm import BiLSTMClassifier  # noqa: E402

# ── 설정 ──────────────────────────────────────────────────────
FEATURE_DIM     = 201
NUM_FRAMES      = 45
RECORD_DURATION = 4.0    # collect_word_data.py 와 동일
MIN_CAPTURE     = 30     # 최소 캡처 프레임 (< 이면 저장 안 함)
CONF_THRESHOLD  = 0.5
MODEL_DIR       = BASE_DIR / "models"
FONT_PATH       = "C:/Windows/Fonts/malgun.ttf"

font_sm = ImageFont.truetype(FONT_PATH, 20)
font_md = ImageFont.truetype(FONT_PATH, 30)
font_lg = ImageFont.truetype(FONT_PATH, 44)


# ── 헬퍼 함수 ─────────────────────────────────────────────────

def put_kr(frame, text, pos, font, color):
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    ImageDraw.Draw(img).text(pos, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def extract_features(result) -> np.ndarray:
    """MediaPipe Holistic → 201차원 어깨 중점 기준 상대 좌표 (collect_word_data.py 와 동일 포맷)"""
    feat = np.zeros(FEATURE_DIM, dtype=np.float32)

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


def sample_frames(buf: list, n: int) -> np.ndarray:
    """균등 샘플링: len(buf) 프레임 → n 프레임 (collect_word_data.py 와 동일)"""
    indices = np.round(np.linspace(0, len(buf) - 1, n)).astype(int)
    return np.array([buf[i] for i in indices], dtype=np.float32)


def draw_hol(frame, result):
    if result.pose_landmarks:
        mp_drawing.draw_landmarks(frame, result.pose_landmarks, mp_holistic.POSE_CONNECTIONS)
    if result.left_hand_landmarks:
        mp_drawing.draw_landmarks(frame, result.left_hand_landmarks, mp_holistic.HAND_CONNECTIONS)
    if result.right_hand_landmarks:
        mp_drawing.draw_landmarks(frame, result.right_hand_landmarks, mp_holistic.HAND_CONNECTIONS)


# ── 모델 로드 ──────────────────────────────────────────────────

def load_model():
    paths = {
        'config': MODEL_DIR / "model_config.pkl",
        'model':  MODEL_DIR / "dynamic_gesture_model.pt",
        'le':     MODEL_DIR / "label_encoder_dynamic.pkl",
        'stats':  MODEL_DIR / "norm_stats.pkl",
    }
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "다음 파일이 없습니다. 먼저 'python ai/train_bilstm.py' 실행:\n"
            + "\n".join(f"  {p}" for p in missing)
        )

    config = joblib.load(paths['config'])
    le     = joblib.load(paths['le'])
    stats  = joblib.load(paths['stats'])

    model = BiLSTMClassifier(
        input_size    = config['input_size'],
        hidden_size   = config['hidden_size'],
        num_layers    = config['num_layers'],
        num_classes   = config['num_classes'],
        bidirectional = config.get('bidirectional', True),
        dropout       = config.get('dropout', 0.5),
    )
    model.load_state_dict(torch.load(paths['model'], map_location='cpu'))
    model.eval()
    return model, le, stats['mean'], stats['std']


# ── 추론 ───────────────────────────────────────────────────────

def infer(model, le, mean, std, frames: np.ndarray):
    arr = (frames - mean) / (std + 1e-8)           # (45, 201)
    x   = torch.from_numpy(arr).unsqueeze(0)       # (1, 45, 201)
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=1)[0]
        idx   = probs.argmax().item()
        conf  = probs[idx].item()
    top3_idx  = probs.topk(3).indices.tolist()
    top3_conf = probs.topk(3).values.tolist()
    top3 = [(le.inverse_transform([i])[0], c) for i, c in zip(top3_idx, top3_conf)]
    print(f"  TOP3: " + "  /  ".join(f"{w}({c*100:.1f}%)" for w, c in top3))
    return le.inverse_transform([idx])[0], conf


# ── 메인 ──────────────────────────────────────────────────────

def main():
    print("모델 로딩 중...")
    try:
        model, le, mean, std = load_model()
    except FileNotFoundError as e:
        print(e)
        return

    print(f"인식 가능 단어 ({len(le.classes_)}개): {list(le.classes_)}")

    holistic = mp_holistic.Holistic(
        model_complexity=0,              # collect_word_data.py 와 동일: LITE
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("카메라를 열 수 없습니다.")
        holistic.close()
        return

    sentence      = []
    last_word     = ""
    last_conf     = 0.0
    capturing     = False
    capture_buf   = []
    capture_start = 0.0

    print(f"실시간 추론 시작 | SPACE: {RECORD_DURATION:.0f}초 캡처  b: 삭제  c: 초기화  q: 종료")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w  = frame.shape[:2]
        result = holistic.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        display = frame.copy()
        draw_hol(display, result)

        # ── 캡처 중 ───────────────────────────────────────────
        if capturing:
            capture_buf.append(extract_features(result))

            elapsed   = time.time() - capture_start
            remaining = max(RECORD_DURATION - elapsed, 0.0)
            progress  = min(elapsed / RECORD_DURATION, 1.0)

            bw = int((w - 40) * progress)
            cv2.rectangle(display, (20, h - 30), (w - 20, h - 10), (40, 40, 40), -1)
            cv2.rectangle(display, (20, h - 30), (20 + bw, h - 10), (0, 0, 220), -1)
            display = put_kr(display,
                             f"캡처 중... {remaining:.1f}초 남음  ({len(capture_buf)}f)",
                             (10, 6), font_md, (0, 0, 255))

            if elapsed >= RECORD_DURATION:
                captured = len(capture_buf)
                if captured >= MIN_CAPTURE:
                    frames = sample_frames(capture_buf, NUM_FRAMES)
                    word, conf = infer(model, le, mean, std, frames)
                    last_word, last_conf = word, conf
                    if conf >= CONF_THRESHOLD:
                        sentence.append(word)
                        print(f"인식: {word} ({conf*100:.1f}%)")
                    else:
                        print(f"낮은 신뢰도: {word} ({conf*100:.1f}%) — 무시됨")
                else:
                    print(f"프레임 부족 ({captured}/{MIN_CAPTURE}) — 카메라/속도 확인")
                capture_buf = []
                capturing   = False

        # ── 대기 중 ───────────────────────────────────────────
        else:
            if last_word:
                col = (0, 255, 0) if last_conf >= CONF_THRESHOLD else (0, 165, 255)
                display = put_kr(display, f"인식: {last_word} ({last_conf*100:.1f}%)",
                                 (10, 6), font_lg, col)
            else:
                display = put_kr(display, "SPACE를 눌러 수어를 인식하세요",
                                 (10, 6), font_md, (180, 180, 180))

        # ── 문장 표시 (하단) ──────────────────────────────────
        sent_text = " ".join(sentence[-5:]) if sentence else "..."
        display = put_kr(display, sent_text, (10, h - 70), font_lg, (255, 240, 80))
        display = put_kr(display, f"SPACE: {RECORD_DURATION:.0f}초 캡처  b: 삭제  c: 초기화  q: 종료",
                         (10, h - 28), font_sm, (140, 140, 140))

        cv2.imshow("수어 단어 인식", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord(' ') and not capturing:
            capturing     = True
            capture_buf   = []
            capture_start = time.time()
            print(f"캡처 시작 ({RECORD_DURATION:.0f}초)...")
        elif key == ord('b') and sentence:
            print(f"삭제: {sentence.pop()}")
        elif key == ord('c'):
            sentence.clear()
            last_word, last_conf = "", 0.0
            print("초기화됨")

    cap.release()
    holistic.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
