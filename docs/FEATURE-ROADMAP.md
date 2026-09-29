# LayoutKeep: eksik ve geliştirilmesi gereken özellikler

Bu rapor, "başka ne yapılabilir, nerede yetersiziz" sorusuna **ölçülmüş durum** ve **dışarıdaki
karşılaştırma noktaları** üzerinden cevap veriyor. İddialar kaynaklı; nerede olduğumuz kendi
denetimlerimizle (L1–L10, D1–D3, `tools/audit/*`) yazılı.

İlk sürüm: 2026-09-20 · **Son güncelleme: 2026-09-29** · Kaynaklar: BabelDOC (ACL 2026 demo, arXiv
2605.10845, AGPLv3), mineru-translate (PyPI 0.1.2), ticari derlemeler (Doclingo, Lara Translate,
Doctranslate, Bluente).

> **Düzeltme (2026-09-20, aynı gün).** Bu raporun ilk sürümü "terim sözlüğü" ve "koşular arası
> önbellek" satırlarını "yok" diye yazmıştı: yanlıştı. İkisi de kodda var (`providers/glossary.py`,
> `providers/memory.py`, ikisinin de kendi testleri var); eksik olan, ikisinin de uygulamadan
> erişilememesiydi. Satırlar düzeltildi, arayüz bağlantısı aynı gün yapıldı.

> **Güncelleme (2026-09-29).** 20 Eylül'den bu yana kalan "Kalan" kalemlerinin hepsi kapandı ya da
> ölçülüp karara bağlandı: sözlüğü dışa aktarma, önizlemeli ve çok dilli terim adayları, ayar
> profilleri (zaten vardı; rapor eskimişti), üst üste çift dilli PDF, görsel sayfa seçici. 4. madde
> (örtüşme kademesi) büyük ölçüde yapılmış durumda; 7. madde (sayfa-ötesi bağlam) ölçüldü ve üründe
> zaten var olduğu görüldü (D-023). Madde 6 (küçük editör) kullanıcı kararıyla yapılmayacak
> (CONTRACT.md D6 ile aynı yönde).

---

## 1. Bugün ne var (kısa envanter)

