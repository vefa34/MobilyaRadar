"""Buyer Fit Score and Data Confidence Score (both 0-100, never collapsed into one number).

Buyer Fit  — how commercially suitable the company is for *this* exporter/product.
Data Confidence — how trustworthy our information about the company is.

Each component returns a value in [0,1] plus explanation strings, so the UI can show *why*.
Unknown facts score 0 for fit but are reported as "unknown" (not as negative facts).
Weights are configuration (``DEFAULT_WEIGHTS``) and are meant to be recalibrated from CRM
outcomes (organization_leads.sales_outcome) — see ``calibration_report``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.data.countries import get_country
from app.services.classifier import Classification

WEIGHTS_VERSION = "v1-initial"
DEFAULT_WEIGHTS = {
    "product_fit": 25, "buyer_role": 20, "import_evidence": 20, "commercial_scale": 15, "market_logistics": 10, "accessibility": 10,
}
ROLE_VALUE = {
    "verified_importer": 1.0, "distributor": 0.95, "wholesaler": 0.9, "retail_chain": 0.85, "contract_ffe": 0.85,
    "brand_private_label": 0.8, "ecommerce": 0.65, "interior_procurement": 0.6, "independent_store": 0.5, "tender_buyer": 0.5,
    "manufacturer": 0.25, "unclear": 0.15,
}
SOURCE_RELIABILITY_DEFAULT = 0.5


@dataclass
class ScoreInput:
    classification: Classification
    country: str | None
    target_products: list[str]
    target_buyer_types: list[str]
    website_product_match: float | None
    website_status: str | None
    store_count: int | None
    location_count: int
    employee_count: int | None
    has_general_email: bool
    has_phone: bool
    has_website: bool
    has_purchasing_contact: bool
    source_keys: list[str]
    source_reliability: dict[str, float]
    registry_verified: bool
    vat_verified: bool
    import_signals_verified: int
    import_signals_claimed: int
    corroborated_fields: int        # fields confirmed by ≥2 independent sources
    last_observed: datetime | None
    is_synthetic: bool
    exporter_country: str = "TR"


@dataclass
class ScoreResult:
    buyer_fit: float
    data_confidence: float
    components: dict[str, float] = field(default_factory=dict)
    confidence_components: dict[str, float] = field(default_factory=dict)
    explanation: list[dict] = field(default_factory=list)


def _component_product(si: ScoreInput, why: list) -> float:
    cats = set(si.classification.product_categories)
    targets = set(si.target_products) - {"home_furniture"}
    if not targets:
        v = 0.7 if si.classification.furniture_relevance >= 0.6 else 0.2
        why.append(("product_fit", f"general furniture relevance {si.classification.furniture_relevance:.1f}"))
        return v
    overlap = cats & targets
    v = 0.0
    if overlap:
        v = 0.6 + 0.4 * len(overlap) / len(targets)
        why.append(("product_fit", f"sells targeted products: {', '.join(sorted(overlap))}"))
    elif cats:
        v = 0.35
        why.append(("product_fit", f"furniture seller, other categories ({', '.join(sorted(cats)[:3])})"))
    elif si.classification.furniture_relevance >= 0.6:
        v = 0.3
        why.append(("product_fit", "furniture business; product range unknown"))
    else:
        why.append(("product_fit", "no product evidence (unknown)"))
    if si.website_product_match is not None:
        v = max(v, si.website_product_match)
        why.append(("product_fit", f"website product match {si.website_product_match:.0%}"))
    return min(1.0, v)


def _component_role(si: ScoreInput, why: list) -> float:
    types = si.classification.buyer_types
    best_t, best_v = "unclear", 0.0
    for t, conf in types.items():
        v = ROLE_VALUE.get(t, 0.2) * (0.5 + 0.5 * conf)
        if si.target_buyer_types and t in si.target_buyer_types:
            v = min(1.0, v + 0.1)
        if v > best_v:
            best_t, best_v = t, v
    if best_t == "manufacturer" and si.classification.oem_signal:
        best_v = max(best_v, 0.55)
        why.append(("buyer_role", "manufacturer with OEM/private-label sourcing signal"))
    if si.target_buyer_types and not (set(types) & set(si.target_buyer_types)):
        best_v *= 0.7
        why.append(("buyer_role", "role differs from requested buyer types"))
    why.append(("buyer_role", f"primary role: {best_t.replace('_', ' ')}"))
    return best_v


def _component_import(si: ScoreInput, why: list) -> float:
    if si.import_signals_verified:
        why.append(("import_evidence", f"{si.import_signals_verified} verified import record(s)"))
        return 1.0
    if si.import_signals_claimed:
        why.append(("import_evidence", "self-declared import activity (unverified)"))
        return 0.35
    if any(t in si.classification.buyer_types for t in ("wholesaler", "distributor")):
        why.append(("import_evidence", "wholesale/distribution role; no import record"))
        return 0.25
    why.append(("import_evidence", "no import evidence (unknown)"))
    return 0.0


def _component_scale(si: ScoreInput, why: list) -> float:
    v = 0.0
    if si.store_count:
        v = max(v, min(1.0, 0.3 + si.store_count / 20))
        why.append(("commercial_scale", f"{si.store_count} stores"))
    if si.location_count >= 2:
        v = max(v, min(0.8, 0.2 + si.location_count / 10))
        why.append(("commercial_scale", f"{si.location_count} known locations"))
    if si.employee_count:
        v = max(v, min(1.0, si.employee_count / 200))
        why.append(("commercial_scale", f"~{si.employee_count} employees"))
    if len(si.source_keys) >= 3:
        v = max(v, 0.4)
        why.append(("commercial_scale", f"present in {len(si.source_keys)} sources"))
    if v == 0.0:
        why.append(("commercial_scale", "scale unknown"))
    return v


def _component_market(si: ScoreInput, why: list) -> float:
    cfg = get_country(si.country or "")
    if not cfg:
        why.append(("market_logistics", "country not configured"))
        return 0.3
    regime_bonus = {"customs_union": 0.2, "fta": 0.15, "mfn": 0.0}.get(cfg.trade_regime, 0.0)
    v = min(1.0, 0.8 * cfg.logistics + regime_bonus)
    why.append(("market_logistics", f"logistics {cfg.logistics:.2f} from {si.exporter_country}; trade regime {cfg.trade_regime}"))
    return v


def _component_access(si: ScoreInput, why: list) -> float:
    v = 0.0
    parts = []
    if si.has_website and si.website_status in (None, "ok"):
        v += 0.3; parts.append("website")
    if si.has_general_email:
        v += 0.3; parts.append("business email")
    if si.has_phone:
        v += 0.2; parts.append("phone")
    if si.has_purchasing_contact:
        v += 0.2; parts.append("purchasing contact")
    why.append(("accessibility", "reachable via " + ", ".join(parts) if parts else "no contact channel found"))
    return min(1.0, v)


def compute_scores(si: ScoreInput, weights: dict[str, int] | None = None) -> ScoreResult:
    w = weights or DEFAULT_WEIGHTS
    why: list[tuple[str, str]] = []
    comp = {
        "product_fit": _component_product(si, why), "buyer_role": _component_role(si, why),
        "import_evidence": _component_import(si, why), "commercial_scale": _component_scale(si, why),
        "market_logistics": _component_market(si, why), "accessibility": _component_access(si, why),
    }
    total_w = sum(w.values())
    fit = sum(comp[k] * w[k] for k in comp) / total_w * 100
    if si.classification.reject_reason:
        fit = min(fit, 15.0)
        why.append(("buyer_role", f"rejected: {si.classification.reject_reason}"))

    # ---- Data confidence
    rel = [si.source_reliability.get(k, SOURCE_RELIABILITY_DEFAULT) for k in si.source_keys] or [0.0]
    conf = {
        "source_quality": max(rel),
        "source_diversity": min(1.0, len(si.source_keys) / 3),
        "official_verification": 1.0 if (si.registry_verified or si.vat_verified) else 0.0,
        "website_verified": 1.0 if si.website_status == "ok" else (0.0 if si.website_status in ("unreachable", "not_found") else 0.3),
        "corroboration": min(1.0, si.corroborated_fields / 3),
        "recency": _recency(si.last_observed),
    }
    cw = {"source_quality": 20, "source_diversity": 20, "official_verification": 20, "website_verified": 15, "corroboration": 15, "recency": 10}
    dc = sum(conf[k] * cw[k] for k in conf) / sum(cw.values()) * 100
    if si.is_synthetic:
        dc = 0.0
        why.append(("data_confidence", "SYNTHETIC demo record — not a real company"))
    explanation = [{"component": c, "text": t} for c, t in why]
    return ScoreResult(round(fit, 1), round(dc, 1), {k: round(v, 3) for k, v in comp.items()},
                       {k: round(v, 3) for k, v in conf.items()}, explanation)


def _recency(dt: datetime | None) -> float:
    if not dt:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    days = (datetime.now(UTC) - dt).days
    return 1.0 if days <= 30 else 0.7 if days <= 180 else 0.4 if days <= 365 else 0.1


def priority_label(fit: float, conf: float) -> str:
    if fit >= 75 and conf >= 60:
        return "high_priority"
    if fit >= 75:
        return "promising_needs_verification"
    if fit < 35 and conf >= 60:
        return "real_but_not_target"
    if fit >= 50:
        return "medium"
    return "low"


def calibration_report(rows: list[tuple[dict, str]]) -> dict:
    """rows: (components, outcome) from CRM. Returns mean component value per outcome — a first step
    toward fitting weights once enough won/lost outcomes exist (≥50 recommended)."""
    agg: dict[str, dict[str, list[float]]] = {}
    for comps, outcome in rows:
        for k, v in comps.items():
            agg.setdefault(outcome, {}).setdefault(k, []).append(v)
    return {o: {k: round(sum(v) / len(v), 3) for k, v in comps.items()} | {"n": len(next(iter(comps.values()), []))}
            for o, comps in agg.items()}
