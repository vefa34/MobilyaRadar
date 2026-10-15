"""Research planning: Country × City × BuyerType × Product × Language × Source.

The plan is generated once per job; execution order is by ``priority`` and the pipeline adapts it
at run time (budget, saturation, target reached). Cells for sources we cannot use are recorded
once per (country, source) as access_restricted / manual_review_required so the coverage report
shows exactly where data is missing, and manual sources get a research-queue item with
ready-to-use local-language queries.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.connectors.registry import SourceAccess, build_connector, resolve_access
from app.data.countries import get_country
from app.models import ManualResearchItem, SearchJob, SearchTask, TaskStatus
from app.services.query_generator import generate_queries
from app.services.source_catalog import sources_for_country

DEFAULT_BUYER_TYPES = ["wholesaler", "distributor", "verified_importer", "retail_chain", "independent_store", "contract_ffe"]
TIER_SCORE = {"P0": 0.3, "P1": 0.22, "P2": 0.12, "P3": 0.0}
ENGLISH_BUSINESS_REGIONS = {"middle_east"}
PAID_THRESHOLD_USD = 0.02  # sources costing more per request than this need the job's paid-sources opt-in


@dataclass
class PlanStats:
    cells: int = 0
    restricted: int = 0
    manual: int = 0
    countries: int = 0
    cities: int = 0


def search_languages(iso2: str) -> list[str]:
    cfg = get_country(iso2)
    if not cfg:
        return ["en"]
    langs = [lang for lang in cfg.languages if lang != "en"]
    if cfg.region in ENGLISH_BUSINESS_REGIONS or not langs:
        langs.append("en")
    # Kurdish has thin web coverage; keep it but after Arabic.
    return langs[:3]


def cities_for(iso2: str, target_per_country: int) -> list:
    cfg = get_country(iso2)
    if not cfg:
        return []
    # All configured cities enter the plan; low-weight cities get low priority and are only reached
    # if earlier cells don't saturate the target. Minimum 3 commercial centres, never only the capital.
    return list(cfg.cities)


def build_plan(db: Session, job: SearchJob) -> PlanStats:
    stats = PlanStats()
    products = job.product_config.get("categories") or ["home_furniture"]
    buyer_types = job.buyer_types or DEFAULT_BUYER_TYPES
    target_per_country = max(10, math.ceil(job.target_company_count / max(1, len(job.countries))))
    selected = set(job.selected_sources or [])
    tasks: list[SearchTask] = []

    for iso in job.countries:
        cfg = get_country(iso)
        if not cfg:
            continue
        stats.countries += 1
        cities = cities_for(iso, target_per_country)
        stats.cities += len(cities)
        langs = search_languages(iso)
        for src in sources_for_country(db, iso):
            if "discovery" not in (src.purposes or []):
                continue
            if selected and src.key not in selected:
                continue
            access: SourceAccess = resolve_access(db, job.org_id, src)
            if access.usable and src.cost_per_request_usd >= PAID_THRESHOLD_USD and not job.use_paid_sources:
                tasks.append(SearchTask(job_id=job.id, country=iso, city=None, buyer_type="*", product_category="*", language="*",
                                        source_key=src.key, priority=-1, status=TaskStatus.SKIPPED_BUDGET.value,
                                        status_reason="paid source — disabled for this job (enable 'use paid sources')"))
                continue
            if not access.usable:
                if src.key == "mock":
                    continue
                st = TaskStatus.MANUAL_REVIEW if access.status_if_blocked == "manual_review_required" else TaskStatus.ACCESS_RESTRICTED
                tasks.append(SearchTask(job_id=job.id, country=iso, city=None, buyer_type="*", product_category="*", language="*",
                                        source_key=src.key, priority=-1, status=st.value, status_reason=access.reason))
                if st == TaskStatus.MANUAL_REVIEW:
                    stats.manual += 1
                    qs = []
                    for lang in langs[:2]:
                        for bt in buyer_types[:3]:
                            qs += generate_queries(bt, products[0], lang, None, max_queries=1, already=set())
                    db.add(ManualResearchItem(org_id=job.org_id, job_id=job.id, source_key=src.key, suggested_queries=qs[:8],
                                              instructions=f"Search {src.name} ({src.url or 'see catalogue'}) for {cfg.name_en} furniture buyers. "
                                                           f"Import findings via CSV upload. Note: {src.terms_summary or src.notes or ''}"))
                else:
                    stats.restricted += 1
                continue
            conn = build_connector(access)
            if not conn.supports_country(iso):
                continue
            src_langs = langs if conn.uses_language else ["*"]
            src_products = products if conn.uses_product else ["*"]
            src_cities = cities if conn.uses_city else [None]
            cheap = 0.15 if src.cost_per_request_usd == 0 else (0.08 if src.cost_per_request_usd < 0.01 else 0.0)
            for ci, city in enumerate(src_cities):
                for bi, bt in enumerate(buyer_types):
                    if not conn.supports_buyer_type(bt):
                        continue
                    for prod in src_products:
                        for li, lang in enumerate(src_langs):
                            pr = ((city.weight if city else 0.8) * 0.4 + TIER_SCORE.get(src.tier, 0) + cheap
                                  + (0.1 - 0.015 * bi) + (0.05 if li == 0 else 0) + (src.reliability or 0.5) * 0.05)
                            tasks.append(SearchTask(job_id=job.id, country=iso, city=city.name if city else None, buyer_type=bt,
                                                    product_category=prod, language=lang, source_key=src.key, priority=round(pr, 4)))
    db.add_all(tasks)
    stats.cells = len([t for t in tasks if t.priority >= 0])
    job.plan_summary = {**(job.plan_summary or {}), "cells": stats.cells, "restricted_sources": stats.restricted,
                        "manual_sources": stats.manual, "countries": stats.countries, "cities_considered": stats.cities,
                        "products": products, "buyer_types": buyer_types,
                        "languages": {iso: search_languages(iso) for iso in job.countries}}
    db.flush()
    return stats
