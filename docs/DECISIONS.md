# Karar ve Deney Tarihçesi

Bu dosya projenin hafızasıdır: ne denendi, ne ölçüldü, ne kabul edildi, ne reddedildi.

Jurnal günlük işi tutar. Burası kararların **gerekçesini** tutar.

**Kural:** Her deneme buraya yazılır. Özellikle işe yaramayanlar. Özellikle kendi iddiasını çürütenler.

**İki yere yazılır.** Proje tarafı burasıdır: gerekçe, ölçüm, kanıt. BrainOS tarafı `learn.py add` ile
tutulur: kalıcı ders, hata, düzeltme, tercih. İkisi birlikte yürür; biri eksik kalırsa kayıt eksiktir.

**Yazım kuralı:** Kısa, net cümleler. Kalabalık ve çok yan cümleli anlatım yok.

**Biçim:** Soru · Yöntem · Ölçüm · Karar · Gerekçe · Yanlış giden · Kanıt.

---

## D-001 · Satır-içi boyut ayarı varsayılan olsun mu? · **KABUL**

**Soru:** `writer.inline_span_sizes` varsayılan açık olmalı mı? Uyarısı "ölçülmeden açılmaz" diyordu.

**Yöntem:** Beş kayıtlı koşu. İki kol da aynı motorla yeniden yazıldı. Biri ayarlı, biri ayarsız.

**Ölçüm:** Düzleşmiş kutu 104 → 75 (−%28). Ezilmiş kutu 1727 → 1658 (69 kutu az). Sadık kutu +53.
L3/L7/D1/D3 beş koşuda da aynı. L7 ayarın riski diye yazılmıştı, o da oynamadı.

**Karar:** Varsayılan açık. Kullanıcı onayı: "sen test ettiysen açabilirsin".

**Gerekçe:** Ayar kendi şartını karşıladı. Hiçbir ölçüt kötüleşmedi. Ezilme azaldı.

**Yanlış giden:** İlk tabloda saklı koşu taban alındı. O çıktı eski motordan geliyordu.
Ayardan sanılan "+4 ezilme" aslında motor değişimiydi. Beş belgeye yayılan ikinci tabloda da
"iyileşen ölçütler" göründü. İki kol da yeniden yazılınca kayboldular.

**Kural:** Saklı çıktı taban alınamaz. İki kol da aynı kodla yazılır.

**Kanıt:** `5d5a32f` · `8e177d5` · `b1fa874` · `4385d10` · `996c8bb`.

---

## D-002 · EPUB düzenleme ekleyicisi metni bozuyor mu? · **KABUL (düzeltildi)**

**Soru:** `epub_writer._apply_edits` üst üste binen düzenlemelerde metni bozuyor mu?

**Yöntem:** İç içe iki düzenlemeyle birim test.

**Ölçüm:** Önce `aaa LONGERXB ccc`. Sonra `aaa LONGER ccc`. Yanlış yere ekleme ve artık karakter vardı.

**Karar:** Düzeltildi. İmleç artık geri gitmiyor. Tamamen içeride kalan düzenleme atlanıyor.

**Gerekçe:** Üst üste binme gerçek bir yol. Blok aralıkları ayrık ama `<img>` alt/title aralığı bloğun
içinde kalabiliyor.

**Yanlış giden:** Düzeltmeyi "11 testi kırdı" sanıp geri aldım. Yanlıştı. Kıran şey aynı dosyada
değiştirdiğim **import satırıydı**. Fix doğru sınandı, 21/21 geçti.

**Kural:** Şüpheli kırılmada önce kendi değişikliğini `git stash` ile ayır.

**Kanıt:** `996c8bb` · `tests/test_epub_writer.py`.

---

## D-003 · Kapak sayfaları neden çevrilmiyor? · **KABUL (ayara çevrildi)**

**Soru:** Kapatan bir şalter mi var?

**Yöntem:** Kaynak ve çevrilmiş EPUB belge belge karşılaştırıldı. Tarama eşikleri okundu.

**Ölçüm:** Şalter yok. İki sabit sayı var: metin yoğunluğu 1.0, görsel kapsama %5.
Çevrilmemiş tek EPUB belgesi görsel ve bağlantıdan oluşuyordu. Çevrilecek metni yoktu.

**Karar:** Üç eşik geliştirici ayarı oldu. Varsayılanlar eski sabitlerle birebir aynı.

**Gerekçe:** Davranış değişmedi. Ama kullanıcı artık `scan_text_density = 0` yapıp kapak metnini
normal çeviriye sokabiliyor.

**Not:** Bekçi testi iki ayarımda uyarı metni olmadığını yakaladı. Eklendi.

**Kanıt:** `6243b71` · `tests/test_scan_threshold_tunables.py`.

---

## D-004 · Bağlamın maliyeti nedir? · **ÖLÇÜLDÜ, VARSAYIM ÇÜRÜDÜ**

**Soru:** Modele komşu metin göndermenin maliyeti ne?

