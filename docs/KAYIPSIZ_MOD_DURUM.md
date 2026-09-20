# Kayıpsız çeviri modu: durum, doğrulama ve bu turda yapılanlar

Bu belge iki soruyu yanıtlar: **(1)** Gemini'nin `v2-vision-layout` dalında yaptığı iş gerçek mi,
neye yarar; **(2)** uygulamanın "kayıpsız ve tam" çeviri moduna ulaşması için ne yapıldı, ne
ölçüldü, ne kaldı.

Ölçümler iki ayrı çalışma ağacı üzerinde yapıldı:

| Ağaç | Dal | Ne var |
|---|---|---|
| `LayoutKeep/` | `feature/lossless-campaign-continuation` | Asıl hat: L1-L9 kayıpsız denetimi, doğrula-onar döngüsü, kampanya + held-out ölçüm altyapısı. **Bundan sonra yalnızca bu ağaçta çalışılıyor.** |
| `LayoutKeep_V2/` | `v2-vision-layout` | Gemini'nin 16 Eyl tarihli tek commit'i (`b89396b`) |

---

## 1. Gemini'nin V2 dalı: iddia ve doğrulanan durum

### 1.1. Gerçekten var olan iş (doğrulandı)

Tek commit `b89396b` (16 Eyl 2026 21:19), 18 dosya, +1596 satır. Dosyalar diskte var ve
`pytest` ile o dalın iddia ettiği dört test dosyası **geçiyor: 12 passed**:

- `src/layoutkeep/readers/vision_layout.py` — VLM'e sayfa mizanpajı soran istemci + JSON ayrıştırıcı
- `src/layoutkeep/readers/glyph_fusion.py` — vektör metni modelin kutularına projekte eden motor
- `src/layoutkeep/fitting/elastic_flow.py` — blok genişlemesini alta öteleyen mikro-akış
- `src/layoutkeep/readers/_segment.py` — özyinelemeli XY-cut bölütleyici (taranmış yoluna bağlı)
- `tests/test_vision_glyph_fusion.py`, `test_pdf_reader_vision_hybrid.py`, `test_elastic_flow.py`,
  `test_benchmark_matrix.py`

`_segment.py` ve onun `image_reader`a bağlanması ciddi iş: iki sütunlu taranmış sayfada satırların
yarıdan bölünmesini, per-line eşik yazmadan, sayfanın kendi boşluğunu keserek çözüyor.

### 1.2. Güven vermeyen kısımlar (doğrulandı)

1. **"Kıyaslama matrisi" ölçüm değil.** `docs/BENCHMARK_VE_GECIS_RAPORU.md` içindeki yüzdeler
   ("%100 sütun izolasyonu", "%0 karakter kaybı") `test_benchmark_matrix.py`'den geliyor; o test
   elle yazılmış dört koordinat ve iki dikdörtgenle kurulmuş bir birim testi. Gerçek bir belge
   üzerinde koşulmuş tek bir ölçüm yok.
2. **"922 passed, 2 xfailed" doğrulanamadı.** `LayoutKeep_V2/` dizininde sanal ortam, `uv.lock` ve
   `pytest` yapılandırması yok; iddia edilen tam paket orada koşulamıyor. Asıl hatta
   (`LayoutKeep/`) 1062 test toplanıyor.
3. **VLM dedektörü hiçbir modele bağlı değil.** `VlmLayoutDetector.__init__` zorunlu bir `chat_fn`
   istiyor; uygulamada (CLI, worker, reader) bunu geçen tek bir çağrı yok. Yani `vision_layout.py`
   şu an ölü kod. Ayrıca kullanıcının sert kısıtı gereği yerel tek model `google/gemma-4-e4b` ve
   görsel model çağrısı yapılmıyor - bu tasarım bugünkü kurulumda çalıştırılamaz.
4. **Dal, asıl hattın gerisinde.** V2'nin tabanı `scanned-pdf-ocr` (16 Eyl); asıl hat o tarihten
   sonra 77 commit ilerledi. V2'de **olmayan** modüller: `verify.py` (L1-L9 denetimi + onarım
   döngüsü), `core/reference.py` (kaynakça koruması), `core/copies.py` (kopya/yanlış dil/sayı
   denetimleri), `fitting/room.py`, `ocr/layout_detector.py`. Yani V2'de kayıpsız denetim yok,
   dolayısıyla V2'nin çıktısının kayıpsız olup olmadığı da ölçülemez.

