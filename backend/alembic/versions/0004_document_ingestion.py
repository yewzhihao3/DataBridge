"""M14 document source metadata and cached extraction state."""
from alembic import op
import sqlalchemy as sa
revision = "0004_document_ingestion"
down_revision = "0003_batch_imports"

def upgrade():
    with op.batch_alter_table("source_files") as batch:
        batch.add_column(sa.Column("media_type", sa.String(50), nullable=False, server_default="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
        batch.add_column(sa.Column("page_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("image_width", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("image_height", sa.Integer(), nullable=True))
    op.create_table("document_extractions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("source_files.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("status", sa.String(20), nullable=False), sa.Column("document_type", sa.String(20), nullable=False), sa.Column("provider", sa.String(80), nullable=False), sa.Column("processing_method", sa.String(40), nullable=False), sa.Column("pages", sa.JSON(), nullable=False), sa.Column("fields", sa.JSON(), nullable=False), sa.Column("line_items", sa.JSON(), nullable=False), sa.Column("warnings", sa.JSON(), nullable=False), sa.Column("error_message", sa.String(500)), sa.Column("processed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("raw_text", sa.Text()))
    op.create_index("ix_document_extractions_source_file_id", "document_extractions", ["source_file_id"])

def downgrade():
    raise RuntimeError("Document ingestion downgrade risks losing cached review data")
