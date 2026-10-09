"""
tests/unit/test_pdf_rasterization.py — Tests for scanned PDF rasterization and extraction pipeline.
"""
from __future__ import annotations
import io
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pypdf
import pytest
from PIL import Image

from app.schemas.ai_receipt import (
    AIReceiptExtraction,
    AIReceiptHeader,
    AIReceiptLineItem,
)
from app.services.document_processing import (
    extract,
    inspect_and_extract_pdf_pages,
    inspect_document,
    ocr_scanned_pdf_pages_locally,
    parse_document,
    parse_invoice,
    parse_receipt,
    process_document_pipeline,
    rasterize_pdf_page_to_jpeg,
)
from app.services.vision_provider import VisionExtractionResult, VisionTimeoutError


# ── Helpers for PDF generation ───────────────────────────────────────────────

def make_scanned_pdf_bytes(page_count: int = 1, width: int = 300, height: int = 400) -> bytes:
    """Creates a PDF consisting entirely of blank/scanned image pages."""
    images = [Image.new("RGB", (width, height), color="white") for _ in range(page_count)]
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:] if page_count > 1 else [])
    return buf.getvalue()


def make_native_pdf_bytes(text_lines: list[str]) -> bytes:
    """Creates a native PDF containing text streams on each page."""
    writer = pypdf.PdfWriter()
    for text in text_lines:
        clean_text = text.replace("(", "").replace(")", "")
        page_stream = f"BT /F1 12 Tf 72 712 Td ({clean_text}) Tj ET".encode("latin-1")
        pdf_template = (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
            b"4 0 obj << /Length " + str(len(page_stream)).encode("ascii") + b" >> stream\n"
            + page_stream + b"\nendstream endobj\n"
            b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000057 00000 n \n0000000114 00000 n \n0000000227 00000 n \n0000000348 00000 n \n"
            b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n419\n%%EOF"
        )
        reader = pypdf.PdfReader(io.BytesIO(pdf_template))
        writer.add_page(reader.pages[0])
    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()


def make_mixed_pdf_bytes() -> bytes:
    """Creates a 2-page PDF where Page 1 is native text and Page 2 is a scanned image."""
    writer = pypdf.PdfWriter()
    native_bytes = make_native_pdf_bytes(["RECEIPT #RC-1001 KEDAI KOPI AMAN TOTAL RM 25.00"])
    scanned_bytes = make_scanned_pdf_bytes(1)
    
    r1 = pypdf.PdfReader(io.BytesIO(native_bytes))
    r2 = pypdf.PdfReader(io.BytesIO(scanned_bytes))
    writer.add_page(r1.pages[0])
    writer.add_page(r2.pages[0])
    
    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()


def sample_vision_extraction(merchant="Kedai Kopi Aman", total=Decimal("25.00")) -> VisionExtractionResult:
    return VisionExtractionResult(
        extraction=AIReceiptExtraction(
            header=AIReceiptHeader(
                merchant_name=merchant,
                receipt_number="RC-9988",
                transaction_date="2026-03-20",
                currency="MYR",
                subtotal=Decimal("20.00"),
                tax_amount=Decimal("5.00"),
                total_amount=total,
            ),
            line_items=[
                AIReceiptLineItem(description="Nasi Lemak Special", quantity=Decimal("2"), unit_price=Decimal("8.00"), amount=Decimal("16.00")),
                AIReceiptLineItem(description="Teh Tarik Kaw", quantity=Decimal("2"), unit_price=Decimal("2.00"), amount=Decimal("4.00")),
            ],
            confidence_ratings={
                "merchant_name": "high",
                "receipt_number": "high",
                "transaction_date": "high",
                "total_amount": "high",
                "currency": "high",
            },
            field_evidence={
                "merchant_name": merchant,
                "receipt_number": "RC-9988",
                "total_amount": f"RM {total}",
            },
            unreadable_elements=[],
            notes=[],
        ),
        reconciliation_warnings=[],
        provider="deepseek_vision",
        model="deepseek-chat",
        processing_duration_seconds=0.45,
        token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        finish_reason="stop",
        raw_response_text='{"header": {"merchant_name": "Kedai Kopi Aman"}}',
    )


# ── Test Cases ───────────────────────────────────────────────────────────────

def test_1_single_page_scanned_pdf_detection_and_rasterization(tmp_path: Path):
    """Scenario 1: Single-page scanned PDF is correctly detected and rasterized."""
    pdf_path = tmp_path / "scanned_1p.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(1, 200, 200))

    pages, has_scanned = inspect_and_extract_pdf_pages(pdf_path)
    assert len(pages) == 1
    assert has_scanned is True
    assert pages[0]["is_scanned"] is True
    assert pages[0]["text"] == ""

    jpeg_bytes = rasterize_pdf_page_to_jpeg(pdf_path, 0)
    assert len(jpeg_bytes) > 0
    assert jpeg_bytes.startswith(b"\xff\xd8\xff")  # valid JPEG signature


