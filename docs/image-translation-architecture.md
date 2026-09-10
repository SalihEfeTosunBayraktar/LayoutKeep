# Görüntü Çevirisi Entegrasyon Mimarisi (Tasarım)

> **Dal:** araştırma belgesi — ana kodu değiştirmez.
> **Amaç:** Vision/multimodal sağlayıcıyı LayoutKeep'e **mevcut sözleşmeyi (CONTRACT.md) bozmadan** nasıl bağlayacağımızı somut dosya/fonksiyon düzeyinde çizmek.
> **Kural:** `core/` şeması değişmez (D1), `providers/` layout-kör kalır (D2), sığdırma ayrı aşamadır (D3). Ağır bağımlılık (torch/paddle) girmez (Yasak §6).

---

## 1. Bugünkü veri akışı (görüntü)

```
.png/.jpg
   │  read_any_document()                     [writers/converter.py]
   ▼
read_image()  ──►  RapidOcrEngine.recognize()  [readers/image_reader.py]
   │                  TextBox(bbox, confidence, text)
   ▼
DocIR: Page → Block(id, bbox, role, lines)
   │  segments_from_document()                [core/docir.py]
   ▼
list[Segment] (block_id, source, context_before/after, max_len)
   │  provider.translate(segments, src, tgt)  [providers/*]
   ▼
list[Segment].target doldurulmuş
   │  pdf-fixing gerekmez (görüntü değil PDF); fit_segment STRICT
   ▼
apply_segments() → write_image()  [writers/image_writer.py]
   │   inpaint_block() + fit_segment + ImageDraw çizim
   ▼
çıktı görüntü (ya da scanned-PDF ise PDF)
```

Kritik gözlem: **görüntü hattında görüntünün kendisi hiçbir zaman provider'a gitmez.** `Segment.source` yalnızca OCR'den gelen metin dizgisidir. Vision sağlayıcı eklemek istiyorsak iki seçenek vardır:

