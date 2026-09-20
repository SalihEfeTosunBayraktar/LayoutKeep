# 2. Mimari: boru hattının her parçası

Bu bölüm, depodaki kodun nasıl bir araya geldiğini anlatır — hangi modül ne yapar, neden o sınırda
durur, ve o sınırı çizmek hangi hatayı önledi. Sayılar bu depodan (`wc -l`, 2026-09-20).

![LayoutKeep çeviri hattı](architecture.png)

## 2.1 Genel akış

```
oku → DocIR → segmentle → sağlayıcı zinciri → sığdır → yaz → doğrula → işaretle
```

Her aşama bir sonrakinin girdisini üretir ve **hiçbiri diğerinin işini yapmaz**. Bu ayrım teorik
değil: her sınır, bir hatanın düzeltilmesiyle çizildi. Örneğin "sığdırma çeviriden ayrı bir aşama
olmalı" (D3) kuralı, modelin "şu cümleyi kısalt" isteğine cevap verirken çeviri kalitesini
bozmasından sonra yazıldı — model artık kısaltma istemini yalnız *ikinci* turda ve yalnız
sığdırma aşamasında görür.

## 2.2 Modüller ve boyutları

| Modül | Satır | Sorumluluk | Sınır kuralı |
|---|---|---|---|
| `readers/` | 3.819 | PDF, EPUB, DOCX, görüntü okuyucuları | Çıktı yalnız DocIR'dır; okuyucu hiçbir şey yazmaz |
| `core/` | 2.519 | DocIR, koruma, sayı-sözcükleri, ayarlar, aralık | Biçim bilmez; yalnız veri |
| `providers/` | 2.718 | Sağlayıcı zinciri: dedupe, bellek, sözlük, koruma, parçalama, yeniden deneme | Düzeni bilmez (D2) |
| `fitting/` | 1.881 | Kutuya sığdırma, büyütme, figür çakışması, metin-üstü-görsel | Çeviri istemez; ölçer |
| `writers/` | 3.196 | PDF, DOCX, EPUB yazıcıları + dönüştürücüler | Karar vermez; çizer |
| `ocr/` | 726 | Taranmış sayfa okuma, düzen dedektörü (IBM Docling Heron) | Okuyucuya veri sağlar |
| `ui/` | 7.864 | PySide6 arayüzü, işçi, yüzen çubuk, karşılama, yardım, sözlük düzenleyici | Motoru çağırır, kopyalamaz |
| `verify.py` | 576 | L1–L10 ve D1–D3 denetimi + onarım | Hem CLI hem arayüz aynı dosyayı koşar |
| `cli.py` | 703 | Komut satırı | Aynı motor, farklı kapı |

Arayüzün motordan büyük olması tesadüf değil: kullanıcıya görünen her kolaylık (karşılama
ekranı, yardım, sözlük tablosu, yüzen çubuk, inceleme kuyruğu) burada yaşıyor. Motor ise küçük
tutuldu — çünkü motorun doğruluğu test edilebilirliğine bağlı.

## 2.3 DocIR: neden biçimden bağımsız ara model

`core/docir.py` şu zinciri taşır:

```
Document → Page → Block → Line → Span
```

- **Block** çevrilebilir bir birimdir: `text`, `bbox`, `role` (title/paragraph/table/caption/...),
  `align`, `direction`, `rotation`, `source_ref` (hangi sayfadan geldiği), `table_id/row/col`.
- **Line/Span** tipografiyi taşır: font ailesi, punto, kalın/italik, renk.
- **Segment** ise çeviri birimidir: `source` (korunan değerler maskelenmiş metin), `target`,
  `block_id`, bayraklar ve gerekçeler.

Neden ayrı bir model? Çünkü okuyucu ile yazıcı arasında **iki yönlü** bir dönüşüm var: PDF→DOCX,
DOCX→EPUB, EPUB→PDF hepsi aynı ara modelden geçer ve aynı denetimden geçer. Bu olmadan her biçim
çifti için ayrı bir boru hattı gerekirdi ve her birinin kendi hataları olurdu.

**Korunan değerler.** Çeviri öncesi sayılar, ölçüler, DOI/URL'ler, parça numaraları, tarihler ve
(ayarla açılıp kapanan) Romen rakamları **modele hiç gösterilmez**: metinden çıkarılıp yerine
U+E000–U+E001 aralığında görünmez yer tutucular konur, çeviri sonrası geri yerleştirilir. Böylece
modelin sayı uydurması ya da düşürmesi yapısal olarak imkânsız hale gelir. Kitap koşusunda bu
kural, "çeviride sayılar kayboldu" bayrağını 49 vakaya indirdi — kalanların çoğu tablo içi sayı
gruplarıdır.

## 2.4 Okuyucular

**PDF okuyucu** (`readers/pdf_reader.py`) iki yol kullanır: metin katmanı varsa oradan, yoksa OCR
ile. Sayfa sayfa karar verilir — bir kitabın 841 sayfasının 2'si taranmış olabilir (ölçüldü) ve
yalnız o 2 sayfa OCR'a girer. Reading order için XY-cut (yatay/dikey kesme) ile sütun ayrımı,
ardından satır birleştirme ve paragraf kuralları çalışır.

