"""LiteLLM adaptörü — SDK yanıtlarının proje tiplerine çevrilmesi.

Ağa çıkılmaz: SDK yanıt nesneleri basit sahtelerle taklit edilir. Buradaki testler
reasoning modelleriyle çalışırken ortaya çıkan iki sessiz kaybı sabitler:

1. Düşünme metni `reasoning_content` alanında gelir; okunmazsa tamamen kaybolur.
2. Model bütçesi düşünme sırasında dolarsa `content` BOŞ gelir. Bu bir başarı değil,
   kesilmiş bir turdur; sessizce boş cevap dönmek kullanıcıya "hiçbir şey yapmadı"
   gibi görünür.
"""

from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.core.types import StreamDone
from fusion_cli.providers.litellm_provider import LiteLlmProvider

from .fakes import request


def _yanit(
    content: str = "",
    *,
    reasoning: str | None = None,
    finish_reason: str = "stop",
) -> SimpleNamespace:
    """SDK'nın döndürdüğü yanıt nesnesinin taklidi."""
    message = SimpleNamespace(content=content, tool_calls=None)
    if reasoning is not None:
        message.reasoning_content = reasoning
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
    )


def _saglayici() -> LiteLlmProvider:
    return LiteLlmProvider("sahte/model", role="agent")


async def test_reasoning_icerigi_okunur_ve_cevaba_karistirilmaz(monkeypatch):
    """Düşünme metni taşınır ama nihai cevabın içine sızmaz."""
    yanit = _yanit("Nihai cevap.", reasoning="Önce şunu düşüneyim…")
    _sdk(monkeypatch, yanit)

    sonuc = await _saglayici().complete(request())

    assert sonuc.text == "Nihai cevap."
    assert sonuc.reasoning == "Önce şunu düşüneyim…"


async def test_reasoning_alternatif_alan_adiyla_da_okunur(monkeypatch):
    """Bazı sağlayıcılar `reasoning_content` yerine `reasoning` yazar."""
    message = SimpleNamespace(content="cevap", tool_calls=None, reasoning="düşünce")
    yanit = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None
    )
    _sdk(monkeypatch, yanit)

    sonuc = await _saglayici().complete(request())

    assert sonuc.reasoning == "düşünce"


async def test_butce_dusunme_sirasinda_dolarsa_tur_basarisiz_sayilir(monkeypatch):
    """content boş + finish_reason=length → sessiz boş cevap DEĞİL, açık hata."""
    yanit = _yanit("", reasoning="yarım kalmış düşünce", finish_reason="length")
    _sdk(monkeypatch, yanit)

    sonuc = await _saglayici().complete(request())

    assert not sonuc.ok
    assert "bütçe" in (sonuc.error or "").lower()
    assert sonuc.reasoning == "yarım kalmış düşünce"


async def test_arac_cagrisi_varsa_bos_content_hata_degildir(monkeypatch):
    """Araç çağıran tur metin üretmez; bu normaldir."""
    message = SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(id="1", function=SimpleNamespace(name="read_file", arguments="{}"))
        ],
    )
    yanit = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")], usage=None
    )
    _sdk(monkeypatch, yanit)

    sonuc = await _saglayici().complete(request())

    assert sonuc.ok
    assert sonuc.tool_calls[0].name == "read_file"


async def test_akista_reasoning_parcalari_metne_karismaz(monkeypatch):
    """Akışta düşünme parçaları kullanıcıya metin olarak yayınlanmaz."""
    parcalar = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content="dü"))]
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content="şün"))]
        ),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="cevap"))]),
    ]
    _sdk(
        monkeypatch,
        akis=parcalar,
        stream_chunk_builder=lambda chunks, messages: _yanit("cevap", reasoning="düşün"),
    )

    metinler = []
    sonuc = None
    async for item in _saglayici().stream(request()):
        if isinstance(item, StreamDone):
            sonuc = item.result
        else:
            metinler.append(item.text)

    assert "".join(metinler) == "cevap"
    assert sonuc is not None and sonuc.reasoning == "düşün"


# --------------------------------------------------------------------------- #


def _sdk(monkeypatch, yanit=None, *, akis=None, stream_chunk_builder=None):
    """LiteLLM modülünü sahte bir SDK ile değiştir."""
    sahte = SimpleNamespace(
        acompletion=_sahte_akis(akis) if akis is not None else _sahte_acompletion(yanit),
        completion_cost=lambda **kwargs: 0.0,
    )
    if stream_chunk_builder is not None:
        sahte.stream_chunk_builder = stream_chunk_builder
    monkeypatch.setattr("fusion_cli.providers.litellm_provider._litellm", lambda: sahte)


def _sahte_acompletion(yanit):
    async def _cagir(**kwargs):
        return yanit

    return _cagir


def _sahte_akis(parcalar):
    async def _cagir(**kwargs):
        async def _uret():
            for parca in parcalar:
                yield parca

        return _uret()

    return _cagir


async def test_kesilen_yanit_isaretlenir(monkeypatch):
    """finish_reason=length → çıktı yarım; üst katman buna güvenmemeli."""
    _sdk(monkeypatch, _yanit("Yarım cüml", finish_reason="length"))

    sonuc = await _saglayici().complete(request())

    assert sonuc.truncated


async def test_tamamlanan_yanit_kesik_isaretlenmez(monkeypatch):
    _sdk(monkeypatch, _yanit("Tam cevap.", finish_reason="stop"))

    sonuc = await _saglayici().complete(request())

    assert not sonuc.truncated
