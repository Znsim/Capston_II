# 한국 수어 지문자 키오스크

웹캠에서 MediaPipe Hands 랜드마크를 추출하고 지문자 MLP 모델로 한글 자모를 인식해 문장을 만든 뒤, 역무원에게 질문하고 답변을 받는 키오스크입니다.

현재 운영 범위는 **정적 지문자 32클래스(`none` 포함)**입니다. 과거 BiLSTM 단어 인식 실험은 운영 코드와 분리해 `research/word_bilstm/`에 보존합니다.

## 구성

```text
cap2_git/
├─ app/                     FastAPI API, 인증, DB, AI 추론
├─ src/                     React 키오스크·역무원 화면
├─ ai/fingerspelling/       데이터 수집·MLP 학습·실시간 평가
├─ app/ai/models/           운영 모델(배포 시 별도 제공)
├─ migrations/              Alembic DB 버전 이력
├─ research/word_bilstm/    운영 미사용 BiLSTM 연구 코드·데이터
├─ tests/                   Python 모델 계약·API 통합 테스트
└─ docs/                    API, 모델 카드, 단계별 테스트·배포 문서
```

## 요구 환경

- Python 3.10
- Node.js 및 npm
- SQLite(기본) 또는 MySQL
- Chrome 계열 브라우저와 웹캠

## 설치

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd install
Copy-Item .env.development.example .env
```

`ADMIN_PASSWORD`, `SESSION_SECRET`, `REACT_APP_KIOSK_DEVICE_ID`를 환경에 맞게 변경합니다. 운영 모델 두 파일을 다음 위치에 배치합니다.

```text
app/ai/models/gesture_model.pkl
app/ai/models/label_encoder.pkl
```

## DB 준비 및 실행

```powershell
venv\Scripts\python.exe -m app.core.migrate
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

다른 PowerShell 창에서 프론트를 실행합니다.

```powershell
npm.cmd start
```

- 키오스크: `http://localhost:3000/`
- 역무원: `http://localhost:3000/admin`
- API 문서: `http://127.0.0.1:8000/docs`

## 테스트

```powershell
npm.cmd run test:all
npm.cmd run lint
npm.cmd run build
```

실제 웹캠 테스트는 [8단계 테스트 가이드](docs/stage_8_test_guide.md)를 따릅니다.

## 핵심 동작

- 프론트와 Python 데모 모두 `(21, 3)` 원시 랜드마크를 펼친 63차원을 사용합니다.
- 신뢰도 `0.80` 이상만 입력에 반영합니다.
- `/api/inference`는 추론만 하며 대화를 저장하지 않습니다.
- 완성 문장은 `/api/conversations`로 한 번 저장하고 반환된 `conversation_id`로 답변을 폴링합니다.
- 역무원 API는 HttpOnly 세션 쿠키 인증을 사용합니다.

## 문서

- [API 명세](docs/api_reference.md)
- [운영 모델 카드](docs/model_card_fingerspelling.md)
- [DB 마이그레이션 절차](docs/database_migrations.md)
- [운영 배포 가이드](docs/stage_10_deployment_guide.md)
- [새 컴퓨터 작업 인수인계](docs/next_computer_handoff.md)
- [보안·배포 설정](docs/stage_6_security_deployment.md)
- [2·3단계 테스트](docs/stage_2_3_test_guide.md)
- [4단계 키오스크 테스트](docs/stage_4_kiosk_test_guide.md)

## 운영 주의사항

- `.env`, DB, 로그, 데이터셋, 모델 파일은 Git에 커밋하지 않습니다.
- 운영은 `.env.production.example`을 기준으로 HTTPS와 정확한 CORS Origin을 설정합니다.
- 모델 카드의 평가는 현재 학습 참여자 기준 normal 조건만 완료된 상태입니다. dim/near/far와 독립 평가자 결과가 추가되기 전에는 최종 검증 완료로 간주하지 않습니다.
