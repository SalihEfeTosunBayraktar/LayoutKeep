# 6. Ürünleşme: motordan uygulamaya

Motor doğru olsa da kullanılamıyorsa proje bitmiş sayılmaz. Bu bölüm, "kütüphane"den "herkesin
indirip çalıştırabildiği bir uygulama"ya giden adımları ve her adımın hangi kullanıcı şikâyetinden
doğduğunu anlatır.

## 6.1 Karşılama ekranı

**Şikâyet:** *"ilk açılışta bir karşılama ve açıklama ekranı olsun, nasıl ilk çeviri yapılır, ne
ayar ne işe yarar, yerel sağlayıcı vb... baya detaylı, dil vb oradan başlarken seçilebilmeli, tema
dahil."*

Karşılama dört sayfadan oluşur ve **ilk çalıştırmada** açılır:

1. **Ne yapar** — belgeyi kutusunda çevirir; üç cümlelik özet ve "kayıpsız" tanımı.
2. **Nasıl çalıştırılır** — sürükle-bırak, dil seçimi, sağlayıcı seçimi; yerel/bulut farkı.
3. **Hangi ayar ne işe yarar** — bağlam penceresi ve yuva sayısı matematiği (7 işçi + 8192 pencere
   = istek başına ~1.2k token), sığdırma eşikleri, korunan değerler.
4. **Dil ve tema** — arayüz dili (TR/EN/DE) ve açık/koyu tema burada seçilir.

Karşılama **sürüm bazlı** işaretlenir: yeni sürüm, yeni karşılamadır. (Bu, "karşılama çıkmadı"
şikâyetinin kalıcı çözümüdür — Bölüm 4.5.)

## 6.2 Yardım: kriterler kullanıcıya açık

**Şikâyet:** *"her türlü kullanıcının kullanabilmesi için yardım ve açıklayıcı kısımlar fazlaca
olmalı."*

Yardım ekranı yedi bölümden oluşur ve **motorun kendi kriterlerini** anlatır: ilk çeviri, sağlayıcı
seçimi, ayarların anlamı, inceleme bayrakları (her bayrağın ne demek olduğu), kayıpsızlık
kriterleri (L1–L10 + D1–D3, Türkçe adlarıyla), çıktıların nerede olduğu (`.lkproj`, bellek,
günlükler, taşınabilir mod), sorun giderme.

Kural: yardım, kodda olmayan bir şey vaat etmez. Her bölüm, o sürümde gerçekten çalışan bir
davranışı anlatır — ve davranış değiştiğinde yardım metni de değişir (bu, sürüm notlarında
görülebilir: paralellik varsayılanı 7→2 olduğunda üç ayrı metin güncellendi).

## 6.3 Sözlük ve bellek arayüzde

**Şikâyet:** *"sözlük nerede?"* (Bölüm 4.6)

- **Sözlük**: dosya seçilir (JSON veya CSV/TSV), uygulama içinde **tablo olarak düzenlenir**
  (satır ekle/sil, dosyadan yükle, farklı kaydet), çeviri sırasında hem istemde hem çıktı
  denetiminde uygulanır. Sözlüğün parmak izi bellek anahtarına girer — sözlüğü değiştirdiğinizde
  eski çeviriler sessizce kullanılmaz.
- **Bellek**: koşular arası SQLite. Tamamlanma ekranı **isabet oranını** gösterir. Gerçek bir
  koşuda 2.555 segment birikti; aynı belgeyi yeniden başlatmak, o segmentler için modeli hiç
  çağırmaz.

## 6.4 Yüzen çubuk ve pencere geçişi

**Şikâyet:** *"aynı anda pill ve ana pencerenin gözükmesi ve büyük pencereyi gizleyince küçüğün
gizlenme sorununu çöz"* + *"pill'i kapatınca geri açamıyorum."*

Uzun koşularda pencereyi arkaya atabilmek gerekir. Çözüm iki yönlü bir geçiş:

- Başlıktaki **▤ "Küçük pencereye geç"** düğmesi pencereyi gizler, ilerleme yüzen çubukta devam
  eder (koşu sürerken etkindir).
- Çubuktaki **"Pencereye dön"** geri getirir; pencereyi küçültmek çubuğu **gizlemez** (sahiplik
  ilişkisi kaldırıldı — Bölüm 4.7).
- Çubuk; ilerleme yüzdesi, aşama, segment sayaçları ve dosya adını gösterir. Dosya adı çubuğa
  sığmazsa kısaltılır ama **tam ad tooltip'te** durur (kısaltılmış bir adı doğrulayamadığınız bir
  ad, işe yaramaz).

## 6.5 Sayfa aralığı: ne vaat ediyorsa onu yapar

**Şikâyet:** *"sadece seçtiğim aralığı çıktı vermesi gerekmez mi?"* (Bölüm 4.12)

Aralık seçildiğinde:

- **Çevrilen**: yalnız seçilen sayfalar.
- **Çıktı**: yalnız seçilen sayfalar (yazıcıya kaynağın dilimi verilir).
- **Proje (`.lkproj`)**: belgenin **tamamı** — inceleme ekranı geri kalanı da gösterir ve yeniden
  dışa aktarma belgeyi sessizce kısaltmaz.

Arayüzde aralık seçildiği anda ne olacağı yazılıdır (TR/EN/DE). Bu davranış 11 testle sabitlendi,
gerçek 15 sayfalık bir corpus PDF'i üzerinde ölçüldü: aralık "1-2" → çıktı 2 sayfa, proje 15 sayfa.

