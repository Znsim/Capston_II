# 6단계 인증·보안 및 배포 가이드

## 관리자 인증

역무원 화면은 프론트 API 키 대신 서버가 서명한 세션 쿠키를 사용한다.

- 로그인: `POST /api/auth/login`
- 로그인 확인: `GET /api/auth/me`
- 로그아웃: `POST /api/auth/logout`
- 쿠키: `HttpOnly`, `SameSite=Strict`, 운영 환경에서 `Secure`
- 기본 세션 만료: 8시간

브라우저 JavaScript에서는 세션 쿠키 값을 읽을 수 없다. 관리자 API는 유효한 세션 쿠키가 없으면 `401`을 반환한다.

## 필수 운영 환경변수

운영 비밀값은 `.env`를 서버에 복사하기보다 배포 플랫폼의 Secret Manager, Docker Secret 또는 OS 서비스 환경변수로 주입한다.

```dotenv
ENVIRONMENT=production
ADMIN_PASSWORD=<12자 이상의 강한 비밀번호>
SESSION_SECRET=<32자 이상의 무작위 문자열>
ALLOWED_ORIGINS=https://kiosk.example.com
REACT_APP_KIOSK_DEVICE_ID=SEOUL_01
```

무작위 세션 비밀값 생성 예시:

```powershell
venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

운영 모드에서는 관리자 비밀번호, 세션 비밀값, HTTPS CORS origin이 올바르지 않으면 서버 시작이 거부된다.

## CORS와 HTTPS

- 운영 CORS에는 실제 HTTPS 프론트 주소만 지정한다.
- `*` 와일드카드는 운영 환경에서 허용되지 않는다.
- 운영 모드에서는 HTTP 요청을 HTTPS로 리다이렉트하고 HSTS 헤더를 추가한다.
- TLS 인증서와 종료 처리는 Nginx, Caddy, 클라우드 로드밸런서 같은 리버스 프록시에서 담당한다.
- 프록시는 원래 요청 스킴을 백엔드에 전달해야 하며 Uvicorn은 신뢰하는 프록시의 forwarded header만 허용해야 한다.

Uvicorn 실행 예시:

```powershell
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
```

## 요청 제한

- 요청 본문: 최대 1MB
- 관리자 로그인: IP당 10회/분
- AI 추론: IP당 300회/분
- 질문 생성: IP당 30회/분
- 역무원 API: IP당 120회/분

현재 빈도 제한은 단일 서버 프로세스 메모리를 사용한다. 여러 worker나 서버 인스턴스로 확장할 때는 Redis 기반 공용 제한기로 교체한다.

## 입력값과 로그

- 손 좌표는 정확히 63개이며 NaN·Infinity를 거부한다.
- 질문과 답변은 공백 입력을 거부하고 최대 500자로 제한한다.
- 관리자 비밀번호는 최대 200자로 제한한다.
- 로그 필터는 password, token, secret, session, cookie, authorization 값을 마스킹한다.
- 질문 본문, 답변 본문, 원시 손 좌표와 인증정보는 애플리케이션 로그에 기록하지 않는다.

## `.env`와 모델 배포

- `.env`, 운영 모델, DB, 로그와 `node_modules`는 Git에 커밋하지 않는다.
- `.env.example`에는 변수 이름과 가짜 값만 유지한다.
- 모델은 승인된 아티팩트 저장소나 배포 패키지에서 `app/ai/models/`로 전달한다.
- 배포 전에 모델과 label encoder의 버전 및 SHA-256을 평가 보고서와 대조한다.

```powershell
Get-FileHash app/ai/models/gesture_model.pkl -Algorithm SHA256
Get-FileHash app/ai/models/label_encoder.pkl -Algorithm SHA256
```

모델 파일을 바꾼 뒤 서버를 재시작하고 시작 로그의 모델·라벨 매핑 검증 성공을 확인한다.

## 완료 체크

- [ ] 프론트 번들에 관리자 API 키가 없음
- [ ] 로그인 전 역무원 API가 401을 반환함
- [ ] 로그인 후 대기 목록과 답변 API가 동작함
- [ ] 로그아웃 후 세션이 폐기됨
- [ ] 운영 CORS가 실제 HTTPS origin으로 제한됨
- [ ] HTTPS 인증서와 리버스 프록시 적용됨
- [ ] 413 요청 크기 제한과 429 빈도 제한 확인
- [ ] 민감정보가 로그에 남지 않음
- [ ] `.env`와 모델이 Git 추적 대상이 아님