### 1.3. Sonuç: V2'den ne alınır

| Parça | Karar | Gerekçe |
|---|---|---|
| `_segment.py` (XY-cut) | Zaten asıl hatta var (`readers/_segment.py`) | Yeniden taşımaya gerek yok |
| `elastic_flow.py` | **Fikir değerli, kod taşınmadı** | D1 (okunabilirlik tabanı) asıl en büyük kalite kaybı; ama asıl hattın `fitting/room.py` + `pdf_writer._layout_rect` ölçümleriyle yeniden yazılmalı, ham `bbox.height` oynatmak yazıcının temizleme dikdörtgenleriyle çelişir (L7/L8 üretir) |
| `glyph_fusion.py` | **Şimdilik alınmadı** | Vektör metni kutulara projekte etmek doğru fikir, ama asıl hattın dijital okuyucusu zaten PyMuPDF bloklarını kullanıyor ve sütun sorununu `_segment.py` çözüyor; kazanç ölçülmeden 1337 satırlık okuyucu değiştirilmez |
| `vision_layout.py` (VLM) | **Alınmadı** | Tek yerel model kısıtı; dedektör bağlı değil |

---

## 2. Gerçek durum: held-out ölçümleri ne diyor

Uygulamanın kullanıcının koştuğu hâli (layout modeli kapalı, doğrulama 2 tur, onarım yok),
10 held-out kaynağı, `docs/campaign/HELDOUT.md` ve `_artifacts/heldout/runs/*/audit.json`:

| Kaynak | L1 | L2 | L3 | L6 | L7 | L8 | D1 |
|---|---|---|---|---|---|---|---|
| arxiv_19145_v2 | 0 | **7** | 0 | 3 | 6 | 6 | 299 |
| gutenberg_sherlock | 0 | **1** | 0 | 1 | 0 | 0 | 0 |
| irs_p505 | 0 | **2** | 0 | 8 | 0 | 2 | 509 |
| irs_i1040gi | 0 | **1** | 0 | 6 | 0 | 3 | 209 |
| cookbook_1907 | 0 | **1** | 0 | 1 | 0 | 0 | 129 |
| mushrooms_1895_sample | 0 | **1** | 0 | 0 | 0 | 0 | 34 |
| wikipedia_printing_press | 0 | 4 | 0 | 0 | 0 | 0 | 8 |
| plos_animal_movement | 0 | 3 | 8 | 0 | 0 | 0 | 102 |
| wikipedia_photosynthesis | 0 | 5 | 0 | 1 | 0 | 0 | 24 |
| nasa_ntrs_scan | 0 | 1 | 0 | 0 | 0 | 0 | 6 |
| L1-L9 = 0 olan (kampanya, onarımlı) | NIST, Think Python, The Time Machine | | | | | | |

