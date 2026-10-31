"""`/goal <koşul>`: turlar arası hedef, tur sonu değerlendirici, otomatik devam (P-058).

Ölçüldü (31 Ekim): `/goal` yalnız tek turluk "pes etme" kipiydi; kalıcı koşul, tur sonu
değerlendirici, İmkânsız çıkışı, danışma (check-in) ve `--resume` ile geri gelme yoktu.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.cli.repl import goal_flow, goal_store, macros
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.session_goal import (
    MAX_CONDITION_CHARS,
    GoalAction,
    GoalError,
    GoalVerdict,
    PauseReason,
    SessionGoal,
    decide,
    new_goal,
    parse_verdict,
    resume,
)
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import goal_judge
from fusion_cli.engines.agent.goal_judge import GoalJudgement, goal_transcript, parse_judgement
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages

from .fakes import make_config


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    config = make_config()
    from dataclasses import replace

    config = replace(config, memory_dir=tmp_path / "bellek")
    return ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")


def _goal(state: ReplState, argument: str) -> str:
    command = build_registry().get("goal")
    assert command is not None
    return command.handler(state, argument)


def _sahte_yargic(*kararlar: GoalVerdict):
    sira = list(kararlar)
    cagrilar: list[str] = []

    async def yargic(condition, history, config, publisher):
        cagrilar.append(condition)
        return GoalJudgement(sira.pop(0), f"gerekçe {len(cagrilar)}")

    return yargic, cagrilar


# --- Karar makinesi ---------------------------------------------------------- #


def test_yeni_hedef_bos_ve_tavani_asan_kosulu_reddeder():
    with pytest.raises(GoalError):
        new_goal("  ", now=0, checkin_minutes=30)
    with pytest.raises(GoalError):
        new_goal("x" * (MAX_CONDITION_CHARS + 1), now=0, checkin_minutes=30)


def test_karar_tamam_ve_imkansiz_hedefi_kapatir():
    goal = new_goal("testler geçiyor", now=0, checkin_minutes=30)
    assert decide(goal, GoalVerdict.MET, "ok", now=1, max_auto_turns=5).goal is None
    adim = decide(goal, GoalVerdict.IMPOSSIBLE, "erişim yok", now=1, max_auto_turns=5)
    assert adim.goal is None and adim.action is GoalAction.IMPOSSIBLE


def test_henuz_degil_devam_eder_ve_tavanda_duraklar():
    goal = new_goal("k", now=0, checkin_minutes=0)
    adim = decide(goal, GoalVerdict.NOT_MET, "", now=1, max_auto_turns=2)
    assert adim.action is GoalAction.CONTINUE and adim.goal is not None
    adim = decide(adim.goal, GoalVerdict.NOT_MET, "", now=2, max_auto_turns=2)
    assert adim.action is GoalAction.CONTINUE and adim.goal is not None
    adim = decide(adim.goal, GoalVerdict.NOT_MET, "", now=3, max_auto_turns=2)
    assert adim.action is GoalAction.PAUSED
    assert adim.goal is not None and adim.goal.paused is PauseReason.TURN_LIMIT


def test_danisma_zamani_duraklatir_ve_devamda_aralik_katlanir():
    goal = new_goal("k", now=0, checkin_minutes=30)
    adim = decide(goal, GoalVerdict.NOT_MET, "", now=30 * 60, max_auto_turns=50)
    assert adim.goal is not None and adim.goal.paused is PauseReason.CHECKIN
    surdu = resume(adim.goal, now=30 * 60)
    assert surdu.is_active
    assert surdu.checkin_interval_s == 60 * 60
    assert surdu.next_checkin_at == 90 * 60


def test_belirsiz_karar_otomatik_devam_etmez():
    goal = new_goal("k", now=0, checkin_minutes=30)
    adim = decide(goal, GoalVerdict.UNKNOWN, "yanıt yok", now=1, max_auto_turns=5)
    assert adim.action is GoalAction.PAUSED
    assert adim.goal is not None and adim.goal.paused is PauseReason.UNKNOWN_VERDICT


def test_hedef_kaydi_gidis_donus_ve_bozuk_kayit():
    goal = decide(
        new_goal("k", now=5, checkin_minutes=30),
        GoalVerdict.NOT_MET,
        "neden",
        now=6,
        max_auto_turns=5,
    ).goal
    assert goal is not None
    assert SessionGoal.from_dict(json.loads(json.dumps(goal.to_dict()))) == goal
    assert SessionGoal.from_dict({"kosul": "x"}) is None


@pytest.mark.parametrize(
    ("metin", "karar"),
    [
        ("tamam", GoalVerdict.MET),
        ("Met", GoalVerdict.MET),
        ("henuz_degil", GoalVerdict.NOT_MET),
        ("not yet met", GoalVerdict.NOT_MET),
        ("İmkânsız", GoalVerdict.IMPOSSIBLE),
        ("belki", GoalVerdict.UNKNOWN),
    ],
)
def test_karar_sozcukleri_cozulur(metin, karar):
    assert parse_verdict(metin) is karar


# --- Değerlendirici ---------------------------------------------------------- #


def test_degerlendirici_json_kararini_okur_bozuksa_belirsiz():
    karar = parse_judgement('Düşündüm.\n{"karar": "tamam", "gerekce": "testler yeşil"}')
    assert karar == GoalJudgement(GoalVerdict.MET, "testler yeşil")
    assert parse_judgement("bilmiyorum").verdict is GoalVerdict.UNKNOWN
    assert parse_judgement("{bozuk").verdict is GoalVerdict.UNKNOWN


def test_degerlendirme_kaydi_sistem_mesajini_atlar_ve_kisaltir():
    gecmis = [
        Message("system", "GİZLİ SİSTEM"),
        Message("user", "testleri düzelt"),
        Message("assistant", "x" * 5_000),
    ]
    kayit = goal_transcript(gecmis)
    assert "GİZLİ" not in kayit
    assert "[KULLANICI] testleri düzelt" in kayit
    assert len(kayit) < 2_000


async def test_degerlendirici_saglayici_hatasinda_belirsiz_doner(monkeypatch):
    from fusion_cli.core.errors import ProviderError

    def patlayan(*args, **kwargs):
        raise ProviderError("anahtar yok")

    monkeypatch.setattr(goal_judge, "build_provider", patlayan)
    karar = await goal_judge.judge_goal("k", [], make_config())
    assert karar.verdict is GoalVerdict.UNKNOWN


async def test_degerlendirici_hakem_modeline_kosulu_ve_kaydi_verir(monkeypatch):
    istekler = []

    class Saglayici:
        async def complete(self, request):
            istekler.append(request)
            return SimpleNamespace(ok=True, text='{"karar":"henuz_degil","gerekce":"test kırık"}')

    monkeypatch.setattr(goal_judge, "build_provider", lambda *a, **k: Saglayici())
    karar = await goal_judge.judge_goal(
        "tüm testler geçiyor", [Message("assistant", "1 test kırık")], make_config()
    )
    assert karar == GoalJudgement(GoalVerdict.NOT_MET, "test kırık")
    istem = istekler[0].messages[0].content
    assert "tüm testler geçiyor" in istem and "1 test kırık" in istem


# --- Komut --------------------------------------------------------------------- #


def test_goal_kosulu_kurar_ilk_turu_hedef_kipinde_hazirlar_ve_kaydeder(state):
    mesaj = _goal(state, "tüm testler geçiyor")

    assert "Hedef kuruldu" in mesaj
    assert state.goal is not None and state.goal.condition == "tüm testler geçiyor"
    assert state.take_pending() == ("tüm testler geçiyor", macros.Mode.GOAL)
    assert goal_store.load(state.config.memory_dir, state.conversation_id) == state.goal


def test_goal_argumansiz_durum_soyler_clear_kapatir(state):
    assert _goal(state, "") == messages.GOAL_NONE
    _goal(state, "lint temiz")
    state.take_pending()
    assert "lint temiz" in _goal(state, "durum")
    assert "bırakıldı" in _goal(state, "clear")
    assert state.goal is None
    assert goal_store.load(state.config.memory_dir, state.conversation_id) is None


def test_goal_devam_duraklatilan_hedefi_surdurur(state):
    _goal(state, "lint temiz")
    state.take_pending()
    assert state.goal is not None
    from dataclasses import replace

    state.goal = replace(state.goal, paused=PauseReason.TURN_LIMIT, auto_turns=7)
    mesaj = _goal(state, "devam")

    assert "sürdürülüyor" in mesaj
    assert state.goal.is_active and state.goal.auto_turns == 0
    gorev, kip = state.take_pending()
    assert "lint temiz" in gorev and kip is macros.Mode.GOAL


# --- Akış ---------------------------------------------------------------------- #


async def test_akis_henuz_degilde_devam_turu_calistirir_tamamda_kapanir(state):
    _goal(state, "testler geçiyor")
    state.take_pending()
    yargic, cagrilar = _sahte_yargic(GoalVerdict.NOT_MET, GoalVerdict.MET)
    turlar: list[str] = []
    yazilan: list[str] = []

    async def tur(gorev: str) -> bool:
        turlar.append(gorev)
        return True

    await goal_flow.drive_goal(state, tur, yazilan.append, judge=yargic)

    assert len(cagrilar) == 2
    assert len(turlar) == 1 and "testler geçiyor" in turlar[0] and "gerekçe 1" in turlar[0]
    assert state.goal is None
    assert yazilan[-1].startswith("✓ Hedef karşılandı")


async def test_akis_imkansizda_tur_baslatmaz(state):
    _goal(state, "uçan araba")
    state.take_pending()
    yargic, _ = _sahte_yargic(GoalVerdict.IMPOSSIBLE)
    turlar: list[str] = []

    async def tur(gorev: str) -> bool:
        turlar.append(gorev)
        return True

    yazilan: list[str] = []
    await goal_flow.drive_goal(state, tur, yazilan.append, judge=yargic)
    assert turlar == [] and state.goal is None
    assert yazilan[0].startswith("✗ Hedef karşılanamıyor")


async def test_akis_kullanici_mesaji_bekliyorsa_devam_etmez(state):
    _goal(state, "k")
    state.take_pending()
    yargic, _ = _sahte_yargic(GoalVerdict.NOT_MET)
    turlar: list[str] = []

    async def tur(gorev: str) -> bool:
        turlar.append(gorev)
        return True

    yazilan: list[str] = []
    await goal_flow.drive_goal(state, tur, yazilan.append, judge=yargic, should_yield=lambda: True)
    assert turlar == [] and state.goal is not None and state.goal.is_active
    assert yazilan[-1] == messages.GOAL_WAITING_USER


async def test_akis_iptal_edilen_devam_turunda_durur(state):
    _goal(state, "k")
    state.take_pending()
    yargic, cagrilar = _sahte_yargic(GoalVerdict.NOT_MET, GoalVerdict.NOT_MET)

    async def tur(gorev: str) -> bool:
        return False

    await goal_flow.drive_goal(state, tur, lambda _m: None, judge=yargic)
    assert len(cagrilar) == 1


async def test_duraklatilmis_hedef_degerlendirilmez(state):
    _goal(state, "k")
    state.take_pending()
    from dataclasses import replace

    assert state.goal is not None
    state.goal = replace(state.goal, paused=PauseReason.CHECKIN)
    yargic, cagrilar = _sahte_yargic()
    assert await goal_flow.evaluate_goal(state, judge=yargic) is None
    assert cagrilar == []


# --- Satır-içi REPL ------------------------------------------------------------ #


async def test_satir_ici_repl_turdan_sonra_hedefi_surdurur(state, monkeypatch):
    from rich.console import Console

    from fusion_cli.cli.repl import loop
    from fusion_cli.core.concurrency import BackgroundTasks

    _goal(state, "testler geçiyor")
    state.take_pending()
    yargic, _ = _sahte_yargic(GoalVerdict.NOT_MET, GoalVerdict.MET)
    monkeypatch.setattr(loop, "judge_goal", yargic)
    turlar: list[tuple[str, macros.Mode]] = []

    async def sahte_tur(line, st, console, background, *, mode=macros.Mode.NONE):
        turlar.append((line, mode))
        return True

    monkeypatch.setattr(loop, "_run_turn", sahte_tur)
    await loop._continue_goal(state, Console(record=True), BackgroundTasks())

    assert [kip for _, kip in turlar] == [macros.Mode.GOAL]
    assert state.goal is None


# --- Masaüstü ------------------------------------------------------------------ #


async def test_masaustu_tur_sonucu_hedef_ve_devam_gorevi_tasir(tmp_path, monkeypatch):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    yakalanan: dict = {}

    async def sahte_gorev(task, config, **kwargs):
        yakalanan.setdefault("adim", []).append(kwargs.get("step_limit"))
        return SimpleNamespace(ok=True, final_text="bir test kırık", messages=[])

    async def yargic(condition, history, config, publisher):
        return GoalJudgement(GoalVerdict.NOT_MET, "bir test kırık")

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", sahte_gorev)
    monkeypatch.setattr(goal_flow, "judge_goal", yargic)

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "goal", "arguman": "testler geçiyor"})
    )
    komut = _sonuc(satirlar, "1")
    assert komut["gorev"] == "testler geçiyor"

    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": komut["gorev"]}))
    tur = _sonuc(satirlar, "2")

    assert tur["hedef"]["eylem"] == "devam"
    assert "bir test kırık" in tur["hedef_devam"]
    assert oturum._next_turn_mode is macros.Mode.GOAL


def _sonuc(satirlar: list[str], kimlik: str) -> dict:
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(kimlik)


async def test_masaustu_durdur_degerlendirmeyi_keser_hedef_etkin_kalir(tmp_path, monkeypatch):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    basladi = asyncio.Event()

    async def sahte_gorev(task, config, **kwargs):
        return SimpleNamespace(ok=True, final_text="ilerliyor", messages=[])

    async def yavas_yargic(condition, history, config, publisher):
        basladi.set()
        await asyncio.sleep(30)
        return GoalJudgement(GoalVerdict.MET, "")

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", sahte_gorev)
    monkeypatch.setattr(goal_flow, "judge_goal", yavas_yargic)

    await oturum.handle(Request(id="1", name="komut.calistir", data={"ad": "goal", "arguman": "k"}))
    tur = asyncio.ensure_future(
        oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "k"}))
    )
    await asyncio.wait_for(basladi.wait(), 5)
    await oturum.handle(Request(id="3", name="tur.kes", data={}))
    await asyncio.wait_for(tur, 5)

    assert _sonuc(satirlar, "3")["ok"] is True
    sonuc = _sonuc(satirlar, "2")
    assert sonuc["hedef"]["eylem"] == "durduruldu"
    assert "hedef_devam" not in sonuc
    assert oturum._state.goal is not None and oturum._state.goal.is_active


# --- Tam ekran TUI ------------------------------------------------------------- #


async def test_tui_hedef_devam_turunu_hedef_kipinde_kosar(state, monkeypatch):
    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.engines.agent import AgentOutcome

    _goal(state, "testler geçiyor")
    state.take_pending()
    session = _TuiSession(state)
    calls: list[dict[str, object]] = []

    async def sahte(task, config, **kwargs):
        calls.append({"task": task, **kwargs})
        return AgentOutcome("bitti", [], 0, ok=True)

    yargic, _ = _sahte_yargic(GoalVerdict.NOT_MET, GoalVerdict.MET)
    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", sahte)
    monkeypatch.setattr(goal_flow, "judge_goal", yargic)

    await session._continue_goal()

    assert len(calls) == 1
    assert calls[0]["step_limit"] == macros.MODE_STEP_LIMITS[macros.Mode.GOAL]
    assert "testler geçiyor" in str(calls[0]["task"])
    assert state.goal is None


def test_resume_hedefi_kayittan_geri_getirir(state):
    _goal(state, "dağıtım yeşil")
    kayitli = state.goal
    yeni = ReplState(
        config=state.config,
        memory=null_memory(),
        root=state.root,
        home=state.home,
        conversation_id=state.conversation_id,
    )
    assert goal_store.load(yeni.config.memory_dir, yeni.conversation_id) == kayitli
