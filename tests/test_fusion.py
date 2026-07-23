"""Fusion motoru — aday toplama, kısa devre, hakem ve sentez akışı."""

from __future__ import annotations

import json

import pytest

from fusion_cli.core.events import CandidatesStarted, JudgingStarted, ModelCallFinished
from fusion_cli.core.types import VerdictSource
from fusion_cli.engines.fusion import engine as fusion_engine
from fusion_cli.engines.fusion.engine import order_candidates, run_fusion

from .fakes import FakeProvider, RecordingSink, make_config


class _Publisher:
    """Doğrudan sink'e yazan basit yayıncı (veriyolu olmadan test için)."""

    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


def _hakem(winner, scores=None, reason="gerekce"):
    payload = json.dumps({"winner": winner, "scores": scores or {}, "reason": reason})
    return FakeProvider("hakem", chunks=(payload,))


@pytest.fixture
def sink():
    return RecordingSink()


@pytest.fixture
def publisher(sink):
    return _Publisher(sink)


async def test_hakem_kazanani_secer_ve_sentez_nihai_cevap_olur(monkeypatch, publisher, sink):
    saglayicilar = {
        "a": FakeProvider("a", chunks=("A cevabi",)),
        "b": FakeProvider("b", chunks=("B cevabi",)),
        "c": FakeProvider("c", chunks=("C cevabi",)),
        "hakem": _hakem("b", {"a": 0.5, "b": 0.9}),
    }
    # Hakem ve sentez ayni spec'i kullanir; sentez cagrisi ikinci kez ayni sahteyi dondurur.
    monkeypatch.setattr(fusion_engine, "_synthesize", _sabit_sentez("SENTEZ"))
    _patch(monkeypatch, saglayicilar)

    result = await run_fusion("gorev", make_config(), publisher=publisher)

    assert result.winner == "b"
    assert result.final_answer == "SENTEZ"
    assert result.synthesized
    assert result.source is VerdictSource.JUDGE
    assert result.scores == {"a": 0.5, "b": 0.9}


async def test_sentez_kapaliyken_kazananin_metni_donulur(monkeypatch, publisher):
    _patch(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("A cevabi",)),
            "b": FakeProvider("b", chunks=("B cevabi",)),
            "c": FakeProvider("c", chunks=("C cevabi",)),
            "hakem": _hakem("a"),
        },
    )

    result = await run_fusion("gorev", make_config(), publisher=publisher, synthesis=False)

    assert result.final_answer == "A cevabi"
    assert not result.synthesized


async def test_tek_basarili_aday_varsa_hakem_atlanir(monkeypatch, publisher, sink):
    _patch(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("tek cevap",)),
            "b": FakeProvider("b", ok=False, error="503"),
            "c": FakeProvider("c", ok=False, error="503"),
            "hakem": _hakem("a"),
        },
    )

    result = await run_fusion("gorev", make_config(), publisher=publisher)

    assert result.source is VerdictSource.SINGLE
    assert result.final_answer == "tek cevap"
    assert not any(isinstance(event, JudgingStarted) for event in sink.events)


async def test_hicbir_aday_yanit_vermezse_kaynak_none(monkeypatch, publisher):
    _patch(
        monkeypatch,
        {
            "a": FakeProvider("a", ok=False, error="429"),
            "b": FakeProvider("b", ok=False, error="429"),
            "c": FakeProvider("c", ok=False, error="429"),
            "hakem": _hakem("a"),
        },
    )

    result = await run_fusion("gorev", make_config(), publisher=publisher)

    assert result.source is VerdictSource.NONE
    assert result.final_answer == ""


async def test_hakem_basarisizsa_ilk_aday_secilir_sentez_yine_gelir(monkeypatch, publisher):
    _patch(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("A",)),
            "b": FakeProvider("b", chunks=("B",)),
            "c": FakeProvider("c", chunks=("C",)),
            "hakem": FakeProvider("hakem", ok=False, error="hakem coktu"),
        },
    )
    monkeypatch.setattr(fusion_engine, "_synthesize", _sabit_sentez("SENTEZ"))

    result = await run_fusion("gorev", make_config(), publisher=publisher)

    assert result.source is VerdictSource.FALLBACK
    assert result.final_answer == "SENTEZ"


async def test_hakem_bozuk_json_verirse_geri_dusulur(monkeypatch, publisher):
    _patch(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("A",)),
            "b": FakeProvider("b", chunks=("B",)),
            "c": FakeProvider("c", chunks=("C",)),
            "hakem": FakeProvider("hakem", chunks=("bu json degil",)),
        },
    )

    result = await run_fusion("gorev", make_config(), publisher=publisher, synthesis=False)

    assert result.source is VerdictSource.FALLBACK


async def test_yavas_aday_turu_kilitlemez(monkeypatch, publisher):
    _patch(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("A",)),
            "b": FakeProvider("b", chunks=("B",)),
            "c": FakeProvider("c", chunks=("gec kalan",), delay=5.0),
            "hakem": _hakem("a"),
        },
    )

    result = await run_fusion("gorev", make_config(), publisher=publisher, synthesis=False)

    assert {c.name for c in result.candidates} == {"a", "b"}


async def test_ilerleme_olaylari_yayinlanir(monkeypatch, publisher, sink):
    _patch(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("A",)),
            "b": FakeProvider("b", chunks=("B",)),
            "c": FakeProvider("c", chunks=("C",)),
            "hakem": _hakem("a"),
        },
    )

    await run_fusion("gorev", make_config(), publisher=publisher, synthesis=False)

    tipler = [type(event) for event in sink.events]
    assert tipler[0] is CandidatesStarted
    assert JudgingStarted in tipler
    assert sum(1 for t in tipler if t is ModelCallFinished) >= 3


def test_gorev_tipi_tercih_edilen_adayi_one_alir():
    config = make_config()

    assert order_candidates(config, "code")[0].name == "c"
    assert order_candidates(config, "general")[0].name == "a"


def test_eslesmeyen_gorev_tipinde_siralama_degismez():
    config = make_config()

    assert order_candidates(config, "bilinmeyen") == config.candidates


# --------------------------------------------------------------------------- #


def _patch(monkeypatch, saglayicilar):
    from .fakes import patch_providers

    patch_providers(monkeypatch, fusion_engine, saglayicilar)


def _sabit_sentez(metin):
    from fusion_cli.core.types import ModelResult

    async def _synthesize(task, answers, config, publisher):
        return ModelResult(name="sentez", model="m", text=metin, latency_ms=1, ok=True)

    return _synthesize
