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
    JSON,
    Boolean,
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
    is_deleted = Column(Boolean, nullable=False, default=False)
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
    source_row_number = Column(Integer, nullable=True)  # 1-based Excel row number for multi-record imports
    raw_data = Column(Text, nullable=False)  # JSON-encoded dictionary of raw extractions
    custom_fields = Column(JSON, nullable=True)  # Optional JSON data for fields that are not core headers
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    batch = relationship("ImportBatch", back_populates="invoice_records")
    line_items = relationship(
        "InvoiceLineItem",
        back_populates="invoice_record",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.source_row_number",
    )

    def __repr__(self) -> str:
        return f"<InvoiceRecord id={self.id} number='{self.invoice_number}' company='{self.company_name}'>"


class InvoiceLineItem(Base):
    """
    Represents an individual product or service line item belonging to an InvoiceRecord.
    """

    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(
        Integer, ForeignKey("invoice_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_row_number = Column(Integer, nullable=False)  # 1-based Excel row number
    description = Column(String(500), nullable=True)
    quantity = Column(Numeric(12, 4), nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True)
    tax_rate = Column(Numeric(8, 4), nullable=True)
    tax_amount = Column(Numeric(12, 2), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    custom_fields = Column(JSON, nullable=True)  # SKU, UOM, discount, serial_number, etc.
    raw_data = Column(Text, nullable=True)  # JSON string of raw extracted cell values
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    invoice_record = relationship("InvoiceRecord", back_populates="line_items")

    def __repr__(self) -> str:
        return f"<InvoiceLineItem id={self.id} invoice_id={self.invoice_id} row={self.source_row_number} desc='{self.description}'>"


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

