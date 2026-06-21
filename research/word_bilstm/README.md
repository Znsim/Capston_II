# 수어 단어 인식 연구 보관소 (BiLSTM, 운영 미사용)

> 이 디렉터리는 과거 `(T, 201)` 단어 수어 실험을 재현하기 위한 연구 자료입니다. 현재 키오스크 운영 경로는 `ai/fingerspelling/`의 63차원 지문자 MLP만 사용하며, 백엔드와 React는 이 코드·모델을 import하지 않습니다.

MediaPipe Holistic + BiLSTM 기반 한국 수어 단어 실시간 인식 프로젝트입니다.

## 인식 단어 목록 (26개)

| | | | | |
|---|---|---|---|---|
| 가다 | 감사 | 건너다 | 고장 | 공항 |
| 기차 | 내리다 | 도움 | 맞다 | 매표소 |
| 버스 | 시간 | 어디 | 엘리베이터 | 여기 |
| 역 | 오른쪽 | 왼쪽 | 잃어버리다 | 정류장 |
| 지하철 | 찾다 | 카드 | 타다 | 택시 |
| 화장실 | | | | |

---

## 폴더 구조

```
new_word/
├── collect_word_data.py      # 1단계: 데이터 수집
├── realtime_word_inference.py # 3단계: 실시간 추론
├── ai/
│   ├── train_bilstm.py       # 2단계: 모델 학습
│   ├── model_bilstm.py       # BiLSTM 모델 정의
│   ├── dataset_dynamic.py    # 데이터셋 로더
│   └── preprocess.py         # 정규화·증강 함수
├── word_data/                # 수집 데이터 저장 위치 (gitignore)
│   └── <수집자>/
│       └── <단어>/
│           └── <단어>_0000.npy  # (45, 201) float32
└── models/                   # 학습 후 생성 (gitignore)
    ├── dynamic_gesture_model.pt
    ├── model_config.pkl
    ├── label_encoder_dynamic.pkl
    └── norm_stats.pkl
```

---

## 설치

Python 3.10 권장

```bash
pip install torch torchvision mediapipe opencv-python scikit-learn joblib Pillow tensorboard
```

---

## 사용 방법

### 1단계 — 데이터 수집

```bash
python collect_word_data.py
```

- 수집자 이름 입력 (예: `홍길동_1`)
- `a` / `d` : 이전 / 다음 단어
- `SPACE` : 3초 카운트다운 후 4초 녹화
- `r` : 마지막 샘플 삭제
- `q` : 종료

> 단어당 **100개** 수집을 권장합니다.  
> 같은 이름으로 다시 실행하면 이어서 수집됩니다.

저장 위치: `word_data/<수집자>/<단어>/<단어_XXXX.npy>`

---

### 2단계 — 모델 학습

```bash
python ai/train_bilstm.py
```

| 주요 옵션 | 기본값 | 설명 |
|---|---|---|
| `--data-root` | `word_data/` | 수집 데이터 경로 |
| `--epochs` | 50 | 학습 에폭 수 |
| `--batch-size` | 32 | 배치 크기 |
| `--hidden` | 128 | LSTM 히든 크기 |

학습 완료 후 `models/` 폴더에 4개 파일이 생성됩니다.

---

### 3단계 — 실시간 추론

```bash
python realtime_word_inference.py
```

- `SPACE` : 4초 캡처 후 자동 추론
- `b` : 마지막 인식 단어 삭제
- `c` : 문장 초기화
- `q` : 종료

---

## 데이터 형식

- **형태**: `(45, 201)` float32 numpy 배열
- **특징 벡터 (201차원)**:
  - `[0:75]` — Pose 25개 랜드마크 `(x, y, visibility)`
  - `[75:138]` — 왼손 21개 랜드마크 `(x, y, 1.0)`
  - `[138:201]` — 오른손 21개 랜드마크 `(x, y, 1.0)`
- **좌표계**: 양쪽 어깨 중점 기준 상대 좌표 → 위치·거리 무관
- **시간축**: 4초 녹화 후 45프레임 균등 샘플링

---

## 모델 구조

```
입력 (B, 45, 201)
  → BiLSTM (hidden=128, layers=2, bidirectional)
  → Dropout → Linear(256→128) → ReLU → Dropout → Linear(128→N)
  → 출력 (B, N클래스)
```

---

## 주의사항

- Windows 환경에서 한국어 폰트는 `C:/Windows/Fonts/malgun.ttf` 사용
- `word_data/`와 `models/`는 `.gitignore`에 포함되어 있어 GitHub에 올라가지 않음
- 여러 PC에서 수집할 경우 수집자 이름을 다르게 설정하면 자동으로 병합됨
