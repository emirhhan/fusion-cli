"""REPL `/oturum-aktar`: web model oturumundan ajan tarayıcı profiline tek yönlü kopya (P-023).

`fusion browser import-web-session` ile aynı akış (`engines.web_session_import`). İki adımlı
onay `/plugin` gibidir: ilk çağrı alan adlarını ve uyarıyı gösterir, hiçbir şey okumaz;
kopya ancak aynı komut `--yes` ile yinelenince yapılır. Çerez değeri hiçbir satıra çıkmaz.

Asenkron çalışır (`ASYNC_COMMANDS`): oturum, web sağlayıcısının paylaşılan Chrome'undan CDP
ile okunur ve REPL olay döngüsü bloklanmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.markup import escape

from ...config.browser_profiles import BrowserProfileStore, default_browser_profile_store
from ...core.errors import FusionError
from ...engines.web_session_import import (
    find_web_session,
    import_web_session,
    preview_web_session,
    validate_domains,
)
from ...ui import messages, theme
from .state import ReplState

_YES = frozenset({"--yes", "-y", "evet"})
_ACCOUNT_FLAGS = frozenset({"--hesap", "--account"})


@dataclass(frozen=True)
class _Request:
    provider: str
    name: str
    domains: tuple[str, ...]
    account: str
    confirmed: bool


def handler(state: ReplState, argument: str) -> str:
    """Masaüstü/uzak yol: bu yüzeylerde komut çalışmaz, doğru yeri söyler."""
    del state, argument
    return messages.WEBOTURUM_DESKTOP


def _store() -> BrowserProfileStore:
    return default_browser_profile_store()


def _parse(argument: str) -> _Request | None:
    words = argument.split()
    confirmed = any(word.lower() in _YES for word in words)
    account = "main"
    positional: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word.lower() in _ACCOUNT_FLAGS and index + 1 < len(words):
            account = words[index + 1]
            index += 2
            continue
        if word.lower() not in _YES:
            positional.append(word)
        index += 1
    if len(positional) < 3:
        return None
    provider, name, *domains = positional
    return _Request(provider, name, tuple(domains), account, confirmed)


async def run(state: ReplState, argument: str, console: Console) -> None:
    del state
    request = _parse(argument)
    if request is None:
        console.print(f"[{theme.DIM}]{messages.WEBOTURUM_USAGE}[/{theme.DIM}]")
        return
    try:
        domains = validate_domains(request.domains)
        source = find_web_session(request.provider, request.account)
        if not request.confirmed:
            preview = preview_web_session(source, domains)
            text = messages.WEBOTURUM_PREVIEW.format(
                provider=source.provider,
                account=source.account,
                name=request.name,
                domains=", ".join(preview.matching or domains),
            )
            console.print(f"[{theme.WARN}]{escape(text)}[/{theme.WARN}]")
            return
        summary = await import_web_session(_store(), source, request.name, domains)
    except FusionError as error:
        console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        return
    done = messages.WEBOTURUM_DONE.format(
        name=summary.name, count=summary.cookie_count, domains=len(summary.domains)
    )
    console.print(f"[{theme.OK}]{escape(done)}[/{theme.OK}]")
