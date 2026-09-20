# 4. Hata kataloğu: on dört vaka, belirtiden teste

Bu bölüm projenin hafızasıdır. Her vaka şu kalıpta yazılıdır: **belirti** (kim, nasıl fark etti),
**araştırma** (hangi ölçüm yapıldı), **kök neden** (kodun neresi, neden öyle yazılmıştı),
**çözüm** (ne değişti), **kanıt** (hangi test/ölçüm). Kasten sıralı değil, önem sırasına göre.

## 4.1 "Model bulunamadı" — hata mesajı yalan söylüyordu

**Belirti.** LM Studio'da model yüklü, uygulama "Model bulunamadı" diyor. Model değiştirildi,
sunucu yeniden başlatıldı, hiçbiri işe yaramadı.

**Araştırma.** Sağlayıcı yanıtının **gövdesi** açıldı (ilk denemede yalnız HTTP durum koduna
bakılıyordu). Gövdede şu yazıyordu: `Context size has been exceeded`.

**Kök neden.** İki ayar birbirini yiyordu: LM Studio `-c 8192` (8 KB bağlam) ile ve uygulama
**7 paralel istek** ile çalışıyordu. Bağlam penceresi yuvalara **bölünür** — 7 işçi 8192'lik
pencerede istek başına ~1.2k token alır ve uzun bir paragraf bunu aşar. Sunucu, taşan isteği
"bağlam aşıldı" diye reddediyor; sağlayıcı katmanı bunu "model bulunamadı" diye sarmalıyordu.

**Çözüm.** Üç katmanlı: (a) hata gövdesi okunur ve mesaj gerçeği söyler, (b) taşma artık ölümcül
değil — parça cümle sınırından bölünüp yeniden sorulur, (c) yardım ve karşılama ekranları bu
matematiği açıkça yazar: *"bağlam penceresi yuvalara bölünür; 7 işçi için `-c 32768` önerilir"*.

**Kanıt.** `tests/test_providers_*` hata gövdesi çözümlemesi; kitap koşusu 32768 ile 220 sayfa
tamamlandı. Bu vaka ayrıca **varsayılan paralelliğin 2'ye çekilmesine** gerekçe oldu (Bölüm 4.10).

## 4.2 Yüzen çubuk: heap çökmesi (0xc0000374)

**Belirti.** Uzun koşularda uygulama ansızın kapanıyor; Windows olay günlüğünde
`0xc0000374` (heap corruption).

**Araştırma.** Çökme, yüzen ilerleme çubuğu açıkken oluyordu. Çubuk, ana pencereden bağımsız bir
pencere; sürükleme yardımcısı (`WindowDrag`) pencereyi tutuyordu.

**Kök neden.** `WindowDrag` nesnesi yalnız yerel değişkende tutuluyordu; Python onu topladığında
Qt tarafındaki sinyal bağlantıları hâlâ ona işaret ediyordu — C++ tarafı serbest bırakılmış
Python nesnesine dokunuyordu. Klasik "sahipliği kim tutuyor" hatası.

**Çözüm.** Sürükleme yardımcısı pencereye **güçlü referansla** bağlandı (`self._drag = WindowDrag(...)`)
— nesne pencereyle birlikte yaşar, pencereyle birlikte ölür.

**Kanıt.** `tests/test_ui_floating_progress.py` (11 test) + çubuk artık kitap koşusunun tamamında
açık kalabiliyor.

## 4.3 Aynı metin defalarca çevriliyordu

**Belirti.** Uzun bir belgede aynı cümle (örneğin bir form etiketi, bir başlık) onlarca kez
modele gidiyordu; koşu gereksiz yavaştı ve aynı metne **farklı** çeviriler çıkabiliyordu.

**Araştırma.** IRS formunda tek bir etiketin 40'tan fazla tekrarı vardı. İstek günlüğüne bakıldı:
her tekrar ayrı istek.

**Kök neden.** Boru hattı her bloğu bağımsız çeviriyordu; tekrar kavramı yoktu.

**Çözüm.** `providers/dedupe.py`: aynı kaynak metin bir kez çevrilir, sonuç tüm tekrarlara
dağıtılır (`--no-repeats` ile kapatılabilir). Ek olarak `core/repeats.py` **farklı** çevirileri
çoğunluğa hizalar — yani "Chapter" bir yerde "Bölüm", başka yerde "Kısım" kalmaz.

**Kanıt.** `tests/test_providers_dedupe.py`, `tests/test_core_repeats.py`; IRS koşusunda istek
sayısı belirgin biçimde düştü, terim tutarlılığı arttı.

## 4.4 Kırılan ve küçülen satırlar — ve ölçülüp geri alınan düzeltme

