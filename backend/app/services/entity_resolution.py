"""Entity resolution: turn raw source records into unique companies.

Matching order (deterministic first, fuzzy last):
  1. same source record id (place_id, OSM id, registry number from the same source)
  2. registration number / VAT number (same country)
  3. non-generic website domain
  4. normalised phone number
  5. distinctive "core" name in the same city / country, then fuzzy name similarity

Confidence ≥ AUTO_MERGE → merged (a different city becomes a branch location of the same company).
REVIEW ≤ confidence < AUTO_MERGE → kept separate and queued in entity_match_reviews (never auto-merged).
Conflicting registration numbers or conflicting domains veto merges.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.connectors.base import RawCompany
from app.models import (
    Company,
    CompanyAlias,
    CompanyContact,
    CompanyEvidence,
    CompanyLocation,
    EntityMatchReview,
    SourceRegistry,
)
from app.services.normalization import (
    core_name,
    detect_script,
    email_department,
    email_is_generic,
    is_generic_domain,
    normalize_domain,
    normalize_name,
    normalize_phone,
    normalize_url,
    transliterate,
)

AUTO_MERGE = 0.85
REVIEW = 0.65


@dataclass
class SourcePolicy:
    key: str
    storage_allowed: bool = True
    max_retention_days: int | None = None
    export_allowed: bool = True
    merge_allowed: bool = True
    reliability: float = 0.5

    @classmethod
    def from_registry(cls, s: SourceRegistry | None, key: str) -> "SourcePolicy":
        if not s:
            return cls(key)
        return cls(key, s.storage_allowed, s.max_retention_days, s.export_allowed, s.merge_allowed, s.reliability)

    def retention_until(self) -> datetime | None:
        return datetime.now(UTC) + timedelta(days=self.max_retention_days) if self.max_retention_days else None


@dataclass
class MatchResult:
    company: Company
    created: bool
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    review_queued: bool = False


@dataclass
class _Norm:
    name: str
    core: str
    domain: str | None
    phone: str | None
    reg: str | None
    vat: str | None
    record_key: str | None


def _norm(raw: RawCompany) -> _Norm:
    domain = normalize_domain(raw.website)
    if domain and is_generic_domain(domain):
        domain = None
    reg = (raw.registration_number or "").strip().upper().replace(" ", "") or None
    vat = (raw.vat_number or "").strip().upper().replace(" ", "").replace(".", "") or None
    return _Norm(
        name=normalize_name(raw.name), core=core_name(raw.name, raw.city), domain=domain,
        phone=normalize_phone(raw.phone, raw.country), reg=reg, vat=vat,
        record_key=f"{raw.source_key}:{raw.source_record_id}" if raw.source_record_id else None,
    )


def score_pair(n: _Norm, raw: RawCompany, c: Company) -> tuple[float, list[str], str]:
    """Return (confidence, reasons, relation) for raw vs existing company."""
    reasons: list[str] = []
    score = 0.0
    relation = "same_entity"
    same_country = (raw.country or c.country) is None or raw.country == c.country
    if not same_country:
        return 0.0, ["different country"], relation
    if n.reg and c.registration_number:
        if n.reg == c.registration_number.upper().replace(" ", ""):
            return 1.0, ["registration number match"], relation
        return 0.0, ["conflicting registration numbers"], relation
    if n.vat and c.vat_number and n.vat == c.vat_number.upper().replace(" ", ""):
        return 1.0, ["VAT number match"], relation
    penalty = 0.0
    if n.domain and c.domain:
        if n.domain == c.domain:
            score = max(score, 0.95); reasons.append("same website domain")
        else:
            penalty += 0.3; reasons.append("different website domains")
    if n.phone and c.phone:
        if n.phone == c.phone:
            score = max(score, 0.9); reasons.append("same phone number")
        else:
            penalty += 0.1
    same_city = bool(raw.city and c.city and normalize_name(raw.city) == normalize_name(c.city))
    if n.core and c.core_name and n.core == c.core_name and len(n.core) >= 3:
        if same_city:
            score = max(score, 0.9); reasons.append("same distinctive name, same city")
        else:
            score = max(score, 0.75); reasons.append("same distinctive name, different city (branch or group?)")
            relation = "branch"
    elif n.core and c.core_name:
        # fuzzy on the *distinctive* part only — generic words ("Furniture Trading") must not create matches
        ratio = fuzz.token_sort_ratio(n.core, c.core_name) / 100  # not token_set: "garnet" ⊂ "garnet tundra" must not score 100
        if same_city and ratio >= 0.92:
            score = max(score, 0.86); reasons.append(f"distinctive-name similarity {ratio:.2f}, same city")
        elif same_city and ratio >= 0.85:
            score = max(score, 0.7); reasons.append(f"distinctive-name similarity {ratio:.2f}, same city")
    if score < 0.95:  # strong identifiers are not outweighed by secondary differences
        score -= penalty
    return max(0.0, min(1.0, score)), reasons, relation


def _candidates(db: Session, org_id, n: _Norm, raw: RawCompany) -> list[Company]:
    conds = []
    if n.domain:
        conds.append(Company.domain == n.domain)
    if n.phone:
        conds.append(Company.phone == n.phone)
    if n.reg:
        conds.append(Company.registration_number == n.reg)
    if n.vat:
        conds.append(Company.vat_number == n.vat)
    if n.core:
        conds.append(Company.core_name == n.core)
    if n.name:
        conds.append(Company.normalized_name == n.name)
    found: dict = {}
    if conds:
        q = select(Company).where(Company.org_id == org_id, or_(*conds))
        if raw.country:
            q = q.where(or_(Company.country == raw.country, Company.country.is_(None)))
        for c in db.scalars(q.limit(50)):
            found[c.id] = c
    # alias table (other scripts / trade names)
    if n.name:
        for c in db.scalars(select(Company).join(CompanyAlias).where(Company.org_id == org_id, CompanyAlias.normalized == n.name).limit(10)):
            found[c.id] = c
    # same source record seen before
    if n.record_key:
        for c in db.scalars(select(Company).join(CompanyEvidence).where(
                Company.org_id == org_id, CompanyEvidence.field == "source_record_id", CompanyEvidence.value == n.record_key).limit(5)):
            found[c.id] = c
    # fuzzy fallback within same city (bounded)
    if not found and raw.city and n.name:
        first = n.core.split(" ")[0] if n.core else n.name.split(" ")[0]
        if len(first) >= 3:
            for c in db.scalars(select(Company).where(Company.org_id == org_id, Company.country == raw.country,
                                                      Company.normalized_name.contains(first)).limit(30)):
                found[c.id] = c
    return list(found.values())


def resolve_record(db: Session, org_id, raw: RawCompany, policy: SourcePolicy, job_id=None) -> MatchResult | None:
    """Insert or merge one raw record. Returns None if the record is unusable."""
    if not raw.name or len(raw.name.strip()) < 2:
        return None
    if not policy.storage_allowed:
        return None
    n = _norm(raw)
    best: tuple[float, list[str], str, Company] | None = None
    for c in _candidates(db, org_id, n, raw):
        s, reasons, rel = score_pair(n, raw, c)
        if n.record_key and s < 1.0:
            ev = db.scalar(select(CompanyEvidence.id).where(CompanyEvidence.company_id == c.id, CompanyEvidence.field == "source_record_id",
                                                             CompanyEvidence.value == n.record_key))
            if ev:
                s, reasons = 1.0, ["same source record"]
        if best is None or s > best[0]:
            best = (s, reasons, rel, c)

    if best and best[0] >= AUTO_MERGE:
        company = best[3]
        merge_into(db, company, raw, n, policy, job_id, branch=(best[2] == "branch"))
        return MatchResult(company, False, best[0], best[1])

    company = _create(db, org_id, raw, n, policy, job_id)
    review = False
    if best and best[0] >= REVIEW:
        db.add(EntityMatchReview(org_id=org_id, company_a_id=best[3].id, company_b_id=company.id, score=round(best[0], 3),
                                 reasons=best[1], suggested_relation=best[2]))
        review = True
    return MatchResult(company, True, best[0] if best else 0.0, best[1] if best else [], review)


def _create(db: Session, org_id, raw: RawCompany, n: _Norm, policy: SourcePolicy, job_id) -> Company:
    script = detect_script(raw.name)
    c = Company(
        org_id=org_id, display_name=raw.name.strip()[:300], trade_name=raw.name.strip()[:300],
        name_original_script=raw.name if script != "latin" else None,
        name_transliterated=transliterate(raw.name)[:300] if script != "latin" else None,
        normalized_name=n.name[:300], core_name=n.core[:300], country=raw.country, is_synthetic=raw.is_synthetic,
        first_seen_job_id=job_id, sources=[], buyer_types=[], product_categories=[],
    )
    db.add(c)
    db.flush()
    merge_into(db, c, raw, n, policy, job_id, branch=False, is_new=True)
    return c


def merge_into(db: Session, c: Company, raw: RawCompany, n: _Norm, policy: SourcePolicy, job_id, *, branch: bool, is_new: bool = False) -> None:
    now = datetime.now(UTC)
    until = policy.retention_until()

    seen = set() if is_new else set(db.execute(select(CompanyEvidence.field, CompanyEvidence.value).where(
        CompanyEvidence.company_id == c.id, CompanyEvidence.source_key == raw.source_key)).all())

    def ev(field_name, value, etype=None, conf=None, snippet=None):
        if value in (None, ""):
            return
        if (field_name, str(value)[:1000]) in seen:
            return  # same fact from the same source already recorded
        seen.add((field_name, str(value)[:1000]))
        db.add(CompanyEvidence(company_id=c.id, job_id=job_id, evidence_type=etype or raw.evidence_type, field=field_name,
                               value=str(value)[:1000], snippet=snippet, source_key=raw.source_key, source_url=raw.source_url,
                               observed_at=now, confidence=conf if conf is not None else raw.confidence,
                               is_synthetic=raw.is_synthetic, retention_until=until))

    ev("name", raw.name, snippet=raw.description[:500] if raw.description else None)
    ev("source_record_id", n.record_key)
    if raw.categories:
        ev("source_categories", ", ".join(raw.categories)[:1000])
    # Fill blanks only; registry records may set the legal name.
    if raw.evidence_type == "registry_record" and raw.name:
        c.legal_name = raw.name[:300]
    if n.domain and not c.domain:
        c.domain = n.domain
        c.website = normalize_url(raw.website)
        ev("website", c.website)
    if n.phone and not c.phone:
        c.phone = n.phone
        ev("phone", n.phone)
    if raw.city and not c.city:
        c.city = raw.city
        ev("city", raw.city)
    if raw.address and not c.address:
        c.address = raw.address
        c.postal_code = c.postal_code or raw.postal_code
        ev("address", raw.address)
    if n.reg and not c.registration_number:
        c.registration_number = n.reg
        ev("registration_number", n.reg)
    if n.vat and not c.vat_number:
        c.vat_number = n.vat
        ev("vat_number", n.vat)
    if raw.email:
        email = raw.email.lower()
        if not c.general_email and email_is_generic(email):
            c.general_email = email
            ev("email", email)
        _add_contact(db, c, "email", email, raw, until, is_generic=email_is_generic(email), department=email_department(email))
    if n.phone:
        _add_contact(db, c, "phone", n.phone, raw, until)

    # Aliases: different spellings / scripts of the same entity are kept, never double-counted.
    existing_aliases = set(db.scalars(select(CompanyAlias.normalized).where(CompanyAlias.company_id == c.id))) if not is_new else set()
    for alias in [raw.name, *raw.alt_names]:
        an = normalize_name(alias)
        if an and an not in existing_aliases and (an != c.normalized_name or is_new):
            db.add(CompanyAlias(company_id=c.id, alias=alias[:300], normalized=an[:300], script=detect_script(alias),
                                alias_type="branch" if branch and alias == raw.name else ("transliteration" if detect_script(alias) != "latin" else "trade_name"),
                                source_key=raw.source_key))
            existing_aliases.add(an)

    # Location (stores/branches) — distinct addresses/cities become separate locations.
    if raw.address or raw.city or raw.latitude:
        key_addr = normalize_name(raw.address or "") or normalize_name(raw.city or "")
        dup = False
        if not is_new:
            for loc in db.scalars(select(CompanyLocation).where(CompanyLocation.company_id == c.id)):
                if (normalize_name(loc.address or "") or normalize_name(loc.city or "")) == key_addr:
                    dup = True
                    if raw.external_ids:
                        loc.external_ids = {**(loc.external_ids or {}), **raw.external_ids}
                    break
        if not dup:
            ltype = "branch" if branch else raw.location_type
            db.add(CompanyLocation(company_id=c.id, location_type=ltype, name=raw.name[:300], address=raw.address, city=raw.city,
                                   country=raw.country, postal_code=raw.postal_code, latitude=raw.latitude, longitude=raw.longitude,
                                   phone=n.phone, external_ids=raw.external_ids or {}, source_key=raw.source_key,
                                   source_url=raw.source_url, observed_at=now, retention_until=until))

    srcs = set(c.sources or [])
    srcs.add(raw.source_key)
    c.sources = sorted(srcs)
    c.source_count = len(srcs)
    if not raw.is_synthetic and c.is_synthetic:
        c.is_synthetic = False  # a real source confirmed it
    db.flush()


def _add_contact(db: Session, c: Company, ctype: str, value: str, raw: RawCompany, until, is_generic=True, department="general"):
    exists = db.scalar(select(CompanyContact.id).where(CompanyContact.company_id == c.id, CompanyContact.contact_type == ctype,
                                                       CompanyContact.value == value))
    if exists:
        return
    db.add(CompanyContact(company_id=c.id, contact_type=ctype, value=value, is_generic=is_generic, department=department,
                          legal_basis="published_business_contact", source_key=raw.source_key, source_url=raw.source_url,
                          retention_until=until))


def merge_companies(db: Session, keep: Company, drop: Company, relation: str = "same_entity") -> None:
    """Manual merge from the review queue. ``relation='group'`` links instead of merging."""
    if relation == "group":
        drop.parent_company_id = keep.id
        return
    for rel in ("aliases", "locations", "contacts", "categories", "evidence", "import_signals"):
        for item in list(getattr(drop, rel)):
            item.company_id = keep.id
    keep.aliases.append(CompanyAlias(company_id=keep.id, alias=drop.display_name, normalized=drop.normalized_name,
                                     script=detect_script(drop.display_name), alias_type="trade_name", source_key="manual_merge"))
    for f in ("website", "domain", "phone", "general_email", "address", "city", "registration_number", "vat_number", "legal_name"):
        if not getattr(keep, f) and getattr(drop, f):
            setattr(keep, f, getattr(drop, f))
    keep.sources = sorted(set(keep.sources or []) | set(drop.sources or []))
    keep.source_count = len(keep.sources)
    db.flush()
    db.delete(drop)
