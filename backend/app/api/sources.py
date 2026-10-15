import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.registry import build_connector, resolve_access
from app.db import get_db
from app.deps import audit, current_user, require_role
from app.models import Company, ResearchCost, SourceExecution, SourcePermission, SourceRegistry, User
from app.schemas import SourceCredentialsIn, SourceIn, SourceReview
from app.security import decrypt_secret, encrypt_secret, mask_secret
from app.services.source_catalog import source_discovery_queries

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _perm(db: Session, org_id, key: str) -> SourcePermission | None:
    return db.scalar(select(SourcePermission).where(SourcePermission.org_id == org_id, SourcePermission.source_key == key))


def _serialize(db: Session, user: User, s: SourceRegistry) -> dict:
    perm = _perm(db, user.org_id, s.key)
    access = resolve_access(db, user.org_id, s)
    creds = {}
    if perm and perm.credentials_encrypted:
        try:
            creds = json.loads(decrypt_secret(perm.credentials_encrypted))
        except Exception:  # noqa: BLE001
            creds = {}
    return {
        "key": s.key, "name": s.name, "url": s.url, "tier": s.tier, "purposes": s.purposes, "countries": s.countries,
        "access_model": s.access_model, "integration_status": s.integration_status, "has_api": s.has_api, "auth_required": s.auth_required,
        "pricing": s.pricing, "terms_url": s.terms_url, "terms_summary": s.terms_summary, "storage_allowed": s.storage_allowed,
        "max_retention_days": s.max_retention_days, "export_allowed": s.export_allowed, "merge_allowed": s.merge_allowed,
        "rate_limit": s.rate_limit, "data_fields": s.data_fields, "reliability": s.reliability, "cost_per_request_usd": s.cost_per_request_usd,
        "product_searchable": s.product_searchable, "customer_types": s.customer_types, "notes": s.notes, "review_status": s.review_status,
        "discovered_automatically": s.discovered_automatically, "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
        "usable": access.usable, "blocked_reason": access.reason or None,
        "permission": {"enabled": perm.enabled if perm else None, "license_confirmed": perm.license_confirmed if perm else False,
                       "license_reference": perm.license_reference if perm else None, "api_key_masked": mask_secret(creds.get("api_key")),
                       "endpoint": creds.get("endpoint"), "monthly_budget_usd": perm.monthly_budget_usd if perm else None,
                       "last_health_status": perm.last_health_status if perm else None,
                       "last_health_message": perm.last_health_message if perm else None,
                       "last_health_at": perm.last_health_at.isoformat() if perm and perm.last_health_at else None},
    }


