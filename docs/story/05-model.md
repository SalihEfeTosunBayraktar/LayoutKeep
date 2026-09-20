# 5. Model seçimi: hangi model, neden — ve IBM Docling meselesi

Bu bölümde iki ayrı model kararı var ve ikisi sık karıştırılıyor:

- **Çeviriyi yapan model** (LLM): yerel `google/gemma-4-e4b`, LM Studio üzerinden.
- **Sayfanın düzenini bulan model**: IBM Docling'in **Heron** düzen dedektörü (ONNX).
- Ayrıca **üçüncü bir hat**: projeye özel ince ayar (Qwen2.5-7B QLoRA), ayrı bir çalışma.

"Neden IBM modeline geçtik" sorusunun cevabı üçüncü değil **ikinci** satırdır: çeviriyi IBM modeli
yapmıyor; IBM'in modeli *sayfayı anlıyor*. Aşağıda her kararın gerekçesi ve ölçümü var.

## 5.1 Çeviri modeli: neden yerel

Projenin varsayılanı **yerel** çalışmaktır ve bu bir tercih değil, tasarım eksenidir:

| | Yerel (LM Studio) | Bulut (OpenAI uyumlu, DeepL) |
|---|---|---|
| Belge makineden çıkar mı | **hayır** | evet |
| Ücret | yok | genelde var |
| Hız | GPU'ya bağlı | ağ + sağlayıcı |
| Kalite | modele bağlı (küçük modellerde daha zayıf) | genelde daha güçlü |
| Paralellik | sunucunun yuva sayısı | sağlayıcı sınırı |

Bulut **desteklenir** (sağlayıcı ayarlarından uç nokta eklenir, "Test Et" ile anahtar
kaydedilmeden denenir) — ama varsayılan değildir. Sebep basit: bu proje bir *belge* aracıdır ve
kullanıcının belgesi (telifli kitap, kişisel tarama, kurumsal form) çoğu zaman makineden
çıkmamalıdır. Yerel-önce olmak, "kayıpsız" iddiasının yanında duran ikinci bir sözdür.

Yerel tarafta **tek model kuralı** vardır: makinede tek bir model yüklenir ve istekler sırayla
gider (paralel yuvalar hariç). Bu, GPU belleği paylaşıldığında model değiştirmenin getirdiği
yükleme cezasını ve kararsızlığı önler. Ölçülen sonuç: 220 sayfalık kitap, 55 parça, ~106 dakika.

## 5.2 Kalite tavanı ve boru hattının cevabı

Küçük bir yerel modelin dil becerisi sınırlıdır. Projenin cevabı "daha iyi model bulmak" değil,
**modelin üstüne değil altına mekanizma koymak** oldu:

- **Korunan değerler** (sayılar, ölçüler, DOI/URL, parça numaraları, Romen rakamları) modele hiç
  gösterilmez — model yanlış yapsa bile kaybolmazlar.
- **Sözlük** terimleri zorlar (istemde + çıktı denetiminde): model "hypothesis"ı bir yerde
  "hipotez", başka yerde "varsayım" yapamaz.
- **Bellek** aynı metne aynı çeviriyi verir (koşular arası, SQLite).
- **Tekrarları birleştir** aynı kaynağın farklı çevirilerini çoğunluğa hizalar.
- **Doğrulayıcı** kaybı bulur, yeniden sorar, kalanı gerekçesiyle işaretler.

Bu yaklaşımın ölçülmüş karşılığı: modelin zayıflığı *metnin akıcılığında* kalır, *belgenin
bütünlüğünde* değil.

## 5.3 IBM Docling (Heron) düzen dedektörü — asıl "IBM modeli"

### Neden gerekliydi

Okuma hattının klasik yöntemi **XY-cut**: sayfayı yatay/dikey boşluk çizgilerinden keserek bloklar
bulur. Hizalanmış, temiz sayfalarda iyi çalışır; karmaşık sayfalarda çöker:

- kutu içinde kutu (form alanları), resim altı yazılar (figure caption), iki sütun arasına sıkışmış
  formüller, sayfa kenarına taşan dipnotlar;
- taranmış sayfalar (çizgi yok, yalnız pikseller).

Bu durumlarda yanlış okunan şey *metin* değil, **bölge sınırıdır**: bir başlık paragrafın içine
karışır, bir dipnot gövdeye girer, bir tablo satırı ayrı blok olur. Sonuç: çeviri doğru ama
yerleşim yanlış — yani kullanıcının şikâyet ettiği şey.

### Ne yapıldı