## 6.6 Çift dilli PDF

**İstenen:** karşılaştırma sitesi kaynak ↔ çeviri yan yana gösteriyor, ama PDF çıktısında yok.

`--dual side|alternate` (ve arayüzde bir kutu): `side` her sayfada solda kaynak sağda çeviri
(sayfa genişliği 2×), `alternate` her kaynak sayfadan sonra çevirisi (sayfa sayısı 2×). Tasarım
kararı **boru hattına dokunmamak**: birleştirme, iki bitmiş dosyadan sonradan yapılır, çünkü
denetim kaynak sayfa N'i çıktı sayfa N ile eşler ve çift dilli bir belge bu eşlemeyi bozar.
Böylece çevrilmiş PDF ve `audit.json` aynen kalır; çift dilli dosya onların yanına yazılır.
Yarıda kalan koşuda yalnız iki belgenin de sahip olduğu sayfalar birleştirilir ve sayı bildirilir.
Plan ve ölçüm: `docs/DUAL-OUTPUT-PLAN.md`.

## 6.7 Sürümler ve yayın akışı

Uygulama **tek dosya** olarak yayınlanır (`LayoutKeep.exe`, ~173 MB, onefile), GitHub Releases
üzerinden. Yayın akışı:

1. `pyproject.toml` + `__init__.py` sürümü artırılır.
2. `PyInstaller packaging/layoutkeep_onefile.spec --noconfirm --clean` ile derlenir.
3. Tam test süiti koşar.
4. Etiket + release; **indirilen dosyanın SHA-256'sı yerel derlemeyle karşılaştırılır**.

Yayınlanan sürümler ve her birinin getirdiği şey:

| Sürüm | Ne getirdi |
|---|---|
| 0.9.1 | İlk genel yayın: karşılama, yardım, sözlük/bellek arayüzü, inceleme kuyruğu |
| 0.9.2 | Çubuk ↔ pencere geçişi; karşılama sürüm bazlı; Romen rakamı koruması (ayarla açılır/kapanır) |
| 0.9.3 | ▤ düğmesi + yardım metinleri |
| 0.9.4 | **Uygulama istekleri paralel gönderiyor** (dalga dalga, belge sırasında birleşir) |
| 0.9.5 | Ölü ayar anahtarı bağlandı; paralellik varsayılanı 2; çubuk tooltip'i; aralık çıktıyı daraltır |

## 6.8 Karşılaştırma sitesi

**İstenen:** *"orijinal kaynakları ve çevrilmiş hallerini yan yana kıyaslayabileceğim bir slider
web sitesi, tüm örnekler için."*

Site `docs/comparison/` altında üretilir ve GitHub Pages'te yayınlanır:

- **Tek belge görüntüleyici**: solda orijinal, sağda çeviri, ortada sürüklenebilir ayırıcı;
  tekerlek ile yakınlaştırma; klavye ile sayfa gezinme.
- **Her belge için denetim özeti**: L ve D sayıları, sayfa sayısı, model, tarih.
- **22 belge**: arXiv makaleleri, NIST dergisi ve formu, IRS formları, NASA raporu (dijital +
  taranmış), Project Gutenberg kitapları, kamu malı bir DOCX, iki taranmış sayfa.
- **Geliştirme koşuları** varsayılan olarak gizli, tek kutucukla açılır — yayınlanan liste gerçek
  belgelerden oluşur.
- **Telif kuralı**: yalnız açık lisanslı/kamu malı kaynaklar yayınlanır; telifli olanlar
  (`NOT_PUBLISHABLE`) yalnız kullanıcının diskinde kalır.

Görseller tek belge başına yüklenir (tembel): toplam 49 MB'lık arşiv, ziyaretçi başına ~1 MB'lık
trafik demektir. NASA belgesinin 6997×3163'lük render'ları 3200px'e indirildi (10,4 MB → 1,9 MB) —
zoom için fazlasıyla yeterli, belge başına yarı yarıya az veri.

## 6.9 GitHub Pages: açılış sayfası ve bağlantılar

- **Kök** (`/LayoutKeep/`): açılış sayfası — indirme, karşılaştırma sitesi ve hikâye bağlantıları.
- **`/docs/comparison/`**: karşılaştırma sitesi.
- **`/docs/story/`**: bu belge (çok sayfalı).
- **Eski adres** (`docs/comparison.html`): 4,4 MB'lık tek dosyalık eski sayfa, paylaşılmış
  bağlantılar kırılmasın diye **yönlendirmeye** dönüştürüldü.
- **README'ler** (EN/TR): indirme bağlantısı `releases/latest` üzerinden; vitrin düğmeleri güncel
  siteye bakar; "bu daldaki kodun durumu" notu iki dilde de kalıcıdır (bir push onu silmişti,
  geri konuldu ve iki tarafta tutuluyor).

## 6.10 Ölçek: bugünkü sayılar

| | Değer |
|---|---|
| Kaynak kod | ~24.000 satır (`src/`), 133 dosya |
| Test | **1192 test**, 138 test dosyası |
| Denetim aracı | 56 (`tools/audit/`) |
| En büyük gerçek koşu | 220 sayfalık kitap, 55 parça, ~106 dakika |
| En büyük tek belge | 841 sayfa (tamamı çevrildiğinde ~%23'ü tek koşuda) |
| Karşılaştırma sitesi | 22 belge, 276 görsel |
| Ayar | 30, hepsi koda bağlı ve testli |
