"""Plan kipi tamamlanması (P-025): plan dosyası, kabul kartı, kipe geçiş.

Ölçüldü (31 Ekim): plan kipinde tur bitince plan hiçbir yere yazılmıyordu
(`plans/` dizini yok, `PlanDrafted` olayı yok); masaüstünde kabul kartı vardı ama
REPL'de yoktu; `/plan` yalnız kipi değiştiriyordu (`goster`/`ac` yok).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from fusion_cli.cli.repl import plan_card
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.events import PlanDrafted
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import plan_mode
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome, run_agent
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages

from .fakes import AlwaysApprove, RecordingSink, ScriptedProvider, make_config, model_result


@pytest.fixture(autouse=True)
def plans_in_tmp(tmp_path: Path, monkeypatch) -> Path:
    """Plan dosyaları kullanıcı dizinine değil tmp'ye yazılsın."""
    hedef = tmp_path / "planlar"
    monkeypatch.setattr(plan_mode, "plans_dir", lambda: hedef)
    return hedef


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self._sink = sink

    def publish(self, event) -> None:
        self._sink.handle(event)


def _deps(tmp_path: Path, sink: RecordingSink, *, conversation_id: str = "oturum-1", **runtime):
    return AgentDeps(
        config=make_config(**runtime),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.PLAN, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        conversation_id=conversation_id,
    )


def _outcome(text: str, *, ok: bool = True) -> AgentOutcome:
    return AgentOutcome(final_text=text, messages=[], ok=ok)


# --- Plan dosyası --------------------------------------------------------------- #


def test_plan_yolu_sohbet_kimligini_dosya_adi_yapar(plans_in_tmp: Path) -> None:
    yol = plan_mode.plan_path("session-abc123")
    assert yol == plans_in_tmp / "session-abc123.md"


def test_plan_yolu_tehlikeli_karakterleri_temizler(plans_in_tmp: Path) -> None:
    yol = plan_mode.plan_path("../../etc/passwd")
    assert yol.parent == plans_in_tmp
    assert ".." not in yol.name and "/" not in yol.name


def test_bos_sohbet_kimligi_varsayilan_dosyaya_duser(plans_in_tmp: Path) -> None:
    assert plan_mode.plan_path("").parent == plans_in_tmp
    assert plan_mode.plan_path("").name.endswith(".md")


def test_plan_kaydedilir_ve_geri_okunur() -> None:
    yol = plan_mode.save_plan("oturum-1", "# Giriş ekranı\n\n1. Form\n2. Test\n")
    assert yol.read_text(encoding="utf-8").startswith("# Giriş ekranı")
    assert plan_mode.read_plan("oturum-1") == "# Giriş ekranı\n\n1. Form\n2. Test\n"
    assert plan_mode.read_plan("yok") is None


def test_plan_basligi_ilk_baslik_yoksa_ilk_satirdir() -> None:
    assert plan_mode.plan_title("hazırlık\n\n## Adımlar\n") == "Adımlar"
    assert plan_mode.plan_title("Önce şunu yap\nsonra bunu") == "Önce şunu yap"
    assert plan_mode.plan_title("   ") == messages.PLAN_UNTITLED


# --- record_plan ---------------------------------------------------------------- #


def test_plan_kipinde_basarili_tur_plani_yazar_ve_olay_yayinlar(tmp_path: Path) -> None:
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)

    yol = plan_mode.record_plan(_outcome("# Plan\n1. a"), deps, plan_mode=True)

    assert yol is not None and yol.read_text(encoding="utf-8") == "# Plan\n1. a"
    olaylar = [e for e in sink.events if isinstance(e, PlanDrafted)]
    assert len(olaylar) == 1
    assert olaylar[0].path == str(yol) and olaylar[0].title == "Plan"


