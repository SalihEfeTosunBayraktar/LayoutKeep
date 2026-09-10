# Sürüm 1 — doğrulananlar ve açık kusurlar

> Bu dosya bir iddia listesi değil, **koşturulmuş** kontrollerin kaydıdır. Her satır ya bir
> ölçümle ya da yeniden üretilebilir bir komutla desteklenir. Okuyucu/yazıcı katmanındaki derin
> denetim ayrı tutulur: [AUDIT-BULGULAR.md](AUDIT-BULGULAR.md).

## Yayın öncesi doğrulanan

| Konu | Nasıl doğrulandı | Sonuç |
|---|---|---|
| Gerçek DeepL çevirisi, uçtan uca | `docs/samples/sample_report.pdf` → `sample_report.tr.pdf`, 16 segment / 1331 karakter | çeviri tamamlandı, **0 segment işaretlendi** |
| Düzen korunumu | Aynı sayfanın kaynak/çıktı render'ı yan yana: `docs/images/comparison_en.png` | iki kolon, sayfa üstü/altı, şekil + altyazı, kalın/italik yerinde |
| Korunan değerler | Aynı çıktıda `12 Nm`, `±0,5 Nm`, `4.5 mm`, `0.42 mm` | hepsi kaynaktaki biçimiyle çıktıda |
| Arayüz dili | `UIStrings.get_language()` varsayılanı ve İngilizce sözlük kapsaması | varsayılan `en`, İngilizceden eksik anahtar **yok** |
| Pencere boyutları | `MainWindow` 900×660, sağlayıcı ayarları 600×560, ekranın kullanılabilir yüksekliği 816 | hepsi ekrana sığıyor; düğmeler görünür |
| Ayar yalıtımı | Tam süit öncesi/sonrası `HKCU\Software\LayoutKeep` karşılaştırması | kayıt defteri **değişmiyor** |
| Taşınabilir mod | `tests/test_ui_settings.py` | `portable.txt` yanındaki dizine yazıyor |
| Test süiti | `pytest -q` | 758+ test yeşil, `ruff` temiz |

## Yayın öncesi bulunup düzeltilenler

| Kusur | Nasıl bulundu | Durum |
|---|---|---|
| Sağlayıcı kutusuna tıklamak listeyi açmıyordu | kullanıcı bildirdi | düzeltildi — düzenlenebilir kutunun metin alanı tıklamayı yutuyordu; alan fareyi geçiriyor, kutu tıklamayı kendisi ele alıyor |
| Sürüklenen uç nokta gruba girince görünmez kalıyordu | kullanıcı bildirdi | düzeltildi — Qt sürüklediği satırı gizler ve taşımayı kendisi bitirdiğinde geri gösterir; gruplama bırakışı bunu yapmadığı için satır gizli kalıyordu |
| Sağ tık menüsü paketlenmiş uygulamada hiç açılmıyordu | **çökme kaydından**: `AttributeError: Slot 'ProviderSettingsDialog::' not found` | düzeltildi — `addAction(metin, çağrılabilir)` çağrısının kardeş aşırı yüklemesi (alıcı + slot adı) bağlı metotla seçiliyor; menü artık `QAction` nesnelerinden kuruluyor ve gösterilmeden sınanabiliyor |
| Test süiti %85'te erişim ihlaliyle ölüyordu | tam süit koşusu (`0xc0000374`, ardından erişim ihlali) | düzeltildi — tıklamayı yakalamak için kurduğum olay filtresi, onu kuran bileşen yok edildikten sonra kuyruktaki olaylarla tetikleniyordu |
| `QMenu` tema tablosunda yoktu | **tema kapsama testi**, ilk koşuşta | düzeltildi — kural eklendi; test bu sınıf hatayı bundan sonra yakalıyor |
| Eksik çeviri anahtarı Türkçeye düşüyordu | İngilizce sözlük kapsama kontrolü | düzeltildi — geri düşüş İngilizce |
| Dil isimleri her arayüzde Türkçeydi | İngilizce ekran görüntüsü | düzeltildi — isimler arayüz diline göre |

## Açık kusurlar

### V1 · Tablo hücreleri çeviride tek bloğa çöküyor · 🔴 Yüksek

- **Nerede:** PDF okuyucunun blok gruplaması (`src/layoutkeep/readers/pdf_reader.py`) — sahibi
  `lk-pdf`, bu yüzden burada yalnızca kanıtla bildiriliyor.
- **Ne oluyor:** aynı satırdaki tablo hücreleri (ayrı metin yerleştirmeleri) tek bir bloğa
  toplanıyor; çeviri de tek bir kutuya yazılıyor. Kaynak tabloda 5 satır × 3 kolon varken çıktıda
  ilk hücrede birleşmiş metin (`Plaka Döngüleri Defleksiyon A-1 10 0.42 mm …`) ve altında boş
  satırlar kalıyor.
- **Kanıt:** `docs/images/comparison_en.png` sağ yarısı, tablo bölgesi. Yeniden üretim:
  ```bash
  .venv/Scripts/python.exe tools/make_sample_document.py docs/samples/sample_report.pdf
  # (çeviri) ardından
  .venv/Scripts/python.exe tools/make_comparison_image.py docs/samples/sample_report.pdf \
      docs/samples/sample_report.tr.pdf docs/images/comparison_en.png
  ```
- **Neden önemli:** sayılar korunuyor (korumalı literal mekanizması çalışıyor), ama tablonun
  **yapısı** kayboluyor — projenin ana iddiası tam olarak bu.
- **Öneri:** bir satır içindeki span'ler arasındaki yatay boşluk bir eşiği geçtiğinde blok
  bölünmeli; kolon boşluğu ile kelime boşluğu farklı büyüklüklerdir.

### V2 · Hedef dil varsayılanı Türkçe · 🟡 Orta

- **Nerede:** `src/layoutkeep/ui/job_setup.py`, `target_lang` ayarının varsayılanı.
- **Ne oluyor:** arayüz İngilizce açılıyor ama hedef dil `tr` geliyor. Yazarın kendi kullanımı
  için doğru, uluslararası bir yayın için beklenmedik.
- **Karar gerekiyor:** varsayılanı sistem diline bağlamak mı, boş bırakıp seçim istemek mi.
  Kullanıcı kararı olduğu için değiştirilmedi.

### V3 · İkon-yalnız satır işaretleri keşfedilebilirliği düşürüyor · 🟡 Orta

- **Nerede:** kurulum ekranının ayarlar kartı.
- **Ne oluyor:** beş alan etiketi metin yerine SVG ikon; hepsinde tam metin tooltip var, ama
  uygulamayı ilk açan biri için küre (diller) ve sunucu (sağlayıcı) ikonları kendiliğinden
  anlaşılır değil.
- **Ölçülmedi:** bu bir kullanılabilirlik yargısı, bir hata değil. Şikayet gelirse en belirsiz iki
  satıra kısa metin geri konabilir.

## Yayın için açıkta kalanlar

- `LayoutKeepLLM/` (16 MB, içinde kaynağı belgelenmemiş 15,6 MB'lık bir eğitim veri kümesi)
  yayın öncesi **depodan çıkarıldı** — alt proje rafa kaldırıldı. Geçmişte duruyor: depo
  boyutunu gerçekten küçültmek için geçmiş temizliği (`git filter-repo`) gerekir, o da
  yeniden yazma olduğu için burada yapılmadı.
- Git geçmişi bu oturumda **yeniden yazılmadı**: aynı depoda başka ajanlar çalışıyor ve geçmişi
  yeniden yazmak onların dallarını kırar. Sürüm etiketi geçmişin üstüne konur.
