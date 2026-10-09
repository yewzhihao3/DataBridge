"""Bounded, deterministic document ingestion helpers.  OCR is deliberately optional."""
from __future__ import annotations
import io, re, shutil
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

IMAGE_MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}
PDF_MAGIC = b"%PDF-"

def detect_media(data: bytes, extension: str) -> str:
    media = next((kind for sig, kind in IMAGE_MAGIC.items() if data.startswith(sig)), None)
    if data.startswith(PDF_MAGIC): media = "application/pdf"
    allowed = {".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".png":"image/png", ".pdf":"application/pdf"}
    if not media or allowed.get(extension.lower()) != media:
        raise ValueError("File extension and document signature do not match.")
    return media

def inspect_document(path: Path, media: str, max_pages: int) -> tuple[int, int | None, int | None]:
    if media.startswith("image/"):
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.width < 80 or image.height < 80: raise ValueError("Image resolution is too low to read reliably.")
            return 1, image.width, image.height
    from pypdf import PdfReader
    reader = PdfReader(str(path), strict=True)
    if reader.is_encrypted: raise ValueError("Encrypted PDFs are not supported.")
    if not reader.pages or len(reader.pages) > max_pages: raise ValueError(f"PDF must contain between 1 and {max_pages} pages.")
    return len(reader.pages), None, None

def _confidence(value: str | None) -> str:
    return "high" if value else "low"

def _find(text: str, labels: list[str], pattern: str) -> tuple[str | None, str | None]:
    for line in text.splitlines():
        if any(label in line.lower() for label in labels):
            found = re.search(pattern, line, re.I)
            if found: return found.group(1).strip(), line.strip()
    return None, None

def parse_invoice(pages: list[dict[str, Any]]) -> tuple[dict[str, dict], list[dict], list[str]]:
    text = "\n".join(page.get("text", "") for page in pages)
    fields: dict[str, dict] = {}
    def add(name, labels, pattern):
        value, source = _find(text, labels, pattern)
        fields[name] = {"value": value, "confidence": _confidence(value), "page": 1 if value else None, "text": source}
    add("invoice_number", ["invoice no", "invoice #", "invoice number", "inv no"], r"(?:no\.?|#|number)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]+)")
    add("invoice_date", ["invoice date", "date issued", "date"], r"[:\-]?\s*(\d{1,4}[\/\-. ][A-Za-z]{0,3}\d{0,4}[A-Za-z0-9\-/ ]*)")
    amount, source = _find(text, ["grand total", "total due", "total"], r"(?:RM|MYR|USD|SGD|EUR|\$|€)?\s*([0-9][0-9, .]+)")
    fields["total_amount"] = {"value": amount, "confidence": _confidence(amount), "page": 1 if amount else None, "text": source}
    currency = "MYR" if re.search(r"\b(RM|MYR)\b", text, re.I) else "USD" if "$" in text or re.search(r"\bUSD\b", text, re.I) else "EUR" if "€" in text else "SGD" if re.search(r"\bSGD\b", text, re.I) else None
    fields["currency"] = {"value": currency, "confidence": _confidence(currency), "page": 1 if currency else None, "text": currency}
    company = next((line.strip() for line in text.splitlines() if len(line.strip()) > 3 and not re.search(r"invoice|date|total|tax|bill to", line, re.I)), None)
    fields["company_name"] = {"value": company, "confidence": "medium" if company else "low", "page": 1 if company else None, "text": company}
    warnings = [f"{key.replace('_', ' ')} needs review." for key, field in fields.items() if field["confidence"] == "low"]
    return fields, [], warnings

def detect_document_type(pages: list[dict[str, Any]]) -> tuple[str, str]:
    text = "\n".join(page.get("text", "") for page in pages).lower()
    receipt_signals = ("receipt", "thank you", "cash", "change", "amount paid", "subtotal")
    invoice_signals = ("invoice", "bill to", "due date", "invoice date", "payment terms")
    receipt_score = sum(1 for signal in receipt_signals if signal in text)
    invoice_score = sum(1 for signal in invoice_signals if signal in text)
    if receipt_score >= 2 and receipt_score > invoice_score: return "receipt", "high" if receipt_score >= 3 else "medium"
    if invoice_score >= 2 and invoice_score >= receipt_score: return "invoice", "high" if invoice_score >= 3 else "medium"
    return "unknown", "low"

def _amount(value: str) -> str:
    return value.replace(",", "").replace(" ", "")

def parse_receipt(pages: list[dict[str, Any]]) -> tuple[dict[str, dict], list[dict], list[str]]:
    text = "\n".join(page.get("text", "") for page in pages)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fields: dict[str, dict] = {}
    def field(name: str, value: str | None, source: str | None, confidence="high"):
        fields[name] = {"value": value, "confidence": confidence if value else "low", "page": 1 if value else None, "text": source}

    number, number_source = _find(text, ["receipt #", "receipt no", "receipt number", "transaction #", "txn #", "order #"], r"(?:receipt|transaction|txn|order)?\s*(?:#|no\.?|number)?\s*[:\-]?\s*(#[A-Z0-9-]+|[A-Z0-9][A-Z0-9-]+)")
    field("receipt_number", number, number_source)
    date_match = re.search(r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})(?:\s+(\d{1,2}:\d{2})\s*(am|pm)?)?", text, re.I)
    field("transaction_date", date_match.group(1) if date_match else None, date_match.group(0) if date_match else None)
    field("transaction_time", ((date_match.group(2) or "") + (date_match.group(3) or "")).strip() if date_match and date_match.group(2) else None, date_match.group(0) if date_match else None)
    merchant = next((line for line in lines[:6] if len(line) > 3 and not re.search(r"receipt|date|tel|phone|road|street|avenue|thank", line, re.I)), None)
    field("merchant_name", merchant, merchant, "medium")
    labels = {
        "subtotal": ["subtotal", "sub total"], "tax_amount": ["tax", "gst", "sst", "vat"],
        "total_amount": ["grand total", "amount paid", "total"], "cash_paid": ["cash paid", "cash"], "change_amount": ["change"],
    }
    for name, match_labels in labels.items():
        value, source = _find(text, match_labels, r"(?:RM|MYR|USD|SGD|EUR|\$|€)?\s*([0-9][0-9, .]*\d)")
        # A total matcher must never accept a subtotal line.
        if name == "total_amount" and source and re.search(r"sub\s*total", source, re.I):
            value, source = next(((m.group(1), line) for line in reversed(lines) if not re.search(r"sub\s*total", line, re.I) and re.search(r"(?:^|\s)(?:grand\s+total|total|amount\s+paid)\s*[:\-]?", line, re.I) and (m := re.search(r"(?:RM|MYR|USD|SGD|EUR|\$|€)?\s*([0-9][0-9, .]*\d)\s*$", line, re.I))), (None, None))
        field(name, _amount(value) if value else None, source)
    context = text.lower()
    if re.search(r"\b(RM|MYR)\b", text, re.I): currency, conf = "MYR", "high"
    elif re.search(r"\bSGD\b|singapore", text, re.I): currency, conf = "SGD", "high"
    elif re.search(r"\bUSD\b", text, re.I): currency, conf = "USD", "high"
    elif re.search(r"\bEUR\b|€", text, re.I): currency, conf = "EUR", "high"
    elif "$" in text: currency, conf = None, "low"
    else: currency, conf = None, "low"
    field("currency", currency, currency, conf)
    items: list[dict] = []
    for row_number, line in enumerate(lines, 1):
        if re.search(r"sub\s*total|tax|grand total|^total|thank", line, re.I): continue
        match = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)\s+\$?([0-9]+(?:\.\d{2}))\s+\$?([0-9]+(?:\.\d{2}))$", line)
        if match:
            items.append({"description": match.group(1).strip(), "quantity": match.group(2), "unit_price": match.group(3), "tax_rate": None, "tax_amount": None, "amount": match.group(4), "source_row_number": row_number})
    warnings = []
    for name, label in (("receipt_number", "Receipt number"), ("total_amount", "Total"), ("merchant_name", "Merchant name"), ("currency", "Currency")):
        if fields[name]["confidence"] == "low": warnings.append(f"{label} needs review.")
    if "$" in text and not fields["currency"]["value"]: warnings.append("The $ currency symbol is ambiguous; select the currency before importing.")
    try:
        item_total = sum(Decimal(str(item["amount"])) for item in items)
        subtotal = Decimal(fields["subtotal"]["value"]) if fields["subtotal"]["value"] else None
        total = Decimal(fields["total_amount"]["value"]) if fields["total_amount"]["value"] else None
        tax = Decimal(fields["tax_amount"]["value"]) if fields["tax_amount"]["value"] else Decimal("0")
        if subtotal is not None and item_total != subtotal: warnings.append("Line item amounts do not reconcile with the subtotal.")
        if subtotal is not None and total is not None and subtotal + tax != total: warnings.append("Subtotal and tax do not reconcile with the total.")
    except (InvalidOperation, ValueError): warnings.append("Receipt totals could not be reconciled.")
    return fields, items, warnings

