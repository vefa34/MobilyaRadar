from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, require_role
from app.models import Company, CompanyScore, OrganizationLead, ResearchCost, SearchJob, SourceExecution, User
from app.services.retention import purge_expired
from app.services.scoring import DEFAULT_WEIGHTS, WEIGHTS_VERSION, calibration_report

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(include_synthetic: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    base = [Company.org_id == user.org_id, Company.research_status != "rejected"]
    if not include_synthetic:
        base.append(Company.is_synthetic.is_(False))
    total = db.scalar(select(func.count(Company.id)).where(*base)) or 0
    by_country = dict(db.execute(select(Company.country, func.count(Company.id)).where(*base).group_by(Company.country)).all())
    by_type = dict(db.execute(select(Company.primary_buyer_type, func.count(Company.id)).where(*base).group_by(Company.primary_buyer_type)).all())
    avg_fit = db.scalar(select(func.avg(Company.buyer_fit_score)).where(*base))
    verified_importers = db.scalar(select(func.count(Company.id)).where(*base, Company.import_activity_status == "verified")) or 0
    high_priority = db.scalar(select(func.count(Company.id)).where(*base, Company.buyer_fit_score >= 75, Company.data_confidence_score >= 60)) or 0
    spent = db.scalar(select(func.coalesce(func.sum(ResearchCost.amount_usd), 0)).where(ResearchCost.org_id == user.org_id)) or 0
    synthetic = db.scalar(select(func.count(Company.id)).where(Company.org_id == user.org_id, Company.is_synthetic.is_(True))) or 0
    jobs = db.scalars(select(SearchJob).where(SearchJob.org_id == user.org_id).order_by(SearchJob.created_at.desc()).limit(5)).all()
    perf = db.execute(select(SourceExecution.source_key, func.count(SourceExecution.id), func.sum(SourceExecution.result_count),
                             func.sum(SourceExecution.cost_usd),
                             func.sum(case((SourceExecution.status != "ok", 1), else_=0)))
                      .where(SourceExecution.org_id == user.org_id, SourceExecution.operation == "discover")
                      .group_by(SourceExecution.source_key)).all()
    spend_by_source = dict(db.execute(select(ResearchCost.source_key, func.sum(ResearchCost.amount_usd)).where(
        ResearchCost.org_id == user.org_id).group_by(ResearchCost.source_key)).all())
    return {
        "total_companies": total, "by_country": by_country, "by_buyer_type": by_type, "avg_buyer_fit": round(float(avg_fit), 1) if avg_fit else None,
        "verified_importers": verified_importers, "high_priority": high_priority, "research_spend_usd": round(float(spent), 4),
        "synthetic_companies": synthetic,
        "source_performance": [{"source": s, "calls": n, "records": int(r or 0), "cost_usd": round(float(c or 0), 4), "errors": int(e or 0),
                                "spend_usd": round(float(spend_by_source.get(s, 0) or 0), 4)} for s, n, r, c, e in perf],
        "recent_jobs": [{"id": str(j.id), "name": j.name, "status": j.status, "spent_usd": j.spent_usd, "created_at": j.created_at.isoformat(),
                         "unique_companies": (j.coverage_report or {}).get("unique_companies") or (j.progress or {}).get("unique_companies")}
                        for j in jobs],
    }


@router.get("/calibration")
def calibration(user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    """Component averages per CRM outcome — input for recalibrating Buyer Fit weights."""
    rows = []
    for lead in db.scalars(select(OrganizationLead).where(OrganizationLead.org_id == user.org_id, OrganizationLead.sales_outcome.is_not(None))):
        sc = db.scalar(select(CompanyScore).where(CompanyScore.company_id == lead.company_id).order_by(CompanyScore.computed_at.desc()).limit(1))
        if sc:
            rows.append(((sc.components or {}).get("fit", {}), lead.sales_outcome))
    return {"weights_version": WEIGHTS_VERSION, "weights": DEFAULT_WEIGHTS, "outcomes": len(rows), "by_outcome": calibration_report(rows),
            "note": "Collect ≥50 won/lost outcomes before changing weights."}


@router.post("/maintenance/purge-expired")
def purge(user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return purge_expired(db)
