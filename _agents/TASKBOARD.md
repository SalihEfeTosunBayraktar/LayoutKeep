# LayoutKeep — Görev Panosu ve Ajan Kadrosu

Şef: ana Claude oturumu. `core/`, `docs/`, `_agents/` sahibi ve tek entegrasyon noktası.
Bu pano tek gerçek kaynaktır. Bir ajan işe başlamadan önce buraya bakar, bitirince buraya yazar.

---

## Kadro

### Claude tarafı (Sonnet alt ajanları — `.claude/agents/`)

| Ajan | Alan | Sahip olduğu dosyalar |
|---|---|---|
| `lk-epub` | EPUB oku/yaz | `readers/epub_reader.py`, `writers/epub_writer.py` |
| `lk-provider` | Çeviri sağlayıcıları, TM, sözlük | `providers/` |
| `lk-pdf` | PDF oku/yaz (PyMuPDF) | `readers/pdf_reader.py`, `writers/pdf_writer.py` |
| `lk-fitting` | Sığdırma motoru, ölçüm | `fitting/fit.py`, `fitting/measure.py` |
| `lk-ui` | PySide6 arayüz | `ui/` |
| `lk-verify` | Bağımsız doğrulama | `tests/conftest.py`, `tests/fixtures/`, entegrasyon testleri |

### Antigravity tarafı (Gemini)

**Model:** Gemini Pro 3.1 (karmaşık iş) / Gemini Flash 3.7 high (mekanik iş).

Antigravity'ye verilen işler şu üç kriteri karşılamalı:
1. Girdi–çıktı sözleşmesi net ve yazılı,
2. Tek dizine kapalı, başka ajanla dosya çakışması yok,
3. Doğrulaması objektif (test geçer / geçmez, ekran görüntüsü var / yok).

| Görev | Dizin | Brief | Neden Antigravity |
|---|---|---|---|
| `AG-1` Font eşleme + glif kapsam denetimi | `fitting/fontmatch.py` | `_agents/briefs/AG-1-fontmatch.md` | Kapalı, tablo ağırlıklı, bol birim test — mekanik iş |
| `AG-2` PySide6 düzeltme editörü kabuğu | `ui/` | `_agents/briefs/AG-2-ui-shell.md` | Görsel iş, IDE'de anlık önizleme avantajı |

**Çakışma kuralı:** Antigravity `fitting/fontmatch.py` yazarken `lk-fitting` **başlatılmaz**.
İkisi aynı dizini paylaşır; sıralı çalışırlar, paralel değil.

---

## Faz 0 — Kanıt (şu anki faz)

Hedef: *"EPUB'da çeviri kalitesi ve terim tutarlılığı gerçekten yeterli mi?"* sorusunu ucuza cevaplamak.
Bu fazda UI yok, PDF yok, OCR yok. Sadece CLI.

