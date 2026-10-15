import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.countries import COUNTRIES
from app.data.terms import PRODUCT_LABELS
from app.db import get_db
from app.deps import audit, current_user, require_role
from app.models import JobStatus, ManualResearchItem, SearchJob, SearchQuery, SearchTask, User
from app.schemas import BUYER_TYPE_CODES, JobCreate, JobOut, TaskOut
from app.services.coverage import build_coverage_report
from app.services.product_catalog import analyze_catalog_text, extract_text
from app.services.request_parser import parse_request
from app.worker import dispatch_job

router = APIRouter(prefix="/api/research", tags=["research"])


def _job(db: Session, user: User, job_id: uuid.UUID) -> SearchJob:
    job = db.scalar(select(SearchJob).where(SearchJob.id == job_id, SearchJob.org_id == user.org_id))
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.get("/options")
def options():
    return {
        "countries": [{"code": c.iso2, "name": c.name_en, "name_tr": c.name_tr, "region": c.region, "languages": list(c.languages),
                       "cities": [x.local_name or x.name for x in c.cities]} for c in COUNTRIES.values()],
        "product_categories": [{"code": k, "label": v} for k, v in PRODUCT_LABELS.items()],
        "buyer_types": BUYER_TYPE_CODES,
    }


@router.post("/parse")
def parse(body: dict):
    return parse_request(body.get("text", ""))


@router.post("/catalog/analyze")
async def analyze_catalog(file: UploadFile = File(...), user: User = Depends(current_user)):
    content = await file.read()
    if len(content) > 30_000_000:
        raise HTTPException(413, "catalogue too large (max 30MB)")
    try:
        text = extract_text(content, file.filename or "catalog.txt")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"could not read file: {exc}") from exc
    return analyze_catalog_text(text)


@router.post("/jobs", response_model=JobOut)
def create_job(body: JobCreate, request: Request, user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    parsed = parse_request(body.request_text) if body.request_text else {}
    countries = body.countries or parsed.get("countries", [])
    if not countries:
        raise HTTPException(422, "no target countries given or recognised in the request text")
    product = body.product.model_dump()
    if body.product.categories == ["home_furniture"] and parsed.get("product_categories"):
        product["categories"] = parsed["product_categories"]
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    org = user.organization
    used = db.scalar(select(func.count(SearchJob.id)).where(SearchJob.org_id == user.org_id, SearchJob.created_at >= month_start)) or 0
    if used >= org.monthly_job_quota:
        raise HTTPException(429, f"monthly job quota reached ({org.monthly_job_quota})")
    spent = db.scalar(select(func.coalesce(func.sum(SearchJob.spent_usd), 0)).where(SearchJob.org_id == user.org_id,
                                                                                    SearchJob.created_at >= month_start)) or 0
    if spent + body.budget_usd > float(org.monthly_research_budget_usd):
        raise HTTPException(402, f"job budget exceeds remaining monthly research budget ({float(org.monthly_research_budget_usd) - spent:.2f} USD)")
    job = SearchJob(
        org_id=user.org_id, created_by=user.id, name=body.name or f"{', '.join(countries)} — {', '.join(product['categories'])}",
        request_text=body.request_text, countries=countries, buyer_types=body.buyer_types or parsed.get("buyer_types", []),
        product_config=product, target_company_count=body.target_company_count, min_buyer_fit=body.min_buyer_fit,
        budget_usd=body.budget_usd, use_paid_sources=body.use_paid_sources, selected_sources=body.selected_sources,
        status=JobStatus.QUEUED.value if body.start else JobStatus.DRAFT.value,
    )
    db.add(job)
    db.flush()
    audit(db, user, "job.create", "search_job", job.id, {"countries": countries, "budget": body.budget_usd}, request)
    db.commit()
    if body.start:
        dispatch_job(job.id)
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(SearchJob).where(SearchJob.org_id == user.org_id).order_by(SearchJob.created_at.desc()).limit(200)).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _job(db, user, job_id)


@router.post("/jobs/{job_id}/start", response_model=JobOut)
def start_job(job_id: uuid.UUID, user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    job = _job(db, user, job_id)
    if job.status not in (JobStatus.DRAFT.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value):
        raise HTTPException(409, f"job is {job.status}")
    job.status, job.cancel_requested, job.error = JobStatus.QUEUED.value, False, None
    db.commit()
    dispatch_job(job.id)
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    job = _job(db, user, job_id)
    job.cancel_requested = True
    db.commit()
    return job


@router.get("/jobs/{job_id}/monitor")
def monitor(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _job(db, user, job_id)
    rows = db.execute(select(SearchTask.country, SearchTask.source_key, SearchTask.status, func.count(SearchTask.id),
                             func.sum(SearchTask.raw_results), func.sum(SearchTask.new_unique), func.sum(SearchTask.cost_usd))
                      .where(SearchTask.job_id == job.id).group_by(SearchTask.country, SearchTask.source_key, SearchTask.status)).all()
    by_country: dict = {}
    by_source: dict = {}
    for country, src, status, n, raw, new, cost in rows:
        for bucket, key in ((by_country, country), (by_source, src)):
            b = bucket.setdefault(key, {"tasks": 0, "statuses": {}, "raw": 0, "new_unique": 0, "cost_usd": 0.0})
            b["tasks"] += n
            b["statuses"][status] = b["statuses"].get(status, 0) + n
            b["raw"] += raw or 0
            b["new_unique"] += new or 0
            b["cost_usd"] = round(b["cost_usd"] + float(cost or 0), 4)
    errors = db.execute(select(SearchTask.source_key, SearchTask.country, SearchTask.city, SearchTask.status, SearchTask.status_reason)
                        .where(SearchTask.job_id == job.id, SearchTask.status.in_(["failed", "rate_limited", "access_restricted", "retry_scheduled"]))
                        .limit(50)).all()
    recent = db.scalars(select(SearchQuery).where(SearchQuery.job_id == job.id).order_by(SearchQuery.executed_at.desc()).limit(15)).all()
    return {
        "job": JobOut.model_validate(job).model_dump(mode="json"), "by_country": by_country, "by_source": by_source,
        "errors": [dict(source=e[0], country=e[1], city=e[2], status=e[3], reason=e[4]) for e in errors],
        "recent_queries": [dict(source=q.source_key, query=q.query_text, language=q.language, page=q.page, results=q.result_count,
                                new=q.new_companies, at=q.executed_at.isoformat()) for q in recent],
    }


@router.get("/jobs/{job_id}/tasks", response_model=list[TaskOut])
def tasks(job_id: uuid.UUID, status: str | None = None, limit: int = Query(500, le=5000), user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    job = _job(db, user, job_id)
    q = select(SearchTask).where(SearchTask.job_id == job.id)
    if status:
        q = q.where(SearchTask.status == status)
    return db.scalars(q.order_by(SearchTask.priority.desc()).limit(limit)).all()


@router.get("/jobs/{job_id}/coverage")
def coverage(job_id: uuid.UUID, refresh: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _job(db, user, job_id)
    if refresh or not job.coverage_report:
        return build_coverage_report(db, job)
    return job.coverage_report


@router.get("/jobs/{job_id}/manual-queue")
def manual_queue(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = _job(db, user, job_id)
    items = db.scalars(select(ManualResearchItem).where(ManualResearchItem.job_id == job.id)).all()
    return [dict(id=str(i.id), source=i.source_key, instructions=i.instructions, queries=i.suggested_queries, status=i.status) for i in items]
