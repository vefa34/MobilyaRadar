# Source inventory & integration suitability matrix

_Generated from `backend/app/data/sources.py`. Licence/ToS notes are operator summaries and must be re-verified before production use._

| Tier | Source | Purpose | Countries | Access model | Status in this build | Auth | Export | Retention | Notes |
|---|---|---|---|---|---|---|---|---|---|
| P0 | Company official websites | verification, contact_enrichment | global | authorized_web | ✅ active | – | yes | – | Fetches only public pages, honours robots.txt, identifies itself via User-Agent, low rate (1 req/s per host). Stores extracted facts with URL provenance. |
| P0 | OpenStreetMap via Overpass API | discovery | global | open_data | ✅ active | – | yes | – | ODbL: attribution '© OpenStreetMap contributors' required; derived databases are share-alike. Public Overpass instance is for moderate use only — the connector caps queries per job; use a self-hosted instance or Geofabri |
| P0 | Synthetic demo connector | discovery | global | user_import | ✅ active | – | yes | – | Generates clearly-flagged SYNTHETIC companies for demos/tests. Never exported as real leads. |
| P0 | User-provided CSV/XLSX import | discovery | global | user_import | ✅ active | – | yes | – | User warrants it has the right to use the uploaded data. |
| P0 | Brave Search API | discovery | global | licensed_api | 🔑 needs API key | X-Subscription-Token API key | yes | – | Licensed web search results. Storage of results for own use generally permitted on paid plans; verify plan terms. |
| P0 | Das Örtliche | discovery | DE | authorized_web | ✎ manual queue | – | yes | – |  |
| P0 | Gelbe Seiten | discovery | DE | authorized_web | ✎ manual queue | – | yes | – | No public API; automated extraction not permitted. |
| P0 | Google Places API (New) | discovery | global | official_api | 🔑 needs API key | API key (X-Goog-Api-Key) + field mask | no | 30 d | Place IDs may be stored indefinitely. Other Places content may only be cached temporarily (max 30 days) and must not be exported in bulk or merged into a third-party database. This system stores place_id persistently and |
| P0 | PagesJaunes (FR) | discovery | FR | authorized_web | ✎ manual queue | – | yes | – | Solocal offers a commercial API — licence required. |
| P0 | SerpApi (Google results) | discovery | global | licensed_api | 🔑 needs API key | api_key | yes | – |  |
| P0 | Yell (UK) | discovery | GB | authorized_web | ✎ manual queue | – | yes | – |  |
| P0 | Yellow Pages Egypt | discovery | EG | authorized_web | ✎ manual queue | – | yes | – |  |
| P1 | Amman Chamber of Commerce | discovery, verification | JO | manual | ✎ manual queue | – | yes | – | Member search by activity available on site. |
| P1 | BIA (GE) | discovery, verification | GE | licensed_api | 📄 needs licence + adapter | – | yes | – |  |
| P1 | Baghdad Chamber of Commerce | discovery, verification | IQ | manual | ✎ manual queue | – | yes | – |  |
| P1 | Competitor brand dealer/stockist pages | discovery | global | search_index | ✎ manual queue | – | yes | – | Find via web search: '<brand> stockists <country>'. Strong signal: retailers already buying imported furniture. |
| P1 | Dubai Business Directory (investindubai.gov.ae) | discovery, verification | AE | authorized_web | ✎ manual queue | – | yes | – | Official licence lookup by activity; check terms before automation. |
| P1 | Dubai Chambers members | discovery | AE | manual | ✎ manual queue | – | yes | – |  |
| P1 | Erbil Chamber of Commerce & Industry | discovery, verification | IQ | manual | ✎ manual queue | – | yes | – |  |
| P1 | Europages | discovery | DE, FR, GB, NL, BE, ES, IT, PL, RO, C… | authorized_web | 📄 needs licence + adapter | – | yes | – | ToS restricts automated extraction. Requires data partnership/licence or manual research. |
| P1 | Jeddah Chamber | discovery | SA | manual | ✎ manual queue | – | yes | – |  |
| P1 | Kerix (MA) | discovery | MA | authorized_web | ✎ manual queue | – | yes | – |  |
| P1 | Kompass | discovery, verification | global | licensed_api | 📄 needs licence + adapter | Commercial contract (EasyBusiness / API) | yes | – |  |
| P1 | Kuwait Chamber of Commerce & Industry | discovery | KW | manual | ✎ manual queue | – | yes | – |  |
| P1 | Maison&Objet network | discovery | global | manual | ✎ manual queue | – | yes | – | Brands and retailers; MOM platform requires account. |
| P1 | Oman Chamber of Commerce & Industry | discovery | OM | manual | ✎ manual queue | – | yes | – |  |
| P1 | Qatar CID | discovery | QA | manual | ✎ manual queue | – | yes | – |  |
| P1 | Qatar Chamber | discovery | QA | manual | ✎ manual queue | – | yes | – |  |
| P1 | Riyadh Chamber | discovery | SA | manual | ✎ manual queue | – | yes | – |  |
| P1 | Salone del Mobile.Milano exhibitors | discovery | global | manual | ✎ manual queue | – | yes | – | Exhibitor lists mostly manufacturers (competitors) — useful for brand/OEM sourcing leads only. |
| P1 | Spyur (AM) | discovery | AM | authorized_web | ✎ manual queue | – | yes | – | Supports activity/product and importer search; manual or licensed access. |
| P1 | TED — Tenders Electronic Daily | discovery | DE, FR, GB, NL, BE, ES, IT, PL, RO, C… | official_api | 📚 catalogue only | Public search API (anonymous) / EU Login for some features | yes | – | Public procurement notices; open data. Buyers are public bodies (tender_buyer type). |
| P1 | Tripoli / Benghazi chambers of commerce | discovery | LY | manual | ✎ manual queue | – | yes | – |  |
| P1 | UTICA & Tunisian directories | discovery | TN | manual | ✎ manual queue | – | yes | – |  |
| P1 | imm cologne / M.O.W. exhibitor directories | discovery | DE | manual | ✎ manual queue | – | yes | – |  |
| P1 | wlw (Wer liefert was) | discovery | DE, AT, CH | authorized_web | 📄 needs licence + adapter | – | yes | – | No public API; scraping prohibited by ToS. |
| P2 | ARES (Czech economic subjects register) | verification, discovery | CZ | official_api | ✅ active | – | yes | – | Supports NACE-based search (46.47 wholesale furniture, 47.59 retail furniture). |
| P2 | EU VIES VAT number validation | verification | DE, FR, NL, BE, ES, IT, PL, RO, CZ, S… | official_api | ✅ active | – | yes | – | Official EU service for VAT validation; not a discovery source. Respect availability; no bulk crawling. |
| P2 | Annuaire des Entreprises / API Recherche d'entreprises (FR) | verification, discovery | FR | official_api | 📚 catalogue only | – | yes | – | Free API supports NAF filter (46.47Z wholesale furniture, 47.59A retail furniture). Connector planned. |
| P2 | Azerbaijan State Tax Service taxpayer search | verification | AZ | manual | ✎ manual queue | – | yes | – |  |
| P2 | BRIS — EU business registers (e-Justice) | verification | DE, FR, GB, NL, BE, ES, IT, PL, RO, C… | manual | ✎ manual queue | – | yes | – | Verification via e-Justice portal; no bulk API. |
| P2 | Bahrain Sijilat (CR) | verification | BH | manual | ✎ manual queue | – | yes | – |  |
| P2 | CNRC / Sidjilcom (DZ) | verification | DZ | manual | ✎ manual queue | – | yes | – |  |
| P2 | Direct Info / OMPIC (MA) | verification | MA | manual | ✎ manual queue | – | yes | – |  |
| P2 | Geostat business register (GE) | verification, discovery | GE | official_api | 📚 catalogue only | – | yes | – | Statistical register searchable by NACE; check reuse terms. |
| P2 | Handelsregister / Unternehmensregister (DE) | verification | DE | manual | ✎ manual queue | – | yes | – | Automated queries restricted (max 60/h); manual verification. |
| P2 | INPI RNE (FR) | verification | FR | official_api | 📚 catalogue only | Account | yes | – |  |
| P2 | ImportGenius | import_data | global | licensed_api | 📄 needs licence + adapter | – | no | – | Coverage mainly US + selected countries; verify target-country coverage. |
| P2 | ImportYeti | import_data | US | authorized_web | 📄 needs licence + adapter | – | no | – | US Customs bill-of-lading data only — NOT relevant for EU/MENA/Caucasus importers; useful only to see which brands already source from Türkiye into the US. |
| P2 | KBO/BCE (BE) | verification | BE | open_data | 📚 catalogue only | – | yes | – | Open data download with NACE codes — usable for activity-based discovery after licence check. |
| P2 | NAPR registry (GE) | verification | GE | manual | ✎ manual queue | – | yes | – |  |
| P2 | ONRC (RO trade register) | verification | RO | manual | ✎ manual queue | – | yes | – |  |
| P2 | Panjiva (S&P Global) | import_data | global | licensed_api | 📄 needs licence + adapter | Enterprise contract (S&P Capital IQ / Xpressfeed) | no | – | Licensed shipment data; redistribution prohibited. Coverage strongest for US/LatAm/India customs; EU import coverage limited — verify per target country. |
| P2 | REGON / KRS (PL) | verification | PL | official_api | 📚 catalogue only | REGON BIR1 needs key; KRS API open | yes | – | Verification by number; KRS not product-searchable. |
| P2 | Saudi Ministry of Commerce CR inquiry | verification | SA | manual | ✎ manual queue | – | yes | – | Commercial registration verification (Wathiq API is licensed). |
| P2 | UK Companies House API | verification, discovery | GB | official_api | 🔑 needs API key | Free API key (HTTP Basic) | yes | – | SIC 46470 (wholesale furniture), 47591 (retail furniture) enable activity-based search via advanced search. |
| P2 | Volza | import_data | global | licensed_api | 📄 needs licence + adapter | – | no | – | Claims multi-country customs data; quality and legal basis per country must be validated. |
| P2 | e-register.am (AM) | verification | AM | manual | ✎ manual queue | – | yes | – |  |
| P3 | Apollo.io | contact_enrichment | global | licensed_api | 📄 needs licence + adapter | api_key (paid plan) | yes | – |  |
| P3 | Hunter.io | contact_enrichment | global | licensed_api | 🔑 needs API key | api_key | yes | – | Returns professional emails for a domain; GDPR: inform data subjects, honour objections. |
| P3 | LinkedIn Sales Navigator | contact_enrichment | global | manual | ✎ manual queue | – | yes | – | Automated profile collection prohibited. Manual use by licensed seat holders only; the system creates manual research tasks with suggested searches. |
