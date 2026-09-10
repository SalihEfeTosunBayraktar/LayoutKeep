# Günümüz standartları — tarama, bulgular, düzeltmeler

> Yöntem: **tahmin değil tarama.** Her satır ya bir komutun çıktısıdır ya da yeniden
> koşturulabilir bir kontroldür. Tarih: 2026-09, HEAD `17a120a` üzerinde.

## Aranıp bulunamayanlar (temiz çıkan taramalar)

Bunlar bulgu değil; bir denetimin neye baktığını söylemek, ne bulduğunu söylemek kadar
önemlidir. Aşağıdakiler arandı ve **hiçbiri yok**:

| Aranan | Neden önemli | Sonuç |
|---|---|---|
| `datetime.utcnow()` | 3.12'de kullanımdan kaldırıldı, zaman dilimsiz | 0 |
| `typing.List/Dict/Optional` | 3.9+ yerleşik jenerikleri var | 0 |
| Çıplak `except:` | `KeyboardInterrupt` dahil her şeyi yutar | 0 |
| Kütüphane kodunda `print()` | kütüphane çıktı basmaz | 0 |
| Zaman aşımsız ağ çağrısı | süresiz asılma | 0 |
| `encoding=` verilmeden `open()` | Windows'ta yerel kod sayfası → bozuk metin | 0 |
| `extractall` (zip-slip) | arşivden dizin dışına yazma | 0 |
| Kütüphane kodunda `assert` | `-O` ile derlenince kaybolur | 0 |
| Entity çözen XML ayrıştırıcı | XXE | **8 ayrıştırıcının 8'i** `resolve_entities=False` |

## Bulgular ve düzeltmeleri

### S1 · Paket kendini "tipsiz" ilan ediyordu · düzeltildi

`src/layoutkeep/py.typed` yoktu. Paket baştan aşağı tip açıklamalı, ama PEP 561 işaretçisi
olmadan onu içeri alan hiçbir tip denetleyicisi bu açıklamaları görmez. Eklendi ve tekerleğin
içinde olduğu doğrulandı.

### S2 · Lint kuralları depoda yazılı değildi · düzeltildi

`pyproject.toml` yalnızca satır uzunluğu ve hedef sürümü söylüyordu. Yürürlükteki 826 kural
kurulu ruff'ın varsayılanından geliyordu: **başka sürümü olan bir katkıcı farklı bir standarda
tabi olur**, ve CI'ın lint adımı yerelde ölçtüğünden başka şey ölçerdi. Kural seti artık
`[tool.ruff.lint]` içinde açıkça yazılı, muafiyetler gerekçeleriyle birlikte.

### S3 · `str` + `Enum` yerine `StrEnum` · düzeltildi

Altı sınıf (`Direction`, `BlockRole`, `FitMode`, `FitLayer`, `FontClass`, `MatchQuality`)
`class X(str, Enum)` kalıbındaydı. Python 3.11 bunun için `StrEnum` getirdi, proje 3.13
hedefliyor. Yan etkisi: `f"{BlockRole.BODY}"` artık `BlockRole.BODY` değil `body` veriyor —
serileştirme zaten `.value` kullandığı için proje dosyaları etkilenmedi (773 test yeşil).

### S4 · `zip()` `strict=` olmadan · düzeltildi

Dört çağrı. Farklı uzunlukta iki diziyi sessizce kırpar; 3.10'dan beri `strict=True` bunu hataya
çevirir.

### S5 · Paket meta verisi eksikti · düzeltildi

`readme`, `keywords`, `classifiers`, `urls` yoktu. GitHub ve PyPI'da bir projeden ilk görülen
şey budur. 12 sınıflandırıcı, 4 bağlantı ve README bağı eklendi; tekerlek kurularak doğrulandı.

### S6 · Depo dosyaları eksikti · düzeltildi

`CONTRIBUTING.md`, `SECURITY.md`, `.editorconfig`, `.github/dependabot.yml`, hata/özellik
şablonları ve PR şablonu yoktu. `SECURITY.md` boş bir nezaket metni değil: belgenin ne zaman
ağa çıktığını, anahtarların nerede durduğunu ve hangi saldırı sınıflarının zaten kapalı
olduğunu yazıyor.

### S7 · CI paketlemeyi denemiyordu · düzeltildi

Testler ve exe derlemesi vardı, ama `python -m build` yoktu: kurulamayan bir tekerlek ya da
fontları/tip işaretçisini taşımayan bir paket ancak yayın günü fark edilirdi. Artık her
gönderimde kuruluyor, `twine check` ile denetleniyor ve içeriği sınanıyor.

### S8 · Küçük modernizasyonlar · düzeltildi

`contextlib.suppress`, `os.path` → `pathlib`, gereksiz atamalar, kullanılmayan döngü
değişkenleri, dosya sonu satırları — yaklaşık 25 madde, ruff'ın otomatik düzeltmesiyle ve
gözden geçirilerek.

## Düzeltmeden bırakılanlar, gerekçesiyle

| Konu | Neden bırakıldı |
|---|---|
| Tip denetleyici (mypy/pyright) CI'da yok | Değerli olur, ama 107 kaynak dosyada ilk koşuş yüzlerce bulgu verir; ayrı bir iş olarak açılmalı, yayın öncesinde aceleye getirilmemeli |
| Kod kapsamı (coverage) ölçülmüyor | Kapsam yüzdesi bu projede yanıltıcı olurdu: 773 testin çoğu davranış sınıyor, satır saymıyor |
| `RUF001/002/003` (belirsiz Unicode) kapalı | Arayüz ve yorumlar Türkçe; `ı`, `ş`, `ğ` belirsiz karakter değil, dilin kendisi. 1201 uyarının tamamı buradan geliyordu |
| `S310` (urlopen) kapalı | Çağrılan adres kullanıcının kendi uç nokta ayarı; kural bunu saldırgan girdisinden ayırt edemiyor |
| OOXML adları (`rPr`, `pPr`) | Biçimin kendi element adları; küçük harfe çevirmek neye karşılık geldiklerini gizler |

## Yol boyunca iki hata (ikisi de ölçümle yakalandı)

**Ruff'ın otomatik düzeltmesi yanlıştı.** `pymupdf.Rect(...) + (-1, -1, 1, 1)` ifadesini liste
birleştirme sanıp sekiz elemanlı bir demete çevirdi — oysa bu, dikdörtgeni her yönden bir punto
büyüten Rect aritmetiği. Döndürülmüş metin işlemeyi bozacaktı. Geri alındı, sebebi koda yazıldı.

**Toplu değiştirme yanlıştı.** `os.path.isdir(d)` → `Path(d)` her zaman doğru döner; var olmayan
font dizinleri listeye girecekti. Font kayıt defteri çalıştırılarak yakalandı (3 dizin, hepsi
gerçek, 259 font).
