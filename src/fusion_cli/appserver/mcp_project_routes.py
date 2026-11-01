"""Masaüstünde proje (`.mcp.json`) sunucu onayı (#246).

Claude Code etkileşimli açılışta onaylanmamış her `.mcp.json` sunucusu için üç seçenek
sorar: "bu ve gelecekteki bütün proje sunucularını kullan", "bu sunucuyu kullan",
"bu sunucu olmadan devam et". Terminal REPL'i bunu `cli/mcp_approval_prompt.py` ile
sorar; masaüstü aynı kaydı (`mcp-local.json`) bu RPC'lerle yazar:

- `baglanti.proje_bekleyen` → onay bekleyen sunucular (`ad`, `hedef`)
- `baglanti.proje_onay` `{ad, secim: all|one|no}` → seçimi kaydet; onaylanan sunucu
  çalışan oturumun yapılandırmasına eklenir (kuruluş politikası uygulanır)
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path

from ..config import mcp_project_approval as approval
from ..config.models import Config, McpServerConfig
from ..core.errors import ConfigError
from ..core.redaction import redact

__all__ = ["MCP_PROJECT_ROUTES", "dispatch_mcp_project"]

PENDING_ROUTE = "baglanti.proje_bekleyen"
CHOICE_ROUTE = "baglanti.proje_onay"
MCP_PROJECT_ROUTES = frozenset({PENDING_ROUTE, CHOICE_ROUTE})
_CHOICES = frozenset({approval.CHOICE_ALL, approval.CHOICE_ONE, approval.CHOICE_NO})


def _target(server: McpServerConfig) -> str:
    text = server.url if server.is_remote else " ".join((server.command, *server.args))
    return redact(text.strip())[:400]


def _pending(root: Path) -> dict[str, object]:
    servers = approval.pending_project_servers(root)
    return {
        "ok": True,
        "sunucular": [{"ad": server.name, "hedef": _target(server)} for server in servers],
    }


def _with_approved(config: Config, root: Path) -> Config:
    """Onaylı proje sunucularından oturumda olmayanları ekle; politikayı uygula."""
    from ..config.mcp_policy import apply_mcp_policy

    present = {server.name for server in config.mcp_servers}
    extra = tuple(s for s in approval.approved_project_servers(root) if s.name not in present)
    if not extra:
        return config
    updated = dataclasses.replace(config, mcp_servers=(*config.mcp_servers, *extra))
    return apply_mcp_policy(updated, root)


def dispatch_mcp_project(
    name: str, data: Mapping[str, object], root: Path, config: Config
) -> tuple[dict[str, object], Config | None]:
    """RPC sonucu ve (değiştiyse) yeni yapılandırma."""
    if name == PENDING_ROUTE:
        return _pending(root), None
    server = data.get("ad")
    choice = data.get("secim")
    pending = {s.name for s in approval.pending_project_servers(root)}
    if not isinstance(server, str) or server not in pending:
        return {"ok": False, "metin": "Onay bekleyen böyle bir proje sunucusu yok."}, None
    if choice not in _CHOICES:
        return {"ok": False, "metin": "Seçim all, one ya da no olmalı."}, None
    try:
        approval.record_choice(root, server, str(choice))
    except ConfigError as error:
        return {"ok": False, "metin": str(error)}, None
    updated = _with_approved(config, root)
    return {**_pending(root), "kaydedildi": server}, (updated if updated is not config else None)
