"""Connector framework shared by every data source.

Each connector implements ``LeadSourceConnector``. The pipeline never talks to HTTP directly;
it calls ``discover`` / ``enrich`` / ``health_check`` / ``estimate_cost`` and receives normalised
records together with cost and call accounting. Connectors raise typed errors so the planner can
set the precise task status (rate_limited, access_restricted, failed, …).
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("connectors")


# ------------------------------------------------------------------------------------- errors
class ConnectorError(Exception):
    """Generic, possibly transient failure."""


class ConfigurationError(ConnectorError):
    """Connector cannot run: missing credentials or misconfiguration."""


class AccessRestrictedError(ConnectorError):
    """Source exists but we are not permitted to automate it (licence/ToS/auth)."""


class RateLimitedError(ConnectorError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class BudgetExceededError(ConnectorError):
    pass


# ------------------------------------------------------------------------------------- records
@dataclass
class RawCompany:
    """A company-like record as returned by one source, before entity resolution."""
    name: str
    source_key: str
    source_url: str | None = None
    source_record_id: str | None = None
    country: str | None = None
    city: str | None = None
    address: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    categories: list[str] = field(default_factory=list)
    description: str | None = None
    registration_number: str | None = None
    vat_number: str | None = None
    alt_names: list[str] = field(default_factory=list)
    location_type: str = "unknown"
    external_ids: dict[str, str] = field(default_factory=dict)
    evidence_type: str = "discovery_listing"
    confidence: float = 0.5
    is_synthetic: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryQuery:
    text: str
    language: str
    country: str
    city: str | None
    buyer_type: str
    product_category: str
    page: int = 1
    page_size: int = 20
    page_token: str | None = None
    negative_terms: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    records: list[RawCompany]
    has_more: bool = False
    next_page_token: str | None = None
    cost_usd: float = 0.0
    http_calls: int = 0
    # Pages/domains that look like directories — fed into dynamic source discovery.
    source_candidates: list[dict] = field(default_factory=list)
    http_status: int | None = None


@dataclass
class CompanySnapshot:
    """Read-only view of a company passed to enrichers (decoupled from ORM)."""
    id: str
    name: str
    country: str | None
    city: str | None = None
    website: str | None = None
    domain: str | None = None
    vat_number: str | None = None
    registration_number: str | None = None
    is_synthetic: bool = False
    product_terms: list[str] = field(default_factory=list)


@dataclass
class EvidenceItem:
    evidence_type: str
    field: str | None
    value: str | None
    source_url: str | None
    snippet: str | None = None
    confidence: float = 0.6


@dataclass
class ContactItem:
    contact_type: str
    value: str | None
    source_url: str | None
    person_name: str | None = None
    job_title: str | None = None
    department: str | None = None
    is_generic: bool = True
    confidence: float = 0.6


@dataclass
class ImportSignalItem:
    signal_type: str
    verified: bool
    source_url: str | None
    description: str | None = None
    hs_code: str | None = None
    origin_country: str | None = None
    shipment_count: int | None = None


@dataclass
class EnrichmentResult:
    evidence: list[EvidenceItem] = field(default_factory=list)
    contacts: list[ContactItem] = field(default_factory=list)
    import_signals: list[ImportSignalItem] = field(default_factory=list)
    updates: dict[str, Any] = field(default_factory=dict)  # attribute -> value (only facts with evidence)
    text_corpus: str = ""   # lower-cased text used for classification (not persisted)
    status: str = "ok"      # ok|unreachable|blocked_by_robots|not_found|skipped
    cost_usd: float = 0.0
    http_calls: int = 0


@dataclass
class HealthStatus:
    status: str   # ok|degraded|down|not_configured|pending_license|manual
    message: str = ""
    latency_ms: int | None = None


@dataclass
class ConnectorContext:
    job_id: str | None = None
    org_id: str | None = None
    budget_remaining_usd: float = float("inf")
    exporter_country: str = "TR"


# ------------------------------------------------------------------------------------- utilities
class RateLimiter:
    """Simple async limiter: at most ``rate`` acquisitions per ``per`` seconds (sliding spacing)."""

    def __init__(self, rate: float, per: float = 1.0):
        self.min_interval = per / rate if rate > 0 else 0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self.min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


async def request_with_retry(client: httpx.AsyncClient, method: str, url: str, *, limiter: RateLimiter | None = None,
                             retries: int = 3, backoff_base: float = 0.5, max_backoff: float = 20.0,
                             sleep=asyncio.sleep, **kwargs) -> httpx.Response:
    """HTTP request with rate limiting, retries and exponential backoff with jitter.

    * 429 → honours Retry-After; after the final attempt raises RateLimitedError
    * 5xx / transport errors → retried; finally raises ConnectorError
    * 401/403 → AccessRestrictedError (never retried)
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        if limiter:
            await limiter.acquire()
        try:
            resp = await client.request(method, url, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt >= retries:
                raise ConnectorError(f"transport error: {exc}") from exc
            await sleep(min(max_backoff, backoff_base * 2 ** attempt + random.uniform(0, backoff_base)))
            continue
        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            if attempt >= retries:
                raise RateLimitedError(f"rate limited by {httpx.URL(url).host}", retry_after)
            await sleep(min(max_backoff, retry_after if retry_after is not None else backoff_base * 2 ** attempt))
            continue
        if resp.status_code in (401, 403):
            raise AccessRestrictedError(f"HTTP {resp.status_code} from {httpx.URL(url).host}: access denied")
        if resp.status_code >= 500:
            last_exc = ConnectorError(f"HTTP {resp.status_code} from {httpx.URL(url).host}")
            if attempt >= retries:
                raise last_exc
            await sleep(min(max_backoff, backoff_base * 2 ** attempt + random.uniform(0, backoff_base)))
            continue
        return resp
    raise ConnectorError(str(last_exc))  # pragma: no cover


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# ------------------------------------------------------------------------------------- base class
class LeadSourceConnector:
    """Base class. Subclasses override what they support; unsupported operations raise."""

    key: str = "base"
    purposes: tuple[str, ...] = ("discovery",)
    cost_per_request_usd: float = 0.0
    # Which plan dimensions produce genuinely different queries for this source. Sources that
    # ignore language (map features) or product (category taxonomies) set these to False so the
    # planner doesn't create redundant cells.
    uses_language: bool = True
    uses_product: bool = True
    uses_city: bool = True
    supported_buyer_types: tuple[str, ...] | None = None  # None = all
    max_pages: int = 3
    requires_credentials: bool = False

    def __init__(self, credentials: dict | None = None, http: httpx.AsyncClient | None = None, settings=None):
        from app.config import get_settings
        self.credentials = credentials or {}
        self.settings = settings or get_settings()
        self._http = http
        self._own_http = http is None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=20.0, headers={"User-Agent": self.settings.http_user_agent},
                                           follow_redirects=True)
        return self._http

    async def aclose(self) -> None:
        if self._own_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    def supports_country(self, iso2: str) -> bool:
        return True

    def supports_buyer_type(self, buyer_type: str) -> bool:
        return self.supported_buyer_types is None or buyer_type in self.supported_buyer_types

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        raise AccessRestrictedError(f"{self.key} does not support discovery")

    async def enrich(self, company: CompanySnapshot, context: ConnectorContext) -> EnrichmentResult:
        raise AccessRestrictedError(f"{self.key} does not support enrichment")

    async def health_check(self) -> HealthStatus:
        return HealthStatus("ok", "no remote dependency")

    def estimate_cost(self, request: DiscoveryQuery | CompanySnapshot | None = None) -> float:
        return self.cost_per_request_usd
