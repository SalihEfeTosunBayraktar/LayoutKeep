# 3. Ölçüm disiplini: sayılar nasıl üretiliyor, ve ölçümün kendisi nasıl yanıldı

Bu projenin en çok tekrarlanan dersi şu: **yanlış ölçüm, ölçümsüzlükten kötüdür.** Yanlış bir sayı
yok sayılmaz — düzeltilmesi gereken bir düzeltme üretir, insan saatleri harcatır, ve bir süre sonra
"kayıpsız" iddiasını güvenilmez yapar. Bu bölüm önce ölçümün ne olduğunu, sonra üç kez nasıl
yanıldığını anlatır.

## 3.1 On kayıp türü, üç kalite eşiği

`verify.py` her koşuda şu kriterleri sayar. Kural: **her kriter ya 0'dır ya da gerekçesi yazılıdır.**

| Kod | Ne sayar | Nasıl ölçülür |
|---|---|---|
| **L1** | Sayfa sayısı farklı | Kaynak ve çıktı PDF'lerinin sayfa sayıları |
| **L2** | Çevrilmemiş ya da başka dilde | Çıktı sayfasındaki kelimeler kaynağın diliyle karşılaştırılır |
| **L3** | Yazıcı bloğu düşürmüş | DocIR'daki blok çıktıda bulunamadı |
| **L4** | Metin sayfanın dışına taşmış | Kelime kutusu sayfa dikdörtgeninin dışında |
| **L5** | Etiket sızmış | Çıktıda `<...>` kalıbı |
| **L6** | Çeviride sayılar kaybolmuş | Kaynaktaki sayı kümesi çıktıda aranır |
| **L7** | Metin başka metnin üstüne yazılmış | Kelime kutularının çakışması |
| **L8** | Çevrilmeyen metin yerinden oynamış | Kaynakta duran blok çıktıda başka yerde |
| **L9** | Başka alfabeden harf karışmış | Örnek: `Việt語` — Latin + CJK karışımı |
| **L10** | Metin bir figürün üstüne çizilmiş | Kelime kutusu görsel kutusuyla kesişiyor |
| **D1** | Okunabilirlik tabanının altında | Punto 0.85 ölçeğinin altına inmiş bloklar |
| **D2** | Kısa bloklar değişmeden kalmış | 3 kelimeden kısa ve çevrilmemiş bloklar |
| **D3** | Kutuya sıkışmış metin | Kelimeler arası boşluk sıfıra inmiş |

L-kriterleri **kayıp**, D-kriterleri **kalite**tir: bir L ihlali "bir şey kayboldu" demektir ve
kabul edilemez; bir D bulgusu "bir şey kötüleşti" demektir ve sayılır, raporlanır, mümkünse
düzeltilir. Kitap koşusunun son tablosu (220 sayfa, 4.491 çevrilebilir blok):
**L1=1, L2=2, L3=0, L4=0, L5=0, L6=4, L7=1, L8=1, L9=0, L10=0, D1=801, D2=163, D3=0.**
L1'in tek vakası bilinçli (kitabın sonundaki kaynakça sayfası çıktıya alınmadı), L2'nin ikisi
kaynakça satırı, D1'in 801'i ise uzun çevirilerin küçültülmesi — hepsi gerekçeli.

## 3.2 Denetim araçları

`tools/audit/` altında 56 araç var; en sık kullanılanlar:

- `lossless_audit.py` — bir koşu dizinini tarar, L1–L10 + D1–D3 tablosunu üretir (`audit.json`).
- `type_drift.py` — yazılan sayfanın **tipografisi** ile okuyucunun kaydettiği stili karşılaştırır:
  büyümüş bloklar (başlık irileşti mi), küçülmüş bloklar (sığdırma merdiveni), hizası değişmiş
  bloklar, okunamaz boyuta inmiş bloklar.
- `text_over_image.py` — yalnız L10'u derinleştirir (bkz. 3.3, ilk yanlış ölçüm).
- `side_by_side.py` — dört panelli görsel karşılaştırma üretir (orijinal | eski | yeni | model).
- `comparison_site.py` — tüm koşuları tek bir kaydırıcılı siteye döker (yayınlanan site budur).
- `translate_book.py` / `translate_epub.py` — parça parça, çok işçili canlı koşu sürücüleri.
- `rewrite_run.py`, `repair_book.py` — mevcut çıktıyı yeni motorla yeniden yaz / onar.
- `live_check.py`, `format_matrix.py`, `translation_completeness.py` — biçim çiftleri ve dil
  tamlığı ölçümleri.

