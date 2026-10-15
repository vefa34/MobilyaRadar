"""Company website enrichment.

Fetches a small number of public pages (home, contact/imprint, about, B2B) of a company's
official site, honouring robots.txt and a polite per-host rate, and extracts facts with URL
provenance: generic business e-mails, phone numbers, VAT/registration numbers, product keyword
matches, buyer-role signals (importer/wholesale/chain/OEM/manufacturer) and store-count hints.

Only role mailboxes and data published by the company for business contact are captured; personal
data beyond that is not harvested.
"""
from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.connectors.base import (
    CompanySnapshot,
    ConnectorContext,
    ContactItem,
    EnrichmentResult,
    EvidenceItem,
    HealthStatus,
    ImportSignalItem,
    LeadSourceConnector,
)
from app.data.terms import CLASSIFIER_SIGNALS
from app.services.normalization import (
    email_department,
    email_is_generic,
    extract_emails,
    extract_phones,
    normalize_domain,
)

LINK_HINTS = re.compile(
    r"(contact|kontakt|impressum|imprint|about|ueber-uns|uber-uns|über-uns|qui-sommes|a-propos|chi-siamo|quienes|"
    r"over-ons|o-nas|despre|o-firme|b2b|wholesale|haendler|händler|revendeur|dealer|stores|filialen|magasins|"
    r"اتصل|من-نحن|контакт|о-компании|კონტაქტ|կապ|əlaqə|legal|mentions-legales)", re.I)

VAT_RE = re.compile(r"\b(?:ATU\d{8}|BE0?\d{9,10}|BG\d{9,10}|CZ\d{8,10}|DE\d{9}|EL\d{9}|ES[A-Z0-9]\d{7}[A-Z0-9]|FR[A-Z0-9]{2}\d{9}|"
                    r"IT\d{11}|NL\d{9}B\d{2}|PL\d{10}|RO\d{2,10}|SK\d{10}|GB\d{9}|GB\d{12})\b")
REG_RE = re.compile(r"\b(HRB|HRA)\s?\d{3,7}\b|\bSIRE[NT]\s?:?\s?\d{3}\s?\d{3}\s?\d{3}(?:\s?\d{5})?\b|\bKRS\s?:?\s?\d{10}\b|"
                    r"\bI[ČC]O?\s?:?\s?\d{8}\b|\bCUI\s?:?\s?(?:RO)?\d{2,10}\b|\bCompany (?:No\.?|number)\s?:?\s?\d{8}\b", re.I)
STORE_COUNT_RE = re.compile(r"\b(\d{1,3})\s+(?:stores|shops|showrooms|branches|filialen|einrichtungshäuser|magasins|"
                            r"tiendas|negozi|winkels|salonów|magazine|prodejen|فرع|فروع|магазинов|филиалов|ფილიალი|մասնաճյուղ|filial)", re.I)


class _TextLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._href: str | None = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "a":
            self._href = dict(attrs).get("href")
        elif tag == "title":
            self._in_title = True
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        elif tag == "a":
            self._href = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        self.text.append(data)
        if self._href:
            self.links.append((self._href, data.strip()))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def parse_html(html: str) -> tuple[str, list[tuple[str, str]], str]:
    p = _TextLinkParser()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML; keep what we parsed
        pass
    # mailto/tel links are captured via hrefs
    hrefs = " ".join(h for h, _ in p.links if h and h.startswith(("mailto:", "tel:")))
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.text))
    return text + "\n" + hrefs.replace("mailto:", " ").replace("tel:", " "), p.links, p.title.strip()


class Fetcher(Protocol):
    async def fetch(self, url: str) -> tuple[int, str]: ...
    async def allowed(self, url: str) -> bool: ...


