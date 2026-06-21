# 한국 수어 지문자 인식 시스템

MediaPipe Hands + MLP 기반 한글 자모(지문자) 실시간 인식 및 단어 조합 프로젝트.

---

## 폴더 구조

```
fingerspelling/
├── collect_data.py          # 1단계: 데이터 수집 (웹캠)
│
├── train_classifier.py      # 2단계 (A): sklearn MLP 학습  ← 권장
├── realtime_inference.py    # 3단계 (A): sklearn 추론 + 한글 자동 조합
│
├── train.py                 # 2단계 (B): PyTorch MLP 학습
├── inference.py             # 3단계 (B): PyTorch 추론 (단순 인식)
│
├── ai/
│   ├── preprocess.py        # 랜드마크 추출 / 정규화 / 증강
│   ├── model.py             # PyTorch MLPClassifier
│   └── dataset.py           # PyTorch Dataset
│
├── composer/
│   ├── korean_composer.py   # 두벌식 오토마타 (자모 → 음절)
│   └── word_builder.py      # Dwell 타이머 입력 확정
│
├── dataset/                 # 수집 데이터 (gitignore)
│   └── <자모>/
│       └── landmarks_npy/
│           └── *.npy        # (21, 3) float32
│
└── models/                  # 학습 후 생성 (gitignore)
    ├── gesture_model.pkl      # sklearn 모델 (A)
    ├── label_encoder.pkl      # sklearn 레이블 (A)
    ├── fingerspelling_model.pt # PyTorch 모델 (B)
    ├── label2idx.pkl           # PyTorch 레이블 (B)
    └── model_config.pkl        # PyTorch 구조 (B)
```

---

## 설치

Python **3.10 / 3.11** 권장

```bash
pip install -r requirements.txt
```

GPU (선택): PyTorch CUDA 버전 별도 설치

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

---

## 사용 순서

### 1단계 — 데이터 수집

```bash
python collect_data.py
```

- 수집자 이름 입력 (영문)
- 모델의 31개 자모와 `none`을 순서대로 수집 (레이블당 100개 권장)
- `none`은 손이 없는 화면이 아니라, 손은 감지되지만 어느 자모에도 해당하지 않는 중립 손 자세를 다양하게 수집
- 이전에 중단한 경우 → 자동으로 미완료 레이블부터 재개

| 키 | 동작 |
|---|---|
| Space | 현재 프레임 저장 |
| n | 다음 레이블로 이동 |
| b | 이전 레이블로 이동 |
| q | 종료 |

저장 위치: `dataset/<자모>/landmarks_npy/<수집자>_<자모>_XXXX.npy`

---

### 2단계 (A) — sklearn 모델 학습 (권장)

```bash
python train_classifier.py
```

- `models/gesture_model.pkl`
- `models/label_encoder.pkl`

---

### 3단계 (A) — 실시간 추론 + 한글 조합 (권장)

```bash
python realtime_inference.py
```

- 자모를 **1초 유지** → 확정 및 한글 조합
- 손 없음 **2초 유지** → 공백 추가

| 키 | 동작 |
|---|---|
| b | 마지막 자모 삭제 |
| c | 전체 초기화 |
| q | 종료 |

---

### 2단계 (B) — PyTorch 모델 학습 (대안)

```bash
python train.py
```

---

### 3단계 (B) — PyTorch 추론 (대안)

```bash
python inference.py
```

---

## 인식 자모 목록

| 자음 (14개) | 모음 (17개) |
|---|---|
| ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ | ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅚ ㅛ ㅜ ㅟ ㅠ ㅡ ㅢ ㅣ |

---

## 데이터 형식

- **파일**: `(21, 3)` float32 numpy 배열
- **내용**: MediaPipe Hands 21개 랜드마크 `(x, y, z)` — 원시 정규화 좌표 (0~1)
- sklearn 시스템: flatten → (63,) 그대로 사용
- PyTorch 시스템: 손목 기준 상대 좌표 + 스케일 정규화 후 사용

---

## 주의사항

- Windows 기준 (`C:/Windows/Fonts/malgun.ttf` 폰트 사용)
- `dataset/`와 `models/`는 `.gitignore` 처리 → 각 PC에서 수집 후 학습 필요
- 팀원 데이터 병합: `dataset/<자모>/landmarks_npy/` 에 .npy 파일 복사 후 재학습
