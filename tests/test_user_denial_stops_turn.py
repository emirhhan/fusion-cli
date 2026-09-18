"""Kullanıcı bir aracı GERÇEKTEN reddedince tur durur ve kullanıcıya sorulur (B3).

Eskiden red ile "onay alınamadı" (oturum etkileşimsiz) TEK bir yolda birleşiyor ve
her ikisinde de model tekrar çağrılıp başka bir yol denemesi isteniyordu. Ölçülen
hata: kullanıcı GERÇEKTEN "hayır" dedi, model bunu görmezden gelip aynı işi başka
bir yoldan yapmaya çalıştı — kullanıcının kararı bir sonraki adımda yok sayıldı.

Bu dosya YALNIZCA gerçek reddi (`AlwaysReject` / `ApprovalAnswer.DENY`) sınar.
"Onay alınamadı" (etkileşimsiz oturum) davranışı ayrı bir testte, ayrıca sınanır:
o durumda tur SÜRMELİDİR.
"""

from __future__ import annotations

from fusion_cli.core.budget import BudgetStop
from fusion_cli.core.events import Event, ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysReject,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

#: Otomatik-devam sezgiseli kısa/teslimsiz cevapları "yarım" sayar; bu sabit onu
#: tetiklemeden gerçekçi bir bitiş metni vermek için kullanılır (bkz. test_agent_loop.py).
TAM_CEVAP = "Görevi tamamladım; ilgili değişiklik `src/app.py:12` satırında yapıldı ve doğrulandı."


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event: Event) -> None:
        self._sink.handle(event)


def _deps(tmp_path, sink, *, mode=ApprovalMode.SECURITY, prompter=None, **config_args):
    prompter = prompter or AlwaysReject()
    return AgentDeps(
        config=make_config(**config_args),
        publisher=_Publisher(sink),
        policy=build_policy(mode, prompter),
        tool_context=ToolContext(root=tmp_path),
    )


def _kur(monkeypatch, provider):
    def _build(
        spec,
        *,
        publisher=None,
        retry_delays_s=(),
        channel=None,
        clock=None,
        sleeper=None,
        background=False,
        health=None,
        key_pools=None,
        web_sessions=None,
    ):
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)
    return provider


class _EtkilesimsizOnayci:
    """TTY olmayan `ConsolePrompter`in davrandığı gibi: kimseye SORULAMADI."""

    async def confirm(self, request):
        return ApprovalAnswer.UNAVAILABLE


async def test_kullanici_reddedince_tur_ikinci_model_cagrisi_yapmadan_biter(
    monkeypatch, tmp_path
):
    sink = RecordingSink()
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("run_shell", command="rm -rf build")]),
                model_result("model bir daha ÇAĞRILMAMALI"),
            ]
        ),
    )

    outcome = await run_agent("build'i temizle", _deps(tmp_path, sink))

    assert outcome.model_calls_made == 1
    assert provider.calls == 1
    assert outcome.ok is True
    assert "run_shell" in outcome.final_text
    assert "nasıl devam edeyim" in outcome.final_text.lower()


async def test_ayni_yanittaki_kalan_cagrilar_calismaz_ama_eslesen_arac_sonucu_alir(
    monkeypatch, tmp_path
):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        tool_call("write_file", path="a.txt", content="y"),
                        tool_call("write_file", path="b.txt", content="z"),
                    ]
                ),
            ]
        ),
    )

    outcome = await run_agent("iki dosya yaz", _deps(tmp_path, sink))

    tool_mesajlari = [m for m in outcome.messages if m.role == "tool"]
    assert len(tool_mesajlari) == 2
    # İkinci çağrı hiç ÇALIŞMADI: dosya oluşmadı, ama sağlayıcı sözleşmesi
    # gereği kendi `tool_call_id`'siyle eşleşen bir "atlandı" sonucu aldı.
    assert not (tmp_path / "b.txt").exists()
    assert tool_mesajlari[1].tool_call_id == "call_write_file"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") != "y"


