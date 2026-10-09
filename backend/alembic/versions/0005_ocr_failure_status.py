"""Structured OCR provider status for document review."""
from alembic import op
import sqlalchemy as sa
revision = "0005_ocr_failure_status"
down_revision = "0004_document_ingestion"

def upgrade():
    with op.batch_alter_table("document_extractions") as batch:
        batch.add_column(sa.Column("ocr_status", sa.String(40), nullable=False, server_default="not_required"))
        batch.add_column(sa.Column("ocr_message", sa.String(500), nullable=True))

def downgrade():
    raise RuntimeError("OCR status downgrade risks losing review diagnostics")
