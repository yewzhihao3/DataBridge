from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class BatchImportCreate(BaseModel):
    file_ids: list[int] = Field(min_length=2, max_length=50)

class BatchImportFileRead(BaseModel):
    id: int
    source_file_id: int
    filename: str
    status: str
    detected_type: str | None = None
    processing_method: str | None = None
    template_id: int | None = None
    template_name: str | None = None
    import_batch_id: int | None = None
    issues: list[dict] = Field(default_factory=list)
    error_message: str | None = None
    model_config = ConfigDict(from_attributes=True)

class BatchImportSummary(BaseModel):
    total: int = 0
    ready: int = 0
    review: int = 0
    duplicate: int = 0
    failed: int = 0
    imported: int = 0
    skipped: int = 0

class BatchImportDetail(BaseModel):
    id: int
    status: str
    summary: BatchImportSummary
    files: list[BatchImportFileRead]
    created_at: datetime
    completed_at: datetime | None = None