**Yöntem:** 2184 segmentli kitap. `segments_from_document` doğrudan çağrıldı, karakter sayıldı.

**Ölçüm:** Kaynak 517.300 karakter. Bağlam 1.030.768 karakter. Yani kaynağın %199'u, isteğin %67'si.
Ortanca bağlam 193 karakter. En uzunu 3781. Segmentlerin %50,5'i 200 karakterden az görüyor.
`context_before` boş olan sadece 1 segment var.

**Karar:** Varsayılan değişmedi. Kırpma ayarı eklendi (D-005).

**Gerekçe:** Docstring "faydası ölçülmüş, maliyeti azdır" diyordu. Fayda ölçülmüştü, maliyet ölçülmemişti.
Ölçüm maliyetin az olmadığını gösterdi. İsteği üçe katlıyor.

**Kanıt:** `62511ae` · `docs/MEASUREMENTS.md`.

---

## D-005 · Bağlamı kırpmak · **KABUL (varsayılan 400)**

**Soru:** Sayısal bir sınır ne kazandırır?

**Yöntem:** `translation.context_max_chars`. Kırpma ortaya yakın taraftan yapılıyor.
Önceki komşunun sonu, sonrakinin başı kalıyor.

**Ölçüm:** Sınırsız 1.548.068 karakter. 400 → 1.144.128 (−%26). 120 → 811.861 (−%48).
Ortanca bağlam 193 olduğu için 400 medyan segmente hiç dokunmuyor.

**Canlı kontrol:** 820–832. segmentlerde cap=400, sınırsız hâlle birebir aynı metni gönderdi.

**Karar:** Varsayılan 400. Kullanıcı: "1 yapılsın".

**Gerekçe:** Yalnız 400'ü aşan komşuları kesiyor. Fayda segmentlerin yarısında aynen kalıyor.
İsraf gidiyor. Risk düşük, kazanç ölçülü.

**Yanlış giden:** "Bağlamı kaldırmak süreyi %63 düşürüyor" demiştim. Üçüncü kolu koşunca aynı girdinin
53,9 sn de 28,3 sn de sürdüğü görüldü. Süre iddiası geri alındı.

**Kural:** Tek koşu süre ölçümü değildir. Karakter ölçümü güvenilir, süre için tekrar gerekir.

**Kanıt:** `3672c31` · `tests/test_context_cap_tunable.py`.

---

## D-006 · İşaretleri modele yollamamak · **RED**

**Soru:** `<0>…</0>` işaretlerini kesmek token tasarrufu sağlar mı?

**Yöntem:** 2184 bloğun düz ve işaretli hâli karşılaştırıldı.

**Ölçüm:** İşaret taşıyan blok 162/2184 = %7,4. Metne katkı +1.602 / 456.021 = **+%0,35**.

**Karar:** Reddedildi. İşaretler modele gitmeye devam ediyor.

**Gerekçe:** Kazanç binde 3,5. Karşılığı %7,4 blokte stil kaybı. İşaretler hizalamanın kendisi.
Geri koymanın başka yolu kelime hizası istiyor, o çözülmemiş (bkz. D-008).

**Kanıt:** `docs/MEASUREMENTS.md`.

---

## D-007 · Belge ön bilgisi ve konu haritası · **KABUL (bağlandı, varsayılan kapalı)**

**Soru (kullanıcı):** Tüm sayfaları modele yollayıp konu ve terim çıkartsak, system prompt'a eklesek?
Sonra: her sayfadan 2 anahtar kelime. Sonra: rastgele sayfalardan özet.

**Yöntem:** Üç modlu araç: konumsal örneklem, rastgele örneklem (sabit tohum), blok başına anahtar
kelime haritası (~8000 karakter). Hepsi yerel modelle.

**Ölçüm:**
- Konumsal, 7164 karakter → 19 özel ad, hepsi gerçek (Nabi Efendi, Mourad IV, Mekke).
- Rastgele, 14 blok → 17 ad ama gürültülü (`Source`, `River` ad değil).
- Harita: 60 istek, 94 saniye, 450 kelime, 60/60 blokta dolu. Koşunun %1,5'i.
  Kelimeler anlatıyı takip ediyor (`king's wrath, vezir's counsel, dervish story`).
- Her sayfa için 1 istek: ~400 istek, yaklaşık +%160 maliyet.

**Karar:** Ön bilgi ve harita ayar olarak bağlandı. Varsayılan boş. Hiçbiri otomatik çalışmıyor.
Kullanıcı: "2 tamam".

**Gerekçe:** Fikir gerçek bir boşluğu dolduruyor. Segmentlerin %50,5'i neredeyse bağlamsız.
Hiçbiri belgenin konusunu bilmiyor. Maliyet ölçüldü: %1,5. Ama kalite etkisi ölçülmedi.
Bu yüzden varsayılan açılmadı.

**Terimler nereye gidiyor:** Glossary'ye. Çünkü proje terimin gerçekten çevrildiğini doğrulayabiliyor.
Konu ve üslup prose olarak yazılıyor. Onu hiçbir şey doğrulayamıyor, o yüzden insan okuyor.

