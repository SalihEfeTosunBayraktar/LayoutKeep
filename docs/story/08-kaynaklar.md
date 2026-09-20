# 8. Dış kaynaklar ve atıflar

Bu proje ayakta durmak için başkalarının işine yaslanıyor. Aşağıda her kaynağın **projedeki rolü**
ve lisansı var. (Aynı tablo `CREDITS.md` dosyasında da tutulur; burası gerekçeleriyle birlikte
genişletilmiş hâlidir.)

## 8.1 Motor ve altyapı

| Kaynak | Projedeki rolü | Lisans |
|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) | PDF okuma ve yazma motoru; metin katmanı, tipografi, görsel çıkarma, redaksiyon, HTML kutusu çizimi | AGPL-3.0 |
| [Qt / PySide6](https://doc.qt.io/qtforpython/) | Masaüstü arayüzü: pencere, yüzen çubuk, karşılama, tablolar, tema | LGPL-3.0 |
| [pytest](https://pytest.org/) | 1.192 testin koşum altyapısı | MIT |
| [PyInstaller](https://pyinstaller.org/) | Tek dosya `.exe` üretimi | GPL-2.0 (özel istisna ile) |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) (PP-OCR modelleri) | Taranmış sayfalarda OCR; güven skoru üretir | Apache-2.0 |

## 8.2 Düzen modeli (IBM Docling)

| Kaynak | Projedeki rolü | Lisans |
|---|---|---|
| [IBM Docling — Heron düzen modeli](https://huggingface.co/docling-project/docling-layout-heron-onnx) | Taranmış/karmaşık sayfalarda bölge sınıflandırması (başlık, paragraf, tablo, şekil, dipnot). ONNX olarak yerelde koşar | MIT |
| [Docling (proje)](https://github.com/docling-project/docling) | Modelin geldiği çerçeve; mimari fikirleri (sayfa görüntüsünden yapı çıkarma) | MIT |

Kararın gerekçesi ve ölçümü Bölüm 5.3'te: 10 kitap sayfası üzerinde dört panelli karşılaştırmada
"hâlâ İngilizce kalan düzyazı" 6/82 → 1/82. Modelin **yalnız başına** çıktısı da kaydedildi
(`tests/layout_eval/2026-09-16_heron_pure/`) ki sonradan eklenen her kural ölçülmüş bir tabana
göre eklensin.

## 8.3 Çeviri modelleri

| Kaynak | Projedeki rolü | Lisans |
|---|---|---|
| [google/gemma-4-e4b](https://huggingface.co/google/gemma-4-e4b) (LM Studio üzerinden) | Varsayılan yerel çeviri modeli | Gemma Terms of Use |
| [LM Studio](https://lmstudio.ai/) | Yerel model sunucusu (OpenAI uyumlu uç nokta, paralel yuvalar, bağlam ayarı) | Özel (ücretsiz kullanım) |
| [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | İnce ayar hattının taban modeli (ayrı çalışma, Bölüm 5.4) | Apache-2.0 |
| [Hugging Face Transformers](https://huggingface.co/docs/transformers/) + PEFT/QLoRA | İnce ayar (Kaggle'da, TRL'e bağımlı olmadan) | Apache-2.0 |

## 8.4 Karşılaştırma noktaları (kod alınmadı, fikir ve ölçüt alındı)

| Kaynak | Neyi karşılaştırdık | Lisans |
|---|---|---|
| [BabelDOC](https://github.com/funstory-ai/BabelDOC) | Paralel PDF çevirisi; "kayıpsız" iddiası ve kendi karşılaştırma tablosu (arXiv 2605.10845) | AGPL-3.0 |
| [PDFMathTranslate](https://github.com/Byaidu/PDFMathTranslate) | PDF çevirisi; formül/görsel koruma yaklaşımı | AGPL-3.0 |
| [MinerU](https://github.com/opendatalab/MinerU) / mineru-translate | Belge anlama hattı; çift dilli çıktı, önbellek | AGPL-3.0 |
| Ticari derlemeler (Doclingo, Lara Translate, Doctranslate, Bluente) | Özellik kapsamı ve fiyatlandırma | — |

**Kod alınmadı.** Bu projedeki hiçbir satır yukarıdaki araçlardan kopyalanmadı; tablo yalnızca
"dışarıda ne var, bizde ne yok" sorusunu ölçülebilir kılmak için var (`docs/FEATURE-ROADMAP.md`).

## 8.5 Test kaynakları (held-out set)

Ölçüm için kullanılan belgeler ve lisans durumları. Telifli olanlar **depoya girmez** ve siteye
yayınlanmaz (`NOT_PUBLISHABLE`); yalnız kullanıcının diskinde kalır.

| Kaynak | Tür | Durum |
|---|---|---|
| NIST Journal of Research (dergi sayıları) | Dijital PDF | Kamu malı (ABD federal) — yayınlanır |
| NIST IR 6643 (vapor pressure) | **Taranmış** PDF | Kamu malı — yayınlanır |
| NIST dergisinden üretilmiş DOCX | DOCX | Kamu malı (projenin kendi PDF→DOCX hattıyla üretildi) — yayınlanır |
| NASA NTRS raporu + NASA grant formu | Dijital + taranmış | Kamu malı — yayınlanır |
| arXiv makaleleri (19113, 19145, 2510.03959, 2605.18014) | Dijital PDF | arXiv lisansı — yayınlanır |
| IRS formları (i1040gi, p505) | Form PDF | Kamu malı (ABD federal) — yayınlanır |
| Project Gutenberg kitapları (The Time Machine, Think Python, cookbook) | EPUB/PDF | Kamu malı / açık lisans — yayınlanır |
| Wikipedia sayfaları | PDF | CC BY-SA — yayınlanır |
| Introductory Statistics (Sheldon M. Ross) | Kitap PDF | **Telifli** — yalnız yerelde |
| computer-systems-Architecture | Kitap PDF | **Telifli** — yalnız yerelde (görüntüleri depodan çıkarıldı) |

## 8.6 Yöntem ve mühendislik kaynakları

| Kaynak | Neyi etkiledi |
|---|---|
| Google DESIGN.md / tasarım token'ları | Arayüz renk paletinin token'lardan gelmesi kuralı (hardcoded hex yasak) |
| Apple HIG, Material Design (genel ilkeler) | Karşılama/yardım ekranlarının yapısı, boşluk ve tipografi ölçeği |
| ISO 639 dil kodları | Dil seçimi ve algılama |
| Unicode özel kullanım alanı (U+E000–U+E001) | Korunan değerlerin modele görünmez şekilde taşınması |
| Portable Document Format spec (ISO 32000) | PDF yazımı ve redaksiyon davranışının doğrulanması |

## 8.7 Bu belgenin kendi kaynakları

Bu hikâye uydurulmadı; şu dosyalardan ve ölçümlerden derlendi:

- `docs/CONTRACT.md` — mimari değişmezler (D1–D7)
- `docs/campaign/JOURNAL.md` — gün gün ölçüm jurnalı (vakaların birincil kaynağı)
- `docs/MEASUREMENTS.md`, `docs/BENCHMARK.md` — sayılar
- `docs/KAYIPSIZ_MOD_DURUM.md`, `docs/LOSSLESS-REPORT.md` — kayıpsızlık durumu
- `docs/FEATURE-ROADMAP.md` — dış karşılaştırma ve açık işler
- `_artifacts/heldout/**/audit.json` — her koşunun denetim sayıları
- `git log` — tarihler ve kararlar
