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
_MOUSE_TOOLS = {"desktop_mouse", "desktop_click", "desktop_scroll"}
#: Fare eylemlerinin kart metni; Claude Code'daki önizleme gibi NE yapılacağı ve NEREDE söylenir.
_MOUSE_LABELS = {
    "click": "sol tık",
    "right_click": "sağ tık",
    "double_click": "çift tık",
    "triple_click": "üçlü tık",
    "middle_click": "orta tık",
    "drag": "sürükle",
    "hover": "imleci götür",
    "down": "düğmeyi bas",
    "up": "düğmeyi bırak",
}


def approval_summary(
    tool_name: str, args: Mapping[str, object], *, element: str = ""
) -> tuple[str, str]:
    """(başlık, hedef) döndür. Hedef yoksa boş metin.

    `element`, tarayıcıda tıklanacak öğenin sayfadaki adıdır (bkz.
    `ChromeBridge.element_name`); ref kimliği ("e52") kullanıcıya bir şey söylemez.
    """
    family = tool_family(tool_name)
    if tool_name == "chrome_click":
        return "Bu öğeye tıklansın mı?", f"“{element}” öğesine tıklanacak" if element else _text(
            args, "ref"
        )
    if tool_name == "chrome_action" and args.get("action") == "key":
        return (
            "Bu tuşa basılsın mı?",
            f"{_text(args, 'value') or 'Enter'} (açık formu gönderebilir)",
        )
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
    if tool_name in _MOUSE_TOOLS:
        return "Bilgisayarında bu işlem yapılsın mı?", _mouse_target(tool_name, args)
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


def _mouse_target(tool_name: str, args: Mapping[str, object]) -> str:
    """'sağ tık (784, 490)' / 'sürükle (10, 20) → (300, 400)' / '5 satır aşağı kaydır (x, y)'."""
    where = _point(args, "x", "y")
    if tool_name == "desktop_scroll":
        parts = []
        for key, pozitif, negatif in (("lines", "yukarı", "aşağı"), ("delta_x", "sola", "sağa")):
            value = args.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value:
                parts.append(f"{abs(value)} satır {pozitif if value > 0 else negatif}")
        return " ve ".join(parts) + " kaydır" + (f" {where}" if where else "")
    action = str(args.get("action", "click")) if tool_name == "desktop_mouse" else "click"
    label = _MOUSE_LABELS.get(action, action)
    if action == "drag":
        return f"{label} {where} → {_point(args, 'to_x', 'to_y')}"
    modifiers = _text(args, "modifiers")
    return f"{label} {where}" + (f" ({modifiers})" if modifiers else "")


def _point(args: Mapping[str, object], key_x: str, key_y: str) -> str:
    x, y = args.get(key_x), args.get(key_y)
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return f"({x:g}, {y:g})"
    return ""


def _text(args: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            return " ".join(value)
    return ""
