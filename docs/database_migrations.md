# DB 마이그레이션 운영 절차

DB 스키마 변경은 SQLAlchemy `create_all`이 아니라 Alembic 리비전으로 관리합니다.

## 적용

개발 환경:

```powershell
venv\Scripts\python.exe -m app.core.migrate
```

운영 환경 파일을 명시하는 경우:

```powershell
$env:ENV_FILE=".env.production"
venv\Scripts\python.exe -m app.core.migrate
```

서버 시작 시 SQLite 개발 환경은 같은 `upgrade head`를 자동 수행합니다. MySQL 운영 배포에서는 애플리케이션을 올리기 전에 별도 배포 단계에서 위 명령을 먼저 실행합니다.

## 스키마 변경 생성

1. `app/model/db_model.py`를 수정합니다.
2. 개발 DB를 백업합니다.
3. 리비전을 생성하고 생성된 파일을 직접 검토합니다.

```powershell
venv\Scripts\alembic.exe revision --autogenerate -m "변경 내용"
venv\Scripts\python.exe -m app.core.migrate
```

4. `npm.cmd run test:all`과 `npm.cmd run lint`를 통과시킵니다.
5. 리비전 파일을 코드와 함께 커밋합니다.

## 최초 리비전

`20260620_01`은 현재 운영 스키마의 기준점입니다. 기존 `communication_log`와 `training_data_log`가 있는 DB에서는 테이블을 덮어쓰지 않고 `alembic_version`만 추가하며, 없는 테이블만 생성합니다.

## 롤백 주의

최초 리비전의 downgrade는 모든 앱 테이블을 삭제하므로 운영 DB에서는 실행하지 않습니다. 이후 리비전도 운영 롤백 전에 반드시 DB 백업과 데이터 변환의 역방향 가능성을 확인합니다.
