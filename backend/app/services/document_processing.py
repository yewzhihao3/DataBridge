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
    try:
        reader = PdfReader(str(path), strict=True)
    except Exception as exc:
        raise ValueError(f"Malformed or corrupt PDF file: {exc}") from exc
    if reader.is_encrypted: raise ValueError("Encrypted PDFs are not supported.")
    if not reader.pages or len(reader.pages) > max_pages: raise ValueError(f"PDF must contain between 1 and {max_pages} pages.")
    return len(reader.pages), None, None

def rasterize_pdf_page_to_jpeg(path_or_bytes: Path | bytes, page_index: int, scale: float = 2.0) -> bytes:
    """Renders a single PDF page to JPEG bytes using pypdfium2."""
    import pypdfium2 as pdfium
    from PIL import Image
    try:
        pdf = pdfium.PdfDocument(str(path_or_bytes) if isinstance(path_or_bytes, Path) else path_or_bytes)
        if page_index < 0 or page_index >= len(pdf):
            raise ValueError(f"Page index {page_index} is out of bounds (document has {len(pdf)} pages).")
        page = pdf[page_index]
        pil_image = page.render(scale=scale).to_pil()
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
        buf = io.BytesIO()
        pil_image.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception as exc:
        raise ValueError(f"Could not render PDF page {page_index + 1}: {exc}") from exc

