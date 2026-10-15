import httpx
import pytest
import respx

from app.connectors.base import (
    AccessRestrictedError,
    CompanySnapshot,
    ConfigurationError,
    ConnectorContext,
    ConnectorError,
    DiscoveryQuery,
    RateLimitedError,
    request_with_retry,
)
from app.connectors.licensed import LicensedSourceConnector, parse_tabular
from app.connectors.mock import MockConnector
from app.connectors.places import GooglePlacesConnector, OverpassConnector
from app.connectors.registries import AresConnector, CompaniesHouseConnector, HunterConnector, ViesConnector
from app.connectors.web_search import BraveSearchConnector
from app.connectors.website import WebsiteConnector

CTX = ConnectorContext()


def q(**kw):
    base = dict(text="Möbelgroßhandel Hamburg", language="de", country="DE", city="Hamburg", buyer_type="wholesaler", product_category="dining_table")
    base.update(kw)
    return DiscoveryQuery(**base)


async def no_sleep(_):
    return None


# ------------------------------------------------------------------ retry / rate limit
@respx.mock
async def test_retry_on_500_then_success():
    route = respx.get("https://api.example.com/x").mock(side_effect=[httpx.Response(500), httpx.Response(502), httpx.Response(200, json={"ok": 1})])
    async with httpx.AsyncClient() as c:
        r = await request_with_retry(c, "GET", "https://api.example.com/x", sleep=no_sleep)
    assert r.status_code == 200 and route.call_count == 3


@respx.mock
async def test_rate_limited_after_retries_and_retry_after_honoured():
    slept = []

    async def rec(s):
        slept.append(s)
    respx.get("https://api.example.com/x").mock(return_value=httpx.Response(429, headers={"Retry-After": "7"}))
    async with httpx.AsyncClient() as c:
        with pytest.raises(RateLimitedError) as ei:
            await request_with_retry(c, "GET", "https://api.example.com/x", retries=2, sleep=rec)
    assert slept == [7.0, 7.0] and ei.value.retry_after == 7.0


@respx.mock
async def test_403_is_access_restricted_without_retry():
    route = respx.get("https://api.example.com/x").mock(return_value=httpx.Response(403))
    async with httpx.AsyncClient() as c:
        with pytest.raises(AccessRestrictedError):
            await request_with_retry(c, "GET", "https://api.example.com/x", sleep=no_sleep)
    assert route.call_count == 1


@respx.mock
async def test_transport_errors_become_connector_error():
    respx.get("https://api.example.com/x").mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as c:
        with pytest.raises(ConnectorError):
            await request_with_retry(c, "GET", "https://api.example.com/x", retries=1, sleep=no_sleep)


# ------------------------------------------------------------------ discovery connectors
async def test_brave_requires_key():
    with pytest.raises(ConfigurationError):
        await BraveSearchConnector({}).discover(q(), CTX)


@respx.mock
async def test_brave_results_to_companies_and_directories():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(return_value=httpx.Response(200, json={
        "query": {"more_results_available": True},
        "web": {"results": [
            {"url": "https://www.nordwind-moebel.de/", "title": "Nordwind Möbel GmbH – Möbelgroßhandel | Hamburg", "description": "Großhandel für Esstische"},
            {"url": "https://www.nordwind-moebel.de/kontakt", "title": "Kontakt - Nordwind Möbel", "description": "dup domain"},
            {"url": "https://www.gelbeseiten.de/moebel/hamburg", "title": "Möbel in Hamburg - Gelbe Seiten", "description": "Branchenbuch"},
            {"url": "https://moebel-verzeichnis.de/hamburg", "title": "Top 10 Möbelgroßhändler in Hamburg", "description": "Liste"},
            {"url": "https://www.facebook.com/x", "title": "X", "description": ""},
        ]}}))
    c = BraveSearchConnector({"api_key": "k"})
    res = await c.discover(q(page=1), CTX)
    await c.aclose()
    assert [r.website for r in res.records] == ["https://nordwind-moebel.de"]
    assert res.records[0].name == "Nordwind Möbel GmbH"
    assert {s["domain"] for s in res.source_candidates} >= {"gelbeseiten.de", "moebel-verzeichnis.de"}
    assert res.has_more and res.cost_usd > 0
    sent = respx.calls.last.request
    assert sent.headers["X-Subscription-Token"] == "k" and "offset=0" in str(sent.url)


