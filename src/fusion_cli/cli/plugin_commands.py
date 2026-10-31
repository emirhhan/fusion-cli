"""`fusion eklenti …` (takma ad `fusion plugin …`) — eklenti paketleri ve pazar yerleri (P-059).

fusion eklenti kur <yol|https://…|sahip/repo|ad@pazar> [--yes] [--dry-run] [--karma <sha256>]
fusion eklenti listele | dogrula <yol|ad> | ac|kapat <ad> [--hepsi] | kaldir <ad>
fusion eklenti guven <ad>            değişmiş eklentiyi yeniden onayla
fusion eklenti guncelle <ad> [--yes] kaydedildiği kaynaktan yeniden çek (Claude `plugin update`)
fusion eklenti kesfet [pazar]        kayıtlı pazarlardaki eklentiler
fusion eklenti pazar ekle|liste|guncelle|kaldir
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from ..config.plugin_layout import validate_plugin
from ..config.plugin_store import inspect_plugin, installed_plugins, load_state, plugins_dir
from ..core.plugins import PluginError
from ..tools import plugin_install as plugins
from ..tools import plugin_update
from .plugin_view import (
    DIGEST_HINT,
    format_catalog,
    format_installed,
    format_marketplaces,
    format_preview,
    format_validation,
)

app = typer.Typer(
    no_args_is_help=True, help="Eklenti paketlerini (beceri+ajan+komut+kanca+MCP) yönet."
)
market_app = typer.Typer(no_args_is_help=True, help="Eklenti pazar yerleri (marketplace.json).")
console = Console()

CONFIRM = "Bu eklenti kurulsun mu?"
CONFIRM_TRUST = "Güncel içerik onaylansın mı?"
NEEDS_YES = "Bu eklenti komut çalıştırabilir; etkileşimsiz terminalde onay için --yes ekle."
INSTALLED = "Kuruldu: {name} ({status}). Etkin olması için yeni bir oturum aç ya da /skills reload."
REMOVED = "Kaldırıldı (çöpte): {name}"
TOGGLED = "{name}: {state}"
ALL_TOGGLED = "Bütün eklentiler: {state}"
TRUSTED = "Onaylandı: {name} (karma yenilendi)"
UPDATED = "Güncellendi: {name}{version}. Bileşenler yeni turda/oturumda etkin olur."
UP_TO_DATE = "Zaten güncel: {name}"
MARKET_UPDATED = "Pazar güncellendi: {name}. Eklentileri gör: fusion eklenti kesfet {name}"
MARKET_ADDED = "Pazar eklendi: {name} ({kind}). Eklentileri gör: fusion eklenti kesfet {name}"
MARKET_REMOVED = "Pazar kaldırıldı: {name}"


def _run(action: Callable[[], str]) -> None:
    try:
        console.print(escape(action()))
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
    source: str = typer.Argument(
        ..., help="Yerel klasör, https git adresi, sahip/repo ya da ad@pazar"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Kanca/MCP onayını sormadan ver."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Yalnız doğrula ve özetle."),
    digest: str = typer.Option(
        "", "--karma", help="--dry-run'da gösterilen karma; içerik değiştiyse kurulmaz."
    ),
) -> None:
    """Eklentiyi kur (betik çalıştırılmaz; kanca/MCP içeriyorsa açık onay ister)."""
    if dry_run:

        def preview() -> str:
            shown = plugins.preview_plugin(source)
            text = format_preview(shown)
            if shown.is_executable and shown.digest:
                text += "\n" + DIGEST_HINT.format(digest=shown.digest, source=source)
            return text

        _run(preview)
        return

    def act() -> str:
        item = plugins.install_plugin(source, approve=approver(yes), expected_digest=digest)
        return INSTALLED.format(name=item.record.name, status=item.status)

    _run(act)


@app.command("listele")
def list_plugins() -> None:
    """Kurulu eklentiler: durum (etkin/kapalı/değişmiş), bileşenler, kaynak."""
    _run(lambda: format_installed(installed_plugins(), load_state()))


@app.command("dogrula")
def validate(
    target: str = typer.Argument(..., help="Eklenti klasörü ya da kurulu eklenti adı"),
) -> None:
    """plugin.json, bileşenler, kancalar ve MCP tanımlarını denetle (Claude `plugin validate`)."""

    def act() -> str:
        state = load_state()
        record = state.plugin(target)
        if record is not None and not Path(target).is_dir():
            item = inspect_plugin(record)
            report = validate_plugin(plugins_dir() / record.name)
            return f"{format_validation(report)}\n  bütünlük: {item.status} {item.detail}".rstrip()
        report = validate_plugin(Path(target).expanduser())
        if not report.ok:
            raise PluginError(format_validation(report))
        return format_validation(report)

    _run(act)


def _toggle(name: str, everything: bool, enabled: bool) -> str:
    label = "açık" if enabled else "kapalı"
    if everything:
        plugins.set_all_disabled(not enabled)
        return ALL_TOGGLED.format(state=label)
    if not name:
        raise PluginError("Eklenti adı ver ya da --hepsi kullan.")
    plugins.set_plugin_enabled(name, enabled)
    return TOGGLED.format(name=name, state=label)


@app.command("ac")
def enable(
    name: str = typer.Argument("", help="Eklenti adı"),
    everything: bool = typer.Option(False, "--hepsi", "--all", help="Genel kapatmayı kaldır."),
) -> None:
    """Eklentiyi (ya da --hepsi ile tüm eklentileri) aç."""
    _run(lambda: _toggle(name, everything, True))


@app.command("kapat")
def disable(
    name: str = typer.Argument("", help="Eklenti adı"),
    everything: bool = typer.Option(False, "--hepsi", "--all", help="Bütün eklentileri kapat."),
) -> None:
    """Eklentiyi kaldırmadan kapat; bileşenleri yüklenmez."""
    _run(lambda: _toggle(name, everything, False))


@app.command("kaldir")
def uninstall(name: str = typer.Argument(..., help="Eklenti adı")) -> None:
    """Eklentiyi kaldır (Fusion çöpüne taşınır, `fusion cop geri-al` ile döner)."""

    def act() -> str:
        plugins.uninstall_plugin(name)
        return REMOVED.format(name=name)

    _run(act)


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
    """Kayıtlı pazarlardaki eklentiler (✓ kurulu)."""
    _run(lambda: format_catalog(plugins.browse(marketplace)))


@market_app.command("ekle")
def market_add(
    source: str = typer.Argument(
        ..., help="Yerel klasör, https git adresi, sahip/repo ya da 'resmi'"
    ),
) -> None:
    """Pazar yeri ekle (`resmi` = anthropics/claude-plugins-official)."""

    def act() -> str:
        record = plugins.add_marketplace(source)
        return MARKET_ADDED.format(name=record.name, kind=record.kind)

    _run(act)


@market_app.command("liste")
def market_list() -> None:
    """Kayıtlı pazar yerleri."""
    _run(lambda: format_marketplaces(load_state()))


@market_app.command("guncelle")
def market_update(name: str = typer.Argument(..., help="Pazar adı")) -> None:
    """Git pazarını yeniden klonla (yerel pazar zaten diskten okunur)."""

    def act() -> str:
        plugin_update.update_marketplace(name)
        return MARKET_UPDATED.format(name=name)

    _run(act)


@market_app.command("kaldir")
def market_remove(name: str = typer.Argument(..., help="Pazar adı")) -> None:
    """Pazar kaydını sil (kurulu eklentiler kalır)."""

    def act() -> str:
        plugins.remove_marketplace(name)
        return MARKET_REMOVED.format(name=name)

    _run(act)


app.add_typer(market_app, name="pazar")

#: Claude Code adlarıyla gizli takma adlar (`fusion plugin install …`).
for _alias, _command in (
    ("install", install),
    ("list", list_plugins),
    ("validate", validate),
    ("enable", enable),
    ("disable", disable),
    ("uninstall", uninstall),
    ("trust", trust),
    ("update", update),
    ("discover", discover),
):
    app.command(_alias, hidden=True)(_command)
for _alias, _command in (
    ("add", market_add),
    ("list", market_list),
    ("update", market_update),
    ("remove", market_remove),
):
    market_app.command(_alias, hidden=True)(_command)
app.add_typer(market_app, name="marketplace", hidden=True)
