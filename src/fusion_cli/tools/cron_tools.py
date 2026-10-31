"""Ajanın oturum zamanlayıcısı araçları: cron_create / cron_list / cron_delete / schedule_wakeup.

Claude Code'un `CronCreate/List/Delete` ve `ScheduleWakeup` araçlarının karşılığı.
Görevler `ToolContext.cron` (oturumun `SessionCron`'u) üzerinde yaşar; araçlar
dünyada iz bırakmaz (`mutating=False`), yalnız oturum durumunu değiştirir. Vadesi
gelen görevi yeni tur olarak kuyruğa almak REPL/masaüstünün işidir.
"""

from __future__ import annotations

from ..core.protocols import Clock
from ..core.session_cron import SessionCron, SessionCronError
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult

_STRING = {"type": "string"}
_NO_CRON = (
    "Bu oturumda zamanlayıcı yok (tek atışlık `fusion agent`). REPL ya da masaüstünde çalışır."
)


def _registry(context: ToolContext) -> SessionCron | None:
    return getattr(context, "cron", None)


def _text(args: ToolArgs, key: str) -> str:
    value = args.get(key)
    return value.strip() if isinstance(value, str) else ""


def cron_tools(clock: Clock) -> tuple[Tool, ...]:
    """Dört aracı üret; saat testte sahteyle değiştirilebilsin diye enjekte edilir."""

    def _create(args: ToolArgs, context: ToolContext) -> ToolResult:
        cron = _registry(context)
        if cron is None:
            return ToolResult.failure(_NO_CRON)
        prompt = _text(args, "prompt")
        every, expression, delay = _text(args, "every"), _text(args, "cron"), _text(args, "in")
        given = [value for value in (every, expression, delay) if value]
        if len(given) != 1:
            return ToolResult.failure(
                "Tam olarak BİR zamanlama ver: 'every' (ör. 5m), 'cron' (ör. '*/15 * * * *') "
                "ya da 'in' (tek seferlik gecikme, ör. 30m)."
            )
        try:
            now = clock.now()
            if every:
                task = cron.create_interval(prompt, every, now=now)
            elif expression:
                task = cron.create_cron(prompt, expression, now=now)
            else:
                task = cron.create_once(prompt, delay, now=now)
        except SessionCronError as error:
            return ToolResult.failure(str(error))
        return ToolResult(
            f"Zamanlandı: {task.describe()}. Görev, oturum boşta kalınca yeni tur olarak "
            "çalışır; 7 gün sonra kendiliğinden düşer."
        )

    def _list(args: ToolArgs, context: ToolContext) -> ToolResult:
        cron = _registry(context)
        if cron is None:
            return ToolResult.failure(_NO_CRON)
        tasks = cron.list(clock.now())
        if not tasks:
            return ToolResult("Zamanlanmış görev yok.")
        lines = [f"{len(tasks)} zamanlanmış görev:"]
        lines.extend(f"- {task.describe()}" for task in tasks)
        return ToolResult("\n".join(lines))

    def _delete(args: ToolArgs, context: ToolContext) -> ToolResult:
        cron = _registry(context)
        if cron is None:
            return ToolResult.failure(_NO_CRON)
        task_id = _text(args, "id")
        if not task_id:
            return ToolResult.failure("'id' alanı gerekli (cron_list ile gör).")
        if not cron.delete(task_id):
            return ToolResult.failure(f"Görev bulunamadı: {task_id}")
        return ToolResult(f"Silindi: {task_id}")

    def _wakeup(args: ToolArgs, context: ToolContext) -> ToolResult:
        cron = _registry(context)
        if cron is None:
            return ToolResult.failure(_NO_CRON)
        delay, note = _text(args, "in"), _text(args, "note")
        prompt = note or "Zamanlanmış uyanma: bıraktığın işi kontrol et ve gerekirse sürdür."
        try:
            task = cron.create_once(prompt, delay or "1m", now=clock.now())
        except SessionCronError as error:
            return ToolResult.failure(str(error))
        return ToolResult(
            f"Uyanma kuruldu ({task.id}); oturum boşta kalınca not yeni tur olarak gelir. "
            "Bu turu kısa bir özetle bitir, bekleme."
        )

    return (
        Tool(
            name="cron_create",
            description=(
                "Bu OTURUMDA yineleyen ya da tek seferlik görev zamanla. Oturum boşta kalınca "
                "görev metni yeni bir tur olarak çalışır. Yalnız biri: every (5m/2h), "
                "cron (5 alan) ya da in (tek seferlik gecikme). En az 1 dakika, 7 günde düşer."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {**_STRING, "description": "Vadesi gelince çalışacak görev metni."},
                    "every": {**_STRING, "description": "Sabit aralık: 5m, 2h, 1d."},
                    "cron": {
                        **_STRING,
                        "description": "Cron ifadesi: dakika saat gün ay hafta-günü.",
                    },
                    "in": {**_STRING, "description": "Tek seferlik gecikme: 30m, 2h."},
                },
                "required": ["prompt"],
            },
            run=_create,
        ),
        Tool(
            name="cron_list",
            description="Bu oturumun zamanlanmış görevlerini listele (id, zaman, çalışma sayısı).",
            parameters={"type": "object", "properties": {}},
            run=_list,
        ),
        Tool(
            name="cron_delete",
            description="Zamanlanmış görevi id ile sil.",
            parameters={
                "type": "object",
                "properties": {"id": {**_STRING, "description": "cron_list'teki görev kimliği."}},
                "required": ["id"],
            },
            run=_delete,
        ),
        Tool(
            name="schedule_wakeup",
            description=(
                "Uzun süren dış bir iş (dağıtım, CI, indirme) için kendini belirli bir süre "
                "sonra uyandır: oturum boşta kalınca 'note' yeni tur olarak gelir. Beklemek "
                "yerine turu bitir."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "in": {**_STRING, "description": "Gecikme: 1m-1h arası önerilir (ör. 10m)."},
                    "note": {**_STRING, "description": "Uyanınca ne kontrol edileceği."},
                },
                "required": ["in"],
            },
            run=_wakeup,
        ),
    )
