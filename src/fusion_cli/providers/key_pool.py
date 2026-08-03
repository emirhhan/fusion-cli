"""Anahtar havuzu — bir sağlayıcının anahtarları arasında adil dönüşüm.

Bir sağlayıcının birden çok anahtarı varsa istekler sırayla dağıtılır (round-robin);
bir anahtar hız sınırına (429) takılınca CD (cooldown) süresi boyunca ATLANIR ve yük
öteki anahtarlara biner. Böylece birkaç ücretsiz hesap tek büyük kotaymış gibi çalışır.

Durum tur-ötesidir ve enjekte edilir (modül-global değil; zaman `Clock`'tan). Sağlık
(circuit breaker) MODEL bazında, bu havuz ise ANAHTAR bazında çalışır — ikisi ayrıdır.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..config.key_pool import collect_keys
from ..core.clock import SystemClock
from ..core.protocols import Clock


class KeyPool:
    """Tek bir sağlayıcının anahtar havuzu (rotasyon + hız-sınırı cooldown'ı)."""

    def __init__(
        self, keys: Sequence[str], *, cooldown_s: float, clock: Clock | None = None
    ) -> None:
        self._keys = tuple(keys)
        self._cooldown_s = cooldown_s
        self._clock = clock or SystemClock()
        self._cooled_until: dict[str, float] = {}
        self._rotation = 0

    @property
    def size(self) -> int:
        return len(self._keys)

    def _available(self) -> tuple[str, ...]:
        now = self._clock.monotonic()
        return tuple(key for key in self._keys if self._cooled_until.get(key, 0.0) <= now)

    def pick(self) -> str | None:
        """Sıradaki KULLANILABİLİR anahtarı ver (round-robin). Hepsi cooldown'daysa None."""
        available = self._available()
        if not available:
            return None
        key = available[self._rotation % len(available)]
        self._rotation += 1
        return key

    def mark_rate_limited(self, key: str) -> None:
        """Anahtarı hız sınırı yüzünden bir süre kenara al."""
        self._cooled_until[key] = self._clock.monotonic() + self._cooldown_s

    def cooled_count(self) -> int:
        """Şu an cooldown'da olan anahtar sayısı (panel/teşhis için)."""
        return self.size - len(self._available())

    def any_key(self) -> str | None:
        """İlk anahtar (hepsi cooldown'daysa son çare için). Havuz boşsa None."""
        return self._keys[0] if self._keys else None


class KeyPoolRegistry:
    """Ortam değişkeni adı → `KeyPool`. Oturum boyunca tek örnek, enjekte edilir."""

    def __init__(
        self, environ: Mapping[str, str], *, cooldown_s: float, clock: Clock | None = None
    ) -> None:
        self._environ = environ
        self._cooldown_s = cooldown_s
        self._clock = clock or SystemClock()
        self._pools: dict[str, KeyPool] = {}

    def for_env(self, env_name: str) -> KeyPool:
        """Bir sağlayıcının anahtar havuzunu getir (tembel, ortamdan toplanır)."""
        pool = self._pools.get(env_name)
        if pool is None:
            pool = KeyPool(
                collect_keys(env_name, self._environ),
                cooldown_s=self._cooldown_s,
                clock=self._clock,
            )
            self._pools[env_name] = pool
        return pool
