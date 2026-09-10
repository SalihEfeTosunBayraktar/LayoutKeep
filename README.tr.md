<p align="center">
  <img src="docs/images/banner_tr.png" alt="LayoutKeep — düzen koruyan belge çevirmeni" width="820">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.tr.md">Türkçe</a>
</p>

# LayoutKeep

Belgeleri, e-kitapları ve görselleri **düzenini koruyarak** çevirir — yazı tipleri, renkler,
biçimlendirme, metin yönü ve yapı, hedef dilin izin verdiği ölçüde özgün haline yakın kalır.

Yerel çalışır. Modelini kendin getirirsin: LM Studio, Ollama veya llama.cpp üzerinden yerel bir
LLM, ya da OpenAI-uyumlu herhangi bir bulut uç noktası. Belgelerinin makineden çıkması gerekmez.

> **Durum: çalışıyor, etkin geliştirme altında.** Masaüstü uygulaması, komut satırı arayüzü ve
> PDF, EPUB, DOCX, HTML ile görseller için okuyucu/yazıcılar bugün çalışıyor. Pürüzler duruyor —
> [Bilinen sınırlar](#bilinen-sınırlar).

---

## Bu iş neden zor, ve bu proje tam olarak ne vadediyor

Tam otomatik, düzeni koruyan çeviri diye bir şey yok — ne burada ne de herhangi bir ticari üründe.
Üç şey size karşı çalışır:

- **Metin uzunluğunu korumaz.** İngilizce→Türkçe **ortalama 0,93x** ölçülüyor ama segmentler
  arasında **0,64x ile 1,40x** arasında geziniyor; yani bazı satırlar kısalır, bazıları geldiği
  kutuyu taşırır. Sorun ortalama değil, sapma.
- **Yazı tipleri altkümelenir.** Bir PDF genellikle yalnızca kullandığı glifleri gömer; Türkçenin
  `ğ ş İ ı` harfleri ya da Almancanın `ß`'si özgün yazı tipinde fiziksel olarak yoktur.
- **Okuma sırası, saklama sırası değildir.** İki kolonlu bir sayfa size cümleleri iç içe geçmiş
  halde verir.

Bu yüzden LayoutKeep kusursuz, tek tıkla bir sonuç vadetmiyor. **İyi bir ilk geçiş**, dürüst bir
gözden geçirme sinyali (motorun emin olmadığı segmentler gerekçesiyle işaretlenir) ve hemen
açabileceğiniz, formatı korunmuş bir çıktı vadediyor. Çeviri diske yazılır ve tamamlanma ekranı
onu açmayı önerir; ayrı bir elle düzeltme editörü yoktur.

Bu dosyadaki her ölçülmüş sayı yeniden üretilebilir; komutlar
[`docs/MEASUREMENTS.md`](docs/MEASUREMENTS.md) içinde.

## Nasıl görünüyor

Aşağıdaki sayfa DeepL üzerinden İngilizce→Türkçe çevrildi. İki görüntü de aynı dosyanın ilk
sayfası, aynı ölçekte: iki kolon, sayfa üstü ve altı, şekil ve altyazısı, tablodaki sayılar,
kalın ve italik parçalar — hepsi bulundukları yerde. Kaynak belge ve çevrilmiş çıktı
[`docs/samples/`](docs/samples/) altında; iki görüntü de
[`tools/make_comparison_image.py`](tools/make_comparison_image.py) ile yeniden üretilir.

![Kaynak ve çeviri yan yana](docs/images/comparison_tr.png)

| İş kurulumu | Çalışırken | Sağlayıcı uç noktaları |
|---|---|---|
| ![Kurulum ekranı](docs/screenshots/01_setup_light.png) | ![İlerleme ekranı](docs/screenshots/02_progress_light.png) | ![Sağlayıcı ayarları](docs/screenshots/06_provider_settings_light.png) |

Arayüz varsayılan olarak İngilizcedir; Türkçe ve Almanca da gelir, seçim başlıktadır ve
hatırlanır. Her ekranın koyu bir varyantı var — görüntüler
[`docs/screenshots/`](docs/screenshots/) altında.

## Ne çalışıyor

| Girdi | Çıktı | Sadakat |
|---|---|---|
| Dijital PDF (metin katmanlı) | PDF, EPUB, DOCX, HTML, PNG/JPG | yüksek — özgün PDF yerinde düzenlenir, şekiller ve vektör çizimler dokunulmaz |
| EPUB | EPUB, PDF, DOCX, HTML, PNG/JPG | EPUB→EPUB'da yüksek (düzen CSS'te yaşar); PDF yeniden akıtır, sınırlara bakın |
| DOCX | yukarıdakilerin tümü | iyi |
| Görseller (PNG/JPG) | görsel, PDF ve diğerleri | orta — OCR'a bağlı |

Latin yazılar (Türkçe, İngilizce, Almanca, Fransızca, İspanyolca, …). Veri modeli bir `direction`
alanı taşır, yani sağdan-sola desteği baştan yazmadan eklenebilir; ama uygulanmış değil.

**Gerçek belgeler bunları yaptığı için ayrıca ele alınanlar:** her açıda döndürülmüş metin, aynalı
metin (sessizce düzeltilmek yerine tespit edilip işaretlenir), çeviri boyunca satır-içi işaretlerle
taşınan kalın/italik parçalar, ve özgün yazı tipi hedef dili çizemediğinde metrik-uyumlu yazı tipi
ikamesi.

