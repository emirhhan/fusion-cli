"""`/plugin` paneli: Discover · Installed · Marketplaces · Errors sekmeleri (Claude Code, #382).

Claude Code (cli-reference "/plugin in a session", install.md): `/plugin` paneli Discover
sekmesinde açar; Discover'da eklenti seçilince ayrıntı ve kurulum kapsamı (user/project/local)
sorulur; Installed'da aç/kapat, kaldır, yapılandır; Marketplaces'te güncelle, kaldır ve
"Enable/Disable auto-update"; Errors yüklenemeyen eklentileri gösterir.

Panel saf bir ekran makinesidir: `screen(state, anahtar)` başlık+seçenekler verir, `act(state,
anahtar, değer)` ya sonraki ekranın anahtarını ya da bitiş mesajını döndürür. TUI uygulama-içi
modalla (`run_async`), satır-içi REPL `ui.picker.pick` ile (`run_sync`) sürer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

from ...config import plugin_store
from ...config.plugin_store import STATUS_ACTIVE, STATUS_DISABLED, installed_plugins, load_state
from ...core.plugins import PluginError
from ...ui.picker import Choice
from .state import ReplState

TABS = (("discover", "Discover"), ("installed", "Installed"), ("markets", "Marketplaces"))
TABS_ALL = (*TABS, ("errors", "Errors"))
SCOPES = (
    ("user", "Senin için kur (user kapsamı)"),
    ("project", "Bu depodaki herkes için kur (project kapsamı)"),
    ("local", "Yalnız senin için, bu depoda kur (local kapsamı)"),
)
CLOSED = "Eklenti paneli kapatıldı"
EMPTY_DISCOVER = "Kurulabilecek eklenti yok — pazar ekle: /plugin marketplace add <kaynak>"
NO_ERRORS = "Yüklenemeyen eklenti yok"
ADD_HINT = "Pazar eklemek için: /plugin marketplace add <kaynak>"
_TAB_PREFIX = "tab:"


@dataclass(frozen=True, slots=True)
class Screen:
    title: str
    choices: tuple[Choice, ...]


@dataclass(frozen=True, slots=True)
class Step:
    """`next_key` doluysa panel o ekrana geçer; yoksa `message` ile kapanır."""

    next_key: str = ""
    message: str = ""


def _tabs(current: str) -> tuple[Choice, ...]:
    return tuple(
        Choice(_TAB_PREFIX + key, f"→ {label}", "sekme")
        for key, label in TABS_ALL
        if key != current
    )


def _discover() -> Screen:
    from ...tools.plugin_install import browse

    rows = tuple(
        Choice(
            f"install:{item.entry.name}@{item.marketplace}",
            f"{item.entry.name}@{item.marketplace}",
            item.entry.description,
        )
        for item in browse()
        if not item.installed
    )
    title = "Eklentiler · Discover" if rows else f"Eklentiler · Discover\n{EMPTY_DISCOVER}"
    return Screen(title, (*rows, *_tabs("discover")))


def _installed() -> Screen:
    state = load_state()
    rows = []
    for item in installed_plugins():
        ident = plugin_store.plugin_id(item.record)
        status = "kapalı" if not item.record.enabled else item.status
        rows.append(Choice(f"plugin:{ident}", ident, f"{item.record.version or ''} · {status}"))
    title = "Eklentiler · Installed" + (" (hepsi kapalı)" if state.all_disabled else "")
    return Screen(title, (*rows, *_flagged_rows(), *_tabs("installed")))


def _flagged_rows() -> tuple[Choice, ...]:
    """#397: pazardan kaldırılıp otomatik kaldırılanlar (Claude "Flagged" grubu); görüldü."""
    from ...tools.plugin_flagged import load_flagged, mark_seen

    flagged = load_flagged()
    mark_seen(item.ident for item in flagged)
    return tuple(
        Choice(f"flagged:{item.ident}", item.ident, f"Flagged · Removed · {item.date}")
        for item in flagged
    )


def _flagged_detail(ident: str) -> Screen:
    from ...tools.plugin_flagged import format_flagged_detail, load_flagged

    item = next((i for i in load_flagged() if i.ident == ident), None)
    title = format_flagged_detail(item) if item is not None else f"{ident}: kayıt yok"
    return Screen(title, _tabs(""))


def _markets() -> Screen:
    rows = tuple(
        Choice(f"market:{m.name}", m.name, f"{m.kind} · {m.source}")
        for m in load_state().marketplaces
    )
    return Screen(f"Eklentiler · Marketplaces\n{ADD_HINT}", (*rows, *_tabs("markets")))


def _errors() -> Screen:
    broken = [
        item
        for item in installed_plugins()
        if item.status not in (STATUS_ACTIVE, STATUS_DISABLED) and item.record.enabled
    ]
    rows = tuple(
        Choice(
            f"plugin:{plugin_store.plugin_id(i.record)}", i.record.name, f"{i.status} {i.detail}"
        )
        for i in broken
    )
    title = "Eklentiler · Errors" if rows else f"Eklentiler · Errors\n{NO_ERRORS}"
    return Screen(title, (*rows, *_tabs("errors")))


