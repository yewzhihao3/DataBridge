"""Authentication dependencies; no client-selected workspace is trusted implicitly."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from dataclasses import dataclass
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.identity import AuthSession, User, OrganizationMembership, AuditEvent

password_hasher = PasswordHasher()
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in settings.trusted_origins:
        raise HTTPException(403, "Untrusted request origin")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site request rejected")


@dataclass
class Identity:
    user: User
    session: AuthSession
    membership: OrganizationMembership


def current_identity(request: Request, db: Session = Depends(get_db)) -> Identity:
    token = request.cookies.get("databridge_session", "")
    session = db.query(AuthSession).filter(AuthSession.token_hash == digest(token), AuthSession.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)).first()
    user = db.get(User, session.user_id) if session else None
    if not user or not user.is_active:
        raise HTTPException(401, "Authentication required")
    # Explicit header pins each tab to its workspace. Cookie session supplies default.
    try:
        organization_id = int(request.headers.get("x-workspace-id", session.organization_id))
    except ValueError:
        raise HTTPException(403, "Workspace access denied")
    membership = db.query(OrganizationMembership).filter_by(user_id=user.id, organization_id=organization_id).first()
    if not membership:
        raise HTTPException(403, "Workspace access denied")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not secrets.compare_digest(session.csrf_hash, digest(csrf)):
            raise HTTPException(403, "CSRF validation failed")
    return Identity(user, session, membership)


def establish_session(db: Session, response: Response, user: User, organization_id: int) -> str:
    token = secrets.token_urlsafe(32)
    csrf = digest(token + ":csrf")
    db.add(AuthSession(token_hash=digest(token), csrf_hash=digest(csrf), user_id=user.id,
                       organization_id=organization_id, expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=settings.session_hours)))
    response.set_cookie("databridge_session", token, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", max_age=settings.session_hours * 3600, path="/")
    return csrf


def audit(db: Session, organization_id: int, user_id: int, action: str, entity_type: str | None = None, entity_id: int | None = None):
    event = AuditEvent(organization_id=organization_id, user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id)
    db.add(event)
    return event


def require_admin(identity: Identity = Depends(current_identity)) -> Identity:
    if identity.membership.role not in {"OWNER", "ADMIN"}:
        raise HTTPException(403, "Workspace administrator required")
    return identity
