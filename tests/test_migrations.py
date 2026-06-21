import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class MigrationTests(unittest.TestCase):
    def test_fresh_database_upgrade_is_idempotent(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "migration_test.db"
            env = os.environ.copy()
            env["SQLITE_PATH"] = str(database_path)

            for _ in range(2):
                result = subprocess.run(
                    [sys.executable, "-m", "app.core.migrate"],
                    cwd=project_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            connection = sqlite3.connect(database_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                revision = connection.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertTrue(
                {
                    "device_info",
                    "ai_label_map",
                    "communication_log",
                    "training_data_log",
                    "conversation",
                    "alembic_version",
                }.issubset(tables)
            )
            self.assertEqual(revision, "20260620_01")
