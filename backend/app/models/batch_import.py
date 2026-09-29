"""Outer session model for M13 multi-file imports.

The existing ImportBatch remains the immutable, atomic persistence record for
one source file.  A BatchImportSession only coordinates those file flows.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship
from app.database import Base


class BatchImportSession(Base):
    __tablename__ = "batch_import_sessions"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="analyzing")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    completed_at = Column(DateTime)
    files = relationship("BatchImportFile", back_populates="session", cascade="all, delete-orphan", order_by="BatchImportFile.id")


class BatchImportFile(Base):
    __tablename__ = "batch_import_files"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("batch_import_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_file_id = Column(Integer, ForeignKey("source_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="uploading")
    detected_type = Column(String(20))
    processing_method = Column(String(30))
    issues = Column(JSON, nullable=False, default=list)
    error_message = Column(String(500))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    session = relationship("BatchImportSession", back_populates="files")
    source_file = relationship("SourceFile")
    template = relationship("Template")
    import_batch = relationship("ImportBatch")
