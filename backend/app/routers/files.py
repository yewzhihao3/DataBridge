"""
app/routers/files.py — Endpoints for file upload, inspection, and previews.

──────────────────────────────────────────────────────────────────────────────
Upload Transaction Safety Workflow:

1. Validate extension from filename (ignoring spoofable client Content-Type headers).
2. Stream incoming chunks to a temporary file on disk while hashing (SHA-256)
   and tracking byte count to prevent exceeding MAX_FILE_SIZE_MB.
3. Validate magic bytes and openpyxl readable via inspect_workbook().
4. Move validated file to final UUID-based filename.
5. Create SourceFile record in database.
6. Commit transaction and return HTTP 201 Created.
7. If ANY exception occurs at any point:
   - Roll back the database transaction.
   - Remove any temporary or destination file from disk.
   - Raise a descriptive HTTPException.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.source_file import SourceFile
from app.schemas.source_file import (
    FileUploadResponse,
    WorkbookInspectionSchema,
    WorksheetPreviewResponse,
)
from app.services.workbook_inspector import (
    CorruptWorkbookError,
    FileSizeExceededError,
    InvalidFileFormatError,
    WorksheetNotFoundError,
    generate_safe_upload_path,
    get_worksheet_preview,
    inspect_workbook,
)

router = APIRouter(prefix="/api/v1/files", tags=["Files"])


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and inspect an Excel (.xlsx) file",
)
async def upload_file(
    file: Annotated[UploadFile, File(description="Excel .xlsx file")],
    db: Session = Depends(get_db),
) -> FileUploadResponse:
    """
    Uploads an Excel file securely, computes its SHA-256 checksum, verifies its
    structure, and stores both file and metadata transactionally.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )

    # 1. Extension check
    ext = os.path.splitext(file.filename)[1].lower()
    if ext != ".xlsx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Only .xlsx files are accepted.",
        )

    # Prepare storage paths
    upload_dir = settings.upload_dir.resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    temp_path = upload_dir / f".tmp_{os.urandom(8).hex()}.xlsx"
    final_path: Path | None = None
    hasher = hashlib.sha256()
    total_bytes = 0
    max_bytes = settings.max_file_size_mb * 1024 * 1024

    try:
        # 2. Stream to temporary file with size cap and hash calculation
        with open(temp_path, "wb") as f_out:
            while chunk := await file.read(64 * 1024):  # 64 KB chunks
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FileSizeExceededError(
                        f"File size exceeds limit of {settings.max_file_size_mb} MB."
                    )
                hasher.update(chunk)
                f_out.write(chunk)

        if total_bytes == 0:
            raise InvalidFileFormatError("Uploaded file is empty (0 bytes).")

        checksum = hasher.hexdigest()

        # 3. Generate safe UUID final destination
        final_path, stored_filename = generate_safe_upload_path(
            upload_dir, file.filename
        )

        # 4. Move temp file to final destination
        os.replace(temp_path, final_path)

        # 5. Inspect the workbook structure and check for formula cells
        inspection_result = inspect_workbook(
            final_path, max_size_mb=settings.max_file_size_mb
        )

        # 6. Database record creation
        source_file = SourceFile(
            original_name=file.filename,
            stored_filename=stored_filename,
            file_size=total_bytes,
            checksum=checksum,
        )
        db.add(source_file)
        db.commit()
        db.refresh(source_file)

        return FileUploadResponse(
            file_id=source_file.id,
            original_name=source_file.original_name,
            file_size=source_file.file_size,
            checksum=source_file.checksum,
            uploaded_at=source_file.uploaded_at,
            inspection=WorkbookInspectionSchema(
                worksheets=inspection_result.worksheets,  # type: ignore[arg-type]
                active_sheet_name=inspection_result.active_sheet_name,
                has_formula_cells=inspection_result.has_formula_cells,
                formula_cells=inspection_result.formula_cells,  # type: ignore[arg-type]
                warnings=inspection_result.warnings,
            ),
        )

    except HTTPException:
        db.rollback()
        _cleanup_files(temp_path, final_path)
        raise

    except FileSizeExceededError as exc:
        db.rollback()
        _cleanup_files(temp_path, final_path)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc

    except (InvalidFileFormatError, CorruptWorkbookError) as exc:
        db.rollback()
        _cleanup_files(temp_path, final_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        db.rollback()
        _cleanup_files(temp_path, final_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while processing the upload: {exc}",
        ) from exc


@router.get(
    "/{file_id}/preview",
    response_model=WorksheetPreviewResponse,
    summary="Preview worksheet cell data for an uploaded file",
)
def preview_worksheet(
    file_id: int,
    sheet_name: str = Query(..., min_length=1, description="Worksheet name to preview"),
    max_rows: int = Query(15, ge=1, le=100, description="Max rows (1 to 100)"),
    max_cols: int = Query(10, ge=1, le=50, description="Max columns (1 to 50)"),
    db: Session = Depends(get_db),
) -> WorksheetPreviewResponse:
    """
    Returns a bounded 2D matrix of cell values from the specified worksheet.
    Allows previewing both visible and hidden worksheets.
    """
    source_file = db.query(SourceFile).filter(SourceFile.id == file_id).first()
    if not source_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID {file_id} was not found.",
        )

    file_path = settings.upload_dir / source_file.stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file was not found on disk storage.",
        )

    try:
        grid = get_worksheet_preview(
            file_path=file_path,
            sheet_name=sheet_name,
            max_rows=max_rows,
            max_cols=max_cols,
            max_size_mb=settings.max_file_size_mb,
        )
        total_rows = len(grid)
        total_cols = len(grid[0]) if grid else 0

        return WorksheetPreviewResponse(
            file_id=file_id,
            sheet_name=sheet_name,
            rows=grid,
            total_rows_returned=total_rows,
            total_cols_returned=total_cols,
        )

    except WorksheetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except CorruptWorkbookError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _cleanup_files(*paths: Path | None) -> None:
    """Safely delete any created temporary or final files if an error occurred."""
    for p in paths:
        if p is not None and p.exists():
            try:
                p.unlink()
            except OSError:
                pass
