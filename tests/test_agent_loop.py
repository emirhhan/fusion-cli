"""Agent döngüsü — araç çağrısı, onay, refleksiyon, otomatik devam, alt-ajan."""

from __future__ import annotations

import pytest

from fusion_cli.core.events import (
    ContextCompressed,
    SelfReviewFinished,
    StepLimitReached,
    SubAgentFinished,
    SubAgentStarted,
    ToolExecuted,
    ToolOutcome,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent import reflexion
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, parse_arguments, run_agent

from .fakes import (
    AlwaysApprove,
    AlwaysReject,
    RecordingSink,
    ScriptedAsker,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

#: Otomatik-devam sezgiseli kısa ve teslimsiz cevapları "yarım" sayar. Bu sabiti
#: kullanan testler o davranışı değil, sınadıkları asıl akışı ölçer.
TAM_CEVAP = "Görevi tamamladım; ilgili değişiklik `src/app.py:12` satırında yapıldı ve doğrulandı."


def _icerir(sonuc, metin):
    return any(mesaj.content == metin for mesaj in sonuc.messages)


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


@pytest.fixture
def sink():
    return RecordingSink()


def _deps(tmp_path, sink, *, mode=ApprovalMode.AUTO, prompter=None, asker=None, **config_args):
    prompter = prompter or AlwaysApprove()
    return AgentDeps(
        config=make_config(**config_args),
        publisher=_Publisher(sink),
        policy=build_policy(mode, prompter),
        tool_context=ToolContext(root=tmp_path),
        asker=asker,
    )


def _kur(monkeypatch, provider):
    def _build(spec, *, publisher=None, channel=None, clock=None):
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)
    return provider


# --------------------------------------------------------------------------- #


async def test_araçsiz_yanit_dogrudan_dondurulur(monkeypatch, tmp_path, sink):
    _kur(monkeypatch, ScriptedProvider([model_result("iste cevap")]))

    sonuc = await run_agent("gorev", _deps(tmp_path, sink))

    assert sonuc.final_text == "iste cevap"
    assert sonuc.tool_calls_made == 0


async def test_arac_cagrisi_calisir_ve_sonuc_gecmise_eklenir(monkeypatch, tmp_path, sink):
    (tmp_path / "a.txt").write_text("dosya icerigi", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink))

    assert sonuc.final_text == TAM_CEVAP
    assert sonuc.tool_calls_made == 1
    arac_mesaji = next(m for m in sonuc.messages if m.role == "tool")
    assert "dosya icerigi" in arac_mesaji.content
    assert arac_mesaji.name == "read_file"


async def test_arac_calistirmasi_olay_yayinlar(monkeypatch, tmp_path, sink):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    await run_agent("oku", _deps(tmp_path, sink))

    olay = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert olay.name == "read_file" and olay.outcome is ToolOutcome.OK


async def test_reddedilen_onay_hata_sayilmaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent(
        "yaz", _deps(tmp_path, sink, mode=ApprovalMode.SECURITY, prompter=AlwaysReject())
    )

    assert not (tmp_path / "a.txt").exists()
    arac_mesaji = next(m for m in sonuc.messages if m.role == "tool")
    assert "onaylamadı" in arac_mesaji.content
    # Reddetme refleksiyon notu tetiklememeli.
    assert not _icerir(sonuc, reflexion.STANDARD_NOTE)
    olay = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert olay.outcome is ToolOutcome.DENIED


async def test_arac_hatasi_refleksiyon_notu_enjekte_eder(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="yok.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink))

    assert _icerir(sonuc, reflexion.STANDARD_NOTE)


async def test_refleksiyon_kapatilabilir(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="yok.txt")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("oku", _deps(tmp_path, sink, runtime={"reflexion": False}))

    assert not _icerir(sonuc, reflexion.STANDARD_NOTE)


async def test_yarim_kalan_is_bir_kez_devam_ettirilir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result("bak"),  # kisa, teslimsiz -> yarim gorunur
                model_result("iste tam cevap `kod` ile birlikte"),
            ]
        ),
    )

    sonuc = await run_agent("yap", _deps(tmp_path, sink))

    assert provider.calls == 3
    assert _icerir(sonuc, reflexion.AUTO_CONTINUE_NOTE)


async def test_otomatik_devam_en_fazla_bir_kez_calisir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result("kisa"),
                model_result("yine kisa"),
            ]
        ),
    )

    await run_agent("yap", _deps(tmp_path, sink))

    assert provider.calls == 3


async def test_adim_siniri_turu_sonlandirir(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [model_result(tool_calls=[tool_call("list_dir", path=".")]) for _ in range(20)]
        ),
    )

    sonuc = await run_agent("sonsuz", _deps(tmp_path, sink, runtime={"agent_max_steps": 3}))

    assert sonuc.hit_step_limit
    assert any(isinstance(e, StepLimitReached) for e in sink.events)


async def test_model_hatasi_turu_bitirir(monkeypatch, tmp_path, sink):
    _kur(monkeypatch, ScriptedProvider([model_result(ok=False, error="saglayici coktu")]))

    sonuc = await run_agent("gorev", _deps(tmp_path, sink))

    assert sonuc.final_text == "saglayici coktu"


