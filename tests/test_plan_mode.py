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

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


@pytest.fixture(autouse=True)
def plans_in_tmp(tmp_path: Path, monkeypatch) -> Path:
    """Plan dosyaları kullanıcı dizinine değil tmp'ye yazılsın."""
    hedef = tmp_path / "planlar"
    monkeypatch.setattr(plan_mode, "plans_directory", lambda root=None: hedef)
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


# --- record_plan: plan yalnız exit_plan_mode ile sunulur (#317) ---------------- #


def _sun(deps: AgentDeps, plan: str) -> None:
    """Modelin `exit_plan_mode(plan)` çağrısının tura bıraktığı istek."""
    deps.tool_context.plan_mode_switch.begin_turn(plan_mode=True)
    deps.tool_context.plan_mode_switch.submit(plan)


def test_plan_kipinde_sunulan_plan_yazilir_ve_olay_yayinlanir(tmp_path: Path) -> None:
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    _sun(deps, "# Plan\n1. a")

    yol = plan_mode.record_plan(_outcome("Plan sunuldu."), deps, plan_mode=True)

    assert yol is not None and yol.read_text(encoding="utf-8") == "# Plan\n1. a"
    olaylar = [e for e in sink.events if isinstance(e, PlanDrafted)]
    assert len(olaylar) == 1
    assert olaylar[0].path == str(yol) and olaylar[0].title == "Plan"


@pytest.mark.parametrize(
    "text",
    ["# Plan\n1. a\n2. b", "1. Oku\n2. Yaz\n3. Test et", "Hangi veritabanını tercih edersin?"],
)
def test_arac_cagrilmadan_cevap_plan_sayilmaz(tmp_path: Path, text: str) -> None:
    """Claude: kart YALNIZ ExitPlanMode çağrısında açılır; başlıklı cevap bile plan değildir."""
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    deps.tool_context.plan_mode_switch.begin_turn(plan_mode=True)

    assert plan_mode.record_plan(_outcome(text), deps, plan_mode=True) is None
    assert not any(isinstance(e, PlanDrafted) for e in sink.events)
    assert plan_mode.read_plan(deps.conversation_id) is None


def test_basarisiz_tur_sunulan_plani_yazmaz(tmp_path: Path) -> None:
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    _sun(deps, "# Plan")
    assert plan_mode.record_plan(_outcome("x", ok=False), deps, plan_mode=True) is None
    assert not any(isinstance(e, PlanDrafted) for e in sink.events)


def test_yeni_plan_eskisinin_uzerine_yazilir_yedek_yok(tmp_path: Path) -> None:
    """Claude (#354): plan dosyası üzerine yazılır; `.onceki.md` yedeği yok."""
    deps = _deps(tmp_path, RecordingSink())
    _sun(deps, "# Plan v1\n1. a")
    plan_mode.record_plan(_outcome("ok"), deps, plan_mode=True)
    _sun(deps, "# Plan v2\n1. b")
    yol = plan_mode.record_plan(_outcome("ok"), deps, plan_mode=True)

    assert yol is not None and yol.read_text(encoding="utf-8") == "# Plan v2\n1. b"
    assert sorted(item.name for item in yol.parent.iterdir()) == [yol.name]


def test_plan_files_kapali_ayari_yok_sayilir(tmp_path: Path) -> None:
    """`runtime.plan_files` Claude'da yok (#354): kullanımdan kalkan ayar, plan yine yazılır."""
    sink = RecordingSink()
    deps = _deps(tmp_path, sink, runtime={"plan_files": False})
    _sun(deps, "# Plan")
    assert plan_mode.record_plan(_outcome("ok"), deps, plan_mode=True) is not None
    assert any(isinstance(e, PlanDrafted) for e in sink.events)


def _plan_sunan_saglayici(plan: str) -> ScriptedProvider:
    return ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("exit_plan_mode", plan=plan)]),
            model_result("Plan onayına sunuldu."),
        ]
    )