**Düzen dedektörü (IBM Docling Heron).** XY-cut, sayfa *çizgilerine* bakar: hizalanmış blokları
bulur. Karmaşık sayfalarda (kutu içinde kutu, resim altı yazı, iki sütun arasına sıkışmış formül)
yetersiz kalır. Bu yüzden `docling-project/docling-layout-heron-onnx` modeli eklendi: sayfayı
görüntü olarak görüp bölge bölge sınıflandırır (başlık, paragraf, tablo, şekil, dipnot). Model
`--layout-detector` ile açılır ve arayüzde varsayılan açıktır. Etkisi ölçüldü: 10 kitap sayfası
üzerinde dört panelli karşılaştırmada (orijinal | eski koşu | XY-cut | dedektörlü), dedektör
"hâlâ İngilizce kalan düzyazı" sayısını 6/82'den 1/82'ye indirdi.

**EPUB ve DOCX okuyucuları** kendi biçimlerinin yapısını doğrudan işler. DOCX'te `python-docx`
bilinçli olarak **kullanılmaz**: o kütüphane belgeyi yeniden serileştirir ve bu, korunması gereken
her şeyi (stil kimlikleri, ilişkiler, içerik denetimleri) yeniden yazar. OOXML doğrudan okunur.

## 2.5 Sağlayıcı zinciri

Sıra önemli — her halka bir üsttekinin işini boşa çıkarır:

```
koruma (mask)  →  dedupe (aynı metni bir kez çevir)  →  bellek (koşular arası)  →
sözlük (terim zorlama)  →  model çağrısı  →  parçalama (aynı metni geri verirse cümle cümle)  →
yeniden deneme (yanıtsız kalanı tekrar sor)  →  tekrarları birleştir (aynı kaynağa tek çeviri)
```

- **dedupe**: bir belgede aynı metin onlarca kez geçer (başlıklar, tablo etiketleri, form
  alanları). Aynı metin bir kez çevrilir; IRS formunda bu, istek sayısını belirgin biçimde düşürür.
- **bellek** (`providers/memory.py`): SQLite; koşular arası. Gerçek bir koşuda 2.555 segment
  birikti ve kullanıcı aynı kitabı yeniden başlattığında o segmentler modele hiç gitmez.
- **parçalama** (`providers/split.py`): model bazen paragrafı olduğu gibi geri verir. O zaman
  paragraf cümlelere bölünüp her cümle ayrı sorulur — sorun "modelin tembelliği" değil, uzun
  bağlamda dikkatin dağılmasıdır; cümle cümle sormak bunu aşar.
- **tekrarları birleştir** (`core/repeats.py`): aynı kaynak farklı yerlerde farklı çevrilmişse
  çoğunluk çevirisine hizalanır. Böylece "Chapter" bir yerde "Bölüm", başka yerde "Kısım" olmaz.

## 2.6 Sığdırma

Çeviri kutuya sığmazsa sırasıyla denenir: **küçült** (0.85 tabanına kadar) → **kısaltma iste**
(modelden daha kısa çeviri) → **aşağı it** (altında boşluk varsa bloğu büyüt) → **işaretle**.
`--fit-mode reflow` ek bir kademe ekler (satır aralığını sıkma + aşağı itme) ama varsayılan
**kapalı**: NIST dergisinde D1'i 52'den 0'a indirdi, ancak IRS formunda aşağı itilen bloklar
hareketsiz metne çarptı (L7 0→1). Yani kazanç belgeye bağlı, kayıp ise kayıpsızlık ihlali —
kural: *kanıtlanmış kayıp varsa varsayılan kapalı.*

## 2.7 Yazıcılar ve yazma kararı

PDF yazıcısı sayfayı **kaynak dosyadan** çizer: her blok kendi kutusunda redakte edilip yeniden
yazılır. Değişmeyen bloklara dokunulmaz (bir ad, bir belge kodu, bir üstbilgi olduğu gibi kalır —
silip yeniden çizmek tipografisini kaybettirir). Bloklar HTML kutusu + CSS ile çizilir; bu, hizalama
(ortala, sağa yasla, iki yana yasla) ve yazı tipi eşlemesi için tarayıcı motorunun işini kullanmak
demektir.

DOCX ve EPUB yazıcıları aynı DocIR'ı kendi biçimlerine döker. `writers/converter.py` biçim
çiftlerini yönetir ve D7 gereği **yalnız ölçülmüş** çiftleri sunar.

## 2.8 Denetleyici: projenin ayırt edici parçası

`verify.py` çıktıyı kaynakla karşılaştırır ve on kayıp türünü sayar (L1–L10), üç de kalite
eşiğini (D1–D3). Denetim **iki taraflıdır**: hem yazma öncesi DocIR üzerinde, hem yazılmış PDF'in
kendisi üzerinde çalışır. İkincisi kritik — çünkü hataların bir kısmı yalnız *çizimde* oluşur
(üst üste binen metin, sayfa dışına taşan kelime, figür üstüne düşen yazı).

Denetim yalnız rapor etmez: kaybı bulduğunda **yeniden sorar** (`ask_again`), düzeltilebileni
düzeltir, kalanı gerekçesiyle işaretler. Kullanıcı arayüzünde gördüğü "inceleme kuyruğu" bu
işaretlerdir — her satırın bir nedeni vardır ve o neden Türkçe yazılıdır.
