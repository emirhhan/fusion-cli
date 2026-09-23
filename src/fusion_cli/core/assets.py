"""Görsel asset dosyalarını ve yeniden üretilebilir lisans kaydını doğrular."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MANIFEST_NAMES = ("ASSETS.json", "assets.json", "asset-manifest.json", "LICENSES.json")


@dataclass(frozen=True, slots=True)
class ImageAssetInspection:
    path: Path
    format: str
    width: int
    height: int
    bytes: int
    findings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.findings


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            return None
        length = struct.unpack(">H", data[offset : offset + 2])[0]
        if length < 2 or offset + length > len(data):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB}:
            if length < 7:
                return None
            height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
            return width, height
        offset += length
    return None


def inspect_image_asset(path: Path) -> ImageAssetInspection:
    """PNG/JPEG başlığını, uzantıyı ve placeholder boyutunu bağımsız denetle."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return ImageAssetInspection(path, "", 0, 0, 0, (f"görsel okunamadı: {exc}",))
    findings: list[str] = []
    image_format = ""
    dimensions: tuple[int, int] | None = None
    if data.startswith(_PNG_SIGNATURE) and len(data) >= 24 and data[12:16] == b"IHDR":
        image_format = "png"
        dimensions = struct.unpack(">II", data[16:24])
    else:
        dimensions = _jpeg_dimensions(data)
        if dimensions is not None:
            image_format = "jpeg"
    if not data:
        findings.append("görsel dosyası boş")
    elif dimensions is None:
        findings.append("PNG veya JPEG başlığı geçersiz")
    expected_suffixes = {"png": {".png"}, "jpeg": {".jpg", ".jpeg"}}
    if image_format and path.suffix.casefold() not in expected_suffixes[image_format]:
        findings.append(f"görsel biçimi ile dosya uzantısı uyuşmuyor: {image_format}")
    width, height = dimensions or (0, 0)
    if width == 1 and height == 1:
        findings.append("1x1 placeholder görsel gerçek asset sayılmaz")
    elif dimensions is not None and (width <= 0 or height <= 0):
        findings.append("görsel boyutları geçersiz")
    return ImageAssetInspection(path, image_format, width, height, len(data), tuple(findings))


#: Manifestin belge düzeyinde taşıdığı, tüm dosyalar için geçerli alanlar.
_BELGE_ALANLARI = ("source_url", "source", "license", "author", "attribution")


def _document_level_entries(raw: dict[str, object]) -> dict[str, object] | None:
    """`{"source": …, "license": …, "files": [...]}` biçimini kayıtlara çevir.

    Tek bir paketten gelen dosyaların hepsi aynı kaynağı ve lisansı paylaşır ve
    model bunu doğal olarak BİR KEZ yazıyor. Ölçüldü (13 Eylül, Godot koşusu):
    OpenGameArt'tan indirilen paket için manifest tam bu biçimde yazıldı; katı
    okuma onu "geçersiz asset kaydı: source" diye reddetti, geri alma dosyayı
    sildi ve adım kurtarılamadı — oysa gereken bilgi (dosya listesi + ortak
    kaynak/lisans) manifestte eksiksiz duruyordu.

    Tolerans BİÇİMdedir: kaynak ya da lisans eksikse kayıtlar yine doğrulamada
    düşer, çünkü alanlar olduğu gibi taşınır.
    """
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        return None
    ortak = {
        # Kaynak alanı iki adla da yazılıyor; doğrulayıcı `source_url` bekler.
        ("source_url" if anahtar == "source" else anahtar): raw[anahtar]
        for anahtar in _BELGE_ALANLARI
        if isinstance(raw.get(anahtar), str)
    }
    kayitlar: dict[str, object] = {}
    for item in files:
        if isinstance(item, str):
            kayitlar[item] = dict(ortak)
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            kayitlar[str(item["path"])] = {**ortak, **item}
        else:
            return None
    return kayitlar


def _manifest_entries(raw: object) -> dict[str, object]:
    if isinstance(raw, list):
        return _asset_list_entries(raw)
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("assets"), dict):
        return cast("dict[str, object]", raw["assets"])
    if isinstance(raw.get("assets"), list):
        return _asset_list_entries(raw["assets"])
    belge = _document_level_entries(raw)
    if belge is not None:
        return belge
    return cast("dict[str, object]", raw)


