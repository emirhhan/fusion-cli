"""REPL `/plugin` (`/plugins`, `/eklenti`) — Claude Code `/plugin` karşılığı (P-059).

/plugin                         kurulu eklentiler
/plugin kur <kaynak> [--yes]    kanca/MCP içeren eklenti --yes ister (önce önizleme gösterilir)
/plugin dogrula <yol|ad> · ac|kapat <ad|--hepsi> · kaldir <ad> · guven <ad> --yes
/plugin guncelle <ad> [--yes] · /plugin kesfet [pazar] · /plugin pazar ekle|liste|guncelle|kaldir …
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...config.loader import refresh_plugin_mcp_servers
from ...config.plugin_layout import validate_plugin
from ...config.plugin_store import installed_plugins, load_state, plugins_dir
from ...core.plugins import PluginError
from ...tools import plugin_install as plugins
from ...tools import plugin_update
from ..plugin_view import (
    format_catalog,
    format_installed,
    format_marketplaces,
    format_preview,
    format_validation,
)
from .state import ReplState

USAGE = (
    "Kullanım: /plugin [liste | kur <kaynak> [--yes] | dogrula <yol> | ac|kapat <ad|--hepsi> | "
    "kaldir <ad> | guven <ad> --yes | guncelle <ad> [--yes] | kesfet [pazar] | "
    "pazar ekle|liste|guncelle|kaldir]"
)
NEEDS_YES = "İnceledikten sonra onayla: /plugin {verb} {target} --yes"
INSTALLED = (
    "Kuruldu: {name} ({status}). Bileşenler yeni turda kataloğa girer; MCP yeniden başlatınca."
)
DONE = "{name}: {state}"
UP_TO_DATE = "Zaten güncel: {name}"
UPDATED = "Güncellendi: {name}{version}. Bileşenler yeni turda kataloğa girer."
_YES = frozenset({"--yes", "-y", "evet"})
#: `(fiil, hedef)` → kullanıcıya gösterilen son önizlemenin karması. `--yes` ikinci çalıştırması
#: kaynağı YENİDEN çeker; karma farklıysa (araya giren değişiklik) kurulmaz.
_SHOWN: dict[tuple[str, str], str] = {}
_ALL = frozenset({"--hepsi", "--all", "hepsi"})
_ALIASES = {
    "list": "liste",
    "listele": "liste",
    "install": "kur",
    "validate": "dogrula",
    "enable": "ac",
    "disable": "kapat",
    "uninstall": "kaldir",
    "remove": "kaldir",
    "trust": "guven",
    "update": "guncelle",
    "discover": "kesfet",
    "marketplace": "pazar",
}


def plugin_command(state: ReplState, argument: str) -> str:
    words = argument.split()
    verb = _ALIASES.get(words[0].lower(), words[0].lower()) if words else "liste"
    rest = [w for w in words[1:] if w not in _YES]
    confirmed = any(w in _YES for w in words[1:])
    handler = _HANDLERS.get(verb)
    if handler is None:
        return USAGE
    try:
        result = handler(rest, confirmed)
    except PluginError as error:
        return str(error)
    if verb not in {"liste", "dogrula", "kesfet"}:
        if state.capabilities is not None:
            state.capabilities.invalidate()
        # Kapanan eklentinin MCP kaydı oturumdan çıkar; havuz bağlantıyı sonraki turda kapatır.
        state.config = refresh_plugin_mcp_servers(state.config)
    return result


def _list(rest: list[str], confirmed: bool) -> str:
    del rest, confirmed
    return format_installed(installed_plugins(), load_state())


def _approval(
    verb: str, target: str, confirmed: bool, notes: list[str], *, always: bool = False
) -> plugins.ApprovalCallback:
    """`always`: yeniden onayda (guven) içerik değiştiği için her eklenti `--yes` ister."""

    def approve(preview: plugins.PluginPreview) -> bool:
        notes.append(format_preview(preview))
        if (preview.is_executable or always) and not confirmed:
            _SHOWN[(verb, target)] = preview.digest
            notes.append(NEEDS_YES.format(verb=verb, target=target))
            return False
        return True

    return approve


def _install(rest: list[str], confirmed: bool) -> str:
    if len(rest) != 1:
        return USAGE
    notes: list[str] = []
    try:
        item = plugins.install_plugin(
            rest[0],
            approve=_approval("kur", rest[0], confirmed, notes),
            expected_digest=_SHOWN.pop(("kur", rest[0]), "") if confirmed else "",
        )
    except PluginError as error:
        return "\n".join([*notes, str(error)])
    return "\n".join([*notes, INSTALLED.format(name=item.record.name, status=item.status)])


def _trust(rest: list[str], confirmed: bool) -> str:
    if len(rest) != 1:
        return USAGE
    notes: list[str] = []
    try:
        record = plugins.trust_plugin(
            rest[0],
            approve=_approval("guven", rest[0], confirmed, notes, always=True),
            expected_digest=_SHOWN.pop(("guven", rest[0]), "") if confirmed else "",
        )
    except PluginError as error:
        return "\n".join([*notes, str(error)])
    return "\n".join([*notes, DONE.format(name=record.name, state="onaylandı")])


def _update(rest: list[str], confirmed: bool) -> str:
    if len(rest) != 1:
        return USAGE
    notes: list[str] = []
    try:
        result = plugin_update.update_plugin(
            rest[0],
            approve=_approval("guncelle", rest[0], confirmed, notes),
            expected_digest=_SHOWN.pop(("guncelle", rest[0]), "") if confirmed else "",
        )
    except PluginError as error:
        return "\n".join([*notes, str(error)])
    if not result.changed:
        return UP_TO_DATE.format(name=rest[0])
    return "\n".join([*notes, UPDATED.format(name=rest[0], version=result.record.version or "")])


def _validate(rest: list[str], confirmed: bool) -> str:
    del confirmed
    if len(rest) != 1:
        return USAGE
    path = Path(rest[0]).expanduser()
    record = load_state().plugin(rest[0])
    if record is not None and not path.is_dir():
        path = plugins_dir() / record.name
    return format_validation(validate_plugin(path))


def _toggle(enabled: bool) -> Callable[[list[str], bool], str]:
    def handler(rest: list[str], confirmed: bool) -> str:
        del confirmed
        label = "açık" if enabled else "kapalı"
        if rest and rest[0] in _ALL:
            plugins.set_all_disabled(not enabled)
            return DONE.format(name="Bütün eklentiler", state=label)
        if len(rest) != 1:
            return USAGE
        plugins.set_plugin_enabled(rest[0], enabled)
        return DONE.format(name=rest[0], state=label)

    return handler


def _remove(rest: list[str], confirmed: bool) -> str:
    del confirmed
    if len(rest) != 1:
        return USAGE
    plugins.uninstall_plugin(rest[0])
    return DONE.format(name=rest[0], state="kaldırıldı (çöpte)")


def _discover(rest: list[str], confirmed: bool) -> str:
    del confirmed
    return format_catalog(plugins.browse(rest[0] if rest else ""))


def _market(rest: list[str], confirmed: bool) -> str:
    del confirmed
    action = rest[0].lower() if rest else "liste"
    if action in {"liste", "list"}:
        return format_marketplaces(load_state())
    if action in {"ekle", "add"} and len(rest) == 2:
        record = plugins.add_marketplace(rest[1])
        return DONE.format(name=record.name, state=f"pazar eklendi ({record.kind})")
    if action in {"guncelle", "update"} and len(rest) == 2:
        plugin_update.update_marketplace(rest[1])
        return DONE.format(name=rest[1], state="pazar güncellendi")
    if action in {"kaldir", "remove"} and len(rest) == 2:
        plugins.remove_marketplace(rest[1])
        return DONE.format(name=rest[1], state="pazar kaldırıldı")
    return USAGE


_HANDLERS: dict[str, Callable[[list[str], bool], str]] = {
    "liste": _list,
    "kur": _install,
    "dogrula": _validate,
    "ac": _toggle(True),
    "kapat": _toggle(False),
    "kaldir": _remove,
    "guven": _trust,
    "guncelle": _update,
    "kesfet": _discover,
    "pazar": _market,
}
