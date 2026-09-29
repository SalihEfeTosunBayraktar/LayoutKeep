# LayoutKeep: Yeni Nesil Doküman Düzen ve Mizanpaj Mimarisi
## (Visual Anchor + Semantic Reading Order + Elastic Flow)

Bu doküman, LayoutKeep projesinde kural tabanlı (heuristic) metin ayrıştırma ve okuma sırası belirleme aşamasında yaşanan tıkanıklığın teknik kök nedenlerini, dünya standartlarındaki (2024–2026 SOTA) çözüm yaklaşımlarını ve projenin yeni mimariye taşınma planını ayrıntılı olarak belgeler.

---

## 1. Mevcut Mimarideki Yapısal Tıkanıklık ve Kök Neden Analizi

Mevcut `src/layoutkeep/readers/pdf_reader.py` motoru, PyMuPDF'in `Page.get_text("dict")` çıktısı üzerine inşa edilmiş kapsamlı bir matematiksel kural zinciri (`_split_side_by_side_lines`, `_merge_wrapped_lines`, `_table_grid`, `_reading_order`) barındırır. Bu yapının tıkanmasının ana nedenleri şunlardır:

### 1.1. PDF Spesifikasyonunun Yapısal Sınırı
PDF formatı (ISO 32000), görsel bir baskı formatıdır. Sayfa içerisinde "bu bir paragraftır", "bu bir sütundur", "bu metin şu sırayla okunur" gibi anlamsal (semantik) hiçbir meta veri bulunmaz. Yalnızca sayfaya rasgele sıralarla çizilmiş harf ve koordinat çiftleri (`x, y, font, size`) vardır.

### 1.2. Kural Tabanlı (Heuristic) Yaklaşımın Çöküşü
- **Çok Sütunlu Sayfalar:** İki sütunlu bir makalede, sol sütunun 4. satırı ile sağ sütunun 1. satırı aynı dikey koordinata (`y`) denk geldiğinde, koordinat tabanlı algoritmalar bu iki sütunu tek bir geniş satır olarak birleştirmeye veya sırayı zikzak şeklinde okumaya meyillidir.
- **Tablo ve Form Karışıklığı:** Hücrelerin satır/sütun sınırları görsel çizgiler veya boşluklarla belirlenir. Eşik değerleri (`_CELL_OVERLAP_KEY`, `_ROW_OVERLAP_KEY`) bir tablodaki kısa hücreleri çözerken, yan yana duran iki adres kutusunu tek bir paragraf zanneder.
- **Formüller ve Şekil Açıklamaları (Captions):** Şekil altı yazıları veya metin içi matematik blokları genellikle ana metin akışının içine sızar (`interleaving`).
- **Kombinatorik Kural Patlaması:** Bir makale tipini düzeltmek için güncellenen her eşik değeri (`threshold`), başka bir dergi veya resmi form formatını bozar. Matematiksel mesafe kurallarıyla insan beyninin görsel algısını simüle etmek teorik olarak imkansızdır.

### 1.3. Çeviri ve Sığdırma Katmanına Yansıyan Hasar (Cascading Failure)
Paragraf yanlış bölündüğünde veya sütunlar karıştığında:
1. LLM'e cümlenin başı gider, devamı gitmez (veya alakasız bir tablonun hücresiyle birleşir).
2. LLM eksik bağlam nedeniyle uydurma (halüsinasyon) çeviri yapar.
3. Çevrilen metin `fitting/` katmanına ulaştığında, yanlış bölünmüş küçük kutulara sığdırılmaya çalışılır; yazı boyutu ya 3 puntoya düşer ya da kutudan taşar.

---

## 2. Yeni Nesil Mimari: Visual Anchor + Digital Glyph Fusion

Dünya genelinde bu problemi tamamen çözen sistemler (IBM Docling, MinerU, Marker, RT-DocLayout) metin çıkarmayı kural yazarak değil, **görsel nesne algılama (Vision Object Detection) ve ilişki grafı (Relation Graph)** ile çözer.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             YENİ MİMARİ AKIŞI                               │
└─────────────────────────────────────────────────────────────────────────────┘

       Sayfa Görüntüsü (150-200 DPI PNG)
                      │
                      ▼
       ┌───────────────────────────────┐
       │   Vision DLA Modeli (ONNX)    │  (IBM Docling Heron / RT-DETRv2 / MinerU)
       │ - Paragraf, Başlık, Tablo     │  - Sayfaya insan gözü gibi bakar
       │ - Bounding Box Sınırları      │  - Görsel sınırları piksel düzeyinde çizer
       └──────────────┬────────────────┘
                      │
                      ▼
       ┌───────────────────────────────┐
       │   Reading Order Transformer   │  - Kutular arası yönlendirilmiş graf (DAG)
       │   (Semantik Okuma Sırası)     │  - Sütun sırasını %98+ doğrulukla çıkarır
       └──────────────┬────────────────┘
                      │
                      │  [Görsel Kutu Koordinatları + Mantıksal Sıra]
                      │
                      ▼
