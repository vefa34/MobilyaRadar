import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.connectors.licensed import parse_tabular, rows_to_raw
from app.db import get_db
from app.deps import audit, current_user, require_role
from app.models import (
    Company,
    CompanyAlias,
    CompanyContact,
    CompanyEvidence,
    CompanyLocation,
    CompanyScore,
    EntityMatchReview,
    ImportSignal,
    OrganizationLead,
    SearchJob,
    SourceRegistry,
    User,
)
from app.schemas import CompanyListItem, CompanyPage, LeadUpdate
from app.services.assessment import assess_company
from app.services.entity_resolution import SourcePolicy, merge_companies, resolve_record
from app.services.retention import erase_company
from app.services.scoring import priority_label

router = APIRouter(prefix="/api/companies", tags=["companies"])

SORTS = {"fit": Company.buyer_fit_score.desc().nullslast(), "confidence": Company.data_confidence_score.desc().nullslast(),
         "name": Company.display_name.asc(), "recent": Company.created_at.desc()}


def _company(db: Session, user: User, cid: uuid.UUID) -> Company:
    c = db.scalar(select(Company).where(Company.id == cid, Company.org_id == user.org_id))
    if not c:
        raise HTTPException(404, "company not found")
    return c


@router.get("", response_model=CompanyPage)
def list_companies(country: list[str] = Query(default=[]), buyer_type: list[str] = Query(default=[]), min_fit: float | None = None,
                   min_confidence: float | None = None, status: str | None = None, q: str | None = None, job_id: uuid.UUID | None = None,
                   import_status: str | None = None, include_synthetic: bool = False, include_rejected: bool = False,
                   crm_status: str | None = None, sort: str = "fit", page: int = Query(1, ge=1), page_size: int = Query(50, le=500),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Company).where(Company.org_id == user.org_id)
    if country:
        query = query.where(Company.country.in_([c.upper() for c in country]))
    if buyer_type:
        query = query.where(Company.primary_buyer_type.in_(buyer_type))
    if min_fit is not None:
        query = query.where(Company.buyer_fit_score >= min_fit)
    if min_confidence is not None:
        query = query.where(Company.data_confidence_score >= min_confidence)
    if status:
        query = query.where(Company.research_status == status)
    elif not include_rejected:
        query = query.where(Company.research_status != "rejected")
    if import_status:
        query = query.where(Company.import_activity_status == import_status)
    if not include_synthetic:
        query = query.where(Company.is_synthetic.is_(False))
    if job_id:
        query = query.where(Company.id.in_(select(CompanyEvidence.company_id).where(CompanyEvidence.job_id == job_id)))
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(Company.display_name).like(like), Company.normalized_name.like(like),
                                Company.domain.like(like), Company.id.in_(select(CompanyAlias.company_id).where(CompanyAlias.normalized.like(like)))))
    if crm_status:
        query = query.where(Company.id.in_(select(OrganizationLead.company_id).where(OrganizationLead.org_id == user.org_id,
                                                                                     OrganizationLead.crm_status == crm_status)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(SORTS.get(sort, SORTS["fit"])).offset((page - 1) * page_size).limit(page_size)).all()
    leads = {lead.company_id: lead for lead in db.scalars(select(OrganizationLead).where(
        OrganizationLead.org_id == user.org_id, OrganizationLead.company_id.in_([c.id for c in rows])))}
    items = []
    for c in rows:
        it = CompanyListItem.model_validate(c)
        it.crm_status = leads[c.id].crm_status if c.id in leads else "new"
        it.priority = priority_label(c.buyer_fit_score or 0, c.data_confidence_score or 0)
        items.append(it)
    return CompanyPage(total=total, items=items)


@router.get("/reviews")
def match_reviews(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(EntityMatchReview).where(EntityMatchReview.org_id == user.org_id, EntityMatchReview.status == "pending").limit(200)):
        a, b = db.get(Company, r.company_a_id), db.get(Company, r.company_b_id)
        if a and b:
            out.append({"id": str(r.id), "score": r.score, "reasons": r.reasons, "relation": r.suggested_relation,
                        "a": {"id": str(a.id), "name": a.display_name, "city": a.city, "domain": a.domain, "phone": a.phone},
                        "b": {"id": str(b.id), "name": b.display_name, "city": b.city, "domain": b.domain, "phone": b.phone}})
    return out


@router.post("/reviews/{review_id}")
def resolve_review(review_id: uuid.UUID, body: dict, request: Request, user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    r = db.scalar(select(EntityMatchReview).where(EntityMatchReview.id == review_id, EntityMatchReview.org_id == user.org_id))
    if not r:
        raise HTTPException(404)
    decision = body.get("decision")
    if decision not in ("merge", "group", "reject"):
        raise HTTPException(422, "decision must be merge|group|reject")
    if decision in ("merge", "group"):
        merge_companies(db, db.get(Company, r.company_a_id), db.get(Company, r.company_b_id), "group" if decision == "group" else "same_entity")
    r.status = "rejected" if decision == "reject" else "merged"
    audit(db, user, f"entity.{decision}", "entity_match_review", r.id, request=request)
    db.commit()
    return {"ok": True}


@router.get("/{company_id}")
def company_detail(company_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _company(db, user, company_id)
    lead = db.scalar(select(OrganizationLead).where(OrganizationLead.org_id == user.org_id, OrganizationLead.company_id == c.id))
    score = db.scalar(select(CompanyScore).where(CompanyScore.company_id == c.id).order_by(CompanyScore.computed_at.desc()).limit(1))
    reg = {s.key: s for s in db.scalars(select(SourceRegistry))}

    def src(k):
        s = reg.get(k)
        return {"key": k, "name": s.name if s else k, "export_allowed": s.export_allowed if s else True}

    return {
        "company": CompanyListItem.model_validate(c).model_dump(mode="json") | {
            "legal_name": c.legal_name, "address": c.address, "postal_code": c.postal_code, "registration_number": c.registration_number,
            "vat_number": c.vat_number, "registry_status": c.registry_status, "website_status": c.website_status,
            "website_product_match": c.website_product_match, "oem_private_label_signal": c.oem_private_label_signal,
            "rejection_reason": c.rejection_reason, "parent_company_id": str(c.parent_company_id) if c.parent_company_id else None,
            "priority": priority_label(c.buyer_fit_score or 0, c.data_confidence_score or 0)},
        "aliases": [dict(alias=a.alias, script=a.script, type=a.alias_type, source=a.source_key) for a in
                    db.scalars(select(CompanyAlias).where(CompanyAlias.company_id == c.id))],
        "locations": [dict(type=loc.location_type, name=loc.name, address=loc.address, city=loc.city, phone=loc.phone, source=src(loc.source_key),
                           url=loc.source_url, external_ids=loc.external_ids, observed_at=loc.observed_at.isoformat(),
                           retention_until=loc.retention_until.isoformat() if loc.retention_until else None)
                      for loc in db.scalars(select(CompanyLocation).where(CompanyLocation.company_id == c.id))],
        "contacts": [dict(id=str(x.id), type=x.contact_type, value=x.value, person=x.person_name, title=x.job_title, department=x.department,
                          generic=x.is_generic, source=src(x.source_key), url=x.source_url, observed_at=x.observed_at.isoformat(),
                          verified=x.verified, do_not_contact=x.do_not_contact)
                     for x in db.scalars(select(CompanyContact).where(CompanyContact.company_id == c.id))],
        "evidence": [dict(type=e.evidence_type, field=e.field, value=e.value, snippet=e.snippet, source=src(e.source_key), url=e.source_url,
                          observed_at=e.observed_at.isoformat(), confidence=e.confidence,
                          retention_until=e.retention_until.isoformat() if e.retention_until else None)
                     for e in db.scalars(select(CompanyEvidence).where(CompanyEvidence.company_id == c.id).order_by(CompanyEvidence.observed_at.desc()).limit(300))],
        "import_signals": [dict(type=s.signal_type, verified=s.verified, hs_code=s.hs_code, origin=s.origin_country, shipments=s.shipment_count,
                                description=s.description, source=src(s.source_key), url=s.source_url)
                           for s in db.scalars(select(ImportSignal).where(ImportSignal.company_id == c.id))],
        "score": dict(buyer_fit=score.buyer_fit, data_confidence=score.data_confidence, components=score.components,
                      explanation=score.explanation, weights_version=score.weights_version,
                      computed_at=score.computed_at.isoformat()) if score else None,
        "lead": dict(crm_status=lead.crm_status, notes=lead.notes, tags=lead.tags, sales_outcome=lead.sales_outcome,
                     job_ids=lead.job_ids) if lead else None,
    }


@router.patch("/{company_id}/lead")
def update_lead(company_id: uuid.UUID, body: LeadUpdate, request: Request, user: User = Depends(require_role("analyst")),
                db: Session = Depends(get_db)):
    c = _company(db, user, company_id)
    lead = db.scalar(select(OrganizationLead).where(OrganizationLead.org_id == user.org_id, OrganizationLead.company_id == c.id))
    if not lead:
        lead = OrganizationLead(org_id=user.org_id, company_id=c.id, job_ids=[])
        db.add(lead)
    for f, v in body.model_dump(exclude_none=True).items():
        setattr(lead, f, v)
    if body.crm_status == "do_not_contact":
        for ct in db.scalars(select(CompanyContact).where(CompanyContact.company_id == c.id)):
            ct.do_not_contact = True
    audit(db, user, "lead.update", "company", c.id, body.model_dump(exclude_none=True), request)
    db.commit()
    return {"ok": True}


@router.post("/{company_id}/rescore")
def rescore(company_id: uuid.UUID, job_id: uuid.UUID | None = None, user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    c = _company(db, user, company_id)
    job = db.scalar(select(SearchJob).where(SearchJob.id == job_id, SearchJob.org_id == user.org_id)) if job_id else None
    _, res = assess_company(db, c, job, exporter_country=user.organization.exporter_origin_country)
    db.commit()
    return {"buyer_fit": res.buyer_fit, "data_confidence": res.data_confidence, "explanation": res.explanation}


@router.delete("/{company_id}")
def erase(company_id: uuid.UUID, reason: str = "data subject request", user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if not erase_company(db, user.org_id, company_id, user.id, reason):
        raise HTTPException(404)
    return {"ok": True}


@router.post("/import")
async def import_companies(file: UploadFile = File(...), default_country: str | None = Form(None), rights_confirmed: bool = Form(False),
                           request: Request = None, user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    if not rights_confirmed:
        raise HTTPException(422, "confirm that you have the right to use this data (rights_confirmed=true)")
    content = await file.read()
    rows = parse_tabular(content, file.filename or "upload.csv")
    if not rows:
        raise HTTPException(422, "no rows with a company name column found")
    policy = SourcePolicy("csv_import", reliability=0.6)
    created = merged = 0
    for raw in rows_to_raw(rows, default_country, file.filename or "upload.csv"):
        m = resolve_record(db, user.org_id, raw, policy)
        if m:
            created += m.created
            merged += not m.created
            assess_company(db, m.company, None, exporter_country=user.organization.exporter_origin_country, persist_score=False)
    audit(db, user, "companies.import", details={"file": file.filename, "rows": len(rows), "created": created, "merged": merged}, request=request)
    db.commit()
    return {"rows": len(rows), "created": created, "merged": merged}
