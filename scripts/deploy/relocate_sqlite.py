"""기존 루트 SQLite DB를 운영 data 경로로 안전하게 최초 이관한다."""

import argparse
from pathlib import Path
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("kiosk.db"))
    parser.add_argument("--target", type=Path, default=Path("data/kiosk.db"))
    args = parser.parse_args()

    if args.target.exists():
        print(f"Existing operational database kept: {args.target}")
        return
    if not args.source.is_file():
        print("No legacy SQLite database to relocate.")
        return

    args.target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(args.source)
    target = sqlite3.connect(args.target)
    try:
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"relocated_database_integrity_failed: {integrity}")
    finally:
        target.close()
        source.close()
    print(f"Relocated SQLite database: {args.source} -> {args.target}")


if __name__ == "__main__":
    main()