async def test_plan_modunda_degistirici_arac_calismaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    await run_agent("planla", _deps(tmp_path, sink, mode=ApprovalMode.PLAN), plan_mode=True)

    assert not (tmp_path / "a.txt").exists()


async def test_plan_modu_sistem_promptuna_eklenir(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("plan")]))

    await run_agent("planla", _deps(tmp_path, sink), plan_mode=True)

    sistem = provider.seen_messages[0][0]
    assert "PLAN MODUNDASIN" in sistem.content


async def test_alt_ajan_temiz_baglamla_calisir(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("spawn_agent", task="alt gorev")]),
                model_result("alt ajan cevabi"),  # alt-ajanin turu
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("bol", _deps(tmp_path, sink))

    assert sonuc.final_text == TAM_CEVAP
    assert any(isinstance(e, SubAgentStarted) for e in sink.events)
    assert any(isinstance(e, SubAgentFinished) for e in sink.events)


async def test_alt_ajan_derinlik_siniri_asilmaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("spawn_agent", task="birinci")]),
                model_result(tool_calls=[tool_call("spawn_agent", task="ikinci")]),
                model_result(TAM_CEVAP),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    await run_agent("bol", _deps(tmp_path, sink))

    olaylar = [e for e in sink.events if isinstance(e, SubAgentStarted)]
    assert len(olaylar) == 1  # ikinci seviye reddedildi


async def test_ask_user_araci_yalnizca_asker_varken_sunulur(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("cevap")]))

    await run_agent("gorev", _deps(tmp_path, sink))
    araclarsiz = provider.calls

    assert araclarsiz == 1


async def test_ask_user_cevabi_modele_dondurulur(monkeypatch, tmp_path, sink):
    asker = ScriptedAsker("mavi olsun")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("ask_user", question="hangi renk?")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("renk sec", _deps(tmp_path, sink, asker=asker))

    assert asker.questions == ["hangi renk?"]
    assert any("mavi olsun" in m.content for m in sonuc.messages if m.role == "tool")


async def test_oz_denetim_sorun_yoksa_ikinci_tur_acmaz(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result("temiz cevap")]))
    monkeypatch.setattr(agent_loop.review, "review_turn", _sabit_denetim(""))

    await run_agent("gorev", _deps(tmp_path, sink, runtime={"self_review": True}))

    assert provider.calls == 1
    olay = next(e for e in sink.events if isinstance(e, SelfReviewFinished))
    assert not olay.issue_found


async def test_oz_denetim_sorun_bulursa_duzeltici_tur_calisir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch, ScriptedProvider([model_result("eksik cevap"), model_result("duzeltilmis")])
    )
    monkeypatch.setattr(agent_loop.review, "review_turn", _sabit_denetim("testleri calistirmadin"))

    sonuc = await run_agent("gorev", _deps(tmp_path, sink, runtime={"self_review": True}))

    assert provider.calls == 2
    assert sonuc.final_text == "duzeltilmis"


async def test_baglam_sikistirma_olayi_yayinlanir(monkeypatch, tmp_path, sink):
    _kur(monkeypatch, ScriptedProvider([model_result("cevap")]))

    async def _sikistir(messages, *, config):
        return messages[:1]

    monkeypatch.setattr(agent_loop.compaction, "compress", _sikistir)

    await run_agent("gorev", _deps(tmp_path, sink))

    assert any(isinstance(e, ContextCompressed) for e in sink.events)


# --- Argüman ayrıştırma ----------------------------------------------------- #


def test_bozuk_json_bos_sozluge_duser():
    assert parse_arguments("{bozuk") == {}


def test_sozluk_olmayan_json_bos_sozluge_duser():
    assert parse_arguments("[1,2]") == {}


def test_bos_arguman_bos_sozluk():
    assert parse_arguments("") == {}


def test_gecerli_json_ayristirilir():
    assert parse_arguments('{"path":"a.txt"}') == {"path": "a.txt"}


def _sabit_denetim(sonuc):
    async def _review(task, final_text, messages, *, config):
        return sonuc

    return _review


# --- Etkileşimsiz ortam ------------------------------------------------------ #


async def test_asker_yoksa_ask_user_araci_modele_sunulmaz(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    await run_agent("gorev", _deps(tmp_path, sink, asker=None))

    semalar = provider.seen_requests[0]
    assert "ask_user" not in {s["function"]["name"] for s in semalar}


async def test_asker_varsa_ask_user_araci_sunulur(monkeypatch, tmp_path, sink):
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))

    await run_agent("gorev", _deps(tmp_path, sink, asker=ScriptedAsker()))

    semalar = provider.seen_requests[0]
    assert "ask_user" in {s["function"]["name"] for s in semalar}


async def test_plan_modunda_engelleme_reddetmeden_ayirt_edilir(monkeypatch, tmp_path, sink):
    """Plan modunda kimseye sorulmaz; model bunu "kullanıcı reddetti" sanmamalı."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    sonuc = await run_agent("planla", _deps(tmp_path, sink, mode=ApprovalMode.PLAN), plan_mode=True)

    olay = next(e for e in sink.events if isinstance(e, ToolExecuted))
    assert olay.outcome is ToolOutcome.BLOCKED
    arac_mesaji = next(m for m in sonuc.messages if m.role == "tool")
    assert "PLAN MODU" in arac_mesaji.content
