"""End-to-end research pipeline: plan → discover → resolve → enrich → classify/score → coverage.

Principle: broad discovery first, evidence-based verification second, commercial qualification third.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.base import (
    AccessRestrictedError,
    CompanySnapshot,
    ConfigurationError,
    ConnectorContext,
    ConnectorError,
    DiscoveryQuery,
    EnrichmentResult,
    RateLimitedError,
)
from app.connectors.registry import build_connector, resolve_access
from app.connectors.website import WebsiteConnector
from app.data.countries import get_country
from app.models import (
    Company,
    CompanyContact,
    CompanyEvidence,
    ImportSignal,
    JobStatus,
    Organization,
    OrganizationLead,
    ResearchCost,
    SearchJob,
    SearchQuery,
    SearchTask,
    SourceExecution,
    SourceRegistry,
    TaskStatus,
)
from app.services.assessment import _reliability_map, assess_company
from app.services.coverage import build_coverage_report
from app.services.entity_resolution import SourcePolicy, resolve_record
from app.services.llm import LLMClient
from app.services.normalization import normalize_query
from app.services.planner import build_plan
from app.services.query_generator import generate_queries, llm_expand_terms, negative_terms, product_terms
from app.services.source_catalog import register_candidate_source

log = logging.getLogger("pipeline")
MAX_TASK_ATTEMPTS = 3
CIRCUIT_BREAKER_FAILURES = 3  # consecutive transport failures before a source is considered down for the job
QUERIES_PER_TASK = 3
ENRICH_CONCURRENCY = 8
MIN_CITIES_PER_COUNTRY = 3


class JobCancelled(Exception):
    pass


class Budget:
    def __init__(self, limit: float, spent: float = 0.0):
        self.limit, self.spent = limit, spent

    @property
    def remaining(self) -> float:
        return max(0.0, self.limit - self.spent)

    def can_afford(self, amount: float) -> bool:
        return self.spent + amount <= self.limit + 1e-9

    def charge(self, amount: float) -> None:
        self.spent += amount


class ResearchPipeline:
    def __init__(self, db: Session, job_id, *, http=None, llm: LLMClient | None = None, website_connector: WebsiteConnector | None = None):
        self.db = db
        self.job: SearchJob = db.get(SearchJob, job_id)
        self.org: Organization = db.get(Organization, self.job.org_id)
        self.settings = get_settings()
        self.http = http
        self.llm = llm or LLMClient()
        self.budget = Budget(self.job.budget_usd, self.job.spent_usd or 0.0)
        self.connectors: dict = {}
        self.policies: dict[str, SourcePolicy] = {}
        self.window: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=self.settings.saturation_window))
        # Saturation is tracked per (country, city, source): a city that stops yielding new companies is
        # dropped for that source, other cities keep running (they bring genuinely new companies).
        self.saturated: set[tuple[str, str | None, str]] = set()
        self.consecutive_failures: dict[str, int] = defaultdict(int)
        self.executed_queries: dict[str, set[str]] = defaultdict(set)
        self.website = website_connector or WebsiteConnector(http=http)
        self.extra_terms: dict = {}
        self.website_text: dict = {}
        self.ctx = ConnectorContext(job_id=str(self.job.id), org_id=str(self.job.org_id),
                                    exporter_country=self.org.exporter_origin_country or self.settings.exporter_origin_country)

    # ------------------------------------------------------------------ helpers
    def _commit_progress(self, **kw) -> None:
        self.job.spent_usd = round(self.budget.spent, 6)
        self.job.progress = {**(self.job.progress or {}), **kw, "updated_at": datetime.now(UTC).isoformat()}
        self.db.commit()
        self.db.refresh(self.job)
        if self.job.cancel_requested:
            raise JobCancelled()

    def _set_status(self, status: JobStatus) -> None:
        self.job.status = status.value
        self._commit_progress(phase=status.value)

    def _cost(self, source_key: str, amount: float, cost_type: str, task: SearchTask | None = None, details: dict | None = None) -> None:
        if amount <= 0:
            return
        self.budget.charge(amount)
        self.db.add(ResearchCost(org_id=self.job.org_id, job_id=self.job.id, task_id=task.id if task else None, source_key=source_key,
                                 cost_type=cost_type, amount_usd=amount, details=details or {}))

    def _policy(self, key: str) -> SourcePolicy:
        if key not in self.policies:
            self.policies[key] = SourcePolicy.from_registry(self.db.scalar(select(SourceRegistry).where(SourceRegistry.key == key)), key)
        return self.policies[key]

    def _connector(self, key: str):
        if key not in self.connectors:
            src = self.db.scalar(select(SourceRegistry).where(SourceRegistry.key == key))
            access = resolve_access(self.db, self.job.org_id, src)
            self.connectors[key] = build_connector(access, self.http) if access.usable else None
        return self.connectors[key]

    def _job_company_ids(self) -> list:
        return list(self.db.scalars(select(CompanyEvidence.company_id).where(CompanyEvidence.job_id == self.job.id).distinct()))

    def _qualified_estimate(self) -> int:
        """Unique, non-rejected, furniture-relevant companies found so far (pre-enrichment proxy)."""
        return self.db.scalar(select(func.count(func.distinct(CompanyEvidence.company_id))).join(Company).where(
            CompanyEvidence.job_id == self.job.id, Company.research_status != "rejected")) or 0

    # ------------------------------------------------------------------ main
    async def run(self) -> SearchJob:
        job = self.job
        job.started_at = job.started_at or datetime.now(UTC)
        try:
            self._set_status(JobStatus.PLANNING)
            if not self.db.scalar(select(func.count(SearchTask.id)).where(SearchTask.job_id == job.id)):
                build_plan(self.db, job)
            await self._expand_terms()
            self._set_status(JobStatus.DISCOVERING)
            await self._discover()
            self._set_status(JobStatus.ENRICHING)
            await self._enrich()
            self._set_status(JobStatus.SCORING)
            self._score_all()
            report = build_coverage_report(self.db, job)
            job.coverage_report = report
            job.status = (JobStatus.COMPLETED_PARTIAL if report["warnings"] else JobStatus.COMPLETED).value
            job.stop_reason = job.stop_reason or ("; ".join(report["warnings"][:3]) if report["warnings"] else "plan executed")
        except JobCancelled:
            job.status = JobStatus.CANCELLED.value
            job.stop_reason = "cancelled by user"
            job.coverage_report = build_coverage_report(self.db, job)
        except Exception as exc:  # noqa: BLE001
            log.exception("job %s failed", job.id)
            self.db.rollback()
            job = self.db.get(SearchJob, job.id)
            job.status = JobStatus.FAILED.value
            job.error = f"{type(exc).__name__}: {exc}"
            self.job = job
        finally:
            job.finished_at = datetime.now(UTC)
            job.spent_usd = round(self.budget.spent, 6)
            self.db.commit()
            for c in self.connectors.values():
                if c:
                    await c.aclose()
            await self.website.aclose()
        return job

    # ------------------------------------------------------------------ LLM term expansion (optional)
    async def _expand_terms(self) -> None:
        if not self.llm.enabled:
            return
        products = self.job.product_config.get("categories") or ["home_furniture"]
        for iso in self.job.countries:
            cfg = get_country(iso)
            if not cfg:
                continue
            for lang in cfg.languages[:2]:
                for prod in products:
                    if not self.budget.can_afford(0.05):
                        return
                    before = self.llm.total_cost_usd
                    terms = await llm_expand_terms(self.llm, cfg.name_en, lang, "wholesaler", prod)
                    self._cost("llm", self.llm.total_cost_usd - before, "llm_tokens", details={"purpose": "term_expansion", "lang": lang})
                    if terms:
                        self.extra_terms.setdefault(prod, {}).setdefault(lang, []).extend(terms)
        self.job.plan_summary = {**(self.job.plan_summary or {}), "llm_suggested_terms": self.extra_terms}

    # ------------------------------------------------------------------ discovery
    async def _discover(self) -> None:
        job = self.job
        target_pool = max(job.target_company_count * 2, job.target_company_count + 20)
        while True:
            task = self._next_task()
            if task is None:
                pending_retry = self.db.scalar(select(func.min(SearchTask.next_retry_at)).where(
                    SearchTask.job_id == job.id, SearchTask.status == TaskStatus.RETRY_SCHEDULED.value))
                if pending_retry is None:
                    break
                wait = (pending_retry.replace(tzinfo=UTC) if pending_retry.tzinfo is None else pending_retry) - datetime.now(UTC)
                await asyncio.sleep(min(30, max(0.05, wait.total_seconds())))
                continue

            if self._qualified_estimate() >= target_pool:
                # Never stop on volume alone: every country must first reach minimum coverage
                # (≥3 commercial centres and every requested buyer type attempted).
                gap_task = self._coverage_gap_task()
                if gap_task is None:
                    self._skip_remaining(TaskStatus.SKIPPED_TARGET_REACHED, f"candidate pool reached {target_pool} (2× target) "
                                                                            "and minimum coverage met")
                    job.stop_reason = "target candidate pool reached"
                    break
                task = gap_task
            if self.budget.remaining <= 0:
                self._skip_remaining(TaskStatus.SKIPPED_BUDGET, "research budget exhausted")
                job.stop_reason = "budget exhausted"
                break
            if (task.country, task.city, task.source_key) in self.saturated:
                task.status = TaskStatus.SKIPPED_SATURATED.value
                task.status_reason = "source saturated for this city (new-company yield below threshold)"
                self.db.commit()
                continue
            await self._run_task(task)
            self._commit_progress(tasks_done=self.db.scalar(select(func.count(SearchTask.id)).where(
                SearchTask.job_id == job.id, SearchTask.status.notin_([TaskStatus.PLANNED.value, TaskStatus.RUNNING.value]))),
                unique_companies=self._qualified_estimate())

    def _next_task(self) -> SearchTask | None:
        """Pick the next cell by static priority adjusted for diversity: cells in countries, cities,
        buyer types and sources that were already searched get a penalty, so the plan spreads across
        markets and commercial centres instead of exhausting the capital first."""
        ready = self.db.scalars(select(SearchTask).where(
            SearchTask.job_id == self.job.id, SearchTask.status.in_([TaskStatus.PLANNED.value, TaskStatus.RETRY_SCHEDULED.value]),
            (SearchTask.next_retry_at.is_(None)) | (SearchTask.next_retry_at <= datetime.now(UTC)),
        )).all()
        if not ready:
            return None
        done = self.db.execute(select(SearchTask.country, SearchTask.city, SearchTask.buyer_type, SearchTask.source_key, SearchTask.new_unique)
                               .where(SearchTask.job_id == self.job.id, SearchTask.started_at.is_not(None))).all()
        n_country, n_city, n_type, found_country = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
        for country, city, bt, src, new in done:
            n_country[country] += 1
            n_city[(country, city)] += 1
            n_type[(country, bt)] += 1
            found_country[country] += new or 0

        def score(t: SearchTask) -> float:
            return (t.priority - 0.12 * n_city[(t.country, t.city)] - 0.03 * n_type[(t.country, t.buyer_type)]
                    - 0.002 * found_country[t.country] - 0.01 * n_country[t.country])
        return max(ready, key=score)

    def _coverage_gap_task(self) -> SearchTask | None:
        """A runnable task that adds a not-yet-searched city (until ≥ MIN_CITIES) or buyer type for its country."""
        rows = self.db.execute(select(SearchTask.country, SearchTask.city, SearchTask.buyer_type, SearchTask.started_at)
                               .where(SearchTask.job_id == self.job.id, SearchTask.priority >= 0)).all()
        planned_cities, done_cities, planned_types, done_types = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
        for country, city, bt, started in rows:
            planned_cities[country].add(city)
            planned_types[country].add(bt)
            if started is not None:
                done_cities[country].add(city)
                done_types[country].add(bt)
        ready = self.db.scalars(select(SearchTask).where(
            SearchTask.job_id == self.job.id, SearchTask.status == TaskStatus.PLANNED.value).order_by(SearchTask.priority.desc())).all()
        for t in ready:
            need_city = len(done_cities[t.country]) < min(MIN_CITIES_PER_COUNTRY, len(planned_cities[t.country]))
            if need_city and t.city not in done_cities[t.country]:
                return t
            if t.buyer_type not in done_types[t.country]:
                return t
        return None

    def _skip_remaining(self, status: TaskStatus, reason: str) -> None:
        for t in self.db.scalars(select(SearchTask).where(SearchTask.job_id == self.job.id,
                                                          SearchTask.status.in_([TaskStatus.PLANNED.value, TaskStatus.RETRY_SCHEDULED.value]))):
            t.status, t.status_reason = status.value, reason
        self.db.commit()

    async def _run_task(self, task: SearchTask) -> None:
        conn = self._connector(task.source_key)
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.now(UTC)
        task.attempts += 1
        self.db.commit()
        if conn is None:
            task.status, task.status_reason = TaskStatus.ACCESS_RESTRICTED.value, "connector unavailable"
            return
        policy = self._policy(task.source_key)
        if conn.uses_language:
            lang = task.language
            queries = generate_queries(task.buyer_type, task.product_category if task.product_category != "*" else "home_furniture",
                                       lang, task.city, max_queries=QUERIES_PER_TASK, already=self.executed_queries[task.source_key],
                                       extra_terms=self.extra_terms)
        else:
            q = f"{task.buyer_type} {task.product_category} {task.city or task.country}"
            norm = normalize_query(q + task.source_key)
            queries = [] if norm in self.executed_queries[task.source_key] else [q]
            self.executed_queries[task.source_key].add(norm)
        if not queries:
            task.status, task.status_reason = TaskStatus.COMPLETED.value, "all query variants already executed in this job"
            task.finished_at = datetime.now(UTC)
            return
        negs = negative_terms(task.language, task.buyer_type) if conn.uses_language else []
        key = (task.country, task.city, task.source_key)
        try:
            for qtext in queries:
                page, token = 1, None
                while True:
                    dq = DiscoveryQuery(text=qtext, language=task.language, country=task.country, city=task.city, buyer_type=task.buyer_type,
                                        product_category=task.product_category, page=page, page_token=token, negative_terms=negs)
                    est = conn.estimate_cost(dq)
                    if not self.budget.can_afford(est):
                        raise _BudgetStop()
                    t0 = time.monotonic()
                    try:
                        res = await asyncio.wait_for(conn.discover(dq, self.ctx), timeout=120)
                    except Exception as exc:
                        self.db.add(SourceExecution(org_id=self.job.org_id, job_id=self.job.id, task_id=task.id, source_key=task.source_key,
                                                    operation="discover", status=type(exc).__name__, error=str(exc)[:1000],
                                                    duration_ms=int((time.monotonic() - t0) * 1000)))
                        raise
                    new = 0
                    for raw in res.records:
                        m = resolve_record(self.db, self.job.org_id, raw, policy, self.job.id)
                        if m and m.created:
                            new += 1
                    for cand in res.source_candidates:
                        register_candidate_source(self.db, cand)
                    self._cost(task.source_key, res.cost_usd, "api_call", task, {"query": qtext, "page": page})
                    self.db.add(SearchQuery(job_id=self.job.id, task_id=task.id, source_key=task.source_key, query_text=qtext,
                                            normalized_query=normalize_query(qtext), language=task.language, page=page,
                                            result_count=len(res.records), new_companies=new, cost_usd=res.cost_usd))
                    self.db.add(SourceExecution(org_id=self.job.org_id, job_id=self.job.id, task_id=task.id, source_key=task.source_key,
                                                operation="discover", status="ok", http_status=res.http_status, result_count=len(res.records),
                                                cost_usd=res.cost_usd, duration_ms=int((time.monotonic() - t0) * 1000)))
                    task.queries_run += 1
                    task.raw_results += len(res.records)
                    task.new_unique += new
                    task.cost_usd += res.cost_usd
                    ratio = new / len(res.records) if res.records else 0.0
                    self.window[key].append(ratio)
                    self.db.commit()
                    # Adaptive pagination: continue only while pages keep yielding new companies.
                    if not res.has_more or page >= conn.max_pages or (page > 1 and ratio < self.settings.saturation_min_new_ratio):
                        break
                    page += 1
                    token = res.next_page_token
                w = self.window[key]
                if len(w) == w.maxlen and sum(w) / len(w) < self.settings.saturation_min_new_ratio:
                    self.saturated.add(key)
                    break
            task.status = TaskStatus.COMPLETED.value if task.raw_results else TaskStatus.NO_RESULTS.value
            self.consecutive_failures[task.source_key] = 0
        except _BudgetStop:
            task.status, task.status_reason = TaskStatus.SKIPPED_BUDGET.value, "next request would exceed the job budget"
        except RateLimitedError as exc:
            if task.attempts < MAX_TASK_ATTEMPTS:
                delay = exc.retry_after or 5 * 2 ** task.attempts
                task.status, task.next_retry_at = TaskStatus.RETRY_SCHEDULED.value, datetime.now(UTC) + timedelta(seconds=delay)
                task.status_reason = f"rate limited; retry in {delay:.0f}s"
            else:
                task.status, task.status_reason = TaskStatus.RATE_LIMITED.value, str(exc)
        except (AccessRestrictedError, ConfigurationError) as exc:
            task.status, task.status_reason = TaskStatus.ACCESS_RESTRICTED.value, str(exc)
            # Same reason applies to all cells of this source in this job
            for t in self.db.scalars(select(SearchTask).where(SearchTask.job_id == self.job.id, SearchTask.source_key == task.source_key,
                                                              SearchTask.status == TaskStatus.PLANNED.value)):
                t.status, t.status_reason = TaskStatus.ACCESS_RESTRICTED.value, str(exc)
        except (ConnectorError, asyncio.TimeoutError) as exc:
            self.consecutive_failures[task.source_key] += 1
            if self.consecutive_failures[task.source_key] >= CIRCUIT_BREAKER_FAILURES:
                reason = f"source unreachable ({self.consecutive_failures[task.source_key]} consecutive failures): {exc}"[:500]
                task.status, task.status_reason = TaskStatus.FAILED.value, reason
                for t in self.db.scalars(select(SearchTask).where(
                        SearchTask.job_id == self.job.id, SearchTask.source_key == task.source_key,
                        SearchTask.status.in_([TaskStatus.PLANNED.value, TaskStatus.RETRY_SCHEDULED.value]))):
                    t.status, t.status_reason = TaskStatus.FAILED.value, "skipped: " + reason
            elif task.attempts < MAX_TASK_ATTEMPTS:
                task.status, task.next_retry_at = TaskStatus.RETRY_SCHEDULED.value, datetime.now(UTC) + timedelta(seconds=5 * 2 ** task.attempts)
                task.status_reason = f"transient error: {exc}"[:500]
            else:
                task.status, task.status_reason = TaskStatus.FAILED.value, str(exc)[:500]
        except Exception as exc:  # noqa: BLE001 - parser bugs etc. must not kill the job
            log.exception("task %s failed", task.id)
            self.db.rollback()
            task = self.db.get(SearchTask, task.id)
            task.status, task.status_reason = TaskStatus.FAILED.value, f"{type(exc).__name__}: {exc}"[:500]
        task.finished_at = datetime.now(UTC)
        self.db.commit()

    # ------------------------------------------------------------------ enrichment
    def _snapshot(self, c: Company) -> CompanySnapshot:
        prods = self.job.product_config.get("categories") or ["home_furniture"]
        cfg = get_country(c.country or "")
        langs = (list(cfg.languages) if cfg else []) + ["en"]
        terms = sorted({t for p in prods for lang in langs for t in product_terms(p, lang, self.extra_terms)})
        return CompanySnapshot(id=str(c.id), name=c.display_name, country=c.country, city=c.city, website=c.website, domain=c.domain,
                               vat_number=c.vat_number, registration_number=c.registration_number, is_synthetic=c.is_synthetic,
                               product_terms=terms)

    def _apply_enrichment(self, c: Company, res: EnrichmentResult, source_key: str) -> None:
        policy = self._policy(source_key)
        until = policy.retention_until()
        for e in res.evidence:
            self.db.add(CompanyEvidence(company_id=c.id, job_id=self.job.id, evidence_type=e.evidence_type, field=e.field, value=(e.value or "")[:1000] or None,
                                        snippet=e.snippet, source_key=source_key, source_url=e.source_url, confidence=e.confidence,
                                        is_synthetic=c.is_synthetic, retention_until=until))
        existing = {(x.contact_type, x.value) for x in self.db.scalars(select(CompanyContact).where(CompanyContact.company_id == c.id))}
        for ct in res.contacts:
            if (ct.contact_type, ct.value) in existing:
                continue
            existing.add((ct.contact_type, ct.value))
            contact = CompanyContact(company_id=c.id, contact_type=ct.contact_type, value=ct.value, person_name=ct.person_name,
                                     job_title=ct.job_title, department=ct.department, is_generic=ct.is_generic,
                                     legal_basis="published_business_contact" if ct.is_generic else "legitimate_interest_b2b",
                                     source_key=source_key, source_url=ct.source_url, verified=ct.confidence >= 0.8, retention_until=until)
            self.db.add(contact)
            if ct.contact_type == "email" and ct.is_generic and not c.general_email:
                c.general_email = ct.value
                self.db.add(CompanyEvidence(company_id=c.id, job_id=self.job.id, evidence_type="website_content", field="email",
                                            value=ct.value, source_key=source_key, source_url=ct.source_url, confidence=ct.confidence,
                                            is_synthetic=c.is_synthetic))
            if ct.department == "purchasing" and not c.purchasing_contact_id:
                self.db.flush()
                c.purchasing_contact_id = contact.id
            if ct.contact_type == "phone" and not c.phone:
                c.phone = ct.value
                self.db.add(CompanyEvidence(company_id=c.id, job_id=self.job.id, evidence_type="website_content", field="phone",
                                            value=ct.value, source_key=source_key, source_url=ct.source_url, confidence=ct.confidence,
                                            is_synthetic=c.is_synthetic))
        for s in res.import_signals:
            dup = self.db.scalar(select(ImportSignal.id).where(ImportSignal.company_id == c.id, ImportSignal.signal_type == s.signal_type,
                                                              ImportSignal.source_key == source_key))
            if not dup:
                self.db.add(ImportSignal(company_id=c.id, signal_type=s.signal_type, verified=s.verified, hs_code=s.hs_code,
                                         origin_country=s.origin_country, shipment_count=s.shipment_count, description=s.description,
                                         source_key=source_key, source_url=s.source_url))
        u = res.updates
        for f in ("website_status", "website_product_match", "store_count", "registry_status", "oem_private_label_signal"):
            if f in u and u[f] is not None:
                setattr(c, f, u[f])
        for f in ("vat_number", "registration_number", "legal_name"):
            if u.get(f) and not getattr(c, f):
                setattr(c, f, u[f])
        if res.status == "ok" and source_key == "company_website":
            c.research_status = "enriched" if c.research_status == "discovered" else c.research_status
        if source_key in ("vies", "companies_house", "ares") and (u.get("vat_verified") or u.get("registry_status") == "active"):
            c.research_status = "verified"
            c.last_verified_at = datetime.now(UTC)
        elif res.status in ("unreachable", "not_found", "blocked_by_robots") and source_key == "company_website":
            c.website_status = res.status
        self.db.add(SourceExecution(org_id=self.job.org_id, job_id=self.job.id, source_key=source_key, operation="enrich",
                                    status=res.status, result_count=len(res.evidence) + len(res.contacts), cost_usd=res.cost_usd))
        self._cost(source_key, res.cost_usd, "enrichment", details={"company_id": str(c.id)})

    async def _enrich(self) -> None:
        job = self.job
        reliability = _reliability_map(self.db)
        ids = self._job_company_ids()
        companies = [self.db.get(Company, i) for i in ids]
        # Preliminary (cheap) assessment from listings only, to decide where enrichment is worth it.
        prelim = []
        for c in companies:
            cl, sc = assess_company(self.db, c, job, reliability=reliability, exporter_country=self.ctx.exporter_country, persist_score=False)
            prelim.append((sc.buyer_fit, c, cl))
        self.db.commit()
        prelim.sort(key=lambda t: -t[0])
        # Stage 1: website enrichment (free) for relevant candidates, best first; cap to keep runtime bounded.
        cap = max(job.target_company_count * 3, 50)
        candidates = [c for fit, c, cl in prelim if c.website and not cl.reject_reason][:cap]
        sem = asyncio.Semaphore(ENRICH_CONCURRENCY)

        async def one(c: Company):
            async with sem:
                try:
                    return c, await asyncio.wait_for(self.website.enrich(self._snapshot(c), self.ctx), timeout=90)
                except Exception as exc:  # noqa: BLE001
                    r = EnrichmentResult(status="unreachable")
                    r.evidence = []
                    log.info("website enrichment failed for %s: %s", c.domain, exc)
                    return c, r

        done = 0
        for chunk_start in range(0, len(candidates), 40):
            chunk = candidates[chunk_start:chunk_start + 40]
            for c, res in await asyncio.gather(*(one(c) for c in chunk)):
                self._apply_enrichment(c, res, "company_website")
                if res.text_corpus:
                    self.website_text[c.id] = res.text_corpus[:50_000]
                done += 1
            self._commit_progress(enriched_websites=done, enrichment_candidates=len(candidates))

        # Stage 2: official verification for candidates that now look relevant.
        verifiers = [k for k in ("vies", "companies_house", "ares") if self._connector(k) is not None]
        for c in candidates:
            for key in verifiers:
                conn = self._connector(key)
                if not conn.supports_country(c.country or "") or c.is_synthetic:
                    continue
                if key == "vies" and not c.vat_number:
                    continue
                try:
                    res = await asyncio.wait_for(conn.enrich(self._snapshot(c), self.ctx), timeout=60)
                    if res.status != "skipped":
                        self._apply_enrichment(c, res, key)
                except Exception as exc:  # noqa: BLE001
                    self.db.add(SourceExecution(org_id=job.org_id, job_id=job.id, source_key=key, operation="verify",
                                                status=type(exc).__name__, error=str(exc)[:500]))
        self.db.commit()

        # Stage 3: paid contact enrichment only for top candidates, only if enabled and affordable.
        if job.use_paid_sources:
            hunter = self._connector("hunter")
            if hunter:
                ranked = []
                for c in candidates:
                    _, sc = assess_company(self.db, c, job, website_text=self.website_text.get(c.id, ""), reliability=reliability,
                                           exporter_country=self.ctx.exporter_country, persist_score=False)
                    if sc.buyer_fit >= job.min_buyer_fit and not c.is_synthetic and not c.purchasing_contact_id:
                        ranked.append((sc.buyer_fit, c))
                ranked.sort(key=lambda t: -t[0])
                for _, c in ranked[: job.target_company_count]:
                    if not self.budget.can_afford(hunter.estimate_cost()):
                        break
                    try:
                        res = await hunter.enrich(self._snapshot(c), self.ctx)
                        self._apply_enrichment(c, res, "hunter")
                    except Exception as exc:  # noqa: BLE001
                        self.db.add(SourceExecution(org_id=job.org_id, job_id=job.id, source_key="hunter", operation="enrich",
                                                    status=type(exc).__name__, error=str(exc)[:500]))
                self.db.commit()

    # ------------------------------------------------------------------ scoring
    def _score_all(self) -> None:
        job = self.job
        reliability = _reliability_map(self.db)
        for cid in self._job_company_ids():
            c = self.db.get(Company, cid)
            assess_company(self.db, c, job, website_text=self.website_text.get(c.id, ""), reliability=reliability,
                           exporter_country=self.ctx.exporter_country)
            lead = self.db.scalar(select(OrganizationLead).where(OrganizationLead.org_id == job.org_id, OrganizationLead.company_id == c.id))
            if not lead:
                lead = OrganizationLead(org_id=job.org_id, company_id=c.id, job_ids=[])
                self.db.add(lead)
            if str(job.id) not in (lead.job_ids or []):
                lead.job_ids = [*(lead.job_ids or []), str(job.id)]
        self._commit_progress(scored=True)


class _BudgetStop(Exception):
    pass


async def run_job_async(db: Session, job_id, **kw) -> SearchJob:
    return await ResearchPipeline(db, job_id, **kw).run()


def run_job(job_id) -> None:
    """Entry point for worker threads / Celery tasks."""
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        asyncio.run(run_job_async(db, job_id))
    finally:
        db.close()
