# Nerede ne var — proje haritası

Bu dosya, LayoutKeep deposunun klasör yapısını ve her şeyin nerede durduğunu anlatır.
Tüm yollar repo kökünden görecelidir.

---

## 1. Klasör ağacı

```
LayoutKeep/
├── _agents/              Agent koordinasyonu: TASKBOARD.md (görev panosu), LOG.md (tarihçe)
├── _artifacts/           Üretilen her şey (git'e girmez, silebilirsin)
│   ├── corpus/           Test korpusu: arXiv, Gutenberg, resmî form PDF'leri (tests/ bunlara bakar)
│   ├── input/            Test girdileri (kodla üretilen EPUB/PDF fixture'ları)
│   ├── output/           Test çıktıları, karşılaştırmalar, .lkproj
│   ├── e2e/              Uçtan uca manuel test girdileri (Gutenberg kitap PDF/EPUB'ları + .out.* çıktıları)
│   ├── reports/          Test/lint/demo raporları
│   └── unpacked/         Açılmış EPUB girdileri (XHTML'i doğrudan incelemek için)
├── build/                PyInstaller ara çıktısı (git'e girmez)
├── dist/                 Derlenmiş LayoutKeep.exe (git'e girmez)
├── docs/                 Mimari ve kullanım dokümantasyonu
│   ├── CONTRACT.md       Mimari kurallar (tüm ajanlar için bağlayıcı)
│   ├── PACKAGING.md      EXE derleme rehberi
│   ├── MEASUREMENTS.md   Ölçüm sonuçları
│   ├── NEREDE-NE-VAR.md  (bu dosya)
│   └── mockups/          Logo ve UI/UX arayüz mockup tasarımları (koyu/açık tema)
├── packaging/            PyInstaller spec dosyaları (EXE üretimi)
├── src/layoutkeep/       Uygulama kaynağı (aşağıya bak)
├── tests/                Test paketi (pytest) + fixtures/
├── tools/                Geliştirici betikleri (bench, coherence, demo, run_checks)
├── pyproject.toml        Paket tanımı ve bağımlılıklar
└── README.md             Proje özeti
```

### src/layoutkeep — katmanlar

| Dizin | Sorumluluk |
|---|---|
| `core/` | DocIR şeması ve ortak tipler (Document, Block, Span, Segment, Style) — ağır bağımlılık yok |
| `readers/` | Belge okuma: PDF, EPUB, DOCX, görüntü → DocIR |
| `writers/` | DocIR → çıktı: PDF, EPUB, DOCX, HTML, görüntü + çapraz format dönüşümleri |
| `fitting/` | Sığdırma motoru: çeviri metnini orijinal kutusuna sığdırma (kısa/uzun çeviri, ölçekleme) |
| `providers/` | Çeviri sağlayıcı katmanı (OpenAI-uyumlu, fake, bellek, sözlük…) — layout-bağımsız |
| `ocr/` | OCR motoru (görüntüdeki metni çıkarma) |
| `ui/` | PySide6 masaüstü arayüzü: adım 1 kurulum, adım 2 ilerleme, adım 3 tamamlandı |

---

## 2. Uygulama akışı (2026-09 sonrası sadeleştirme)

Uygulama üç adımlıdır; **gözden geçirme editörü kaldırıldı**:

1. **Belge & Format** (`ui/job_setup.py`) — dosya seç, kaynak/hedef dil, çıktı formatı, sağlayıcı
2. **Çeviri Süreci** (`ui/worker.py` + `ui/progress.py`) — ilerleme, hız (karakter/sn), ETA
3. **Tamamlandı** (`ui/completion.py`) — çıktıyı aç / klasörde göster / yeni çeviri

Çeviri bitince `.out.<format>` dosyası ve `.lkproj` proje dosyası üretilir. Segmentler
`needs_review`/`confidence` bayrakları taşır (çeviri motorunda işlevsel); bu bayrakların
ayrı bir görsel düzeltme ekranı yoktur.

---

## 3. Test çıktıları

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v --html=_artifacts\reports\tests.html --self-contained-html
```

```powershell
.venv\Scripts\python.exe tools\make_demo.py     # demo çevirisi yapar
```

Raporlar `_artifacts\reports\` altına yazılır: `tests.html` (tarayıcıda aç), `tests.xml`
(JUnit), `lint.txt` (ruff), `demo.txt`.

Test girdileri `_artifacts\corpus\` ve `_artifacts\input\` altındadır; test kodu bunlara
`Path("_artifacts/...")` ile erişir. Testler kendi fixture'larını da üretebilir
(`tests/fixtures/`).

---

## 4. Kendi belgeni çevirmek (CLI)

```powershell
.venv\Scripts\python.exe -m layoutkeep.cli inspect "kitabin.epub" --sample 10
.venv\Scripts\python.exe -m layoutkeep.cli models
.venv\Scripts\python.exe -m layoutkeep.cli translate "kitabin.epub" --to tr --model MODEL_ADI --memory tm.sqlite --limit 20
```

`--limit 20` sadece ilk 20 segmenti çevirir. Çeviri belleği `tm.sqlite` tekrar çevirmez.

---

## 5. Çalışma takibi

| Dosya | Ne var |
|---|---|
| `_agents\TASKBOARD.md` | Görev panosu — hangi görev kimde, hangi durumda |
| `_agents\LOG.md` | Tarih sırasıyla ne bitti, nasıl doğrulandı |
| `docs\CONTRACT.md` | Mimari kurallar (tüm ajanlar için bağlayıcı) |
| `git log --oneline` | Her commit ne yaptı ve neyle doğrulandı |

---

## 6. EXE üretimi

```powershell
.venv\Scripts\python.exe -m PyInstaller packaging\layoutkeep_onefile.spec --noconfirm --clean
```

Tek dosya `dist\LayoutKeep.exe` üretir. Ayrıntılar `docs\PACKAGING.md`'de.