IBM Research'ün geliştirdiği **Docling** projesinin düzen modeli (`docling-layout-heron-onnx`)
eklendi. Model sayfayı görüntü olarak görür ve bölgeleri sınıflandırır: başlık, paragraf, tablo,
şekil, liste, dipnot. ONNX olarak **yerelde** koşar (CPU'da bile), yani yerel-önce ilkesini bozmaz.

- Komut satırında `--layout-detector` ile açılır; arayüzde varsayılan açıktır.
- Yalnız gerekli yerde çalışır: sayfa metin katmanıyla okunabiliyorsa ve yapı basitse XY-cut
  yeterlidir; model taranmış/karmaşık sayfalarda devreye girer.

### Ölçüm: gerçekten ne değişti

10 kitap sayfası üzerinde **dört panelli** karşılaştırma üretildi: `orijinal | eski koşu |
XY-cut | dedektörlü`. Ölçülen metrik: "çıktıda hâlâ İngilizce kalan düzyazı" ve "sayfadan taşan
kelime".

| | İngilizce kalan düzyazı | Sayfadan taşan kelime |
|---|---|---|
| Eski koşu (524 sayfa, model yok) | 6/82 (%7) | 0 |
| XY-cut | 6/82 (%7) | 0 |
| **Dedektörlü** | **1/82 (%1)** | 0 |

Ayrıca modelin **yalnız başına** ne yaptığı da kaydedildi (`tests/layout_eval/2026-09-16_heron_pure/`):
her bölge, modelin döndürdüğü hâliyle çizildi — XY-cut yok, paragraf kuralı yok, sıralama yok. Bu
"temiz taban", sonradan eklenen her kuralın **ölçülmüş** bir tabana göre eklenmesini sağladı;
"model şunu da bulur herhalde" diye varsayım yapılmadı.

### V2 planı: neden yeniden yazmadık

Aynı dönemde bir **V2 planı** yazıldı: boru hattını Gemini ile baştan kurmak, düzen modelini
merkeze almak. Plan dokümanı `docs/YENI_MIMARI_VE_GECIS_PLANI.md` olarak duruyor. Plan
uygulanmadı, çünkü:

1. Yeniden yazım, kayıpsızlık denetimini (L1–L10) ve 1.000'den fazla testi geçersiz kılardı.
2. Çalışan motorda **tek bir eksik** vardı: karmaşık sayfalarda bölge bulma. Bunu çözmek için
   modeli *mevcut* okuyucuya eklemek yeterliydi — öyle de yapıldı.
3. V2 dalı (`v2-vision-layout`) çakışmasız birleşmiyordu (6 çakışma); zorla birleştirmek, ölçülmüş
   davranışları ölçülmemiş olanlarla değiştirmek olurdu.

Yani "IBM modeline geçiş" bir **yeniden yazım değil**, mevcut boru hattına eklenen bir **okuma
yeteneği** oldu. Planın işe yarayan parçası alındı, gerisi arşivde duruyor — ve bu karar da
yazılı: *kanıtsız düzeltme taşınmaz, kanıtsız yeniden yazım da taşınmaz.*

## 5.4 Üçüncü hat: projeye özel ince ayar (LayoutKeepLLM)

Ayrı bir çalışma kolu (kendi klasöründe), iki hedefi birlikte kovalıyor:

1. **Uygulamanın tel protokolüne uyum**: çok segmentli JSON yanıtı, `<0>…</0>` işaretleri,
   U+E000–U+E001 aralığındaki korunan değer token'ları, bağlam/uzunluk sınırları. Amaç, modelin
   "serbest metin" değil **protokol** üretmesi.
2. **Akademik düzeyde tutarlı EN↔TR çeviri** — yani yalnız doğru değil, terim tutarlılığı olan.

Tasarım kararları:

- Taban model **Qwen2.5-7B-Instruct**; eğitim **Kaggle'da QLoRA** (yerel GPU'da değil).
- Veri omurgası **elle yazılmış alan-uzmanı çiftler** (üretici: `01_Dataset/build_dataset.py`,
  korpus: `_dataset_corpus.py`); toplam ~6.000 kayıt.
- **OPUS-100 reddedildi**: EN-TR kısmı ölçüldü, haber ve günlük konuşma ağırlıklı — bu projenin
  çevirdiği şey akademik/teknik belge. "Bol veri" ile "doğru veri" aynı şey değil.
- Eğitim betiği **TRL'e bağımlı değil** (düz `transformers.Trainer` + `apply_chat_template`),
  çünkü TRL'in `SFTConfig` API'si sürümler arasında değişiyor ve notebook Kaggle'da kırılıyordu.

Bu hat, ürünün bugünkü sürümünde **kullanılmıyor**: çalışma zamanı modeli gemma. İnce ayar, kalite
tavanını yükseltmek için duran bir yol; ölçüm ölçütü aynı: L/D tablosu ve terim tutarlılığı.

## 5.5 Özet: hangi model neyi yapıyor

| Katman | Model/araç | Neden o |
|---|---|---|
| Sayfa düzeni (taranmış/karmaşık) | IBM Docling **Heron** ONNX | Bölge sınıflandırmasında XY-cut'ın çöktüğü yerde çalışır; yerel koşar; ölçülmüş kazanç 6/82 → 1/82 |
| Metin çıkarma (dijital) | PyMuPDF | Metin katmanı varsa en doğru kaynak; tipografi bilgisi taşır |
| OCR (taranmış) | RapidOCR (PP-OCR modelleri) | Güven skoru verir; düşük güven işaretlenir |
| Çeviri | `google/gemma-4-e4b` (LM Studio) | Yerel, ücretsiz, yuvalara paralel; belge makineden çıkmaz |
| Bulut çeviri (isteğe bağlı) | OpenAI uyumlu uç noktalar, DeepL | Güçlü modeller; kullanıcı açıkça seçerse |
| Kalite garantisi | `verify.py` + sözlük + bellek | Modelin zayıflığını belge bütünlüğüne taşımaz |
