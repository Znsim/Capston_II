"""SQLite online backup with SHA-256 sidecar and retention cleanup."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/kiosk.db"))
    parser.add_argument("--output", type=Path, default=Path("backups"))
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args()

    if args.retention_days < 1:
        raise ValueError("retention_days_must_be_positive")
    if not args.database.is_file():
        raise FileNotFoundError(f"database_not_found: {args.database}")

    args.output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = args.output / f"kiosk_{timestamp}.db"
    source_connection = sqlite3.connect(args.database)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".db.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    for backup in args.output.glob("kiosk_*.db"):
        modified = datetime.fromtimestamp(backup.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            backup.unlink()
            backup.with_suffix(".db.sha256").unlink(missing_ok=True)

    print(destination)


if __name__ == "__main__":
    main()