def parse_document(pages: list[dict[str, Any]], requested_type: str | None = None):
    detected_type, confidence = detect_document_type(pages)
    document_type = requested_type or detected_type
    if document_type == "receipt": fields, items, warnings = parse_receipt(pages)
    elif document_type == "invoice": fields, items, warnings = parse_invoice(pages)
    else: fields, items, warnings = {}, [], ["Document type could not be determined. Select Invoice or Receipt to continue."]
    return document_type, confidence, fields, items, warnings

def extract(path: Path, media: str) -> tuple[list[dict], str, str, list[str], str, str | None]:
    if media == "application/pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path)); pages = [{"page_number": i + 1, "text": (page.extract_text() or "")[:20000]} for i, page in enumerate(reader.pages)]
        if any(page["text"].strip() for page in pages): return pages, "pypdf", "native_pdf_text", [], "not_required", None
        return pages, "tesseract", "ocr_required", ["This PDF appears to contain scanned pages and could not be read as text."], "unsupported", "Image-based PDF OCR is not available yet."
    # Tesseract is intentionally an optional local provider; a deployment can add it without changing application code.
    try:
        import pytesseract
        from PIL import Image
        if not shutil.which("tesseract"):
            for candidate in (
                Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            ):
                if candidate.is_file():
                    pytesseract.pytesseract.tesseract_cmd = str(candidate)
                    break
        text = pytesseract.image_to_string(Image.open(path), timeout=20)[:20000]
        if text.strip():
            return [{"page_number": 1, "text": text}], "tesseract", "image_ocr", [], "succeeded", None
        return [{"page_number": 1, "text": ""}], "tesseract", "image_ocr", ["DataBridge could not extract text from this image."], "failed", "Tesseract completed but returned no readable text."
    except (ImportError, ModuleNotFoundError):
        return [{"page_number": 1, "text": ""}], "tesseract", "ocr_required", [], "provider_unavailable", "Tesseract Python support is not installed."
    except Exception as exc:
        # pytesseract raises TesseractNotFoundError when the native executable is absent.
        if exc.__class__.__name__ == "TesseractNotFoundError":
            return [{"page_number": 1, "text": ""}], "tesseract", "ocr_required", [], "provider_unavailable", "Tesseract executable was not found."
        return [{"page_number": 1, "text": ""}], "tesseract", "image_ocr", ["DataBridge could not extract text from this image."], "failed", "The OCR provider returned an error."
