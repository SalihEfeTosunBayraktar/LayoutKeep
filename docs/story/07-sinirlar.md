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

**İnceleme kuyruğu düzenlenemiyor** (yukarıda): bayrağın gerekçesi var, düzeltme yok. Yol
haritasının en yüksek emekli işi.

## 7.2 Yol haritası (etki / emek sırasına göre)

Önceki yol haritasının 1, 3 ve 7. maddeleri **yayınlandı**: çift dilli PDF, belgeden terim
adayları, ayar profilleri. Kalanlar, bugünkü durumlarıyla:

1. **Örtüşme kademesi** (küçült → satır aralığını sık → aşağı it). Satır aralığı adımı tek başına
   2026-09-20'de yazıldı, ölçüldü ve **geri alındı**: geçişin kendi ikame fontuyla hiçbir bloğu
   kurtarmadı, yazılmış sayfa A/B'si iki kolda aynıydı. Ölçüm asıl işi de gösterdi: bayraklı
   blokların çoğu satır değil **kutu** eksiğidir (`room_below` ölçülen kutuyu 6pt'ye ezebiliyor).
   Emek: orta-yüksek. Ölçüm: D1 ve "okunamaz boyut" sayısı, L7 ile birlikte okunur.
2. **Küçük editör** — inceleme bayraklı blokları uygulama içinde düzeltip yeniden yazmak. Emek: yüksek.
3. **Sayfa-ötesi bağlam** — parça sınırında önceki parçanın son bloklarını isteme eklemek; L2 ve
   D2'yi düşürmesi beklenir.
4. **Aralık için görsel sayfa seçici** — küçük önizlemelerle aralık seçmek.
5. **Sınırların arayüze taşınması** — D1/kutu ayrımı tamamlanma ekranında (0.9.7); kaynakça notu
   henüz değil.

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
*"bariz daha büyük font"*, *"pill'i kapatınca geri açamıyorum"*. Hiçbiri 1.256 testin yakaladığı
türden değildi — hepsi *kullanım* sırasında çıktı. Test süiti regresyonu tutar, kullanım yeni
hatayı bulur.

**8. Telif ve gizlilik mimarinin parçasıdır.** Hangi içeriğin yayınlanacağı (`NOT_PUBLISHABLE`),
belgenin makineden çıkmaması (yerel-önce), ve deponun temizlenmesi (36 MB → 12 MB) sonradan
eklenen özellikler değil; tasarımın parçası olmalıydı ve oldu.