@pytest.mark.parametrize(
    ("text", "ok", "plan_flag"),
    [("# Plan", True, False), ("", True, True), ("# Plan", False, True)],
)
def test_plan_kipi_disi_bos_ya_da_basarisiz_tur_plan_yazmaz(
    tmp_path: Path, text: str, ok: bool, plan_flag: bool
) -> None:
    sink = RecordingSink()
    assert (
        plan_mode.record_plan(_outcome(text, ok=ok), _deps(tmp_path, sink), plan_mode=plan_flag)
        is None
    )
    assert not any(isinstance(e, PlanDrafted) for e in sink.events)


def test_plan_dosyasi_ayarla_kapatilabilir(tmp_path: Path) -> None:
    sink = RecordingSink()
    deps = _deps(tmp_path, sink, runtime={"plan_files": False})
    assert plan_mode.record_plan(_outcome("# Plan"), deps, plan_mode=True) is None
    assert not any(isinstance(e, PlanDrafted) for e in sink.events)


async def test_run_agent_plan_kipinde_plani_dosyaya_yazar(monkeypatch, tmp_path: Path) -> None:
    from fusion_cli.engines.agent import loop as agent_loop

    provider = ScriptedProvider([model_result("# Oturum planı\n1. Oku\n2. Yaz")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: provider)
    sink = RecordingSink()

    await run_agent("planla", _deps(tmp_path, sink, conversation_id="s-9"), plan_mode=True)

    assert plan_mode.read_plan("s-9") == "# Oturum planı\n1. Oku\n2. Yaz"
    assert any(isinstance(e, PlanDrafted) for e in sink.events)


async def test_run_agent_sonucu_plan_yolunu_tasir_dosya_kapaliyken_tasimaz(
    monkeypatch, tmp_path: Path
) -> None:
    """İnceleme bulgusu (orta): yüzeyler kartı yalnız plan GERÇEKTEN yazıldıysa açmalı.

    Ölçüldü (31 Ekim): REPL/TUI plan kipinde biten her başarılı turda pending_plan'ı
    `plan_path()` ile kuruyordu; `runtime.plan_files=false` iken ya da yazma hatasında
    kart yine çıkıyor, "Plan dosyası: <yol>" basılıyor ve kabulde model olmayan ya da
    bayat bir dosyayı uygulamaya kalkıyordu.
    """
    from fusion_cli.engines.agent import loop as agent_loop

    monkeypatch.setattr(
        agent_loop,
        "build_provider",
        lambda spec, **_: ScriptedProvider([model_result("# Plan\n1. a\n2. b")]),
    )
    acik = await run_agent(
        "planla", _deps(tmp_path, RecordingSink(), conversation_id="s-11"), plan_mode=True
    )
    assert acik.plan_path == plan_mode.plan_path("s-11") and acik.plan_path.exists()

    monkeypatch.setattr(
        agent_loop,
        "build_provider",
        lambda spec, **_: ScriptedProvider([model_result("# Plan\n1. a\n2. b")]),
    )
    kapali = await run_agent(
        "planla",
        _deps(tmp_path, RecordingSink(), conversation_id="s-12", runtime={"plan_files": False}),
        plan_mode=True,
    )
    assert kapali.ok and kapali.final_text and kapali.plan_path is None


async def test_run_agent_plan_kipi_kapaliyken_plan_yazmaz(monkeypatch, tmp_path: Path) -> None:
    from fusion_cli.engines.agent import loop as agent_loop

    provider = ScriptedProvider([model_result("cevap")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: provider)
    sink = RecordingSink()

    await run_agent("yap", _deps(tmp_path, sink, conversation_id="s-10"), plan_mode=False)

    assert plan_mode.read_plan("s-10") is None


# --- Kabul kartı (REPL) --------------------------------------------------------- #


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    durum = ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    durum.approval = ApprovalMode.PLAN
    return durum


def test_kabul_karti_secenekleri_masaustu_kartiyla_ayni_sirada() -> None:
    etiketler = [choice.value for choice in plan_card.choices()]
    assert etiketler == [
        plan_card.CHOICE_AUTO,
        plan_card.CHOICE_EDITS,
        plan_card.CHOICE_SECURITY,
        plan_card.CHOICE_KEEP_PLANNING,
    ]
    assert plan_card.mode_for(plan_card.CHOICE_AUTO) is ApprovalMode.AUTO
    assert plan_card.mode_for(plan_card.CHOICE_EDITS) is ApprovalMode.ACCEPT_EDITS
    assert plan_card.mode_for(plan_card.CHOICE_SECURITY) is ApprovalMode.SECURITY
    assert plan_card.mode_for(plan_card.CHOICE_KEEP_PLANNING) is None
    assert plan_card.mode_for(None) is None


def test_kabul_kipi_degistirir_izinleri_sifirlar_ve_uygulama_gorevi_doner(state: ReplState) -> None:
    sifirlandi: list[bool] = []
    monkeypatch_revoke = state.approval_memory.revoke
    state.approval_memory.revoke = lambda: (sifirlandi.append(True), monkeypatch_revoke())  # type: ignore[method-assign]
    yol = plan_mode.save_plan(state.conversation_id, "# Plan\n1. a")
    state.pending_plan = yol

    gorev = plan_card.accept(state, ApprovalMode.ACCEPT_EDITS)

    assert state.approval is ApprovalMode.ACCEPT_EDITS
    assert sifirlandi == [True]
    assert state.pending_plan is None
    assert gorev == messages.PLAN_IMPLEMENT_TASK.format(path=yol)


def test_planlamaya_devam_kipi_degistirmez(state: ReplState) -> None:
    state.pending_plan = plan_mode.save_plan(state.conversation_id, "# Plan")
    assert plan_card.decline(state) == messages.PLAN_KEEP_PLANNING
    assert state.approval is ApprovalMode.PLAN
    assert state.pending_plan is None


async def test_kart_etkilesimsiz_ortamda_gosterilmez_plan_bekler(
    state: ReplState, monkeypatch
) -> None:
    console = Console(record=True, width=400, force_terminal=False, no_color=True)
    state.pending_plan = plan_mode.save_plan(state.conversation_id, "# Plan")
    monkeypatch.setattr(plan_card, "pick", lambda *a, **k: pytest.fail("seçici açılmamalı"))

    gorev = await plan_card.offer(state, console, interactive=False)

    assert gorev is None
    assert state.pending_plan is None
    assert str(plan_mode.plan_path(state.conversation_id)) in console.export_text()


async def test_kart_secimi_uygulama_gorevini_dondurur(state: ReplState, monkeypatch) -> None:
    console = Console(record=True, width=400, force_terminal=False, no_color=True)
    yol = plan_mode.save_plan(state.conversation_id, "# Plan")
    state.pending_plan = yol
    monkeypatch.setattr(plan_card, "pick", lambda *a, **k: plan_card.CHOICE_AUTO)

    gorev = await plan_card.offer(state, console, interactive=True)

    assert gorev == messages.PLAN_IMPLEMENT_TASK.format(path=yol)
    assert state.approval is ApprovalMode.AUTO


async def test_kart_vazgecilince_plan_kipinde_kalir(state: ReplState, monkeypatch) -> None:
    console = Console(record=True, width=400, force_terminal=False, no_color=True)
    state.pending_plan = plan_mode.save_plan(state.conversation_id, "# Plan")
    monkeypatch.setattr(plan_card, "pick", lambda *a, **k: None)

    assert await plan_card.offer(state, console, interactive=True) is None
    assert state.approval is ApprovalMode.PLAN


# --- /plan komutu --------------------------------------------------------------- #


def test_plan_komutu_argumansiz_kipi_degistirir(state: ReplState) -> None:
    state.approval = ApprovalMode.AUTO
    command = build_registry().get("plan")
    assert command is not None
    assert command.handler(state, "") == messages.REPL_MODE_CHANGED.format(mode="plan")
    assert state.approval is ApprovalMode.PLAN


def test_plan_goster_plan_yoksa_soyler(state: ReplState) -> None:
    command = build_registry().get("plan")
    assert command is not None
    assert command.handler(state, "goster") == messages.PLAN_NONE


def test_plan_goster_plan_metnini_ve_yolunu_basar(state: ReplState) -> None:
    yol = plan_mode.save_plan(state.conversation_id, "# Plan\n1. a")
    command = build_registry().get("plan")
    assert command is not None
    cikti = command.handler(state, "goster")
    assert str(yol) in cikti and "1. a" in cikti


def test_plan_ac_editor_yoksa_yolu_soyler(state: ReplState, monkeypatch) -> None:
    yol = plan_mode.save_plan(state.conversation_id, "# Plan")
    monkeypatch.setattr(plan_card, "preferred_editor", lambda: None)
    command = build_registry().get("plan")
    assert command is not None
    assert command.handler(state, "ac") == messages.PLAN_NO_EDITOR.format(path=yol)


def test_plan_ac_editoru_plan_dosyasiyla_calistirir(state: ReplState, monkeypatch) -> None:
    yol = plan_mode.save_plan(state.conversation_id, "# Plan")
    calistirilan: list[list[str]] = []
    monkeypatch.setattr(plan_card, "preferred_editor", lambda: "nano")
    monkeypatch.setattr(plan_card, "_launch", lambda argv: calistirilan.append(argv))
    command = build_registry().get("plan")
    assert command is not None

    assert command.handler(state, "ac") == messages.PLAN_OPENED.format(editor="nano", path=yol)
    assert calistirilan == [["nano", str(yol)]]


def test_plan_bilinmeyen_alt_komut_kullanimi_soyler(state: ReplState) -> None:
    command = build_registry().get("plan")
    assert command is not None
    assert command.handler(state, "sil") == messages.PLAN_USAGE


# --- TUI kabul kartı ---------------------------------------------------------- #


async def test_tui_kabul_karti_modalda_secilir_ve_uygulama_turu_baslar(tmp_path: Path) -> None:
    import asyncio

    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.memory.factory import null_memory as _null

    from .fakes import make_config

    durum = ReplState(config=make_config(), memory=_null(), root=tmp_path, home=tmp_path)
    durum.approval = ApprovalMode.PLAN
    durum.pending_plan = plan_mode.save_plan(durum.conversation_id, "# Plan")
    session = _TuiSession(durum)
    calisan: list[str] = []

    async def sahte_tur(line: str, *, mode=None) -> None:
        calisan.append(line)

    session._turn = sahte_tur  # type: ignore[method-assign]
    gorev = asyncio.ensure_future(session._offer_plan_card())
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"
    session.tui._resolve(plan_card.CHOICE_EDITS)
    await gorev

    assert durum.approval is ApprovalMode.ACCEPT_EDITS
    assert calisan == [
        messages.PLAN_IMPLEMENT_TASK.format(path=plan_mode.plan_path(durum.conversation_id))
    ]
    assert durum.pending_plan is None


async def test_tui_kartta_vazgecilince_plan_kipinde_kalinir(tmp_path: Path) -> None:
    import asyncio

    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.memory.factory import null_memory as _null

    from .fakes import make_config

    durum = ReplState(config=make_config(), memory=_null(), root=tmp_path, home=tmp_path)
    durum.approval = ApprovalMode.PLAN
    durum.pending_plan = plan_mode.save_plan(durum.conversation_id, "# Plan")
    session = _TuiSession(durum)

    gorev = asyncio.ensure_future(session._offer_plan_card())
    await asyncio.sleep(0)
    session.tui._resolve(None)
    await gorev

    assert durum.approval is ApprovalMode.PLAN
    assert messages.PLAN_KEEP_PLANNING in session.tui.transcript
