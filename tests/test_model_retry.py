"""Tur düzeyi yeniden deneme: geçici model hatası turu bitirmez.

Kaynak: Claude Code belgesi (code.claude.com/docs/en/errors) — geçici hatalar
(429 hız sınırı, 5xx, zaman aşımı) üstel geri çekilmeyle yeniden denenir, bekleme
kullanıcıya geri sayımla gösterilir; kalıcı hata denenmez.
Ölçüldü (28 Eylül): 28 dakikalık iş NIM'in 429 hatasıyla ham istisna metniyle bitti.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.events import StatusChanged
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.loop import retry_delay_s, run_agent

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_agent_loop import _deps, _kur

HIZ_SINIRI = "RateLimitError: Nvidia_nimException - Error code: 429 - Too Many Requests"


@pytest.fixture
def sink():
    return RecordingSink()


@pytest.fixture
def beklemeler(monkeypatch):
    kayit: list[float] = []

    async def _bekle(delay_s: float) -> None:
        kayit.append(delay_s)

    monkeypatch.setattr(agent_loop, "_retry_sleep", _bekle)
    return kayit


def test_bekleme_ustel_artar_ve_tavanda_durur():
    assert [retry_delay_s(n) for n in range(7)] == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]


async def test_hiz_sinirinda_beklenip_ayni_cagri_yeniden_denenir(
    monkeypatch, tmp_path, sink, beklemeler
):
    saglayici = ScriptedProvider(
        [
            model_result(ok=False, error=HIZ_SINIRI),
            model_result(ok=False, error=HIZ_SINIRI),
            model_result("Tamamlandı: istenen iş yapıldı ve doğrulandı."),
        ]
    )
    _kur(monkeypatch, saglayici)

    sonuc = await run_agent("görev", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3}))

    assert sonuc.ok
    assert sonuc.final_text.startswith("Tamamlandı")
    assert beklemeler == [2.0, 4.0]
    durumlar = [e.message for e in sink.events if isinstance(e, StatusChanged)]
    assert any("hız sınırına takıldı" in d and "deneme 1/3" in d for d in durumlar)


async def test_kalici_hata_yeniden_denenmez(monkeypatch, tmp_path, sink, beklemeler):
    _kur(
        monkeypatch,
        ScriptedProvider([model_result(ok=False, error="401 Unauthorized: invalid API key")]),
    )

    sonuc = await run_agent("görev", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3}))

    assert not sonuc.ok
    assert beklemeler == []
    assert "Model kullanılamıyor" in sonuc.final_text


async def test_denemeler_bitince_ham_istisna_yerine_turkce_aciklama(
    monkeypatch, tmp_path, sink, beklemeler
):
    _kur(
        monkeypatch,
        ScriptedProvider([model_result(ok=False, error=HIZ_SINIRI) for _ in range(5)]),
    )

    sonuc = await run_agent("görev", _deps(tmp_path, sink, runtime={"model_retry_attempts": 2}))

    assert not sonuc.ok
    assert len(beklemeler) == 2
    assert "RateLimitError" not in sonuc.final_text
    assert "hız sınırına takıldı" in sonuc.final_text
    assert "devam et" in sonuc.final_text
    assert sonuc.model_error == HIZ_SINIRI


async def test_sure_sinirinda_bitmeyen_cagridan_sonra_modele_kisa_adim_notu_gider(
    monkeypatch, tmp_path, sink, beklemeler
):
    """Ölçüldü (2 Ekim 2026, NIM Nemotron 3 Ultra): tema dosyası yazan çağrı 600 sn
    sınırını iki kez aştı; aynı istek aynen yinelendiği için sonuç değişmedi."""
    gorulen: list[list[str]] = []
    cagri = {"n": 0}

    async def _model(messages, deps, registry, allowed_tools, **_kwargs):
        cagri["n"] += 1
        gorulen.append([m.content for m in messages if m.harness_note])
        if cagri["n"] == 1:
            raise TimeoutError
        return model_result("Tamamlandı: istenen iş yapıldı ve doğrulandı.")

    monkeypatch.setattr(agent_loop, "_call_model", _model)

    sonuc = await run_agent("görev", _deps(tmp_path, sink, runtime={"model_retry_attempts": 3}))

    assert sonuc.ok and cagri["n"] == 2
    assert agent_loop.SHORTER_AFTER_TIMEOUT_NOTE not in gorulen[0]
    assert gorulen[1].count(agent_loop.SHORTER_AFTER_TIMEOUT_NOTE) == 1
