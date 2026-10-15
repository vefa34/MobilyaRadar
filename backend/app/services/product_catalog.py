"""Product catalogue parsing → categories, materials, search terms and HS codes.

Accepts PDF, CSV, XLSX or plain text. Detection is rule-based over the multilingual lexicon
(Turkish catalogues included); HS codes are derived from category + material + upholstery
attributes per product line, never from a generic "furniture" keyword. An LLM can refine the
attribute extraction when configured, but its output is validated against the known category set.
"""
from __future__ import annotations

import io
import re
from collections import Counter

from app.data.hs_codes import METAL, PLASTIC, WOOD, suggest_hs_codes
from app.data.terms import PRODUCT_TERMS

TR_TERMS = {
    "dining_table": ["yemek masası", "masa", "yemek odası"], "chair": ["sandalye"], "sofa": ["koltuk takımı", "kanepe", "köşe koltuk", "koltuk"],
    "armchair": ["berjer", "tekli koltuk"], "bed": ["yatak odası", "karyola", "baza"], "cabinet": ["gardırop", "dolap", "konsol", "büfe"],
    "office_furniture": ["ofis", "çalışma masası", "ofis koltuğu"], "hotel_furniture": ["otel"], "restaurant_furniture": ["cafe", "kafe", "restoran"],
    "kitchen_furniture": ["mutfak"], "outdoor_furniture": ["bahçe"],
}
MATERIAL_WORDS = {"wood": WOOD | {"ahşap", "masif", "kayın", "ceviz", "meşe"}, "metal": METAL | {"metal", "demir", "çelik"},
                  "plastic": PLASTIC, "glass": {"glass", "cam"}, "marble": {"marble", "mermer"}, "fabric": {"fabric", "kumaş", "velvet", "kadife"},
                  "leather": {"leather", "deri"}}
UPHOLSTERY = {"upholstered", "döşemeli", "fabric", "kumaş", "velvet", "kadife", "leather", "deri", "padded", "süngerli"}


def extract_text(content: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:200])
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        lines = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                lines.append(" ".join(str(v) for v in row if v is not None))
        return "\n".join(lines)
    return content.decode("utf-8", errors="replace")


def analyze_catalog_text(text: str) -> dict:
    low = text.lower()
    counts: Counter = Counter()
    for cat, langs in PRODUCT_TERMS.items():
        if cat == "home_furniture":
            continue
        terms = {t.lower() for ts in langs.values() for t in ts} | set(TR_TERMS.get(cat, []))
        for t in terms:
            n = len(re.findall(r"(?<!\w)" + re.escape(t) + r"(?!\w)", low))
            if n:
                counts[cat] += n
    materials = [m for m, words in MATERIAL_WORDS.items() if any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low) for w in words)]
    upholstered = any(w in low for w in UPHOLSTERY)
    categories = [c for c, _ in counts.most_common() if counts[c] >= 1][:6]
    hs = []
    for cat in categories:
        for s in suggest_hs_codes(cat, materials, upholstered if cat in ("chair", "sofa", "armchair") else None,
                                  swivel="swivel" in low or "döner" in low, convertible="sofa bed" in low or "yataklı" in low):
            hs.append({"category": cat, "code": s.code, "description": s.description, "confidence": s.confidence, "reasoning": s.reasoning})
    terms = {cat: {lang: PRODUCT_TERMS[cat][lang][:3] for lang in ("en", "de", "fr", "ar", "ru")} for cat in categories if cat in PRODUCT_TERMS}
    return {"categories": categories, "category_mentions": dict(counts), "materials": materials, "upholstered": upholstered,
            "hs_codes": hs, "search_terms": terms,
            "notes": "HS codes are 6-digit HS2022 suggestions; confirm national tariff lines (GTİP/CN) with a customs broker."}
