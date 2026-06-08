ㅠ# AI 개발 가이드

## AI 파트 역할 요약

```
[웹캠 영상]
    │
    │  ① MediaPipe로 손/몸 랜드마크 추출
    ▼
[특징 벡터]
    │
    │  ② 지문자 모델 (MLPClassifier) — 자모 1개 반환
    │  ② 수어 단어 모델 (BiLSTM)     — 단어 1개 반환
    ▼
[인식 결과 + 신뢰도]
    │
    │  ③ 백엔드 /api/inference 로 전달
    ▼
[DB 기록 + 역무원 전달]
```

| 모듈 | 파일 위치 | 기술 스택 | 입력 | 출력 |
|------|-----------|-----------|------|------|
| 지문자 인식 | `ai/fingerspelling/` | MediaPipe Hands + MLPClassifier | 손 랜드마크 63차원 | 자모 1개 (32클래스) |
| 수어 단어 인식 | `ai/new_word/` | MediaPipe Holistic + BiLSTM | 시퀀스 (45, 201) | 단어 1개 (26클래스) |

---

## 1단계: 환경 세팅

### Python 버전

Python **3.10** 권장

### 지문자 모듈 패키지

```bash
pip install mediapipe opencv-python scikit-learn==1.7.2 joblib Pillow numpy
```

> `scikit-learn` 버전이 다르면 모델 로드 시 오류 발생 → **반드시 1.7.2 고정**

### 수어 단어 모듈 패키지

```bash
pip install torch torchvision mediapipe opencv-python scikit-learn joblib Pillow tensorboard
```

---

## 2단계: 폴더 구조

```
ai/
├── fingerspelling/                  # 지문자(자모) 인식 모듈
│   ├── collect_data.py              # 데이터 수집
│   ├── train_classifier.py          # 모델 학습
│   ├── realtime_inference.py        # 실시간 추론 + 한글 조합 데모
│   ├── composer/
│   │   ├── korean_composer.py       # 두벌식 오토마타 (자모 → 음절)
│   │   └── word_builder.py          # Dwell 타이머 기반 입력 확정
│   ├── dataset/                     # 수집 데이터 (gitignore)
│   │   └── <자모>/landmarks_npy/*.npy
│   └── models/                      # 학습 완료 모델 (gitignore)
│       ├── gesture_model.pkl
│       └── label_encoder.pkl
│
└── new_word/                        # 수어 단어 인식 모듈
    ├── collect_word_data.py          # 데이터 수집
    ├── realtime_word_inference.py    # 실시간 추론 데모
    ├── ai/
    │   ├── train_bilstm.py           # 모델 학습
    │   ├── model_bilstm.py           # BiLSTM 아키텍처 정의
    │   ├── dataset_dynamic.py        # PyTorch 데이터셋 로더
    │   └── preprocess.py             # 정규화·증강 함수
    ├── word_data/                    # 수집 데이터 (gitignore)
    │   └── <수집자>/<단어>/*.npy
    └── models/                       # 학습 완료 모델 (gitignore)
        ├── dynamic_gesture_model.pt
        ├── model_config.pkl
        ├── label_encoder_dynamic.pkl
        └── norm_stats.pkl
```

---

## 3단계: 모델 스펙 (백엔드 인수인계용)

### 모델 A — 지문자 분류기 (MLPClassifier)

백엔드에 전달하는 파일:

| 파일 | 크기 (참고) | 용도 |
|------|-------------|------|
| `fingerspelling/models/gesture_model.pkl` | ~942KB | 학습된 MLP 모델 |
| `fingerspelling/models/label_encoder.pkl` | ~839B | 인덱스(0~31) → 한글 자모 변환기 |

| 항목 | 값 |
|------|-----|
| 모델 타입 | `sklearn.neural_network.MLPClassifier` |
| 저장 형식 | `.pkl` (joblib) |
| 입력 형태 | `float32` shape `(1, 63)` |
| 입력 내용 | MediaPipe Hands 21개 랜드마크 × (x, y, z) |
| 출력 | 클래스 인덱스 0~31 + 확률값 |
| 클래스 수 | 32개 (자음 14 + none 1 + 모음 17) |
| 학습 scikit-learn 버전 | **1.7.2** (버전 불일치 시 로드 실패) |

**백엔드 로드 코드:**

```python
import joblib

model = joblib.load("fingerspelling/models/gesture_model.pkl")
le    = joblib.load("fingerspelling/models/label_encoder.pkl")
```

**백엔드 추론 코드:**

```python
import numpy as np

def inference_jamo(keypoints: list[float]) -> dict:
    x = np.array(keypoints, dtype=np.float32).reshape(1, -1)  # (1, 63)
    pred  = model.predict(x)[0]                                # 인덱스 0~31
    proba = float(model.predict_proba(x)[0].max())             # 신뢰도
    label = le.inverse_transform([pred])[0]                    # 한글 자모
    return {"label_id": int(pred), "jamo": label, "confidence": proba}
```