def _plugin_actions(ident: str) -> Screen:
    from ...tools.plugin_toggle import find_record

    record = find_record(load_state(), ident)
    toggle = ("disable", "Kapat") if record.enabled else ("enable", "Aç")
    actions = (toggle, ("configure", "Yapılandır"), ("update", "Güncelle"), ("details", "Ayrıntı"))
    rows = tuple(Choice(f"{verb}:{ident}", label) for verb, label in actions)
    remove = Choice(f"uninstall:{ident}", "Kaldır", "kopya, ayarlar ve veri silinir")
    return Screen(f"Eklenti · {ident}", (*rows, remove, *_tabs("")))


def _market_actions(name: str) -> Screen:
    record = load_state().marketplace(name)
    on = record is not None and _auto_update_on(name, record.auto_update)
    toggle = Choice(
        f"autoupdate:{name}", "Disable auto-update" if on else "Enable auto-update", "otomatik"
    )
    rows = (
        Choice(f"mupdate:{name}", "Güncelle"),
        toggle,
        Choice(f"mremove:{name}", "Kaldır", "pazardan kurulan eklentiler de kaldırılır"),
    )
    return Screen(f"Pazar · {name}", (*rows, *_tabs("")))


def _auto_update_on(name: str, recorded: bool | None) -> bool:
    from pathlib import Path

    from ...tools.plugin_auto_update import is_auto_update
    from ...tools.plugin_declared import declared_marketplaces

    try:
        declared = declared_marketplaces(Path.cwd())
    except (OSError, PluginError):
        declared = {}
    return is_auto_update(name, declared, recorded)


def _install_screen(ident: str) -> Screen:
    from ...tools.plugin_install import browse

    name, _, market = ident.partition("@")
    entry = next(
        (i.entry for i in browse() if i.entry.name == name and i.marketplace == market), None
    )
    detail = f"\n{entry.description}" if entry is not None and entry.description else ""
    version = f" {entry.version}" if entry is not None and entry.version else ""
    rows = tuple(Choice(f"scope:{scope}:{ident}", label) for scope, label in SCOPES)
    return Screen(f"{ident}{version}{detail}\nKurulum kapsamı:", (*rows, *_tabs("")))


_SCREENS: dict[str, Callable[[], Screen]] = {
    "discover": _discover,
    "installed": _installed,
    "markets": _markets,
    "errors": _errors,
}


def screen(key: str) -> Screen:
    """Anahtar: sekme adı, `plugin:<id>`, `market:<ad>` ya da `install:<id>`."""
    kind, _, target = key.partition(":")
    if kind in _SCREENS and not target:
        return _SCREENS[kind]()
    builders = {
        "plugin": _plugin_actions,
        "market": _market_actions,
        "install": _install_screen,
        "flagged": _flagged_detail,
    }
    return builders[kind](target)


def act(state: ReplState, key: str, value: str) -> Step:
    """Seçilen değeri uygula: yeni ekran ya da bitiş mesajı."""
    del key
    if value.startswith(_TAB_PREFIX):
        return Step(next_key=value.removeprefix(_TAB_PREFIX))
    verb, _, target = value.partition(":")
    if verb in ("plugin", "market", "install", "flagged"):
        return Step(next_key=value)
    return Step(message=_run_action(state, verb, target))


def _run_action(state: ReplState, verb: str, target: str) -> str:
    from .plugin_command import plugin_command

    if verb == "scope":
        scope, _, ident = target.partition(":")
        # Panelde kapsam seçimi kurulum onayıdır (Claude: ayrıntı ekranı + kapsam).
        return plugin_command(state, f"install {ident} --scope {scope} --yes")
    if verb == "autoupdate":
        return _toggle_auto_update(target)
    commands = {
        "enable": "enable {t}",
        "disable": "disable {t}",
        "uninstall": "uninstall {t}",
        "configure": "configure {t}",
        "update": "update {t}",
        "details": "details {t}",
        "mupdate": "marketplace update {t}",
        "mremove": "marketplace remove {t}",
    }
    return plugin_command(state, commands[verb].format(t=target))


def _toggle_auto_update(name: str) -> str:
    record = load_state().marketplace(name)
    if record is None:
        return f"Pazar yok: {name}"
    current = _auto_update_on(name, record.auto_update)
    updated = replace(record, auto_update=not current)
    plugin_store.update_state(lambda s: s.with_marketplace(updated))
    word = "açıldı" if updated.auto_update else "kapatıldı"
    return f"{name}: auto-update {word}"


def start_key(argument: str) -> str | None:
    """Paneli açan `/plugin` biçimleri: argümansız, `manage`, `install <ad>` (bayraksız)."""
    words = argument.split()
    if not words:
        return "discover"
    if words == ["manage"]:
        return "installed"
    if len(words) == 2 and words[0] in ("install", "i") and "/" not in words[1]:
        return f"install:{words[1]}"
    return None


SyncChoose = Callable[[Sequence[Choice], str], "str | None"]
AsyncChoose = Callable[[str, list[Choice]], Awaitable["str | None"]]


def run_sync(state: ReplState, choose: SyncChoose, start: str = "discover") -> str:
    key = start
    while True:
        shown = screen(key)
        value = choose(shown.choices, shown.title)
        if value is None:
            return CLOSED
        step = act(state, key, value)
        if not step.next_key:
            return step.message
        key = step.next_key


async def run_async(state: ReplState, choose: AsyncChoose, start: str = "discover") -> str:
    key = start
    while True:
        shown = screen(key)
        value = await choose(shown.title, list(shown.choices))
        if value is None:
            return CLOSED
        step = act(state, key, value)
        if not step.next_key:
            return step.message
        key = step.next_key