async def test_run_agent_exit_plan_mode_plani_dosyaya_yazar(monkeypatch, tmp_path: Path) -> None:
    from fusion_cli.engines.agent import loop as agent_loop

    provider = _plan_sunan_saglayici("# Oturum planı\n1. Oku\n2. Yaz")
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: provider)
    sink = RecordingSink()

    sonuc = await run_agent("planla", _deps(tmp_path, sink, conversation_id="s-9"), plan_mode=True)

    assert plan_mode.read_plan("s-9") == "# Oturum planı\n1. Oku\n2. Yaz\n"
    assert any(isinstance(e, PlanDrafted) for e in sink.events)
    assert sonuc.plan_path == plan_mode.plan_path("s-9")


async def test_run_agent_basliklı_cevap_araçsız_kart_acmaz(monkeypatch, tmp_path: Path) -> None:
    from fusion_cli.engines.agent import loop as agent_loop

    provider = ScriptedProvider([model_result("# Soru\nHangi veritabanı?")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: provider)

    sonuc = await run_agent(
        "planla", _deps(tmp_path, RecordingSink(), conversation_id="s-13"), plan_mode=True
    )

    assert sonuc.plan_path is None and plan_mode.read_plan("s-13") is None


async def test_exit_plan_mode_plan_kipi_disinda_hata_verir(tmp_path: Path) -> None:
    from fusion_cli.tools.plan_tools import exit_plan_mode_tool

    context = ToolContext(root=tmp_path)
    sonuc = await exit_plan_mode_tool({"plan": "# P"}, context)
    assert not sonuc.ok and context.plan_mode_switch.submitted_plan is None


async def test_enter_plan_mode_kalan_cagrilarda_duzenlemeyi_engeller(
    monkeypatch, tmp_path: Path
) -> None:
    """Claude EnterPlanMode (#324): model kendini plan kipine geçirir, sonra düzenleme yok."""
    from fusion_cli.engines.agent import loop as agent_loop

    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("enter_plan_mode")]),
            model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
            model_result("Plan kipindeyim."),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        conversation_id="s-14",
    )

    await run_agent("önce planla sonra yap", deps)

    assert not (tmp_path / "a.txt").exists()
    assert deps.tool_context.plan_mode_switch.take_enter() is True


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


def test_kabul_karti_claude_uclusu(state: ReplState) -> None:
    """Claude Code üçlüsü: 'Yes, and use auto mode' / 'Yes, manually approve edits' /
    'No, keep planning' (#325)."""
    etiketler = [choice.value for choice in plan_card.choices(state)]
    assert etiketler == [
        plan_card.CHOICE_AUTO,
        plan_card.CHOICE_SECURITY,
        plan_card.CHOICE_KEEP_PLANNING,
    ]
    assert plan_card.mode_for(plan_card.CHOICE_AUTO) is ApprovalMode.AUTO
    assert plan_card.mode_for(plan_card.CHOICE_EDITS) is ApprovalMode.ACCEPT_EDITS
    assert plan_card.mode_for(plan_card.CHOICE_BYPASS) is ApprovalMode.BYPASS
    assert plan_card.mode_for(plan_card.CHOICE_SECURITY) is ApprovalMode.SECURITY
    assert plan_card.mode_for(plan_card.CHOICE_KEEP_PLANNING) is None
    assert plan_card.mode_for(None) is None


def test_otomatik_kip_yoksa_duzenlemeleri_kabul_secenegi(state: ReplState) -> None:
    from dataclasses import replace

    state.config = replace(
        state.config, agent_launch=replace(state.config.agent_launch, disable_auto_mode=True)
    )
    ilk = plan_card.choices(state)[0]
    assert ilk.value == plan_card.CHOICE_EDITS and ilk.label == messages.PLAN_CARD_EDITS


def test_bypass_kullanilabilirse_bypass_secenegi(state: ReplState) -> None:
    state.bypass_available = True
    ilk = plan_card.choices(state)[0]
    assert ilk.value == plan_card.CHOICE_BYPASS and ilk.label == messages.PLAN_CARD_BYPASS


