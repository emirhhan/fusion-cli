"""Catch-all Next API istemcisinin sunucu karşılığını denetle.

Yalnız bu turda değişen istemcide sabit bir API tabanı dinamik yola ekleniyorsa
çalışır. Derleme ve sahte fetch testleri eksik route'u göremediğinden gerekir.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...core.verification import VerificationResult

_SOURCE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx"})
_BASE = re.compile(
    r"\b(?:const|let)\s+(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*"
    r"[\"'](?P<base>/api/[A-Za-z0-9/_-]+)[\"']"
)
_INLINE_DYNAMIC = re.compile(r"\bfetch\s*\(\s*`(?P<base>/api(?:/[A-Za-z0-9_-]+)+)/\$\{")
_STATIC_SUCCESS = re.compile(
    r"\breturn\s+NextResponse\.json\s*\(\s*\{\s*success\s*:\s*true"
    r"(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)?\s*\}\s*\)"
)
_LOCAL_IMPORT = re.compile(r"\bfrom\s*[\"'](?:@/|\.{1,2}/)")


class NextRouteVerifier:
    def __init__(self, root: Path, changed_paths: tuple[Path, ...]) -> None:
        self._root = root.resolve()
        self._changed_paths = changed_paths

    async def verify(self) -> VerificationResult:
        findings: list[str] = []
        for path in self._changed_paths:
            source = path.resolve()
            if (
                not source.is_relative_to(self._root)
                or not source.is_file()
                or source.suffix not in _SOURCE_SUFFIXES
                or "__tests__" in source.parts
            ):
                continue
            try:
                content = source.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if _is_stub_post(source.relative_to(self._root), content):
                findings.append(
                    f"{source.relative_to(self._root)}: POST rotası yerel servis veya "
                    "veri işlemi olmadan koşulsuz başarı döndürüyor."
                )
            bases = {match.group("base") for match in _INLINE_DYNAMIC.finditer(content)}
            for match in _BASE.finditer(content):
                name, base = match.group("name", "base")
                if re.search(rf"\bfetch\s*\(\s*`\$\{{{re.escape(name)}\}}/", content):
                    bases.add(base)
            for base in sorted(bases):
                if _has_route(self._root, base) or _has_rewrite(self._root, base):
                    continue
                relative = source.relative_to(self._root)
                findings.append(
                    f"{relative}: {base}/* çağrılıyor ama Next catch-all API rotası "
                    "veya yönlendirmesi yok. İstemci istekleri 404 dönecek."
                )
        if findings:
            return VerificationResult(
                ok=False,
                summary="Next API bağlantısı doğrulanamadı",
                findings=tuple(findings),
            )
        return VerificationResult(ok=True)


def _is_stub_post(relative: Path, content: str) -> bool:
    parts = relative.parts
    if not any(parts[index : index + 2] == ("app", "api") for index in range(len(parts) - 1)):
        return False
    if relative.name not in {"route.ts", "route.js"}:
        return False
    return bool(
        _STATIC_SUCCESS.search(content)
        and not _LOCAL_IMPORT.search(content)
        and not re.search(r"\b(?:fetch|writeFile|prisma)\s*[.(]", content)
    )


def _has_route(root: Path, base: str) -> bool:
    segments = base.removeprefix("/api/")
    for prefix in (root, root / "src"):
        app = prefix / "app/api" / segments
        pages = prefix / "pages/api" / segments
        if app.is_dir():
            for entry in app.iterdir():
                if _is_catchall(entry.name) and any(
                    (entry / f"route{suffix}").is_file() for suffix in (".ts", ".js")
                ):
                    return True
        if pages.is_dir() and any(
            _is_catchall(entry.stem) and entry.suffix in (".ts", ".js") for entry in pages.iterdir()
        ):
            return True
    return False


def _is_catchall(name: str) -> bool:
    return (name.startswith("[...") and name.endswith("]")) or (
        name.startswith("[[...") and name.endswith("]]")
    )


def _has_rewrite(root: Path, base: str) -> bool:
    for name in ("next.config.js", "next.config.mjs", "next.config.ts"):
        config = root / name
        if not config.is_file():
            continue
        try:
            source = config.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if re.search(rf"source\s*:\s*[\"'`]{re.escape(base)}/:path\*", source):
            return True
    return False
