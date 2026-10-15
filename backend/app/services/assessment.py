"""(Re)classify and score a company from everything stored about it."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    CompanyCategory,
    CompanyContact,
    CompanyEvidence,
    CompanyLocation,
    CompanyScore,
    ImportSignal,
    SearchJob,
    SourceRegistry,
)
from app.services.classifier import Classification, classify
from app.services.scoring import WEIGHTS_VERSION, ScoreInput, ScoreResult, compute_scores


def _reliability_map(db: Session) -> dict[str, float]:
    return {k: r for k, r in db.execute(select(SourceRegistry.key, SourceRegistry.reliability))}


def assess_company(db: Session, c: Company, job: SearchJob | None, website_text: str = "", reliability: dict | None = None,
                   exporter_country: str = "TR", persist_score: bool = True) -> tuple[Classification, ScoreResult]:
    reliability = reliability or _reliability_map(db)
    evid = db.scalars(select(CompanyEvidence).where(CompanyEvidence.company_id == c.id)).all()
    cats: list[str] = []
    descs: list[str] = []
    field_sources: dict[tuple[str, str], set[str]] = defaultdict(set)
    last_obs = None
    for e in evid:
        if e.field == "source_categories" and e.value:
            cats += [x.strip() for x in e.value.split(",") if x.strip()]
        if e.field == "name" and e.snippet:
            descs.append(e.snippet)
        if e.evidence_type == "website_content" and e.snippet and (e.field or "").startswith("signal:"):
            descs.append(e.snippet)
        if e.evidence_type == "website_content" and e.field == "product_match" and e.value:
            descs.append(e.value)
        if e.field in ("phone", "website", "address", "email", "vat_number", "registration_number") and e.value:
            field_sources[(e.field, e.value.lower())].add(e.source_key)
        obs = e.observed_at.replace(tzinfo=UTC) if e.observed_at and e.observed_at.tzinfo is None else e.observed_at
        if obs and (last_obs is None or obs > last_obs):
            last_obs = obs
    signals = db.scalars(select(ImportSignal).where(ImportSignal.company_id == c.id)).all()
    loc_count = db.scalar(select(func.count(CompanyLocation.id)).where(CompanyLocation.company_id == c.id)) or 0
    contacts = db.scalars(select(CompanyContact).where(CompanyContact.company_id == c.id, CompanyContact.do_not_contact.is_(False))).all()
    verified_imp = sum(1 for s in signals if s.verified)
    claimed_imp = sum(1 for s in signals if not s.verified)

    cl = classify(name=c.display_name, source_categories=cats, descriptions=descs, website_text=website_text,
                  verified_import=verified_imp > 0, claimed_import=claimed_imp > 0, store_count=c.store_count,
                  location_count=loc_count, source_keys=c.sources or [])
    pc = job.product_config if job else {}
    si = ScoreInput(
        classification=cl, country=c.country, target_products=(pc or {}).get("categories") or [],
        target_buyer_types=(job.buyer_types if job else []) or [], website_product_match=c.website_product_match,
        website_status=c.website_status, store_count=c.store_count, location_count=loc_count, employee_count=c.employee_count,
        has_general_email=bool(c.general_email) or any(x.contact_type == "email" for x in contacts),
        has_phone=bool(c.phone), has_website=bool(c.website),
        has_purchasing_contact=any(x.department == "purchasing" for x in contacts),
        source_keys=c.sources or [], source_reliability=reliability,
        registry_verified=c.registry_status == "active" and any(e.evidence_type == "registry_record" for e in evid),
        vat_verified=any(e.evidence_type == "vat_check" and "valid=True" in (e.snippet or "") for e in evid),
        import_signals_verified=verified_imp, import_signals_claimed=claimed_imp,
        corroborated_fields=sum(1 for s in field_sources.values() if len(s) >= 2), last_observed=last_obs,
        is_synthetic=c.is_synthetic, exporter_country=exporter_country,
    )
    res = compute_scores(si)

    # Persist classification
    c.buyer_types = sorted(cl.buyer_types, key=lambda t: -cl.buyer_types[t])
    c.primary_buyer_type = cl.primary
    c.product_categories = sorted(set(cl.product_categories))
    c.import_activity_status = cl.import_status
    c.oem_private_label_signal = c.oem_private_label_signal or cl.oem_signal
    c.buyer_fit_score = res.buyer_fit
    c.data_confidence_score = res.data_confidence
    if cl.reject_reason:
        c.research_status = "rejected"
        c.rejection_reason = cl.reject_reason
    elif c.research_status == "rejected":
        c.research_status = "discovered"
        c.rejection_reason = None
    db.query(CompanyCategory).filter(CompanyCategory.company_id == c.id).delete()
    for t, conf in cl.buyer_types.items():
        db.add(CompanyCategory(company_id=c.id, kind="buyer_type", code=t, confidence=conf, reasons=cl.reasons.get(t, [])))
    for p in set(cl.product_categories):
        db.add(CompanyCategory(company_id=c.id, kind="product", code=p, confidence=0.7, reasons=[]))
    if persist_score:
        db.add(CompanyScore(company_id=c.id, job_id=job.id if job else None, buyer_fit=res.buyer_fit, data_confidence=res.data_confidence,
                            components={"fit": res.components, "confidence": res.confidence_components},
                            explanation=res.explanation, weights_version=WEIGHTS_VERSION, computed_at=datetime.now(UTC)))
    db.flush()
    return cl, res
