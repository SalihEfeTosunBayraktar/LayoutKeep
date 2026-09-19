"""The welcome screen's copy, in the interface languages.

Kept apart from `welcome.py` on purpose: the screen is a small amount of behaviour and a large
amount of prose, and mixing the two makes either one hard to change. The user asked for a
detailed first-run introduction - how to make a first translation, what each setting does, what a
local provider means, what decides quality - so the prose is the feature here.

Turkish first (the interface defaults to English, and this is the language the project is
explained in), then English and German.
"""

from __future__ import annotations

#: Page keys in the order they are shown.
PAGES = ("hello", "first", "provider", "quality", "done")

_TEXT: dict[str, dict[str, dict[str, str]]] = {
    "tr": {
        "hello": {
            "title": "LayoutKeep'e hoş geldin",
            "lead": (
                "LayoutKeep bir belgeyi çevirirken sayfadaki yerleşimi korur: yazı tipi, punto, "
                "satır konumu, tablolar ve görseller yerinde kalır; yalnız metin değişir."
            ),
            "bullets": (
                "PDF, EPUB, DOCX, PNG ve JPG okur; çıktıyı aynı düzende yazar.\n"
                "Yerel bir modelle (LM Studio) ya da bulut sağlayıcıyla çalışır; ikisi de ayarlardan seçilir.\n"
                "Kayıpsız mod, yazdığı sayfayı kaynağıyla karşılaştırıp kaybı (düşen sayfa, çevrilmemiş "
                "metin, üst üste binen yazı, görselin üstüne binen metin) raporlar.\n"
                "Şüpheli bulduğu yerleri inceleme kuyruğuna işaretler; hiçbir şeyi sessizce geçmez."
            ),
            "setup": "Bu ekrandan dilini ve temanı seçebilirsin:",
        },
        "first": {
            "title": "İlk çevirin: üç adım",
            "bullets": (
                "1. Belgeyi pencereye sürükle ya da “Gözat” ile seç. Türüne göre hangi çıktı "
                "biçimlerinin açık olduğunu uygulama gösterir.\n"
                "2. Kaynak ve hedef dili, sonra sağlayıcıyı seç. Uzun belgelerde paralel işçi sayısı "
                "(varsayılan 7) modelin yuva sayısıyla eşleşmeli.\n"
                "3. “Çeviriyi Başlat”a bas. Belge okunur, metinler çevrilir, çeviri kutulara "
                "sığdırılır, çıktı yazılır ve yazılan sayfa kaynağıyla doğrulanır."
            ),
            "float": (
                "Uzun belgelerde ekranın üstünde küçük bir ilerleme çubuğu belirir: hangi belge, "
                "hangi aşama, kaç parça bitti ve yüzde. Üzerinden sürükleyebilir, “—” ile minik bir "
                "hapa indirebilir, bitince çıktıyı oradan açabilirsin."
            ),
            "phases": "Aşamalar: okuma → çeviri → sığdırma → yazma → doğrulama",
        },
        "provider": {
            "title": "Çeviriyi kim yapıyor?",
            "lead": (
                "İki yol var; ikisi de aynı boru hattını besler, fark yalnızca metni kimin çevirdiği:"
            ),
            "bullets": (
                "Yerel (LM Studio): ücretsiz ve çevrimdışı. Model bu makinede koşar, bağlam penceresi "
                "paralel yuvalara bölünür — 7 işçi için -c 32768 önerilir, yoksa uzun istekler taşar.\n"
                "Bulut (OpenAI uyumlu ya da DeepL): hızlı ve güçlü, API anahtarı ve internet ister; "
                "ücret sağlayıcının fiyatlandırmasına bağlıdır.\n"
                "Sağlayıcı ayarlarından uç nokta ekleyip “Test Et” ile anahtarı kaydetmeden denersin."
            ),
            "local_hint": (
                "LM Studio ile başlamak için: modeli yükle, sunucuyu aç, adresi "
                "http://127.0.0.1:1234/v1 olarak bırak."
            ),
        },
        "quality": {
            "title": "Kaliteyi ne belirler?",
            "lead": (
                "Aynı ayarla bile sonuç belgeden belgeye değişir. Sıralı etkisi şu:"
            ),
            "bullets": (
                "Belgenin türü: dijital PDF ve EPUB neredeyse birebir korunur; taranmış sayfa ve "
                "fotoğraf ağırlıklı belgeler daha kırılgandır (metin önce okunur, sonra yerine yazılır).\n"
                "Tarama kalitesi: 300 dpi ve üzeri temiz taramalar okunaklı olur; eğik, lekeli ya da "
                "düşük çözünürlüklü sayfalar OCR'da karakter kaybeder.\n"
                "Modelin dil becerisi: yerel küçük modeller terim ve deyimlerde zayıflar; hedef dilde "
                "güçlü bir model (ya da bulut sağlayıcı) belirgin fark yaratır.\n"
                "Dil çifti: İngilizce→Türkçe ortalama 0.93x uzunlukta çıkar, ama blok blok 0.64x–1.40x "
                "arasında gezer; kısa kalan yerler inceleme bayrağı alır.\n"
                "Tablolar ve formlar: hücreye sığmayan çeviri küçültülür ya da işaretlenir; en çok "
                "bayrak buralarda çıkar."
            ),
        },
        "done": {
            "title": "Hazırsın",
            "lead": (
                "Karşılaştırma sitesinden gerçek örnekleri yan yana inceleyebilir, gelişmiş "
                "ayarlardan sığdırma davranışını değiştirebilirsin."
            ),
            "bullets": (
                "İnceleme bayrakları: bitince kaç blok işaretlendiğini ve nedenini gösterir.\n"
                "Gelişmiş ayarlar: sığdırma sınırları, işçi sayısı, yüzen çubuk ve daha fazlası.\n"
                "Bu ekranı sonra yeniden görmek için: Gelişmiş Ayarlar → “Karşılamayı göster”."
            ),
            "skip": "Atla",
            "back": "Geri",
            "next": "İleri",
            "start": "Çeviriye başla",
            "never": "Bir daha gösterme",
        },
    },
    "en": {
        "hello": {
            "title": "Welcome to LayoutKeep",
            "lead": (
                "LayoutKeep translates a document without moving anything on its page: typeface, "
                "size, line positions, tables and images stay where they were; only the text changes."
            ),
            "bullets": (
                "Reads PDF, EPUB, DOCX, PNG and JPG, and writes the output in the same layout.\n"
                "Runs against a local model (LM Studio) or a cloud provider; both are chosen in settings.\n"
                "Lossless mode compares every written page with its source and reports what was lost "
                "(a dropped page, untranslated text, text over text, text over a figure).\n"
                "Anything it is unsure about goes to the review queue; nothing is lost silently."
            ),
            "setup": "Pick your language and theme right here:",
        },
        "first": {
            "title": "Your first translation: three steps",
            "bullets": (
                "1. Drop the document on the window, or pick it with “Browse”. The application shows "
                "which output formats that type can produce.\n"
                "2. Choose the source and target language, then the provider. On long documents the "
                "worker count (7 by default) should match the model's parallel slots.\n"
                "3. Press “Start translation”. The document is read, the text is translated, the "
                "translation is fitted into its boxes, the output is written, and the written page is "
                "verified against the source."
            ),
            "float": (
                "Long documents raise a small bar at the top of the screen: which document, which "
                "phase, how many segments are done and the percentage. Drag it anywhere, fold it to a "
                "pill with “—”, and open the output from it when the run ends."
            ),
            "phases": "Phases: read → translate → fit → write → verify",
        },
        "provider": {
            "title": "Who does the translating?",
            "lead": "Two routes, the same pipeline — only the translator differs:",
            "bullets": (
                "Local (LM Studio): free and offline. The model runs on this machine, and its context "
                "window is shared across parallel slots — use -c 32768 for 7 workers, or long requests "
                "overflow.\n"
                "Cloud (OpenAI-compatible or DeepL): fast and strong, needs an API key and a "
                "connection; cost follows the provider's pricing.\n"
                "In provider settings you add an endpoint and test the key with “Test” before saving."
            ),
            "local_hint": (
                "To start with LM Studio: load a model, start the server, and leave the address at "
                "http://127.0.0.1:1234/v1."
            ),
        },
        "quality": {
            "title": "What decides quality?",
            "lead": "Even with the same settings, results differ per document. In order of impact:",
            "bullets": (
                "The document's kind: digital PDF and EPUB survive almost exactly; scanned pages and "
                "image-heavy books are more fragile (text is read, then written back).\n"
                "Scan quality: clean 300 dpi scans read well; skewed, stained or low-resolution pages "
                "lose characters in OCR.\n"
                "The model's language skill: small local models are weak on terms and idioms; a model "
                "strong in the target language (or a cloud provider) makes a visible difference.\n"
                "The language pair: English→Turkish comes out at 0.93x on average, but per block it "
                "ranges 0.64x–1.40x; the short ones get a review flag.\n"
                "Tables and forms: a translation that will not fit its cell is shrunk or flagged, and "
                "that is where most flags come from."
            ),
        },
        "done": {
            "title": "You are ready",
            "lead": (
                "The comparison site shows real held-out documents side by side, and the advanced "
                "settings change how the fitting behaves."
            ),
            "bullets": (
                "Review flags: the completion screen shows how many blocks were flagged and why.\n"
                "Advanced settings: fitting limits, worker count, the floating bar and more.\n"
                "See this screen again any time: Advanced Settings → “Show the welcome screen”."
            ),
            "skip": "Skip",
            "back": "Back",
            "next": "Next",
            "start": "Start translating",
            "never": "Do not show this again",
        },
    },
    "de": {
        "hello": {
            "title": "Willkommen bei LayoutKeep",
            "lead": (
                "LayoutKeep übersetzt ein Dokument, ohne das Seitenlayout zu verschieben: Schriftart, "
                "Größe, Zeilenpositionen, Tabellen und Bilder bleiben, nur der Text ändert sich."
            ),
            "bullets": (
                "Liest PDF, EPUB, DOCX, PNG und JPG und schreibt die Ausgabe im selben Layout.\n"
                "Läuft mit einem lokalen Modell (LM Studio) oder einem Cloud-Anbieter.\n"
                "Der verlustfreie Modus vergleicht jede geschriebene Seite mit der Quelle.\n"
                "Unsicheres landet in der Prüfliste; nichts geht still verloren."
            ),
            "setup": "Sprache und Thema wählst du gleich hier:",
        },
        "first": {
            "title": "Die erste Übersetzung: drei Schritte",
            "bullets": (
                "1. Dokument ins Fenster ziehen oder über „Durchsuchen“ wählen.\n"
                "2. Quell- und Zielsprache wählen, dann den Anbieter.\n"
                "3. „Übersetzung starten“ drücken: lesen, übersetzen, einpassen, schreiben, prüfen."
            ),
            "float": (
                "Lange Dokumente zeigen oben eine kleine Leiste: Dokument, Phase, Abschnitte und "
                "Prozent. Sie lässt sich verschieben, mit „—“ einklappen und öffnet am Ende die Ausgabe."
            ),
            "phases": "Phasen: lesen → übersetzen → einpassen → schreiben → prüfen",
        },
        "provider": {
            "title": "Wer übersetzt?",
            "lead": "Zwei Wege, dieselbe Verarbeitung — nur der Übersetzer unterscheidet sich:",
            "bullets": (
                "Lokal (LM Studio): kostenlos und offline; der Kontext wird über parallele Slots "
                "geteilt (-c 32768 für 7 Worker).\n"
                "Cloud (OpenAI-kompatibel oder DeepL): schnell und stark, braucht Schlüssel und "
                "Verbindung."
            ),
            "local_hint": "Mit LM Studio: Modell laden, Server starten, Adresse http://127.0.0.1:1234/v1 lassen.",
        },
        "quality": {
            "title": "Was bestimmt die Qualität?",
            "lead": "Auch bei gleichen Einstellungen unterscheiden sich die Ergebnisse:",
            "bullets": (
                "Art des Dokuments: digitales PDF und EPUB bleiben fast exakt; Scans sind brüchiger.\n"
                "Scan-Qualität: saubere 300 dpi lesen gut, schiefe oder fleckige Seiten verlieren Zeichen.\n"
                "Sprachfähigkeit des Modells: kleine lokale Modelle schwächeln bei Fachbegriffen.\n"
                "Sprachpaar: Englisch→Türkisch ergibt im Mittel 0.93x, pro Block 0.64x–1.40x."
            ),
        },
        "done": {
            "title": "Fertig",
            "lead": "Die Vergleichsseite zeigt echte Beispiele nebeneinander.",
            "bullets": (
                "Markierungen: wie viele Blöcke geprüft werden müssen.\n"
                "Erweiterte Einstellungen: Einpassgrenzen, Worker, schwebende Leiste."
            ),
            "skip": "Überspringen",
            "back": "Zurück",
            "next": "Weiter",
            "start": "Übersetzung starten",
            "never": "Nicht mehr anzeigen",
        },
    },
}


def text(language: str, page: str, key: str) -> str:
    """One string of the welcome copy, falling back the way the interface does."""
    active = _TEXT.get(language) or _TEXT["en"]
    page_text = active.get(page, {})
    if key in page_text:
        return page_text[key]
    return _TEXT["en"].get(page, {}).get(key, "")