Okunan tablo şu: **L1/L3/L4/L5/L9 pratikte kapandı.** Kayıpsızlığı engelleyen tek kalem **L2
(çevrilmeden kalan blok) ve o her kaynakta var.** Arkasından L6 (sayı), L7 (üst üste yazım), L8
(çevrilmeyen metnin yerinden oynaması) ve kalite tarafında D1 (okunabilirlik tabanının altına
inmiş yazı, blokların %17-24'ü) geliyor.

---

## 3. Bu turda uygulananlar (asıl hat üzerinde)

### 3.1. L2 için son çare: parçalı çeviri

`src/layoutkeep/providers/split.py` + `providers/retry.py`

Retry merdiveni bugüne kadar isteğin **eşini ve bağlamını** değiştiriyordu: önce küçük parti,
sonra üç kez tek başına. **Boyutunu** değiştirmiyordu; modelin aynen geri verdiği şey ise bir
paragraf. Kampanyanın kendi ölçümü bunu söylüyor: The Time Machine'de bir diyalog paragrafı ana
geçişte ve parti retry'ında Yankılandı, tek başına gönderildiğinde 24/24 çevrildi.

Yeni son basamak: hâlâ çevrilmemiş blok, kendi cümle ve liste sınırlarından kesilir, her parça tek
tek sorulur, cevaplar **kaynağın kendi ayırıcılarıyla** (boşluklar, satır sonları) birleştirilir.
Parçalardan biri kullanılamaz gelirse bütün deneme iptal edilir - yarım çevrilmiş paragraf,
çevrilmemiş paragraftan daha kötüdür, çünkü artık kayıp gibi okunmaz. Kapatılabilir:
`translation.piecewise_max_pieces` (varsayılan 12, 0 = kapalı).

Testler: `tests/test_provider_pieces.py` (8 test) - ayırıcıların birebir korunması, tek cümlelik
metnin kesilmemesi, çok parçalı metnin reddi, parça başarısızlığında bütünün korunması, kapatma.

### 3.2. Sayı denetimi: yanlış alarmı kes, gerçek kaybı kesme

`src/layoutkeep/core/copies.py`

`drops_numbers` yalnızca rakam gruplarını sayıyordu ve 0-10 arası sayı sözcüklerini tanıyordu.
Artık: dile göre sayı sözcükleri **değere katlanıyor** ("on iki" → 12, "iki bin beş yüz" → 2500),
sıra sayıları tanınıyor ("üçüncü" → 3, "3rd"), vulgar kesirler genişletiliyor ("½" → 1 ve 2).

**Ölçüm (11 held-out koşusunun kayıtlı `.lkproj` projeleri üzerinde, model gerekmez):** 29 kayıtlı
L6 bulgusundan **1'i** bu türdendi ve temizlendi
(`irs_p505`: "tier 1 railroad benefits" → "birinci kademe demiryolu yardımı"). Kalan 28'i gerçek:
kaynak PDF'in dipnot rakamını sayıya yapıştırması ("20261"), tekrar sayılan değerlerin çeviride
bir kez geçmesi ("1099" üç kez → iki kez) ve gerçekten düşen değerler. Yani bu değişiklik doğru
ama küçük bir kazanç; L6'nın çoğu **kaynak artefaktı ya da gerçek kayıp**, denetim hatası değil.

### 3.3. Kod ve formül: çeviriye gönderilmemesi gereken metin

`src/layoutkeep/readers/_nonprose.py` + `readers/pdf_reader.py`

Okuyucu kodu yalnızca **eşaralıklı yazı tipinden** tanıyordu. LaTeX'in verbatim satırları normal
yazı tipinde çıkıyor, dolayısıyla arXiv 2609.19145'in `trim_offsets=True, use_regex=True)` satırı
"çevrilmemiş metin" olarak sayıldı ve retry merdiveni ona üç tek istek + parça başına istek harcadı.
Aynı şey normal yazı tipinde dizilmiş denklemler için de geçerliydi (`f(a) ≈f(x) + (a −x)f′(x)`).

Artık metnin *şekli* de soruluyor: `like_this` tanımlayıcı, yapışık parantezli çağrı veya anahtar
argüman + sembol yoğunluğu → `BlockRole.CODE`; kısa, operatör taşıyan, cümle gibi bitmeyen parça →
`BlockRole.FORMULA`. İkisi de çevrilmeden taşınan roller.

**Ölçüm 1 (kayıtlı bulgular):** 34 kayıtlı L2 bulgusundan 2'si tam olarak bu kod satırlarıydı.
**Ölçüm 2 (gerçek korpus taraması):** arxiv_19145 (115 blok), Think Python (49), NIST (51),
Popular Science (147), Time Machine (16), Electricity (16) sayfalarında yeni kuralın işaretlediği
bloklar elle okundu: Think Python'da 5/5 gerçek kod, arXiv'da formül parçaları ve arXiv damgası,
diğer dört dokümanda **0 işaretleme** - prose kaybı yok.

Yol boyunca bir hata yakalandı ve düzeltildi: ilk sürüm tek harfli `f(a)` çağrısını kod sayıp
arXiv'ın kendi prose paragrafını (`"Now, define f(a) = a log a, which implies ..."`) çeviri dışı
bırakıyordu. Kural artık ≥3 harfli çağrı adı + "10'dan fazla gerçek sözcük taşıyan metin prose
sayılır" koruması taşıyor. Bu, ölçümün değil, taramanın yakaladığı bir hata.

### 3.4. Pürüzsüzlük: aynı metin bir kez çevrilir, belge kendisiyle aynı dili konuşur

`src/layoutkeep/providers/dedupe.py` + `src/layoutkeep/core/repeats.py`

Ölçütler (L1-L9) "bir şey kayboldu mu" diye sorar; "bu belge tek bir belge gibi mi okunuyor" diye
sormaz. Kayıtlı koşular ise okunmadığını söylüyor: `irs_p505` çevrilebilir segmentlerinin
**537'sini (25%) tekrar ediyor** (`irs_i1040gi` %34, arXiv 2609.19145 %31, plos %30) - form
etiketleri, her sayfada aynı talimat, tekrar eden tablo başlıkları - ve **bu tekrarların 80'i
birden fazla farklı çeviriyle** geri gelmiş (272 segment). IRS 1040 talimatları "Married filing
separately" terimini tek belgede üç ayrı şekilde ("ayrı ayrı beyan eden", "evli ayrı ayrı beyan
eden", "ayrı ayrı evli"), "Head of household" terimini iki ayrı şekilde ("hane başkanı", "hanevi")
yazıyor; her satır tek başına doğru, belge bütün olarak tutarsız.

1. **Aynı metin bir kez sorulur** (`providers/dedupe.py`): koruma sarmalayıcısının içinde, yani
   paylaşılan metin token'lanmış metin - "Tighten the bolts to 63 Nm" ile "...150 Nm" tek istek
   olur, her biri kendi değerini geri alır. Anahtar boşluk ve büyük/küçük harfi yok sayar; üç
   kelimeden kısa metin asla paylaşılmaz ("where" → "nerede"/"ner", "ours" → "biz"/"bizim").
   **Ölçüm (kayıtlı kaynaklar):** plos 468 isteğin 86'sı (%18), irs_i1040gi 737'nin 115'i (%16),
   irs_p505 2144'ün 224'ü (%10), arXiv v2 489'un 36'sı (%7); düzyazı ağırlıklı kaynaklarda 0.
   Kapatma: `--no-repeats` veya `translation.reuse_repeats` ayarı.
2. **Yazılmış olan kendisiyle aynı hâle getirilir** (`core/repeats.py`): retry merdiveninden sonra,
   sığdırma geçişinden önce. Aynı kaynak metnin birden çok çevirisi varsa çoğunluk kazanır,
   azınlık ona çevrilir. Hiçbir şey yeniden sorulmaz, hiçbir şey uydurulmaz - her düzeltme bu
   belgenin o kaynak için zaten ürettiği bir çeviridir. **Sayısını kaybetmiş bir varyant, sayıları
   koruyan bir varyasyon varken asla seçilmez** (tutarlılık kayıp pahasına satın alınmaz).
   **Ölçüm (kayıtlar olduğu gibi, yani paylaşma hiç yokken üretilmiş hâlleri - üst sınır):**
   irs_p505 66 metin / 87 segment, irs_i1040gi 16/42, arXiv v2 8/22, cookbook 4/4.

Testler: `tests/test_provider_dedupe.py` (14 test) - CLI zincirinin varsayılanı ve `--no-repeats`
dâhil.

### 3.5. Boru hattının tam sırası (bundan sonra)

```
oku → bölütle → [tekrarları paylaş] → çevir → onar (retry, parçalı son çare)
   → [tekrar tutarlılığını birleştir] → doğrula/onar (L1-L9) → sığdır → yaz → doğrula
```

Köşeli parantezdekiler bu turda eklendi; ikisi de varsayılan açık, ikisi de kapatılabilir.

---

### 3.6. Sığdırma: blok, altındaki boş alanı kullanabilir (gerçek modelle ölçüldü)

`src/layoutkeep/fitting/growth.py` + `pdf_pass.py` + `writers/pdf_writer.py`,
ayar: `write.grant_room_pt` (varsayılan 24 punto)

Gerçek modelle koşan ilk ölçüm kriterlerin hiç sormadığı bir şeyi gösterdi: **hiçbir kayıp yok ama
sayfa iyi görünmüyor.** arXiv 2507.03009'un tablo sayfası `fitting 70 blocks: shrunk=42 overflow=28`
ile döndü - 70 bloğun **hiçbiri olduğu gibi sığmadı** - ve aynı çıktının denetimi "no losses found"
diyordu. `room_below` bunu çözemez: "yazıcının 3 puntoluk payının ne kadarı boş" sorusunu yanıtlar
ve asla o paydan fazlasını döndürmez, yani "sayfanın altında yer var" diyemez.

Artık çevrilmiş bir blok, altındaki gerçek boşluğa büyüyebilir: aynı sütundaki bir sonraki blokla,
sayfadaki bir resimle sınırlı; ayarla kapaklanmış; boşluğun 2 puntosu olduğu gibi bırakılır. Sığdırma
geçişi ve yazıcı **aynı fonksiyonu** çağırır (biri ölçüp diğeri başka kutuda çizerse metin iki kez
küçültülür). Olduğu gibi bırakılan blok kendi kutusunda çizilir (metni oynamasın: L8), döndürülmüş
blok eskisi gibi ölçülür.

**Ölçüm (gerçek model, gemma-4-e4b):**

| kaynak | önce | sonra |
|---|---|---|
| 2 sayfalık tekrar fixture'ı | `shrunk=2 overflow=4`, 4 inceleme bayrağı | `as_is=6`, bayrak yok, "no losses found" |
| arXiv 2507.03009 s.5 (yeni, tablo sayfası) | `shrunk=42 overflow=28` (as_is=0) | `as_is=32 shrunk=12 overflow=24`, **LOSSLESS**, L7 0, L8 0 |
| arXiv 2507.03009 s.7 (yazar listesi) | `overflow=3` | `as_is=1 overflow=2` |
| arXiv 2507.03009 (10 sayfa, son hâl: `fresh_pdfmt_r5`) | L2 2, L7 1, L8 1, L9 1, D1 63, D3 1 | **L7 0, L8 0, D3 0**, L2 2 (kaynakça), L9 1, D1 66 |
| NASA tarama s.1 (held-out) | L2 1, D1 6 | L2 1, D1 5 - değişmedi (tarama: engel sayfanın kendi resmi) |

**Hâlâ pürüzlü olan:** tablo sayfasının 70 bloğundan 24'ü hâlâ taşıyor ve 33 kontrol edilen bloğun
22'si okunabilirlik tabanının altında - tablo hücresinin altında tanım gereği yer yok, merdiven
ancak taban kadar küçültüp kısa çeviri isteyip bayrak koyabiliyor.

### 3.7. Kısa cümle merdiveni ve L7: ölçümün gösterdiği üç ayrı kusur

`src/layoutkeep/fitting/fit.py`, `readers/_layout.py`, `writers/pdf_writer.py`

Kısa cümle merdiveni iki yerden düzeltildi: (1) kutuya sığan ama **yalnız küçültmeyle** sığan bir
çeviri artık orada durmuyor, kısa cümle isteniyor (`fit.shorten_below_scale`, varsayılan 0.95);
(2) imkânsız istekler kesiliyor - 24 karakterden kısa metne "daha kısa yaz" denmiyor ve bütçe
metnin kendisinden büyükse istek yapılmıyor. Ölçüm (arXiv tablo sayfası, kuru prova): istek sayısı
70 bloğun tamamına karşı **14 -> 7**.

Ama gerçek koşuda (`fresh_pdfmt_r3`, 758 s) yeni bir **L7** çıktı: chunk_0001'de bir kelime çifti
üst üste. Kökeni kaynak sayfada ölçüldü - PyMuPDF footer'ı **üç satır** veriyor:

    (319,755,338,765)   '1See:'                                <- dipnot, ayrı blok olur
    (388,756,526,765)   'https://platform.openai.com/docs/api-'
    (306,766,381,775)   'reference/chat/create'

Üç ayrı kusur vardı, üçü de ölçümle bulundu:

1. **Tire birleştirme linkin tiresini yedi.** Satır `api-` ile bitiyor, sonraki `reference` ile
   başlıyor: kuralın istediği tek şey "harften sonra tire" ve "sonraki küçük harf" idi. Birleşince
   URL `.../docs/apireference/chat/create` oldu (tire gitti) ve blok tek satıra indi - kaynak
   satırların **2.4 katı** genişlikte. İki koruma eklendi: tireyi taşıyan token **kelime** olmalı
   (sadece harf; `/`, `:`, `.`, rakam varsa URL/yol/kimlik ve tire metnin parçası) ve sonraki satır
   **aynı sütunu sürdürmeli** (üsttekiyle kesişmeli, onun sol kenarından başlamalı). Dipnotun iki
   satırı zaten hiç kesişmiyordu.

2. **`_unchanged`, `source_text`'i boş olan bloğu "değişmiş" sayıyordu.** Boru hattı `source_text`'i
   yalnızca segment çevrilmiş olarak döndüğünde yazar (`apply_segments`); yani boşsa bloğun metni
   **hâlâ kaynak** - toplu istek düşmüş ya da blok hiç gönderilmemiş. Böyle bloklar boşuna yedek
   yazı tipiyle yeniden çiziliyordu ve yeniden çizilen blok **kendi kutusunun sol kenarından**
   diziliyor: URL'in ilk satırı kaynakta durduğu yerden **82 punto sola** kayıp dipnotun üstüne
   bindi. Artık olduğu gibi bırakılıyorlar.

3. **"Temizleme bu bloğa ulaşır mı" testi birleşim kutusunu soruyordu.** URL bloğunun kutusu iki
   satırının birleşimi ve dipnotun kutusunu kapsıyor; bu yüzden blok çizim listesine giriyordu -
   oysa dipnotun temizlemesi iki satırın **hiçbirine** değmiyor. Test artık bloğun kendi satırlarını
   soruyor (1 punto payla: temizleme glifleri bütün alır ve glif kutusu satır kutusundan taşabilir)
   ve **değen kenar ulaşmak değildir**.

3. **Reddedilen tire birleşmesi, satırı yanlış komşuya bırakıyordu.** URL'in ikinci satırı
   (`reference/chat/create`) dipnotun sütunuyla çakıştığı için `_split_side_by_side_lines` onu
   dipnotla aynı bloğa koydu ve ikisi `1See: reference/chat/create` olarak çevrildi (sonra taşıp
   D1 oldu). Artık `_hyphen_parents` var: tireyle biten bir satırın altında küçük harfle başlayan
   satır **o satıra** aittir; satırlar sütuna göre değil **metin sırasına** göre okunuyor, böylece
   ebeveyn her zaman önce görülüyor.

4. **Sütun koruması fazla katıydı ve bir adı ikiye böldü.** `_continues_the_column` iki kutunun
   kesişmesini şart koşuyordu; paragrafın son satırı kısadır - sütunun sağında biten `(Von Gizy-`
   satırını kenardan başlayan `cki; Montgomery).` sürdürür ve iki kutunun ortak genişliği yoktur.
   Şart kaldırıldı: süren satır üsttekinin sol kenarından veya daha soldan başlar, **sağından
   başlamaz**.

Bu dördü `tools/audit/reader_ab.py` ile ölçüldü: 43 held-out chunk iki farklı kaynak ağacıyla
(HEAD worktree'si vs çalışma ağacı) baştan okunur ve yalnız **gerçek** farklar yazılır (id'ler
sayılmaz). Sonuç: 21 chunk yalnızca blok kimliğinde farklı (iç yapı), **içerik olarak 2 sayfa
farklı ve ikisi de doğru yönde**:

| sayfa | önce | sonra |
|---|---|---|
| chunk_0001 (arXiv footer) | `https://platform.openai.com/docs/apireference/chat/create` - tek satır, tire yenmiş, olması gerekenden 2.4 kat geniş | `https://platform.openai.com/docs/api-` + `reference/chat/create` - kaynağın kendi iki satırı, tire yerinde |
| chunk_0005 (arXiv s.1) | `Exclusion of the non-Englishspeaking` - tire yenmiş | `Exclusion of the non-English-` + `speaking world from ...` - kaynağın kendi satırları |

Denenip **geri alınan**: kelimesiz bloklar için `white-space: nowrap`. Gerekçe, `insert_htmlbox`'ın
URL'in puntosunu kutuya sığdırmak için büyüttüğü varsayımıydı; `tools/audit/url_size_probe.py`
ölçtü - 11.9 puntoluk yükseklik yedek yazı tipinin kendi ascent+descent'i (9.06 puntoda 1.31em) ve
nowrap hiçbir şeyi değiştirmiyor (kutudan geniş token iki durumda da hiç çizilmiyor). Ölçülmemiş
düzeltme kodda kalmaz.

**Doğrulama aracı:** `tools/audit/rewrite_run.py` - kayıtlı bir koşunun sayfalarını projelerinden
güncel yazıcıyla yeniden çizer ve denetler; model gerekmez, yazıcı değişikliği dakikalar içinde
ölçülür. Kayıtlı `fresh_pdfmt_shorten` koşusunda: **L7 1 -> 0**.

### 3.8. Gerçek modelle doğrulama (LM Studio)

LM Studio'nun model klasörü `T:\AiModels` ve sürücü takılı değildi; takıldıktan sonra indeks yine
eskisi gibiydi (uygulama model klasörünü açılışta tarar), `lms import -L --user-repo local/gemma-4-e4b`
dosyayı indeksin gördüğü yere sabit bağladı ve model `gemma-4-e4b` olarak geri geldi.
`--identifier google/gemma-4-e4b --gpu max -c 8192 --parallel 7` ile yüklendi, böylece uygulamanın
varsayılan model kimliği ve kampanyanın 7 işçisi birebir çalışıyor.

Bu tur için `tools/audit/live_check.py` eklendi: bir kaynağı gerçek sağlayıcıyla baştan çevirir,
denetler ve kayıtlı koşuyla karşılaştırır (`_artifacts/heldout/live/<ad>`, kayıtlı ölçümlerin üstüne
asla yazmaz).

---

## 4. Kalan işler ve neden acele edilmemeli

| Kalem | Ne gerekiyor | Risk |
|---|---|---|
| **L7** (bu turda kökünden kapatıldı - bkz. 3.7) | Üç ayrı kusur: linkin tiresini yiyen tire birleştirme, hiç çevrilmemiş bloğu "değişmiş" sayan `_unchanged`, temizleme testinin birleşim kutusunu sorması. Kalan: taranmış yol (`_cover_scanned_blocks`) aynı gözle ölçülmedi | Taranmış yol ayrı ölçülmeli: orada kaynak metin sayfanın kendi resmi |
| **L8** (bu turda kökü kurutuldu - bkz. 3.7) | Çevrilmeyen blok artık yalnızca temizleme gliflerine gerçekten ulaştığında yeniden çiziliyor; kalan tek kayıt (`fresh_pdfmt_shorten` sonrası yeniden çizim, chunk_0004) eski okuyucuyla yazılmış projeden geliyordu | Yeni uçtan uca koşu bunu kesinleştirir |
| **L10** (bu turda eklendi ve düzeltildi) | Metnin **görselin üstüne** binmesi hiçbir kriterde yoktu (L7 yalnız metin-metin örtüşmesini görüyordu). Kök neden: kaynakta satırlar fotoğrafın çevresinden akıyor, bloğun kutusu görseli **kapsıyor**; çeviri aynı kutuya akıtılınca satırlar fotoğrafın üstüne çıkıyordu. Çözüm: blok kutusu ölçümden önce görselin kapsamadığı en geniş şeride daraltılıyor (`fitting/figures.py`), ölçüm ve çizim aynı kutuyu görsün diye fit geçişinde. Ölçüm: `wikipedia_printing_press` yeniden çevrildi, **L10 13 → 0** | Tarayıcıda kapsam eşiği (COVERED=0.55, sayfanın %85'inden büyük görseller hariç) taranmış belgelerde yanlış pozitif veriyordu, ölçümle düzeltildi |
| **D1** (296-509 blok) | Gemini'nin elastic flow fikrinin doğrusu: `fitting/room.py`'nin boş alan ölçümüyle bloğu aşağı doğru büyütmek, fontu okunabilirlik tabanının altına indirmek yerine. **2026-09-20: bir parçası yapıldı** - blok kutuları birkaç punto üst üste bindiğinde `room_below` negatif çıkıyor ve yazar kutuyu kısaltıp 6.7pt'lik satırı 4.5pt'ye eziyordu; yazar artık taban ölçek tutmazsa bloğun **kendi kutusunu** da deniyor. Ölçüm (`rewrite_run` + `type_drift`): okunamaz 12 → 2, küçültülmüş 84 → 6, hizası değişmiş 4 → 0; bedeli bir sayfada sıkışan satır (D3 1 → 2). Kalan: dikey sayı şeritleri (8pt genişliğinde, 56 satırlık form sütunları) ve `reflow` modunun varsayılan kaliteye çıkarılması | Yazıcının temizleme ve komşu kurallarıyla birlikte değişmeli; tek başına `bbox.height` oynatmak L7/L8 üretir. Kutuyu sağa genişletme denendi ve **ölçümle çürütüldü** (12 → 12 okunamaz; kısıt genişlik değil yükseklik), geri alındı |
| **Kaynakça** | `--preserve-references` var ama **varsayılan kapalı**; held-out koşuları onu geçmiyor, bu yüzden arXiv'ın kaynakça satırları çeviriye gidip Yankılanıyor | Açmak, çevrilmeyen metni artırır; denetim onları L2 saymaz - metrik yanıltıcı olur. Bilinçli tercih olmalı |
| **L9** (1 blok, arXiv s.7) | `Urdu, Ukraynaca, Việt語, Galce` - modelin dil adları listesinde karışık yazım; çeviri kalitesi, kayıp denetimi değil. Sözlük (`glossary`) ile düzeltilir | Yanlış düzeltme metni bozar; terim listesi kullanıcı onayıyla |
| **L1** (Elektrik 1922'de 1) | 148 sayfalık taramada bir sayfa | Ayrı ölçüm gerekir |

---

## 5. Kayıpsız ve pürüzsüz mod için önerilen ayarlar

- `translation.reuse_repeats` = açık (varsayılan) - aynı metin bir kez çevrilir; kapatmak için
  `--no-repeats`
- `translation.piecewise_max_pieces` = 12 (varsayılan; kapatmak için 0)
- `write.grant_room_pt` = 24 (varsayılan) - çevrilen blok alttaki boşluğa bu kadar büyüyebilir;
  0 kapatır ve eski "yalnız kendi kutusu" davranışına döner
- `--verify-rounds 2` (varsayılan) - onarım turlarını artırmak L2'yi daha da düşürür
- Akademik PDF'lerde `--preserve-references`: kaynakçayı kaynak dilde bırakır (kayıpsız mod için
  doğru davranış, ama "çevrilmemiş blok" sayısı ile denetim metriği farklı şeyler söyler)
- Kod/formül sınıflandırması, tekrar birleştirme ve boşluk kullanımı artık varsayılan; ayrı bayrak yok

---

## 6. Doğrulama

- Yeni testler: `tests/test_provider_pieces.py` (8), `tests/test_provider_dedupe.py` (14),
  `tests/test_fitting_growth.py` (7), `tests/test_fitting_fit.py` (kısalma merdiveni: ağır
  küçültmede kısa çeviri istenir, iyileştirmeyen aday reddedilir, kısa metne kısalma sorulmaz),
  `tests/test_image_reader_hyphenation.py` (URL/yol tiresi ve başka sütunda süren satır
  birleştirilmez), `tests/test_pdf_writer_unchanged_blocks.py` (temizleme bloğun kendi
  satırlarına sorulur, ölçüsüz blok kutusuyla korunur), `tests/test_core_copies.py` ve
  `tests/test_pdf_reader_code_blocks.py` içine eklenenler — geçiyor
- Tam paket: `pytest -q` — **1108 passed / 0 failed** (bu turun son hâli; sığdırma sırasında
  1097, kısalma merdiveninden sonra 1104, L7 düzeltmelerinden sonra 1108)
- **Gerçek modelle uçtan uca (gemma-4-e4b, 7 yuva):** fixture, NASA taraması (held-out) ve
  arXiv 2507.03009 (yeni kaynak) çevrildi, denetlendi, kayıtlı koşularla karşılaştırıldı — ayrıntı
  3.6 ve 3.7'de. En önemlisi: tablo sayfası `LOSSLESS True` (L1-L9 = 0) ve sığdırma `as_is` 0 → 32
- Araçlar: `tools/audit/live_check.py` (kayıtlı ölçümlerin üstüne yazmaz),
  `tools/audit/rewrite_run.py` (kayıtlı koşuyu güncel yazıcıyla yeniden çizer + denetler,
  model gerekmez), `tools/audit/url_size_probe.py` (renderer puntoyu büyütüyor mu sorusunu
  ölçer - cevap: hayır, o yedek yazı tipinin metriği)

