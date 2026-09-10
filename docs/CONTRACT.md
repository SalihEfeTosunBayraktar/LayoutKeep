# LayoutKeep — Ortak Sözleşme (tüm ajanlar için bağlayıcı)

Bu dosya, projede çalışan **her** ajanın (Claude alt ajanları ve Antigravity ajanları) uyması gereken
değişmezleri tanımlar. Kod yazmadan önce oku.

---

## 1. Proje kimliği

| | |
|---|---|
| Ad | LayoutKeep |
| Amaç | Belge/e-kitap/görselleri **düzen, font, renk, stil korunarak** çevirmek |
| Lisans | **AGPL-3.0-or-later** (açık kaynak, ticari kısıt yok) |
| Platform | Windows / macOS / Linux |
| Faz 1 kapsamı | **Sadece Latin yazı sistemi** (TR, EN, DE, FR, ES, IT, PT, NL, PL…) |
| UI | PySide6 |
| Python | **3.13 hedef** (3.14 wheel'leri güvenilmez — sistem 3.14 kullanma, venv aç) |

---

## 2. Mimari değişmezler — bunlar tartışmaya kapalı

### D1 — DocIR tek gerçek kaynaktır
Her okuyucu (`readers/`) girdiyi **DocIR**'e çevirir. Her yazıcı (`writers/`) **sadece** DocIR'den üretir.
Okuyucu ile yazıcı birbirini asla doğrudan tanımaz. Yeni format eklemek = 1 okuyucu + 1 yazıcı, çekirdek değişmez.

### D2 — Çeviri katmanı düzenden habersizdir
`providers/` sadece `list[Segment] -> list[Segment]` bilir. Font, bbox, PDF diye bir kavramı yoktur.
Bu sayede sağlayıcı değiştirmek tek satırlık iştir.

### D3 — Sığdırma, çeviriden sonra ayrı bir aşamadır
`fitting/` çeviri metnini alır ve kutuya sığdırır. Çeviri sağlayıcısı sığdırmayı düşünmez;
sadece `max_len` ipucu alır ve `fitting` gerekirse **yeniden çeviri** isteyebilir.

### D4 — Latin-only ama RTL'e hazır
`Span.direction` alanı **şimdi** var ve `"ltr"` sabitleniyor. Kod hiçbir yerde LTR varsayımını
gömmez (örn. "metin soldan başlar" gibi sabit mantık `direction`'a bakmalı).
RTL uygulanmaz ama mimari onu dışlamaz.

**Kapsam teyidi (kullanıcı, 2026-09-02):** Sadece Latin. RTL ve CJK **kapsam dışı** — sormaya
gerek yok, mimari hazır kalsın yeter.

**Ama yön ≠ oryantasyon.** Latin metin de eğik, dik, baş aşağı veya aynalanmış olabilir ve bunlar
gerçek belgelerde sık görülür. `Block.rotation` bunun için var. İki durumu karıştırma:
- **Döndürme** — yön vektöründen (`line["dir"]`) türetilir, açı olarak taşınır.
- **Aynalama** — dönüşüm matrisinin determinantı negatiftir. Yön vektörü bunu **gösteremez**;
  aynalanmış bir satır gayet normal bir açı bildirebilir ama ters render edilir. Sadece açıya
  bakarak geri yazmak metni sessizce düzeltir ve düzeni bozar.

Aynalamayı üretemiyorsak bile **tespit edip `needs_review` işaretlemek**, sessizce düzeltmekten
iyidir. Kullanıcıya yanlış bir belgeyi doğruymuş gibi vermek bu projede en kötü sonuçtur.

**Durum: tespit ediliyor.** Uzun süre "yön vektörü determinantı gösteremez, dolayısıyla aynalama
tespit edilemez" diye kayıtlıydı. İlk yarısı doğru, ikincisi değildi. Yön vektörü taşıyamaz ama
glifler taşıyor: saf bir döndürmede glif, taban çizgisindeki orijininden `dir`'in çeyrek tur
döndürülmüş yönüne doğru uzanır; aynalama `dir`'e dokunmadan bu tarafı ters çevirir. 0/45/90/180/270
derecede, aynalı ve aynasız ölçüldü - izdüşüm on düz durumda +0.65, on aynalı durumda -0.65.
Eşik ayarı yok, işaret yeterli. Bkz. `readers/pdf_reader.py:_span_is_mirrored`.

### D5 — Her şey yeniden çalıştırılabilir olmalı
İşlem sonucu `.lkproj` (JSON) olarak diske yazılır. Kullanıcı kapatıp açınca kaldığı yerden devam eder,
çeviriyi elle düzeltip yeniden üretebilir. **Tek seferlik, durumsuz boru hattı yazma.**

### D6 — Çeviri kalitesi segment bayraklarıyla izlenir
%100 otomatik doğruluk hedefi yok. Her segment `confidence` ve `needs_review` taşır ve
bu bayraklar çeviri motoru içinde işlevseldir (fitting motoru taşan segmenti işaretler,
passthrough literal yakaladığında flag'ler, CLI skor tablosu sayar). **Gözden geçirme
editörü kaldırıldı** (2026-09): uygulama akışı 1. Belge → 2. Çeviri → 3. Tamamlandı
(çıktıyı aç / klasörde göster / yeni çeviri). Bayraklar .lkproj'e yazılmaya devam eder;
UI'da ayrı bir düzeltme ekranı yoktur.

---

## 3. Dizin sahipliği — çakışmayı önleyen tek kural

**Bir ajan yalnızca kendi dizinine yazar.** Başka dizinde değişiklik gerekiyorsa, kod yazmaz;
şefe (ana Claude oturumu) bildirir.

| Dizin | Sahip |
|---|---|
| `src/layoutkeep/core/` | Şef (ana oturum) — DocIR ve ortak tipler |
| `src/layoutkeep/readers/pdf_reader.py`, `writers/pdf_writer.py` | `lk-pdf` |
| `src/layoutkeep/readers/epub_reader.py`, `writers/epub_writer.py` | `lk-epub` |
| `src/layoutkeep/providers/` | `lk-provider` |
| `src/layoutkeep/fitting/` | `lk-fitting` |
| `src/layoutkeep/ui/` | `lk-ui` (veya Antigravity) |
| `tests/` | `lk-verify` (diğerleri kendi testini yazabilir, ama `lk-verify` denetler) |
| `docs/`, `_agents/` | Şef |

`core/` **hiçbir alt ajan tarafından değiştirilmez.** Şema değişikliği talebi şefe gider.

---

## 4. Kodlama kuralları

- Kod, commit mesajı ve kod içi yorum **İngilizce**. Kullanıcıya rapor **Türkçe**.
- Type hint zorunlu. `from __future__ import annotations` her dosyada.
- Çekirdek modüller (`core/`, `fitting/`, `providers/`) **ağır bağımlılık import etmez** —
  PyMuPDF sadece `readers/pdf_reader.py` ve `writers/pdf_writer.py` içinde geçer.
  Bu, test edilebilirliği ve ileride motor değiştirmeyi mümkün kılar.
- İstenmeyen soyutlama yok. Tek kullanımlık kod için factory/registry/plugin yazma.
- Mevcut kod stiline uy. İlgisiz kodu "iyileştirme". Ölü kod görürsen **sil değil, bildir**.
- Her değişen satır doğrudan verilen göreve izlenebilmeli.

## 5. Doğrulama kuralı

"Bitti" demeden önce **çalıştır ve çıktıyı göster**. Test yoksa yaz.
Çıktı olmadan "çalışıyor" iddiası kabul edilmez. Başarısız testi başarılı gibi raporlama —
başarısızsa çıktısıyla birlikte söyle.

## 6. Yasak

- DRM kırma kodu — hiçbir biçimde.
- `core/` şemasını izinsiz değiştirmek.
- Ağır bağımlılığı (torch, paddle) Faz 1'e sokmak.
- API anahtarını düz metin dosyaya yazmak — OS keychain (`keyring`) kullanılır.
