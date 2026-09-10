# Görüntü Çevirisi — Implementasyon Backlog'u

> **Dal:** araştırma belgesi — ana kodu değiştirmez; iş listesi sunar.
> **Bağımlı belgeler:** `image-translation-providers.md` (sağlayıcı kararı), `image-translation-architecture.md` (tasarım), `image-pipeline-audit.md` (risk kayıtları).
> **Kural:** CONTRACT.md — `core/` şeması değişmez, `providers/` ağır bağımlılık almaz, API anahtarı düz metne yazılmaz (OS keyring), her iş çalıştırıp çıktı gösterilir.

Bu backlog "hepsini sırayla yap" isteğinin **ana koda dokunmadan** uygulanabilir listesidir. Her madde tek başına küçük, üstlenebilir ve test edilebilir tutuldu. Öncelik ve bağımlılık belirtilir.

---

## Faz 0 — Öncelik: riskleri ölç (kod yazmadan önce)

| # | Madde | Dosya/alan | Çıktı | Öncelik |
|---|---|---|---|---|
| 0.1 | İnpaint düz-dolgu yama görünürlüğünü ölç | `_artifacts/` + `tests/test_inpaint.py` | 2-3 dokulu/gradyanlı fixture; çıktı raporu (dolgu-sınır piksel delta istatistiği) | P0 |
| 0.2 | 2-3 sütunlu görüntüde okuma sırasını ölç | `tests/test_image_reader.py` | Beklenen→fiili `Block.order` matrisi | P0 |
| 0.3 | Serif kaynak görüntünün çıktıda sans'a dönüşmesini doğrulayan fixture | `tests/` | R3 (font sınıf kaybı) davranışını sabitleyen iddia | P1 |
| 0.4 | 90/180° döndürülmüş etiket görüntüsünde davranış ölçümü | `tests/` | `Block.rotation`'a görüntü hattının cevap vermediğini doğrulayan kayıt | P1 |
| 0.5 | OCR ilk kurulum + büyük tarama süresi | `_artifacts/` | `MEASUREMENTS.md` "görüntü" bölümü taslak | P2 |

Bu fazın hiçbir ürünü `src/` altına girmez; `_artifacts/` ve `tests/` ile `docs/` arasında döner. Amaç, Faz 1'deki kod kararlarını **ölçümle** gerekçelendirmek (D5/D6 + "tahmin değil ölçüm" kuralı).

---

## Faz 1 — Yeni çeviri sağlayıcıları (ana kodu en az değiştir)

**İlke:** mevcut `providers/*` kontratı (`list[Segment] → list[Segment]`) bozulmaz; her yeni sağlayıcı **yapısal olarak en az riskli** şablonda eklenir. "DeepL gibi bidirected-markup + sıra" yöntemi kanıtlanmış (`deepl.py` şablon).

### P1.1 — Google Cloud Translation v3 (metin, özel MT)
- **Dosya (yeni):** `src/layoutkeep/providers/google_translate.py`
- **Şablon:** `deepl.py` (sıralı `text[]`, `tag_handling`, `ignore_tags` yerine Google'ın `mime_type=text/html`'lı eş-API'si).
- **Ana kod etkisi:** sadece `ui/job.py::ProviderConfig.kind` + `cli.py::_build_provider` + `ui/provider_settings*` listing/kind——yeni `kind = "google"`. **core/ şemasına dokunmaz.**
- **Kabul mål:** `README.md`'nin sağlayıcı listesine ek + `test_provider_google.py` (deepl testlerini şablon alır: free/paid host ayrımı yok ama kimlik belirli host'a gönderir; `usage` ile test).
- **Bağımlı:** yok.

