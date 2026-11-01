"""Oturum-kapsamlı zamanlayıcı: `/loop`, `cron_create/list/delete`, `schedule_wakeup` (P-038).

Claude Code'un oturum içi cron'uyla aynı model: görevler oturumla yaşar, sabit
aralık (`5m`), cron ifadesi (`*/10 * * * *`) ya da tek seferlik gecikme (`30m`)
ile tetiklenir; en az 1 dakika, en çok 50 görev, 7 günde süresi dolar. Görev
"çalışmaz" — vadesi gelince REPL/masaüstü onu yeni bir tur olarak kuyruğa alır.

Yalnız stdlib; zaman dışarıdan verilir (`now` parametresi) ki testler sahte saat
kullanabilsin. Durum `to_dict`/`from_dict` ile taşınır (kalıcılık `cli` katmanında).

Ölçüldü (31 Ekim): `/schedule` yalnız tek seferlik hatırlatma basıyordu; yineleyen
görev, cron ifadesi ve ajanın kendi kendini uyandırma aracı yoktu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from itertools import pairwise
from uuid import uuid4

from .cron_jitter import is_five_minute, once_offset, recurring_offset
from .errors import FusionError

#: Oturum başına en çok görev (Claude Code ile aynı tavan).
MAX_TASKS = 50
#: En kısa yineleme aralığı: saniye başı tetikleme kota yakar ve kullanıcıyı boğar.
MIN_INTERVAL_S = 60
#: Görevin yaşam süresi; sonrasında sessizce düşer (unutulan döngü haftalarca koşmaz).
MAX_AGE_S = 7 * 24 * 3600
#: Cron'da sıradaki zaman en çok bu kadar ileride aranır.
_CRON_LOOKAHEAD_DAYS = 366
#: Görev metninin tavanı.
MAX_PROMPT_CHARS = 8000
#: Kendi tempolu döngüde ajanın seçebileceği gecikme aralığı (Claude Code: 1 dk – 1 sa).
SELF_PACED_MIN_S = 60
SELF_PACED_MAX_S = 3600
#: Ajan sıradaki çalışmayı seçmezse döngü bu kadar sonra yine çalışır (eski sabit 10 dk).
SELF_PACED_FALLBACK_S = 1200

_INTERVAL = re.compile(r"^\s*(\d+)\s*([smhd]?)\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "": 60}


class SessionCronError(FusionError):
    """Zamanlama girdisi geçersiz; mesaj kullanıcıya/modele gösterilir."""


class Kind(Enum):
    INTERVAL = "aralik"
    CRON = "cron"
    ONCE = "bir_kez"
    #: Kendi tempolu döngü (aralıksız `/loop <görev>`): sıradaki çalışmayı ajan seçer
    #: (`schedule_wakeup loop_id`); seçmezse `SELF_PACED_FALLBACK_S` sonra bir kez daha çalışır.
    SELF_PACED = "kendi_tempolu"


#: Yineleyen türler (7 gün dolunca son bir kez çalışır; #364).
_RECURRING = frozenset({Kind.INTERVAL, Kind.CRON})


class Source(Enum):
    """Görevi kim kurdu? Yüzeyler ajan görevini yalnız TUR olarak çalıştırır (komut değil).

    Ölçüldü (31 Ekim): `cron_create(prompt="/bypass")` onaysız kuruluyor, vadesi gelince
    REPL satırı kullanıcı yazmış gibi `/bypass` komutu olarak işliyordu — istem
    enjeksiyonu onay kipini kullanıcıya sormadan yükseltebiliyordu.
    """

    USER = "kullanici"
    AGENT = "ajan"


def looks_like_interval(text: str) -> bool:
    """Metin aralık SÖZDİZİMİNDE mi (`5m`, `30s`)? Kısa olsa da True: hata sonra verilir."""
    return _INTERVAL.match(text or "") is not None


def parse_interval(text: str) -> int:
    """`30s`, `5m`, `2h`, `1d` → saniye. Birimsiz sayı dakikadır. Tavan: en az 1 dakika."""
    match = _INTERVAL.match(text or "")
    if match is None:
        raise SessionCronError(
            f"Aralık anlaşılmadı: {text!r}. Örnek: 30s, 5m, 2h, 1d (birimsiz sayı dakika)."
        )
    seconds = int(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()]
    if seconds < MIN_INTERVAL_S:
        raise SessionCronError(f"Aralık en az {MIN_INTERVAL_S // 60} dakika olmalı.")
    return seconds


# --- Cron ifadesi ---------------------------------------------------------------- #

_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_FIELD_NAMES = ("dakika", "saat", "ayın günü", "ay", "haftanın günü")


def _parse_field(text: str, low: int, high: int, name: str) -> frozenset[int]:
    """Tek cron alanı: `*`, `a`, `a-b`, `a,b`, `*/n`, `a-b/n` → değer kümesi."""
    values: set[int] = set()
    for part in text.split(","):
        step = 1
        body = part
        if "/" in part:
            body, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) < 1:
                raise SessionCronError(f"Cron {name} alanında adım geçersiz: {part!r}")
            step = int(step_text)
        if body == "*":
            start, end = low, high
        elif "-" in body:
            first, last = body.split("-", 1)
            if not (first.isdigit() and last.isdigit()):
                raise SessionCronError(f"Cron {name} alanı geçersiz: {part!r}")
            start, end = int(first), int(last)
        elif body.isdigit():
            start = int(body)
            end = high if step > 1 else start
        else:
            raise SessionCronError(f"Cron {name} alanı geçersiz: {part!r}")
        if not (low <= start <= high and low <= end <= high and start <= end):
            raise SessionCronError(f"Cron {name} alanı {low}-{high} aralığında olmalı: {part!r}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class CronSpec:
    """Ayrıştırılmış 5 alanlı cron ifadesi."""

    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    #: Gün alanı `*` ise haftanın günü tek başına belirleyicidir (ve tersi).
    any_day: bool
    any_weekday: bool

    def matches_day(self, moment: datetime) -> bool:
        if moment.month not in self.months:
            return False
        day_ok = moment.day in self.days
        weekday_ok = (moment.weekday() + 1) % 7 in self.weekdays  # Pazartesi=0 → cron 1
        if self.any_day and self.any_weekday:
            return True
        if self.any_day:
            return weekday_ok
        if self.any_weekday:
            return day_ok
        # crontab: iki alan da kısıtlıysa biri tutsa yeter.
        return day_ok or weekday_ok


def parse_cron(expression: str) -> CronSpec:
    """`dakika saat ayın-günü ay haftanın-günü` → `CronSpec`; hata Türkçe."""
    fields = (expression or "").split()
    if len(fields) != 5:
        raise SessionCronError(
            "Cron ifadesi 5 alan olmalı: dakika saat ayın-günü ay haftanın-günü "
            "(ör. '*/15 9-18 * * 1-5')."
        )
    parsed = [
        _parse_field(text, low, high, name)
        for text, (low, high), name in zip(fields, _FIELD_RANGES, _FIELD_NAMES, strict=True)
    ]
    # crontab uyumu: haftanın gününde 7 de Pazar'dır.
    weekdays = frozenset(0 if day == 7 else day for day in parsed[4])
    return CronSpec(
        minutes=parsed[0],
        hours=parsed[1],
        days=parsed[2],
        months=parsed[3],
        weekdays=weekdays,
        any_day=fields[2] == "*",
        any_weekday=fields[4] == "*",
    )


def cron_next(spec: CronSpec, after: datetime) -> datetime:
    """`after` anından kesinlikle SONRAKİ ilk eşleşme (aynı saat dilimi)."""
    start = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    day = start.replace(hour=0, minute=0)
    for offset in range(_CRON_LOOKAHEAD_DAYS + 1):
        current = day + timedelta(days=offset)
        if not spec.matches_day(current):
            continue
        for hour in sorted(spec.hours):
            for minute in sorted(spec.minutes):
                candidate = current.replace(hour=hour, minute=minute)
                if candidate >= start:
                    return candidate
    raise SessionCronError("Cron ifadesi önümüzdeki bir yıl içinde hiç eşleşmiyor.")


def cron_next_local(spec: CronSpec, after: float) -> float:
    """`after` (epoch) anından sonraki eşleşme; ifade YEREL duvar saatinde yorumlanır.

    Ölçüldü (31 Ekim): `astimezone()` sabit ofset verir; gün eklemek ofseti korur ve
    yaz saati geçişinden sonra '0 9 * * *' yerel 08:00'da tetikleniyordu. Aday saf
    yerel saatte üretilir, ofset o günün gerçek ofsetiyle sonradan bağlanır.
    """
    wall = datetime.fromtimestamp(after)
    return cron_next(spec, wall).astimezone().timestamp()


def cron_min_gap_minutes(spec: CronSpec) -> int:
    """İfadenin ardışık iki eşleşmesi arasındaki en küçük fark (dakika).

    İlk vadeye değil ifadenin kendisine bakar: '* 9 * * *' saat 08:00'da kurulsa
    bile 1 dakikalıktır. Gün sınırı ardışık iki günün eşleştiği varsayılarak
    hesaplanır (temkinli taraf).
    """
    times = sorted(hour * 60 + minute for hour in spec.hours for minute in spec.minutes)
    gaps = [later - earlier for earlier, later in pairwise(times)]
    gaps.append(times[0] + 24 * 60 - times[-1])
    return min(gaps)


# --- Görevler ------------------------------------------------------------------- #


def _loop_abandoned(task: CronTask, now: float) -> bool:
    """Yedek uyanması harcanmış ve yine zamanlanmamış kendi tempolu döngünün vakti geldi mi?"""
    return (
        task.kind is Kind.SELF_PACED
        and task.fallback_armed
        and task.fallback_spent
        and task.next_due <= now
    )


def _next_future_due(task: CronTask, now: float) -> float:
    """Kaçırılan çalışmayı telafi etmeden sıradaki gelecek vade (#372)."""
    if task.next_due > now:
        return task.next_due
    if task.kind is Kind.INTERVAL and task.every_s > 0:
        missed = int((now - task.next_due) // task.every_s) + 1
        return task.next_due + missed * task.every_s
    return cron_next_local(parse_cron(task.cron), now)


@dataclass(frozen=True, slots=True)
class CronTask:
    """Oturum içi zamanlanmış tek görev."""

    id: str
    prompt: str
    kind: Kind
    created_at: float
    next_due: float
    #: Yalnız `INTERVAL`: saniye.
    every_s: int = 0
    #: Yalnız `CRON`: ham ifade (yeniden ayrıştırılır).
    cron: str = ""
    runs: int = 0
    last_run_at: float | None = None
    #: Kullanıcı (`/loop`) ya da ajan (`cron_create`, `schedule_wakeup`).
    source: Source = Source.USER
    #: Yalnız `SELF_PACED`: sıradaki çalışma ajanın değil yedek uyanmanın (#343).
    fallback_armed: bool = False
    #: Yalnız `SELF_PACED`: yedek uyanma bir kez kullanıldı; yine zamanlanmazsa döngü biter.
    fallback_spent: bool = False
    #: `next_due`'ya eklenmiş Claude gecikmesi (sn; erken çalışmada negatif, #363).
    jitter_s: float = 0.0

    @property
    def expires_at(self) -> float:
        return self.created_at + MAX_AGE_S

    def describe(self) -> str:
        """Kullanıcıya/modele tek satır özet."""
        if self.kind is Kind.INTERVAL:
            zaman = f"her {_human_interval(self.every_s)}"
        elif self.kind is Kind.CRON:
            zaman = f"cron {self.cron}"
        elif self.kind is Kind.SELF_PACED:
            zaman = "kendi tempolu"
        else:
            zaman = "bir kez"
        sirada = datetime.fromtimestamp(self.next_due).strftime("%H:%M")
        return f"{self.id} · {zaman} · sıradaki {sirada} · {self.runs} çalışma · {self.prompt[:80]}"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "kind": self.kind.value,
            "created_at": self.created_at,
            "next_due": self.next_due,
            "every_s": self.every_s,
            "cron": self.cron,
            "runs": self.runs,
            "last_run_at": self.last_run_at,
            "source": self.source.value,
            "fallback_armed": self.fallback_armed,
            "fallback_spent": self.fallback_spent,
            "jitter_s": self.jitter_s,
        }


def _cron_offset(task: CronTask, base: float) -> float:
    spec = parse_cron(task.cron)
    gap = cron_next_local(spec, base) - base
    return recurring_offset(task.id, gap, five_minute=is_five_minute(cron=task.cron))


def _with_jitter(task: CronTask) -> CronTask:
    """Yeni görevin ilk vadesine Claude gecikmesini uygula (#363)."""
    if task.kind is Kind.INTERVAL:
        offset = recurring_offset(
            task.id, task.every_s, five_minute=is_five_minute(every_s=task.every_s)
        )
    elif task.kind is Kind.CRON:
        offset = _cron_offset(task, task.next_due)
    elif task.kind is Kind.ONCE:
        offset = once_offset(task.id, task.next_due)
    else:
        return task
    return replace(task, next_due=task.next_due + offset, jitter_s=offset)


def _next_cron_run(task: CronTask, now: float) -> tuple[float, float]:
    """Sıradaki cron çalışması (gecikmeli) ve gecikmesi; kaçırılan çalışma telafi edilmez."""
    spec = parse_cron(task.cron)
    base = cron_next_local(spec, task.next_due - task.jitter_s)
    offset = _cron_offset(task, base)
    while base + offset <= now:
        base = cron_next_local(spec, base)
        offset = _cron_offset(task, base)
    return base + offset, offset


def _human_interval(seconds: int) -> str:
    for unit, label in ((86400, "gün"), (3600, "saat"), (60, "dk"), (1, "sn")):
        if seconds % unit == 0:
            return f"{seconds // unit} {label}"
    return f"{seconds} sn"


class SessionCron:
    """Oturumun görev listesi. Zaman her çağrıda dışarıdan verilir."""

    def __init__(self, tasks: tuple[CronTask, ...] = ()) -> None:
        self._tasks: dict[str, CronTask] = {task.id: task for task in tasks}

    def __len__(self) -> int:
        return len(self._tasks)

    def list(self, now: float | None = None) -> tuple[CronTask, ...]:
        """Süresi dolmamış görevler, vade sırasıyla."""
        if now is not None:
            self.prune(now)
        return tuple(sorted(self._tasks.values(), key=lambda task: task.next_due))

    def get(self, task_id: str) -> CronTask | None:
        return self._tasks.get(task_id)

    def create_interval(
        self, prompt: str, every: str, *, now: float, source: Source = Source.USER
    ) -> CronTask:
        seconds = parse_interval(every)
        return self._add(prompt, Kind.INTERVAL, now, now + seconds, every_s=seconds, source=source)

    def create_cron(
        self, prompt: str, expression: str, *, now: float, source: Source = Source.USER
    ) -> CronTask:
        spec = parse_cron(expression)
        due = cron_next_local(spec, now)
        return self._add(
            prompt, Kind.CRON, now, due, cron=" ".join(expression.split()), source=source
        )

    def create_cron_once(
        self, prompt: str, expression: str, *, now: float, source: Source = Source.USER
    ) -> CronTask:
        """Cron ifadesinin sıradaki eşleşmesinde BİR kez çalışan görev (recurring=false)."""
        due = cron_next_local(parse_cron(expression), now)
        return self._add(prompt, Kind.ONCE, now, due, source=source)

    def create_once(
        self, prompt: str, delay: str, *, now: float, source: Source = Source.USER
    ) -> CronTask:
        """Tek seferlik: `delay` aralık sözdizimidir (`30m`); 1 dakikadan kısa olamaz."""
        seconds = parse_interval(delay)
        return self._add(prompt, Kind.ONCE, now, now + seconds, source=source)

    def create_self_paced(
        self, prompt: str, *, now: float, source: Source = Source.USER
    ) -> CronTask:
        """Kendi tempolu döngü: ilk çalışma hemen (boşta), sonrakini ajan seçer."""
        return self._add(prompt, Kind.SELF_PACED, now, now, source=source)

    def reschedule_self_paced(self, task_id: str, delay_s: int, *, now: float) -> CronTask:
        """Ajanın seçtiği gecikmeyle döngünün sıradaki çalışmasını kur (1 dk – 1 sa)."""
        task = self._tasks.get(task_id)
        if task is None or task.kind is not Kind.SELF_PACED:
            raise SessionCronError(f"Kendi tempolu döngü bulunamadı: {task_id}")
        delay = min(max(delay_s, SELF_PACED_MIN_S), SELF_PACED_MAX_S)
        updated = replace(task, next_due=now + delay, fallback_armed=False, fallback_spent=False)
        self._tasks[task_id] = updated
        return updated

    def restore(self, task: CronTask) -> None:
        """Verilip gönderilemeyen görevin önceki hâlini geri koy (masaüstü `cron.geri_ver`)."""
        self._tasks[task.id] = task

    def merged(self, other: SessionCron) -> SessionCron:
        """İki listenin birleşimi (yeni nesne); aynı kimlikte `other` kazanır, tavan korunur."""
        tasks = {**self._tasks, **other._tasks}
        return SessionCron(tuple(tasks.values())[:MAX_TASKS])

    def delete(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None

    def clear(self) -> int:
        count = len(self._tasks)
        self._tasks.clear()
        return count

    def prune(self, now: float) -> tuple[CronTask, ...]:
        """Süresi dolan görevleri düşür ve düşenleri döndür.

        Claude: yineleyen görev 7 gün dolunca SON BİR KEZ çalışır, sonra kendini siler (#364);
        bu yüzden süresi dolan yineleyen görev düşürülmez, hemen vadesi gelir ve `complete`
        onu siler. Yedek uyanması da harcanmış ve yine zamanlanmamış kendi tempolu döngü biter
        (#343).
        """
        expired: list[CronTask] = []
        for task in tuple(self._tasks.values()):
            if task.expires_at <= now and task.kind in _RECURRING:
                self._tasks[task.id] = replace(task, next_due=min(task.next_due, now))
            elif task.expires_at <= now or _loop_abandoned(task, now):
                del self._tasks[task.id]
                expired.append(task)
        return tuple(expired)

    def restored(self, now: float) -> SessionCron:
        """`--resume` ile geri yüklenecek görevler (#372; yeni nesne).

        Claude: kendi tempolu `/loop` hiç geri gelmez; süresi dolmuş yineleyen ve vakti geçmiş
        tek seferlik görev düşer; kaçırılan çalışmalar telafi edilmez (sıradaki vade ileri alınır).
        """
        kept: list[CronTask] = []
        for task in self._tasks.values():
            if task.kind is Kind.SELF_PACED or task.expires_at <= now:
                continue
            if task.kind is Kind.ONCE:
                if task.next_due > now:
                    kept.append(task)
                continue
            kept.append(replace(task, next_due=_next_future_due(task, now)))
        return SessionCron(tuple(kept))

    def due(self, now: float) -> tuple[CronTask, ...]:
        """Vadesi gelen görevler (vade sırasıyla). Durumu DEĞİŞTİRMEZ; `complete` ilerletir."""
        self.prune(now)
        return tuple(
            sorted(
                (task for task in self._tasks.values() if task.next_due <= now),
                key=lambda task: task.next_due,
            )
        )

    def complete(self, task_id: str, *, now: float) -> CronTask | None:
        """Görev kuyruğa alındı: sayacı artır, sıradaki vadeyi hesapla; tek seferliği düşür."""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.kind is Kind.ONCE or (task.kind in _RECURRING and task.expires_at <= now):
            del self._tasks[task_id]
            return replace(task, runs=task.runs + 1, last_run_at=now)
        if task.kind is Kind.SELF_PACED:
            # Ajan bu yinelemede zamanlamazsa ~20 dk sonra TEK yedek uyanma; o yinelemede de
            # zamanlanmazsa döngü biter (#343). `reschedule_self_paced` ikisini de sıfırlar.
            updated = replace(
                task,
                runs=task.runs + 1,
                last_run_at=now,
                next_due=now + SELF_PACED_FALLBACK_S,
                fallback_armed=True,
                fallback_spent=task.fallback_armed,
            )
            self._tasks[task_id] = updated
            return updated
        if task.kind is Kind.INTERVAL:
            # Aralık çalışmadan sayılır: ilk çalışmadaki gecikme sonrakilere de taşınır (Claude:
            # eşit aralıklı görev her seferinde aynı kadar geç); 5 dakikalık 15 sn erken (#363).
            next_due, jitter = now + task.every_s + min(task.jitter_s, 0.0), task.jitter_s
        else:
            next_due, jitter = _next_cron_run(task, now)
        updated = replace(
            task, runs=task.runs + 1, last_run_at=now, next_due=next_due, jitter_s=jitter
        )
        self._tasks[task_id] = updated
        return updated

    def to_dict(self) -> dict[str, object]:
        return {"gorevler": [task.to_dict() for task in self.list()]}

    @classmethod
    def from_dict(cls, data: object) -> SessionCron:
        """Bozuk kayıt görevi düşürür, oturumu düşürmez."""
        tasks: list[CronTask] = []
        raw = data.get("gorevler") if isinstance(data, dict) else None
        for item in raw if isinstance(raw, list) else ():
            if not isinstance(item, dict):
                continue
            try:
                tasks.append(
                    CronTask(
                        id=str(item["id"]),
                        prompt=str(item["prompt"]),
                        kind=Kind(item["kind"]),
                        created_at=float(item["created_at"]),
                        next_due=float(item["next_due"]),
                        every_s=int(item.get("every_s", 0)),
                        cron=str(item.get("cron", "")),
                        runs=int(item.get("runs", 0)),
                        last_run_at=(
                            float(item["last_run_at"])
                            if item.get("last_run_at") is not None
                            else None
                        ),
                        # Eski kayıtta alan yok: kullanıcı görevi sayılır (geri uyum).
                        source=Source(item.get("source", Source.USER.value)),
                        fallback_armed=item.get("fallback_armed") is True,
                        fallback_spent=item.get("fallback_spent") is True,
                        jitter_s=float(item.get("jitter_s", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return cls(tuple(tasks))

    def _add(
        self,
        prompt: str,
        kind: Kind,
        now: float,
        next_due: float,
        *,
        every_s: int = 0,
        cron: str = "",
        source: Source = Source.USER,
    ) -> CronTask:
        text = (prompt or "").strip()
        if not text:
            raise SessionCronError("Görev metni boş olamaz.")
        self.prune(now)
        if len(self._tasks) >= MAX_TASKS:
            raise SessionCronError(f"Oturumda en çok {MAX_TASKS} zamanlanmış görev olabilir.")
        task = CronTask(
            id=uuid4().hex[:8],
            prompt=text[:MAX_PROMPT_CHARS],
            kind=kind,
            created_at=now,
            next_due=next_due,
            every_s=every_s,
            cron=cron,
            source=source,
        )
        task = _with_jitter(task)
        self._tasks[task.id] = task
        return task