**Yanlış giden:** Araç ilk sürümde soruyu `translate()` üzerinden sordu. O yol çevirmen system
prompt'unu taşıyor. Model boş yanıt verdi. Düz sohbet çağrısına geçildi.
Ayrıca "her bölümün başı" örneklemesi romanlarda yanlı çıktı. Rastgele örneklem eklendi.

**Kanıt:** `e84849b` · jurnal.

---

## D-008 · EPUB çıktısında işaretleme kaybı · **KAPALI (düzeltildi)**

**Soru:** Çevrilmiş EPUB neden geçersiz XHTML döndürüyor?

**Yöntem:** Kaynak ve çeviri belge belge karşılaştırıldı. Etiket farkı çıkarıldı. Birim testle üretildi.

**Ölçüm:** Kaynak 14 belge, 0 bozuk. Çeviri 1 belge bozuk. Kaybolanlar: 1 `<div>` açılışı,
1 `<span>` çifti, 3 `<a href>` açılışı.

**Kök neden:** Blok, çevrilmiş span'lardan yeniden kuruluyordu. Span yalnız kalın/italik taşır.
Kaynak bir bağlantıyı sarıyorsa o etiket düşüyordu. Ölçüldü: fixtürdeki not paragrafı
`See the note | [1] | below for details.` diye **üç span** olarak okunuyor, yazıcı çok-span yoluna
giriyor ve `<a href="#note1">` kayboluyor.

**Düzeltme:** Kaynak, span'ın taşıyamayacağı bir satır-içi etiket içeriyorsa yazıcı artık **kaynağın
kendi etiketlerini koruyor** ve yalnız kelimeleri taşıyor. Kelimeler kaynak metin run'larına, uzunluk
oranına göre ve kelime sınırlarına oturtularak dağıtılıyor.

**Doğrulama:** Aynı kitap düzeltilmiş yazıcıyla yeniden yazıldı: **14 belge, 0 bozuk** (önce 1 bozuk).
Testler 30/30 geçti. Bağlantı testi artık `xfail` değil.

**Yanlış giden:** İlk denemede düzeltme **doğru yerdeydi** ama test iddiam fazla katıydı: çeviri
cümlesini bitişik arıyordu, oysa etiket cümleyi bölebilir. Bu yüzden test kırmızı kaldı ve düzeltmeyi
"yakınsamadı" diye park ettim. Hata bendeydi, kodda değil. **Kural:** bir düzeltme kırmızı kalıyorsa
önce **iddiayı** sorgula, sonra kodu.

**Kanıt:** `tests/test_epub_writer.py` · `docs/DECISIONS.md` · düzeltilmiş EPUB (14/0).

---

## D-016 · Hiçbir arayüz metni hiçbir dilde eksik kalamaz (2026-09-22) · **fikir: kullanıcı**

**Soru:** Kullanıcı ekran görüntüsünde arama kutusunda **ham anahtar** gördü: `MODEL_SEARCH_PLACEHOLDER` ✗.
Ardından kural: "her dil tüm projeye uygulanmalı, çevrilmemiş kısım olmaması lazım".