def test_kabul_kipi_degistirir_izinleri_sifirlamaz_ve_ad_verir(state: ReplState) -> None:
    sifirlandi: list[bool] = []
    state.approval_memory.revoke = lambda: sifirlandi.append(True)  # type: ignore[method-assign]
    yol = plan_mode.save_plan(state.conversation_id, "# Giriş sayfası yenileme\n1. a")
    state.pending_plan = yol

    gorev = plan_card.accept(state, ApprovalMode.ACCEPT_EDITS)

    assert state.approval is ApprovalMode.ACCEPT_EDITS
    assert sifirlandi == [], "Claude belgesinde onayda izin sıfırlama yok"
    assert state.pending_plan is None
    assert gorev == messages.PLAN_IMPLEMENT_TASK.format(path=yol)
    assert state.conversation_name == "Giriş sayfası yenileme"


def test_adli_oturumun_adi_degismez(state: ReplState) -> None:
    state.conversation_name = "benim"
    state.pending_plan = plan_mode.save_plan(state.conversation_id, "# Başka")
    plan_card.accept(state, ApprovalMode.AUTO)
    assert state.conversation_name == "benim"


def _claude_settings(data: dict) -> None:
    import json
    import os

    folder = Path(os.environ["CLAUDE_CONFIG_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def test_baglami_temizleme_secenegi_yalniz_ayar_acikken_basta(state: ReplState) -> None:
    """Claude `showClearContextOnPlanAccept` (varsayılan false) başa "bağlamı temizle" ekler."""
    assert all(not plan_card.clears_context(c.value) for c in plan_card.choices(state))
    _claude_settings({"showClearContextOnPlanAccept": True})

    secenekler = plan_card.choices(state)

    assert secenekler[0].value == plan_card.CLEAR_PREFIX + plan_card.CHOICE_AUTO
    assert secenekler[0].label == "Evet, bağlamı temizle ve otomatik kipi kullan"
    assert [c.value for c in secenekler[1:]] == [
        plan_card.CHOICE_AUTO,
        plan_card.CHOICE_SECURITY,
        plan_card.CHOICE_KEEP_PLANNING,
    ]
    assert plan_card.mode_for(secenekler[0].value) is ApprovalMode.AUTO


def test_baglami_temizleyerek_kabul_gecmisi_siler(state: ReplState) -> None:
    from fusion_cli.core.types import Message

    state.history = [Message("user", "planla"), Message("assistant", "plan")]
    state.pending_plan = plan_mode.save_plan(state.conversation_id, "# Plan\n1. a")

    gorev = plan_card.accept(state, ApprovalMode.AUTO, clear=True)

    assert state.history == [] and state.approval is ApprovalMode.AUTO
    assert "Plan" in gorev or str(plan_mode.plan_path(state.conversation_id, state.root)) in gorev


def test_masaustu_plan_karti_ayni_secenekler_ve_kabul(state: ReplState) -> None:
    from dataclasses import replace

    from fusion_cli.appserver.plan_routes import plan_accept, plan_card_payload

    assert plan_card_payload(state)["bekliyor"] is False
    state.config = replace(
        state.config, agent_launch=replace(state.config.agent_launch, disable_auto_mode=True)
    )
    state.pending_plan = plan_mode.save_plan(state.conversation_id, "# Plan\n1. a")

    kart = plan_card_payload(state)

    assert kart["bekliyor"] is True
    assert kart["secenekler"][0]["deger"] == plan_card.CHOICE_EDITS
    assert kart["onerilen"] == messages.PLAN_CARD_EDITS
    assert plan_accept(state, {"deger": plan_card.CHOICE_AUTO})["ok"] is False  # kartta yok
    sonuc = plan_accept(state, {"deger": plan_card.CHOICE_EDITS})
    assert sonuc["ok"] and sonuc["kip"] == ApprovalMode.ACCEPT_EDITS.value
    assert sonuc["temizle"] is False and "gorev" in sonuc
    assert state.approval is ApprovalMode.ACCEPT_EDITS and state.pending_plan is None


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


def test_plan_aciklamasi_plan_kipinde_gorevi_baslatir(state: ReplState) -> None:
    """Claude (#75): `/plan [description]` plan kipine geçer ve açıklamayı ilk istem yapar."""
    state.approval = ApprovalMode.AUTO
    command = build_registry().get("plan")
    assert command is not None
    command.handler(state, "giriş akışını yeniden tasarla")
    assert state.approval is ApprovalMode.PLAN
    assert state.pending_task == "giriş akışını yeniden tasarla"


def test_plan_tek_sozcuk_aciklama_da_gorev_olur(state: ReplState) -> None:
    """Eski "bilinmeyen alt komut → kullanım" davranışı Claude'da yok (#327)."""
    command = build_registry().get("plan")
    assert command is not None
    command.handler(state, "sil")
    assert state.pending_task == "sil" and state.approval is ApprovalMode.PLAN


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


def test_plan_aciklama_plan_kipine_gecip_gorevi_baslatir(state: ReplState) -> None:
    """Claude Code `/plan fix the auth bug`: plan kipine geçer ve görevle hemen başlar (#327)."""
    state.approval = ApprovalMode.AUTO
    cikti = plan_card.command(state, "giriş hatasını düzelt")
    assert state.approval is ApprovalMode.PLAN
    assert state.pending_task == "giriş hatasını düzelt"
    assert ApprovalMode.PLAN.value in cikti


def test_plan_argumansiz_yalniz_kipe_gecer(state: ReplState) -> None:
    state.approval = ApprovalMode.AUTO
    plan_card.command(state, "")
    assert state.approval is ApprovalMode.PLAN and not state.pending_task


async def test_kartta_ctrl_g_plani_editorde_acar_ve_karti_yeniden_gosterir(
    state: ReplState, monkeypatch
) -> None:
    """Claude Code: onay kartı açıkken Ctrl+G planı varsayılan editörde açar (#326)."""
    console = Console(record=True, width=400, force_terminal=False, no_color=True)
    yol = plan_mode.save_plan(state.conversation_id, "# Plan")
    state.pending_plan = yol
    secimler = iter([plan_card.CHOICE_EDIT_PLAN, plan_card.CHOICE_AUTO])
    gorulen: list[dict] = []

    def _sec(*_a, hotkeys=None, **_k):
        gorulen.append(dict(hotkeys or {}))
        return next(secimler)

    acilan: list[list[str]] = []
    monkeypatch.setattr(plan_card, "pick", _sec)
    monkeypatch.setattr(plan_card, "preferred_editor", lambda: "nano")
    monkeypatch.setattr(plan_card, "_launch", acilan.append)

    gorev = await plan_card.offer(state, console, interactive=True)

    assert acilan == [["nano", str(yol)]]
    assert gorulen == [{"c-g": plan_card.CHOICE_EDIT_PLAN}] * 2
    assert gorev == messages.PLAN_IMPLEMENT_TASK.format(path=yol)
    assert state.approval is ApprovalMode.AUTO


def test_plan_dosyalari_claude_plans_altinda_ve_plansdirectory(tmp_path, monkeypatch) -> None:
    """Claude Code: varsayılan ~/.claude/plans; `plansDirectory` proje köküne göre (#354)."""
    import json

    from fusion_cli.config import plans_location

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    proje = tmp_path / "proje"
    proje.mkdir()
    assert plans_location.plans_directory(proje) == tmp_path / "claude" / "plans"
    monkeypatch.setattr(
        "fusion_cli.config.claude_settings.is_project_settings_trusted", lambda _r: True
    )
    (proje / ".claude").mkdir()
    (proje / ".claude" / "settings.json").write_text(
        json.dumps({"plansDirectory": "./planlar"}), encoding="utf-8"
    )
    assert plans_location.plans_directory(proje) == proje / "planlar"


def test_eski_fusion_plan_dizini_okuma_yedegi(tmp_path, monkeypatch) -> None:
    from fusion_cli.config.paths import plans_dir

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    eski = plans_dir() / "eski.md"
    eski.parent.mkdir(parents=True, exist_ok=True)
    eski.write_text("# Eski plan", encoding="utf-8")
    assert plan_mode.read_plan("eski", tmp_path) == "# Eski plan"
