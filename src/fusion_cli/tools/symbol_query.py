"""İsteğe bağlı, çağrıya ait yerel LSP oturumu ve açık sözcüksel yedek yol."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..config.keys import environ_snapshot
from ..core.constants import (
    MAX_OUTPUT_CHARS,
    MAX_READ_BYTES,
    MAX_SEARCH_HITS,
    PROCESS_POLL_S,
)
from ..core.errors import PathAccessError, ProcessCancelledError
from ..core.localization import MAX_LOCALIZATION_CANDIDATES, localization_symbol
from ..core.owned_thread import await_cancellable_thread, await_owned_thread
from ..core.process_control import process_group_options
from ..core.redaction import redact
from ..core.source_read import read_scoped_source
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import ArgumentError, optional_str, require_str
from .files import display_path, resolve_path
from .lsp_client import HEADER_LIMIT, LspProtocolError, LspQuery, close_owned, exchange
from .registry import _CancellationEvent
from .search import SearchSource, is_searchable_source, search_code

_ACTIONS = frozenset({"definition", "references", "diagnostics"})
_ARGUMENTS = frozenset({"action", "path", "line", "character", "symbol"})
_LANGUAGES = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".rs": "rust",
    ".go": "go",
}
_LEXICAL_NOTE = "lexical fallback: anlamsal LSP sonucu değildir."


@dataclass(frozen=True, slots=True)
class SymbolQuerySettings:
    """Yalnız güvenilir kullanıcı yapılandırmasından gelen komut; araç argümanı değildir.

    Sunucu kullanıcı tarafından önceden kurulmuş olmalı. Adaptör paket kurmaz ve
    komut keşfetmez. Ortak yapılandırmaya bağlanması Task 8b'nin sorumluluğudur.
    """

    command: tuple[str, ...] = ()
    timeout_s: float = 8.0

    def __post_init__(self) -> None:
        if not isinstance(self.command, tuple) or any(
            not isinstance(part, str) or not part or "\x00" in part for part in self.command
        ):
            raise ValueError("LSP komutu boş olmayan bağımsız argümanlardan oluşmalı.")
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("LSP süre sınırı pozitif ve sonlu olmalı.")


@dataclass(frozen=True, slots=True)
class _Document:
    path: Path
    text: str
    action: str
    line: int
    character: int
    symbol: str

    @property
    def uri(self) -> str:
        return self.path.as_uri()


def _document(args: ToolArgs, context: ToolContext) -> _Document:
    if set(args) - _ARGUMENTS:
        raise ArgumentError("Sembol sorgusunda bilinmeyen alan var; sunucu komutu verilemez.")
    action = require_str(args, "action")
    if action not in _ACTIONS:
        raise ArgumentError("Sembol eylemi definition, references veya diagnostics olmalı.")
    path = resolve_path(context, require_str(args, "path")).resolve()
    _check_path(path, context)
    if not is_searchable_source(path, context.root.resolve()) or not path.is_file():
        raise ArgumentError("Sembol sorgusu için proje içindeki bir kaynak dosyasını seçin.")
    source = read_scoped_source(
        context.root.resolve(), path.relative_to(context.root.resolve()), max_bytes=MAX_READ_BYTES
    )
    if source is None:
        raise ArgumentError("Kaynak güvenli ve kararlı biçimde okunamadı; dosya yolunu denetleyin.")
    positions = [args.get("line", 0), args.get("character", 0)]
    if any(type(value) is not int or value < 0 for value in positions):
        raise ArgumentError("Satır ve karakter sıfır tabanlı, negatif olmayan tamsayı olmalı.")
    line, character = int(str(positions[0])), int(str(positions[1]))
    text = source.decode("utf-8")
    lines = text.split("\n")
    if line >= len(lines) or character > len(lines[line].encode("utf-16-le")) // 2:
        raise ArgumentError("Satır veya UTF-16 karakter konumu dosyanın dışında.")
    symbol = optional_str(args, "symbol", "")
    if len(symbol) > HEADER_LIMIT:
        raise ArgumentError("Sembol araması çok uzun; adı kısaltın.")
    return _Document(path, text, action, line, character, symbol)


def _check_path(path: Path, context: ToolContext) -> None:
    resolve_path(context, str(path))
    if not path.is_relative_to(context.root.resolve()):
        raise PathAccessError("LSP sorgusu ve sonuçları proje kökünün içinde kalmalı.")


async def _fallback(document: _Document, context: ToolContext) -> ToolResult:
    if document.action == "diagnostics":
        return ToolResult.failure(
            f"{_LEXICAL_NOTE} Sunucu yok; gerçek diagnostics alınamadı.",
            structured={"source": "lexical", "action": document.action},
        )
    if not document.symbol:
        return ToolResult.failure(
            f"{_LEXICAL_NOTE} Metin araması için 'symbol' alanına adı yazın.",
            structured={"source": "lexical", "action": document.action},
        )
    cancelled = _CancellationEvent(context.cancelled)
    result = await await_cancellable_thread(
        partial(search_code, source=SearchSource(document.path, document.text)),
        cancelled.set,
        {"pattern": re.escape(document.symbol), "path": str(document.path)},
        replace(context, cancelled=cancelled),
    )
    output = f"{_LEXICAL_NOTE}\n{result.output}"
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[: MAX_OUTPUT_CHARS - 50] + "\n… (sonuç kısmidir; sorguyu daraltın)"
    return replace(
        result,
        output=output,
        structured={**(result.structured or {}), "source": "lexical", "action": document.action},
    )


class SymbolQuery:
    """Her çağrıda tek süreç aç; bütün çıkış yollarında sahip olunan grubu kapat."""

    def __init__(self, settings: SymbolQuerySettings) -> None:
        self._settings = settings

    async def __call__(self, args: ToolArgs, context: ToolContext) -> ToolResult:
        if context.cancelled.is_set():
            return ToolResult.failure("Sembol sorgusu başlamadan iptal edildi.")
        try:
            document = await await_owned_thread(_document, args, context)
        except (OSError, UnicodeError) as error:
            return ToolResult.failure(f"Sembol dosyası okunamadı ({type(error).__name__}).")
        if not self._settings.command:
            return await _fallback(document, context)
        try:
            process = await self._start(context)
        except FileNotFoundError:
            return await _fallback(document, context)
        except OSError as error:
            return ToolResult.failure(f"LSP sunucusu başlatılamadı ({type(error).__name__}).")
        tasks = [
            asyncio.create_task(
                exchange(
                    process,
                    LspQuery(
                        uri=document.uri,
                        root_uri=context.root.resolve().as_uri(),
                        text=document.text,
                        language=_LANGUAGES.get(document.path.suffix, "plaintext"),
                        action=document.action,
                        line=document.line,
                        character=document.character,
                    ),
                )
            ),
            asyncio.create_task(_wait_cancelled(context)),
        ]
        try:
            done, _ = await asyncio.wait(
                tasks, timeout=self._settings.timeout_s, return_when=asyncio.FIRST_COMPLETED
            )
            if tasks[1] in done:
                raise ProcessCancelledError("Sembol sorgusu iptal edildi.")
            if tasks[0] not in done:
                return ToolResult.failure("LSP süre sınırına ulaştı; sorguyu daraltın.")
            return await await_owned_thread(_render, await tasks[0], document, context)
        except (ProcessCancelledError, LspProtocolError) as error:
            return ToolResult.failure(str(error))
        except (
            OSError,
            ValueError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ) as error:
            return ToolResult.failure(f"LSP yanıtı okunamadı ({type(error).__name__}).")
        finally:
            await close_owned(process, tasks)

    async def _start(self, context: ToolContext) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            *self._settings.command,
            cwd=context.root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                name: value
                for name, value in environ_snapshot().items()
                if name not in context.hidden_env
            },
            limit=HEADER_LIMIT,
            **process_group_options(),
        )


async def _wait_cancelled(context: ToolContext) -> None:
    while not context.cancelled.is_set():  # noqa: ASYNC110 - paylaşılan threading.Event yoklanır
        await asyncio.sleep(PROCESS_POLL_S)


def _render(result: object, document: _Document, context: ToolContext) -> ToolResult:
    lines = [f"LSP {document.action}: {display_path(context, document.path)}"]
    if document.action == "diagnostics" and (
        not isinstance(result, dict)
        or not isinstance(result.get("items"), list)
        or result.get("kind") != "full"
    ):
        raise LspProtocolError("LSP tam ve güncel diagnostics döndürmedi; tekrar sorgulayın.")
    entries = (
        result.get("items")
        if isinstance(result, dict) and document.action == "diagnostics"
        else result
    )
    entries = entries if isinstance(entries, list) else [entries] if entries is not None else []
    candidates: list[dict[str, str]] = []
    for entry in entries[:MAX_SEARCH_HITS]:
        if not isinstance(entry, dict):
            raise LspProtocolError("LSP sonuç girdisi geçersiz.")
        if document.action == "diagnostics":
            shown = display_path(context, document.path)
            detail = redact(str(entry.get("message", "")))[:MAX_OUTPUT_CHARS]
        else:
            uri = entry.get("uri", entry.get("targetUri"))
            if not isinstance(uri, str):
                raise LspProtocolError("LSP sonuç yolu eksik.")
            parsed = urlsplit(uri)
            if parsed.scheme != "file" or parsed.netloc:
                raise LspProtocolError("LSP sonucu yerel bir dosya olmalı.")
            path = Path(unquote(parsed.path)).resolve()
            _check_path(path, context)
            if not is_searchable_source(path, context.root.resolve()):
                raise LspProtocolError("LSP sonucu gizli dosyaya yöneldi; sonuç reddedildi.")
            shown, detail = display_path(context, path), ""
        location = entry.get("range", entry.get("targetSelectionRange", {}))
        start = location.get("start", {}) if isinstance(location, dict) else {}
        line = start.get("line", 0) if isinstance(start, dict) else 0
        if type(line) is not int or line < 0:
            raise LspProtocolError("LSP satır konumu geçersiz.")
        lines.append(f"{shown}:{line + 1}: {detail}")
        evidence_path = document.path if document.action == "diagnostics" else path
        if evidence_path == document.path and len(candidates) < MAX_LOCALIZATION_CANDIDATES:
            candidates.append(_document_candidate(document, context))
    output = "\n".join(lines)
    if len(entries) > MAX_SEARCH_HITS or len(output) > MAX_OUTPUT_CHARS:
        output = output[: MAX_OUTPUT_CHARS - 50] + "\n… (sonuç kısmidir; sorguyu daraltın)"
    return ToolResult(
        output,
        structured={
            "source": "lsp",
            "action": document.action,
            "localization_candidates": tuple(candidates),
        },
    )


def _document_candidate(document: _Document, context: ToolContext) -> dict[str, str]:
    """Yalnız sunucuya gönderilen belge snapshot'ına kaynak kanıtı bağla.

    Başka hedefin sunucu tarafından hangi sürümde okunduğu bilinmez; o hedef
    için ayrıca gerçek kaynak araması yapılmadan hash iddiası üretilmez.
    """
    return {
        "path": document.path.relative_to(context.root.resolve()).as_posix(),
        "symbol": localization_symbol(document.text, document.line + 1, document.path),
        "source_digest": hashlib.sha256(document.text.encode("utf-8")).hexdigest(),
    }
