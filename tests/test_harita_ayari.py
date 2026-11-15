"""Depo haritası ayarı ve ölçüm izi (yol haritası 8. adım).

`runtime.repo_map_chars` bütçeyi belirler (0 = kapalı), modelin penceresi küçükse harita
küçülür; kök turda `RepoMapBuilt` olayı karakter/dosya/süre izini bırakır.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.events import RepoMapBuilt
from fusion_cli.engines.agent.loop import run_agent

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_agent_loop import _deps, _kur


def _ana_mesajlar(saglayici, sira):
    return saglayici.seen_messages[sira]


async def test_kok_tur_harita_olcum_izini_olay_olarak_yazar_ve_butce_ayardan_gelir(
    monkeypatch, tmp_path
):
    (tmp_path / "a.py").write_text("def a(): ...\n", "utf-8")
    (tmp_path / "b.py").write_text("from a import a\ndef b(): ...\n", "utf-8")
    sink = RecordingSink()
    _kur(monkeypatch, ScriptedProvider([model_result("bitti")]))

    await run_agent("a.py dosyasını incele", _deps(tmp_path, sink, runtime={"repo_map_chars": 40}))

    olay = next(e for e in sink.events if isinstance(e, RepoMapBuilt))
    assert olay.budget_chars <= 40 and olay.chars <= 40
    assert olay.files == 2 and olay.symbols == 2 and olay.edges == 1


async def test_harita_ayarla_kapatilabilir(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def a(): ...\n", "utf-8")
    sink = RecordingSink()
    saglayici = _kur(monkeypatch, ScriptedProvider([model_result("bitti")]))

    await run_agent("a.py incele", _deps(tmp_path, sink, runtime={"repo_map_chars": 0}))

    assert not any(isinstance(e, RepoMapBuilt) for e in sink.events)
    assert "Depo haritası" not in " ".join(m.content for m in _ana_mesajlar(saglayici, 0))


@pytest.mark.parametrize(
    ("ayar", "pencere", "beklenen"),
    [
        (3000, None, 3000),
        (3000, 200_000, 3000),
        (3000, 32_768, 2949),
        (3000, 8_192, 737),
        (3000, 1_000, 600),
        (0, 8_192, 0),
        (1500, 200_000, 1500),
    ],
)
def test_etkin_butce_ayar_ve_pencereye_gore(ayar, pencere, beklenen):
    from fusion_cli.engines.agent.repo_context import effective_budget

    assert effective_budget(ayar, pencere) == beklenen


def test_varsayilan_harita_butcesi_yuklenir():
    from .fakes import make_config

    runtime = make_config().runtime
    assert runtime.repo_map_chars == 3000


def test_negatif_harita_butcesi_yapilandirmada_reddedilir(tmp_path):
    from fusion_cli.config.loader import load_config
    from fusion_cli.core.errors import ConfigError

    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  repo_map_chars: -1\n", "utf-8")
    with pytest.raises(ConfigError, match="repo_map_chars"):
        load_config(yol)
