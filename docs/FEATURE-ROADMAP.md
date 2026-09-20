# LayoutKeep: eksik ve geliştirilmesi gereken özellikler

Bu rapor, "başka ne yapılabilir, nerede yetersiziz" sorusuna **ölçülmüş durum** ve **dışarıdaki
karşılaştırma noktaları** üzerinden cevap veriyor. İddialar kaynaklı; nerede olduğumuz kendi
denetimlerimizle (L1–L10, D1–D3, `tools/audit/*`) yazılı.

Tarih: 2026-09-20 · Kaynaklar: BabelDOC (ACL 2026 demo, arXiv 2605.10845, AGPLv3), mineru-translate
(PyPI 0.1.2), ticari derlemeler (Doclingo, Lara Translate, Doctranslate, Bluente).

> **Düzeltme (2026-09-20, aynı gün).** Bu raporun ilk sürümü "terim sözlüğü" ve "koşular arası
> önbellek" satırlarını "yok" diye yazmıştı: yanlıştı. İkisi de kodda var (`providers/glossary.py`,
> `providers/memory.py`, ikisinin de kendi testleri var); eksik olan, ikisinin de uygulamadan
> erişilememesiydi. Satırlar düzeltildi, arayüz bağlantısı aynı gün yapıldı.

---

## 1. Bugün ne var (kısa envanter)

| Alan | Durum |
|---|---|
| Boru hattı | DocIR (tek ara temsil) → okuyucu/yazıcı çiftleri; PDF, EPUB, DOCX, PNG, JPG |
| Kayıpsızlık denetimi | **L1–L10 + D1–D3**, hem uygulamada (`verify.py`) hem CLI'da, hem de kayıtlı koşularda (`tools/audit/lossless_audit.py`) |
| Sığdırma | İki yönlü merdiven (kısalt → küçült → gerekirse büyüt), `fitting/`, ayarlanabilir eşikler |
| Çeviri belleği | Aynı metni bir kez çevirme, tekrarları çoğunluk çevirisiyle birleştirme |
| **Koşular arası bellek** | `providers/memory.py`: SQLite, (kaynak, diller, model) anahtarlı; CLI'da `--memory`, uygulamada ayar anahtarı (2026-09-20'de arayüze bağlandı) |
| **Terim sözlüğü** | `providers/glossary.py`: JSON sözlük isteme eklenir, çıktıda kullanımı denetlenir; CLI'da `--glossary`, uygulamada ayar alanı (2026-09-20'de bağlandı) |
| Sağlayıcılar | OpenAI uyumlu (LM Studio, bulut), DeepL |
| Paralellik | Bölüm/parça bazlı paralel koşu, `.lkproj` kontrol noktası + `--resume` |
| Arayüz | PySide6: kurulum, ilerleme (yüzen çubuk), tamamlanma, gelişmiş ayarlar, karşılama ekranı |
| Vitrin | 18 belgelik karşılaştırma sitesi (zoom'lu), `docs/LOSSLESS-REPORT.md` |

## 2. Dışarıda ne var, bizde ne yok

BabelDOC'un kendi karşılaştırma tablosundan (arXiv 2605.10845, Tablo 1–2) ve mineru-translate'in
özellik listesinden bizde **olmayan** kalemler:

| Özellik | Kimde var | Bizde | Değer |
|---|---|---|---|
| **Çift dilli çıktı** (kaynak+çeviri yan yana ya da almaşık sayfalar) | BabelDOC, mineru-translate, Doclingo, Lara | site var, **PDF yok** | Yüksek: inceleme akışının tamamı buna bakıyor |
| Terim sözlüğü kısıtı | BabelDOC (`--glossary` CSV), DeepL, Lara, Taia | **var** (JSON **veya CSV/TSV**, istem + çıktı denetimi, uygulama içi tablo düzenleyici) | Kalan: sözlük dışa aktarma, otomatik terim adayları |
| **Otomatik terim çıkarımı** | BabelDOC | yok | Orta: sözlüğü elle doldurmak yerine aday listesi |
| **Sayfa-ötesi bağlam** | BabelDOC | kısmi (`context_before/after`) | Orta: paragraf bölünmelerinde zamir/atıf tutarlılığı |
| **Örtüşme çözümü kademesi** (küçült → satır aralığını sık → aşağı it) | mineru-translate | kısmi (`--fit-mode reflow` deneysel) | Orta: D1'e düşen 801 blok (kitap koşusu) tam bu sınıf |
| Çeviri önbelleği (koşular arası) | mineru-translate | **var** (SQLite bellek) | Kalan: arayüzde isabet oranını göstermek, sözlük değişince geçersiz kılmak (sözlük parmak izi anahtara eklendi) |
| **Görsel/tablo içi metin çevirisi** | BabelDOC | yok (kilitli) | Düşük-orta: manga/infografik boru hattı |
| **Kaynakça + dipnot yeniden kurma** | BabelDOC | blok olarak korunuyor, "yeniden kurma" yok | Düşük: akademik akış |
| **Editör / sonradan düzeltme** | Doclingo, Lara, X-doc | yok (D6 akışı kaldırıldı) | Orta: "ilk geçiş + inceleme" vaadimizin devamı |
| **Eklenti ekosistemi** (Zotero, Word) | BabelDOC/PDFMathTranslate | yok | Düşük: kapsam dışı, bilinçli |
| **Kurumsal uygunluk** (SOC2/ISO) | Bluente | yok | Düşük: yerel-önce olmamız zaten farklı bir cevap |

**Bizde olup onlarda görünmeyen:** L1–L10 kayıpsızlık denetimi (kaynağa karşı sayfa sayfa), inceleme
bayrakları + gerekçe, gerçek held-out örneklerden üretilen karşılaştırma sitesi, ayarların
(bağlam penceresi, sığdırma eşikleri) çalışma anında değiştirilebilmesi, AGPLv3 + tam yerel çalışma.

## 3. Önerilen sıra (etki / emek / nasıl ölçülür)

1. **Çift dilli PDF çıktısı** (`--dual page|alternate`). Emek: orta. Kilidi kolay: aynı sayfayı iki
   kez yazıp sayfa boyutunu ikiye katlamak ya da sayfa sırasını değiştirmek; `pdf_writer` zaten
   sayfa bazlı. Ölçüm: çıktı sayfa sayısı = 2×kaynak (almaşık) ve L1–L10 bozulmuyor.
2. ~~Sözlüğü ve belleği arayüzün parçası yapmak~~ **yapıldı (2026-09-20)**: sözlük dosyası ve bellek
   anahtarı Gelişmiş Ayarlar'da, uygulama içi tablo düzenleyici (satır ekle/sil, dosyadan yükle,
   farklı kaydet), CSV/TSV içe alma, sözlük parmak izi bellek anahtarında, tamamlanma ekranında
   bellek isabeti. Kalan: otomatik terim adayları ve sözlüğü dışa aktarma.
