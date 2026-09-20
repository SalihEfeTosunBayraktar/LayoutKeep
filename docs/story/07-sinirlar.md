# 7. Dürüst sınırlar, açık işler ve dersler

Bir mühendislik belgesinin en değerli kısmı, çalışmayan şeyleri yazdığı kısmıdır. Bu bölüm
süslenmemiştir.

## 7.1 Bugünkü sınırlar (ölçülmüş)

**Kaynakça ve numaralı başlıklar.** Kitap koşusunda L2 = 2: kaynakça satırları ve bazı numaralı
başlıklar kaynak dilde kalıyor. Bunlar *işaretli* (sessiz değil) ama çevrilmiyor — sebep, bu
satırların "çevrilemez" sayılması: çoğu bir yazar adı, dergi adı, yıl ve sayfa aralığından oluşur
ve çevirmek akademik atıf geleneğine aykırıdır. Karar bilinçli, ama kullanıcı bunu bazen "eksik
çeviri" olarak görüyor; arayüzde daha iyi anlatılması gerekiyor.

**Okunabilirlik tabanının altına inen bloklar (D1).** Uzun çeviriler küçültülüyor; kitapta 801
blok tabanın altında. `--fit-mode reflow` bu sınıfı büyük ölçüde kaldırıyor (NIST dergisinde
D1 52 → 0) ama sabit düzenlerde metni üst üste bindirebiliyor (IRS formunda L7 0 → 1). Bu yüzden
varsayılan **kapalı**: kanıtlanmış kayıp, ölçülmüş kazancın önüne geçer.

**Taranmış sayfalar OCR kalitesine bağlı.** Düşük güvenli bloklar işaretlenir, düzeltilmez. 300 dpi
temiz taramalar güvenilir; eğik, lekeli, düşük çözünürlüklü taramalar değil. Ölçüm: NASA taraması
ve NIST'in taranmış vapor-pressure raporu bu yolu test ediyor.

**Sayı şeritleri.** Bir tablo başlığında satır boyunca dağılmış salt sayı dizileri (örneğin
`11 34 56 79 101 124`) tek bir sola yaslı bloğa düşebiliyor: sayılar korunuyor ama **dizilişleri**
kayboluyor. Bu, tablo yapısının düz metne indiği yerlerde oluyor; çözüm tablo tanımayı
genişletmekten geçiyor.

**Sağdan sola yazı sistemleri uygulanmadı.** Şema `direction` alanını taşıyor (D4), yazıcı bunu
kullanmıyor. Arapça/İbranice bir belge bugün doğru çevrilmez — ve arayüz bunu *söylemez*, çünkü
desteklenen diller listesinde görünmüyorlar.

**Kalite modelin becerisidir.** Boru hattı kaybı engeller, akıcılığı üretmez. Yerel küçük modelle
elde edilen metin, bulut modelinden zayıftır; bu fark sözlük ve bellekle azaltılır, yok edilmez.

**İnceleme kuyruğu okunur, düzenlenemez.** Bayrakların gerekçesi yazılı ama kullanıcı çeviriyi
uygulama içinde düzeltip yeniden yazamıyor. Bu, yol haritasındaki en yüksek emekli iş.

**Çift dilli PDF çıktısı yok.** Site karşılaştırmayı sunuyor; PDF'in kendisi almaşık sayfalı
üretilemiyor (BabelDOC'ta var).

## 7.2 Yol haritası (etki / emek sırasına göre)

1. **Çift dilli PDF çıktısı** (`--dual page|alternate`). Emek: orta. Ölçüm: çıktı sayfa sayısı
   2×kaynak, L1–L10 bozulmuyor.
2. **Örtüşme çözümü kademesi** — `reflow`'u deneysel olmaktan çıkarıp kademeli hâle getirmek
   (küçült → satır aralığını sık → aşağı it), D1=801'i ve "okunamaz boyut" sayısını düşürmek.
3. **Otomatik terim adayları** — belgede sık geçen isim öbeklerini sözlük düzenleyiciye önermek.
4. **Küçük editör** — inceleme bayraklı blokları uygulama içinde düzeltip yeniden yazmak.
5. **Sayfa-ötesi bağlam** — parça sınırında önceki parçanın son bloklarını isteme eklemek; L2 ve
   D2'yi düşürmesi beklenir.
6. **Aralık için görsel sayfa seçici** — küçük önizlemelerle aralık seçmek.
7. **Ayar profilleri** — "hızlı taslak" / "yayın kalitesi" ön ayarları.

## 7.3 Dersler

**1. Ölçüm, özellikten önce gelir.** "Kayıpsız" iddiası ancak sayılabilirse anlamlıdır. Bu projede
her özellik bir *sayıyla* geldi: L/D tablosu, `type_drift`, dört panelli görsel karşılaştırma.

**2. Yanlış ölçüm, ölçümsüzlükten kötüdür.** L10'un yarısı, "bariz büyük font"un tamamı ve
hizalama bayraklarının bir kısmı **ölçüm hatasıydı** (Bölüm 3.3). Üçü de ancak ölçüm aracının
kendisi denetlenerek bulundu. Kural: bir sayı şüpheliyse, önce araca bak.

**3. Kanıtsız düzeltme taşınmaz — ve kanıtsız yeniden yazım da.** Blok genişletme denemesi
ölçümle çürütüldü (12 → 12) ve geri alındı. V2 yeniden yazım planı, tek bir eksik için 1.000+
testi çöpe atacaktı; onun yerine o eksik mevcut motora eklendi.

**4. Aynı yeteneğin iki kapısı olmalı: komut satırı ve arayüz.** İki kez aynı hatayı yaptık:
sözlük/bellek CLI'da vardı, arayüzde yoktu (4.6); paralellik CLI'da vardı, uygulamada yoktu (4.8).
Ders: bir yetenek eklendiğinde **iki kapı da** bağlanmalı, yoksa kullanıcı için yoktur.

**5. Görünmeyen ayar, çalışmayan ayardır.** `timeout.first_batch_s` ayar ekranında duruyordu ve
hiçbir şeyi değiştirmiyordu (4.11). Artık "bildirilen her ayar kodda geçmeli" diye bir test var.

**6. Varsayılan muhafazakâr olmalı.** Paralellik 7'den 2'ye indi: agresif varsayılan, kullanıcının
ilk deneyimini (ve küçük modellerde kaliteyi) bozar. Kullanıcı yükseltebilir; düşürmeyi akıl
etmesi gerekmez.

**7. Kullanıcı geri bildirimi en iyi test setidir.** Bu belgedeki vakaların çoğu kullanıcı
cümlesiyle başlar: *"paralel 7 slot ayarlı olsa da 1 slot yolluyor"*, *"neden tüm kitabı vermiş"*,
*"bariz daha büyük font"*, *"pill'i kapatınca geri açamıyorum"*. Hiçbiri 1.192 testin yakaladığı
türden değildi — hepsi *kullanım* sırasında çıktı. Test süiti regresyonu tutar, kullanım yeni
hatayı bulur.

**8. Telif ve gizlilik mimarinin parçasıdır.** Hangi içeriğin yayınlanacağı (`NOT_PUBLISHABLE`),
belgenin makineden çıkmaması (yerel-önce), ve deponun temizlenmesi (36 MB → 12 MB) sonradan
eklenen özellikler değil; tasarımın parçası olmalıydı ve oldu.
