"""app/schemas/relationship.py — Pydantic schemas for document relationships and suggestions."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["invoice", "receipt", "source_file"]
RelationshipType = Literal["related_to", "supports"]
MatchCategory = Literal["exact_file_duplicate", "possible_duplicate", "possible_related"]


class RelationshipCreateRequest(BaseModel):
    """Payload to create an explicit relationship between two documents."""
    source_type: EntityType = Field(..., description="Source entity type ('invoice', 'receipt', 'source_file')")
    source_id: int = Field(..., ge=1, description="Primary key ID of the source entity")
    target_type: EntityType = Field(..., description="Target entity type ('invoice', 'receipt', 'source_file')")
    target_id: int = Field(..., ge=1, description="Primary key ID of the target entity")
    relationship_type: RelationshipType = Field(
        default="related_to",
        description="Type of relationship: 'related_to' (symmetric) or 'supports' (directional: source supports target)",
    )


class RelatedDocumentSummary(BaseModel):
    """Minimal display summary of a related document or source file."""
    model_config = ConfigDict(from_attributes=True)

    entity_type: EntityType
    entity_id: int
    document_number: str | None = None
    counterparty: str | None = None
    document_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    direction: str | None = None
    filename: str | None = None
    media_type: str | None = None
    file_size: int | None = None
    source_file_id: int | None = None


class RelationshipRead(BaseModel):
    """Full detail of a document relationship from the perspective of an entity or router."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    relationship_type: RelationshipType
    direction_semantic: str = Field(
        ...,
        description="'symmetric' for related_to, or 'supports' / 'supported_by' depending on perspective",
    )
    source_type: EntityType
    source_id: int
    target_type: EntityType
    target_id: int
    related_entity: RelatedDocumentSummary
    created_by_user_id: int | None = None
    created_at: datetime


class RelationshipListResponse(BaseModel):
    """Paginated or listed relationships for an entity."""
    items: list[RelationshipRead]
    total: int


class SuggestionItem(BaseModel):
    """A candidate related or duplicate document suggestion with explainable evidence."""
    model_config = ConfigDict(from_attributes=True)

    candidate_type: EntityType
    candidate_id: int
    match_category: MatchCategory = Field(
        ...,
        description="'exact_file_duplicate', 'possible_duplicate', or 'possible_related'",
    )
    heuristic_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Uncalibrated heuristic ranking score between 0.0 and 1.0 (not a probability)",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Structured, explainable reasons why this candidate was suggested",
    )
    candidate_summary: RelatedDocumentSummary
    is_already_linked: bool = Field(
        default=False,
        description="True if an explicit relationship already links these two entities",
    )


class SuggestionListResponse(BaseModel):
    """List of candidate suggestions for an entity."""
    target_type: EntityType
    target_id: int
    suggestions: list[SuggestionItem]
    total: int