### P1.2 — Azure Translator v3.0 (metin, özel MT)
- **Dosya (yeni):** `src/layoutkeep/providers/azure_translate.py`
- **Şablon:** `deepl.py`. Azure `TextTranslatorClient` yerine **stdlib `urllib`** (proje kuralı: ağır bağımlılık yok; Azure SDK'sı sadece curl-equivalent).
- **Özel nokta:** `api.cognitive.microsofttranslator.com/translate?api-version=3.0` query + `Ocp-Apim-Subscription-Key` header'ı.
- **Ana kod etkisi:** yeni `kind = "azure"`. Region bilgisi ProviderProfile'da opsiyonel alan.
- **Bağımlı:** yok.

### P1.3 — `VisionAwareProvider` (multimodal opsiyon, ana kodu en az eden yol)
- **Dosyalar (yeni):** `src/layoutkeep/providers/vision.py` + `src/layoutkeep/providers/_vision_http.py` (transport ayrı).
- **Şablon:** `openai_compat.py`'nin transport'u yeniden kullanılır; yalnızca `content` block'u string değil `[{type:text},{type:image_url}]` olur.
- **Ana kod etkisi:** `ui/job.py::ProviderConfig.kind = "vision"` + `worker.py::_build_provider` + `cli.py::_build_provider`'a görüntü kaynağını (input path) `page_images` olarak geçirmek.
  - En az_kodlu yol: `ProviderConfig`'e **opsiyonel** `image_path: str | None` alanı ekle (dataclass alanı = ana kodda tek satır; `core/` değil, `ui/job.py`/`cli.py` modeli).
  - `VisionAwareProvider`, `inner` (OpenAI-compat veya DeepL) sarmalayıcı; vision çağrısı eksik/hatalı dönerse segment `inner.translate` ile doldurulur, dönmeyenler `needs_review` (D6).
- **Fallback garantisi:** Hiçbir segment sessizce boş dönmez; her `id` ya vision sonucu ya `inner` sonucuyla eşleşir; ikisi de olmazsa `needs_review=True` + `review_reason.`
- **Bağımlı:** Faz 0'daki ölçümler (hangi görüntü boyutu/encod işe yarar) doğrulanmış olmalı.
- **Risk notu:** görüntü buluta çıkar → `provider_settings` uyarı metni gerekir (privacy).

### P1.4 — LMStudio/Ollama **multimodal** sunucuda vision denemesi (varsayımsal)
- OpenAI-vision uyumlu `/v1/chat/completions` content-block'u destekleyen yerel sunucular (örn. LM Studio'nun daha yeni sürümleri). **Transport eklemesiz** `vision.py` doğrudan kullanır; tek fark base_url.
- **Önkoşul:** `openai_compat.py`'unun vision content-block'unu reddetmediğinden emin olmak (zaten aynı chat uç); yeni `provider` dosyası gerekmez, yapılandırma yeterli.
- **Bağımlı:** P1.2/1.3 tamamlandığında bedava; ölçümde `MEASUREMENTS.md`'ye yerel-vision satırı eklenir.

---

## Faz 2 — Görüntü hattı kalite iyileştirmeleri (ölçüm odaklı)

| # | Madde | Dosyalar | Not |
|---|---|---|---|
| 2.1 | `test_inpaint` fixture genişliği: dokulu/gradyanlı zeminde delta ölçümü | `tests/test_inpaint.py` + `_artifacts/` | Faz 0.1'in kalıcı fixture'a dönüşümü |
| 2.2 | Çok sütunlu okuma sırası için basit aritmetik tespit (x-ekseninde dikey beyaz şerit) | `readers/image_reader.py` (opsiyonel mod özelliği; varsayılan bugunkü davranış) | CONTRACT bozulmaz (davranış değişikliği ayrı PR) |
| 2.3 | `Block.rotation`'ın görüntü hattında kullanımına dair **araştırma notu** (uygulanmasa da) | `docs/` | D4'ün görüntü karşılığını resmileştir, tasarımı ertele |
| 2.4 | Font fallback'ının görüntü ÇERMESİ (serif→sans) beklenen; bunu belgele | `docs/` + README | Kullanıcı beklentisini ayarlamak |
| 2.5 | Görüntü `confidence` düşüklüğünde `review_reason`'ı zenginleştir | `readers/image_reader.py` | OCR nedeniyle zaten işaretli; ekranda detay görünür |
| 2.6 | DPI/<=varsayım>sınırı: çok tuhaf DPI'da (örn. 72 vs 300) doğru boyut için `_style_in_pixels`'e birim testi | `tests/` | R5 pending'ten çıkarma |

---

## Faz 3 — UI (ana koda dokunarak, minimal)

> UI, CONTRACT'te ayrı sahiplik (`lk-ui`). Bu maddeler yalnızca **servis kullanılabilirliği** ekler; ekran yapısını bozmaz.

