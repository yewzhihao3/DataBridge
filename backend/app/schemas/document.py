from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator

class DocumentField(BaseModel):
    value: str | None = None
    confidence: str = "low"
    page: int | None = None
    text: str | None = None

class DocumentUploadResponse(BaseModel):
    document_id: int
    filename: str
    media_type: str
    size: int
    page_count: int | None = None
    status: str

class DocumentExtractionResponse(BaseModel):
    document_id: int
    status: str
    document_type: str
    provider: str
    ocr_status: str
    ocr_message: str | None = None
    processing_method: str
    fields: dict[str, DocumentField]
    line_items: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    processed_at: datetime

class DocumentConfirmRequest(BaseModel):
    document_type: str = "invoice"
    company_name: str | None = Field(None, max_length=255)
    invoice_number: str | None = Field(None, max_length=100)
    invoice_date: str | None = None
    merchant_name: str | None = Field(None, max_length=255)
    receipt_number: str | None = Field(None, max_length=100)
    transaction_date: str | None = None
    transaction_time: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = Field(None, max_length=10)
    line_items: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def identifiers(self):
        required = ("merchant_name", "receipt_number") if self.document_type == "receipt" else ("company_name", "invoice_number")
        if self.document_type not in {"invoice", "receipt"}: raise ValueError("Select Invoice or Receipt before importing.")
        if any(not (getattr(self, field) or "").strip() for field in required): raise ValueError(f"{required[0]} and {required[1]} are required.")
        return self

class DocumentParseRequest(BaseModel):
    document_type: str