**Ölçüm:** `UIStrings.get` çözülemeyen anahtarda **anahtarın kendisini** döndürüyor ✗
(`_TRANSLATIONS[lang].get(key, _TRANSLATIONS["en"].get(key, key))`), yani eksik çeviri ekrana anahtar
adı olarak basılıyor ✗✗. Yeni araç `tools/audit/ui_strings.py` kaynağı `UIStrings.NAME` için tarayıp
sözlüklerle karşılaştırdı: **3 dil** (tr 188 · en 183 · **de 182**), kodda **125 anahtar**, toplam
**34 eksik** ✗ (en 8 · de 9 · tr 5 + eşlik farkları: `SAVE_BTN`, `DEFAULT_PROFILE_NAME` yalnız TR'de ✗).

**Karar:** 34 eksik **üç dile birden** eklendi ✓ → **3 × 193**, eşit ✓. Model seçicinin boş açılır
kutusuna yer tutucu kondu ✓ (`MODEL_INPUT_PLACEHOLDER`, 3 dil ✓) — kullanıcının sorduğu "boş alan" buydu ✓.

**Kural (test):** `tests/test_ui_strings_complete.py` — denetim sıfır dışı dönerse kırmızı ✓; ayrıca
diller arasında **anahtar eşitliği** ✓.

**Yanlış giden:** `SUPPORTED_LANGUAGES` bir **demet** (metin değil ✗) — denetim önce onu da eksik
sandı ✗; artık sınıfın ham sözlüğüne bakıyor ✓ (metaclass çözümlemesine değil ✗).

**Kanıt:** `297a129` · `tools/audit/ui_strings.py` · `tests/test_ui_strings_complete.py`.

## D-015 · Ayar ekranı: 16 gruptan 8'e, uyarıdan ayrı ölçüm satırı (2026-09-22) · **fikir: kullanıcı**

**Soru:** "Ayar menüleri hâlâ karışık duruyor, bir mantığa oturt; uyarı/açıklamalar dağınık."

**Ölçüm:** 44 ayar **16 gruba** dağılmıştı; **9 grup tek satırlık**, **8 ayar grupsuz** (diyalog
bunları "Diğer" başlığına atıyor ✗). Diyalog bölümü **ardışık grup değişimine** göre kurduğu için,
kayıt sırasında arasına başka grup giren bir grup **iki ayrı başlık** olarak açılıyordu ✗.
Uyarılar: 36'sı ~230 karakter ✓ ama **3'ü 375–520** ✗ — diyalog tümünü turuncu duvar olarak basıyor ✗.

**Karar:** (1) Gruplar **8'e** indirildi ve **boru hattı sırasına** dizildi: Çeviri · İstem ve bağlam ·
Sağlayıcı ve istek · Okuma · Tablo ve satırlar · Sığdırma ve yazma · Arayüz · Ek test araçları ✓.
(2) Kayıt yeniden sıralandı, gruplar **bitişik** ✓. (3) `Tunable.evidence` alanı eklendi: ölçüm
kanıtı kısa uyarıdan ayrıldı, diyalog onu **soluk ve bir punto küçük** çiziyor ✓.

**Ölçüm (sonrası):** katlanabilir bölüm **21 → 11** ✓; en uzun uyarı **520 → 236** karakter ✓;
3 ayarın kanıtı ayrı satırda ✓.

**Kurallar (test):** `tests/test_tunables_groups.py` — her ayarın grubu var · gruplar boru hattı
sırasında ve bitişik · tek satırlık grup yok · uyarı ≤ 300 karakter · kanıt varsa uyarı da var.

**Yanlış giden:** "Her grup en az bir temel ayar içermeli" kuralını ben uydurdum ✗ — "Okuma",
"Sığdırma ve yazma", "Tablo ve satırlar", "Ek test araçları" zaten **yalnız gelişmiş** sekmede
olmalı ✓; kural silindi ✗.

**Kanıt:** `80f8ada`, `c7ad7c4` · `tests/test_tunables_groups.py`.

## D-014 · Paketlenmiş exe çeviri başlarken kapanıyor: ağır C eklentileri işçi iş parçacığında geç yükleniyordu (2026-09-22)

**Soru:** Kullanıcı: "DeepL ile ilgili exede sorun yaşıyorum, çeviri başlayınca direkt exe kapanıyor."

**Ölçüm:** Windows olay günlüğü: `LayoutKeep.exe`, hatalı modül **QtWidgets.pyd**, `0xc0000005`
(erişim ihlali). Uygulamanın kendi **fault log**'u iki ayrı iz verdi:
1. 11:44 — işçi iş parçacığı `writers/converter.py → ui/worker.py:_read_document` içinde, ana iş
   parçacığı `ui/progress.py:_on_tick` içinde → erişim ihlali ✗.
2. 12:23 — **`Fatal Python error: Aborted`**: işçi iş parçacığı **numpy'ı içe aktarırken**
   (`ocr/layout_detector.py:41` ← `readers/pdf_reader.py` ← `converter.py`), ana iş parçacığı
   **çöp topluyordu** (ve pill'in `eventFilter`'ındaydı) ✗✗.

**Kök neden:** numpy / OpenCV / onnxruntime / MuPDF metin makinesi **ilk kez işçi iş parçacığında**
yükleniyordu (tembel import ✓). Paketlenmiş PyInstaller + shiboken ortamında bu yükleme, ana iş
parçacığının zamanlayıcı/GC işiyle yarışıyor ve süreç düşüyor ✗.

**Karar:** `app.main` artık `window.show()` sonrası, `app.exec()` **öncesinde**
`_warm_heavy_imports()` çağırıyor ✓ — aynı modüller ana iş parçacığında yükleniyor. Hata olsa bile
uygulama açılır ✓ (eksik okuyucu yalnız onu kullanan işte söylenir ✓).

**Gerekçe:** İki çökme kaydının da ortak izi bu ✗; yarış tamamen ortadan kalkıyor ✓.

**Yanlış giden:** İlk şüphe "DeepL'e özgü"ydü ✗ — değil ✗; sağlayıcıdan bağımsız ✗ (kullanıcı yalnız
DeepL denerken görse de ✗). İkinci şüphe pill'in şeffaf/çerçevesiz ayarlarıydı ✗ — log, çökmenin
pill'de değil **işçi iş parçacığındaki yükleme** olduğunu gösterdi ✓.

**Kanıt:** `bd6df36` · `tests/test_ui_app_warmup.py` · `%APPDATA%\LayoutKeep\layoutkeep_fault.log`
(11:44 ve 12:23 kayıtları) · olay günlüğü 11:45 `QtWidgets.pyd 0xc0000005`.

## D-013 · DeepL: tek bir kontrol karakteri 40 segmentlik isteği düşürüyor (2026-09-22)

**Soru:** DeepL ile karşılaştırma denemesi yapılacaktı; ilk koşu "Tag handling parsing failed …
not well-formed (invalid token)" ile düştü. Sebep ne?

**Ölçüm:** arXiv makalesinin 2. sayfasında **tek bir segmentin kaynağı** tek başına `\x08`
(backspace) karakteriydi ✗ — PDF metin çıkarımından gelen çöp. Segmentler **tek tek** gönderildiğinde
6/6 geçti ✓; parti hâlinde gönderildiğinde **tek bozuk bayt tüm isteği** düşürüyor ✗✗ (DeepL metni
XML olarak ayrıştırıyor ✓). XML 1.0 `\x00-\x08`, `\x0b`, `\x0c`, `\x0e-\x1f` karakterlerini yasaklar;
sekme, satır sonu ve satır başı serbesttir ✓.

**Karar:** `to_deepl_markup` artık XML'in taşıyamadığı kontrol karakterlerini **atıyor** ✓; korunan
değerler (`<lkv>`) de aynı temizlikten ve kaçıştan geçiyor ✓ (o elementi biz yazıyoruz ✓).

**Gerekçe:** Tek karakter yüzünden 40 segmentlik parti düşüyordu ✗; bu, DeepL kullanan her belgeyi
vurabilecek gerçek bir hata ✗. Düzeltmeden sonra aynı kol `failed: []` ile bitti ✓✓.

**Yanlış giden:** İlk teşhis "ham `<`/`&` kaçırılmıyor" sanıldı ✗ — kaçış zaten vardı ✓; suçlu
ancak segmentleri **tek tek** göndererek bulundu ✓ (toplu istekte hata mesajı yalnız sütun numarası
veriyor ✗).

**Kanıt:** `562d25d` · `tests/test_provider_deepl.py` (kontrol karakteri + korunan değer testleri) ·
arXiv 2609.19145 sayfa 2, segment `p2#39`.

## D-012 · Kapak: çeviri resmin üstüne çiziliyor, orijinal silinmiyor (2026-09-21)

**Soru:** Elmasri kapağında "Fundamentals of Database Systems" ile "Veritabanı Sistemleri" üst üste
görünüyor. Program çevirmiş ama orijinali silmemiş.

**Ölçüm:** Kaynak PDF'in 1. sayfasında **metin katmanı boş** (`''`) ve tek bir 700×866 görüntü var →
kapak **saf resim**. Çıktının metin katmanında `Fundamentals`/`Sixth Edition` **hiç yok** (0 sayfa) →
silinecek metin zaten yoktu. Yani: kapak OCR ile okundu (`readers/image_reader.py`), segmentler
çevrildi, çeviri **resmin üstüne** çizildi ve resimdeki orijinal yazı olduğu gibi kaldı.

**Kök neden (düzeltildi - ilk teşhis yanlıştı ✗):** Yazıcıda taranmış sayfa için bir kapatma yolu
**var** (`_cover_scanned_blocks` + `_erase_ink_from_scan`) ve çağrılıyor da. Ama `_erase_ink_from_scan`
kutuyu Otsu ile ikiye bölüp **koyu** kütleyi "mürekkep" siliyor; kapakta koyu olan **kırmızı zemin**,
sarı başlık ise "kâğıt" sayılıyor ✗ → zemin silinip yazı kalıyor. Üstelik fonksiyon `True` dönüyor →
çağıranın yedek olarak tuttuğu **dikdörtgen dolgusu** hiç çalışmıyor ✗.

**Ölçüm (2026-09-21):** Kutu içindeki sarı piksel - kaynak **20.369** · eski kodla **44.436**
(daha da kötü ✗✗) · düzeltmeyle **3.960** ✓ (−%81). Yazar satırı kaynak 175 → **0** ✓✓. Kalan 3.960
muhtemelen kapağın kendi sarı grafiği ✗ (doğrulanmadı ✗). Medyan doygunluk ölçümleri: kapak
**201/201/202** ✓, 1895 tarihli sarı kâğıt taramaları **52-56** ✓ → eşik **120** ✓.

**Karar (uygulandı - `51aee55`):** kutunun medyan doygunluğu > 120 ise kutu kâğıt değil, **renkli panel**
sayılır ✓; erase'ten vazgeçilir ve `False` dönülür → çağıran **kendi zemin dolgusunu** (bloğun
örneklenmiş arka plan rengi ✓) boyar ✓✓. Renkli panelde orijinal yazı böylece temiz kapanıyor ✓.

