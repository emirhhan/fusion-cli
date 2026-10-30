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

from ..core.errors import PathAccessError
from ..core.tools import ToolContext
from ..tools.args import ArgumentError
from ..tools.esnek_eslesme import FlexibleEdit, describe
from ..tools.files import parse_edits, replace_once, resolve_path

__all__ = ["onizleme_diffi"]

#: Önizleme üretilebilen düzenleme araçları.
_DUZENLEME_ARACLARI = frozenset({"write_file", "edit_file", "multi_edit"})

#: Önizlemede gösterilecek en fazla satır. Uzun diff onay kartını okunmaz yapar;
#: kullanıcı kararı için başı yeterlidir, tamamı değişiklik kartında zaten görünür.
MAX_SATIR = 60

#: Önizleme için okunacak en büyük dosya (bayt). Ölçüldü (30 Ekim): sınırsızdı;
#: çok büyük bir hedef dosya onay kartı için tamamen belleğe alınıyordu.
MAX_DOSYA_BAYT = 1024 * 1024


def onizleme_diffi(
    tool_name: str, args: dict[str, Any], root: Path, *, edit_fuzzy_match: bool = True
) -> str:
    """Araç çalıştırılsa dosyanın nasıl değişeceğini unified diff olarak ver.

    Düzenleme araçlarında değişim aracın KENDİ ortak yoluyla (`replace_once`, aynı
    `edit_fuzzy_match` ayarı) hesaplanır: esnek eşleşmeyle uygulanacak bir düzenleme
    boş önizleme yerine gerçek diff'i gösterir ve başına kısa bir not eklenir.
    """
    if tool_name not in _DUZENLEME_ARACLARI:
        return ""
    yol = args.get("path")
    if not isinstance(yol, str) or not yol.strip():
        return ""
    # Yol çözümü aracın kendisininkiyle AYNI olmalı (`~` açılır, kısıtlı kipte kök
    # dışı reddedilir): aksi hâlde kök dışı bir dosyanın içeriği diff olarak karta
    # okunurdu (ölçüldü: önce `root / yol` sonra `expanduser` sırası `~/x`'i açmıyordu).
    try:
        hedef = resolve_path(ToolContext(root=root), yol)
    except PathAccessError:
        return ""
    mevcut = _oku(hedef)
    if mevcut is None:
        return ""
    context = ToolContext(root=root, edit_fuzzy_match=edit_fuzzy_match)
    notlar: list[str] = []
    yeni = _yeni_icerik(tool_name, args, mevcut, context, notlar)
    if yeni is None or yeni == mevcut:
        return ""
    fark = _diff(yol, mevcut, yeni)
    return "".join(f"# {not_}\n" for not_ in notlar) + fark


def _oku(hedef: Path) -> list[str] | None:
    """Dosyanın satırları; yoksa boş liste, okunamıyorsa ``None``."""
    if not hedef.exists():
        return []
    try:
        if hedef.stat().st_size > MAX_DOSYA_BAYT:
            return None
        return hedef.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return None


def _yeni_icerik(
    tool_name: str,
    args: dict[str, Any],
    mevcut: list[str],
    context: ToolContext,
    notlar: list[str],
) -> list[str] | None:
    if tool_name == "write_file":
        content = args.get("content")
        return None if not isinstance(content, str) else content.splitlines(keepends=True)
    if tool_name in ("edit_file", "multi_edit"):
        return _metin_degistir(tool_name, args, mevcut, context, notlar)
    return None


def _metin_degistir(
    tool_name: str,
    args: dict[str, Any],
    mevcut: list[str],
    context: ToolContext,
    notlar: list[str],
) -> list[str] | None:
    """`edit_file` / `multi_edit` değişimlerini araçla AYNI şemadan uygula.

    Gerçek şema `old`/`new`/`replace_all` (tek düzenleme) ve `edits` listesidir
    (`tools/builtin.py`). `old_string`/`new_string` yalnız yedek adlardır; boş yeni
    metin (silme) `or` ile ikinci anahtara düşmesin diye varlığa bakılır.
    """
    metin = "".join(mevcut)
    if tool_name == "multi_edit":
        try:
            edits = parse_edits(args.get("edits"))
        except ArgumentError:
            return None
    else:
        eski = _alan(args, "old", "old_string")
        yeni = _alan(args, "new", "new_string")
        if not isinstance(eski, str) or not isinstance(yeni, str):
            return None
        edits = ((eski, yeni, args.get("replace_all") is True),)
    for sira, (eski, yeni, replace_all) in enumerate(edits, 1):
        if not eski:
            return None
        if replace_all:
            if eski not in metin:
                return None
            metin = metin.replace(eski, yeni)
            continue
        # Araçla AYNI yol: tam eşleşme, yoksa (ayar açıksa) tek ve belirsiz olmayan esnek blok.
        adim = replace_once(
            metin, eski, yeni, context, position=sira if tool_name == "multi_edit" else None
        )
        if isinstance(adim, str):
            return None
        metin = adim[0]
        notlar.extend(_esnek_not(konum, duzenleme) for konum, duzenleme in adim[1])
    return metin.splitlines(keepends=True)


def _esnek_not(konum: int | None, duzenleme: FlexibleEdit) -> str:
    onek = f"{konum}. düzenleme: " if konum is not None else ""
    return f"{onek}{describe(duzenleme)}"


def _alan(args: dict[str, Any], *anahtarlar: str) -> object:
    """İlk MEVCUT anahtarın değeri (boş string de geçerli bir değerdir)."""
    for anahtar in anahtarlar:
        if anahtar in args:
            return args[anahtar]
    return None


def _diff(yol: str, mevcut: list[str], yeni: list[str]) -> str:
    satirlar = list(difflib.unified_diff(mevcut, yeni, fromfile=f"a/{yol}", tofile=f"b/{yol}", n=2))
    if not satirlar:
        return ""
    if len(satirlar) > MAX_SATIR:
        kalan = len(satirlar) - MAX_SATIR
        satirlar = [*satirlar[:MAX_SATIR], f"… {kalan} satır daha\n"]
    return "".join(satirlar)