@respx.mock
async def test_google_places_pagination_and_restrictions():
    route = respx.post("https://places.googleapis.com/v1/places:searchText").mock(side_effect=[
        httpx.Response(200, json={"places": [{"id": "p1", "displayName": {"text": "Möbel Kraft"}, "formattedAddress": "A 1, Hamburg",
                                              "types": ["furniture_store"], "internationalPhoneNumber": "+49 40 123456",
                                              "addressComponents": [{"types": ["locality"], "longText": "Hamburg"}]},
                                             {"id": "p2", "displayName": {"text": "Closed"}, "businessStatus": "CLOSED_PERMANENTLY"}],
                                  "nextPageToken": "T2"}),
        httpx.Response(200, json={"places": [{"id": "p3", "displayName": {"text": "Wohnwelt"}}]}),
    ])
    c = GooglePlacesConnector({"api_key": "k"})
    r1 = await c.discover(q(), CTX)
    r2 = await c.discover(q(page=2, page_token=r1.next_page_token), CTX)
    await c.aclose()
    assert [r.name for r in r1.records] == ["Möbel Kraft"] and r1.records[0].external_ids == {"google_place_id": "p1"}
    assert r1.has_more and r1.next_page_token == "T2" and not r2.has_more
    import json
    assert json.loads(route.calls[1].request.content)["pageToken"] == "T2"
    assert "places.id" in route.calls[0].request.headers["X-Goog-FieldMask"]


@respx.mock
async def test_overpass_builds_area_query_and_parses():
    route = respx.post("https://overpass-api.de/api/interpreter").mock(return_value=httpx.Response(200, json={"elements": [
        {"type": "node", "id": 1, "lat": 53.5, "lon": 10.0, "tags": {"name": "Möbel Höffner", "shop": "furniture", "brand": "Höffner",
                                                                     "website": "https://hoeffner.de", "addr:city": "Hamburg"}},
        {"type": "way", "id": 2, "center": {"lat": 1, "lon": 2}, "tags": {"shop": "furniture"}},  # nameless → skipped
    ]}))
    c = OverpassConnector({})
    res = await c.discover(q(buyer_type="independent_store"), CTX)
    await c.aclose()
    body = route.calls.last.request.content.decode()
    assert "ISO3166-1" in body and "Hamburg" in body and "furniture" in body
    assert len(res.records) == 1 and "has_brand" in res.records[0].categories
    assert res.records[0].source_url == "https://www.openstreetmap.org/node/1"


async def test_overpass_public_cap(monkeypatch):
    c = OverpassConnector({})
    c.queries_this_job = 10_000
    with pytest.raises(ConfigurationError):
        await c.discover(q(), CTX)


@respx.mock
async def test_companies_house_sic_search():
    route = respx.get("https://api.company-information.service.gov.uk/advanced-search/companies").mock(return_value=httpx.Response(200, json={
        "hits": 250, "items": [{"company_name": "OAK & CO FURNITURE LTD", "company_number": "01234567", "company_status": "active",
                                "sic_codes": ["46470"], "registered_office_address": {"locality": "Manchester", "postal_code": "M1 1AA"}}]}))
    c = CompaniesHouseConnector({"api_key": "k"})
    res = await c.discover(q(country="GB", city="Manchester", language="en"), CTX)
    await c.aclose()
    assert "sic_codes=46470" in str(route.calls.last.request.url)
    assert res.records[0].registration_number == "01234567" and res.has_more
    assert route.calls.last.request.headers["Authorization"].startswith("Basic ")


@respx.mock
async def test_vies_verification():
    respx.post("https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number").mock(
        return_value=httpx.Response(200, json={"valid": True, "name": "NORDWIND MOEBEL GMBH", "address": "HAMBURG"}))
    c = ViesConnector({})
    res = await c.enrich(CompanySnapshot(id="1", name="Nordwind", country="DE", vat_number="DE 123456789"), CTX)
    await c.aclose()
    assert res.updates["vat_verified"] is True and res.updates["legal_name"] == "NORDWIND MOEBEL GMBH"
    assert ViesConnector.split_vat("EL123456789", "GR") == ("EL", "123456789")


@respx.mock
async def test_ares_lookup_and_nace_search():
    respx.get("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/27074358").mock(return_value=httpx.Response(200, json={
        "ico": "27074358", "obchodniJmeno": "Nábytek Praha s.r.o.", "dic": "CZ27074358", "czNace": ["4647"],
        "sidlo": {"nazevObce": "Praha", "textovaAdresa": "Praha 1"}}))
    respx.post("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat").mock(return_value=httpx.Response(200, json={
        "pocetCelkem": 1, "ekonomickeSubjekty": [{"ico": "1", "obchodniJmeno": "X", "czNace": ["4647"], "sidlo": {"nazevObce": "Brno"}}]}))
    c = AresConnector({})
    res = await c.enrich(CompanySnapshot(id="1", name="x", country="CZ", registration_number="27074358"), CTX)
    disc = await c.discover(q(country="CZ", city="Brno"), CTX)
    await c.aclose()
    assert res.updates["vat_number"] == "CZ27074358" and res.evidence[0].evidence_type == "registry_record"
    assert disc.records[0].categories == ["nace:4647"]


@respx.mock
async def test_hunter_filters_irrelevant_departments():
    respx.get("https://api.hunter.io/v2/domain-search").mock(return_value=httpx.Response(200, json={"data": {"emails": [
        {"value": "einkauf@x.de", "type": "generic", "department": None, "confidence": 90},
        {"value": "anna@x.de", "type": "personal", "department": "purchasing", "first_name": "Anna", "position": "Head of Purchasing", "confidence": 80},
        {"value": "dev@x.de", "type": "personal", "department": "it", "confidence": 99},
    ]}}))
    c = HunterConnector({"api_key": "k"})
    res = await c.enrich(CompanySnapshot(id="1", name="X", country="DE", domain="x.de"), CTX)
    await c.aclose()
    vals = {x.value for x in res.contacts}
    assert vals == {"einkauf@x.de", "anna@x.de"}
    assert next(x for x in res.contacts if x.value == "anna@x.de").department == "purchasing"