**Açık kalan:** dolgu hâlâ bloğun **tam kutusu** ✗; taşan glif uçları için ~1,5 pt pay **ölçülmedi** ✗.

**İç sayfa ölçümü (kullanıcı uyarısı üzerine - "kapağı düzelteceğim diye sayfa çevirilerini bozma"):**
Aynı kaynak, **aynı hedef yazı**, kural 120 ve 255 ile iki kez yazıldı → sıradan kâğıt sayfada iki
çıktı **piksel piksel aynı** ✓✓ (fark **0 piksel** ✓; ikisi de kaynağa göre 4.945 piksel değiştiriyor -
o da çevrilen yazının kendisi ✓). Fark yalnız **renkli panel** kutularında ✓. Test:
`test_the_panel_rule_never_changes_a_paper_page` (kural kâğıda sızarsa test kırmızı ✓). Kanıt: `8a13d3b`.
**Yan bulgu ✗:** OCR, doygun panel **üstündeki yazıyı** çoğu zaman hiç bulmuyor ✗ (sarı-kırmızı kapakta ✗,
siyah-kırmızı şekilde ✗) → o kutular zaten çevrilmiyor ✓.

**Risk:** Zemin dolgusu, metnin altındaki **resmi** de boyar ✗ - görselin üstündeki yazıda istenen bu ✓,
ama yanlış kutu komşu grafiği de boyayabilir ✗. Rengi doygun panelde ölçüm yapıldı ✓; taşma payı hâlâ açık ✗.

