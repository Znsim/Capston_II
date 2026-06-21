# 2·3단계 추후 테스트 가이드

이 문서는 지문자 모델 성능 검증(2단계)과 대화 데이터 구조 검증(3단계)을 나중에 다시 수행하기 위한 체크리스트다.

## 공통 준비

프로젝트 루트에서 가상환경을 활성화하거나 아래 명령처럼 가상환경의 Python을 직접 사용한다.

```powershell
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

프론트엔드는 별도 PowerShell 창에서 실행한다.

```powershell
npm.cmd start
```

- 사용자 화면: `http://localhost:3000/`
- 관리자 화면: `http://localhost:3000/admin`
- 관리자 화면에서 `.env`의 `ADMIN_PASSWORD`로 로그인한다. 비밀번호는 프론트 환경변수에 넣지 않는다.

---

## 2단계: 모델 성능 검증

### 현재 상태

- 모델 버전: `fingerspelling-mlp-2026.06.19-v2`
- 운영 신뢰도 임계값: `0.80`
- tester01의 normal 조건 평가: 전체 정확도 `96.67%`
- normal 조건 자모별 최저 정확도: `85%`
- tester01은 기존 학습 데이터 수집 참여자이므로 독립 평가자는 아니다.
- normal 조건은 완료됐지만 dim, near, far 조건과 학습에 참여하지 않은 평가자 테스트는 남아 있다.

### 합격 기준

- 조건별 전체 정확도: `95% 이상`
- 자모별 정확도: `85% 이상`
- none 정확도: `98% 이상`
- 심각하게 반복되는 혼동 자모가 없어야 한다.
- 학습 미참여자 평가가 가능해지면 동일 기준을 다시 적용한다.

### 평가 조건

| 조건 | 촬영 방법 |
|---|---|
| normal | 평소 조명과 평소 거리 |
| dim | 평소보다 어두운 조명 |
| near | 손을 카메라 가까이에 위치 |
| far | 손을 카메라에서 멀리 위치 |

좌우 손은 모두 필요하다. 각 자모는 학습 당시 의도한 손으로 표현하고, 모든 자모를 임의로 한 손으로 통일하지 않는다. 평가 결과에는 MediaPipe가 판단한 handedness가 함께 기록된다.

### 평가 실행

각 조건을 20개씩 수집한다.

```powershell
venv\Scripts\python.exe ai/fingerspelling/evaluate_live.py --evaluator tester01 --condition dim --samples-per-label 20
venv\Scripts\python.exe ai/fingerspelling/evaluate_live.py --evaluator tester01 --condition near --samples-per-label 20
venv\Scripts\python.exe ai/fingerspelling/evaluate_live.py --evaluator tester01 --condition far --samples-per-label 20
```

조작키는 다음과 같다.

- `Space`: 현재 자모 샘플 저장
- `n`: 다음 자모
- `b`: 이전 자모
- `q`: 저장 후 종료

학습에 참여하지 않은 사람이 가능해지면 평가자 이름만 바꿔 다시 실행한다.

```powershell
venv\Scripts\python.exe ai/fingerspelling/evaluate_live.py --evaluator tester02 --condition normal --samples-per-label 20
```

### 결과 위치와 확인 항목

결과는 `ai/fingerspelling/evaluation/<시간>_<평가자>_<조건>/`에 생성된다.

- `metrics.json`: 전체 및 자모별 정확도
- `confusion_matrix.csv`: 혼동행렬
- `results.csv`: 샘플별 정답, 예측, 신뢰도, 좌우 손
- 자모별 폴더: 평가 원천 좌표 파일

다음 항목을 확인한다.

- 전체 정확도가 기준 이상인지
- 자모별 정확도가 기준 미만인 항목이 있는지
- 혼동행렬에서 반복적으로 섞이는 자모가 무엇인지
- 낮은 신뢰도로 미인식된 자모가 무엇인지
- 좌우 손이 의도와 다르게 기록된 샘플이 많은지

### 통합 보고서 생성

아래의 `<...세션>` 부분을 실제 생성된 폴더명으로 바꾼다.

```powershell
venv\Scripts\python.exe ai/fingerspelling/summarize_evaluations.py --sessions <normal세션> <dim세션> <near세션> <far세션> --threshold 0.80 --model-version fingerspelling-mlp-2026.06.19-v2 --output docs/fingerspelling_model_evaluation.md --independent-evaluator no
```

tester02처럼 학습에 참여하지 않은 사람이 평가했다면 `--independent-evaluator yes`를 사용한다.

기준 미달 자모가 있으면 해당 자모와 혼동 상대만 추가 수집하고 재학습한 뒤, 모델 버전을 올려 같은 평가를 반복한다.

### 2단계 완료 체크

