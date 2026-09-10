# Görüntü (Image) Çevirisi İçin Sağlayıcı Araştırması

> **Dal:** `research/image-translation-vision` (öneri) — bu belge ana kodu değiştirmez, yalnızca araştırma kaydıdır.
> **Kapsam:** LayoutKeep'in mevcut raster-görüntü çeviri hattına (*RapidOCR → DocIR → provider → inpaint/yaz*) eklenebilecek yeni sağlayıcı seçeneklerinin değerlendirmesi.
> **Tarih:** 2026-09 (araştırma).

---

## 1. Bugün ne var, ne yok

LayoutKeep görüntüyü **zaten** iki aşamalı çeviriyor:

1. `readers/image_reader.py` → `ocr/engine.py::RapidOcrEngine` (ONNX Runtime, CPU-only) metni çıkarır, `image_reader` bunu satır→paragraf olarak DocIR bloklarına dönüştürür.
2. Çeviri sağlayıcısı (`providers/`) `list[Segment] → list[Segment]` yapar.
3. `writers/image_writer.py` → `ocr/inpaint.py::inpaint_block` metin kutusunu temizler, `fitting/` ölçümüyle kutuya sığdırılmış çeviriyi yeniden çizer.

Yani **"görseli çevir"** işi mimari olarak var. Eksik olan şey, *doğrudan görselden çeviren* (multimodal/vision) bir sağlayıcı alternatifi ve piyasa seçeneklerinin sistematik bir değerlendirmesi değil; şu an çeviri motoru yalnızca **metin** alıyor.

Araştırmanın hedefi: (a) mevcut OCR-then-translate hattına eklenebilecek daha iyi bir **çeviri** motoru, ve (b) gelecekte OCR + translate'i tek çağrıda birleştirebilecek bir **multimodal** sağlayıcı yönü belirlemek.

---

## 2. Sağlayıcı kategorileri

Görüntü çevirisinde üç mimari yaklaşım vardır ve bunlar birbirinin rakibi değil, farklı maliyet/kalite noktalarıdır:

| # | Yaklaşım | Metin ekstraksiyonu | Çeviri | Çıktı |
|---|---|---|---|---|
| A | **OCR + MT ayrı** (bugünkü LayoutKeep) | RapidOCR / Cloud Vision | metin provider'ı | inpaint+redraw |
| B | **Multimodal LLM tek çağrı** (vision) | modelin kendisi | modelin kendisi | metin (kutu geri çizimi hâlâ bizde) |
| C | **Uçtan uca görüntü çevirisi** (image-to-image) | — | — | doğrudan çevrilmiş görüntü |

LayoutKeep'in değer önerisi layout korunması olduğu için **C** (image-to-image üretim) bu projeye uymaz: düzeni "koruyan" bir üretken model, onu sadakatle korumayı değil, estetik olarak *yeniden üretmeyi* öğrenir. Sözleşme (CONTRACT.md) de açıkça "sessizce düzeltmek / yanlış belgeyi doğruymuş gibi vermek bu projede en kötü sonuç" der. Bu yüzden odak **A'nın çeviri ayağını iyileştirmek** ve **B'yi opsiyonel alternatif** olarak değerlendirmektir.

---

## 3. Metin çevirisi sağlayıcıları (A yaklaşımı — mevcut hattın motoru)

Bunlar `list[Segment] -> list[Segment]` kontratına birebir oturur (CONTRACT.md D2). Bugün zaten var: `OpenAICompatProvider`, `DeepLProvider`, `FakeProvider`.

