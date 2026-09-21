"""
app/models/invoice.py — Database models for import batches and invoice records.

──────────────────────────────────────────────────────────────────────────────
Model Relationships:
1. ImportBatch:
   - source_file: 1-to-Many backref from SourceFile (ON DELETE RESTRICT)
   - template: 1-to-Many backref from Template (ON DELETE RESTRICT)
   - invoice_records: 1-to-Many relationship (cascade="all, delete-orphan")
   - validation_issues: 1-to-Many relationship (cascade="all, delete-orphan")

2. InvoiceRecord:
   - Stores normalized fields (company_name, invoice_number, invoice_date, total_amount, currency)
   - total_amount and currency are nullable to accommodate optional template mappings.
   - raw_data: JSON string containing exact raw cell extractions for auditability.

3. ValidationErrorRecord:
   - Stores historical non-fatal warnings and info diagnostics associated with
     an imported batch.
──────────────────────────────────────────────────────────────────────────────
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ImportBatch(Base):
    """
    Represents an individual import execution run.
    """

    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, index=True)
    source_file_id = Column(
        Integer, ForeignKey("source_files.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_id = Column(
        Integer, ForeignKey("templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status = Column(String(20), nullable=False, default="imported")  # "imported"
    record_count = Column(Integer, nullable=False, default=1)
    warning_count = Column(Integer, nullable=False, default=0)
    imported_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    source_file = relationship("SourceFile", backref="import_batches")
    template = relationship("Template", backref="import_batches")
    invoice_records = relationship(
        "InvoiceRecord",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="InvoiceRecord.id",
    )
    validation_issues = relationship(
        "ValidationErrorRecord",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ValidationErrorRecord.id",
    )

    def __repr__(self) -> str:
        return f"<ImportBatch id={self.id} status='{self.status}' records={self.record_count}>"


class InvoiceRecord(Base):
    """
    Stores normalized invoice header data with a full raw JSON payload audit trail.
    """

    __tablename__ = "invoice_records"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(
        Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_name = Column(String(255), nullable=False, index=True)
    invoice_number = Column(String(100), nullable=False, index=True)
    invoice_date = Column(Date, nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=True)
    source_worksheet = Column(String(100), nullable=False)
    raw_data = Column(Text, nullable=False)  # JSON-encoded dictionary of raw extractions
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    batch = relationship("ImportBatch", back_populates="invoice_records")

    def __repr__(self) -> str:
        return f"<InvoiceRecord id={self.id} number='{self.invoice_number}' company='{self.company_name}'>"


class ValidationErrorRecord(Base):
    """
    Persists non-fatal warnings and diagnostic issues associated with an approved import.
    """

    __tablename__ = "validation_error_records"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(
        Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id = Column(String(50), nullable=False)
    field_name = Column(String(100), nullable=True)
    severity = Column(String(20), nullable=False)  # "warning" | "info"
    message = Column(Text, nullable=False)
    cell_ref = Column(String(20), nullable=True)
    worksheet = Column(String(100), nullable=True)

    batch = relationship("ImportBatch", back_populates="validation_issues")

    def __repr__(self) -> str:
        return f"<ValidationErrorRecord id={self.id} rule='{self.rule_id}' severity='{self.severity}'>"