def inspect_and_extract_pdf_pages(
    path: Path,
    max_pages: int = 25,
) -> tuple[list[dict[str, Any]], bool]:
    """Reads PDF pages using pypdf, detecting which pages contain native text or scanned images."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path), strict=True)
    except Exception as exc:
        raise ValueError(f"Malformed or corrupt PDF file: {exc}") from exc

    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported.")
    if not reader.pages or len(reader.pages) > max_pages:
        raise ValueError(f"PDF must contain between 1 and {max_pages} pages.")

    pages: list[dict[str, Any]] = []
    has_scanned_pages = False

    for i, page in enumerate(reader.pages):
        raw_text = (page.extract_text() or "").strip()
        if len(raw_text) >= 20:
            pages.append({
                "page_number": i + 1,
                "text": raw_text[:20000],
                "is_scanned": False,
            })
        else:
            has_scanned_pages = True
            pages.append({
                "page_number": i + 1,
                "text": "",
                "is_scanned": True,
            })

    return pages, has_scanned_pages

def ocr_scanned_pdf_pages_locally(
    path: Path,
    pages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, str, list[str], str, str | None]:
    """Runs local Tesseract OCR on rasterized image buffers for scanned PDF pages."""
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

        for page_info in pages:
            if page_info.get("is_scanned"):
                page_idx = page_info["page_number"] - 1
                jpeg_bytes = rasterize_pdf_page_to_jpeg(path, page_idx)
                img = Image.open(io.BytesIO(jpeg_bytes))
                ocr_text = pytesseract.image_to_string(img, timeout=20)[:20000]
                page_info["text"] = ocr_text.strip()

        if any(p["text"].strip() for p in pages):
            return pages, "tesseract", "scanned_pdf_ocr", [], "succeeded", None
        return pages, "tesseract", "scanned_pdf_ocr", ["DataBridge could not extract text from this scanned PDF."], "failed", "Tesseract completed but returned no readable text."
    except (ImportError, ModuleNotFoundError):
        return pages, "tesseract", "ocr_required", ["Tesseract is not installed locally."], "provider_unavailable", "Tesseract Python support is not installed."
    except Exception as exc:
        if exc.__class__.__name__ == "TesseractNotFoundError":
            return pages, "tesseract", "ocr_required", ["Tesseract executable was not found."], "provider_unavailable", "Tesseract executable was not found."
        return pages, "tesseract", "scanned_pdf_ocr", ["DataBridge could not extract text from this scanned PDF."], "failed", f"OCR error: {exc}"

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
    if "tax invoice" in text or "tax inv" in text:
        return "invoice", "high"
    receipt_signals = ("receipt", "thank you", "cash", "change", "amount paid", "subtotal")
    invoice_signals = ("invoice", "bill to", "due date", "invoice date", "payment terms", "invoice #", "invoice no", "inv #", "inv no")
    receipt_score = sum(1 for signal in receipt_signals if signal in text)
    invoice_score = sum(1 for signal in invoice_signals if signal in text)
    if "invoice" in text and "receipt" not in text and invoice_score >= 1:
        return "invoice", "high" if invoice_score >= 2 else "medium"
    if receipt_score >= 2 and receipt_score > invoice_score:
        return "receipt", "high" if receipt_score >= 3 else "medium"
    if invoice_score >= 2 and invoice_score >= receipt_score:
        return "invoice", "high" if invoice_score >= 3 else "medium"
    if invoice_score > receipt_score:
        return "invoice", "medium"
    if receipt_score > invoice_score:
        return "receipt", "medium"
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
    if number and (re.search(r"[*xX]{3,}|\b\d{4}[-* ]?[*xX]{4,}|\b\d{12,19}\b", number) or re.search(r"^(?:table|tab|tbl|seat)\s*#?\s*\d+$", number, re.I)):
        number = None
        number_source = None
    field("receipt_number", number, number_source, "high" if number else "low")
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
    for name, label in (("total_amount", "Total"), ("merchant_name", "Merchant name"), ("currency", "Currency")):
        if fields[name]["confidence"] == "low" or not fields[name]["value"]: warnings.append(f"{label} needs review.")
    if not fields["receipt_number"]["value"]:
        warnings.append("Receipt number missing (optional).")
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

def build_validation_summary(
    document_type: str,
    fields: dict[str, Any],
    line_items: list[dict[str, Any]],
    warnings: list[str],
    provider: str = "",
    ocr_status: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Separates warnings into structured severity categories and isolates verbose AI commentary."""
    items: list[dict[str, Any]] = []
    ai_notes: list[str] = []
    actionable_warnings: list[str] = []

    for w in warnings:
        if w.startswith("AI Note:") or w.startswith("Note:"):
            ai_notes.append(w.replace("AI Note:", "").replace("Note:", "").strip())
        elif w.startswith("Unreadable:") or w.startswith("Unreadable element:"):
            ai_notes.append(w)
        else:
            actionable_warnings.append(w)

    # 1. Amounts & Arithmetic validation
    has_arithmetic_issue = False
    for w in actionable_warnings:
        if "reconcile" in w.lower() or "arithmetic" in w.lower() or "does not match" in w.lower():
            items.append({
                "severity": "warning",
                "category": "amounts",
                "message": "Arithmetic discrepancy",
                "details": w,
            })
            has_arithmetic_issue = True

    total_val = fields.get("total_amount", {}).get("value")
    subtotal_val = fields.get("subtotal", {}).get("value")
    if document_type == "receipt":
        if not has_arithmetic_issue and total_val:
            items.append({
                "severity": "success",
                "category": "amounts",
                "message": "Amounts verified",
                "details": "Line items, subtotal, and tax reconcile mathematically.",
            })
        elif not total_val:
            items.append({
                "severity": "warning",
                "category": "amounts",
                "message": "Total amount missing",
                "details": "Total amount was not detected with high confidence.",
            })

    # 2. Identifiers validation
    if document_type == "receipt":
        merchant = fields.get("merchant_name", {}).get("value")
        if not merchant:
            items.append({
                "severity": "error",
                "category": "identifiers",
                "message": "Merchant name missing",
                "details": "Merchant name is required before confirming import.",
            })
        receipt_num = fields.get("receipt_number", {}).get("value")
        if not receipt_num:
            items.append({
                "severity": "info",
                "category": "identifiers",
                "message": "Receipt number missing (optional)",
                "details": "No printed receipt number detected. DataBridge will assign an automatic internal reference.",
            })
    else:  # invoice
        company = fields.get("company_name", {}).get("value")
        inv_num = fields.get("invoice_number", {}).get("value")
        if not company or not inv_num:
            items.append({
                "severity": "error",
                "category": "identifiers",
                "message": "Invoice number or vendor name missing",
                "details": "Company name and invoice number are required before confirming import.",
            })

    # 3. Dates validation
    for w in actionable_warnings:
        if "future" in w.lower():
            items.append({
                "severity": "warning",
                "category": "dates",
                "message": "Future transaction date",
                "details": w,
            })
        elif "old" in w.lower() or "years" in w.lower():
            items.append({
                "severity": "info",
                "category": "dates",
                "message": "Old transaction date",
                "details": w,
            })

    # 4. Currency
    curr = fields.get("currency", {}).get("value")
    conf = fields.get("currency", {}).get("confidence", "low")
    if curr:
        if conf == "high":
            items.append({
                "severity": "info",
                "category": "currency",
                "message": f"Currency: {curr}",
                "details": f"Stated currency {curr}.",
            })
        else:
            items.append({
                "severity": "info",
                "category": "currency",
                "message": f"Currency inferred: {curr}",
                "details": "Inferred from store context or currency symbol.",
            })
    else:
        items.append({
            "severity": "warning",
            "category": "currency",
            "message": "Currency needs review",
            "details": "The currency symbol or code is ambiguous; select currency before confirming.",
        })

    # 5. Engine / Fallback / Multipage
    for w in actionable_warnings:
        if "fell back to local ocr" in w.lower():
            items.append({
                "severity": "info",
                "category": "engine",
                "message": "AI Vision fallback used",
                "details": w,
            })
        elif "multipage document" in w.lower():
            items.append({
                "severity": "info",
                "category": "engine",
                "message": "Multipage document",
                "details": w,
            })

    return items, ai_notes

