"""Real cookie authentication and hostile cross-workspace regression checks."""
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session
from app.main import app
from app.models import SourceFile, Template, ImportBatch, InvoiceRecord, InvoiceLineItem
from app.models.identity import User, OrganizationMembership, AuthSession, OrganizationInvitation


async def register(client, email="new@example.test", workspace="New Workspace"):
    result = await client.post("/api/v1/auth/register", json=dict(email=email, password="secure-test-password", display_name="Test User", workspace_name=workspace))
    assert result.status_code == 201, result.text
    client.headers["x-csrf-token"] = result.json()["csrf_token"]
    return result.json()


@pytest.mark.asyncio
async def test_registration_sessions_csrf_password(client, db_session):
    result = await register(client, " New@Example.test ")
    assert result["user"]["email"] == "new@example.test"
    assert result["workspaces"][0]["role"] == "OWNER"
    assert "HttpOnly" in (await client.post("/api/v1/auth/login", json={"email":"new@example.test", "password":"secure-test-password"})).headers["set-cookie"]
    me = (await client.get("/api/v1/auth/me")).json()
    client.headers["x-csrf-token"] = me["csrf_token"]
    assert (await client.post("/api/v1/auth/register", json=dict(email="NEW@example.test", password="secure-test-password", display_name="Duplicate", workspace_name="Duplicate"))).status_code == 409
    assert (await client.post("/api/v1/auth/login", json=dict(email="new@example.test", password="wrong"))).status_code == 401
    assert (await client.post("/api/v1/auth/change-password", json=dict(current_password="secure-test-password", new_password="new-secure-password"), headers={"x-csrf-token":"bad"})).status_code == 403
    assert (await client.post("/api/v1/auth/change-password", json=dict(current_password="secure-test-password", new_password="new-secure-password"), headers={"origin":"https://evil.test"})).status_code == 403
    changed = await client.post("/api/v1/auth/change-password", json=dict(current_password="secure-test-password", new_password="new-secure-password"))
    assert changed.status_code == 200
    client.headers["x-csrf-token"] = changed.json()["csrf_token"]
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/templates")).status_code == 401
    assert (await client.post("/api/v1/auth/login", json=dict(email="new@example.test", password="secure-test-password"))).status_code == 401
    assert (await client.post("/api/v1/auth/login", json=dict(email="new@example.test", password="new-secure-password"))).status_code == 200
    with Session(db_session.bind) as db:
        db.query(User).filter_by(email="new@example.test").one().is_active = False
        db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_expired_invalid_session(client, db_session):
    with Session(db_session.bind) as db:
        for session in db.query(AuthSession).all():
            session.expires_at = datetime(2000, 1, 1)
        db.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    client.cookies.set("databridge_session", "invalid")
    assert (await client.get("/api/v1/templates")).status_code == 401


def seed_data(bind, org, amount, company):
    with Session(bind) as db:
        db.info["organization_id"] = org
        file = SourceFile(original_name=company + ".xlsx", stored_filename=company + ".xlsx", file_size=20, checksum="a" * 64)
        template = Template(name="Shared name", worksheet="Invoice")
        db.add_all([file, template]); db.flush()
        batch = ImportBatch(source_file_id=file.id, template_id=template.id)
        db.add(batch); db.flush()
        invoice = InvoiceRecord(batch_id=batch.id, company_name=company, invoice_number=company, total_amount=Decimal(amount), currency="MYR", source_worksheet="Invoice", raw_data="{}")
        db.add(invoice); db.flush()
        db.add(InvoiceLineItem(invoice_id=invoice.id, source_row_number=1, description=company, amount=Decimal(amount)))
        db.commit()
        return file.id, template.id, batch.id, invoice.id


