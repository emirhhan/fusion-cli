"""`fusion knowledge` komut ailesi — ortak bilgi paketini durumla ve senkronize et.

İstemci paketi yalnızca okur ve doğruladıktan sonra yerel belleğe uygular; global
depoya asla yazmaz. İmza anahtarı bütünlük/oynama tespiti içindir (sır değil).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ..config.loader import load_config
from ..knowledge import KnowledgeManifest, read_manifest, status, sync
from ..knowledge.signing import DEFAULT_PUBLIC_KEY
from ..memory.factory import Memory, build_memory
from ..ui import theme

app = typer.Typer(no_args_is_help=True, help="Ortak bilgi paketini görüntüle ve senkronize et.")
console = Console()

#: Varsayılan manifest yolu (modül-seviyesi singleton: B008'den kaçınmak için).
_DEFAULT_PACKAGE = Path("knowledge/manifest.json")

#: Kullanıcıya görünen metinler tek yerde.
_STATE_FILENAME = "knowledge_state.json"
_MSG_NO_PACKAGE = "Bilgi paketi bulunamadı: {path}"
_MSG_STATUS = "Bilgi paketi v{version}: {added} yeni, {updated} değişen, {unchanged} güncel."
_MSG_SYNC_OK = "Senkronize edildi: {added} yeni, {updated} değişen ders uygulandı."
_MSG_SYNC_FAIL = "Paket reddedildi (uygulanmadı):"


@app.command("status")
def knowledge_status(
    package: Annotated[Path, typer.Argument(help="Manifest yolu")] = _DEFAULT_PACKAGE,
) -> None:
    """Yerel duruma göre pakette neyin yeni/değişmiş olduğunu göster (uygulamaz)."""
    manifest = _read_or_exit(package)
    plan = status(manifest, _state_path())
    console.print(
        _MSG_STATUS.format(
            version=manifest.version,
            added=len(plan.added),
            updated=len(plan.updated),
            unchanged=len(plan.unchanged),
        )
    )


@app.command("sync")
def knowledge_sync(
    package: Annotated[Path, typer.Argument(help="Manifest yolu")] = _DEFAULT_PACKAGE,
) -> None:
    """Paketi doğrula ve yalnızca değişen dersleri yerel belleğe uygula."""
    manifest = _read_or_exit(package)
    memory = _open_memory()
    report = sync(manifest, memory.lessons, state_path=_state_path(), public_key=DEFAULT_PUBLIC_KEY)
    if not report.ok:
        console.print(f"[{theme.ERROR}]{_MSG_SYNC_FAIL}[/{theme.ERROR}]")
        for problem in report.problems:
            console.print(f"[{theme.WARN}]  - {problem}[/{theme.WARN}]")
        raise typer.Exit(1)
    console.print(_MSG_SYNC_OK.format(added=report.added, updated=report.updated))


# --------------------------------------------------------------------------- #


def _read_or_exit(package: Path) -> KnowledgeManifest:
    if not package.exists():
        console.print(f"[{theme.ERROR}]{_MSG_NO_PACKAGE.format(path=package)}[/{theme.ERROR}]")
        raise typer.Exit(1)
    return read_manifest(package)


def _state_path() -> Path:
    return load_config().memory_dir / _STATE_FILENAME


def _open_memory() -> Memory:
    memory = build_memory(load_config(), root=Path.cwd())
    if not memory.enabled:
        console.print(f"[{theme.ERROR}]Bellek açılamadı; senkronizasyon yapılamaz.[/{theme.ERROR}]")
        raise typer.Exit(1)
    return memory
