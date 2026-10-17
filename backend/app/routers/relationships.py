"""
app/routers/relationships.py — Endpoints for managing document relationships.

Routes:
- POST   /api/v1/relationships: Create an explicit relationship between two documents.
- GET    /api/v1/relationships/{entity_type}/{entity_id}: List active relationships for an entity.
- DELETE /api/v1/relationships/{relationship_id}: Remove a relationship without affecting underlying records.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.schemas.relationship import (
    RelationshipCreateRequest,
    RelationshipListResponse,
    RelationshipRead,
    SuggestionListResponse,
)
from app.security import Identity, current_identity
from app.services.matching_service import find_document_suggestions
from app.services.relationship_service import (
    create_relationship,
    delete_relationship,
    list_relationships,
)
from app.tenancy import get_tenant_db
from fastapi import Query

router = APIRouter(prefix="/api/v1/relationships", tags=["Relationships"])


@router.post(
    "",
    response_model=RelationshipRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an explicit relationship between two business documents",
)
def create_doc_relationship(
    payload: RelationshipCreateRequest,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_tenant_db),
) -> RelationshipRead:
    return create_relationship(
        db=db,
        organization_id=identity.membership.organization_id,
        user_id=identity.user.id,
        payload=payload,
    )


@router.get(
    "/suggestions/{entity_type}/{entity_id}",
    response_model=SuggestionListResponse,
    summary="Suggest potentially duplicate or related business documents",
)
def get_doc_suggestions(
    entity_type: str,
    entity_id: int,
    limit: int = Query(10, ge=1, le=50, description="Max number of candidate suggestions to return"),
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_tenant_db),
) -> SuggestionListResponse:
    return find_document_suggestions(
        db=db,
        organization_id=identity.membership.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=RelationshipListResponse,
    summary="List active document relationships for a business document",
)
def get_doc_relationships(
    entity_type: str,
    entity_id: int,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_tenant_db),
) -> RelationshipListResponse:
    return list_relationships(
        db=db,
        organization_id=identity.membership.organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )


@router.delete(
    "/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a document relationship",
)
def delete_doc_relationship(
    relationship_id: int,
    identity: Identity = Depends(current_identity),
    db: Session = Depends(get_tenant_db),
) -> Response:
    delete_relationship(
        db=db,
        organization_id=identity.membership.organization_id,
        user_id=identity.user.id,
        relationship_id=relationship_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
