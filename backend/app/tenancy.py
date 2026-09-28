"""Tenant query boundary shared by every business router.

Loader criteria cover entities, aggregates, aliases, eager/lazy relationships and
Session.get. A fresh request Session prevents identity-map cross-workspace reuse.
Raw SQL/bulk writes are prohibited in this boundary.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria
from app.database import get_db
from app.security import Identity, current_identity, audit
from app.models import Template, TemplateFieldMapping, SourceFile, ImportBatch, InvoiceRecord, InvoiceLineItem, ValidationErrorRecord


def get_tenant_db(identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    db.info["organization_id"] = identity.membership.organization_id
    db.info["user_id"] = identity.user.id
    return db


@event.listens_for(Session, "do_orm_execute")
def scope_queries(state):
    org = state.session.info.get("organization_id")
    if org is None:
        return
    if not state.is_select or not state.is_orm_statement:
        raise RuntimeError("Tenant sessions require ORM queries and instance writes")
    templates = Template.__table__.alias("tenant_templates")
    batches = ImportBatch.__table__.alias("tenant_batches")
    invoices = InvoiceRecord.__table__.alias("tenant_invoices")
    criteria = [
        (Template, Template.organization_id == org),
        (SourceFile, SourceFile.organization_id == org),
        (ImportBatch, ImportBatch.organization_id == org),
        (TemplateFieldMapping, TemplateFieldMapping.template_id.in_(select(templates.c.id).where(templates.c.organization_id == org))),
        (InvoiceRecord, InvoiceRecord.batch_id.in_(select(batches.c.id).where(batches.c.organization_id == org))),
        (ValidationErrorRecord, ValidationErrorRecord.batch_id.in_(select(batches.c.id).where(batches.c.organization_id == org))),
        (InvoiceLineItem, InvoiceLineItem.invoice_id.in_(select(invoices.c.id).select_from(invoices.join(batches, invoices.c.batch_id == batches.c.id)).where(batches.c.organization_id == org))),
    ]
    for model, condition in criteria:
        state.statement = state.statement.options(with_loader_criteria(model, condition, include_aliases=True))


@event.listens_for(Session, "before_flush")
def scope_writes(db, context, instances):
    org = db.info.get("organization_id")
    if org is None:
        return
    for obj in list(db.new) + list(db.dirty) + list(db.deleted):
        if isinstance(obj, (Template, SourceFile, ImportBatch)):
            if obj in db.new and obj.organization_id is None:
                obj.organization_id = org
            if obj.organization_id != org:
                raise HTTPException(404, "Resource not found")
        parents = []
        if isinstance(obj, ImportBatch):
            parents = [(SourceFile, obj.source_file_id), (Template, obj.template_id)]
        elif isinstance(obj, TemplateFieldMapping):
            parents = [(Template, obj.template_id)]
        elif isinstance(obj, (InvoiceRecord, ValidationErrorRecord)):
            parents = [(ImportBatch, obj.batch_id)]
        elif isinstance(obj, InvoiceLineItem):
            parents = [(InvoiceRecord, obj.invoice_id)]
        for parent, pk in parents:
            if pk is not None and db.query(parent).filter(parent.id == pk).first() is None:
                raise HTTPException(404, "Resource not found")
        if isinstance(obj, (Template, ImportBatch, InvoiceRecord)) and db.info.get("user_id"):
            if obj in db.new:
                action = {Template: "CREATE_TEMPLATE", ImportBatch: "CONFIRM_IMPORT", InvoiceRecord: "CREATE_INVOICE"}[type(obj)]
            elif obj in db.deleted or (isinstance(obj, ImportBatch) and obj.is_deleted):
                action = "DELETE_TEMPLATE" if isinstance(obj, Template) else "DELETE_IMPORT"
            elif db.is_modified(obj, include_collections=True):
                action = "UPDATE_TEMPLATE" if isinstance(obj, Template) else "EDIT_INVOICE"
            else:
                continue
            entry = audit(db, org, db.info["user_id"], action, obj.__tablename__, obj.id)
            if obj in db.new:
                db.info.setdefault("audit_entity_ids", []).append((entry, obj))


@event.listens_for(Session, "after_flush_postexec")
def assign_audit_ids(db, context):
    for entry, obj in db.info.pop("audit_entity_ids", []):
        entry.entity_id = obj.id


@event.listens_for(Session, "after_rollback")
def discard_pending_audit_ids(db):
    db.info.pop("audit_entity_ids", None)
