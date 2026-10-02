"""Ajanın kendi geçmişini okuması: "ne yaptın / neyi sildin" sorusu kayıttan cevaplanır.

Ölçüldü (1 Ekim olayı): "hatalı bir şey silmiş olabilir misin?" sorusuna model
yalnız hafızasıyla cevap verebiliyordu; araç çağrıları hiçbir yerde okunabilir
değildi. Denetim günlüğü (`observability/audit.py`) artık her araç sonucunu
tutuyor; bu araç onu ve Fusion çöpünü modele açar. Salt okumadır.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from ...config.paths import trash_dir
from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...observability.audit import audit_path, read_recent
from ...tools.safe_delete import list_trash

#: Varsayılan ve en fazla kayıt sayısı.
DEFAULT_LIMIT = 30
MAX_LIMIT = 200
#: Çöp listesinde gösterilecek en eski girdi (gün).
TRASH_WINDOW_DAYS = 7


def recent_actions_tool(memory_dir: Path, conversation_id: str) -> Tool:
    path = audit_path(memory_dir / "audit", conversation_id)

    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        limit = args.get("limit", DEFAULT_LIMIT)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            limit = DEFAULT_LIMIT
        records = read_recent(path, min(limit, MAX_LIMIT))
        lines = [f"Bu sohbetteki son {len(records)} araç çağrısı (eskiden yeniye):"]
        for item in records:
            lines.append(
                f"- {item.get('zaman', '?')} [{item.get('ajan', 'ana')}] {item.get('arac')} "
                f"{str(item.get('argumanlar', ''))[:200]} → {item.get('sonuc')}"
            )
        if not records:
            lines.append("(kayıt yok — bu sohbette araç çalışmamış ya da günlük yeni açıldı)")
        lines.extend(_trash_lines())
        return ToolResult("\n".join(lines))

    return Tool(
        name="recent_actions",
        description="Bu sohbette GERÇEKTEN çalışmış araç çağrılarını (komut, dosya, sonuç) ve "
        "Fusion çöpüne taşınanları listele. 'Ne yaptın / neyi sildin' sorusunu bununla "
        "cevapla; tahmin etme.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
        run=_run,
    )


def _trash_lines() -> list[str]:
    limit = datetime.datetime.now().timestamp() - TRASH_WINDOW_DAYS * 86_400
    entries = [entry for entry in list_trash(trash_dir()) if entry.deleted_at >= limit]
    if not entries:
        return [f"Fusion çöpü (son {TRASH_WINDOW_DAYS} gün): boş."]
    lines = [f"Fusion çöpü (son {TRASH_WINDOW_DAYS} gün, `fusion cop geri-al <kimlik>`):"]
    for entry in entries:
        zaman = datetime.datetime.fromtimestamp(entry.deleted_at).strftime("%d.%m %H:%M")
        lines.append(f"- {entry.id} {zaman} {entry.original}")
    return lines
