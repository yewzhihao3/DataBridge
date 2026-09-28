import importlib.util
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from app.config import settings
from app.database import Base
import pytest


@pytest.mark.parametrize("empty_identity_tables", [False, True])
def test_upgrade_existing_m11_without_data_loss(tmp_path, monkeypatch, empty_identity_tables):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("snapshot", root / "alembic/legacy_schema.py")
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    legacy.Base.metadata.create_all(engine)
    if empty_identity_tables:
        for table in Base.metadata.sorted_tables:
            if table.name not in legacy.Base.metadata.tables:
                table.create(engine)
    with engine.begin() as db:
        db.execute(text("INSERT INTO templates(id,name,template_type,file_type) VALUES(1,'Preserved','invoice','xlsx')"))
        db.execute(text("INSERT INTO source_files(id,original_name,stored_filename,file_size,checksum) VALUES(1,'original.xlsx','original.xlsx',20,'checksum')"))
        db.execute(text("INSERT INTO import_batches(id,source_file_id,template_id,status,record_count,warning_count,is_deleted) VALUES(1,1,1,'imported',1,0,0)"))
        db.execute(text("INSERT INTO invoice_records(id,batch_id,company_name,invoice_number,total_amount,source_worksheet,raw_data,custom_fields) VALUES(1,1,'Original','INV-1',123.45,'Sheet1','{}','{\"custom\":\"kept\"}')"))
    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(root / "alembic.ini"))
    with engine.connect() as migration_connection:
        migration_connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        migration_connection.commit()
        config.attributes["connection"] = migration_connection
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        migration_connection.commit()
    with engine.connect() as db:
        assert db.execute(text("SELECT name FROM organizations")).scalar() == "Default Workspace"
        assert db.execute(text("SELECT count(*) FROM organization_memberships")).scalar() == 0
        for table in ["templates", "source_files", "import_batches"]:
            assert db.execute(text(f"SELECT organization_id FROM {table}")).scalar() == 1
        assert db.execute(text("SELECT company_name,invoice_number,total_amount,custom_fields FROM invoice_records")).one() == ("Original","INV-1",123.45,'{"custom":"kept"}')
        assert not db.execute(text("PRAGMA foreign_key_check")).all()
    assert not next(c for c in inspect(engine).get_columns("templates") if c["name"] == "organization_id")["nullable"]


def test_empty_upgrade_and_postgresql_schema_compilation(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    engine = create_engine(url)
    config = Config(str(root / "alembic.ini"))
    with engine.connect() as migration_connection:
        migration_connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        migration_connection.commit()
        config.attributes["connection"] = migration_connection
        command.upgrade(config, "head")
        migration_connection.commit()
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())
    for table in Base.metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=postgresql.dialect()))