- **(i) Görüntüyü çeviri bağlamı olarak eklemek** (D2'yi korur: provider hâlâ `list[Segment]` alır, görüntü opsiyonel ek girdi).
- **(ii) Görüntüyü birincil girdi yapmak** (D2'yi kırar: provider artık `list[Segment]` değil görüntü alır → yeni kontrat gerekir, `core/` değişir).

Öneri açık: **(i)**. Bu, sözleşmeyi ve ana kodu korur.

---

## 2. Önerilen genişletme: `VisionAwareProvider` (varsayımsal, yeni dosya)

`providers/` altına **yeni bir sarmalayıcı (wrapper)** olarak eklenir; mevcut `base.TranslationProvider` imzası genişletilmez, aynen korunur.

### 2.1 Sözleşmeye ek opsiyonel girdi

Mevcut imza (değişmez):

```python
def translate(self, segments, src_lang, tgt_lang, glossary=None, on_progress=None) -> list[Segment]
```

Önerilen: görüntü referansını `Segment`'a gömmeden, sarmalayıcının **kurulum ayarı** olarak taşımak. Yani provider inşa edilirken:

```python
provider = VisionAwareProvider(inner, page_images={"img1#0": image_bytes, ...})
```

Burada `inner` herhangi bir metin provider'ı (`DeepLProvider`, `OpenAICompatProvider` vb.), `page_images` ise `block_id → görüntü` eşlemesidir. Ama D2 katı yorumlanırsa provider'ın DocIR/font/bbox bilmemesi gerekir; görüntü zaten "içeriğin kendisi"dir, layout değil — bu yüzden sınır aşılmaz.

### 2.2 `VisionAwareProvider.translate` nasıl çalışır

İki faz:

1. **Görüntüyi vision modeline gönder**, şu çıktıyı iste (JSON):

   ```json
   [
     {"id": "img1#0", "translation": "…", "hint": "başlık/…"},
     {"id": "img1#1", "translation": "…"}
   ]
   ```

   Burada `id`, segmentin `block_id`'sidir (OCR zaten vermişti). Model segment bazında değil, **tam sayfa görüntü bazında** bakıp tüm metin bloklarını çevirir.
2. **`id` üzerinden geri eşle**; dönmeyen segmentler `inner` (fallback metin provider'ı) ile çevrilir veya `needs_review` işaretlenir (D6 uyarınca asla sessizce boş bırakılmaz).

Bu iki faz, hata toleransı açısından `openai_compat.py`'nin mevcut adaptive-batch + marker-repair mantığına benzetilir: görüntü çağrısı başarısız/eksik dönerse fallback'e düşülür, segment kaybı `needs_review` ile raporlanır.

### 2.3 Neden `inner` fallback gereklidir

- Yerel multimodal modellerde JSON/bbox güvenilirliği düşük (bkz. providers raporu §4).
- Vision çağrısı tek nokta arızası olursa (rate-limit, model yok), job'un tamamı çökmesin.
- `inner` (DeepL gibi yapısal olarak güvenilir bir MT) her zaman "segment düzeyinde garanti" sağlar.

---

## 3. Dosya/katman etki haritası (hangi dosya ne yapar)

Ana koda dokunmadan gerçekleştirilebilecek katman değişiklikleri **yeni dosya** olarak listelenir; mevcut dosyalar ancak *minimal* eklenmeyle genişler ve her biri ayrı bir commit/PR konusu olur.

| Katman | Yeni dosya | Değişen dosya | Amaç | CONTRACT riski |
|---|---|---|---|---|
| Provider | `providers/vision.py` | — | `VisionAwareProvider` wrapper + vision HTTP (OpenAI/Gemini uyumlu) | Yok (D2 korunur: hâlâ Segment alır) |
| Provider | `providers/vision_transport.py` | — | görüntü base64/gzip + multipart + vision response parse | Yok |
| Job modeli | — | `ui/job.py` (`ProviderConfig.kind == "vision"`) | yeni `kind` değeri | Düşük; sadece enum genişlemesi |
| İnşa | — | `ui/worker.py::_build_provider` + `cli.py::_build_provider` | görüntüyü okuyup `page_images` kurmak | Düşük; zaten provider inşa noktası |
| UI | `providers/vision_settings.py` (opsiyonel) | — | vision anahtarı/model seçimi | Yok |

**Not:** `core/` hiçbir alt ajan tarafından değiştirilmez (CONTRACT §3). Bu tasarımda `core/docir.py` (DocIR şeması) değişmez — görüntüler `Segment`'a değil, sarmalayıcıya dışarıdan verilir. Böylece şema güncelleme talebi şefe gitmez.

---

## 4. Vision çağrısı için tel (wire) formatı

### 4.1 OpenAI-uyumlu vision (LM Studio/Ollama/vLLM dahil)

OpenAI Chat Completions'taki çok-parçalı içerik bloğu kullanılır:

```json
{
  "model": "llava-13b",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Bu görüntüdeki tüm metinleri çevir: JSON..."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
      ]
    }
  ]
}
```

Bu, `openai_compat.py`'nin zaten konuştuğu `/v1/chat/completions` ile aynı uç noktadır — tek fark `content`'in string değil dizi (karma içerik) olması. Bu yüzden `VisionAwareProvider`, `OpenAICompatProvider`'in transport'unu **yeniden kullanabilir**; yeni HTTP katmanı yazmaya gerek yoktur.

### 4.2 Gemini / Anthropic

Format farklıdır (base64 `inline_data` / `image` bloğu). Bunlar için ayrı transport gerekir; kısa vadede öncelik **OpenAI-uyumlu** (yerel + OpenAI tek kod yolu) olmalı, Gemini/Anthropic sonraki iterasyona bırakılmalıdır.

---

## 5. Görüntüyü provider'a taşıma maliyeti ve boyut

- Görüntü base64'e çevrilince ~%33 büyür. 4K tarama PNG'si 10–20 MB olabilir → 13–27 MB istek gövdesi. Cloud sağlayıcılar bunu reddedebilir (örn. bazıları 10–20 MB sınır).
- **Çözüm:** göndermeden önce **düşük çözünürlüklü önizleme** üret (örn. en uzun kenar 1024px, JPEG kalite ~80). Vision modelleri OCR için tam çözünürlüğe değil, okunabilir netliğe ihtiyaç duyar; `detail=low` (OpenAI) veya tile sayısını düşüren boyutlandırma maliyeti ciddi azaltır.
- **Gizlilik:** görüntü buluta çıkıyorsa kullanıcıya açıkça bildirilir (mevcut `provider_settings` akışında anahtar girişi sırasında). Yerel multimodal kullanılıyorsa belge makineden çıkmaz.

---

## 6. Uygulama adımları (backlog özeti)

Ayrıntılı madde listesi `image-translation-backlog.md` içindedir. Kısa özet:

1. `providers/vision.py` + `vision_transport.py` yeni dosya (wrapper + HTTP).
2. `ProviderConfig.kind` değerine `"vision"` ekle (küçük enum genişlemesi).
3. `_build_provider`'ı iki yerde (worker + cli) görüntü kaynağını okuyacak şekilde genişlet (görüntü dosyası varsa `page_images` kur).
4. Fallback: vision çağrısı eksik/hatalı dönerse `inner` metin provider'ına düş (asla segment kaybetme).
5. Ölçüm: görüntü çıktı kalitesi (inpaint + font + taşma) `MEASUREMENTS.md`'ye görüntü bölümü olarak eklenir.

---

## 7. Neden bu tasarım "güvenli"dir

- **D1:** DocIR şeması hiç değişmez; görüntü `Segment`'a girmez.
- **D2:** `providers/` hâlâ `list[Segment] → list[Segment]`; görüntü opsiyonel, sarmalayıcı-içi bir ayar.
- **D3:** sığdırma ayrı (`fitting/`), vision çeviriye dokunmaz.
- **D5:** `.lkproj`/yeniden çalıştırma değişmez; vision sonucu da aynı segment yapısına yazılır.
- **D6:** eksik/yanlış vision çıktısı `needs_review` ile işaretlenir, sessizce doldurulmaz.
- **Yasak §6:** torch/paddle girmez; yalnızca stdlib HTTP (`urllib`) + mevcut transport yeniden kullanımı.