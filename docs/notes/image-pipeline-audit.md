# Görüntü (Image) Pipeline Analizi — Darboğazlar ve Kalite Riskleri

> **Dal:** araştırma belgesi — ana kodu değiştirmez.
> **Kapsam:** `readers/image_reader.py` → `ocr/engine.py` → `writers/image_writer.py` → `ocr/inpaint.py` → `fitting/` zincirinin, görüntü çevirisinde kaliteyi/düzgünlüğü tehdit eden somut noktalarının envanteri.
> **Yöntem:** kod okuma + sözleşme (CONTRACT.md) çapraz kontrol. Sayısal iddialar gerektiren noktalar "ölçülmedi — ölçülmeli" olarak ayrıca işaretlenir (D5/D6 ve "tahmin değil ölçüm" kuralı gereği).

---

## 1. Zincirin bugünkü hali (özet)

```
görüntü → RapidOCR (ONNX) → TextBox(bbox, text, confidence)
        → _merge_boxes_into_lines → _merge_lines_into_paragraphs
        → Block(role=BODY, confidence=min(...), style=Arial + 2-means renk)
        → Segment'lere ayrılır → provider.translate
        → apply_segments → write_image:
            inpaint_block(flat_fill) → fit_segment(STRICT) → ImageDraw çizim
```

Aşağıdaki riskler bu zincirin **belirli adımlarına** bağlıdır ve çoğu *görüntüye özgü* olduğu için metin (PDF/EPUB/DOCX) hattında görülmez.

---

## 2. Kalite riskleri (önem sırasıyla)

### R1 — Düz dolgu (flat-fill) inpaint, dokulu zeminde iz bırakır

