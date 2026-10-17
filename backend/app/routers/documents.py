from __future__ import annotations
import hashlib, json, os, logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.models import SourceFile, DocumentExtraction, ImportBatch, InvoiceRecord, InvoiceLineItem, Template, ReceiptRecord, ReceiptLineItem
from app.schemas.document import DocumentUploadResponse, DocumentExtractionResponse, DocumentConfirmRequest, DocumentParseRequest
from app.security import Identity, audit, current_identity
from app.services.storage import storage
from app.services.document_processing import (
    detect_media,
    inspect_document,
    extract,
    parse_document,
    process_document_pipeline,
)
from app.tenancy import get_tenant_db as get_db

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])
logger = logging.getLogger(__name__)

def _response(record: DocumentExtraction, filename: str | None = None) -> DocumentExtractionResponse:
    return DocumentExtractionResponse(document_id=record.source_file_id, status=record.status, document_type=record.document_type,
        provider=record.provider, ocr_status=record.ocr_status, ocr_message=record.ocr_message, processing_method=record.processing_method, fields=record.fields or {}, line_items=record.line_items or [],
        warnings=record.warnings or [], error_message=record.error_message, original_filename=filename, processed_at=record.processed_at)

def _process(source: SourceFile, db: Session, mode: str | None = None, provider: Any = None) -> DocumentExtraction:
    res = process_document_pipeline(storage.local_path(source.stored_filename), source.media_type, mode=mode, provider=provider)
    record = db.query(DocumentExtraction).filter_by(source_file_id=source.id).first()
    if not record:
        record = DocumentExtraction(source_file_id=source.id, provider=res["provider"], processing_method=res["processing_method"])
        db.add(record)
    record.provider = res["provider"]
    record.processing_method = res["processing_method"]
    record.pages = res["pages"]
    record.ocr_status = res["ocr_status"]
    record.ocr_message = res["ocr_message"]
    record.fields = res["fields"]
    record.line_items = res["line_items"]
    record.document_type = res["document_type"]
    record.warnings = res["warnings"]
    record.raw_text = res["raw_text"]
    record.status = res["status"]
    record.error_message = res["error_message"]
    return record

@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...), mode: str | None = None, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    if mode and mode not in {"auto", "vision_only", "local_ocr"}:
        raise HTTPException(422, "Invalid processing mode; must be auto, vision_only, or local_ocr.")
    if not file.filename: raise HTTPException(400, "Uploaded file must have a filename.")
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in {".jpg", ".jpeg", ".png", ".pdf"}: raise HTTPException(400, "Supported document formats are JPG, JPEG, PNG, and PDF.")
    temp = storage.new_key(True, extension); final = None; total = 0; digest = hashlib.sha256()
    try:
        with open(storage.local_path(temp), "wb") as output:
            while chunk := await file.read(65536):
                total += len(chunk)
                # The stricter initial 20 MB cap prevents reading a malicious upload unboundedly.
                if total > settings.max_document_pdf_size_mb * 1024 * 1024: raise HTTPException(413, "Document exceeds the 20 MB upload limit.")
                digest.update(chunk); output.write(chunk)
        path = storage.local_path(temp)
        if not total: raise HTTPException(400, "Uploaded document is empty.")
        media = detect_media(path.read_bytes()[:16], extension)
        limit = settings.max_document_image_size_mb if media.startswith("image/") else settings.max_document_pdf_size_mb
        if total > limit * 1024 * 1024: raise HTTPException(413, f"Document exceeds the {limit} MB upload limit.")
        pages, width, height = inspect_document(path, media, settings.max_document_pages)
        final = storage.new_key(False, extension); storage.promote(temp, final)
        source = SourceFile(organization_id=identity.membership.organization_id, original_name=file.filename, stored_filename=final, file_size=total,
            checksum=digest.hexdigest(), media_type=media, page_count=pages, image_width=width, image_height=height)
        db.add(source); db.flush(); _process(source, db, mode=mode)
        audit(db, identity.membership.organization_id, identity.user.id, "DOCUMENT_UPLOADED", "source_files", source.id)
        audit(db, identity.membership.organization_id, identity.user.id, "DOCUMENT_PROCESSED", "source_files", source.id)
        db.commit()
        return DocumentUploadResponse(document_id=source.id, filename=source.original_name, media_type=media, size=total, page_count=pages, status="needs_review")
    except HTTPException:
        db.rollback();
        for key in (temp, final):
            if key: storage.delete(key)
        raise
    except ValueError as exc:
        # Validation/readability messages are deliberately safe for users.
        db.rollback()
        for key in (temp, final):
            if key: storage.delete(key)
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        db.rollback();
        for key in (temp, final):
            if key: storage.delete(key)
        logger.exception("document_upload_failed filename=%r", file.filename)
        raise HTTPException(400, "Could not read this document.") from exc

