"""Tur bitişi: yan çağrılar sınırsız beklemez, kanıt satırı görünür (30 Ekim deneme).

Gerçek kullanım denemesinde (`fusion agent`, ana model `gemini_web`, yedek NVIDIA) bir
tur iş bittikten sonra 20 dakika boyunca hiçbir çıktı basmadan asılı kaldı. İz dosyası
son olayın arka plan model çağrısının (`ModelCallStarted ... background=true`) başlayıp
HİÇ bitmediğini gösteriyordu: tur sonu bağlam özeti (`compaction._summarize`) dış bir
süre sınırı olmadan web modelini bekliyordu.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from fusion_cli.core.events import StatusChanged
from fusion_cli.core.types import ModelResult
from fusion_cli.engines.agent import compaction
from fusion_cli.engines.agent import history as agent_history
from fusion_cli.engines.agent.loop import run_agent

from .fakes import make_config, model_result, tool_call
from .test_teacher_first import _setup


class _AsiliSaglayici:
    """Hiç cevap vermeyen web modeli: `complete` iptal edilene kadar bekler."""

    label = "asili"

    def __init__(self) -> None:
        self.cagri = 0
        self.iptal_edildi = False

    async def complete(self, request):
        del request
        self.cagri += 1
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.iptal_edildi = True
            raise
        return ModelResult(name="a", model="asili/a", text="özet", latency_ms=1)


async def test_ozet_cagrisi_asilirsa_sinirli_surede_bos_ozet_olur(monkeypatch) -> None:
    """Ölçüldü (30 Ekim): web modeli özet isteğine hiç dönmedi; `_summarize` sınırsızdı."""
    saglayici = _AsiliSaglayici()
    monkeypatch.setattr(compaction, "build_provider", lambda *a, **k: saglayici)
    config = make_config()
    config = replace(config, runtime=replace(config.runtime, request_timeout_s=0.05))

    ozet = await asyncio.wait_for(compaction._summarize("iz", config, None), timeout=1.0)

    assert ozet == ""
    assert saglayici.iptal_edildi


async def test_ozet_siniri_yapilandirilmis_istek_suresini_asmaz() -> None:
    config = make_config()
    config = replace(config, runtime=replace(config.runtime, request_timeout_s=600.0))

    assert compaction.summary_timeout_s(config) == compaction.SUMMARY_TIMEOUT_S
    assert compaction.SUMMARY_TIMEOUT_S <= 180.0


async def test_bitis_ogretmeni_dusup_ozet_asilsa_da_tur_kanitlarla_biter(
    monkeypatch, tmp_path
) -> None:
    """g2 senaryosu: bitiş öğretmen incelemesi hata verir + tur sonu özeti asılır."""
    (tmp_path / "src").mkdir()
    plan = model_result(
        '{"adimlar":["Dosyayı yaz"],"dosyalar":[],"riskler":[],"yapilamayanlar":[],"dogrulama":[]}'
    )
    basarisiz = ModelResult(
        name="o", model="sahte/o", text="", latency_ms=1, ok=False, error="web oturumu hatası"
    )
    deps, sink, teacher, _apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[plan, basarisiz, basarisiz],
        apprentice_answers=[
            model_result(
                tool_calls=(tool_call("write_file", path="src/app.py", content="x = 1\n"),)
            ),
            model_result("Dosya yazıldı."),
        ],
    )
    saglayici = _AsiliSaglayici()
    monkeypatch.setattr(compaction, "build_provider", lambda *a, **k: saglayici)
    monkeypatch.setattr(agent_history, "needs_compression", lambda *a, **k: True)
    monkeypatch.setattr(agent_history, "safe_cut", lambda messages: 4)
    monkeypatch.setattr(compaction, "SUMMARY_TIMEOUT_S", 0.05)

    sonuc = await asyncio.wait_for(run_agent("src/app.py dosyasını oluştur", deps), timeout=5.0)

    assert teacher.calls >= 2
    assert (tmp_path / "src" / "app.py").read_text(encoding="utf-8") == "x = 1\n"
    assert sonuc.final_text.strip()
    # Tur sonu özeti GERÇEKTEN denendi ve süre sınırında vazgeçildi (iptal edildi).
    assert saglayici.cagri == 1
    assert saglayici.iptal_edildi
    assert any(isinstance(e, StatusChanged) and "tek başıma" in e.message for e in sink.events)


async def test_bitis_ogretmeni_beklenmedik_istisna_atarsa_tur_biter(monkeypatch, tmp_path) -> None:
    (tmp_path / "src").mkdir()
    plan = model_result(
        '{"adimlar":["Dosyayı yaz"],"dosyalar":[],"riskler":[],"yapilamayanlar":[],"dogrulama":[]}'
    )
    deps, _sink, teacher, _apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[plan],
        apprentice_answers=[
            model_result(
                tool_calls=(tool_call("write_file", path="src/app.py", content="x = 1\n"),)
            ),
            model_result("Dosya yazıldı."),
        ],
    )
    gercek = teacher.complete
    cagrilar: list[int] = []

    async def _bitiste_patla(request):
        cagrilar.append(1)
        if len(cagrilar) > 1:
            raise RuntimeError("öğretmen oturumu çöktü")
        return await gercek(request)

    monkeypatch.setattr(teacher, "complete", _bitiste_patla)

    sonuc = await asyncio.wait_for(run_agent("src/app.py dosyasını oluştur", deps), timeout=5.0)

    assert len(cagrilar) >= 2
    assert (tmp_path / "src" / "app.py").is_file()
    assert sonuc.final_text.strip()