---

### 모델 B — 수어 단어 분류기 (BiLSTM)

백엔드에 전달하는 파일:

| 파일 | 용도 |
|------|------|
| `new_word/models/dynamic_gesture_model.pt` | 학습된 BiLSTM 가중치 |
| `new_word/models/model_config.pkl` | 모델 하이퍼파라미터 (hidden_size, num_layers 등) |
| `new_word/models/label_encoder_dynamic.pkl` | 인덱스 → 한국어 단어 변환기 |
| `new_word/models/norm_stats.pkl` | 정규화 평균·표준편차 (추론 전 적용 필수) |

| 항목 | 값 |
|------|-----|
| 모델 타입 | `BiLSTM` (PyTorch) |
| 저장 형식 | `.pt` (torch.save) + `.pkl` (joblib) |
| 입력 형태 | `float32` shape `(1, 45, 201)` |
| 입력 내용 | MediaPipe Holistic 시퀀스 (45프레임 × 201차원) |
| 출력 | 26개 클래스 로짓 → argmax → 단어 |
| 클래스 수 | 26개 교통 도메인 단어 |

**입력 특징 벡터 구성 (201차원):**

```
[  0: 75] — Pose 25개 랜드마크 (x, y, visibility)
[ 75:138] — 왼손 21개 랜드마크 (x, y, 1.0)
[138:201] — 오른손 21개 랜드마크 (x, y, 1.0)
```

> 좌표는 **양쪽 어깨 중점 기준 상대 좌표**로 정규화 → 사람 위치·거리 무관

**백엔드 로드 코드:**

```python
import torch
import joblib
from new_word.ai.model_bilstm import GestureClassifier

config = joblib.load("new_word/models/model_config.pkl")
le     = joblib.load("new_word/models/label_encoder_dynamic.pkl")
stats  = joblib.load("new_word/models/norm_stats.pkl")

model = GestureClassifier(**config)
model.load_state_dict(torch.load("new_word/models/dynamic_gesture_model.pt", map_location="cpu"))
model.eval()
```

**백엔드 추론 코드:**

```python
import numpy as np

def inference_word(sequence: np.ndarray) -> dict:
    # sequence: (45, 201) float32
    # 정규화 (학습 시 사용한 stats 적용)
    mean, std = stats["mean"], stats["std"]
    sequence = (sequence - mean) / (std + 1e-8)

    x = torch.tensor(sequence, dtype=torch.float32).unsqueeze(0)  # (1, 45, 201)
    with torch.no_grad():
        logits = model(x)                               # (1, 26)
        probs  = torch.softmax(logits, dim=-1)
        pred   = logits.argmax(dim=-1).item()
        proba  = float(probs[0, pred])

    label = le.inverse_transform([pred])[0]
    return {"class_id": pred, "word": label, "confidence": proba}
```

---

## 4단계: 데이터 수집 및 학습 절차

### A. 지문자 데이터 수집

```bash
cd ai/fingerspelling
python collect_data.py
```

| 키 | 동작 |
|----|------|
| `m` | 자음 ↔ 모음 모드 전환 |
| `1`~`9`, `a`~`e` | 자모 선택 (10초 자동 녹화 시작) |
| `0` | none (손 없음) 수집 |
| `q` | 종료 |

저장 형식: `dataset/<자모>/landmarks_npy/<자모>_NNNN.npy` — shape `(21, 3)` float32

**권장 수집량:** 자모당 **200개 이상**

---

### A-2. 지문자 모델 학습

```bash
python train_classifier.py
```

- `dataset/` 안의 모든 자모 폴더를 자동 탐색
- 완료 후 `models/gesture_model.pkl`, `models/label_encoder.pkl` 생성

---

### B. 수어 단어 데이터 수집

```bash
cd ai/new_word
python collect_word_data.py
```

| 키 | 동작 |
|----|------|
| `a` / `d` | 이전 / 다음 단어 |
| `SPACE` | 3초 카운트다운 후 4초 녹화 시작 |
| `r` | 마지막 샘플 삭제 |
| `q` | 종료 |

저장 형식: `word_data/<수집자>/<단어>/<단어_XXXX.npy>` — shape `(45, 201)` float32

**권장 수집량:** 단어당 **100개 이상**, 수집자 여러 명 권장

> 여러 PC에서 수집할 경우 수집자 이름을 다르게 설정하면 자동 병합됩니다.

---

### B-2. 수어 단어 모델 학습

```bash
python ai/train_bilstm.py
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--data-root` | `word_data/` | 수집 데이터 경로 |
| `--epochs` | 50 | 학습 에폭 수 |
| `--batch-size` | 32 | 배치 크기 |
| `--hidden` | 128 | LSTM 히든 크기 |