@router.get("/{document_id}", response_model=DocumentExtractionResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    item = db.query(DocumentExtraction).filter_by(source_file_id=document_id).first()
    if not item: raise HTTPException(404, "Document not found.")
    source = db.query(SourceFile).filter_by(id=document_id).first()
    return _response(item, filename=source.original_name if source else None)

@router.get("/{document_id}/preview")
def preview(document_id: int, db: Session = Depends(get_db)):
    source = db.query(SourceFile).filter_by(id=document_id).first()
    if not source or not source.media_type.startswith(("image/", "application/pdf")): raise HTTPException(404, "Document not found.")
    path = storage.local_path(source.stored_filename)
    if not path.exists(): raise HTTPException(404, "Document is unavailable.")
    return FileResponse(path, media_type=source.media_type, filename=source.original_name, content_disposition_type="inline")

@router.get("/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    source = db.query(SourceFile).filter_by(id=document_id).first()
    if not source: raise HTTPException(404, "Document not found.")
    path = storage.local_path(source.stored_filename)
    if not path.exists(): raise HTTPException(404, "Document is unavailable.")
    return FileResponse(path, media_type=source.media_type, filename=source.original_name, content_disposition_type="attachment")

@router.post("/{document_id}/process", response_model=DocumentExtractionResponse)
def reprocess(document_id: int, mode: str | None = None, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    if mode and mode not in {"auto", "vision_only", "local_ocr"}:
        raise HTTPException(422, "Invalid processing mode; must be auto, vision_only, or local_ocr.")
    source = db.query(SourceFile).filter_by(id=document_id).first()
    if not source: raise HTTPException(404, "Document not found.")
    record = db.query(DocumentExtraction).filter_by(source_file_id=document_id).first()
    if record and record.status == "imported":
        raise HTTPException(400, "Cannot reprocess an already imported document.")
    record = _process(source, db, mode=mode)
    audit(db, identity.membership.organization_id, identity.user.id, "DOCUMENT_REPROCESSED", "source_files", source.id)
    db.commit()
    db.refresh(record)
    return _response(record, filename=source.original_name)

@router.post("/{document_id}/parse", response_model=DocumentExtractionResponse)
def parse_as(document_id: int, payload: DocumentParseRequest, db: Session = Depends(get_db)):
    if payload.document_type not in {"invoice", "receipt"}: raise HTTPException(422, "Document type must be invoice or receipt.")
    record = db.query(DocumentExtraction).filter_by(source_file_id=document_id).first()
    if not record: raise HTTPException(404, "Document not found.")
    if record.status == "imported":
        raise HTTPException(400, "Cannot re-parse an already imported document.")
    document_type, _confidence, fields, lines, warnings = parse_document(record.pages or [], payload.document_type)
    if record.fields:
        for k, v in record.fields.items():
            if k not in fields or not fields[k].get("value"):
                fields[k] = v
        if payload.document_type == "invoice":
            if not fields.get("company_name", {}).get("value") and fields.get("merchant_name", {}).get("value"):
                fields["company_name"] = fields["merchant_name"]
            if not fields.get("invoice_number", {}).get("value") and fields.get("receipt_number", {}).get("value"):
                fields["invoice_number"] = fields["receipt_number"]
            if not fields.get("invoice_date", {}).get("value") and fields.get("transaction_date", {}).get("value"):
                fields["invoice_date"] = fields["transaction_date"]
        elif payload.document_type == "receipt":
            if not fields.get("merchant_name", {}).get("value") and fields.get("company_name", {}).get("value"):
                fields["merchant_name"] = fields["company_name"]
            if not fields.get("receipt_number", {}).get("value") and fields.get("invoice_number", {}).get("value"):
                fields["receipt_number"] = fields["invoice_number"]
            if not fields.get("transaction_date", {}).get("value") and fields.get("invoice_date", {}).get("value"):
                fields["transaction_date"] = fields["invoice_date"]
        if not lines and record.line_items:
            lines = record.line_items
    record.document_type, record.fields, record.line_items, record.warnings = document_type, fields, lines, warnings
    db.commit()
    db.refresh(record)
    source = db.query(SourceFile).filter_by(id=document_id).first()
    return _response(record, filename=source.original_name if source else None)

@router.post("/{document_id}/confirm")
def confirm(document_id: int, payload: DocumentConfirmRequest, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    source = db.query(SourceFile).filter_by(id=document_id).first()
    extraction = db.query(DocumentExtraction).filter_by(source_file_id=document_id).first()
    if not source or not extraction: raise HTTPException(404, "Document not found.")

    can_acknowledge = bool(payload.acknowledge_duplicate or payload.acknowledge_warnings)
    duplicate_found = False
    duplicate_reason = ""
    conflicting_record_id = None

    # Record-level duplicate check
    if payload.document_type == "receipt":
        merchant_clean = (payload.merchant_name or "").strip()
        receipt_num_clean = (payload.receipt_number or "").strip()
        tx_date = datetime.fromisoformat(payload.transaction_date).date() if payload.transaction_date else None

        base_rec_query = (
            db.query(ReceiptRecord)
            .join(ImportBatch)
            .filter(
                ImportBatch.is_deleted.is_(False),
                ReceiptRecord.merchant_name.ilike(merchant_clean),
            )
        )

        if receipt_num_clean:
            # Printed receipt number is available: match on merchant + receipt_number
            rec_dup = base_rec_query.filter(ReceiptRecord.receipt_number == receipt_num_clean).first()
            if rec_dup:
                duplicate_found = True
                conflicting_record_id = rec_dup.id
                duplicate_reason = f"Receipt number '{receipt_num_clean}' from '{rec_dup.merchant_name}' already exists (ID #{rec_dup.id})."
        else:
            # Missing/empty receipt_number:
            # DO NOT reject based solely on merchant and amount!
            # Only match if merchant, amount, AND transaction_date match (or both dates are missing)
            if payload.total_amount is not None:
                date_filter = (ReceiptRecord.transaction_date == tx_date) if tx_date else ReceiptRecord.transaction_date.is_(None)
                rec_dup = base_rec_query.filter(
                    ReceiptRecord.total_amount == payload.total_amount,
                    date_filter,
                ).first()
                if rec_dup:
                    duplicate_found = True
                    conflicting_record_id = rec_dup.id
                    date_info = f" on {tx_date}" if tx_date else ""
                    duplicate_reason = f"Matching transaction from '{rec_dup.merchant_name}' for {payload.total_amount}{date_info} already exists (ID #{rec_dup.id})."

    elif not duplicate_found and payload.document_type == "invoice":
        comp_clean = (payload.company_name or "").strip()
        inv_clean = (payload.invoice_number or "").strip()
        inv_dup = (
            db.query(InvoiceRecord)
            .join(ImportBatch)
            .filter(
                ImportBatch.is_deleted.is_(False),
                InvoiceRecord.company_name.ilike(comp_clean),
                InvoiceRecord.invoice_number == inv_clean,
            )
            .first()
        )
        if inv_dup:
            duplicate_found = True
            conflicting_record_id = inv_dup.id
            duplicate_reason = f"Invoice number '{inv_clean}' from '{inv_dup.company_name}' already exists (ID #{inv_dup.id})."

    if duplicate_found and not can_acknowledge:
        conflict_headers = {}
        if conflicting_record_id:
            conflict_headers["X-Duplicate-Record-Id"] = str(conflicting_record_id)
            conflict_headers["X-Duplicate-Document-Type"] = payload.document_type
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Possible duplicate {payload.document_type} found. {duplicate_reason}",
            headers=conflict_headers or None,
        )

    template_name = "Document receipt" if payload.document_type == "receipt" else "Document invoice"
    template = db.query(Template).filter_by(name=template_name, file_type="document").first()
    if not template:
        template = Template(organization_id=identity.membership.organization_id, name=template_name, description="Internal deterministic document import template", template_type="invoice", file_type="document", worksheet="Document")
        db.add(template); db.flush()
    batch = ImportBatch(organization_id=identity.membership.organization_id, source_file_id=source.id, template_id=template.id, status="imported", record_count=1, warning_count=len(extraction.warnings or []))
    db.add(batch); db.flush()

    raw_payload = payload.model_dump(mode="json")
    if duplicate_found and can_acknowledge:
        raw_payload["duplicate_acknowledged"] = True
        raw_payload["duplicate_warning_reason"] = duplicate_reason
        raw_payload["conflicting_record_id"] = conflicting_record_id

    raw_data = json.dumps({"document_extraction": extraction.fields, "corrected": raw_payload}, default=str)
    if payload.document_type == "receipt":
        receipt = ReceiptRecord(
            batch_id=batch.id,
            merchant_name=payload.merchant_name,
            receipt_number=payload.receipt_number or "",
            transaction_date=datetime.fromisoformat(payload.transaction_date).date() if payload.transaction_date else None,
            transaction_time=payload.transaction_time,
            subtotal=payload.subtotal,
            tax_amount=payload.tax_amount,
            total_amount=payload.total_amount,
            currency=payload.currency,
            direction=payload.direction or "unclassified",
            payment_method=payload.payment_method,
            store_address=payload.store_address,
            cash_paid=payload.cash_paid,
            change_amount=payload.change_amount,
            raw_data=raw_data,
        )
        db.add(receipt); db.flush()
        for index, line in enumerate(payload.line_items, 1): db.add(ReceiptLineItem(receipt_id=receipt.id, source_row_number=index, description=line.get("description"), quantity=line.get("quantity"), unit_price=line.get("unit_price"), tax_rate=line.get("tax_rate"), tax_amount=line.get("tax_amount"), amount=line.get("amount"), raw_data=json.dumps(line, default=str)))
        record_id = receipt.id
    else:
        invoice = InvoiceRecord(batch_id=batch.id, company_name=payload.company_name, invoice_number=payload.invoice_number, invoice_date=datetime.fromisoformat(payload.invoice_date).date() if payload.invoice_date else None, total_amount=payload.total_amount, currency=payload.currency, direction=payload.direction or "unclassified", source_worksheet="Document", raw_data=raw_data)
        db.add(invoice); db.flush()
        for index, line in enumerate(payload.line_items, 1): db.add(InvoiceLineItem(invoice_id=invoice.id, source_row_number=index, description=line.get("description"), quantity=line.get("quantity"), unit_price=line.get("unit_price"), tax_rate=line.get("tax_rate"), tax_amount=line.get("tax_amount"), amount=line.get("amount"), raw_data=json.dumps(line, default=str)))
        record_id = invoice.id
    extraction.status = "imported"; audit(db, identity.membership.organization_id, identity.user.id, "DOCUMENT_IMPORT_CONFIRMED", "source_files", source.id); db.commit()
    return {"batch_id": batch.id, "record_id": record_id, "document_type": payload.document_type, "status": "imported"}