**Kanıt:** `ElmasriBook.pdf` sayfa 1 (`get_text()` boş, `get_images()` 700×866) · kutu ölçümü
20.369 → 44.436 → 3.960 · `tests/test_pdf_writer_scanned_paper.py` (renkli panel testi) · `51aee55`.

## D-011 · Karakter bütçesi ilk çeviriden ÖNCE verilsin (2026-09-21) · **fikir: kullanıcı**

**Soru:** Sığdırma sürenin %61'ini yiyor. İlk çeviri isteğine kutunun karakter bütçesi baştan
söylense süreç kısalmaz mı?

**Ölçüm (bulgu):** Mekanizma zaten var ama **kullanılmıyor**: `providers/openai_compat.py:467`
isteğe `"max_len": seg.max_len` koyuyor ve satır 484 modele "max_len verilmişse KISA yaz" diyor.
Ancak `Segment.max_len` **yalnızca sığdırma sırasında** dolduruluyor (`worker.py:650`,
`cli.py:572`). İlk çeviride değer `None` → talimat hiç ateşlenmiyor → metin kutuyu taşıyor →
sığdırma tek tek düzeltiyor.

**Karar:** Bölümlemeden hemen sonra, çeviriden önce her PDF bloğunun karakter bütçesi hesaplanıp
`seg.max_len`'e yazılır. Hesap saf geometri (sığdırmanın kullandığı **aynı** ölçücü: `_as_drawn` +
`TextMeasurer.char_budget`), model çağrısı yok, drift riski yok çünkü tek kaynak.

**Ayar:** `translation.prefit_budget`, varsayılan **kapalı** — ölçüm yapılmadan açılmaz (kural:
varsayılan ancak ölçümle değişir).

**Ölçülecek:** Aynı belge, aynı model, iki kod sürümü; kollar (a) bütçesiz (bugünkü), (b) bütçeli.
Karşılaştırma: toplam süre, sığdırmadaki istek sayısı, bayrak sayısı (41 → ?), ve **çıktı kalitesi**
(L3/D1 ölçütleri aynı mı - kısa yazdırmak içeriği kırpmasın).

**Ölçüldü (2026-09-21):** A/B'de **D-010 ile birlikte** koştu (B kolu = toplu istek + `strict` bütçe).
48/48 kutuya bütçe verildi ✓, `budget` fazı 0,2 sn sürdü ✓ (hesap bedava ✓). Kalite kaybı **yok**:
13 ölçütün tamamı 0, `LOSSLESS YES`, bayraklı blok 30 ↔ 29 ✗ (gürültü sınırı ✓).

**Ayrıştırma eksik ✗:** Bu koşu iki değişikliği birden test etti; bütçenin **tek başına** katkısı
ölçülmedi. Sabah bir tur daha: (a) yalnız toplu istek, (b) toplu + bütçe. İkisi ayrı ayrı görülmeden
`translation.prefit_budget` varsayılanı açılmaz ✗ (kural: ölçüm olmadan varsayılan değişmez).

**Risk:** Model bütçeye uymak için **içeriği kısaltabilir** ✗ — bu yüzden ölçümde yalnız süre değil
kayıpsızlık ölçütleri de karşılaştırılır.

**Kanıt:** `providers/openai_compat.py:467,484` · `ui/worker.py:650` · `cli.py:572` ·
`fitting/pdf_pass.py` (`_as_drawn`, `char_budget`).

## D-010 · Sığdırma aşaması neden tek tek istek atıyor (2026-09-21)

**Soru:** 1553 segmentlik koşuda çeviri %100'e geldi, dosya bitmedi; sığdırma (fit) aşamasında
modelden **tek segmentlik** istekler gidiyor. Neden toplanıp tek istekte sorulmuyor?

**Ölçüm:** `fitting/pdf_pass.py:87` segmentleri sırayla geziyor; her sığmayan kutu için
`fit_pdf_pass` → `retranslate(segment, budget)` → `worker.py:651` `provider.translate([segment])`.
Yani istek sayısı = sığmayan kutu sayısı. İstek başına sabit yük ölçülü: 1 segment 32,7 sn ·
2 segment 37,3 sn · 3 segment 42,2 sn (marjinal maliyet ~5 sn). 10 sayfalık denemede fit, toplam
sürenin **%61'i** (65 sn'nin 39 sn'si).

