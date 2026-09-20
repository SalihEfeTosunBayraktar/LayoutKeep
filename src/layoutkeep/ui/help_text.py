"""The help screen's copy, in the interface languages.

Separate from `help_dialog.py` for the same reason the welcome screen keeps its prose apart: a
screen is a little behaviour and a lot of text, and the two change for different reasons. The
criteria list is not repeated here — it is read from `verify.LABELS`, so a new criterion appears in
the help screen the moment it exists in the checker.
"""

from __future__ import annotations

#: Section keys in the order they are listed.
SECTIONS = ("first", "provider", "settings", "flags", "criteria", "quality", "output", "trouble")

_TEXT: dict[str, dict[str, dict[str, str]]] = {
    "tr": {
        "first": {
            "title": "İlk çeviri",
            "body": (
                "1. Belgeyi pencereye sürükle ya da Gözat ile seç. Uygulama, seçtiğin türe göre "
                "hangi çıktı biçimlerinin açık olduğunu kendisi belirler.\n"
                "2. Kaynak ve hedef dili seç; ardından sağlayıcıyı (yerel LM Studio ya da bulut).\n"
                "3. Çeviriyi başlat. Uzun belgelerde iş bölümlere ayrılır ve her bölüm bittiğinde "
                "diske yazılır; pencereyi kapatsan bile kaldığın yerden sürdürebilirsin.\n\n"
                "Uzun koşularda pencereyi arkaya atabilirsin: başlıktaki ▤ düğmesi pencereyi "
                "gizler, ilerleme yüzen çubukta devam eder; çubuktaki “Pencereye dön” geri "
                "getirir.\n\n"
                "İş bittiğinde üç şey elinde olur: çevrilmiş dosya, `.lkproj` çalışma dosyası "
                "(yeniden yazmak için) ve kayıpsızlık denetiminin özeti.\n\n"
                "Çift dilli PDF: kurulumda “Çift dilli PDF” kutusunu seçersen çevrilmiş dosyanın "
                "yanına kaynağı da içeren ikinci bir PDF yazılır — “Yan yana” (kaynak solda) ya da "
                "“Almaşık sayfalar”. Asıl çıktı ve denetim değişmez.\n"
                "Sayfa aralığı: yalnız seçtiğin sayfalar çevrilir ve çıktı yalnız o sayfaları "
                "içerir; kaydedilen `.lkproj` ise belgenin tamamını saklar, böylece inceleme "
                "ekranında geri kalanı da görürsün ve yeniden dışa aktarma belgeyi sessizce "
                "kısaltmaz."
            ),
        },
        "provider": {
            "title": "Sağlayıcı seçimi",
            "body": (
                "Yerel (LM Studio, Ollama): ücretsiz, çevrimdışı, belge makineden çıkmaz. Kalite "
                "yüklediğin modele bağlıdır.\n"
                "Bulut (OpenAI uyumlu ya da DeepL): daha güçlü modeller, daha hızlı; metin "
                "sağlayıcıya gider ve genelde ücretlidir.\n\n"
                "Yerel sunucuda iki ayar önemlidir: bağlam penceresi ve paralel yuva sayısı. Bağlam "
                "penceresi yuvalara bölünür: paralellik varsayılan 2'dir ve 8192'lik pencere istek başına "
                "~4k token bırakır; işçiyi 7'ye çıkarırsanız (sunucuda 7 yuva varsa) istek başına "
                "~1.2k kalır ve uzun paragraflar taşar. LM Studio'da -c 32768 ile 7 işçi rahat "
                "çalışır (istek başına ~4.7k token). Taşma artık ölümcül değil (parça cümle sınırından bölünür) ama "
                "yavaşlatır."
            ),
        },
        "settings": {
            "title": "Ayarların anlamı",
            "body": (
                "Genel sekmesi: işçi sayısı (sunucunun yuva sayısıyla eşleşmeli), tekrarlanan "
                "metni bir kez çevirme, çeviri belleği (koşular arası SQLite; aynı belgeyi yeniden "
                "çevirmeyi ucuzlatır) ve terim sözlüğü. Sözlüğü “Düzenle…” ile tablo hâlinde "
                "yazabilir, JSON ya da iki sütunlu CSV/TSV yükleyebilirsin; kullanılmayan terim "
                "inceleme kuyruğuna düşer.\n"
                "Ayarların tepesindeki hazır ayar birkaç değeri birlikte değiştirir: “Hızlı "
                "taslak” (7 istek, okunabilirlik tabanı 0.80, kısaltma isteme kapalı) okunacak ilk "
                "geçiş için, “Yayın kalitesi” (2 istek, ölçülmüş eşikler) saklanacak çıktı için. "
                "Sonrasında tek tek düzenleyebilirsin; bir değer değiştiyse kutu “Özel” der.\n"
                "Sözlük düzenleyicisindeki “Belgeden öner” kurulumdaki dosyada sık geçen terim "
                "adaylarını boş hedef hücreleriyle ekler; çevirilerini sen yazarsın.\n"
                "Geliştirici sekmesi: sığdırma ve parti büyüklüğü eşikleri. Buradaki değerler "
                "yanlış olduğunda hata vermez, sessizce daha kötü çıktı üretir; bu yüzden her "
                "birinin yanında ne bozulduğu yazılıdır.\n\n"
                "Değişiklikler anında etkilidir; koşan bir iş başladığı değerlerle devam eder."
            ),
        },
        "flags": {
            "title": "İnceleme bayrakları",
            "body": (
                "Her bayrak bir blok için 'buraya bak' demektir; hiçbiri sessiz geçilmez:\n\n"
                "• çeviri kutuya sığmadı, küçültme yetmedi — metin kısaltılamadı ve kutu yetmedi.\n"
                "• kalın/italik biçimlendirme kayboldu — çeviri gövde metnine indi.\n"
                "• model metni çevirmeden aynen geri verdi — çıktı kaynakla aynı.\n"
                "• partinin tamamı çevrilemedi — istek başarısız oldu ve kurtarılamadı.\n"
                "• sözlük terimi çeviride kullanılmamış — terim politikasına uyulmadı.\n"
                "• Sayfa alt sınırını aştı — blok sayfanın dışına taştı.\n"
                "• DeepL bu segmenti yanıtlamadı — sağlayıcı boş döndü."
            ),
        },
        "criteria": {
            "title": "Kayıpsızlık kriterleri",
            "body": (
                "Denetim, yazılan sayfayı kaynağıyla karşılaştırır. L ile başlayanlar kayıp, D ile "
                "başlayanlar betimleyicidir (kayıp sayılmaz, ama bakılması gerekir). Aşağıdaki "
                "liste denetimin kendi kodundan okunur."
            ),
        },
        "quality": {
            "title": "Çevirinin kalitesini ne belirler",
            "body": (
                "Aynı belge farklı koşullarda farklı sonuç verir. Etkisi en büyükten küçüğe:\n\n"
                "• Modelin dil becerisi — en büyük tek faktör. Yerel küçük bir modelle öncü bir "
                "bulut modeli deyimlerde yakın değildir; hangi modeli seçtiğin çevirinin "
                "okunurluğunu belirler.\n"
                "• Belge dijital mi, tarama mı — dijital PDF kendi yazı tiplerini, boyutlarını ve "
                "koordinatlarını taşır, stiller korunur; tarama OCR'dan geçer ve tanıma hataları "
                "metne karışabilir.\n"
                "• Tarama çözünürlüğü — kabaca 200 dpi altında OCR küçük puntoyu ve üst simgeleri "
                "kaybetmeye başlar; yanlış karakter, yanlış çeviridir.\n"
                "• Belge türü — düz metin geniş kutulara akar; formun ve tablonun kutuları tam bir "
                "satır yüksekliğindedir ve sığdırma orada küçültmek zorunda kalır. Formüller, kod "
                "ve figürler bilerek dokunulmadan bırakılır.\n"
                "• Kaynağın kendi düzeni — dar kolonlar, üst üste binen kutular ve figürün "
                "etrafına sarılan metin, çevirinin kullanabileceği yeri daraltır.\n"
                "• Çeviri yönü — Türkçe eklemeli bir dildir: İngilizceye çevrilirken kısalır, "
                "İngilizceden çevrilirken uzar. Aynı paragraf her yönde farklı yer ister.\n"
                "• Terim sözlüğü ve çeviri belleği — sözlük sözcükleri sabitler; bellek tekrar "
                "eden metni bir kez çevirir ve her yerde aynı bırakır.\n"
                "• Ayarların — kayıpsız mod, tekrar birleştirme ve parça parça onarım hız ile "
                "sadakat arasında takas yapar; varsayılanlar kayıpsız olanlardır.\n\n"
                "Özet: okunurluğu model belirler, düzenin ayakta kalmasını belge belirler, "
                "ikisinin de doğru olduğunu denetim söyler."
            ),
        },
        "output": {
            "title": "Çıktılar nerede",
            "body": (
                "Çevrilmiş dosya: seçtiğin yol.\n"
                "Çalışma dosyası: aynı adla `.lkproj` — yeniden yazmak, incelemek ya da başka bir "
                "biçimde dışa aktarmak için gereken her şey.\n"
                "Denetim: komut satırında `tools/audit/lossless_audit.py --work <koşu dizini>`; "
                "uygulamada tamamlanma ekranındaki özet sayılar.\n"
                "İnceleme bayrakları: tamamlanma ekranı “N parça inceleme bekliyor” diyorsa, o "
                "parçalar ya kutusuna sığmadı ya bir sayıyı/korunan değeri düşürdü. Ekran ayrıca "
                "kaç tanesinin kutu kısaltmasından olduğunu söyler: onlar metnin uzunluğuyla "
                "değil sayfa düzeniyle ilgilidir — aynı metni yeniden çevirmek çözmez.\n"
                "Çökme günlüğü: veri klasöründeki `crash.log` (uygulama beklenmedik kapanırsa)."
            ),
        },
        "trouble": {
            "title": "Sorun giderme",
            "body": (
                "“Model bulunamadı veya yüklenmedi” — çoğu zaman model yüklü ve çalışıyordur; "
                "gerçek sebep sunucunun yanıt gövdesindedir. En sık görüleni bağlam taşmasıdır "
                "(yukarıdaki sağlayıcı bölümüne bak).\n"
                "“Sunucu yanıt vermedi (timeout)” — büyük bir modelin yüklenmesi dakikalar sürer; "
                "Sağlayıcı Ayarları'ndan zaman aşımını yükselt.\n"
                "“adresine ulaşılamıyor” — LM Studio (1234) ya da Ollama (11434) çalışmıyor, ya da "
                "sunucu modu kapalı.\n"
                "Taramalarda okunamayan sayfa — eğik/lekeli taramalarda OCR düşer; inceleme "
                "bayrakları hangi sayfada olduğunu söyler.\n"
                "Uzun bir belgede iş kesildi — `.lkproj` dosyaları durur; aynı işi `--resume` ile "
                "yeniden başlatmak kaldığı yerden devam eder."
            ),
        },
    },
    "en": {
        "first": {
            "title": "Your first translation",
            "body": (
                "1. Drop the document onto the window, or pick it with Browse. The application "
                "decides which output formats are open from the file type you chose.\n"
                "2. Choose the source and target language, then the provider (local LM Studio or a "
                "cloud endpoint).\n"
                "3. Start it. Long documents are split into parts and each finished part is "
                "written to disk, so a closed window costs nothing.\n\n"
                "For a long run you can put the window away: the ▤ button in the header hides it "
                "and the progress continues in the floating bar; “Back to window” on the bar "
                "brings it back.\n\n"
                "When it finishes you have three things: the translated file, the `.lkproj` "
                "working file, and the lossless audit summary.\n\n"
                "Bilingual PDF: with “Bilingual PDF” chosen in the setup, a second PDF is written "
                "beside the translated file, holding the source too - “Side by side” (source left) "
                "or “Alternating pages”. The main output and the audit are unchanged.\n"
                "Page range: only the pages you select are translated, and the output holds only "
                "those pages; the saved `.lkproj` keeps the whole document, so the review screen "
                "still shows the rest and re-exporting cannot silently shorten it."
            ),
        },
        "provider": {
            "title": "Choosing a provider",
            "body": (
                "Local (LM Studio, Ollama): free, offline, the document never leaves the machine. "
                "Quality follows the model you loaded.\n"
                "Cloud (OpenAI-compatible or DeepL): stronger models, faster; the text goes to the "
                "provider and usually costs money.\n\n"
                "Two server settings matter locally: the context window and the number of parallel "
                "slots. Parallelism defaults to 2, and an 8192 window leaves about 4k tokens per "
                "request; raising the workers to 7 (when the server really has 7 slots) leaves "
                "about 1.2k per request and long paragraphs overflow. Loading with -c 32768 keeps "
                "seven workers comfortable (about 4.7k per request). An overflow is no longer fatal (the segment is cut "
                "at sentence boundaries), but it is slower."
            ),
        },
        "settings": {
            "title": "What the settings mean",
            "body": (
                "General tab: worker count (match the server's slot count), translate repeated text "
                "once, the translation memory (a cross-run SQLite store that makes re-translating "
                "the same document cheap) and the glossary. “Edit…” opens it as a table; it also "
                "loads JSON or a two-column CSV/TSV, and a term that was not used lands in the "
                "review queue.\n"
                "The preset at the top of the dialog moves several values together: “Fast draft” "
                "(7 requests, readability floor 0.80, shorter-rendering requests off) for a first "
                "pass to read, “Publication quality” (2 requests, measured thresholds) for output "
                "you keep. Edit any value afterwards; if one changed, the box says “Custom”.\n"
                "“Suggest from document” in the glossary editor adds term candidates that recur in "
                "the file the setup screen points at, with empty target cells for you to fill in.\n"
                "Developer tab: fitting and batch-size thresholds. A wrong value there does not "
                "raise an error, it quietly produces worse output - which is why every entry says "
                "what goes wrong next to it.\n\n"
                "Changes take effect immediately; a running job keeps the values it started with."
            ),
        },
        "flags": {
            "title": "Review flags",
            "body": (
                "Every flag says \"look here\" about one block; none of them is a silent pass:\n\n"
                "• the translation did not fit its box and shrinking was not enough\n"
                "• bold/italic formatting was lost\n"
                "• the model returned the text untranslated\n"
                "• a whole batch failed to translate\n"
                "• a glossary term was not used in the translation\n"
                "• the block ran past the bottom margin\n"
                "• the provider returned nothing for the segment"
            ),
        },
        "criteria": {
            "title": "Loss criteria",
            "body": (
                "The audit compares the written page against the source. L-criteria are losses; "
                "D-criteria are descriptive (not counted as losses, but they are what to look at). "
                "The list below is read from the checker's own code."
            ),
        },
        "quality": {
            "title": "What decides the quality of a translation",
            "body": (
                "The same document gives different results under different conditions. From the "
                "largest effect down:\n\n"
                "• The model's language ability — the single largest factor. A small local model "
                "and a frontier cloud model are not close on idiom; which model you pick decides "
                "how well the translation reads.\n"
                "• Digital text or a scan — a digital PDF carries its own fonts, sizes and "
                "coordinates, so styles survive; a scan goes through OCR and recognition errors "
                "enter the text.\n"
                "• Scan resolution — below roughly 200 dpi the OCR starts losing small type and "
                "superscripts, and a wrong character is a wrong translation.\n"
                "• The document type — prose re-flows into generous boxes; a form's and a table's "
                "boxes are exactly one line tall and the fitting has to shrink there. Formulae, "
                "code and figures are deliberately left untouched.\n"
                "• The source's own layout — narrow columns, overlapping boxes and text wrapped "
                "around a figure all narrow the room the translation can use.\n"
                "• The language direction — Turkish is agglutinative: it contracts into English "
                "and expands out of it. The same paragraph needs different room each way.\n"
                "• The glossary and the translation memory — a term list pins the vocabulary; the "
                "memory translates a repeated string once and keeps it the same everywhere.\n"
                "• Your settings — lossless mode, repeat unification and piecewise repair trade "
                "speed for fidelity; the defaults are the lossless ones.\n\n"
                "The short version: the model decides whether the translation reads well, the "
                "document decides whether the layout survives, and the audit decides whether "
                "either is true."
            ),
        },
        "output": {
            "title": "Where the outputs are",
            "body": (
                "The translated file: the path you chose.\n"
                "The working file: `.lkproj` beside it - everything needed to re-write, review or "
                "export in a different format.\n"
                "The audit: `tools/audit/lossless_audit.py --work <run directory>` on the command "
                "line; the completion screen shows its headline numbers.\n"
                "Review flags: when the completion screen says \"N segments need review\", those "
                "segments either did not fit their box or dropped a number or protected value. It "
                "also says how many of them are shortened boxes: those are a page-layout problem, "
                "not a long translation, and translating the same text again will not fix them.\n"
                "The crash log: `crash.log` in the data directory, if the application ever closes "
                "unexpectedly."
            ),
        },
        "trouble": {
            "title": "Troubleshooting",
            "body": (
                "\"Model not found or not loaded\" - usually the model is loaded and answering; the "
                "real reason is in the server's response body, and the most common one is a "
                "context overflow (see the provider section above).\n"
                "\"The server did not respond (timeout)\" - a large model takes minutes to load; "
                "raise the timeout in Provider Settings.\n"
                "\"cannot be reached\" - LM Studio (port 1234) or Ollama (port 11434) is not "
                "running, or its server mode is off.\n"
                "Unreadable pages in a scan - OCR drops on skewed or stained pages; the review "
                "flags say which page.\n"
                "A long document stopped - the `.lkproj` files remain; re-run the same job with "
                "`--resume` and it continues where it left off."
            ),
        },
    },
}


def text(language: str, key: str) -> dict[str, str]:
    """The copy for one section, falling back to English for languages without their own."""
    section = _TEXT.get(language, _TEXT["en"])
    return section.get(key) or _TEXT["en"][key]
