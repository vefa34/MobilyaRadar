# Architecture

## Components
| Layer | Tech | Path |
|---|---|---|
| Web UI | Next.js 14 (App Router), TypeScript, Tailwind | `frontend/` |
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | `backend/app/main.py`, `backend/app/api/` |
| Jobs | Celery + Redis (prod), in-process thread (dev), inline (tests) | `backend/app/worker.py` |
| Storage | PostgreSQL 16 (JSONB) | `backend/app/models.py` |
| Connectors | async httpx adapters behind `LeadSourceConnector` | `backend/app/connectors/` |
| Domain services | planner, pipeline, entity resolution, classifier, scoring, coverage, export, retention, LLM adapter | `backend/app/services/` |
| Reference data | countries/cities, multilingual terms, HS codes, source catalogue | `backend/app/data/` |

## Connector contract
```python
class LeadSourceConnector:
    async def discover(self, query: DiscoveryQuery, context) -> DiscoveryResult   # records, has_more, page token, cost, source candidates
    async def enrich(self, company: CompanySnapshot, context) -> EnrichmentResult  # evidence, contacts, import signals, updates
    async def health_check(self) -> HealthStatus
    def estimate_cost(self, request) -> float
    # planner hints: uses_language / uses_product / uses_city / supported_buyer_types / max_pages
```
Shared helpers: `RateLimiter`, `request_with_retry` (429 + Retry-After, 5xx/transport exponential backoff with jitter,
401/403 → `AccessRestrictedError`). Typed errors map to task statuses: `RateLimitedError → retry_scheduled/rate_limited`,
`AccessRestrictedError/ConfigurationError → access_restricted`, `ConnectorError → retry/failed (+ circuit breaker)`.

Access resolution (`connectors/registry.py::resolve_access`) combines catalogue status, org permission (enabled,
encrypted credentials, licence confirmation) and env keys. A licensed source with a confirmed licence still refuses to run
until a provider-specific adapter exists — the system never pretends to have access.

## Planning & execution
* Cells: every usable discovery source × country × city (all configured commercial centres, weighted) × buyer type ×
  product × language, collapsing dimensions a source ignores (OSM ignores language & product; registries ignore language/product).
* Next cell = static priority − diversity penalties (same city / buyer type / country already searched).
* Stop rules: budget (pre-checked per request), target pool (2× target) **only after minimum coverage** (≥3 cities and all buyer
  types per country), saturation per (country, city, source) when the new-unique ratio of the last N pages < threshold,
  circuit breaker after 3 consecutive transport failures of a source.
* Query de-duplication per source via normalised token sets.

## Entity resolution
Normalisation: transliteration (unidecode) for Arabic/Cyrillic/Georgian/Armenian/Greek, legal-suffix removal (60+ forms incl.
GmbH, SARL, W.L.L., ООО, ش.م.م), generic trade-word removal → `core_name`. Match signals in order: same source record,
registration number (conflict vetoes), VAT, domain (non-generic), phone (E.164), core name + city, fuzzy core name.
Thresholds: ≥0.85 auto-merge, 0.65–0.85 review queue, else new company. Different city + same identity → branch location.

## Scoring
Buyer Fit (0–100) = weighted components: product fit 25, buyer role 20, import evidence 20, commercial scale 15,
market & logistics 10 (logistics from TR + customs union/FTA), accessibility 10. Rejected businesses capped at 15.
Data Confidence (0–100) = source quality, source diversity, official verification (registry/VAT), website verified,
field corroboration across sources, recency. Synthetic → 0. Weights are versioned (`v1-initial`); `/api/dashboard/calibration`
aggregates component means by CRM outcome for recalibration.

## Multi-tenancy & security
Every tenant row carries `org_id`; all queries filter by the authenticated user's org. JWT (HS256), bcrypt passwords,
role ranks viewer < analyst < admin < owner. Connector credentials Fernet-encrypted (`CREDENTIALS_ENCRYPTION_KEY`).
Audit log for auth, jobs, exports, source permission changes, merges, erasures. Monthly job quota and research budget per org.

## Data lifecycle
Evidence/contacts/locations carry `retention_until` from the source's licence (`max_retention_days`). Celery beat runs
`purge_expired` every 6h: deletes expired evidence and contacts, strips licensed content from locations (persistent IDs
such as Google `place_id` kept), blanks denormalised fields no longer supported by evidence, removes companies with no
remaining name evidence. Export filters each field by exportable provenance.
