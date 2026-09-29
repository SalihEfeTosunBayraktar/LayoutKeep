# Çift dilli PDF çıktısı: plan ve ölçüm

**Durum:** uygulandı (2026-09-20). Bu belge kararın gerekçesini ve ölçümünü tutar.

## Neden bu madde ilk sırada

Yol haritasındaki en yüksek etkili eksik: kullanıcı çeviriyi **kaynakla yan yana** görmek istiyor
(karşılaştırma sitesi bunu yapıyor ama PDF çıktısında yok). Dışarıda bu özellik standart:
BabelDOC `--use-alternating-pages-dual` ile almaşık sayfalar, varsayılan olarak da aynı sayfada
**yan yana** üretiyor. Bizde eksikti.

## Tasarım kararı: boru hattına dokunma, sonradan birleştir

İlk düşünülen yol yazıcıyı değiştirmekti (çeviri yazılırken kaynağı da çizmek). Bu yanlış olurdu:

1. **Denetim bozulurdu.** L1–L10 kuralları "kaynak sayfa N ↔ çıktı sayfa N" varsayar; çift dilli
   bir çıktıda bu eşleşme kaybolur (yan yana modunda sayfa genişliği değişir, almaşıkta sayfa
   sayısı ikiye katlanır). Denetimin anlamlı kalması için **çevrilmiş PDF'in kendisi değişmemeli**.
2. **Yazıcı tek sorumluluk taşımalı.** `pdf_writer` çeviriyi kaynağın kutularına yazar; "iki
   belgeyi birleştirmek" ayrı bir iştir.

Bu yüzden çift dilli çıktı bir **birleştirme adımı**dır: kaynak PDF + çevrilmiş PDF → yeni PDF.
Çeviri hattı hiç değişmez, denetim değişmez, `audit.json` değişmez.

## İki mod

| Mod | Ne yapar | Sayfa sayısı | Sayfa boyutu |
|---|---|---|---|
| `side` | Her sayfada solda kaynak, sağda çeviri | değişmez | genişlik 2× |
| `alternate` | Kaynak sayfa, ardından çevirisi | 2× | değişmez |

Varsayılan `side`: kitap okurken göz aynı hizada kalır; `alternate` ise sayfa boyutu büyütmek
istemeyenler için (tablet, e-okuyucu) ve yazdırmak için uygundur.

## Uygulama

`src/layoutkeep/writers/dual_pdf.py`:

- `compose_dual(source: Path, translated: Path, out: Path, mode: str) -> int`
- `side`: yeni sayfa = `(2×w, h)`; kaynak `show_pdf_page` ile sol yarıya, çeviri sağ yarıya çizilir.
- `alternate`: her kaynak sayfa kopyalanır, ardından çevrilmiş sayfa eklenir (`insert_pdf`).
- Sayfa sayıları eşit değilse (kısmi koşu) **ortak sayfa sayısı kadar** birleştirilir ve bu sayı
  döndürülür — sessizce eksik belge üretilmez.

Komut satırı: `--dual side|alternate` (varsayılan kapalı). Arayüzde çıktı bölümünde bir kutu.

## Ölçüm (kabul kriterleri)

| Kriter | Nasıl ölçülür | Beklenen |
|---|---|---|
| Sayfa sayısı | `pymupdf` ile çıktı sayfaları | `side`: kaynakla eşit · `alternate`: 2× |
| Sayfa boyutu | ilk sayfanın `rect` | `side`: genişlik 2× · `alternate`: eşit |
| İçerik yerleşimi | yan yana modda sol yarının metni kaynağın metniyle aynı | eşit |
| Denetim değişmezliği | çevrilmiş PDF üzerinde `lossless_audit` önce/sonra | aynı sayılar |
| Kısmi koşu | kaynak 10 sayfa, çeviri 4 sayfa | çıktı 4 sayfa, döndürülen sayı 4 |

Testler: `tests/test_writers_dual_pdf.py`.

## Riskler ve sınırlar

- **Dosya boyutu** kabaca iki katına çıkar (görseller iki kez gömülür — pymupdf nesneleri
  paylaşabildiği ölçüde; ölçüm: NIST dergisi 4 sayfa üzerinde).
- **Bağlantılar ve ek açıklamalar** yan yana modda kopyalanmaz; almaşık modda kaynak sayfanın
  kendi bağlantıları korunur.
- **Telif**: çift dilli çıktı kaynağı da içerir; yalnız kullanıcının kendi belgesi için üretilir,
  yayınlanmaz (siteye yalnız açık lisanslı belgelerin karşılaştırması girer).
- **Sağdan sola** belgelerde anlamlı değildir (RTL zaten uygulanmadı, D4).