| Sağlayıcı | Tip | Segment JSON'a uyum | LayoutKeep notu |
|---|---|---|---|
| **DeepL** | özel MT servisi | mükemmel (sıralı `text[]` döner, segment kaydırmaz) | Zaten entegre. Marker'ları `<lk0>` XML'e, korunan değerleri `<lkv>` ignore-tag'e çevirir. Doğruluk yüksek, JSON bozulma riski sıfır. |
| **Google Cloud Translation (v3)** | özel MT servisi | mükemmel (`translateText` / batch, sıralı) | DeepL'e benzer, glossary + language detection yerleşik. Fiyat/karakter bazlı. |
| **Azure Translator (v3.0)** | özel MT servisi | mükemmel | DeepL'e benzer; `fromScript/toScript`, dynamic dictionary, custom translator. |
| **OpenAI / GPT (chat)** | LLM | zayıf–orta (JSON array istenirse marker/segment kayması) | `openai_compat.py` ölçümü: %30 geçersiz JSON, %20 çevrilmeden dönen segment. Kaliteli modelle iyi çeviri ama yapılandırılmış çıktı zayıf. |
| **Yerel LLM (LM Studio/Ollama)** | LLM | zayıf–orta (küçük modeller JSON'u tutamıyor) | `MEASUREMENTS.md`: batch 5 çalışıyor, 6 kırılıyor; marker sadakati %57. |

**Sonuç:** Doğruluk ve yapılandırılmış çıktı güvenilirliği açısından **özel MT servisleri (DeepL/Google/Azure) LLM'lerden üstün**. LLM'lerin tek avantajı: yerel/ücretsiz çalışabilmeleri ve bağlama duyarlı serbest çeviri. LayoutKeep ikisini de destekliyor ve bu doğru bir strateji.

**Bu kategorideki uygulanabilir YENİ ek:** DeepL'in yanına **Google Cloud Translation** ve **Azure Translator** eklemek, kullanıcıya üç özel MT seçeneği sunar. Ancak bunlar "görüntü" çevirisi değil, genel metin çevirisi sağlayıcılarıdır — görüntü hattı zaten onları kullanır.

---

## 4. Multimodal / Vision sağlayıcıları (B yaklaşımı — tek çağrıda OCR+çeviri)

Bu modeller bir görüntüyü girdi olarak alır, içindeki metni hem okur hem çevirir. Two-stage hattın hem hata kaynağını (ayrı OCR) hem de bir API turunu ortadan kaldırabilir. Ama **düzen geri yazımı bizde kalır**: model yalnızca çevrilmiş metin (ve ideal olarak kaynak metnin kutu konumları) döner; `writers/image_writer.py` yine inpaint + redraw yapar. Aksi halde C yaklaşımına (image-to-image) savruluruz ve layout sadakati kaybolur.

| Sağlayıcı | Model(ler) | Girdi | Yapılandırılmış çıktı alınabilir mi? | API şekli | Not |
|---|---|---|---|---|---|
| **OpenAI** | `gpt-4o`, `gpt-4.1`, `gpt-4o-mini`, GPT-5 serisi | `image_url` (base64/URL), `detail=auto/low/high` | Evet (JSON mode / function calling) | `/v1/chat/completions` (vision içerik bloğu) | En olgun vision. `detail=high` küçük metni okur ama token maliyeti artar (512×512 tile = 170 token). |
| **Anthropic** | Claude 3.x/4.x (Haiku/Sonnet/Opus) | `image` içerik bloğu (base64) | Evet | `/v1/messages` | El yazısı/yoğun tablo okumada güçlü. Görüntü token'ı ~1,600/1MP civarı. |
| **Google Gemini** | `gemini-2.x/3.x-flash/pro`, `gemini-3.5-flash` | inline bytes / PIL / File API | Evet | `generateContent` / `interactions` | 258 token/tile (~768×768). 1M+ bağlam, çok sayfalı görüntü/PDF desteği. |
| **Yerel multimodal (LM Studio/Ollama/vLLM)** | LLaVA, Qwen-VL, Gemma-3-vision, InternVL, vb. | OpenAI-vision uyumlu bazı sunucular | Kısmen | `/v1/chat/completions` (vision bloğu, sunucu desteklerse) | Ücretsiz/gizlilik. Küçük modellerde kutu koordinatı + JSON tutarlılığı zayıf; `MEASUREMENTS.md`'deki JSON bozulma davranışı burada da geçerli. |

### Vision çıktısından DoIR'e geri eşleme sorunu

A yaklaşımında kutu koordinatları zaten elimizde (DocIR'deki `bbox`). B yaklaşımında model görüntüyü görür ama bize **normalize koordinat** dönmezse (örn. yalnızca çevrilmiş metin listesi), hangi çevirinin hangi kutuya gittiğini eşlemek zorlaşır. Bu yüzden vision modelinden istenecek ideal çıktı:

```json
[
  {"bbox": [x0,y0,x1,y1], "source": "...", "translation": "..."},
  ...
]
```

Ancak çoğu model bbox'ı güvenilir dönmez. **Pragmatik sonuç:** vision alternatifi, OCR aşamasını değiştirmeden bırakıp yalnızca **çeviri** aşamasına bağlam (tam sayfa görüntü) sağlayan bir "context-görüntü" eklentisi olarak daha güvenli entegre edilir. Böylece:

- OCR zaten kutu/koordinatı veriyor (onun doğruluğunu kaybetmeyiz).
- Vision modeli, çevirinin tonunu/bağlamını (başlık mı, dipnot mu, tablo hücresi mi) görerek iyileştirir.
- JSON segment yapısı değişmez, D2 bozulmaz.

---

## 5. Karar matrisi (LayoutKeep özelinde)

| Kriter | DeepL (A, mevcut) | Google/Azure MT (A, yeni) | OpenAI Vision (B) | Gemini Vision (B) | Yerel multimodal (B) |
|---|---|---|---|---|---|
| Yapılandırılmış çıktı güvenilirliği | ★★★★★ | ★★★★★ | ★★★☆ | ★★★☆ | ★★☆ |
| Çeviri doğruluğu (görüntü bağlamı olmadan) | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★☆ |
| Görüntü bağlamından faydalanma | — (yalnız metin) | — | ★★★★☆ | ★★★★☆ | ★★★☆ |
| Yerel/çevrimdışı çalışma | Hayır | Hayır | Hayır | Hayır | **Evet** |
| Ücretsiz katman | Sınırlı (fx) | Sınırlı | Hayır (ücretli) | Sınırlı | Evet |
| Gizlilik (belge buluta çıkıyor) | Evet | Evet | Evet | Evet | **Hayır (yerel)** |
| LayoutKeep'e entegrasyon maliyeti | Yapıldı | Düşük (deepl.py şablon) | Orta (yeni provider + vision blob) | Orta | Düşük (openai_compat + vision blok) |
| Ana kod değişmeden gerçekleşir mi? | — | Evet (yeni dosya) | Yeni dosya + `job.py`'da `kind` | Yeni dosya + `kind` | `openai_compat`'i vision'a genişletme |

**Önerilen sıralama (ana kodu koruyarak, artımlı):**

1. **Kısa vadede yeni sağlayıcı eklemeye gerek yok** — DeepL + OpenAICompat + Fake görüntü çevirisini zaten karşılıyor. Yol haritasına **Google Cloud Translation** ve **Azure Translator** eklemek, "özel MT servisi" seçeneğini zenginleştirir ve `deepl.py`'yi şablon alır (en düşük risk).
2. **Orta vadede vision bağlam eklentisi:** `providers/` altına görüntüyü *ikinci bir bağlam girdisi* olarak modelenaile değiştirmeden taşıyacak bir `VisionContextProvider` sarmalayıcı — D2'yi bozmaz, sadece `translate()` çağrısına opsiyonel görüntü referansı ekler.
3. **Uzun vadede:** Görüntü çıktısını (inpaint kalitesi, font eşleme, çok sütunlu tarama) ölçmek ve `MEASUREMENTS.md`'ye görüntü bölümü eklemek. Ancak bu araştırma belgesi değil, ölçüm kaydıdır.

---

## 6. Kaynaklar (doğrulanmış, 2026-09)

- **Google Cloud Vision API** — `:images:annotate` (TEXT_DETECTION / DOCUMENT_TEXT_DETECTION), OCR + Translation API birlikte resmi eğitim: `cloud.google.com/vision/docs`.
- **Azure AI Vision (Read OCR v3.2/v4.0)** — `:read/analyze` async, kutu + satır + kelime + güven skoru döner; Translator ile iki aşamalı pipeline Microsoft'un resmi önerisi: `learn.microsoft.com/azure/ai-services/`.
- **Azure Translator Document Translation** — görüntü tek parça çevirisi `2025-12-01-preview` olarak dökümante fakat **bölgelerde henüz canlı değil** (UnsupportedApiVersion); resmi çözüm Vision OCR + Translator Text (iki aşamalı).
- **OpenAI vision** — `image_url` içerik bloğu + `detail` parametresi, chat completions üzerinden: `platform.openai.com/docs/guides/vision`.
- **Gemini multimodal** — inline bytes / File API, 258 token/tile; 2026'da `google-genai` SDK: `ai.google.dev/gemini-api/docs/vision`.
- **ACL 2025 — InImageTrans** (Zuo et al.): multimodal LLM tabanlı text-image machine translation; end-to-end image-to-image yönü araştırma konusu, layout sadakati açık problem. (Referans: `aclanthology.org/2025.findings-acl.1039`.)