@pytest.mark.asyncio
async def test_every_business_boundary(client, db_session):
    a = (await client.get("/api/v1/auth/me")).json()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        b = await register(other, "other@example.test", "Secret Workspace")
        bf, bt, bb, bi = seed_data(db_session.bind, b["active_workspace_id"], "1000000", "SECRET_COMPANY")
        af, at, ab, ai = seed_data(db_session.bind, a["active_workspace_id"], "100", "VISIBLE_COMPANY")
        for path in [f"/templates/{bt}", f"/files/{bf}/preview?sheet_name=Invoice", f"/imports/{bb}", f"/data/invoices/{bi}"]:
            assert (await client.get("/api/v1" + path)).status_code == 404, path
        for method, path, body in [
            ("PUT", f"/templates/{bt}", {"name":"stolen"}),
            ("DELETE", f"/templates/{bt}", None), ("DELETE", f"/imports/{bb}", None),
            ("PATCH", f"/data/invoices/{bi}", {"company_name":"stolen"}),
            ("PATCH", f"/imports/{bb}/records/{bi}", {"company_name":"stolen"}),
            ("POST", "/imports/extract", {"file_id":bf,"template_id":at}),
            ("POST", "/imports/confirm", {"file_id":bf,"template_id":at}),
            ("POST", "/suggestions/analyze", {"file_id":bf}),
        ]:
            res = await client.request(method, "/api/v1"+path, json=body)
            assert res.status_code == 404, (path, res.text)
        for path in ["/templates", "/imports", "/data/invoices", "/data/line-items", "/data/filter-options", "/analytics/filter-options", "/analytics/dashboard?currency=MYR", "/exports/summary?dataset=invoices", "/exports/invoices.csv", "/exports/line-items.csv", "/workspaces/current/audit", "/workspaces/current/members"]:
            res = await client.get("/api/v1"+path)
            assert res.status_code == 200, (path, res.text)
            assert "SECRET_COMPANY" not in res.text and "1000100" not in res.text and "other@example.test" not in res.text, path
        dashboard = (await client.get("/api/v1/analytics/dashboard?currency=MYR")).json()
        assert Decimal(dashboard["summary"]["total_invoice_value"]) == Decimal("100")
        assert dashboard["summary"]["invoice_count"] == 1
        assert dashboard["summary"]["line_item_count"] == 1
        assert (await client.get(f"/api/v1/templates/{at}")).status_code == 200
        assert (await client.get("/api/v1/templates", headers={"x-workspace-id":str(b["active_workspace_id"])})).status_code == 403
        assert (await client.post(f"/api/v1/workspaces/{b['active_workspace_id']}/switch")).status_code == 404


@pytest.mark.asyncio
async def test_invites_roles_owner_safety(client, db_session):
    owner = (await client.get("/api/v1/workspaces/current/members")).json()[0]
    assert (await client.delete(f"/api/v1/workspaces/current/members/{owner['id']}")).status_code == 409
    assert (await client.patch(f"/api/v1/workspaces/current/members/{owner['id']}", json={"role":"MEMBER"})).status_code == 409
    invite = await client.post("/api/v1/workspaces/current/invitations", json={"email":"invitee@example.test", "role":"MEMBER"})
    assert invite.status_code == 201
    token = invite.json()["invitation_url"].split("#")[1]
    assert (await client.post("/api/v1/workspaces/invitations/accept", json={"token":token})).status_code == 403
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await register(other, "invitee@example.test")
        accepted = await other.post("/api/v1/workspaces/invitations/accept", json={"token":token})
        assert accepted.status_code == 200, accepted.text
        assert (await other.post("/api/v1/workspaces/invitations/accept", json={"token":token})).status_code == 400
        assert (await other.get("/api/v1/templates")).status_code == 200
        assert (await other.post("/api/v1/workspaces/current/invitations", json={"email":"third@example.test"})).status_code == 403
        assert (await other.get("/api/v1/workspaces/current/audit")).status_code == 403
        assert (await other.request("DELETE", "/api/v1/workspaces/current", json={"name":"Test Workspace"})).status_code == 403
        member = next(m for m in (await client.get("/api/v1/workspaces/current/members")).json() if m["email"] == "invitee@example.test")
        assert (await client.patch(f"/api/v1/workspaces/current/members/{member['id']}", json={"role":"ADMIN"})).status_code == 200
        assert (await other.post("/api/v1/workspaces/current/invitations", json={"email":"third@example.test"})).status_code == 201
        assert (await other.request("DELETE", "/api/v1/workspaces/current", json={"name":"Test Workspace"})).status_code == 403
        assert (await other.patch(f"/api/v1/workspaces/current/members/{owner['id']}", json={"role":"MEMBER"})).status_code == 403
        expired = await client.post("/api/v1/workspaces/current/invitations", json={"email":"invitee@example.test"})
        with Session(db_session.bind) as db:
            db.get(OrganizationInvitation, expired.json()["id"]).expires_at = datetime(2000,1,1)
            db.commit()
        assert (await other.post("/api/v1/workspaces/invitations/accept", json={"token":expired.json()["invitation_url"].split("#")[1]})).status_code == 400
        assert (await client.delete(f"/api/v1/workspaces/current/members/{member['id']}")).status_code == 204
        assert (await other.get("/api/v1/templates")).status_code == 401


