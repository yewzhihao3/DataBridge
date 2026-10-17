"""
app/services/relationship_service.py — Service layer for document relationships.

Encapsulates:
- Entity resolution and workspace ownership validation.
- Soft-deletion checks (ImportBatch.is_deleted).
- Self-link and duplicate-link prevention.
- Canonical normalization for symmetric relationships.
- Direction semantics calculation ("symmetric", "supports", "supported_by").
- Audit event generation.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.models.relationship import DocumentRelationship
from app.models.source_file import SourceFile
from app.schemas.relationship import (
    RelatedDocumentSummary,
    RelationshipCreateRequest,
    RelationshipListResponse,
    RelationshipRead,
)
from app.security import audit

logger = logging.getLogger(__name__)

VALID_ENTITY_TYPES = {"invoice", "receipt", "source_file"}
VALID_RELATIONSHIP_TYPES = {"related_to", "supports"}


def validate_and_resolve_entity(
    db: Session,
    organization_id: int,
    entity_type: str,
    entity_id: int,
) -> tuple[Any, RelatedDocumentSummary]:
    """
    Validates that an entity exists, belongs to the specified organization,
    and is not soft-deleted. Returns the ORM instance and its summary schema.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported entity type '{entity_type}'. Must be one of: {sorted(list(VALID_ENTITY_TYPES))}.",
        )

    if entity_type == "invoice":
        record = (
            db.query(InvoiceRecord)
            .join(ImportBatch)
            .filter(
                InvoiceRecord.id == entity_id,
                ImportBatch.organization_id == organization_id,
                ImportBatch.is_deleted.is_(False),
            )
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice with ID {entity_id} was not found or has been deleted.",
            )
        summary = RelatedDocumentSummary(
            entity_type="invoice",
            entity_id=record.id,
            document_number=record.invoice_number,
            counterparty=record.company_name,
            document_date=record.invoice_date,
            total_amount=record.total_amount,
            currency=record.currency,
            direction=record.direction,
            source_file_id=record.batch.source_file_id if record.batch else None,
        )
        return record, summary

    if entity_type == "receipt":
        record = (
            db.query(ReceiptRecord)
            .join(ImportBatch)
            .filter(
                ReceiptRecord.id == entity_id,
                ImportBatch.organization_id == organization_id,
                ImportBatch.is_deleted.is_(False),
            )
            .first()
        )
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Receipt with ID {entity_id} was not found or has been deleted.",
            )
        summary = RelatedDocumentSummary(
            entity_type="receipt",
            entity_id=record.id,
            document_number=record.receipt_number,
            counterparty=record.merchant_name,
            document_date=record.transaction_date,
            total_amount=record.total_amount,
            currency=record.currency,
            direction=record.direction,
            source_file_id=record.batch.source_file_id if record.batch else None,
        )
        return record, summary

    # entity_type == "source_file"
    sf = (
        db.query(SourceFile)
        .filter(
            SourceFile.id == entity_id,
            SourceFile.organization_id == organization_id,
        )
        .first()
    )
    if not sf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source file with ID {entity_id} was not found.",
        )
    summary = RelatedDocumentSummary(
        entity_type="source_file",
        entity_id=sf.id,
        filename=sf.original_name,
        media_type=sf.media_type,
        file_size=sf.file_size,
        source_file_id=sf.id,
    )
    return sf, summary


def create_relationship(
    db: Session,
    organization_id: int,
    user_id: int,
    payload: RelationshipCreateRequest,
) -> RelationshipRead:
    """
    Creates an explicit relationship between two existing documents within the workspace.
    Symmetric relationships are canonically normalized to avoid duplicate inverse edges.
    """
    if payload.relationship_type not in VALID_RELATIONSHIP_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported relationship_type '{payload.relationship_type}'. Must be one of: {sorted(list(VALID_RELATIONSHIP_TYPES))}.",
        )

    if payload.source_type == payload.target_type and payload.source_id == payload.target_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A document cannot be linked to itself.",
        )

    # 1. Resolve & validate both entities (existence, workspace ownership, active non-deleted status)
    _, source_summary = validate_and_resolve_entity(db, organization_id, payload.source_type, payload.source_id)
    _, target_summary = validate_and_resolve_entity(db, organization_id, payload.target_type, payload.target_id)

    # 2. Canonical normalization for symmetric relationships
    src_type, src_id = payload.source_type, payload.source_id
    tgt_type, tgt_id = payload.target_type, payload.target_id

    if payload.relationship_type == "related_to":
        if (src_type, src_id) > (tgt_type, tgt_id):
            src_type, tgt_type = tgt_type, src_type
            src_id, tgt_id = tgt_id, src_id

    # 3. Duplicate check before insert
    existing = (
        db.query(DocumentRelationship)
        .filter(
            DocumentRelationship.organization_id == organization_id,
            DocumentRelationship.source_type == src_type,
            DocumentRelationship.source_id == src_id,
            DocumentRelationship.target_type == tgt_type,
            DocumentRelationship.target_id == tgt_id,
            DocumentRelationship.relationship_type == payload.relationship_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A relationship already exists between these documents.",
        )

    # 4. Insert and commit with concurrency protection
    rel = DocumentRelationship(
        organization_id=organization_id,
        source_type=src_type,
        source_id=src_id,
        target_type=tgt_type,
        target_id=tgt_id,
        relationship_type=payload.relationship_type,
        created_by_user_id=user_id,
    )
    db.add(rel)

    try:
        db.commit()
        db.refresh(rel)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A relationship already exists between these documents.",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to insert document relationship")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist document relationship.",
        ) from exc

    # 5. Audit log
    audit(db, organization_id, user_id, "CREATE_RELATIONSHIP", "document_relationships", rel.id)
    db.commit()

    # Determine direction semantic and related entity from perspective of the request's source
    if payload.relationship_type == "supports":
        direction_semantic = "supports"
        related_entity = target_summary
    else:
        direction_semantic = "symmetric"
        related_entity = target_summary if (rel.source_type == payload.source_type and rel.source_id == payload.source_id) else source_summary

    return RelationshipRead(
        id=rel.id,
        relationship_type=rel.relationship_type,
        direction_semantic=direction_semantic,
        source_type=rel.source_type,
        source_id=rel.source_id,
        target_type=rel.target_type,
        target_id=rel.target_id,
        related_entity=related_entity,
        created_by_user_id=rel.created_by_user_id,
        created_at=rel.created_at,
    )