class HttpFetcher:
    def __init__(self, client: httpx.AsyncClient, user_agent: str, timeout: float = 12.0, max_bytes: int = 1_500_000):
        self.client, self.ua, self.timeout, self.max_bytes = client, user_agent, timeout, max_bytes
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}

    async def allowed(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self._robots:
            rp = RobotFileParser()
            try:
                r = await self.client.get(f"{urlparse(url).scheme}://{host}/robots.txt", timeout=self.timeout)
                if r.status_code in (401, 403) or r.status_code >= 500:
                    rp.disallow_all = True  # RFC 9309: server errors → assume complete disallow
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp.disallow_all = True  # unreachable robots.txt → conservative (RFC 9309 §2.3.1.4)
            self._robots[host] = rp
        rp = self._robots[host]
        return rp.can_fetch(self.ua, url) if rp else True

    async def fetch(self, url: str) -> tuple[int, str]:
        import asyncio
        host = urlparse(url).netloc
        wait = self._last_hit.get(host, 0) + 1.0 - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_hit[host] = time.monotonic()
        r = await self.client.get(url, timeout=self.timeout, headers={"User-Agent": self.ua, "Accept": "text/html"})
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return r.status_code, ""
        return r.status_code, r.text[: self.max_bytes]


class SyntheticFetcher:
    """Serves the synthetic sites of MockConnector companies (``*.invalid`` domains)."""

    async def allowed(self, url: str) -> bool:
        return True

    async def fetch(self, url: str) -> tuple[int, str]:
        from app.connectors.mock import synthetic_site_html
        p = urlparse(url)
        html = synthetic_site_html(p.hostname or "", p.path or "/")
        return (200, html) if html else (404, "")


class WebsiteConnector(LeadSourceConnector):
    key = "company_website"
    purposes = ("verification", "contact_enrichment")
    cost_per_request_usd = 0.0

    def __init__(self, *a, fetcher: Fetcher | None = None, **kw):
        super().__init__(*a, **kw)
        self._fetcher = fetcher

    def fetcher_for(self, domain: str) -> Fetcher:
        if self._fetcher:
            return self._fetcher
        if domain.endswith(".invalid"):
            return SyntheticFetcher()
        if not hasattr(self, "_http_fetcher"):
            self._http_fetcher = HttpFetcher(self.http, self.settings.http_user_agent, self.settings.website_timeout_s)
        return self._http_fetcher

    async def enrich(self, company: CompanySnapshot, context: ConnectorContext) -> EnrichmentResult:
        res = EnrichmentResult()
        domain = company.domain or normalize_domain(company.website)
        if not domain:
            res.status = "skipped"
            return res
        if domain.endswith(".invalid") and not company.is_synthetic:
            res.status = "skipped"
            return res
        fetcher = self.fetcher_for(domain)
        home = company.website if company.website and company.website.startswith("http") else f"https://{domain}"
        if not await fetcher.allowed(home):
            res.status = "blocked_by_robots"
            res.evidence.append(EvidenceItem("website_content", "website_status", "blocked_by_robots", home, confidence=0.9))
            return res
        try:
            status, html = await fetcher.fetch(home)
            res.http_calls += 1
        except httpx.HTTPError as exc:
            res.status = "unreachable"
            res.evidence.append(EvidenceItem("website_content", "website_status", "unreachable", home, snippet=str(exc)[:200], confidence=0.7))
            return res
        if status >= 400 or not html:
            res.status = "not_found" if status == 404 else "unreachable"
            res.evidence.append(EvidenceItem("website_content", "website_status", res.status, home, snippet=f"HTTP {status}", confidence=0.7))
            return res

        pages: list[tuple[str, str]] = []
        text, links, title = parse_html(html)
        pages.append((home, text))
        followed: list[str] = []
        for href, label in links:
            if len(followed) >= self.settings.website_max_pages - 1:
                break
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            full = urljoin(home + "/", href)
            if normalize_domain(full) != domain or full in followed:
                continue
            if LINK_HINTS.search(href) or LINK_HINTS.search(label or ""):
                followed.append(full)
        for url in followed:
            if not await fetcher.allowed(url):
                continue
            try:
                st, h = await fetcher.fetch(url)
                res.http_calls += 1
            except httpx.HTTPError:
                continue
            if st < 400 and h:
                pages.append((url, parse_html(h)[0]))

        res.status = "ok"
        res.updates["website_status"] = "ok"
        res.evidence.append(EvidenceItem("website_content", "website", f"https://{domain}", home,
                                         snippet=(title or "")[:200], confidence=0.9))
        corpus_parts = []
        for url, ptext in pages:
            low = ptext.lower()
            corpus_parts.append(low)
            for email in extract_emails(ptext):
                if normalize_domain(email) != domain and not email.endswith(domain):
                    continue  # only mailboxes on the company's own domain
                generic = email_is_generic(email)
                if not generic:
                    continue  # personal mailboxes are not harvested from websites
                res.contacts.append(ContactItem("email", email, url, department=email_department(email), is_generic=True, confidence=0.8))
            for phone in extract_phones(ptext, company.country)[:3]:
                res.contacts.append(ContactItem("phone", phone, url, is_generic=True, confidence=0.6))
            for m in VAT_RE.findall(ptext):
                res.evidence.append(EvidenceItem("website_content", "vat_number", m, url, snippet=_ctx(ptext, m), confidence=0.7))
                res.updates.setdefault("vat_number", m)
            for m in REG_RE.finditer(ptext):
                res.evidence.append(EvidenceItem("website_content", "registration_number", m.group(0), url, snippet=_ctx(ptext, m.group(0)), confidence=0.6))
                res.updates.setdefault("registration_number", m.group(0))
            for m in STORE_COUNT_RE.finditer(ptext):
                n = int(m.group(1))
                if 2 <= n <= 900:
                    res.evidence.append(EvidenceItem("website_content", "store_count", str(n), url, snippet=_ctx(ptext, m.group(0)), confidence=0.6))
                    res.updates["store_count"] = max(n, res.updates.get("store_count", 0))
            if re.search(r"\bcontact form|kontaktformular|formulaire de contact\b", low):
                res.contacts.append(ContactItem("contact_form", url, url, is_generic=True, confidence=0.5))
        corpus = "\n".join(corpus_parts)
        res.text_corpus = corpus

        # Product match
        if company.product_terms:
            hits = sorted({t for t in company.product_terms if t.lower() in corpus})
            ratio = len(hits) / max(1, len(set(t.lower() for t in company.product_terms)))
            res.updates["website_product_match"] = round(min(1.0, ratio * 2.5), 3)  # a few hits already indicate strong fit
            if hits:
                res.evidence.append(EvidenceItem("website_content", "product_match", ", ".join(hits[:10]), home,
                                                 snippet=_ctx(corpus, hits[0]), confidence=0.7))

        # Role signals with snippets as evidence
        for signal in ("importer", "wholesaler", "distributor", "chain", "ecommerce", "contract", "interior", "oem",
                       "manufacturer", "brand", "used"):
            kw = next((k for k in CLASSIFIER_SIGNALS[signal] if k in corpus), None)
            if kw:
                res.evidence.append(EvidenceItem("website_content", f"signal:{signal}", kw, home, snippet=_ctx(corpus, kw), confidence=0.55))
        imp_kw = next((k for k in CLASSIFIER_SIGNALS["importer"] if k in corpus), None)
        if imp_kw:
            res.import_signals.append(ImportSignalItem("self_declared", False, home,
                                                       description=f"Website mentions import activity: “{_ctx(corpus, imp_kw)}”"))
        if any(k in corpus for k in CLASSIFIER_SIGNALS["oem"]):
            res.updates["oem_private_label_signal"] = True
        return res

    async def health_check(self) -> HealthStatus:
        return HealthStatus("ok", "fetches public company websites (robots.txt honoured)")


def _ctx(text: str, needle: str, width: int = 90) -> str:
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    s = max(0, i - width)
    return re.sub(r"\s+", " ", text[s:i + len(needle) + width]).strip()