def _asset_list_entries(items: list[object]) -> dict[str, object]:
    """Liste manifestlerinde `path` ve `file` alanlarını aynı dosya yolu say."""
    entries: dict[str, object] = {}
    for item in items:
        if not isinstance(item, dict):
            return {}
        path = item.get("path") or item.get("file")
        if not isinstance(path, str) or not path:
            return {}
        entries[path] = item
    return entries


def is_asset_inventory(path: Path) -> bool:
    """Salt lisans belgelerinden ayrı, dosya teslim envanteri adlarını tanı."""
    return path.name.casefold() in {"assets.json", "asset-manifest.json"}


def _resolve_asset_path(name: str, manifest: Path, root: Path) -> Path | None:
    """Manifestteki yolu diskteki dosyaya çöz; iki taban da denenir.

    Yol iki farklı ve ikisi de doğal olan konvansiyonla yazılıyor: manifestin
    bulunduğu klasöre göre (`Previews/grass.png`) ya da proje köküne göre
    (`assets/Previews/grass.png`). Ölçüldü (13 Eylül, Godot koşusu): Kenney
    paketi indirildi, 777 dosya açıldı ve manifest kök tabanlı yazıldı; tek
    tabanlı çözüm `assets/assets/Previews/grass.png` arayıp "dosya bulunamadı"
    dedi. Dosyalar diskte duruyordu ve adım kurtarılamadı.

    Var olan dosya tercih edilir; hiçbiri yoksa manifest tabanlı yol döner ki
    hata mesajı kullanıcının yazdığı yolu gösterebilsin.
    """
    adaylar: list[Path] = []
    for taban in (manifest.parent, root):
        try:
            adaylar.append((taban / name).resolve())
        except (OSError, ValueError, RuntimeError):
            continue
    if not adaylar:
        return None
    for aday in adaylar:
        try:
            if aday.is_file():
                return aday
        except OSError:
            continue
    return adaylar[0]


def _locate_by_name(file_name: str, root: Path) -> str | None:
    """Aynı ADLA proje içinde var olan dosyanın göreli yolu; yoksa None.

    Arşiv açıldıktan sonra manifest yolları elle yazılıyor ve bir segment
    kaybolabiliyor ya da iki kez yazılabiliyor. Dosya diskte durduğu hâlde
    "bulunamadı" demek, modeli yeniden indirmeye itiyor ve hakkını tüketiyor.
    """
    from .constants import SKIP_DIRECTORIES

    if not file_name:
        return None
    try:
        adaylar = sorted(root.rglob(file_name))
    except OSError:
        return None
    for aday in adaylar:
        if any(part in SKIP_DIRECTORIES or part.startswith(".") for part in aday.parts):
            continue
        try:
            if aday.is_file():
                return aday.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
    return None


