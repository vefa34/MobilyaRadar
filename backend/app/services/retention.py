"""Data lifecycle: licence-driven retention purges and GDPR/KVKK erasure."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Company, CompanyContact, CompanyEvidence, CompanyLocation, OrganizationLead

FIELD_COLUMNS = {"phone": "phone", "address": "address", "website": "website", "email": "general_email", "city": "city"}


def purge_expired(db: Session, now: datetime | None = None) -> dict:
    """Delete evidence/contacts/locations past ``retention_until`` and blank denormalised fields that
    no remaining evidence supports. Persistent identifiers (e.g. Google place_id in external_ids)
    survive on locations only when the location itself is retained."""
    now = now or datetime.now(UTC)
    expired = db.scalars(select(CompanyEvidence).where(CompanyEvidence.retention_until.is_not(None), CompanyEvidence.retention_until < now)).all()
    touched = {e.company_id for e in expired}
    n_ev = len(expired)
    for e in expired:
        db.delete(e)
    n_ct = db.execute(delete(CompanyContact).where(CompanyContact.retention_until.is_not(None), CompanyContact.retention_until < now)).rowcount
    # Locations: keep row (with persistent external ids) but strip licensed content.
    n_loc = 0
    for loc in db.scalars(select(CompanyLocation).where(CompanyLocation.retention_until.is_not(None), CompanyLocation.retention_until < now)):
        loc.address = loc.phone = loc.name = None
        loc.latitude = loc.longitude = None
        loc.retention_until = None
        n_loc += 1
    db.flush()
    blanked = 0
    for cid in touched:
        c = db.get(Company, cid)
        if not c:
            continue
        remaining = {(e.field, (e.value or "").lower()) for e in db.scalars(select(CompanyEvidence).where(CompanyEvidence.company_id == cid))}
        for field, col in FIELD_COLUMNS.items():
            val = getattr(c, col)
            if val and (field, str(val).lower()) not in remaining:
                setattr(c, col, None)
                blanked += 1
        if not any(f == "name" for f, _ in remaining):
            db.delete(c)  # nothing left that we may keep
    db.commit()
    return {"evidence_deleted": n_ev, "contacts_deleted": n_ct, "locations_stripped": n_loc, "fields_blanked": blanked}


def erase_company(db: Session, org_id, company_id, user_id=None, reason: str = "data subject request") -> bool:
    c = db.scalar(select(Company).where(Company.id == company_id, Company.org_id == org_id))
    if not c:
        return False
    db.execute(delete(OrganizationLead).where(OrganizationLead.company_id == company_id))
    db.delete(c)
    db.add(AuditLog(org_id=org_id, user_id=user_id, action="company.erase", entity_type="company", entity_id=str(company_id),
                    details={"reason": reason}))
    db.commit()
    return True
