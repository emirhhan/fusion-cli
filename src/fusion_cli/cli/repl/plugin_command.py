"""REPL `/plugin` (`/plugins`; `/marketplace` → `/plugin marketplace`) — Claude Code (#382).

Claude Code (cli-reference "/plugin in a session"): argümansız `/plugin` paneli Discover
sekmesinde açar (`plugin_panel`); alt komutlar `help`, `list [--enabled|--disabled]` (`ls`),
`manage`, `install <ad>` (ayrıntı + kapsam seçimi; doğrudan yol/URL "not found in any configured
marketplace"), `enable`/`disable`/`uninstall`, `configure`, `validate`, `details`, `update`, `tag`
ve `marketplace` (`market`) `add|list|update|remove|rm`.

Fusion'ın eski Türkçe alt komutları (`kur`, `ac`, `kapat`, `kaldir`, `guncelle`, `dogrula`,
`kesfet`, `pazar`, `guven`) bir sürüm boyunca kullanımdan kalkmış takma addır: uyarı satırıyla
eski davranışı sürdürür (`kur` doğrudan kaynağı kurar).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from ...config.loader import refresh_plugin_mcp_servers
from ...config.plugin_store import installed_plugins, load_state, plugin_folder
from ...config.plugin_validate import ValidationCrashError, validate_target
from ...core.plugins import PluginError
from ...tools import plugin_install as plugins
from ...tools import plugin_update
from ..plugin_view import format_catalog, format_installed, format_marketplaces, format_preview
from .state import ReplState

USAGE = (
    "Kullanım: /plugin [help | list [--enabled|--disabled] | manage | install <ad[@pazar]> "
    "[--scope user|project|local] | enable|disable <ad> [--scope …] | uninstall <ad> "
    "[--keep-data] | configure <ad> | validate <yol> [--strict] | details <ad> | update <ad> | "
    "tag [yol] [--dry-run] | marketplace add|list|update|remove <…>]"
)
NEEDS_YES = "İnceledikten sonra onayla: /plugin {verb} {target} --yes"
INSTALLED = (
    "Kuruldu: {name} (kapsam: {scope} · {status}). Açık oturuma uygulamak için /reload-plugins."
)
DONE = "{name}: {state}"
UP_TO_DATE = "Zaten güncel: {name}"
UPDATED = "Güncellendi: {name}{version}. Bileşenler yeni turda kataloğa girer."
DEPRECATED = "'/plugin {old}' kullanımdan kalktı; Claude Code adı: /plugin {new}"
_YES = frozenset({"--yes", "-y", "evet"})
#: `(fiil, hedef)` → kullanıcıya gösterilen son önizlemenin karması. `--yes` ikinci çalıştırması
#: kaynağı YENİDEN çeker; karma farklıysa (araya giren değişiklik) kurulmaz.
_SHOWN: dict[tuple[str, str], str] = {}
_ALL = frozenset({"--hepsi", "--all", "-a", "hepsi"})
_CLAUDE = {"ls": "list", "i": "install", "remove": "uninstall", "rm": "uninstall"}
_CLAUDE |= {"market": "marketplace", "marketplaces": "marketplace", "plugins": "list"}
#: Eski Türkçe ad → Claude adı (kullanımdan kalktı uyarısı).
_TURKISH = {
    "liste": "list",
    "listele": "list",
    "kur": "install",
    "dogrula": "validate",
    "ac": "enable",
    "kapat": "disable",
    "kaldir": "uninstall",
    "guven": "trust",
    "guncelle": "update",
    "kesfet": "list --available",
    "pazar": "marketplace",
    "discover": "list --available",
}


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def plugin_command(state: ReplState, argument: str) -> str:
    words = argument.split()
    if not words:
        return _open_panel(state, "discover")
    raw = words[0].lower()
    verb = _CLAUDE.get(raw, _TURKISH.get(raw, raw))
    if raw in ("discover", "kesfet"):
        verb = "discover"
    legacy = raw in _TURKISH
    rest = [w for w in words[1:] if w not in _YES]
    confirmed = any(w in _YES for w in words[1:])
    handler = _HANDLERS.get(verb.split()[0])
    if handler is None:
        return USAGE
    try:
        result = handler(state, rest, confirmed, legacy)
    except PluginError as error:
        result = str(error)
    if verb not in {"list", "validate", "discover", "help", "details", "configure", "tag"}:
        if state.capabilities is not None:
            state.capabilities.invalidate()
        # Kapanan eklentinin MCP kaydı oturumdan çıkar; havuz bağlantıyı sonraki turda kapatır.
        state.config = refresh_plugin_mcp_servers(state.config)
    if legacy:
        return DEPRECATED.format(old=raw, new=_TURKISH[raw]) + "\n" + result
    return result


def marketplace_command(state: ReplState, argument: str) -> str:
    """`/marketplace …` = `/plugin marketplace …` (Claude takma adı)."""
    return plugin_command(state, f"marketplace {argument}".strip())


def _open_panel(state: ReplState, start: str) -> str:
    """Satır-içi REPL'de ok tuşlu panel; terminal değilse (masaüstü/boru) kurulu liste."""
    if not _interactive():
        return format_installed(installed_plugins(), load_state())
    from ...ui.picker import pick
    from .plugin_panel import run_sync

    return run_sync(state, lambda choices, title: pick(choices, title=title), start)


