"""Web-session sağlayıcı çerçevesi — mock transport ile uçtan uca.

Gerçek ağ/oturum YOK: transport enjekte edilir. Master prompt §21 test 5-6'nın
mock-provider senaryolarını karşılar.
"""

from __future__ import annotations

import json

from fusion_cli.config.tool_policy import can_be_mutation_agent
from fusion_cli.core.model_capability import ModelCapability, ToolSupport
from fusion_cli.core.tool_emulation import CALL_CLOSE, CALL_OPEN
from fusion_cli.core.types import CompletionRequest, Message, StreamDone, TextChunk
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential


def _request(tools=()):
    return CompletionRequest(
        messages=(Message("user", "selam"),),
        temperature=0.0,
        max_tokens=64,
        timeout_s=5.0,
        tools=tuple(tools),
    )


def _echo_transport(reply):
    async def _t(credential, messages, model):
        return reply

    return _t


def _cred():
    return WebSessionCredential(token="test-token")


# --- test 5: web benzeri sağlayıcı düz sohbet üretir ----------------------- #


async def test_web_saglayici_duz_sohbet_uretir():
    adapter = WebProviderAdapter(
        model="mock-web", credential=_cred(), transport=_echo_transport("Merhaba, ben web modeli.")
    )
    sonuc = await adapter.complete(_request())
    assert sonuc.ok is True
    assert sonuc.text == "Merhaba, ben web modeli."
    assert sonuc.tool_calls == ()


async def test_web_saglayici_stream_metin_ve_done_verir():
    adapter = WebProviderAdapter(
        model="mock-web", credential=_cred(), transport=_echo_transport("akan cevap")
    )
    ogeler = [item async for item in adapter.stream(_request())]
    assert any(isinstance(o, TextChunk) and o.text == "akan cevap" for o in ogeler)
    assert isinstance(ogeler[-1], StreamDone)


# --- test 6: araçsız web modeli yalnızca council adayı olabilir ------------ #


async def test_arac_desteksiz_web_modeli_araclari_yoksayar():
    tools = ({"type": "function", "function": {"name": "edit_file", "parameters": {}}},)
    adapter = WebProviderAdapter(
        model="mock-web",
        credential=_cred(),
        transport=_echo_transport("düz cevap"),
        tool_support=ToolSupport.NONE,
    )
    sonuc = await adapter.complete(_request(tools=tools))
    # NONE: araç çağrısı üretmez, düz metin döner.
    assert sonuc.tool_calls == ()
    assert sonuc.text == "düz cevap"


def test_araçsiz_web_modeli_mutation_agent_olamaz():
    # Araçsız web modeli yalnızca sohbet/council rollerinde kullanılabilir.
    cap = ModelCapability(tool_support=ToolSupport.NONE)
    assert can_be_mutation_agent(cap).ok is False


# --- emulated web modeli araç çağrısını ayrıştırır ------------------------- #


async def test_emulated_web_modeli_arac_cagrisi_ayristirir():
    blok = json.dumps({"name": "edit_file", "arguments": {"path": "a"}})
    reply = f"Şunu yapıyorum. {CALL_OPEN}{blok}{CALL_CLOSE}"
    tools = ({"type": "function", "function": {"name": "edit_file", "parameters": {}}},)
    adapter = WebProviderAdapter(
        model="mock-web",
        credential=_cred(),
        transport=_echo_transport(reply),
        tool_support=ToolSupport.EMULATED,
    )
    sonuc = await adapter.complete(_request(tools=tools))
    assert len(sonuc.tool_calls) == 1
    assert sonuc.tool_calls[0].name == "edit_file"
    assert "yapıyorum" in sonuc.text


async def test_emulated_arac_cagrisinda_oncu_metin_yayinlanir():
    """Model araç çağırırken yazdığı öncü cümle kullanıcıya ULAŞMALIDIR.

    Bastırma eskiden çağrı VARLIĞINA bakıyordu: model "şu dosyalara bakıyorum"
    dese bile kullanıcı yalnızca araç satırlarını görüyor, turun neden başladığını
    hiç öğrenemiyordu.
    """
    blok = json.dumps({"name": "read_file", "arguments": {"path": "a"}})
    reply = f"Önce yapılandırmayı okuyorum. {CALL_OPEN}{blok}{CALL_CLOSE}"
    tools = ({"type": "function", "function": {"name": "read_file", "parameters": {}}},)
    adapter = WebProviderAdapter(
        model="mock-web",
        credential=_cred(),
        transport=_echo_transport(reply),
        tool_support=ToolSupport.EMULATED,
    )
    ogeler = [item async for item in adapter.stream(_request(tools=tools))]
    metinler = [o.text for o in ogeler if isinstance(o, TextChunk)]
    assert metinler == ["Önce yapılandırmayı okuyorum."]


async def test_emulated_ayristirma_hatasinda_metin_bastirilir():
    """Ayrıştırma hatası varsa metin yarım kalmış olabilir; ekrana sızmaz."""
    reply = f"Şunu yazıyorum. {CALL_OPEN}{{bozuk json{CALL_CLOSE}"
    tools = ({"type": "function", "function": {"name": "write_file", "parameters": {}}},)
    adapter = WebProviderAdapter(
        model="mock-web",
        credential=_cred(),
        transport=_echo_transport(reply),
        tool_support=ToolSupport.EMULATED,
    )
    ogeler = [item async for item in adapter.stream(_request(tools=tools))]
    assert not [o for o in ogeler if isinstance(o, TextChunk)]


async def test_emulated_web_modeli_arac_talimatini_enjekte_eder():
    yakalanan = {}

    async def _capture(credential, messages, model):
        yakalanan["messages"] = messages
        return "tamam"

    tools = ({"type": "function", "function": {"name": "edit_file", "parameters": {}}},)
    adapter = WebProviderAdapter(
        model="mock-web", credential=_cred(), transport=_capture, tool_support=ToolSupport.EMULATED
    )
    await adapter.complete(_request(tools=tools))
    sistem = [m for m in yakalanan["messages"] if m.role == "system"]
    assert sistem and "edit_file" in sistem[0].content


# --- hata sınırı: transport patlarsa ok=False (fırlatmaz) ------------------ #


async def test_transport_hatasi_sonuca_cevrilir():
    async def _patla(credential, messages, model):
        raise RuntimeError("oturum süresi doldu")

    adapter = WebProviderAdapter(model="mock-web", credential=_cred(), transport=_patla)
    sonuc = await adapter.complete(_request())
    assert sonuc.ok is False
    assert "oturum" in sonuc.error


# --- yığına oturur: LlmProvider gibi FallbackProvider içinde çalışır -------- #


async def test_web_adapter_fallback_zincirinde_calisir():
    from fusion_cli.providers.chain import FallbackProvider

    adapter = WebProviderAdapter(
        model="mock-web", credential=_cred(), transport=_echo_transport("zincirden cevap")
    )
    zincir = FallbackProvider([adapter], role="agent")
    sonuc = await zincir.complete(_request())
    assert sonuc.text == "zincirden cevap"
