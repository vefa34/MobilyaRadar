"""Synthetic connector for demos and tests.

Every record it produces is flagged ``is_synthetic=True``, its name starts with "[DEMO]", its
website uses the reserved ``.invalid`` TLD (RFC 2606, can never resolve) and phone numbers use a
``000`` block. Synthetic data is excluded from exports and dashboards unless the user explicitly
includes it, so it can never be mistaken for a real customer list.

The generator is deterministic and deliberately realistic in *shape*: overlapping results across
queries, name variants of the same company (to exercise entity resolution), manufacturers,
second-hand shops and irrelevant businesses (to exercise classification and negative filters).
"""
from __future__ import annotations

import hashlib
import random
import re

from app.connectors.base import (
    ConnectorContext,
    DiscoveryQuery,
    DiscoveryResult,
    HealthStatus,
    LeadSourceConnector,
    RawCompany,
)
from app.data.countries import get_country

PREFIXES = ["Nordlicht", "Atlas", "Cedar", "Orion", "Lumen", "Vega", "Aurora", "Delta", "Helix", "Zenith", "Sahara",
            "Olive", "Granit", "Marble", "Linden", "Falcon", "Harbor", "Crescent", "Summit", "Meridian", "Pioneer",
            "Riviera", "Vista", "Ember", "Saffron", "Topaz", "Indigo", "Coral", "Willow", "Basalt", "Kestrel", "Juniper",
            "Opal", "Sierra", "Tundra", "Arbor", "Cobalt", "Dune", "Fjord", "Garnet"]
PROFILES = [  # (profile, weight)
    ("wholesaler", 0.14), ("distributor", 0.09), ("retail_chain", 0.08), ("independent_store", 0.28),
    ("ecommerce", 0.08), ("contract_ffe", 0.07), ("interior_procurement", 0.05), ("importer", 0.06),
    ("manufacturer", 0.09), ("used_furniture", 0.03), ("irrelevant", 0.03),
]
PRODUCTS = ["dining_table", "chair", "sofa", "bed", "cabinet", "office_furniture", "hotel_furniture", "outdoor_furniture"]
LOCAL_WORD = {"de": "Möbel", "fr": "Meubles", "ar": "Furniture", "ka": "Aveji", "hy": "Kahuyk", "az": "Mebel", "ru": "Mebel",
              "it": "Mobili", "es": "Muebles", "nl": "Meubelen", "pl": "Meble", "ro": "Mobila", "cs": "Nabytek",
              "sk": "Nabytok", "bg": "Mebeli", "el": "Epipla", "sr": "Namestaj"}
LEGAL = {"DE": "GmbH", "AT": "GmbH", "FR": "SARL", "GB": "Ltd", "NL": "B.V.", "BE": "BV", "ES": "S.L.", "IT": "S.r.l.",
         "PL": "Sp. z o.o.", "RO": "SRL", "CZ": "s.r.o.", "SK": "s.r.o.", "BG": "EOOD", "GR": "AE", "RS": "d.o.o.",
         "AE": "LLC", "SA": "Est.", "QA": "W.L.L.", "KW": "W.L.L.", "BH": "W.L.L.", "OM": "LLC", "IQ": "Co.", "JO": "Co.",
         "LB": "SAL", "MA": "SARL", "DZ": "SARL", "TN": "SARL", "LY": "Co.", "EG": "S.A.E.", "GE": "LLC", "AZ": "MMC", "AM": "LLC"}


def _rng(*parts) -> random.Random:
    seed = int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def _pick_profile(r: random.Random) -> str:
    x, acc = r.random(), 0.0
    for name, w in PROFILES:
        acc += w
        if x <= acc:
            return name
    return PROFILES[-1][0]


