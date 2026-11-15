"""`--json` hata satırının `failureCode`'u ve komut onayı (Claude Code `plugin … --json`, #381).

Kodlar Claude Code 2.1.287'nin `failureCode` değerleridir; Fusion'da karşılığı olan hatalar
eşlenir, gerisi alanı taşımaz (Claude da her hatada kod vermez).
"""

from __future__ import annotations

import string
import sys
from collections.abc import Callable

import typer
from rich.console import Console
from rich.markup import escape

from ..core.plugins import PluginError
from ..tools import plugin_install, plugin_toggle
from ..tools.plugin_source_fetch import (
    CommandConsent,
    CommandRefusedError,
    ShownCommand,
    accept_by_sha,
)

CODE_REFUSED = "command_source_refused"
CODE_DECLINED = "command_source_declined"
ERR_YES_CONFLICT = "--accept-command ile -y/--yes birlikte kullanılamaz"
CONFIRM_COMMAND = "Bu komut çalıştırılsın mı?"
SHOWN_COMMAND = (
    'Pazar "{plugin}" için şu yerel komutu çalıştıracak ({what}):\n  {command}\n'
    "Komut sizin kullanıcınızla, ev klasörünüzden çalışır. "
    "Yalnız güvendiğiniz pazarlarda onaylayın."
)

console = Console(stderr=True)


class CommandDeclinedError(CommandRefusedError):
    """Kullanıcı gösterilen komutu reddetti (Claude: "Aborted.")."""


def _pattern(template: str) -> Callable[[str], bool]:
    """Şablonun ilk yer tutucuya kadarki sabit öneki ve sonraki sabit parçalar."""
    parts = [text for text, *_ in string.Formatter().parse(template) if text]
    return lambda message: all(part.strip() in message for part in parts if part.strip())


_TEMPLATES: tuple[tuple[str, str], ...] = (
    (plugin_toggle.ERR_NOT_INSTALLED, "not_installed"),
    (plugin_toggle.ERR_AMBIGUOUS, "ambiguous_marketplace"),
    (plugin_install.ERR_AMBIGUOUS, "ambiguous_marketplace"),
    (plugin_toggle.ERR_ALREADY, "already_in_goal_state"),
    (plugin_toggle.ERR_UNINSTALL_SCOPE, "not_installed_at_scope"),
    (plugin_install.ERR_NO_ENTRY, "not_found"),
)
_MATCHERS = tuple((_pattern(template), code) for template, code in _TEMPLATES)


def failure_code(error: PluginError) -> str:
    if isinstance(error, CommandDeclinedError):
        return CODE_DECLINED
    if isinstance(error, CommandRefusedError):
        return CODE_REFUSED
    explicit = getattr(error, "failure_code", "")
    if isinstance(explicit, str) and explicit:
        return explicit
    message = str(error)
    return next((code for matches, code in _MATCHERS if matches(message)), "")


def failure_fields(error: PluginError) -> dict[str, object]:
    fields: dict[str, object] = {}
    code = failure_code(error)
    if code:
        fields["failureCode"] = code
    shown = getattr(error, "shown", None)
    if isinstance(shown, ShownCommand):
        fields["shownCommand"] = shown.to_json()
    return fields


def command_consent(yes: bool, accept_command: str) -> CommandConsent | None:
    """`-y` gösterileni, `--accept-command` yalnız o özeti kabul eder; ikisi yoksa terminalde
    sorulur, terminal değilse onay yoktur (komut reddedilir)."""
    if accept_command and yes:
        raise PluginError(ERR_YES_CONFLICT)
    if accept_command:
        return accept_by_sha(accept_command)
    if yes:
        return _show_and(lambda _shown: True)
    if sys.stdin.isatty() and sys.stdout.isatty():
        return _show_and(_ask)
    return None


def _ask(shown: ShownCommand) -> bool:
    if typer.confirm(CONFIRM_COMMAND, default=False):
        return True
    raise CommandDeclinedError("Aborted.", shown)


def _show_and(decide: CommandConsent) -> CommandConsent:
    def consent(shown: ShownCommand) -> bool:
        what = "eklenti kaynağı" if shown.kind == "command_source" else "arşiv başlıkları"
        console.print(
            escape(SHOWN_COMMAND.format(plugin=shown.plugin_id, what=what, command=shown.command))
        )
        return decide(shown)

    return consent
