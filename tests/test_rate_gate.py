"""Paylaşılan hız defteri ve hız kapısı: 429'a düşmeden yavaşlatma, sekmeler arası soğuma."""

from __future__ import annotations

import asyncio
import multiprocessing
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.core.rate_control import RateControl
from fusion_cli.core.turn_deadline import TurnDeadline
from fusion_cli.core.types import CompletionRequest, Message, ModelResult, StreamDone
from fusion_cli.providers.key_pool import ledger_key_pool
from fusion_cli.providers.rate_gate import GATE_ERROR_PREFIX, RateGatedProvider, gate, keyed_label
from fusion_cli.providers.rate_ledger import SqliteRateLedger
from tests.fakes import FakeProvider


class _Clock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.value = now

    def monotonic(self) -> float:
        return self.value

    def now(self) -> float:
        return self.value


class _Sleeper:
    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self.slept: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.clock.value += seconds


_REQUEST = CompletionRequest(
    messages=(Message("user", "selam"),), temperature=0.0, max_tokens=8, timeout_s=5.0
)


def _ledger(tmp_path: Path, clock: _Clock) -> SqliteRateLedger:
    return SqliteRateLedger(tmp_path / "defter.sqlite3", clock=clock)


def _gate(inner, ledger, clock, *, per_minute=None, pace=3.0, cooldown=60.0):
    return RateGatedProvider(
        inner,
        ledger=ledger,
        key="nvidia_nim/model",
        per_minute=per_minute,
        pace_max_wait_s=pace,
        cooldown_s=cooldown,
        clock=clock,
        sleeper=_Sleeper(clock),
    )


def test_defter_kovasi_dolu_baslar_ve_dakikalik_hakkı_asmaz(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)

    waits = [ledger.take_token("m", 40) for _ in range(41)]

    assert waits[:40] == [0.0] * 40
    assert waits[40] > 0.0


