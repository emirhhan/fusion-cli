"""Yerel bilgisayar RPC'si yalnız host bağı ve mevcut konuşma kapsamıyla çalışır."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from .local_computer import LocalComputer

LOCAL_COMPUTER_ROUTES = {"bilgisayar.durum": "status", "bilgisayar.snapshot": "snapshot"}


async def dispatch_local_computer(
    name: str,
    data: Mapping[str, object],
    computer: LocalComputer | None,
    root: Callable[[], Path],
    conversation: Callable[[], str | None],
) -> dict[str, object]:
    """İstek JSON'u host kimliği veya yürütücü seçemez."""
    if data or computer is None or name not in LOCAL_COMPUTER_ROUTES:
        return {
            "ok": False,
            "status": "unavailable",
            "metin": "Yerel host bağlı değil veya istek geçersiz.",
        }

    def in_scope() -> bool:
        return (
            computer.root.resolve() == root().resolve()
            and computer.host.session_id == conversation()
        )

    if not in_scope():
        return {
            "ok": False,
            "status": "unavailable",
            "metin": "Yerel host konuşma kapsamı geçersiz.",
        }
    result = await computer.invoke(LOCAL_COMPUTER_ROUTES[name])
    if not in_scope():
        return {
            "ok": False,
            "status": "unavailable",
            "metin": "Yerel host konuşma kapsamı değişti.",
        }
    payload: dict[str, object] = {
        "ok": result.status != "unavailable",
        "status": result.status,
        "source_id": result.host.source_id,
        "session_id": result.host.session_id,
        "snapshot_id": result.snapshot_id,
        "images": [image for entry in result.results for image in entry.images],
        "text": "\n".join(entry.output for entry in result.results),
    }
    if result.status == "unavailable":
        payload["metin"] = "Yerel bilgisayar sondası doğrulanamadı."
    return payload
