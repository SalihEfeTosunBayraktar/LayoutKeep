# LayoutKeep — Denetim Bulguları ve Eksiklikler

> Denetleyen: **@bugbountiy** · Tarih: 2026-09 · Git HEAD: `d726807`
> Yöntem: kod incelemesi + gerçek çalıştırma (759 test yeşil, 2 tam denetim turu; canlı dönüşümler;
> uç-durum fixture'ları; hata yolu tetiklemeleri; paketlenmiş exe içerik analizi). Her bulgunun
> kanıtı `dosya:satır` referansı ve/veya `tools/audit/`
> altındaki yeniden koşulabilir betikle verilir. Ana analiz: [AUDIT-PROJE-ANALIZI.md](AUDIT-PROJE-ANALIZI.md)
>
> **Sınıflandırma:**
> - **S1** Sessiz veri kaybı (kullanıcı fark etmeden içerik yok olur) — en yüksek öncelik
> - **S2** Yanlış/kandırıcı davranış (hata vermez ama iddiasını karşılamaz)
> - **S3** Performans/verimlilik (çalışır ama kaynak israfı)
> - **S4** UX/tutarlılık/teknik borç

---

## S1 — Sessiz veri kaybı

### B1 · EPUB okuyucu SVG-sarmalı resimleri hiç görmüyor · 🔴 Yüksek

- **Nerede:** `src/layoutkeep/readers/epub_reader.py:205-253` (`_extract_page_images`) ve `:36` (`BLOCK_TAGS`)
- **Ne oluyor:** `_extract_page_images` yalnız `<img src=...>` arar; EPUB 3'te yaygın olan
  `<svg><image xlink:href="fig.png"/></svg>` sarmalı resimler eşleşmez. `<svg>` ve `<image>` ne
  `BLOCK_TAGS`'te ne de görsel taramasında var.
- **Kanıt (koşuldu):** uç-durum fixture (`lk-audit/edge_epub_test.py`): XHTML içinde
  `<svg><image xlink:href="fig.png"/></svg>` → **0 ImageRef**. Resim EPUB→PDF/DOCX/HTML çıktısında
  sessizce yok; hiçbir uyarı yok.
- **Etki:** kullanıcı EPUB→PDF çevirince "görseller korunmuyor" şikayetinin teknik kökü budur.
  Gutenberg'in `-images-3` kitaplarında eski-üslup `<img>` bulunur (canlı test: pg23319 → 339 ref'in
  337'si taşındı), ama modern EPUB 3 üreticileri (Sigil, Calibre profilleri) SVG sarmayı tercih eder.
- **Düzeltme önerisi:** `_extract_page_images`'a `image` ve `svg image` element taraması eklenmeli
  (`xlink:href` + `href`); `img_idx` sayacı ile `BLOCK_ID_RE`'nin (`epub_writer.py:43`) yeni desenleri
  de tanıması gerekir. **Sahip: `lk-epub`.**

### B2 · OPF kapak resmi (`<meta name="cover">`, `properties="cover-image"`) kayboluyor · 🔴 Yüksek

- **Nerede:** `src/layoutkeep/readers/epub_reader.py:272-293` (`read_epub`)
- **Ne oluyor:** kapak resmi hiçbir XHTML sayfasında `<img>` olarak geçmeyebilir; OPF manifest'te
  `properties="cover-image"` veya `<meta name="cover" content="…"/>` ile bildirilir. Okuyucu bunları
  okumaz. `epub_writer` zip'i bayt-bayt kopyaladığı için **EPUB→EPUB yolunda** kapak hayatta kalır;
  ama **çapraz format** (EPUB→PDF/DOCX/HTML) DocIR'dan kurar ve DocIR'da kapak yoktur → çıktıda kapak yok.
- **Kanıt:** `edge_epub_test.py`: `properties="cover-image"` + `<meta name="cover">` → `len(page.images)==0`.
- **Düzeltme önerisi:** `read_epub` OPF'den kapak item'ını çözse ve ilk `Page.images`'a ekleyecek
  bir `cover: bool` (veya sıra 0 ImageRef) eklese çapraz formatlar da kapak çizebilir. **Sahip: `lk-epub`.**

### B3 · Taranmış PDF sayfaları OCR'a hiç düşmüyor · 🔴 Yüksek

- **Nerede:** `src/layoutkeep/readers/pdf_reader.py` (tüm modül — `is_scanned_page` çağrısı yok) ve
  `readers/image_reader.py:55` (`is_scanned_page` tanımlı ama pdf_reader'dan kimse çağırmıyor)
- **Ne oluyor:** Metin katmanı olmayan (taranmış) bir PDF sayfası 0 blok üretir; OCR katmanı
  (`ocr/engine.py` — RapidOCR, sorunsuz çalışır durumda) yalnız `read_image` (doğrudan PNG/JPG girdisi)
  üzerinden kullanılır. PDF→herhangi-bir-format dönüşümünde taranmış sayfalar boş/serbest geçer.
- **Kanıt (koşuldu):** `check_ocr_gap2.py`: sadece resim içeren sayfa → `blocks=0, ImageRefs=1`;
  CLI herhangi bir hata/uyarı vermeden "çevrildi" raporlar.
- **Etki:** "Images (PNG/JPG): OCR-dependent" README satırı yanıltıcı — taranmış **PDF** (en yaygın
  gerçek kullanım) OCR'a hiç gitmez. Uygulamanın kapsam tablosu bunu kapsıyormuş gibi okunuyor.
- **Düzeltme önerisi:** `read_pdf` sayfa başına `is_scanned_page(page.get_text())` kontrolü yapıp
  sayfayı `image_reader._page_from_image`'a (render → OCR) yönlendirmeli. Mimari zaten hazır; sadece
  bağlanmamış. **Sahip: `lk-pdf` + `lk-ocr`.**

### B4 · `<th>` hücre metni DocIR'a hiç girmiyor · 🟠 Orta

- **Nerede:** `epub_reader.py:36` — `BLOCK_TAGS = {h1..h6, p, li, blockquote, td, pre, code}` — `th` yok
- **Ne oluyor:** tablo başlık hücreleri (`<th>`) ne blok ne de görüntü olur; metin kaybolur. (`td` var,
  `th` unutulmuş.)
- **Kanıt:** `edge_epub_test.py` — `<th>Header Cell Text</th>` → DocIR'da "Header Cell Text" yok.
  DOCX okuyucuda da `th` eşleniği yok denebilir ama DOCX'te hücre her zaman `<w:p>` içerir; sorun
  asıl EPUB tarafında.
- **Düzeltme:** `BLOCK_TAGS`'e `th`; `_role_for` içinde `TABLE`. `epub_writer._BLOCK_ID_RE` zaten
  `[a-zA-Z0-9]+` etiketi kabul ediyor — uyum sorun değil. **Sahip: `lk-epub`.**

### B5 · `<figcaption>` ve diğer gövde dışı etiketler kayboluyor · 🟠 Orta

- **Nerede:** `epub_reader.py:36` (`BLOCK_TAGS`), `:45` (`_CONTAINER_TAGS = div, section, article, aside, main` — `figure`, `figcaption` yok)
- **Ne oluyor:** `<figure><img/><figcaption>…</figcaption></figure>` yapısında `figure`, `_CONTAINER_TAGS`'te
  olmadığından içine inilir; `<figcaption>` blok etiketi olmadığı için metni de düşer.
  (`dl/dt/dd`, `address` benzer kenar etiketler de aynı durumda.)
- **Kanıt:** `edge_epub_test.py` — figcaption metni DocIR'da yok.
- **Düzeltme:** `figcaption` → BLOCK_TAGS (role: `CAPTION`); `figure` → _CONTAINER_TAGS. **Sahip: `lk-epub`.**

### B6 · DOCX okuyucu belge içi resimleri DocIR'a taşımıyor · 🟠 Orta

- **Nerede:** `src/layoutkeep/readers/docx_reader.py` — `ImageRef` hiç geçmiyor (grep: 0 eşleşme)
- **Ne oluyor:** DOCX→PDF/EPUB/HTML çapraz dönüşümünde `word/media/*` resimleri hiç çıkarılmaz;
  DOCX→DOCUX (yerinde yazıcı) yolunda sorun yok (zip kopyalanır), çapraz yolda resimler sessizce yok.
  `epub_reader`'ın ImageRef eklemeden önceki haliyle aynı hata sınıfı — EPUB tarafı düzeltilmiş,
  DOCX tarafı unutulmuş.
- **Düzeltme:** `<w:drawing>/<a:blip r:embed>` → ilişkiden parçaya → base64 ImageRef (page=part sahipli,
  yer = paragraf konumu). **Sahip: `lk-epub` (docx_reader sahibi).**

### B7 · EPUB resimleri akışta konumsuz: hepsi dokümanın sonuna yığılıyor · 🟠 Orta

- **Nerede:** `core/docir.py:258-271` (`Page.content_in_reading_order` — resmi `bbox.y0`'a göre blokların
  arasına sokar) + `epub_reader.py:42` (`_DUMMY_BBOX = BBox(0,0,0,0)`) + `epub_reader.py:248` (ImageRef'e
  bbox olarak yine `_DUMMY_BBOX`)
- **Ne oluyor:** EPUB okuyucu her bloğa ve her resme `(0,0,0,0)` bbox koyar. `content_in_reading_order`
  resmin yerini bbox'tan hesapladığı için tüm resimler `y0=0` okunur → resim bulunduğu paragrafın
  yanına değil, **belge akışının başına/sonuna** serilir.
- **Kanıt (koşuldu):** `imgpos_test.py`: p1 → resim → p2 sıralı XHTML → çıktı sırası
  `[p1, p2, alt-metni, resim]`. EPUB→PDF'te tüm şekiller bölümün sonunda toplu çıkar.
- **Düzeltme:** okuyucu ImageRef'e sıra bilgisi taşımalı. En küçük dokir teması: `ImageRef`'e
  `order: int = 0` alanı eklemek (okuyucu doldurur, `content_in_reading_order` önce order'a, sonra
  y0'a bakar) — ya da reader bloklar arasında sentetik `FIGURE` rolü placeholder blokları üretir.
  Şema değişikliği olduğundan **şef onayı** gerekir (CONTRACT §3: core/). **Sahip: şef + `lk-epub`.**

### B8 · CLI bağlantı hatalarında tam traceback sızdırıyor · 🟠 Orta

- **Nerede:** `cli.py:212-233` — `except TimeoutError` / `except OSError` var; ama `_http_compat.py:184`
  bağlantı reddini **`RuntimeError`** olarak çevirir. `run_batches` ilk partiyi aynen yükselttiği için
  `RuntimeError` CLI'ya fırlar ve `main()`'in `except SystemExit / KeyboardInterrupt` bloğu yakalamaz.
- **Kanıt (koşuldu):** `cli_error_test.py` — kapalı port `127.0.0.1:9`, `--timeout 3`:
  stdout "provider ProtectedProvider model=m"de kalır, stderr'de **21 satırlık tam traceback**,
  exit code 1. Projenin kendi K3 kuralı ("eksik girdi → tek cümle, traceback değil") bağlantı
  durumunda ihlal ediliyor.
- **Etki:** CLI kullanıcı için; GUI kendi `failed.emit` zinciriyle aynı hatayı düzgün gösterir.
- **Düzeltme:** `cli.py`'ya `except RuntimeError` yakalayıcı (tek cümle + exit 1) ya da
  `_http_compat`'ta bağlantı hatalarını `OSError`'a çevirip CLI mevcut bloğunun yakalaması.
  **Sahip: `lk-provider` veya şef (cli.py sahibi).**

---

## S2 — Yanlış/kandırıcı davranış

### B9 · İki tunable ölü: UI'da ayarlanıyor, hiçbir kod okumuyor · 🟠 Orta

- **Nerede:** `core/tunables.py` — `timeout.first_batch_s` (satır ~67, BASIC bölümde!) ve
  `fit.min_scale` (ADVANCED) tanımlı; `grep -rn 'tunables.get("timeout.first_batch_s")' src/` →
  **0 eşleşme**; `fit.min_scale` için de 0. `ui/worker.py:42-46` kendi sabitlerini (`_FIRST_BATCH_BASE_TIMEOUT_S=240`
  vb.) kullanır; `fitting/fit.py:18` `MIN_SCALE = 0.85` sabitini.
- **Ne oluyor:** kullanıcı ayarlar ekranından "İlk parti zaman aşımı"nı değiştirir → GUI worker
  240'ı sabit okumaya devam eder; "En küçük yazı tipi ölçeği"ni değiştirir → sığdırma 0.85'i sabit
  kullanır. Ayar kutusu işe yaramaz ama işe yaramış gibi görünür — ayarlayıcının kendi felsefesi
  ("read at use, not at import") da sessizce ihlal edilmiş olur.
- **Düzeltme:** ya `worker.py:50` `base = tunables.get("timeout.first_batch_s" if is_first else "timeout.warm_batch_s")`
  ve `fit.py` `min_scale` varsayılanını `tunables.get("fit.min_scale")`'e bağlanır; ya da tunable
  tanımı silinir. Vakit: ~10 dk. **Sahip: `lk-ui` + `lk-fitting`.**

### B10 · `epub_reader` `%99 metin` iddiası markup kenarlarıyla çelişiyor · 🟡 Düşük (dokümantasyon)

- **Nerede:** README "The EPUB reader captures about 99% of a book's visible text"
- **Ne oluyor:** B1/B4/B5'teki boşluklar ölçülmüş "%99" iddiasının şartlarını daraltıyor; SVG resimli
  kitaplarda kapsama düştüğü halde README değişmedi. Bu, projenin "ölçülmemiş iddia yok" kültürüne aykırı.
- **Düzeltme:** ya kapsama düzeltilir ya README "Known limits" bölümüne bu kenarlar eklenir.
  **Sahip: şef (docs).**

### B11 · Glossary (terim sözlüğü) yalnız CLI'da; GUI'de hiç yok · 🟡 Orta

- **Nerede:** `cli.py:202-207, 251-256` (`--glossary`); `ui/job.py` (JobConfig'te alan yok);
  `ui/worker.py` (`glossary` hiç geçmiyor)
- **Ne oluyor:** terminoloji tutarlılığı (ölçüm: 83 tekrar eden terimin 6-12'si tutarlı — MEASUREMENTS §6)
  projenin bilinen zayıf noktası ve çözüm aracı (`Glossary`) yazılmış durumda, ama masaüstü kullanıcı
  (asıl hedef kitle) ona erişemiyor. `ui/worker.py` ayrıca `flag_passthrough` sonrası `glossary.verify`
  zincirini de çalıştırmıyor.
- **Düzeltme:** JobConfig'e `glossary_path`; worker'da CLI ile aynı zincir (`_finalize_document`
  içinde `verify`). **Sahip: `lk-ui`.**

### B12 · REFLOW modu yarım: kimse `FitResult.reflow`'u tüketmiyor · 🟡 Orta

- **Nerede:** `fitting/fit.py:149` (`FitResult(..., reflow=True)`) — `grep -rn "\.reflow\b" src/` →
  0 tüketici. `cli.py:333` `FitMode.REFLOW`'u iletebilir ama `pdf_pass.py`'den dönen sonuçta
  `reflow=True`'yu okuyan ve blokları iten kimse yok; `pdf_writer` blokları sabit kutulara yazar.
- **Ne oluyor:** `--fit-mode reflow` bayrağı fiilen `--fit-mode strict` ile aynı davranır
  (taşma bayraklanır, hiçbir blok büyümez). CLI yardımı ("reflow lets blocks grow") kullanıcıyı
  yanıltır.
- **Düzeltme (seçenekler):** (a) bayrak kaldırılırsa dokümantasyon dürüstleşir; (b) `reflow=True`'da
  writer `insert_htmlbox(rect büyütülmüş)`… — ciddi yerleşim motoru gerektirir; şefin kapsam
  kararı. **Sahip: şef + `lk-fitting`.**

### B13 · Bağlam (context) prompt'un %66'sı: maliyet hiç raporlanmıyor, taşıma stratejisi yok · 🟡 Orta (S3'e kayar)

- **Nerede:** `core/docir.py:325-352` (`segments_from_document` her segmente 1 komşu blok bağlam
  ekler) + `providers/batching.py:71-74` (`_content_chars` bağlamı da sayar) + `openai_compat.py:380-389`
  (bağlam istek gövdesine girer)
- **Kanıt (ölçüldü):** pg11.epub → 873 segment; kaynak 165.251 kr, bağlam 326.994 kr → **%66,4**.
  MEASUREMENTS.md de bunu belirtir ("prompt'u kabaca üçe katlar") ama değer zincirinde tek yerde
  görünür durumda; kullanıcıya asla söylenmez, öncesinde kapatılamaz.
- **Ne oluyor:** (1) Üç kez aynı bağlam parçası üç farklı istekte yeniden okunur (i-1, i, i+1 segment
  partileri) — prompt-cache dostu **önek istikrarı** da yok (CacheBlend/RAGCache sınıfı literatür
  tam bunu çözer; küçük partilerle arka-arkaya çalışırken sistem iletisi sabit ama bağlam blokları
  segment sırasıyla değiştiğinden önek cache'i isabet edemez — LM Studio'da llama.cpp önek cache
  istikrarlı önekte ciddi hız getirir). (2) `--limit 5` gibi kısa geçişlerde bile her segment
  iki komşusunu taşır. (3) Ölçüm kararı "bağlam kaldırılmadı" — doğrudur ama alternatifler
  (yalnız sentence-level overlap, yalnız glossary ile destek) denenmemiş.
- **Düzeltme önerisi (küçükten büyüğe):** (a) CLI/GUI tam istatistiğe "context share" yazsın;
  (b) `context_blocks` 0 yapılabilsin (tunable) — mevcut koddaki tek parametre zaten;
  (c) parti içinde öbekleşme aynı anda gönderilen segmentlerde komşuları hariç tut
  (batch zaten bağlamı kapsıyor). **Sahip: `lk-provider` + şef.**

---

## S3 — Performans / verimlilik

### B14 · GUI worker'ın chunk=20 partilemesi AdaptiveBatchSize'ın karşısında çift boşlama yapıyor · 🟡 Orta

- **Nerede:** `ui/worker.py:161` (`chunk_size = tunables.get("batch.chunk_size")` — default 20) +
  `openai_compat.translate` içinde `run_batches(batch_chars=2000, adaptive)`
- **Ne oluyor:** worker 873 segmenti 20'lik chunk'lara böler (44 chunk, ort. 11.187 kr — ölçüldü);
  her chunkProtected→Cached→OpenAI zincirine girer; OpenAI kendi içinde tekrar adaptif partiler
  (1→…→5 büyüme). Sonuç: **AdaptiveBatchSize her chunk başında 1'e resetlenir** — 44 kez "1'den
  başlayıp yeniden keşif" yapar; model 5'e ulaşmadan chunk biter. CLI'da aynı iş tek `translate`
  çağrısı olduğundan keşif bir kez yapılır (simulate: ~309 istek). Yani aynı kitap GUI'de önemli
  ölçüde daha çok istek atar — "GUI ile CLI aynı olmalı" (CONTRACT) ilkesinin performans ayaklığı
  da bozuk.
- **Düzeltme:** worker `chunk_size`'ı kaldırıp iptal/duraklatmayı `on_progress` geri çağrısına taşımalı
  (gerçek iptal noktası zaten parti sınırı; ProtectedProvider'in ilettiği `on_progress` bunu taşır),
  ya da chunk başına resetlenen adaptif durum provider'da iş-bazında (job-scoped) tutulmalı.
  **Sahip: `lk-ui` + `lk-provider`.**

### B15 · Sığdırma retranslate turları da ayrı HTTP istekleri; maliyeti görünmez · 🟡 Düşük-Orta

- **Nerede:** `fitting/fit.py:128-144` (`retranslate` çağrıları) + `cli.py:325-331` / `worker.py:468-475`
- **Ne oluyor:** taşan/alt-dolan her segment için en fazla 3+3 tur tek-segmentli çeviri isteği
  (canlı test: 3 segmentlik PDF'te bile 1 retranslate). W-4 formunda ölçüldü: 10 segmentte
  `shrunk=7` — küçük fontla çözülenler tur atmadan kurtuldu; iyi. Ama `retranslated/expanded`
  katmanlarının istek maliyeti hiçbir raporda sayılmıyor (CLI sadece katman sayılarını basar).
- **Düzeltme:** katman istatistiklerine tur sayısı ekle; muhtemelen `fitting` öncesi `max_len`'in
  ilk istekte sağlanması (bütçe biliniyorsa — PDF'te bbox ölçülebilir) turların çoğunu keser.
  **Sahip: `lk-fitting`.**

### B16 · Çeviri belleği WAL modunda ama `put()` her segmentte `commit()` atıyor · 🟢 Düşük

- **Nerede:** `providers/memory.py:87` — her `put` ayrı `commit`
- **Ne oluyor:** 100 segmentlik bir partide 100 fsync; yerel SSD'de fark edilmez ama WAL'un amacı
  (batch commit) boşa düşer. `CachedProvider.translate` sonunda tek `commit` yeterli olurdu.
- **Düzeltme:** `CachedProvider`'a `put_many` ya da sonda `conn.commit()`. **Sahip: `lk-provider`.**

### B17 · `_rotated_quads` her blok için sayfayı yeniden tarıyor (şüpheli ama küçük) · 🟢 Düşük

- **Nerede:** `writers/pdf_writer.py:220-246`
- **Ne oluyor:** döndürülmüş her blok için `page.get_text("dict", clip=…)` + `search_for` çalışır.
  Rotasyon az dosyada önemsiz; çok döndürülmüş etiketli teknik çizimlerde (LeGO manual vb.)
  kare sayısında artış. Ölçülmeden bırakılmış — şüphe olarak kaydedildi.
- **Düzeltme (isteğe bağlı):** sayfa başına tek tarama sonucu önbelleği. **Sahip: `lk-pdf`.**

### B18 · `.lkproj` dosyaları tüm resimleri base64 olarak şişiriyor · 🟢 Düşük

- **Kanıt:** `_artifacts/e2e/pg79503-images-3.out.lkproj` = **1,17 MB**; pg23319 sınıfı bir kitapta
  (339 resim) proje dosyası onlarca MB'a çıkar. DocIR'ın `asdict`/JSON serileştirmesi bilinçli
  (D5: self-contained) — ama resimli kitaplarda diske yazım süresi ve boyut sert büyür.
- **Düzeltme (opsiyonel):** `save_project`'te resim verisini ayrı parça dosyalarına koyan bir
  "dış referans" modu ya da en azından gzip. Şema değişimi → şef onayı. **Sahip: şef.**

---

## S4 — UX / tutarlılık / teknik borç

### B19 · CLI yetenekleri GUI'de eksik: `--skip`, `--fit-mode`, `--page-range`… · 🟡 Orta

- **Nerede:** `cli.py:384-414` (argparser) vs `ui/job.py:30-41` (JobConfig)
- **Ne oluyor:** JobConfig `page_range` taşıyor (worker `:389-395` kullanıyor) ama `skip`/`limit`
  yok; `fit-mode` GUI'de seçilemez (worker `_fit_pdf_pass` hep `FitMode.STRICT` — `worker.py:491`);
  glossary (B11) ve `--memory` dışında provider timeout override var. Kullanıcı "ilk 20 segmenti
  çevir kaliteye bak" (README'nin önerdiği iş akışı!) tuzağını yalnızca CLI'dan yapabilir.
- **Düzeltme:** kurulum ekranına "sınırlı geçiş" alanı; fit-mode seçici. **Sahip: `lk-ui`.**

### B20 · GUI worker'da hızı bir chunk içinde son batch ezer (displayed rate), ayrıca `_compute_batch_timeout` double-set · 🟢 Düşük

- **Nerede:** `ui/worker.py:179-186` (`timeout = _compute_batch_timeout(...)` — içi `_set_provider_timeout`
  çağırır) + `:186` hemen ardından `_set_provider_timeout(provider, timeout)` tekrar; `:218-225`
  `chars_per_second` chunk'un geneli üzerinden hesaplanır ve son ölçüm öncekini ezer (moving average yok)
- **Ne oluyor:** (1) zararsız ama kirli: aynı değer iki kez set edilir. (2) ETA hızı tek chunk'un
  ortalamasına kilitlenir; uzun kitapta dalgalanma sert görünür. Kozmetik ağırlıklı.
- **Düzeltme:** `_compute_batch_timeout` zaten set ediyor — ikinci satır silinir; hız için EMA. **Sahip: `lk-ui`.**

### B21 · `FakeProvider` `[tr] kaynak` döndürüyor → passthrough tespiti asla tetiklenmez, ölçümler 1.20x şişer · 🟢 Düşük

- **Kanıt:** fake çevirilerde CLI hep `target/source = 1.05–1.23x` raporladı (`[tr] ` öneki yüzünden).
  `is_passthrough` `[tr] Hello world` için False (önek fark).
- **Ne oluyor:** fake provider ile yapılan smoke testlerde genleşme ölçümü anlamsız; geliştirici
  bunu bilmezse yanlış izlenim edinir. Zararsız ama yanltıcı bir ölçüm üretir.
- **Düzeltme:** fake provider önek yerine çevirisiz döndürsün ya da `[tr]` önekini çıkarıp
  gerçek bir kelime değişimi yapsın. **Sahip: `lk-provider`.**

### B22 · `epub_reader` `options={"ignore_ncx": True}` — eski EPUB 2 kitaplarında TOC kaydı yerine işaretlenmiyor · 🟢 Düşük (incelenmeli)

- **Nerede:** `epub_reader.py:274`, `epub_writer.py:61`
- **Ne oluyor:** `ignore_ncx` ile NCX tamamen atlanır. Spine XHTML'leri çevrildiğinden içerik kaybolmaz
  ama EPUB 2 okuyucuları NCX'i TOC olarak kullandığından çeviri sonrası NCX başlıkları eski dilde
  kalır (nav.xhtml de aynı şekilde). "TOC hedef dilde değil" bilinen bir daralmadır ama flag/reason
  üretilmiyor.
- **Düzeltme (küçük):** writer, `<nav>`/NCX başlıklarını da çevrilmiş bloklarla eşleyip güncelleyebilir;
  en azından dokümante edilmeli. **Sahip: `lk-epub`.**

### B23 · `epub_generator` (çapraz EPUB üretimi) rol etiketlerini düzleştiriyor: liste/tablo/kod `<p>` olur · 🟢 Düşük

- **Nerede:** `writers/epub_generator.py` — blok başına `<p>`/`<h1>`/`<h2>` üçlüsünden fazlası yok
  (list/table/code rolleri `<p>` olur; bold/italic span'ler `html.escape(item.text)` ile düzleşir).
- **Ne oluyor:** PDF→EPUB gibi çapraz yollarda çıktı "çevrilmiş düz metin kitabı"dır; liste, tablo ve
  kod rolleri `<p>` olur; bold/italic span'ler `html.escape(item.text)` ile düzleşir.
- **Düzeltme:** `html_writer._ROLE_TAGS` gibi bir eşlemeyi epub_generator da kullanmalı (başlangıç
  noktası zaten yazılı). **Sahip: `lk-epub`.**

### B24 · `pdf_generator._draw_flowing_page` sayfa büyütme mantığı `insert_htmlbox`'ın dönüşüne kör · 🟢 Düşük

- **Nerede:** `writers/pdf_generator.py:73-92` — `spare`>=0 yolunda `curr_y += max(18, rect.height - spare + 6)`
  — `spare` "rect içinde kalan boşluk" olduğundan `rect.height - spare` bloğun yüksekliğidir; ama
  `insert_htmlbox` scale yapmışsa ölçü şimdi yanlış olabilir. Yorumlu, ölçülmemiş; DOCX→PDF gibi
  çapraz yollarda sayfalar arasında büyük boşluklar/girinti görülürse buradan şüphelenin.
- **Düzeltme:** gerçek `filled` ölçüsünü kullanmak (PyMuPDF döndürür). **Sahip: `lk-pdf` (generator sahibi).**

### B25 · Deneme çıktıları birikmiş durumda: `_artifacts/output/` altında 40+ eski e2e dosyası · 🟢 Düşük (hijyen)

- **Nerede:** `_artifacts/output/` — exp_150..185.epub, bs1-5.epub gibi deneme çıktıları.
  `docs/NEREDE-NE-VAR.md` "_artifacts/ git'e girmez" der; `.gitignore` var gibi — denetimde
  `git status` temizdi. Yine de karışıklık üretiyor; exp_* dosyaları silinebilir.
- **Düzeltme:** temizlik. **Sahip: herkes.**

### B26 · `.html`/`.htm` `DOCUMENT_EXTENSIONS` listesinde ama okuyucu yok: girdi reddediliyor · 🟡 Orta

- **Nerede:** `writers/converter.py:14` (`DOCUMENT_EXTENSIONS` içinde `.html, .htm`) vs
  `read_any_document()` (aynı dosya, `:18-41`) — `.html` için reader case'i **yok**.
- **Ne oluyor:** kullanıcı bir `.html` dosyası bırakınca "Unsupported input type '.html'. Expected
  document or image (.png, .jpg, .epub, .pdf, .docx, .lkproj)." hatası alır. Hata metni bile
  listede `.html`'in olduğunu bilmiyor. CLI çıktı tarafında `.html` writer var, UI drop-zone'ı
  `SUPPORTED_INPUT_EXTENSIONS`'i kullanıyor → UI'ya HTML bırakılabilir ama çevrilemez.
- **Kanıt (koşuldu):** `Temp\lk-audit\pass3_live.py` — `translate in.html --to tr` → exit 1,
  "Unsupported input type".
- **Düzeltme:** ya reader case'i ekleyin (`read_html` — `html.parser` ile yeterli, `lxml` gerekmez)
  ya da listelerden ve drop-zone'dan `.html/.htm` girişini kaldırıp hata mesajını düzeltin.
  **Sahip: `lk-pdf` (converter sahibi) veya şef kararı.**

### B27 · `.lkproj` yeniden çevirisi **çift çeviri** yapıyor: `segments_from_document` `block.text`'i (çevrilmiş) kaynak alıyor, `source_text`'i değil · 🔴 Yüksek

- **Nerede:** `core/docir.py::segments_from_document` — segmentin `source`'u bloğun mevcut
  metninden üretilir; `.lkproj` yüklendiğinde `block.text` zaten **ilk çeviriyi içerir**.
- **Ne oluyor:** kullanıcı projeyi yeniden açıp farklı dil/modelle çevirirse, modelden gelen
  metnin üstüne çeviri yapılır: iki kez çevrilmiş metin → `"[tr] [tr] Form W-4"` gibi katmanlaşma
  (fake provider'la kanıtlandı; gerçek sağlayıcıda "çevrilmiş çeviri" = kalite çöküşü).
- **Kanıt (koşuldu):** `pass3_final.py` — W-4 `.lkproj` iki kez çevrildi: 1. geçiş `[tr] Form W-4`,
  2. geçiş `[tr] [tr] Form W-4`; `source_text` alanı DocIR'da duruyor ama **hiç okunmuyor**.
- **Düzeltme:** `segments_from_document` bir `.lkproj` girdisinde (veya `Document.retranslate`
  bayrağında) `source_text`'i tercih etmeli; `source_text` boşsa mevcut davranış. 
  **Sahip: şef (`core/`'un sahibi) — şema değişikliği değil, okuma tercihinde düzeltme.**
- **✅ DÜZELTİLDİ (2026-09-09, commit `054c93d`):** `segments_from_document` artık `_original_text(block)`
  okuyor; bağlam da aynı kaynaktan geliyor. Kanıt betiği `pass3_final.py` eski davranışı
  belgeler (regresyon testi: `tests/test_core_retranslate.py`).

### B28 · Bellekten dönen segmentlerde `needs_review`/`review_reason` **kayboluyor** · 🟡 Orta

- **Nerede:** `providers/memory.py::TranslationMemory.get` — saklanan alanlar target/model/tarih;
  bayraklar saklanmıyor.
- **Ne oluyor:** ilk geçişte taşma/uyarı nedeniyle `needs_review=True` ile belleğe yazılan
  segment, ikinci geçişte (aynı metin/model) bayraksız "temiz" döner. Kullanıcı ilk seferde
  17 taşma uyarısı görür, ikincisinde hiç — oysa metin aynıdır. D6 "sessizce boş bırakma" ruhu
 yla çelişir: bayrak kaybı da sessizdir.
- **Kanıt (koşuldu):** `pass3_tm.py` bölüm 5 — `needs_review=True` ile `put`, geri okumada
  `needs_review=False`.
- **Düzeltme:** `put` çağrısı `needs_review`'u da saklasın (SQL şema + 1 alan), `get` döndürsün.
  **Sahip: `lk-provider`.**

### B29 · DeepL `glossary` parametresi alınıyor ama isteğe **hiç konmuyor** · 🟡 Orta

- **Nerede:** `providers/deepl.py:239` — `glossary: dict[str, str] | None = None` imzada var,
  `:245-260` arası gövdede **tek bir kullanım yok** (payload'a `glossary_id` eklenmiyor).
- **Ne oluyor:** kullanıcı terim sözlüğü tanımlarsa (B11'de GUI'de eksik olduğu bulunmuştu),
  OpenAI-uyumlu sağlayıcı prompt'a ekler (`openai_compat.py:423-425`), DeepL ise **sessizce yok sayar**.
- **Kanıt:** `grep -n glossary deepl.py` → yalnız 1 satır (imza). İstek gövdesi inceledi:
  `glossary_id` yok.
- **Düzeltme (kısa yol):** DeepL glossary API'si ile kullanıcı sözlüğünü oluşturup `glossary_id`
  göndermek ayrı iş; kısa vadede en azından **belgeleyin** ("DeepL şu an glossary kullanmıyor") ve
  UI'da DeepL seçiliyken glossary alanını devre dışı bırakın. **Sahip: `lk-provider`+`lk-ui`.**

### B30 · `parse_page_range` geçersiz/boş ifadeyi **sessizce "tüm sayfalar"a** çeviriyor · 🟡 Orta

- **Nerede:** `core/range_helper.py::parse_page_range` — `0`, `-1`, `abc`, `99` (5 sayfalık
  dokümanda), `""` → hepsi `{1..5}` döner.
- **Ne oluyor:** kullanıcı "3. sayfa" yazmak isterken yanlışlıkla `0` yazarsa CLI/GUI sessizce
  **tüm belgeyi** çevirir (maliyet + karışıklık). Hata yok, uyarı yok — D6'nın "sessizce
  düzeltme" yasağının ta kendisi.
- **Kanıt (koşuldu):** `pass3_live.py` bölüm 1: beş uçlu da `{1,2,3,4,5}`.
- **Düzeltme:** geçersiz ifade → `ValueError` (kısa mesajla); `99` gibi aralık dışı → boş küre
  kırpılsın ama kullanıcıya "sayfa yok" bilgisi verilsin. **Sahip: şef (`core/` sahibi).**

### B31 · Paketlenmiş exe'de OCR **hiç çalışmıyor**: model dosyaları + config pakete girmemiş · 🔴 Yüksek

- **Nerede:** `packaging/layoutkeep_onefile.spec:65+` (`datas`) — rapidocr'ın `models/*.onnx`
  (31,7 MB) ve `config.yaml` **datas'a eklenmemiş**; PKG-00.toc'ta 0 `.onnx`, 0 rapidocr config girdisi.
- **Ne oluyor:** exe'de görüntü çevirisine tıklandığında RapidOCR kendi paket dizininde
  (`_MEIPASS/rapidocr/models/`) model arar — PyInstaller onefile'da bu dizin **yok**; engine
  internetten indirmeye çalışır, offline kullanıcıda **çöker** ya da FileNotFoundError.
  PYZ'de rapidocr .py kodu var (82 modül), yalnızca veriler eksik.
- **Kanıt (koşuldu):** `exe_ocr_verdict.py` + `pkg_parse2.py`: PKG içinde `.onnx` = 0,
  `assets/fonts` = 28 (karşılaştırma: fontlar doğru paketlenmiş; toplam 192 DATA girdisi).
- **Düzeltme:** `datas`'a `.venv/Lib/site-packages/rapidocr/models/*.onnx` + `config.yaml`
  ekleyin (`('...models', 'rapidocr/models')` hedefiyle) ve `_MEIPASS` çözümlemesini
  `ocr/engine.py`'de yapın (`sys._MEIPASS` kontrolü). **Sahip: `lk-ocr` + paketleme.**
- **✅ DÜZELTİLDİ (2026-09-09, commit `054c93d`):** ağırlıklar pakete girdi, engine bundle'da
  yolları açıkça veriyor (model eşlemesi stage bazlı: det/rec/cls). Exe 138→164 MB.
  Yeniden üretilen PKG-00.toc artık 3 `.onnx` + `rapidocr/config.yaml` listeliyor
  (`pkg_parse2.py` ile doğrulandı). Regresyon: `tests/test_ocr_engine_packaging.py`.

### B32 · Taranmış PDF algılama eşiği çok kaba: `len(text) < 10` — "Page 1" metni bile OCR'ı atlatıyor · 🟡 Orta

- **Nerede:** `readers/image_reader.py:47` `_SCANNED_TEXT_CHAR_THRESHOLD = 10` +
  `is_scanned_page()` — ama zaten **kimse çağırmıyor** (B3). Bu bulgu B3'ün eşik katmanıdır.
- **Ne oluyor:** Sayfa numarası veya kısa bir başlık içeren taranmış sayfa "metin katmanı var"
  sayılır → OCR'a hiç gidilmez → o sayfanın gövde metni sessizce yok olur (0 blok yerine
  "yalnızca sayfa numarası" bloğu).
- **Kanıt (koşuldu):** `pass3_live.py` bölüm 4: boş-görüntü sayfası 0 blok; üzerine 6 karakter
  ("Page 1") eklenince 1 blok (6 karakter) — gövde yok, OCR tetiklenmedi.
- **Düzeltme:** B3'ün parçası olarak: pdf_reader sayfa başına `is_scanned_page` çağırsın; eşik
  katmanı olarak "metin kapsama oranı" (karakter/piksel) daha sağlam, saf karakter sayısı değil.
  **Sahip: `lk-pdf`+`lk-ocr`.**

### B33 · `NEEDS_REVIEW_THRESHOLD` ölü sabit: kod `tunables.get("ocr.needs_review_threshold")` kullanıyor, sabit hiç okunmuyor · 🟢 Düşük

- **Nerede:** `readers/image_reader.py:42` tanım; kullanım `:188` `tunables.get(...)` — sabit
  yalnızca testte import ediliyor (`tests/test_image_reader.py:27`).
- **Ne oluyor:** İki doğruluk kaynağı birbirinden kopuk: sabit 0.80, tunable'ın varsayılanı
  değişirse test hâlâ 0.80'i doğrular ama kod farklı davranır → sessiz sapma.
- **Düzeltme:** sabiti kaldırıp testi tunable varsayılanına bağlamak. **Sahip: `lk-ocr`.**


---

## Negatif bulgu (şüphe vardı, temiz çıktı)

- **"EPUB→PDF'te hiçbir resim taşınmıyor" iddiası** genel olarak doğru **değil**: eski-üslup
  `<img src>` kitaplarında resimler taşınıyor (pg23319: 339 ref → 337 resim çıktıda; pg79501: 2/3).
  Kayıp; SVG-sarmalı (B1), kapak (B2) ve konum yanlışlığı (B7) özelinde. Kullanıcının genel hissi
  doğru, ama tam mekanizma budur.
- **FakeProvider sızıntısı**: fake çevirilerde marker'lar doğru taşınıyor; `passthrough` önek
  yüzünden tetiklenmiyor (B21) — bu bir fake-provider özellik boşluğu, çekirdek bug'ı değil.
- **Mirror detection yanlış pozitif veriyor mu?** `Hello How Are You Today.pdf` üzerinde koşuldu:
  12 blok, hiçbiri aynalanmış işaretlenmedi. Ölçülmüş mekanizma (`_span_is_mirrored`, ±0.65
  projeksiyon) sağlam görünüyor.

---

## Öncelik matrisi (önerilen sıra)

| # | Bulgu | Sınıf | Efor (tahmin) | Önerilen ajan |
|---|---|---|---|---|
| 1 | B1 SVG resim kaybı | S1 | M | `lk-epub` |
| 2 | B3 taranmış PDF → OCR boşluğu | S1 | M | `lk-pdf`+`lk-ocr` |
| 3 | B2 kapak resmi | S1 | S | `lk-epub` |
| 4 | B7 resim konumu (şema) | S1 | M+şef | şef+`lk-epub` |
| 5 | B4/B5 th/figcaption | S1 | S | `lk-epub` |
| 6 | B6 DOCX resimleri | S1 | M | `lk-epub` (docx) |
| 7 | B8 CLI traceback | S2 | S | şef |
| 8 | B9 ölü tunable'lar | S2 | S | `lk-ui`+`lk-fitting` |
| 9 | B14 GUI chunk×adaptive çifte keşif | S3 | M | `lk-ui`+`lk-provider` |
| 10 | B11 glossary GUI | S2 | S | `lk-ui` |
| 11 | B12 reflow yarım | S2 | kararı şef | şef |
| 12 | B13 context %66 raporlanması | S3 | S | `lk-provider` |
| 13 | B19/B20/B21/B22 küçük UX | S4 | S | ilgili ajanlar |

(Efor: S ≤ 1 saat, M ≤ yarım gün.)

## Yeniden üretim

Denetim betikleri `tools/audit/` altında (repo içinde, commit'li):
`edge_epub_test.py` (B1/B2/B4/B5), `imgpos_test.py` (B7), `check_ocr_gap2.py` (B3),
`cli_error_test.py` (B8), `check_perf2.py` (B13/B14 verisi), `check_imgloss.py` (resim kapsaması),
`e2e_pipeline.py` (tam akış dumanı). Hepsi LayoutKeep venv'i ile koşuldu; `pytest tests/ -q` → 754
passed. Canlı model (LM Studio localhost:1234) denetim sırasında kapalıydı; model bağlantılı
davranışlar (parti keşfi, marker tamiri) ölçüm dosyalarına ve mevcut test paketine dayanır.
Kurulum kalıbı: `python tools/audit/<betik>.py` — `_common.py` repo kökünü kendisi bulur,
karalama çıktıları `%TEMP%/lk-audit`'e gider (depoya değil). Betik → bulgu eşlemesi:
`tools/audit/README.md`.

---

# 3-Geçiş Derin Denetim (2. tur) — Yeni Bulgular

> İkinci tam tur (2026-09): kaynak okuma kapsamı tamamlandı (fitting/measure, fontmatch, docx_writer,
> deepl, UI'nin tamamı, conftest, CI, packaging, RELEASE-V1, image dokümanları), tutarlılık denetimi
> ve canlı uç testleri yeniden koşuldu. **Test süiti: 759/759 yeşil (192,8 sn)** — 3 geçişin sonunda
> 5 yeni test eklenmiş. Bu bölüm B26–B33'ü içerir.


## Öncelik matrisi güncellemesi (2. tur)

| # | Bulgu | Sınıf | Efor | Önerilen ajan |
|---|---|---|---|---|
| 1 | B31 exe'de OCR modelleri yok | S1 | S (spec datas satırı) | `lk-ocr`+paketleme |
| 2 | B27 .lkproj çift çeviri | S1 | S (`source_text` tercih koşulu) | şef (core/) |
| 3 | B3+B32 taranmış PDF eşik katmanı | S1 | M | `lk-pdf`+`lk-ocr` |
| 4 | B26 .html girdi listesi vs reader | S2 | S | converter sahibi |
| 5 | B28 bellek bayrak kaybı | S2 | S | `lk-provider` |
| 6 | B30 page-range sessiz "hepsi" | S2 | S | şef (core/) |
| 7 | B29 DeepL glossary yok sayılıyor | S2 | S | `lk-provider`+`lk-ui` |
| 8 | B33 ölü sabit | S4 | S | `lk-ocr` |

## 2. tur yeniden üretim betikleri

- `pass1_img_docs.py` — image dokümanı iddialarının koda karşı doğrulaması (R1 vurgu, R3, R4, D4, vision)
- `pass2_full.py` — sınıf boyutları, .html tutarsızlığı, ölü tunable tam listesi, 2-means maliyet ölçümü (kutu başına 9 ms)
- `tunable_audit.py` — 10 tunable'ın tamamının kullanım denetimi: 2 ölü (`timeout.first_batch_s`, `fit.min_scale`)
- `pass3_live.py` — page-range uçları, .html girdi, skip+limit, scanned-PDF eşiği
- `pass3_final.py` — **B27 çift çeviri kanıtı** (`[tr] [tr]` katmanlaşması)
- `pass3_tm.py` — bellek bayrak kaybı (B28) + model kimliği ayrımı + context_blocks=0 yolu
- `exe_ocr_verdict.py` / `pkg_parse2.py` — **B31**: PKG içeriğinde 0 `.onnx`

---

# Bağımsız Değerlendirme — Image Pipeline Dokümanları (@bugbountiy)

> Kullanıcı talebi: image-translation/pipeline adlı MD'lerin hepsini oku, kendi fikirlerini ayrı
> bölüme not et. Okunanlar: `image-pipeline-audit.md`, `image-translation-architecture.md`,
> `image-translation-backlog.md`, `image-translation-providers.md` (toplam 506 satır).
> Aşağıdaki her iddia bu denetimin gerçek koşularıyla test edildi; sonuçlar kanıtlı.

## Dokümanların kalitesi: genel olarak yüksek

Bu 4 doküman projenin en olgun araştırma katmanı. Güçlü yanları:

- **Sözleşme disiplini:** her tasarımda CONTRACT D1-D6 ve Yasak §6 ekranlara taşınıyor; hiçbir
  öneri `core/` şemasını değiştirmiyor. `VisionAwareProvider` sarmalayıcı önerisi mimari olarak
  doğru kalıyor: provider kontratı kırılmadan görüntü bağlamı taşınır.
- **"Tahmin değil ölçüm" kültürü:** R1 (inpaint), R5 (DPI) gibi her risk "ölçülmedi — ölçülmeli"
  diye dürüstçe işaretlenmiş. Sağlam yaklaşım.

## Yanlış veya eksik bulduğum iddialar (kanıtla)

**1. `image-pipeline-audit.md` R1'in vurgu iddiası kodla çelişiyor.** Doküman "vurgulu metnin
dolgu rengi vurgu görünümünü kapatır → çeviri vurgusuz düz zemine yazılır" diyor. **Yanlış.**
`inpaint_block` span bazlı çalışır ve `span.style.background`'u kullanır — vurgulu span'ın bg'si
sarı ise yama **sarıya** boyanır (koştum: `pass1_img_docs.py`, sonuç `#ffff00` korundu). Vurgu
kaybolmuyor. Dokümanın doğru kısmı gradyan/dokulu zemin eleştirisi: onu da koştum, zemindeki
gradyanla tek renk yaması arasında gözle görülür kopma var. **Önerim:** R1'in vurgu cümlesi
dokümandan çıkarılmalı; gradyan bölümü kalmalı.

**2. `image-translation-providers.md` "vision modeli bbox dönmezse eşleme zorlaşır" derken
`block_id` çözümünü atlıyor.** Mimari doküman (`architecture.md` §2.2) tam bunu çözüyor:
vision'a segmentlerin `block_id` listesiyle JSON isteniyor, OCR kutuları korunuyor. Providers
dokümanı §4'te bu çözümü görmüş ama "bbox istersek kırılır" bariyerini önceleyip sayfa-tamamı
görüntü yaklaşımlına savrulmuş. Mimari dokümanın `id` eşlemesi daha sağlam; providers dokümanı
"bbox isteme" varsayımını bırakıp `id` yanıt formatına göre yazılmalı.

**3. `backlog.md` P1.1/P1.2 (Google/Azure) önceliklendirmesi bu denetimin bulgularıyla ters.**
Backlog "önce Google/Azure, sonra vision" diyor. Ama denetim bulgularım B1-B3, B26-B32'yi
görünce: kullanıcıya **şimdi** sessiz veri kaybı yaşatan hatalar (SVG resim, kapak, taranmış PDF,
exe'de OCR yok) yeni sağlayıcı eklemekten önce gelmeli. Yeni sağlayıcı = mevcut sorunları çoğaltan
yeni yüzey. Backlog'un kendi kuralı "ana kodu değiştirme"; ama B27 çift-çeviri gibi çekirdek
davranış hataları düzeltilmeden 3 sağlayıcı daha eklemek kalabalık ama riskli.

**4. Vision önceliğinde ölçüm boşluğu:** providers dokümanı OpenAI vision'ı "JSON mode evet"
diyor ama projenin kendi ölçümü (`MEASUREMENTS.md`: batch 5 çalışıyor, 6 kırılıyor) LLM JSON
güvenilirliğini gösteriyor. Vision JSON iddiası hiç ölçülmemiş. P1.3'e başlamadan önce
"vision modelden 10-segmentlik JSON döner mi" testi (tek curl) koşulmalı — backlog Faz 0'a
eklenmeli.

**5. `image-pipeline-audit.md` D4/rotation eleştirisi doğru ama yarım:** "görüntü hattında
rotation yok" tespiti doğru (koştum: image_reader'da `rotation` geçmiyor). Ama PDF hattının
rotation'ı *nasıl* kullandığını söylemiyor: pdf_reader `Block.rotation`'ı blok metadata olarak
taşır ama PDF writer'da döndürülmüş metin çizimi de sınırlı. Yani görüntü hattı PDF hattından
"kopyalanacak" bir çözüme sahip değil; doküman kalan izlenim veriyor.

**6. Exe/OCR (B31) hiçbir image dokümanında yok.** `image-pipeline-audit.md` "OCR ilk kurulum:
model indirme süresi + çevrimdışı davranış ölçülmeli" diyor (P) ama **paketlenmiş exe'de
modellerin hiç olmadığı** gerçeğini kaçırıyor. Geliştirme ortamında model var (venv'te indirilmiş),
exe'de yok — dokümanın "offline kullanıcıda hata" öngörüsü geliştirme makinelerinde görünmez,
sadece paketlenmiş yapıda patlar. Bu, dokümanların geliştirici-merceralı bakışının kanıtı.

## Katıldığım tasarım kararları

- **C yaklaşımının (image-to-image üretim) reddi:** kesinlikle doğru. LayoutKeep'in kimliği
  "düzeni koru"; üretken model estetik yeniden üretir, sadakat etmez. Ayrıca AGPL + LaMa CC BY-NC-SA
  lisans çatışması tespiti yerinde.
- **A yaklaşımının (OCR + MT) omurga olarak korunması:** doğru; B31 düzeltilirse mevcut hat
  çalışır durumda.
- **`VisionAwareProvider`'ın sarmalayıcı + `inner` fallback'i:** D2'yi koruyan tek temiz yol.
  `openai_compat` zaten `content` dizisini destekleyen transport'a sahip (`image_url` eklemek
  küçük yüzey).
- **Çok sütunlu okuma sırası (R2) bilinçli erteleme:** faz olarak doğru; ama pdf_reader'ın çok
  sütun tespiti görüntü hattına taşınabilir (beyaz şerit analizi önerisi makul).

## Somut önerilerim (öncelik sırasıyla)

1. **Önce B31** (exe OCR modelleri) — image dokümanlarının "offline kırılma" öngörüsünü paketleme
   gerçeğine bağlar; tek spec satırı + `_MEIPASS` çözümü, yarım saatlik iş.
2. **B27'yi düzeltmeden vision'a başlamayın:** vision sonuçları da `segments_from_document`
   üzerinden akar; çift-çeviri bug'ı vision'ı da kirletir.
3. **Faz 0'a "vision JSON güvenilirliği" ölçümü ekleyin** (tek sağlayıcı, 10 segment, gerçek
   curl) — P1.3'ün ön koşulu.
4. **`image-pipeline-audit.md` R1'in vurgu cümlesini düzeltin** (kanıt: vurgu korunuyor).
5. **Providers dokümanının §4'ünü `block_id` eşleme formatına göre yeniden yazın** — mimari
   dokümanla tutarlı olur.
6. **Backlog önceliğini AUDIT-BULGULAR matrisiyle hizalayın:** sessiz kayıplar (S1 sınıfı)
   yeni sağlayıcı entegrasyonundan önce gelir.

## Genel hüküm

Bu dokümanlar "araştırma disiplinli, sözleşme saygılı" bir katman; vizyoner kısımları
(backlog/providers) sağlam ama öncelik sıralaması mevcut hata envanteriyle yeniden
ilişkilendirilmeli. Image hattının bugünkü en büyük gerçek riski dokümanların öngördüğü
değil: **paketlenmiş exe'de OCR'ın hiç çalışmaması** (B31) ve **taranmış PDF'in OCR'a hiç
düşmemesi** (B3/B32). Vision yolculuğuna başlamadan önce bu iki sessiz kayıp kapatılmalı.
