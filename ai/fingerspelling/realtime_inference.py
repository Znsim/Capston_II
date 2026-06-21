"""한글 지문자 실시간 추론 및 단어 조합

웹캠 손 랜드마크를 MLPClassifier로 분류하고,
Dwell(유지) 입력으로 자모를 확정 → KoreanComposer로 한글 음절/단어 조합.

사전 조건 (train_classifier.py 실행 후 생성됨):
  fingerspelling/models/gesture_model.pkl
  fingerspelling/models/label_encoder.pkl

조작:
  b  : 마지막 자모 삭제
  c  : 전체 초기화
  q  : 종료
"""

from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import cv2
import numpy as np
import joblib
import mediapipe as mp
from PIL import ImageFont, ImageDraw, Image
from composer.word_builder import WordBuilder

MODEL_DIR = BASE_DIR / "models"

# ── 모델 로드 ─────────────────────────────────────────────────

_missing = [p for p in [MODEL_DIR / "gesture_model.pkl", MODEL_DIR / "label_encoder.pkl"] if not p.exists()]
if _missing:
    raise FileNotFoundError(
        "다음 파일이 없습니다. 먼저 'python train_classifier.py' 실행:\n"
        + "\n".join(f"  {p}" for p in _missing)
    )

model = joblib.load(MODEL_DIR / "gesture_model.pkl")
le    = joblib.load(MODEL_DIR / "label_encoder.pkl")
print(f"인식 가능 클래스 ({len(le.classes_)}개): {list(le.classes_)}")

# ── 설정 ──────────────────────────────────────────────────────

FONT_PATH      = "C:/Windows/Fonts/malgun.ttf"
CONF_THRESHOLD = 0.80

font_large = ImageFont.truetype(FONT_PATH, 44)
font_mid   = ImageFont.truetype(FONT_PATH, 34)
font_small = ImageFont.truetype(FONT_PATH, 20)

CONSONANTS = {'ㄱ','ㄴ','ㄷ','ㄹ','ㅁ','ㅂ','ㅅ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'}
VOWELS     = {'ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅚ','ㅛ','ㅜ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ'}

RECT = (80, 60, 560, 420)

# ── MediaPipe ─────────────────────────────────────────────────

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5,
)

# ── 헬퍼 함수 ─────────────────────────────────────────────────

def put_text_kr(frame, text, pos, font, color):
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    ImageDraw.Draw(img_pil).text(pos, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def get_char_type(label):
    if label in CONSONANTS:
        return "자음"
    if label in VOWELS:
        return "모음"
    return ""

def extract_landmarks(result):
    if not result.multi_hand_landmarks:
        return None
    coords = [[lm.x, lm.y, lm.z] for lm in result.multi_hand_landmarks[0].landmark]
    return np.array(coords, dtype=np.float32)

def predict(landmarks):
    x     = landmarks.flatten().reshape(1, -1)
    pred  = model.predict(x)[0]
    proba = model.predict_proba(x)[0].max()
    label = le.inverse_transform([pred])[0]
    return label, proba

# ── 메인 루프 ─────────────────────────────────────────────────

builder = WordBuilder(dwell=1.0, space_dwell=2.0)

cap = cv2.VideoCapture(0)
print("실시간 추론 시작  |  b: 지우기  c: 초기화  q: 종료")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame   = cv2.flip(frame, 1)
    h, w    = frame.shape[:2]
    result  = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    display = frame.copy()

    if result.multi_hand_landmarks:
        for hand_lm in result.multi_hand_landmarks:
            mp_drawing.draw_landmarks(
                display, hand_lm,
                mp_hands.HAND_CONNECTIONS,
                mp_drawing_styles.get_default_hand_landmarks_style(),
                mp_drawing_styles.get_default_hand_connections_style(),
            )

    x1, y1, x2, y2 = RECT
    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)

    landmarks = extract_landmarks(result)
    if landmarks is not None:
        label, confidence = predict(landmarks)
        char_type  = get_char_type(label)
        type_tag   = f"[{char_type}] " if char_type else ""
        jamo_text  = f"{type_tag}{label}  ({confidence*100:.1f}%)"
        jamo_color = (0, 255, 0) if confidence >= 0.8 else (0, 165, 255)
        feed_label = label if confidence >= CONF_THRESHOLD else None
    else:
        jamo_text  = "No hand  (2초 유지 → 공백)"
        jamo_color = (150, 150, 150)
        feed_label = None

    wb = builder.update(feed_label)

    display = put_text_kr(display, jamo_text, (x1, 12), font_large, jamo_color)

    # ── 하단 단어 표시 바 ──────────────────────────────────────
    bar = np.zeros((130, w, 3), dtype=np.uint8)

    bar_fill  = int((w - 20) * wb['progress'])
    bar_color = (0, 200, 100) if feed_label else (80, 80, 80)
    cv2.rectangle(bar, (10, 6), (w - 10, 20), (40, 40, 40), -1)
    if bar_fill > 0:
        cv2.rectangle(bar, (10, 6), (10 + bar_fill, 20), bar_color, -1)

    comp_str = f"조합 중: 【{wb['composing']}】" if wb['composing'] else "조합 중: 【 】"
    bar = put_text_kr(bar, comp_str, (10, 24), font_small, (160, 160, 160))

    word_display = wb['text'][-12:] if len(wb['text']) > 12 else wb['text']
    word_display = word_display if word_display.strip() else "..."
    bar = put_text_kr(bar, word_display, (10, 52), font_mid, (255, 240, 80))

    bar = put_text_kr(bar, "b: 지우기    c: 초기화    q: 종료",
                      (10, 104), font_small, (100, 100, 100))

    display = np.vstack([display, bar])
    cv2.imshow("지문자 인식", display)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('b'):
        builder.backspace()
    elif key == ord('c'):
        builder.clear()

cap.release()
hands.close()
cv2.destroyAllWindows()
