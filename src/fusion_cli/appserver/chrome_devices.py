"""Köprüye bağlı birden çok tarayıcı (#432): her eklenti kendi komut kuyruğunu yoklar.

Claude in Chrome: birden çok tarayıcı bağlıysa `list_connected_browsers` hepsini listeler,
`select_browser` birini seçer, `switch_browser` bütün tarayıcılara bağlanma isteği yayar
ve kullanıcı istediği tarayıcıda "Connect"e basar; seçim başka tarayıcı bağlansa da korunur.
Bir tarayıcı eylemi başlarken birden çok tarayıcı bağlı ve seçim yoksa kullanıcıya hangisinin
kullanılacağı sorulur. Eklentinin eski sürümü kimlik göndermez; o bağlantı `fusion-local`
cihazı sayılır (geri uyum).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

#: Kimlik göndermeyen (eski) eklentinin cihazı; Claude'un `deviceId`'sine karşılık gelir.
LOCAL_DEVICE_ID = "fusion-local"
#: Komut kanalı bu süre sessiz kalırsa cihaz kopuk sayılır (köprüyle aynı eşik).
DEVICE_STALE_SECONDS = 35
_DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NAME_LIMIT = 40


class BrowserChoiceRequiredError(ConnectionError):
    """Birden çok tarayıcı bağlı ve hiçbiri seçilmemiş: kullanıcıya sorulmalı."""


@dataclass
class BrowserDevice:
    device_id: str
    name: str
    last_seen: float = 0.0
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)


def parse_device(body: object) -> tuple[str, str]:
    """İstek gövdesindeki `cihaz: {id, ad}`; yoksa ya da geçersizse yerel cihaz."""
    raw = body.get("cihaz") if isinstance(body, dict) else None
    if not isinstance(raw, dict):
        return LOCAL_DEVICE_ID, "Chrome"
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not _DEVICE_ID.match(identifier):
        return LOCAL_DEVICE_ID, "Chrome"
    name = raw.get("ad")
    clean = name.strip()[:_NAME_LIMIT] if isinstance(name, str) and name.strip() else "Chrome"
    return identifier, clean


class BrowserDevices:
    """Bağlı tarayıcılar, seçili tarayıcı ve `switch_browser` bekleyişi."""

    def __init__(self) -> None:
        self._devices: dict[str, BrowserDevice] = {}
        self.selected: str | None = None
        self._switch: asyncio.Future[str] | None = None

    def touch(self, device_id: str = LOCAL_DEVICE_ID, name: str = "Chrome") -> BrowserDevice:
        device = self._devices.get(device_id)
        if device is None:
            device = BrowserDevice(device_id, name)
            self._devices[device_id] = device
        device.name = name
        device.last_seen = time.monotonic()
        return device

    def queue(self, device_id: str) -> asyncio.Queue[dict[str, Any]]:
        device = self._devices.get(device_id) or self.touch(device_id)
        return device.queue

    def forget(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device is not None:
            device.last_seen = 0.0

    def connected(self) -> list[BrowserDevice]:
        now = time.monotonic()
        alive = [d for d in self._devices.values() if now - d.last_seen < DEVICE_STALE_SECONDS]
        return sorted(alive, key=lambda device: device.device_id)

    def target(self) -> BrowserDevice | None:
        """Komutun gideceği cihaz; birden çok bağlı ve seçim yoksa `BrowserChoiceRequiredError`."""
        alive = self.connected()
        chosen = next((d for d in alive if d.device_id == self.selected), None)
        if chosen is not None:
            return chosen
        if self.selected is not None:
            raise BrowserChoiceRequiredError(
                "Seçili tarayıcı bağlantısı koptu. Başka tarayıcıya işlem gönderilmedi. "
                "Yeniden bağlan veya select_browser ile kullanıcı seçimini güncelle."
            )
        if len(alive) > 1:
            names = ", ".join(f"{d.name} ({d.device_id})" for d in alive)
            raise BrowserChoiceRequiredError(
                f"Birden çok tarayıcı bağlı: {names}. Kullanıcıya hangisinin kullanılacağını "
                "sor; seçince select_browser ile o deviceId'yi seç (terminalde /chrome select)."
            )
        return alive[0] if alive else None

    def select(self, device_id: str) -> BrowserDevice | None:
        device = next((d for d in self.connected() if d.device_id == device_id), None)
        if device is None:
            return None
        self.selected = device_id
        if self._switch is not None and not self._switch.done():
            self._switch.set_result(device_id)
        return device

    def describe(self) -> list[dict[str, Any]]:
        """Claude `list_connected_browsers` biçimi."""
        alive = self.connected()
        in_use = self.selected if any(d.device_id == self.selected for d in alive) else None
        if self.selected is None and len(alive) == 1:
            in_use = alive[0].device_id
        return [
            {
                "deviceId": device.device_id,
                "name": device.name,
                "isLocal": True,
                "inUse": device.device_id == in_use,
            }
            for device in alive
        ]

    async def wait_switch(self, wait_s: float) -> str | None:
        """Kullanıcı bir tarayıcıda "Bu tarayıcıyı kullan"a basana dek bekle."""
        loop = asyncio.get_running_loop()
        if self._switch is None or self._switch.done():
            self._switch = loop.create_future()
        waiting = self._switch
        try:
            return await asyncio.wait_for(asyncio.shield(waiting), wait_s)
        except TimeoutError:
            return None
        finally:
            if self._switch is waiting:
                self._switch = None
                if not waiting.done():
                    waiting.cancel()

    def close(self) -> None:
        for device in self._devices.values():
            while not device.queue.empty():
                device.queue.get_nowait()
            device.queue.put_nowait({})
            device.last_seen = 0.0
        if self._switch is not None and not self._switch.done():
            self._switch.cancel()
        self._switch = None
