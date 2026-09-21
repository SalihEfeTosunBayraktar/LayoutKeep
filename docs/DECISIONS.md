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

## D-010 · System prompt düzenlenebilirliği · **KABUL**

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
