# Sıfırdan bugüne LayoutKeep

**Ölçülmüş bir mühendislik hikâyesi: ne denedik, ne kırıldı, neyi düzelttik, neyi geri aldık.**

> **English abstract.** LayoutKeep translates PDF, EPUB and DOCX documents without moving anything
> on the page: every text box keeps its position and its size, figures stay where they were, tables
> keep their rows. This document is the project's full record - how it started, what was tried and
> abandoned (including a full rewrite and a fine-tuning campaign), which bugs were found and how
> each root cause was measured, why the runtime model is a local one and why the layout detector is
> IBM Docling's Heron, and what is still known to be broken. Every number here comes from a command
> that is written down next to it.

---

## 0. Özet, sayılarla

| Ne | Değer | Nasıl ölçüldü |
|---|---|---|
| Desteklenen biçimler | PDF → PDF, EPUB, DOCX, PNG/JPG, LKPROJ | `capabilities.py` matrisi, iki yönlü testli |
| Kayıpsızlık kriteri | **10 kayıp (L1–L10) + 3 kalite eşiği (D1–D3)** | `verify.py`; kriterler denetleyicinin kendisinden okunur |
| Yayınlanan ölçüm seti | **22 belge**, 276 görsel, 0 "eski kayıt" | karşılaştırma sitesi (her belge kendi denetim sayılarıyla) |
| En büyük gerçek koşu | 220 sayfalık istatistik kitabı, 55 parça, ~106 dakika | `translate_book.py`, `--workers 7` |
| Test paketi | **1192 test**, 138 dosya | `.venv/Scripts/python.exe -m pytest -q` |
| Kaynak kod | ~24.000 satır (`src/`), 56 denetim aracı | `wc -l`, `tools/audit/` |
| Uygulama | tek dosya Windows exe (kurulumsuz), ~173 MB | PyInstaller onefile |
| Çalışma zamanı modeli | `google/gemma-4-e4b`, LM Studio, varsayılan 2 işçi | yerel; belge makineden çıkmaz |
| Düzen modeli | IBM Docling **Heron** (ONNX, yerel) | taranmış/karmaşık sayfalarda bölge sınıflandırması |

---

## 1. Bu belge nasıl okunur

Hikâye sekiz bölüme ayrıldı. Her bölüm kendi başına okunabilir; sırayla okunduğunda projenin
mantığı çıkar: önce problem, sonra mimari, sonra **ölçüm** (çünkü her karar bir sayıya dayanıyor),
sonra hatalar, sonra model kararları, sonra ürün, sonra dürüst sınırlar ve kaynaklar.

| # | Bölüm | İçinde ne var |
|---|---|---|
| 1 | [Problem: "kayıpsız çeviri" tam olarak ne demek](story/01-problem.md) | Tanım, dört ölçülmüş zorluk, dış araçlarla karşılaştırma tablosu, sözleşme (D1–D7) |
| 2 | [Mimari: boru hattının her parçası](story/02-mimari.md) | Modüller ve satır sayıları, DocIR, okuyucular, sağlayıcı zinciri, sığdırma, yazıcılar, denetleyici |
| 3 | [Ölçüm disiplini](story/03-olcum.md) | L1–L10 + D1–D3 tablosu, 56 denetim aracı, **ölçümün kendisinin üç kez yanılması** |
| 4 | [Hata kataloğu: on dört vaka](story/04-hatalar.md) | Her vaka: belirti → araştırma → kök neden → çözüm → kanıt |
| 5 | [Model seçimi ve IBM Docling meselesi](story/05-model.md) | Yerel-önce kararı, Heron düzen modeli (neden, ölçüm), V2 planı neden uygulanmadı, ince ayar hattı |
| 6 | [Ürünleşme: motordan uygulamaya](story/06-urun.md) | Karşılama, yardım, sözlük/bellek, yüzen çubuk, aralık, sürümler, karşılaştırma sitesi |
| 7 | [Dürüst sınırlar ve dersler](story/07-sinirlar.md) | Bugün çalışmayanlar, yol haritası, sekiz ders |
| 8 | [Dış kaynaklar ve atıflar](story/08-kaynaklar.md) | Her bağımlılığın rolü ve lisansı, test kaynaklarının hukuki durumu |

Markdown dosyaları depoda: `docs/story/01-problem.md` … `docs/story/08-kaynaklar.md`.

---

## 2. Kısa kronoloji

