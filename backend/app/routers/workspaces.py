from datetime import datetime, timedelta, timezone
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.identity import Organization, OrganizationMembership, OrganizationInvitation, AuditEvent, User, AuthSession
from app.schemas.identity import NameInput, InviteInput, AcceptInput, RoleInput, SessionRead
from app.security import Identity, current_identity, require_admin, audit, digest
from app.routers.auth import session_response, make_workspace

router = APIRouter(prefix="/api/v1/workspaces", tags=["Workspaces"])


@router.post("", response_model=SessionRead, status_code=201)
def create_workspace(payload: NameInput, request: Request, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    org = make_workspace(db, payload.name.strip(), identity.user)
    identity.session.organization_id = org.id
    audit(db, org.id, identity.user.id, "CREATE_WORKSPACE")
    db.commit()
    return session_response(db, identity.user, org.id, digest(request.cookies["databridge_session"] + ":csrf"))


@router.post("/{organization_id}/switch", response_model=SessionRead)
def switch_workspace(organization_id: int, request: Request, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    if not db.query(OrganizationMembership).filter_by(user_id=identity.user.id, organization_id=organization_id).first():
        raise HTTPException(404, "Workspace not found")
    identity.session.organization_id = organization_id
    db.commit()
    return session_response(db, identity.user, organization_id, digest(request.cookies["databridge_session"] + ":csrf"))


@router.patch("/current")
def rename_workspace(payload: NameInput, identity: Identity = Depends(require_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, identity.membership.organization_id)
    org.name = payload.name.strip()
    audit(db, org.id, identity.user.id, "CHANGE_WORKSPACE_SETTINGS")
    db.commit()
    return {"id": org.id, "name": org.name, "slug": org.slug}


@router.get("/current/members")
def members(identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    rows = db.query(OrganizationMembership, User).join(User).filter(OrganizationMembership.organization_id == identity.membership.organization_id).all()
    return [dict(id=m.id, user_id=u.id, display_name=u.display_name, email=u.email, role=m.role) for m, u in rows]


@router.delete("/current", status_code=204)
def delete_workspace(payload: NameInput, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    from app.models import ImportBatch, SourceFile, Template
    from app.services.storage import storage
    import logging
    org_id = identity.membership.organization_id
    if identity.membership.role != "OWNER":
        raise HTTPException(403, "Only owners may delete a workspace")
    org = db.query(Organization).filter_by(id=org_id).with_for_update().one()
    if payload.name != org.name:
        raise HTTPException(400, "Enter the exact workspace name to confirm deletion")
    if not db.query(OrganizationMembership).filter(OrganizationMembership.user_id == identity.user.id, OrganizationMembership.organization_id != org_id).first():
        raise HTTPException(409, "Create another workspace before deleting your final workspace")
    for batch in db.query(ImportBatch).filter_by(organization_id=org_id).all():
        db.delete(batch)
    db.flush()
    files = db.query(SourceFile).filter_by(organization_id=org_id).all()
    keys = [file.stored_filename for file in files]
    for obj in files + db.query(Template).filter_by(organization_id=org_id).all():
        db.delete(obj)
    db.flush()
    db.delete(org)
    db.commit()
    for key in keys:
        try:
            storage.delete(key)
        except OSError:
            logging.getLogger(__name__).exception("Workspace storage cleanup failed")


def locked_member(db, identity, member_id):
    org_id = identity.membership.organization_id
    # Serialize owner changes on PostgreSQL; SQLite serializes its writes.
    db.execute(update(Organization).where(Organization.id == org_id).values(updated_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    target = db.query(OrganizationMembership).filter_by(id=member_id, organization_id=org_id).first()
    if not target:
        raise HTTPException(404, "Member not found")
    if target.role == "OWNER":
        if identity.membership.role != "OWNER":
            raise HTTPException(403, "Only an owner may manage owners")
        if db.query(OrganizationMembership).filter_by(organization_id=org_id, role="OWNER").count() <= 1:
            raise HTTPException(409, "The final owner cannot be removed or downgraded")
    return target


@router.patch("/current/members/{member_id}")
def change_role(member_id: int, payload: RoleInput, identity: Identity = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.role == "OWNER" and identity.membership.role != "OWNER":
        raise HTTPException(403, "Only owners may appoint owners")
    target = locked_member(db, identity, member_id)
    target.role = payload.role
    audit(db, identity.membership.organization_id, identity.user.id, "CHANGE_MEMBER_ROLE", "membership", member_id)
    db.commit()
    return {"id": target.id, "role": target.role}


@router.delete("/current/members/{member_id}", status_code=204)
def remove_member(member_id: int, identity: Identity = Depends(require_admin), db: Session = Depends(get_db)):
    target = locked_member(db, identity, member_id)
    # Revoke sessions whose default workspace has just been removed.
    for session in db.query(AuthSession).filter_by(user_id=target.user_id, organization_id=target.organization_id).all():
        db.delete(session)
    db.delete(target)
    audit(db, identity.membership.organization_id, identity.user.id, "REMOVE_MEMBER", "membership", member_id)
    db.commit()


@router.post("/current/invitations", status_code=201)
def invite(payload: InviteInput, identity: Identity = Depends(require_admin), db: Session = Depends(get_db)):
    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(organization_id=identity.membership.organization_id, email=payload.email,
        role=payload.role, token_hash=digest(token), expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7), created_by_user_id=identity.user.id)
    db.add(invitation)
    audit(db, identity.membership.organization_id, identity.user.id, "INVITE_MEMBER")
    db.commit()
    # Fragment keeps the secret out of HTTP request URLs and access logs.
    return {"id": invitation.id, "invitation_url": f"{settings.frontend_url.rstrip('/')}/invite#{token}", "expires_at": invitation.expires_at}


@router.post("/invitations/accept", response_model=SessionRead)
def accept(payload: AcceptInput, request: Request, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    invitation = db.query(OrganizationInvitation).filter_by(token_hash=digest(payload.token)).first()
    if not invitation or invitation.accepted_at or invitation.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(400, "Invitation is invalid or expired")
    if invitation.email != identity.user.email:
        raise HTTPException(403, "Sign in with the invited email address")
    claimed = db.execute(update(OrganizationInvitation).where(OrganizationInvitation.id == invitation.id,
        OrganizationInvitation.accepted_at.is_(None), OrganizationInvitation.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)).values(accepted_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    if claimed.rowcount != 1:
        raise HTTPException(400, "Invitation is invalid or expired")
    if not db.query(OrganizationMembership).filter_by(user_id=identity.user.id, organization_id=invitation.organization_id).first():
        db.add(OrganizationMembership(user_id=identity.user.id, organization_id=invitation.organization_id, role=invitation.role))
    identity.session.organization_id = invitation.organization_id
    audit(db, invitation.organization_id, identity.user.id, "ACCEPT_INVITE")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Membership already exists; retry the invitation")
    return session_response(db, identity.user, invitation.organization_id, digest(request.cookies["databridge_session"] + ":csrf"))


@router.get("/current/audit")
def audit_log(identity: Identity = Depends(require_admin), db: Session = Depends(get_db), offset: int = 0):
    rows = db.query(AuditEvent).filter_by(organization_id=identity.membership.organization_id).order_by(AuditEvent.id.desc()).offset(max(offset, 0)).limit(100).all()
    return [dict(id=e.id, action=e.action, user_id=e.user_id, entity_type=e.entity_type, entity_id=e.entity_id, created_at=e.created_at) for e in rows]
