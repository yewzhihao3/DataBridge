"""
app/routers/templates.py — Template management endpoints (CRUD).

──────────────────────────────────────────────────────────────────────────────
Features:
- Full CRUD for extraction templates with nested field mappings.
- HTTP 201 Created on resource creation.
- HTTP 409 Conflict on duplicate template names.
- Automatic cascade deletion of child field mappings.
- Automatic updating of updated_at timestamps.
- GET /canonical-fields: returns the list of supported canonical target fields.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.constants import CANONICAL_INVOICE_FIELDS_LIST
from app.database import get_db
from app.models.template import Template, TemplateFieldMapping
from app.schemas.template import (
    TemplateCreate,
    TemplateListItem,
    TemplateRead,
    TemplateUpdate,
)

router = APIRouter(prefix="/api/v1/templates", tags=["Templates"])

@router.get(
    "/canonical-fields",
    response_model=list[str],
    summary="List all supported canonical invoice field names",
)
def list_canonical_fields() -> list[str]:
    """
    Returns the list of canonical target field names supported by InvoiceRecord.
    Use these as `target_field` values in template field mappings to route
    extracted data directly into the corresponding database column.
    Any mapping whose target_field is NOT in this list will be stored as a
    custom field in the invoice record's `custom_fields` JSON column.
    """
    return CANONICAL_INVOICE_FIELDS_LIST


@router.post(
    "",
    response_model=TemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new extraction template",
)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
) -> TemplateRead:
    """
    Creates a new template along with its initial field mappings.
    Returns 409 Conflict if a template with the same name already exists.
    """
    # 1. Check for duplicate name
    existing = db.query(Template).filter(Template.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A template with the name '{payload.name}' already exists.",
        )

    # 2. Build model hierarchy
    template = Template(
        name=payload.name,
        description=payload.description,
        file_type=payload.file_type,
        worksheet=payload.worksheet,
        header_row=payload.header_row,
        data_start_row=payload.data_start_row,
        date_format=payload.date_format,
    )

    for mapping in payload.field_mappings:
        template.field_mappings.append(
            TemplateFieldMapping(
                field_name=mapping.field_name,
                target_field=mapping.target_field,
                mapping_type=mapping.mapping_type,
                cell_ref=mapping.cell_ref,
                column_ref=mapping.column_ref,
                is_required=mapping.is_required,
                data_type=mapping.data_type,
            )
        )

    try:
        db.add(template)
        db.commit()
        db.refresh(template)
        return template  # type: ignore[return-value]
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Could not create template due to a constraint conflict: {exc.orig}",
        ) from exc


@router.get(
    "",
    response_model=list[TemplateListItem],
    summary="List all templates",
)
def list_templates(db: Session = Depends(get_db)) -> list[TemplateListItem]:
    """
    Retrieves a list of all configured templates with mapping summary counts.
    """
    templates = (
        db.query(Template)
        .options(joinedload(Template.field_mappings))
        .order_by(Template.name)
        .all()
    )

    results: list[TemplateListItem] = []
    for t in templates:
        results.append(
            TemplateListItem(
                id=t.id,
                name=t.name,
                description=t.description,
                file_type=t.file_type,
                worksheet=t.worksheet,
                mapping_count=len(t.field_mappings),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
        )
    return results


@router.get(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Get a template by ID",
)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
) -> TemplateRead:
    """
    Retrieves a single template with all its child field mappings.
    """
    template = (
        db.query(Template)
        .options(joinedload(Template.field_mappings))
        .filter(Template.id == template_id)
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {template_id} was not found.",
        )
    return template  # type: ignore[return-value]


@router.put(
    "/{template_id}",
    response_model=TemplateRead,
    summary="Update a template",
)
def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
) -> TemplateRead:
    """
    Updates template fields and optionally replaces all field mappings.
    """
    template = (
        db.query(Template)
        .options(joinedload(Template.field_mappings))
        .filter(Template.id == template_id)
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {template_id} was not found.",
        )

    # If updating name, check for collisions
    if payload.name and payload.name != template.name:
        collision = db.query(Template).filter(Template.name == payload.name).first()
        if collision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A template with the name '{payload.name}' already exists.",
            )
        template.name = payload.name

    # Update base fields if provided
    if payload.description is not None:
        template.description = payload.description
    if payload.worksheet is not None:
        template.worksheet = payload.worksheet
    if payload.header_row is not None:
        template.header_row = payload.header_row
    if payload.data_start_row is not None:
        template.data_start_row = payload.data_start_row
    if payload.date_format is not None:
        template.date_format = payload.date_format

    # Replace field mappings if supplied in payload
    if payload.field_mappings is not None:
        # Delete old mappings first and flush so unique constraints don't collide
        template.field_mappings.clear()
        db.flush()

        for m in payload.field_mappings:
            template.field_mappings.append(
                TemplateFieldMapping(
                    field_name=m.field_name,
                    target_field=m.target_field,
                    mapping_type=m.mapping_type,
                    cell_ref=m.cell_ref,
                    column_ref=m.column_ref,
                    is_required=m.is_required,
                    data_type=m.data_type,
                )
            )

    template.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(template)
        return template  # type: ignore[return-value]
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Update failed due to constraint conflict: {exc.orig}",
        ) from exc


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a template",
)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """
    Deletes a template and all its associated field mappings.
    """
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {template_id} was not found.",
        )

    db.delete(template)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
