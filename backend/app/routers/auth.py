import re
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.identity import User, Organization, OrganizationMembership, OrganizationInvitation, AuthSession
from app.schemas.identity import LoginInput, RegisterInput, InviteRegisterInput, PasswordInput, NameInput, SessionRead
from app.security import Identity, current_identity, check_origin, digest, establish_session, password_hasher, verify_password, DUMMY_HASH, audit

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def session_response(db, user, organization_id, csrf):
    workspaces = db.query(Organization, OrganizationMembership).join(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).all()
    return SessionRead(user=user, active_workspace_id=organization_id, csrf_token=csrf,
        workspaces=[dict(id=o.id, name=o.name, slug=o.slug, role=m.role) for o, m in workspaces])


def make_workspace(db, name, user):
    stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100] or "workspace"
    # Random suffix also prevents concurrent registration collisions.
    org = Organization(name=name, slug=f"{stem}-{secrets.token_hex(6)}")
    db.add(org)
    db.flush()
    db.add(OrganizationMembership(user_id=user.id, organization_id=org.id, role="OWNER"))
    db.flush()
    return org


@router.post("/register", response_model=SessionRead, status_code=201)
def register(payload: RegisterInput, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    if db.query(User).filter_by(email=payload.email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=payload.email, display_name=payload.display_name, password_hash=password_hasher.hash(payload.password))
    try:
        db.add(user)
        db.flush()
        org = make_workspace(db, payload.workspace_name, user)
        csrf = establish_session(db, response, user, org.id)
        audit(db, org.id, user.id, "REGISTER")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account could not be created")
    return session_response(db, user, org.id, csrf)


@router.post("/register-invitation", response_model=SessionRead, status_code=201)
def register_invitation(payload: InviteRegisterInput, request: Request, response: Response, db: Session = Depends(get_db)):
    """Atomically create an invited account and consume its one-time invitation."""
    check_origin(request)
    invitation = db.query(OrganizationInvitation).filter_by(token_hash=digest(payload.token)).first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not invitation or invitation.accepted_at or invitation.expires_at <= now:
        raise HTTPException(400, "Invitation is invalid or expired")
    if invitation.email != payload.email:
        raise HTTPException(403, "Register with the invited email address")
    if db.query(User).filter_by(email=payload.email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=payload.email, display_name=payload.display_name, password_hash=password_hasher.hash(payload.password))
    try:
        db.add(user)
        db.flush()
        claimed = db.query(OrganizationInvitation).filter(
            OrganizationInvitation.id == invitation.id,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.expires_at > now,
        ).update({OrganizationInvitation.accepted_at: now}, synchronize_session=False)
        if claimed != 1:
            raise HTTPException(400, "Invitation is invalid or expired")
        db.add(OrganizationMembership(user_id=user.id, organization_id=invitation.organization_id, role=invitation.role))
        csrf = establish_session(db, response, user, invitation.organization_id)
        audit(db, invitation.organization_id, user.id, "REGISTER_INVITATION")
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account could not be created")
    return session_response(db, user, invitation.organization_id, csrf)


@router.post("/login", response_model=SessionRead)
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    user = db.query(User).filter_by(email=payload.email).first()
    valid = verify_password(user.password_hash if user else DUMMY_HASH, payload.password)
    if not user or not valid or not user.is_active:
        raise HTTPException(401, "Invalid email or password")
    membership = db.query(OrganizationMembership).filter_by(user_id=user.id).order_by(OrganizationMembership.id).first()
    if not membership:
        raise HTTPException(403, "No workspace membership")
    old = db.query(AuthSession).filter_by(token_hash=digest(request.cookies.get("databridge_session", ""))).first()
    if old:
        db.delete(old)
    csrf = establish_session(db, response, user, membership.organization_id)
    audit(db, membership.organization_id, user.id, "LOGIN")
    db.commit()
    return session_response(db, user, membership.organization_id, csrf)


@router.get("/me", response_model=SessionRead)
def me(request: Request, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    return session_response(db, identity.user, identity.membership.organization_id, digest(request.cookies["databridge_session"] + ":csrf"))


@router.post("/logout", status_code=204)
def logout(response: Response, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    audit(db, identity.membership.organization_id, identity.user.id, "LOGOUT")
    db.delete(identity.session)
    db.commit()
    response.delete_cookie("databridge_session", path="/", secure=False, httponly=True, samesite="lax")


@router.patch("/account", response_model=SessionRead)
def account(payload: NameInput, request: Request, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    identity.user.display_name = payload.name.strip()
    db.commit()
    return me(request, identity, db)


@router.post("/change-password", response_model=SessionRead)
def change_password(payload: PasswordInput, response: Response, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    if not verify_password(identity.user.password_hash, payload.current_password):
        raise HTTPException(400, "Current password is incorrect")
    identity.user.password_hash = password_hasher.hash(payload.new_password)
    for session in db.query(AuthSession).filter_by(user_id=identity.user.id).all():
        db.delete(session)
    org_id = identity.membership.organization_id
    csrf = establish_session(db, response, identity.user, org_id)
    audit(db, org_id, identity.user.id, "CHANGE_PASSWORD")
    db.commit()
    return session_response(db, identity.user, org_id, csrf)
