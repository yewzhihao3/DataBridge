"""
app/database.py — Database connectivity and session management.

──────────────────────────────────────────────────────────────────────────────
Core SQLAlchemy concepts explained:

1. Engine:
   The core interface to the database. It manages a pool of connections and
   translates SQLAlchemy dialect commands into database-specific SQL.

2. SQLite Foreign Key Pragma:
   By default, SQLite does NOT enforce FOREIGN KEY constraints unless explicitly
   enabled per connection via 'PRAGMA foreign_keys=ON'. We register a connection
   listener to enforce foreign key integrity and cascading deletes automatically.

3. SessionLocal (Sessionmaker):
   A factory for creating individual database sessions. A session represents
   a conversation with the database where queries and transactions occur.

4. Base (DeclarativeBase):
   The root class that all ORM models inherit from. SQLAlchemy uses this base
   class to maintain a registry of tables and column mappings.

5. get_db() (FastAPI Dependency):
   A generator function yielded per request. Ensures each API request receives
   its own isolated session and that the session is properly closed when the
   request completes.
──────────────────────────────────────────────────────────────────────────────
"""

import sqlite3
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import settings

# SQLite requires check_same_thread=False when used across multiple threads
# (as in FastAPI's asynchronous thread pool). For PostgreSQL/MySQL, this is omitted.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,  # Set to True if you want raw SQL query logging in console
)


# ── SQLite Foreign Key Listener ───────────────────────────────────────────────
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    """
    Ensure SQLite enforces foreign key constraints and cascade deletions.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a database session per request.

    Guarantees clean closure after request lifecycle.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
