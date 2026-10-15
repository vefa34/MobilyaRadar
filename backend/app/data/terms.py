# -*- coding: utf-8 -*-
"""Multilingual trade terminology.

These are the commercial terms that buyers actually use in each market (directory category names,
how wholesalers describe themselves, etc.), not word-for-word translations. Entries flagged in
``REVIEW_NEEDED`` should be validated by a native-speaking sales person; the LLM-based expander
(services.query_generator) can extend these lists at runtime, but every LLM suggestion is stored
separately and never overrides curated terms.
"""

# Generic "furniture" word per language (used as fallback and for classification).
FURNITURE_WORD = {
    "en": ["furniture"], "de": ["Möbel"], "fr": ["meubles", "mobilier"], "ar": ["أثاث", "اثاث", "موبيليا"],
    "ru": ["мебель"], "ka": ["ავეჯი"], "hy": ["կահույք"], "az": ["mebel"], "it": ["mobili", "arredamento"],
    "es": ["muebles", "mobiliario"], "nl": ["meubelen", "meubels"], "pl": ["meble"], "ro": ["mobilă", "mobila"],
    "cs": ["nábytek"], "sk": ["nábytok"], "bg": ["мебели"], "el": ["έπιπλα"], "sr": ["namještaj", "nameštaj", "намештај"],
    "ku": ["کەلوپەلی ناوماڵ", "mobîlya"], "tr": ["mobilya"],
}

