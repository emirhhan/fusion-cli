"""Biten arka plan işini oturuma bildir (Claude Code arka plan bildirimi, #334).

Claude'da arka plan Bash işi bitince model yoklamadan haberdar olur ve çıktı dosyasını
Read ile okur (TaskOutput v2.1.277'de kaldırıldı). İzleyici iş parçacığı burada oturumun
olay kuyruğuna tek satırlık bir bildirim bırakır; kuyruk yoksa (tek atışlık bağlam) hiçbir
şey yapılmaz.
"""

from __future__ import annotations

from pathlib import Path

from ..core.background_events import BackgroundEvents
from ..core.tools import ToolContext

__all__ = ["events_of", "notify_job_done", "started_hint"]

#: Bildirimde gösterilen komutun en uzun hâli.
_COMMAND_PREVIEW = 120


def events_of(context: ToolContext) -> BackgroundEvents | None:
    return getattr(context, "background_events", None)


def notify_job_done(
    events: BackgroundEvents | None, job_id: str, command: str, log: Path, code: int | None
) -> None:
    """İş bitti/durduruldu bildirimini kuyruğa bırak."""
    if events is None:
        return
    preview = " ".join(command.split())
    if len(preview) > _COMMAND_PREVIEW:
        preview = preview[:_COMMAND_PREVIEW] + "…"
    state = "bitti" if code is not None else "sonlandı (çıkış kodu bilinmiyor)"
    tail = f" (çıkış kodu {code})" if code is not None else ""
    events.push(
        f'Arka plan işi {job_id} {state}{tail}: "{preview}". Çıktı dosyası: {log} '
        "(read_file ile oku)."
    )


def started_hint(job_id: str) -> str:
    """İş başlarken modele verilen Claude biçimli yönerge."""
    return (
        "Bitince bildirim gelir; beklemek için turu bitirebilirsin. Çıktıyı read_file ile "
        f"oku; gerekirse task_stop(task_id='{job_id}') ile durdur."
    )
