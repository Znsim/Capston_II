# API 명세

기본 주소는 `http://127.0.0.1:8000/api`이며 모든 오류 응답에는 가능한 경우 `X-Request-ID` 헤더가 포함됩니다. 실제 OpenAPI 화면은 서버 실행 후 `/docs`에서 확인할 수 있습니다.

## 시스템

### `GET /api/health`

DB 연결과 AI 모델 적재 상태를 확인합니다. 둘 다 준비되면 `200`, 하나라도 준비되지 않으면 `503`입니다.

```json
{"database":"connected","ai_model":"loaded","all_systems_ready":true,"timestamp":"2026-06-20T00:00:00+00:00"}
```

## 키오스크

### `POST /api/inference`

63개 원시 손 랜드마크 좌표로 자모를 추론합니다. DB에는 저장하지 않습니다.

```json
{"device_id":"SEOUL_01","keypoints":[0.0, "... 총 63개"]}
```

응답:

```json
{"recognized_word":"ㄱ","confidence":0.99}
```

모델 미적재 시 `503`, 길이·유한값 검증 실패 시 `422`입니다.

### `POST /api/conversations`

완성 문장 전체를 한 건 생성합니다.

```json
{"device_id":"SEOUL_01","question_text":"화장실이 어디예요?"}
```

성공 `201`:

```json
{"conversation_id":42,"status":"WAITING"}
```

### `GET /api/conversations/{conversation_id}?device_id=SEOUL_01`

지정한 장치와 대화 ID가 모두 일치하는 답변만 조회합니다.

```json
{"conversation_id":42,"status":"COMPLETED","staff_reply":"오른쪽에 있습니다."}
```

상태는 `WAITING`, `COMPLETED`, `CANCELLED` 중 하나입니다.

## 역무원 인증

### `POST /api/auth/login`

```json
{"password":"관리자 비밀번호"}
```

성공하면 `/api` 경로에 적용되는 HttpOnly 세션 쿠키가 설정됩니다.

### `GET /api/auth/me`

현재 세션이 유효하면 `{"authenticated":true}`를 반환합니다.

### `POST /api/auth/logout`

세션 쿠키를 제거합니다.

## 역무원

아래 API는 로그인 세션이 필요합니다.

### `GET /api/staff/list?page=1&limit=20`

`WAITING` 질문을 오래된 순서로 페이지 조회합니다. 각 항목에는 `conversation_id`, `device_id`, `station_name`, `location`, `question_text`, `status`, `created_at`이 포함됩니다.

### `POST /api/staff/reply`

```json
{"conversation_id":42,"reply":"오른쪽에 있습니다."}
```

한 번 완료된 대화에 다시 답하면 `400`, 취소된 대화는 `400`, 존재하지 않으면 `404`입니다.

## 공통 제한

- 장치 ID 형식: 영문 대문자와 밑줄·숫자 조합(예: `SEOUL_01`)
- 질문·답변: 공백 제외 1~500자
- 요청 본문: 기본 1 MiB 이하
- 운영 CORS: `.env`에 명시한 HTTPS Origin만 허용
