from app.services.document_processing import detect_document_type, parse_document

RECEIPT = """ARTGROUP T-Shirt Emporium
456 Orchard Road, Singapore
Receipt #: #0000001
Date: 2025-06-26 11:20am
Description Qty U/Price Total
Men's Classic Tee 1 19.90 19.90
Women's V-Neck Tee 1 9.90 9.90
Kids' Crew Neck Tee 4 9.90 39.60
Sub Total: $69.40
Tax: $10.00
Total: $79.40
Thank you for shopping with us!
"""

def pages(text): return [{"page_number": 1, "text": text}]

def test_receipt_detection_and_fields():
    assert detect_document_type(pages(RECEIPT))[0] == "receipt"
    kind, _, fields, items, warnings = parse_document(pages(RECEIPT))
    assert kind == "receipt"
    assert fields["merchant_name"]["value"] == "ARTGROUP T-Shirt Emporium"
    assert fields["receipt_number"]["value"] == "#0000001"
    assert fields["transaction_date"]["value"] == "2025-06-26"
    assert fields["transaction_time"]["value"] == "11:20am"
    assert fields["currency"]["value"] == "SGD"
    assert fields["subtotal"]["value"] == "69.40"
    assert fields["tax_amount"]["value"] == "10.00"
    assert fields["total_amount"]["value"] == "79.40"
    assert len(items) == 3

def test_invoice_and_unknown_detection():
    invoice = pages("INVOICE\nInvoice No: INV-10\nBill To: Example\nDue Date: 2026-10-01")
    assert detect_document_type(invoice)[0] == "invoice"
    assert detect_document_type(pages("A miscellaneous note with no business labels"))[0] == "unknown"

def test_ambiguous_dollar_requires_review():
    _, _, fields, _, warnings = parse_document(pages(RECEIPT.replace("Singapore", "Online Store")))
    assert fields["currency"]["value"] is None
    assert any("ambiguous" in warning.lower() for warning in warnings)