4. **Örtüşme çözümü**: `reflow` modunu deneysel olmaktan çıkar; "küçült → satır aralığını sık →
   aşağı it" kademesini `fit` içine al. Emek: orta-yüksek. Ölçüm: kitap koşusundaki D1=801'in ve
   `type_drift` "okunamaz" sayısının düşmesi (bugünkü düzeltme 12→2 yaptı; kalan sınıf bu).
5. **Otomatik terim adayları**: belgede sık geçen isim öbekleri → kullanıcıya liste (sözlük
   düzenleyicisine "belgeden öner" düğmesi). Emek: orta. Ölçüm: çıkarılan adayların elle seçilen
   sözlükle örtüşmesi.
6. **Küçük editör**: inceleme bayraklı blokları uygulama içinde düzeltip yeniden yazma. Emek:
   yüksek. Ölçüm: bayrak kapatma oranı, çıktıda L-kriterleri bozulmadan.
7. **Sayfa-ötesi bağlam**: parça sınırında önceki parçanın son 2 bloğunu isteme eklemek. Emek:
   düşük. Ölçüm: L2 (çevrilmemiş/başka dilde) ve D2 sayılarının düşmesi; insan okumasında zamir
   tutarlılığı.

## 4. Bilinçli olarak yapılmayacaklar

- **Bulut-öncelikli olmak / hesap zorunluluğu**: projenin varlık sebebi yerel çalışmak.
- **Surya gibi RAIL-M ağırlıklı modeller**: lisans uyumsuzluğu (daha önce ölçülüp çıkarıldı).
- **Tüm format çiftlerini açmak**: `format_matrix` ölçümü gösterdi ki çapraz dönüşümlerin bir kısmı
  içerik kaybediyor; açma kararı ürün kararı olarak duruyor, koda gömülü değil.
- **Eklenti ekosistemi** (Zotero/Word): bakım maliyeti, tek geliştiricili proje için gerçekçi değil.

## 5. Bugünkü dürüst tablo (nerede zayıfız)

- **D1 = 801 / 4491 blok** (220 sayfalık ders kitabı): "çeviri kutusuna sığmadı" bayrağı. Bunların
  bir kısmı gerçekten zor (tablo hücreleri), ama 3. maddedeki kademeli çözüm bu sayıyı düşürmeli.
- **L2 = 2, L6 = 4** (aynı kitap): modelin çevirmediği ya da sayı düşürdüğü bloklar; hepsi inceleme
  kuyruğuna düşüyor ama kapanmıyor.
- **Taramalarda OCR**: %98-100 okuma ölçülüyor; eğik/lekeli sayfalarda bu düşer, henüz ölçülmüş bir
  eğim düzeltme yok.
- **Yerel küçük modelin dil becerisi**: deyim ve terimlerde zayıf; bulut sağlayıcı belirgin fark
  yaratıyor (ölçüm: aynı belgede terim uyumu karşılaştırması henüz yapılmadı — yapılacak).

## 6. Nasıl ölçeriz (hazır araçlar)

| Soru | Araç |
|---|---|
| Kayıp var mı? | `tools/audit/lossless_audit.py --work <koşu>` (L1–L10, D1–D3) |
| Metin görselin üstünde mi? | `tools/audit/text_over_image.py <koşu>` |
| Tipografi kaynaktan sapmış mı? | `tools/audit/type_drift.py <koşu>` (büyümüş/küçülmüş/hizası değişmiş/okunamaz) |
| İstek sayısı ve süre? | her koşunun sonundaki `spent read | translate | write | verify` satırı |
| Değişiklik işe yaradı mı? | `rewrite_run.py` (yazıcı) / `reader_ab.py` (okuyucu) — model gerekmez |
