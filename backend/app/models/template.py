"""
app/models/template.py — Database models for templates and field mappings.

──────────────────────────────────────────────────────────────────────────────
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
──────────────────────────────────────────────────────────────────────────────
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

from app.database import Base


class Template(Base):
    """
    Defines how data should be extracted from a specific spreadsheet format.
    """

    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
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
        return f"<Template id={self.id} name='{self.name}'>"


class TemplateFieldMapping(Base):
    """
    Defines an individual field extraction target inside a Template.
    """

    __tablename__ = "template_field_mappings"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(
        Integer, ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name = Column(String(100), nullable=False)
    mapping_type = Column(String(20), nullable=False, default="cell")  # "cell" | "column"
    cell_ref = Column(String(20), nullable=True)  # e.g. "B2"
    column_ref = Column(String(20), nullable=True)  # e.g. "B" (for future column mappings)
    is_required = Column(Boolean, default=False, nullable=False)
    data_type = Column(String(20), default="text", nullable=False)  # text | date | decimal | integer

    # Back reference to parent template
    template = relationship("Template", back_populates="field_mappings")

    __table_args__ = (
        UniqueConstraint("template_id", "field_name", name="uq_template_field_name"),
    )

    def __repr__(self) -> str:
        return f"<TemplateFieldMapping id={self.id} field='{self.field_name}' cell='{self.cell_ref}'>"