# Product category -> language -> terms (most specific first).
PRODUCT_TERMS: dict[str, dict[str, list[str]]] = {
    "dining_table": {
        "en": ["dining table", "dining tables", "dining furniture"],
        "de": ["Esstisch", "Esstische", "Esszimmermöbel"],
        "fr": ["table à manger", "table de salle à manger", "mobilier salle à manger"],
        "ar": ["طاولة طعام", "طاولات طعام", "سفرة", "غرف سفرة"],
        "ru": ["обеденный стол", "обеденные столы", "столы для кухни"],
        "ka": ["სასადილო მაგიდა", "მაგიდები"],
        "hy": ["ճաշասեղան", "սեղաններ"],
        "az": ["yemək masası", "masalar"],
        "it": ["tavolo da pranzo", "tavoli"], "es": ["mesa de comedor", "mesas de comedor"],
        "nl": ["eettafel", "eettafels"], "pl": ["stół do jadalni", "stoły"], "ro": ["masă dining", "mese dining"],
        "cs": ["jídelní stůl", "jídelní stoly"], "sk": ["jedálenský stôl"], "bg": ["трапезна маса", "маси"],
        "el": ["τραπέζι τραπεζαρίας"], "sr": ["trpezarijski sto", "stolovi"], "tr": ["yemek masası"],
        "ku": ["مێزی نانخواردن"],
    },
    "chair": {
        "en": ["chairs", "dining chairs", "chair"],
        "de": ["Stühle", "Esszimmerstühle", "Stuhl"],
        "fr": ["chaises", "chaises de salle à manger", "sièges"],
        "ar": ["كراسي", "كراسي طعام", "كرسي"],
        "ru": ["стулья", "обеденные стулья"],
        "ka": ["სკამები", "სკამი"], "hy": ["աթոռներ", "աթոռ"], "az": ["stullar", "stul"],
        "it": ["sedie"], "es": ["sillas"], "nl": ["stoelen", "eetkamerstoelen"], "pl": ["krzesła"],
        "ro": ["scaune"], "cs": ["židle"], "sk": ["stoličky"], "bg": ["столове"], "el": ["καρέκλες"],
        "sr": ["stolice"], "tr": ["sandalye"], "ku": ["کورسی"],
    },
    "sofa": {
        "en": ["sofas", "sofa", "couches", "upholstered furniture"],
        "de": ["Sofas", "Polstermöbel", "Couch", "Wohnlandschaften"],
        "fr": ["canapés", "canapé", "salons"],
        "ar": ["كنب", "كنبات", "صالونات", "أطقم كنب"],
        "ru": ["диваны", "мягкая мебель"],
        "ka": ["დივანი", "რბილი ავეჯი"], "hy": ["բազմոց", "փափուկ կահույք"], "az": ["divan", "yumşaq mebel"],
        "it": ["divani", "imbottiti"], "es": ["sofás", "tapizados"], "nl": ["banken", "zitbanken"],
        "pl": ["sofy", "meble tapicerowane"], "ro": ["canapele", "mobilier tapițat"], "cs": ["pohovky", "sedačky"],
        "sk": ["sedačky", "pohovky"], "bg": ["дивани", "мека мебел"], "el": ["καναπέδες"], "sr": ["sofe", "garniture"],
        "tr": ["koltuk takımı", "kanepe"], "ku": ["قەنەفە"],
    },
    "armchair": {
        "en": ["armchairs"], "de": ["Sessel"], "fr": ["fauteuils"], "ar": ["كراسي بذراعين", "فوتيه"],
        "ru": ["кресла"], "ka": ["სავარძელი"], "hy": ["բազկաթոռ"], "az": ["kreslo"], "it": ["poltrone"],
        "es": ["sillones"], "nl": ["fauteuils"], "pl": ["fotele"], "ro": ["fotolii"], "cs": ["křesla"],
        "sk": ["kreslá"], "bg": ["фотьойли"], "el": ["πολυθρόνες"], "sr": ["fotelje"], "tr": ["berjer"],
    },
    "bed": {
        "en": ["beds", "bedroom furniture"], "de": ["Betten", "Schlafzimmermöbel"],
        "fr": ["lits", "chambres à coucher"], "ar": ["أسرة", "غرف نوم"], "ru": ["кровати", "спальни"],
        "ka": ["საწოლი", "საძინებელი"], "hy": ["մահճակալ", "ննջասենյակ"], "az": ["çarpayı", "yataq otağı"],
        "it": ["letti", "camere da letto"], "es": ["camas", "dormitorios"], "nl": ["bedden", "slaapkamers"],
        "pl": ["łóżka", "sypialnie"], "ro": ["paturi", "dormitoare"], "cs": ["postele", "ložnice"],
        "sk": ["postele", "spálne"], "bg": ["легла", "спални"], "el": ["κρεβάτια", "κρεβατοκάμαρες"],
        "sr": ["kreveti", "spavaće sobe"], "tr": ["yatak odası"],
    },
    "cabinet": {
        "en": ["cabinets", "wardrobes", "storage furniture", "sideboards"],
        "de": ["Schränke", "Kleiderschränke", "Sideboards"], "fr": ["armoires", "buffets", "rangement"],
        "ar": ["خزائن", "دواليب", "بوفيه"], "ru": ["шкафы", "комоды"], "ka": ["კარადა"], "hy": ["պահարան"],
        "az": ["şkaf", "dolab"], "it": ["armadi", "credenze"], "es": ["armarios", "aparadores"],
        "nl": ["kasten", "dressoirs"], "pl": ["szafy", "komody"], "ro": ["dulapuri", "comode"],
        "cs": ["skříně", "komody"], "sk": ["skrine"], "bg": ["гардероби", "шкафове"], "el": ["ντουλάπες"],
        "sr": ["ormari"], "tr": ["dolap"],
    },
    "office_furniture": {
        "en": ["office furniture", "office chairs", "office desks"], "de": ["Büromöbel", "Bürostühle"],
        "fr": ["mobilier de bureau", "sièges de bureau"], "ar": ["أثاث مكتبي", "أثاث مكاتب", "كراسي مكتب"],
        "ru": ["офисная мебель", "офисные кресла"], "ka": ["საოფისე ავეჯი"], "hy": ["գրասենյակային կահույք"],
        "az": ["ofis mebeli"], "it": ["mobili per ufficio"], "es": ["mobiliario de oficina"],
        "nl": ["kantoormeubelen"], "pl": ["meble biurowe"], "ro": ["mobilier de birou"], "cs": ["kancelářský nábytek"],
        "sk": ["kancelársky nábytok"], "bg": ["офис мебели"], "el": ["έπιπλα γραφείου"], "sr": ["kancelarijski nameštaj"],
        "tr": ["ofis mobilyası"],
    },
    "hotel_furniture": {
        "en": ["hotel furniture", "contract furniture", "hospitality furniture", "FF&E"],
        "de": ["Hotelmöbel", "Objektmöbel", "Objekteinrichtung"], "fr": ["mobilier hôtelier", "mobilier CHR", "agencement hôtel"],
        "ar": ["أثاث فنادق", "أثاث فندقي", "تجهيز فنادق"], "ru": ["мебель для гостиниц", "мебель для отелей"],
        "ka": ["სასტუმროს ავეჯი"], "hy": ["հյուրանոցային կահույք"], "az": ["otel mebeli"],
        "it": ["arredamento contract", "arredo alberghiero"], "es": ["mobiliario contract", "mobiliario hotelero"],
        "nl": ["projectinrichting", "hotelmeubilair"], "pl": ["meble hotelowe"], "ro": ["mobilier hotelier"],
        "cs": ["hotelový nábytek"], "sk": ["hotelový nábytok"], "bg": ["хотелско обзавеждане"], "el": ["ξενοδοχειακός εξοπλισμός"],
        "sr": ["hotelski nameštaj"], "tr": ["otel mobilyası"],
    },
    "restaurant_furniture": {
        "en": ["restaurant furniture", "cafe furniture", "horeca furniture"], "de": ["Gastronomiemöbel", "Restaurantmöbel"],
        "fr": ["mobilier restaurant", "mobilier CHR", "chaises restaurant"], "ar": ["أثاث مطاعم", "أثاث مقاهي", "كراسي مطاعم"],
        "ru": ["мебель для ресторанов", "мебель для кафе"], "ka": ["რესტორნის ავეჯი"], "hy": ["ռեստորանային կահույք"],
        "az": ["restoran mebeli"], "it": ["arredamento bar ristoranti"], "es": ["mobiliario hostelería"],
        "nl": ["horecameubilair"], "pl": ["meble gastronomiczne"], "ro": ["mobilier horeca"], "cs": ["gastro nábytek"],
        "sk": ["gastro nábytok"], "bg": ["мебели за заведения"], "el": ["έπιπλα εστίασης"], "sr": ["ugostiteljski nameštaj"],
        "tr": ["kafe restoran mobilyası"],
    },
    "kitchen_furniture": {
        "en": ["kitchen furniture", "kitchen cabinets"], "de": ["Küchenmöbel", "Küchen"], "fr": ["meubles de cuisine", "cuisines"],
        "ar": ["مطابخ", "خزائن مطبخ"], "ru": ["кухонная мебель", "кухни"], "ka": ["სამზარეულოს ავეჯი"],
        "hy": ["խոհանոցային կահույք"], "az": ["mətbəx mebeli"], "it": ["cucine"], "es": ["muebles de cocina"],
        "nl": ["keukens"], "pl": ["meble kuchenne"], "ro": ["mobilier bucătărie"], "cs": ["kuchyňský nábytek"],
        "sk": ["kuchynský nábytok"], "bg": ["кухненски мебели"], "el": ["έπιπλα κουζίνας"], "sr": ["kuhinjski nameštaj"],
        "tr": ["mutfak mobilyası"],
    },
    "outdoor_furniture": {
        "en": ["garden furniture", "outdoor furniture"], "de": ["Gartenmöbel", "Outdoormöbel"], "fr": ["mobilier de jardin"],
        "ar": ["أثاث حدائق", "أثاث خارجي"], "ru": ["садовая мебель"], "ka": ["ბაღის ავეჯი"], "hy": ["այգու կահույք"],
        "az": ["bağ mebeli"], "it": ["arredo giardino"], "es": ["muebles de jardín"], "nl": ["tuinmeubelen"],
        "pl": ["meble ogrodowe"], "ro": ["mobilier de grădină"], "cs": ["zahradní nábytek"], "sk": ["záhradný nábytok"],
        "bg": ["градински мебели"], "el": ["έπιπλα κήπου"], "sr": ["baštenski nameštaj"], "tr": ["bahçe mobilyası"],
    },
    "home_furniture": {lang: words for lang, words in FURNITURE_WORD.items()},
}

