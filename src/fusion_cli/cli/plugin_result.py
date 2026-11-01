"""Eklenti komutlarının `--json` sonuç satırı (Claude Code `plugin … --json`, #381).

Son stdout satırı tek JSON nesnesi: her zaman `command`, `outcome` (`ok`|`failed`), `message`;
uygun olduğunda `pluginId`, `scope`, `marketplace`; hatada `failureCode` ve (pazar komutu
reddedildiyse) `shownCommand` (`sha256` → `--accept-command`). Çıkış kodu başarıda 0, hatada 1.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import typer
from rich.console import Console
from rich.markup import escape

from ..core.plugins import PluginError
from ..tools.plugin_install import PluginAlreadyInstalledError

OUTCOME_OK = "ok"
OUTCOME_FAILED = "failed"

console = Console()

ResultAction = Callable[[], tuple[str, dict[str, object]]]


def run_result(command: str, as_json: bool, action: ResultAction) -> None:
    """Eylemi koştur; insan okunur mesaj ya da `--json` nesnesi bas; hatada 1 ile çık."""
    failed = False
    fields: dict[str, object] = {}
    try:
        message, fields = action()
    except PluginAlreadyInstalledError as error:
        message = str(error)  # Claude: bilgi mesajı, çıkış 0 (#407)
    except PluginError as error:
        from .plugin_failure import failure_fields

        message, failed = str(error), True
        fields = failure_fields(error)  # #381: failureCode, shownCommand
    if as_json:
        outcome = OUTCOME_FAILED if failed else OUTCOME_OK
        payload = {"command": command, "outcome": outcome, "message": message, **fields}
        typer.echo(json.dumps(payload, ensure_ascii=False))
    elif failed:
        console.print(f"[red]{escape(message)}[/red]")
    else:
        console.print(escape(message))
    if failed:
        raise typer.Exit(1)