**Karar:** İki geçişli toplu sığdırma. (1) Birinci geçiş `retranslate` yerine bir **kaydedici**
alır: istenen (segment, bütçe) çiftleri toplanır, model çağrılmaz. (2) Toplanan çiftler **tek
istekte** sorulur. (3) İkinci geçiş kaydedilen yanıtları sözlükten verir, sığdırma normal akışına
devam eder. Sonraki turlar (nadir) tek kalır; kazanç ilk turda çünkü orada patlıyor.

**Ölçüldü (2026-09-21, aynı gece):** 3 sayfa, yerel gemma, izole çeviri belleği, iki kol.
Fit **11 dk 22 sn → 6 dk 26 sn = −%43** ✓. Ama **toplam yalnız %6,8 kısaldı** (1162 → 1083 sn) ✗:
kurtarma adımı B'de 7 segment, A'da 2 segment koştu ve o adım zamanlayıcıda hiç yoktu → ~300 sn
kayıp ölçüm kör noktasıydı. `recover` ve `unify` artık faz olarak yazılıyor.
**Kalite:** iki kolda da 13 ölçütün tamamı 0 ve `LOSSLESS YES` ✓; bayraklı blok 29 ↔ 30 (1214 blokta,
gürültü sınırı ✓).

**Yanlış giden:** Kazancın tamamı tek koşuda görünmedi ✗; sebep toplu sığdırma değil, kurtarma
sayısının koldan kola değişmesi ✗. Tek koşuyla "toplam süre" iddiası kurulmaz ✓ - tekrar koşu şart.

**Kanıt:** `lk_prefit/a_baseline/out.timing.html` · `b_prefit_strict/out.timing.html` ·
`audit_a.json` / `audit_b.json` · `lk_prefit_ab.py`.

**Beklenen kazanç:** 8 sığmayan kutu: tek tek ~260 sn ↔ tek istekte ~60 sn (≈4 kat).

**Neden paralel değil:** yerel sunucu istekleri zaten sırayla işliyor; 7 slotlu deneme bu yüzden
etkisiz kaldı. Kazanç istek **sayısında**, eşzamanlılıkta değil.

**Yanlış giden:** Yok — henüz uygulanmadı. Uygulanırken ölçüm şart: aynı belge, aynı model, iki kod
sürümü (yalnız sığdırma farkı), ve karşılaştırma toplam süre + kutu başına sonuç üzerinden.

**Kanıt:** `src/layoutkeep/fitting/pdf_pass.py` · `src/layoutkeep/fitting/fit.py` (satır 203/303/367) ·
`src/layoutkeep/ui/worker.py:649-657` · `providers/batching.py` (ölçülmüş süre tablosu).

## D-009 · EPUB→PDF'te çok sayıda az-metinli sayfa · **TEŞHİS EDİLDİ (düzeltme bekliyor)**

**Soru:** Üretilen 436 sayfalık PDF'te neden 105 sayfa neredeyse boş?

**Yöntem:** Sayfa sayfa metin, görsel ve çizim sayıldı. Punto ve içerik incelendi. Kaynak EPUB'ın aynı
bölümü okundu.

**Ölçüm:** Boş sayfalar 19 blokta toplanıyor. En uzunları 11-15 sayfa (138-149, 151-164, 215-229).
Bu sayfalarda görsel **0**, çizim **0**, toplam ~100 karakter. Yani sayfa başına 5-16 karakter.
İçerik 12 punto ve tek kelime: `RUBĀ'Î`, `GAZEL`, `MUSEDDES` — içindekiler ve bölüm başlıkları.

**İçerik kaybı YOK.** Şiirler PDF'te var: `MUSEDDES` 178, 206 ve 215. sayfalarda da geçiyor.
14-18 arasındakiler içindekiler tablosu. Yani sorun içerikte değil, **sayfalamada**: her başlık ve
içindekiler satırı kendi sayfasını alıyor.

**Kök neden (bulundu):** `pdf_generator._reflow_block_html` **her** TITLE ve HEADING bloğuna
`page-break-before: always` koyuyordu ve MuPDF Story bunu uyguluyor. Yani içindekiler satırları ve her
şiir türü başlığı kendi sayfasını alıyordu.

**Denenen düzeltme (REDDEDİLDİ):** Kırma yalnız bölüm başında (her belge sayfasının ilk bloğu) kalsın.
Sonuç sayfa sayısında büyük kazanç: **436 → 176 sayfa**, seyrek sayfa **105 → 2**. Ama kitabın **başlık
sayfası düştü**: `TÜRK EDEBİYATI İÇERİK`, `Masallar, Güzel Edebiyat ve Kutsal Gelenekler` ve
`EPIPHANIUS WILSON` artık PDF'te yok. Sessiz içerik kaybı, sayfa kazancından ağır basar: **geri alındı**.