def build_pool(country: str, city_index: int) -> list[dict]:
    cfg = get_country(country)
    if not cfg or city_index >= len(cfg.cities):
        return []
    city = cfg.cities[city_index]
    r = _rng("pool", country, city_index)
    size = int(15 + 45 * city.weight)
    lang = cfg.languages[0]
    pool = []
    used: set[str] = set()
    for i in range(size):
        base = r.choice(PREFIXES)
        if base in used:
            base = f"{base} {r.choice(PREFIXES)}"
        used.add(base)
        profile = _pick_profile(r)
        prods = r.sample(PRODUCTS, k=r.randint(1, 4))
        if profile == "irrelevant":
            prods = []
        slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
        domain = f"demo-{slug}-{country.lower()}{city_index}-{i}.invalid"
        stores = r.randint(3, 40) if profile == "retail_chain" else (1 if profile in ("independent_store", "used_furniture") else None)
        pool.append({
            "index": i, "base": base, "profile": profile, "products": prods, "domain": domain,
            "phone": f"+{_dial(country)}000{r.randint(100000, 999999)}", "city": city.name,
            "city_display": city.local_name or city.name, "country": country, "lang": lang,
            "legal": LEGAL.get(country, "Ltd"), "stores": stores, "has_website": r.random() > 0.12,
            "employees": r.choice([3, 8, 15, 40, 120, 350]), "importer_claim": profile in ("importer", "wholesaler", "distributor") and r.random() > 0.4,
            "shipments": r.randint(4, 60) if profile == "importer" and r.random() > 0.3 else 0,
            "oem": profile in ("retail_chain", "contract_ffe", "ecommerce") and r.random() > 0.5,
        })
    return pool


def _dial(country: str) -> str:
    from app.services.normalization import DIAL_CODES
    return DIAL_CODES.get(country, "1")


def profile_for_domain(domain: str) -> dict | None:
    m = re.match(r"^demo-[a-z0-9-]+?-([a-z]{2})(\d+)-(\d+)\.invalid$", domain or "")
    if not m:
        return None
    pool = build_pool(m.group(1).upper(), int(m.group(2)))
    idx = int(m.group(3))
    return pool[idx] if idx < len(pool) else None


def _name_variant(c: dict, r: random.Random) -> str:
    local = LOCAL_WORD.get(c["lang"], "Furniture")
    variants = [f"{c['base']} {local} {c['legal']}", f"{c['base']} Furniture", f"{c['base']} {local}",
                f"{c['base']} Furniture Trading", f"{c['base']} {local} - {c['city_display']} Branch"]
    if c["profile"] == "used_furniture":
        variants = [f"{c['base']} Second-Hand {local}"]
    if c["profile"] == "irrelevant":
        variants = [f"{c['base']} Kitchen Appliances", f"{c['base']} Electronics"]
    return "[DEMO] " + r.choice(variants)


TYPE_AFFINITY = {
    "verified_importer": {"importer", "wholesaler", "distributor"}, "wholesaler": {"wholesaler", "importer", "distributor"},
    "distributor": {"distributor", "wholesaler", "importer"}, "retail_chain": {"retail_chain", "independent_store"},
    "independent_store": {"independent_store", "retail_chain", "used_furniture"}, "ecommerce": {"ecommerce", "retail_chain"},
    "contract_ffe": {"contract_ffe", "interior_procurement", "manufacturer"},
    "interior_procurement": {"interior_procurement", "contract_ffe"}, "brand_private_label": {"retail_chain", "ecommerce", "manufacturer"},
}


