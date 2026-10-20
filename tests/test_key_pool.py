"""Çok-hesap anahtar havuzu — toplama, rotasyon, cooldown, döndüren sağlayıcı."""

from __future__ import annotations

from fusion_cli.config.key_pool import collect_keys
from fusion_cli.providers.key_pool import KeyPool, KeyPoolRegistry
from fusion_cli.providers.key_rotation import KeyRotatingProvider

from .fakes import request


class _Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def now(self):
        return self.t


# --- collect_keys ---------------------------------------------------------- #


def test_tek_anahtar():
    assert collect_keys("OPENROUTER_API_KEY", {"OPENROUTER_API_KEY": "k1"}) == ("k1",)


def test_numarali_sonekler():
    env = {"K": "k1", "K_2": "k2", "K_3": "k3"}
    assert collect_keys("K", env) == ("k1", "k2", "k3")


def test_virgullu():
    assert collect_keys("K", {"K": "k1, k2 ,k3"}) == ("k1", "k2", "k3")


def test_bos_ve_tekrar_elenir():
    env = {"K": "k1,,k1", "K_2": "  ", "K_3": "k2"}
    assert collect_keys("K", env) == ("k1", "k2")


def test_hic_anahtar_yok():
    assert collect_keys("K", {}) == ()


# --- KeyPool --------------------------------------------------------------- #


def test_round_robin_doner():
    pool = KeyPool(("a", "b", "c"), cooldown_s=60.0, clock=_Clock())
    assert [pool.pick() for _ in range(4)] == ["a", "b", "c", "a"]


def test_hiz_siniri_anahtari_atlar():
    clock = _Clock()
    pool = KeyPool(("a", "b"), cooldown_s=60.0, clock=clock)
    pool.mark_rate_limited("a")
    # 'a' cooldown'da → yalnız 'b' seçilir.
    assert pool.pick() == "b"
    assert pool.pick() == "b"


def test_cooldown_dolunca_geri_gelir():
    clock = _Clock()
    pool = KeyPool(("a", "b"), cooldown_s=60.0, clock=clock)
    pool.mark_rate_limited("a")
    clock.t = 60.0
    assert "a" in {pool.pick(), pool.pick()}


def test_hepsi_cooldownda_none():
    pool = KeyPool(("a",), cooldown_s=60.0, clock=_Clock())
    pool.mark_rate_limited("a")
    assert pool.pick() is None
    assert pool.any_key() == "a"


def test_registry_ayni_env_ayni_havuz():
    reg = KeyPoolRegistry({"K": "k1,k2"}, cooldown_s=60.0, clock=_Clock())
    assert reg.for_env("K") is reg.for_env("K")
    assert reg.for_env("K").size == 2


# --- KeyRotatingProvider --------------------------------------------------- #


class _KeyProvider:
    """Belirli anahtarlarda 429 döndüren sahte sağlayıcı."""

    def __init__(self, key, bad_keys):
        self._key = key
        self._bad = bad_keys
        self.started = False

    @property
    def label(self):
        return "m"

    async def complete(self, req):
        from fusion_cli.core.types import ModelResult

        self.started = True
        if self._key in self._bad:
            return ModelResult(
                name="m", model="m", text="", latency_ms=1, ok=False, error="429 rate limit"
            )
        return ModelResult(name="m", model="m", text=f"cevap[{self._key}]", latency_ms=1, ok=True)


async def test_rotasyon_429da_sonraki_anahtara_gecer():
    pool = KeyPool(("bad", "good"), cooldown_s=60.0, clock=_Clock())
    yapilan = []

    def factory(key):
        yapilan.append(key)
        return _KeyProvider(key, bad_keys={"bad"})

    rot = KeyRotatingProvider(factory, pool, label="m")
    result = await rot.complete(request())
    assert result.ok is True
    assert "good" in result.text
    assert "bad" in yapilan and "good" in yapilan  # ikisi de denendi


async def test_iyi_anahtar_hemen_doner():
    pool = KeyPool(("good", "good2"), cooldown_s=60.0, clock=_Clock())
    rot = KeyRotatingProvider(lambda key: _KeyProvider(key, bad_keys=set()), pool, label="m")
    result = await rot.complete(request())
    assert result.ok is True
