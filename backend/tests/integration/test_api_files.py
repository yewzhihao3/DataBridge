"""
tests/integration/test_api_files.py — Integration tests for file upload & preview API.
"""

from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models.source_file import SourceFile


@pytest.mark.asyncio
async def test_upload_valid_xlsx_success(
    client: AsyncClient, clean_single_sheet_xlsx: Path, db_session: Session
) -> None:
    """A valid .xlsx upload creates DB record, saves file, and returns 201 with metadata."""
    file_bytes = clean_single_sheet_xlsx.read_bytes()

    response = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", file_bytes, "application/octet-stream")},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["original_name"] == "invoice.xlsx"
    assert data["file_size"] == len(file_bytes)
    assert len(data["checksum"]) == 64
    assert data["file_id"] > 0

    # Inspection details
    inspection = data["inspection"]
    assert len(inspection["worksheets"]) == 1
    assert inspection["worksheets"][0]["name"] == "Invoice"
    assert inspection["has_formula_cells"] is False

    # Check database persistence
    db_file = db_session.query(SourceFile).filter(SourceFile.id == data["file_id"]).first()
    assert db_file is not None
    assert db_file.checksum == data["checksum"]

    # Check file exists on disk with UUID name
    stored_path = settings.upload_dir / db_file.stored_filename
    assert stored_path.exists()
    assert stored_path.stat().st_size == len(file_bytes)


@pytest.mark.asyncio
async def test_duplicate_upload_allowed_with_same_checksum(
    client: AsyncClient, clean_single_sheet_xlsx: Path
) -> None:
    """Duplicate file uploads are allowed and record the same checksum with distinct IDs."""
    file_bytes = clean_single_sheet_xlsx.read_bytes()

    res1 = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice1.xlsx", file_bytes, "application/octet-stream")},
    )
    res2 = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice2.xlsx", file_bytes, "application/octet-stream")},
    )

    assert res1.status_code == 201
    assert res2.status_code == 201

    data1 = res1.json()
    data2 = res2.json()

    assert data1["file_id"] != data2["file_id"]
    assert data1["checksum"] == data2["checksum"]


@pytest.mark.asyncio
async def test_upload_invalid_extension_rejected_and_cleaned_up(
    client: AsyncClient, tmp_path: Path
) -> None:
    """Non-xlsx extension returns 400 and leaves no files in upload_dir."""
    response = await client.post(
        "/api/v1/files/upload",
        files={"file": ("data.csv", b"a,b,c\n1,2,3", "text/csv")},
    )
    assert response.status_code == 400
    assert "Only .xlsx files are accepted" in response.json()["detail"]

    # Verify upload directory is clean
    assert list(settings.upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_fake_magic_bytes_rejected_and_cleaned_up(
    client: AsyncClient, fake_magic_bytes_xlsx: Path
) -> None:
    """Fake magic bytes file returns 400 and is immediately cleaned up."""
    file_bytes = fake_magic_bytes_xlsx.read_bytes()

    response = await client.post(
        "/api/v1/files/upload",
        files={"file": ("spoofed.xlsx", file_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Invalid file signature" in response.json()["detail"]

    # Verify no leaked files in upload_dir
    assert list(settings.upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_corrupt_file_rejected_and_cleaned_up(
    client: AsyncClient, corrupt_xlsx: Path
) -> None:
    """Corrupted ZIP archive returns 400 and is cleaned up."""
    file_bytes = corrupt_xlsx.read_bytes()

    response = await client.post(
        "/api/v1/files/upload",
        files={"file": ("broken.xlsx", file_bytes, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Failed to parse Excel workbook" in response.json()["detail"]

    # Verify no leaked files
    assert list(settings.upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_preview_worksheet_success(
    client: AsyncClient, clean_single_sheet_xlsx: Path
) -> None:
    """Preview endpoint returns 2D grid matrix of cell data."""
    # First upload
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    # Then request preview
    preview_res = await client.get(
        f"/api/v1/files/{file_id}/preview",
        params={"sheet_name": "Invoice", "max_rows": 5, "max_cols": 4},
    )
    assert preview_res.status_code == 200

    data = preview_res.json()
    assert data["file_id"] == file_id
    assert data["sheet_name"] == "Invoice"
    assert data["total_rows_returned"] == 5
    assert len(data["rows"]) == 5
    assert data["rows"][0][0] == "INVOICE"


@pytest.mark.asyncio
async def test_preview_bounds_validation(
    client: AsyncClient, clean_single_sheet_xlsx: Path
) -> None:
    """Preview endpoint rejects zero or excessive row/column bounds."""
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    # Negative/zero max_rows
    res_zero = await client.get(
        f"/api/v1/files/{file_id}/preview",
        params={"sheet_name": "Invoice", "max_rows": 0},
    )
    assert res_zero.status_code == 422

    # Excess max_rows (> 100)
    res_excess = await client.get(
        f"/api/v1/files/{file_id}/preview",
        params={"sheet_name": "Invoice", "max_rows": 200},
    )
    assert res_excess.status_code == 422


@pytest.mark.asyncio
async def test_preview_nonexistent_sheet_returns_404(
    client: AsyncClient, clean_single_sheet_xlsx: Path
) -> None:
    upload_res = await client.post(
        "/api/v1/files/upload",
        files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes(), "application/octet-stream")},
    )
    file_id = upload_res.json()["file_id"]

    res = await client.get(
        f"/api/v1/files/{file_id}/preview",
        params={"sheet_name": "MissingSheet"},
    )
    assert res.status_code == 404
    assert "not found in workbook" in res.json()["detail"]


@pytest.mark.asyncio
async def test_preview_nonexistent_file_id_returns_404(client: AsyncClient) -> None:
    res = await client.get(
        "/api/v1/files/99999/preview",
        params={"sheet_name": "Invoice"},
    )
    assert res.status_code == 404