@router.get("")
def list_sources(country: str | None = None, include_pending: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(SourceRegistry)
    if not include_pending:
        q = q.where(SourceRegistry.review_status == "approved")
    rows = db.scalars(q.order_by(SourceRegistry.tier, SourceRegistry.name)).all()
    if country:
        rows = [r for r in rows if "*" in r.countries or country.upper() in r.countries]
    # performance stats for this org
    stats = {k: (n, cost) for k, n, cost in db.execute(
        select(SourceExecution.source_key, func.count(SourceExecution.id), func.sum(SourceExecution.cost_usd))
        .where(SourceExecution.org_id == user.org_id).group_by(SourceExecution.source_key))}
    spend = dict(db.execute(select(ResearchCost.source_key, func.sum(ResearchCost.amount_usd)).where(ResearchCost.org_id == user.org_id)
                            .group_by(ResearchCost.source_key)).all())
    qualified_by_source: dict[str, int] = {}
    for srcs in db.scalars(select(Company.sources).where(Company.org_id == user.org_id, Company.buyer_fit_score >= 60,
                                                         Company.is_synthetic.is_(False), Company.research_status != "rejected")):
        for k in srcs or []:
            qualified_by_source[k] = qualified_by_source.get(k, 0) + 1
    out = []
    for s in rows:
        d = _serialize(db, user, s)
        n_exec, _ = stats.get(s.key, (0, 0))
        qualified = qualified_by_source.get(s.key, 0)
        d["stats"] = {"executions": n_exec, "spend_usd": round(float(spend.get(s.key, 0) or 0), 4), "qualified_companies": qualified,
                      "avg_cost_usd": round(float(spend.get(s.key, 0) or 0) / n_exec, 5) if n_exec else None}
        out.append(d)
    return out


@router.get("/matrix")
def integration_matrix(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Source inventory & integration suitability matrix."""
    rows = db.scalars(select(SourceRegistry).where(SourceRegistry.review_status == "approved").order_by(SourceRegistry.tier)).all()
    return [{"key": s.key, "name": s.name, "tier": s.tier, "purposes": s.purposes, "countries": s.countries, "access_model": s.access_model,
             "integration_status": s.integration_status, "api": s.has_api, "auth": s.auth_required, "pricing": s.pricing,
             "export_allowed": s.export_allowed, "retention_days": s.max_retention_days, "usable_now": resolve_access(db, user.org_id, s).usable}
            for s in rows]


@router.get("/discovery-queries/{country}")
def discovery_queries(country: str, user: User = Depends(current_user)):
    return [{"query": q, "language": lang} for q, lang in source_discovery_queries(country.upper())]


@router.put("/{key}/permission")
def set_permission(key: str, body: SourceCredentialsIn, request: Request, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    src = db.scalar(select(SourceRegistry).where(SourceRegistry.key == key))
    if not src:
        raise HTTPException(404)
    perm = _perm(db, user.org_id, key)
    if not perm:
        perm = SourcePermission(org_id=user.org_id, source_key=key, enabled=True)
        db.add(perm)
    if body.enabled is not None:
        perm.enabled = body.enabled
    if body.api_key is not None or body.endpoint is not None:
        creds = {}
        if perm.credentials_encrypted:
            try:
                creds = json.loads(decrypt_secret(perm.credentials_encrypted))
            except Exception:  # noqa: BLE001
                creds = {}
        if body.api_key is not None:
            creds["api_key"] = body.api_key
        if body.endpoint is not None:
            creds["endpoint"] = body.endpoint
        perm.credentials_encrypted = encrypt_secret(json.dumps(creds)) if any(creds.values()) else None
    if body.license_confirmed is not None:
        perm.license_confirmed = body.license_confirmed
        perm.confirmed_by = user.id if body.license_confirmed else None
        perm.confirmed_at = datetime.now(UTC) if body.license_confirmed else None
    if body.license_reference is not None:
        perm.license_reference = body.license_reference
    if body.monthly_budget_usd is not None:
        perm.monthly_budget_usd = body.monthly_budget_usd
    audit(db, user, "source.permission", "source", key, {"enabled": body.enabled, "license_confirmed": body.license_confirmed,
                                                        "api_key_changed": body.api_key is not None}, request)
    db.commit()
    return _serialize(db, user, src)


@router.post("/{key}/health")
async def health(key: str, user: User = Depends(require_role("analyst")), db: Session = Depends(get_db)):
    src = db.scalar(select(SourceRegistry).where(SourceRegistry.key == key))
    if not src:
        raise HTTPException(404)
    access = resolve_access(db, user.org_id, src)
    perm = _perm(db, user.org_id, key) or SourcePermission(org_id=user.org_id, source_key=key, enabled=True)
    if not access.usable and src.connector_key in (None, ""):
        status, message = ("manual" if access.status_if_blocked == "manual_review_required" else "not_configured"), access.reason
    else:
        conn = build_connector(access)
        try:
            h = await conn.health_check()
            status, message = h.status, h.message
            if not access.usable and status == "ok":
                status, message = "not_configured", access.reason
        finally:
            await conn.aclose()
    perm.last_health_status, perm.last_health_message, perm.last_health_at = status, message, datetime.now(UTC)
    db.add(perm)
    src.last_checked_at = datetime.now(UTC)
    db.add(SourceExecution(org_id=user.org_id, source_key=key, operation="health", status=status, error=None if status == "ok" else message))
    db.commit()
    return {"status": status, "message": message}


@router.post("")
def add_source(body: SourceIn, request: Request, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if db.scalar(select(SourceRegistry).where(SourceRegistry.key == body.key)):
        raise HTTPException(409, "key exists")
    s = SourceRegistry(**body.model_dump(), integration_status="catalog_only" if body.access_model != "manual" else "manual",
                       review_status="approved", last_checked_at=datetime.now(UTC))
    db.add(s)
    audit(db, user, "source.create", "source", body.key, request=request)
    db.commit()
    return _serialize(db, user, s)


@router.post("/{key}/review")
def review_source(key: str, body: SourceReview, request: Request, user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    s = db.scalar(select(SourceRegistry).where(SourceRegistry.key == key))
    if not s:
        raise HTTPException(404)
    s.review_status = body.review_status
    if body.access_model:
        s.access_model = body.access_model
    if body.terms_summary is not None:
        s.terms_summary = body.terms_summary
    if body.notes is not None:
        s.notes = body.notes
    s.last_checked_at = datetime.now(UTC)
    audit(db, user, "source.review", "source", key, body.model_dump(), request)
    db.commit()
    return _serialize(db, user, s)


_ = uuid