PRODUCT_LABELS = {
    "dining_table": "Dining tables", "chair": "Chairs", "sofa": "Sofas / upholstery", "armchair": "Armchairs",
    "bed": "Beds / bedroom", "cabinet": "Cabinets / storage", "office_furniture": "Office furniture",
    "hotel_furniture": "Hotel / contract furniture", "restaurant_furniture": "Restaurant / HoReCa furniture",
    "kitchen_furniture": "Kitchen furniture", "outdoor_furniture": "Outdoor furniture", "home_furniture": "Home furniture (general)",
}

# Buyer type -> language -> phrase templates. "{p}" is replaced with product term; "{f}" with generic furniture word.
BUYER_TERMS: dict[str, dict[str, list[str]]] = {
    "verified_importer": {  # discovery phrasing only — "verified" status requires shipment evidence
        "en": ["{f} importer", "{p} importer", "{f} import company"],
        "de": ["Möbelimporteur", "Möbel Import", "{p} Import"],
        "fr": ["importateur de meubles", "importateur {p}", "import meubles"],
        "ar": ["مستورد أثاث", "استيراد أثاث", "شركة استيراد {p}"],
        "ru": ["импортер мебели", "импорт мебели", "импортер {p}"],
        "ka": ["ავეჯის იმპორტიორი", "ავეჯის იმპორტი"], "hy": ["կահույքի ներմուծող", "կահույքի ներմուծում"],
        "az": ["mebel idxalatçısı", "mebel idxalı"], "it": ["importatore mobili"], "es": ["importador de muebles"],
        "nl": ["meubelimporteur", "importeur meubelen"], "pl": ["importer mebli"], "ro": ["importator mobilă"],
        "cs": ["dovozce nábytku"], "sk": ["dovozca nábytku"], "bg": ["вносител на мебели"], "el": ["εισαγωγέας επίπλων"],
        "sr": ["uvoznik nameštaja"], "ku": ["هاوردەکەری کەلوپەل"],
    },
    "wholesaler": {
        "en": ["{f} wholesaler", "wholesale {p}", "{f} wholesale"],
        "de": ["Möbelgroßhandel", "{p} Großhandel", "Möbel Großhändler"],
        "fr": ["grossiste mobilier", "grossiste {p}", "grossiste meubles"],
        "ar": ["تجار الأثاث بالجملة", "أثاث بالجملة", "{p} جملة"],
        "ru": ["оптовая продажа мебели", "мебель оптом", "{p} оптом"],
        "ka": ["ავეჯი საბითუმოდ", "საბითუმო ავეჯი"], "hy": ["կահույք մեծածախ", "մեծածախ կահույք"],
        "az": ["topdan mebel", "mebel topdan satış"], "it": ["ingrosso mobili", "grossista mobili"],
        "es": ["mayorista de muebles", "muebles al por mayor"], "nl": ["meubelgroothandel"], "pl": ["hurtownia mebli"],
        "ro": ["mobilă en-gros", "angro mobilă"], "cs": ["velkoobchod nábytek"], "sk": ["veľkoobchod nábytok"],
        "bg": ["мебели на едро"], "el": ["χονδρική επίπλων"], "sr": ["veleprodaja nameštaja"], "ku": ["فرۆشتنی کۆ کەلوپەل"],
    },
    "distributor": {
        "en": ["{f} distributor", "{p} distributor"], "de": ["Möbelvertrieb", "Möbel Distributor", "Möbelagentur"],
        "fr": ["distributeur de meubles", "distributeur {p}", "agent mobilier"],
        "ar": ["موزع أثاث", "وكيل أثاث", "موزع {p}"], "ru": ["дистрибьютор мебели", "дилер мебели"],
        "ka": ["ავეჯის დისტრიბუტორი"], "hy": ["կահույքի դիստրիբյուտոր"], "az": ["mebel distribyutoru", "mebel dileri"],
        "it": ["distributore mobili", "agenzia mobili"], "es": ["distribuidor de muebles"], "nl": ["meubeldistributeur", "meubelagentuur"],
        "pl": ["dystrybutor mebli"], "ro": ["distribuitor mobilă"], "cs": ["distributor nábytku"], "sk": ["distribútor nábytku"],
        "bg": ["дистрибутор на мебели"], "el": ["διανομέας επίπλων"], "sr": ["distributer nameštaja"],
    },
    "retail_chain": {
        "en": ["{f} store chain", "{f} retailer"], "de": ["Möbelhaus", "Einrichtungshaus", "Möbelkette"],
        "fr": ["enseigne de meubles", "chaîne de magasins de meubles"], "ar": ["سلسلة معارض أثاث", "معارض الأثاث"],
        "ru": ["сеть мебельных магазинов", "мебельный гипермаркет"], "ka": ["ავეჯის მაღაზიების ქსელი"],
        "hy": ["կահույքի խանութների ցանց"], "az": ["mebel mağazalar şəbəkəsi"], "it": ["catena negozi mobili"],
        "es": ["cadena de tiendas de muebles"], "nl": ["woonwinkel keten", "meubelzaak"], "pl": ["sieć salonów meblowych"],
        "ro": ["lanț magazine mobilă"], "cs": ["síť prodejen nábytku"], "sk": ["sieť predajní nábytku"],
        "bg": ["верига мебелни магазини"], "el": ["αλυσίδα καταστημάτων επίπλων"], "sr": ["lanac prodavnica nameštaja"],
    },
    "independent_store": {
        "en": ["{f} store", "{f} showroom", "{p} shop"], "de": ["Möbelgeschäft", "Möbelhändler", "Möbel Showroom"],
        "fr": ["magasin de meubles", "showroom meubles"], "ar": ["معرض أثاث", "محل أثاث", "محلات {p}"],
        "ru": ["мебельный магазин", "салон мебели"], "ka": ["ავეჯის მაღაზია", "ავეჯის სალონი"],
        "hy": ["կահույքի խանութ", "կահույքի սրահ"], "az": ["mebel mağazası", "mebel salonu"], "it": ["negozio di mobili"],
        "es": ["tienda de muebles"], "nl": ["meubelwinkel"], "pl": ["salon meblowy", "sklep meblowy"],
        "ro": ["magazin mobilă"], "cs": ["prodejna nábytku"], "sk": ["predajňa nábytku"], "bg": ["мебелен магазин"],
        "el": ["κατάστημα επίπλων"], "sr": ["salon nameštaja"], "ku": ["فرۆشگای کەلوپەل"],
    },
    "ecommerce": {
        "en": ["online {f} store", "buy {p} online"], "de": ["Möbel Onlineshop", "{p} online kaufen"],
        "fr": ["meubles en ligne", "boutique en ligne meubles"], "ar": ["متجر أثاث أونلاين", "أثاث اون لاين"],
        "ru": ["интернет-магазин мебели"], "ka": ["ავეჯის ონლაინ მაღაზია"], "hy": ["կահույքի առցանց խանութ"],
        "az": ["onlayn mebel mağazası"], "it": ["mobili online"], "es": ["tienda online muebles"], "nl": ["meubels online"],
        "pl": ["sklep internetowy meble"], "ro": ["magazin online mobilă"], "cs": ["e-shop nábytek"], "sk": ["e-shop nábytok"],
        "bg": ["онлайн магазин мебели"], "el": ["ηλεκτρονικό κατάστημα επίπλων"], "sr": ["online prodavnica nameštaja"],
    },
    "contract_ffe": {
        "en": ["contract furniture", "hotel furniture supplier", "FF&E procurement"],
        "de": ["Objekteinrichter", "Objektmöbel", "Hoteleinrichtung"], "fr": ["mobilier contract", "agenceur CHR", "mobilier hôtellerie"],
        "ar": ["تجهيز فنادق", "أثاث فنادق", "مشاريع أثاث"], "ru": ["мебель для гостиниц под заказ", "контрактная мебель"],
        "ka": ["სასტუმროს ავეჯის მომწოდებელი"], "hy": ["հյուրանոցային կահույքի մատակարար"], "az": ["otel mebeli təchizatı"],
        "it": ["contract arredamento"], "es": ["contract mobiliario hotel"], "nl": ["projectinrichter"], "pl": ["wyposażenie hoteli"],
        "ro": ["mobilier contract hotel"], "cs": ["vybavení hotelů nábytek"], "sk": ["vybavenie hotelov"],
        "bg": ["обзавеждане на хотели"], "el": ["εξοπλισμός ξενοδοχείων"], "sr": ["opremanje hotela"],
    },
    "brand_private_label": {
        "en": ["furniture brand sourcing", "private label furniture"], "de": ["Möbelmarke", "Eigenmarke Möbel"],
        "fr": ["marque de meubles", "marque propre mobilier"], "ar": ["علامة تجارية أثاث"], "ru": ["мебельный бренд"],
        "it": ["marchio di mobili"], "es": ["marca de muebles"], "nl": ["meubelmerk"], "pl": ["marka mebli"],
        "ro": ["brand mobilă"], "cs": ["značka nábytku"], "sk": ["značka nábytku"], "bg": ["марка мебели"],
        "el": ["μάρκα επίπλων"], "sr": ["brend nameštaja"], "ka": ["ავეჯის ბრენდი"], "hy": ["կահույքի բրենդ"], "az": ["mebel brendi"],
    },
    "interior_procurement": {
        "en": ["interior design fit-out company", "interior contractor"], "de": ["Innenausbau", "Innenarchitekt Einrichtung"],
        "fr": ["architecte d'intérieur agencement", "aménagement intérieur"], "ar": ["شركة تصميم داخلي وتنفيذ", "ديكور وتجهيز"],
        "ru": ["дизайн интерьера комплектация"], "ka": ["ინტერიერის დიზაინი"], "hy": ["ինտերիերի դիզայն"],
        "az": ["interyer dizayn"], "it": ["architettura d'interni"], "es": ["interiorismo"], "nl": ["interieurbouw"],
        "pl": ["aranżacja wnętrz"], "ro": ["amenajări interioare"], "cs": ["interiérový design"], "sk": ["interiérový dizajn"],
        "bg": ["интериорен дизайн"], "el": ["διακόσμηση εσωτερικών χώρων"], "sr": ["enterijer dizajn"],
    },
    "tender_buyer": {
        "en": ["furniture tender", "furniture supply tender"], "de": ["Ausschreibung Möbel"], "fr": ["appel d'offres mobilier"],
        "ar": ["مناقصة أثاث", "مناقصات توريد أثاث"], "ru": ["тендер мебель"], "it": ["gara arredi"], "es": ["licitación mobiliario"],
        "nl": ["aanbesteding meubilair"], "pl": ["przetarg meble"], "ro": ["licitație mobilier"], "cs": ["veřejná zakázka nábytek"],
        "sk": ["tender nábytok"], "bg": ["обществена поръчка мебели"], "el": ["διαγωνισμός επίπλων"], "sr": ["tender nameštaj"],
        "ka": ["ავეჯის ტენდერი"], "hy": ["կահույքի մրցույթ"], "az": ["mebel tenderi"],
    },
}

