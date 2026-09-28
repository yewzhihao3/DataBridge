"""Local operator-only ownership assignment for migrated M11 data.

Usage: python claim_workspace.py registered-owner@example.com
No HTTP route exposes this operation. Register first, then run locally.
"""
import argparse
from app.database import SessionLocal
from app.models.identity import User, Organization, OrganizationMembership


def claim(email: str):
    with SessionLocal.begin() as db:
        org = db.query(Organization).filter_by(slug="default-workspace").with_for_update().one()
        if db.query(OrganizationMembership).filter_by(organization_id=org.id).first():
            raise SystemExit("Default Workspace is already claimed")
        user = db.query(User).filter_by(email=email.strip().lower(), is_active=True).one()
        db.add(OrganizationMembership(user_id=user.id, organization_id=org.id, role="OWNER"))
    print("Default Workspace ownership assigned")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    claim(parser.parse_args().email)
