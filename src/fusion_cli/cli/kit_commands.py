"""`fusion kit` — terminalden bir Kit'e mesaj/görev bırak, gelen kutusunu oku.

Araçlar (`kit_send`) ve masaüstü RPC'si (`kit.gonder`) ile aynı istemciyi kullanır
(`tools/kits.py`). Kits çalışmıyorsa nereden açılacağını söyleyen Türkçe hata verir.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from collections.abc import Callable, Coroutine
from typing import TypeVar

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..core.errors import FusionError
from ..tools.kits import KitsClient, validate_text
from ..ui import messages

app = typer.Typer(no_args_is_help=True, help="Kits'teki bir Kit'e mesaj/görev bırak, durumunu oku.")
console = Console()
ResultT = TypeVar("ResultT")


def _run(work: Callable[[KitsClient], Coroutine[object, object, ResultT]]) -> ResultT:
    client = KitsClient()
    try:
        return asyncio.run(work(client))
    except FusionError:
        raise
    except Exception as error:  # araç sınırı: çıplak traceback yerine Türkçe hata
        raise FusionError(messages.KIT_COMMAND_FAILED.format(error=type(error).__name__)) from error


def _when(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "-"
    return datetime.datetime.fromtimestamp(value / 1000).strftime("%d.%m.%Y %H:%M")


@app.command("liste")
def list_kits() -> None:
    """Kit'leri, Fusion izinlerini ve gelen kutusu sohbetlerini listele."""
    kits = _run(lambda client: client.list_kits())
    if not kits:
        console.print(messages.KIT_NONE)
        return
    table = Table(title="Kits")
    for column in ("ad", "kimlik", "Fusion izni", "gelen kutusu"):
        table.add_column(column)
    for kit in kits:
        table.add_row(
            escape(str(kit.get("name", ""))),
            escape(str(kit.get("id", ""))),
            "açık" if kit.get("fusionAllowed") else "kapalı",
            "var" if kit.get("inboxThreadId") else "yok",
        )
    console.print(table)


@app.command("gonder")
def send(
    kit: str = typer.Argument(..., help="Kit adı ya da kimliği (`fusion kit liste`)"),
    metin: str = typer.Argument(..., help="Kit'e bırakılacak metin (3-4000 karakter)"),
    baslik: str | None = typer.Option(None, "--baslik", help="Kısa başlık"),
    mesaj: bool = typer.Option(False, "--mesaj", help="Görev değil düz mesaj olarak gönder"),
) -> None:
    """Kit'e görev (varsayılan) ya da mesaj bırak; makbuz kuyruğa alındığını söyler."""
    reason = validate_text(metin)
    if reason is not None:
        raise FusionError(reason)
    receipt = _run(
        lambda client: client.send(kit, metin, title=baslik, kind="mesaj" if mesaj else "gorev")
    )
    console.print(
        messages.KIT_SENT.format(kit=escape(kit), task=escape(str(receipt.get("taskId", ""))))
    )


@app.command("gelen")
def inbox(kit: str = typer.Argument(..., help="Kit adı ya da kimliği")) -> None:
    """Kit'in Fusion gelen kutusundaki son kayıtları ve durumlarını göster."""
    items = _run(lambda client: client.inbox(kit))
    if not items:
        console.print(messages.KIT_INBOX_EMPTY.format(kit=escape(kit)))
        return
    table = Table(title=f"{escape(kit)} — Fusion gelen kutusu")
    for column in ("görev", "tür", "başlık", "durum", "güncellendi"):
        table.add_column(column)
    for item in items:
        table.add_row(
            escape(str(item.get("taskId", ""))),
            "mesaj" if item.get("kind") == "message" else "görev",
            escape(str(item.get("title", ""))),
            escape(str(item.get("status", ""))),
            _when(item.get("updatedAt")),
        )
    console.print(table)


@app.command("durum")
def status(
    kit: str = typer.Argument(..., help="Kit adı ya da kimliği"),
    gorev_id: str = typer.Argument(..., help="`fusion kit gelen` görev kimliği"),
) -> None:
    """Tek görevin durumunu, sonuç özetini ve olaylarını göster."""
    detail = _run(lambda client: client.status(kit, gorev_id))
    console.print(escape(json.dumps(detail, ensure_ascii=False, indent=2)))
