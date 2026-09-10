# Ölçümler

Bu belge, projede **tahmin yerine ölçüme** dayandırdığımız sayıları ve nasıl elde edildiklerini
tutar. Tekrarlanabilir olsun diye komutlar da burada.

Donanım: RTX 4070 Laptop (8188 MiB VRAM), Ryzen 7 8845HS, 32 GB RAM, Windows 11.
Sunucu: LM Studio, llama.cpp CUDA arka ucu.

---

## 1. EN→TR genleşme oranı — **0.93x**

**Fizibilitede 1.15x varsayılmıştı. Ölçüm bunu çürüttü.**

| | |
|---|---|
| Örneklem | 40 segment, 9562 karakter |
| Kaynak | Alice in Wonderland (Project Gutenberg #11), kitabın ortasından düzyazı |
| Model | `google/gemma-4-e4b`, Q4_K_M, 8K bağlam |
| **Ağırlıklı oran** | **0.931x** |
| Medyan | 0.933x |
| Aralık | 0.64x – 1.40x |
| 1.00x üstünde | 10/40 blok |

Türkçe eklemeli bir dil: İngilizcenin birkaç kelimeyle kurduğu yapıyı tek kelimeye sığdırabiliyor
(`that it had fallen` → `düştüğü`). Metin genişlemek yerine kısalıyor.

**Ama ortalama tek başına yanıltıcı.** Bloklar 0.64x ile 1.40x arasında dağılıyor; ortalama
küçülse de azınlık bloklar hâlâ %40 büyüyebiliyor. Yani sığdırma motoru gereksiz değil —
tasarım gerekçesi değişti: **sistematik genleşme sorunu değil, değişkenlik sorunu.**

### Bu ölçümün sınırları
Tek kitap, tek tür (bol diyaloglu Viktorya dönemi çocuk edebiyatı), tek model. Teknik
dokümantasyon veya hukuki metin farklı davranabilir; daha ayrıntılı bir model daha uzun
çevirebilir. Başka bir tür veya modelle çalışacaksan yeniden ölç.

```powershell
# 8 parti x 5 segment
foreach ($off in 150,155,160,165,170,175,180,185) {
  .venv\Scripts\python.exe -m layoutkeep.cli translate _artifacts\corpus\pg11.epub `
    --to tr --from en --model "google/gemma-4-e4b" --skip $off --limit 5 `
    --memory _artifacts\exp.sqlite -o "_artifacts\output\exp_$off.epub"
}
```

---

## 2. Parti boyutu — **5 çalışıyor, 6 kırılıyor**

İstemimiz modelden numaralandırılmış JSON istiyor. Küçük yerel modeller uzun ve kusursuz biçimli
bir diziyi bir arada tutamıyor.

`google/gemma-4-e4b` ile aynı pasajda:

| Parti | Dönen | Süre |
|---|---|---|
| 1 | 1/1 ✅ | 32.7 sn |
| 2 | 2/2 ✅ | 37.3 sn |
| 3 | 3/3 ✅ | 42.2 sn |
| 4 | 4/4 ✅ | 44.7 sn |
| 5 | 5/5 ✅ | 60.1 sn |
| **6** | **3/6 ❌** | **341 sn** |

Maliyet istek başına sabit ek yükte yoğunlaşıyor, segment sayısında değil: beşli parti, beş tekil
istekten 2.7 kat verimli. Altılı parti sadece başarısız olmuyor, 8 kat da yavaşlıyor.

---

## 3. Model karşılaştırması

Aynı altı segment, aynı koşullar. **Çeviri kalitesi tek kriter değil** — istemimiz yapılandırılmış
çıktı gerektiriyor ve çeviriye özel eğitilmiş modeller bunda zayıf çıktı.

| Model | Dönen | Süre | Türkçe kalitesi |
|---|---|---|---|
| `noesis-qwopus3.5-9b-translate` | 1/6 | 419 sn | — |
| `qwen3.8_4b_distilled` | 5/6 | 57 sn | Kötü (`Rabbit`→`Kaplumbağa`) |
| **`google/gemma-4-e4b`** | 3/6 | 341 sn | **İyi (`Rabbit`→`Tavşan`)** |
| `qwen3.8-14b-instruct-turbo` | 0/6 | 311 sn | — |

Altılı parti hepsini zorladı; beşli partide `gemma-4-e4b` 40/40 yaptı.

Aynı modellerin LayoutKeep'in gerçek tel protokolünde (JSON segment dizisi + `<N>` marker +
korunan değer token'ı) güncel ölçümü: `tools/bench_protocol.py` + `tools/bench_chart.py`
(bkz. `_artifacts/benchmark_report.html`).

---

## 4. VRAM — sorun model boyutu değil, bağlam ayarıydı

LM Studio modelleri **262144 token bağlam ve 4 paralel yuvayla** yüklüyordu. Model ağırlığı
5.63 GB olmasına rağmen KV önbelleği VRAM'i doldurup CPU'ya taşmaya zorluyordu.

| Durum | Kullanılan | Boş |
|---|---|---|
| 9B, 262144 bağlam | 7295 MiB | 654 MiB |
| Model boşaltıldı | 755 MiB | 7194 MiB |
| 9B, 8192 bağlam, tam GPU | 6131 MiB | 1818 MiB |

8K bağlamda `lms load --estimate-only` ile gerçek ihtiyaçlar:

| Model | GPU belleği |
|---|---|
| `qwen3.8_4b@q4` | 2.33 GiB |
| `noesis-9b-translate` | 5.24 GiB |
| `google/gemma-4-e4b` | 5.89 GiB |
| `qwen3.8-14b-turbo` | 6.37 GiB |
| 27B'ler | 10–11 GiB ❌ |

**Modeli her zaman açık bağlam uzunluğuyla yükle:**

```powershell
lms load "google/gemma-4-e4b" --context-length 8192 --parallel 1 --gpu max -y
```

`translategemma-4b-it` VRAM boşken bile yüklenmiyor (`llama-server` çöküyor) — görüntü yetenekli
bir Gemma 3 GGUF'u, muhtemelen projeksiyon dosyası eksik.

---

## 5. Hız

`gemma-4-e4b`, 8K bağlam, tam GPU offload, beşerlik partiler: **segment başına ~12 sn.**

826 segmentlik bir kitap (147k karakter) kabaca **2.5–3 saat** eder. Çeviri belleği tekrar eden
metni atladığı için gerçek süre bunun altında kalır. Bu boyuttaki işler için toplu işleme ve
gece çalıştırma gerekiyor; etkileşimli kullanım için değil.

## 6. Bağlam ve tutarlılık — **ölçüldü, karar verilmedi**

`context_before` / `context_after` en baştan beri gönderiliyordu ve prompt'u kabaca üçe
katlıyor. Hiç ölçülmemişti.

`tools/coherence_check.py`, pg11.epub, 2 pasaj x 60 segment, gemma-4-e2b. Bir terimin
karşılığı, o terimi içeren segmentlerin hedeflerini içermeyenlerle karşılaştırarak bulunuyor;
üç kol da **aynı terim kümesi** üzerinden puanlanıyor (83 terim).

| kol | tutarlı |
|---|---|
| bağlamlı | 6/83 (%7) |
| bağlamsız | 12/83 (%14) |
| parti=1 | 7/83 (%8) |

Mutlak oranlar düşük çünkü ölçüt katı: bir karşılığın, terimin geçtiği *her* segmentte
görünmesi gerekiyor. Kolları karşılaştırmak için kullanılabilir, tek başına "çeviri %7 tutarlı"
diye okunamaz.

### Asıl bulgu: sessiz geçirme

Aday listelerinde sadece bağlamlı kolda İngilizce kelimeler çıktı (`such -> would, like, she`).
Aynı pasajda doğrudan ölçüldü:

| model | bağlamlı | bağlamsız |
|---|---|---|
| gemma-4-e2b | **10/60 segment çevrilmeden aynen döndü** | 0/60, 60/60 çevrildi |
| gemma-4-e4b | 0/60, 60/60 çevrildi | **sadece 40/60 çevrildi** |

İki model zıt yönde bozuluyor. **Bu yüzden bağlam kaldırılmadı** - ilk sonuca dayanarak karar
vermek yanlış olurdu.

Ortak nokta şu: `Segment.translated` sadece `bool(target)` olduğu için, kaynağını aynen geri
veren bir cevap başarılı çeviri sayılıyor ve çevrilmemiş İngilizce belgeye yazılıyordu.
`providers/passthrough.py` bunu yakalıyor (bkz. 3adee52).

### Tekrarlamak için

```
.venv/Scripts/python.exe tools/coherence_check.py --model google/gemma-4-e2b --limit 60 --dump out.json
```

### Bu ölçümün sınırları

Tek dil çifti, tek kitap, iki model, iki pasaj. Edebi düzyazı - teknik belgede terim tutarlılığı
farklı davranabilir. Ölçüt Türkçe'yi 5 karakterlik gövdelerle yaklaşıklıyor, çekim ekleri
yüzünden doğru çeviriyi tutarsız sayabilir; bu yüzden kollar arası fark anlamlı, mutlak oran
değil.
