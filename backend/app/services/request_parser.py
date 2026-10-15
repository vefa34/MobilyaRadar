"""Parse a free-text research request (Turkish or English) into structured job parameters.

Rule-based so it is deterministic and free; the UI shows the parsed result for confirmation.
"""
from __future__ import annotations

import re

from app.data.countries import find_countries_in_text
from app.data.terms import PRODUCT_TERMS
from app.services.product_catalog import TR_TERMS

BUYER_KEYWORDS = {
    "verified_importer": ["ithal", "ithalatçı", "importer", "import ", "importing"],
    "wholesaler": ["toptan", "toptancı", "wholesale", "wholesaler"],
    "distributor": ["distribütör", "distributor", "bayi", "dealer", "acente"],
    "retail_chain": ["perakende zinciri", "zincir mağaza", "retail chain", "chain store", "mağaza zinciri"],
    "independent_store": ["mağaza", "showroom", "store", "perakende", "retailer"],
    "ecommerce": ["e-ticaret", "online", "e-commerce", "internet satış"],
    "contract_ffe": ["otel", "restoran", "proje", "contract", "hospitality", "ff&e", "hotel"],
    "interior_procurement": ["iç mimar", "interior", "dekorasyon firması"],
    "brand_private_label": ["private label", "fason", "oem", "kendi markası"],
    "tender_buyer": ["ihale", "tender"],
}


def parse_request(text: str) -> dict:
    low = (text or "").lower()
    countries = find_countries_in_text(text or "")
    products: list[str] = []
    for cat, words in TR_TERMS.items():
        if any(re.search(r"(?<!\w)" + re.escape(w), low) for w in words if len(w) > 3):
            products.append(cat)
    for cat, langs in PRODUCT_TERMS.items():
        if cat in products or cat == "home_furniture":
            continue
        if any(t.lower() in low for t in langs.get("en", [])):
            products.append(cat)
    # "masa" alone is ambiguous; keep dining_table only when explicitly a dining/eating table or chairs context
    buyer_types: list[str] = []
    for bt, kws in BUYER_KEYWORDS.items():
        if any(k in low for k in kws):
            buyer_types.append(bt)
    if "retail_chain" in buyer_types and "independent_store" in buyer_types and "mağaza" not in low.replace("zincir", ""):
        buyer_types.remove("independent_store")
    return {"countries": countries, "product_categories": products or ["home_furniture"], "buyer_types": buyer_types}