**Belirti.** Kullanıcı, çıktı sayfalarında satırların kırıldığını ve bazı blokların gereğinden çok
küçüldüğünü bildirdi.

**Araştırma.** Hipotez: "blok kutusu genişletilirse satır kırılmaz". Kutuyu genişletme denendi:
kırılan satır sayısı **12 → 12** (hiç değişmedi). Hipotez ölçümle çürütüldü.

**Kök neden.** Gerçek sebep sığdırma merdivenindeydi: çeviri kutuya sığmadığında blok hemen
küçültülüyordu; oysa önce **kısaltma isteme** (modelden daha kısa çeviri) hakkı vardı.

**Çözüm.** Sığdırma sırası yeniden düzenlendi: küçült → kısaltma iste → aşağı it → işaretle.
Genişletme denemesi **geri alındı** ve gerekçesi koda yazıldı (kanıtsız düzeltme taşınmaz).

**Kanıt.** `type_drift` "okunamaz boyutta" sayısı IRS'te 14 → 2; kırılan satırlar için
`tests/test_pdf_writer_widen.py` geri alma kararını belgeler.

## 4.5 Karşılama ekranı görünmüyordu (kendi doğrulama koşum yüzünden)

**Belirti.** Kullanıcı: "yeni 9.1 sürümlü exe'de herhangi bir karşılama ekranı çıkmadı."

**Araştırma.** Ayar kayıt defterinde `welcome_shown = true` görünüyordu. Kim yazmıştı? Karşılama
ekranını test eden **kendi otomatik koşularım** — test bitince bayrağı geri almıyorlardı.

**Kök neden.** Karşılama bir kez gösterilip işaretleniyordu; hem testler hem de gerçek kullanıcı
aynı bayrağı paylaşıyordu. Ayrıca kullanıcı yeni bir sürüm indirdiğinde ne olduğunu göremiyordu.

**Çözüm.** İki değişiklik: (a) otomatik testler `LAYOUTKEEP_NO_WELCOME` kaçış anahtarıyla
çalışır, (b) karşılama artık **sürüm bazlı** işaretlenir — yeni sürüm yeni karşılamadır, ne
değiştiğini kullanıcı ilk açılışta görür.

**Kanıt.** `tests/test_ui_welcome*.py` + kayıt defterinde `welcome_shown_version = 0.9.3`.

## 4.6 Sözlük ve bellek yalnız komut satırında vardı

**Belirti.** Kullanıcı sözlük (terim zorlama) ve çeviri belleği özelliklerini duydu, arayüzde
bulamadı: "sözlük nerede?"

**Araştırma.** Kod taraması: `providers/glossary.py` ve `providers/memory.py` vardı, testleri
vardı, **arayüzden çağrılmıyordu**. Kullanıcı için "olmayan özellik" ile "görünmeyen özellik"
arasında fark yoktur.

**Kök neden.** Özellikler motor katmanında eklenmiş, arayüz bağlantısı sonraya bırakılmıştı ve
sonra hiç yapılmamıştı.

**Çözüm.** İkisi de arayüze bağlandı: sözlük dosyası (JSON **veya** CSV/TSV) seçilebilir,
uygulama içinde **tablo olarak düzenlenebilir** (satır ekle/sil, dosyadan yükle, farklı kaydet),
sözlüğün parmak izi bellek anahtarına girer (sözlük değişince eski çeviriler geçersiz olur) ve
tamamlanma ekranı bellek isabetini gösterir.

**Kanıt.** `tests/test_ui_glossary*.py`, `tests/test_ui_settings_memory*.py`.

## 4.7 Yüzen çubuk ana pencereyi rehin alıyordu

**Belirti.** Kullanıcı: "pill'i kapatınca geri açamıyorum" + "aynı anda hem pill hem ana pencere
görünüyor".

**Araştırma.** Çubuk, ana pencerenin **sahipli** (owned) penceresiydi: ana pencere küçültülünce
çubuk da kayboluyor, ama çubuk kapatıldığında geri getirecek bir yol kalmıyordu.

**Kök neden.** Sahiplik ilişkisi yanlış kurulmuştu: çubuk ana pencereden bağımsız yaşamalı, ama
pencereyle **birlikte** görünmelidir; ayrıca geçiş iki yönlü olmalıydı.

**Çözüm.** Çubuk sahiplikten çıkarıldı; başlığa **▤ "Küçük pencereye geç"** düğmesi eklendi
(koşu sürerken etkin) ve çubuktaki "Pencereye dön" ile geri dönülüyor. Pencere küçültülünce çubuk
kaybolmuyor.

