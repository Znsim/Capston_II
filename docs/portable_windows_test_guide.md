# Sign Kiosk Windows 포터블 테스트

## 실행

1. `SignKiosk-windows-x64.zip`을 영문 경로에 압축 해제한다.
2. Chrome 또는 Edge가 설치되어 있는지 확인한다.
3. `SignKiosk.exe`를 실행한다. Windows 경고가 나오면 파일 출처를 확인한 뒤 실행을 허용한다.
4. 첫 실행이 끝나면 브라우저가 `http://localhost:8000`을 연다.
5. 관리자 비밀번호는 첫 실행 폴더의 `FIRST_RUN_ADMIN_PASSWORD.txt`에서 확인한다.

실행 창을 닫으면 서버가 종료된다. 다음 실행부터는 같은 `.env`와 `data/kiosk.db`를 사용한다.

## 외부 PC 확인 항목

- `/api/health`에서 DB와 AI가 준비 상태인지 확인
- 카메라 권한 허용 후 한 손 지문자 인식 확인
- 장치 옆 `설정`에서 관리자 인증, 장치 등록·수정·선택 확인
- `/admin`에서 질문과 장치 정보 확인 및 답변 전송
- 답변 표시와 음성 출력 확인

## 보안 및 데이터

- 외부 테스트가 끝나면 `.env`의 `ADMIN_PASSWORD`를 새 값으로 변경한다.
- 비밀번호 변경 후 `FIRST_RUN_ADMIN_PASSWORD.txt`는 사용자가 직접 안전하게 제거한다.
- 질문 DB는 `data/kiosk.db`, 로그는 `logs/`에 저장된다.
- 모델 해시는 `MODEL_SHA256.txt`에서 확인한다.
- 이 포터블 패키지는 같은 PC의 `localhost` 테스트용이다. 다른 PC에서 네트워크로 접속하려면 HTTPS 배포 구성이 필요하다.