Proje **10 Eylül 2026**'da tek bir cümleyle başladı: *"translate a document without moving anything
on the page"*.

| Tarih | Ne oldu |
|---|---|
| 10 Eyl | İlk çalışan boru hattı: PDF → PDF, DocIR doğdu, sözleşme yazıldı; ilk "kayıpsız" raporun yanlış olduğu görüldü (yalnız metin akışına bakıyordu) ve **zengin fixture** kuralı geldi |
| 11–13 Eyl | EPUB/DOCX yolları, görsel-üstü-metin ve tablo testleri, ilk gerçek belgelerde ölçümler |
| 14 Eyl | Sığdırma (fit) geçişi, kısaltma merdiveni, `reflow` fikrinin ilk ölçümleri |
| 15–16 Eyl | Masaüstü uygulaması (PySide6): kurulum, ilerleme, tamamlanma; sağlayıcı ayarları; **IBM Docling Heron** düzen modelinin eklenmesi |
| 17 Eyl | Kaynak türü ayrımı (dijital/taranmış/karma), OCR güven eşiği, dört panelli görsel karşılaştırma |
| 18 Eyl | Kayıpsızlık kampanyası: L kriterlerinin genişletilmesi, `lossless_audit`, held-out seti |
| 19 Eyl | Çok işçili parça çevirisi (`--workers`), `--resume`, bellek ve sözlük sağlayıcıları, karşılaştırma sitesinin ilk sürümü |
| 19–20 Eyl (gece) | 220 sayfalık kitap (55 parça, ~106 dk); L10'un ölçüm hatası; reflow'un iki ölçümü; sözlük/bellek arayüzde; yardım ve karşılama; yüzen çubuk |
| 20 Eyl | Ürünleşme ve düzeltmeler: **uygulamada paralellik**, aralık davranışı, hizalama (justify), ölü ayar anahtarı, telif temizliği, sürümler **v0.9.1 → v0.9.5** |

---

## 3. Bugünkü durum: belge belge

Her sayı o koşunun `audit.json` dosyasından; karşılaştırma sitesinde her belgenin yanında duruyor.

| Belge | Parça | Kalan gerçek kayıplar |
|---|---|---|
| Wikipedia ×2 (yeniden çevirim) | 19 / 33 | L2 satırları; **L10 = 0** |
| cookbook_1907 | 35 | L6=2, D1 (küçük punto) |
| mushrooms_1895_sample | 41 | L2=1, L6=1 |
| NIST dergisi / NISTIR taraması | 8 / 6 | L1 kısmi koşu; **L2–L10 = 0** |
| IRS formu (48 parça) | 48 | L7 (yoğun form; reflow kapalıyken ölçüldü) |
| 220 sayfalık kitap | 55 | L2=2, L6=4, L7=1, L8=1, L10=0, D1=801 (küçük punto sınıfı) |

![Karşılaştırma sitesi](story/site.png)

*Yayınlanan karşılaştırma sitesi: solda orijinal, sağda çeviri, üstte o belgenin denetim sayıları.*

**Bilinen sınırlar (özet):** tablo başlıklarındaki **sayı şeritleri** dizilişini kaybedebilir;
kaynakça satırları bazen kaynak dilde kalır (L2, işaretli); yoğun formlarda okunabilirlik tabanının
altına inen bloklar vardır (D1); taranmış sayfalar OCR kalitesine bağlıdır ve düşük güvenle
işaretlenir; **sağdan sola yazı sistemleri uygulanmamıştır**; kalite modelin becerisidir. Ayrıntılı
liste ve yol haritası: [Bölüm 7](story/07-sinirlar.md).

---

## 4. Tek cümlelik özet

Bir belgeyi başka bir dile çevirmek kolay; **sayfayı yerinde bırakarak** çevirmek zor — ve bu proje
ikincisini yapıp **kaybı sayarak** kanıtlıyor: her koşu kaynağa karşı sayfa sayfa denetlenir, her
kayıp ya düzeltilir ya gerekçesiyle işaretlenir, ve hiçbir sayı gizlenmez.

---

*Bu belge depodaki `docs/CONTRACT.md`, `docs/campaign/JOURNAL.md`, `docs/MEASUREMENTS.md`,
`docs/KAYIPSIZ_MOD_DURUM.md`, `docs/LOSSLESS-REPORT.md`, `docs/FEATURE-ROADMAP.md` dosyalarından,
`_artifacts/heldout/**/audit.json` denetim kayıtlarından ve git geçmişinden derlendi.*
