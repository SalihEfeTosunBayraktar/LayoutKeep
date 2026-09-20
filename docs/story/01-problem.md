# 1. Problem: "kayıpsız çeviri" tam olarak ne demek

Bu bölüm, projenin çözmeye çalıştığı problemi tanımlar, neden zor olduğunu ölçülerle anlatır ve
dışarıdaki çözümlerle karşılaştırır. Sonraki bölümler bu problem etrafında kurulan mimariyi,
ölçümleri ve hataları anlatır.

## 1.1 Tanım

Bir PDF'i çevirmek, metni başka bir dilde yeniden yazmak demek değildir — o kolaydır: belgeyi
okuyup metni çıkarır, modele verir, yeni bir belge üretirsiniz. Zor olan, **sayfanın kendisini
korumaktır**: aynı sayfa boyutu, aynı sütun düzeni, aynı kutuya aynı yerde oturan metin, aynı
başlık hiyerarşisi, aynı tablo ızgarası, aynı görseller, aynı dipnotlar. Okuyucu iki belgeyi yan
yana koyduğunda "aynı kitabın başka bir dildeki baskısı" görmeli, "yeniden dizilmiş bir özet"
değil.

Bu proje o hedefi şöyle tanımlıyor: **her çevrilebilir blok, kaynaktaki kutusunda, kaynağın
tipografisine yakın biçimde, kaynağın konumunu koruyarak çizilir; çevrilemeyen hiçbir şey sessizce
kaybolmaz — ya korunur ya işaretlenir.**

## 1.2 Neden zor: dört ölçülmüş gerçek

**1) Metin uzunluğu değişir, kutular değişmez.** İngilizce→Türkçe bu projede **0.93x** ölçüldü
(aynı segmentlerin karakter sayısı oranı) — yani çeviri ortalama olarak kaynaktan biraz kısa.
Ortalama yanıltıcı: bir başlık `Introduction` → `Giriş` diye yarıya inerken, bir cümle `state of
the art` → `son teknoloji ürünü` diye %60 büyüyebilir. Sabit bir kutuda büyüyen metin ya taşar ya
küçültülür; küçültmenin de bir okunabilirlik tabanı vardır (bu projede **0.85** — altına inen
bloklar D1 olarak işaretlenir).

**2) PDF yeniden akıtan bir biçim değildir.** PDF bir *baskı* biçimidir: her glifin yeri bellidir,
"paragraf" diye bir kavram dosyada yoktur. Çeviri metnini yazmak için önce sayfanın *yapısını*
geri kazanmak gerekir — hangi metin bir paragraf, hangisi başlık, hangisi tablo hücresi, hangisi
sayfa numarası. Bu geri kazanım (reading order, blok birleştirme, sütun ayrımı) projenin en çok
test edilen parçasıdır ve hataların çoğu burada çıkar.

**3) Kaynak belge türü kaliteyi doğrudan belirler.** Ölçtüğümüz farklar:

| Kaynak türü | Ne olur | Ölçüm |
|---|---|---|
| Dijital PDF (metin katmanı var) | En iyi durum; tipografi, font adı, punto, renk okunabilir | NIST dergisi: 4 parça, 114 blok, D1 **52** → reflow ile 0 |
| Taranmış PDF (görüntü) | OCR gerekir; harf hataları ve güven skoru devreye girer | NASA taraması: düşük güvenli blok "OCR güveni düşük (0.62)" ile **işaretlenir** |
| Karma (metin + görüntü) | Sayfa sayfa karar verilir; görsel üstü yazı tuzağı | Tarama sayfaları hariç tutulur (L10 kuralı, bkz. Bölüm 3) |
| EPUB | Düzen CSS'te; akışkan ama yine de korunabilir | Rich fixture'da %95+ sadakat |
| DOCX | OOXML doğrudan işlenir (`python-docx` bilinçli olarak kullanılmaz) | Kamu malı NIST DOCX test kaynağı eklendi |
| PNG/JPG | Yalnız OCR yolu; sayfa düzeni çizimden çıkarılır | Sayfa görüntüsü → PDF → aynı boru hattı |

**4) Modelin dil becerisi tavanı belirler.** Boru hattı ne kadar iyi olursa olsun, cümleyi kuran
modeldir. Yerel `google/gemma-4-e4b` (LM Studio) ile alınan sonuçlar, bulut modellerine göre
terim tutarlılığında zayıf; bu yüzden sözlük (terim zorlama) ve bellek (aynı metne aynı çeviri)
mekanizmaları modelin üstüne değil, *altına* konuldu: model yanlış yapsa bile terim ve tutarlılık
boru hattında garanti edilir.

## 1.3 Dışarıda ne var

BabelDOC'un kendi karşılaştırma tablosundan (arXiv 2605.10845, Tablo 1–2), mineru-translate'in
özellik listesinden ve ticari araçlardan (Doclingo, Lara Translate, Doctranslate, Bluente) derlenen
fark tablosu. "Bizde" kolonu bu depodaki kodla doğrulanmıştır.

