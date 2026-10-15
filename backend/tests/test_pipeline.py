import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.connectors import registry
from app.connectors.base import (
    ConnectorContext,
    ConnectorError,
    DiscoveryQuery,
    DiscoveryResult,
    LeadSourceConnector,
    RateLimitedError,
    RawCompany,
)
from app.models import (
    Company,
    CompanyEvidence,
    ManualResearchItem,
    OrganizationLead,
    SearchJob,
    SearchQuery,
    SearchTask,
    SourceRegistry,
    TaskStatus,
)
from app.services import pipeline as pl
from app.services.export import build_rows, to_csv, to_xlsx
from app.services.pipeline import run_job_async
from app.services.retention import purge_expired


def make_job(db, org, **kw):
    base = dict(org_id=org.id, name="t", countries=["DE", "MA", "GE"], buyer_types=["wholesaler", "retail_chain", "independent_store"],
                product_config={"categories": ["dining_table", "chair"]}, target_company_count=150, budget_usd=2.0, min_buyer_fit=40,
                selected_sources=["mock"])
    base.update(kw)
    job = SearchJob(**base)
    db.add(job)
    db.commit()
    return job


def run(db, job, **kw):
    return asyncio.run(run_job_async(db, job.id, **kw))


def test_full_mock_pipeline(db, org):
    # Few cities + large target → the whole plan runs and sources return overlapping companies.
    job = make_job(db, org, countries=["GE", "MA"], target_company_count=400)
    job = run(db, job)
    assert job.status in ("completed", "completed_partial"), job.error
    rep = job.coverage_report
    assert rep["unique_companies"] > 50
    assert rep["raw_records"] > rep["unique_companies"]  # dedup happened
    assert rep["synthetic_companies"] == rep["unique_companies"]
    assert rep["warnings"][0].startswith("All results are SYNTHETIC")
    # multiple cities per country, not only the capital
    for iso in ("MA", "GE"):
        assert len(rep["by_country"][iso]["cities_searched"]) >= 3, rep["by_country"][iso]
    # budget accounting
    assert 0 < job.spent_usd <= job.budget_usd
    # every company has traceable evidence
    for c in db.scalars(select(Company)):
        assert db.scalar(select(func.count(CompanyEvidence.id)).where(CompanyEvidence.company_id == c.id, CompanyEvidence.source_url.is_not(None)))
        assert c.is_synthetic and c.data_confidence_score == 0
    # enrichment ran on synthetic websites and produced classified, scored companies
    scored = db.scalars(select(Company).where(Company.buyer_fit_score.is_not(None))).all()
    assert len(scored) == rep["unique_companies"]
    assert {c.primary_buyer_type for c in scored} >= {"wholesaler", "independent_store"}
    assert any(c.research_status == "rejected" for c in scored)  # used furniture / irrelevant filtered
    assert not any(c.import_activity_status == "verified" for c in scored)  # no shipment data → never "verified"
    assert db.scalar(select(func.count(OrganizationLead.id))) == rep["unique_companies"]
    # queries are never repeated within a source
    qs = db.execute(select(SearchQuery.source_key, SearchQuery.normalized_query, SearchQuery.page)).all()
    assert len(qs) == len(set(qs))


def test_synthetic_never_exported_by_default(db, org):
    job = run(db, make_job(db, org, countries=["GE"], target_company_count=20))
    rows, stats = build_rows(db, org.id, job_id=job.id)
    assert rows == []
    rows, _ = build_rows(db, org.id, job_id=job.id, include_synthetic=True)
    assert rows and all(r["is_synthetic"] for r in rows)
    assert to_csv(rows).startswith("﻿".encode())
    assert to_xlsx(rows, {"a": 1})[:2] == b"PK"


def test_budget_is_never_exceeded(db, org):
    job = run(db, make_job(db, org, budget_usd=0.0045, target_company_count=2000))
    assert job.spent_usd <= 0.0045 + 1e-9
    assert job.stop_reason in ("budget exhausted",) or db.scalar(select(func.count(SearchTask.id)).where(
        SearchTask.job_id == job.id, SearchTask.status == TaskStatus.SKIPPED_BUDGET.value))


def test_discovery_spreads_across_countries_and_cities(db, org):
    job = run(db, make_job(db, org, countries=["DE", "FR", "IQ"], target_company_count=60))
    rep = job.coverage_report["by_country"]
    assert all(len(rep[iso]["cities_searched"]) >= 2 for iso in ("DE", "FR", "IQ")), rep


def test_target_reached_stops_discovery(db, org):
    job = run(db, make_job(db, org, countries=["DE"], target_company_count=10))
    assert db.scalar(select(func.count(SearchTask.id)).where(SearchTask.job_id == job.id,
                                                             SearchTask.status == TaskStatus.SKIPPED_TARGET_REACHED.value)) > 0


def test_unavailable_sources_are_reported_not_hidden(db, org):
    job = run(db, make_job(db, org, countries=["DE"], selected_sources=["mock", "brave_search", "panjiva", "gelbe_seiten", "europages"],
                           target_company_count=20))
    st = {t.source_key: (t.status, t.status_reason) for t in db.scalars(select(SearchTask).where(SearchTask.job_id == job.id, SearchTask.priority < 0))}
    assert st["brave_search"][0] == "access_restricted" and "API key" in st["brave_search"][1]
    assert st["europages"][0] == "access_restricted" and "licence" in st["europages"][1]
    assert st["gelbe_seiten"][0] == "manual_review_required"
    assert db.scalar(select(func.count(ManualResearchItem.id)).where(ManualResearchItem.job_id == job.id)) >= 1
    rep = job.coverage_report["by_country"]["DE"]
    assert "brave_search" in rep["sources_restricted"] and "gelbe_seiten" in rep["sources_manual"]


