"""M13 outer batch import session."""
from alembic import op
import sqlalchemy as sa

revision = "0003_batch_imports"
down_revision = "0002_saas"

def upgrade():
    op.create_table("batch_import_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime()),
    )
    op.create_index("ix_batch_import_sessions_organization_id", "batch_import_sessions", ["organization_id"])
    op.create_table("batch_import_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("batch_import_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("source_files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("templates.id", ondelete="SET NULL")),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("detected_type", sa.String(20)),
        sa.Column("processing_method", sa.String(30)), sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(500)), sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_batch_import_files_session_id", "batch_import_files", ["session_id"])
    op.create_index("ix_batch_import_files_source_file_id", "batch_import_files", ["source_file_id"])

def downgrade():
    op.drop_table("batch_import_files")
    op.drop_table("batch_import_sessions")
