import pytest
from pydantic import BaseModel

from app.services.llm import LLMClient, LLMUnavailable, LLMUsage
from app.services.normalization import detect_script
from app.services.planner import search_languages
from app.services.query_generator import generate_queries, llm_expand_terms, negative_terms


@pytest.mark.parametrize("lang,expected_script,needle", [
    ("de", "latin", "Möbel"), ("fr", "latin", "grossiste"), ("ar", "arabic", "أثاث"), ("ru", "cyrillic", "мебел"),
    ("ka", "georgian", "ავეჯ"), ("hy", "armenian", "կահույք"), ("az", "latin", "mebel"),
])
def test_local_language_queries(lang, expected_script, needle):
    qs = generate_queries("wholesaler", "dining_table", lang, None, max_queries=4)
    assert qs, lang
    assert any(needle.lower() in q.lower() for q in qs)
    assert all(detect_script(q) == expected_script for q in qs)


def test_queries_include_city_and_are_not_repeated():
    seen: set[str] = set()
    a = generate_queries("wholesaler", "chair", "de", "Hamburg", max_queries=3, already=seen)
    b = generate_queries("wholesaler", "chair", "de", "Hamburg", max_queries=3, already=seen)
    assert all("Hamburg" in q for q in a)
    assert not set(a) & set(b)


def test_arabic_mandatory_for_middle_east():
    assert search_languages("IQ")[0] == "ar"
    assert "ar" in search_languages("SA") and "en" in search_languages("SA")
    assert search_languages("MA")[:2] == ["fr", "ar"]
    assert search_languages("GE")[:2] == ["ka", "ru"]


def test_negative_terms_never_exclude_manufacturers():
    for lang in ("de", "fr", "ar"):
        negs = negative_terms(lang, "wholesaler")
        assert negs and not any("manufactur" in n.lower() or "hersteller" in n.lower() for n in negs)


class FakeProvider:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    async def complete_json(self, model, system, prompt, schema):
        self.calls.append(model)
        p = self.payloads.pop(0)
        if isinstance(p, Exception):
            raise p
        return p, LLMUsage(model, 1000, 200)


async def test_llm_terms_validated_by_script():
    llm = LLMClient(provider=FakeProvider([{"terms": ["تجارة الأثاث", "Furniture Wholesale", "ACME Ltd company name very long phrase here ok no",
                                                      "معارض موبيليا"]}]), model="claude-opus-5-5", fallback_model=None)
    terms = await llm_expand_terms(llm, "Iraq", "ar", "wholesaler", "dining_table")
    assert terms == ["تجارة الأثاث", "معارض موبيليا"]
    assert llm.total_cost_usd == pytest.approx((1000 * 4 + 200 * 20) / 1e6)


class Out(BaseModel):
    terms: list[str]


async def test_llm_fallback_on_invalid_output():
    prov = FakeProvider([{"wrong": 1}, {"terms": ["a"]}])
    llm = LLMClient(provider=prov, model="claude-opus-5-5", fallback_model="claude-sonnet-5-5")
    res = await llm.structured("s", "p", Out)
    assert res.terms == ["a"] and prov.calls == ["claude-opus-5-5", "claude-sonnet-5-5"]


async def test_llm_disabled_returns_nothing():
    llm = LLMClient(provider=None)
    assert not llm.enabled
    assert await llm_expand_terms(llm, "Germany", "de", "wholesaler", "chair") == []
    with pytest.raises(LLMUnavailable):
        await llm.structured("s", "p", Out)
