"""Zamanlananlar: daha sonra çalışacak görevlerin kalıcı deposu (`zamanlama.*`).

Çekirdek yalnız depoyu ve "sıradaki çalışma" hesabını taşır. Görevi çalıştıran
masaüstü uygulamasıdır: vadesi gelenleri `zamanlama.vadesi_gelenler` ile ALIR
(alınan görevin sıradaki zamanı aynı yazımda ilerler; aynı görev iki kez verilmez)
ve her biri için yeni bir sohbet açar ya da Kits kuyruğuna teslim eder.

Uygulama açıkken yoklama sohbet açık olmasa da sürer: hazır sohbet yoksa arayüz
`zamanlayici` kimlikli görünmez bir çekirdek oturumu açar (`app/src/schedule/schedulerCore.ts`).
Yoklamayı aynı anda tek uygulama örneği yürütür (`zamanlama.sahiplik`, bkz. `schedule_lease`).
Uygulama kapalıyken görev çalışmaz; açılışta vadesi geçmiş görev bir kez, gecikmeli olarak verilir.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec

from ..config.paths import user_data_dir
from ..core.session_cron import (
    SessionCronError,
    cron_min_gap_minutes,
    cron_next_local,
    parse_cron,
)
from .schedule_delivery import (
    acknowledge_delivery,
    add_delivery,
    pending_deliveries,
    store_lock,
    validate_deliveries,
)
from .schedule_lease import LEASE_TTL_S, acquire_lease, release_lease

KIND_ONCE = "bir_kez"
KIND_DAILY = "gunluk"
KIND_WEEKLY = "haftalik"
KIND_INTERVAL = "aralik"
#: Cron ifadesi (5 alan); ayrıştırıcı oturum zamanlayıcısıyla ortak (`core.session_cron`, P-038).
KIND_CRON = "cron"
KINDS = (KIND_ONCE, KIND_DAILY, KIND_WEEKLY, KIND_INTERVAL, KIND_CRON)
#: Zamanlama türüne göre taşınan alanlar; tür değişince öteki türün alanı düşer.
SPEC_KEYS = ("zaman", "saat", "gunler", "dakika", "cron")

#: En kısa yineleme aralığı (dakika). Her çalışma yeni bir sohbet ve model turu
#: açar; ücretsiz sağlayıcı kotası (NIM 40 istek/dk) daha sık tetiklemeyi kaldırmaz.
MIN_INTERVAL_MINUTES = 15
MAX_TITLE = 120
MAX_TASK = 8000
MAX_SCHEDULES = 100


class ScheduleError(ValueError):
    """Zamanlama verisi sözleşmeye uymuyor; mesaj kullanıcıya gösterilir."""


def schedules_path() -> Path:
    return user_data_dir() / "zamanlananlar.json"


def _read_records(path: Path) -> list[Any]:
    """Dosyayı oku; dosya düzeyi bozulma (okunamaz, JSON değil, liste değil) hata verir."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError) as error:
        raise ScheduleError("Zamanlama deposu okunamadı; mevcut teslimler korunuyor.") from error
    try:
        raw = json.loads(content)
    except ValueError as error:
        raise ScheduleError("Zamanlama deposu bozuk; mevcut teslimler korunuyor.") from error
    if not isinstance(raw, list):
        raise ScheduleError("Zamanlama deposu liste/kayıt sözleşmesine uymuyor.")
    return raw


def _record_problem(item: object) -> str | None:
    """Kaydın neden geçersiz olduğu; geçerliyse None."""
    if not isinstance(item, dict):
        return "Zamanlama deposu liste/kayıt sözleşmesine uymuyor."
    try:
        validate_deliveries(item)
    except ValueError as error:
        return str(error)
    return None


def _split_records(path: Path) -> tuple[list[dict[str, Any]], list[Any]]:
    raw = _read_records(path)
    good = [item for item in raw if _record_problem(item) is None]
    return good, [item for item in raw if _record_problem(item) is not None]


def _load(path: Path) -> list[dict[str, Any]]:
    """Tüm kayıtlar geçerliyse döner; biri bozuksa HİÇBİR yazma yapılmaz.

    Bozuk kayıt teslim bilgisi taşıyabilir; sessizce atlayıp depoyu yeniden yazmak onu
    kalıcı olarak silerdi (bkz. `test_schedule_delivery`). Çıkış yolu `quarantine_invalid`:
    kullanıcının açık eylemiyle bozuk kayıtlar yedeklenip ayrılır.
    """
    raw = _read_records(path)
    for item in raw:
        problem = _record_problem(item)
        if problem is not None:
            raise ScheduleError(f"{problem} Bozuk kaydı ayırmak için 'bozuk kayıtları ayır' de.")
    return raw


