import io
import zipfile
from decimal import Decimal
import openpyxl
import pytest
from sqlalchemy.orm import Session
from app.models import ImportBatch, InvoiceRecord
from app.services.export_builder import sanitize_csv_value, generate_invoices_xlsx
from app.services.workbook_inspector import validate_xlsx_file, FileSizeExceededError
from app.services.storage import storage
from tests.integration.test_saas import seed_data


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-cmd", "@SUM(A1)", "\t=1", "\r=1", "+123"])
def test_csv_formula_text(value):
    assert sanitize_csv_value(value) == "'" + value
    assert sanitize_csv_value(Decimal("-12.50")) == Decimal("-12.50")


def test_xlsx_formulas_and_filter_bounds(db_session):
    _, _, _, invoice_id = seed_data(db_session.bind, 1, "-12.50", "=1+1")
    invoice = db_session.get(InvoiceRecord, invoice_id)
    invoice.currency = "@evil"
    data = generate_invoices_xlsx([invoice])
    workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
    sheet = workbook.active
    assert sheet["A2"].value == "=1+1" and sheet["A2"].data_type == "s"
    assert sheet["E2"].value == -12.5
    assert sheet.auto_filter.ref.endswith("2")
    assert all(cell.data_type != "f" for row in sheet for cell in row)
    workbook.close()


def test_zip_resource_limit_and_storage_traversal(tmp_path):
    path = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"a" * (5 * 1024 * 1024))
    with pytest.raises(FileSizeExceededError):
        validate_xlsx_file(path)
    for key in ["../secret", "..\\secret", "C:\\secret", "/secret"]:
        with pytest.raises(ValueError):
            storage.local_path(key)


@pytest.mark.asyncio
async def test_duplicate_deleted_history_summary_export_audit(client, db_session):
    from app.routers.imports import _create_db_duplicate_checker
    _, _, batch_id, _ = seed_data(db_session.bind, 1, "100", "Visible")
    assert _create_db_duplicate_checker(db_session)("Visible", "Visible")
    assert (await client.get("/api/v1/imports/summary")).json()["total_records"] == 1
    assert (await client.get("/api/v1/exports/invoices.csv")).status_code == 200
    assert "EXPORT_INVOICES" in (await client.get("/api/v1/workspaces/current/audit")).text
    assert (await client.delete(f"/api/v1/imports/{batch_id}")).status_code == 204
    db_session.expire_all()
    assert not _create_db_duplicate_checker(db_session)("Visible", "Visible")
    assert (await client.get("/api/v1/imports/summary")).json()["total_records"] == 0


@pytest.mark.asyncio
async def test_export_custom_fields_after_200_rows(client, db_session):
    _, _, batch_id, _ = seed_data(db_session.bind, 1, "100", "Visible")
    for i in range(205):
        db_session.add(InvoiceRecord(batch_id=batch_id, company_name="Visible", invoice_number=str(i), source_worksheet="Sheet", raw_data="{}", custom_fields={"late_field": "found"} if i == 204 else {}))
    db_session.commit()
    assert "Late Field" in (await client.get("/api/v1/exports/summary?dataset=invoices")).json()["columns"]


@pytest.mark.asyncio
async def test_owner_delete_and_member_denial(client, db_session):
    from tests.integration.test_saas import register
    state = await register(client)
    original = state["active_workspace_id"]
    assert (await client.request("DELETE", "/api/v1/workspaces/current", json={"name":"New Workspace"})).status_code == 409
    seed_data(db_session.bind, original, "100", "Delete Me")
    new = (await client.post("/api/v1/workspaces", json={"name":"Keep"})).json()
    assert (await client.post(f"/api/v1/workspaces/{original}/switch")).status_code == 200
    assert (await client.request("DELETE", "/api/v1/workspaces/current", json={"name":"New Workspace"})).status_code == 204
    with Session(db_session.bind) as db:
        assert db.query(ImportBatch).filter_by(organization_id=original).count() == 0
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limit(client):
    for _ in range(30):
        result = await client.post("/api/v1/auth/login", json={"email":"missing@example.test", "password":"wrong"})
    assert result.status_code == 429
    assert result.headers["retry-after"] == "60"


def test_tenant_session_rejects_core_queries(db_session):
    from sqlalchemy import select, text
    for statement in [text("SELECT * FROM invoice_records"), select(InvoiceRecord.__table__)]:
        with pytest.raises(RuntimeError, match="ORM"):
            db_session.execute(statement)


@pytest.mark.asyncio
async def test_missing_identifiers_rejected_without_placeholder(client, clean_single_sheet_xlsx, db_session):
    file = (await client.post("/api/v1/files/upload", files={"file":("invoice.xlsx", clean_single_sheet_xlsx.read_bytes())})).json()["file_id"]
    template = await client.post("/api/v1/templates", json={"name":"Missing identifiers", "worksheet":"Invoice", "field_mappings":[
        {"field_name":"total_amount", "cell_ref":"D6", "mapping_type":"cell", "data_type":"decimal"}]})
    assert template.status_code == 201
    result = await client.post("/api/v1/imports/confirm", json={"file_id":file,"template_id":template.json()["id"],"acknowledge_warnings":True})
    assert result.status_code == 422, result.text
    assert db_session.query(InvoiceRecord).count() == 0
    assert db_session.query(ImportBatch).count() == 0
