"""Onay kartı için "ne değişecek" önizlemesi.

Neden var — ölçüldü (17 Eylül denetimi): onay diyaloğu yalnız araç adını ve
argümanları gösteriyordu. Kullanıcı `write_file(path=…, content=<1500 karakter>)`
satırını görüp dosyanın NASIL değişeceğini bilmeden karar veriyordu. Kararın
dayanağı argümanın kendisi değil, sonucudur.

Önizleme bir KOLAYLIKTIR: üretilemezse (ikili dosya, okunamayan yol, tanınmayan
araç) boş metin döner ve onay akışı olduğu gibi devam eder. Bu modül diske
YAZMAZ; yalnız okur.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

__all__ = ["onizleme_diffi"]

#: Önizleme üretilebilen düzenleme araçları.
_DUZENLEME_ARACLARI = frozenset({"write_file", "edit_file", "multi_edit"})

#: Önizlemede gösterilecek en fazla satır. Uzun diff onay kartını okunmaz yapar;
#: kullanıcı kararı için başı yeterlidir, tamamı değişiklik kartında zaten görünür.
MAX_SATIR = 60


def onizleme_diffi(tool_name: str, args: dict[str, Any], root: Path) -> str:
    """Araç çalıştırılsa dosyanın nasıl değişeceğini unified diff olarak ver."""
    if tool_name not in _DUZENLEME_ARACLARI:
        return ""
    yol = args.get("path")
    if not isinstance(yol, str) or not yol.strip():
        return ""
    hedef = (root / yol).expanduser()
    mevcut = _oku(hedef)
    if mevcut is None:
        return ""
    yeni = _yeni_icerik(tool_name, args, mevcut)
    if yeni is None or yeni == mevcut:
        return ""
    return _diff(yol, mevcut, yeni)


def _oku(hedef: Path) -> list[str] | None:
    """Dosyanın satırları; yoksa boş liste, okunamıyorsa ``None``."""
    if not hedef.exists():
        return []
    try:
        return hedef.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return None


def _yeni_icerik(tool_name: str, args: dict[str, Any], mevcut: list[str]) -> list[str] | None:
    if tool_name == "write_file":
        content = args.get("content")
        return None if not isinstance(content, str) else content.splitlines(keepends=True)
    if tool_name in ("edit_file", "multi_edit"):
        return _metin_degistir(args, mevcut)
    return None


def _metin_degistir(args: dict[str, Any], mevcut: list[str]) -> list[str] | None:
    """`edit_file` ailesinin tam-metin eşleşmeli değişimini uygula."""
    eski = args.get("old_string") or args.get("old")
    yeni = args.get("new_string") or args.get("new")
    if not isinstance(eski, str) or not isinstance(yeni, str) or not eski:
        return None
    metin = "".join(mevcut)
    if eski not in metin:
        return None
    return metin.replace(eski, yeni, 1).splitlines(keepends=True)


def _diff(yol: str, mevcut: list[str], yeni: list[str]) -> str:
    satirlar = list(
        difflib.unified_diff(mevcut, yeni, fromfile=f"a/{yol}", tofile=f"b/{yol}", n=2)
    )
    if not satirlar:
        return ""
    if len(satirlar) > MAX_SATIR:
        kalan = len(satirlar) - MAX_SATIR
        satirlar = [*satirlar[:MAX_SATIR], f"… {kalan} satır daha\n"]
    return "".join(satirlar)
