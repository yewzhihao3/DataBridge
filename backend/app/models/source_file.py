"""
app/models/source_file.py — Database model for tracked source files.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, func
from app.database import Base


class SourceFile(Base):
    """
    Represents an uploaded data file (e.g. .xlsx workbook).

    Attributes:
        id: Primary key integer.
        original_name: Human-readable filename as uploaded by client.
        stored_filename: Safe UUID filename saved in uploads/ directory.
        file_size: Size in bytes.
        checksum: SHA-256 hash used for identification and traceability.
                  (Non-unique to allow deliberate re-imports if needed).
        uploaded_at: UTC timestamp when the file was registered.
    """

    __tablename__ = "source_files"

    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True, index=True)
    file_size = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False, index=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<SourceFile id={self.id} name='{self.original_name}' stored='{self.stored_filename}'>"
