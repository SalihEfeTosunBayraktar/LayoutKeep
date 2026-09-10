# LayoutKeep — Proje Analizi (Bağımsız Denetim)

> Denetim tarihi: 2026-09 (git HEAD: `d726807`)
> Denetleyen: **@bugbountiy** (bağımsız denetim ajanı)
> Yöntem: kaynak kod okuma + **gerçek çalıştırma** (754 test, canlı EPUB/PDF/DOCX dönüşümleri, uç-durum
> fixture'ları, hata yolu tetiklemeleri). Bu belgedeki her iddia ya çalışan bir komutun çıktısına ya da
> `dosya:satır` referansına dayanır; tahmin yok.
> Eksiklik ve hata listesi ayrı dosyada: **[AUDIT-BULGULAR.md](AUDIT-BULGULAR.md)**

---

## 1. Proje tek cümleyle ne yapıyor?

LayoutKeep; PDF, EPUB, DOCX, HTML ve taranmış görüntüleri **düzeni bozulmadan** çeviren (EN→TR başta
olmak üzere Latin dilleri), yerel çalışabilen (LM Studio / Ollama / herhangi bir OpenAI-uyumlu uç nokta
/ DeepL) bir masaüstü çeviri uygulamasıdır. "Düzen korunarak" ifadesinin somut anlamı: çevrilen metin
orijinal kutusuna, orijinal fontuna en yakın metric-uyumlu fontla, orijinal rengiyle ve hizasıyla geri
yazılır; sığmayan çeviri için küçültme → yeniden çeviri isteme → taşma bayrağı kademeleri işletilir.

Proje aynı zamanda bir **araştırma disiplini** sergiler: her tasarım kararı ölçümle gerekçelendirilmiş
(`docs/MEASUREMENTS.md`), mimari kurallar yazılı sözleşmeyle sabitlenmiş (`docs/CONTRACT.md`), her
modülün sahibi ve görev panosu tanımlı (`_agents/TASKBOARD.md`). Kod ~14.000 satır Python, test paketi
**754 test, 192 saniyede tamamı yeşil** (denetimde yeniden koşuldu).

## 2. Mimari — veri nasıl akıyor?

Tek ara gösterim: **DocIR** (`core/docir.py`). Her okuyucu DocIR üretir, her yazıcı DocIR tüketir;
okuyucu-yazıcı çiftleri birbirini tanımaz (`CONTRACT.md D1`). Çeviri katmanı (`providers/`) yalnızca
`Segment` görür — font, bbox, PDF kavramı yoktur (`D2`). Sığdırma (`fitting/`) çeviriden sonra ayrı bir
aşamadır ve gerekirse sağlayıcıdan yeniden çeviri ister (`D3`).

```
readers/            DocIR                 providers/            fitting/           writers/
pdf_reader  ──┐                          ┌─ openai_compat ─┐
epub_reader ──┤   Document / Page /       ├─ deepl          │  fit_segment      ┌─ pdf_writer (kaynağı yerinde düzenler)
docx_reader ──┼─▶ Block / Line / Span ──▶ ├─ fake           ├─▶ (shrink →     ──┼─ pdf_generator (sıfırdan üretir)
image_reader┘   ImageRef / Segment        ├─ cached (TM)    │   retranslate →  ├─ epub_writer / epub_generator
(OCR)           Style / BBox             ├─ memory (SQLite)│   expand)         ├─ docx_writer / docx_generator
                                          └─ protected (değer koruma)           ├─ html_writer / image_writer
                                          glossary, passthrough, batching        └─ converter (orkestrasyon)
```

### 2.1 DocIR'ın taşıdığı şey

| Tip | Ne taşır | Neden önemli |
|---|---|---|
| `Document` | sayfalar, kaynak/hedef dil, metadata | `.lkproj` olarak JSON'a gidiş-dönüş yapar (D5: iş kaydedilebilir, tekrar açılabilir) |
| `Page` | bloklar + `images: list[ImageRef]` + `source_ref` | PDF'te sayfa indeksi, EPUB'ta XHTML href'i, görüntüde dosya yolu |
| `Block` | `role` (title/heading/body/list/table/footnote/formula/code/figure/page_number/…), `align`, `rotation`, `order`, `confidence`, `needs_review`, `review_reason`, `source_text` | rol, çevrilip çevrilmeyeceğini; `order`, çok-sütunlu okuma sırasını; `rotation`, eğik metni; bayraklar insan denetimini belirler |
| `Span`/`Style` | font ailesi, punto, bold/italic, renk, `font_path` (sığdırma aşamasının doldurduğu gerçek font dosyası) | görsel sadakatın tamamı bu alanlarda |
| `ImageRef` | bbox + **base64 veri** + format | çapraz format yazıcıları belgeyi sıfırdan kurarken resimleri yeniden çizebilsin diye |
| `Segment` | `block_id`, `source`, `target`, `context_before/after`, `max_len`, `confidence`, `needs_review` | sağlayıcının gördüğü tek tip (D2); `block_id` cevabı yerine geri götürür |

### 2.2 Çeviri protokolü (tellin ayrıntısı — alt projenin kalbi)

1. `segments_from_document` blokları `Segment`'lere düzler; her birine 1 komşu blok bağlam ekler.
2. `ProtectedProvider` (koruma sarmalayıcı):
   - **Yalnızca-veri** segmentleri (tümü rakam/işaret, `is_data_only`) modele hiç gitmez — cevabı kendisi.
   - Veri **içeren** segmentlerde ölçüler, parça numaraları, form kimlikleri (`34 Nm`, `Form W-4`,
     `1545-0074`, `0.3+0.2 mm`…) `protect()` desenleriyle U+E000..U+E001 sarmalı dijital tokenlara
     çevrilir; model gerçek değeri asla görmez, cevap kaynak `Protection.literals`'tan geri konur
     (`restore`). Kaybolan token → `needs_review` + gerekçe. Ölçümlü gerekçe: W-4 formunda 162 değer
     korunmuş, hepsi birebir dönmüş.
3. `CachedProvider`: SQLite çeviri belleği — (kaynak metin, diller, **model kimliği**) SHA-256 anahtarı;
   başka modelin çevirisi asla servis edilmez. WM üzerinden `ProtectedProvider`'ın dışında değil
   içinde durur (bilinçli: token'lı hali saklanır, "63 Nm" ve "150 Nm" aynı önbellek girdisini paylaşır).
4. `OpenAICompatProvider`: stdlib `urllib` ile `/v1/chat/completions`. Segmentleri
   `batch_chars=2000` karakter bütçesiyle partiler; parti boyutu **adaptiftir** (`AdaptiveBatchSize`):
   1'den başlar, bozuk/eksik JSON dönüşte kalıcı tavana küçülür (ölçüm: gemma-4-e4b'de 5 sağlam, 6 kırık).
   Tel protokolü: `[{id, text, context_before, context_after, max_len}, ...]` → cevap
   `[{"id":…, "text":…}, …]`. Satır-içi biçim `<0>kalın</0>` marker'ları taşınır; marker çokluğu
   (`Counter`) kaynaktan cevaba birebir geçmezse hedefe yönelik tamir turu atılır; o da başarısızsa
   segment `needs_review` olur. JSON bozuksa "kendi cevabını geçerli JSON'a çevir" tamir turu.
5. Sonra `flag_passthrough`: model metni aynen geri verdiyse (≥4 kelime) bayraklanır — ölçümle bulunan
   gerçek bir kusur (gemma-4-e2b 60 segmentte 10'u bağlamlıyken aynen döndürmüş).
6. `Glossary.verify`: terim sözlüğü hedefte geçmiyorsa bayraklar. (Yalnızca CLI'da takılı; GUI'de
   bağlanmamış — bkz. BULGULAR B11.)
7. `apply_segments` (core): cevapları bloklara yazar. Marker'lar geri `Span`'lere parse edilir;
   bozuksa düz metin konur ve "kalın/italik biçimlendirme kayboldu" bayrağı düşer. `block.source_text`
   orijinali (marker'lı biçimiyle) saklar — `.lkproj` insan gözlemi için kaynak-çeviri yan yana taşır.

### 2.3 Sığdırma motoru (fitting/)

`fit_segment` iki yönlü çalışır (ölçüm: EN→TR ort. 0.93x ama bloklar 0.64x–1.40x arası):
- **Taşma yönü**: 0.85'e kadar küçült → sığmazsa `max_len` karakter bütçesiyle yeniden çeviri iste
  (bütçeyi her turda daraltarak, en çok 3 tur) → hâlâ sığmazsa STRICT modda `needs_review`
  ("çeviri kutuya sığmadı, küçültme yetmedi"), REFLOW modunda büyüme sinyali.
- **Alt-dolma yönü**: çeviri kutunun %75'inden azını dolduruyorsa (EN→TR'nin 0.64x kuyruğu) daha uzun
  bir çeviri ister; uzun aday sığmıyorsa reddedilir — dolgu uğruna taşma yaratılmaz.

Ölçüm dikişi (`MeasureFn`): PDF'te `pdf_writer.measure_fit` — PyMuPDF `insert_htmlbox`'ı özel bir
scratch sayfasında gerçekten dener; döndürülen `scale` yazım anında gerçek uygulanır. Font çözümü
`fitting/fontmatch.py`: kaynağın gömülü fontu hedef dilin gliflerini zaten taşıyorsa (glif kapsam
denetimi `fontTools` ile) **o** font yeniden kullanılır; taşımıyorsa metric-uyumlu bundled font
(Tinos↔Times, Arimo↔Arial, Carlito↔Calibri, Caladea↔Cambria, Cousine↔Courier, Noto) seçilir.

### 2.4 Yazıcılar — iki ayrı strateji

| Strateji | Modüller | Ne yapar |
|---|---|---|
| **Yerinde düzenleme** (kaynak = hedef formatı) | `pdf_writer`, `epub_writer`, `docx_writer`, `image_writer` | Kaynak dosyayı açar, yalnızca değişen metni cerrahi olarak değiştirir. PDF: redaction ile eski glifler silinir (resim/vektör özellikle korunur), çeviri aynı kutuya gerçek fontla yazılır; her stil için font **karakter-bazlı subset** edilip gömülür. EPUB: zip girdileri bayt-bayt kopyalanır, yalnızca değişen blokların metni regex-konumlu tekil editle değişir (ebooklib'in bozucu yeniden serileştirmesinden kaçınılır). |
| **Sıfırdan üretim** (çapraz format) | `pdf_generator`, `epub_generator`, `docx_generator`, `html_writer` | DocIR'dan yeni belge kurar. EPUB→PDF: MuPDF **Story** motoru — `page-break-before`'i bilir (bölümler yeni sayfa başlar), resimler data-URI olarak akışa in-line edilir; okuyucunun çözümlediği CSS punto/hiza taşınır. |

### 2.5 Masaüstü uygulaması (PySide6)

Üç ekran: Kurulum (`job_setup`) → İlerleme (`progress`: sayaç, ETA, canlı kaynak/hedef yan-yana
önizleme, duraklat/sürdür) → Tamamlandı (`completion`: çıktıyı aç / klasörde göster / istatistikler —
segment, hız, "düzen sadakati" = bayraksız segment oranı). Arka plan `TranslationWorker(QThread)`
CLI ile **aynı** core/provider/fitting çağrılarını kullanır (GUI↔CLI sapması CONTRACT'a göre bug).
Tüm tunable'lar ayarlar dialogundan çalışma zamanında değişebilir (ama ikisi ölü çıktı — B9).
Crash log: sys-hook + `faulthandler` (C seviyesi çökmelerde bile stack kalır), AppData altına yazılır.

### 2.6 LayoutKeepLLM (alt proje)

Kendi mini çeviri modelinin fine-tune'u (Qwen2.5-7B, QLoRA, Kaggle'da eğitim). Amaç **protokol
sadakati**: çok segmentli JSON'u eksiksiz döndürmek, `<N>` marker'larını ve korunan değer token'larını
birebir taşımak, hiçbir segmenti aynen iade etmemek. `01_Dataset` üreticisi 6.000 kayıtlı veri seti
üretir (65 elle yazılmış domain uzmanı çiftin katmanlı genişletilmesi); `05_Optimization_DPO` +
`pdf_evaluator` ile DPO hazırlığı; `06_Model_Export_GGUF` llama.cpp'e export. Bu denetim ana
uygulamaya odaklandı; alt proje ayrıca denetlenmelidir.

## 3. Ölçülmüş gerçekler (uygulamanın kararlarını çerçeveleyen)

- **EN→TR genleşme: 0.93x ort.** (fizibilitedeki 1.15x varsayımını çürüttü), ama bloklar **0.64x–1.40x**
  arası → sığdırma motorunun varlık nedeni sistemik genleşme değil, **varyans**.
- **Parti boyutu: 5 çalışır, 6 kırılır** (gemma-4-e4b) → AdaptiveBatchSize'ın doğrudan gerekçesi.
- **Hız: ~12 sn/segment** (gemma-4-e4b, 8K bağlam, tam GPU) → 826 segmentlik kitap ≈ 2.5–3 saat;
  çeviri belleği tekrar eden metni (koşan başlık/altbilgi) atlar.
- **Tutarlılık**: bağlam göndermek bir modelde sessiz geçirmeye (10/60 segment aynen döndü!), başka
  modelde terim tutarlılığına zarar veriyor → bağlam açık/kapalı karar verilmedi, `passthrough`
  tespiti eklendi (bu gerginlik denetim bulgularına da yansıyor — B13).
- **VRAM**: LM Studio'un 262k varsayılan bağlamı KV cache'i patlatıyordu; 8K + tek yuva çözüm.

## 4. Güçlü yönler (kanıtıyla)

1. **Sessiz kaybı önleme refleksi her yerde**: `apply_segments` eşleşmeyen çeviri kimliklerini
   (`orphans`) rapor eder; `run_batches` ilk parti hariç her hatayı bayrağa çevirir, işi düşürmez;
   `_review_copy` hiçbir zaman kaynak metinle "sahte çeviri" üretmez; aynalanmış metin sessizce
   düzeltilmeyip bayraklanır (CONTRACT D4: "kullanıcıya yanlış belgeyi doğruymuş gibi vermek en kötü
   sonuçtur").
2. **Cerrahi EPUB/DOCX yazımı**: hem ebooklib hem python-docx'in yeniden serileştirme hasarları
   (nbsp, öz-kapanan etiketler, rsid'ler) belgelenmiş ve bayt-düzeyi editle aşılmış. Kimlik testleri
   (çevrilmemiş EPUB'ın çıktıyla diff'i boş) var.
3. **Font zinciri dürüst**: kaynak font glif kapsamını taşıyorsa yeniden kullanılır; taşımıyorsa metric
   uyumlu yedek; bold/italic'in gerçekten teslim edildiği `head.macStyle`'dan doğrulanır, edilmeyen
   stilde base-14'e düşer; her font belgenin gerçek karakterlerine subset edilir + `garbage=4` dedup.
4. **Değer koruma katmanı** gerçekçi desenlerle (tolerans, tork, para, OMB no, şema çağrı numarası)
   ve "kaybolan değer = bayrak, asla sessiz düzeltme yok" politikasıyla.
5. **Test disiplini**: 754 test yeşil; ama README'nin kendi dürüst uyarısı geçerli — "her ciddi hata
   şimdiye dek gerçek belgeyle çalıştırmaktan çıktı, geçen testten değil". Bu denetim de öyle buldu:
   754 test yeşil iken aşağıdaki sessiz kayıpların tümü canlı uç-durum tetiklemesiyle ortaya çıktı.

## 5. Zayıf yönler / risk alanları (özet — ayrıntılı liste AUDIT-BULGULAR.md'de)

- **Girdi kapsama boşlukları sessiz veri kaybına dönüşüyor**: SVG-sarmalı EPUB resimleri, OPF kapak
  resmi, `<th>`/`<figcaption>` metinleri, DOCX kaynaklı resimler, taranmış PDF'ler — hiçbiri hata
  vermez, sadece çıktıda yok olurlar. Kullanıcının "EPUB→PDF'te görüntüler korunmuyor" şikayetinin
  teknik kökü budur: eski-üslup `<img src>` kitaplarında resimler taşınıyor (canlı test: 339 ImageRef'in
  337'si çıktı PDF'te), ama SVG-sarmalı/kapak resimli kitaplarda sessizce düşüyor.
- **"Ölçülmediyse varsayma" ilkesi bağlam (context) konusunda askıya alınmış**: prompt'un ~%66'sı
  komşu metin; bilinçli bir kararla korunuyor ama maliyeti hiçbir yerde raporlanmıyor (B13).
- **GUI↔CLI paritesi eksik**: glossary, fit-mode, page-range yalnız bir tarafta; iki tunable ölü (B9,
  B11, B12, B26).
- **REFLOW yarımdur**: `FitResult.reflow=True` üreten tek yol (fit.py) var, ama `reflow` alanını
  tüketen hiçbir yazıcı/kod yok — CLI bayrağı ve enum değerine rağmen reflow modu fiilen
  "taşmayı bayrakla" ile aynı (B12).

## 6. Denetim sırasında gerçekten koşulanlar (doğrulanabilirlik)

| Ne koşuldu | Sonuç |
|---|---|
| `pytest tests/ -q` | **754 passed, 0 failed** (192.7 sn) |
| `ruff check src/` | **All checks passed** |
| CLI `translate` fake provider: EPUB→EPUB, EPUB→PDF, PDF→PDF (fit dahil), DOCX→DOCX, DOCX→HTML, W-4 formu `--limit 10` (protect=3, fitting 10 blok: as_is=2, shrunk=7, overflow=1) | hepsi çıktı üretti; taşan segment bayraklandı |
| Canlı EPUB→PDF: pg23319 (339 ImageRef) → 212 sayfa, **337 resim çıktıda** | görsel taşınması eski-üslup kitapta çalışıyor |
| Uç-durum EPUB fixture (SVG-sarmalı resim + OPF kapak + `<th>` + `<figcaption>`) | **0 ImageRef, th/figcaption metni DocIR'da yok** — sessiz kayıp (B1/B2/B5/B6) |
| Resim konumu fixture'ı (p1 → resim → p2) | `content_in_reading_order` = [p1, p2, alt-metni, resim] — DUMMY_BBOX yüzünden resimler akışın sonuna yığılıyor (B7) |
| Sadece-görüntü PDF sayfası (text layer yok) | 0 blok — taranmış PDF OCR'a hiç düşmüyor (B4) |
| CLI, kapalı porta (`127.0.0.1:9`) karşı | **tam Python traceback sızıyor** (B8) |
| GUI offscreen smoke testi | MainWindow 900x660 açıldı, üç ekran da mevcut |
| pg11 segment analizi | 873 segment; source 165.251 kr, **context 326.994 kr → prompt'un %66,4'ü bağlam** (B13) |

Denetim betikleri: `tools/audit/` altında, commit'li (`edge_epub_test.py`, `imgpos_test.py`,
`check_ocr_gap2.py`, `cli_error_test.py`, `check_perf2.py`, …) — her bulgunun kanıtı yeniden
koşulabilir. Betik → bulgu eşlemesi `tools/audit/README.md`'de; koşum: `python tools/audit/<betik>.py`.

## 7. Genel değerlendirme

Proje iddiasını dürüst koyuyor ("tam otomatik, mükemmel tek-tık çeviri yok; iyi bir ilk geçiş + dürüst
inceleme sinyali + açılır çıktı") ve mimarisi bu iddiayı taşıyacak olgunlukta: DocIR ayrıştırması,
sağlayıcı soyutlaması, sığdırma motoru ve cerrahi yazıcılar gerçek belgelerle çalışıyor. En büyük
risk yazılımda değil **kapsamada**: her yeni girdi tipinin kenarında (SVG-sarmalı resim, kapak,
taralı sayfa, th hücresi) sessiz veri kaybı sınıfından hatalar oturuyor — ve bu sınıf, test paketinin
"bilinenden öğrenen" doğası gereği testlerde yakalanmıyor, sadece gerçek belgeyle koşunca ortaya
çıkıyor. İkincil risk: GUI-CLI parite eksikleri ve ölü ayarların kullanıcıyı yanıltması.
Üçüncül: maliyet görünürlüğü (bağlam %66'sı, parti keşif maliyeti, retranslate turları) hiçbir yerde
ölçülüp raporlanmıyor.

Önerilen öncelik sırası — eksiksiz liste ve ajan atamaları için **[AUDIT-BULGULAR.md](AUDIT-BULGULAR.md)**.
