"""Document relationships junction table and constraints.

Revision ID: 0008_document_relationships
Revises: 0007_financial_direction
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_document_relationships"
down_revision = "0007_financial_direction"


def upgrade():
    op.create_table(
        "document_relationships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("relationship_type", sa.String(30), nullable=False, server_default="related_to"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relationship_type",
            name="uq_document_relationships_edge",
        ),
        sa.CheckConstraint(
            "relationship_type IN ('related_to', 'supports')",
            name="ck_document_relationships_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('invoice', 'receipt', 'source_file')",
            name="ck_document_relationships_source_type",
        ),
        sa.CheckConstraint(
            "target_type IN ('invoice', 'receipt', 'source_file')",
            name="ck_document_relationships_target_type",
        ),
        sa.CheckConstraint(
            "NOT (source_type = target_type AND source_id = target_id)",
            name="ck_document_relationships_no_self_link",
        ),
    )

    op.create_index("ix_document_relationships_id", "document_relationships", ["id"])
    op.create_index("ix_document_relationships_organization_id", "document_relationships", ["organization_id"])
    op.create_index("ix_doc_rel_org_source", "document_relationships", ["organization_id", "source_type", "source_id"])
    op.create_index("ix_doc_rel_org_target", "document_relationships", ["organization_id", "target_type", "target_id"])
    op.create_index("ix_doc_rel_org_type", "document_relationships", ["organization_id", "relationship_type"])


def downgrade():
    op.drop_index("ix_doc_rel_org_type", table_name="document_relationships")
    op.drop_index("ix_doc_rel_org_target", table_name="document_relationships")
    op.drop_index("ix_doc_rel_org_source", table_name="document_relationships")
    op.drop_index("ix_document_relationships_organization_id", table_name="document_relationships")
    op.drop_index("ix_document_relationships_id", table_name="document_relationships")
    op.drop_table("document_relationships")