**Sıradaki adım:** Story'nin başlıkları sayfa altına itme davranışını koruyup yalnızca içindekiler ve
kısa başlıklar için kırmayı kaldırmak. Yani kırma kararı role göre değil, bloğun **konumuna ve
boyutuna** göre verilmeli. Ölçüm olmadan denenmez.

**Kanıt:** `src/layoutkeep/writers/pdf_generator.py` · `lk_epub_to_pdf_gutenberg_56464.pdf` ·
`lk_reflow_duzeltilmis.pdf` (reddedilen sürümün çıktısı).

---

## D-018 · System prompt düzenlenebilirliği · **KABUL**

*Numara düzeltmesi (2026-09-22): bu kayıt önce yanlışlıkla D-010 numarasını almıştı. Jurnaldeki ve
D-011'deki "D-010" atıfları sığdırma kaydını gösterir.*

**Soru (kullanıcı):** Kullanıcı prompt'u düzenleyip varsayılana dönebilmeli.

**Yöntem:** Üç ayar. `provider.system_prompt_file` rol satırını değiştirir.
`provider.system_prompt_extra` ek satır ekler. `translation.document_preamble` belge bağlamı ekler.

**Ölçüm:** Varsayılanlar boş. İstem birebir aynı kalıyor. Test bunu çiviyor.

**Karar:** Kabul.

**Gerekçe:** Tel protokolü pazarlık dışı. JSON dizisi, işaretler, korunan token'lar, `max_len` hep kalır.
Ayrıştırılamayan yanıt sayfaya geri konamaz. Kullanıcı yalnız talimat tarafını değiştirebilir.
Dosya yoksa sessizce yerleşik role dönülüyor.

**Kanıt:** `d0e722f` · `tests/test_system_prompt_tunables.py`.

---

## Kalıcı dersler

1. **Saklı çıktı taban alınamaz.** İki kol da aynı kodla yazılır. Yoksa motorun kayması değişikliğe yazılır.
2. **Tek koşu süre ölçümü değildir.** Aynı girdi 53,9 sn de 28,3 sn de sürdü.
3. **Kendi kırılmanı önce kendinde ara.** İmport satırı 11 testi kırmıştı, fix değil.
4. **Ölçülmemiş "azdır" cümlesi borçtur.** Ya ölçülür ya "ölçülmedi" diye işaretlenir.
5. **Kazanç küçükse yapısal kayıp kabul edilmez.** Binde 3,5 için stil kaybı reddedildi.
6. **Varsayılan açmak ölçülmüş bir eylemdir.** Açılan varsayılanlar testle çivilenir.

## D-017 · TranslationWorker'un bölünmesi (220 satır kuralı)

- **Soru:** Sınıf gövdesi ~220 satırı aşıyor (494). Nasıl bölünür, davranış değişmeden?
- **Yöntem:** Önce ölçüm (AST ile metot metot satır sayıları), sonra sırayla çıkarma; her adımda
  ilgili testler + TAM paket; her adım ayrı commit.
- **Ölçüm:** 494 → 409 (`FitPassRunner`) → 281 (`DocumentFinalizer`) → **253** (`TopicMapBuilder`).
  Her adımdan sonra tam paket: **1338 passed, 4 xfailed, 1 xpassed** (üç kez).
- **Karar:** Sinyaller ve sayaçlar **geri çağırma** olarak geçirilir; yeni sınıflar Qt durumu tutmaz.
  Worker üç isim için ince delege bırakır (`_fit_pdf_pass`, `_finalize_document`, `_verify`) çünkü
  testler o adları gözetliyor. Kalan ~33 satır `_run`'ın orkestrasyonu; bölünmedi (iş parçacığının
  kalbi, risk/ödül oranı düşük).
- **Yanlış giden:** İlk cerrahide sınır `'    def '` ile aranınca **iç metoda** (`def ask`) kadar
  kesildi ve dosya IndentationError verdi; `git checkout` ile geri alınıp sınır `'\n    def '`
  (satır başı + 4 boşluk) olarak düzeltildi.
- **Kanıt:** commit'ler `00bc76f`, `140a432` + son commit; `tests/test_fitting_mode_setting.py` tarama
  hedefi `fit_pass_runner`'a taşındı (ayar orada yaşıyor).

## D-017 ek · Kurulum ekranından iki çıkarma

`_JobSetupUiBuilder` 290 → **238** (iki adımda): biçim kutusunun doldurulması ve sağlayıcı
kontrolleri `ui/setup_controls.py`'ye taşındı (kare düğme genişliği de oraya: `ICON_BUTTON_WIDTH`).
İlk denemede `ProviderProfileStore` için yanlış modül yolu yazıldı (`providers.profiles`);
**20 test birden yakaladı** — güvenlik ağı çalışıyor. Kalan >220 sınıflar (provider_settings 320,
main_window 310, tweaks_dialog 258, floating_progress 254, openai_compat 235, progress 223)
sıradaki oturuma kalıyor; yöntem aynı: AST haritası → çıkarma → ilgili testler → TAM paket →
ayrı commit.