Araçların ortak kuralı: **çıktı makine okunur** (JSON) ve **iddia taşımaz**, sayı taşır.

## 3.3 Ölçümün kendisi üç kez yanıldı

### Vaka A: L10 yanlış pozitifleri — sayıların yarısı ölçüm hatasıydı

L10 "metin bir figürün üstüne çizilmiş" demek. İlk uygulama, kelime kutusu görsel kutusuyla
kesişiyorsa kayıp sayıyordu. Sonuçlar şöyleydi: cookbook **182**, mushrooms **124**, kitap **6**,
arXiv **25** — yani "her belgede figür üstü yazı var" gibi görünüyordu.

Tek tek bakıldığında iki hata ortaya çıktı:

1. **Tam sayfa / döşemeli tarama görselleri.** Taranmış bir belgede sayfanın tamamı bir görüntüdür;
   üstündeki her kelime "figür üstü" sayılıyordu. Kural düzeltildi: görsel alanların **birleşimi**
   sayfanın tamamına yakınsa (≥%100) L10 uygulanmaz.
2. **Kaynağın kendi grafik etiketleri.** arXiv makalesinde grafiğin içindeki eksen etiketleri
   kaynakta zaten vardı; çeviri onları koruyordu ama "kayıp" sayılıyordu. Kural düzeltildi: bir
   kelime **kaynağın da yazdığı** bir kelimeyse L10 sayılmaz.

Düzeltilmiş ölçüm: cookbook 182→**0**, mushrooms 124→**0**, kitap 6→**0**, arXiv 25→**0**
(hepsi yanlış pozitif). Wikipedia koşularında ise 13/13 **gerçekti** — ve yeniden çevirimle
**0**'a indi. Yani düzeltme hem yanlış pozitifleri eledi hem gerçek vakayı yakalamaya devam etti.
Aynı kural çekirdeğe de taşındı (`verify.words_over_figures`); NIST dergisinde L10 8→0 oldu.

### Vaka B: "bariz daha büyük font" — ölçüm hatası, kod hatası değil

Kullanıcı "bazı örneklerde bariz daha büyük font" bildirdi. İlk ölçüm şöyle yapılmıştı: yazılan
satır, **en yakın yükseklikteki** kaynak satırla eşleştiriliyordu. Bir formda her etiket kendi
değeriyle aynı yükseklik bandındadır — 10 puntoluk etiket 12 puntoluk komşusuyla "karşılaştırıldı"
ve doğru bir sayfa şişmiş göründü. Ölçüm, okuyucunun **o blok için kaydettiği** stille, geometriyle
eşleştirilerek yeniden yazıldı (`type_drift.py`); sonuç: **büyüyen blok yok.** Sorun kodda değil,
ölçümdeydi — ve bu ancak ölçüm aracı denetlenerek anlaşıldı.

### Vaka C: hizalama bayrakları — sütun sınırından okumak

`type_drift` bir süre arXiv'da 4 blok için "hizası değişmiş" dedi. Blok blok bakıldığında kaynak
**iki yana yaslı** (her satır 72→540, son satır kısa), çıktı ise sola yaslı ve sağ kenarı tırtıklı
çıkıyordu — yani gerçek bir kayıp vardı ama **sebebi beklenen yerde değildi**: yazıcı `text-align:
justify`'ı zaten destekliyordu (bloklar HTML kutusuyla çiziliyor), eksik olan **okuyucunun hiç
"justify" üretmemesiydi** (yalnız left/right/center üretiyordu).

Düzeltme iki ayırt edici kural gerektirdi: sol kenarlar düz **ve** son satır kısa **ve** son satırın
**sol kenarı** gövdeyle aynı. Üçüncüsü olmadan ortalanmış bir başlık da "justify" okunuyordu (onun
satırları da kısalır, ama son satır ortadan başlar) — NASA kapak başlığı tam olarak bu yüzden
merkezden kayıyordu, ve test yakaladı. Aynı oturumda eklenen girinti kuralı da fazla genişti:
ortalanmış bir bloğun ilk satırı (en uzun satır) solda başlar, "girinti" sanılmamalıydı.