PDF Vektörel   ┌───────────────────────────────┐
Metin Katmanı ─┼─> Spatial Intersection        │  (Point-in-BBox Projeksiyonu)
(PyMuPDF)      │   (Glif - Kutu Eşlemesi)      │  - OCR YAPILMAZ!
               │                               │  - Orijinal vektör metin korunur
               └──────────────┬────────────────┘
                              │
                              ▼
               ┌───────────────────────────────┐
               │    Yapılandırılmış DocIR      │  - Eksiksiz tam cümleler/paragraflar
               │   (Temiz Paragraf/Tablolar)   │  - Rol etiketleri (Title, Body, Table)
               └──────────────┬────────────────┘
                              │
                              ▼
               ┌───────────────────────────────┐
               │         LLM Çevirisi          │  - Sıfır halüsinasyon, tam bağlam
               └──────────────┬────────────────┘
                              │
                              ▼
               ┌───────────────────────────────┐
               │   Elastic Micro-Flow Fitting  │  - Kutu taşarsa alt bloğu aşağı iter
               │    (Dinamik Öteleme Motoru)   │  - Font boyutunu öldürmez
               └───────────────────────────────┘
```

---

## 3. Hangi Modüller Değişecek? (Bileşen Etki Analizi)

| Modül / Dosya | Mevcut Durum | Yeni Durum ve Yapılacaklar |
|---|---|---|
| `src/layoutkeep/core/docir.py` | Düz `Block` ve `Line` hiyerarşisi | **Genişletilecek:** Çok sütunlu akışı temsil eden `FlowRegion` ve bloklar arası ilişkiyi tutan `reading_order_graph` eklenecek. |
| `src/layoutkeep/readers/pdf_reader.py` | 1060 satır karmaşık kural/hesaplama | **Sadeleştirilecek:** Kırılgan kural fonksiyonları (`_split_side_by_side_lines`, `_merge_wrapped_lines`, vb.) kaldırılacak. Yerine görsel model çıktısı ile PyMuPDF gliflerini eşleştiren temiz bir projeksiyon katmanı gelecek. |
| `src/layoutkeep/readers/vision_layout.py` | Yok (yalnızca taranmış sayfa için prototip) | **Yeni Modül:** Hafif, optimize edilmiş yerel ONNX modeli (RT-DETR / Docling Heron veya PP-DocLayoutV2) çalıştıracak inferans modülü. |
| `src/layoutkeep/fitting/fit.py` | Sabit kutu içinde font küçültme / ölçekleme | **Geliştirilecek (Elastic Flow):** Çeviri uzadığında komşu kutuları dikeyde öteleyebilen (vertical push margin) mikro-akış desteği. |
| `src/layoutkeep/writers/pdf_writer.py` | Sabit koordinata doğrudan yazım | **Güncellenecek:** Ötelenen yeni koordinatları ve temizlenmiş arka planı kusursuz çizen yeniden yerleşim motoru. |

---

## 4. Kullanılacak Model Seçenekleri (Yerel & Hızlı)

1. **Öneri 1 (Öncelikli): IBM Docling - Heron Layout Engine (RT-DETRv2)**
   - **Mimari:** Real-Time Detection Transformer v2.
   - **Hız:** CPU üzerinde ~80–140 ms/sayfa (GPU ile saniyede 50+ sayfa).
   - **Lisans:** MIT / Apache-2.0.
   - **Yetenek:** DocLayNet üzerinde eğitilmiş; başlık, paragraf, tablo, formül, dipnot, şekil altı yazılarını kusursuz ayırır.
2. **Öneri 2: OpenDataLab MinerU (PP-DocLayoutV2 / PDF-Extract-Kit)**
   - **Mimari:** RT-DETR + Bidirectional Attention Reading Order Decoder.
   - **Yetenek:** Özellikle çok sütunlu akademik makalelerde ve karmaşık finansal tablolarda açık kaynak dünyasının en yüksek okuma sırası doğruluğuna (%97.4) sahip modeldir.
3. **Öneri 3: Fallback / Hafif Mod (Surya OCR Layout)**
   - Tamamen Python ve hafif PyTorch/ONNX kütüphanesiyle bağımlılık karmaşası olmadan entegre edilebilir.

---

## 5. Geçiş Yol Haritası (Fazlar)

- **Faz 1: İzole Çalışma Ortamının Kurulması**
  - Orijinal `LayoutKeep` çalışma dizini tamamen dondurulur ve korunur.
  - Bağımsız bir kopya (`LayoutKeep_V2`) oluşturularak yeni nesil mimari burada inşa edilir.
- **Faz 2: Vision Layout Modülünün Entegrasyonu**
  - ONNX runtime tabanlı hafif mizanpaj çıkarım motoru (`vision_layout.py`) kodlanır.
  - Sayfa görüntüsü üzerinde kutuları ve okuma sırasını çıkaran model test edilir.
- **Faz 3: Glif-Kutu Projeksiyon Katmanı (Glyph Fusion)**
  - PyMuPDF ile PDF'ten çıkarılan dijital kelimeler/spans, modelin bulduğu kutuların içine matematiksel olarak yerleştirilir.
  - Metin bütünlüğü ve okuma sırası test korpusunda (arXiv çift sütun, Gutenberg, IRS formları) ölçülür.
- **Faz 4: Elastic Flow (Dinamik Sığdırma) ve PDF Yazıcı Uyumu**
  - Genişleyen metinlerin alt blokları aşağı itmesi sağlanır.
- **Faz 5: Kıyaslama ve Doğrulama (Benchmark Matrix)**
  - Eski kural tabanlı sistem ile yeni görsel motor aynı belgeler üzerinde karşılaştırılır (Karakter kayıp oranı, okuma sırası hatası, sütun karışma metrikleri).
