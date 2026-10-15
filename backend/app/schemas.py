from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.data.countries import COUNTRIES
from app.data.terms import PRODUCT_TERMS

BUYER_TYPE_CODES = ["verified_importer", "wholesaler", "distributor", "retail_chain", "independent_store", "ecommerce", "contract_ffe",
                    "brand_private_label", "interior_procurement", "tender_buyer", "manufacturer", "unclear"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    org_id: uuid.UUID


class InviteIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(viewer|analyst|admin)$")
    full_name: str | None = None


# ---------------------------------------------------------------- research
class ProductConfig(BaseModel):
    categories: list[str] = Field(default_factory=lambda: ["home_furniture"])
    price_segment: str | None = Field(default=None, pattern="^(economy|mid|upper|luxury)$")
    design_segment: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    supply_models: list[str] = Field(default_factory=list)  # oem|odm|private_label|own_brand|project
    moq: str | None = None
    capacity: str | None = None
    hs_codes: list[str] = Field(default_factory=list)
    catalog_analysis: dict | None = None

    @field_validator("categories")
    @classmethod
    def known_categories(cls, v):
        bad = [c for c in v if c not in PRODUCT_TERMS]
        if bad:
            raise ValueError(f"unknown product categories: {bad}")
        return v or ["home_furniture"]


class JobCreate(BaseModel):
    name: str | None = None
    request_text: str | None = None
    countries: list[str] = Field(default_factory=list)
    buyer_types: list[str] = Field(default_factory=list)
    product: ProductConfig = Field(default_factory=ProductConfig)
    target_company_count: int = Field(default=200, ge=1, le=20000)
    min_buyer_fit: int = Field(default=50, ge=0, le=100)
    budget_usd: float = Field(default=10.0, ge=0, le=100000)
    use_paid_sources: bool = False
    selected_sources: list[str] = Field(default_factory=list)
    start: bool = True

    @field_validator("countries")
    @classmethod
    def known_countries(cls, v):
        v = [c.upper() for c in v]
        bad = [c for c in v if c not in COUNTRIES]
        if bad:
            raise ValueError(f"unsupported countries: {bad}")
        return v

    @field_validator("buyer_types")
    @classmethod
    def known_types(cls, v):
        bad = [b for b in v if b not in BUYER_TYPE_CODES]
        if bad:
            raise ValueError(f"unknown buyer types: {bad}")
        return v


class JobOut(ORM):
    id: uuid.UUID
    name: str
    request_text: str | None
    countries: list
    buyer_types: list
    product_config: dict
    target_company_count: int
    min_buyer_fit: int
    budget_usd: float
    spent_usd: float
    use_paid_sources: bool
    status: str
    stop_reason: str | None
    error: str | None
    progress: dict
    plan_summary: dict
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskOut(ORM):
    id: uuid.UUID
    country: str
    city: str | None
    buyer_type: str
    product_category: str
    language: str
    source_key: str
    priority: float
    status: str
    status_reason: str | None
    attempts: int
    queries_run: int
    raw_results: int
    new_unique: int
    cost_usd: float


# ---------------------------------------------------------------- companies
class CompanyListItem(ORM):
    id: uuid.UUID
    display_name: str
    name_original_script: str | None
    name_transliterated: str | None
    country: str | None
    city: str | None
    website: str | None
    general_email: str | None
    phone: str | None
    primary_buyer_type: str
    buyer_types: list
    product_categories: list
    import_activity_status: str
    store_count: int | None
    buyer_fit_score: float | None
    data_confidence_score: float | None
    source_count: int
    sources: list
    research_status: str
    is_synthetic: bool
    last_verified_at: datetime | None
    crm_status: str | None = None
    priority: str | None = None


class CompanyPage(BaseModel):
    total: int
    items: list[CompanyListItem]


class LeadUpdate(BaseModel):
    crm_status: str | None = Field(default=None, pattern="^(new|qualified|contacted|in_discussion|customer|not_interested|do_not_contact)$")
    notes: str | None = None
    tags: list[str] | None = None
    sales_outcome: str | None = Field(default=None, pattern="^(won|lost|no_response)$")


class SourceCredentialsIn(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    endpoint: str | None = None
    license_confirmed: bool | None = None
    license_reference: str | None = None
    monthly_budget_usd: float | None = None


class SourceIn(BaseModel):
    key: str = Field(pattern="^[a-z0-9_]{3,80}$")
    name: str
    url: str | None = None
    tier: str = Field(pattern="^P[0-3]$")
    purposes: list[str]
    countries: list[str]
    access_model: str
    terms_summary: str | None = None
    notes: str | None = None


class SourceReview(BaseModel):
    review_status: str = Field(pattern="^(approved|rejected|pending_review)$")
    access_model: str | None = None
    terms_summary: str | None = None
    notes: str | None = None


TokenOut.model_rebuild()