def test_2_multipage_scanned_pdf_detection_and_rasterization(tmp_path: Path):
    """Scenario 2: Multipage scanned PDF handles all pages without dropping or crashing."""
    pdf_path = tmp_path / "scanned_3p.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(3, 200, 200))

    pages, has_scanned = inspect_and_extract_pdf_pages(pdf_path)
    assert len(pages) == 3
    assert has_scanned is True
    for idx, page in enumerate(pages):
        assert page["page_number"] == idx + 1
        assert page["is_scanned"] is True
        jpeg = rasterize_pdf_page_to_jpeg(pdf_path, idx)
        assert jpeg.startswith(b"\xff\xd8\xff")


def test_3_native_text_pdf_extraction(tmp_path: Path):
    """Scenario 3: Native text PDF uses pypdf and is not marked as scanned."""
    pdf_path = tmp_path / "native_text.pdf"
    pdf_path.write_bytes(make_native_pdf_bytes(["INVOICE #INV-5544 ACME CORP TOTAL USD 1200.00"]))

    pages, has_scanned = inspect_and_extract_pdf_pages(pdf_path)
    assert len(pages) == 1
    assert has_scanned is False
    assert pages[0]["is_scanned"] is False
    assert "INVOICE #INV-5544" in pages[0]["text"]


def test_4_mixed_native_and_scanned_pdf(tmp_path: Path):
    """Scenario 4: Mixed PDF flags scanned pages while preserving native text pages."""
    pdf_path = tmp_path / "mixed.pdf"
    pdf_path.write_bytes(make_mixed_pdf_bytes())

    pages, has_scanned = inspect_and_extract_pdf_pages(pdf_path)
    assert len(pages) == 2
    assert has_scanned is True
    assert pages[0]["is_scanned"] is False
    assert "RECEIPT #RC-1001" in pages[0]["text"]
    assert pages[1]["is_scanned"] is True
    assert pages[1]["text"] == ""


def test_5_malformed_pdf_handling(tmp_path: Path):
    """Scenario 5: Malformed PDF raises descriptive ValueError."""
    corrupt_path = tmp_path / "corrupt.pdf"
    corrupt_path.write_bytes(b"%PDF-1.4\ncorrupted gibberish")

    with pytest.raises(ValueError, match="Malformed or corrupt PDF file"):
        inspect_and_extract_pdf_pages(corrupt_path)

    with pytest.raises(ValueError, match="Malformed or corrupt PDF file"):
        inspect_document(corrupt_path, "application/pdf", 25)


def test_6_encrypted_pdf_handling(tmp_path: Path):
    """Scenario 6: Encrypted PDF is safely rejected."""
    writer = pypdf.PdfWriter()
    native_bytes = make_native_pdf_bytes(["SECRET CONTENT INVOICE #999 TOTAL RM 100.00"])
    reader = pypdf.PdfReader(io.BytesIO(native_bytes))
    writer.add_page(reader.pages[0])
    writer.encrypt("supersecretpassword")
    
    enc_buf = io.BytesIO()
    writer.write(enc_buf)
    
    enc_path = tmp_path / "encrypted.pdf"
    enc_path.write_bytes(enc_buf.getvalue())

    with pytest.raises(ValueError, match="Encrypted PDFs are not supported"):
        inspect_and_extract_pdf_pages(enc_path)


def test_7_page_limit_exceeded(tmp_path: Path):
    """Scenario 7: PDF exceeding max_pages is rejected."""
    pdf_path = tmp_path / "huge.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(6))

    with pytest.raises(ValueError, match="PDF must contain between 1 and 5 pages"):
        inspect_and_extract_pdf_pages(pdf_path, max_pages=5)


def test_8_rendering_failure_out_of_bounds(tmp_path: Path):
    """Scenario 8: Rendering non-existent page index raises bounds error."""
    pdf_path = tmp_path / "single.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(1))

    with pytest.raises(ValueError, match="out of bounds"):
        rasterize_pdf_page_to_jpeg(pdf_path, 99)


def test_9_local_ocr_mode_zero_external_requests(tmp_path: Path):
    """Scenario 9: local_ocr mode processes scanned PDF without external AI requests."""
    pdf_path = tmp_path / "scanned_local.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(1))

    mock_provider = MagicMock()
    with patch("pytesseract.image_to_string", return_value="RECEIPT #R-101 KEDAI KITA TOTAL RM 45.00"):
        res = process_document_pipeline(pdf_path, "application/pdf", mode="local_ocr", provider=mock_provider)

    mock_provider.extract_receipt.assert_not_called()
    assert res["status"] == "needs_review"
    assert res["provider"] == "tesseract"
    assert res["processing_method"] == "scanned_pdf_ocr"
    assert res["ocr_status"] == "succeeded"