# ------------------------------------------------------------------ fake connectors for failure modes
class FlakyConnector(LeadSourceConnector):
    key = "flaky"
    calls = 0
    mode = "ratelimit_once"
    max_pages = 1

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        type(self).calls += 1
        if self.mode == "ratelimit_once" and type(self).calls == 1:
            raise RateLimitedError("429", retry_after=0.01)
        if self.mode == "down":
            raise ConnectorError("connection refused")
        return DiscoveryResult(records=[RawCompany(name=f"Real Möbel {query.city} {type(self).calls}", source_key="flaky", country=query.country,
                                                   city=query.city, website=f"https://real-{type(self).calls}.de",
                                                   source_url=f"https://example.org/{type(self).calls}")], cost_usd=0.01)


@pytest.fixture
def flaky(db, monkeypatch):
    registry.CONNECTOR_CLASSES["flaky"] = FlakyConnector
    FlakyConnector.calls = 0
    db.add(SourceRegistry(key="flaky", name="Flaky", tier="P0", purposes=["discovery"], countries=["*"], access_model="official_api",
                          integration_status="active", connector_key="flaky", reliability=0.6, cost_per_request_usd=0.01))
    db.commit()

    async def no_enrich(self, snap, ctx):
        from app.connectors.base import EnrichmentResult
        return EnrichmentResult(status="unreachable")
    monkeypatch.setattr("app.connectors.website.WebsiteConnector.enrich", no_enrich)
    yield FlakyConnector
    registry.CONNECTOR_CLASSES.pop("flaky", None)


def test_rate_limited_task_is_retried(db, org, flaky):
    flaky.mode = "ratelimit_once"
    job = run(db, make_job(db, org, countries=["GE"], buyer_types=["wholesaler"], selected_sources=["flaky"], target_company_count=500))
    tasks = db.scalars(select(SearchTask).where(SearchTask.job_id == job.id, SearchTask.source_key == "flaky")).all()
    assert any(t.attempts == 2 and t.status in ("completed", "no_results") for t in tasks)
    assert job.status in ("completed", "completed_partial")
    # Real (non-synthetic) companies are exportable with evidence URLs
    rows, _ = build_rows(db, org.id, job_id=job.id, include_rejected=True)
    assert rows and all(r["evidence_urls"] for r in rows)


def test_circuit_breaker_stops_dead_source(db, org, flaky, monkeypatch):
    flaky.mode = "down"
    monkeypatch.setattr(pl, "MAX_TASK_ATTEMPTS", 1)
    job = run(db, make_job(db, org, countries=["DE"], buyer_types=["wholesaler"], selected_sources=["flaky"]))
    assert flaky.calls == pl.CIRCUIT_BREAKER_FAILURES
    statuses = {t.status for t in db.scalars(select(SearchTask).where(SearchTask.job_id == job.id, SearchTask.source_key == "flaky"))}
    assert statuses == {"failed"}
    assert any("failed" in w for w in job.coverage_report["warnings"])


def test_cancel(db, org):
    job = make_job(db, org)
    job.cancel_requested = True
    db.commit()
    job = run(db, job)
    assert job.status == "cancelled"


def test_places_content_withheld_from_export_and_purged(db, org):
    from app.services.entity_resolution import SourcePolicy, resolve_record
    gp = db.scalar(select(SourceRegistry).where(SourceRegistry.key == "google_places"))
    m = resolve_record(db, org.id, RawCompany(name="Möbel Kraft", source_key="google_places", country="DE", city="Hamburg",
                                              phone="+49 40 123456", address="A 1", source_url="https://maps.google.com/?cid=1",
                                              external_ids={"google_place_id": "p1"}), SourcePolicy.from_registry(gp, "google_places"))
    # A second, exportable source confirms the name and website but not the phone
    resolve_record(db, org.id, RawCompany(name="Möbel Kraft", source_key="osm_overpass", country="DE", city="Hamburg",
                                          website="https://kraft.de", source_url="https://www.openstreetmap.org/node/9"), SourcePolicy("osm_overpass"))
    db.commit()
    rows, stats = build_rows(db, org.id, include_rejected=True)
    assert len(rows) == 1 and rows[0]["phone"] is None and rows[0]["website"] == "https://kraft.de"
    assert stats["withheld_fields"] >= 1
    # Places-only company is excluded entirely
    resolve_record(db, org.id, RawCompany(name="Wohnwelt Süd", source_key="google_places", country="DE", city="München",
                                          source_url="https://maps.google.com/?cid=2"), SourcePolicy.from_registry(gp, "google_places"))
    db.commit()
    rows, stats = build_rows(db, org.id, include_rejected=True)
    assert stats["excluded_companies"] == 1
    # After the 30-day licence window the Places content is purged; place_id survives on the location
    res = purge_expired(db, now=datetime.now(UTC) + timedelta(days=31))
    assert res["evidence_deleted"] > 0
    c = db.get(Company, m.company.id)
    assert c.phone is None
    assert any(loc.external_ids.get("google_place_id") == "p1" for loc in c.locations)
    assert db.scalar(select(func.count(Company.id)).where(Company.display_name == "Wohnwelt Süd")) == 0
