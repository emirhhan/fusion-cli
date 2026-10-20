"""Eşleşmiş cihaz kaydı: kalıcı, atomik yazılan, 0600 izinli dosya.

Cihaz sırrı imza doğrulaması için sunucuda durmak zorundadır; bu yüzden dosya
yalnız sahibine açık yazılır. Kayıtlar günlüğe ve olaylara asla düşmez.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.protocols import Clock
from .constants import DEVICE_SECRET_BYTES

#: Bir cihazın bağlandığı kanal.
CHANNEL_SIGNED = "signed"
CHANNEL_TELEGRAM = "telegram"


@dataclass(frozen=True, slots=True)
class Device:
    """Eşleşmiş bir uzak cihaz."""

    device_id: str
    name: str
    channel: str
    scopes: frozenset[str]
    secret_hex: str
    created_at: float
    revoked: bool = False
    screen_trusted: bool = False
    external_id: str = ""  # Telegram kullanıcı kimliği gibi kanal-içi kimlik

    @property
    def secret(self) -> bytes:
        return bytes.fromhex(self.secret_hex)

    def public_view(self) -> dict[str, object]:
        """Sır içermeyen görünüm (cihaz listesi için)."""
        return {
            "deviceId": self.device_id,
            "name": self.name,
            "channel": self.channel,
            "scopes": sorted(self.scopes),
            "createdAt": self.created_at,
            "revoked": self.revoked,
            "screenTrusted": self.screen_trusted,
        }


class DeviceRegistry:
    """Cihazları kalıcı tutar; iptal anında etkilidir."""

    def __init__(
        self,
        path: Path,
        clock: Clock,
        *,
        token_bytes: Callable[[int], bytes] = os.urandom,
    ) -> None:
        self._path = path
        self._clock = clock
        self._token_bytes = token_bytes
        self._devices: dict[str, Device] = self._load()

    def add(self, name: str, channel: str, scopes: frozenset[str], external_id: str = "") -> Device:
        device = Device(
            device_id="dev_" + self._token_bytes(9).hex(),
            name=name.strip()[:60] or "Adsız cihaz",
            channel=channel,
            scopes=scopes,
            secret_hex=self._token_bytes(DEVICE_SECRET_BYTES).hex(),
            created_at=self._clock.now(),
            external_id=external_id,
        )
        self._devices = {**self._devices, device.device_id: device}
        self._save()
        return device

    def get(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def active(self, device_id: str) -> Device | None:
        device = self._devices.get(device_id)
        return device if device is not None and not device.revoked else None

    def find_external(self, channel: str, external_id: str) -> Device | None:
        for device in self._devices.values():
            if (
                device.channel == channel
                and device.external_id == external_id
                and not device.revoked
            ):
                return device
        return None

    def revoke(self, device_id: str) -> bool:
        device = self._devices.get(device_id)
        if device is None or device.revoked:
            return False
        self._devices = {
            **self._devices,
            device_id: replace(device, revoked=True, screen_trusted=False),
        }
        self._save()
        return True

    def set_screen_trusted(self, device_id: str, trusted: bool) -> bool:
        """Yalnız etkin imzalı gözlemcinin açık ekran tercihini kalıcı tut."""
        device = self.active(device_id)
        if (
            device is None
            or device.channel != CHANNEL_SIGNED
            or "desktop.observe" not in device.scopes
        ):
            return False
        self._devices = {**self._devices, device_id: replace(device, screen_trusted=trusted)}
        self._save()
        return True

    def list_devices(self) -> list[Device]:
        return sorted(self._devices.values(), key=lambda item: item.created_at)

    def _load(self) -> dict[str, Device]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        devices: dict[str, Device] = {}
        for item in raw.get("devices", []) if isinstance(raw, dict) else []:
            try:
                device = Device(
                    device_id=item["deviceId"],
                    name=item["name"],
                    channel=item["channel"],
                    scopes=frozenset(item["scopes"]),
                    secret_hex=item["secret"],
                    created_at=float(item["createdAt"]),
                    revoked=bool(item.get("revoked", False)),
                    external_id=item.get("externalId", ""),
                    screen_trusted=item.get("screenTrusted") is True,
                )
            except (KeyError, TypeError, ValueError):
                continue
            devices[device.device_id] = device
        return devices

    def _save(self) -> None:
        payload = {
            "devices": [
                {
                    "deviceId": d.device_id,
                    "name": d.name,
                    "channel": d.channel,
                    "scopes": sorted(d.scopes),
                    "secret": d.secret_hex,
                    "createdAt": d.created_at,
                    "revoked": d.revoked,
                    "externalId": d.external_id,
                    "screenTrusted": d.screen_trusted,
                }
                for d in self._devices.values()
            ]
        }
        atomic_replace_text(self._path, json.dumps(payload, ensure_ascii=False))
        self._path.chmod(0o600)
