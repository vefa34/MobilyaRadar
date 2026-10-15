"""Rule-based, evidence-producing buyer classification.

Input is everything we know about a company (name, source categories, listing descriptions,
website text, import signals, store counts). Output is a set of buyer types with confidence and
human-readable reasons. Multiple types are allowed. 'verified_importer' requires a *verified*
import signal (shipment/customs-grade evidence) — website claims only produce 'claimed'.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.data.terms import CLASSIFIER_SIGNALS, FURNITURE_WORD, PRODUCT_TERMS

SOURCE_CATEGORY_MAP = {
    # OSM
    "shop=furniture": ("independent_store", 0.7), "shop=bed": ("independent_store", 0.6), "shop=kitchen": ("independent_store", 0.5),
    "shop=interior_decoration": ("independent_store", 0.4), "shop=wholesale": ("wholesaler", 0.6), "wholesale=furniture": ("wholesaler", 0.8),
    "trade=furniture": ("wholesaler", 0.6), "has_brand": ("retail_chain", 0.5),
    # Google Places types
    "furniture_store": ("independent_store", 0.7), "home_goods_store": ("independent_store", 0.4), "wholesaler": ("wholesaler", 0.7),
    "interior_designer": ("interior_procurement", 0.6),
    # Registries (SIC / NACE)
    "sic:46470": ("wholesaler", 0.85), "sic:47591": ("independent_store", 0.7), "sic:47910": ("ecommerce", 0.4),
    "nace:4647": ("wholesaler", 0.85), "nace:4759": ("independent_store", 0.7), "nace:46470": ("wholesaler", 0.85),
    # Synthetic connector profile labels
    "importer": ("distributor", 0.4), "distributor": ("distributor", 0.6), "retail_chain": ("retail_chain", 0.6),
    "independent_store": ("independent_store", 0.6), "ecommerce": ("ecommerce", 0.6), "contract_ffe": ("contract_ffe", 0.6),
    "interior_procurement": ("interior_procurement", 0.6), "manufacturer": ("manufacturer", 0.6),
}
FURNITURE_SOURCE_CATS = {"shop=furniture", "shop=bed", "furniture_store", "wholesale=furniture", "trade=furniture", "sic:46470",
                         "sic:47591", "nace:4647", "nace:4759"}

ALL_PRODUCT_TERMS = {cat: sorted({t.lower() for terms in langs.values() for t in terms}) for cat, langs in PRODUCT_TERMS.items()
                     if cat != "home_furniture"}
ALL_FURNITURE_WORDS = sorted({w.lower() for ws in FURNITURE_WORD.values() for w in ws})
EXTRA_FURNITURE_HINTS = ["furnish", "möbel", "moebel", "meubl", "mobil", "mebel", "мебел", "أثاث", "اثاث", "مفروشات", "ავეჯ", "կահույք",
                         "nábyt", "namešt", "nameštaj", "έπιπλ", "sofa", "canap", "divan", "chair", "stuhl", "chaise", "table", "tisch"]


@dataclass
class Classification:
    buyer_types: dict[str, float] = field(default_factory=dict)       # type -> confidence
    reasons: dict[str, list[str]] = field(default_factory=dict)
    product_categories: list[str] = field(default_factory=list)
    furniture_relevance: float = 0.0
    import_status: str = "unknown"   # unknown|claimed|indicated|verified
    oem_signal: bool = False
    reject_reason: str | None = None

    @property
    def primary(self) -> str:
        if not self.buyer_types:
            return "unclear"
        order = ["verified_importer", "distributor", "wholesaler", "retail_chain", "contract_ffe", "brand_private_label",
                 "ecommerce", "interior_procurement", "independent_store", "tender_buyer", "manufacturer", "unclear"]
        best = max(self.buyer_types.items(), key=lambda kv: (kv[1], -order.index(kv[0]) if kv[0] in order else -99))
        return best[0]

    def add(self, t: str, conf: float, reason: str) -> None:
        self.buyer_types[t] = max(self.buyer_types.get(t, 0.0), conf)
        self.reasons.setdefault(t, []).append(reason)


def classify(*, name: str, source_categories: list[str], descriptions: list[str], website_text: str = "",
             verified_import: bool = False, claimed_import: bool = False, store_count: int | None = None,
             location_count: int = 1, source_keys: list[str] | None = None) -> Classification:
    cl = Classification()
    cats = [c.lower() for c in source_categories]
    text = " ".join([name or "", " ".join(descriptions), " ".join(cats), website_text or ""]).lower()

    # --- furniture relevance
    rel = 0.0
    if any(c in FURNITURE_SOURCE_CATS for c in cats):
        rel = max(rel, 0.8)
    if any(w in text for w in ALL_FURNITURE_WORDS) or any(h in text for h in EXTRA_FURNITURE_HINTS):
        rel = max(rel, 0.6)
    for cat, terms in ALL_PRODUCT_TERMS.items():
        if any(t in text for t in terms):
            cl.product_categories.append(cat)
    if cl.product_categories:
        rel = max(rel, 0.75)
    if website_text and cl.product_categories:
        rel = max(rel, 0.9)
    cl.furniture_relevance = rel

    # --- reject obvious non-buyers
    if any(k in text for k in CLASSIFIER_SIGNALS["used"]) and not any(k in text for k in CLASSIFIER_SIGNALS["wholesaler"]):
        cl.reject_reason = "second-hand / antique furniture business"
    if rel == 0.0:
        cl.reject_reason = cl.reject_reason or "no furniture relevance found"

    # --- source category mapping
    for c in cats:
        if c in SOURCE_CATEGORY_MAP:
            t, conf = SOURCE_CATEGORY_MAP[c]
            cl.add(t, conf, f"source category '{c}'")

    def has(sig: str) -> str | None:
        return next((k for k in CLASSIFIER_SIGNALS[sig] if k in text), None)

    if (k := has("wholesaler")):
        cl.add("wholesaler", 0.7, f"text mentions '{k.strip()}'")
    if (k := has("distributor")):
        cl.add("distributor", 0.65, f"text mentions '{k.strip()}'")
    if (k := has("ecommerce")):
        cl.add("ecommerce", 0.65, f"text mentions '{k.strip()}'")
    if (k := has("contract")):
        cl.add("contract_ffe", 0.65, f"text mentions '{k.strip()}'")
    if (k := has("interior")):
        cl.add("interior_procurement", 0.55, f"text mentions '{k.strip()}'")
    if (k := has("tender")) or "ted_europa" in (source_keys or []):
        cl.add("tender_buyer", 0.6, f"tender signal '{k or 'TED'}'")
    if (k := has("manufacturer")):
        cl.add("manufacturer", 0.6, f"text mentions '{k.strip()}'")
    chain_kw = has("chain")
    if (store_count and store_count >= 3) or chain_kw or location_count >= 3:
        why = f"{store_count} stores" if store_count and store_count >= 3 else (f"{location_count} locations" if location_count >= 3 else f"text mentions '{chain_kw}'")
        cl.add("retail_chain", 0.75 if (store_count or 0) >= 3 or location_count >= 3 else 0.55, why)
    if (k := has("retail")) and "retail_chain" not in cl.buyer_types:
        cl.add("independent_store", 0.55, f"text mentions '{k.strip()}'")
    oem = has("oem")
    brand = has("brand")
    if oem or brand:
        cl.oem_signal = bool(oem)
        if any(t in cl.buyer_types for t in ("retail_chain", "ecommerce", "independent_store", "contract_ffe", "manufacturer")):
            cl.add("brand_private_label", 0.6 if oem else 0.45, f"own-brand / sourcing signal '{oem or brand}'")

    # --- import status
    imp_kw = has("importer")
    if verified_import:
        cl.import_status = "verified"
        cl.add("verified_importer", 0.95, "verified import/shipment record")
    elif claimed_import or imp_kw:
        cl.import_status = "claimed"
        # A claim strengthens wholesale/distribution roles but is NOT verification.
        for t in ("wholesaler", "distributor"):
            if t in cl.buyer_types:
                cl.buyer_types[t] = min(0.9, cl.buyer_types[t] + 0.1)
                cl.reasons[t].append(f"claims import activity ('{imp_kw or 'import'}') — unverified")
        if not any(t in cl.buyer_types for t in ("wholesaler", "distributor", "retail_chain")):
            cl.add("distributor", 0.45, f"claims import activity ('{imp_kw or 'import'}') — unverified")

    if not cl.buyer_types:
        cl.add("unclear", 0.3, "no role signals found")
    return cl