async def test_licensed_stub_never_pretends():
    with pytest.raises(AccessRestrictedError, match="not confirmed"):
        await LicensedSourceConnector("panjiva").discover(q(), CTX)
    with pytest.raises(AccessRestrictedError, match="adapter not implemented"):
        await LicensedSourceConnector("panjiva", {"api_key": "x"}, license_confirmed=True).discover(q(), CTX)
    assert (await LicensedSourceConnector("volza").health_check()).status == "pending_license"


async def test_mock_connector_pagination_and_flags():
    c = MockConnector({})
    p1 = await c.discover(q(page=1), CTX)
    p2 = await c.discover(q(page=2), CTX)
    assert p1.records and all(r.is_synthetic and r.name.startswith("[DEMO]") for r in p1.records)
    assert all(r.website is None or r.website.endswith(".invalid") for r in p1.records)
    assert not {r.source_record_id for r in p1.records} & {r.source_record_id for r in p2.records}


# ------------------------------------------------------------------ website enrichment
HOME = """<html><head><title>Nordwind Möbel</title></head><body><h1>Nordwind Möbel GmbH</h1>
<p>Möbelgroßhandel und Importeur: Esstische und Stühle für den Fachhandel. 14 Filialen.</p>
<a href="/kontakt">Kontakt</a> <a href="/impressum">Impressum</a> <a href="https://other.com/x">x</a></body></html>"""
CONTACT = """<html><body><a href="mailto:info@nordwind-moebel.de">info@nordwind-moebel.de</a> Einkauf: einkauf@nordwind-moebel.de
Max Mustermann: max.mustermann@nordwind-moebel.de  Tel: <a href="tel:+494012345678">040 123 456 78</a></body></html>"""
IMPRINT = "<html><body>Amtsgericht Hamburg HRB 123456 USt-IdNr.: DE123456789</body></html>"


@respx.mock
async def test_website_enrichment_extracts_facts_with_provenance():
    respx.get("https://nordwind-moebel.de/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nDisallow: /intern/"))
    respx.get("https://nordwind-moebel.de/").mock(return_value=httpx.Response(200, text=HOME, headers={"content-type": "text/html"}))
    respx.get("https://nordwind-moebel.de/kontakt").mock(return_value=httpx.Response(200, text=CONTACT, headers={"content-type": "text/html"}))
    respx.get("https://nordwind-moebel.de/impressum").mock(return_value=httpx.Response(200, text=IMPRINT, headers={"content-type": "text/html"}))
    w = WebsiteConnector({})
    snap = CompanySnapshot(id="1", name="Nordwind", country="DE", website="https://nordwind-moebel.de", domain="nordwind-moebel.de",
                           product_terms=["Esstisch", "Stühle", "dining table"])
    res = await w.enrich(snap, CTX)
    await w.aclose()
    assert res.status == "ok"
    emails = {c.value for c in res.contacts if c.contact_type == "email"}
    assert emails == {"info@nordwind-moebel.de", "einkauf@nordwind-moebel.de"}  # personal mailbox NOT harvested
    assert any(c.department == "purchasing" for c in res.contacts)
    assert "+494012345678" in {c.value for c in res.contacts if c.contact_type == "phone"}
    assert res.updates["vat_number"] == "DE123456789" and "HRB" in res.updates["registration_number"]
    assert res.updates["store_count"] == 14
    assert res.updates["website_product_match"] > 0.5
    assert all(e.source_url and e.source_url.startswith("https://nordwind-moebel.de") for e in res.evidence)
    assert res.import_signals and not res.import_signals[0].verified


@respx.mock
async def test_website_robots_disallow_respected():
    respx.get("https://blocked.de/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nDisallow: /"))
    home = respx.get("https://blocked.de/").mock(return_value=httpx.Response(200, text="x"))
    w = WebsiteConnector({})
    res = await w.enrich(CompanySnapshot(id="1", name="B", country="DE", website="https://blocked.de", domain="blocked.de"), CTX)
    await w.aclose()
    assert res.status == "blocked_by_robots" and home.call_count == 0


def test_csv_xlsx_import_parsing():
    rows = parse_tabular("Firma;Website;Stadt;Land\nMöbel A;a.de;Berlin;DE\n;x;y;z\n".encode(), "x.csv")
    assert rows == [{"name": "Möbel A", "website": "a.de", "city": "Berlin", "country": "DE"}]
    from io import BytesIO

    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["Company Name", "Country", "Phone"])
    wb.active.append(["Dar Al Athath", "IQ", "+964 750 000 0000"])
    buf = BytesIO()
    wb.save(buf)
    assert parse_tabular(buf.getvalue(), "x.xlsx")[0]["name"] == "Dar Al Athath"