async def test_red_sonrasi_dogrulama_kapisi_ve_oz_denetim_calismaz(monkeypatch, tmp_path):
    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")])]
        ),
    )
    calisti = {"verifier": False, "self_review": False}

    class _SahteVerifier:
        async def verify(self, *args, **kwargs):
            calisti["verifier"] = True
            raise AssertionError("red sonrası doğrulama kapısı çalışmamalı")

    deps = _deps(tmp_path, sink, runtime={"self_review": True})
    deps.verifier = _SahteVerifier()

    async def _patlayan_self_review(*args, **kwargs):
        calisti["self_review"] = True
        raise AssertionError("red sonrası öz-denetim çalışmamalı")

    monkeypatch.setattr(agent_loop, "_self_review", _patlayan_self_review)

    outcome = await run_agent("yaz", deps)

    assert outcome.ok is True
    assert calisti == {"verifier": False, "self_review": False}


async def test_ic_ice_tur_red_sonrasi_hemen_doner(monkeypatch, tmp_path):
    """`budget.stop is USER_DENIED` iken `_drive` model çağırmadan döner.

    Bir sonraki `_drive` çağrısı (öz-denetim/doğrulama/plan) aynı bütçeyi miras
    alsa bile bu kuraldan muaf değildir.
    """
    sink = RecordingSink()
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result("HİÇ görülmemeli"),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)

    await run_agent("yaz", deps)
    # Aynı bütçeyi paylaşan ikinci bir `run_agent` (ör. iç bir düzeltme turu)
    # da modeli tekrar çağırmamalı.
    ikinci = await run_agent("devam et", deps, depth=1, internal=True, verify=False)

    assert provider.calls == 1
    assert ikinci.model_calls_made == 0
    assert ikinci.ok is True


async def test_etkilesimsiz_oturumda_onay_alinamamasi_red_sayilmaz(monkeypatch, tmp_path):
    """Kimseye SORULAMAMIŞ olmak reddedilmekle KARIŞTIRILMAMALI: tur sürer.

    Tam tersi senaryoyla (`test_kullanici_reddedince_...`) karşılaştır: orada
    model tam olarak BİR kez çağrılır ve tur durur; burada engellenen çağrıdan
    SONRA da model çağrılmaya devam eder — `budget.stop` hiç `USER_DENIED`
    olmaz. Kesin çağrı sayısı bu testin konusu değildir (motorun "hiç değişiklik
    olmadı" dürtmesi gibi bağımsız sezgiseller de araya girebilir); asıl sözleşme
    turun DURMAMASI ve modelin "onay alınamadı" metnini görmesidir.
    """
    sink = RecordingSink()
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, prompter=_EtkilesimsizOnayci())

    outcome = await run_agent("yaz", deps)

    # Reddedilen senaryonun aksine burada tur hiç durmadı: model birden fazla
    # kez çağrıldı.
    assert provider.calls > 1
    assert deps.budget is not None
    assert deps.budget.stop is not BudgetStop.USER_DENIED
    tool_mesaji = next(m for m in outcome.messages if m.role == "tool")
    assert "onay alınamadı" in tool_mesaji.content
    assert "UYDUR" in tool_mesaji.content


async def test_reddedilen_git_akisi_durur(monkeypatch, tmp_path):
    """`effects/tool_runner.EffectToolRunner` DENIED'da mevcut davranışı korur.

    Bu görevin dosyaları arasında yalnız TEST vardır — davranış zaten vardı ve
    değişmedi; burada sözleşme olarak KİLİTLENİR.
    """
    from fusion_cli.core.events import ToolOutcome as _Outcome
    from fusion_cli.core.tools import Tool, ToolEffect
    from fusion_cli.engines.effects.tool_runner import EffectToolRunner
    from fusion_cli.tools import ToolRegistry

    sink = RecordingSink()
    arac = Tool(
        name="run_shell",
        description="",
        parameters={},
        run=lambda a, c: None,
        mutating=True,
        effect=ToolEffect.LOCAL,
    )
    registry = ToolRegistry()
    registry.register(arac)
    deps = _deps(tmp_path, sink)

    runner = EffectToolRunner(deps, registry)
    executed = await runner.execute("run_shell", {"command": "git push"})

    assert executed.outcome is _Outcome.DENIED
    assert runner.tool_calls_made == 0
    assert runner.mutating_tool_calls_made == 0
    olay = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert olay.outcome is ToolOutcome.DENIED
