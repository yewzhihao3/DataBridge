"""
tests/conftest.py — Shared pytest fixtures and configuration.

Provides:
- Isolated in-memory SQLite database per test session/function.
- Async HTTP client with dependency overrides for FastAPI app.
- Programmatic Excel (.xlsx) fixture workbooks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import AsyncGenerator, Generator

import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app


# ── Database Test Fixtures ────────────────────────────────────────────────────

# Create an in-memory SQLite engine with foreign key support enabled
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma_test(dbapi_connection: object, connection_record: object) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path: Path) -> Generator[None, None, None]:
    """
    Creates fresh database schema in memory and overrides upload_dir to a tmp_path
    before each test, cleaning up afterwards.
    """
    # Override upload directory to temporary directory
    original_upload_dir = settings.upload_dir
    settings.upload_dir = tmp_path / "test_uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)
    settings.upload_dir = original_upload_dir


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides a transactional database session for unit/integration tests."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── HTTP Client Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Provides an asynchronous test client with get_db overridden to use
    the in-memory test database.
    """
    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Excel Workbook Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def clean_single_sheet_xlsx(tmp_path: Path) -> Path:
    """Creates a basic valid .xlsx file with sample invoice-like text data."""
    file_path = tmp_path / "clean_invoice.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoice"

    # Header section
    ws["A1"] = "INVOICE"
    ws["B2"] = "Acme Supplies Ltd"
    ws["B3"] = "INV-2026-001"
    ws["F3"] = "2026-09-22"
    ws["D6"] = 1450.50

    # Line items
    ws["A10"] = "Item"
    ws["B10"] = "Qty"
    ws["C10"] = "Price"
    ws["A11"] = "Industrial Gloves"
    ws["B11"] = 100
    ws["C11"] = 14.50

    wb.save(file_path)
    wb.close()
    return file_path


@pytest.fixture
def multi_sheet_with_hidden_xlsx(tmp_path: Path) -> Path:
    """Creates a workbook with 3 sheets: visible, hidden, and veryHidden."""
    file_path = tmp_path / "multi_sheet.xlsx"
    wb = openpyxl.Workbook()

    # Sheet 1: Visible
    ws1 = wb.active
    ws1.title = "Overview"
    ws1["A1"] = "Summary Report"

    # Sheet 2: Hidden
    ws2 = wb.create_sheet(title="Lookup_Rates")
    ws2["A1"] = "USD"
    ws2["B1"] = 1.35
    ws2.sheet_state = "hidden"

    # Sheet 3: VeryHidden
    ws3 = wb.create_sheet(title="Audit_Internal")
    ws3["A1"] = "Secret Data"
    ws3.sheet_state = "veryHidden"

    wb.save(file_path)
    wb.close()
    return file_path


@pytest.fixture
def workbook_with_formulas_xlsx(tmp_path: Path) -> Path:
    """Creates a workbook with uncalculated formula cells."""
    file_path = tmp_path / "formulas.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Calculations"

    ws["A1"] = 100
    ws["A2"] = 250
    ws["A3"] = "=SUM(A1:A2)"

    wb.save(file_path)
    wb.close()
    return file_path


@pytest.fixture
def corrupt_xlsx(tmp_path: Path) -> Path:
    """Creates a corrupted file that starts with PK magic bytes but is invalid ZIP."""
    file_path = tmp_path / "corrupt.xlsx"
    file_path.write_bytes(b"PK\x03\x04GARBAGE_DATA_NOT_A_REAL_ZIP")
    return file_path


@pytest.fixture
def fake_magic_bytes_xlsx(tmp_path: Path) -> Path:
    """Creates a plain text file pretending to be .xlsx (wrong magic bytes)."""
    file_path = tmp_path / "fake.xlsx"
    file_path.write_text("This is just a text file renamed to xlsx", encoding="utf-8")
    return file_path
