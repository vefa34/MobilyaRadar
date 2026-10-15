"""Source catalogue management: seeding, per-country selection, and dynamic source discovery."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.countries import get_country
from app.data.sources import SEED_SOURCES
from app.models import SourceRegistry

# Fields that are curated in code and overwritten on sync; operator-managed fields (status overrides,
# review notes) are preserved if the row was edited after seeding.
SYNC_FIELDS = ["name", "url", "tier", "purposes", "countries", "access_model", "connector_key", "has_api", "auth_required",
               "pricing", "terms_url", "terms_summary", "storage_allowed", "max_retention_days", "export_allowed", "merge_allowed",
               "persistent_id_fields", "rate_limit", "data_fields", "reliability", "cost_per_request_usd", "product_searchable",
               "customer_types", "regions", "languages", "notes", "integration_status"]


def sync_seed_sources(db: Session) -> int:
    existing = {s.key: s for s in db.scalars(select(SourceRegistry))}
    n = 0
    for entry in SEED_SOURCES:
        row = existing.get(entry["key"])
        if row is None:
            row = SourceRegistry(key=entry["key"], last_checked_at=datetime.now(UTC))
            db.add(row)
            n += 1
        for f in SYNC_FIELDS:
            setattr(row, f, entry.get(f))
    db.flush()
    return n


def sources_for_country(db: Session, iso2: str) -> list[SourceRegistry]:
    rows = db.scalars(select(SourceRegistry).where(SourceRegistry.review_status == "approved")).all()
    return [r for r in rows if "*" in (r.countries or []) or iso2 in (r.countries or [])]


SOURCE_DISCOVERY_PATTERNS = [
    "{country} furniture importers directory", "{country} furniture wholesalers association", "{country} furniture retailers directory",
    "{country} chamber of commerce members directory", "{country} furniture exhibition exhibitors",
    "{country} registered furniture businesses", "{country} furniture distributors", "{country} furniture dealers wholesale",
]
LOCAL_PATTERNS = {
    "de": ["Möbel Importeure Verzeichnis {country}", "Möbelgroßhandel Verband", "Möbelhändler Verzeichnis", "IHK Mitgliederverzeichnis Möbel", "Möbelmesse Aussteller"],
    "fr": ["annuaire importateurs meubles {country}", "fédération négoce ameublement", "annuaire magasins de meubles", "chambre de commerce annuaire membres meubles", "salon du meuble exposants"],
    "ar": ["دليل مستوردي الأثاث {country}", "دليل تجار الأثاث بالجملة", "غرفة التجارة دليل الأعضاء أثاث", "معرض الأثاث العارضين"],
    "ru": ["каталог импортеров мебели {country}", "ассоциация мебельщиков", "справочник мебельных компаний", "мебельная выставка участники"],
    "ka": ["ავეჯის იმპორტიორები საქართველო", "ავეჯის კომპანიების კატალოგი"],
    "hy": ["կահույքի ներմուծողներ Հայաստան", "կահույքի ընկերություններ"],
    "az": ["mebel idxalatçıları Azərbaycan", "mebel şirkətləri kataloqu"],
    "pl": ["katalog firm meblowych", "importerzy mebli Polska"], "ro": ["director firme mobilă România", "importatori mobilă"],
    "cs": ["katalog firem nábytek"], "it": ["elenco importatori mobili"], "es": ["directorio importadores muebles"],
    "nl": ["meubelbranche vereniging leden"], "bg": ["каталог фирми мебели"], "el": ["κατάλογος εταιρειών επίπλων"], "sr": ["katalog firmi nameštaj"],
}


def source_discovery_queries(iso2: str) -> list[tuple[str, str]]:
    """(query, language) pairs used to discover new directories/associations for a country."""
    cfg = get_country(iso2)
    if not cfg:
        return []
    out = [(p.format(country=cfg.name_en), "en") for p in SOURCE_DISCOVERY_PATTERNS]
    for lang in cfg.languages:
        out += [(p.format(country=cfg.name_en), lang) for p in LOCAL_PATTERNS.get(lang, [])]
    return out


def register_candidate_source(db: Session, candidate: dict) -> SourceRegistry | None:
    """Store a directory-like domain found during discovery as a *pending review* catalogue entry.

    It is never auto-activated: an operator must review terms of use and choose an access model.
    """
    domain = candidate.get("domain")
    if not domain:
        return None
    key = "disc_" + domain.replace(".", "_")[:70]
    row = db.scalar(select(SourceRegistry).where(SourceRegistry.key == key))
    if row:
        countries = set(row.countries or [])
        if candidate.get("country"):
            countries.add(candidate["country"])
        row.countries = sorted(countries)
        return row
    if db.scalar(select(SourceRegistry).where(SourceRegistry.url.contains(domain))):
        return None  # already curated
    row = SourceRegistry(
        key=key, name=(candidate.get("title") or domain)[:200], url=f"https://{domain}", tier="P1", purposes=["discovery"],
        countries=[candidate["country"]] if candidate.get("country") else [], access_model="manual",
        integration_status="catalog_only", discovered_automatically=True, review_status="pending_review",
        languages=[candidate.get("language")] if candidate.get("language") else [],
        notes=f"Auto-discovered via query: {candidate.get('query')}", reliability=0.3, last_checked_at=datetime.now(UTC),
    )
    db.add(row)
    return row
