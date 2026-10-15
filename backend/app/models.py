"""Database models.

Design notes
------------
* Every tenant-owned row carries ``org_id``. Companies are tenant-scoped on purpose: data obtained
  through one organisation's licensed providers (e.g. shipment data) must never leak to another
  tenant, and GDPR/KVKK erasure requests can be executed per tenant.
* Every important fact is stored together with its provenance (``source_key``, ``source_url``,
  ``observed_at``) in ``company_evidence``; denormalised columns on ``companies`` are a cache of the
  best-known value and always have at least one evidence row behind them.
* Rows whose source licence limits retention carry ``retention_until``; ``services.retention``
  purges them.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:
        return self.value


class BuyerType(StrEnum):
    VERIFIED_IMPORTER = "verified_importer"            # A
    WHOLESALER = "wholesaler"                          # B
    DISTRIBUTOR = "distributor"                        # C
    RETAIL_CHAIN = "retail_chain"                      # D
    INDEPENDENT_STORE = "independent_store"            # E
    ECOMMERCE = "ecommerce"                            # F
    CONTRACT_FFE = "contract_ffe"                      # G
    BRAND_PRIVATE_LABEL = "brand_private_label"        # H
    INTERIOR_PROCUREMENT = "interior_procurement"      # I
    TENDER_BUYER = "tender_buyer"                      # J
    MANUFACTURER = "manufacturer"                      # K
    UNCLEAR = "unclear"                                # L


class TaskStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    NO_RESULTS = "no_results"
    RATE_LIMITED = "rate_limited"
    ACCESS_RESTRICTED = "access_restricted"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    MANUAL_REVIEW = "manual_review_required"
    SKIPPED_BUDGET = "skipped_budget"
    SKIPPED_SATURATED = "skipped_saturated"
    SKIPPED_TARGET_REACHED = "skipped_target_reached"


class JobStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    PLANNING = "planning"
    DISCOVERING = "discovering"
    ENRICHING = "enriching"
    SCORING = "scoring"
    COMPLETED = "completed"
    COMPLETED_PARTIAL = "completed_partial"   # finished but coverage gaps / budget stop
    FAILED = "failed"
    CANCELLED = "cancelled"


class IntegrationStatus(StrEnum):
    ACTIVE = "active"                         # connector implemented and usable now
    PENDING_CREDENTIALS = "pending_credentials"  # implemented; needs API key
    PENDING_LICENSE = "pending_license"       # needs a commercial contract / licence confirmation
    MANUAL = "manual"                         # human research queue only
    CATALOG_ONLY = "catalog_only"             # known source, no connector yet
    INACTIVE = "inactive"


# ---------------------------------------------------------------------------------------------
# Tenancy & users
# ---------------------------------------------------------------------------------------------
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(50), default="trial")
    monthly_research_budget_usd: Mapped[float] = mapped_column(Numeric(12, 4), default=100)
    monthly_job_quota: Mapped[int] = mapped_column(Integer, default=50)
    exporter_origin_country: Mapped[str] = mapped_column(String(2), default="TR")
    data_retention_days: Mapped[int] = mapped_column(Integer, default=730)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="analyst")  # owner|admin|analyst|viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    organization: Mapped[Organization] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------------------------------------
# Source catalogue & permissions
# ---------------------------------------------------------------------------------------------
class SourceRegistry(Base):
    """Catalogue of known data sources. Presence here does NOT mean the source is connected."""
    __tablename__ = "source_registry"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(500))
    tier: Mapped[str] = mapped_column(String(4))               # P0..P3
    purposes: Mapped[list] = mapped_column(JSONType, default=list)  # discovery|verification|import_data|contact_enrichment
    regions: Mapped[list] = mapped_column(JSONType, default=list)
    countries: Mapped[list] = mapped_column(JSONType, default=list)  # ISO-2; ["*"] = global
    customer_types: Mapped[list] = mapped_column(JSONType, default=list)
    product_searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    has_api: Mapped[bool] = mapped_column(Boolean, default=False)
    access_model: Mapped[str] = mapped_column(String(40))  # official_api|licensed_api|open_data|authorized_web|search_index|user_import|manual
    auth_required: Mapped[str | None] = mapped_column(String(200))
    pricing: Mapped[str | None] = mapped_column(Text)
    terms_url: Mapped[str | None] = mapped_column(String(500))
    terms_summary: Mapped[str | None] = mapped_column(Text)
    storage_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    max_retention_days: Mapped[int | None] = mapped_column(Integer)   # None = no source-imposed limit
    export_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    merge_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    persistent_id_fields: Mapped[list] = mapped_column(JSONType, default=list)  # e.g. ["place_id"]
    rate_limit: Mapped[str | None] = mapped_column(String(200))
    data_fields: Mapped[list] = mapped_column(JSONType, default=list)
    reliability: Mapped[float] = mapped_column(Float, default=0.5)
    cost_per_request_usd: Mapped[float] = mapped_column(Float, default=0.0)
    connector_key: Mapped[str | None] = mapped_column(String(80))
    integration_status: Mapped[str] = mapped_column(String(30), default=IntegrationStatus.CATALOG_ONLY.value)
    languages: Mapped[list] = mapped_column(JSONType, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    discovered_automatically: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(20), default="approved")  # approved|pending_review|rejected
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SourcePermission(Base):
    """Per-organisation enablement, credentials and licence confirmation for a source."""
    __tablename__ = "source_permissions"
    __table_args__ = (UniqueConstraint("org_id", "source_key"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    license_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    license_reference: Mapped[str | None] = mapped_column(String(300))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    monthly_budget_usd: Mapped[float | None] = mapped_column(Float)
    last_health_status: Mapped[str | None] = mapped_column(String(40))
    last_health_message: Mapped[str | None] = mapped_column(Text)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------------------------
# Research jobs
# ---------------------------------------------------------------------------------------------
class SearchJob(Base):
    __tablename__ = "search_jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300))
    request_text: Mapped[str | None] = mapped_column(Text)
    product_config: Mapped[dict] = mapped_column(JSONType, default=dict)
    countries: Mapped[list] = mapped_column(JSONType, default=list)
    buyer_types: Mapped[list] = mapped_column(JSONType, default=list)
    target_company_count: Mapped[int] = mapped_column(Integer, default=200)
    min_buyer_fit: Mapped[int] = mapped_column(Integer, default=50)
    budget_usd: Mapped[float] = mapped_column(Float, default=10.0)
    spent_usd: Mapped[float] = mapped_column(Float, default=0.0)
    use_paid_sources: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_sources: Mapped[list] = mapped_column(JSONType, default=list)  # empty = all permitted
    include_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default=JobStatus.QUEUED.value, index=True)
    stop_reason: Mapped[str | None] = mapped_column(Text)
    plan_summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    coverage_report: Mapped[dict] = mapped_column(JSONType, default=dict)
    progress: Mapped[dict] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchTask(Base):
    """One cell of the plan: Country × City × BuyerType × Product × Language × Source."""
    __tablename__ = "search_tasks"
    __table_args__ = (Index("ix_task_job_status", "job_id", "status"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), index=True)
    country: Mapped[str] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(120))
    buyer_type: Mapped[str] = mapped_column(String(40))
    product_category: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(10))
    source_key: Mapped[str] = mapped_column(String(80))
    priority: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default=TaskStatus.PLANNED.value)
    status_reason: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queries_run: Mapped[int] = mapped_column(Integer, default=0)
    raw_results: Mapped[int] = mapped_column(Integer, default=0)
    new_unique: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchQuery(Base):
    __tablename__ = "search_queries"
    __table_args__ = (Index("ix_query_job_norm", "job_id", "source_key", "normalized_query"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_tasks.id", ondelete="CASCADE"))
    source_key: Mapped[str] = mapped_column(String(80))
    query_text: Mapped[str] = mapped_column(Text)
    normalized_query: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10))
    page: Mapped[int] = mapped_column(Integer, default=1)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    new_companies: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceExecution(Base):
    __tablename__ = "source_executions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_tasks.id", ondelete="CASCADE"))
    source_key: Mapped[str] = mapped_column(String(80), index=True)
    operation: Mapped[str] = mapped_column(String(30))  # discover|enrich|verify|health
    status: Mapped[str] = mapped_column(String(30))
    http_status: Mapped[int | None] = mapped_column(Integer)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchCost(Base):
    __tablename__ = "research_costs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_tasks.id", ondelete="SET NULL"))
    source_key: Mapped[str] = mapped_column(String(80))
    cost_type: Mapped[str] = mapped_column(String(30))  # api_call|llm_tokens|enrichment|verification
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    units: Mapped[float] = mapped_column(Float, default=1)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------------------------
class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_company_org_domain", "org_id", "domain"),
        Index("ix_company_org_country_core", "org_id", "country", "core_name"),
        Index("ix_company_org_reg", "org_id", "country", "registration_number"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    trade_name: Mapped[str | None] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(300))
    name_original_script: Mapped[str | None] = mapped_column(String(300))
    name_transliterated: Mapped[str | None] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)
    core_name: Mapped[str] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(2), index=True)
    city: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(String(30))
    website: Mapped[str | None] = mapped_column(String(500))
    domain: Mapped[str | None] = mapped_column(String(255))
    general_email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(60))
    registration_number: Mapped[str | None] = mapped_column(String(80))
    vat_number: Mapped[str | None] = mapped_column(String(40))
    registry_status: Mapped[str | None] = mapped_column(String(40))  # active|dissolved|unknown
    industry: Mapped[str] = mapped_column(String(60), default="furniture")
    buyer_types: Mapped[list] = mapped_column(JSONType, default=list)
    primary_buyer_type: Mapped[str] = mapped_column(String(40), default=BuyerType.UNCLEAR.value)
    product_categories: Mapped[list] = mapped_column(JSONType, default=list)
    price_segment: Mapped[str | None] = mapped_column(String(20))
    company_size: Mapped[str | None] = mapped_column(String(30))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    store_count: Mapped[int | None] = mapped_column(Integer)
    import_activity_status: Mapped[str] = mapped_column(String(30), default="unknown")  # unknown|claimed|indicated|verified
    oem_private_label_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    website_product_match: Mapped[float | None] = mapped_column(Float)
    website_status: Mapped[str | None] = mapped_column(String(30))  # ok|unreachable|blocked_by_robots|not_found
    purchasing_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    buyer_fit_score: Mapped[float | None] = mapped_column(Float, index=True)
    data_confidence_score: Mapped[float | None] = mapped_column(Float)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[list] = mapped_column(JSONType, default=list)
    parent_company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    research_status: Mapped[str] = mapped_column(String(30), default="discovered")  # discovered|enriched|verified|rejected
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    first_seen_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_jobs.id", ondelete="SET NULL"))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    aliases: Mapped[list["CompanyAlias"]] = relationship(cascade="all, delete-orphan", back_populates="company")
    locations: Mapped[list["CompanyLocation"]] = relationship(cascade="all, delete-orphan", back_populates="company")
    contacts: Mapped[list["CompanyContact"]] = relationship(cascade="all, delete-orphan", back_populates="company")
    categories: Mapped[list["CompanyCategory"]] = relationship(cascade="all, delete-orphan", back_populates="company")
    evidence: Mapped[list["CompanyEvidence"]] = relationship(cascade="all, delete-orphan", back_populates="company")
    import_signals: Mapped[list["ImportSignal"]] = relationship(cascade="all, delete-orphan", back_populates="company")


class CompanyAlias(Base):
    __tablename__ = "company_aliases"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(300))
    normalized: Mapped[str] = mapped_column(String(300), index=True)
    script: Mapped[str | None] = mapped_column(String(20))
    alias_type: Mapped[str] = mapped_column(String(30), default="trade_name")  # legal|trade_name|transliteration|brand|branch
    source_key: Mapped[str | None] = mapped_column(String(80))
    company: Mapped[Company] = relationship(back_populates="aliases")


class CompanyLocation(Base):
    __tablename__ = "company_locations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    location_type: Mapped[str] = mapped_column(String(30), default="unknown")  # hq|branch|store|showroom|warehouse|unknown
    name: Mapped[str | None] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(30))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str | None] = mapped_column(String(60))
    external_ids: Mapped[dict] = mapped_column(JSONType, default=dict)  # e.g. {"google_place_id": "..."}
    source_key: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[Company] = relationship(back_populates="locations")


class CompanyContact(Base):
    __tablename__ = "company_contacts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    contact_type: Mapped[str] = mapped_column(String(20))  # email|phone|contact_form|person|whatsapp
    value: Mapped[str | None] = mapped_column(String(500))
    person_name: Mapped[str | None] = mapped_column(String(200))
    job_title: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(60))  # purchasing|sales|management|general
    is_generic: Mapped[bool] = mapped_column(Boolean, default=True)  # role mailbox vs personal data
    legal_basis: Mapped[str | None] = mapped_column(String(60))  # e.g. legitimate_interest_b2b_published
    source_key: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[Company] = relationship(back_populates="contacts")


class CompanyCategory(Base):
    __tablename__ = "company_categories"
    __table_args__ = (UniqueConstraint("company_id", "kind", "code"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # buyer_type|product
    code: Mapped[str] = mapped_column(String(60))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    reasons: Mapped[list] = mapped_column(JSONType, default=list)
    company: Mapped[Company] = relationship(back_populates="categories")


class CompanyEvidence(Base):
    __tablename__ = "company_evidence"
    __table_args__ = (Index("ix_evidence_field_value", "field", "value"), Index("ix_evidence_job_company", "job_id", "company_id"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_jobs.id", ondelete="SET NULL"))
    evidence_type: Mapped[str] = mapped_column(String(40))  # discovery_listing|website_content|registry_record|vat_check|import_record|places_listing|map_feature|user_import|manual_note
    field: Mapped[str | None] = mapped_column(String(60))  # which attribute this proves (phone, buyer_type, …)
    value: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[Company] = relationship(back_populates="evidence")


class ImportSignal(Base):
    __tablename__ = "import_signals"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    signal_type: Mapped[str] = mapped_column(String(40))  # shipment_record|customs_registry|self_declared|trade_show|brand_origin_claim
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # True only for shipment/customs grade evidence
    hs_code: Mapped[str | None] = mapped_column(String(12))
    origin_country: Mapped[str | None] = mapped_column(String(2))
    shipment_count: Mapped[int | None] = mapped_column(Integer)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    company: Mapped[Company] = relationship(back_populates="import_signals")


class CompanyScore(Base):
    __tablename__ = "company_scores"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), index=True)
    buyer_fit: Mapped[float] = mapped_column(Float)
    data_confidence: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSONType, default=dict)
    explanation: Mapped[list] = mapped_column(JSONType, default=list)
    weights_version: Mapped[str] = mapped_column(String(30), default="v1-initial")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EntityMatchReview(Base):
    """Low-confidence duplicate candidates are never merged automatically; they land here."""
    __tablename__ = "entity_match_reviews"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    company_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    company_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSONType, default=list)
    suggested_relation: Mapped[str] = mapped_column(String(30), default="same_entity")  # same_entity|branch|group
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|merged|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrganizationLead(Base):
    """CRM state of a company for the tenant and which jobs surfaced it."""
    __tablename__ = "organization_leads"
    __table_args__ = (UniqueConstraint("org_id", "company_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_ids: Mapped[list] = mapped_column(JSONType, default=list)
    crm_status: Mapped[str] = mapped_column(String(30), default="new")  # new|qualified|contacted|in_discussion|customer|not_interested|do_not_contact
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONType, default=list)
    sales_outcome: Mapped[str | None] = mapped_column(String(30))  # for score calibration: won|lost|no_response
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ManualResearchItem(Base):
    """Queue for sources that cannot be automated (no API / licence pending / ToS forbids automation)."""
    __tablename__ = "manual_research_items"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_jobs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_tasks.id", ondelete="CASCADE"))
    source_key: Mapped[str] = mapped_column(String(80))
    instructions: Mapped[str] = mapped_column(Text)
    suggested_queries: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|done|dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
