"""Licensed web-search connectors (Brave Search API, SerpApi).

Search engines return *pages*, not companies. ``results_to_candidates`` turns organic results
into company candidates (one per non-generic domain) and separates directory/listing pages, which
are fed into dynamic source discovery instead of being stored as companies.
"""
from __future__ import annotations

import re

from app.connectors.base import (
    ConfigurationError,
    ConnectorContext,
    DiscoveryQuery,
    DiscoveryResult,
    HealthStatus,
    LeadSourceConnector,
    RateLimiter,
    RawCompany,
    request_with_retry,
)
from app.services.normalization import is_generic_domain, normalize_domain

DIRECTORY_HINTS = re.compile(
    r"\b(directory|verzeichnis|annuaire|répertoire|top \d+|best \d+|\d+ best|list of|liste|ranking|branchenbuch|"
    r"gelbe seiten|pages jaunes|yellow pages|firmen in|companies in|entreprises|dizini|دليل|справочник|каталог)\b", re.I)
TITLE_SPLIT = re.compile(r"\s+[|–—\-:•·»]\s+")


def _clean_title(title: str) -> str:
    parts = [p.strip() for p in TITLE_SPLIT.split(title or "") if p.strip()]
    if not parts:
        return title.strip()
    # Prefer the shortest segment that contains a capitalised token and isn't a generic page label
    generic = re.compile(r"^(home|startseite|accueil|welcome|willkommen|contact|kontakt|impressum|about us|shop)$", re.I)
    cands = [p for p in parts if not generic.match(p)]
    return (cands[0] if cands else parts[0])[:200]


def results_to_candidates(results: list[dict], query: DiscoveryQuery, source_key: str) -> tuple[list[RawCompany], list[dict]]:
    companies: list[RawCompany] = []
    candidates: list[dict] = []
    seen: set[str] = set()
    for r in results:
        url, title, snippet = r.get("url"), r.get("title") or "", r.get("snippet") or ""
        domain = normalize_domain(url)
        if not domain:
            continue
        text = f"{title} {snippet}"
        if is_generic_domain(domain) or DIRECTORY_HINTS.search(text):
            candidates.append({"url": url, "domain": domain, "title": title, "country": query.country,
                               "language": query.language, "query": query.text})
            continue
        if domain in seen:
            continue
        seen.add(domain)
        companies.append(RawCompany(
            name=_clean_title(title) or domain, source_key=source_key, source_url=url, source_record_id=domain,
            country=query.country, city=query.city, website=f"https://{domain}", description=snippet[:500],
            categories=[], evidence_type="search_result", confidence=0.35,
        ))
    return companies, candidates


class BraveSearchConnector(LeadSourceConnector):
    key = "brave_search"
    cost_per_request_usd = 0.005
    max_pages = 3
    requires_credentials = True
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.api_key = self.credentials.get("api_key") or self.settings.brave_search_api_key
        self.limiter = RateLimiter(rate=1.0)

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        if not self.api_key:
            raise ConfigurationError("BRAVE_SEARCH_API_KEY not configured")
        q = query.text + "".join(f' -"{n}"' if " " in n else f" -{n}" for n in query.negative_terms)
        params = {"q": q, "count": min(query.page_size, 20), "offset": query.page - 1, "country": query.country.lower(),
                  "search_lang": query.language if query.language not in ("ku",) else "ar", "safesearch": "off"}
        resp = await request_with_retry(self.http, "GET", self.endpoint, params=params, limiter=self.limiter,
                                        headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"})
        if resp.status_code == 422:  # unsupported country/lang combination → retry without
            params.pop("search_lang", None); params.pop("country", None)
            resp = await request_with_retry(self.http, "GET", self.endpoint, params=params, limiter=self.limiter,
                                            headers={"X-Subscription-Token": self.api_key})
        resp.raise_for_status()
        data = resp.json()
        results = [{"url": r.get("url"), "title": r.get("title"), "snippet": r.get("description")}
                   for r in (data.get("web") or {}).get("results", [])]
        companies, cands = results_to_candidates(results, query, self.key)
        more = bool((data.get("query") or {}).get("more_results_available")) and query.page < self.max_pages
        return DiscoveryResult(records=companies, has_more=more, cost_usd=self.cost_per_request_usd, http_calls=1,
                               source_candidates=cands, http_status=resp.status_code)

    async def health_check(self) -> HealthStatus:
        if not self.api_key:
            return HealthStatus("not_configured", "API key missing")
        try:
            resp = await request_with_retry(self.http, "GET", self.endpoint, params={"q": "furniture", "count": 1},
                                            headers={"X-Subscription-Token": self.api_key}, retries=0)
            return HealthStatus("ok" if resp.status_code == 200 else "degraded", f"HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            return HealthStatus("down", str(exc))


class SerpApiConnector(LeadSourceConnector):
    key = "serpapi"
    cost_per_request_usd = 0.01
    max_pages = 3
    requires_credentials = True
    endpoint = "https://serpapi.com/search.json"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.api_key = self.credentials.get("api_key") or self.settings.serpapi_api_key
        self.limiter = RateLimiter(rate=2.0)

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        if not self.api_key:
            raise ConfigurationError("SERPAPI_API_KEY not configured")
        q = query.text + "".join(f" -{n}" for n in query.negative_terms if " " not in n)
        params = {"engine": "google", "q": q, "gl": query.country.lower(), "hl": query.language, "num": 20,
                  "start": (query.page - 1) * 20, "api_key": self.api_key}
        resp = await request_with_retry(self.http, "GET", self.endpoint, params=params, limiter=self.limiter)
        resp.raise_for_status()
        data = resp.json()
        results = [{"url": r.get("link"), "title": r.get("title"), "snippet": r.get("snippet")}
                   for r in data.get("organic_results", [])]
        companies, cands = results_to_candidates(results, query, self.key)
        more = bool((data.get("serpapi_pagination") or {}).get("next")) and query.page < self.max_pages
        return DiscoveryResult(records=companies, has_more=more, cost_usd=self.cost_per_request_usd, http_calls=1,
                               source_candidates=cands, http_status=resp.status_code)

    async def health_check(self) -> HealthStatus:
        if not self.api_key:
            return HealthStatus("not_configured", "API key missing")
        try:
            resp = await request_with_retry(self.http, "GET", "https://serpapi.com/account.json",
                                            params={"api_key": self.api_key}, retries=0)
            return HealthStatus("ok" if resp.status_code == 200 else "degraded", f"HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            return HealthStatus("down", str(exc))
