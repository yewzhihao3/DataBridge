"""app/models/relationship.py — Database model for document relationships."""
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from app.database import Base


class DocumentRelationship(Base):
    """
    Represents an explicit, user-confirmed relationship between business documents
    or source attachments within a tenant workspace.
    """
    __tablename__ = "document_relationships"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_type = Column(String(30), nullable=False)
    source_id = Column(Integer, nullable=False)

    target_type = Column(String(30), nullable=False)
    target_id = Column(Integer, nullable=False)

    relationship_type = Column(String(30), nullable=False, default="related_to")

    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relationship_type",
            name="uq_document_relationships_edge",
        ),
        CheckConstraint(
            "relationship_type IN ('related_to', 'supports')",
            name="ck_document_relationships_type",
        ),
        CheckConstraint(
            "source_type IN ('invoice', 'receipt', 'source_file')",
            name="ck_document_relationships_source_type",
        ),
        CheckConstraint(
            "target_type IN ('invoice', 'receipt', 'source_file')",
            name="ck_document_relationships_target_type",
        ),
        CheckConstraint(
            "NOT (source_type = target_type AND source_id = target_id)",
            name="ck_document_relationships_no_self_link",
        ),
        Index("ix_doc_rel_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_doc_rel_org_target", "organization_id", "target_type", "target_id"),
        Index("ix_doc_rel_org_type", "organization_id", "relationship_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentRelationship id={self.id} org={self.organization_id} "
            f"{self.source_type}:{self.source_id} -> {self.relationship_type} -> "
            f"{self.target_type}:{self.target_id}>"
        )
