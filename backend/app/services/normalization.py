"""Normalisation helpers: names (multi-script), domains, phones, emails."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from unidecode import unidecode

from app.data.terms import GENERIC_NAME_TOKENS, LEGAL_SUFFIXES

DIAL_CODES = {
    "DE": "49", "FR": "33", "GB": "44", "NL": "31", "BE": "32", "ES": "34", "IT": "39", "PL": "48", "RO": "40",
    "CZ": "420", "SK": "421", "AT": "43", "BG": "359", "GR": "30", "RS": "381", "IQ": "964", "SA": "966",
    "AE": "971", "JO": "962", "QA": "974", "KW": "965", "OM": "968", "BH": "973", "LB": "961", "MA": "212",
    "DZ": "213", "TN": "216", "LY": "218", "EG": "20", "GE": "995", "AZ": "994", "AM": "374", "TR": "90", "US": "1",
}

# Domains that never identify a company on their own.
GENERIC_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr", "outlook.com", "live.com",
    "icloud.com", "mail.ru", "yandex.ru", "yandex.com", "gmx.de", "gmx.net", "web.de", "t-online.de", "orange.fr",
    "wanadoo.fr", "free.fr", "laposte.net", "aol.com", "protonmail.com", "proton.me", "msn.com", "bk.ru", "inbox.ru",
    "facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "tiktok.com",
    "wa.me", "whatsapp.com", "t.me", "google.com", "goo.gl", "maps.google.com", "business.site", "wixsite.com",
    "blogspot.com", "wordpress.com", "linktr.ee", "yell.com", "gelbeseiten.de", "pagesjaunes.fr", "europages.com",
    "kompass.com", "wlw.de", "amazon.com", "amazon.de", "amazon.fr", "ebay.com", "ebay.de", "etsy.com",
    "wikipedia.org", "tripadvisor.com", "yelp.com", "olx.ro", "olx.pl", "leboncoin.fr", "avito.ru", "opensooq.com",
    "dubizzle.com", "jumia.com", "trustpilot.com", "alibaba.com", "made-in-china.com", "indiamart.com",
}

_SCRIPT_RANGES = [
    ("arabic", 0x0600, 0x06FF), ("arabic", 0x0750, 0x077F), ("arabic", 0xFB50, 0xFDFF), ("arabic", 0xFE70, 0xFEFF),
    ("cyrillic", 0x0400, 0x04FF), ("georgian", 0x10A0, 0x10FF), ("georgian", 0x1C90, 0x1CBF),
    ("armenian", 0x0530, 0x058F), ("greek", 0x0370, 0x03FF), ("hebrew", 0x0590, 0x05FF),
]

EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,24})(?![\w-])")
PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s./-]?)?(?:\(?\d{1,5}\)?[\s./-]?){2,6}\d{2,6}")
GENERIC_MAILBOX_PREFIXES = {"info", "contact", "kontakt", "office", "sales", "vente", "ventes", "verkauf", "service",
                            "hello", "hallo", "bonjour", "mail", "admin", "support", "export", "import", "purchasing",
                            "einkauf", "achat", "achats", "procurement", "buying", "buyer", "order", "orders",
                            "commercial", "b2b", "trade", "wholesale", "showroom", "shop", "store", "team", "enquiries",
                            "inquiries", "post", "zakaz", "sale"}
PURCHASING_PREFIXES = {"purchasing", "einkauf", "achat", "achats", "procurement", "buying", "buyer", "acquisti", "compras",
                       "inkoop", "zakupy", "achizitii", "nakup", "zakupki", "import"}


def detect_script(text: str) -> str:
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        if not ch.isalpha():
            continue
        script = "latin"
        for name, lo, hi in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                script = name
                break
        counts[script] = counts.get(script, 0) + 1
    if not counts:
        return "latin"
    return max(counts.items(), key=lambda kv: kv[1])[0]


def transliterate(text: str) -> str:
    return unidecode(text or "").strip()


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    """Lowercase, transliterated, punctuation-free, legal suffixes removed."""
    if not name:
        return ""
    s = name
    # strip Arabic legal prefixes before transliteration
    for token in ("شركة", "مؤسسة", "ش.م.م", "ذ.م.م"):
        s = s.replace(token, " ")
    s = transliterate(s).lower()
    s = _strip_accents(s)
    s = s.replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)              # parenthetical branch info
    s = re.sub(r"[\"'`´’]", "", s)
    s = re.sub(r"[^a-z0-9.\s/-]", " ", s)
    tokens = [t.strip(".-/") for t in re.split(r"[\s/]+", s)]
    tokens = [t for t in tokens if t and t not in LEGAL_SUFFIXES and t.replace(".", "") not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def core_name(name: str, city: str | None = None) -> str:
    """Distinctive part of a name: legal forms, generic trade words and the city removed.

    "ABC Furniture Trading LLC", "ABC Möbel GmbH", "ABC Furniture - Berlin Branch" -> "abc".
    Falls back to the normalised name if everything would be stripped (e.g. "Furniture House").
    """
    norm = normalize_name(name)
    city_tokens = set(normalize_name(city).split()) if city else set()
    tokens = [t for t in norm.split() if t not in GENERIC_NAME_TOKENS and t not in city_tokens and not t.isdigit()]
    # translit of Arabic "athath"/"mafrushat" variants, Cyrillic "mebel'", etc.
    tokens = [t for t in tokens if not re.fullmatch(r"(mebel\w*|mobil\w*|meub\w*|möbel\w*|athath|mafrushat|furnitur\w*)", t)]
    return " ".join(tokens) or norm


def normalize_domain(url_or_domain: str | None) -> str | None:
    if not url_or_domain:
        return None
    s = url_or_domain.strip().lower()
    if "@" in s and "/" not in s:
        s = s.split("@", 1)[1]
    if "://" not in s:
        s = "http://" + s
    try:
        host = urlparse(s).hostname or ""
    except ValueError:
        return None
    host = host.strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    return host


def is_generic_domain(domain: str | None) -> bool:
    if not domain:
        return True
    d = domain.lower()
    return any(d == g or d.endswith("." + g) for g in GENERIC_DOMAINS)


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    try:
        p = urlparse(u)
    except ValueError:
        return None
    if not p.hostname:
        return None
    return f"{p.scheme.lower()}://{p.hostname.lower()}{p.path.rstrip('/') if p.path not in ('', '/') else ''}"


def normalize_phone(phone: str | None, country: str | None = None) -> str | None:
    """Best-effort E.164 normalisation without external data. Returns None when implausible."""
    if not phone:
        return None
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif country and country.upper() in DIAL_CODES:
        cc = DIAL_CODES[country.upper()]
        if digits.startswith(cc) and len(digits) > len(cc) + 6:
            pass
        else:
            digits = cc + digits.lstrip("0")
    if not 8 <= len(digits) <= 15:
        return None
    return "+" + digits


def extract_emails(text: str) -> list[str]:
    out: list[str] = []
    for m in EMAIL_RE.findall(text or ""):
        e = m.strip(".").lower()
        if e.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")) or "example." in e or "sentry" in e:
            continue
        if e not in out:
            out.append(e)
    return out


def extract_phones(text: str, country: str | None = None) -> list[str]:
    out: list[str] = []
    for m in PHONE_RE.findall(text or ""):
        digits = re.sub(r"\D", "", m)
        if len(digits) < 8 or len(set(digits)) <= 2:
            continue
        # skip date/number-like strings without separators or plus sign
        if not re.search(r"[\s+()./-]", m) and not m.startswith(("+", "00")):
            continue
        p = normalize_phone(m, country)
        if p and p not in out:
            out.append(p)
    return out


def email_is_generic(email: str) -> bool:
    local = email.split("@", 1)[0].lower()
    return local in GENERIC_MAILBOX_PREFIXES or any(local.startswith(p + ".") or local.startswith(p + "-") for p in GENERIC_MAILBOX_PREFIXES)


def email_department(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    if any(local.startswith(p) for p in PURCHASING_PREFIXES):
        return "purchasing"
    if local in {"sales", "vente", "ventes", "verkauf", "export", "b2b", "trade", "wholesale", "commercial"}:
        return "sales"
    return "general"


def normalize_query(text: str) -> str:
    s = transliterate(text).lower()
    tokens = sorted(set(re.findall(r"[a-z0-9]+", s)))
    return " ".join(tokens)