def extract(path: Path, media: str) -> tuple[list[dict], str, str, list[str], str, str | None]:
    if media == "application/pdf":
        pages, has_scanned = inspect_and_extract_pdf_pages(path)
        if not has_scanned:
            return pages, "pypdf", "native_pdf_text", [], "not_required", None
        pages, prov, method, warns, stat, msg = ocr_scanned_pdf_pages_locally(path, pages)
        all_scanned = all(p.get("is_scanned") for p in pages)
        provider = "tesseract" if all_scanned else "tesseract+pypdf"
        method = "scanned_pdf_ocr" if all_scanned else "mixed_pdf_ocr"
        return pages, provider, method, warns, stat, msg
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


def map_ai_extraction_to_review_state(
    result: Any,
) -> tuple[dict[str, dict], list[dict], list[str]]:
    ext = result.extraction
    h = ext.header
    fields: dict[str, dict] = {}

    def set_field(name: str, val: Any, conf_name: str | None = None, evidence_name: str | None = None):
        v_str = str(val) if val is not None else None
        conf = ext.confidence_ratings.get(conf_name or name, "high" if val is not None else "low")
        evidence = ext.field_evidence.get(evidence_name or name)
        fields[name] = {
            "value": v_str,
            "confidence": conf,
            "page": 1 if val is not None else None,
            "text": evidence,
        }

    set_field("merchant_name", h.merchant_name)
    set_field("receipt_number", h.receipt_number)
    set_field("transaction_date", h.transaction_date)
    set_field("company_name", h.merchant_name, conf_name="merchant_name", evidence_name="merchant_name")
    set_field("invoice_number", h.receipt_number, conf_name="receipt_number", evidence_name="receipt_number")
    set_field("invoice_date", h.transaction_date, conf_name="transaction_date", evidence_name="transaction_date")
    set_field("transaction_time", h.transaction_time)
    set_field("currency", h.currency)
    set_field("subtotal", h.subtotal)
    set_field("tax_amount", h.tax_amount)
    set_field("total_amount", h.total_amount)

    if h.merchant_address:
        set_field("store_address", h.merchant_address)
    if h.payment_method:
        set_field("payment_method", h.payment_method)
    if h.service_charge is not None:
        set_field("service_charge", h.service_charge)
    if h.discount_amount is not None:
        set_field("discount_amount", h.discount_amount)
    if h.rounding_adjustment is not None:
        set_field("rounding_adjustment", h.rounding_adjustment)
    if h.cash_paid is not None:
        set_field("cash_paid", h.cash_paid)
    if h.change_amount is not None:
        set_field("change_amount", h.change_amount)
    if h.merchant_tax_id:
        set_field("merchant_tax_id", h.merchant_tax_id)
    if h.merchant_phone:
        set_field("merchant_phone", h.merchant_phone)

    lines = [
        {
            "description": item.description,
            "quantity": str(item.quantity) if item.quantity is not None else None,
            "unit_price": str(item.unit_price) if item.unit_price is not None else None,
            "tax_rate": str(item.tax_rate) if item.tax_rate is not None else None,
            "tax_amount": str(item.tax_amount) if item.tax_amount is not None else None,
            "amount": str(item.amount) if item.amount is not None else None,
            "discount": str(item.discount) if item.discount is not None else None,
            "unit": item.unit,
            "source_row_number": idx,
        }
        for idx, item in enumerate(ext.line_items, 1)
    ]

    warnings = list(result.reconciliation_warnings)
    if ext.notes:
        for n in ext.notes:
            warnings.append(f"AI Note: {n}")
    if ext.unreadable_elements:
        for u in ext.unreadable_elements:
            warnings.append(f"Unreadable element: {u}")

    for name, label in (
        ("total_amount", "Total"),
        ("merchant_name", "Merchant name"),
        ("currency", "Currency"),
    ):
        if fields.get(name, {}).get("confidence") == "low" or not fields.get(name, {}).get("value"):
            w = f"{label} needs review."
            if w not in warnings:
                warnings.append(w)
    if not fields.get("receipt_number", {}).get("value"):
        w = "Receipt number missing (optional)."
        if w not in warnings:
            warnings.append(w)

    return fields, lines, warnings


