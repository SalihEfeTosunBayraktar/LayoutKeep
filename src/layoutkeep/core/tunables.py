"""Runtime-adjustable parameters.

Numbers that used to be module constants and could only be changed by editing the source and
restarting. Some of them are genuinely machine-dependent - how long a cold model takes to
load, how many segments an endpoint will accept - so the right value is not something this
project can pick once for everyone.

Two rules make this safe to have:

  * **Read at use, not at import.** A call site must call `get()` when it needs the value.
    Binding it to a module-level name again would restore exactly the restart-to-apply
    behaviour this replaces.
  * **The default stays the constant.** Every tunable's default is the value the code shipped
    with, so an untouched installation behaves identically and `reset_all()` is a real escape
    hatch.

Qt-free on purpose: the CLI reads the same overrides as the desktop app, so the two cannot
drift into behaving differently on the same machine.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Which screen a tunable belongs on. `ADVANCED` entries are ones where a wrong value produces
#: quietly worse output rather than an obvious error, so they carry a warning and live behind a
#: developer section.
BASIC = "basic"
ADVANCED = "advanced"


@dataclass(frozen=True, slots=True)
class Tunable:
    key: str
    label: str
    default: Any
    #: "int" | "float" | "bool"
    kind: str
    section: str = BASIC
    minimum: float | None = None
    maximum: float | None = None
    help_text: str = ""
    #: Shown next to advanced entries. Says what goes wrong, not merely "be careful".
    warning: str = ""
    #: Heading this entry sits under in the dialog. Entries sharing one are shown together;
    #: an empty group means "no heading", which is how the list read before there were enough
    #: entries to need any.
    group: str = ""


TUNABLES: tuple[Tunable, ...] = (
    # -- basic -------------------------------------------------------------
    Tunable(
        key="batch.chunk_size",
        label="Parti boyutu (iptal/duraklat aralığı)",
        default=20,
        kind="int",
        minimum=1,
        maximum=200,
        help_text=(
            "Worker'ın sağlayıcıya bir seferde verdiği segment sayısı. İstek boyutu değildir - "
            "sağlayıcı kendi istek boyutunu ayrıca uyarlar. Küçültmek iptal ve duraklatmayı "
            "daha çabuk hissettirir, büyütmek istek sayısını azaltır."
        ),
    ),
    Tunable(
        key="timeout.first_batch_s",
        label="İlk parti zaman aşımı (sn)",
        default=240.0,
        kind="float",
        minimum=10.0,
        maximum=3600.0,
        help_text=(
            "Soğuk bir yerel model ilk yanıtı vermeden önce dakikalarca yüklenebilir. "
            "Büyük modellerde bunu yükseltin."
        ),
    ),
    Tunable(
        key="timeout.warm_batch_s",
        label="Sonraki parti zaman aşımı (sn)",
        default=15.0,
        kind="float",
        minimum=5.0,
        maximum=600.0,
        help_text="Model yüklendikten sonraki partiler için taban süre; metin uzunluğuna göre artar.",
    ),
    Tunable(
        key="preview.keep_segments",
        label="Canlı önizlemede tutulan segment",
        default=40,
        kind="int",
        minimum=5,
        maximum=500,
        help_text="İlerleme ekranındaki yan yana görünümde kaç segment saklanacağı.",
    ),
    Tunable(
        key="deepl.max_texts_per_request",
        label="DeepL: istek başına metin",
        default=40,
        kind="int",
        minimum=1,
        maximum=50,
        help_text="DeepL istek başına en fazla 50 metin kabul eder.",
    ),
    # -- advanced ----------------------------------------------------------
    Tunable(
        key="batch.adaptive_max_segments",
        label="Uyarlanabilir parti tavanı",
        default=20,
        kind="int",
        section=ADVANCED,
        group="Parti ve istek",
        minimum=1,
        maximum=100,
        help_text="Sağlayıcının tek istekte deneyebileceği en fazla segment sayısı.",
        warning=(
            "Ölçüldü: denenen modellerin hiçbiri tek JSON dizisinde 6 segmenti eksiksiz "
            "döndüremedi. Sağlayıcı bozuk yanıtta küçülerek kendini toparlar, ama bu değeri "
            "yükseltmek boşa giden istek demektir."
        ),
    ),
    Tunable(
        key="passthrough.min_words",
        label="Geçirme tespiti: en az kelime",
        default=4,
        kind="int",
        section=ADVANCED,
        group="Çeviri denetimi",
        minimum=1,
        maximum=50,
        help_text="Bu kadar veya daha uzun bir metin aynen geri gelirse çevrilmemiş sayılır.",
        warning=(
            "Düşürmek yanlış alarm üretir: başlıklar, isimler ve kodlar doğru olarak "
            "kendileriyle aynı çevrilir. Yükseltmek gerçek geçirmeleri kaçırır."
        ),
    ),
    Tunable(
        key="fit.min_scale",
        label="En küçük yazı tipi ölçeği",
        default=0.85,
        kind="float",
        section=ADVANCED,
        group="Sığdırma",
        minimum=0.5,
        maximum=1.0,
        help_text="Çeviri kutuya sığmazsa yazı tipi bu orana kadar küçültülür.",
        warning=(
            "Çok düşürmek metni okunmaz hale getirir ve sığmayan bir çeviriyi sığmış gibi "
            "gösterir - inceleme bayrağı kalkmaz, sorun görünmez olur."
        ),
    ),
    Tunable(
        key="ocr.needs_review_threshold",
        label="OCR inceleme eşiği",
        default=0.80,
        kind="float",
        section=ADVANCED,
        group="OCR",
        minimum=0.0,
        maximum=1.0,
        help_text="Bu güvenin altındaki OCR blokları incelenmek üzere işaretlenir.",
        warning="Düşürmek şüpheli OCR metnini sessizce kabul eder.",
    ),
    Tunable(
        key="table.cell_overlap_ratio",
        label="Tablo: hücre örtüşme oranı",
        default=0.35,
        kind="float",
        section=ADVANCED,
        group="Tablo tanıma",
        minimum=0.05,
        maximum=0.95,
        help_text=(
            "Bir bloğun satırları yan yana mı duruyor yoksa alt alta mı? Yatay örtüşmeleri "
            "dar olanın bu kesrinden azsa ayrı hücre sayılırlar."
        ),
        warning=(
            "Ölçüldü: tablo başlık satırı PDF'ten tek blok olarak gelir. Yükseltmek satırı "
            "yeniden tek hücreye çöktürür - çeviri ilk hücreye yazılır, kalanlar boş kalır. "
            "Düşürmek sarmalanmış paragraf satırlarını hücre sanıp paragrafı böler."
        ),
    ),
    Tunable(
        key="table.row_overlap_ratio",
        label="Tablo: satır örtüşme oranı",
        default=0.6,
        kind="float",
        section=ADVANCED,
        group="Tablo tanıma",
        minimum=0.1,
        maximum=1.0,
        help_text="İki hücrenin aynı satırda sayılması için yüksekliklerinin örtüşmesi gereken kesir.",
        warning=(
            "Düşürmek 0.5 punto'luk örtüşmelerin satırları birbirine zincirlemesine yol açar: "
            "iki ayrı tablo tek bir bandda birleşir ve ikisi de tanınmaz."
        ),
    ),
    Tunable(
        key="table.column_align_ratio",
        label="Tablo: sütun hizalama payı",
        default=1.2,
        kind="float",
        section=ADVANCED,
        group="Tablo tanıma",
        minimum=0.2,
        maximum=5.0,
        help_text=(
            "İki hücrenin aynı sütunda sayılması için sol kenarları, satır yüksekliğinin bu "
            "katı kadar yaklaşık olmalı."
        ),
        warning=(
            "Yükseltmek ilgisiz blokları sütun sanıp paragrafları tablo gibi dondurur; "
            "düşürmek gerçek tabloları kaçırır ve satırlar tekrar tek bloğa birleşir."
        ),
    ),
    Tunable(
        key="table.height_similarity",
        label="Tablo: yükseklik benzerliği",
        default=1.6,
        kind="float",
        section=ADVANCED,
        group="Tablo tanıma",
        minimum=1.0,
        maximum=5.0,
        help_text="Aynı satırdaki hücrelerin yükseklikleri en fazla bu katı kadar farklı olabilir.",
        warning="Yükseltmek başlık ile gövde metnini aynı tablo satırında birleştirir.",
    ),
    Tunable(
        key="merge.line_gap_ratio",
        label="Satır birleştirme: boşluk oranı",
        default=0.6,
        kind="float",
        section=ADVANCED,
        group="Satır ve paragraf birleştirme",
        minimum=0.0,
        maximum=3.0,
        help_text=(
            "İki blok, aralarındaki boşluk punto boyutunun bu katından küçükse aynı "
            "paragrafın ardışık satırları sayılır."
        ),
        warning=(
            "Düşürmek çok satırlı bir başlığı satır satır çevirtir - her satır kendi cümlesi "
            "sanılır ve dilbilgisi bozulur. Yükseltmek ayrı paragrafları birbirine yapıştırır."
        ),
    ),
    Tunable(
        key="merge.line_height_ratio",
        label="Satır birleştirme: satır yüksekliği katsayısı",
        default=1.2,
        kind="float",
        section=ADVANCED,
        group="Satır ve paragraf birleştirme",
        minimum=0.8,
        maximum=2.5,
        help_text=(
            "Döndürülmüş bir satırın merkezinden kenarlarına gitmek için punto boyutunun "
            "çarpıldığı katsayı. Yazıcının satırları geri istiflerken varsaydığı değerle aynı."
        ),
        warning="Değiştirmek yalnızca döndürülmüş metni etkiler; yatay metin bundan etkilenmez.",
    ),
    Tunable(
        key="merge.rotation_eps_deg",
        label="Aynı açı toleransı (derece)",
        default=0.5,
        kind="float",
        section=ADVANCED,
        group="Satır ve paragraf birleştirme",
        minimum=0.0,
        maximum=10.0,
        help_text=(
            "Bu farktan az açı farkı olan bloklar aynı açıda kabul edilir; daha fazlası "
            "\"farklı açı, aynı paragraf değil\" demektir."
        ),
        warning=(
            "Yükseltmek yelpaze gibi dizilmiş ayrı etiketleri tek paragrafa toplar."
        ),
    ),
    Tunable(
        key="write.box_slack_pt",
        label="Kutuya verilen pay (punto)",
        default=3.0,
        kind="float",
        section=ADVANCED,
        group="Yazma",
        minimum=0.0,
        maximum=12.0,
        help_text=(
            "Okuyucunun ölçtüğü kutu gliflere tam oturur; PDF'e yazan motor ise kendi iç "
            "boşluğu için biraz daha yer ister. Metin kutusuna sığmadığında sağına ve altına "
            "bu kadar punto eklenip bir kez daha denenir."
        ),
        warning=(
            "Ölçüldü: 6 punto'luk bir grafik ekseni etiketi bu pay olmadan 4.4 punto'ya kadar "
            "küçülüyordu - hiç çevrilmemiş sayılar bile. Sıfırlamak o küçülmeyi geri getirir; "
            "çok yükseltmek bir bloğun komşusunun üzerine taşmasına yol açabilir."
        ),
    ),
    Tunable(
        key="redact.coverage_ratio",
        label="Silme kapsama oranı",
        default=0.6,
        kind="float",
        section=ADVANCED,
        group="Kaynak metni silme",
        minimum=0.1,
        maximum=1.0,
        help_text=(
            "Döndürülmüş bir satırın altında bulunan parçalar, satırın kendi kutusunun bu "
            "kesrini kaplamıyorsa satır yeniden aranır."
        ),
        warning=(
            "Ölçüldü: eşleşemeyen bir karakter (sembol fontundan gelen kesme işareti gibi) "
            "satırı parçalara böler. Düşürmek kaynak metnin çevirinin altında görünür "
            "kalmasına yol açar - ikisi üst üste okunur."
        ),
    ),
    Tunable(
        key="http.max_retry_after_s",
        label="Retry-After üst sınırı (sn)",
        default=60.0,
        kind="float",
        section=ADVANCED,
        group="Ağ",
        minimum=1.0,
        maximum=600.0,
        help_text="Sunucu 'şu kadar bekle' derse en fazla bu kadar beklenir.",
        warning="Yükseltmek uygulamayı donmuş gibi gösterebilir.",
    ),
)

_BY_KEY: dict[str, Tunable] = {t.key: t for t in TUNABLES}

#: Values differing from the defaults. Empty for a fresh installation.
_overrides: dict[str, Any] = {}

#: Where overrides are stored. Environment variable first so a test run, a CI job or a
#: portable build can point it somewhere harmless.
_ENV_PATH = "LAYOUTKEEP_TUNABLES"


def definitions(section: str | None = None) -> list[Tunable]:
    if section is None:
        return list(TUNABLES)
    return [t for t in TUNABLES if t.section == section]


def definition(key: str) -> Tunable:
    return _BY_KEY[key]


def get(key: str) -> Any:
    """The value in force, override first. Call this where the value is used."""
    if key in _overrides:
        return _overrides[key]
    return _BY_KEY[key].default


def _coerce(spec: Tunable, value: Any) -> Any:
    if spec.kind == "bool":
        return bool(value)
    number = float(value)
    if spec.minimum is not None:
        number = max(spec.minimum, number)
    if spec.maximum is not None:
        number = min(spec.maximum, number)
    return round(number) if spec.kind == "int" else number


def set_value(key: str, value: Any) -> Any:
    """Override a tunable, clamped to its range. Returns the value actually stored.

    Clamping rather than raising is deliberate: this is fed by a settings dialog, and a value
    outside the range means the user wanted the extreme, not that the program should stop.
    """
    spec = _BY_KEY[key]
    coerced = _coerce(spec, value)
    if coerced == spec.default:
        _overrides.pop(key, None)
    else:
        _overrides[key] = coerced
    return coerced


def reset(key: str) -> None:
    _overrides.pop(key, None)


def reset_all() -> None:
    _overrides.clear()


def overrides() -> dict[str, Any]:
    return dict(_overrides)


def is_overridden(key: str) -> bool:
    return key in _overrides


def storage_path() -> Path:
    from_env = os.environ.get(_ENV_PATH)
    if from_env:
        return Path(from_env)
    from layoutkeep.core.paths import data_dir

    return data_dir() / "tunables.json"


def load(path: str | Path | None = None) -> None:
    """Read stored overrides. A missing or unreadable file leaves the defaults in place."""
    target = Path(path) if path else storage_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        if key in _BY_KEY:
            try:
                set_value(key, value)
            except (TypeError, ValueError):
                # A stored value that no longer makes sense for this build is dropped rather
                # than taking the whole settings file down with it.
                continue


def save(path: str | Path | None = None) -> Path:
    target = Path(path) if path else storage_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_overrides, indent=2, sort_keys=True), encoding="utf-8")
    return target
