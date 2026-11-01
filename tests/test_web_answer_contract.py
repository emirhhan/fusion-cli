"""Web sözleşme metni motordan gelir (P1-33); taşıma yalnız yerleştirir.

Ölçüldü (30 Ekim): `_ANSWER_CONTRACT` `providers/web_browser.py` içinde sabitti. Plan
modunda ya da `todo_write`/`ask_user` sunulmayan kümede modele var olmayan aracı
çağırmasını söylüyor, her devam turunda "İLK iş todo_write ile plan yaz" cümlesini
yineliyordu.
"""

from __future__ import annotations

from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.engines.agent.web_contract import render_answer_contract, tool_names
from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import format_browser_prompt
from fusion_cli.providers.web_session import (
    WebProviderAdapter,
    WebSessionCredential,
    WebTurn,
    WebTurnContext,
)

_TAM = frozenset({"todo_write", "ask_user", "read_file"})
_SISTEM = Message("system", "Araç kullanacaksan yalnız aşağıdaki çağrı biçimlerini kullan.")


def test_tasima_katmaninda_sozlesme_metni_kalmadi():
    assert not hasattr(web_browser, "_ANSWER_CONTRACT")
    govde = format_browser_prompt((_SISTEM, Message("user", "görev")))
    assert "todo_write" not in govde
    assert "ask_user" not in govde


def test_tam_arac_kumesinde_plan_ve_soru_cumleleri_gelir():
    metin = render_answer_contract(_TAM, has_todos=False)

    assert "İLK iş todo_write ile" in metin
    assert "ask_user aracını çağır" in metin


def test_plan_modunda_todo_write_ve_ask_user_yoksa_olmayan_arac_anilmaz():
    metin = render_answer_contract({"read_file", "grep"}, has_todos=False)

    assert "todo_write" not in metin
    assert "ask_user" not in metin
    assert "varsayım" in metin  # soru aracı yoksa makul varsayımla ilerle


def test_gorev_listesi_varsa_her_turda_yeniden_plan_yazdirilmaz():
    metin = render_answer_contract(_TAM, has_todos=True)

    assert "İLK iş todo_write ile" not in metin
    assert "yeniden plan yazma" in metin


def test_aracsiz_cagrida_sozlesme_bos():
    assert render_answer_contract(frozenset(), has_todos=False) == ""


def test_arac_adlari_sematdan_cikarilir():
    sema = ({"type": "function", "function": {"name": "todo_write", "parameters": {}}},)

    assert tool_names(sema) == {"todo_write"}


def test_tasima_verilen_sozlesmeyi_devam_ve_ilk_turda_yerlestirir():
    sozlesme = "ÖZEL SÖZLEŞME METNİ"
    mesajlar = (_SISTEM, Message("user", "görev"), Message("tool", "x", name="read_file", ok=True))

    ilk = format_browser_prompt(mesajlar, answer_contract=sozlesme)
    devam = format_browser_prompt(mesajlar[1:], continuation=True, answer_contract=sozlesme)
    bos = format_browser_prompt(mesajlar)

    assert sozlesme in ilk and sozlesme in devam
    assert sozlesme not in bos
    assert "FUSION//" in bos  # çerçeve notu taşımanındır, sözleşme boşken de kalır


async def test_adaptor_baglami_yalniz_doluysa_gecirir():
    cagrilar: list[tuple[int, WebTurnContext | None]] = []

    async def tasima(credential, messages, model, context=None):
        cagrilar.append((len(messages), context))
        return WebTurn("tamam")

    adaptor = WebProviderAdapter(
        model="m",
        credential=WebSessionCredential(),
        transport=tasima,
        tool_support=ToolSupport.NONE,
    )
    temel = {"temperature": 0.0, "max_tokens": 8, "timeout_s": 5.0}
    sema = ({"type": "function", "function": {"name": "todo_write"}},)

    await adaptor.complete(CompletionRequest(messages=(Message("user", "a"),), **temel))
    await adaptor.complete(
        CompletionRequest(
            messages=(Message("user", "a"),),
            conversation_id="alt/1",
            answer_contract="S",
            tools=sema,
            **temel,
        )
    )

    assert cagrilar[0][1] is None
    assert cagrilar[1][1] == WebTurnContext(conversation_id="alt/1", answer_contract="S")


class _IstekKaydeden:
    """Gelen `CompletionRequest`'leri olduğu gibi saklayan, tek cevaplı sağlayıcı."""

    label = "kaydeden"

    def __init__(self) -> None:
        self.istekler: list[CompletionRequest] = []

    async def complete(self, request):  # pragma: no cover - motor akıtır
        raise AssertionError

    async def stream(self, request):
        from fusion_cli.core.types import ModelResult, StreamDone

        self.istekler.append(request)
        yield StreamDone(ModelResult(name="agent", model="m", text="bitti", latency_ms=1, ok=True))


async def test_motor_istege_conversation_id_ve_sozlesmeyi_koyar(tmp_path, monkeypatch):
    from dataclasses import replace

    from fusion_cli.engines.agent.loop import run_agent

    from .agent_harness import install_provider, web_deps
    from .fakes import RecordingSink

    kaydeden = _IstekKaydeden()
    install_provider(monkeypatch, kaydeden)
    # Claude dışı modelde görev aracı varsayılan yok (#329); Claude gibi açıkça açılır ve
    # CLAUDE_CODE_ENABLE_TASKS=0 ile todo_write gelir.
    monkeypatch.setenv("CLAUDE_CODE_ENABLE_TODO_TOOLS", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENABLE_TASKS", "0")
    deps = replace(web_deps(tmp_path, RecordingSink()), conversation_id="oturum-7")

    await run_agent("selam", deps, allowed_tools={"read_file"})

    istek = kaydeden.istekler[0]
    assert istek.conversation_id == "oturum-7"
    # Soru sorabilen taraf (asker) yok → ask_user sunulmaz ve sözleşme onu anmaz (P1-33);
    # todo_write sunulur ve görev listesi boşken plan cümlesi gelir.
    adlar = tool_names(istek.tools)
    assert "ask_user" not in adlar and "todo_write" in adlar
    assert "ask_user" not in istek.answer_contract
    assert "İLK iş todo_write ile" in istek.answer_contract


async def test_baglamdan_habersiz_uc_argumanli_tasima_kirilmaz():
    """Eski/özel taşıma ve test sahteleri `context` kabul etmez: bağlam verilmeden çağrılır."""
    cagrilar: list[int] = []

    async def eski_tasima(credential, messages, model):
        cagrilar.append(len(messages))
        return WebTurn("tamam")

    adaptor = WebProviderAdapter(
        model="m",
        credential=WebSessionCredential(),
        transport=eski_tasima,
        tool_support=ToolSupport.NONE,
    )
    sema = ({"type": "function", "function": {"name": "todo_write"}},)

    sonuc = await adaptor.complete(
        CompletionRequest(
            messages=(Message("user", "a"),),
            temperature=0.0,
            max_tokens=8,
            timeout_s=5.0,
            conversation_id="x",
            answer_contract="S",
            tools=sema,
        )
    )

    assert sonuc.ok and cagrilar == [1]
