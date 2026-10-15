# Global Furniture Buyer Intelligence Platform

Mobilya ihracatçıları için dünya çapında potansiyel alıcı **keşfeden**, bulunan firmaları **kanıta dayalı doğrulayan** ve
satın alma potansiyeline göre **niteliklendiren** SaaS platformu.

> İlke: *Önce kapsamlı firma keşfi, sonra kanıta dayalı doğrulama, ardından ticari niteliklendirme.*

---

## 1. Hızlı başlangıç

### Docker Compose (önerilen)
```bash
cp .env.example .env            # API anahtarlarını isteğe bağlı doldurun
docker compose up --build       # db, redis, api (FastAPI), worker (Celery+beat), web (Next.js)
# Arayüz: http://localhost:3000   API: http://localhost:8000/docs
```
İlk açılışta **"Create a workspace"** ile organizasyon ve sahip kullanıcısı oluşturun (veya `.env` içinde `BOOTSTRAP_ADMIN_EMAIL/PASSWORD`).

### Yerel geliştirme
```bash
# PostgreSQL 16 ve Redis çalışıyor olmalı
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
createdb fbi && .venv/bin/alembic upgrade head
TASK_BACKEND=thread .venv/bin/uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install && npm run dev        # http://localhost:3000 (/api → :8000 proxy)
```

### Testler
```bash
cd backend && createdb fbi_test && .venv/bin/pytest -q          # 81 test (PostgreSQL üzerinde)
cd frontend && npm run typecheck && npm run build
# E2E (backend :8000 ve frontend :3000 çalışırken):
PW_CHROMIUM_PATH=/path/to/chromium npx playwright test
```

---

## 2. Mimari (kısa)

```
Next.js (TS, Tailwind)  ──/api proxy──►  FastAPI (Pydantic, SQLAlchemy 2, Alembic)
                                              │
                         ┌────────────────────┼─────────────────────┐
                         ▼                    ▼                     ▼
                  PostgreSQL 16        Redis + Celery         Connector katmanı
               (tenant-scoped veri)   (araştırma işleri,     (LeadSourceConnector:
                                       saklama temizliği)     discover/enrich/health/cost)
```

**Araştırma pipeline'ı** (`backend/app/services/pipeline.py`):

1. **Plan** – `Ülke × Şehir × Alıcı tipi × Ürün × Dil × Kaynak` hücreleri (`planner.py`). Kullanılamayan kaynaklar
   *gizlenmez*: `access_restricted` / `manual_review_required` hücresi + manuel araştırma kuyruğu (yerel dilde hazır sorgularla).
2. **Keşif** – Öncelik + çeşitlilik cezası (aynı şehir/ülke/tipe tekrar gitmemek), adaptif sayfalama, şehir×kaynak bazında
   doygunluk tespiti, bütçe ön kontrolü (`estimate_cost`), 429'da `retry_scheduled` + exponential backoff, ardışık hatada
   kaynak bazlı *circuit breaker*. Hedef sayıya ulaşılsa bile her ülkede **≥3 ticari merkez ve tüm istenen alıcı tipleri**
   denenmeden durmaz ("bir sayfa aradım, 20 firma buldum" davranışı engellenir).
3. **Entity resolution** (`entity_resolution.py`) – sicil no / VAT / domain / telefon / ayırt edici isim (yasal ek ve
   genel kelimeler atılmış, transliterasyonlu) ile deterministik eşleştirme; düşük güvenli eşleşmeler otomatik
   birleştirilmez → *Duplicate Review* kuyruğu. Farklı şehirdeki şube → aynı şirketin lokasyonu.
4. **Zenginleştirme** – Önce ucuz ön değerlendirme; sadece değer katacak firmalara: resmi web sitesi (robots.txt'e uyar,
   yalnız kurumsal/rol e-postaları), resmi sicil doğrulaması (VIES, Companies House, ARES), en son ücretli kişi
   zenginleştirmesi (Hunter, yalnız en iyi adaylar ve bütçe varsa).
5. **Sınıflandırma + skor** – Çok dilli kural tabanlı sınıflandırıcı (12 alıcı tipi, çoklu seçim, gerekçeli).
   **Buyer Fit** ve **Data Confidence** ayrı tutulur; her bileşen açıklamalı.
6. **Coverage Report** – ülke/şehir/kaynak/dil kapsamı, erişilemeyen kaynaklar, ücretli veri ihtiyacı, nitelikli lead
   başına maliyet ve **uyarılar** (ör. "DE: sadece 12 ilgili firma, bu pazar için ≥120 beklenir").

Ayrıntı: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · Kaynak matrisi: [`docs/SOURCE_MATRIX.md`](docs/SOURCE_MATRIX.md)

---

## 3. Kaynak entegrasyon durumu (bu sürüm)