| Özellik | Kimde var | Bizde |
|---|---|---|
| Çift dilli çıktı (kaynak+çeviri almaşık sayfalar) | BabelDOC, mineru-translate, Doclingo, Lara | sitede var, **PDF çıktısında yok** |
| Terim sözlüğü kısıtı | BabelDOC (`--glossary` CSV), DeepL, Lara | **var** (JSON veya CSV/TSV, istem + çıktı denetimi, uygulama içi düzenleyici) |
| Otomatik terim çıkarımı | BabelDOC | yok |
| Sayfa-ötesi bağlam | BabelDOC | kısmi (`context_before/after`) |
| Örtüşme çözümü kademesi (küçült → sıkıştır → aşağı it) | mineru-translate | kısmi (`--fit-mode reflow`, deneysel, varsayılan kapalı) |
| Koşular arası çeviri önbelleği | mineru-translate | **var** (SQLite bellek, 2.555 segmentlik gerçek koşuda doğrulandı) |
| Görsel/tablo içi metin çevirisi | BabelDOC | yok (bilinçli) |
| Editör / sonradan düzeltme | Doclingo, Lara | yok (inceleme kuyruğu var, düzenleme yok) |
| Eklenti ekosistemi (Zotero, Word) | BabelDOC/PDFMathTranslate | yok (bilinçli) |
| **Sayfa sayfa kayıpsızlık denetimi (L1–L10)** | **görünmüyor** | **var** — kaynağa karşı, her koşuda |
| İnceleme bayrağı + gerekçe | kısmi | **var** — 4.614 bayrağın gerekçesi yazılı (kitap koşusu) |
| Gerçek held-out örneklerden karşılaştırma sitesi | yok | **var** — 22 belge, kaydırıcılı, denetim sayılarıyla |
| Çalışma anında ayar (bağlam penceresi, eşikler) | kısmi | **var** — 30 ayar, hepsi koda bağlı (Bölüm 4, vaka 11) |

Kritik fark şu: dışarıdaki araçlar **çıktının iyi görünmesini** hedefler; bu proje **kaybı
saymayı** hedefler. İkincisi olmadan "kayıpsız" iddiası ölçülemez bir reklam cümlesidir.

## 1.4 Sözleşme: pazarlık konusu olmayan yedi karar

Projenin `docs/CONTRACT.md` dosyası, mimarinin tartışmaya kapalı yedi kuralını yazar. Bunlar
keyfi değil — her biri bir hatanın ardından yazıldı:

- **D1 — DocIR tek doğruluk kaynağıdır.** Biçimden bağımsız ara belge modeli; okuyucular onu
  üretir, yazıcılar onu tüketir. Çeviri katmanı PDF'i bilmez.
- **D2 — Çeviri katmanı düzenden habersizdir.** Sağlayıcı yalnız metin görür; kutu, punto, konum
  bilgisi oraya sızmaz. Bu, modeli değiştirmeyi ve sağlayıcıları paralel çalıştırmayı mümkün kılar.
- **D3 — Sığdırma ayrı bir aşamadır.** Çeviriden *sonra* çalışır; kutuya sığdırma kararları
  (küçült, kısaltma iste, aşağı it) çeviri kalitesini etkilemez.
- **D4 — Latin alfabesi, ama RTL'e hazır.** Sağdan sola yazı sistemleri *uygulanmadı*; şema
  `direction` alanını taşır.
- **D5 — Her şey sürdürülebilir olmalı.** Kesilen koşu kaldığı yerden devam eder; aralık
  uygulanırken belge *küçültülmez* (bu kural iki kez yanlış uygulandı, bkz. Bölüm 4, vaka 12).
- **D6 — Çeviri kalitesi segment bayraklarıyla izlenir.** Her blok ya çevrilmiştir ya da *neden*
  çevrilmediği yazılıdır.
- **D7 — Bir dönüşüm ancak ölçüldükten sonra sunulur.** Ölçülmemiş biçim çifti arayüzde kapalıdır.

## 1.5 "Kayıpsız"ın operasyonel tanımı

Sözü ölçülebilir hale getiren tanım `docs/campaign/JOURNAL.md`'nin başında yazılıdır ve üç
maddeden oluşur:

1. **Hiçbir çevrilebilir blok kaybolmaz.** Her blok çıktıda ya çevrilmiş ya da kaynaktaki hâliyle
   durur; ikisi de değilse L3/L4 ihlalidir.
2. **Hiçbir çevrilmemiş blok sessiz kalmaz.** Çevrilemeyen her blok bir *gerekçeyle* işaretlenir
   (L2, D1, D2, OCR güveni, korunan değer kaybı, biçim kaybı...).
3. **Kaynak ile çıktı sayfa sayfa karşılaştırılabilir.** L1–L10 kuralları bunu sayar; denetim
   çıktısı (`audit.json`) her koşunun yanında durur ve karşılaştırma sitesinde yayınlanır.

Bu tanımın pratik sonucu: projenin başarısı "güzel görünüyor" ile değil, **kalan bayrak sayısı**
ile ölçülür — ve o sayı her koşuda yazılır, kötü çıktığında da yazılır.
