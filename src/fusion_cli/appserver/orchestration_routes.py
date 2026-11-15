"""Masaüstünün iş akışı (P-062) ve ekip (P-061) panosu RPC'leri.

`/workflows` ve araçlarla aynı depoları okur; ikinci bir yol açmaz. Yanıt `{ok, ...}`,
alanlar Türkçe. Koşturma burada değil: arayüz `/workflows <ad>` komutunu gönderir.

- `akis.liste`  → `{tanimlar: [...], kosular: [...]}`
- `akis.kosu`   → `{kosu: {...}}` (`kimlik`)
- `akis.iptal`  → koşan koşuya iptal işareti (`kimlik`)
- `ekip.liste`  → `{ekipler: [{ad, hedef, uyeler, gorev, tamam, guncellendi}]}`
- `ekip.pano`   → `{pano: {...}}` (`ad`; lidere gelen son mesajlar dahil)
- `ekip.sil`    → panoyu ve gelen kutularını sil (`ad`)
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..engines.agent.team_board import LEAD, NAME_PATTERN, TeamBoard, TeamError, TeamStore
from ..engines.agent.workflow_store import RunRecord
from ..engines.agent.workflow_tools import workflow_store

WORKFLOW_ROUTES = frozenset({"akis.liste", "akis.kosu", "akis.iptal"})
TEAM_ROUTES = frozenset({"ekip.liste", "ekip.pano", "ekip.sil"})
ORCHESTRATION_ROUTES = WORKFLOW_ROUTES | TEAM_ROUTES


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _run_payload(record: RunRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload.pop("pid", None)
    return payload


async def dispatch_orchestration(
    name: str, data: Mapping[str, object], root: Path
) -> dict[str, Any]:
    """Tek giriş: bilinmeyen ad ya da eksik kimlik `ok: False` ve Türkçe `metin`."""
    if name in WORKFLOW_ROUTES:
        # Küçük dosya okumaları da olay döngüsünü bloklamasın.
        return await asyncio.to_thread(_workflow, name, data, root)
    if name in TEAM_ROUTES:
        return await asyncio.to_thread(_team, name, data, root)
    return {"ok": False, "metin": "Bilinmeyen pano isteği."}


def _team(name: str, data: Mapping[str, object], root: Path) -> dict[str, Any]:
    store = TeamStore(root)
    try:
        if name == "ekip.liste":
            boards = [board for item in store.names() if (board := store.load(item)) is not None]
            return {"ok": True, "ekipler": [_board_summary(board) for board in boards]}
        team = _text(data, "ad")
        if not team:
            return {"ok": False, "metin": "Ekip adı gerekli."}
        if not NAME_PATTERN.match(team):
            return {"ok": False, "metin": "Geçersiz ekip adı (küçük harf, rakam, '-' ya da '_')."}
        if name == "ekip.sil":
            if store.delete(team):
                return {"ok": True, "ad": team}
            return {"ok": False, "ad": team, "metin": "Bu adla ekip yok."}
        board = store.load(team)
    except TeamError as error:
        return {"ok": False, "metin": str(error)}
    if board is None:
        return {"ok": False, "metin": "Bu adla ekip yok."}
    return {
        "ok": True,
        "pano": {
            **asdict(board),
            "lider_mesajlari": [asdict(m) for m in store.inbox(team, LEAD)][-20:],
        },
    }


def _board_summary(board: TeamBoard) -> dict[str, Any]:
    return {
        "ad": board.name,
        "hedef": board.goal,
        "uyeler": [member.name for member in board.members],
        "gorev": len(board.tasks),
        "tamam": sum(task.status == "tamam" for task in board.tasks),
        "guncellendi": board.updated_at,
    }


def _workflow(name: str, data: Mapping[str, object], root: Path) -> dict[str, Any]:
    store = workflow_store(root)
    if name == "akis.liste":
        return {
            "ok": True,
            "tanimlar": [
                {"ad": item.name, "kapsam": item.scope, "aciklama": item.description}
                for item in store.definitions()
            ],
            "kosular": [_run_payload(record) for record in store.runs()],
        }
    identifier = _text(data, "kimlik")
    if not identifier:
        return {"ok": False, "metin": "Koşu kimliği gerekli."}
    if name == "akis.kosu":
        record = store.run(identifier)
        if record is None:
            return {"ok": False, "metin": "Bu kimlikte koşu yok."}
        return {"ok": True, "kosu": _run_payload(record)}
    if store.request_cancel(identifier):
        return {"ok": True, "kimlik": identifier}
    return {"ok": False, "metin": "Koşan bir koşu bulunamadı; bitmiş ya da hiç başlamamış."}