def validate_asset_inventory(manifest: Path, root: Path) -> tuple[str, ...]:
    """Manifestin adını değil, bildirdiği gerçek dosyaları ve kaynakları doğrula."""
    try:
        entries = _manifest_entries(json.loads(manifest.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return ("asset manifesti okunamadı veya geçerli JSON değil",)
    if not entries:
        return ("asset manifesti gerçek dosya kaydı içermiyor",)
    findings: list[str] = []
    for name, entry in entries.items():
        if not name or not isinstance(entry, dict):
            # Hangi biçimin beklendiği SÖYLENİR: "geçersiz kayıt" mesajı, manifesti
            # belge düzeyinde yazan modele ne yapacağını göstermiyordu (ölçüldü:
            # 13 Eylül, Godot koşusu — dört alan da bu satırda reddedildi).
            findings.append(
                f"geçersiz asset kaydı: {name} — manifest ya "
                '{"<dosya yolu>": {"source_url": …, "license": …}} ya da '
                '{"source_url": …, "license": …, "files": ["<dosya yolu>", …]} '
                "biçiminde olmalı"
            )
            continue
        path = _resolve_asset_path(name, manifest, root)
        if path is None:
            findings.append(f"asset yolu çözümlenemedi: {name!r}")
            continue
        if path.name.casefold() in {item.casefold() for item in _MANIFEST_NAMES}:
            findings.append(f"manifest veya lisans belgesi teslim asseti değildir: {name}")
            continue
        if not path.is_relative_to(root.resolve()):
            findings.append(f"asset yolu çalışma kökü dışında: {name}")
            continue
        try:
            present = path.is_file() and path.stat().st_size > 0
        except OSError:
            present = False
        if not present:
            # Sıra söylenir: ölçüldü (13 Eylül, Godot koşusu) — model manifesti
            # İLK yazdı, hiç indirme yapmadı ve "manifest oluşturuldu" diye
            # bildirdi. Eksik olanı söylemek yetmiyor, YAPILACAĞI söylemek gerekiyor.
            gercek = _locate_by_name(Path(name).name, root)
            if gercek is not None:
                # Dosya VAR, yol yanlış. Ölçüldü (13 Eylül, Godot koşusu):
                # arşiv açıldıktan sonra manifest `assets/PNG/PNG/Player/...`
                # yazdı (bir segment iki kez); dosya `assets/PNG/Player/...`
                # altındaydı. "Bulunamadı" demek modele düzeltmeyi göstermiyordu
                # ve adım yeniden indirmeye kalkıp hakkını tüketti.
                findings.append(
                    f"manifestteki yol yanlış: {name} yok ama aynı adlı dosya "
                    f"{gercek} altında var. Manifestteki yolu buna göre düzelt; "
                    "yeniden indirmeye gerek yok."
                )
                continue
            findings.append(
                f"manifestteki gerçek asset dosyası bulunamadı veya boş: {name} "
                "(önce web_search + download_file ile indir, arşivse extract_archive "
                "ile aç, manifesti EN SON yaz)"
            )
            continue
        findings.extend(f"{name}: {item}" for item in validate_asset_manifest(path, root))
        if path.suffix.casefold() in {".png", ".jpg", ".jpeg"}:
            findings.extend(f"{name}: {item}" for item in inspect_image_asset(path).findings)
    return tuple(findings)


def _manifest_keys(path: Path, manifest: Path, root: Path) -> tuple[str, ...]:
    """Bu asset için manifestte aranacak anahtarlar, olasılık sırasıyla.

    Yol manifeste göre de (`Previews/grass.png`) köke göre de
    (`assets/Previews/grass.png`) yazılabiliyor; kayıt hangisiyle yazıldıysa
    onunla bulunmalı (bkz. `_resolve_asset_path`).
    """
    hedef = path.resolve()
    anahtarlar: list[str] = []
    for taban in (manifest.parent.resolve(), root):
        try:
            anahtarlar.append(hedef.relative_to(taban).as_posix())
        except ValueError:
            continue
    anahtarlar.append(path.name)
    return tuple(dict.fromkeys(anahtarlar))


def validate_asset_manifest(path: Path, root: Path) -> tuple[str, ...]:
    """Asset için proje içinde kaynak URL'si ve lisans kaydı ara."""
    resolved_root = root.resolve()
    current = path.resolve().parent
    manifests: list[Path] = []
    while current.is_relative_to(resolved_root):
        manifests.extend(current / name for name in _MANIFEST_NAMES if (current / name).is_file())
        if current == resolved_root:
            break
        current = current.parent
    if not manifests:
        return ("görsel asset için ASSETS.json lisans manifesti bulunamadı",)
    for manifest in manifests:
        try:
            entries = _manifest_entries(json.loads(manifest.read_text(encoding="utf-8")))
            anahtarlar = _manifest_keys(path, manifest, resolved_root)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        entry = next(
            (entries[anahtar] for anahtar in anahtarlar if isinstance(entries.get(anahtar), dict)),
            None,
        )
        if not isinstance(entry, dict):
            continue
        source = entry.get("source_url")
        license_name = entry.get("license")
        parsed = urlparse(source) if isinstance(source, str) else None
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return (f"{manifest.name} kaydında geçerli source_url yok",)
        if not isinstance(license_name, str) or not license_name.strip():
            return (f"{manifest.name} kaydında lisans yok",)
        return ()
    return ("görsel asset lisans manifestinde kayıtlı değil",)


#: "İndirildi ama kullanılmadı" bulgusunun değişmez öneki.
#
# Motor katmanı bu işarete bakarak onarılacak adımı seçer; metin iki yerde ayrı
# yazılırsa sessizce ayrışır (bkz. `FILE_MISSING_PREFIX` ile aynı gerekçe).
UNUSED_ASSETS_PREFIX = "indirilen varlıklar üründe HİÇ kullanılmamış:"


#: Üründe gerçekten KULLANILABİLİR varlık uzantıları.
#
# Lisans metni, yönerge kısayolu ve paket dokümanı teslim varlığı değildir; onların
# koddan referanslanmasını beklemek anlamsızdır.
_USABLE_ASSET_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ogg", ".wav", ".mp3", ".ttf", ".otf"}
)


#: Varlık referansı aranacak kaynak dosya uzantıları.
#
# Liste dar tutulur: kaynak ve sahne dosyaları. İkili dosyalarda metin aramak
# anlamsız, manifest ve lisans belgelerinde ise referans bulmak yanıltıcı olur —
# manifest zaten dosyayı listeler, onu "kullanım" saymak kapıyı işlevsiz kılar.
_REFERENCE_SUFFIXES = frozenset(
    {
        ".gd", ".tscn", ".tres", ".cs", ".gdshader", ".json",
        ".py", ".js", ".ts", ".tsx", ".html", ".css", ".lua", ".cpp", ".h",
    }
)  # fmt: skip

#: Taramadan DIŞLANAN yapılandırma dosyaları.
#
# Ölçüldü (13 Eylül, koşu 26): üretilen oyunda tek varlık referansı
# `project.godot` içindeki `config/icon="res://Preview.png"` satırıydı. Kapı bunu
# "sanat ürüne girdi" saydı ve sahnede tek sprite olmayan bir projeyi geçirdi.
# Pencere ikonu oyunun içeriği değildir; referans sahnede ya da kodda olmalı.
_CONFIG_FILE_NAMES = frozenset({"project.godot", "export_presets.cfg", "default_env.tres"})

#: Referans taramasında atlanan dosya adları (manifest/lisans belgeleri).
_REFERENCE_SKIP_NAMES = frozenset(item.casefold() for item in _MANIFEST_NAMES)


def unused_manifest_assets(manifest: Path, root: Path) -> tuple[str, ...]:
    """Manifestte bildirilen ama PROJE KODUNDA hiç anılmayan varlıklar.

    İndirmek kullanmak değildir. Ölçüldü (13 Eylül, Godot koşusu): Kenney Pixel
    Platformer indirildi, 252 dosya açıldı, manifest doğru yazıldı ve plan
    "tamamlandı" raporladı — ama üretilen sahnede TEK BİR sprite yoktu, oyun
    HealthBar ve Label'lardan oluşuyordu. Kullanıcının isteği ("assetsiz hiçbir
    şey istemiyorum") tam olarak bu sonucu dışlıyordu.

    Referans, dosya adının kaynak/sahne dosyalarında geçmesidir. Kasıtlı olarak
    kabadır: amaç "doğru kullanılmış mı" demek değil, HİÇ kullanılmamış varlığı
    yakalamaktır. Tilemap/atlas gibi tek dosyanın yüzlerce karoyu taşıdığı
    durumlarda da doğru çalışır — atlas dosyası anılmışsa kullanılmış sayılır.
    """
    entries = _manifest_entries(_read_json(manifest))
    if not entries:
        return ()
    metin = _project_text(root)
    if not metin:
        return ()
    varliklar = [
        name
        for name in entries
        if isinstance(name, str)
        and name
        and Path(name).suffix.casefold() in _USABLE_ASSET_SUFFIXES
    ]
    if not varliklar:
        return ()
    kullanilmayan = [name for name in varliklar if Path(name).name.casefold() not in metin]
    if len(kullanilmayan) < len(varliklar):
        # EN AZ BİR varlık üründe anılıyor: paket gerçekten kullanılmış.
        #
        # Ölçüldü (13 Eylül, Godot koşusu): manifest paketin tamamını listeledi ve
        # kapı `License.txt`, `Sample.png`, `Tilesheet.txt` gibi belge/önizleme
        # dosyalarının "kullanılmadığını" söyleyip bitmiş bir oyunu reddetti. Bir
        # paketin her dosyasının kullanılması ne mümkün ne gereklidir; sorulan soru
        # "indirilen sanat ürüne girdi mi" sorusudur.
        return ()
    return tuple(sorted(kullanilmayan))


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _project_text(root: Path) -> str:
    """Projedeki kaynak ve sahne dosyalarının birleşik, küçük harfe indirilmiş metni."""
    from .constants import SKIP_DIRECTORIES

    parcalar: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.casefold() not in _REFERENCE_SUFFIXES:
            continue
        if path.name.casefold() in _REFERENCE_SKIP_NAMES:
            continue
        if path.name.casefold() in _CONFIG_FILE_NAMES:
            continue
        # Gizli dizinler taranmaz: devam kaydı (`.fusion`), git verisi ve araç
        # önbellekleri projenin kodu değildir ve içlerindeki JSON, kullanım
        # kanıtı sayılamaz — testte `.cp/` altındaki checkpoint dosyaları kapıyı
        # yanlış tarafa düşürdü.
        if any(part in SKIP_DIRECTORIES or part.startswith(".") for part in path.parts):
            continue
        try:
            parcalar.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parcalar).casefold()