| # | Görev | Sahip | Durum | Bağımlılık |
|---|---|---|---|---|
| 0.1 | DocIR çekirdeği + `.lkproj` gidiş-dönüş | Şef | ✅ **bitti** (duman testi geçti) | — |
| 0.2 | `TranslationProvider` + `openai_compat` + `FakeProvider` | `lk-provider` | ✅ **bitti** (19 test geçti, stdlib-only) | 0.1 |
| 0.3 | EPUB oku/yaz + kimlik testi | `lk-epub` | ✅ **bitti** (kimlik diff = boş, 14 test) | 0.1 |
| 0.4 | Çeviri belleği (SQLite) + terim sözlüğü | `lk-provider` | ✅ **bitti** (49 test, TM %100 isabet 2. geçişte) | 0.2 |
| 0.5 | CLI: `inspect` / `models` / `translate` | Şef | ✅ **bitti** (sahte sağlayıcıyla uçtan uca çalıştı) | 0.2 |
| 0.7 | **Satır içi biçim koruma** (marker sistemi) | Şef + `lk-provider` + `lk-epub` | ✅ **bitti** (çekirdek + prompt + yazıcı, orijinal etiket adları korunuyor) | 0.3 |
| 0.6 | Uçtan uca doğrulama, gerçek EPUB, gerçek local model | `lk-verify` | ✅ **bitti** (Alice/Gutenberg #11, LM Studio gemma-4-e4b, EN→TR: 20/20 + 19-20/25; 3 kusur rapor edildi — LOG.md 2026-09-06) | 0.5, 0.7 |

**Faz 0 çıkış kriteri:** Gerçek bir EPUB, local bir LLM ile EN→TR çevrilecek; çıktı okunabilir,
terimler tutarlı ve yapı bozulmamış olacak. Bu sağlanmazsa proje burada durur — 300+ saat harcamadan öğrenmiş oluruz.

---

## Faz 1 — MVP (Faz 0 geçerse)

| # | Görev | Sahip |
|---|---|---|
| 1.1 | PDF okuma | `lk-pdf` | ✅ bitti |
| 1.2 | Font eşleme + glif kapsamı | `lk-fitting` | ✅ bitti (font paketleme açık) |
| 1.3 | Sığdırma motoru (4 katman) | `lk-fitting` | ✅ bitti |
| 1.4 | PDF yazma | `lk-pdf` | ✅ bitti (arka plan sanatı korunuyor) |
| 1.5 | 3 adımlı masaüstü akışı (kurulum → ilerleme → tamamlama ekranı) | `lk-ui` | ✅ bitti — gözden geçirme editörü kaldırıldı; çekirdek `needs_review`/`confidence` bayrakları sığdırma/passthrough için duruyor |
| 1.6 | Paketleme (Win) | Şef | ✅ bitti — `packaging/layoutkeep_onefile.spec`, tek dosya `dist/LayoutKeep.exe` (~155 MB) |

---

## Devir protokolü (Antigravity ↔ Claude)

1. Şef, `_agents/briefs/AG-*.md` altına görev brief'i yazar. Brief kendi başına yeterlidir —
   bu konuşmayı görmeyen biri de uygulayabilmelidir.
2. İş kendi git dalında yapılır: `ag/<görev-id>`.
3. Antigravity bitirince brief'in altındaki **Sonuç** bölümünü doldurur: ne yapıldı, testler,
   bilinen eksikler.
4. `lk-verify` bağımsız doğrular. Geçerse şef `main`'e alır.
5. Antigravity `core/` ve başka ajanın dizinine **yazmaz**. İhtiyaç varsa brief'in Sonuç bölümüne
   talep olarak yazar.

## Ortak kayıt

Her ajan iş bitirince bu panonun Durum sütununu günceller ve `_agents/LOG.md` dosyasına tek satır ekler:
`YYYY-MM-DD | ajan | görev | sonuç | doğrulama`

---

## Faz 2 — Taranmis belge ve gorsel (tamamlandi)

| # | Görev | Sahip | Durum |
|---|---|---|---|
| 2.1 | OCR motoru + görsel okuyucu | `lk-ocr` | ✅ RapidOCR/ONNX, torch yok |
| 2.2 | İnpainting + görsel yazıcı | `lk-ocr` | ✅ düz dolgu 6 zeminden 4'ünde yeterli (ölçüldü) |
| 2.3 | Çekirdek şema: confidence / needs_review / source_text | Şef | ✅ 3 metadata geçici çözümü kapandı |

**Bilinen sınır:** düşük çözünürlüklü ve gradyanlı zeminlerde düz dolgu yetersiz.
Model tabanlı inpainting AGPL uyumlu bir seçenek bulunana kadar yapılmayacak
(LaMa ağırlıkları CC BY-NC-SA).

---

## Faz 3 — Genişleme (başlanmadı)

| # | Görev | Not |
|---|---|---|
| 3.1 | GitHub Pages web sürümü | EPUB + dijital PDF, API-only, 50 sayfa sınırı |
| 3.2 | Manga / çizgi roman modu | Balon tespiti, gelişmiş inpainting, dikey metin |
| 3.3 | DOCX / PPTX | DOCX oku/yaz/generate ✅ bitti; PPTX açık |
| 3.4 | XLIFF dışa aktarım (CAT araçları) | |

**Faz 3 öncesi zorunlu:** 0.6 — gerçek local modelle EN→TR genleşme oranı ölçümü.
Sığdırma eşikleri o ana kadar literatür tahminidir.

---

## Çift yönlü sığdırma (2026-09-06, tamamlandı)

Hedef: *EN↔TR çeviride metnin yer/boyut/şekil/renk niteliklerini koruyarak, hedef alan
boyutuna göre kısa/uzun çeviri seçip orijinal doluluk yakalanana kadar deneme-düzeltme.*

| # | Görev | Sahip | Durum |
|---|---|---|---|
| S1 | Çift yönlü iteratif motor (`fit.py`: EXPANDED, MIN_FILL=0.75, MAX_RETRANSLATE_ROUNDS=3) | GLM5.3 | ✅ bitti (15/15 test) |
| S2 | Ortak PDF pası (`pdf_pass.py`) + CLI `_fit_pdf` → pas | GLM5.3 | ✅ bitti |
| S3 | UI worker PDF sığdırma entegrasyonu + ortak `apply_scale` | Orkestratör | ✅ bitti (regresyon testli) |
| S4 | K1 review_reason, K2 marker temizliği, K3 kullanıcı dostu hatalar | Orkestratör | ✅ bitti (hepsi testli) |
| S5 | E2E doğrulama: Hello PDF, gemma-4-e4b, EN→TR | Orkestratör | ✅ as_is=1 shrunk=4 retranslated=1 expanded=2 overflow=3 (review'a düştü, reason dolu); 653 test yeşil |
| S6 | Akademik PDF e2e (arXiv 2301.05062, Tracr): matematik blokları %54'ü çevrilmeye çalışılıyor, passthrough %58 | Orkestratör | ✅ **bitti** — pdf_reader `_looks_like_math`: saf matematik fontları (CMMI/CMSY/CMEX/MSAM/MSBM/Euler/rsfs/*math*) + prose fontu yoksa FORMULA; CMR10 kısa blokta denklem, uzun blokta paragraf (dvips gövdesi CMR10 olabilir). 100 denklem bloğu çeviri dışı (segment 558→458), 23 birim test + gerçek PDF doğrulaması |
| K1 | LayoutKeepLLM/ klasörü baştan düzenlenecek | Şef | ✅ kapandı — alt proje rafa kaldırıldı, klasör yayın öncesi depodan çıkarıldı |

---

## Çapraz format sadakati (2026-09-06, tamamlandı)

Hedef: *Yeniden kuran yazıcılar kaynak tipografiyi koruyamıyordu — bölüm başlıkları sayfa ortasına
düşüyor, hizalama düzleşiyor, punto CSS'ten alınmıyor, görseller düşüyordu.*

| # | Görev | Sahip | Durum |
|---|---|---|---|
| X1 | DocIR `Block.align` alanı (left/center/right/justify) | Şef | ✅ bitti — varsayılan "left", eski `.lkproj` dosyaları geçerli |
| X2 | EPUB CSS çözümleme (`readers/_epub_css.py`): font-size + text-align | Şef | ✅ bitti — 7 birim test; em/px/%/pt, inline > stylesheet > tag default |
| X3 | PDF reader `_infer_alignment`: bbox x-konumundan center/right tespiti | Şef | ✅ bitti — 4 test; tam genişlik justfy yanlış center okunmuyor |
| X4 | EPUB reader görsel çıkarımı (`ImageRef`) | Şef | ✅ bitti — img src manifest'ten çözülüyor, base64 |
| X5 | EPUB→PDF reflow: MuPDF `layout()` yerine Story API | Şef | ✅ bitti — `page-break-before` uygulanıyor (bölümler sayfa başında), görseller data URI ile korunuyor, gerçek CSS punto/align taşınıyor |
| X6 | Align yazıcılara uygulandı (pdf_generator, docx_generator, html_writer) | Şef | ✅ bitti |

**Doğrulama:** gerçek `pg79501-images-3.epub` — CHAPTER II/III/IV artık ayrı sayfalarda
(önce y=781 sayfa dibinde, y=233 ortada); 3/3 görsel korunuyor. 670+13 yeni test yeşil.