def process_document_pipeline(
    path: Path,
    media_type: str,
    mode: str | None = None,
    provider: Any = None,
) -> dict[str, Any]:
    from app.config import settings
    from app.services.vision_provider import DeepSeekVisionProvider

    effective_mode = mode or settings.ai_receipt_mode
    is_image = media_type.startswith("image/")
    is_pdf = media_type == "application/pdf"

    if is_image and effective_mode in {"auto", "vision_only"}:
        try:
            active_provider = provider or DeepSeekVisionProvider()
            image_bytes = path.read_bytes()
            result = active_provider.extract_receipt(image_bytes, media_type)
            fields, lines, warnings = map_ai_extraction_to_review_state(result)
            raw_text = (result.raw_response_text or "").lower()
            doc_num = (result.extraction.header.receipt_number or "").upper()
            doc_type = "receipt"
            if "tax invoice" in raw_text or "tax inv" in raw_text or doc_num.startswith("INV"):
                doc_type = "invoice"
            elif "invoice" in raw_text and "receipt" not in raw_text:
                doc_type = "invoice"
            return {
                "status": "needs_review",
                "document_type": doc_type,
                "provider": f"deepseek_vision:{result.model}",
                "processing_method": "vision_llm",
                "ocr_status": "not_required",
                "ocr_message": None,
                "pages": [{"page_number": 1, "text": result.raw_response_text}],
                "fields": fields,
                "line_items": lines,
                "warnings": warnings,
                "raw_text": result.raw_response_text[:50000],
                "error_message": None,
            }
        except Exception as exc:
            if effective_mode == "vision_only":
                return {
                    "status": "failed",
                    "document_type": "receipt",
                    "provider": "deepseek_vision",
                    "processing_method": "vision_llm",
                    "ocr_status": "failed",
                    "ocr_message": str(exc),
                    "pages": [{"page_number": 1, "text": ""}],
                    "fields": {},
                    "line_items": [],
                    "warnings": [f"AI extraction failed: {exc}"],
                    "raw_text": None,
                    "error_message": f"AI Vision extraction failed in vision_only mode: {exc}",
                }
            fallback_reason = str(exc)
            pages, prov, method, ocr_warns, ocr_stat, ocr_msg = extract(path, media_type)
            doc_type, _conf, fields, lines, parse_warns = parse_document(pages)
            warnings = [f"AI vision extraction failed ({fallback_reason}); fell back to local OCR engine."] + ocr_warns + parse_warns
            return {
                "status": "needs_review",
                "document_type": doc_type,
                "provider": prov,
                "processing_method": method,
                "ocr_status": ocr_stat,
                "ocr_message": ocr_msg,
                "pages": pages,
                "fields": fields,
                "line_items": lines,
                "warnings": warnings,
                "raw_text": "\n".join(page.get("text", "") for page in pages)[:50000],
                "error_message": None,
            }

    if is_pdf:
        pages, has_scanned = inspect_and_extract_pdf_pages(path)
        if (effective_mode == "vision_only") or (effective_mode == "auto" and has_scanned):
            try:
                active_provider = provider or DeepSeekVisionProvider()
                target_page_idx = 0
                for idx, p in enumerate(pages):
                    if p.get("is_scanned"):
                        target_page_idx = idx
                        break
                jpeg_bytes = rasterize_pdf_page_to_jpeg(path, target_page_idx)
                result = active_provider.extract_receipt(jpeg_bytes, "image/jpeg")
                fields, lines, warnings = map_ai_extraction_to_review_state(result)
                if len(pages) > 1:
                    multipage_warn = f"Multipage document ({len(pages)} pages): AI Vision extracted page {target_page_idx + 1}. Verify line items from all pages before importing."
                    if multipage_warn not in warnings:
                        warnings.append(multipage_warn)
                raw_text = (result.raw_response_text or "").lower()
                doc_num = (result.extraction.header.receipt_number or "").upper()
                doc_type = "receipt"
                if "tax invoice" in raw_text or "tax inv" in raw_text or doc_num.startswith("INV"):
                    doc_type = "invoice"
                elif "invoice" in raw_text and "receipt" not in raw_text:
                    doc_type = "invoice"
                return {
                    "status": "needs_review",
                    "document_type": doc_type,
                    "provider": f"deepseek_vision:{result.model}",
                    "processing_method": "scanned_pdf_vision" if has_scanned else "vision_llm",
                    "ocr_status": "not_required",
                    "ocr_message": None,
                    "pages": pages if len(pages) > 1 else [{"page_number": 1, "text": result.raw_response_text}],
                    "fields": fields,
                    "line_items": lines,
                    "warnings": warnings,
                    "raw_text": result.raw_response_text[:50000],
                    "error_message": None,
                }
            except Exception as exc:
                if effective_mode == "vision_only":
                    return {
                        "status": "failed",
                        "document_type": "receipt",
                        "provider": "deepseek_vision",
                        "processing_method": "scanned_pdf_vision" if has_scanned else "vision_llm",
                        "ocr_status": "failed",
                        "ocr_message": str(exc),
                        "pages": pages,
                        "fields": {},
                        "line_items": [],
                        "warnings": [f"AI extraction failed: {exc}"],
                        "raw_text": None,
                        "error_message": f"AI Vision extraction failed in vision_only mode: {exc}",
                    }
                fallback_reason = str(exc)
                pages, prov, method, ocr_warns, ocr_stat, ocr_msg = extract(path, media_type)
                doc_type, _conf, fields, lines, parse_warns = parse_document(pages)
                warnings = [f"AI vision extraction failed ({fallback_reason}); fell back to local OCR engine."] + ocr_warns + parse_warns
                return {
                    "status": "needs_review",
                    "document_type": doc_type,
                    "provider": prov,
                    "processing_method": method,
                    "ocr_status": ocr_stat,
                    "ocr_message": ocr_msg,
                    "pages": pages,
                    "fields": fields,
                    "line_items": lines,
                    "warnings": warnings,
                    "raw_text": "\n".join(page.get("text", "") for page in pages)[:50000],
                    "error_message": None,
                }

    pages, prov, method, ocr_warns, ocr_stat, ocr_msg = extract(path, media_type)
    doc_type, _conf, fields, lines, parse_warns = parse_document(pages)
    return {
        "status": "needs_review",
        "document_type": doc_type,
        "provider": prov,
        "processing_method": method,
        "ocr_status": ocr_stat,
        "ocr_message": ocr_msg,
        "pages": pages,
        "fields": fields,
        "line_items": lines,
        "warnings": ocr_warns + parse_warns,
        "raw_text": "\n".join(page.get("text", "") for page in pages)[:50000],
        "error_message": None,
    }
