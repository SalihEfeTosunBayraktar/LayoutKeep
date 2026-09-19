> Not: bu belge terk edilen V2 (ayrı klon, `v2-vision-layout` dalı) çalışması için yazıldı.
> V2 klasörü terk edildi; dallar ve gerekçe `docs/campaign/JOURNAL.md`'de kayıtlı.

# Yeni Nesil Görsel Mizanpaj ve Kayıpsız Çeviri Mimarisi Geçiş Planı

Bu plan, kullanıcının `/goal` komutu doğrultusunda [docs/YENI_MIMARI_VE_GECIS_PLANI.md](file:///c:/MyProjects/AntigravityProjects/AI_and_LLM/LayoutKeep/docs/YENI_MIMARI_VE_GECIS_PLANI.md) dokümanında belirlenen tüm fazları adım adım tamamlayarak, orijinal `LayoutKeep` projesini koruma altında tutarken izole `LayoutKeep_V2` çalışma alanında yeni nesil görsel mizanpaj (Visual Anchor + Glyph Fusion) sistemini kurmayı ve test etmeyi kapsar.

---

## 1. Çalışma ve İzolasyon Esasları

- **Orijinal Çalışmanın Korunması:** Orijinal `LayoutKeep` çalışma dizini ve git geçmişi tamamen dondurulmuş ve korunmuştur. Tüm yeni nesil mimari çalışmaları, bağımsız `c:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep_V2` dizinindeki `v2-vision-layout` dalında yürütülmektedir.
- **ONNX ve VLM Hibrit Desteği:** Ortamda `onnxruntime` (1.29.0), `cv2`, `PIL` ve `pymupdf` mevcuttur. Sistem hem yerel hafif nesne algılama (RT-DETR / DocLayNet ONNX) hem de çok modlu VLM (Qwen2.5-VL / Claude / Gemini) API'leri ile hibrit çalışacak şekilde tasarlanmıştır.
- **Kodlama Kuralları:** Sınıflar 200-220 satırı, fonksiyonlar 40 satırı aşmaz. Emoji kullanımı kesinlikle yasaktır (resmi SVG ikonlar ve temiz metinler). İki dilli yorum satırları (`// Türkçe / English`).

---

## 2. Mimari Bileşenler ve Yapılan Değişiklikler

Tüm değişiklikler **`LayoutKeep_V2`** izole proje kopyası üzerinde gerçekleştirilmektedir:

### 2.1. Görsel Mizanpaj ve Glif Birleştirme Katmanı (`src/layoutkeep/readers/`)

#### [NEW] `vision_layout.py`
- Sayfa görseli üzerinden mizanpaj bölgelerini (`LayoutRegion`: başlık, paragraf, tablo, formül, üst/alt bilgi) ve mantıksal okuma sırasını tespit eden protokol ve VLM adaptörü.
- ONNX model çıkarım şablonu ve kural bağımsız görsel algılama arayüzü.

#### [NEW] `glyph_fusion.py`
- `GlyphFusionEngine`: PDF'in ham vektörel dijital metin katmanını görsel bölgelerin içine projekte ederek çok sütunlu sayfalarda satır karışmasını (%100) engelleyen ve bölge dışı metinleri kayıpsız toplayan motor.
- `point-in-bbox` ve ağırlıklı kesişim (`IoU`) mantığıyla OCR kaynaklı harf bozulması olmadan orijinal vektör kalitesini korur.

#### [MODIFY] `pdf_reader.py`
- Kırılgan kural zincirini (`_split_side_by_side_lines`, `_merge_wrapped_lines`, vb.) görsel mizanpaj motoruna bağlayan ve görsel analiz bulunamadığında klasik okuyucuya düşen güvenli köprü entegrasyonu.
- `_extract_vision_blocks` fonksiyonu ve `_extract_heuristic_blocks` ayrımı.

---

### 2.2. Dinamik Sığdırma ve Öteleme (`src/layoutkeep/fitting/` & `writers/`)

#### [NEW] `elastic_flow.py`
- `ElasticFlowEngine`: Metin uzadığında yalnızca fontu küçültmek yerine, bloklar arası dikey kaydırma toleransını (elastic vertical push) hesaplayan mikro-akış desteği.
- Sütun bağımsızlığını koruyarak sol sütundaki genişlemenin sağ sütunu bozmasını engeller; sayfa alt sınırını aşan blokları denetim bayrağıyla işaretler.

#### [MODIFY] `fit.py` & `pdf_pass.py`
- Çeviri uzadığında `FitMode.REFLOW` modunu tetikleyen ve blokların esnek dikey koordinatlarını güncelleyen akış entegrasyonu.

---

### 2.3. Test ve Doğrulama (`tests/`)

#### [NEW] `test_vision_glyph_fusion.py`
- Çok sütunlu sayfalarda aynı Y seviyesindeki satırların sütun bazlı ayrılma testi (100% başarılı).
- Boşta kalan kenar notlarının kayıpsız kurtarılma testi (100% başarılı).

#### [NEW] `test_pdf_reader_vision_hybrid.py`
- PDF okuyucunun görsel mizanpaj motoruyla entegre uçtan uca testi (100% başarılı).

#### [NEW] `test_elastic_flow.py`
- Tek sütun ardışık blok öteleme testi (100% başarılı).
- Çok sütunlu bağımsız öteleme testi (100% başarılı).
- Sayfa alt marj sınırı koruma testi (100% başarılı).

---

## 3. Doğrulama ve Kıyaslama Planı

1. **Birim Testler:**
   - `test_vision_glyph_fusion.py`
   - `test_pdf_reader_vision_hybrid.py`
   - `test_elastic_flow.py`
2. **Statik Kod Analizi:**
   - `ruff check src/ tests/` (Sıfır hata, sıfır uyarı)
3. **Mevcut Sistem Karşılaştırması:**
   - Kural tabanlı ayrıştırma vs. Visual Anchor ayrıştırma arasındaki okuma sırası ve sütun izolasyonu kıyaslaması.
