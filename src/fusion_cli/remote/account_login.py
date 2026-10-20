"""Fusion hesabıyla cihaz kaydı: eşleştirme kodu yerine kimlik + parola.

Yalnız güvenilir tünel ya da TLS bağlamasında açılır. Parola yalnız doğrulanır: loglanmaz,
saklanmaz. Başarılı girişte proje okuma, ajan çalıştırma/iptal ve ekran izleme isteği
verilir. Ekran görüntüsü her oturumda masaüstü onayından sonra açılır; kontrol ve yazma
yetkileri bu yoldan verilmez.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from .devices import CHANNEL_SIGNED, Device, DeviceRegistry
from .rate_limit import FailureLimiter
from .scopes import DEFAULT_SCOPES, Scope

IDENTIFIER_MAX = 200
PASSWORD_MAX = 1024

#: Ekran oturumu ayrıca masaüstünde onaylanır; bu kapsam yalnız istek açar.
ACCOUNT_SCOPES = DEFAULT_SCOPES | {Scope.DESKTOP_OBSERVE.value}


class LoginError(Exception):
    """Kullanıcıya gösterilebilir giriş hatası; durum kodu HTTP için."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class AccountLogin:
    def __init__(
        self,
        *,
        authenticate: Callable[[str, str], bool],
        registry: DeviceRegistry,
        limiter: FailureLimiter,
    ) -> None:
        self._authenticate = authenticate
        self._registry = registry
        self._limiter = limiter

    async def login(self, client: str, identifier: str, password: str, device_name: str) -> Device:
        """Doğrulanırsa ekran onayı isteyebilen cihaz; aksi halde `LoginError`."""
        if not identifier.strip() or not password:
            raise LoginError(400, "gecersiz_istek", "Kullanıcı adı ve parola gerekli.")
        if len(identifier) > IDENTIFIER_MAX or len(password) > PASSWORD_MAX:
            raise LoginError(400, "gecersiz_istek", "Girdi çok uzun.")
        keys = (f"login:{client}", f"login-id:{identifier.strip().casefold()}")
        if any(self._limiter.is_locked(key) for key in keys):
            raise LoginError(429, "cok_deneme", "Çok fazla deneme; biraz bekle.")
        ok = await asyncio.to_thread(self._authenticate, identifier.strip(), password)
        if not ok:
            for key in keys:
                self._limiter.record_failure(key)
            raise LoginError(401, "kimlik_hatali", "Kullanıcı adı veya parola hatalı.")
        for key in keys:
            self._limiter.record_success(key)
        return self._registry.add(device_name, CHANNEL_SIGNED, ACCOUNT_SCOPES)
