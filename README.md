# 캡스톤디자인 II — 한국 수어 인식 키오스크

청각장애인이 수어(지문자 + 단어)로 질문을 입력하면 역무원이 텍스트로 답변하는 양방향 커뮤니케이션 키오스크 시스템입니다.

---

## 목차

1. [시스템 개요](#시스템-개요)
2. [디렉토리 구조](#디렉토리-구조)
3. [기술 스택](#기술-스택)
4. [모듈별 설명](#모듈별-설명)
5. [설치 및 실행](#설치-및-실행)
6. [API 명세](#api-명세)
7. [개발 현황](#개발-현황)
8. [주의사항](#주의사항)

---

## 시스템 개요

```
[키오스크 웹캠]
      │
      ▼ MediaPipe 손 랜드마크 추출 (프론트)
      │
      ├─► 지문자 모드: MLPClassifier → 자모 → KoreanComposer → 한글 단어
      └─► 수어단어 모드: BiLSTM → 단어(교통 도메인 26개)
      │
      ▼ POST /api/inference (백엔드)
      │
      ├─► DB 저장 (Communication_Log, Training_Data_Log)
      │
      ├─► [키오스크 화면] 완성 문장 표시 + 역무원 답변 폴링
      └─► [역무원 화면] 대기 질문 목록 확인 + 답변 입력
```

---

## 디렉토리 구조

```
cap2_git/
├── ai/
│   ├── fingerspelling/          # 지문자(한글 자모) 인식
│   │   ├── collect_data.py      # 웹캠으로 자모 데이터 수집
│   │   ├── train_classifier.py  # sklearn MLP 모델 학습 (권장)
│   │   ├── train.py             # PyTorch MLP 학습 (대안)
│   │   ├── realtime_inference.py # 실시간 추론 + 한글 자동 조합
│   │   ├── inference.py         # PyTorch 추론
│   │   ├── ai/
│   │   │   ├── model.py         # PyTorch MLP 클래스
│   │   │   ├── preprocess.py    # 랜드마크 정규화·증강
│   │   │   └── dataset.py       # PyTorch Dataset
│   │   ├── composer/
│   │   │   ├── korean_composer.py  # 두벌식 오토마타 (자모→음절)
│   │   │   └── word_builder.py     # Dwell 타이머 (입력 확정 로직)
│   │   ├── dataset/             # 수집 데이터 (.gitignore)
│   │   └── models/              # 학습 완료 모델 (.gitignore)
│   │
│   └── new_word/                # 수어 단어 인식 (교통 도메인 26개)
│       ├── collect_word_data.py # 웹캠으로 단어 시퀀스 수집
│       ├── realtime_word_inference.py # 실시간 추론
│       ├── ai/
│       │   ├── train_bilstm.py  # BiLSTM 모델 학습
│       │   ├── model_bilstm.py  # BiLSTM 아키텍처
│       │   ├── dataset_dynamic.py # PyTorch 데이터셋
│       │   └── preprocess.py    # 정규화·증강
│       ├── word_data/           # 수집 데이터 (.gitignore)
│       └── models/              # 학습 모델 (.gitignore)
│
├── back/                        # 백엔드 (FastAPI) — 개발 중
├── front/                       # 프론트엔드 — 개발 중
├── docs/
│   ├── AI_개발_가이드.md
│   ├── 백엔드_개발_가이드.md
│   └── 프론트엔드_개발_가이드.md
└── requirements.txt
```

---

## 기술 스택

### AI (Python)
| 기술 | 용도 |
|------|------|
| MediaPipe 0.10.x | 손/신체 랜드마크 추출 |
| scikit-learn 1.7.2 | 지문자 분류 (MLPClassifier) |
| PyTorch | 수어 단어 분류 (BiLSTM) |
| OpenCV | 웹캠 영상 처리 |
| Pillow | 한글 폰트 렌더링 |
| TensorBoard | 학습 모니터링 |

### 백엔드 (구현 예정)
| 기술 | 용도 |
|------|------|
| FastAPI + Uvicorn | REST API 서버 |
| SQLAlchemy | ORM |
| MySQL / SQLite | 데이터베이스 |

### 프론트엔드 (구현 예정)
| 기술 | 용도 |
|------|------|
| MediaPipe Hands (JS) | 브라우저 손 랜드마크 추출 |
| KoreanComposer (JS 포팅) | 자모→한글 음절 조합 |
| Dwell 타이머 (JS 포팅) | 입력 확정 로직 |

---

## 모듈별 설명

### 지문자 인식 (`ai/fingerspelling/`)

한글 자모 32개(ㄱ~ㅎ, ㅏ~ㅣ) + none 클래스를 분류합니다.

- **입력**: MediaPipe Hands 21개 랜드마크 × (x, y, z) = 63차원
- **모델**: sklearn MLPClassifier `[256 → 128 → 64 → 32]`
- **임계값**: confidence ≥ 0.75 이상만 인식 처리
- **저장 파일**: `models/gesture_model.pkl`, `models/label_encoder.pkl`

**한글 조합 흐름**:
```
자모 인식 → Dwell 타이머(1초 유지) → KoreanComposer → 음절/단어
예: ㅅ → ㅏ → ㄱ → ㅗ → ㅏ  ═══► "사과"
```

### 수어 단어 인식 (`ai/new_word/`)

교통 도메인 수어 단어 26개를 인식합니다 (가다, 감사, 건너다 ... 화장실).

- **입력**: MediaPipe Holistic 시퀀스 `(45프레임, 201차원)`
  - Pose 25개 × (x, y, visibility) + 양손 각 21개 × (x, y)
  - 어깨 중점 기준 상대 좌표 (키오스크 위치 무관)
- **모델**: BiLSTM `(201 → 256 → 128 → 26)`
- **임계값**: confidence ≥ 0.6
- **저장 파일**: `models/dynamic_gesture_model.pt`, `norm_stats.pkl`

### 한글 자모 조합 엔진 (`ai/fingerspelling/composer/`)

두벌식 오토마타 기반으로 자모 시퀀스를 완성형 한글로 조합합니다.

- 쌍자음 지원: ㄱ+ㄱ=ㄲ
- 복합 모음: ㅗ+ㅏ=ㅘ
- 복합 종성: ㄹ+ㄱ=ㄺ
- 받침 이동: 한+ㅡ → 하느

> 프론트엔드 구현 시 `korean_composer.py`를 JavaScript로 포팅해야 합니다.

---

## 설치 및 실행

### 공통 의존성 설치

```bash
python -m pip install -r requirements.txt
```

> `pip` 명령이 차단된 환경이라면 `python -m pip` 를 사용하세요.

### 지문자 데이터 수집

```bash
python ai/fingerspelling/collect_data.py
```

자모당 30개 이상 수집을 권장합니다.

### 지문자 모델 학습

```bash
python ai/fingerspelling/train_classifier.py
```

### 지문자 실시간 추론 데모

```bash
python ai/fingerspelling/realtime_inference.py
```

조작: `b` 지우기 | `c` 초기화 | `q` 종료

### 수어 단어 데이터 수집

```bash
python ai/new_word/collect_word_data.py
```

단어당 100개 이상 수집을 권장합니다.

### 수어 단어 모델 학습

```bash
python ai/new_word/ai/train_bilstm.py
```

### 수어 단어 실시간 추론 데모

```bash
python ai/new_word/realtime_word_inference.py
```

---

## API 명세

| 엔드포인트 | 메서드 | 역할 |
|-----------|--------|------|
| `/api/inference` | POST | 손 랜드마크 수신 → AI 추론 → DB 저장 |
| `/api/poll/answer` | GET | 역무원 답변 상태 확인 (1초마다 폴링) |
| `/api/staff/list` | GET | 역무원: 대기 중인 질문 목록 조회 |
| `/api/staff/reply` | POST | 역무원: 답변 등록 |

자세한 요청/응답 스펙은 `docs/백엔드_개발_가이드.md` 참조.

---

## 개발 현황

| 모듈 | 상태 |
|------|------|
| 지문자 인식 AI | 완료 |
| 수어 단어 인식 AI | 완료 |
| 한글 자모 조합 엔진 (Python) | 완료 |
| 백엔드 (FastAPI) | 개발 중 |
| 프론트엔드 (키오스크 화면) | 개발 중 |
| 프론트엔드 (역무원 화면) | 개발 중 |
| KoreanComposer JS 포팅 | 예정 |
| 전체 통합 테스트 | 예정 |

---

## 주의사항

- **scikit-learn 버전 고정**: 반드시 `1.7.2` 사용 (버전 불일치 시 모델 로드 실패)
- **모델 파일 Git 제외**: `dataset/`, `models/`, `word_data/`, `runs/` 는 `.gitignore` 처리 — 팀원 간 직접 전달 필요
- **모델 서버 시작 시 1회 로드**: 요청마다 로드하면 응답 지연 발생
- **수어 단어 정규화 필수**: 추론 전 반드시 `norm_stats.pkl`의 mean·std 적용
- **HTTPS 필수**: 브라우저 웹캠 접근은 HTTPS 또는 localhost 환경에서만 가능
- **CORS 설정**: 프론트 → 백엔드 API 호출 가능하도록 백엔드에서 CORS 허용 필요