Handler = Callable[[ReplState, list[str], bool, bool], str]


def _help(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, rest, confirmed, legacy
    return USAGE


def _list(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, confirmed, legacy
    found = installed_plugins()
    if "--enabled" in rest:
        found = tuple(item for item in found if item.record.enabled)
    elif "--disabled" in rest:
        found = tuple(item for item in found if not item.record.enabled)
    return format_installed(found, load_state())


def _manage(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del rest, confirmed, legacy
    return _open_panel(state, "installed")


def _approval(
    verb: str, target: str, confirmed: bool, notes: list[str], *, always: bool = False
) -> plugins.ApprovalCallback:
    """`always`: yeniden onayda (trust) içerik değiştiği için her eklenti `--yes` ister."""

    def approve(preview: plugins.PluginPreview) -> bool:
        notes.append(format_preview(preview))
        if (preview.is_executable or always) and not confirmed:
            _SHOWN[(verb, target)] = preview.digest
            notes.append(NEEDS_YES.format(verb=verb, target=target))
            return False
        return True

    return approve


def _install(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    from ...tools.plugin_install_scope import install_scoped

    names, scope = _scope_flag(rest)
    if len(names) != 1:
        return USAGE
    target = names[0]
    verb = "kur" if legacy else "install"
    if not legacy and not confirmed and not scope and _interactive():
        return _open_panel(state, f"install:{target}")  # Claude: ayrıntı + kapsam seçimi
    notes: list[str] = []
    try:
        done = install_scoped(
            target,
            approve=_approval(verb, target, confirmed, notes),
            scope=scope,
            expected_digest=_SHOWN.pop((verb, target), "") if confirmed else "",
            allow_direct=legacy,
        )
    except plugins.PluginAlreadyInstalledError as error:
        return str(error)
    except PluginError as error:
        return "\n".join([*notes, str(error)])
    text = INSTALLED.format(name=done.ident, scope=done.scope, status=done.item.status)
    return "\n".join([*notes, text])


def _trust(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, legacy
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


def _update(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, legacy
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


def _validate(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, confirmed, legacy
    names = [w for w in rest if w != "--strict"]
    if len(names) != 1:
        return USAGE
    path = Path(names[0]).expanduser()
    record = load_state().plugin(names[0])
    if record is not None and not path.exists():
        path = plugin_folder(record)
    try:
        return validate_target(path, strict="--strict" in rest).text()
    except ValidationCrashError as error:
        return str(error)


def _toggle(enabled: bool) -> Handler:
    def handler(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
        del state, confirmed, legacy
        label = "açık" if enabled else "kapalı"
        if rest and rest[0] in _ALL:
            if enabled:  # Claude'da `enable --all` yok; eski genel kapatmayı kaldırır.
                plugins.set_all_disabled(False)
            else:
                plugins.disable_all_plugins()
            return DONE.format(name="Bütün eklentiler", state=label)
        names, scope = _scope_flag(rest)
        if len(names) != 1:
            return USAGE
        written = plugins.set_plugin_enabled(names[0], enabled, scope=scope)
        return DONE.format(name=names[0], state=f"{label} (kapsam: {written})")

    return handler


def _remove(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, confirmed, legacy
    names, scope = _scope_flag([w for w in rest if w != "--keep-data"])
    if len(names) != 1:
        return USAGE
    keep = "--keep-data" in rest
    plugins.uninstall_plugin(names[0], keep_data=keep, scope=scope)
    kept = " (veri korundu)" if keep else ""
    return DONE.format(name=names[0], state=f"kaldırıldı{kept}")


def _scope_flag(words: list[str]) -> tuple[list[str], str]:
    """`--scope x` / `-s x` / `--scope=x` (#376); kalan sözcükler ve kapsam."""
    names: list[str] = []
    scope = ""
    items = iter(words)
    for word in items:
        if word in {"--scope", "-s"}:
            scope = next(items, "")
        elif word.startswith("--scope="):
            scope = word.split("=", 1)[1]
        else:
            names.append(word)
    return names, scope


def _discover(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, confirmed, legacy
    return format_catalog(plugins.browse(rest[0] if rest else ""))


def _details(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    from ...tools.plugin_listing import details_text

    del state, confirmed, legacy
    return details_text(rest[0]) if len(rest) == 1 else USAGE


def _configure(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    """Seçenekleri ve durumlarını göster (değer girişi: `plugin configure --values-stdin`)."""
    from ...config import plugin_user_config as user_config
    from ...config.plugin_store import plugins_dir
    from ...tools.plugin_toggle import find_record

    del state, confirmed, legacy
    if len(rest) != 1:
        return USAGE
    base = plugins_dir()
    record = find_record(load_state(base), rest[0])
    schema = user_config.read_schema(plugin_folder(record, base))
    if not schema:
        return "Bu eklentinin userConfig seçeneği yok."
    saved = set(user_config.saved_values(record.name, base))
    rows = [f"{rest[0]} seçenekleri (değer gir: fusion plugin configure {rest[0]} --values-stdin):"]
    for option in schema:
        flags = ["required" if option.required else "optional"]
        flags += ["sensitive"] if option.sensitive else []
        flags.append("set" if option.key in saved else "not set")
        rows.append(f"  {option.key}  {' · '.join(flags)}  {option.title}")
    return "\n".join(rows)


def _tag(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    from ...tools.plugin_tag import create_tag, plan_tag

    del state, confirmed, legacy
    paths = [w for w in rest if not w.startswith("-")]
    force = "--force" in rest or "-f" in rest
    plan = plan_tag(Path(paths[0] if paths else "."), force=force)
    header = f"Plugin:  {plan.name}\nVersion: {plan.version}\nTag:     {plan.tag}"
    if "--dry-run" in rest:
        return f"{header}\nDeneme: {plan.tag_command}"
    create_tag(plan, force=force)
    return f"{header}\nEtiket oluşturuldu: {plan.tag}\n  Göndermek için: {plan.push_command}"


def _market(state: ReplState, rest: list[str], confirmed: bool, legacy: bool) -> str:
    del state, confirmed, legacy
    action = rest[0].lower() if rest else "list"
    if action in {"liste", "list"}:
        return format_marketplaces(load_state())
    if action in {"ekle", "add"} and len(rest) == 2:
        record = plugins.add_marketplace(rest[1])
        return DONE.format(name=record.name, state=f"pazar eklendi ({record.kind})")
    from ...tools.plugin_market_sync import sync_by_name

    if action in {"guncelle", "update"} and len(rest) == 1:
        updated = plugin_update.update_all_marketplaces()
        notes = [n for record in updated for n in sync_by_name(record.name)]
        return "\n".join([f"{len(updated)} pazar güncellendi", *notes])
    if action in {"guncelle", "update"} and len(rest) == 2:
        plugin_update.update_marketplace(rest[1])
        notes = list(sync_by_name(rest[1]))  # renames / forceRemoveDeletedPlugins (#397)
        return "\n".join([DONE.format(name=rest[1], state="pazar güncellendi"), *notes])
    if action in {"kaldir", "remove", "rm"} and len(rest) == 2:
        from ...tools.plugin_market_declare import undeclare

        removed = plugins.remove_marketplace(rest[1])
        undeclare(rest[1])
        names = ", ".join(removed)
        also = f"; ayrıca {len(removed)} eklenti kaldırıldı: {names}" if removed else ""
        return DONE.format(name=rest[1], state="pazar kaldırıldı" + also)
    return USAGE


_HANDLERS: dict[str, Handler] = {
    "help": _help,
    "list": _list,
    "manage": _manage,
    "install": _install,
    "validate": _validate,
    "enable": _toggle(True),
    "disable": _toggle(False),
    "uninstall": _remove,
    "trust": _trust,
    "update": _update,
    "discover": _discover,
    "details": _details,
    "configure": _configure,
    "tag": _tag,
    "marketplace": _market,
}
