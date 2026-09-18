"""Gözlem turu — kod kipinde de salt okuma isteyen tur yazamaz (B4, A13).

Kaynak: `docs/superpowers/plans/2026-09-18-tek-ajan-dongusu.md` Görev 5.

İki değişikliği birlikte kilitler:

1. Gözlem kilidi genelleşti (`chat_mode.observe_execution`): sohbet kipiyle
   sınırlı kalmaz, kod kipinde de turun METNİ yalnızca `workspace_read` etkisi
   istiyorsa model o turda yazamaz. Tetikleyici `effects/detect.py`'nin kararlı
   sınıflandırmasıdır (bkz. plan §6 karar 1), kelime dürtmesi değil.
2. Kapsamı büyüten genel dürtme kapıları (`_needs_push_to_act`,
   `_stopped_without_acting`, `_asked_instead_of_acting`, karmaşık-görev dalı
   `_never_acted`) kaldırıldı: model ne zaman araç kullanıp ne zaman
   bitireceğine kendi karar verir. Yalnız bloklayan doğrulama düzeltmesinin
   (`require_local_mutation`) araçsız kapanmaması korunur.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelResult
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

#: Otomatik-devam sezgiseli kısa ve teslimsiz cevapları "yarım" sayar; bu sabiti
#: kullanan testler o davranışı değil sınadıkları asıl akışı ölçer.
TAM_CEVAP = "Görevi tamamladım; ilgili değişiklik `src/app.py:12` satırında yapıldı ve doğrulandı."

#: `required_effect_for` bu metni kararlı biçimde `workspace_read` sınıflar
#: (plan §6 karar 1'in doğrudan örneği).
SALT_OKUMA_ISTEGI = "src/app.py dosyasını oku ve ne yaptığını anlat"


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


@pytest.fixture
def sink():
    return RecordingSink()


def _deps(tmp_path, sink, **config_args):
    return AgentDeps(
        config=make_config(**config_args),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _kur(monkeypatch, provider):
    monkeypatch.setattr(agent_loop, "build_provider", lambda *a, **k: provider)
    return provider


async def test_salt_okuma_isteginde_degistirici_arac_semasi_sunulmaz(monkeypatch, tmp_path, sink):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="src/app.py")]),
                model_result("Dosya `x` değişkenine 1 atıyor."),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)

    await run_agent(SALT_OKUMA_ISTEGI, deps)

    sunulan = {sema["function"]["name"] for sema in provider.seen_requests[0]}
    for degistirici in ("write_file", "edit_file", "multi_edit", "run_shell", "scaffold_web"):
        assert degistirici not in sunulan, f"{degistirici} salt okuma turunda sunulmamalı"


async def test_gozlem_turunda_yazma_cagrisi_engellenir_ve_diske_dosya_dusmez(
    monkeypatch, tmp_path, sink
):
    """Model yine de değiştirici bir araç çağırırsa BLOCKED olur, disk değişmez."""
    from fusion_cli.core.events import ToolExecuted, ToolOutcome

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("write_file", path="kopya.py", content="x = 2\n")]
                ),
                model_result("Elimden geleni yaptım."),
            ]
        ),
    )
    deps = _deps(tmp_path, sink)

    await run_agent(SALT_OKUMA_ISTEGI, deps)

    assert not (tmp_path / "kopya.py").exists()
    engellenen = [
        olay
        for olay in sink.events
        if isinstance(olay, ToolExecuted) and olay.name == "write_file"
    ]
    assert engellenen and engellenen[0].outcome is ToolOutcome.BLOCKED


async def test_okuma_turlarinda_kesif_durtmesi_yapilmaz(monkeypatch, tmp_path, sink):
    """Beş okuma turundan sonra bile eski 'dur-ve-yap' dürtmesi gönderilmez.

    `complex_task` doğrudan politika üzerinden zorlanır (`requires_tool_evidence`
    kasıtlı olarak AÇILMAZ): amaç yalnızca kaldırılan keşif kapısını yalıtmak,
    ayrı bir davranış olan kanıt kapısını değil (bkz. eski test_turn_budget.py
    `test_okuyup_duran_tur_bir_kez_devam_ettirilir`).
    """
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    for isim in ("a.py", "b.py", "c.py", "d.py", "e.py"):
        (tmp_path / isim).write_text("x = 1\n", encoding="utf-8")
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="a.py")]),
                model_result(tool_calls=[tool_call("read_file", path="b.py")]),
                model_result(tool_calls=[tool_call("read_file", path="c.py")]),
                model_result(tool_calls=[tool_call("read_file", path="d.py")]),
                model_result(tool_calls=[tool_call("read_file", path="e.py")]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})
    deps.execution = ExecutionPolicy(is_web=True, complex_task=True, heuristic_auto_continue=False)

    sonuc = await run_agent("bu beş dosyadaki hatayı bul ve düzelt", deps)

    assert provider.calls == 6
    assert not [m for m in sonuc.messages if "[dur-ve-yap]" in m.content]


async def test_arac_cagirmadan_cevaplanan_kod_sorusu_zorlanmaz(monkeypatch, tmp_path, sink):
    """Kod kipinde araçsız verilen düz bir cevap zorlanmadan tek çağrıyla biter."""
    provider = _kur(monkeypatch, ScriptedProvider([model_result("Girdiyi ikiye katlar.")]))
    deps = _deps(tmp_path, sink, runtime={"self_review": False})

    sonuc = await run_agent("bu fonksiyon ne işe yarar", deps)

    assert provider.calls == 1
    assert sonuc.ok is True


async def test_bekleyen_todo_varken_devam_notu_verilir(monkeypatch, tmp_path, sink):
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        tool_call(
                            "todo_write",
                            todos=[{"content": "ilk iş", "status": "pending"}],
                        )
                    ]
                ),
                # Todo hâlâ bekliyorken final metin: auto-continue notu enjekte edilmeli.
                model_result("bakıyorum"),
                model_result(
                    tool_calls=[
                        tool_call(
                            "todo_write",
                            todos=[{"content": "ilk iş", "status": "completed"}],
                        )
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})

    await run_agent("çok adımlı görev: önce ilk işi yap, sonra raporla", deps)

    assert provider.calls == 4, "bekleyen todo varken tur erken bitirildi"


async def test_kesik_yanitta_butunluk_notu_korunur(monkeypatch, tmp_path, sink):
    kesik = ModelResult(
        name="agent", model="sahte", text="yarım kalan cüm", latency_ms=1, ok=True, truncated=True
    )
    provider = _kur(monkeypatch, ScriptedProvider([kesik, model_result(TAM_CEVAP)]))
    deps = _deps(tmp_path, sink, runtime={"self_review": False})

    await run_agent("uzun bir cevap yaz", deps)

    assert provider.calls == 2, "kesilmiş yanıt devam ettirilmedi"


async def test_acik_dis_etkide_kanit_kapisi_korunur(monkeypatch, tmp_path, sink):
    """'Commit at' gibi gerçek bir etki isteyen görevde araçsız 'yaptım' geçmez."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result("Commit'i attım."),
                model_result("Commit'i attım."),
            ]
        ),
    )
    deps = _deps(tmp_path, sink, runtime={"self_review": False})

    sonuc = await run_agent("değişiklikleri commit at", deps)

    assert sonuc.ok is False
    assert "tamamlanmadı" in sonuc.final_text.lower()


async def test_dogrulama_duzeltmesinde_mutasyon_zorunlulugu_korunur():
    """Bloklayan doğrulama düzeltmesi araçsız kapanamaz (require_local_mutation dalı)."""
    from types import SimpleNamespace

    from fusion_cli.engines.agent.loop import _never_acted, _State

    execution = SimpleNamespace(complex_task=True, offer_tools=True, max_evidence_reprompts=0)
    durum = _State(internal=True, require_local_mutation=True)

    assert _never_acted(durum, execution) is True

    durum.mutating_tool_calls_made = 1
    assert _never_acted(durum, execution) is False