# Negative filters per language (web search only). Applied contextually: second-hand and job
# filters always; manufacturer exclusion is never applied blindly (see query_generator).
NEGATIVE_TERMS = {
    "en": ["jobs", "vacancy", "used", "second hand", "review"],
    "de": ["Stellenangebot", "Jobs", "gebraucht", "Kleinanzeigen"],
    "fr": ["emploi", "offre d'emploi", "occasion", "leboncoin"],
    "ar": ["وظائف", "مستعمل"],
    "ru": ["вакансии", "б/у", "авито"],
    "ka": ["ვაკანსია", "მეორადი"], "hy": ["աշխատանք", "օգտագործված"], "az": ["vakansiya", "işlənmiş"],
    "it": ["lavoro", "usato"], "es": ["empleo", "segunda mano"], "nl": ["vacature", "tweedehands", "marktplaats"],
    "pl": ["praca", "używane", "olx"], "ro": ["locuri de muncă", "second hand", "olx"], "cs": ["práce", "bazar"],
    "sk": ["práca", "bazár"], "bg": ["работа", "втора употреба"], "el": ["εργασία", "μεταχειρισμένα"], "sr": ["posao", "polovni"],
}

# Classification lexicon: language-agnostic list of signal keywords per buyer type (lowercased,
# matched against company names, directory categories and website text).
CLASSIFIER_SIGNALS: dict[str, list[str]] = {
    "importer": ["importer", "import ", "imports", "importeur", "importateur", "importador", "importatore", "importer mebli",
                 "مستورد", "استيراد", "импорт", "იმპორტ", "ներմուծ", "idxal", "dovozce", "dovozca", "uvoznik",
                 "εισαγωγ", "вносител", "importator"],
    "wholesaler": ["wholesale", "großhandel", "grosshandel", "grossiste", "gros ", "en gros", "mayorista", "ingrosso", "groothandel",
                   "hurtownia", "en-gros", "angro", "velkoobchod", "veľkoobchod", "veleprodaja", "на едро", "χονδρ",
                   "بالجملة", "جملة", "опт", "საბითუმო", "մեծածախ", "topdan", "b2b"],
    "distributor": ["distributor", "distribution", "vertrieb", "distributeur", "distribuidor", "distributore", "distributeur",
                    "dystrybut", "distribuitor", "distribut", "дистрибут", "дилер", "dealer", " agent ", "agentur", "موزع", "وكيل",
                    "დისტრიბუტ", "դիստրիբյուտ", "diler", "διανομ"],
    "retail": ["store", "shop", "showroom", "möbelhaus", "einrichtungshaus", "magasin", "boutique", "tienda", "negozio", "winkel",
               "salon", "sklep", "magazin", "prodejna", "predajňa", "prodavnica", "магазин", "салон", "κατάστημα",
               "معرض", "معارض", "محل", "مفروشات", "მაღაზია", "სალონი", "խանութ", "սրահ", "mağaza", "galeria", "gallery"],
    "chain": ["branches", "filialen", "stores nationwide", "magasins en france", "our stores", "unsere häuser", "nos magasins",
              "فروع", "فروعنا", "филиалы", "магазины сети", "ფილიალები", "մասնաճյուղեր", "filiallar"],
    "ecommerce": ["online shop", "onlineshop", "webshop", "e-shop", "eshop", "add to cart", "in den warenkorb", "ajouter au panier",
                  "añadir al carrito", "aggiungi al carrello", "do koszyka", "в корзину", "أضف إلى السلة", "კალათაში", "զամբյուղ",
                  "səbətə", "checkout", "free delivery", "livraison gratuite", "kostenloser versand"],
    "contract": ["contract", "hospitality", "hotel furniture", "objekt", "objekteinricht", "ff&e", " ffe ", "horeca", " chr ",
                 "fit-out", "fitout", "turnkey", "project furniture", "تجهيز فنادق", "مشاريع", "гостиниц", "проектн"],
    "interior": ["interior design", "innenarchitekt", "architecte d'intérieur", "interiorismo", "interieur", "ديكور", "تصميم داخلي",
                 "дизайн интерьера", "ინტერიერ", "ինտերիեր", "interyer", "aranżacja", "amenajări"],
    "brand": ["our brand", "our collection", "designed in", "unsere kollektion", "notre collection", "private label",
              "eigenmarke", "marque propre", "own brand"],
    "oem": ["oem", "odm", "private label", "contract manufacturing", "sourcing", "outsourc", "lohnfertigung", "sous-traitance",
            "we source", "sourcing office", "global sourcing", "made for us"],
    "manufacturer": ["furniture manufacturer", "we manufacture", "manufacturer of", "our factory", "own factory", "own production",
                     "contract manufacturing", "production facility", "hersteller", "herstellung", "fabrik", "fabricant", "fabrication",
                     "fabricante", "produttore", "fabbrica", "fabrikant", "producent", "producător", "výrobce", "výrobca",
                     "proizvođač", "производител", "κατασκευ", "مصنع", "تصنيع", "производ", "фабрика", "მწარმოებ",
                     "արտադր", "istehsal", "atelier", "workshop"],
    "tender": ["tender", "ausschreibung", "appel d'offres", "licitación", "gara", "aanbesteding", "przetarg", "مناقصة", "тендер"],
    "used": ["used furniture", "second hand", "gebrauchte möbel", "occasion", "مستعمل", "б/у", "secondhand", "antique", "antik"],
}

