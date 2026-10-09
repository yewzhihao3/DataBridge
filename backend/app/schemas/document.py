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

class DocumentValidationItem(BaseModel):
    severity: str  # "error" | "warning" | "info" | "success"
    category: str  # "amounts" | "identifiers" | "dates" | "currency" | "engine" | "general"
    message: str
    details: str | None = None

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
    validation_items: list[DocumentValidationItem] = Field(default_factory=list)
    ai_notes: list[str] = Field(default_factory=list)
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
    payment_method: str | None = Field(None, max_length=50)
    store_address: str | None = Field(None, max_length=500)
    cash_paid: Decimal | None = None
    change_amount: Decimal | None = None
    service_charge: Decimal | None = None
    discount_amount: Decimal | None = None
    rounding_adjustment: Decimal | None = None
    line_items: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def identifiers(self):
        if self.document_type not in {"invoice", "receipt"}:
            raise ValueError("Select Invoice or Receipt before importing.")
        if self.document_type == "invoice":
            if not (self.company_name or "").strip() or not (self.invoice_number or "").strip():
                raise ValueError("company_name and invoice_number are required.")
        elif self.document_type == "receipt":
            if not (self.merchant_name or "").strip():
                raise ValueError("merchant_name is required.")
        return self

class DocumentParseRequest(BaseModel):
    document_type: str