**Kanıt.** 7 test (`tests/test_ui_floating_pairing.py`), v0.9.2/v0.9.3 sürüm notları.

## 4.8 Uygulama istekleri tek tek gönderiyordu

**Belirti (kullanıcı).** *"paralel 7 slot ayarlı olsa da aynı anda sadece 1 slot yolluyor bu bir
hata olmalı."*

**Araştırma.** İki yol karşılaştırıldı: komut satırı (`translate_book.py`) parçaları
`ThreadPoolExecutor` ile paralel çeviriyordu; uygulamanın işçisi (`ui/worker.py`) **tek tek**
istek gönderiyordu. Yani 7 yuva ayarı yalnız komut satırında işe yarıyordu — kitap koşuları hızlı,
uygulama koşuları yavaştı.

**Kök neden.** Paralellik özelliği CLI'da eklenmiş, arayüzün çeviri döngüsüne hiç taşınmamıştı.
(Bu, 4.6'nın kardeşi: motor yeteneği arayüzde yok.)

**Çözüm.** Döngü **dalga dalga** çalışacak şekilde yazıldı: her dalgada `translation.workers`
kadar batch paralel gider, dalga sonunda duraklat/iptal kontrol edilir, sonuçlar **belge sırasına
göre** birleştirilir (hangi isteğin önce bittiğine bağlı değildir). Her paralel iş parçası kendi
sağlayıcı zincirini alır — dedupe önbelleği ve bellek bağlantısı paylaşılırsa yarış olurdu. Döngü
`worker.py`'den `ui/translation_loop.py`'ye taşındı (tek sorumluluk).

**Kanıt.** `tests/test_ui_translation_parallel.py`: (a) eşzamanlılık gerçekten >1, (b) tek işçide
sıralı kalır, (c) çıktı belge sırasında. Süit 1192 test yeşil.

## 4.9 OCR gürültüsü sessiz değil

**Belirti.** NASA taramasında dekoratif başlık "Naga Merorautigs Frogrom Amerika" diye okundu.

**Araştırma.** OCR güven skoru o blok için 0.62'ydi (eşik 0.75).

**Kök neden.** Gürültü OCR'ın doğasında var; sorun gürültü değil, **sessizlik** olurdu.

**Çözüm.** Düşük güvenli bloklar çıktıya yazılır ama **"OCR güveni düşük (0.62)"** gerekçesiyle
inceleme kuyruğuna düşer. Kullanıcı neyin şüpheli olduğunu bilir.

**Kanıt.** `tests/test_ocr_confidence*.py`; jurnal notu (2026-09-20).

## 4.10 Varsayılan paralellik fazla agresifti

**Belirti (kullanıcı).** *"default paralellik 1 veya 2 olabilir."*

**Araştırma.** 4.1'in matematiği: tek bir yerel GPU'da 7 eşzamanlı istek bağlam penceresini
bölüşür, istek başına token düşer, küçük modellerde kalite kaybı ve taşma riski artar.

**Çözüm.** `translation.workers` varsayılanı **7 → 2**. Yuva sayısı elveren sunucularda
(örneğin LM Studio `-c 32768 --parallel 7`) kullanıcı yükseltir; ayarın uyarı metni bunu söyler.
Komut satırı araçlarının yedek sabiti de 2'ye çekildi ki tek bir hikâye olsun.

**Kanıt.** `tests/test_parallel_workers.py` + `tests/test_core_tunables_wired.py`.

## 4.11 Ayar ekranındaki ölü anahtar

**Belirti (kullanıcı).** *"uygulamanın arayüzüne bağlanmamış ayarları bul ve uygulamaya bağla."*

**Araştırma.** Bildirilen 30 ayarın anahtarları, `src/` içinde okunan anahtarlarla karşılaştırıldı
(statik tarama + dolaylı okumalar için sabit adları da arandı). Sonuç: **bir** ölü anahtar —
`timeout.first_batch_s`: ayar ekranında görünüyor, kaydediliyor ve **hiçbir şey okumuyordu**
(ilk partinin zaman aşımı sabitten geliyordu). Ayrıca ayar ekranının 30/30 gösterdiği de ölçüldü.

**Çözüm.** Anahtar worker'a bağlandı (soğuk modelin ilk yanıtı dakikalarca sürebilir; bu makinenin
özelliği, kodun değil). Beş test eklendi: *bildirilen her ayar kodda geçmeli*, ilk-parti ayarının
zaman aşımına ulaştığı, warm partinin ondan etkilenmediği, varsayılanın 2 olduğu, ayar ekranının
her bildirileni gösterdiği.

**Ders.** Çalışmayan bir anahtar, hiç olmayan bir anahtardan kötüdür — çalışanlara olan güveni
harcar.

