"""Tenant-scoped cached OCR and deterministic extraction state for a source file."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, func
from app.database import Base


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    id = Column(Integer, primary_key=True)
    source_file_id = Column(Integer, ForeignKey("source_files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default="needs_review")
    document_type = Column(String(20), nullable=False, default="invoice")
    provider = Column(String(80), nullable=False)
    ocr_status = Column(String(40), nullable=False, default="not_required")
    ocr_message = Column(String(500), nullable=True)
    processing_method = Column(String(40), nullable=False)
    pages = Column(JSON, nullable=False, default=list)  # bounded OCR/text blocks and page provenance
    fields = Column(JSON, nullable=False, default=dict)
    line_items = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)
    error_message = Column(String(500), nullable=True)
    processed_at = Column(DateTime, server_default=func.now(), nullable=False)
    raw_text = Column(Text, nullable=True)  # cached, bounded text; never included in audit events
