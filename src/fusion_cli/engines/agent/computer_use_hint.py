"""Computer use kapalıyken masaüstü isteğinde açma önerisi (#420).

Claude Code (code.claude.com/docs/en/computer-use): computer use varsayılan kapalıdır;
kapalıyken kullanıcı masaüstü işi isterse Claude onu nasıl açacağını söyler. Fusion'da not
yalnız istek masaüstü işine benziyorsa (`is_desktop_task`) ve `desktop_*` araçları bu turda
yoksa eklenir; sabit sistem istemine girmez (araç istemi bütçesi değişmez).
"""

from __future__ import annotations

from collections.abc import Iterable

from .expertise import is_desktop_task

COMPUTER_USE_OFF_NOTE = (
    "Bilgisayar kullanımı (computer use) şu an kapalı; desktop_* araçların yok. İş yerel bir "
    "masaüstü uygulamasını kullanmayı gerektiriyorsa bunu yapamayacağını söyle ve açmayı öner: "
    "terminalde `/mcp enable computer-use`, masaüstü uygulamasında Ayarlar › Bu bilgisayar › "
    "Computer use'u etkinleştir. İş tarayıcıda ya da kabukta yapılabiliyorsa öneri yapma."
)


def computer_use_off_hint(task: str, *, enabled: bool, tool_names: Iterable[str]) -> str | None:
    if enabled or not is_desktop_task(task):
        return None
    if any(name.startswith("desktop_") for name in tool_names):
        return None
    return COMPUTER_USE_OFF_NOTE
