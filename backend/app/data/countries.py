"""Country research configuration.

``cities`` are ordered by commercial priority for furniture trade (population, wholesale/retail
clusters, ports and logistics hubs) — not just the capital. ``weight`` (0-1) feeds the planner.
``logistics`` is relative to the default exporter origin (Türkiye) and is used by the
market & logistics fit component of the Buyer Fit Score; it is configurable per organisation.

``trade_regime`` captures tariff context for TR-origin furniture:
  * customs_union  – EU–Türkiye customs union covers industrial goods incl. HS 94.
  * fta            – a free-trade agreement with Türkiye is in force.
  * mfn            – standard tariffs.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class City:
    name: str
    weight: float
    local_name: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class CountryConfig:
    iso2: str
    name_en: str
    name_tr: str
    region: str  # europe | middle_east | north_africa | caucasus
    languages: tuple[str, ...]  # search languages in priority order (ISO-639-1)
    cities: tuple[City, ...]
    logistics: float  # 0-1 ease of logistics from TR (distance, routes, transit time)
    trade_regime: str = "mfn"
    vat_prefix: str | None = None  # EU VIES prefix
    scripts: tuple[str, ...] = ("latin",)
    aliases: tuple[str, ...] = field(default_factory=tuple)  # names used in free-text requests
    notes: str | None = None


C = City

COUNTRIES: dict[str, CountryConfig] = {}


def _add(cfg: CountryConfig) -> None:
    COUNTRIES[cfg.iso2] = cfg


# ------------------------------------------------------------------ Europe
_add(CountryConfig("DE", "Germany", "Almanya", "europe", ("de", "en"), (
    C("Berlin", 0.85), C("Hamburg", 0.9, note="port, import/wholesale hub"), C("München", 0.8, "Munich"),
    C("Köln", 0.8, "Cologne", note="imm cologne furniture fair"), C("Frankfurt am Main", 0.75),
    C("Düsseldorf", 0.7), C("Stuttgart", 0.7), C("Bielefeld", 0.75, note="OWL furniture cluster"),
    C("Herford", 0.7, note="OWL furniture cluster"), C("Bad Salzuflen", 0.65, note="M.O.W. trade fair"),
    C("Hannover", 0.6), C("Nürnberg", 0.6), C("Leipzig", 0.55), C("Dortmund", 0.6), C("Essen", 0.55),
    C("Bremen", 0.6, note="port"), C("Dresden", 0.45), C("Mannheim", 0.5)),
    logistics=0.75, trade_regime="customs_union", vat_prefix="DE",
    aliases=("germany", "almanya", "deutschland", "allemagne")))
_add(CountryConfig("FR", "France", "Fransa", "europe", ("fr", "en"), (
    C("Paris", 0.95), C("Lyon", 0.8), C("Marseille", 0.8, note="Mediterranean port"), C("Lille", 0.7),
    C("Bordeaux", 0.65), C("Toulouse", 0.65), C("Nantes", 0.6), C("Strasbourg", 0.55), C("Nice", 0.5),
    C("Le Havre", 0.55, note="port"), C("Montpellier", 0.5), C("Rennes", 0.45)),
    logistics=0.7, trade_regime="customs_union", vat_prefix="FR",
    aliases=("france", "fransa", "frankreich")))
_add(CountryConfig("GB", "United Kingdom", "Birleşik Krallık", "europe", ("en",), (
    C("London", 0.95), C("Manchester", 0.8), C("Birmingham", 0.8), C("Leeds", 0.65), C("Glasgow", 0.6),
    C("Liverpool", 0.6), C("Bristol", 0.55), C("High Wycombe", 0.55, note="furniture heritage cluster"),
    C("Nottingham", 0.5), C("Sheffield", 0.5), C("Leicester", 0.5), C("Edinburgh", 0.5)),
    logistics=0.6, trade_regime="fta", vat_prefix=None,
    aliases=("uk", "united kingdom", "england", "birleşik krallık", "ingiltere", "britain"),
    notes="UK–Türkiye FTA in force since 2021."))
_add(CountryConfig("NL", "Netherlands", "Hollanda", "europe", ("nl", "en"), (
    C("Amsterdam", 0.85), C("Rotterdam", 0.9, note="largest EU port"), C("Utrecht", 0.65),
    C("Den Haag", 0.6), C("Eindhoven", 0.55), C("Tilburg", 0.5), C("Groningen", 0.45)),
    logistics=0.7, trade_regime="customs_union", vat_prefix="NL", aliases=("netherlands", "hollanda", "holland")))
_add(CountryConfig("BE", "Belgium", "Belçika", "europe", ("nl", "fr", "en"), (
    C("Brussel", 0.8, "Bruxelles"), C("Antwerpen", 0.85, note="port"), C("Gent", 0.6), C("Liège", 0.55),
    C("Charleroi", 0.45), C("Brugge", 0.4)),
    logistics=0.7, trade_regime="customs_union", vat_prefix="BE", aliases=("belgium", "belçika", "belgique")))
_add(CountryConfig("ES", "Spain", "İspanya", "europe", ("es", "en"), (
    C("Madrid", 0.9), C("Barcelona", 0.9), C("Valencia", 0.8, note="furniture cluster & port"), C("Sevilla", 0.6),
    C("Málaga", 0.55), C("Bilbao", 0.55), C("Zaragoza", 0.5), C("Murcia", 0.5, note="Yecla furniture cluster nearby")),
    logistics=0.65, trade_regime="customs_union", vat_prefix="ES", aliases=("spain", "ispanya", "españa")))
_add(CountryConfig("IT", "Italy", "İtalya", "europe", ("it", "en"), (
    C("Milano", 0.95, note="Salone del Mobile"), C("Roma", 0.8), C("Napoli", 0.6), C("Torino", 0.6),
    C("Bologna", 0.55), C("Firenze", 0.5), C("Bari", 0.5), C("Treviso", 0.5, note="furniture district"),
    C("Udine", 0.45, note="chair district (Manzano)"), C("Padova", 0.45)),
    logistics=0.7, trade_regime="customs_union", vat_prefix="IT", aliases=("italy", "italya", "italia")))
_add(CountryConfig("PL", "Poland", "Polonya", "europe", ("pl", "en"), (
    C("Warszawa", 0.9), C("Poznań", 0.75, note="furniture fair (Meble Polska)"), C("Kraków", 0.65),
    C("Wrocław", 0.65), C("Łódź", 0.6), C("Gdańsk", 0.6, note="port"), C("Katowice", 0.55), C("Szczecin", 0.5)),
    logistics=0.65, trade_regime="customs_union", vat_prefix="PL", aliases=("poland", "polonya", "polska")))
_add(CountryConfig("RO", "Romania", "Romanya", "europe", ("ro", "en"), (
    C("București", 0.95, "Bucharest"), C("Cluj-Napoca", 0.65), C("Timișoara", 0.6), C("Iași", 0.55),
    C("Constanța", 0.6, note="Black Sea port"), C("Brașov", 0.5), C("Craiova", 0.4)),
    logistics=0.8, trade_regime="customs_union", vat_prefix="RO", aliases=("romania", "romanya")))
_add(CountryConfig("CZ", "Czechia", "Çekya", "europe", ("cs", "en"), (
    C("Praha", 0.9), C("Brno", 0.7), C("Ostrava", 0.55), C("Plzeň", 0.45), C("Olomouc", 0.4)),
    logistics=0.65, trade_regime="customs_union", vat_prefix="CZ", aliases=("czechia", "czech republic", "çekya")))
_add(CountryConfig("SK", "Slovakia", "Slovakya", "europe", ("sk", "en"), (
    C("Bratislava", 0.9), C("Košice", 0.6), C("Žilina", 0.45), C("Nitra", 0.4)),
    logistics=0.65, trade_regime="customs_union", vat_prefix="SK", aliases=("slovakia", "slovakya")))
_add(CountryConfig("AT", "Austria", "Avusturya", "europe", ("de", "en"), (
    C("Wien", 0.95, "Vienna"), C("Graz", 0.6), C("Linz", 0.6), C("Salzburg", 0.55), C("Innsbruck", 0.45)),
    logistics=0.7, trade_regime="customs_union", vat_prefix="AT", aliases=("austria", "avusturya", "österreich")))
_add(CountryConfig("BG", "Bulgaria", "Bulgaristan", "europe", ("bg", "en"), (
    C("София", 0.95, "Sofia"), C("Пловдив", 0.7, "Plovdiv"), C("Варна", 0.65, "Varna"), C("Бургас", 0.6, "Burgas")),
    logistics=0.9, trade_regime="customs_union", vat_prefix="BG", scripts=("cyrillic", "latin"),
    aliases=("bulgaria", "bulgaristan")))
_add(CountryConfig("GR", "Greece", "Yunanistan", "europe", ("el", "en"), (
    C("Αθήνα", 0.95, "Athens"), C("Θεσσαλονίκη", 0.8, "Thessaloniki"), C("Πειραιάς", 0.6, "Piraeus"),
    C("Πάτρα", 0.45, "Patras"), C("Ηράκλειο", 0.45, "Heraklion")),
    logistics=0.85, trade_regime="customs_union", vat_prefix="EL", scripts=("greek", "latin"),
    aliases=("greece", "yunanistan")))
_add(CountryConfig("RS", "Serbia", "Sırbistan", "europe", ("sr", "en"), (
    C("Beograd", 0.95, "Belgrade"), C("Novi Sad", 0.7), C("Niš", 0.55), C("Kragujevac", 0.4)),
    logistics=0.8, trade_regime="fta", scripts=("cyrillic", "latin"), aliases=("serbia", "sırbistan", "srbija"),
    notes="Türkiye–Serbia FTA."))

# ------------------------------------------------------------------ Middle East
_add(CountryConfig("IQ", "Iraq", "Irak", "middle_east", ("ar", "ku", "en"), (
    C("بغداد", 0.95, "Baghdad"), C("أربيل", 0.9, "Erbil", note="KRG trade hub, TR land border route"),
    C("البصرة", 0.75, "Basra", note="Umm Qasr port"), C("السليمانية", 0.7, "Sulaymaniyah"),
    C("الموصل", 0.6, "Mosul"), C("دهوك", 0.6, "Duhok", note="Habur/Ibrahim Khalil border crossing"),
    C("كركوك", 0.5, "Kirkuk"), C("النجف", 0.5, "Najaf"), C("كربلاء", 0.45, "Karbala")),
    logistics=0.85, scripts=("arabic", "latin"), aliases=("iraq", "irak", "العراق")))
_add(CountryConfig("SA", "Saudi Arabia", "Suudi Arabistan", "middle_east", ("ar", "en"), (
    C("الرياض", 0.95, "Riyadh"), C("جدة", 0.9, "Jeddah", note="Red Sea port"), C("الدمام", 0.8, "Dammam"),
    C("الخبر", 0.6, "Khobar"), C("مكة", 0.55, "Makkah", note="hospitality projects"),
    C("المدينة المنورة", 0.5, "Madinah", note="hospitality projects"), C("تبوك", 0.4, "Tabuk", note="NEOM area")),
    logistics=0.6, scripts=("arabic", "latin"), aliases=("saudi arabia", "suudi arabistan", "ksa", "السعودية")))
_add(CountryConfig("AE", "United Arab Emirates", "Birleşik Arap Emirlikleri", "middle_east", ("en", "ar"), (
    C("Dubai", 0.95, "دبي", note="re-export hub to GCC/Africa"), C("Abu Dhabi", 0.8, "أبوظبي"),
    C("Sharjah", 0.75, "الشارقة", note="furniture wholesale cluster"), C("Ajman", 0.55, "عجمان"),
    C("Ras Al Khaimah", 0.4, "رأس الخيمة")),
    logistics=0.65, scripts=("latin", "arabic"), aliases=("uae", "united arab emirates", "bae", "emirates", "dubai")))
_add(CountryConfig("JO", "Jordan", "Ürdün", "middle_east", ("ar", "en"), (
    C("عمان", 0.95, "Amman"), C("إربد", 0.55, "Irbid"), C("الزرقاء", 0.5, "Zarqa"), C("العقبة", 0.45, "Aqaba", note="port")),
    logistics=0.7, scripts=("arabic", "latin"), aliases=("jordan", "ürdün", "الأردن")))
_add(CountryConfig("QA", "Qatar", "Katar", "middle_east", ("ar", "en"), (
    C("الدوحة", 0.95, "Doha"), C("الوكرة", 0.4, "Al Wakrah"), C("الريان", 0.45, "Al Rayyan")),
    logistics=0.55, scripts=("arabic", "latin"), aliases=("qatar", "katar", "قطر")))
_add(CountryConfig("KW", "Kuwait", "Kuveyt", "middle_east", ("ar", "en"), (
    C("مدينة الكويت", 0.95, "Kuwait City"), C("حولي", 0.6, "Hawalli"), C("الفروانية", 0.5, "Farwaniya"),
    C("الشويخ", 0.6, "Shuwaikh", note="industrial/wholesale area")),
    logistics=0.55, scripts=("arabic", "latin"), aliases=("kuwait", "kuveyt", "الكويت")))
_add(CountryConfig("OM", "Oman", "Umman", "middle_east", ("ar", "en"), (
    C("مسقط", 0.95, "Muscat"), C("صلالة", 0.5, "Salalah", note="port"), C("صحار", 0.5, "Sohar", note="port")),
    logistics=0.5, scripts=("arabic", "latin"), aliases=("oman", "umman", "عمان")))
_add(CountryConfig("BH", "Bahrain", "Bahreyn", "middle_east", ("ar", "en"), (
    C("المنامة", 0.95, "Manama"), C("المحرق", 0.5, "Muharraq")),
    logistics=0.55, scripts=("arabic", "latin"), aliases=("bahrain", "bahreyn", "البحرين")))
_add(CountryConfig("LB", "Lebanon", "Lübnan", "middle_east", ("ar", "fr", "en"), (
    C("بيروت", 0.95, "Beirut"), C("طرابلس", 0.6, "Tripoli"), C("صيدا", 0.45, "Sidon"), C("زحلة", 0.4, "Zahle")),
    logistics=0.7, scripts=("arabic", "latin"), aliases=("lebanon", "lübnan", "لبنان")))

# ------------------------------------------------------------------ North Africa
_add(CountryConfig("MA", "Morocco", "Fas", "north_africa", ("fr", "ar", "en"), (
    C("Casablanca", 0.95, "الدار البيضاء"), C("Rabat", 0.7, "الرباط"), C("Marrakech", 0.65, "مراكش", note="hospitality"),
    C("Tanger", 0.7, "طنجة", note="Tanger Med port"), C("Fès", 0.55, "فاس"), C("Agadir", 0.5, "أكادير"),
    C("Meknès", 0.4, "مكناس"), C("Oujda", 0.35, "وجدة")),
    logistics=0.65, trade_regime="fta", scripts=("latin", "arabic"), aliases=("morocco", "fas", "maroc", "المغرب"),
    notes="Türkiye–Morocco FTA (2006)."))
_add(CountryConfig("DZ", "Algeria", "Cezayir", "north_africa", ("fr", "ar", "en"), (
    C("Alger", 0.95, "الجزائر"), C("Oran", 0.75, "وهران"), C("Constantine", 0.6, "قسنطينة"), C("Sétif", 0.55, "سطيف"),
    C("Annaba", 0.5, "عنابة"), C("Blida", 0.45, "البليدة")),
    logistics=0.6, scripts=("latin", "arabic"), aliases=("algeria", "cezayir", "algérie", "الجزائر"),
    notes="Import licensing regimes change frequently; verify current rules."))
_add(CountryConfig("TN", "Tunisia", "Tunus", "north_africa", ("fr", "ar", "en"), (
    C("Tunis", 0.95, "تونس"), C("Sfax", 0.7, "صفاقس"), C("Sousse", 0.6, "سوسة", note="hospitality"),
    C("Nabeul", 0.45, "نابل"), C("Bizerte", 0.4, "بنزرت")),
    logistics=0.65, trade_regime="fta", scripts=("latin", "arabic"), aliases=("tunisia", "tunus", "tunisie", "تونس")))
_add(CountryConfig("LY", "Libya", "Libya", "north_africa", ("ar", "en"), (
    C("طرابلس", 0.95, "Tripoli"), C("بنغازي", 0.8, "Benghazi"), C("مصراتة", 0.7, "Misrata", note="port & free zone"),
    C("الزاوية", 0.4, "Zawiya")),
    logistics=0.65, scripts=("arabic", "latin"), aliases=("libya", "ليبيا")))
_add(CountryConfig("EG", "Egypt", "Mısır", "north_africa", ("ar", "en"), (
    C("القاهرة", 0.95, "Cairo"), C("الجيزة", 0.7, "Giza"), C("الإسكندرية", 0.8, "Alexandria", note="port"),
    C("دمياط", 0.7, "Damietta", note="furniture manufacturing cluster"), C("المنصورة", 0.45, "Mansoura"),
    C("بورسعيد", 0.45, "Port Said")),
    logistics=0.7, trade_regime="fta", scripts=("arabic", "latin"), aliases=("egypt", "mısır", "مصر"),
    notes="Türkiye–Egypt FTA. Damietta is a large domestic producer cluster — many manufacturers."))

# ------------------------------------------------------------------ Caucasus
_add(CountryConfig("GE", "Georgia", "Gürcistan", "caucasus", ("ka", "ru", "en"), (
    C("თბილისი", 0.95, "Tbilisi"), C("ბათუმი", 0.75, "Batumi", note="port, hospitality, TR border"),
    C("ქუთაისი", 0.55, "Kutaisi"), C("რუსთავი", 0.45, "Rustavi"), C("ფოთი", 0.4, "Poti", note="port")),
    logistics=0.9, trade_regime="fta", scripts=("georgian", "cyrillic", "latin"),
    aliases=("georgia", "gürcistan", "საქართველო", "sakartvelo")))
_add(CountryConfig("AZ", "Azerbaijan", "Azerbaycan", "caucasus", ("az", "ru", "en"), (
    C("Bakı", 0.95, "Baku"), C("Gəncə", 0.6, "Ganja"), C("Sumqayıt", 0.5, "Sumgait"), C("Naxçıvan", 0.45, "Nakhchivan", note="TR border")),
    logistics=0.8, trade_regime="mfn", scripts=("latin", "cyrillic"), aliases=("azerbaijan", "azerbaycan")))
_add(CountryConfig("AM", "Armenia", "Ermenistan", "caucasus", ("hy", "ru", "en"), (
    C("Երևան", 0.95, "Yerevan"), C("Գյումրի", 0.5, "Gyumri"), C("Վանաձոր", 0.4, "Vanadzor")),
    logistics=0.5, scripts=("armenian", "cyrillic", "latin"), aliases=("armenia", "ermenistan", "hayastan"),
    notes="TR–AM land border closed; shipments route via Georgia. Verify current status."))


def get_country(iso2: str) -> CountryConfig | None:
    return COUNTRIES.get(iso2.upper())


def resolve_country(text: str) -> CountryConfig | None:
    t = text.strip().lower()
    if len(t) == 2 and t.upper() in COUNTRIES:
        return COUNTRIES[t.upper()]
    for cfg in COUNTRIES.values():
        if t == cfg.name_en.lower() or t == cfg.name_tr.lower() or t in cfg.aliases:
            return cfg
    return None


def find_countries_in_text(text: str) -> list[str]:
    """Extract ISO codes mentioned in a free-text request (Turkish/English/local names)."""
    low = text.lower()
    found: list[tuple[int, str]] = []
    for cfg in COUNTRIES.values():
        names = {cfg.name_en.lower(), cfg.name_tr.lower(), *[a.lower() for a in cfg.aliases]}
        for n in names:
            if len(n) < 3:
                continue
            idx = _find_word(low, n)
            if idx >= 0:
                found.append((idx, cfg.iso2))
                break
    found.sort()
    out: list[str] = []
    for _, iso in found:
        if iso not in out:
            out.append(iso)
    return out


def _find_word(haystack: str, needle: str) -> int:
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return -1
        before = haystack[idx - 1] if idx > 0 else " "
        # allow Turkish suffixes after the name ("Almanya'da", "Fas'ta") but require a boundary before
        if not before.isalnum():
            return idx
        start = idx + 1
