# Paketleme

Görev 1.6. Bu belge neyin hazır olduğunu ve neyin **para veya karar** beklediğini ayırır.

---

## Yerel yapı (hazır)

Tek dosya EXE üretilir (güncel standart — CLI ve masaüstü için tek `dist\LayoutKeep.exe`):

```powershell
.venv\Scripts\python.exe -m PyInstaller packaging\layoutkeep_onefile.spec --noconfirm --clean
```

Çıktı: `dist\LayoutKeep.exe`

`packaging\layoutkeep.spec` (eski çoklu-klasör varyantı) CI'da ve arşivde durur; el ile üretimde
kullanılmaz. `keyring` arka ucunu çalışma anında import ettiği için `hiddenimports`'a elle
eklendi; yoksa API anahtarı saklama paketlenmiş yapıda sessizce bozulur.

Tek dosyalık yapı her açılışta EXE'yi geçici dizine açar — ilk başlatma biraz yavaş ve bazı
virüs tarayıcıları tetiklenir. Bu, tek dosya dağıtımının bilinen takasıdır; kullanıcı tercihi
olarak kabul edildi.

---

## Kod imzalama (ertelendi — bütçe yok, bilinçli karar)

**Karar: şimdilik imzalanmıyor.** Sertifika bütçesi yok. Sonuçları bilerek kabul ediyoruz:

- **Linux birincil dağıtım kanalı.** İmza gerektirmiyor, sürtünme sıfır.
- **Windows imzasız dağıtılıyor.** SmartScreen "bilinmeyen yayıncı" uyarısı verecek; sürüm notlarında
  bunu açıkça yaz ve kullanıcıya "Ek bilgi → Yine de çalıştır" adımını anlat. Uyarıyı gizlemeye
  çalışma, dürüstçe açıkla.
- **macOS resmî olarak desteklenmiyor.** Gatekeeper imzasız uygulamayı çalıştırmayı reddediyor;
  kullanıcıyı sağ tık → Aç numarasına yönlendirmek kötü bir ilk deneyim. Apple Developer hesabı
  alınana kadar "kaynaktan kurulum" yolu belgeleniyor, ikili dağıtılmıyor.

Bütçe çıktığında sırayla: Windows OV sertifikası (~$200–400/yıl), sonra Apple Developer ($99/yıl).
Aşağıdaki tablo o zaman geldiğinde geçerli.

| Platform | Gereken | Yıllık maliyet | İmzasız ne olur |
|---|---|---|---|
| **Windows** | OV veya EV kod imzalama sertifikası | ~$200–400 | SmartScreen "bilinmeyen yayıncı" uyarısı verir. Çoğu kullanıcı burada vazgeçer |
| **macOS** | Apple Developer üyeliği + notarization | $99 | Gatekeeper **çalıştırmayı tamamen reddeder**. Kullanıcı sağ tık → Aç ile zorlamak zorunda kalır |
| **Linux** | Yok | $0 | Sorun yok. AppImage veya Flatpak imzasız dağıtılabilir |

**Öneri:** Linux ile başla (bedava ve sürtünmesiz), Windows sertifikasını ilk gerçek kullanıcılar
çıkınca al, macOS'u en sona bırak. Açık kaynak projeler için bazı sertifika sağlayıcıları indirim
uygular; almadan önce araştırmaya değer.

macOS'ta ayrıca: universal binary (arm64 + x86_64) gerekir ve **PyInstaller'ın ürettiği tüm alt
süreçler ve dylib'ler ayrı ayrı imzalanmalıdır** — sadece ana çalıştırılabilir dosyayı imzalamak
notarization'dan geçmez.

---

## Font paketleme (✅ tamamlandı)

17 font dosyası `assets/fonts/` altında, hepsi OFL 1.1, lisans metinleriyle birlikte paketleniyor.
Her birinin Türkçe ve Avrupa Latin glif kapsamı **eklenmeden önce doğrulandı**. Toplam ~10 MB —
ilk tahmin 40 MB'dı, subset'lemeye gerek kalmadı. Ayrıntı: `assets/fonts/README.md`.

## Font paketleme — özgün analiz (tarihçe)

`fitting/fontmatch.py` metrik uyumlu ikame fontları arıyor: Tinos, Arimo, Cousine, Caladea,
Carlito, Noto ailesi. **Standart bir Windows kurulumunda bunların hiçbiri yok** — bu ölçüldü,
varsayılmadı.

Sonuç: font eşleştirici sınıfa göre en yakın sistem fontuna düşüyor ve nedenini raporluyor,
ama ikame kalitesi belirgin şekilde daha düşük oluyor.

Hepsi OFL veya Apache-2.0 lisanslı, yani AGPL-3.0 projesiyle uyumlu ve **paketlenebilirler**.
Yaklaşık maliyet: subset edilmiş Latin seti için ~40 MB.

Yapılacaklar (onay sonrası):
1. Font dosyalarını `assets/fonts/` altına al, lisans metinlerini yanlarına koy
2. `fontTools.subset` ile Latin + Latin Extended-A'ya indir
3. Spec dosyasının `datas` listesine ekle
4. `FontRegistry`'nin arama yoluna paketlenmiş dizini **sistem fontlarından önce** koy

---

## CI

`.github/workflows/ci.yml` üç platformda test ve lint çalıştırır, Windows'ta ayrıca yapıyı
derleyip artefakt olarak yükler.

**Maliyet uyarısı:** GitHub Actions'ta macOS koşucuları Linux'un 10 katı dakika harcar. Herkese
açık depolarda ücretsiz, özel depolarda pahalı. Depo özel kalacaksa macOS işini sadece etiket
(tag) push'larında çalıştır.

---

## Durum özeti

| | |
|---|---|
| Windows yapısı | ✅ derleniyor, imzasız |
| macOS yapısı | ⬜ Apple Developer hesabı gerekiyor |
| Linux yapısı | ⬜ AppImage/Flatpak paketleme yazılmadı |
| Kod imzalama | ⬜ sertifika kararı bekliyor |
| Font paketleme | ⬜ onay bekliyor |
| Otomatik güncelleme | ⬜ Faz 2 |
