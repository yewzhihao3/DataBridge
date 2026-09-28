"""Verify migration on a read-only snapshot of local M11 data, never in place."""
from pathlib import Path
import sqlite3
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def verify():
    with tempfile.TemporaryDirectory(prefix="databridge-m12-") as directory:
        copy_path = Path(directory) / "migration-copy.sqlite"
        source = sqlite3.connect((root / "databridge.db").as_uri() + "?mode=ro", uri=True)
        destination = sqlite3.connect(copy_path)
        try:
            source.backup(destination)
        finally:
            source.close()
            destination.close()
        engine = create_engine(f"sqlite:///{copy_path.as_posix()}")
        try:
            with engine.connect() as db:
                tables = ["templates", "template_field_mappings", "source_files", "import_batches", "invoice_records", "invoice_line_items", "validation_error_records"]
                before = {table: db.exec_driver_sql(f'SELECT * FROM "{table}" ORDER BY id').all() for table in tables}
                columns = {table: [r[1] for r in db.exec_driver_sql(f'PRAGMA table_info("{table}")')] for table in tables}
                db.commit()
                config = Config(str(root / "alembic.ini"))
                config.attributes["connection"] = db
                command.upgrade(config, "head")
                db.commit()
                for table in tables:
                    names = ",".join(f'"{name}"' for name in columns[table])
                    after = db.exec_driver_sql(f'SELECT {names} FROM "{table}" ORDER BY id').all()
                    assert before[table] == after, f"Data changed in {table}"
                assert not db.exec_driver_sql("PRAGMA foreign_key_check").all()
                for table in ("source_files", "templates", "import_batches"):
                    assert db.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id IS NULL")).scalar() == 0
                print({table: len(rows) for table, rows in before.items()})
                print("All original values preserved; foreign keys valid; tenant ownership backfilled. Source was read-only.")
        finally:
            engine.dispose()


if __name__ == "__main__":
    verify()
