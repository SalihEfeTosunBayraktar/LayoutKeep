# LayoutKeep - Tasarım Kılavuzu ve Mockup Galerisi

Bu dizin, **LayoutKeep** uygulamasının kurumsal kimlik, logo ve masaüstü arayüz (UI/UX) mockup tasarımlarını içerir.

---

## 1. Tasarım Varlıkları Özeti

| Dosya Adı | Açıklama | Çözünürlük / Format |
|---|---|---|
| `03_app_ui_light_theme.jpg` | **Ana Kurulum Ekranı (Açık Tema):** Masaüstü uygulama ana kurulum ve dosya yükleme mockup'ı | 1792x1024 (16:9) |
| `06_logo_app_icon_transparent.png` | **Şeffaf Arka Planlı Büyük Boy Uygulama İkonu:** Arayüzün sol üstündeki mavi squircle ikonun 824x824 şeffaf PNG sürümü | 824x824 (PNG / Alpha) |
| `07_logo_glyph_white_transparent.png` | **Beyaz LK Monogram Glif:** Koyu zeminlerde, başlık çubuklarında ve filigranlarda kullanılabilir saf beyaz şeffaf glif | 468x489 (PNG / Alpha) |
| `08_logo_glyph_blue_transparent.png` | **Mavi LK Monogram Glif:** Açık zeminlerde ve dokümanlarda doğrudan kullanılabilir kurumsal mavi (`#2563eb`) şeffaf glif | 468x489 (PNG / Alpha) |
| `09_app_ui_progress_screen.jpg` | **Adım 2 İlerleme Ekranı (Koyu Tema):** Yeni LK logosu, %72 ilerleme çubuğu, anlık hız/ETA sayaçları ve canlı çift panel önizleme | 1792x1024 (16:9) |
| `10_app_ui_completion_screen.jpg` | **Adım 3 Tamamlandı Ekranı (Açık Tema):** Yeni LK logosu, başarı paneli, belge özet metrikleri ve eylem butonları | 1792x1024 (16:9) |
| `11_app_ui_layout_inspector.jpg` | **Düzen İnceleyici & Karşılaştırma Ekranı (Pro View):** Yeni LK logosu, yan yana orijinal ve çeviri belge düzen geometrisi denetimi | 1792x1024 (16:9) |
| `layoutkeep_logo.svg` | **Vektörel SVG Logo:** Her ölçekte kayıpsız vektörel logo (Qt / PySide6 ve web için doğrudan kullanılabilir) | Vektör SVG (512x512) |

---

## 2. Logo ve Marka Kimliği

### Tasarım Konsepti
- **Monogram & Sembolizm:** "L" ve "K" harflerinin kesişimi, orijinal belge katmanlarını (EPUB, PDF, DOCX) ve hizalama ızgaralarını simgeler.
- **Yapay Zeka Vurgusu:** Geometrik ızgara üzerindeki bağlantı noktaları ve devre düğümleri, yerel ve bulut tabanlı yapay zeka modelleriyle yapılan yüksek hassasiyetli düzen koruma sürecini temsil eder.
- **Renk Paleti:**
  - **Ana Mavi (Primary Blue):** `#2563eb` / `#1d4ed8` (Güvenilirlik, teknik hassasiyet)
  - **Elektrik Camgöbeği (Cyan / Accent):** `#38bdf8` / `#60a5fa` (Yapay zeka akışı ve modern teknoloji)
  - **Koyu Zemin (Dark Background):** `#0f172a` (Derin lacivert / Slate 900)
  - **Açık Zemin (Light Background):** `#f8fafc` (Temiz gri-beyaz / Slate 50)

---

## 3. Arayüz (UI) ve Menü Mimarisi

### Açık Tema (Light Theme)
- Arka plan: `#f8fafc`
- Kart yüzeyleri: `#ffffff`
- Kenarlıklar: 1px `#cbd5e1`
- Vurgu rengi: `#2563eb`
- Tipografi: Yüksek kontrastlı birincil metin (`#0f172a`), ikincil metin (`#334155`), silik etiketler (`#64748b`).

### Koyu Tema (Dark Theme)
- Arka plan: `#0f172a`
- Kart yüzeyleri: `#1e293b`
- Kenarlıklar: 1px `#334155`
- Vurgu rengi: `#3b82f6` (hafif parıltı efekti ile)
- Tipografi: Yüksek kontrastlı beyaz/açık gri (`#f8fafc`), ikincil (`#cbd5e1`), silik (`#94a3b8`).

### Menü ve Model Kataloğu Özellikleri
- **Akıllı Arama:** Model adı veya sağlayıcıya göre anlık filtreleme (`Llama`, `Qwen`, `Mistral`, `GPT-4o`, `Claude`, vb.).
- **Kategorik Gruplama:**
  - *Yerel Modeller:* LM Studio, Ollama (çevrimdışı, gizlilik odaklı, sıfır maliyet).
  - *Bulut Sağlayıcılar:* OpenAI, Anthropic, DeepSeek.
- **Görsel Rozetler (Badges):** "Yerel" (yeşil rozet) ve "Bulut" (mavi rozet) durum göstergeleri ile gecikme/token bilgileri.
- **Sağlayıcı Yapılandırması:** API uç noktası, API anahtarı, sıcaklık (temperature) kaydırıcısı ve yazı tipi eşleştirme anahtarı.

---

## 4. Arayüz SVG İkon Seti

Arayüz mockup'ındaki tüm kontrollerin vektörel SVG ikonları [`icons/`](icons/README.md) dizininde toplanmış ve `src/layoutkeep/ui/icons.py` modülüne kaydedilmiştir:
- `translate_ai.svg` - Kaynak dil seçimi (`文A`)
- `globe.svg` - Hedef dil seçimi
- `file_pdf.svg` - Çıktı formatı seçimi
- `chevron_down.svg` - Açılır menü okları
- `folder_select.svg` - Dosya seçimi
- `sparkles.svg` - Yapay zeka özellikleri
- `cpu_local.svg` - Yerel model sağlayıcıları
- `settings_sliders.svg` - Sağlayıcı ayarları
- `theme_toggle.svg` - Tema geçiş anahtarı
- `badge_check.svg` - Yerel model onay rozeti
- `play_start.svg` - Çeviriyi başlat butonu
- `layoutkeep_app_icon.svg` - Vektörel logo ikonu

