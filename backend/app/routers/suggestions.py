"""Read-only analysis of already uploaded workbooks."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
from app.config import settings
from app.services.storage import storage
from app.tenancy import get_tenant_db as get_db
from app.models.source_file import SourceFile
from app.models.template import Template
from app.schemas.suggestion import AnalyzeRequest, AnalyzeResponse
from app.services.workbook_profiler import profile_workbook
from app.services.workbook_inspector import WorkbookInspectionError
from app.services.structure_detector import analyze_sheet, suggest_worksheet
from app.services.template_matcher import match_templates

router = APIRouter(prefix="/api/v1/suggestions", tags=["Suggestions"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest, db: Session = Depends(get_db)):
    source = db.get(SourceFile, request.file_id)
    if not source:
        raise HTTPException(404, "Uploaded file not found.")
    path = storage.local_path(source.stored_filename)
    if not path.is_file():
        raise HTTPException(404, "Uploaded file not found on disk.")
    try:
        profiles = profile_workbook(path, settings.max_file_size_mb)
    except (WorkbookInspectionError, OSError) as exc:
        raise HTTPException(400, "Workbook analysis unavailable; manual mapping remains available.") from exc
    analyses = [analyze_sheet(p) for p in profiles]
    suggested = suggest_worksheet(profiles, analyses)
    selected = request.worksheet or suggested
    analysis = next((a for a in analyses if a.worksheet == selected), None)
    if not analysis:
        raise HTTPException(404, "Worksheet not found.")
    templates = db.query(Template).options(selectinload(Template.field_mappings)).all()
    warnings = ["Suggestions require review. Existing extraction and validation remain authoritative."]
    if any(p.metadata.truncated for p in profiles):
        warnings.append("Analysis is limited to the first 2,000 rows and 100 columns of the first 30 sheets; profile counts describe scanned cells only.")
    if any(p.metadata.formula_cells for p in profiles):
        warnings.append("Formulas are structural hints only; analysis does not calculate them. Preview checks cached values.")
    return AnalyzeResponse(file_id=request.file_id, suggested_worksheet=suggested, selected_worksheet=selected,
        profiles=[p.metadata for p in profiles], analysis=analysis,
        template_matches=match_templates(analysis, templates), warnings=warnings)