def list_relationships(
    db: Session,
    organization_id: int,
    entity_type: str,
    entity_id: int,
) -> RelationshipListResponse:
    """
    Lists all active relationships for a specified entity.
    Filters out any relationships pointing to soft-deleted entities.
    """
    # Verify focal entity exists and is active
    validate_and_resolve_entity(db, organization_id, entity_type, entity_id)

    edges = (
        db.query(DocumentRelationship)
        .filter(
            DocumentRelationship.organization_id == organization_id,
            or_(
                and_(DocumentRelationship.source_type == entity_type, DocumentRelationship.source_id == entity_id),
                and_(DocumentRelationship.target_type == entity_type, DocumentRelationship.target_id == entity_id),
            ),
        )
        .order_by(DocumentRelationship.created_at.desc(), DocumentRelationship.id.desc())
        .all()
    )

    items: list[RelationshipRead] = []
    for edge in edges:
        # Determine the other entity in the relationship
        if edge.source_type == entity_type and edge.source_id == entity_id:
            other_type = edge.target_type
            other_id = edge.target_id
            direction_semantic = "supports" if edge.relationship_type == "supports" else "symmetric"
        else:
            other_type = edge.source_type
            other_id = edge.source_id
            direction_semantic = "supported_by" if edge.relationship_type == "supports" else "symmetric"

        # Resolve the other entity; skip if soft-deleted
        try:
            _, other_summary = validate_and_resolve_entity(db, organization_id, other_type, other_id)
        except HTTPException:
            # Related record is soft-deleted or removed
            continue

        items.append(
            RelationshipRead(
                id=edge.id,
                relationship_type=edge.relationship_type,
                direction_semantic=direction_semantic,
                source_type=edge.source_type,
                source_id=edge.source_id,
                target_type=edge.target_type,
                target_id=edge.target_id,
                related_entity=other_summary,
                created_by_user_id=edge.created_by_user_id,
                created_at=edge.created_at,
            )
        )

    return RelationshipListResponse(items=items, total=len(items))


def delete_relationship(
    db: Session,
    organization_id: int,
    user_id: int,
    relationship_id: int,
) -> None:
    """
    Deletes an existing document relationship. Never touches underlying documents.
    """
    rel = (
        db.query(DocumentRelationship)
        .filter(
            DocumentRelationship.id == relationship_id,
            DocumentRelationship.organization_id == organization_id,
        )
        .first()
    )
    if not rel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relationship with ID {relationship_id} was not found.",
        )

    db.delete(rel)
    audit(db, organization_id, user_id, "DELETE_RELATIONSHIP", "document_relationships", relationship_id)
    db.commit()


def get_connected_counts_batch(
    db: Session,
    organization_id: int,
    entity_type: str,
    entity_ids: list[int],
) -> dict[int, int]:
    """
    Returns a mapping of entity_id -> confirmed connected relationships count.
    Executes in 2 fast queries across an entire page of records without N+1 query overhead.
    """
    if not entity_ids:
        return {}

    from sqlalchemy import func

    source_counts = (
        db.query(DocumentRelationship.source_id, func.count(DocumentRelationship.id))
        .filter(
            DocumentRelationship.organization_id == organization_id,
            DocumentRelationship.source_type == entity_type,
            DocumentRelationship.source_id.in_(entity_ids),
        )
        .group_by(DocumentRelationship.source_id)
        .all()
    )

    target_counts = (
        db.query(DocumentRelationship.target_id, func.count(DocumentRelationship.id))
        .filter(
            DocumentRelationship.organization_id == organization_id,
            DocumentRelationship.target_type == entity_type,
            DocumentRelationship.target_id.in_(entity_ids),
        )
        .group_by(DocumentRelationship.target_id)
        .all()
    )

    result = {eid: 0 for eid in entity_ids}
    for sid, count in source_counts:
        result[sid] = result.get(sid, 0) + count
    for tid, count in target_counts:
        result[tid] = result.get(tid, 0) + count
    return result
