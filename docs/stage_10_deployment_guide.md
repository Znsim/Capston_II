# 10단계 배포 가이드

## 결정된 기본 운영 구조

```text
Chrome/Edge 키오스크 모드
        │ HTTPS 443
        ▼
      Caddy ── /, /admin, 정적 파일 → build/
        └───── /api/* → Uvicorn 127.0.0.1:8000
                              │
                       SQLite data/kiosk.db
                       운영 MLP 모델 2개
```

한 장비에서 운영하는 현재 단계는 SQLite와 Uvicorn worker 1개를 사용한다. 여러 키오스크가 중앙 서버를 공유하거나 백엔드 worker를 늘려야 할 때 MySQL로 전환한다.

## 1. 운영 파일 준비

```powershell
Copy-Item .env.production.example .env.production
```

다음 값을 실제 환경에 맞게 변경한다.

- `ADMIN_PASSWORD`: 12자 이상
- `SESSION_SECRET`: 32자 이상 무작위 값
- `ALLOWED_ORIGINS`: 실제 Caddy HTTPS 주소
- `REACT_APP_KIOSK_DEVICE_ID`: 설치 장비 ID
- `SQLITE_PATH=data/kiosk.db`

승인된 모델 두 파일을 `deployment/models/`에 넣는다. 파일 해시는 `deployment/model_manifest.json`과 일치해야 한다.

```text
deployment/models/gesture_model.pkl
deployment/models/label_encoder.pkl
```

준비 명령은 의존성, 기존 `kiosk.db`의 `data/kiosk.db` 최초 이관, 모델 검증·배치, lint, 테스트, React 빌드, DB 마이그레이션을 순서대로 수행한다. 자리표시자 비밀번호나 `example.com` 주소가 남아 있으면 준비 단계가 중단된다. 이미 `data/kiosk.db`가 있으면 덮어쓰지 않는다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/deploy/prepare_release.ps1
```

## 2. HTTPS 선택

### 공인 도메인 권장

1. 실제 도메인의 DNS를 장비 또는 서버 IP로 연결한다.
2. 방화벽에서 80·443 포트를 허용한다.
3. 공식 Caddy Windows 실행 파일을 `deployment/bin/caddy.exe`에 둔다.
4. `.env.production`과 실행 인자의 `kiosk.example.com`을 실제 도메인으로 바꾼다.

Caddy가 공인 인증서를 자동 발급·갱신한다.

### 폐쇄망

`deployment/Caddyfile.local.example`의 `tls internal` 구성을 사용한다. 장비에서 `kiosk.local`이 127.0.0.1 또는 서버 IP로 해석되게 hosts/DNS를 설정하고, Caddy 내부 CA 루트 인증서를 해당 Windows 신뢰 저장소에 등록해야 카메라·마이크 권한이 정상 동작한다.

## 3. 수동 실행 확인

PowerShell 1:

```powershell
scripts\deploy\run_backend.ps1
```

PowerShell 2:

```powershell
scripts\deploy\run_caddy.ps1 -Site https://kiosk.example.com
```

폐쇄망은 다음처럼 실행한다.

```powershell
scripts\deploy\run_caddy.ps1 -Site https://kiosk.local -Config deployment\Caddyfile.local.example
```

검증:

```powershell
scripts\deploy\smoke_test.ps1 -BaseUrl https://kiosk.example.com
```

## 4. 자동 시작과 장애 복구

관리자 PowerShell에서 실행한다.

```powershell
scripts\deploy\install_startup_tasks.ps1 -Site https://kiosk.example.com
```

등록되는 작업:

- `SignKiosk-Backend`: 부팅 시 Uvicorn 시작, 실패 시 1분 후 재시작
- `SignKiosk-Caddy`: 부팅 시 HTTPS 프록시 시작, 실패 시 재시작
- `SignKiosk-Browser`: 사용자 로그인 시 전체 화면 브라우저 시작
- `SignKiosk-DatabaseBackup`: 매일 02:00 SQLite 온라인 백업

MySQL을 선택했다면 `-DatabaseMode MySQL`을 추가해 SQLite 백업 작업 등록을 건너뛴다.

등록 후 Windows 작업 스케줄러에서 각 작업을 한 번 수동 실행하고 최근 실행 결과가 `0x0`인지 확인한다.

## 5. DB 정책과 백업

### SQLite

- 장비 한 대, 백엔드 worker 1개만 허용한다.
- 외래키, WAL, 5초 busy timeout을 서버 연결 시 자동 적용한다.
- 매일 온라인 백업하고 30일 보존한다.
- `backups/*.db`와 `.sha256`을 매일 다른 디스크나 암호화된 원격 저장소로 복제한다.
- 월 1회 복구 연습으로 백업 DB의 테이블과 최근 대화를 확인한다.

수동 백업:

```powershell
venv\Scripts\python.exe scripts\deploy\backup_sqlite.py --database data\kiosk.db --output backups --retention-days 30
```

### MySQL 전환 조건

- 여러 PC가 한 중앙 DB를 사용함
- Uvicorn worker 2개 이상 또는 서버 인스턴스 여러 개가 필요함
- 중앙 백업·복제·장애조치가 필요함

MySQL에서는 `.env.production`의 `DB_*`를 활성화하고 배포 전 Alembic을 한 번 실행한다. 백업은 `mysqldump --single-transaction` 일 1회와 binlog 시점 복구 정책을 사용하며, 백업 파일은 DB 서버 밖에 보관한다.

## 6. 전체 화면과 장치 점검

전체 화면 수동 실행:

```powershell
scripts\deploy\start_kiosk.ps1 -Url https://kiosk.example.com/
```

장치 진단 페이지:

```text
https://kiosk.example.com/hardware-check.html
```

여기서 카메라 영상, 마이크 레벨, 한국어 시험 음성을 각각 확인한다. 이후 실제 `/` 화면에서 좌우 손 지문자 입력, 문장 전송, `/admin` 답변, 해당 키오스크의 음성 출력까지 한 번 완주한다.

## 현장에서 반드시 결정할 값

- [ ] 공인 도메인 또는 폐쇄망 내부 인증서 방식
- [ ] 실제 `REACT_APP_KIOSK_DEVICE_ID`
- [ ] SQLite 백업을 복제할 별도 저장소
- [ ] Chrome 또는 Edge 카메라·마이크 영구 허용 정책
- [ ] 스피커 기본 출력 장치와 볼륨

## 완료 기준

- [ ] `npm.cmd run lint`, `npm.cmd run test:all`, `npm.cmd run build` 통과
- [ ] 모델 배치 스크립트의 SHA·63차원·32클래스 검증 통과
- [ ] HTTPS에서 `/api/health`가 준비 상태 반환
- [ ] 재부팅 후 백엔드·Caddy·전체 화면이 자동 시작
- [ ] 프로세스 강제 종료 후 1분 내 자동 복구
- [ ] 백업 생성 및 별도 위치 복제·복구 확인
- [ ] 실제 카메라·마이크·스피커 테스트 통과
