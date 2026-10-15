"""Official registry connectors: EU VIES, UK Companies House, Czech ARES; plus Hunter.io contacts.

Registries are primarily *verification* sources. Companies House and ARES additionally support
activity-code (SIC/NACE) search, which makes them usable for discovery in their countries; other
registries are not assumed to allow product-based bulk discovery.
"""
from __future__ import annotations

import re

from app.connectors.base import (
    CompanySnapshot,
    ConfigurationError,
    ConnectorContext,
    ConnectorError,
    ContactItem,
    DiscoveryQuery,
    DiscoveryResult,
    EnrichmentResult,
    EvidenceItem,
    HealthStatus,
    LeadSourceConnector,
    RateLimiter,
    RawCompany,
    request_with_retry,
)
from app.data.sources import EU_VIES
from app.services.normalization import normalize_name

VIES_PREFIX = {"GR": "EL"}


class ViesConnector(LeadSourceConnector):
    key = "vies"
    purposes = ("verification",)
    endpoint = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.limiter = RateLimiter(rate=1.0)

    def supports_country(self, iso2: str) -> bool:
        return iso2 in EU_VIES

    @staticmethod
    def split_vat(vat: str, country: str | None) -> tuple[str, str] | None:
        v = re.sub(r"[\s.-]", "", vat or "").upper()
        m = re.match(r"^([A-Z]{2})([0-9A-Z]{2,13})$", v)
        if m:
            return m.group(1), m.group(2)
        if country:
            return VIES_PREFIX.get(country, country), v
        return None

    async def enrich(self, company: CompanySnapshot, context: ConnectorContext) -> EnrichmentResult:
        res = EnrichmentResult()
        if not company.vat_number:
            res.status = "skipped"
            return res
        parts = self.split_vat(company.vat_number, company.country)
        if not parts:
            res.status = "skipped"
            return res
        cc, num = parts
        resp = await request_with_retry(self.http, "POST", self.endpoint, json={"countryCode": cc, "vatNumber": num},
                                        limiter=self.limiter, retries=2)
        res.http_calls = 1
        if resp.status_code >= 400:
            raise ConnectorError(f"VIES HTTP {resp.status_code}")
        data = resp.json()
        if data.get("userError") and data.get("userError") not in ("VALID", "INVALID"):
            raise ConnectorError(f"VIES unavailable: {data.get('userError')}")
        valid = bool(data.get("valid"))
        url = f"https://ec.europa.eu/taxation_customs/vies/#/vat-validation-result?country={cc}&number={num}"
        res.evidence.append(EvidenceItem("vat_check", "vat_number", f"{cc}{num}", url,
                                         snippet=f"valid={valid}; name={data.get('name')}; address={data.get('address')}",
                                         confidence=0.95))
        if valid:
            res.updates["vat_verified"] = True
            name = (data.get("name") or "").strip()
            if name and name != "---":
                res.updates["legal_name"] = name
        else:
            res.updates["vat_verified"] = False
        return res

    async def health_check(self) -> HealthStatus:
        try:
            r = await request_with_retry(self.http, "GET", "https://ec.europa.eu/taxation_customs/vies/rest-api/check-status", retries=0)
            return HealthStatus("ok" if r.status_code == 200 else "degraded", f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            return HealthStatus("down", str(exc))


# SIC 2007 codes relevant to furniture buyers.
UK_SIC = {"wholesaler": ["46470"], "distributor": ["46470", "46150"], "verified_importer": ["46470"],
          "retail_chain": ["47591"], "independent_store": ["47591"], "ecommerce": ["47910"],
          "contract_ffe": ["46470", "43320"], "interior_procurement": ["74100", "43390"]}


class CompaniesHouseConnector(LeadSourceConnector):
    key = "companies_house"
    purposes = ("verification", "discovery")
    base = "https://api.company-information.service.gov.uk"
    uses_language = False
    uses_product = False
    requires_credentials = True
    max_pages = 5

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.api_key = self.credentials.get("api_key") or self.settings.companies_house_api_key
        self.limiter = RateLimiter(rate=2.0)  # 600 / 5 min

    def supports_country(self, iso2: str) -> bool:
        return iso2 == "GB"

    def _auth(self):
        if not self.api_key:
            raise ConfigurationError("COMPANIES_HOUSE_API_KEY not configured")
        return (self.api_key, "")

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        sic = UK_SIC.get(query.buyer_type)
        if not sic:
            return DiscoveryResult(records=[])
        params = {"sic_codes": ",".join(sic), "company_status": "active", "size": 100,
                  "start_index": (query.page - 1) * 100}
        if query.city:
            params["location"] = query.city
        resp = await request_with_retry(self.http, "GET", f"{self.base}/advanced-search/companies", params=params,
                                        auth=self._auth(), limiter=self.limiter)
        if resp.status_code == 404:
            return DiscoveryResult(records=[], http_calls=1, http_status=404)
        resp.raise_for_status()
        data = resp.json()
        recs = []
        for it in data.get("items", []):
            addr = it.get("registered_office_address") or {}
            num = it.get("company_number")
            recs.append(RawCompany(
                name=it.get("company_name", ""), source_key=self.key, source_record_id=num,
                source_url=f"https://find-and-update.company-information.service.gov.uk/company/{num}",
                country="GB", city=addr.get("locality") or query.city,
                address=", ".join(filter(None, [addr.get("address_line_1"), addr.get("address_line_2"), addr.get("postal_code")])),
                postal_code=addr.get("postal_code"), registration_number=num, categories=[f"sic:{s}" for s in it.get("sic_codes", [])],
                evidence_type="registry_record", location_type="hq", confidence=0.85,
                extra={"company_status": it.get("company_status")},
            ))
        total = data.get("hits", 0)
        return DiscoveryResult(records=recs, has_more=query.page * 100 < total and query.page < self.max_pages,
                               http_calls=1, http_status=resp.status_code)

    async def enrich(self, company: CompanySnapshot, context: ConnectorContext) -> EnrichmentResult:
        res = EnrichmentResult()
        if company.country != "GB":
            res.status = "skipped"
            return res
        if company.registration_number and re.fullmatch(r"[A-Z0-9]{8}", company.registration_number):
            url = f"{self.base}/company/{company.registration_number}"
            resp = await request_with_retry(self.http, "GET", url, auth=self._auth(), limiter=self.limiter)
            res.http_calls = 1
            if resp.status_code == 404:
                res.status = "not_found"
                return res
            item = resp.json()
        else:
            resp = await request_with_retry(self.http, "GET", f"{self.base}/search/companies",
                                            params={"q": company.name, "items_per_page": 5}, auth=self._auth(), limiter=self.limiter)
            res.http_calls = 1
            items = resp.json().get("items", []) if resp.status_code == 200 else []
            target = normalize_name(company.name)
            item = next((i for i in items if normalize_name(i.get("title", "")) == target), None)
            if not item:
                res.status = "not_found"
                return res
        num = item.get("company_number")
        url = f"https://find-and-update.company-information.service.gov.uk/company/{num}"
        status = item.get("company_status")
        res.evidence.append(EvidenceItem("registry_record", "registration_number", num, url,
                                         snippet=f"{item.get('company_name') or item.get('title')} — status: {status}; SIC: {item.get('sic_codes')}",
                                         confidence=0.95))
        res.updates.update({"registration_number": num, "registry_status": "active" if status == "active" else (status or "unknown"),
                            "legal_name": item.get("company_name") or item.get("title")})
        return res

    async def health_check(self) -> HealthStatus:
        if not self.api_key:
            return HealthStatus("not_configured", "API key missing")
        try:
            r = await request_with_retry(self.http, "GET", f"{self.base}/search/companies", params={"q": "furniture", "items_per_page": 1},
                                         auth=self._auth(), retries=0)
            return HealthStatus("ok" if r.status_code == 200 else "degraded", f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            return HealthStatus("down", str(exc))


CZ_NACE = {"wholesaler": ["4647"], "distributor": ["4647", "4615"], "verified_importer": ["4647"],
           "retail_chain": ["4759"], "independent_store": ["4759"], "ecommerce": ["4791"]}


class AresConnector(LeadSourceConnector):
    """Czech ARES REST API (free, official). Field names follow the ARES 'ekonomicke-subjekty-v-be' API."""

    key = "ares"
    purposes = ("verification", "discovery")
    base = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"
    uses_language = False
    uses_product = False
    max_pages = 5

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.limiter = RateLimiter(rate=4.0)

    def supports_country(self, iso2: str) -> bool:
        return iso2 == "CZ"

    @staticmethod
    def _to_raw(s: dict, city_hint: str | None) -> RawCompany:
        sidlo = s.get("sidlo") or {}
        ico = s.get("ico")
        return RawCompany(
            name=s.get("obchodniJmeno", ""), source_key="ares", source_record_id=ico,
            source_url=f"https://ares.gov.cz/ekonomicke-subjekty?ico={ico}", country="CZ",
            city=sidlo.get("nazevObce") or city_hint, address=sidlo.get("textovaAdresa"), postal_code=str(sidlo.get("psc") or "") or None,
            registration_number=ico, vat_number=s.get("dic"), categories=[f"nace:{c}" for c in s.get("czNace", [])],
            evidence_type="registry_record", location_type="hq", confidence=0.85,
        )

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        nace = CZ_NACE.get(query.buyer_type)
        if not nace:
            return DiscoveryResult(records=[])
        body = {"start": (query.page - 1) * 100, "pocet": 100, "czNace": nace}
        if query.city:
            body["sidlo"] = {"nazevObce": query.city}
        resp = await request_with_retry(self.http, "POST", f"{self.base}/ekonomicke-subjekty/vyhledat", json=body, limiter=self.limiter)
        if resp.status_code == 400:
            raise ConnectorError(f"ARES rejected search: {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()
        recs = [self._to_raw(s, query.city) for s in data.get("ekonomickeSubjekty", [])]
        total = data.get("pocetCelkem", 0)
        return DiscoveryResult(records=recs, has_more=query.page * 100 < total and query.page < self.max_pages,
                               http_calls=1, http_status=resp.status_code)

    async def enrich(self, company: CompanySnapshot, context: ConnectorContext) -> EnrichmentResult:
        res = EnrichmentResult()
        ico = re.sub(r"\D", "", company.registration_number or "")
        if company.country != "CZ" or len(ico) != 8:
            res.status = "skipped"
            return res
        resp = await request_with_retry(self.http, "GET", f"{self.base}/ekonomicke-subjekty/{ico}", limiter=self.limiter)
        res.http_calls = 1
        if resp.status_code == 404:
            res.status = "not_found"
            return res
        resp.raise_for_status()
        s = resp.json()
        raw = self._to_raw(s, company.city)
        res.evidence.append(EvidenceItem("registry_record", "registration_number", ico, raw.source_url,
                                         snippet=f"{raw.name}; {raw.address}; NACE {s.get('czNace')}", confidence=0.95))
        res.updates.update({"registration_number": ico, "legal_name": raw.name, "registry_status": "active"})
        if raw.vat_number:
            res.updates["vat_number"] = raw.vat_number
        return res


class HunterConnector(LeadSourceConnector):
    """Hunter.io domain search — used only for top-ranked companies (P3, paid per request)."""

    key = "hunter"
    purposes = ("contact_enrichment",)
    cost_per_request_usd = 0.05
    requires_credentials = True
    endpoint = "https://api.hunter.io/v2/domain-search"
    RELEVANT_DEPTS = {"management", "executive", "sales", "operations", "purchasing", "procurement"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.api_key = self.credentials.get("api_key") or self.settings.hunter_api_key
        self.limiter = RateLimiter(rate=5.0)

    async def enrich(self, company: CompanySnapshot, context: ConnectorContext) -> EnrichmentResult:
        if not self.api_key:
            raise ConfigurationError("HUNTER_API_KEY not configured")
        res = EnrichmentResult(cost_usd=self.cost_per_request_usd)
        if not company.domain or company.is_synthetic:
            res.status, res.cost_usd = "skipped", 0.0
            return res
        resp = await request_with_retry(self.http, "GET", self.endpoint, params={"domain": company.domain, "limit": 10, "api_key": self.api_key},
                                        limiter=self.limiter)
        res.http_calls = 1
        resp.raise_for_status()
        for e in (resp.json().get("data") or {}).get("emails", []):
            dept = (e.get("department") or "").lower()
            generic = e.get("type") == "generic"
            if not generic and dept and dept not in self.RELEVANT_DEPTS:
                continue
            name = " ".join(filter(None, [e.get("first_name"), e.get("last_name")])) or None
            src = (e.get("sources") or [{}])[0].get("uri") or f"https://hunter.io/search/{company.domain}"
            res.contacts.append(ContactItem("email" if generic else "person", e.get("value"), src, person_name=name,
                                            job_title=e.get("position"), department="purchasing" if dept in ("purchasing", "procurement") else (dept or "general"),
                                            is_generic=generic, confidence=min(1.0, (e.get("confidence") or 50) / 100)))
        return res

    async def health_check(self) -> HealthStatus:
        if not self.api_key:
            return HealthStatus("not_configured", "API key missing")
        try:
            r = await request_with_retry(self.http, "GET", "https://api.hunter.io/v2/account", params={"api_key": self.api_key}, retries=0)
            return HealthStatus("ok" if r.status_code == 200 else "degraded", f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            return HealthStatus("down", str(exc))
