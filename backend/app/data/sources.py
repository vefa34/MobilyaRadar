"""Seed source catalogue.

This is a *starting* catalogue. Entries are synchronised into ``source_registry`` at startup
(``services.source_catalog.sync_seed_sources``) and can be extended by users or by the source
discovery job. ``integration_status`` reflects what this codebase can actually do today:

* active               – connector implemented, usable without extra credentials
* pending_credentials  – connector implemented, needs an API key (free or paid)
* pending_license      – connector skeleton only; requires a commercial contract / licence
                         confirmation and API documentation before it may run
* manual               – no compliant automation path; tasks go to the manual research queue
* catalog_only         – known useful source, no connector yet (manual queue)

Licence/ToS notes are summaries for operators and MUST be re-checked (``last_checked_at``) before
production use. Nothing here asserts that a public API exists unless stated.
"""

D, V, I, E = "discovery", "verification", "import_data", "contact_enrichment"

_GLOBAL = ["*"]
EU = ["DE", "FR", "GB", "NL", "BE", "ES", "IT", "PL", "RO", "CZ", "SK", "AT", "BG", "GR", "RS"]
EU_VIES = ["DE", "FR", "NL", "BE", "ES", "IT", "PL", "RO", "CZ", "SK", "AT", "BG", "GR"]
ALL_BUYERS = ["wholesaler", "distributor", "retail_chain", "independent_store", "ecommerce", "contract_ffe",
              "interior_procurement", "brand_private_label", "verified_importer"]


def S(key, name, url, tier, purposes, countries, access_model, status, *, connector=None, has_api=False,
      auth=None, pricing=None, terms_url=None, terms=None, storage=True, retention=None, export=True, merge=True,
      persistent_ids=(), rate_limit=None, fields=(), reliability=0.5, cost=0.0, product_searchable=False,
      customer_types=ALL_BUYERS, regions=(), languages=(), notes=None):
    return dict(key=key, name=name, url=url, tier=tier, purposes=list(purposes), countries=list(countries),
                access_model=access_model, integration_status=status, connector_key=connector, has_api=has_api,
                auth_required=auth, pricing=pricing, terms_url=terms_url, terms_summary=terms, storage_allowed=storage,
                max_retention_days=retention, export_allowed=export, merge_allowed=merge,
                persistent_id_fields=list(persistent_ids), rate_limit=rate_limit, data_fields=list(fields),
                reliability=reliability, cost_per_request_usd=cost, product_searchable=product_searchable,
                customer_types=list(customer_types), regions=list(regions), languages=list(languages), notes=notes)


