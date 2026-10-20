"""Godot alanı — motorun kendisi projeyi açabiliyor mu, hata basıyor mu?

Ölçüldü (5-6 Eylül): Godot bozuk script'te ve çalışma zamanı hatasında `0` çıkış
kodu verebiliyor; "açıldı" ile "hatasız açıldı" ayrı şeylerdir. Bu modül Godot'a
özgü tüm kanıt bilgisini tek yerde tutar; motor bu adları hiç bilmez.
"""

from __future__ import annotations

import re
from pathlib import Path

from ....core.constants import SKIP_DIRECTORIES
from .contract import DomainAdapter

#: `project.godot` içinde ana sahneyi tanımlayan anahtar.
_MAIN_SCENE = re.compile(r"^\s*run/main_scene\s*=\s*\S")
_SECTION = re.compile(r"^\s*\[")

#: Godot'un içe aktarma gerektiren görsel/ses uzantıları.
_GODOT_IMPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".ogg", ".wav", ".mp3"})


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


def _declared_main_scene_exists(root: Path, line: str) -> bool:
    """`run/main_scene` satırındaki sahne dosyası diskte var mı?"""
    eslesme = re.search(r'res://(?P<yol>[^"\']+)', line)
    if eslesme is None:
        return False
    return (root / eslesme.group("yol").strip()).is_file()


def godot_needs_import(root: Path) -> bool:
    """Projede İÇE AKTARILMAMIŞ varlık var mı?

    Godot bir PNG'yi ancak içe aktardıktan sonra yükleyebilir; yanında bir
    `<dosya>.import` üretir. Editör hiç açılmadan eklenen dosyalar için bu kayıt
    yoktur ve `load("res://...png")` çalışma anında düşer.

    Ölçüldü (13 Eylül, Godot koşusu): 400 karo indirilip açıldı, kod doğru yolu
    yüklüyordu ve motor `No loader found for resource:
    res://assets/Tiles/Default/tile_0000.png` bastı — üstelik çıkış kodu 0'dı.
    """
    for path in root.rglob("*"):
        if path.suffix.casefold() not in _GODOT_IMPORTED_SUFFIXES:
            continue
        if any(part in SKIP_DIRECTORIES or part.startswith(".") for part in path.parts):
            continue
        if not path.with_suffix(path.suffix + ".import").exists():
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