| Durum | Kaynaklar |
|---|---|
| ✅ **Çalışır, anahtar gerekmez** | Firma web siteleri (enrichment), EU **VIES** (VAT doğrulama), Çek **ARES** (NACE ile keşif + doğrulama), **OpenStreetMap/Overpass** (public instance iş başına sınırlı), CSV/XLSX içe aktarma, Synthetic demo connector |
| 🔑 **Hazır, API anahtarı gerekli** | **Brave Search API**, **SerpApi**, **Google Places API (New)**, **UK Companies House** (ücretsiz anahtar), **Hunter.io** |
| 📄 **Lisans + sağlayıcı adaptörü gerekli** (iskelet; erişim varmış gibi davranmaz) | Panjiva, ImportGenius, Volza, ImportYeti (yalnız ABD verisi), Kompass, Europages, wlw, Apollo, BIA (GE) |
| ✎ **Manuel kuyruk / katalog** | Gelbe Seiten, Das Örtliche, PagesJaunes, Yell, ticaret odaları (Bağdat, Erbil, Riyad, Cidde, Amman, Katar, Kuveyt, Umman), Dubai Business Directory, Kerix, DirectInfo, CNRC, Spyur, e-register.am, taxes.gov.az, NAPR, BRIS, Handelsregister, ONRC, TED (bağlayıcı planlandı), Annuaire des Entreprises (planlandı), KBO/BCE… |

Tam liste (61 kaynak, erişim modeli, lisans/saklama/dışa aktarım kuralları): `docs/SOURCE_MATRIX.md`.
Keşif sırasında bulunan dizin/rehber siteleri otomatik olarak **`pending_review`** kaynak adayı olarak kaydedilir; onaylanmadan kullanılmaz.

### API anahtarı gerektiren servisler
| Değişken | Servis | Ücret |
|---|---|---|
| `BRAVE_SEARCH_API_KEY` | Brave Search API | ücretsiz katman + ücretli |
| `SERPAPI_API_KEY` | SerpApi | ücretli |
| `GOOGLE_PLACES_API_KEY` | Google Places API (New) | ücretli (faturalandırma hesabı) |
| `COMPANIES_HOUSE_API_KEY` | UK Companies House | ücretsiz |
| `HUNTER_API_KEY` | Hunter.io | ücretsiz katman + ücretli |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | LLM terim genişletme (opsiyonel) | ücretli |

Anahtarlar organizasyon bazında **Source Manager** ekranından da girilebilir (Fernet ile şifreli saklanır, maskeli gösterilir).

---

## 4. Uyumluluk ve veri güvenilirliği kararları

- **Uydurma şirket yok**: LLM yalnızca arama terimi önerir (script/dil doğrulamalı); şirket kaydı ancak bir connector
  kaydı + izlenebilir `source_url` ile oluşur. Her alan için kaynak + tarih `company_evidence` tablosunda.
- **Synthetic veri**: Demo connector'ı `[DEMO]` isimli, `.invalid` alan adlı, `is_synthetic=true` kayıtlar üretir;
  Data Confidence = 0, dashboard ve dışa aktarımda varsayılan olarak hariç.
- **"Verified importer"** yalnızca doğrulanmış sevkiyat/gümrük kaydıyla verilir; web sitesinde "importer" yazması `claimed` sayılır.
- **Google Places**: yalnız `place_id` kalıcı; diğer içerik 30 gün `retention_until` ile saklanır, dışa aktarılmaz,
  başka kaynaklarla birleşik export'a girmez (alan bazlı kaynak kontrolü). Süre dolunca `purge_expired` siler.
- **OSM**: Nominatim toplu madencilik için kullanılmaz; Overpass public instance iş başına sınırlı, hacim için self-host.
- **LinkedIn**: otomatik profil toplama yok — yalnızca manuel kuyruk.
- **Web siteleri**: robots.txt'e uyulur, kendini tanıtan User-Agent, host başına ~1 istek/sn; kişisel e-postalar sitelerden toplanmaz.
- **KVKK/GDPR**: tenant izolasyonu, `do_not_contact`, silme (erasure) endpoint'i + audit log, kaynak lisansına bağlı saklama süreleri.

---

## 5. API özeti

