"""Zamanlayıcı sahipliği: vade yoklamasını aynı anda tek uygulama örneği yürütür.

Zamanlama deposu kullanıcı düzeyinde TEK dosyadır; birden çok uygulama örneği (ya da
yeniden yüklenen bir pencere) aynı bekleyen teslimi aynı anda Kits'e göndermeye çalışabilir.
`claim_due` vadeyi zaten atomik verir (kilit altında ilerler); ama bekleyen teslim ack'e
kadar çekirdekte durduğu için iki yoklayıcı onu birlikte görür.

Çözüm süreli kira: yoklayıcı her turda `acquire_lease` ile kirayı alır/yeniler, kira
başkasındaysa yoklamayı atlar. Sahip çökerse kira süre dolunca devralınır; kira kaybı veri
kaybı değildir (kayıtlar dosyada kalır), bu yüzden bozuk kira dosyası kimseyi kilitlemez.
Kira ayrı bir dosyada tutulur: görev kayıtlarının şeması (eski sürümler katı doğrular)
değişmez.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .schedule_delivery import store_lock

#: Varsayılan kira süresi. Yoklama 30 sn'de bir yeniler; çökmüş sahip en çok bu kadar bekletir.
LEASE_TTL_S = 90.0
LEASE_MIN_S = 30.0
LEASE_MAX_S = 300.0
MAX_OWNER = 100


def _lease_path(store: Path) -> Path:
    return store.with_name(store.name + ".lease")


def _read(path: Path) -> tuple[str, float] | None:
    """Geçerli kira (sahip, bitiş); yok ya da bozuksa None."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    owner, end = raw.get("sahip"), raw.get("bitis")
    if not isinstance(owner, str) or not owner:
        return None
    if isinstance(end, bool) or not isinstance(end, (int, float)):
        return None
    return owner, float(end)


def _write(path: Path, owner: str, end: float) -> None:
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"sahip": owner, "bitis": end}), encoding="utf-8")
    temporary.replace(path)


def _valid_owner(owner: object) -> bool:
    return isinstance(owner, str) and 0 < len(owner) <= MAX_OWNER


def acquire_lease(
    owner: str,
    store: Path,
    *,
    now: float | None = None,
    ttl: float = LEASE_TTL_S,
) -> dict[str, Any]:
    """Kirayı al ya da yenile; başkasındaysa `sahip=False` ve kalan süreyi bildir."""
    if not _valid_owner(owner):
        return {"ok": False, "metin": "Zamanlayıcı sahibi 1-100 karakterlik bir kimlik olmalı."}
    moment = time.time() if now is None else now
    length = min(max(ttl, LEASE_MIN_S), LEASE_MAX_S)
    path = _lease_path(store)
    with store_lock(store):
        current = _read(path)
        if current is not None and current[0] != owner and current[1] > moment:
            return {"ok": True, "sahip": False, "bekle_s": current[1] - moment}
        _write(path, owner, moment + length)
    return {"ok": True, "sahip": True, "bitis": moment + length}


def release_lease(owner: str, store: Path) -> dict[str, Any]:
    """Kiranın sahibi bırakırsa hemen devralınabilir; yabancı bırakamaz."""
    if not _valid_owner(owner):
        return {"ok": False, "metin": "Zamanlayıcı sahibi 1-100 karakterlik bir kimlik olmalı."}
    path = _lease_path(store)
    with store_lock(store):
        current = _read(path)
        if current is None or current[0] != owner:
            return {"ok": True, "birakildi": False}
        path.unlink(missing_ok=True)
    return {"ok": True, "birakildi": True}
