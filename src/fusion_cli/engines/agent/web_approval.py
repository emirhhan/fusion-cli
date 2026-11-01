"""WebFetch ve WebSearch onayı — Claude Code ile birebir (#55).

Kaynak: code.claude.com/docs/en/permissions#permission-system ve
code.claude.com/docs/en/tools-reference#webfetch-tool-behavior.

    Manuel, acceptEdits   web_fetch sorulur (allow/deny kuralı olan alan ve yerleşik önceden
                          onaylı belge alanları hariç); web_search sorulur
    plan                  sorulur (okuma dışı çağrı gibi)
    auto, bypass          sorulmaz (açık `ask` kuralı hariç)
    dontAsk               önceden onaylı alan ya da allow kuralı yoksa reddedilir

"Bir daha sorma" `WebFetch(domain:<alan>)` ya da `WebSearch` kuralı yazar. Açık
`WebFetch(domain:…)` kuralı önceden onaylı kümenin önüne geçer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ...config.permission_rules import PermissionDecision, PermissionRule
from ...core.tools import ToolArgs, ToolEffect

if TYPE_CHECKING:
    from .approval import ApprovalRequest

WEB_FETCH = "web_fetch"
WEB_SEARCH = "web_search"
#: Claude Code'un yerleşik önceden onaylı belge alanlarından seçilmiş küme. Belge listeyi
#: yayımlamıyor; burada yalnız yaygın, salt belge sunan alanlar var (alt alanlar dahil değil).
PREAPPROVED_DOCS_DOMAINS = frozenset(
    {"code.claude.com", "docs.claude.com", "docs.anthropic.com", "platform.claude.com",
     "docs.python.org", "developer.mozilla.org", "learn.microsoft.com", "docs.oracle.com",
     "en.cppreference.com", "doc.rust-lang.org", "docs.rs", "go.dev", "pkg.go.dev",
     "nodejs.org", "www.typescriptlang.org", "react.dev", "vuejs.org", "angular.dev",
     "nextjs.org", "docs.djangoproject.com", "flask.palletsprojects.com",
     "fastapi.tiangolo.com", "pandas.pydata.org", "numpy.org", "pytorch.org",
     "docs.github.com", "git-scm.com", "kubernetes.io", "docs.docker.com", "www.php.net",
     "docs.swift.org", "kotlinlang.org", "ruby-doc.org"}
)  # fmt: skip


def is_web_tool(tool_name: str) -> bool:
    return tool_name in {WEB_FETCH, WEB_SEARCH}


def fetch_host(args: ToolArgs) -> str | None:
    raw = args.get("url")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        host = urlsplit(raw.strip() if "//" in raw else f"https://{raw.strip()}").hostname
    except ValueError:
        return None
    return host.lower() if host else None


def adjust_web_request(request: ApprovalRequest) -> ApprovalRequest:
    """Web çağrısının onay alanları: önceden onaylı alan okuma sayılır, öteki sorulur.

    `risk` boş kalır (auto kipi sormaz); `unattended_safe` düşer (acceptEdits sorar);
    `read_only` yalnız önceden onaylı ve kurala takılmayan alanda doğrudur.
    """
    if not is_web_tool(request.tool.name) or request.effect is not ToolEffect.LOCAL:
        return request
    host = fetch_host(request.args) if request.tool.name == WEB_FETCH else None
    preapproved = host in PREAPPROVED_DOCS_DOMAINS and request.rule is None
    return replace(request, read_only=preapproved, unattended_safe=preapproved, risk=None)


def web_rule(request: ApprovalRequest) -> PermissionRule | None:
    """Kalıcı onay kuralı: `WebFetch(domain:<alan>)` ya da `WebSearch`."""
    name = request.tool.name
    if name == WEB_SEARCH:
        return PermissionRule("WebSearch", None, PermissionDecision.ALLOW)
    if name != WEB_FETCH:
        return None
    host = fetch_host(request.args)
    if host is None:
        return None
    return PermissionRule("WebFetch", f"domain:{host}", PermissionDecision.ALLOW)


def web_scope(request: ApprovalRequest) -> str | None:
    """Oturum izninin kapsamı: alan başına (`web_fetch:<alan>`); arama araç başına."""
    if request.tool.name == WEB_FETCH:
        host = fetch_host(request.args)
        return f"{WEB_FETCH}:{host}" if host else None
    if request.tool.name == WEB_SEARCH:
        return WEB_SEARCH
    return None
