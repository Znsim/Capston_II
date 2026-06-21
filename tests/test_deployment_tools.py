from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class DeploymentToolTests(unittest.TestCase):
    def test_legacy_sqlite_database_is_relocated_without_data_loss(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "legacy.db"
            target = temp / "data" / "kiosk.db"
            connection = sqlite3.connect(source)
            try:
                connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sample VALUES ('legacy-row')")
                connection.commit()
            finally:
                connection.close()

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.deploy.relocate_sqlite",
                    "--source",
                    str(source),
                    "--target",
                    str(target),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            relocated = sqlite3.connect(target)
            try:
                value = relocated.execute("SELECT value FROM sample").fetchone()[0]
            finally:
                relocated.close()
            self.assertEqual(value, "legacy-row")

    def test_model_placement_validates_and_copies_artifacts(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "models"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/deploy/place_models.py",
                    "--source",
                    "app/ai/models",
                    "--target",
                    str(target),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "gesture_model.pkl").is_file())
            self.assertTrue((target / "label_encoder.pkl").is_file())

    def test_sqlite_online_backup_preserves_rows(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            database = temp / "source.db"
            output = temp / "backups"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sample VALUES ('preserved')")
                connection.commit()
            finally:
                connection.close()

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/deploy/backup_sqlite.py",
                    "--database",
                    str(database),
                    "--output",
                    str(output),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            backup = next(output.glob("kiosk_*.db"))
            copied = sqlite3.connect(backup)
            try:
                value = copied.execute("SELECT value FROM sample").fetchone()[0]
            finally:
                copied.close()
            self.assertEqual(value, "preserved")
            self.assertTrue(backup.with_suffix(".db.sha256").is_file())
