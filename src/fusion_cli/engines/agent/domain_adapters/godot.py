"""Godot alanı — motorun kendisi projeyi açabiliyor mu, hata basıyor mu?

Ölçüldü (5-6 Eylül): Godot bozuk script'te ve çalışma zamanı hatasında `0` çıkış
kodu verebiliyor; "açıldı" ile "hatasız açıldı" ayrı şeylerdir. Bu modül Godot'a
özgü tüm kanıt bilgisini tek yerde tutar; motor bu adları hiç bilmez.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from ....core.constants import SKIP_DIRECTORIES
from .contract import DomainAdapter

#: `project.godot` içinde ana sahneyi tanımlayan anahtar.
_MAIN_SCENE = re.compile(r"^\s*run/main_scene\s*=\s*\S")
_SECTION = re.compile(r"^\s*\[")

#: Godot'un içe aktarma gerektiren görsel/ses/3B/yazı tipi uzantıları.
#
# Ölçüldü (30 Ekim): küme yalnız 2B görsel ve sesi kapsıyordu; Meshy→Blender→Godot
# zincirinin `.glb/.gltf/.obj/.fbx` varlıkları, `.svg`, yazı tipleri ve HDR/EXR dokular
# `.import`suz kalınca `load()` çalışma anında düşüyor ama içe aktarma hiç tetiklenmiyordu.
_GODOT_IMPORTED_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tga",
        ".svg",
        ".exr",
        ".hdr",
        ".ogg",
        ".wav",
        ".mp3",
        ".glb",
        ".gltf",
        ".obj",
        ".fbx",
        ".dae",
        ".ttf",
        ".otf",
    }
)


#: Godot'nun macOS uygulama paketindeki çalıştırılabilir dosyalar (PATH'te olmayabilir).
GODOT_APP_BUNDLES = (
    Path("/Applications/Godot.app/Contents/MacOS/Godot"),
    Path("/Applications/Godot_mono.app/Contents/MacOS/Godot"),
    Path.home() / "Applications" / "Godot.app" / "Contents" / "MacOS" / "Godot",
)


def find_godot_executable(
    environ: Mapping[str, str] | None = None,
    *,
    which: Callable[[str], str | None] | None = None,
    bundles: Iterable[Path] | None = None,
) -> str | None:
    """Godot yürütülebilirini bul: `GODOT_BIN` → PATH'te `godot` → uygulama paketi.

    Ölçüldü (30 Ekim, E1-10): kapı komutu hep literal `godot`'tu; macOS'ta Godot çoğu
    kurulumda PATH'te değildir ve kapı "command not found" (127) ile doğrulanamıyordu.
    Bulunamazsa None döner (komut olduğu gibi kalır, 127 zaten "doğrulanamadı" sayılır).
    `GODOT_BIN` geçersizse (dosya değil / çalıştırılamaz) atlanır.
    """
    env = os.environ if environ is None else environ
    custom = env.get("GODOT_BIN", "").strip()
    if custom and _is_executable_file(Path(custom).expanduser()):
        return str(Path(custom).expanduser())
    on_path = (which or shutil.which)("godot")
    if on_path:
        return on_path
    for bundle in GODOT_APP_BUNDLES if bundles is None else bundles:
        if _is_executable_file(bundle):
            return str(bundle)
    return None


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _godot_gate_executable() -> str | None:
    """Kapı komutunda kullanılacak yol; PATH'teki `godot` ise adı olduğu gibi kalır."""
    found = find_godot_executable()
    return "godot" if found is not None and found == shutil.which("godot") else found


def godot_has_main_scene(root: Path) -> bool:
    """Godot projesi çalıştırılabilir mi: ana sahne tanımlı ve diskte mi.

    Bölümsüz yazılmış anahtar SAYILMAZ; Godot da saymaz ve "no main scene
    defined in the project" der (bkz. `core/structured_files.py`).
    """
    try:
        content = (root / "project.godot").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    in_section = False
    for line in content.splitlines():
        if _SECTION.match(line):
            in_section = True
        elif in_section and _MAIN_SCENE.match(line):
            # Tanımlı olması yetmez: dosya DİSKTE de olmalı.
            #
            # Ölçüldü (13 Eylül, koşu 32): `run/main_scene="res://scenes/main.tscn"`
            # yazıyordu ama dosya hiç yazılmamıştı. Proje "çalıştırılabilir" sayıldı,
            # kurulum kapısı (içe aktarma) atlandı ve çalıştırma kapısı üç satır
            # ERROR'a rağmen sıfır çıkışla geçti.
            return _declared_main_scene_exists(root, line)
    return False


_RES_YOLU = re.compile(r'res://(?P<yol>[^"\']+)')
_UID_DEGERI = re.compile(r'(?P<uid>uid://[^"\'\s]+)')
_SAHNE_UID_BASLIGI = re.compile(r'^\[gd_scene\b[^\]]*\buid="(?P<uid>uid://[^"]+)"')