_ScheduleParams = ParamSpec("_ScheduleParams")


def _storage_errors(
    function: Callable[_ScheduleParams, dict[str, Any]],
) -> Callable[_ScheduleParams, dict[str, Any]]:
    """Depo bozukken mutation yapılmaz; RPC/direct çağrı hata sonucu taşır."""

    @wraps(function)
    def guarded(*args: _ScheduleParams.args, **kwargs: _ScheduleParams.kwargs) -> dict[str, Any]:
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError) as error:
            return {"ok": False, "metin": str(error)}

    return guarded


def _store(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def _clock(value: object) -> tuple[int, int]:
    if isinstance(value, str):
        hour, _, minute = value.partition(":")
        if hour.isdigit() and minute.isdigit() and int(hour) < 24 and int(minute) < 60:
            return int(hour), int(minute)
    raise ScheduleError("Saat SS:DD biçiminde olmalı (ör. 09:00).")


def _root_problem(root: object) -> str | None:
    """Gözetimsiz görev için kabul edilmeyen kök: dosya sistemi kökü ya da ev klasörü.

    Zamanlanmış görev kullanıcı başında olmadan çalışır; `/` ya da `~` kökü ona tüm
    makineyi/ev klasörünü okuma-yazma alanı yapar (S2-25). Proje klasörü seçilmeli.
    Ölçüldü (30 Ekim): doğrulama yalnız `is_dir()` bakıyordu; ikisi de geçiyordu.
    """
    if not isinstance(root, str) or not root.strip():
        return None
    try:
        path = Path(root).expanduser().resolve()
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        return None
    if path == path.parent or path == home:
        return "Zamanlanmış görev kök dizinde ya da ev klasöründe çalışamaz; bir proje klasörü seç."
    return None


def next_run(spec: dict[str, Any], after: datetime) -> float | None:
    """`after` anından SONRAKİ ilk çalışma (epoch saniye); bitmiş tek seferlikte None."""
    kind = spec.get("tur")
    if kind == KIND_ONCE:
        moment = spec.get("zaman")
        if not isinstance(moment, (int, float)) or isinstance(moment, bool):
            raise ScheduleError("Tek seferlik görev için tarih ve saat gerekli.")
        return float(moment) if moment > after.timestamp() else None
    if kind == KIND_INTERVAL:
        minutes = spec.get("dakika")
        if not isinstance(minutes, int) or isinstance(minutes, bool):
            raise ScheduleError("Aralık dakika cinsinden bir tam sayı olmalı.")
        if minutes < MIN_INTERVAL_MINUTES:
            raise ScheduleError(f"Aralık en az {MIN_INTERVAL_MINUTES} dakika olmalı.")
        return (after + timedelta(minutes=minutes)).timestamp()
    if kind == KIND_CRON:
        expression = spec.get("cron")
        if not isinstance(expression, str) or not expression.strip():
            raise ScheduleError("Cron ifadesi gerekli (dakika saat gün ay hafta-günü).")
        try:
            parsed = parse_cron(expression)
        except SessionCronError as error:
            raise ScheduleError(str(error)) from error
        # Sıklık ifadenin kendisinden ölçülür, ilk vadeden değil. Ölçüldü (31 Ekim):
        # 08:00'da kaydedilen '* 9 * * *' denetimi geçiyor, ilk çalışmadan sonra
        # `_advance` hatayı yutup görevi sessizce kapatıyordu.
        if cron_min_gap_minutes(parsed) < MIN_INTERVAL_MINUTES:
            raise ScheduleError(
                f"Cron ifadesi en sık {MIN_INTERVAL_MINUTES} dakikada bir çalışabilir."
            )
        try:
            return cron_next_local(parsed, after.timestamp())
        except SessionCronError as error:
            raise ScheduleError(str(error)) from error
    if kind not in (KIND_DAILY, KIND_WEEKLY):
        raise ScheduleError("Bilinmeyen zamanlama türü.")
    hour, minute = _clock(spec.get("saat"))
    days = _weekdays(spec.get("gunler")) if kind == KIND_WEEKLY else frozenset(range(7))
    # Duvar saati yerel saatte, ofset HER GÜN için ayrı hesaplanır. Ölçüldü (29 Ekim):
    # `astimezone()` sabit ofset verir; gün eklemek ofseti korur ve yaz saatine geçilen
    # bölgede 09:00 görevi ertesi gün yerel 10:00'da çalışıyordu.
    local = after.astimezone().replace(tzinfo=None)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for offset in range(8):
        wall = candidate + timedelta(days=offset)
        moment = wall.astimezone()  # saf yerel saat → o günün gerçek ofseti
        if moment > after and wall.weekday() in days:
            return moment.timestamp()
    raise ScheduleError("Sıradaki çalışma hesaplanamadı.")


def _weekdays(value: object) -> frozenset[int]:
    message = "Haftalık görev için en az bir gün seç (0=Pazartesi … 6=Pazar)."
    if not isinstance(value, list) or not value:
        raise ScheduleError(message)
    days = [day for day in value if isinstance(day, int) and not isinstance(day, bool)]
    if len(days) != len(value) or not all(0 <= day <= 6 for day in days):
        raise ScheduleError(message)
    return frozenset(days)


def _validated(data: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Yalnız bilinen alanlarla YENİ bir kayıt döndür; geçersizse `ScheduleError`."""
    title, task, root = data.get("baslik"), data.get("gorev"), data.get("kok")
    if not isinstance(task, str) or not task.strip():
        raise ScheduleError("Görev metni boş olamaz.")
    if not isinstance(root, str) or not Path(root).expanduser().is_dir():
        raise ScheduleError("Görevin çalışacağı klasör bulunamadı.")
    if (problem := _root_problem(root)) is not None:
        raise ScheduleError(problem)
    kind = data.get("tur")
    if kind not in KINDS:
        raise ScheduleError("Bilinmeyen zamanlama türü.")
    spec: dict[str, Any] = {"tur": kind}
    for key in SPEC_KEYS:
        if data.get(key) is not None:
            spec[key] = data[key]
    if isinstance(spec.get("cron"), str):
        spec["cron"] = " ".join(spec["cron"].split())
    upcoming = next_run(spec, now)
    if upcoming is None:
        raise ScheduleError("Seçilen zaman geçmişte kaldı.")
    clean_title = title.strip()[:MAX_TITLE] if isinstance(title, str) and title.strip() else ""
    return {
        **spec,
        "baslik": clean_title or task.strip()[:60],
        "gorev": task.strip()[:MAX_TASK],
        "kok": str(Path(root).expanduser()),
        "etkin": data.get("etkin") is not False,
        "sonraki": upcoming,
    }


@_storage_errors
def list_schedules(path: Path | None = None) -> dict[str, Any]:
    """Geçerli görevleri listeler; bozuk kayıt varsa sayısını da bildirir (yazma yapılmaz)."""
    items, bad = _split_records(path or schedules_path())
    items.sort(key=lambda item: (item.get("sonraki") is None, item.get("sonraki") or 0))
    result: dict[str, Any] = {"ok": True, "gorevler": items}
    if bad:
        result["bozuk_kayit"] = len(bad)
        result["metin"] = f"{len(bad)} bozuk kayıt var; çalışmaları durduruldu. Ayırmak gerekir."
    return result


@_storage_errors
def quarantine_invalid(path: Path | None = None) -> dict[str, Any]:
    """Bozuk kayıtları `<dosya>.bad-<özet>` yedeğine al, depoyu geçerli kayıtlarla yaz.

    Yalnız kullanıcının açık eylemiyle çalışır. Önce yedek yazılır; yedek yazılamazsa
    depoya dokunulmaz, yani kayıt hiçbir koşulda yedeksiz silinmez.
    """
    target = path or schedules_path()
    with store_lock(target):
        good, bad = _split_records(target)
        if not bad:
            return {"ok": True, "ayrilan": 0}
        payload = json.dumps(bad, ensure_ascii=False, indent=1)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        backup = target.with_name(f"{target.name}.bad-{digest}")
        if not backup.exists():
            backup.write_text(payload, encoding="utf-8")
        _store(target, good)
        return {"ok": True, "ayrilan": len(bad), "yedek": backup.name}


@_storage_errors
def save_schedule(
    data: dict[str, Any], path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Yeni görev oluştur ya da `id` verilmişse var olanı güncelle."""
    target = path or schedules_path()
    try:
        record = _validated(data, now or datetime.now().astimezone())
    except ScheduleError as error:
        return {"ok": False, "metin": str(error)}
    with store_lock(target):
        items = _load(target)
        schedule_id = data.get("id")
        if isinstance(schedule_id, str) and schedule_id:
            existing = next((item for item in items if item.get("id") == schedule_id), None)
            if existing is None:
                return {"ok": False, "metin": "Güncellenecek görev bulunamadı."}
            saved = {**existing, **record}
            for key in SPEC_KEYS:
                if key not in record:
                    saved.pop(key, None)
            items = [saved if item.get("id") == schedule_id else item for item in items]
        else:
            if len(items) >= MAX_SCHEDULES:
                return {"ok": False, "metin": f"En çok {MAX_SCHEDULES} zamanlanmış görev tutulur."}
            saved = {
                **record,
                "id": uuid.uuid4().hex,
                "olusturma": time.time(),
                "son_calisma": None,
            }
            items = [*items, saved]
        _store(target, items)
        return {"ok": True, "gorev": saved}


@_storage_errors
def delete_schedule(data: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    # Açık silme takvimi ve ona bağlı onaysız teslimleri birlikte iptal eder.
    target = path or schedules_path()
    with store_lock(target):
        items = _load(target)
        remaining = [item for item in items if item.get("id") != data.get("id")]
        if len(remaining) == len(items):
            return {"ok": False, "metin": "Silinecek görev bulunamadı."}
        _store(target, remaining)
        return {"ok": True}


@_storage_errors
def set_enabled(
    data: dict[str, Any], path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Görevi duraklat ya da sürdür. Sürdürülen görevin zamanı bugünden hesaplanır."""
    target = path or schedules_path()
    moment = now or datetime.now().astimezone()
    enabled = data.get("etkin") is True
    with store_lock(target):
        items = _load(target)
        updated = None
        for index, item in enumerate(items):
            if item.get("id") != data.get("id"):
                continue
            upcoming = item.get("sonraki")
            if enabled:
                try:
                    upcoming = next_run(item, moment)
                except ScheduleError as error:
                    return {"ok": False, "metin": str(error)}
            updated = {**item, "etkin": enabled and upcoming is not None, "sonraki": upcoming}
            items[index] = updated
        if updated is None:
            return {"ok": False, "metin": "Görev bulunamadı."}
        _store(target, items)
        return {"ok": True, "gorev": updated}


def _advance(item: dict[str, Any], moment: datetime, *, late: bool) -> dict[str, Any]:
    try:
        upcoming = next_run(item, moment)
    except ScheduleError:
        upcoming = None
    return {
        **item,
        "son_calisma": moment.timestamp(),
        "son_gecikmeli": late,
        "sonraki": upcoming,
        "etkin": bool(item.get("etkin")) and upcoming is not None,
    }


#: Vadesinden bu kadar sonra verilen görev "gecikmeli" sayılır (uygulama kapalıydı).
LATE_AFTER_S = 300.0


@_storage_errors
def claim_due(path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Vadesi gelen etkin görevleri ver ve sıradaki zamanlarını ilerlet."""
    target = path or schedules_path()
    moment = now or datetime.now().astimezone()
    stamp = moment.timestamp()
    with store_lock(target):
        items = _load(target)
        due: list[dict[str, Any]] = []
        changed = False
        for index, item in enumerate(items):
            upcoming = item.get("sonraki")
            if not item.get("etkin") or not isinstance(upcoming, (int, float)) or upcoming > stamp:
                continue
            if (problem := _root_problem(item.get("kok"))) is not None:
                # Doğrulamadan önce kaydedilmiş tehlikeli kök: teslim edilmez, görev durdurulur.
                items[index] = {**item, "etkin": False, "durdurma_nedeni": problem}
                changed = True
                continue
            item = add_delivery(item, float(upcoming))
            advanced = _advance(item, moment, late=stamp - upcoming > LATE_AFTER_S)
            items[index] = advanced
            due.append(advanced)
        if due or changed:
            _store(target, items)
        return {"ok": True, "gorevler": due}


@_storage_errors
def run_now(
    data: dict[str, Any], path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Görevi zamanını beklemeden ver; yinelenen görevin takvimi değişmez."""
    target = path or schedules_path()
    moment = now or datetime.now().astimezone()
    with store_lock(target):
        items = _load(target)
        for index, item in enumerate(items):
            if item.get("id") == data.get("id"):
                if (problem := _root_problem(item.get("kok"))) is not None:
                    return {"ok": False, "metin": problem}
                started = {**item, "son_calisma": moment.timestamp(), "son_gecikmeli": False}
                items[index] = started
                _store(target, items)
                return {"ok": True, "gorev": started}
        return {"ok": False, "metin": "Görev bulunamadı."}


#: Görev başına saklanan son çalışma sayısı ve özet tavanı (P-038 çalışma geçmişi).
MAX_RUN_HISTORY = 10
MAX_RUN_SUMMARY = 240
RUN_STATES = ("tamam", "hata", "onay_bekliyor")


@_storage_errors
def record_run(
    data: dict[str, Any], path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """`zamanlama.calisma_kaydet {id, sohbet_id, durum, ozet}`: biten çalışmayı geçmişe yaz.

    Ölçüldü (31 Ekim): kalıcı zamanlayıcı yalnız `son_calisma` damgası tutuyordu; çalışmanın
    sonucu, hangi sohbette koştuğu ve hata verip vermediği görülemiyordu.
    """
    target = path or schedules_path()
    state, conversation = data.get("durum"), data.get("sohbet_id")
    if state not in RUN_STATES or not isinstance(conversation, str) or not conversation:
        return {"ok": False, "metin": "Çalışma kaydı için durum ve sohbet kimliği gerekli."}
    summary = data.get("ozet")
    entry = {
        "zaman": (now or datetime.now().astimezone()).timestamp(),
        "sohbet_id": conversation[:128],
        "durum": state,
        "ozet": summary.strip()[:MAX_RUN_SUMMARY] if isinstance(summary, str) else "",
    }
    with store_lock(target):
        items = _load(target)
        for index, item in enumerate(items):
            if item.get("id") == data.get("id"):
                history = item.get("gecmis")
                previous = history if isinstance(history, list) else []
                items[index] = {**item, "gecmis": [entry, *previous][:MAX_RUN_HISTORY]}
                _store(target, items)
                return {"ok": True, "gorev": items[index]}
        return {"ok": False, "metin": "Görev bulunamadı."}


def list_pending_deliveries() -> dict[str, object]:
    """Kuyruk tüketicisi yeniden açılışta onaysız teslimleri alabilir."""
    from dataclasses import asdict

    try:
        deliveries = pending_deliveries(schedules_path())
    except (ValueError, OSError) as error:
        return {"ok": False, "metin": str(error)}
    return {
        "ok": True,
        "teslimler": [{**asdict(delivery), "gorev": delivery.task} for delivery in deliveries],
    }


def ack_pending_delivery(data: dict[str, Any]) -> dict[str, object]:
    occurrence, task = data.get("occurrence_id"), data.get("task_id")
    if not isinstance(occurrence, str) or not isinstance(task, str):
        return {"ok": False, "metin": "Vade ve task kimliği gerekli."}
    try:
        accepted = acknowledge_delivery(schedules_path(), occurrence, task)
    except (ValueError, OSError) as error:
        return {"ok": False, "metin": str(error)}
    return {"ok": accepted}


def acquire_scheduler_lease(data: dict[str, Any]) -> dict[str, Any]:
    """`zamanlama.sahiplik`: vade yoklamasının sahibi olmayı iste ya da kirayı yenile."""
    owner, duration = data.get("sahip"), data.get("sure_s")
    if not isinstance(owner, str):
        return {"ok": False, "metin": "Zamanlayıcı sahibi gerekli."}
    ttl = (
        duration if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
    )
    try:
        return acquire_lease(owner, schedules_path(), ttl=float(ttl or LEASE_TTL_S))
    except OSError as error:
        return {"ok": False, "metin": str(error)}


def release_scheduler_lease(data: dict[str, Any]) -> dict[str, Any]:
    """`zamanlama.sahiplik_birak`: uygulama kapanırken kirayı hemen bırak."""
    owner = data.get("sahip")
    if not isinstance(owner, str):
        return {"ok": False, "metin": "Zamanlayıcı sahibi gerekli."}
    try:
        return release_lease(owner, schedules_path())
    except OSError as error:
        return {"ok": False, "metin": str(error)}


#: İstek adı → işleyici. `session.py` yalnız bu tabloya bakar.
SCHEDULE_ROUTES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "zamanlama.liste": lambda _data: list_schedules(),
    "zamanlama.bozuklari_ayir": lambda _data: quarantine_invalid(),
    "zamanlama.kaydet": save_schedule,
    "zamanlama.sil": delete_schedule,
    "zamanlama.etkin": set_enabled,
    "zamanlama.vadesi_gelenler": lambda _data: claim_due(),
    "zamanlama.simdi": run_now,
    "zamanlama.calisma_kaydet": record_run,
    "zamanlama.teslim_bekleyenler": lambda _data: list_pending_deliveries(),
    "zamanlama.teslim_onayla": ack_pending_delivery,
    "zamanlama.sahiplik": acquire_scheduler_lease,
    "zamanlama.sahiplik_birak": release_scheduler_lease,
}
