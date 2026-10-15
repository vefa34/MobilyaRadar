"""Google Places API (New) — Text Search, and OpenStreetMap Overpass connectors."""
from __future__ import annotations

from app.config import get_settings
from app.connectors.base import (
    ConfigurationError,
    ConnectorContext,
    ConnectorError,
    DiscoveryQuery,
    DiscoveryResult,
    HealthStatus,
    LeadSourceConnector,
    RateLimiter,
    RawCompany,
    request_with_retry,
)
from app.data.countries import get_country

PLACES_FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.addressComponents", "places.location",
    "places.nationalPhoneNumber", "places.internationalPhoneNumber", "places.websiteUri", "places.types",
    "places.businessStatus", "places.googleMapsUri", "nextPageToken",
])


class GooglePlacesConnector(LeadSourceConnector):
    """Places content is subject to Google Maps Platform terms: only ``place_id`` is persisted
    indefinitely; all other content is stored with a 30-day ``retention_until`` and excluded from
    exports (see source_registry 'google_places')."""

    key = "google_places"
    cost_per_request_usd = 0.032
    uses_language = True
    uses_product = True
    max_pages = 3
    requires_credentials = True
    supported_buyer_types = ("independent_store", "retail_chain", "wholesaler", "distributor", "contract_ffe",
                             "interior_procurement", "verified_importer")
    endpoint = "https://places.googleapis.com/v1/places:searchText"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.api_key = self.credentials.get("api_key") or self.settings.google_places_api_key
        self.limiter = RateLimiter(rate=5.0)

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        if not self.api_key:
            raise ConfigurationError("GOOGLE_PLACES_API_KEY not configured")
        body = {"textQuery": query.text, "languageCode": query.language if query.language != "ku" else "ar",
                "regionCode": query.country, "pageSize": min(query.page_size, 20)}
        if query.page_token:
            body["pageToken"] = query.page_token
        resp = await request_with_retry(self.http, "POST", self.endpoint, json=body, limiter=self.limiter,
                                        headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": PLACES_FIELDS})
        if resp.status_code == 400:
            raise ConnectorError(f"Places API rejected request: {resp.text[:300]}")
        resp.raise_for_status()
        data = resp.json()
        records = []
        for p in data.get("places", []):
            if p.get("businessStatus") == "CLOSED_PERMANENTLY":
                continue
            city = None
            for comp in p.get("addressComponents", []):
                if "locality" in comp.get("types", []):
                    city = comp.get("longText")
            loc = p.get("location") or {}
            records.append(RawCompany(
                name=(p.get("displayName") or {}).get("text") or "", source_key=self.key,
                source_url=p.get("googleMapsUri"), source_record_id=p.get("id"), country=query.country,
                city=city or query.city, address=p.get("formattedAddress"), latitude=loc.get("latitude"),
                longitude=loc.get("longitude"), phone=p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"),
                website=p.get("websiteUri"), categories=p.get("types", []), external_ids={"google_place_id": p.get("id")},
                evidence_type="places_listing", location_type="store", confidence=0.65,
            ))
        token = data.get("nextPageToken")
        return DiscoveryResult(records=records, has_more=bool(token) and query.page < self.max_pages, next_page_token=token,
                               cost_usd=self.cost_per_request_usd, http_calls=1, http_status=resp.status_code)

    async def health_check(self) -> HealthStatus:
        if not self.api_key:
            return HealthStatus("not_configured", "API key missing")
        try:
            resp = await request_with_retry(self.http, "POST", self.endpoint, retries=0,
                                            json={"textQuery": "furniture store Berlin", "pageSize": 1},
                                            headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": "places.id"})
            return HealthStatus("ok" if resp.status_code == 200 else "degraded", f"HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            return HealthStatus("down", str(exc))


# OSM tags per buyer type. Map features don't carry product granularity, so this connector ignores
# the product dimension (uses_product=False) and the planner creates one cell per city × tag group.
OSM_TAGS = {
    "independent_store": ['["shop"="furniture"]', '["shop"="interior_decoration"]', '["shop"="bed"]', '["shop"="kitchen"]'],
    "retail_chain": ['["shop"="furniture"]["brand"]'],
    "wholesaler": ['["shop"="wholesale"]["wholesale"~"furniture"]', '["wholesale"="furniture"]', '["trade"="furniture"]'],
    "contract_ffe": ['["office"]["name"~"[Ff]urniture|[Mm]öbel|[Mm]eubl|أثاث"]'],
}


class OverpassConnector(LeadSourceConnector):
    key = "osm_overpass"
    cost_per_request_usd = 0.0
    uses_language = False
    uses_product = False
    max_pages = 1
    supported_buyer_types = tuple(OSM_TAGS)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.endpoint = self.credentials.get("endpoint") or self.settings.overpass_url
        self.is_public = "overpass-api.de" in self.endpoint or "kumi.systems" in self.endpoint
        self.limiter = RateLimiter(rate=0.5)  # ≤1 request / 2s against public instances
        self.queries_this_job = 0

    def build_query(self, country: str, city: str | None, buyer_type: str) -> str:
        tags = OSM_TAGS.get(buyer_type, OSM_TAGS["independent_store"])
        area = f'area["ISO3166-1"="{country}"][admin_level=2]->.c;'
        if city:
            safe = city.replace('"', "")
            area += f'area["name"="{safe}"](area.c)->.a;'
            scope = "area.a"
        else:
            scope = "area.c"
        body = "".join(f"nwr{t}({scope});" for t in tags)
        return f"[out:json][timeout:60];{area}({body});out center tags 500;"

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        if self.is_public and self.queries_this_job >= get_settings().overpass_public_max_queries_per_job:
            raise ConfigurationError("public Overpass per-job query cap reached — configure a self-hosted OVERPASS_URL for volume")
        self.queries_this_job += 1
        city = query.city
        cfg = get_country(query.country)
        if cfg and city:  # OSM uses local-script names; local_name holds the Latin alias when city is non-Latin
            city = next((c.name for c in cfg.cities if city in (c.name, c.local_name)), city)
        ql = self.build_query(query.country, city, query.buyer_type)
        resp = await request_with_retry(self.http, "POST", self.endpoint, data={"data": ql}, limiter=self.limiter,
                                        retries=2, backoff_base=2.0)
        resp.raise_for_status()
        records = []
        for el in resp.json().get("elements", []):
            tags = el.get("tags") or {}
            name = tags.get("name") or tags.get("brand")
            if not name:
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            addr = ", ".join(x for x in [" ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")])),
                                          tags.get("addr:postcode"), tags.get("addr:city")] if x) or None
            alt = [tags[k] for k in ("name:en", "name:ar", "name:ru", "int_name", "official_name", "name:latin") if tags.get(k)]
            cats = [f"{k}={tags[k]}" for k in ("shop", "wholesale", "trade", "office", "craft") if tags.get(k)]
            if tags.get("brand"):
                cats.append("has_brand")
            osm_id = f"{el.get('type')}/{el.get('id')}"
            records.append(RawCompany(
                name=name, source_key=self.key, source_url=f"https://www.openstreetmap.org/{osm_id}", source_record_id=osm_id,
                country=query.country, city=tags.get("addr:city") or query.city, address=addr, postal_code=tags.get("addr:postcode"),
                latitude=lat, longitude=lon, phone=tags.get("phone") or tags.get("contact:phone"),
                email=tags.get("email") or tags.get("contact:email"), website=tags.get("website") or tags.get("contact:website"),
                categories=cats, alt_names=alt, external_ids={"osm_id": osm_id}, evidence_type="map_feature",
                location_type="store" if tags.get("shop") else "unknown", confidence=0.6,
                extra={"brand": tags.get("brand"), "brand_wikidata": tags.get("brand:wikidata")},
            ))
        return DiscoveryResult(records=records, has_more=False, cost_usd=0.0, http_calls=1, http_status=resp.status_code)

    async def health_check(self) -> HealthStatus:
        try:
            status_url = self.endpoint.replace("/interpreter", "/status")
            resp = await request_with_retry(self.http, "GET", status_url, retries=0)
            return HealthStatus("ok" if resp.status_code == 200 else "degraded",
                                ("public instance — fair use only. " if self.is_public else "") + f"HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            return HealthStatus("down", str(exc))
