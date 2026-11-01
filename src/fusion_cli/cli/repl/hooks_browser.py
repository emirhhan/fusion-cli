"""`/hooks` salt okunur kanca tarayıcısı (#130) — Claude Code `/hooks` menüsü gibi.

Liste her kancayı geldiği yerle etiketler (kullanıcı/proje/yerel ayarı, yönetilen ayar,
eklenti, oturum: beceri frontmatter'ı). Bir kanca seçilince çalıştırdığı tam metin ve
tanımlandığı yer (ayar dosyası ya da eklenti adı) gösterilir; listenin sonundaki
"All events" tanımı olmayanlar dahil bütün olayları açar.

TUI'de argümansız `/hooks` uygulama-içi seçiciyle açılır (`hook_choices`); düz REPL ve
masaüstünde numaralı liste basılır, `/hooks <no>` ayrıntıyı, `/hooks all` bütün olayları
gösterir.
"""

from __future__ import annotations

from ...config.hooks import LAYER_MANAGED
from ...config.permission_rules import LAYER_FUSION, LAYER_LOCAL, LAYER_PROJECT, LAYER_USER
from ...config.plugin_hooks import PLUGIN_SOURCE_PREFIX
from ...core.hooks.events import CLAUDE_ONLY_EVENTS, HookCommand, HookEvent, HookSet
from ...engines.agent.skill_hooks import SKILL_SOURCE_PREFIX
from ...ui import messages
from ...ui.picker import Choice

#: "All events" seçeneğinin değeri ve kabul edilen yazımları.
ALL_EVENTS = "all"
ALL_EVENTS_LABEL = "All events"
_ALL_WORDS = frozenset({ALL_EVENTS, "all events", "tum", "tüm", "hepsi"})
_COMMAND_CHARS = 60
_LAYER_LABELS = {
    LAYER_USER: "kullanıcı ayarı",
    LAYER_FUSION: "kullanıcı ayarı (eski hooks.json)",
    LAYER_PROJECT: "proje ayarı",
    LAYER_LOCAL: "yerel ayar",
    LAYER_MANAGED: "yönetilen ayar",
}


def source_label(command: HookCommand) -> str:
    """Kancanın geldiği yer (Claude: user/project/local settings, plugin, session)."""
    if command.source.startswith(PLUGIN_SOURCE_PREFIX):
        return f"eklenti: {command.source.removeprefix(PLUGIN_SOURCE_PREFIX)}"
    if command.source.startswith(SKILL_SOURCE_PREFIX):
        return f"oturum (beceri: {command.source.removeprefix(SKILL_SOURCE_PREFIX)})"
    return _LAYER_LABELS.get(command.source, command.source or "oturum")


def _shown(command: HookCommand) -> str:
    if command.handler == "http":
        return f"POST {command.command}"
    if command.handler == "mcp_tool":
        return f"mcp_tool {command.server}/{command.tool}"
    return command.command


def ordered(hooks: HookSet) -> tuple[HookCommand, ...]:
    """Tarayıcı sırası: olay adı, sonra tanım sırası (numaralar buna göre)."""
    return tuple(sorted(hooks.commands, key=lambda command: command.event.value))


def hook_choices(hooks: HookSet) -> list[Choice]:
    """Seçici satırları: her kanca (`1`, `2`…) ve sonda "All events"."""
    choices = []
    for number, command in enumerate(ordered(hooks), start=1):
        text = _shown(command)
        short = text if len(text) <= _COMMAND_CHARS else text[: _COMMAND_CHARS - 1] + "…"
        matcher = f" [{command.matcher}]" if command.matcher else ""
        choices.append(
            Choice(
                str(number),
                f"{command.event.value}{matcher}",
                f"{short} · {source_label(command)}",
            )
        )
    choices.append(Choice(ALL_EVENTS, ALL_EVENTS_LABEL, "tanımı olmayanlar dahil bütün olaylar"))
    return choices


def is_all_events(argument: str) -> bool:
    return argument.strip().lower() in _ALL_WORDS


def detail_lines(hooks: HookSet, argument: str) -> list[str] | None:
    """`/hooks <no>`: tam komut ve tanım yeri; numara geçersizse `None`."""
    text = argument.strip()
    commands = ordered(hooks)
    if not text.isdigit() or not 1 <= int(text) <= len(commands):
        return None
    command = commands[int(text) - 1]
    where = command.path or "—"
    lines = [
        f"{command.event.value}" + (f" [{command.matcher}]" if command.matcher else ""),
        f"  tür: {command.handler}",
        f"  çalıştırır: {_shown(command)}",
    ]
    if command.args is not None:
        lines.append(f"  args: {list(command.args)}")
    if command.condition:
        lines.append(f"  if: {command.condition}")
    lines.append(f"  süre: {command.timeout_s:g} sn")
    lines.append(f"  kaynak: {source_label(command)}")
    lines.append(f"  tanım: {where}")
    return lines


def all_event_lines(hooks: HookSet) -> list[str]:
    """ "All events": her olay ve tanımlı kanca sayısı (tetiklenmeyenler işaretli)."""
    counts: dict[str, int] = {}
    for command in hooks.commands:
        counts[command.event.value] = counts.get(command.event.value, 0) + 1
    names = sorted({event.value for event in HookEvent} | set(CLAUDE_ONLY_EVENTS))
    lines = [f"{ALL_EVENTS_LABEL} — {len(names)} olay:"]
    for name in names:
        count = counts.get(name, 0)
        mark = "  (Fusion bu olayı tetiklemiyor)" if name in CLAUDE_ONLY_EVENTS else ""
        lines.append(f"· {name}: {count} kanca{mark}")
    return lines


def browser_lines(hooks: HookSet) -> list[str]:
    """Düz REPL/masaüstü: uyarılar, numaralı liste, atlananlar ve gezinme ipucu."""
    lines: list[str] = []
    if hooks.disabled_reason is not None:
        lines.append(messages.HOOKS_LIST_DISABLED.format(reason=hooks.disabled_reason))
    lines.append(
        messages.HOOKS_LIST_HEADER.format(active=len(hooks.commands), skipped=len(hooks.skipped))
    )
    lines.extend(
        f"{choice.value}. {choice.label}  {choice.description}" for choice in hook_choices(hooks)
    )
    lines.extend(
        f"· {skip.event}"
        + (f" [{skip.matcher}]" if skip.matcher else "")
        + f"  {skip.detail} — atlandı: {skip.reason}"
        for skip in hooks.skipped
    )
    if hooks.untrusted_layers:
        lines.append(messages.HOOKS_LIST_UNTRUSTED.format(layers=", ".join(hooks.untrusted_layers)))
    lines.append(messages.HOOKS_BROWSER_HINT)
    return lines
