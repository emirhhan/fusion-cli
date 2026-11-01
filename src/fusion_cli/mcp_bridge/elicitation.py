"""MCP elicitation Claude Code gibi (#257): sunucu görev ortasında kullanıcıdan girdi ister.

Belge (code.claude.com/docs/en/mcp, "Respond to MCP elicitation requests"):

- Form kipi: sunucunun tanımladığı alanlar sorulur, yanıt sunucuya döner.
- URL kipi: bağlantının tarayıcıda açılıp açılmayacağı sorulur. Kaçışlı uzunluğu sınırı
  (~8.000 karakter; kaçış gerektiren her karakter dört sayılır) aşan URL yalnız reddedilebilir.
- İstemci `elicitation: {form: {}, url: {}}` bildirir (SDK, geri çağırım verilince bildirir).

Soru, oturumun kullanıcıya soru sorabilen tarafıyla (`UserAsker`: REPL/TUI/masaüstü) sorulur.
Soru sorabilen taraf yoksa (başsız `-p`, alt süreç) istek `cancel` ile döner: kullanıcı yerine
hiçbir şey uydurulmaz.
"""

from __future__ import annotations

import logging
import webbrowser
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from mcp import types
from mcp.client.session import ElicitationFnT

_LOG = logging.getLogger(__name__)

#: Claude Code URL bağımsız değişken sınırı (kaçışsız ~8.000 karakter).
URL_ARGUMENT_CAP = 8_000
_ESCAPED = frozenset("%&|<>^\"' ()!;$`\\")

ACCEPT = "Kabul et"
DECLINE = "Reddet"
CANCEL = "Vazgeç"
OPEN = "Tarayıcıda aç"


@dataclass(frozen=True, slots=True)
class ElicitOption:
    """`engines.agent.engine_tools.QuestionOption` ile aynı biçim (katman yukarı içe aktarmaz)."""

    label: str
    description: str = ""


class Asker(Protocol):
    async def ask(
        self, question: str, options: tuple[Any, ...] = (), recommended: str | None = None
    ) -> str: ...


_ASKER: list[Asker | None] = [None]


def register_elicitation_asker(asker: Asker | None) -> None:
    """Oturumun soru sorabilen tarafını kaydet (None: kaldır)."""
    _ASKER[0] = asker


def escaped_length(url: str) -> int:
    return sum(4 if char in _ESCAPED else 1 for char in url)


def _options(*labels: str) -> tuple[ElicitOption, ...]:
    return tuple(ElicitOption(label) for label in labels)


def _coerce(kind: str, text: str) -> object:
    value = text.strip()
    if kind == "boolean":
        return value.lower() in ("true", "evet", "e", "yes", "y", "1")
    if kind == "integer":
        return int(value)
    if kind == "number":
        return float(value)
    return value


async def _ask_form(
    asker: Asker, server: str, params: types.ElicitRequestFormParams
) -> types.ElicitResult:
    schema = params.requestedSchema or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or ())
    header = f"MCP sunucusu {server} bilgi istiyor:\n{params.message}"
    choice = await asker.ask(header, _options(ACCEPT, DECLINE, CANCEL), ACCEPT)
    if choice.strip() == DECLINE:
        return types.ElicitResult(action="decline")
    if choice.strip() == CANCEL:
        return types.ElicitResult(action="cancel")
    content: dict[str, Any] = {}
    for name, spec in properties.items():
        field: Mapping[str, Any] = spec if isinstance(spec, Mapping) else {}
        label = str(field.get("title") or name)
        hint = str(field.get("description") or "")
        kind = str(field.get("type") or "string")
        enum = tuple(str(item) for item in field.get("enum") or ())
        options = _options(*enum) if enum else ()
        if not enum and kind == "boolean":
            options = _options("true", "false")
        answer = await asker.ask(f"{label}{(' — ' + hint) if hint else ''}", options)
        if not answer.strip():
            if name in required:
                return types.ElicitResult(action="cancel")
            continue
        try:
            content[str(name)] = _coerce(kind, answer)
        except ValueError:
            return types.ElicitResult(action="cancel")
    return types.ElicitResult(action="accept", content=content)


async def _ask_url(
    asker: Asker, server: str, params: types.ElicitRequestURLParams
) -> types.ElicitResult:
    url = str(params.url)
    header = f"MCP sunucusu {server} bir bağlantı açmak istiyor:\n{params.message}\n{url}"
    if escaped_length(url) > URL_ARGUMENT_CAP:
        await asker.ask(header + "\n(Bağlantı çok uzun; yalnız reddedilebilir.)", _options(DECLINE))
        return types.ElicitResult(action="decline")
    choice = await asker.ask(header, _options(OPEN, DECLINE), OPEN)
    if choice.strip() != OPEN:
        return types.ElicitResult(action="decline")
    try:
        webbrowser.open(url)
    except Exception as error:  # tarayıcı açılamazsa kullanıcı adresi kendisi açar
        _LOG.warning("Tarayıcı açılamadı: %s", type(error).__name__)
    return types.ElicitResult(action="accept")


def elicitation_callback(server: str) -> ElicitationFnT:
    """`ClientSession(elicitation_callback=…)`: kayıtlı soru sorabilen tarafla yanıtla."""

    async def _callback(context: object, params: types.ElicitRequestParams) -> types.ElicitResult:
        del context
        asker = _ASKER[0]
        if asker is None:
            return types.ElicitResult(action="cancel")
        try:
            if isinstance(params, types.ElicitRequestURLParams):
                return await _ask_url(asker, server, params)
            return await _ask_form(asker, server, params)
        except Exception as error:  # soru arayüzü düşerse sunucuya iptal dön, tur sürer
            _LOG.warning("MCP elicitation sorulamadı: %s", type(error).__name__)
            return types.ElicitResult(action="cancel")

    return _callback