class MockConnector(LeadSourceConnector):
    key = "mock"
    purposes = ("discovery",)
    cost_per_request_usd = 0.001  # tiny synthetic cost so budget logic is exercised
    uses_language = False
    max_pages = 3

    async def discover(self, query: DiscoveryQuery, context: ConnectorContext) -> DiscoveryResult:
        cfg = get_country(query.country)
        if not cfg:
            return DiscoveryResult(records=[], cost_usd=self.cost_per_request_usd, http_calls=1)
        city_idx = next((i for i, c in enumerate(cfg.cities) if c.name == query.city or c.local_name == query.city), 0)
        pool = build_pool(query.country, city_idx)
        affinity = TYPE_AFFINITY.get(query.buyer_type, set())
        r = _rng("q", query.text, query.buyer_type, query.product_category, query.city)
        scored = []
        for c in pool:
            s = r.random()
            if c["profile"] in affinity:
                s += 0.8
            if query.product_category in c["products"]:
                s += 0.5
            scored.append((s, c))
        scored.sort(key=lambda t: -t[0])
        start = (query.page - 1) * query.page_size
        page = [c for _, c in scored[start:start + query.page_size]]
        records = []
        for c in page:
            rr = _rng("variant", c["domain"], query.text, query.page)
            fixed = _rng("fixed", c["domain"])
            records.append(RawCompany(
                name=_name_variant(c, rr), source_key=self.key, source_url=f"https://{c['domain']}/listing",
                source_record_id=c["domain"], country=c["country"], city=c["city"],
                address=f"{fixed.randint(1, 200)} Demo Street, {c['city_display']}", phone=c["phone"],
                website=f"https://{c['domain']}" if c["has_website"] else None,
                email=f"info@{c['domain']}" if fixed.random() > 0.5 else None,
                categories=[c["profile"]] + c["products"], description=f"Synthetic {c['profile'].replace('_', ' ')} record",
                location_type="store" if c["profile"] in ("independent_store", "retail_chain") else "hq",
                is_synthetic=True, confidence=0.5,
            ))
        has_more = start + query.page_size < len(scored) and query.page < self.max_pages
        return DiscoveryResult(records=records, has_more=has_more, cost_usd=self.cost_per_request_usd, http_calls=1)

    async def health_check(self) -> HealthStatus:
        return HealthStatus("ok", "synthetic data generator (demo mode)")


def synthetic_site_html(domain: str, path: str) -> str | None:
    """HTML for synthetic websites, used by the website enricher's mock fetcher."""
    c = profile_for_domain(domain)
    if not c:
        return None
    from app.data.terms import PRODUCT_TERMS
    lang = "en"
    prods = ", ".join(PRODUCT_TERMS.get(p, {}).get(lang, [p])[0] for p in c["products"]) or "kitchen appliances and electronics"
    lines = {
        "wholesaler": f"We are a furniture wholesaler supplying {prods} to retailers across the region. B2B wholesale only.",
        "distributor": f"Exclusive distributor and agent for European and Turkish furniture brands: {prods}.",
        "importer": f"Furniture importer. We import {prods} from Turkey, Italy and China and supply dealers.",
        "retail_chain": f"Our stores: {c['stores']} furniture stores nationwide. Discover our collection of {prods}. Our brand, designed in-house.",
        "independent_store": f"Family-owned furniture showroom offering {prods}. Visit our store.",
        "ecommerce": f"Online shop for {prods}. Add to cart. Free delivery.",
        "contract_ffe": f"Contract furniture and FF&E procurement for hotels and restaurants: {prods}. Turnkey hospitality projects.",
        "interior_procurement": f"Interior design and fit-out company. We source {prods} for residential and commercial projects.",
        "manufacturer": f"Furniture manufacturer. Our factory produces {prods}. Contract manufacturing and private label available.",
        "used_furniture": "Used furniture and second hand antiques. We buy and sell.",
        "irrelevant": "Kitchen appliances, electronics and home gadgets.",
    }
    body = lines.get(c["profile"], "")
    if c["importer_claim"] and c["profile"] != "importer":
        body += " We import directly from manufacturers."
    if c["oem"]:
        body += " We work with private label / OEM partners for our own brand."
    if path.startswith("/contact"):
        purchasing = f"<p>Purchasing: <a href='mailto:purchasing@{domain}'>purchasing@{domain}</a></p>" if c["profile"] in ("retail_chain", "wholesaler", "importer") else ""
        return (f"<html><body><h1>Contact</h1><p>Email: <a href='mailto:info@{domain}'>info@{domain}</a></p>{purchasing}"
                f"<p>Tel: <a href='tel:{c['phone']}'>{c['phone']}</a></p><p>Employees: {c['employees']}</p></body></html>")
    return (f"<html><head><title>[DEMO] {c['base']}</title></head><body><h1>[DEMO] {c['base']}</h1><p>{body}</p>"
            f"<a href='/contact'>Contact</a></body></html>")
