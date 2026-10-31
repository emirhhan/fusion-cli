"""Onay kartındaki "bir daha sorma" kuralının yazıcısı ve bildirimi — TEK yardımcı (P-003).

Üç yüzey (düz konsol REPL, TUI, `fusion run`) aynı iki işi yapar: `ApprovalMemory`ye kalıcı
kural yazıcısını bağlar ve tur sonunda "kural yazıldı/yazılamadı" bildirimini basar.
Ölçüldü (31 Ekim): TUI döngüsü bildirimi hiç basmıyor, `fusion run` yolunda yazıcı hiç
bağlanmıyordu (ConsolePrompter `k` ipucunu gösteriyor ama `k` yalnız oturum içi hatırlıyordu).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from ..engines.agent.approval import ApprovalMemory, ApprovalRequest
from ..engines.agent.permission_persist import remember_always
from ..ui import messages, theme


def attach_rule_writer(memory: ApprovalMemory, root: Path | Callable[[], Path]) -> ApprovalMemory:
    """Hafızaya kalıcı kural yazıcısını bağla; kök çağrı anında okunur (proje değişebilir)."""

    def write(request: ApprovalRequest) -> str:
        current = root() if callable(root) else root
        return remember_always(current, request)

    memory.rule_writer = write
    return memory


def rule_notice_lines(memory: ApprovalMemory) -> list[str]:
    """Bekleyen bildirimleri al (hafıza boşalır) ve kullanıcı metnine çevir."""
    return [
        messages.PERMISSION_RULE_SAVED.format(summary=notice) for notice in memory.take_notices()
    ]


def print_rule_notices(console: Console, memory: ApprovalMemory) -> None:
    for line in rule_notice_lines(memory):
        # Vurgulama kapalı: kalıp (`Bash(npm test *)`) parçalanmasın, dökümde düz okunsun.
        console.print(f"[{theme.INFO}]{escape(line)}[/{theme.INFO}]", highlight=False)
