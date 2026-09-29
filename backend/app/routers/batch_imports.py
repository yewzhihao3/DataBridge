"""M13 batch orchestration; extraction and persistence stay in existing services."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.config import settings
from app.models import BatchImportFile, BatchImportSession, SourceFile, Template
from app.schemas.batch_import import BatchImportCreate, BatchImportDetail, BatchImportFileRead, BatchImportSummary
from app.schemas.import_batch import ImportConfirmRequest
from app.schemas.extraction import ExtractionPreviewResponse, ExtractionRequest
from app.security import Identity, audit, current_identity
from app.services.storage import storage
from app.services.workbook_profiler import profile_workbook
from app.services.structure_detector import analyze_sheet, suggest_worksheet
from app.services.template_matcher import match_templates
from app.tenancy import get_tenant_db as get_db
from app.routers.imports import confirm_import, extract_preview

router = APIRouter(prefix="/api/v1/batch-imports", tags=["Batch imports"])

def _summary(files):
    counts = {key: 0 for key in ("ready", "review", "duplicate", "failed", "imported", "skipped")}
    for item in files:
        key = item.status.lower()
        if key in counts: counts[key] += 1
    return BatchImportSummary(total=len(files), **counts)

def _detail(session):
    return BatchImportDetail(id=session.id, status=session.status, created_at=session.created_at,
        completed_at=session.completed_at, summary=_summary(session.files), files=[BatchImportFileRead(
            id=item.id, source_file_id=item.source_file_id, filename=item.source_file.original_name,
            status=item.status, detected_type=item.detected_type, processing_method=item.processing_method,
            template_id=item.template_id, template_name=item.template.name if item.template else None,
            import_batch_id=item.import_batch_id, issues=item.issues or [], error_message=item.error_message) for item in session.files])

def _analyze(item, templates):
    item.status = "analyzing"
    try:
        profiles = profile_workbook(storage.local_path(item.source_file.stored_filename), settings.max_file_size_mb)
        analyses = [analyze_sheet(profile) for profile in profiles]
        selected = suggest_worksheet(profiles, analyses)
        analysis = next((value for value in analyses if value.worksheet == selected), None)
        if not analysis or not analysis.suggested_template_type:
            item.status, item.processing_method = "review", "unresolved"
            item.issues = [{"message": "Workbook structure needs manual mapping."}]
            return
        item.detected_type = analysis.suggested_template_type
        matches = match_templates(analysis, templates)
        strong = next((match for match in matches if match.confidence == "high"), None)
        if strong:
            item.template_id, item.status, item.processing_method = strong.template_id, "ready", "saved_template"
            item.issues = []
        else:
            item.status, item.processing_method = "review", "smart_mapping"
            item.issues = [{"message": "Suggested mapping requires review before import."}]
    except Exception:
        item.status, item.processing_method = "failed", "unresolved"
        item.error_message = "Workbook analysis failed. Check that this is a valid, unencrypted XLSX file."

@router.post("", response_model=BatchImportDetail, status_code=201)
def create_batch(payload: BatchImportCreate, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    if len(set(payload.file_ids)) != len(payload.file_ids):
        raise HTTPException(422, "Each source file may be included once per batch.")
    if len(payload.file_ids) > settings.max_batch_file_count:
        raise HTTPException(422, f"A batch may include at most {settings.max_batch_file_count} files.")
    sources = db.query(SourceFile).filter(SourceFile.id.in_(payload.file_ids)).all()
    if len(sources) != len(payload.file_ids): raise HTTPException(404, "One or more uploaded files were not found.")
    by_id = {source.id: source for source in sources}
    session = BatchImportSession(organization_id=identity.membership.organization_id, created_by_user_id=identity.user.id, status="analyzing")
    session.files = [BatchImportFile(source_file=by_id[file_id], status="uploading") for file_id in payload.file_ids]
    db.add(session); db.flush()
    templates = db.query(Template).options(joinedload(Template.field_mappings)).all()
    for item in session.files: _analyze(item, templates)
    session.status = "review" if any(item.status in {"review", "failed", "duplicate"} for item in session.files) else "ready"
    audit(db, identity.membership.organization_id, identity.user.id, "BATCH_UPLOAD_CREATED", "batch_import_sessions", session.id)
    db.commit(); db.refresh(session)
    return _detail(session)

@router.get("", response_model=list[BatchImportDetail])
def list_batches(db: Session = Depends(get_db)):
    sessions = db.query(BatchImportSession).options(
        joinedload(BatchImportSession.files).joinedload(BatchImportFile.source_file),
        joinedload(BatchImportSession.files).joinedload(BatchImportFile.template),
    ).order_by(BatchImportSession.created_at.desc()).all()
    return [_detail(session) for session in sessions]

@router.get("/{session_id}", response_model=BatchImportDetail)
def get_batch(session_id: int, db: Session = Depends(get_db)):
    session = db.query(BatchImportSession).options(joinedload(BatchImportSession.files).joinedload(BatchImportFile.source_file), joinedload(BatchImportSession.files).joinedload(BatchImportFile.template)).filter(BatchImportSession.id == session_id).first()
    if not session: raise HTTPException(404, "Batch import session not found.")
    return _detail(session)

@router.delete("/{session_id}/files/{file_id}", response_model=BatchImportDetail)
def remove_file(session_id: int, file_id: int, db: Session = Depends(get_db)):
    item = db.query(BatchImportFile).filter(BatchImportFile.session_id == session_id, BatchImportFile.source_file_id == file_id, BatchImportFile.status.notin_(["imported"])).first()
    if not item: raise HTTPException(404, "Pending batch file not found.")
    item.status = "skipped"; item.issues = [{"message": "Removed from this batch before import."}]
    db.commit(); return get_batch(session_id, db)

@router.post("/{session_id}/analyze", response_model=BatchImportDetail)
def retry_analysis(session_id: int, db: Session = Depends(get_db)):
    session = db.query(BatchImportSession).options(joinedload(BatchImportSession.files).joinedload(BatchImportFile.source_file)).filter(BatchImportSession.id == session_id).first()
    if not session: raise HTTPException(404, "Batch import session not found.")
    templates = db.query(Template).options(joinedload(Template.field_mappings)).all()
    for item in session.files:
        if item.status in {"failed", "review"}: _analyze(item, templates)
    db.commit(); return get_batch(session_id, db)

@router.post("/{session_id}/import-ready", response_model=BatchImportDetail)
def import_ready(session_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    session = db.query(BatchImportSession).options(joinedload(BatchImportSession.files).joinedload(BatchImportFile.source_file)).filter(BatchImportSession.id == session_id).first()
    if not session: raise HTTPException(404, "Batch import session not found.")
    for item in session.files:
        if item.status != "ready" or not item.template_id: continue
        item.status = "importing"; db.commit()
        try:
            result = confirm_import(ImportConfirmRequest(file_id=item.source_file_id, template_id=item.template_id), db)
            item.import_batch_id, item.status = result.id, "imported"; item.issues = []
        except HTTPException as exc:
            detail = str(exc.detail)
            item.status = "duplicate" if "duplicate" in detail.lower() else ("review" if "warning" in detail.lower() else "failed")
            item.error_message = detail
        db.commit()
    session.status, session.completed_at = "completed", datetime.utcnow()
    audit(db, identity.membership.organization_id, identity.user.id, "BATCH_IMPORT_COMPLETED", "batch_import_sessions", session.id)
    db.commit(); return get_batch(session_id, db)

def _review_item(session_id: int, file_id: int, db: Session):
    item = db.query(BatchImportFile).filter(BatchImportFile.session_id == session_id, BatchImportFile.source_file_id == file_id).first()
    if not item: raise HTTPException(404, "Batch review item not found.")
    if item.status not in {"review", "imported"} or not item.template_id:
        raise HTTPException(409, "This file is not available for warning review.")
    return item

@router.get("/{session_id}/files/{file_id}/review", response_model=ExtractionPreviewResponse)
def review_preview(session_id: int, file_id: int, db: Session = Depends(get_db)):
    item = _review_item(session_id, file_id, db)
    return extract_preview(ExtractionRequest(file_id=item.source_file_id, template_id=item.template_id), db)

@router.post("/{session_id}/files/{file_id}/accept-warnings", response_model=BatchImportDetail)
def accept_warnings(session_id: int, file_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    item = _review_item(session_id, file_id, db)
    if item.status == "imported": return get_batch(session_id, db)
    item.status = "importing"; db.commit()
    try:
        result = confirm_import(ImportConfirmRequest(file_id=item.source_file_id, template_id=item.template_id, acknowledge_warnings=True), db)
        item.import_batch_id, item.status, item.error_message, item.issues = result.id, "imported", None, []
        audit(db, identity.membership.organization_id, identity.user.id, "BATCH_REVIEW_ACCEPTED", "batch_import_files", item.id)
        db.commit()
    except HTTPException as exc:
        item.status = "duplicate" if "duplicate" in str(exc.detail).lower() else "review"
        item.error_message = "This file still needs review: " + ("possible duplicate found." if item.status == "duplicate" else "import could not be confirmed.")
        db.commit()
        raise
    return get_batch(session_id, db)
