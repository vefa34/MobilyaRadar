"""Maps source keys to connector implementations and resolves per-organisation access."""
from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.base import LeadSourceConnector
from app.connectors.licensed import CsvImportConnector, LicensedSourceConnector
from app.connectors.mock import MockConnector
from app.connectors.places import GooglePlacesConnector, OverpassConnector
from app.connectors.registries import AresConnector, CompaniesHouseConnector, HunterConnector, ViesConnector
from app.connectors.web_search import BraveSearchConnector, SerpApiConnector
from app.connectors.website import WebsiteConnector
from app.models import IntegrationStatus, SourcePermission, SourceRegistry
from app.security import decrypt_secret

CONNECTOR_CLASSES: dict[str, type[LeadSourceConnector]] = {
    "mock": MockConnector,
    "brave_search": BraveSearchConnector,
    "serpapi": SerpApiConnector,
    "google_places": GooglePlacesConnector,
    "osm_overpass": OverpassConnector,
    "website": WebsiteConnector,
    "companies_house": CompaniesHouseConnector,
    "vies": ViesConnector,
    "ares": AresConnector,
    "hunter": HunterConnector,
    "csv_import": CsvImportConnector,
}

ENV_KEYS = {
    "brave_search": "brave_search_api_key", "serpapi": "serpapi_api_key", "google_places": "google_places_api_key",
    "companies_house": "companies_house_api_key", "hunter": "hunter_api_key", "apollo": "apollo_api_key",
}


@dataclass
class SourceAccess:
    source: SourceRegistry
    usable: bool
    reason: str               # why not usable → becomes task status reason
    status_if_blocked: str    # access_restricted | manual_review_required
    credentials: dict
    license_confirmed: bool


def resolve_access(db: Session, org_id, source: SourceRegistry) -> SourceAccess:
    s = get_settings()
    perm = db.scalar(select(SourcePermission).where(SourcePermission.org_id == org_id, SourcePermission.source_key == source.key))
    creds: dict = {}
    if perm and perm.credentials_encrypted:
        try:
            creds = json.loads(decrypt_secret(perm.credentials_encrypted))
        except Exception:  # noqa: BLE001
            creds = {}
    env_attr = ENV_KEYS.get(source.key)
    if env_attr and getattr(s, env_attr, None) and "api_key" not in creds:
        creds["api_key"] = getattr(s, env_attr)
    license_ok = bool(perm and perm.license_confirmed)
    status = source.integration_status
    # Org may explicitly disable a source; for free/official ones default is enabled
    explicitly_disabled = perm is not None and not perm.enabled

    def blocked(reason, st="access_restricted"):
        return SourceAccess(source, False, reason, st, creds, license_ok)

    if source.key == "mock" and not s.demo_mode:
        return blocked("demo mode disabled")
    if explicitly_disabled:
        return blocked("disabled by organisation")
    if status in (IntegrationStatus.MANUAL.value, IntegrationStatus.CATALOG_ONLY.value):
        return blocked("no automated connector — manual research queue", "manual_review_required")
    if status == IntegrationStatus.INACTIVE.value:
        return blocked("source inactive")
    if status == IntegrationStatus.PENDING_LICENSE.value:
        return blocked("licence/contract required" if not license_ok else "licence confirmed; provider adapter pending")
    if status == IntegrationStatus.PENDING_CREDENTIALS.value and not creds.get("api_key"):
        return blocked("API key not configured")
    if source.connector_key not in CONNECTOR_CLASSES:
        return blocked("connector not implemented")
    return SourceAccess(source, True, "", "", creds, license_ok)


def build_connector(access: SourceAccess, http: httpx.AsyncClient | None = None) -> LeadSourceConnector:
    key = access.source.connector_key
    if key == "licensed_stub" or key not in CONNECTOR_CLASSES:
        return LicensedSourceConnector(access.source.key, access.credentials, http, license_confirmed=access.license_confirmed)
    return CONNECTOR_CLASSES[key](access.credentials, http)
