"""Ajanın oturum zamanlayıcısı araçları: cron_create / cron_list / cron_delete / schedule_wakeup.

Claude Code'un `CronCreate/List/Delete` ve `ScheduleWakeup` araçlarının karşılığı.
Görevler `ToolContext.cron` (oturumun `SessionCron`'u) üzerinde yaşar; araçlar
dünyada iz bırakmaz (`mutating=False`), yalnız oturum durumunu değiştirir. Vadesi
gelen görevi yeni tur olarak kuyruğa almak REPL/masaüstünün işidir.

Ajanın kurduğu görev `Source.AGENT` ile işaretlenir: yüzeyler onu yalnız TUR olarak
çalıştırır, `/bypass` gibi bir satır komut olarak işlenmez (onaysız araç kipi
yükseltemesin).
"""

from __future__ import annotations

from ..core.protocols import Clock
from ..core.session_cron import SessionCron, SessionCronError, Source, parse_interval
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ..ui import messages

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
        # Claude CronCreate: cron (5 alan) + prompt + recurring. Eski `every`/`in` alanları
        # takma ad olarak okunur (şemada yok; #366).
        every, expression, delay = _text(args, "every"), _text(args, "cron"), _text(args, "in")
        given = [value for value in (every, expression, delay) if value]
        if len(given) != 1:
            return ToolResult.failure(
                "Tam olarak BİR zamanlama ver: 'cron' (5 alanlı ifade, ör. '*/15 * * * *'); "
                "tek seferlik için recurring=false."
            )
        try:
            now = clock.now()
            if every:
                task = cron.create_interval(prompt, every, now=now, source=Source.AGENT)
            elif expression and args.get("recurring") is False:
                task = cron.create_cron_once(prompt, expression, now=now, source=Source.AGENT)
            elif expression:
                task = cron.create_cron(prompt, expression, now=now, source=Source.AGENT)
            else:
                task = cron.create_once(prompt, delay, now=now, source=Source.AGENT)
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
        delay = _text(args, "in")
        loop_id = _text(args, "loop_id")
        if not loop_id:
            # Claude ScheduleWakeup yalnız kendi tempolu `/loop` içindir (#362).
            return ToolResult.failure(messages.WAKEUP_NEEDS_LOOP)
        if args.get("stop") is True:
            if not cron.delete(loop_id):
                return ToolResult.failure(f"Döngü bulunamadı: {loop_id}")
            # Claude kullanıcı ekranında "Pending wakeup cancelled" gösterir (#362).
            return ToolResult(
                messages.WAKEUP_CANCELLED, structured={"user_notice": messages.WAKEUP_CANCELLED}
            )
        # Kendi tempolu `/loop` (P-038): yeni görev değil, döngünün sıradaki çalışması.
        try:
            seconds = parse_interval(delay or "10m")
            task = cron.reschedule_self_paced(loop_id, seconds, now=clock.now())
        except SessionCronError as error:
            return ToolResult.failure(str(error))
        return ToolResult(
            f"Döngü {task.id} sıradaki çalışması "
            f"{int(task.next_due - clock.now()) // 60} dk sonra. Turu kısa özetle bitir."
        )

    return (
        Tool(
            name="cron_create",
            description=(
                "Bu OTURUMDA görev zamanla: 5 alanlı cron ifadesi ve görev metni; tek seferlik "
                "için recurring=false. Oturum boşta kalınca görev yeni bir tur olarak çalışır; "
                "yineleyen görev 7 gün sonra son kez çalışıp düşer."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cron": {
                        **_STRING,
                        "description": "Cron ifadesi: dakika saat gün ay hafta-günü.",
                    },
                    "prompt": {**_STRING, "description": "Vadesi gelince çalışacak görev metni."},
                    "recurring": {
                        "type": "boolean",
                        "description": "true (varsayılan) yineler; false bir kez çalışır.",
                    },
                },
                "required": ["cron", "prompt"],
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
                "Kendi tempolu /loop döngüsünün sıradaki çalışmasını zamanla (loop_id ile); "
                "döngüyü bitirmek için stop=true. Beklemek yerine turu bitir."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "in": {**_STRING, "description": "Gecikme: 1m-1h arası (ör. 10m)."},
                    "loop_id": {**_STRING, "description": "Kendi tempolu döngünün kimliği."},
                    "stop": {"type": "boolean", "description": "true: döngüyü bitir."},
                },
                "required": ["loop_id"],
            },
            run=_wakeup,
        ),
    )
