"""Beklenen yolda olmayan bir dosyanın çalışma alanındaki gerçek yerini bulur.

Ölçüldü (7 Eylül canlı Godot koşusu, `game-manager-eksiklerini-tamamla`): plan
`scripts/game_manager.gd` bekledi, model dosyayı depo köküne yazdı. "Dosya
bulunamadı" cevabı yönsüzdü; model dosyayı taşımak yerine iki kez yeniden üretti
ve kurtarma hakkı bitti.

"Yok" ile "burada" farklı cevaplardır: ilki adımı öldürür, ikincisi tek hamlede
düzeltilebilir bir iş bırakır.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from .constants import SKIP_DIRECTORIES

#: Bulgu metnine yazılacak en fazla aday yol.
#
# Metin bir YÖNERGE'dir, dizin dökümü değil: üçten fazla aday modelin kararını
# kolaylaştırmaz, istemi şişirir.
MAX_LOCATE_HITS = 3


def locate_by_name(root: Path, name: str, *, limit: int = MAX_LOCATE_HITS) -> tuple[str, ...]:
    """Kök altında aynı ADI taşıyan dosyaların köke göreli yollarını bul.

    Gürültü dizinleri (`SKIP_DIRECTORIES`) ve gizli dizinler taranmaz; okunamayan
    dizin sessizce atlanır — bu bir iddia değil, bir yardımdır.
    """
    if not name:
        return ()
    hits: list[str] = []
    for path in _walk(root.resolve()):
        if path.name != name:
            continue
        hits.append(path.relative_to(root.resolve()).as_posix())
        if len(hits) >= limit:
            break
    return tuple(sorted(hits))


def _walk(root: Path) -> Iterator[Path]:
    """Gürültü dizinlerini atlayarak kök altındaki dosyaları tembel gez.

    Tembel olması şart: arama ilk birkaç eşleşmede durur ve büyük bir depoyu
    baştan sona taramak, yalnız bir yol tarifi üretmek için pahalıdır.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIRECTORIES or entry.name.startswith("."):
                    continue
                stack.append(entry)
            elif entry.is_file():
                yield entry