def test_defter_kovasi_zamanla_dolar(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    for _ in range(40):
        ledger.take_token("m", 40)

    clock.value += 1.5

    assert ledger.take_token("m", 40) == 0.0


def test_paced_bucket_does_not_rewind_on_wall_clock_change(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    assert ledger.take_token("m", 5, burst=1) == 0
    clock.value -= 12
    assert ledger.take_token("m", 5, burst=1) == 12
    clock.value += 12
    assert ledger.take_token("m", 5, burst=1) == 12


@pytest.mark.parametrize("warm_bucket", [False, True])
async def test_model_rate_spaces_calls_across_processes(tmp_path, warm_bucket):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    name = "nvidia_nim/model"
    if warm_bucket:
        assert ledger.take_token(name, 40) == 0.0
    request = replace(_REQUEST, timeout_s=20)
    model = FakeProvider(name, chunks=("tamam",))

    def make_gate(shared):
        return gate(
            model,
            RateControl(shared, {"nvidia_nim": 40, name: 5}, 3.0, 60.0),
            key=name,
            provider_id="nvidia_nim",
            clock=clock,
            sleeper=_Sleeper(clock),
        )

    assert (await make_gate(ledger).complete(request)).ok
    assert (await make_gate(_ledger(tmp_path, clock)).complete(request)).ok
    assert clock.value == 1012.0


async def test_model_pacing_is_shared_by_keys_and_respects_stricter_provider_rate(tmp_path):
    clock = _Clock()
    name = "nvidia_nim/model"
    rate = RateControl(_ledger(tmp_path, clock), {"nvidia_nim": 2, name: 5}, 3.0, 60.0)
    request = replace(_REQUEST, timeout_s=40)
    for api_key in ("a", "b"):
        wrapped = gate(
            FakeProvider(name, chunks=("tamam",)),
            rate,
            key=keyed_label(name, api_key),
            provider_id="nvidia_nim",
            clock=clock,
            sleeper=_Sleeper(clock),
        )
        assert (await wrapped.complete(request)).ok
    assert clock.value == 1030


async def test_smoothed_gate_rechecks_deadline_after_final_cooldown_read(tmp_path):
    clock = _Clock()

    class SlowLedger(SqliteRateLedger):
        reads = 0

        def cooled_until(self, key):
            self.reads += 1
            if self.reads == 3:
                clock.value += 2
            return super().cooled_until(key)

    name = "nvidia_nim/model"
    model = FakeProvider(name, chunks=("tamam",))
    wrapped = gate(
        model,
        RateControl(SlowLedger(tmp_path / "slow.sqlite", clock=clock), {name: 5}),
        key=name,
        provider_id="nvidia_nim",
        clock=clock,
        sleeper=_Sleeper(clock),
    )
    result = await wrapped.complete(
        replace(_REQUEST, rate_retry_deadline=TurnDeadline(clock, 1001))
    )
    assert result.is_rate_limited
    assert not model.started


@pytest.mark.parametrize("deadline", ["request", "opening", "turn"])
async def test_smoothed_gate_does_not_sleep_past_available_time(tmp_path, deadline):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    name = "nvidia_nim/model"
    first = FakeProvider(name, chunks=("tamam",))
    second = FakeProvider(name, chunks=("tamam",))
    rate = RateControl(ledger, {name: 5}, 3.0, 60.0)

    def wrap(model):
        return gate(
            model, rate, key=name, provider_id="nvidia_nim", clock=clock, sleeper=_Sleeper(clock)
        )

    assert (await wrap(first).complete(_REQUEST)).ok
    request = _REQUEST
    if deadline == "opening":
        request = replace(
            request,
            timeout_s=20,
            rate_retry_opening_at=asyncio.get_running_loop().time() + 5,
        )
    elif deadline == "turn":
        request = replace(request, timeout_s=20, rate_retry_deadline=TurnDeadline(clock, 1005))
    result = await wrap(second).complete(request)
    assert result.is_rate_limited and result.retry_after_s == 12
    assert clock.value == 1000.0 and not second.started


def test_defter_soguma_daha_gec_kaydi_kisaltmaz(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)

    ledger.cool("m", 1_100.0)
    ledger.cool("m", 1_050.0)

    assert ledger.cooled_until("m") == 1_100.0
    clock.value = 1_200.0
    assert ledger.cooled_until("m") == 0.0


def test_defter_bozuk_dosyada_turu_dusurmez(tmp_path):
    bozuk = tmp_path / "defter.sqlite3"
    bozuk.write_bytes(b"bu bir sqlite dosyasi degil" * 100)
    ledger = SqliteRateLedger(bozuk, clock=_Clock())

    assert ledger.cooled_until("m") == 0.0
    assert ledger.take_token("m", 40) == 0.0
    ledger.cool("m", 2_000.0)
    assert ledger.next_index("sayac") == 0


async def test_kapi_429_alinca_modeli_paylasilan_defterde_sogutur(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    kota = FakeProvider("nvidia_nim/model", ok=False, error="RateLimitError: 429")
    birinci_sekme = _gate(kota, ledger, clock)
    ikinci_sekme_modeli = FakeProvider("nvidia_nim/model", chunks=("cevap",))
    ikinci_sekme = _gate(ikinci_sekme_modeli, ledger, clock)

    await birinci_sekme.complete(_REQUEST)
    result = await ikinci_sekme.complete(_REQUEST)

    assert result.is_rate_limited
    assert result.error is not None and result.error.startswith(GATE_ERROR_PREFIX)
    assert not ikinci_sekme_modeli.started


async def test_kapi_kisa_beklemeyle_hak_doldurup_cagriyi_yapar(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    for _ in range(40):
        ledger.take_token("nvidia_nim/model", 40)
    model = FakeProvider("nvidia_nim/model", chunks=("tamam",))
    kapi = _gate(model, ledger, clock, per_minute=40)

    result = await kapi.complete(_REQUEST)

    assert result.ok
    assert model.started


async def test_kapi_uzun_beklemede_cagri_yapmadan_yedege_birakir(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    for _ in range(40):
        ledger.take_token("nvidia_nim/model", 40)
    model = FakeProvider("nvidia_nim/model", chunks=("tamam",))
    kapi = _gate(model, ledger, clock, per_minute=40, pace=1.0)

    result = await kapi.complete(_REQUEST)

    assert result.is_rate_limited
    assert not model.started


async def test_kapi_akista_da_429u_paylasir(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    kota = FakeProvider("nvidia_nim/model", ok=False, error="429 Too Many Requests")
    kapi = _gate(kota, ledger, clock)

    items = [item async for item in kapi.stream(_REQUEST)]

    assert isinstance(items[-1], StreamDone)
    assert ledger.cooled_until("nvidia_nim/model") == clock.value + 60.0


async def test_kapi_sinirsiz_saglayicida_kovaya_dokunmaz(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    model = FakeProvider("openrouter/model", chunks=("x",))
    kapi = _gate(model, ledger, clock, per_minute=None)

    for _ in range(100):
        result: ModelResult = await kapi.complete(_REQUEST)
        assert result.ok


def test_anahtar_etiketi_anahtarin_kendisini_tasimaz():
    etiket = keyed_label("nvidia_nim/model", "nvapi-gizli-anahtar")

    assert "gizli" not in etiket
    assert etiket.startswith("nvidia_nim/model#")


def test_defterli_havuz_sirayi_surecler_arasi_dagitir(tmp_path, monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "a,b,c")
    rate = RateControl(ledger=_ledger(tmp_path, _Clock()), cooldown_s=60.0)

    ilk = ledger_key_pool("NVIDIA_NIM_API_KEY", rate).pick()
    ikinci = ledger_key_pool("NVIDIA_NIM_API_KEY", rate).pick()

    assert {ilk, ikinci} <= {"a", "b", "c"}
    assert ilk != ikinci


def _baska_surecte_hak_al(yol: str, adet: int, kuyruk) -> None:
    ledger = SqliteRateLedger(Path(yol))
    kuyruk.put([ledger.take_token("ortak", 40) for _ in range(adet)])


def test_defter_iki_surec_arasinda_tek_kova_paylasir(tmp_path):
    yol = str(tmp_path / "defter.sqlite3")
    baglam = multiprocessing.get_context("spawn")
    kuyruk = baglam.Queue()
    surecler = [
        baglam.Process(target=_baska_surecte_hak_al, args=(yol, 30, kuyruk)) for _ in range(2)
    ]
    for surec in surecler:
        surec.start()
    sonuclar = [kuyruk.get(timeout=60) for _ in surecler]
    for surec in surecler:
        surec.join(timeout=60)

    alinan = sum(1 for bekleme in sonuclar[0] + sonuclar[1] if bekleme == 0.0)
    # 60 istekten yalnız kovanın kapasitesi (40, çok kısa sürede dolum payı ile) geçer.
    assert 40 <= alinan <= 42


async def test_fabrika_429_alan_anahtari_atlayip_digerine_gecer(tmp_path, monkeypatch):
    from fusion_cli.core.health import HealthRegistry
    from fusion_cli.core.model_capability import ModelCapability
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.providers import factory

    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "dolu,bos")
    yapraklar: list[tuple[str, FakeProvider]] = []

    class _Yaprak(FakeProvider):
        def __init__(self, model, *, role, clock=None, api_key=None, capability=None):
            assert isinstance(capability, ModelCapability)
            assert not capability.reasoning_efforts_verified
            yapraklar.append((api_key or "", self))
            if api_key == "dolu":
                super().__init__(model, ok=False, error="RateLimitError: 429")
            else:
                super().__init__(model, chunks=("cevap",))

    monkeypatch.setattr(factory, "LiteLlmProvider", _Yaprak)
    monkeypatch.setattr(factory, "configure_litellm", lambda: None)
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    health = HealthRegistry(
        failure_threshold=3,
        cooldown_s=60.0,
        alpha=0.3,
        rate_control=RateControl(ledger=ledger, cooldown_s=60.0),
    )
    spec = ModelSpec(name="agent", model="nvidia_nim/deneme")

    for _ in range(3):
        provider = factory.build_provider(spec, publisher=None, retry_delays_s=(), health=health)
        result = await provider.complete(_REQUEST)
        assert result.ok

    # "dolu" anahtar bir kez 429 verdi; sonra defterde soğumada kaldı ve çağrılmadı.
    dolu_cagrilari = [yaprak for anahtar, yaprak in yapraklar if anahtar == "dolu"]
    assert sum(1 for yaprak in dolu_cagrilari if yaprak.started) == 1
    assert ledger.cooled_until(keyed_label("nvidia_nim/deneme", "dolu")) > 0


def test_defter_dizini_yoksa_da_ilk_kullanimda_kurulur(tmp_path):
    """Ölçüldü (30 Ekim): `sqlite3.connect` dizin oluşturulmadan ÖNCE çalışıyordu; dizin
    yoksa `OperationalError` yakalanıp 'hak alındı' denir, hız kapısı sessizce
    çalışmazdı. Tablo sonradan silinirse her işlem uyarı üretirdi (P1-37)."""
    from fusion_cli.providers.rate_ledger import SqliteRateLedger

    yol = tmp_path / "yok" / "daha-yok" / "rate.sqlite"
    defter = SqliteRateLedger(yol)

    defter.cool("k", 9_999_999_999.0)
    assert defter.cooled_until("k") == 9_999_999_999.0

    yol.unlink()  # dosya sonradan silinirse defter yeniden kurulur
    defter.cool("k2", 9_999_999_999.0)
    assert defter.cooled_until("k2") == 9_999_999_999.0


class _Sirali:
    """Sırayla verilen sonuçları döndüren tek modelli sağlayıcı; çağrıları sayar."""

    label = "nvidia_nim/model"

    def __init__(self, *sonuclar: ModelResult) -> None:
        self._sonuclar = list(sonuclar)
        self.cagri_sayisi = 0

    async def complete(self, request: CompletionRequest) -> ModelResult:
        self.cagri_sayisi += 1
        return self._sonuclar[min(self.cagri_sayisi - 1, len(self._sonuclar) - 1)]

    async def stream(self, request: CompletionRequest):
        yield StreamDone(await self.complete(request))


def _sonuc(*, ok: bool, error: str | None = None) -> ModelResult:
    return ModelResult(
        name="r", model="nvidia_nim/model", text="tamam" if ok else "", latency_ms=1, ok=ok,
        error=error,
    )  # fmt: skip


@pytest.mark.parametrize("hint", [0.0, 7.0, 90.0])
async def test_rate_gate_records_provider_retry_after_for_other_calls(tmp_path, hint):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    result = replace(_sonuc(ok=False, error="429 Too Many Requests"), retry_after_s=hint)
    first = _gate(_Sirali(result), ledger, clock)
    assert (await first.complete(_REQUEST)).retry_after_s == hint
    next_leaf = _Sirali(_sonuc(ok=True))
    second = await _gate(next_leaf, ledger, clock).complete(_REQUEST)
    assert next_leaf.cagri_sayisi == (1 if hint == 0 else 0)
    assert second.retry_after_s == (hint or None)


async def test_kapi_soguma_blogu_kalan_sureyi_retry_after_olarak_tasir(tmp_path):
    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    ledger.cool("nvidia_nim/model", clock.now() + 42.0)
    kapi = _gate(FakeProvider("nvidia_nim/model", chunks=("x",)), ledger, clock)

    result = await kapi.complete(_REQUEST)

    assert result.is_rate_limited
    assert result.retry_after_s == 42.0


async def test_kapi_yedeksiz_modelde_retry_soguma_bitene_kadar_bekler_sonra_dener(tmp_path):
    """P1-07. Ölçüldü (30 Ekim): retry kapının DIŞINDA; ilk 429 sonrası 1,5/4 sn'lik
    gecikmeler 60 sn'lik soğumanın içinde kalıyor, kapı her seferinde anında "soğumada"
    döndürüyor ve hiç gerçek yeniden deneme yapılmıyordu."""
    from fusion_cli.providers.retrying import RetryingProvider

    clock = _Clock()
    ledger = _ledger(tmp_path, clock)
    sleeper = _Sleeper(clock)
    model = _Sirali(
        _sonuc(ok=False, error="RateLimitError: 429"),
        _sonuc(ok=True),
    )
    kapi = RateGatedProvider(
        model,
        ledger=ledger,
        key="nvidia_nim/model",
        per_minute=None,
        pace_max_wait_s=3.0,
        cooldown_s=60.0,
        clock=clock,
        sleeper=sleeper,
    )
    retry = RetryingProvider(kapi, delays_s=(1.5, 4.0), sleeper=sleeper)

    result = await retry.complete(_REQUEST)

    assert result.ok
    assert model.cagri_sayisi == 2  # gerçek ikinci çağrı yapıldı
    assert sleeper.slept == [60.0]  # max(1,5; kalan soğuma)
