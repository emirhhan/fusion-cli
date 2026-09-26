"""İzin kartının insan dilindeki başlığı ve hedefi.

Kart eskiden `run_shell` adını ve `command='npm test'` gibi ham argümanları
gösteriyordu; kullanıcı neye izin verdiğini okumak için argüman listesini
çözmek zorundaydı. Claude'daki gibi kart TEK cümleyle ne olacağını söyler,
hedefi (komut, dosya, adres) ayrıca ve olduğu gibi gösterir.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from ..core.tools import ToolFamily, tool_family

_FILE_WRITE = {"write_file", "create_file"}
_FILE_EDIT = {"edit_file", "multi_edit"}


def approval_summary(tool_name: str, args: Mapping[str, object]) -> tuple[str, str]:
    """(başlık, hedef) döndür. Hedef yoksa boş metin."""
    family = tool_family(tool_name)
    path = _text(args, "path", "file_path", "target")
    if family is ToolFamily.SHELL:
        return "Bu komut çalıştırılsın mı?", _text(args, "command", "cmd")
    if tool_name in _FILE_WRITE:
        return "Bu dosya yazılsın mı?", path
    if tool_name in _FILE_EDIT:
        return "Bu dosya düzenlensin mi?", path
    if family is ToolFamily.FILES:
        return "Bu dosya işlemi yapılsın mı?", path
    if family is ToolFamily.VCS:
        return "Bu git işlemi yapılsın mı?", _text(args, "args", "command", "subcommand")
    if family is ToolFamily.BROWSER:
        return "Tarayıcıda bu işlem yapılsın mı?", _text(args, "url", "text", "selector", "ref")
    if family is ToolFamily.DESKTOP:
        return "Bilgisayarında bu işlem yapılsın mı?", _text(args, "app", "text", "key", "name")
    if family is ToolFamily.WEB:
        return "Bu web isteği yapılsın mı?", _text(args, "url", "query")
    if "__" in tool_name:
        sunucu, arac = tool_name.split("__", 1)
        yetenek = _text(args, "ability_name")
        if yetenek:
            # WordPress yetenek geçidi: araç adı değil ÇALIŞACAK yetenek söylenir.
            parametreler = args.get("parameters")
            ayrinti = json.dumps(parametreler, ensure_ascii=False) if parametreler else ""
            return f"{sunucu} üzerinde “{yetenek}” çalıştırılsın mı?", ayrinti[:400]
        return f"{sunucu} üzerinde “{arac}” çalıştırılsın mı?", ""
    return f"“{tool_name}” aracı çalıştırılsın mı?", ""


def _text(args: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            return " ".join(value)
    return ""
