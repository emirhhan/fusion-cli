"""Masaüstü `izin.dizin*` istekleri — Claude `/permissions` Workspace sekmesi (#83).

    izin.dizinler       birincil kök + bu oturumda eklenen dizinler
    izin.dizin_ekle     {yol}  → `/add-dir <yol>` ile aynı kurallar (ev/disk kökü/üst dizin yok)
    izin.dizin_kaldir   {yol}  → `/add-dir kaldır <yol>`

Yazma işi REPL/TUI kutusunun da kullandığı `workspace_commands.add_dir` üzerinden geçer;
ikinci bir yol açılmaz. Erişim oturumluktur, diske yazılmaz. Beceri kataloğunu yeniden
kurmak çağıranın (oturum) işidir: yanıttaki `degisti` doğruysa.
"""

from __future__ import annotations

from typing import Any

from ..cli.repl import workspace_commands
from ..cli.repl.state import ReplState
from .protocol import Request

#: Bu modülün karşıladığı istek adları.
NAMES = frozenset({"izin.dizinler", "izin.dizin_ekle", "izin.dizin_kaldir"})
_EMPTY_PATH = "Dizin yolu boş."


def handle(state: ReplState, request: Request) -> dict[str, Any]:
    if request.name == "izin.dizinler":
        return _payload(state, changed=False)
    path = str(request.data.get("yol", "") or "").strip()
    if not path:
        return {**_payload(state, changed=False), "ok": False, "metin": _EMPTY_PATH}
    before = state.extra_roots
    argument = path if request.name == "izin.dizin_ekle" else f"kaldır {path}"
    text = workspace_commands.add_dir(state, argument)
    return {**_payload(state, changed=state.extra_roots != before), "metin": text}


def _payload(state: ReplState, *, changed: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "kok": str(state.root),
        "dizinler": [str(path) for path in state.extra_roots],
        "degisti": changed,
    }