| Alan | Durum |
|---|---|
| Boru hattı | DocIR (tek ara temsil) → okuyucu/yazıcı çiftleri; PDF, EPUB, DOCX, PNG, JPG |
| Kayıpsızlık denetimi | **L1–L10 + D1–D3**, hem uygulamada (`verify.py`) hem CLI'da, hem de kayıtlı koşularda (`tools/audit/lossless_audit.py`) |
| Sığdırma | İki yönlü merdiven (kısalt → küçült → gerekirse büyüt), kutunun altındaki ve yanındaki boş kâğıdı kullanma (`fitting/growth.py`), deneysel `reflow` modunda alttaki blokları aşağı itme (`fitting/elastic_flow.py`), ayarlanabilir eşikler |
| Çeviri belleği | Aynı metni bir kez çevirme, tekrarları çoğunluk çevirisiyle birleştirme |
| **Koşular arası bellek** | `providers/memory.py`: SQLite, (kaynak, diller, model, sözlük parmak izi) anahtarlı; CLI'da `--memory`, uygulamada ayar anahtarı |
| **Terim sözlüğü** | `providers/glossary.py`: JSON veya CSV/TSV; isteme eklenir, çıktıda denetlenir, kaçan terim bir kez yeniden sorulur. Uygulama içi tablo düzenleyici: yükle (JSON/CSV/TSV), farklı kaydet, **dışa aktar**, **önizlemeli "Belgeden öner"** |
| **Otomatik belge sözlüğü** | `core/doc_glossary.py`: belgenin tekrar eden terimleri tek istekle çevrilir (`translation.auto_glossary`) |
| **Terim adayları** | `core/terms.py` + `core/stopwords.py`: sıklık kuralı, 8 dil için işlev sözcükleri, kesme işaretli ekler, künye/URL parçaları dışarıda |
| **Ayar profilleri** | `core/profiles.py`: "hızlı taslak" / "yayın kalitesi", ayarlar penceresinde seçilir |
| Sağlayıcılar | OpenAI uyumlu (LM Studio, bulut), DeepL |
| Paralellik | Bölüm/parça bazlı paralel koşu, `.lkproj` kontrol noktası + `--resume` |
| **Çift dilli PDF** | `writers/dual_pdf.py`: yan yana, almaşık ve **üst üste (iki katman)** |
| **Sayfa aralığı** | Metin alanı + **görsel sayfa seçici** (PDF küçük resimleri); çıktı yalnız seçilen sayfaları içerir, proje tüm belgeyi saklar |
| Arayüz | PySide6: kurulum, ilerleme (yüzen çubuk, canlı olay akışı), tamamlanma, gelişmiş ayarlar, karşılama ekranı; tr/en/de |
| Vitrin | Karşılaştırma sitesi (zoom'lu), tarihçe kitabı, mimari atlas, `docs/LOSSLESS-REPORT.md` |

## 2. Dışarıda ne var, bizde ne yok

BabelDOC'un kendi karşılaştırma tablosundan (arXiv 2605.10845, Tablo 1–2) ve mineru-translate'in
özellik listesinden:

| Özellik | Kimde var | Bizde | Değer |
|---|---|---|---|
| **Çift dilli çıktı** | BabelDOC, mineru-translate, Doclingo, Lara | **var**: yan yana, almaşık, üst üste (katman) | — |
| Terim sözlüğü kısıtı | BabelDOC (`--glossary` CSV), DeepL, Lara, Taia | **var** (JSON/CSV/TSV, istem + çıktı denetimi, düzenleyici, dışa aktarma) | — |
| **Otomatik terim çıkarımı** | BabelDOC | **var** (aday listesi önizlemeli; otomatik belge sözlüğü modelle) | Kalan: tutarlılık yargıcıyla yeni aday listesinin etkisini ölçmek |
| **Sayfa-ötesi bağlam** | BabelDOC | **var** (bağlam belgenin tamamı üzerinden kurulur; D-023) | — |
| **Örtüşme çözümü kademesi** (küçült → satır aralığını sık → aşağı it) | mineru-translate | büyük ölçüde (boş kâğıdı kullanma varsayılan; aşağı itme `reflow`'da; satır aralığı adımı ölçüldü, geri alındı) | Kalan: `reflow`'u varsayılana almak için bench ölçümü |
| Çeviri önbelleği (koşular arası) | mineru-translate | **var** (SQLite bellek, sözlük parmak izi anahtarda, tamamlanma ekranında isabet) | — |
| **Görsel/tablo içi metin çevirisi** | BabelDOC | kısmi (`translation.figure_text`, varsayılan kapalı: metin katmanından ve OCR ile) | Düşük-orta |
| **Kaynakça + dipnot yeniden kurma** | BabelDOC | kaynakça korunabiliyor (`translation.preserve_references`), "yeniden kurma" yok | Düşük: akademik akış |
| **Editör / sonradan düzeltme** | Doclingo, Lara, X-doc | yok (D6 akışı bilinçli kaldırıldı) | Yapılmayacak (madde 6, kullanıcı kararı) |
| **Eklenti ekosistemi** (Zotero, Word) | BabelDOC/PDFMathTranslate | yok | Düşük: kapsam dışı, bilinçli |
| **Kurumsal uygunluk** (SOC2/ISO) | Bluente | yok | Düşük: yerel-önce olmamız zaten farklı bir cevap |

**Bizde olup onlarda görünmeyen:** L1–L10 kayıpsızlık denetimi (kaynağa karşı sayfa sayfa), inceleme
bayrakları + gerekçe, sabit bench (21 kaynak, iki yön, üç ölçüt), gerçek held-out örneklerden
üretilen karşılaştırma sitesi, ayarların çalışma anında değiştirilebilmesi, AGPLv3 + tam yerel
çalışma.

## 3. Maddeler (durum / ölçüm)

0. ~~Sayfa aralığının çıktıyı da daraltması~~ **yapıldı (2026-09-20)**: aralık yazılan kopyaya
   uygulanıyor, kaydedilen `.lkproj` belgenin tamamını saklıyor. Ölçüm: 15 sayfalık PDF'te aralık
   "1-2" → çıktı 2 sayfa, proje 15 sayfa (11 test).
   ~~Kalan: görsel sayfa seçici~~ **yapıldı (2026-09-29)**: "Sayfaları seç…" PDF sayfalarını
   işaretli küçük resimler olarak gösterir ve alanın zaten aldığı aralık metnini yazar
   (`ui/page_picker.py`, `range_helper.format_page_range`; 200 rastgele seçimde gidiş-dönüş
   birebir). Hiç sayfa işaretli değilse onay kapalı (boş aralık "tümü" demek).
1. ~~Ayar ekranındaki ölü anahtar~~ **yapıldı (2026-09-20)**. ~~Kalan: ayar profilleri~~ **zaten
   vardı**: `core/profiles.py` ("hızlı taslak" / "yayın kalitesi"), ayarlar penceresinde seçiliyor,
   `tests/test_core_profiles.py`. Bu rapor 20 Eylül'den sonra güncellenmediği için "kalan" diye
   duruyordu.
2. ~~Çift dilli PDF çıktısı~~ **yapıldı (2026-09-20)**: yan yana ve almaşık, `--dual` + ayar.
   ~~Kalan: üst üste~~ **yapıldı (2026-09-29)**: `overlay` modu sayfa boyutunu ve sayısını korur;
   çeviri ve kaynak aynı sayfada iki PDF katmanıdır (çeviri açık, kaynak kapalı), görüntüleyicinin
   katman panelinden çevrilir. Gerçek koşuda (TCK 5237, TR→EN) varsayılan sayfa çevrilmiş sayfayla,
   katman çevrilince kaynak sayfayla piksel piksel aynı. Aynı işte düzeltilen hata: ayar listesi
   iki seçenek için ham anahtar ve koda gömülü Türkçe etiket gösteriyordu.
3. ~~Sözlüğü ve belleği arayüzün parçası yapmak~~ **yapıldı (2026-09-20)**. ~~Kalan: sözlüğü dışa
   aktarma~~ **yapıldı (2026-09-29)**: "Dışa aktar…" tablonun kopyasını CSV/TSV/JSON yazar; çalışmanın
   okuduğu dosya yerinden oynamaz. Aynı işte: "Dosyadan yükle" filtresi CSV/TSV gösterip yalnız JSON
   okuyordu; başlık satırı olan tabloda ayırıcı artık başlıktan alınıyor (virgüllü terimli TSV
   CSV sanılıyordu).
4. **Örtüşme çözümü: büyük ölçüde yapıldı.**
   - Kutunun altındaki boş kâğıdı kullanma (`fitting/growth.py`, `write.grant_room_pt`, varsayılan
     24 pt) ve satırın yanındaki kâğıdı kullanma (`write.grant_room_right_pt`, 60 pt): **varsayılan
     açık**, fitting geçişi ve yazıcı aynı fonksiyonu okur. Bu, 2026-09-20 ölçümünün asıl
     darboğazını ("`room_below` kutuyu 6pt'ye eziyor") kapatan adım.
   - Aşağı itme (`fitting/elastic_flow.py`): alttaki blokları aynı sütunda öteler; **yalnız `reflow`
     modunda** (`fitting.reflow`, varsayılan kapalı).
   - Satır aralığını sıkma adımı: 2026-09-20'de denendi, **geri alındı** (geçişin kendi fontuyla
     hiçbir bloğu kurtarmadı; iki kolun yazılmış sayfası birebir aynıydı).
   - Bugünkü düzen ölçütü (0.9.12, G kolu): bloğun şekli korunan payı EN→TR %94.5, TR→EN %95.0.
   **Kalan:** `reflow`'u varsayılana almak ancak bench ile (L7 ve D3 artmadan D1 düşerse).
5. ~~Otomatik terim adayları~~ **yapıldı (2026-09-20)**. ~~Kalan: önizleme ve çok dilli
   stopword~~ **yapıldı (2026-09-29)**:
   - "Belgeden öner" önce önizleme açar (`ui/term_candidates_dialog.py`): her aday kullanım
     sayısıyla, işaretli; yalnız işaretliler tabloya girer. Aday sayısı ayardan
     (`translation.suggest_limit`, varsayılan 25).
   - `core/stopwords.py`: en, tr, de, fr, es, it, pt, nl için işlev sözcükleri; dil belgeden, yoksa
     metinden tahmin. Kesme işaretinden sonraki ek ayrılır ("Türkiye’nin" → "Türkiye"), öbek ekin
     üstünden geçmez; URL/künye parçaları hiçbir dilde terim değil.
   - **Ölçüm (bench'in 21 kaynağı, model gerekmez):** 600 adaydan 110'u değişti: `your`,
     `through`, `tarafından`, `yönelik`, `https doi org`, `ncbi nlm nih gov`, `SKA ların` gitti;
     yerine `machine translation`, `estimated tax`, `Sosyal Politikalar Bakanlığı` gibi terimler geldi.
   **Kalan:** otomatik belge sözlüğü de bu listeyi kullandığı için, terim tutarlılığına etkisi
   tutarlılık yargıcıyla (bulut modeli) ölçülmeli.
6. ~~Küçük editör~~ **yapılmayacak (kullanıcı kararı, 2026-09-29)**: inceleme bayraklı blokları
   uygulama içinde düzeltip yeniden yazma. CONTRACT.md D6'daki kararla aynı yönde: düzeltme
   editörü ürüne geri gelmiyor.
7. ~~Sayfa-ötesi bağlam~~ **ölçüldü, üründe zaten var (2026-09-29, D-023)**: bağlam belgenin tamamı
   üzerinden, partilemeden ve sayfa aralığından önce kurulur; sayfanın ilk bloğu önceki sayfanın son
   bloğunu bağlam olarak taşır (`tests/test_context_across_pages.py`). Sınır yalnız kitap aracının
   parça başına ayrı süreç açtığı yerde kesiliyor; iki bench kolunda parça başındaki 60 bloğun
   bayraklı 5'i de "PLOS ONE" sayfa başlığı. Bağlama bağlanabilecek L2/D2: 0. Kod değişmedi.

## 4. Bilinçli olarak yapılmayacaklar

- **Bulut-öncelikli olmak / hesap zorunluluğu**: projenin varlık sebebi yerel çalışmak.
- **Surya gibi RAIL-M ağırlıklı modeller**: lisans uyumsuzluğu (daha önce ölçülüp çıkarıldı).
- **Tüm format çiftlerini açmak**: `format_matrix` ölçümü gösterdi ki çapraz dönüşümlerin bir kısmı
  içerik kaybediyor; açma kararı ürün kararı olarak duruyor, koda gömülü değil.
- **Eklenti ekosistemi** (Zotero/Word): bakım maliyeti, tek geliştiricili proje için gerçekçi değil.
- **Uygulama içi düzeltme editörü**: CONTRACT.md D6 ile kaldırıldı, 2026-09-29'da kullanıcı yeniden
  onayladı (madde 6).

## 5. Bugünkü dürüst tablo (nerede zayıfız)

**Bench, 2026-09-29 (commit `a8b2f80`, modül bölme refaktörlerinin ardından, G kolunun ayarlarıyla,
google/gemma-4-e4b):** 21 kaynakta kayıp 11 (G: 14), kayıpsız kaynak 13/21 (G: 12/21), düzen EN→TR
%94.2 / TR→EN %94.6 (G: %94.5 / %95.0). 21 kaynağın 20'sinde denetlenen blok sayısı G ile birebir;
irs_p505'te 243 → 246, ama blok kimlikleri üç parçada da aynı: fark, üç form satırının bu koşuda
modelin çevirisiyle denetim kapsamına girmesi, okuyucudan değil. Refaktörler çıktıyı değiştirmedi;
kalan oynama model gürültüsü aralığında.

- **Kalan kayıp sınıfları (a8b2f80):** L2 = 6 (NASA taramasında 3, arXiv'lerde 3: model bloğu
  çevirmedi), L3 = 2, L6 = 2 (sayı düşürme), L10 = 1. D1 (sığmadı) = 63 blok; en çok IRS formunda
  (17) ve arXiv 19145'te (9): dar tablo hücreleri.

- **Yerel küçük modelin dil becerisi**: kalite yargıcı EN→TR 94.8, TR→EN 96.3 veriyor (0.9.12);
  EN→DE %85–86 düzenle hâlâ "ölçülmedi (deneysel)" (D-021, D-022).
- **Taramalarda OCR**: %98-100 okuma ölçülüyor; eğik/lekeli sayfalarda bu düşer, henüz ölçülmüş bir
  eğim düzeltme yok.
- **D-009** (EPUB→PDF az metinli sayfa) teşhisli, düzeltilmedi.

## 6. Nasıl ölçeriz (hazır araçlar)

| Soru | Araç |
|---|---|
| Ürün bugün ne durumda? | `tools/audit/bench.py` (21 kaynak × 3 sayfa, iki yön; commit başına tablo) |
| Kayıp var mı? | `tools/audit/lossless_audit.py --work <koşu>` (L1–L10, D1–D3) |
| Metin görselin üstünde mi? | `tools/audit/text_over_image.py <koşu>` |
| Tipografi kaynaktan sapmış mı? | `tools/audit/type_drift.py <koşu>` — **sayı yanıltıcıdır**: kutunun içindeki her satırı kutunun *tek* stiline böler |
| Kutuda hangi punto **kayboldu**? | `tools/audit/type_map.py <koşu>` — `faithful` / `flattened` / `shrunk` / `grown` / `mixed` |
| Terimler tutarlı mı? | `tools/audit/term_consistency.py` (bulut yargıç) |
| İstek sayısı ve süre? | her koşunun sonundaki `spent read | translate | write | verify` satırı |
| Değişiklik işe yaradı mı? | `rewrite_run.py` (yazıcı) / `reader_ab.py` (okuyucu) — model gerekmez |
