from sqlalchemy.orm import declarative_base
Base = declarative_base()

"""
app/models/template.py â€” Database models for templates and field mappings.

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Key ORM concepts:

1. Cascade Deletion:
   cascade="all, delete-orphan" on Template.field_mappings tells SQLAlchemy
   that TemplateFieldMapping rows are owned entirely by their parent Template.
   Deleting a Template automatically removes all its child mappings.

2. Unique Constraints:
   - Template.name is unique to prevent duplicate template definitions.
   - (template_id, field_name) is unique so a template cannot contain duplicate
     mappings for the same field (e.g. mapping invoice_number twice).

3. Column Mapping Extensibility:
   cell_ref is nullable at the database column level so future 'column'
   mappings (e.g., column_ref="B") can be added seamlessly without migrations.
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
"""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship


from sqlalchemy import ForeignKey


class Template(Base):
    """
    Defines how data should be extracted from a specific spreadsheet format.
    """

    __tablename__ = "templates"
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_workspace_template_name"),)
    description = Column(Text, nullable=True)
    template_type = Column(String(20), nullable=False, default="invoice")  # "invoice" | "dataset"
    file_type = Column(String(20), nullable=False, default="xlsx")
    worksheet = Column(String(100), nullable=True)  # None means default/first sheet
    header_row = Column(Integer, nullable=True)
    data_start_row = Column(Integer, nullable=True)
    date_format = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 1-to-many relationship with cascading delete
    field_mappings = relationship(
        "TemplateFieldMapping",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateFieldMapping.id",
    )

    def __repr__(self) -> str:
        return f"<Template id={self.id} name='{self.name}' type='{self.template_type}'>"


class TemplateFieldMapping(Base):
    """
    Defines an individual field extraction target inside a Template.
    """

    __tablename__ = "template_field_mappings"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(
        Integer, ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mapping_group = Column(String(20), nullable=False, default="header")  # "header" | "line_item"
    field_name = Column(String(100), nullable=False)
    target_field = Column(String(100), nullable=True)  # Canonical or custom backend field to map to
    mapping_type = Column(String(20), nullable=False, default="cell")  # "cell" | "column"
    cell_ref = Column(String(20), nullable=True)  # e.g. "B2"
    column_ref = Column(String(20), nullable=True)  # e.g. "B" (for column / line-item mappings)
    is_required = Column(Boolean, default=False, nullable=False)
    data_type = Column(String(20), default="text", nullable=False)  # text | date | decimal | integer

    # Back reference to parent template
    template = relationship("Template", back_populates="field_mappings")

    __table_args__ = (
        UniqueConstraint("template_id", "mapping_group", "field_name", name="uq_template_group_field_name"),
    )

    def __repr__(self) -> str:
        return f"<TemplateFieldMapping id={self.id} group='{self.mapping_group}' field='{self.field_name}' cell='{self.cell_ref}' col='{self.column_ref}'>"


"""
app/models/source_file.py â€” Database model for tracked source files.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, func

from sqlalchemy import ForeignKey


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
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True, index=True)
    file_size = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False, index=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<SourceFile id={self.id} name='{self.original_name}' stored='{self.stored_filename}'>"

"""
app/models/invoice.py â€” Database models for import batches and invoice records.

â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


from sqlalchemy import ForeignKey


class ImportBatch(Base):
    """
    Represents an individual import execution run.
    """

    __tablename__ = "import_batches"
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)

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


"""Accounts, workspace membership and revocable browser sessions."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func



class Timestamps:
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class User(Timestamps, Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(254), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class Organization(Timestamps, Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(140), nullable=False, unique=True)


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(10), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "organization_id"), CheckConstraint("role IN ('OWNER','ADMIN','MEMBER')"))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    csrf_hash = Column(String(64), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(254), nullable=False)
    role = Column(String(10), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (CheckConstraint("role IN ('ADMIN','MEMBER')"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(60), nullable=False)
    entity_type = Column(String(60))
    entity_id = Column(Integer)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
