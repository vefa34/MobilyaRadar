"""Local-language query generation.

Builds search phrases from curated trade terminology (data.terms) for a plan cell
(country × city × buyer type × product × language), adds contextual negative filters, and
de-duplicates against queries already executed in the job (normalised token sets).
An optional LLM step proposes *additional* market-specific terms; they are validated (must be in
the requested language's script, short, no company names) and stored as suggestions.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.data.terms import BUYER_TERMS, FURNITURE_WORD, NEGATIVE_TERMS, PRODUCT_TERMS
from app.services.llm import LLMClient, LLMUnavailable
from app.services.normalization import detect_script, normalize_query

SCRIPT_BY_LANG = {"ar": "arabic", "ku": "arabic", "ru": "cyrillic", "bg": "cyrillic", "ka": "georgian", "hy": "armenian", "el": "greek"}


def product_terms(category: str, lang: str, extra: dict | None = None) -> list[str]:
    terms = list(PRODUCT_TERMS.get(category, {}).get(lang) or [])
    if extra:
        terms += [t for t in extra.get(category, {}).get(lang, []) if t not in terms]
    return terms or list(PRODUCT_TERMS.get(category, {}).get("en") or [])


def buyer_phrases(buyer_type: str, lang: str) -> list[str]:
    return list(BUYER_TERMS.get(buyer_type, {}).get(lang) or BUYER_TERMS.get(buyer_type, {}).get("en") or [])


def generate_queries(buyer_type: str, product: str, lang: str, city: str | None, *, max_queries: int = 4,
                     already: set[str] | None = None, extra_terms: dict | None = None,
                     include_city: bool = True) -> list[str]:
    """Return up to ``max_queries`` distinct queries not yet executed (by normalised form)."""
    already = already if already is not None else set()
    furniture = (FURNITURE_WORD.get(lang) or FURNITURE_WORD["en"])[0]
    prods = product_terms(product, lang, extra_terms)
    phrases = buyer_phrases(buyer_type, lang)
    out: list[str] = []
    candidates: list[str] = []
    for ph in phrases:
        if "{p}" in ph:
            for p in prods[:2]:
                candidates.append(ph.replace("{p}", p).replace("{f}", furniture))
        else:
            q = ph.replace("{f}", furniture)
            candidates.append(q)
            # combine generic buyer phrase with the most specific product term
            if prods and product != "home_furniture":
                candidates.append(f"{q} {prods[0]}")
    for c in candidates:
        q = f"{c} {city}" if (city and include_city) else c
        norm = normalize_query(q)
        if norm in already:
            continue
        already.add(norm)
        out.append(q)
        if len(out) >= max_queries:
            break
    return out


def negative_terms(lang: str, buyer_type: str) -> list[str]:
    """Jobs/second-hand filters always; manufacturers are never excluded here (they may be OEM buyers)."""
    neg = list(NEGATIVE_TERMS.get(lang, [])) + (NEGATIVE_TERMS["en"][:2] if lang != "en" else [])
    if buyer_type in ("wholesaler", "distributor", "verified_importer"):
        neg = [n for n in neg if n.lower() not in ("review",)]
    return neg[:5]


class TermSuggestions(BaseModel):
    terms: list[str] = Field(description="Commercial search terms actually used by businesses in this market")


async def llm_expand_terms(llm: LLMClient, country_name: str, lang: str, buyer_type: str, product: str) -> list[str]:
    """Ask the LLM for extra trade terms. Returns validated suggestions ([] if LLM disabled)."""
    if not llm.enabled:
        return []
    seed = buyer_phrases(buyer_type, lang)[:3] + product_terms(product, lang)[:3]
    prompt = (f"Market: {country_name}. Language code: {lang}. Buyer type: {buyer_type.replace('_', ' ')}. "
              f"Product: {product.replace('_', ' ')}.\nExisting terms: {seed}.\n"
              "List up to 8 additional short search phrases (2-5 words) that furniture importers, wholesalers or "
              "retailers in this market actually use to describe themselves or their products on websites and in "
              "business directories. Use the target language and script. No company names, no brand names, no translations "
              "into other languages.")
    try:
        res = await llm.structured("You are a B2B trade terminology expert for the furniture industry.", prompt, TermSuggestions)
    except LLMUnavailable:
        return []
    want = SCRIPT_BY_LANG.get(lang, "latin")
    clean = []
    for t in res.terms:
        t = t.strip()
        if not (3 <= len(t) <= 60) or len(t.split()) > 6:
            continue
        if detect_script(t) != want:
            continue
        if t not in clean and t not in seed:
            clean.append(t)
    return clean[:8]
