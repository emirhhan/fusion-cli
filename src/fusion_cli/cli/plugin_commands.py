"""`fusion eklenti …` (takma ad `fusion plugin …`) — eklenti paketleri ve pazar yerleri (P-059).

fusion eklenti kur <yol|https://…|sahip/repo|ad@pazar> [--yes] [--dry-run] [--karma <sha256>]
fusion eklenti listele | dogrula <yol|ad> | ac|kapat <ad> [--scope] [--all]
fusion eklenti kaldir <ad> [--keep-data]
fusion eklenti guven <ad>            değişmiş eklentiyi yeniden onayla
fusion eklenti guncelle <ad> [--yes] kaydedildiği kaynaktan yeniden çek (Claude `plugin update`)
fusion eklenti kesfet [pazar]        kayıtlı pazarlardaki eklentiler
fusion eklenti pazar ekle|liste|guncelle|kaldir
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from ..config.plugin_store import inspect_plugin, installed_plugins, load_state, plugin_folder
from ..core.plugins import PluginError
from ..tools import plugin_install as plugins
from ..tools import plugin_update
from .plugin_result import run_result
from .plugin_view import (
    DIGEST_HINT,
    format_catalog,
    format_installed,
    format_marketplaces,
    format_preview,
)

app = typer.Typer(
    no_args_is_help=True, help="Eklenti paketlerini (beceri+ajan+komut+kanca+MCP) yönet."
)
market_app = typer.Typer(no_args_is_help=True, help="Eklenti pazar yerleri (marketplace.json).")
console = Console()

CONFIRM = "Bu eklenti kurulsun mu?"
CONFIRM_TRUST = "Güncel içerik onaylansın mı?"
NEEDS_YES = "Bu eklenti komut çalıştırabilir; etkileşimsiz terminalde onay için --yes ekle."
INSTALLED = (
    "Kuruldu: {name} (kapsam: {scope} · {status}). "
    "Açık oturuma uygulamak için /reload-plugins çalıştır."
)
REMOVED = "Eklenti kaldırıldı: {name} (kapsam: user; klasör çöpte{data})"
DATA_KEPT = ", veri korundu"
TOGGLED = "Eklenti {verb}: {name} (kapsam: {scope})"
ALL_TOGGLED = "Bütün eklentiler: {state}"
DISABLED_ALL = "{count} eklenti kapatıldı"
ENABLE_ALL_DEPRECATED = "enable --all kullanımdan kalktı; Claude Code'da yok"
TRUSTED = "Onaylandı: {name} (karma yenilendi)"
UPDATED = "Güncellendi: {name}{version}. Bileşenler yeni turda/oturumda etkin olur."
UP_TO_DATE = "Zaten güncel: {name}"
MARKET_UPDATED = "Pazar güncellendi: {name}. Eklentileri gör: fusion eklenti kesfet {name}"
MARKETS_UPDATED = "{count} pazar güncellendi"
MARKET_ADDED = "Pazar eklendi: {name} ({kind}). Eklentileri gör: fusion eklenti kesfet {name}"
MARKET_REMOVED = "Pazar kaldırıldı: {name}"
MARKET_ALSO = "Ayrıca bu pazardan {count} eklenti kaldırıldı:"
SCOPE_HELP = "Kapsam: user, project ya da local (verilmezse algılanır)."
JSON_HELP = "Sonucu son satırda tek JSON nesnesi olarak bas."
DISCOVER_DEPRECATED = (
    "discover/kesfet kullanımdan kalktı; Claude Code karşılığı: "
    "fusion plugin list --json --available"
)


def _run(action: Callable[[], str]) -> None:
    try:
        console.print(escape(action()))
    except plugins.PluginAlreadyInstalledError as error:
        console.print(escape(str(error)))  # Claude: bilgi mesajı, çıkış kodu 0 (#407)
    except PluginError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(1) from error


def approver(yes: bool) -> plugins.ApprovalCallback:
    """Önizlemeyi bas; çalıştırılabilir eklentide onay iste (`--yes` ya da TTY'de soru)."""

    def approve(preview: plugins.PluginPreview) -> bool:
        console.print(escape(format_preview(preview)))
        if not preview.is_executable or yes:
            return True
        if not sys.stdin.isatty():
            console.print(NEEDS_YES)
            return False
        return typer.confirm(CONFIRM, default=False)

    return approve


@app.command("kur")
def install(
    source: str = typer.Argument(..., help="Eklenti adı ya da ad@pazar (eski: klasör/https/repo)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Kanca/MCP onayını sormadan ver."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Yalnız doğrula ve özetle."),
    digest: str = typer.Option(
        "", "--karma", help="--dry-run'da gösterilen karma; içerik değiştiyse kurulmaz."
    ),
    scope: str = typer.Option(
        "", "--scope", "-s", help="Kapsam: user (varsayılan), project, local."
    ),
    marketplace: str = typer.Option(
        "",
        "--marketplace",
        help="Çıplak adı bu kaynaktaki pazardan kur (pazar yoksa önce eklenir).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Sonucu son satırda tek JSON nesnesi bas."),
) -> None:
    """Eklentiyi pazardan kur (betik çalıştırılmaz; kanca/MCP içeriyorsa açık onay ister)."""
    if dry_run:

        def preview() -> str:
            shown = plugins.preview_plugin(source)
            text = format_preview(shown)
            if shown.is_executable and shown.digest:
                text += "\n" + DIGEST_HINT.format(digest=shown.digest, source=source)
            return text

        _run(preview)
        return

    def act() -> tuple[str, dict[str, object]]:
        from ..tools.plugin_install_scope import install_scoped

        done = install_scoped(
            source,
            approve=approver(yes),
            scope=scope,
            marketplace=marketplace,
            expected_digest=digest,
        )
        text = INSTALLED.format(name=done.ident, scope=done.scope, status=done.item.status)
        return text, {"pluginId": done.ident, "scope": done.scope}

    run_result("install", as_json, act)


@app.command("listele")
def list_plugins(
    as_json: bool = typer.Option(False, "--json", help="Listeyi JSON olarak bas."),
    available: bool = typer.Option(
        False, "--available", help="Pazarlardaki kurulmamış eklentileri de ekle (yalnız --json)."
    ),
) -> None:
    """Kurulu eklentiler: sürüm, kapsam, durum (Claude `plugin list`)."""
    if as_json:
        from ..tools.plugin_listing import list_payload

        try:
            payload = list_payload(available=available)
        except PluginError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(1) from error
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    from ..tools.plugin_listing import session_text

    def text() -> str:
        found = installed_plugins()
        session = session_text()
        if session and not found:
            return session
        return "\n\n".join(p for p in (format_installed(found, load_state()), session) if p)

    _run(text)


@app.command("dogrula")
def validate(
    target: str = typer.Argument(..., help="Bildirim dosyası, klasör ya da kurulu eklenti adı"),
    strict: bool = typer.Option(False, "--strict", help="Uyarıları hata say."),
    as_json: bool = typer.Option(False, "--json", help="Raporu tek JSON nesnesi olarak bas."),
) -> None:
    """plugin.json ya da marketplace.json'u doğrula (Claude `plugin validate`; çıkış 0/1/2)."""
    from ..config.plugin_validate import ValidationCrashError, validate_target

    path = Path(target).expanduser()
    record = load_state().plugin(target)
    if record is not None and not path.exists():
        path = plugin_folder(record)
    try:
        run = validate_target(path, strict=strict)
    except ValidationCrashError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error
    if as_json:
        typer.echo(json.dumps(run.payload(), ensure_ascii=False))
    else:
        console.print(escape(run.text()))
        if record is not None and path == plugin_folder(record):
            item = inspect_plugin(record)
            console.print(escape(f"  bütünlük: {item.status} {item.detail}".rstrip()))
    raise typer.Exit(run.exit_code)


def _toggle_json(name: str, everything: bool, enabled: bool, scope: str, as_json: bool) -> None:
    def act() -> tuple[str, dict[str, object]]:
        text = _toggle(name, everything, enabled, scope)
        fields: dict[str, object] = {"pluginId": name} if name else {}
        return text, fields

    run_result("enable" if enabled else "disable", as_json, act)


def _toggle(name: str, everything: bool, enabled: bool, scope: str = "") -> str:
    if everything and (name or scope):
        raise PluginError("--all bir eklenti adı ya da --scope ile birlikte kullanılamaz.")
    if everything and enabled:
        # Claude'da `enable --all` yok: yalnız eski genel kapatmayı kaldırır (kullanımdan kalktı).
        plugins.set_all_disabled(False)
        return ALL_TOGGLED.format(state="açık") + " (" + ENABLE_ALL_DEPRECATED + ")"
    if everything:
        closed = plugins.disable_all_plugins()
        return DISABLED_ALL.format(count=len(closed))
    if not name:
        raise PluginError("Eklenti adı ver ya da --all kullan.")
    written = plugins.set_plugin_enabled(name, enabled, scope=scope)
    verb = "açıldı" if enabled else "kapatıldı"
    return TOGGLED.format(verb=verb, name=name.split("@", 1)[0], scope=written)


@app.command("ac")
def enable(
    name: str = typer.Argument("", help="Eklenti adı ya da ad@pazar"),
    everything: bool = typer.Option(False, "--hepsi", "--all", help="Genel kapatmayı kaldır."),
    scope: str = typer.Option("", "--scope", "-s", help=SCOPE_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Eklentiyi aç (enabledPlugins; kapsam verilmezse local → project → user algılanır)."""
    _toggle_json(name, everything, True, scope, as_json)


@app.command("kapat")
def disable(
    name: str = typer.Argument("", help="Eklenti adı ya da ad@pazar"),
    everything: bool = typer.Option(
        False, "--hepsi", "--all", "-a", help="Bütün eklentileri kapat."
    ),
    scope: str = typer.Option("", "--scope", "-s", help=SCOPE_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Eklentiyi kaldırmadan kapat; bileşenleri yüklenmez."""
    _toggle_json(name, everything, False, scope, as_json)


@app.command("kaldir")
def uninstall(
    name: str = typer.Argument(..., help="Eklenti adı ya da ad@pazar"),
    scope: str = typer.Option("", "--scope", "-s", help="Kapsam (Fusion kurulumları: user)."),
    keep_data: bool = typer.Option(
        False, "--keep-data", help="Eklentinin kalıcı veri klasörünü (CLAUDE_PLUGIN_DATA) koru."
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Eklentiyi kaldır (klasör Fusion çöpüne taşınır; veri klasörü --keep-data yoksa silinir)."""

    def act() -> tuple[str, dict[str, object]]:
        plugins.uninstall_plugin(name, keep_data=keep_data, scope=scope)
        data = DATA_KEPT if keep_data else ""
        text = REMOVED.format(name=name.split("@", 1)[0], data=data)
        return text, {"pluginId": name, "scope": "user"}

    run_result("uninstall", as_json, act)


@app.command("guven")
def trust(
    name: str = typer.Argument(..., help="Eklenti adı"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Sormadan onayla."),
) -> None:
    """Kurulumdan sonra değişen eklentinin güncel içeriğini incele ve yeniden onayla."""

    def approve(preview: plugins.PluginPreview) -> bool:
        console.print(escape(format_preview(preview)))
        if yes:
            return True
        return sys.stdin.isatty() and typer.confirm(CONFIRM_TRUST, default=False)

    _run(lambda: TRUSTED.format(name=plugins.trust_plugin(name, approve=approve).name))


@app.command("guncelle")
def update(
    name: str = typer.Argument(..., help="Eklenti adı"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Kanca/MCP onayını sormadan ver."),
    digest: str = typer.Option("", "--karma", help="Önizlenen karma; içerik değiştiyse kurulmaz."),
) -> None:
    """Eklentiyi kaydedildiği kaynaktan yeniden çek; yeni içerik önizlenir ve onay ister."""

    def act() -> str:
        result = plugin_update.update_plugin(name, approve=approver(yes), expected_digest=digest)
        if not result.changed:
            return UP_TO_DATE.format(name=name)
        version = f" {result.record.version}" if result.record.version else ""
        return UPDATED.format(name=name, version=version)

    _run(act)


@app.command("kesfet")
def discover(marketplace: str = typer.Argument("", help="Yalnız bu pazar")) -> None:
    """Kayıtlı pazarlardaki eklentiler (✓ kurulu). Kullanımdan kalktı (#415)."""
    typer.echo(DISCOVER_DEPRECATED, err=True)
    _run(lambda: format_catalog(plugins.browse(marketplace)))


@market_app.command("ekle")
def market_add(
    source: str = typer.Argument(
        ..., help="./klasör, ./pazar.json, sahip/repo[#ref], https://….git ya da resmi"
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Pazar yeri ekle (`resmi` = anthropics/claude-plugins-official)."""

    def act() -> tuple[str, dict[str, object]]:
        record = plugins.add_marketplace(source)
        text = MARKET_ADDED.format(name=record.name, kind=record.kind)
        return text, {"marketplace": record.name}

    run_result("marketplace-add", as_json, act)


@market_app.command("liste")
def market_list() -> None:
    """Kayıtlı pazar yerleri."""
    _run(lambda: format_marketplaces(load_state()))


@market_app.command("guncelle")
def market_update(
    name: str = typer.Argument("", help="Pazar adı (boşsa hepsi)"),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Git pazarını yeniden klonla; ad verilmezse bütün pazarları yenile (#410)."""

    def act() -> tuple[str, dict[str, object]]:
        if not name:
            count = len(plugin_update.update_all_marketplaces())
            return MARKETS_UPDATED.format(count=count), {}
        plugin_update.update_marketplace(name)
        return MARKET_UPDATED.format(name=name), {"marketplace": name}

    run_result("marketplace-update", as_json, act)


@market_app.command("kaldir")
def market_remove(
    name: str = typer.Argument(..., help="Pazar adı"),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Pazarı ve ondan kurulan bütün eklentileri kaldır (Claude `marketplace remove`)."""

    def act() -> tuple[str, dict[str, object]]:
        removed = plugins.remove_marketplace(name)
        lines = [MARKET_REMOVED.format(name=name)]
        if removed:
            lines.append(MARKET_ALSO.format(count=len(removed)))
            lines.extend(f"  - {plugin}" for plugin in removed)
        return "\n".join(lines), {"marketplace": name}

    run_result("marketplace-remove", as_json, act)


app.add_typer(market_app, name="pazar")

#: Claude Code adları BİRİNCİL ve görünür (`claude plugin install|i …`, #380); Fusion'ın Türkçe
#: adları bir sürüm boyunca gizli, kullanımdan kalkmış takma addır.
_TURKISH_NAMES = frozenset(
    {"kur", "listele", "dogrula", "ac", "kapat", "kaldir", "guven", "guncelle", "kesfet"}
)
TURKISH_DEPRECATED = "'{old}' kullanımdan kalktı; Claude Code adı: fusion plugin {new}"
_CLAUDE_NAMES = {
    "kur": "install",
    "listele": "list",
    "dogrula": "validate",
    "ac": "enable",
    "kapat": "disable",
    "kaldir": "uninstall",
    "guven": "trust",
    "guncelle": "update",
    "kesfet": "list --json --available",
    "ekle": "marketplace add",
    "liste": "marketplace list",
    "pazar": "marketplace",
}


@app.callback()
def _warn_turkish(ctx: typer.Context) -> None:
    """Eklenti paketlerini (beceri+ajan+komut+kanca+MCP) yönet."""
    _warn_alias(ctx.invoked_subcommand or "")


@market_app.callback()
def _warn_turkish_market(ctx: typer.Context) -> None:
    """Eklenti pazar yerleri (marketplace.json)."""
    command = ctx.invoked_subcommand or ""
    market = {"guncelle": "marketplace update", "kaldir": "marketplace remove"}
    if command in market:
        typer.echo(TURKISH_DEPRECATED.format(old=command, new=market[command]), err=True)
    else:
        _warn_alias(command)


def _warn_alias(command: str) -> None:
    new = _CLAUDE_NAMES.get(command)
    if new and command != "kesfet":  # kesfet kendi uyarısını basar
        typer.echo(TURKISH_DEPRECATED.format(old=command, new=new), err=True)


for _info in (*app.registered_commands, *market_app.registered_commands):
    if _info.name in _TURKISH_NAMES | {"ekle", "liste"}:
        _info.hidden = True
for _alias, _command, _hidden in (
    ("install", install, False),
    ("i", install, True),
    ("list", list_plugins, False),
    ("validate", validate, False),
    ("enable", enable, False),
    ("disable", disable, False),
    ("uninstall", uninstall, False),
    ("remove", uninstall, True),
    ("rm", uninstall, True),
    ("update", update, False),
    ("trust", trust, True),
    ("discover", discover, True),
):
    app.command(_alias, hidden=_hidden)(_command)
for _m_alias, _m_command, _m_hidden in (
    ("add", market_add, False),
    ("list", market_list, False),
    ("update", market_update, False),
    ("remove", market_remove, False),
    ("rm", market_remove, True),
):
    market_app.command(_m_alias, hidden=_m_hidden)(_m_command)
app.add_typer(market_app, name="marketplace")

from . import plugin_extra_commands as _extra  # noqa: E402,F401  (details, prune)

for _group in app.registered_groups:
    if _group.name == "pazar":
        _group.hidden = True