## 4.12 Sayfa aralığı çıktıyı daraltmıyordu

**Belirti (kullanıcı).** 841 sayfalık kitapta aralık seçildi; çıktı yine **tüm kitap** geldi:
*"ama sadece seçtiğim aralığı çıktı vermesi gerekmez mi, neden tüm kitabı vermiş."*

**Araştırma.** Çıktı PDF'i: 841 sayfa, 194'ünde Türkçe (%23 — seçilen aralık), gerisi İngilizce.
Motor aralığı **yalnız çeviriye** uyguluyordu; çıktı, kaynağın tamamının kopyasıydı.

**Kök neden 1 (tarihsel).** Bu bilinçli bir karardı ve yazılıydı: bir zamanlar aralık belgeden
sayfa **silerek** uygulanmış, proje yalnız seçili sayfaları saklayınca inceleme kaybolmuş ve
yeniden dışa aktarma sessizce kısalmıştı (CONTRACT.md, D5). Doğru çözüm aralığı **ikiye
ayırmaktı**: yazılan kopyaya uygula, kaydedilen projede tüm sayfaları tut.

**Kök neden 2 (ölçümle çıktı).** İlk denemede belge içinden sayfaları düşürmek yetmedi — çıktı
yine 841 sayfa geldi, çünkü PDF yazıcısı sayfaları **kaynak dosyadan** çiziyor. Yazıcıya kaynağın
**dilimi** verildi; dilimdeki sayfalar 0..n olarak yeniden numaralandı ki doğrulama sayfa N'i N ile
karşılaştırsın, proje ise özgün numaraları korusun (sayfalar kopyalanarak — paylaşılan nesneleri
yerinde değiştirmek projeyi bozardı).

**Çözüm.** `_output_document` + `_source_slice`; arayüzde aralık seçilince ne olacağı yazıyor
(RANGE_HINT, tr/en/de). **Kanıt:** 11 yeni test + eski D5 testi yeni sözleşmeye çevrildi —
gerçek 15 sayfalık corpus PDF'inde aralık "1-2" → çıktı 2 sayfa, proje 15 sayfa.

## 4.13 İki yana yaslı paragraflar sola yaslı çıkıyordu

**Belirti (kullanıcı).** *"sayı başlık hizalamaları çevirilerde kaybolmuş."*

**Araştırma.** `type_drift` arXiv 19113'te 4 gövde paragrafını `right → left` diye işaretledi.
Satır satır bakıldığında kaynak iki yana yaslı (her satır 72→540, son satır kısa), çıktı sola
yaslı ve sağ kenarı tırtıklı.

**Kök neden.** Yazıcı blokları HTML kutusuyla çiziyor ve orada `text-align: justify` zaten
destekli; eksik olan **okuyucunun hiç "justify" üretmemesiydi** (yalnız left/right/center).

**Çözüm.** Üç şartlı kural: sol kenarlar düz + son satır kısa + son satırın **sol kenarı** gövdeyle
aynı. Üçüncüsü kritik — ortalanmış başlığın satırları da kısalır, ama son satır ortadan başlar;
o şart olmadan NASA kapak başlığı merkezden kayıyordu (test yakaladı).

**Kanıt.** 19 hizalama testi + 218 okuyucu/layout testi; iki eski test yeni sözleşmeye çevrildi,
dört yeni test eklendi.

## 4.14 Klasör düzeni: telifli sayfa görüntüleri depoda

**Belirti (kullanıcı kriteri).** *"açık kaynaklı olan içerikleri githubda yayınla gerisi lokalde
kalsın."*

**Araştırma.** İzlenen dosya taraması: `tests/layout_eval/` altında 62 JPEG vardı; ikisi telifli
bir ders kitabının sayfaları (`computer-systems-Architecture.pdf`), biri kişisel bir tarama
(`Notes_...`), artı bir `run.log`. Toplam izlenen depo: **36 MB**.

**Çözüm.** Telifli/kişisel görüntüler **izlemeden çıkarıldı** (dosyalar diskte kaldı, README'lerine
"telif nedeniyle yayından çıkarıldı, komutlarla yeniden üretilebilir" notu düşüldü). Kamu malı NASA
görüntüleri kaldı. `.gitignore` kuralları eklendi. İkinci geçişte bir alt klasördeki zoom'lar da
(ilk taramada gözden kaçmıştı) çıkarıldı. **İzlenen depo: 36 MB → 12 MB.**

**Ders.** İlk tarama yeterli değildi; desen eşleşmesi alt klasörleri kapsamıyordu. Tekrar taramak
"gereksiz titizlik" değil, tamamlanmış işin parçasıydı.