**Sonuç:** 19 hizalama testi + 218 okuyucu/layout testi yeşil; iki eski test yeni sözleşmeye
çevrildi, dört yeni test eklendi (tırtıklı flush-left "left" kalır, ortalanmış kısalma justify
sayılmaz, sağa yaslı iki satır sağ kalır). **Aynı gün gerçek koşuda:** kitabın yeniden çevrilen
parçalarında 70 uzun gövde bloğunun 26'sı "justify" okundu ve `type_drift` hizalama bayrağı 0
çıktı — düzeltme ölçümden çizilmiş sayfaya kadar doğrulandı.

### Üçüncü vaka: sonda, geçişin sormadığı soruyu yanıtladı (2026-09-20)

Kitapta en büyük inceleme bayrağı sınıfı "çeviri kutuya sığmadı" (42 parçada 6.014 bloğun 1.130'u).
Merdivene bir **satır aralığı adımı** eklendi: kutu okunabilirlik tabanında bile sığmıyorsa, modele
sormadan önce satırları sıkılaştır. Adım çalışıyordu — sentetik bir kutuda testleri geçti.

Ölçüm iki kez yapıldı ve **ikisi farklı cevap verdi**:

- *Sonda* (kayıtlı koşunun çevirileri üzerinde ölçüm): 158 taşan bloğun **20'si** kurtuluyor.
- *Enstrümanlı geçiş* (fonksiyon sarmalanıp sayıldı): 6 parçada adım **14 kez çağrıldı, 0 kez
  sığdırdı**.
- *Yazılmış sayfa A/B'si* (20 parça, iki kol): **birebir aynı** — D1=627, D3=0, tüm L aynı.

Fark tek bir satırdı: sonda `block.dominant_style()` ile ölçüyordu, geçiş ise
`_as_drawn(...)` ile — hedef dilin **ikame fontu** çözülmüş stil. İki fontun metrikleri farklı ve
sonda, motorun hiç sormadığı bir soruyu yanıtlıyordu.

**Sonuç:** adım geri alındı (dal birleştirilmedi, girişim `bbf5958` olarak jurnalde duruyor).
Ölçüm göstermiyorsa değişiklik geri alınır kuralı burada bir *sondayı* değil, bir *fikri*
kurtardı. İki enstrüman (`fit_probe.py`, `fit_ab.py`) kaldı; ikisi de model harcamıyor.

**Sıradaki kol da bu ölçümden çıktı:** kurtulmayan 138 bloğun derdi satır değil **kutu** —
`room_below` bir bloğun ölçülen kutusunu sonraki bloğa değmemek için 6pt'ye eziyor ve 6pt'ye
hiçbir şey sığmaz. Yani asıl iş örtüşme/yer açma (yol haritası 4), merdiven değil.

## 3.4 Ölçüm altyapısının kuralları

Bu üç vakadan çıkan ve artık yazılı olan kurallar:

1. **Ölçüm aracının kendisi test edilir.** `text_over_image.py`'nin düzeltmesi, eski koşular
   üzerinde yeniden koşularak doğrulandı: gerçek vakayı (wikipedia 13/13) yakalamaya devam etti,
   yanlış pozitifleri (cookbook, mushrooms, kitap, arXiv) eledi.
2. **Ölçüm, kaynağın kendi verisiyle çapraz kontrol edilir.** "Kayıp" denen bir şey kaynağın da
   yazdığı bir şeyse kayıp değildir (arXiv grafik etiketleri).
3. **Yanlış çıkan bir sayı, düzeltilmiş sayıyla birlikte yazılır.** Bu depoda "182 → 0" gibi
   ifadeler bilinçli: eski sayının yanlış olduğunu gizlemek, yeni sayıya duyulan güveni de
   götürürdü.
4. **Sonda ile boru hattı anlaşmazsa, boru hattı enstrümanlanır.** Bir değişikliği ölçen sonda
   motorun kullandığı girdileri kullanmalı (stil dahil: geçiş `_as_drawn` ile ölçer, blok stiliyle
   değil). Anlaşmazlıkta doğru hamle, test edilen fonksiyonu sarmalayıp saymaktır — sondayı
   düzeltmek değil.
5. **Varsayılan, kanıtlanmış kayıp varsa kapalıdır.** `reflow` modu NIST'te D1'i 52→0 yaptı ama
   IRS'te L7'yi 0→1 yaptı; kazanç belgeye bağlı, kayıp kayıpsızlık ihlali — o yüzden mod var,
   varsayılan değil.
