"""Dokunulan JavaScript kaynaklarını çalıştırmadan ayrıştıran doğrulama kapısı."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from ...core.constants import JAVASCRIPT_SYNTAX_TIMEOUT_S
from ...core.tools import ToolContext
from ...core.verification import (
    JavaScriptSyntaxChecker,
    SyntaxCheckResult,
    VerificationResult,
)

logger = logging.getLogger(__name__)

JAVASCRIPT_SUFFIXES = frozenset({".js", ".mjs", ".cjs"})
HTML_SUFFIXES = frozenset({".html", ".htm"})

_CLASSIC_SCRIPT_TYPES = frozenset({"", "text/javascript", "application/javascript"})
_MODULE_SCRIPT_TYPE = "module"

#: Tek bir sözdizimi hatasından düzeltici modele taşınacak çıktı sınırları.
#: Node kaynak satırını ve stack'i tekrarlar; son 12 satır gerçek hata ile konumu
#: korurken prompt'u doldurmaz. Uzun/minified tek satır ayrıca karakterle sınırlanır.
_ERROR_TAIL_LINES = 12
_ERROR_MAX_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class JavaScriptSource:
    """Doğrulanacak tek bir JavaScript kaynak birimi."""

    label: str
    content: str
    #: True=module, False=classic/CommonJS, None=bağlam bilinmiyor; iki kip de denenir.
    is_module: bool | None


class _InlineScriptParser(HTMLParser):
    """Çalıştırılabilir inline script gövdelerini HTML'den ayır."""

    def __init__(self, page_name: str) -> None:
        super().__init__(convert_charrefs=False)
        self._page_name = page_name
        self._script_number = 0
        self._active_parts: list[str] | None = None
        self._active_is_module = False
        self.sources: list[JavaScriptSource] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return

        self._script_number += 1
        attributes = {name.lower(): value or "" for name, value in attrs}
        script_type = attributes.get("type", "").split(";", 1)[0].strip().lower()
        if "src" in attributes or script_type not in {
            *_CLASSIC_SCRIPT_TYPES,
            _MODULE_SCRIPT_TYPE,
        }:
            self._active_parts = None
            return

        self._active_parts = []
        self._active_is_module = script_type == _MODULE_SCRIPT_TYPE

    def handle_data(self, data: str) -> None:
        if self._active_parts is not None:
            self._active_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._active_parts is not None:
            self._active_parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._active_parts is not None:
            self._active_parts.append(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or self._active_parts is None:
            return

        content = "".join(self._active_parts)
        if content.strip():
            self.sources.append(
                JavaScriptSource(
                    label=f"{self._page_name} içindeki {self._script_number}. <script>",
                    content=content,
                    is_module=self._active_is_module,
                )
            )
        self._active_parts = None


def find_node_executable() -> str | None:
    """PATH üzerinde Node.js varsa somut yolunu döndür."""
    return shutil.which("node")


class NodeJavaScriptSyntaxChecker:
    """Node.js `--check` ile JavaScript'i çalıştırmadan ayrıştırır."""

    def __init__(
        self,
        executable: str,
        *,
        timeout_s: float = JAVASCRIPT_SYNTAX_TIMEOUT_S,
    ) -> None:
        self._executable = executable
        self._timeout_s = timeout_s

    async def check(self, source: str, *, is_module: bool) -> SyntaxCheckResult:
        arguments = [self._executable, "--check"]
        if is_module:
            arguments.append("--input-type=module")
        arguments.append("-")

        try:
            process = await asyncio.create_subprocess_exec(
                *arguments,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as error:
            logger.info("Node.js sözdizimi doğrulayıcısı başlatılamadı: %s", error)
            return SyntaxCheckResult(ok=True)

        try:
            raw_output, _ = await asyncio.wait_for(
                process.communicate(source.encode("utf-8")),
                timeout=self._timeout_s,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            logger.warning(
                "Node.js sözdizimi doğrulayıcısı %.1f saniyede tamamlanamadı",
                self._timeout_s,
            )
            return SyntaxCheckResult(ok=True)

        if process.returncode == 0:
            return SyntaxCheckResult(ok=True)
        return SyntaxCheckResult(ok=False, detail=_error_tail(raw_output))


class JavaScriptSyntaxVerifier:
    """Dokunulan HTML/JS dosyalarında parse edilemeyen betikleri engeller."""

    def __init__(self, context: ToolContext, checker: JavaScriptSyntaxChecker) -> None:
        self._context = context
        self._checker = checker

    async def verify(self) -> VerificationResult:
        sources = await asyncio.to_thread(_collect_sources, self._context)
        findings: list[str] = []

        for source in sources:
            modes = (source.is_module,) if source.is_module is not None else (False, True)
            results = [
                await self._checker.check(source.content, is_module=is_module)
                for is_module in modes
            ]
            if any(result.ok for result in results):
                continue
            result = results[0]
            detail = result.detail or "ayrıştırıcı hata ayrıntısı üretmedi"
            findings.append(
                f"{source.label} JavaScript sözdizimi hatası nedeniyle çalışmaz:\n{detail}"
            )

        if not findings:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False,
            summary=f"JavaScript sözdiziminde {len(findings)} engelleyici sorun",
            findings=tuple(findings),
        )


def _collect_sources(context: ToolContext) -> tuple[JavaScriptSource, ...]:
    sources: list[JavaScriptSource] = []
    for path in sorted(context.touched):
        suffix = path.suffix.lower()
        if suffix not in JAVASCRIPT_SUFFIXES | HTML_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        label = _display_path(path, context.root)
        if suffix in HTML_SUFFIXES:
            parser = _InlineScriptParser(label)
            parser.feed(content)
            parser.close()
            sources.extend(parser.sources)
            continue

        sources.append(
            JavaScriptSource(
                label=label,
                content=content,
                is_module=_module_mode(path, context.root),
            )
        )
    return tuple(sources)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _module_mode(path: Path, root: Path) -> bool | None:
    if path.suffix.lower() == ".mjs":
        return True
    if path.suffix.lower() == ".cjs":
        return False

    current = path.parent
    root = root.resolve()
    while current == root or root in current.parents:
        package_json = current / "package.json"
        if package_json.is_file():
            try:
                package_data = json.loads(package_json.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            if not isinstance(package_data, dict):
                return None
            package_type = package_data.get("type")
            if package_type == "module":
                return True
            if package_type == "commonjs":
                return False
            return None
        if current == root:
            break
        current = current.parent
    return None


def _error_tail(raw_output: bytes) -> str:
    text = raw_output.decode("utf-8", errors="replace").strip()
    if not text:
        return "Node.js hata ayrıntısı üretmedi"
    tail = "\n".join(text.splitlines()[-_ERROR_TAIL_LINES:])
    return tail if len(tail) <= _ERROR_MAX_CHARS else tail[-_ERROR_MAX_CHARS:]