def test_10_auto_mode_vision_success(tmp_path: Path):
    """Scenario 10: auto mode uses DeepSeek Vision on scanned PDF and maps review state."""
    pdf_path = tmp_path / "scanned_auto.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(1))

    mock_provider = MagicMock()
    mock_provider.extract_receipt.return_value = sample_vision_extraction(merchant="Kedai Kopi Aman", total=Decimal("25.00"))

    res = process_document_pipeline(pdf_path, "application/pdf", mode="auto", provider=mock_provider)

    mock_provider.extract_receipt.assert_called_once()
    assert res["status"] == "needs_review"
    assert "deepseek_vision" in res["provider"]
    assert res["processing_method"] == "scanned_pdf_vision"
    assert res["fields"]["merchant_name"]["value"] == "Kedai Kopi Aman"
    assert res["fields"]["total_amount"]["value"] == "25.00"
    assert len(res["line_items"]) == 2


def test_11_auto_mode_fallback_to_local_ocr(tmp_path: Path):
    """Scenario 11: auto mode falls back to local Tesseract OCR when DeepSeek Vision fails."""
    pdf_path = tmp_path / "scanned_fallback.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(1))

    mock_provider = MagicMock()
    mock_provider.extract_receipt.side_effect = VisionTimeoutError("Request to DeepSeek timed out.")

    with patch("pytesseract.image_to_string", return_value="RECEIPT #FB-1 RESTORAN FALLBACK TOTAL RM 30.00"):
        res = process_document_pipeline(pdf_path, "application/pdf", mode="auto", provider=mock_provider)

    assert res["status"] == "needs_review"
    assert res["provider"] == "tesseract"
    assert any("fell back to local OCR engine" in w for w in res["warnings"])


def test_12_vision_only_failure_does_not_fallback(tmp_path: Path):
    """Scenario 12: vision_only mode returns failed status and does not fall back."""
    pdf_path = tmp_path / "scanned_strict.pdf"
    pdf_path.write_bytes(make_scanned_pdf_bytes(1))

    mock_provider = MagicMock()
    mock_provider.extract_receipt.side_effect = VisionTimeoutError("API timeout")

    with patch("pytesseract.image_to_string") as mock_tess:
        res = process_document_pipeline(pdf_path, "application/pdf", mode="vision_only", provider=mock_provider)

    mock_tess.assert_not_called()
    assert res["status"] == "failed"
    assert "AI Vision extraction failed in vision_only mode" in res["error_message"]


def test_13_receipt_line_item_multipage_aggregation():
    """Scenario 13: Receipt line items across multiple pages are parsed sequentially."""
    pages = [
        {"page_number": 1, "text": "RECEIPT #RC-2020\nSUPERSTORE JAYA\nItem A 1 10.00 10.00\nItem B 2 5.00 10.00"},
        {"page_number": 2, "text": "Item C 1 15.00 15.00\nSUBTOTAL RM 35.00\nTAX RM 0.00\nTOTAL RM 35.00"},
    ]
    doc_type, conf, fields, items, warnings = parse_document(pages)
    assert doc_type == "receipt"
    assert len(items) == 3
    assert [it["description"] for it in items] == ["Item A", "Item B", "Item C"]
    assert [it["amount"] for it in items] == ["10.00", "10.00", "15.00"]
    assert fields["total_amount"]["value"] == "35.00"


def test_14_duplicate_total_prevention():
    """Scenario 14: Repeated total mentions across pages do not duplicate or multiply total."""
    pages = [
        {"page_number": 1, "text": "RECEIPT #RC-3030\nItem 1 1 50.00 50.00\nSUBTOTAL 50.00\nTOTAL RM 50.00"},
        {"page_number": 2, "text": "SUMMARY PAGE\nTOTAL RM 50.00\nTHANK YOU FOR SHOPPING"},
    ]
    doc_type, conf, fields, items, warnings = parse_document(pages)
    assert fields["total_amount"]["value"] == "50.00"
    assert Decimal(fields["total_amount"]["value"]) == Decimal("50.00")


def test_15_native_text_invoice_regression(tmp_path: Path):
    """Scenario 15: Native text invoice PDF parses invoice correctly without AI calls."""
    pdf_path = tmp_path / "invoice_native.pdf"
    pdf_path.write_bytes(make_native_pdf_bytes(["INVOICE #INV-888 BILL TO TECH CORP INVOICE DATE 2026-03-01 TOTAL USD 450.00"]))

    mock_provider = MagicMock()
    res = process_document_pipeline(pdf_path, "application/pdf", mode="auto", provider=mock_provider)
    
    mock_provider.extract_receipt.assert_not_called()
    assert res["status"] == "needs_review"
    assert res["provider"] == "pypdf"
    assert res["processing_method"] == "native_pdf_text"
    assert res["document_type"] == "invoice"
