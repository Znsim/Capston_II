"""Alembic 마이그레이션 실행 진입점.

실행: venv\Scripts\python.exe -m app.core.migrate
별도 환경 파일: $env:ENV_FILE='.env.production'; ...
"""

from pathlib import Path


def upgrade_database(revision: str = "head") -> None:
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        raise RuntimeError("alembic_not_installed_run_pip_install_requirements") from exc

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    command.upgrade(config, revision)


if __name__ == "__main__":
    upgrade_database()
    print("Database migrations are up to date.")