SEED_SOURCES: list[dict] = [
    # ------------------------------------------------------------------ P0 — implemented connectors
    S("mock", "Synthetic demo connector", None, "P0", [D], _GLOBAL, "user_import", "active", connector="mock",
      notes="Generates clearly-flagged SYNTHETIC companies for demos/tests. Never exported as real leads.",
      reliability=0.0, product_searchable=True),
    S("brave_search", "Brave Search API", "https://api.search.brave.com", "P0", [D], _GLOBAL, "licensed_api",
      "pending_credentials", connector="brave_search", has_api=True, auth="X-Subscription-Token API key",
      pricing="Free tier ~2k queries/month; paid plans per 1k queries (check current pricing)",
      terms_url="https://api.search.brave.com/app/documentation/terms-of-service",
      terms="Licensed web search results. Storage of results for own use generally permitted on paid plans; verify plan terms.",
      rate_limit="1 req/s (free), higher on paid", fields=["title", "url", "description"], reliability=0.45, cost=0.005,
      product_searchable=True),
    S("serpapi", "SerpApi (Google results)", "https://serpapi.com", "P0", [D], _GLOBAL, "licensed_api",
      "pending_credentials", connector="serpapi", has_api=True, auth="api_key", pricing="Paid plans per search",
      terms_url="https://serpapi.com/terms", rate_limit="plan dependent", fields=["title", "link", "snippet"],
      reliability=0.45, cost=0.01, product_searchable=True),
    S("google_places", "Google Places API (New)", "https://developers.google.com/maps/documentation/places/web-service",
      "P0", [D], _GLOBAL, "official_api", "pending_credentials", connector="google_places", has_api=True,
      auth="API key (X-Goog-Api-Key) + field mask", pricing="Pay-as-you-go per SKU; Text Search Pro fields ~USD 32/1000",
      terms_url="https://cloud.google.com/maps-platform/terms",
      terms=("Place IDs may be stored indefinitely. Other Places content may only be cached temporarily (max 30 days) "
             "and must not be exported in bulk or merged into a third-party database. This system stores place_id "
             "persistently and Places content with retention_until=+30d, excludes it from exports, and refreshes on demand."),
      storage=True, retention=30, export=False, merge=False, persistent_ids=["place_id"],
      rate_limit="QPM quota per project", fields=["displayName", "formattedAddress", "nationalPhoneNumber", "websiteUri", "types"],
      reliability=0.7, cost=0.032, product_searchable=False,
      customer_types=["independent_store", "retail_chain", "wholesaler"]),
    S("osm_overpass", "OpenStreetMap via Overpass API", "https://wiki.openstreetmap.org/wiki/Overpass_API", "P0", [D],
      _GLOBAL, "open_data", "active", connector="osm_overpass", has_api=True, auth=None,
      pricing="Free (public instance, fair use) / self-host",
      terms_url="https://www.openstreetmap.org/copyright",
      terms=("ODbL: attribution '© OpenStreetMap contributors' required; derived databases are share-alike. "
             "Public Overpass instance is for moderate use only — the connector caps queries per job; use a "
             "self-hosted instance or Geofabrik extracts for volume. Nominatim is NOT used for bulk mining."),
      rate_limit="~10k queries/day, 2 concurrent (public overpass-api.de)",
      fields=["name", "shop", "addr:*", "phone", "website", "email", "brand"], reliability=0.6, cost=0.0,
      customer_types=["independent_store", "retail_chain", "wholesaler"]),
    S("company_website", "Company official websites", None, "P0", [V, E], _GLOBAL, "authorized_web", "active",
      connector="website", auth=None, terms="Fetches only public pages, honours robots.txt, identifies itself via User-Agent, "
      "low rate (1 req/s per host). Stores extracted facts with URL provenance.", reliability=0.75, cost=0.0),
    S("csv_import", "User-provided CSV/XLSX import", None, "P0", [D], _GLOBAL, "user_import", "active", connector="csv_import",
      terms="User warrants it has the right to use the uploaded data.", reliability=0.6),

    # ------------------------------------------------------------------ P1 — sector directories
    S("europages", "Europages", "https://www.europages.com", "P1", [D], EU, "authorized_web", "pending_license",
      connector="licensed_stub", product_searchable=True, terms_url="https://www.europages.com/terms",
      terms="ToS restricts automated extraction. Requires data partnership/licence or manual research.",
      reliability=0.6, cost=0.0, regions=["europe"]),
    S("kompass", "Kompass", "https://www.kompass.com", "P1", [D, V], _GLOBAL, "licensed_api", "pending_license",
      connector="licensed_stub", has_api=True, auth="Commercial contract (EasyBusiness / API)",
      pricing="Paid subscription; data export credits", product_searchable=True, reliability=0.7, cost=0.15),
    S("wlw", "wlw (Wer liefert was)", "https://www.wlw.de", "P1", [D], ["DE", "AT", "CH"], "authorized_web", "pending_license",
      connector="licensed_stub", product_searchable=True, terms="No public API; scraping prohibited by ToS.",
      reliability=0.65, languages=["de"]),
    S("salone_milano", "Salone del Mobile.Milano exhibitors", "https://www.salonemilano.it", "P1", [D], _GLOBAL, "manual",
      "manual", notes="Exhibitor lists mostly manufacturers (competitors) — useful for brand/OEM sourcing leads only."),
    S("maison_objet", "Maison&Objet network", "https://www.maison-objet.com", "P1", [D], _GLOBAL, "manual", "manual",
      notes="Brands and retailers; MOM platform requires account."),
    S("imm_cologne", "imm cologne / M.O.W. exhibitor directories", "https://www.imm-cologne.com", "P1", [D], ["DE"], "manual", "manual"),
    S("ted_europa", "TED — Tenders Electronic Daily", "https://ted.europa.eu", "P1", [D], EU, "official_api", "catalog_only",
      has_api=True, auth="Public search API (anonymous) / EU Login for some features",
      terms="Public procurement notices; open data. Buyers are public bodies (tender_buyer type).",
      customer_types=["tender_buyer"], product_searchable=True, reliability=0.9,
      notes="Use CPV 39100000 (furniture), 39110000 (seats/chairs), 39120000 (tables). Connector planned (Phase 3)."),
    S("competitor_stockists", "Competitor brand dealer/stockist pages", None, "P1", [D], _GLOBAL, "search_index", "manual",
      notes="Find via web search: '<brand> stockists <country>'. Strong signal: retailers already buying imported furniture."),

    # ------------------------------------------------------------------ P2 — import/shipment data & registries
    S("panjiva", "Panjiva (S&P Global)", "https://panjiva.com", "P2", [I], _GLOBAL, "licensed_api", "pending_license",
      connector="licensed_stub", auth="Enterprise contract (S&P Capital IQ / Xpressfeed)", pricing="Enterprise, quote-based",
      terms="Licensed shipment data; redistribution prohibited. Coverage strongest for US/LatAm/India customs; EU import coverage limited — verify per target country.",
      storage=True, export=False, reliability=0.9, cost=1.0),
    S("importgenius", "ImportGenius", "https://www.importgenius.com", "P2", [I], _GLOBAL, "licensed_api", "pending_license",
      connector="licensed_stub", pricing="Subscription; API on enterprise plans", terms="Coverage mainly US + selected countries; verify target-country coverage.",
      export=False, reliability=0.85, cost=0.5),
    S("volza", "Volza", "https://www.volza.com", "P2", [I], _GLOBAL, "licensed_api", "pending_license", connector="licensed_stub",
      pricing="Subscription credits", terms="Claims multi-country customs data; quality and legal basis per country must be validated.",
      export=False, reliability=0.7, cost=0.3),
    S("importyeti", "ImportYeti", "https://www.importyeti.com", "P2", [I], ["US"], "authorized_web", "pending_license",
      connector="licensed_stub", terms="US Customs bill-of-lading data only — NOT relevant for EU/MENA/Caucasus importers; "
      "useful only to see which brands already source from Türkiye into the US.", export=False, reliability=0.8),
    S("vies", "EU VIES VAT number validation", "https://ec.europa.eu/taxation_customs/vies", "P2", [V], EU_VIES, "official_api",
      "active", connector="vies", has_api=True, auth=None, pricing="Free",
      terms="Official EU service for VAT validation; not a discovery source. Respect availability; no bulk crawling.",
      rate_limit="Member-state services have downtime windows", fields=["valid", "name", "address"], reliability=0.95),
    S("companies_house", "UK Companies House API", "https://developer.company-information.service.gov.uk", "P2", [V, D], ["GB"],
      "official_api", "pending_credentials", connector="companies_house", has_api=True, auth="Free API key (HTTP Basic)",
      pricing="Free", rate_limit="600 requests / 5 min", fields=["company_name", "company_number", "company_status", "sic_codes", "address"],
      reliability=0.95, notes="SIC 46470 (wholesale furniture), 47591 (retail furniture) enable activity-based search via advanced search."),
    S("ares", "ARES (Czech economic subjects register)", "https://ares.gov.cz", "P2", [V, D], ["CZ"], "official_api", "active",
      connector="ares", has_api=True, auth=None, pricing="Free", rate_limit="Fair use (~500 req/min)",
      fields=["ico", "obchodniJmeno", "sidlo", "czNace", "dic"], reliability=0.95,
      notes="Supports NACE-based search (46.47 wholesale furniture, 47.59 retail furniture)."),
    S("bris", "BRIS — EU business registers (e-Justice)", "https://e-justice.europa.eu", "P2", [V], EU, "manual", "manual",
      notes="Verification via e-Justice portal; no bulk API."),
    S("handelsregister", "Handelsregister / Unternehmensregister (DE)", "https://www.handelsregister.de", "P2", [V], ["DE"],
      "manual", "manual", terms="Automated queries restricted (max 60/h); manual verification."),
    S("annuaire_entreprises", "Annuaire des Entreprises / API Recherche d'entreprises (FR)", "https://annuaire-entreprises.data.gouv.fr",
      "P2", [V, D], ["FR"], "official_api", "catalog_only", has_api=True, auth=None, pricing="Free (open data, Etalab licence)",
      reliability=0.95, notes="Free API supports NAF filter (46.47Z wholesale furniture, 47.59A retail furniture). Connector planned."),
    S("inpi", "INPI RNE (FR)", "https://data.inpi.fr", "P2", [V], ["FR"], "official_api", "catalog_only", has_api=True, auth="Account"),
    S("regon_krs", "REGON / KRS (PL)", "https://api-krs.ms.gov.pl", "P2", [V], ["PL"], "official_api", "catalog_only", has_api=True,
      auth="REGON BIR1 needs key; KRS API open", notes="Verification by number; KRS not product-searchable."),
    S("onrc", "ONRC (RO trade register)", "https://www.onrc.ro", "P2", [V], ["RO"], "manual", "manual"),
    S("kbo_bce", "KBO/BCE (BE)", "https://kbopub.economie.fgov.be", "P2", [V], ["BE"], "open_data", "catalog_only",
      notes="Open data download with NACE codes — usable for activity-based discovery after licence check."),

    # ------------------------------------------------------------------ Country directories (manual / catalog)
    S("gelbe_seiten", "Gelbe Seiten", "https://www.gelbeseiten.de", "P0", [D], ["DE"], "authorized_web", "manual",
      terms="No public API; automated extraction not permitted.", customer_types=["independent_store", "retail_chain", "wholesaler"]),
    S("das_oertliche", "Das Örtliche", "https://www.dasoertliche.de", "P0", [D], ["DE"], "authorized_web", "manual"),
    S("yell", "Yell (UK)", "https://www.yell.com", "P0", [D], ["GB"], "authorized_web", "manual"),
    S("pagesjaunes", "PagesJaunes (FR)", "https://www.pagesjaunes.fr", "P0", [D], ["FR"], "authorized_web", "manual",
      notes="Solocal offers a commercial API — licence required."),
    S("baghdad_chamber", "Baghdad Chamber of Commerce", "https://www.baghdadchamber.com", "P1", [D, V], ["IQ"], "manual", "manual", languages=["ar"]),
    S("erbil_chamber", "Erbil Chamber of Commerce & Industry", "https://www.erbilchamber.org", "P1", [D, V], ["IQ"], "manual", "manual", languages=["ar", "ku", "en"]),
    S("dubai_business_directory", "Dubai Business Directory (investindubai.gov.ae)", "https://www.investindubai.gov.ae", "P1", [D, V],
      ["AE"], "authorized_web", "manual", notes="Official licence lookup by activity; check terms before automation."),
    S("dubai_chambers", "Dubai Chambers members", "https://www.dubaichamber.com", "P1", [D], ["AE"], "manual", "manual"),
    S("sa_mc_cr", "Saudi Ministry of Commerce CR inquiry", "https://mc.gov.sa", "P2", [V], ["SA"], "manual", "manual",
      notes="Commercial registration verification (Wathiq API is licensed)."),
    S("riyadh_chamber", "Riyadh Chamber", "https://www.rdcci.org.sa", "P1", [D], ["SA"], "manual", "manual", languages=["ar"]),
    S("jeddah_chamber", "Jeddah Chamber", "https://www.jcci.org.sa", "P1", [D], ["SA"], "manual", "manual", languages=["ar"]),
    S("amman_chamber", "Amman Chamber of Commerce", "https://www.ammanchamber.org.jo", "P1", [D, V], ["JO"], "manual", "manual",
      notes="Member search by activity available on site."),
    S("qatar_chamber", "Qatar Chamber", "https://www.qatarchamber.com", "P1", [D], ["QA"], "manual", "manual"),
    S("qatarcid", "Qatar CID", "https://www.qatarcid.com", "P1", [D], ["QA"], "manual", "manual"),
    S("kuwait_chamber", "Kuwait Chamber of Commerce & Industry", "https://www.kuwaitchamber.org.kw", "P1", [D], ["KW"], "manual", "manual"),
    S("oman_chamber", "Oman Chamber of Commerce & Industry", "https://www.chamberoman.om", "P1", [D], ["OM"], "manual", "manual"),
    S("bahrain_sijilat", "Bahrain Sijilat (CR)", "https://www.sijilat.bh", "P2", [V], ["BH"], "manual", "manual"),
    S("kerix", "Kerix (MA)", "https://www.kerix.net", "P1", [D], ["MA"], "authorized_web", "manual", languages=["fr"]),
    S("directinfo_ma", "Direct Info / OMPIC (MA)", "https://www.directinfo.ma", "P2", [V], ["MA"], "manual", "manual"),
    S("cnrc_dz", "CNRC / Sidjilcom (DZ)", "https://sidjilcom.cnrc.dz", "P2", [V], ["DZ"], "manual", "manual"),
    S("utica_tn", "UTICA & Tunisian directories", "https://www.utica.org.tn", "P1", [D], ["TN"], "manual", "manual"),
    S("libya_chambers", "Tripoli / Benghazi chambers of commerce", None, "P1", [D], ["LY"], "manual", "manual", languages=["ar"]),
    S("yellowpages_eg", "Yellow Pages Egypt", "https://www.yellowpages.com.eg", "P0", [D], ["EG"], "authorized_web", "manual"),
    S("bia_ge", "BIA (GE)", "https://www.bia.ge", "P1", [D, V], ["GE"], "licensed_api", "pending_license", connector="licensed_stub",
      pricing="Subscription", languages=["ka", "en"], product_searchable=True),
    S("geostat_br", "Geostat business register (GE)", "https://br.geostat.ge", "P2", [V, D], ["GE"], "official_api", "catalog_only",
      notes="Statistical register searchable by NACE; check reuse terms."),
    S("napr_ge", "NAPR registry (GE)", "https://napr.gov.ge", "P2", [V], ["GE"], "manual", "manual"),
    S("taxes_az", "Azerbaijan State Tax Service taxpayer search", "https://www.taxes.gov.az", "P2", [V], ["AZ"], "manual", "manual"),
    S("spyur_am", "Spyur (AM)", "https://www.spyur.am", "P1", [D], ["AM"], "authorized_web", "manual", product_searchable=True,
      notes="Supports activity/product and importer search; manual or licensed access."),
    S("eregister_am", "e-register.am (AM)", "https://www.e-register.am", "P2", [V], ["AM"], "manual", "manual"),

    # ------------------------------------------------------------------ P3 — contact enrichment
    S("hunter", "Hunter.io", "https://hunter.io", "P3", [E], _GLOBAL, "licensed_api", "pending_credentials", connector="hunter",
      has_api=True, auth="api_key", pricing="Free tier 25 searches/mo; paid plans", rate_limit="15 req/s",
      terms="Returns professional emails for a domain; GDPR: inform data subjects, honour objections.",
      fields=["email", "first_name", "last_name", "position", "department", "confidence"], reliability=0.7, cost=0.05),
    S("apollo", "Apollo.io", "https://www.apollo.io", "P3", [E], _GLOBAL, "licensed_api", "pending_license", connector="licensed_stub",
      has_api=True, auth="api_key (paid plan)", pricing="Credits", reliability=0.65, cost=0.1),
    S("linkedin_sales_navigator", "LinkedIn Sales Navigator", "https://business.linkedin.com/sales-solutions", "P3", [E], _GLOBAL,
      "manual", "manual", terms="Automated profile collection prohibited. Manual use by licensed seat holders only; "
      "the system creates manual research tasks with suggested searches."),
]
