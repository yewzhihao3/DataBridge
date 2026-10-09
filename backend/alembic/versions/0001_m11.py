"""Frozen M11 baseline; adopt an existing complete M11 schema without data loss."""
from alembic import op
from sqlalchemy import inspect
from pathlib import Path
import sys
# Alembic loads revision modules before env.py runs; make this frozen baseline's
# sibling schema module resolvable for `alembic heads` and upgrades alike.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from legacy_schema import Base

revision = "0001_m11"
down_revision = None


def upgrade():
    connection = op.get_bind()
    existing = set(inspect(connection).get_table_names()) - {"alembic_version"}
    expected = set(Base.metadata.tables)
    if existing:
        if not expected.issubset(existing):
            raise RuntimeError("Database is not a complete M11 schema; restore/upgrade it before M12")
        for name, table in Base.metadata.tables.items():
            columns = {c["name"] for c in inspect(connection).get_columns(name)}
            if not set(table.columns.keys()).issubset(columns):
                raise RuntimeError(f"M11 columns missing in {name}")
    else:
        for table in Base.metadata.sorted_tables:
            table.create(connection)


def downgrade():
    raise RuntimeError("Destructive baseline downgrade is disabled; restore a backup")