| Endpoint | Açıklama |
|---|---|
| `POST /api/auth/register`, `/login`, `GET /me`, `POST/GET /users` | JWT auth, roller: owner/admin/analyst/viewer |
| `GET /api/research/options`, `POST /parse`, `POST /catalog/analyze` | Ülke/ürün seçenekleri, serbest metin ayrıştırma (TR/EN), katalog (PDF/CSV/XLSX) → kategori + HS kodu |
| `POST /api/research/jobs` · `GET /jobs[/id]` · `/start` · `/cancel` | Araştırma işi (kota + aylık bütçe kontrolü) |
| `GET /jobs/{id}/monitor` · `/tasks` · `/coverage` · `/manual-queue` | Canlı izleme, plan hücreleri, kapsam raporu, manuel kuyruk |
| `GET /api/companies` (filtre/sıralama/sayfalama) · `GET /{id}` · `PATCH /{id}/lead` · `POST /{id}/rescore` · `DELETE /{id}` | Şirketler, kanıtlar, CRM durumu, GDPR silme |
| `POST /api/companies/import` | CSV/XLSX içe aktarma (hak beyanı zorunlu) |
| `GET /api/companies/reviews` · `POST /reviews/{id}` | Duplicate review (merge / group / reject) |
| `GET /api/sources` · `/matrix` · `PUT /{key}/permission` · `POST /{key}/health` · `POST /{key}/review` | Source Manager |
| `GET /api/exports/companies?format=csv|xlsx` | CRM uyumlu export (lisans bazlı alan filtreleme) |
| `GET /api/dashboard` · `/calibration` · `POST /maintenance/purge-expired` | Dashboard, skor kalibrasyon girdisi, saklama temizliği |

OpenAPI: `http://localhost:8000/docs`

---

## 6. Veri modeli

`organizations, users, audit_logs, source_registry, source_permissions, search_jobs, search_tasks, search_queries,
source_executions, research_costs, companies, company_aliases, company_locations, company_contacts, company_categories,
company_evidence, import_signals, company_scores, entity_match_reviews, organization_leads, manual_research_items`
— şema: `backend/app/models.py`, migration: `backend/alembic/versions/0001_initial_schema.py`.

---

## 7. Durum: tamamlanan / eksik

**Tamamlanan (Faz 1 + Faz 2'nin büyük kısmı, Faz 3/4 temelleri)**
- Uçtan uca çalışan araştırma pipeline'ı (plan → keşif → dedup → enrichment → sınıflandırma → skor → coverage)
- 32 ülke konfigürasyonu (Avrupa, Orta Doğu, K. Afrika, Kafkasya), ticari merkez öncelikli şehir listeleri, lojistik/ticaret rejimi
- 20 dilde ticari terminoloji (Arapça, Gürcüce, Ermenice, Rusça, Azerice dahil), negatif filtreler, sorgu tekrarı engelleme
- Connector'lar: Brave, SerpApi, Google Places, Overpass, web sitesi, VIES, Companies House, ARES, Hunter, CSV/XLSX, lisanslı kaynak iskeletleri
- Entity resolution (çok alfabeli alias, şube/grup ilişkisi, review kuyruğu), iki ayrı skor + açıklama
- Bütçe/maliyet takibi, kota, coverage raporu, manuel kuyruk, dinamik kaynak keşfi (pending review)
- Multi-tenant auth/RBAC, şifreli API anahtarları, audit log, saklama/silme, CRM alanları, CSV/XLSX export
- Web arayüzü: Dashboard, New Research, Research Monitor, Companies (+detay), Duplicate Review, Source Manager, Exports

**Doğrulanmadı / eksik (dürüst not)**
- Bu geliştirme ortamında dış ağ kapalıydı: gerçek API'ler (Brave, Places, Overpass, VIES, ARES, Companies House, Hunter)
  **yalnızca mock HTTP yanıtlarıyla** test edildi; canlı anahtarla ilk çalıştırmada yanıt alanları doğrulanmalı (özellikle ARES arama gövdesi).
- Lisanslı veri sağlayıcıları (Panjiva, Volza, ImportGenius, Kompass, Europages, Apollo…) için yalnız iskelet var — sözleşme + API dokümanı gerekir.
- TED, Annuaire des Entreprises, KBO/BCE, REGON/KRS connector'ları katalogda, kod bekliyor.
- Abonelik/faturalama (Stripe vb.), SSO, monitoring (Prometheus/Sentry) henüz yok; e-posta doğrulama/şifre sıfırlama yok.
- Görev yürütme sıralı (kaynak başına paralellik yok); büyük işlerde performans iyileştirmesi gerekebilir.

**Önceliklendirilmiş sonraki adımlar**
1. Gerçek anahtarlarla (Brave + Places + Companies House) DE/FR/GB pilot araştırma; connector alanlarını canlı yanıtlara göre doğrula.
2. Annuaire des Entreprises (FR, NAF 46.47Z/47.59A) ve TED (CPV 391*) connector'ları — ücretsiz, yüksek değerli.
3. Bir shipment-data sağlayıcısıyla (hedef ülke kapsamı doğrulanmış) lisans → `verified_importer` akışı.
4. Kaynak başına paralel yürütme + istek havuzu; büyük işlerde Celery task'larına bölme.
5. CRM sonuçlarıyla skor ağırlık kalibrasyonu (≥50 won/lost sonrası), HubSpot/Pipedrive push entegrasyonu.
6. Faturalama/kota, SSO, monitoring, rate-limit'li public API.