## Çevrilmemesi gereken değerler

Tork değerleri, toleranslar, parça numaraları, form kimlikleri ve şema etiketleri model onları
görmeden önce simgelerle değiştirilir ve sonrasında kaynaktan geri yazılır — bir model, istemine
hiç girmemiş bir şeyi başka sözcüklerle anlatamaz. IRS W-4 formunda ölçüldü: 162 değer geri
tutuldu, 116 segmentin 35'i hiç istek gönderilmeden yanıtlandı ve denetlenen her değer çıktıda
kaynaktakiyle tam olarak aynı sayıda görünüyor.

## Kurulum (geliştirme)

**Python 3.13** gerekir (3.11–3.13 destekli; 3.14 OCR bağımlılıklarını kırar).

```bash
git clone <repo-url> && cd LayoutKeep
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[pdf,epub,docx,ui,dev]"
```

Çekirdek paketin (`layoutkeep`) tasarım gereği **zorunlu üçüncü-parti bağımlılığı yoktur** —
okuyucu/yazıcı katmanları isteğe bağlı ekstralardır, böylece yalnızca DocIR çekirdeğine ve sahte
sağlayıcıya ihtiyacı olan bir CI işi standart kütüphaneyle kalır. Yalnızca gerçekten dokunduğunuz
formatların ekstralarını kurun:

| Ekstra | Ne getirir | Ne için gerekir |
|---|---|---|
| `pdf` | `pymupdf` | PDF okuma/yazma, EPUB→PDF akıtma, görsel render |
| `epub` | `ebooklib`, `lxml` | EPUB okuma/yazma |
| `docx` | `lxml` | DOCX okuma/yazma (zipfile + lxml, python-docx yok) |
| `fitting` | `fonttools` | Sığdırma motoru için glif kapsamı + gerçek yazı tipi metrikleri |
| `ocr` | RapidOCR / ONNX runtime | Taranmış belge ve görsel çevirisi |
| `ui` | `PySide6` | Masaüstü uygulaması |
| `dev` | `pytest`, `ruff` | Testler ve linting |

Hepsi birden: `.[pdf,epub,docx,ocr,ui,dev]`.

## Kullanım

### Masaüstü uygulaması

```bash
.venv/Scripts/python -m layoutkeep.ui.app
```

Dosyayı bırak, dilleri ve sağlayıcıyı seç, başlat. Sağlayıcı uç noktaları ayar penceresinde
yönetilir: sürükleyerek sıralanır, birini diğerinin üstüne bırakınca grup olur, sağ tıkla silinir
ve **Test Et** kaydetmeden dener.

### Komut satırı

Bir belgeyi çevirmeden okuyucunun onu nasıl anladığını görmek için:

```bash
layoutkeep inspect book.epub --sample 5
```

Yerel bir LM Studio veya Ollama sunucusu üzerinden çeviri:

```bash
layoutkeep translate book.epub --to tr --base-url http://localhost:1234/v1 --model your-model
```

DeepL üzerinden — bu bir model değil, çeviri servisidir. Seçilecek model yoktur; anahtar hangi
sunucuya gidileceğini belirler ve ücretsiz anahtarlar `:fx` ile biter. Yerel yolun tersine bu,
metni DeepL sunucularına gönderir:

```bash
layoutkeep translate book.epub --to tr --provider deepl --api-key YOUR-KEY:fx
```

`--limit 20` yalnızca ilk 20 segmenti çevirir; bütün bir kitaba girişmeden kaliteyi sınamanın ucuz
yolu budur. `--save-project out.lkproj` yeniden kullanılabilir bir proje dosyası yazar (segmentler,
düzen, bayraklar).

## Gözden geçirme bayrakları

Motorun emin olmadığı her şey segmentin üzerinde bir gerekçeyle işaretlenir; sinyal bir çıplak
boolean değil, okunabilir bir cümledir:

```
model metni çevirmeden aynen geri verdi
3 korunan değer çeviride yok
kalın/italik biçimlendirme kayboldu
çeviri kutuya sığmadı, küçültme yetmedi
```

Bayraklar `.lkproj` dosyasına yazılır ve komut satırı skor tablosunda sayılır.

## Bilinen sınırlar

İngilizce README'deki [Known limits](README.md#known-limits) bölümü bu listenin kaynağıdır ve
ölçümlerle birlikte orada tutulur — iki dilde iki ayrı doğruluk iddiası yerine tek bir yer.

Sürüm 1 için açık kalan bilinen kusurlar
[`docs/RELEASE-V1.md`](docs/RELEASE-V1.md) içinde, kanıtlarıyla listelenir.

## Mimari

```
readers/ ──▶ DocIR ──▶ providers/ ──▶ fitting/ ──▶ writers/
```

Her okuyucu DocIR üretir, her yazıcı DocIR tüketir; çeviri katmanı hangi formattan geldiğini
bilmez. Sözleşme [`docs/CONTRACT.md`](docs/CONTRACT.md) içinde.

## Lisans

AGPL-3.0. Bkz. [LICENSE](LICENSE).

## Hukuki not

Bu araç, çevirme hakkına sahip olduğunuz belgeler için bir çeviri aracıdır. Telif hakkıyla
korunan eserlerin çevirisi ve dağıtımı, hak sahibinin iznini gerektirir.