완료 후 `models/` 폴더에 4개 파일 생성:
- `dynamic_gesture_model.pt`
- `model_config.pkl`
- `label_encoder_dynamic.pkl`
- `norm_stats.pkl`

TensorBoard 로그 확인:

```bash
tensorboard --logdir runs/
```

---

## 5단계: 실시간 추론 데모 (독립 실행 확인용)

### 지문자 데모

```bash
cd ai/fingerspelling
python realtime_inference.py
```

- 손을 화면 내 **녹색 사각형** 안에 위치
- 자모를 **1초 유지** → 자동 확정 및 한글 조합
- 손 없음 **2초 유지** → 공백 추가
- `b`: 마지막 자모 삭제 / `c`: 전체 초기화 / `q`: 종료

### 수어 단어 데모

```bash
cd ai/new_word
python realtime_word_inference.py
```

- `SPACE` → 4초 캡처 후 자동 추론
- `b`: 마지막 인식 단어 삭제 / `c`: 문장 초기화 / `q`: 종료

---

## 6단계: 전체 시스템에서 AI 위치

```
[키오스크 웹캠]
    │
    │  ① 프론트: MediaPipe로 랜드마크 추출
    │      지문자 → 손 랜드마크 63개 float
    │      수어단어 → Holistic 시퀀스 (45, 201)
    ▼
POST /api/inference  ← 프론트가 keypoints 전송
    │
    │  ② 백엔드: AI 모델로 추론
    │      지문자 모델 → 자모 1개 반환 (confidence 포함)
    │      수어단어 모델 → 단어 1개 반환 (confidence 포함)
    │  ③ 백엔드: Communication_Log에 결과 저장
    ▼
GET /api/poll/answer  ← 키오스크가 역무원 답변 폴링
    │
    ▼
[역무원 화면 → 답변 → 키오스크 화면 표시]
```

---

## 인식 클래스 목록

### 지문자 (32개)

| 구분 | 클래스 |
|------|--------|
| 자음 (14개) | ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ |
| 모음 (17개) | ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅚ ㅛ ㅜ ㅟ ㅠ ㅡ ㅢ ㅣ |
| 기타 (1개) | none (손 인식 안 됨) |

### 수어 단어 (26개)

| | | | | |
|---|---|---|---|---|
| 가다 | 감사 | 건너다 | 고장 | 공항 |
| 기차 | 내리다 | 도움 | 맞다 | 매표소 |
| 버스 | 시간 | 어디 | 엘리베이터 | 여기 |
| 역 | 오른쪽 | 왼쪽 | 잃어버리다 | 정류장 |
| 지하철 | 찾다 | 카드 | 타다 | 택시 |
| 화장실 | | | | |

---

## 주의사항

| 항목 | 내용 |
|------|------|
| scikit-learn 버전 | 지문자 모델이 `1.7.2`로 학습됨 → `pip install scikit-learn==1.7.2` 필수 |
| 모델 로드 시점 | 서버 시작 시 1회만 로드 (요청마다 로드하면 응답 지연 발생) |
| 정규화 필수 | 수어 단어 추론 전 반드시 `norm_stats.pkl`의 mean·std 적용 |
| none 처리 | 지문자 인식 결과가 `none`(label_id=0)이면 "손 인식 안 됨"으로 처리 |
| confidence 임계값 | 지문자 0.75 미만, 수어단어 0.6 미만이면 인식 실패로 처리 권장 |
| 좌표 정규화 방식 | 모든 랜드마크는 MediaPipe 정규화 좌표(0~1) → 카메라 해상도 무관 |
| 어깨 기준 상대 좌표 | 수어 단어 데이터는 어깨 중점 기준 상대 좌표 → 키오스크 위치 무관 |
| Windows 전용 폰트 | 데모 스크립트에서 `C:/Windows/Fonts/malgun.ttf` 사용 (서버 배포 시 수정 필요) |
| 모델 파일 Git 제외 | `dataset/`, `models/`, `word_data/`, `runs/` 모두 `.gitignore` 처리됨 → 직접 전달 필요 |

---

## 참고 파일

| 파일 | 설명 |
|------|------|
| `fingerspelling/composer/korean_composer.py` | 두벌식 자모 조합 엔진 (프론트 JS 포팅 원본) |
| `fingerspelling/composer/word_builder.py` | Dwell 타이머 로직 (프론트 JS 포팅 원본) |
| `fingerspelling/realtime_inference.py` | 지문자 전체 파이프라인 참고 |
| `new_word/realtime_word_inference.py` | 수어 단어 전체 파이프라인 참고 |
| `new_word/ai/model_bilstm.py` | BiLSTM 모델 클래스 정의 |
| `new_word/ai/preprocess.py` | 정규화·증강 함수 (학습·추론 공통 사용) |
