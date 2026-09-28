from pathlib import Path
import sys
from alembic import context
from sqlalchemy import create_engine
from app.config import settings
from app.database import Base
import app.models

sys.path.insert(0, str(Path(__file__).parent))
target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    connection = context.config.attributes["connection"]
    if connection.dialect.name == "sqlite" and not connection.in_transaction():
        connection.exec_driver_sql("BEGIN")
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        # SQLite batch reconstruction needs FK checks suspended on this one
        # migration connection, then a full integrity check before committing.
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            # sqlite3 legacy transaction mode does not BEGIN for DDL by itself.
            connection.exec_driver_sql("BEGIN")
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
            if connection.dialect.name == "sqlite":
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(f"Migration foreign key violations: {violations}")
        connection.commit()
