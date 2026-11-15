"""MCP sunucusunun araç yüzeyini kullanıcı ayarına göre daralt (M1-12).

Ölçüldü (30 Ekim): araç sayısı üst sınırı yoktu. WordPress `mcp-adapter` 63 yetenek,
GitHub MCP 90+ araç sunar; hepsi kayıt defterine girip modele şema olarak gidiyordu.
Küçük bağlamlı modelde bu hem bağlamı yer hem araç seçimini bozar.

İki ayar, ikisi de sunucu başına ve boşken eski davranış (hepsi kayıtlı):

- `allowed_tools`: yalnız bu uzak adlar kaydedilir.
- `max_tools`: izin listesinden sonra sunucunun verdiği sırayla ilk N araç kalır.

Güven özeti (`trust.tools_digest`) süzmeden ÖNCE, sunucunun bütün tanımları üzerinden
alınır; bu yüzden süzme, değişen bir tanımın gözden kaçmasına yol açmaz.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from ..config.models import McpServerConfig
from .types import RemoteTool

_LOG = logging.getLogger(__name__)


def select_remote_tools(
    config: McpServerConfig | None, tools: Sequence[RemoteTool]
) -> list[RemoteTool]:
    """İzin listesi ve `max_tools` sınırını uygula; sırayı koru."""
    selected = list(tools)
    if config is None:
        return selected
    if config.allowed_tools:
        wanted = set(config.allowed_tools)
        missing = sorted(wanted - {tool.name for tool in selected})
        if missing:
            _LOG.warning(
                "MCP izin listesindeki araçlar sunucuda yok",
                extra={"sunucu": config.name, "eksik": missing},
            )
        selected = [tool for tool in selected if tool.name in wanted]
    if config.max_tools is not None and len(selected) > config.max_tools:
        _LOG.warning(
            "MCP araç sayısı max_tools ile sınırlandı",
            extra={"sunucu": config.name, "sunulan": len(selected), "sinir": config.max_tools},
        )
        selected = selected[: config.max_tools]
    return selected
