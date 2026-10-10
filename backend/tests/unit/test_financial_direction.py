"""Unit tests for financial direction models, constraints, and schemas."""
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    DEFAULT_INVOICE_DIRECTION,
    DEFAULT_RECEIPT_DIRECTION,
    INVOICE_DIRECTIONS,
    RECEIPT_DIRECTIONS,
)
from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.models.source_file import SourceFile
from app.models.template import Template
from app.schemas.document import DocumentConfirmRequest
from app.schemas.import_batch import InvoiceRecordUpdate, ReceiptRecordRead


def test_direction_constants():
    assert "sales" in INVOICE_DIRECTIONS
    assert "purchase" in INVOICE_DIRECTIONS
    assert "unclassified" in INVOICE_DIRECTIONS
    assert DEFAULT_INVOICE_DIRECTION == "unclassified"

    assert "expense" in RECEIPT_DIRECTIONS
    assert "income" in RECEIPT_DIRECTIONS
    assert "unclassified" in RECEIPT_DIRECTIONS
    assert DEFAULT_RECEIPT_DIRECTION == "unclassified"


def test_invoice_confirm_request_valid_directions():
    for dir_val in ("sales", "purchase", "unclassified", "SALES", "  purchase  "):
        req = DocumentConfirmRequest(
            document_type="invoice",
            company_name="Acme Corp",
            invoice_number="INV-100",
            direction=dir_val,
        )
        assert req.direction in INVOICE_DIRECTIONS


def test_invoice_confirm_request_invalid_directions():
    for invalid in ("expense", "income", "unknown", "invalid"):
        with pytest.raises(ValidationError) as exc:
            DocumentConfirmRequest(
                document_type="invoice",
                company_name="Acme Corp",
                invoice_number="INV-100",
                direction=invalid,
            )
        assert "Invoice direction must be" in str(exc.value)


def test_receipt_confirm_request_valid_directions():
    for dir_val in ("expense", "income", "unclassified", "EXPENSE", "  income  "):
        req = DocumentConfirmRequest(
            document_type="receipt",
            merchant_name="Shell Station",
            direction=dir_val,
        )
        assert req.direction in RECEIPT_DIRECTIONS


def test_receipt_confirm_request_invalid_directions():
    for invalid in ("sales", "purchase", "unknown", "other"):
        with pytest.raises(ValidationError) as exc:
            DocumentConfirmRequest(
                document_type="receipt",
                merchant_name="Shell Station",
                direction=invalid,
            )
        assert "Receipt direction must be" in str(exc.value)


def test_confirm_request_default_direction():
    req_inv = DocumentConfirmRequest(
        document_type="invoice",
        company_name="Acme Corp",
        invoice_number="INV-101",
    )
    assert req_inv.direction == "unclassified"

    req_rcpt = DocumentConfirmRequest(
        document_type="receipt",
        merchant_name="Shell Station",
    )
    assert req_rcpt.direction == "unclassified"


def test_invoice_record_update_direction():
    valid = InvoiceRecordUpdate(direction="sales")
    assert valid.direction == "sales"

    valid_purchase = InvoiceRecordUpdate(direction="purchase")
    assert valid_purchase.direction == "purchase"

    with pytest.raises(ValidationError):
        InvoiceRecordUpdate(direction="invalid_direction")


def _create_test_batch(db_session: Session) -> ImportBatch:
    source = SourceFile(
        organization_id=1,
        original_name="test.pdf",
        stored_filename="test.pdf",
        file_size=100,
        checksum="abc123test",
    )
    db_session.add(source)
    db_session.flush()

    template = Template(
        organization_id=1,
        name="Test Template",
        template_type="invoice",
        file_type="document",
        worksheet="Sheet1",
    )
    db_session.add(template)
    db_session.flush()

    batch = ImportBatch(
        organization_id=1,
        source_file_id=source.id,
        template_id=template.id,
        status="imported",
        record_count=1,
    )
    db_session.add(batch)
    db_session.flush()
    return batch


def test_invoice_record_db_default_and_constraint(db_session: Session):
    batch = _create_test_batch(db_session)

    # Default is unclassified upon database persist
    rec = InvoiceRecord(
        batch_id=batch.id,
        company_name="Test Co",
        invoice_number="INV-TEST-DEF",
        source_worksheet="Sheet1",
        raw_data="{}",
    )
    db_session.add(rec)
    db_session.flush()
    db_session.refresh(rec)
    assert rec.direction == "unclassified"

    # Valid directions persist successfully
    rec_sales = InvoiceRecord(
        batch_id=batch.id,
        company_name="Sales Co",
        invoice_number="INV-TEST-SALES",
        direction="sales",
        source_worksheet="Sheet1",
        raw_data="{}",
    )
    rec_purch = InvoiceRecord(
        batch_id=batch.id,
        company_name="Supplier Co",
        invoice_number="INV-TEST-PURCH",
        direction="purchase",
        source_worksheet="Sheet1",
        raw_data="{}",
    )
    db_session.add_all([rec_sales, rec_purch])
    db_session.flush()
    assert rec_sales.direction == "sales"
    assert rec_purch.direction == "purchase"

    # Invalid direction violates check constraint
    invalid_rec = InvoiceRecord(
        batch_id=batch.id,
        company_name="Test Co",
        invoice_number="INV-TEST-BAD",
        direction="invalid_direction",
        source_worksheet="Sheet1",
        raw_data="{}",
    )
    db_session.add(invalid_rec)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_receipt_record_db_default_and_constraint(db_session: Session):
    batch = _create_test_batch(db_session)

    # Default is unclassified upon database persist
    rec = ReceiptRecord(
        batch_id=batch.id,
        merchant_name="Test Merchant",
        receipt_number="REC-TEST-DEF",
        raw_data="{}",
    )
    db_session.add(rec)
    db_session.flush()
    db_session.refresh(rec)
    assert rec.direction == "unclassified"

    # Valid directions persist successfully
    rec_exp = ReceiptRecord(
        batch_id=batch.id,
        merchant_name="Gas Station",
        receipt_number="REC-TEST-EXP",
        direction="expense",
        raw_data="{}",
    )
    rec_inc = ReceiptRecord(
        batch_id=batch.id,
        merchant_name="Client Deposit",
        receipt_number="REC-TEST-INC",
        direction="income",
        raw_data="{}",
    )
    db_session.add_all([rec_exp, rec_inc])
    db_session.flush()
    assert rec_exp.direction == "expense"
    assert rec_inc.direction == "income"

    # Invalid direction violates check constraint
    invalid_rec = ReceiptRecord(
        batch_id=batch.id,
        merchant_name="Test Merchant",
        receipt_number="REC-TEST-BAD",
        direction="sales",  # 'sales' is invalid for receipt
        raw_data="{}",
    )
    db_session.add(invalid_rec)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
