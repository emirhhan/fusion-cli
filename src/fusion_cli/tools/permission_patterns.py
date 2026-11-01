"""İzin kuralı metin kalıpları: Bash belirteci, araç adı globu, WebFetch alan adı.

Claude Code belgesiyle birebir (code.claude.com/docs/en/permissions):

    Bash(…)          `*` her konumda olabilir ve boşluk dahil her metni karşılar
                     (`git * main`, `* --version`, `* --help *`). Yıldızsız kural birebirdir.
                     Kuralın TEK yıldızı sonda ve önünde boşluk varsa yalın komutu da
                     karşılar (`ls *` → `ls`); `:*` yalnız sonda ` *` ile eşdeğerdir
                     (`git:* push` içindeki `:` düz karakterdir) (#43).
    Araç adı globu   deny/ask kuralında tam ad globu: `*` her araç, `mcp__*` her MCP aracı.
                     Allow globu yalnız sabit `mcp__<sunucu>__` öneki sonrasında geçerlidir;
                     `*`, `B*`, `mcp__*` allow kuralı hiçbir şeyi onaylamaz (#46).
    domain:…         ana makine birebir; `*.x.com` her derinlikte alt alan (x.com hariç);
                     yalın `*` her alan; başka konumdaki `*` iki nokta arasını aşmaz (#62).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache
from urllib.parse import urlsplit

from ..config.permission_rules import PermissionDecision

_MCP_PREFIX = "mcp__"
#: Allow globunda zorunlu sabit önek: `mcp__<globsuz sunucu>__`.
_ANCHORED_MCP_ALLOW = re.compile(r"mcp__[^*]+?__")


def bash_pattern_matches(spec: str, text: str) -> bool:
    """Bash belirteci (`*` her konumda) komut metnini karşılıyor mu?"""
    if spec.endswith(":*"):
        spec = spec[:-2] + " *"
    if "*" not in spec:
        return text == spec
    if spec.count("*") == 1 and spec.endswith(" *") and text == spec[:-2].rstrip():
        return True
    return _bash_regex(spec).fullmatch(text) is not None


@lru_cache(maxsize=512)
def _bash_regex(spec: str) -> re.Pattern[str]:
    return re.compile(".*".join(re.escape(part) for part in spec.split("*")), re.DOTALL)


def is_tool_glob(pattern: str) -> bool:
    """Araç adı konumunda glob var mı (`*`, `mcp__*`, `mcp__s__get_*`)?"""
    return "*" in pattern


def tool_glob_matches(pattern: str, names: Iterable[str], decision: PermissionDecision) -> bool:
    """Araç adı globu adlardan birini TAM karşılıyor mu? Allow globu sabit MCP öneki ister."""
    if decision is PermissionDecision.ALLOW and _ANCHORED_MCP_ALLOW.match(pattern) is None:
        return False
    regex = _name_regex(pattern)
    return any(regex.fullmatch(name) is not None for name in names)


@lru_cache(maxsize=256)
def _name_regex(pattern: str) -> re.Pattern[str]:
    return re.compile(".*".join(re.escape(part) for part in pattern.split("*")))


def domain_matches(pattern: str, url: object) -> bool:
    """`domain:` kalıbı (büyük/küçük harf duyarsız, sondaki `.` atılır) URL'nin ana makinesi mi?"""
    if not pattern or not isinstance(url, str):
        return False
    host = (urlsplit(url if "://" in url else f"//{url}").hostname or "").lower().rstrip(".")
    pattern = pattern.strip().lower().rstrip(".")
    if not host or not pattern:
        return False
    if pattern == "*":
        return True
    if pattern.startswith("*."):
        suffix = pattern[1:]
        return host.endswith(suffix) and len(host) > len(suffix) and _label_match(suffix, host)
    return _label_regex(pattern).fullmatch(host) is not None


def _label_match(suffix: str, host: str) -> bool:
    """`*.x.*` gibi önek sonrası yıldızlar da nokta aşmaz."""
    tail = host[len(host) - len(suffix) :]
    return _label_regex(suffix.lstrip(".")).fullmatch(tail.lstrip(".")) is not None


@lru_cache(maxsize=256)
def _label_regex(pattern: str) -> re.Pattern[str]:
    return re.compile("[^.]*".join(re.escape(part) for part in pattern.split("*")))