# Terms that are too generic to be considered part of a company's distinctive name (dedup).
GENERIC_NAME_TOKENS = {
    "furniture", "furnitures", "furnishing", "furnishings", "mobel", "moebel", "mobelhaus", "mobilier", "meubles", "meuble",
    "mobili", "muebles", "meubelen", "meubels", "meble", "mobila", "nabytek", "nabytok", "mebel", "mebeli", "mebelj",
    "nameshtaj", "namestaj", "namjestaj", "epipla", "mobilya", "athath", "athaath", "athath", "home", "house", "living",
    "interiors", "interior", "design", "decor", "deco", "trading", "trade", "group", "company", "co", "store", "shop",
    "showroom", "gallery", "galerie", "center", "centre", "world", "import", "export", "imports", "wholesale",
    "grosshandel", "handel", "the", "and", "et", "und", "de", "la", "le", "les", "al", "el", "branch", "filiale",
    "mobili", "ahvedzhi", "avedzhi", "kahuyk", "kahuyq", "kahuyk'", "mebeli", "branch", "store",
}

# Legal-form suffixes stripped during normalization.
LEGAL_SUFFIXES = {
    "llc", "l.l.c", "ltd", "limited", "inc", "corp", "corporation", "plc", "gmbh", "mbh", "ag", "kg", "ohg", "ug", "gbr", "ek",
    "e.k", "co.kg", "sarl", "s.a.r.l", "sas", "sasu", "sa", "s.a", "eurl", "snc", "srl", "s.r.l", "spa", "s.p.a", "sl", "s.l",
    "bv", "b.v", "nv", "n.v", "vof", "bvba", "sp", "z", "o.o", "zoo", "sro", "s.r.o", "as", "a.s", "ad", "ood", "eood", "doo",
    "d.o.o", "ae", "epe", "ike", "ooo", "ооо", "zao", "оао", "ip", "ип", "wll", "w.l.l", "fzco", "fze", "fz", "fzllc", "est",
    "establishment", "ش.م.م", "ذ.م.م", "شركة", "مؤسسة", "jsc", "cjsc", "pjsc", "mmc", "mmş", "ltd.", "pty", "kft", "zrt", "oy", "ab",
    "aps", "a/s", "sprl", "scs", "scrl", "suarl", "sarlau",
}