- **3.1** `provider_settings_form.py` + `provider_settings.py`'ye yeni `kind` değerlerini ekle (kind combobox listesi + açıklama satırı). Her yeni provider için tek satır.
- **3.2** Vision için **"Bu sağlayıcı görüntüyü sunucuya gönderir"** uyarı satırı (gizlilik), DeepL satırı gibi `status` metni ile.
- **3.3** `provider_profile.py::_DEFAULT_PROFILES`'a LMS-style vision örneği eklemek (yorum satırıyla "vision-ready" ifadesi). Yerel multimodal kurulumu yapan kullanıcıya yol gösterir.
- **3.4** Dil seçimi: vision sağlayıcısında dil listesi kısıtlaması **yok** (uygulanmaz; Gemini/OpenAI geniş); DeepL gibi daraltma gerekmesin.

---

## Faz 4 — Doğrulama / Measurement (D5)

- **4.1** `_artifacts/` içine `sample_image_translation` testi: 1 sayfalık tarama al → OCR → çevir → yaz çıktısını üret, sonra `test_inpaint + test_image_reader + test_image_writer`'ları bu iş üzerinde koştur (e2e).
- **4.2** `tools/coherence_check.py`'ye görüntü modu ekleme (terim tutarlılığı OCR-işli veride de ölçülür). ANCESTRAÖNEM: görüntü bağlamı tutarlılığı ölçüm için doğrudan karşılığı yok (PDF/EPUB'a göre). Ancak Faz 0.2 (çok sütunlu okuma) sonuçları buna girdi olur.
- **4.3** `MEASUREMENTS.md`'ye **"7. Görüntü çevirisi"** bölümü: genleşme, batch uyumu, vision vs OCR+MT kalitesi, süre, inpaint delta.

---

## Faz 5 — Commit stratejisi (ana koda minimum dokunuş)

1. Her Faz-1 sağlayıcı **kendi commit/PR**'sinde: `providers/<ad>.py` + `ui/job.py + cli.py`'deki 3 satırık kind entegrasyonu + testi. `core/`'e hiç dokunma.
2. Vision (P1.3) iki aşamada: (a) `vision.py` + transport (sadece providers'a yeni kod); (b) `worker.py + cli.py` entegrasyonu (en dış katman).
3. Her commit INGILIZCE: `Add the Google Translate provider` / `Add a vision-context wrapper provider` vb. (CONTRACT §4: kod/commit İngilizce, rapor Türkçe).
4. **Yasak check:** yeni dosyalarda torch/paddle/import yoksa, API anahtarı keyring'ten geliyorsa (düz metin yok), sözleşme ihlali yok demektir.

---

## "Ana kod değiştirilmeden" ölçütü (bu iş listesinin neyi değiştirdiği)

| Katman | Bu backlog ne yapar? | Ana kod koruması |
|---|---|---|
| `core/` (DocIR, segment, protected) | **hiçbir şey** | Bozulmaz (D1/D2) |
| `providers/` | 2 yeni metin sağlayıcı + 1 vision sarmalayıcı | Mevcut imza korunur |
| `fitting/` | hiçbir şey | D3 |
| `readers/image_reader.py` | sadece test/fixture önerileri + çok sütun opsiyonel iyileştirme | D2'ye saygılı |
| `writers/image_writer.py` | sadece measurement önerisi | D3 |
| `ui/job.py / cli.py` | sadece yeni `kind` değeri + görüntü path geçişi | Dataclass alan ek, şema değişmez |
| `ui/provider_settings*` | yeni kind listelemek + privacy uyarısı | Davranış ekleme, kırma yok |
| `tests/` | genişletilmiş fixture ve yeni testler | Doğrulama D5 |
| `docs/` | tüm araştırma + ölçüm kayıtları | Şef dizini |

**Son karar:** Backlog, **öncelik Google/Azure metin sağlayıcıları (P1.1/P1.2)**, ondan sonra **opsiyonel vision bağlam sarmalayıcısı (P1.3)**, en son da görüntü kalitesi ölçümleri (Faz 2) şeklindedir. Vision ile layout'tan ödün vermeden yararlanmak, ancak sarmalayıcı + fallback (inner) deseniyle mümkündür; aksi halde sözleşme bozulur veya çeviri kalitesi görünmez şekilde düşer.