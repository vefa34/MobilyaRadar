from datetime import UTC, datetime

from app.data.hs_codes import suggest_hs_codes
from app.services.classifier import classify
from app.services.product_catalog import analyze_catalog_text
from app.services.request_parser import parse_request
from app.services.scoring import ScoreInput, compute_scores, priority_label


def test_wholesaler_with_import_claim_is_not_verified_importer():
    cl = classify(name="Nordwind Möbel Großhandel GmbH", source_categories=[], descriptions=[],
                  website_text="Wir sind Möbelgroßhandel und Importeur von Esstischen und Stühlen. B2B only.")
    assert "wholesaler" in cl.buyer_types
    assert "verified_importer" not in cl.buyer_types
    assert cl.import_status == "claimed"
    assert {"dining_table", "chair"} <= set(cl.product_categories)


def test_verified_importer_requires_verified_signal():
    cl = classify(name="X Trading", source_categories=["wholesale=furniture"], descriptions=[], website_text="furniture wholesale",
                  verified_import=True)
    assert cl.primary == "verified_importer" and cl.import_status == "verified"


def test_arabic_wholesaler_detected():
    cl = classify(name="شركة النور", source_categories=[], descriptions=["تجار الأثاث بالجملة - طاولات طعام وكراسي"])
    assert "wholesaler" in cl.buyer_types and cl.furniture_relevance > 0


def test_chain_by_store_count_and_oem():
    cl = classify(name="Maison Bleu", source_categories=["shop=furniture"], descriptions=[], store_count=25,
                  website_text="nos magasins. notre collection, private label sourcing from Turkey")
    assert cl.primary in ("retail_chain", "brand_private_label")
    assert "brand_private_label" in cl.buyer_types and cl.oem_signal


def test_manufacturer_is_not_automatically_buyer():
    cl = classify(name="Holzwerk Fabrik", source_categories=[], descriptions=[], website_text="furniture manufacturer, our factory produces tables")
    assert cl.primary == "manufacturer"
    cl2 = classify(name="Möbel Import", source_categories=[], descriptions=[], website_text="we import tables directly from manufacturers")
    assert "manufacturer" not in cl2.buyer_types


def test_used_and_irrelevant_rejected():
    assert classify(name="Second hand furniture shop", source_categories=[], descriptions=["used furniture"]).reject_reason
    assert classify(name="Elektro Meier", source_categories=[], descriptions=["Kitchen appliances and TVs"]).reject_reason


def _si(cl, **kw):
    base = dict(classification=cl, country="DE", target_products=["dining_table", "chair"], target_buyer_types=["wholesaler"],
                website_product_match=0.8, website_status="ok", store_count=None, location_count=1, employee_count=50,
                has_general_email=True, has_phone=True, has_website=True, has_purchasing_contact=False, source_keys=["brave_search", "company_website"],
                source_reliability={"brave_search": 0.45, "company_website": 0.75}, registry_verified=False, vat_verified=False,
                import_signals_verified=0, import_signals_claimed=1, corroborated_fields=1, last_observed=datetime.now(UTC), is_synthetic=False)
    base.update(kw)
    return ScoreInput(**base)


def test_scores_are_separate_and_explained():
    cl = classify(name="Nordwind Möbel Großhandel", source_categories=[], descriptions=[], website_text="Möbelgroßhandel Esstische Stühle import")
    r = compute_scores(_si(cl))
    assert 0 <= r.buyer_fit <= 100 and 0 <= r.data_confidence <= 100
    assert r.buyer_fit > 55
    assert any(e["component"] == "import_evidence" and "unverified" in e["text"] for e in r.explanation)
    verified = compute_scores(_si(cl, registry_verified=True, vat_verified=True, corroborated_fields=3))
    assert verified.data_confidence > r.data_confidence
    assert verified.buyer_fit == r.buyer_fit  # confidence does not leak into fit


def test_verified_import_raises_fit():
    cl = classify(name="X", source_categories=[], descriptions=[], website_text="furniture wholesale dining table chairs", verified_import=True)
    a = compute_scores(_si(cl, import_signals_verified=2))
    b = compute_scores(_si(cl, import_signals_verified=0, import_signals_claimed=0))
    assert a.components["import_evidence"] == 1.0 and a.buyer_fit > b.buyer_fit


def test_synthetic_has_zero_confidence_and_rejection_caps_fit():
    cl = classify(name="[DEMO] X", source_categories=[], descriptions=[], website_text="furniture wholesale")
    assert compute_scores(_si(cl, is_synthetic=True)).data_confidence == 0
    rej = classify(name="Used furniture", source_categories=[], descriptions=["second hand furniture"])
    assert compute_scores(_si(rej)).buyer_fit <= 15


def test_priority_labels():
    assert priority_label(87, 94) == "high_priority"
    assert priority_label(92, 38) == "promising_needs_verification"
    assert priority_label(24, 96) == "real_but_not_target"


def test_hs_codes_from_attributes():
    assert suggest_hs_codes("dining_table", ["oak"])[0].code == "9403.60"
    assert suggest_hs_codes("dining_table", ["steel"])[0].code == "9403.20"
    assert suggest_hs_codes("chair", ["beech"], upholstered=True)[0].code == "9401.61"
    assert suggest_hs_codes("chair", ["metal"], upholstered=False)[0].code == "9401.79"
    assert suggest_hs_codes("office_furniture", ["wood"], swivel=True)[0].code == "9401.31"
    assert suggest_hs_codes("bed", ["MDF"])[0].code == "9403.50"
    unknown = suggest_hs_codes("dining_table", [])
    assert all(s.confidence < 0.5 for s in unknown)  # never confident without material info


def test_catalog_analysis_turkish():
    text = "2025 Katalog — Masif ahşap yemek masası 180x90, kumaş döşemeli sandalye, metal ayaklı yemek masası"
    res = analyze_catalog_text(text)
    assert set(res["categories"]) >= {"dining_table", "chair"}
    codes = {h["code"] for h in res["hs_codes"]}
    assert "9403.60" in codes and "9401.61" in codes


def test_request_parser():
    p = parse_request("Almanya, Fransa, Irak, Fas ve Gürcistan'da yemek masası ve sandalye ithal eden, toptan satan veya perakende zinciri işleten potansiyel müşterileri bul.")
    assert p["countries"] == ["DE", "FR", "IQ", "MA", "GE"]
    assert set(p["product_categories"]) >= {"dining_table", "chair"}
    assert {"verified_importer", "wholesaler", "retail_chain"} <= set(p["buyer_types"])
