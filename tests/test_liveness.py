"""Sessiz model çağrısında sunucu canlılık yoklaması (bkz. `engines/agent/liveness`)."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.core.events import StatusChanged
from fusion_cli.core.types import ModelSpec, StreamDone, TextChunk
from fusion_cli.engines.agent import liveness
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.loop import run_agent

from .fakes import RecordingSink, model_result
from .test_agent_loop import _deps, _kur


@pytest.fixture(autouse=True)
def _hizli(monkeypatch):
    monkeypatch.setattr(liveness, "CHECK_AFTER_S", 0.05)
    monkeypatch.setattr(liveness, "RECHECK_S", 0.05)

    async def _bekleme(_s: float) -> None:
        return None

    monkeypatch.setattr(agent_loop, "_retry_sleep", _bekleme)


def _yoklama(*cevaplar):
    kalan = list(cevaplar)
    sayac = {"n": 0}

    async def _ping():
        sayac["n"] += 1
        return kalan.pop(0) if kalan else None

    return _ping, sayac


async def test_sessizlikte_saglıksiz_yoklama_nedeni_doner():
    ping, sayac = _yoklama("Service temporarily overloaded")

    neden = await asyncio.wait_for(liveness.watch(lambda: 0, ping), 2)

    assert neden == "Service temporarily overloaded" and sayac["n"] == 1


async def test_saglikli_sunucu_yeniden_yoklanir_sonra_cokerse_yakalanir():
    ping, sayac = _yoklama(None, None, "yoklamaya 30 sn içinde cevap yok")

    neden = await asyncio.wait_for(liveness.watch(lambda: 0, ping), 2)

    assert "cevap yok" in neden and sayac["n"] == 3


async def test_parca_gelen_akista_yoklama_yapilmaz():
    ping, sayac = _yoklama("olmamalı")

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(liveness.watch(lambda: 5, ping), 0.3)

    assert sayac["n"] == 0


def test_web_oturumu_modelleri_yoklanmaz():
    assert liveness.is_api_model(ModelSpec(name="a", model="nvidia_nim/nvidia/x"))
    assert not liveness.is_api_model(ModelSpec(name="b", model="gemini_web/main/auto"))


class _AsiliSaglayici:
    """İlk çağrıda hiç parça göndermeden asılı kalır; sonrakilerde cevap verir."""

    label = "asili"

    def __init__(self) -> None:
        self.cagri = 0

    async def complete(self, request):  # pragma: no cover - akış kullanılır
        raise AssertionError

    async def stream(self, request):
        self.cagri += 1
        if self.cagri == 1:
            await asyncio.sleep(3600)
        yield TextChunk("Tamamlandı: istenen iş yapıldı ve doğrulandı.")
        yield StreamDone(model_result("Tamamlandı: istenen iş yapıldı ve doğrulandı."))


async def test_saglıksiz_sunucuda_asili_cagri_kesilir_ve_yeniden_denenir(monkeypatch, tmp_path):
    sink = RecordingSink()
    saglayici = _kur(monkeypatch, _AsiliSaglayici())
    ping, _ = _yoklama("Service temporarily overloaded")
    monkeypatch.setattr(liveness, "ping_for", lambda spec: ping)

    sonuc = await asyncio.wait_for(
        run_agent("görev", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3})), 10
    )

    durumlar = [e.message for e in sink.events if isinstance(e, StatusChanged)]
    assert sonuc.ok and saglayici.cagri == 2
    assert any("sunucu sağlıksız (Service temporarily overloaded)" in d for d in durumlar)


async def test_saglikli_sunucuda_sessiz_cagri_beklenir(monkeypatch, tmp_path):
    """Sağlıklı sunucu: sessiz ama çalışan çağrı kesilmez (165 sn düşünme ölçüldü)."""

    class _YavasSaglayici(_AsiliSaglayici):
        async def stream(self, request):
            self.cagri += 1
            await asyncio.sleep(0.4)
            yield StreamDone(model_result("Tamamlandı: istenen iş yapıldı ve doğrulandı."))

    sink = RecordingSink()
    saglayici = _kur(monkeypatch, _YavasSaglayici())
    ping, sayac = _yoklama()
    monkeypatch.setattr(liveness, "ping_for", lambda spec: ping)

    sonuc = await run_agent("görev", _deps(tmp_path, sink))

    assert sonuc.ok and saglayici.cagri == 1 and sayac["n"] >= 1