`ocr/inpaint.py::flat_fill` ve `inpaint_block` kutuyu **tek renkle** boyuyor. Arka plan 2-means ile kutu içinden ölçülen tek bir `background` rengi. Bu yalnızca **yerel olarak düzgün** zeminde yeterlidir (CONTRACT/brief'in "cheap path only" notu bunu kabul eder).

- **Dokulu/gradyanlı zeminlerde** (fotoğraf üstü yazı, gölge, gradyan) dikdörtgen dolgu, çevresine göre **belirgin bir "yama"** olarak kalır.
- **Çok renkli blokta** (örn. vurgulanmış kelime) `inpaint_block` span başına dolgu yapar (`span.style.background`), bu düzeltir; ama satır düzeyinden ince geçişlerde hâlâ hizalanma hatası olabilir.
- **Vurgulanmış metin** (highlight) span'ları: dolgu vurgu rengini de kapatır → çeviri, vurgu görünümünden yoksun düz zemine yazılır. Görsel sadakat kaybolur.

**Durum:** Bilinen sınır, bilinçli trade-off (LaMa CC BY-NC-SA lisansı AGPL paketine giremez — `inpaint.py` dosya başında açıkça). Ancak **"düz dolgu ne kadar yeterli?" sorusu ölçülmemiş** — `tests/test_inpaint.py` fixture bazında sayılar ürettiği söyleniyor ama gerçek dokulu tarama/etiket görselleri için sonuç bilinmiyor.

**Öneri (araştırma):** `_artifacts/` içine 2-3 dokulu/zeminli örnek (etiket, grafik, fotoğraf üstü yazı) koyup `test_inpaint`'i bu fixture'lara genişleterek "yama görünürlüğü"nü piksel-seviye (ör. dolgu sınırındaki gradyan sapması) ölçmek. Model tabanlı inpaint (LaMa yerine **Apache-2.0/izinli** bir alternatif) uzun vadeli seçenek — ama araştırma dokümanı değil, uygulama konusu.

### R2 — OCR satır/paragraf birleştirme, çok sütunlu düzende yanlış okuyabilir

`_merge_boxes_into_lines` → `_merge_lines_into_paragraphs` **basit kural** kullanır: dikey boşluk (`gap <= prev_height * 0.6`) + sol hizalama (`abs(cur_x0 - prev_x0) <= prev_height * 1.5`). Dosya başı yorumunda açıkça belirtilir: **çok sütunlu düzen tespiti bilinçli olarak yapılmıyor**.

- İki sütunlu bir taramada, sağ sütunun ilk satırı sol sütunun son satırına "aynı paragrafın devamı" gibi yapışabilir → **okuma sırası bozulur**, blok `role`/`order` yanlış olur.
- `Block.order` bu yüzden "gerçek" değildir (basit üst-→alt, sol-→sağ), `image_reader.py` yorumunda itiraf edilir.

**Etki:** Çeviri değil, **segment sıralaması/bağlam** bozulur. `context_before`/`context_after` yanlış komşular taşır → çeviri tutarlılığı düşer. Çok sütunlu belge (gazete, dergi, broşür) görüntü çevirisinin en zayıf senaryosudur.

**Öneri:** Kısa vadede bu kısıtı belgelemek yeter; uzun vadede çok sütunlu tespit (`x` ekseninde dikey "beyaz şerit" analizi) ayrı bir araştırma notu olarak açılabilir. `pdf_reader.py`'nin çok sütun tespiti yaptığı düşünülürse (CONTRACT metin hattında), görüntü hattı bu konuda asimetrik kalıyor.

### R3 — Font eşleme görüntüde hep "Arial" + sınıflandırma ile sınırlı

`readers/image_reader.py::_block_from_paragraph` her span'ı **sabit `Arial`** (sans) ile işaretler (`font_family="Arial"`, boyut `(y1-y0)*72/dpi`). Ayrıca **bold/italic bilinçli tespit edilmez** (`Style.bold/italic` False kalır — dosya yorumu).

- Buradaki "Arial" yalnızca sans sınıflandırma için bir etiket; gerçek font OCR'den bilinemez. `fontmatch.py`'nin `classify()`'u "Arial"i sans olarak doğru eşler (yorumda bu tuzağın farkında olunduğu belirtilir: "serif" ⊂ "sans-serif").
- **Ama:** kaynak zaten serif bir fontsa (kitap taraması), görüntüde `Arial`→sans olarak çizilir → **serif metin sans olur**, görsel uyum bozulur. Bu kaçınılmaz (OCR fontu görür ama sınıflandırmaz) ancak görüntü çıktısının harfi harfine sadık olmayacağı gerçeğidir.
- **Vurgu (bold/italic) kaybolur:** görüntü OCR'de bold/italic bilgisi çıkarılmadığı için çevrilmiş metin düz (regular) çizilir.

**Etki:** Görüntü çevirisinde "aynı font/üslup" garantisi yoktur; yalnızca "okunabilir, sığdırılmış" metin garanti edilir. Bu, PDF hattının aksine (embedded font'tan gerçek eşleme) görüntü hattının temel bir sınırıdır.

### R4 — Box-yükseklik boyutu ile fit/sığdırma unit karışımı

`writers/image_writer.py::_draw_block` içinde `_style_in_pixels` kullanılır: `Style.size` nokta (pt) iken `Block.bbox` piksel olduğu için bir kopya üretilir ve boyut, **satır yüksekliği ortancası** (`median` of line heights) ile piksel cinsinden ifade edilir. Bu bilinçli ve doğru bir çözüm (yorumda açıklanır).

- **Risk:** `heights` boşsa (bbox'i olmayan satır) `block.bbox.height` kullanılır — çok satırlı bir blokta bu **tüm blok yüksekliği** olur ve tek satır boyutu olarak şişer → fit yanlış, çeviri ya gereksiz küçültülür ya da taşar.
- **İnce yazı boyu:** çok küçük puntolu metinde `max(1, round(final_size))` ile PIL font boyutu en az 1px'e çekilir; bu okunabilirliği kurtarır ama **kutuya sığmayı** garanti etmez (fit STRICT zaten `needs_review` işaretler).

### R5 — Görüntü DPI/metrikleri olmayan kaynaklarda varsayım

`readers/image_reader.py` `_DEFAULT_DPI = 96.0` varsayar (DIP metadata yoksa). Boyut `(y1-y0)*72/dpi` ile hesaplanır. Screenshot/scan araçlarının gömdüğü DPI değişken olduğu için:

- DPI yanlışsa **punto boyutu yanlış** → fit/sığdırma ölçeği kayar.
- Bu, çıktı metninin boyutunu gerçek kaynağa göre büyük/küçük yapabilir; ancak piksel bbox doğru olduğu için `_style_in_pixels` bunu kısmen telafi eder (satır yükseklik ortancası).

**Durum:** Kısmen önemsiz (piksel bbox bağlayıcı), ama kaynak DPI'sı aşırı sapkınsa sınırda yanlış olur. Ölçülmeli.

---

## 3. Performans / darboğazlar

| Nokta | Mevcut davranış | Risk |
|---|---|---|
| OCR model indirme | `RapidOCR()` ilk `recognize()`'de `rapidocr/models/*.onnx`'i (~31 MB) indirir | İlk görüntü çevirisinde bir kez ağ + disk gerekir; çevrimdışı kurulumda model yoksa hata (dosya yorumunda belirtilir). |
| OCR CPU-only | ONNX Runtime CPU, tek thread | Çok sayfalı/skannı belge için yavaş olabilir; batch/GPU yolu yok (torch/paddle yasağına uygun bilinçli tercih). |
| Renk ölçümü | `_box_colors` her span için 2-means (8 iterasyon) tekrar çalışır | Küçük resimlerde ihmal edilir; büyük çok-bloklu taranmış sayfada toplanır ama ölçülmedi. |
| `write_image` | Her sayfa `Image.open` → inpaint → draw | Sayfa başına tam piksel kopyası; bellek/resim boyutu büyükse yavaş. |

---

## 4. Sözleşme (CONTRACT.md) ile çapraz kontrol

- **D4 (Latin-only + yön):** görüntü hattı `Direction.LTR` sabitler, `Block.rotation` **görüntü okuyucusunda hiç kullanılmaz**. Döndürülmüş/yana yatırılmış metin (etiket, ambalaj) OCR'de ya yanlış okunur ya hiç alınmaz. PDF hattı `Block.rotation` + aynalama tespiti yapar; görüntü hattı bunları **bilmez**. → görüntüde döndürülmüş metin sessizce yanlış/ters işlenme riski. CONTRACT §2 ("Latin de eğik/dik/baş aşağı olabilir") uyarısı görüntü hattında **karşılanmıyor**.
- **D6 (bayrak/needs_review):** görüntü hattı `confidence` (OCR) + `needs_review` taşır; `NEEDS_REVIEW_THRESHOLD = 0.80` ile düşük güven işaretlenir. Bu kurallı ve doğru. Ancak **taşma/okunamama** görüntüye özgü ek bir bayrak taşımaz (fit STRICT sadece `needs_review` set eder, `review_reason` yok — `_draw_block` içinde `block.needs_review=True` yeterli mi görülür).
- **Yasak §6 (ağır bağımlılık):** görüntü hattında torch/paddle yok; ONNX Runtime (rapidocr bağımlılığı) kabul edilmiş. Tutarlı.

---

## 5. Ölçülmesi gerekenler (tahmin değil, ölçüm kuralı)

Bu liste bir ölçüm kaydına (`MEASUREMENTS.md`'ye görüntü bölümü) dönüştürülmelidir; bu belge iddiayı değil, **ölçülecek başlıkları** sıralar:

1. **İnpaint yama görünürlüğü:** dokulu/gradyanlı zeminde flat-fill'in görsel sapması (piksel delta histogramı).
2. **Çok sütunlu düzende okuma sırası doğruluğu:** sentetik 2-3 sütunlu taramada `Block.order`'ın beklenen sırayla uyumu.
3. **Font sınıfı kaybı:** serif kaynak görüntünün çıktıda sans'a dönüşmesi — hazır fixture üzerinde doğrulama.
4. **Bold/italic kaybı:** vurgulu kaynak metinde çıktının düz kalması.
5. **Döndürülmüş metin:** `Block.rotation` bilgisi görüntü hattında yok; 90°/180° döndürülmüş etiketlerde davranış.
6. **OCR ilk kurulum:** model indirme süresi + çevrimdışı davranış.
7. **Büyük skan performansı:** çok bloklu sayfa başına OCR+inpaint+draw süresi.

---

## 6. Özet tablo

| Ref | Alan | Önem | Tip | Mevcut durum |
|---|---|---|---|---|
| R1 | flat-fill inpaint | Yüksek | kalite | bilinçli trade-off, ölçülmedi |
| R2 | çok sütunlu okuma sırası | Yüksek | doğruluk | bilinçli yapılmıyor |
| R3 | font/bold-italic kaybı | Orta | sadakat | kaçınılmaz, belgeye işlenmeli |
| R4 | boyut unit karışımı | Düşük | doğruluk | kısmen telafi, sınırda risk |
| R5 | DPI varsayımı | Düşük | doğruluk | pixellik bbox kısmen örter |
| P | OCR perf / ilk indirme | Orta | performans | ölçülmedi |
| D4 | döndürülmüş metin | Yüksek | kapsam | görüntü hattında yok |

**Sonuç:** Görüntü çevirisi mimari olarak eksiksiz ve sözleşmeye uygun; ancak **kalite sınırları ölçümle değil varsayımla** yönetiliyor. En yüksek öncelikli iki konu (R1 düz dolgu yaması, D4 döndürülmüş metin) hem en görünür hem de şu an en az gerekçelendirilmiş olanlardır.