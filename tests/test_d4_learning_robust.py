"""Ders çıkarımı: ayrıştırma, hata dayanıklılığı, maskeleme, yer tutucu (A2-09..A2-13, A2-41)."""

from __future__ import annotations

import pytest

from fusion_cli.core.errors import ConfigError, ProviderError
from fusion_cli.core.types import Message, ModelResult
from fusion_cli.engines.agent import learning

from .fakes import make_config

_DERS = '{"kind":"mistake","lesson":"res:// önekini kullanma"}'


def test_aciklamali_metin_icindeki_ilk_gecerli_dizi_alinir():
    metin = f"[Not] işte dersler:\n[{_DERS}]\nUmarım yardımcı olur [1]."
    assert [d.text for d in learning.parse_lessons(metin, "g")] == ["res:// önekini kullanma"]


def test_tek_nesne_dizi_olmadan_gelirse_alinir():
    assert len(learning.parse_lessons(f"Ders: {_DERS}", "g")) == 1


def test_gecersiz_metin_bos_doner():
    assert learning.parse_lessons("[bozuk", "g") == ()
    assert learning.parse_lessons("", "g") == ()


def test_gorevdeki_trace_yazisi_oturum_iziyle_degismez():
    sonuc = learning._fill_prompt("{trace} içeren görev", "GERÇEK İZ")
    assert "{trace} içeren görev" in sonuc and sonuc.count("GERÇEK İZ") == 1


@pytest.mark.parametrize("hata", [ConfigError("x"), ProviderError("y"), OSError("z")])
async def test_saglayici_hatasi_dersi_bos_doner_turu_dusurmez(monkeypatch, hata):
    def _kur(*args, **kwargs):
        raise hata

    monkeypatch.setattr(learning, "build_provider", _kur)
    mesajlar = [Message("user", "g"), Message("tool", "çıktı")]

    assert await learning.extract_lessons("g", mesajlar, config=make_config()) == ()


async def test_judge_a_giden_iz_maskelenir(monkeypatch):
    gorulen = []

    class _Saglayici:
        async def complete(self, request):
            gorulen.append(request.messages[0].content)
            return ModelResult(name="j", model="j", text="[]", latency_ms=1, ok=True)

    monkeypatch.setattr(learning, "build_provider", lambda *a, **k: _Saglayici())
    sir = "sk-" + "a1b2c3d4e5f6g7h8i9j0k1l2"
    mesajlar = [Message("user", f"anahtar {sir} kullan"), Message("tool", "tamam")]

    await learning.extract_lessons("g", mesajlar, config=make_config())

    assert gorulen and sir not in gorulen[0]
