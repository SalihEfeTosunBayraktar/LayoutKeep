# LayoutKeep - Arayüz SVG İkon Kütüphanesi

Bu dizin, `03_app_ui_light_theme.jpg`, `09_app_ui_progress_screen.jpg`, `10_app_ui_completion_screen.jpg` ve `11_app_ui_layout_inspector.jpg` mockup'larında ve masaüstü uygulamasında kullanılan tüm vektörel (SVG) ikon kaynaklarını içerir.

Tüm ikonlar **24x24** standart görünüm kutusunda (`viewBox="0 0 24 24"`), **2px çizgi kalınlığı** (`stroke-width="2"`), yuvarlatılmış uç ve köşe birleşimleri (`stroke-linecap="round"`, `stroke-linejoin="round"`) ile hazırlanmıştır.

---

## 1. Mockup 03 - Kurulum ve Belge Ayarları İkonları

| İkon Dosyası | Önizleme Adı | Kullanım Alanı (Arayüz Konumu) | `icons.py` Kodu |
|---|---|---|---|
| [`translate_ai.svg`](translate_ai.svg) | Kaynak Dil / Çeviri (`文A`) | Belge Ayarları > Kaynak Dil Seçim Kutusu (`Otomatik Algıla`) | `"translate"` |
| [`globe.svg`](globe.svg) | Dünya Küresi (`Globe`) | Belge Ayarları > Hedef Dil Seçim Kutusu (`Türkçe`) | `"globe"` |
| [`file_pdf.svg`](file_pdf.svg) | PDF / Belge Formatı | Belge Ayarları > Çıktı Formatı Seçim Kutusu (`PDF (.pdf)`) | `"file_pdf"` |
| [`chevron_down.svg`](chevron_down.svg) | Açılır Liste Oku | Dil, format ve profil açılır menüleri (`QComboBox`) | `"chevron_down"` |
| [`folder_select.svg`](folder_select.svg) | Klasör / Dosya Seç | Belge Bırakma Alanı > `Dosya Seç` butonu | `"folder"` |
| [`sparkles.svg`](sparkles.svg) | Yapay Zeka Işıltısı | AI Modeli Kart Başlığı ve akıllı çeviri özellikleri | `"sparkles"` |
| [`cpu_local.svg`](cpu_local.svg) | İşlemci / Donanım | Yerel LLM sağlayıcıları (`LM Studio`, `Ollama`) | `"cpu"` |
| [`settings_sliders.svg`](settings_sliders.svg) | Ayar Çubukları (`Tune`) | AI Modeli > `Sağlayıcı Ayarları` butonu | `"sliders"` |
| [`theme_toggle.svg`](theme_toggle.svg) | Güneş / Ay Çift Geçiş | Üst Çubuk (Header) > Açık/Koyu Tema Değiştirici | `"theme_sun"` / `"theme_moon"` |
| [`badge_check.svg`](badge_check.svg) | Onay / Durum Rozeti | Model Kartı > `Yerel` / Aktif model durumu | `"check"` |
| [`play_start.svg`](play_start.svg) | Başlat Üçgeni | Alt Eylem Butonu > `Çeviriyi Başlat` | `"play"` |
| [`layoutkeep_app_icon.svg`](layoutkeep_app_icon.svg) | Vektörel Logo | Sol üst köşe marka alanı ve pencere başlığı | Logo |

---

## 2. Mockup 09 - Çeviri İlerleme Ekranı İkonları

| İkon Dosyası | Önizleme Adı | Kullanım Alanı | `icons.py` Kodu |
|---|---|---|---|
| [`gauge_speed.svg`](gauge_speed.svg) | Hız Göstergesi | `Hız: 165 kar/sn` metrik kartı | `"gauge"` |
| [`hourglass_eta.svg`](hourglass_eta.svg) | Kum Saati / Geri Sayım | `Kalan Süre (ETA): 01:15` metrik kartı | `"hourglass"` |
| [`layers_segments.svg`](layers_segments.svg) | Katmanlar / Segmentler | `İşlenen Segment: 296 / 412` metrik kartı | `"layers"` |
| [`pause_control.svg`](pause_control.svg) | Duraklatma Çift Çizgi | Alt kontrol barı > `Duraklat` butonu | `"pause"` |
| [`cancel_control.svg`](cancel_control.svg) | İptal Çemberi | Alt kontrol barı > `İptal Et` butonu | `"close"` |

---

## 3. Mockup 10 - Tamamlandı Ekranı İkonları

| İkon Dosyası | Önizleme Adı | Kullanım Alanı | `icons.py` Kodu |
|---|---|---|---|
| [`success_badge.svg`](success_badge.svg) | Başarı Rozeti | `Çeviri Başarıyla Tamamlandı!` tepe rozeti | `"check"` |
| [`file_output.svg`](file_output.svg) | Çıktı Belgesi | `Çıktı Dosyası: AI_Research_Paper.out.pdf` kartı | `"document"` |
| [`external_open.svg`](external_open.svg) | Dışa Aç Bağlantısı | `Çıktı Dosyasını Aç` ana eylem butonu | `"external_link"` |
| [`refresh_restart.svg`](refresh_restart.svg) | Yenile / Döngü Oku | `Yeni Çeviri Başlat` ikincil butonu | `"refresh"` |

---

## 4. Mockup 11 - Düzen İnceleyici İkonları

| İkon Dosyası | Önizleme Adı | Kullanım Alanı | `icons.py` Kodu |
|---|---|---|---|
| [`split_view.svg`](split_view.svg) | Çift Bölmeli Görünüm | Orijinal ve çeviri sayfalarını yan yana görüntüleme | `"split"` |
| [`zoom_in.svg`](zoom_in.svg) | Yakınlaştır (`+`) | Belge yakınlaştırma araç çubuğu | `"zoom_in"` |
| [`zoom_out.svg`](zoom_out.svg) | Uzaklaştır (`-`) | Belge uzaklaştırma araç çubuğu | `"zoom_out"` |
| [`layout_grid_inspect.svg`](layout_grid_inspect.svg) | Düzen Izgarası | Düzen kutuları ve hizalama çizgisi katmanı | `"document"` |
| [`export_tray.svg`](export_tray.svg) | Dışa Aktar Tepsisi | Sağ üst araç çubuğu > `Export` butonu | `"export"` |

---

## 5. Python (PySide6) Kodundan Kullanım

```python
from layoutkeep.ui.icons import get_svg_icon

# İlerleme ekranı metrikleri:
speed_icon = get_svg_icon("gauge", color="#3b82f6", size=18)
eta_icon = get_svg_icon("hourglass", color="#3b82f6", size=18)
layers_icon = get_svg_icon("layers", color="#3b82f6", size=18)

# İnceleyici kontrolleri:
zoom_in = get_svg_icon("zoom_in", color="#cbd5e1", size=16)
zoom_out = get_svg_icon("zoom_out", color="#cbd5e1", size=16)
split_icon = get_svg_icon("split", color="#3b82f6", size=18)
export_icon = get_svg_icon("export", color="#ffffff", size=18)
```