@pytest.mark.asyncio
async def test_matching_upload_and_mixed_parent_ids(client, clean_single_sheet_xlsx):
    own_file = (await client.post("/api/v1/files/upload", files={"file": ("invoice.xlsx", clean_single_sheet_xlsx.read_bytes())})).json()["file_id"]
    payload = {"name":"Visible Template", "worksheet":"Invoice", "field_mappings":[
        {"field_name":"company_name", "mapping_type":"cell", "cell_ref":"B2", "is_required":True},
        {"field_name":"invoice_number", "mapping_type":"cell", "cell_ref":"B3", "is_required":True}]}
    own_template = (await client.post("/api/v1/templates", json=payload)).json()["id"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await register(other, "other@example.test")
        payload["name"] = "Hidden Template"
        foreign_template = (await other.post("/api/v1/templates", json=payload)).json()["id"]
        analysis = await client.post("/api/v1/suggestions/analyze", json={"file_id":own_file})
        assert analysis.status_code == 200
        assert "Hidden Template" not in analysis.text
        assert all(match["template_id"] != foreign_template for match in analysis.json()["template_matches"])
        assert (await client.post("/api/v1/imports/extract", json={"file_id":own_file, "template_id":foreign_template})).status_code == 404
        assert (await client.post("/api/v1/imports/confirm", json={"file_id":own_file, "template_id":foreign_template})).status_code == 404
        assert (await client.post("/api/v1/imports/extract", json={"file_id":own_file, "template_id":own_template})).status_code == 200
        assert (await other.get(f"/api/v1/files/{own_file}/preview?sheet_name=Invoice")).status_code == 404


@pytest.mark.asyncio
async def test_registration_rollback_and_no_password_echo(client, db_session, monkeypatch):
    from app.routers import auth
    from sqlalchemy.exc import IntegrityError
    from app.models.identity import Organization
    with Session(db_session.bind) as db:
        count = db.query(Organization).count()
    def fail(*args):
        raise IntegrityError("simulated", {}, Exception("simulated"))
    monkeypatch.setattr(auth, "establish_session", fail)
    result = await client.post("/api/v1/auth/register", json=dict(email="rollback@example.test", password="secure-test-password", display_name="Rollback", workspace_name="Rollback"))
    assert result.status_code == 409
    with Session(db_session.bind) as db:
        assert not db.query(User).filter_by(email="rollback@example.test").first()
        assert db.query(Organization).count() == count
    result = await client.post("/api/v1/auth/register", json=dict(email="rollback@example.test", password="shortsecret", display_name="Rollback", workspace_name="Rollback"))
    assert result.status_code == 422
    assert "shortsecret" not in result.text
