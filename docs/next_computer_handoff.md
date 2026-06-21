# 새 컴퓨터 작업 인수인계

이 문서는 다른 컴퓨터에서 현재 프로젝트를 이어서 진행하기 위한 체크리스트다.

## Git 정보

- 저장소: `https://github.com/Znsim/Capston_II.git`
- 작업 브랜치: `handoff/kiosk-integration-20260621`
- 운영 모델 버전: `fingerspelling-mlp-2026.06.19-v2`
- 신뢰도 임계값: `0.80`

## 현재 판정

### 코드와 자동 검증이 완료된 부분

- 학습·Python·React의 63차원 지문자 입력 좌표계 통일
- 한 손, 감지 `0.7`, 추적 `0.5`, 좌우 반전 조건 통일
- `label_encoder` 직접 사용 및 32개 DB 라벨 시작 시 검증
- 추론과 문장 대화 저장 분리
- `conversation_id` 기반 정확한 답변 폴링
- 키오스크·역무원 화면의 오류 및 중복 요청 처리
- 관리자 세션 인증, CORS, 요청 크기·빈도 제한
- DB·모델 상태가 포함된 헬스 체크
- Alembic DB 마이그레이션
- React 테스트 25개와 Python 테스트 8개
- BiLSTM 단어 모델을 `research/word_bilstm/`으로 분리
- React 프로덕션 빌드 및 Windows 배포 스크립트

### 실시간 또는 현장 검증이 남은 부분

- Python 데모와 웹의 동일 동작 최종 회귀 확인
- dim, near, far 조건 평가
- 가능할 때 학습 미참여자 평가
- 실제 카메라 권한 거부·미연결 테스트
- 실제 마이크 음성 입력과 스피커 답변 출력
- 두 브라우저 또는 두 장치에서 다중 키오스크 전체 흐름
- Caddy 설치와 실제 HTTPS 인증서 적용
- 자동 시작 작업 등록 후 재부팅·장애 복구 확인
- SQLite 백업의 외부 저장소 복제와 복구 연습

현재 모델 평가 보고서는 normal 조건 660개에서 전체 정확도 `96.67%`, 임계값 이상 결과 정확도 `98.14%`다. tester01은 학습 데이터 수집 참여자이므로 최종 독립 평가 결과는 아니다.

## Git에 포함되지 않는 필수 파일

보안과 용량 문제로 다음 파일은 GitHub에 올라가지 않는다. 기존 컴퓨터에서 USB 또는 승인된 저장소로 별도 복사한다.

```text
app/ai/models/gesture_model.pkl
app/ai/models/label_encoder.pkl
ai/fingerspelling/dataset/       # 재학습할 경우 필요
kiosk.db                         # 기존 로그를 이어갈 경우 필요
.env                             # 비밀값이 있으므로 직접 복사보다 새로 작성 권장
```

모델 파일의 SHA-256:

```text
gesture_model.pkl
75a8bf05864297676048f50963a0a5aaff036cabe4ab31c9cf56fe2a732b6067

label_encoder.pkl
9bf71b1c50c14fb0691b81e23408517a936d404b6fd2e8825764009ea5361ab5
```

## 새 컴퓨터 설치

```powershell
git clone https://github.com/Znsim/Capston_II.git
cd Capston_II
git switch handoff/kiosk-integration-20260621

python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd ci
Copy-Item .env.development.example .env
```

`.env`에서 최소한 다음 값을 변경한다.

```dotenv
ADMIN_PASSWORD=<개발용 관리자 비밀번호>
SESSION_SECRET=<32자 이상 무작위 문자열>
REACT_APP_KIOSK_DEVICE_ID=SEOUL_01
```

모델 두 파일을 `app/ai/models/`에 배치하고 다음 명령으로 확인한다.

```powershell
Get-FileHash app/ai/models/gesture_model.pkl -Algorithm SHA256
Get-FileHash app/ai/models/label_encoder.pkl -Algorithm SHA256
venv\Scripts\python.exe -m app.core.migrate
npm.cmd run lint
npm.cmd run test:all
npm.cmd run build
```

## 개발 실행

PowerShell 1:

```powershell
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

PowerShell 2:

```powershell
npm.cmd start
```

- 키오스크: `http://localhost:3000/`
- 역무원: `http://localhost:3000/admin`
- API 문서: `http://127.0.0.1:8000/docs`
- 헬스 체크: `http://127.0.0.1:8000/api/health`

## 다음 작업 권장 순서

1. normal 조건에서 Python 데모와 웹이 같은 자모를 출력하는지 확인
2. `dim`, `near`, `far` 평가를 각각 20개씩 수집
3. 키오스크에서 문장 생성·전송 후 역무원 답변과 음성 출력을 확인
4. 카메라·마이크·스피커를 `/hardware-check.html`에서 확인
5. 실제 도메인 또는 `kiosk.local` 인증서 방식을 결정
6. `docs/stage_10_deployment_guide.md`에 따라 Caddy와 자동 시작 적용
7. 가능해지는 즉시 학습 미참여자 평가 수행

평가 명령과 합격 기준은 `docs/stage_2_3_test_guide.md`, 화면 테스트는 `docs/stage_4_kiosk_test_guide.md`, 배포는 `docs/stage_10_deployment_guide.md`를 따른다.

## 완료 기준

- normal/dim/near/far 조건별 전체 정확도 95% 이상
- 자모별 정확도 85% 이상
- `none` 정확도 98% 이상
- 전체 문장이 대화 한 건으로 저장되고 정확한 장치에만 답변됨
- HTTPS 환경에서 카메라·마이크·스피커 동작
- 재부팅과 프로세스 장애 후 서비스 자동 복구
- DB 백업 생성 및 복구 확인