def _declared_main_scene_exists(root: Path, line: str) -> bool:
    """`run/main_scene` satırındaki sahne dosyası diskte var mı?

    Ölçüldü (29 Ekim): Godot 4.x `run/main_scene="uid://..."` yazabilir; yalnız
    `res://` tanıyan eşleme geçerli projeyi "ana sahne yok" diye reddediyordu.
    uid, sahne dosyasının `[gd_scene ... uid="uid://..."]` başlığında çözülür
    (motorun `.godot/uid_cache.bin` önbelleği kullanılmaz, editör açılmamış
    projede yoktur).
    """
    eslesme = _RES_YOLU.search(line)
    if eslesme is not None:
        return (root / eslesme.group("yol").strip()).is_file()
    uid = _UID_DEGERI.search(line)
    if uid is None:
        return False
    return _scene_with_uid_exists(root, uid.group("uid"))


def _scene_with_uid_exists(root: Path, uid: str) -> bool:
    """Proje içinde başlığı bu uid'i taşıyan bir `.tscn` var mı?"""
    for path in root.rglob("*.tscn"):
        if any(
            part in SKIP_DIRECTORIES or part.startswith(".")
            for part in path.relative_to(root).parts
        ):
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                ilk = handle.readline()
        except OSError:
            continue
        baslik = _SAHNE_UID_BASLIGI.match(ilk)
        if baslik is not None and baslik.group("uid") == uid:
            return True
    return False


def godot_needs_import(root: Path) -> bool:
    """Projede İÇE AKTARILMAMIŞ varlık var mı?

    Godot bir PNG'yi ancak içe aktardıktan sonra yükleyebilir; yanında bir
    `<dosya>.import` üretir. Editör hiç açılmadan eklenen dosyalar için bu kayıt
    yoktur ve `load("res://...png")` çalışma anında düşer.

    Ölçüldü (13 Eylül, Godot koşusu): 400 karo indirilip açıldı, kod doğru yolu
    yüklüyordu ve motor `No loader found for resource:
    res://assets/Tiles/Default/tile_0000.png` bastı — üstelik çıkış kodu 0'dı.
    """
    # `os.walk` ile BUDAMA: `node_modules`/`.git`/`.godot` ağacına hiç girilmez (eskiden
    # `rglob("*")` hepsini gezip sonra süzüyordu; her kapı çağrısında tekrarlanırdı).
    # Süzgeç kökten GÖRELİ olduğundan `~/.projects/oyun` gibi gizli üst dizin projeyi
    # görünmez kılmaz (C1-04 ile aynı ilke).
    for dizin, alt_dizinler, dosyalar in os.walk(root):
        alt_dizinler[:] = [
            ad for ad in alt_dizinler if ad not in SKIP_DIRECTORIES and not ad.startswith(".")
        ]
        for ad in dosyalar:
            yol = Path(dizin) / ad
            if yol.suffix.casefold() not in _GODOT_IMPORTED_SUFFIXES or ad.startswith("."):
                continue
            if not yol.with_suffix(yol.suffix + ".import").exists():
                return True
    return False


def _godot_preparation(root: Path) -> tuple[str, ...]:
    """İçe aktarılmamış varlık varsa kapıdan önce bir kez içe aktar."""
    if not godot_needs_import(root):
        return ()
    return ("godot --headless --path . --editor --quit",)


def godot_adapter() -> DomainAdapter:
    """Godot kanıt sözleşmesi.

    Kapı `--headless --quit` ile projenin AÇILDIĞINI ölçer. Ölçülen hata: model bozuk
    `project.godot` ve `main.tscn` üretti, tur "tamamlandı" dedi; Godot elle
    çalıştırıldığında iki saniyede `no main scene defined in the project` diyordu.
    """
    return DomainAdapter(
        name="godot",
        marker="project.godot",
        gates=("godot --headless --path . --quit",),
        setup_gates=("godot --headless --path . --editor --quit",),
        is_runnable=godot_has_main_scene,
        preparation=_godot_preparation,
        executable="godot",
        executable_resolver=_godot_gate_executable,
        # "no loader found" sıfır çıkışla basılır ve oyunun varlığı yükleyemediğini
        # söyler; kapının sessiz kalması tam da bu yüzden yanlıştır.
        output_failure_markers=(
            "script error",
            "parse error",
            "can't run project",
            "failed to load script",
            "no loader found",
            # Ölçüldü (koşu 32): ana sahne dosyası yoktu; motor "Cannot open file"
            # ve "Failed loading scene" bastı, çıkış kodu yine 0'dı.
            "cannot open file",
            "failed loading",
        ),
        criteria=(
            "project.godot içinde ana sahne (run/main_scene) tanımlı",
            "godot --headless çalıştığında hiçbir SCRIPT ERROR / Parse Error basılmıyor",
            "sahnedeki düğüm tipi, bağlı script'in kullandığı API ile uyumlu",
        ),
        # Yalnız Godot'u ADIYLA anan kelimeler: "oyun"/"game" tarayıcı oyununa da
        # Godot koşulu sokardı.
        task_markers=("godot", "gdscript", "tscn"),
    )
