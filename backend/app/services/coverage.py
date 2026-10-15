"""Research Coverage Report — makes thin or incomplete research visible instead of calling it success."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.countries import get_country
from app.models import (
    Company,
    CompanyContact,
    CompanyEvidence,
    ResearchCost,
    SearchJob,
    SearchQuery,
    SearchTask,
    SourceRegistry,
    TaskStatus,
)

# Minimum unique furniture-relevant companies we'd expect from a reasonably covered market.
# Large markets with few results trigger a warning instead of silently "completing".
EXPECTED_MIN_BY_REGION = {"europe": 40, "middle_east": 20, "north_africa": 15, "caucasus": 10}
LARGE_MARKETS = {"DE": 120, "FR": 100, "GB": 100, "IT": 80, "ES": 70, "PL": 50, "NL": 40, "SA": 40, "AE": 40, "EG": 30}


def build_coverage_report(db: Session, job: SearchJob) -> dict:
    tasks = db.scalars(select(SearchTask).where(SearchTask.job_id == job.id)).all()
    company_ids = list(db.scalars(select(CompanyEvidence.company_id).where(CompanyEvidence.job_id == job.id).distinct()))
    companies = [db.get(Company, i) for i in company_ids]
    real = [c for c in companies if not c.is_synthetic]
    synthetic = len(companies) - len(real)
    status_counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        status_counts[t.status] += 1

    by_country: dict[str, dict] = {}
    for iso in job.countries:
        ct = [t for t in tasks if t.country == iso]
        cc = [c for c in companies if c.country == iso]
        relevant = [c for c in cc if c.research_status != "rejected" and not c.is_synthetic]
        qualified = [c for c in relevant if (c.buyer_fit_score or 0) >= job.min_buyer_fit]
        cities_searched = sorted({t.city for t in ct if t.city and t.status in (TaskStatus.COMPLETED.value, TaskStatus.NO_RESULTS.value)})
        cfg = get_country(iso)
        restricted = sorted({t.source_key for t in ct if t.status == TaskStatus.ACCESS_RESTRICTED.value})
        manual = sorted({t.source_key for t in ct if t.status == TaskStatus.MANUAL_REVIEW.value})
        paid_skipped = sorted({t.source_key for t in ct if t.status == TaskStatus.SKIPPED_BUDGET.value and "paid" in (t.status_reason or "")})
        used = sorted({t.source_key for t in ct if t.status in (TaskStatus.COMPLETED.value, TaskStatus.NO_RESULTS.value)})
        expected = LARGE_MARKETS.get(iso) or (EXPECTED_MIN_BY_REGION.get(cfg.region, 15) if cfg else 15)
        gaps = []
        if len(relevant) < expected:
            gaps.append(f"only {len(relevant)} real relevant companies (expected ≥{expected} for this market)")
        if cfg and len(cities_searched) < min(3, len(cfg.cities)):
            gaps.append(f"only {len(cities_searched)} cities searched")
        if not [s for s in used if s != "mock"]:
            gaps.append("no real data source executed")
        if not any(c.import_activity_status == "verified" for c in cc):
            gaps.append("no verified importers — licensed shipment data (P2) needed")
        by_country[iso] = {
            "country": cfg.name_en if cfg else iso, "cities_planned": len({t.city for t in ct if t.city}),
            "cities_searched": cities_searched, "sources_used": used, "sources_restricted": restricted,
            "sources_manual": manual, "paid_sources_disabled": paid_skipped,
            "queries": db.scalar(select(func.count(SearchQuery.id)).join(SearchTask).where(SearchQuery.job_id == job.id, SearchTask.country == iso)) or 0,
            "unique_companies": len(cc), "relevant_companies": len(relevant), "qualified_companies": len(qualified),
            "synthetic_companies": len([c for c in cc if c.is_synthetic]), "gaps": gaps,
            "needs_paid_data": bool(restricted) or "no verified importers — licensed shipment data (P2) needed" in gaps,
        }

    queries = db.scalars(select(SearchQuery).where(SearchQuery.job_id == job.id)).all()
    distinct_queries = {(q.source_key, q.normalized_query) for q in queries}
    langs = sorted({q.language for q in queries})
    raw_total = sum(t.raw_results for t in tasks)
    with_contact = sum(1 for c in real if c.general_email or c.phone or db.scalar(
        select(func.count(CompanyContact.id)).where(CompanyContact.company_id == c.id)))
    costs = dict(db.execute(select(ResearchCost.source_key, func.sum(ResearchCost.amount_usd)).where(ResearchCost.job_id == job.id)
                            .group_by(ResearchCost.source_key)).all())
    qualified_real = [c for c in real if c.research_status != "rejected" and (c.buyer_fit_score or 0) >= job.min_buyer_fit]
    spent = float(job.spent_usd or 0)

    source_perf = []
    reg = {s.key: s for s in db.scalars(select(SourceRegistry))}
    for key in sorted({t.source_key for t in tasks}):
        st = [t for t in tasks if t.source_key == key]
        found = [c for c in companies if key in (c.sources or [])]
        source_perf.append({
            "source": key, "name": reg[key].name if key in reg else key, "tasks": len(st),
            "queries": sum(t.queries_run for t in st), "raw_results": sum(t.raw_results for t in st),
            "new_unique": sum(t.new_unique for t in st),
            "qualified": len([c for c in found if (c.buyer_fit_score or 0) >= job.min_buyer_fit and c.research_status != "rejected"]),
            "cost_usd": round(float(costs.get(key, 0) or 0), 4),
            "duplicate_rate": round(1 - sum(t.new_unique for t in st) / max(1, sum(t.raw_results for t in st)), 3),
            "errors": len([t for t in st if t.status in (TaskStatus.FAILED.value, TaskStatus.RATE_LIMITED.value)]),
            "statuses": dict(_count(t.status for t in st)),
        })

    warnings = []
    for iso, d in by_country.items():
        for g in d["gaps"]:
            warnings.append(f"{iso}: {g}")
    if synthetic and synthetic == len(companies):
        warnings.insert(0, "All results are SYNTHETIC demo data — configure real sources (API keys) for actual leads")
    if job.stop_reason == "budget exhausted":
        warnings.append("budget exhausted before plan completed")
    if status_counts.get(TaskStatus.FAILED.value):
        warnings.append(f"{status_counts[TaskStatus.FAILED.value]} plan cells failed")

    return {
        "countries_requested": len(job.countries), "countries_researched": len([d for d in by_country.values() if d["sources_used"]]),
        "cities_searched": sum(len(d["cities_searched"]) for d in by_country.values()),
        "sources_used": sorted({k for d in by_country.values() for k in d["sources_used"]}),
        "sources_unreachable": sorted({k for d in by_country.values() for k in d["sources_restricted"]}),
        "sources_manual": sorted({k for d in by_country.values() for k in d["sources_manual"]}),
        "local_language_queries": len(distinct_queries), "languages": langs,
        "raw_records": raw_total, "unique_companies": len(companies), "real_companies": len(real), "synthetic_companies": synthetic,
        "duplicate_rate": round(1 - len(companies) / raw_total, 3) if raw_total else 0.0,
        "product_verified": len([c for c in real if c.website_product_match and c.website_product_match >= 0.4]),
        "importers_verified": len([c for c in real if c.import_activity_status == "verified"]),
        "importers_claimed": len([c for c in real if c.import_activity_status == "claimed"]),
        "contact_enriched": with_contact, "registry_verified": len([c for c in real if c.research_status == "verified"]),
        "rejected": len([c for c in companies if c.research_status == "rejected"]),
        "qualified_real": len(qualified_real),
        "budget_usd": job.budget_usd, "spent_usd": round(spent, 4),
        "cost_per_qualified_lead_usd": round(spent / len(qualified_real), 4) if qualified_real else None,
        "task_status_counts": dict(status_counts), "by_country": by_country, "source_performance": source_perf,
        "countries_needing_paid_data": sorted(iso for iso, d in by_country.items() if d["needs_paid_data"]),
        "warnings": warnings,
    }


def _count(it):
    d: dict = defaultdict(int)
    for x in it:
        d[x] += 1
    return d
