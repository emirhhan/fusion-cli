"""Zamanlananlar: daha sonra çalışacak görevlerin kalıcı deposu (`zamanlama.*`).

Çekirdek yalnız depoyu ve "sıradaki çalışma" hesabını taşır. Görevi çalıştıran
masaüstü uygulamasıdır: vadesi gelenleri `zamanlama.vadesi_gelenler` ile ALIR
(alınan görevin sıradaki zamanı aynı yazımda ilerler; aynı görev iki kez verilmez)
ve her biri için yeni bir sohbet açar. Uygulama kapalıyken görev çalışmaz;
açılışta vadesi geçmiş görev bir kez, gecikmeli olarak verilir.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config.paths import user_data_dir

KIND_ONCE = "bir_kez"
KIND_DAILY = "gunluk"
KIND_WEEKLY = "haftalik"
KIND_INTERVAL = "aralik"
KINDS = (KIND_ONCE, KIND_DAILY, KIND_WEEKLY, KIND_INTERVAL)

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


def _load(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


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
    if kind not in (KIND_DAILY, KIND_WEEKLY):
        raise ScheduleError("Bilinmeyen zamanlama türü.")
    hour, minute = _clock(spec.get("saat"))
    days = _weekdays(spec.get("gunler")) if kind == KIND_WEEKLY else frozenset(range(7))
    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for offset in range(8):
        moment = candidate + timedelta(days=offset)
        if moment > after and moment.weekday() in days:
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
    kind = data.get("tur")
    if kind not in KINDS:
        raise ScheduleError("Bilinmeyen zamanlama türü.")
    spec: dict[str, Any] = {"tur": kind}
    for key in ("zaman", "saat", "gunler", "dakika"):
        if data.get(key) is not None:
            spec[key] = data[key]
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


def list_schedules(path: Path | None = None) -> dict[str, Any]:
    items = _load(path or schedules_path())
    items.sort(key=lambda item: (item.get("sonraki") is None, item.get("sonraki") or 0))
    return {"ok": True, "gorevler": items}


def save_schedule(
    data: dict[str, Any], path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Yeni görev oluştur ya da `id` verilmişse var olanı güncelle."""
    target = path or schedules_path()
    try:
        record = _validated(data, now or datetime.now().astimezone())
    except ScheduleError as error:
        return {"ok": False, "metin": str(error)}
    items = _load(target)
    schedule_id = data.get("id")
    if isinstance(schedule_id, str) and schedule_id:
        existing = next((item for item in items if item.get("id") == schedule_id), None)
        if existing is None:
            return {"ok": False, "metin": "Güncellenecek görev bulunamadı."}
        saved = {**existing, **record}
        for key in ("zaman", "saat", "gunler", "dakika"):
            if key not in record:
                saved.pop(key, None)
        items = [saved if item.get("id") == schedule_id else item for item in items]
    else:
        if len(items) >= MAX_SCHEDULES:
            return {"ok": False, "metin": f"En çok {MAX_SCHEDULES} zamanlanmış görev tutulur."}
        saved = {**record, "id": uuid.uuid4().hex, "olusturma": time.time(), "son_calisma": None}
        items = [*items, saved]
    _store(target, items)
    return {"ok": True, "gorev": saved}


def delete_schedule(data: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    target = path or schedules_path()
    items = _load(target)
    remaining = [item for item in items if item.get("id") != data.get("id")]
    if len(remaining) == len(items):
        return {"ok": False, "metin": "Silinecek görev bulunamadı."}
    _store(target, remaining)
    return {"ok": True}


def set_enabled(
    data: dict[str, Any], path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Görevi duraklat ya da sürdür. Sürdürülen görevin zamanı bugünden hesaplanır."""
    target = path or schedules_path()
    moment = now or datetime.now().astimezone()
    enabled = data.get("etkin") is True
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


def claim_due(path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Vadesi gelen etkin görevleri ver ve sıradaki zamanlarını ilerlet."""
    target = path or schedules_path()
    moment = now or datetime.now().astimezone()
    stamp = moment.timestamp()
    items = _load(target)
    due: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        upcoming = item.get("sonraki")
        if not item.get("etkin") or not isinstance(upcoming, (int, float)) or upcoming > stamp:
            continue
        advanced = _advance(item, moment, late=stamp - upcoming > LATE_AFTER_S)
        items[index] = advanced
        due.append(advanced)
    if due:
        _store(target, items)
    return {"ok": True, "gorevler": due}


def run_now(
    data: dict[str, Any], path: Path | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Görevi zamanını beklemeden ver; yinelenen görevin takvimi değişmez."""
    target = path or schedules_path()
    moment = now or datetime.now().astimezone()
    items = _load(target)
    for index, item in enumerate(items):
        if item.get("id") == data.get("id"):
            started = {**item, "son_calisma": moment.timestamp(), "son_gecikmeli": False}
            items[index] = started
            _store(target, items)
            return {"ok": True, "gorev": started}
    return {"ok": False, "metin": "Görev bulunamadı."}


#: İstek adı → işleyici. `session.py` yalnız bu tabloya bakar.
SCHEDULE_ROUTES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "zamanlama.liste": lambda _data: list_schedules(),
    "zamanlama.kaydet": save_schedule,
    "zamanlama.sil": delete_schedule,
    "zamanlama.etkin": set_enabled,
    "zamanlama.vadesi_gelenler": lambda _data: claim_due(),
    "zamanlama.simdi": run_now,
}