- [ ] dim 평가 완료
- [ ] near 평가 완료
- [ ] far 평가 완료
- [ ] 전체 정확도 확인
- [ ] 자모별 정확도 확인
- [ ] 혼동행렬 확인
- [ ] 취약 자모 재수집 여부 결정
- [ ] 가능할 때 학습 미참여자 평가
- [ ] 최종 모델 버전과 결과 보고서 저장

---

## 3단계: 대화 데이터 구조 검증

### 검증할 동작

- `/api/inference` 호출은 대화와 원시 좌표를 저장하지 않는다.
- 전송 버튼을 눌렀을 때 완성 문장 전체가 한 건만 저장된다.
- 질문 저장 응답에 `conversation_id`가 포함된다.
- 사용자는 해당 `conversation_id`의 답변만 조회한다.
- 관리자 답변 후 상태가 `WAITING`에서 `COMPLETED`로 바뀐다.
- 기존 `communication_log`와 `training_data_log`는 삭제되지 않는다.

### 사전 준비

새 DB 환경이거나 운영 DB에 아직 적용하지 않았다면 마이그레이션을 실행한다.

```powershell
venv\Scripts\python.exe -m app.core.migrate
```

테스트 전 현재 대화 건수를 기록한다.

```powershell
venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('kiosk.db'); print(c.execute('SELECT COUNT(*) FROM conversation').fetchone()[0])"
```

### 테스트 A: 추론만으로 대화가 생성되지 않는지 확인

1. 사용자 화면에서 손동작을 여러 번 인식시킨다.
2. 전송 버튼은 누르지 않는다.
3. 위 대화 건수 확인 명령을 다시 실행한다.
4. 건수가 이전과 같으면 통과다.

### 테스트 B: 문장 한 번 전송 시 정확히 한 건 생성되는지 확인

1. 사용자 화면에서 예: `화장실이 어디예요` 문장을 완성한다.
2. 전송 버튼을 한 번만 누른다.
3. 대화 건수를 다시 확인한다.
4. 건수가 정확히 `1` 증가했는지 확인한다.
5. 저장된 최신 내용을 확인한다.

```powershell
venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('kiosk.db'); print(c.execute('SELECT conversation_id, device_id, question_text, status FROM conversation ORDER BY conversation_id DESC LIMIT 1').fetchone())"
```

예상 상태는 `WAITING`이며, `question_text`에는 자모 하나가 아니라 완성 문장 전체가 있어야 한다.

### 테스트 C: 정확한 conversation_id로 답변되는지 확인

1. 사용자 화면에서 서로 다른 질문 두 개를 차례로 전송한다.
2. 관리자 화면에서 첫 번째 질문에만 답변한다.
3. 첫 번째 사용자 요청에 해당 답변이 표시되는지 확인한다.
4. 두 번째 대화는 계속 `WAITING`인지 확인한다.
5. 최신 장치 로그의 답변이 잘못 표시되지 않는지 확인한다.

### 테스트 D: 관리자 답변 상태 전환 확인

1. 관리자 화면에서 대기 문장 전체가 한 개의 채팅방으로 표시되는지 확인한다.
2. 답변을 한 번 전송한다.
3. 사용자 화면에 같은 답변이 표시되고 음성으로 읽히는지 확인한다.
4. DB에서 최신 대화 상태를 확인한다.

```powershell
venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('kiosk.db'); print(c.execute('SELECT conversation_id, question_text, staff_reply, status FROM conversation ORDER BY conversation_id DESC LIMIT 1').fetchone())"
```

예상 상태는 `COMPLETED`이며 `staff_reply`에 관리자 답변이 있어야 한다.

### 테스트 E: 원시 좌표 미저장 확인

1. 테스트 전 `training_data_log` 건수를 기록한다.
2. 손동작 인식을 여러 번 수행한다.
3. 문장도 한 번 전송한다.
4. `training_data_log` 건수가 증가하지 않았는지 확인한다.

```powershell
venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('kiosk.db'); print(c.execute('SELECT COUNT(*) FROM training_data_log').fetchone()[0])"
```

### 3단계 완료 체크

- [ ] 추론만으로 conversation이 증가하지 않음
- [ ] 문장 1회 전송으로 conversation이 정확히 1건 증가
- [ ] 저장된 `question_text`가 완성 문장 전체임
- [ ] 응답에서 `conversation_id` 반환
- [ ] 정확한 `conversation_id`만 조회
- [ ] 관리자 화면에서 문장 단위로 표시
- [ ] 답변 후 `COMPLETED` 전환
- [ ] 사용자 화면에 정확한 답변 표시 및 음성 출력
- [ ] 새 원시 좌표가 저장되지 않음
- [ ] 기존 자모 로그가 보존됨

## 최종 판정

- 2단계는 dim, near, far 및 추후 독립 평가자 테스트까지 기록한 뒤 최종 완료로 판정한다.
- 3단계는 위 A~E 테스트가 모두 통과하면 완료다.
