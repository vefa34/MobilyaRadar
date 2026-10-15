from app.data.countries import find_countries_in_text
from app.services.normalization import (
    core_name,
    detect_script,
    email_is_generic,
    extract_emails,
    extract_phones,
    is_generic_domain,
    normalize_domain,
    normalize_name,
    normalize_phone,
    normalize_query,
)


def test_legal_suffixes_and_generic_words_removed():
    variants = ["ABC Furniture LLC", "ABC Furnitures", "ABC Möbel GmbH", "ABC Furniture Trading", "ABC Furniture - Berlin Branch"]
    assert {core_name(v, "Berlin") for v in variants} == {"abc"}


def test_core_name_falls_back_when_everything_generic():
    assert core_name("Furniture House") == "furniture house"


def test_normalize_name_multiscript():
    assert normalize_name("Möbel Müller GmbH & Co. KG") == "mobel muller and co.kg" or "muller" in normalize_name("Möbel Müller GmbH & Co. KG")
    assert detect_script("شركة الأثاث الحديث") == "arabic"
    assert detect_script("ავეჯის სახლი") == "georgian"
    assert detect_script("Կահույքի տուն") == "armenian"
    assert detect_script("Мебельный дом") == "cyrillic"
    # Arabic legal prefix stripped, transliterated to Latin
    n = normalize_name("شركة النور للأثاث")
    assert n and n.isascii()


def test_domains():
    assert normalize_domain("https://www.Example-Moebel.de/kontakt") == "example-moebel.de"
    assert normalize_domain("info@shop.fr") == "shop.fr"
    assert normalize_domain("not a url") is None
    assert is_generic_domain("facebook.com") and is_generic_domain("m.facebook.com") and not is_generic_domain("moebel-abc.de")


def test_phones():
    assert normalize_phone("030 1234567", "DE") == "+49301234567"
    assert normalize_phone("+49 (0)30 1234-567", "DE") is not None
    assert normalize_phone("0049 30 1234567", "DE") == "+49301234567"
    assert normalize_phone("12", "DE") is None
    assert "+33142681234" in extract_phones("Tél : 01 42 68 12 34", "FR")


def test_emails():
    text = "Contact: info@abc-moebel.de, logo@2x.png, Max.Mustermann@abc-moebel.de"
    assert extract_emails(text) == ["info@abc-moebel.de", "max.mustermann@abc-moebel.de"]
    assert email_is_generic("info@x.de") and email_is_generic("einkauf@x.de") and not email_is_generic("max.mustermann@x.de")


def test_query_normalisation_ignores_order_and_case():
    assert normalize_query("Möbel Großhandel Berlin") == normalize_query("berlin möbel großhandel")


def test_country_extraction_from_turkish_request():
    text = "Almanya, Fransa, Irak, Fas ve Gürcistan'da yemek masası ve sandalye ithal eden firmaları bul."
    assert find_countries_in_text(text) == ["DE", "FR", "IQ", "MA", "GE"]
