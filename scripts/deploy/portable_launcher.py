"""Windows portable launcher for the kiosk application."""

from __future__ import annotations

import os
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def runtime_paths() -> tuple[Path, Path]:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent, Path(sys._MEIPASS).resolve()
    project_root = Path(__file__).resolve().parents[2]
    return project_root, project_root


def ensure_runtime_config(base_dir: Path) -> Path:
    env_file = base_dir / ".env"
    (base_dir / "data").mkdir(exist_ok=True)
    (base_dir / "logs").mkdir(exist_ok=True)
    if env_file.exists():
        return env_file

    admin_password = secrets.token_urlsafe(14)
    session_secret = secrets.token_urlsafe(48)
    env_file.write_text(
        "\n".join(
            [
                "ENVIRONMENT=development",
                "APP_DEBUG=false",
                "PORT=8000",
                "BIND_HOST=127.0.0.1",
                "UVICORN_WORKERS=1",
                f"ADMIN_PASSWORD={admin_password}",
                f"SESSION_SECRET={session_secret}",
                "SESSION_TTL_SECONDS=28800",
                "SQLITE_PATH=data/kiosk.db",
                "ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000",
                "REACT_APP_KIOSK_DEVICE_ID=SEOUL_01",
                "CONFIDENCE_THRESHOLD=0.80",
                "SERVE_FRONTEND=true",
                "LOG_LEVEL=INFO",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (base_dir / "FIRST_RUN_ADMIN_PASSWORD.txt").write_text(
        "Sign Kiosk first-run administrator password\n"
        f"{admin_password}\n\n"
        "Change ADMIN_PASSWORD in .env after the external-PC test, then delete this file.\n",
        encoding="utf-8",
    )
    return env_file


def open_browser_when_ready(url: str) -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=2) as response:
                if response.status == 200:
                    webbrowser.open(url, new=1)
                    return
        except Exception:
            time.sleep(1)
    print(f"Server did not become ready. Open {url}/api/health and inspect logs/app.log.")


def main() -> None:
    base_dir, asset_root = runtime_paths()
    os.chdir(base_dir)
    env_file = ensure_runtime_config(base_dir)
    os.environ["ENV_FILE"] = str(env_file)
    os.environ["SIGNKIOSK_ASSET_DIR"] = str(asset_root / "build")
    os.environ["MODEL_PATH"] = str(asset_root / "app" / "ai" / "models" / "gesture_model.pkl")
    os.environ["LABEL_ENCODER_PATH"] = str(
        asset_root / "app" / "ai" / "models" / "label_encoder.pkl"
    )

    import uvicorn
    from app.core.config import settings
    from app.main import app

    url = f"http://localhost:{settings.PORT}"
    if os.getenv("SIGNKIOSK_NO_BROWSER") != "1":
        threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()
    print(f"Sign Kiosk is starting at {url}")
    print("Keep this window open. Press Ctrl+C to stop the kiosk server.")
    uvicorn.run(
        app,
        host=settings.BIND_HOST,
        port=settings.PORT,
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()
