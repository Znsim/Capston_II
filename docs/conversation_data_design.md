# 대화 데이터 구조

## 저장 정책

- `POST /api/inference`는 추론만 수행하며 DB에 자모 로그나 63차원 원시 좌표를 저장하지 않는다.
- 사용자가 전송 버튼을 누르면 `POST /api/conversations`가 완성 문장 전체를 `conversation` 테이블에 한 건 저장한다.
- 답변은 생성 시 반환된 `conversation_id`로만 조회한다. 장치의 최신 기록을 대신 조회하지 않는다.
- 새 추론 원시 좌표는 저장하지 않으므로 별도 보존 기간이 없다.
- 기존 `communication_log`와 `training_data_log`는 과거 데이터 보존을 위해 삭제하거나 변환하지 않는다.

## 상태

- `WAITING`: 역무원 답변 대기
- `COMPLETED`: 답변 등록 완료
- `CANCELLED`: 취소된 대화(답변 등록 불가)

## 마이그레이션

이번 변경은 기존 테이블을 수정하지 않고 `conversation` 테이블만 추가하는 비파괴 방식이다.

```powershell
venv\Scripts\python.exe -m app.core.migrate
```

SQLite 개발 환경에서는 서버 시작 시에도 동일한 `create_all` 방식이 실행된다. MySQL 등 운영 DB에는 배포 전에 위 명령을 한 번 실행한다.
