"""Ink-benzeri tek yol REPL döngüsü — komut yönlendirme, önizleme ve prompter."""

from __future__ import annotations

import asyncio
import contextlib

from fusion_cli.cli.repl.state import Engine, ReplState
from fusion_cli.cli.repl.tui import FusionTui
from fusion_cli.cli.repl.tui_loop import TuiPrompter, _preview, _TuiSession
from fusion_cli.core.tools import AuthorizationScope, ToolEffect
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalRequest
from fusion_cli.engines.agent.engine_tools import QuestionOption
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path) -> ReplState:
    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)


class _Tool:
    name = "run_shell"


def test_onay_onizlemesi_tehlike_gerekcesini_gosterir():
    request = ApprovalRequest(tool=_Tool(), args={"command": "rm -rf /"}, danger="kök silme")

    metin = _preview(request)

    assert "run_shell(" in metin and "kök silme" in metin


def test_onay_onizlemesi_tehlikesizde_gerekce_yok():
    request = ApprovalRequest(tool=_Tool(), args={"command": "ls"}, danger=None)

    metin = _preview(request)

    assert "run_shell(" in metin


def _noop_tui() -> FusionTui:
    return FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )


async def test_prompter_confirm_modali_e_ile_true_doner():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.confirm(ApprovalRequest(tool=_Tool(), args={}, danger=None))
    )
    await asyncio.sleep(0)

    tui._resolve("once")

    assert await task is ApprovalAnswer.ONCE


async def test_prompter_confirm_sonrasi_onceki_calisma_satirini_geri_getirir():
    tui = _noop_tui()
    tui.set_work_source(lambda: "hazırlanıyor…")
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.confirm(ApprovalRequest(tool=_Tool(), args={}, danger=None))
    )
    await asyncio.sleep(0)
    tui._resolve("once")
    await task

    assert "hazırlanıyor…" in tui._work_now()


async def test_prompter_tehlikesiz_istekte_oturum_secimi_sunar():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.confirm(ApprovalRequest(tool=_Tool(), args={}, danger=None))
    )
    await asyncio.sleep(0)

    assert tui._mode == "choice"
    # P-003: tehlikesiz yerel istekte "bir daha sorma" (always) kalıcı kuralı da sunulur.
    assert [choice.value for choice in tui._choices] == ["once", "session", "always", "deny"]
    tui._resolve("session")
    assert await task is ApprovalAnswer.SESSION


async def test_prompter_yikici_istekte_oturum_secimi_sunmaz():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.confirm(ApprovalRequest(tool=_Tool(), args={}, danger="riskli"))
    )
    await asyncio.sleep(0)

    # Tehlikede öntanımlı (ilk) seçenek RED'dir (L1-01).
    assert [choice.value for choice in tui._choices] == ["deny", "once"]
    tui._resolve("deny")
    assert await task is ApprovalAnswer.DENY


async def test_remote_without_verified_scope_never_offers_session_permission():
    """CLI, masaüstüyle aynı kapsam kuralını kullanır."""
    tui = _noop_tui()
    tool = _Tool()
    tool.name = "remote_write"
    request = ApprovalRequest(tool=tool, args={}, danger=None, effect=ToolEffect.REMOTE_WRITE)
    task = asyncio.create_task(TuiPrompter(tui, None).confirm(request))
    await asyncio.sleep(0)
    try:
        assert [choice.value for choice in tui._choices] == ["once", "deny"]
    finally:
        tui._resolve("deny")
        await task


async def test_remote_session_permission_displays_scope_in_terminal():
    tui = _noop_tui()
    tool = _Tool()
    tool.name = "remote_write"
    request = ApprovalRequest(
        tool=tool,
        args={},
        danger=None,
        effect=ToolEffect.REMOTE_WRITE,
        authorization_scope=AuthorizationScope("docs", "work", "update", ("doc-42",)),
    )
    task = asyncio.create_task(TuiPrompter(tui, None).confirm(request))
    await asyncio.sleep(0)
    try:
        choice = next(choice for choice in tui._choices if choice.value == "session")
        assert all(value in choice.description for value in ("docs", "work", "update", "doc-42"))
    finally:
        tui._resolve("deny")
        await task


async def test_prompter_ask_metni_doner():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(prompter.ask("hangi dosya?"))
    await asyncio.sleep(0)
    tui._resolve("src/app.py")

    assert await task == "src/app.py"


async def test_prompter_ask_onerilen_secenek_ve_diger_sunar():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.ask(
            "hangi renk?",
            (
                QuestionOption("mavi", "Sakin görünür."),
                QuestionOption("kırmızı", "Daha canlıdır."),
            ),
            "mavi",
        )
    )
    await asyncio.sleep(0)

    assert tui._mode == "choice"
    assert [choice.value for choice in tui._choices] == ["mavi", "kırmızı", "__other__"]
    assert "önerilen" in tui._choices[0].description.lower()
    tui._resolve("mavi")
    assert await task == "mavi"


async def test_prompter_ask_diger_secilince_serbest_metin_alir():
    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.ask("hangisi?", (QuestionOption("A", "İlk seçenek."),), "A")
    )
    await asyncio.sleep(0)
    tui._resolve("__other__")
    await asyncio.sleep(0)

    assert tui._mode == "ask"
    tui._resolve("kendi cevabım")
    assert await task == "kendi cevabım"


async def test_bilinmeyen_komut_uyarir(tmp_path):
    session = _TuiSession(_state(tmp_path))

    await session._command("/olmayan")

    assert "bilinmeyen komut" in session.tui.transcript.lower()


async def test_agent_fusion_komutu_motoru_degistirir(tmp_path):
    state = _state(tmp_path)
    session = _TuiSession(state)

    await session._command("/fusion")
    assert state.engine is Engine.FUSION

    await session._command("/agent")
    assert state.engine is Engine.AGENT


async def test_argumansiz_secici_komut_yonlendirir(tmp_path):
    """TUI çalışırken iç içe seçici açılmaz; argümansız /mode, uygulama-içi modal açar."""
    session = _TuiSession(_state(tmp_path))

    gorev = asyncio.ensure_future(session._command("/mode"))
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"
    session.tui._resolve(None)
    await gorev


def test_would_open_picker_nested_secici_komutlarini_yakalar():
    from fusion_cli.cli.repl.tui_loop import _would_open_picker

    assert _would_open_picker("development", "x")
    # #211: argümansız /model modal açar; /provider, /verify, /profiles edit de modalla çözülür.
    assert not _would_open_picker("model", "")
    assert not _would_open_picker("provider", "")
    assert not _would_open_picker("verify", "")
    assert not _would_open_picker("profiles", "edit code")
    assert _would_open_picker("providers", "add")
    # mode/level/effort uygulama-içi modalla çözülür; guard'lanmaz.
    assert not _would_open_picker("mode", "")
    assert not _would_open_picker("level", "")


async def test_provider_komutu_uygulama_ici_modalla_cozulur(tmp_path):
    """L2-14: /provider artık engellenmez; TUI modalı açılır, esc vazgeçmektir."""
    session = _TuiSession(_state(tmp_path))

    gorev = asyncio.ensure_future(session._command("/provider"))
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"
    session.tui._resolve(None)
    await gorev

    assert "argüman ister" not in session.tui.transcript
    assert "seçim yapılmadı" in session.tui.transcript


async def test_model_argumansiz_model_seciciyi_acar(tmp_path):
    """Claude Code ModelPicker (#211): argümansız /model uygulama içi seçiciyi açar."""
    state = _state(tmp_path)
    session = _TuiSession(state)

    gorev = asyncio.ensure_future(session._command("/model"))
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"
    assert session.tui._choice_alt_keys == ("s", "left", "right")
    session.tui._resolve(None)
    await gorev

    assert "argüman ister" not in session.tui.transcript
    assert "seçim yapılmadı" in session.tui.transcript


async def test_mode_komutu_uygulama_ici_secimle_uygulanir(tmp_path):
    """/mode uygulama-içi seçim açar; seçilen değer handler'a argüman olarak uygulanır."""
    state = _state(tmp_path)
    session = _TuiSession(state)

    task = asyncio.ensure_future(session._command("/mode"))
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"  # nested picker DEĞİL, uygulama-içi modal

    session.tui._resolve("auto")  # ilk seçenek: auto kipi
    await task

    assert state.auto_profile is True


async def test_mesgulken_gonderi_kuyruga_alinir(tmp_path):
    """Tur çalışırken yazılan mesaj SESSİZCE DÜŞMEZ; kuyruğa alınır ve bildirilir."""
    session = _TuiSession(_state(tmp_path))

    async def _bekle() -> None:
        await asyncio.sleep(10)

    session._task = asyncio.ensure_future(_bekle())
    session._submit("ikinci mesaj")

    assert session._queue == ["ikinci mesaj"]
    assert "sıraya alındı" in session.tui.transcript
    session._task.cancel()


async def test_kuyruk_tur_bitince_islenir(tmp_path):
    """Bir tur bitince kuyruktaki sonraki satır kendiliğinden işlenir."""
    state = _state(tmp_path)
    session = _TuiSession(state)
    session._queue = ["/agent"]

    await session._handle("/fusion")  # bu tur biter, finally kuyruğu boşaltır
    assert state.engine is Engine.FUSION

    assert session._task is not None
    await session._task  # kuyruktan gelen /agent
    assert state.engine is Engine.AGENT


def test_mesgulken_yeni_satir_gorev_baslatmaz(tmp_path):
    session = _TuiSession(_state(tmp_path))

    async def _bekleyen() -> None:
        await asyncio.sleep(10)

    async def _dene() -> None:
        session._task = asyncio.ensure_future(_bekleyen())
        session._submit("yeni görev")  # meşgulken yok sayılmalı
        assert session._task is not None
        # Aynı görev; yenisi başlatılmadı.
        mevcut = session._task
        session._submit("bir daha")
        assert session._task is mevcut
        session._task.cancel()

    asyncio.run(_dene())


# --- /undo TUI'de çalışmıyordu --------------------------------------------- #
#
# Ölçüldü: kullanıcı bir CSS düzeltmesini geri almak istedi, `/undo` "geri
# alınacak değişiklik yok" dedi — oysa dosya gerçekten değişmişti. Sebep:
# değişiklik kümesi YALNIZCA eski satır-içi REPL'de saklanıyordu; varsayılan
# olan TUI hiç saklamıyordu. Araç bağlamı `run_agent_task` içinde gizlice
# kuruluyor ve çağıranın elinde hiçbir referans kalmıyordu.


async def test_agent_turu_verilen_arac_baglamini_kullanir(tmp_path):
    """Çağıran bağlam verdiyse o kullanılmalı; yoksa `/undo` bağlanamaz."""
    from fusion_cli.cli.session import run_agent_task
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import loop as agent_loop

    from .fakes import ScriptedProvider, make_config, model_result, tool_call

    context = ToolContext(root=tmp_path)
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("write_file", path="a.txt", content="yeni")]),
            model_result("`a.txt` oluşturuldu."),
        ]
    )
    original = agent_loop.build_provider
    agent_loop.build_provider = lambda *a, **k: provider
    try:
        await run_agent_task(
            "a.txt oluştur",
            make_config(),
            sinks=(),
            prompter_factory=lambda _flush: _Onaylayan(),
            root=tmp_path,
            interactive=False,
            tool_context=context,
        )
    finally:
        agent_loop.build_provider = original

    assert context.changes.paths, "değişiklik kümesi çağıranın bağlamında birikmedi"
    assert (tmp_path / "a.txt").exists()


async def test_tui_consumes_pending_digest_once_and_injects_home(tmp_path, monkeypatch) -> None:
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    session = _TuiSession(state)
    calls: list[dict[str, object]] = []

    async def _fake_run_agent_task(task, config, **kwargs):
        calls.append(kwargs)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _fake_run_agent_task)
    state.pending_digest = "TUI devralma künyesi"

    await session._turn("ilk görev")
    await session._turn("ikinci görev")

    assert calls[0]["home"] == state.home
    assert calls[0]["extra_system"] == "TUI devralma künyesi"
    assert "TUI devralma künyesi" not in str(calls[1]["extra_system"])
    assert state.pending_digest is None
    assert calls[0].get("conversation_id") == session._transcript_store.session_id
    assert calls[1].get("conversation_id") == calls[0].get("conversation_id")
    other = _TuiSession(_state(tmp_path))
    assert other._transcript_store.session_id != calls[0].get("conversation_id")


async def test_tui_kalici_kural_bildirimini_tur_sonunda_basar(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): TUI döngüsü `approval_memory.take_notices()` çağırmıyordu; 'bir daha
    sorma' sonrası kural yazıldı/yazılamadı bildirimi hiç görünmüyordu."""
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    session = _TuiSession(state)

    async def _fake_run_agent_task(task, config, **kwargs):
        kwargs["approval_memory"].notices.append("Bash(npm test *) → /proje/.claude/x.json")
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _fake_run_agent_task)
    await session._turn("görev")

    assert "İzin kuralı kaydedildi" in session.tui.transcript
    assert "Bash(npm test *)" in session.tui.transcript
    assert state.approval_memory.take_notices() == []


async def test_tui_turlari_ayni_onay_hafizasini_paylasir(tmp_path, monkeypatch) -> None:
    """Oturum boyunca verilen izin TUI'de de tur değişince unutulmamalı."""
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    session = _TuiSession(state)
    calls: list[dict[str, object]] = []

    async def _fake_run_agent_task(task, config, **kwargs):
        calls.append(kwargs)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _fake_run_agent_task)

    await session._turn("ilk görev")
    await session._turn("ikinci görev")

    assert calls[0].get("approval_memory") is not None
    assert calls[0]["approval_memory"] is calls[1]["approval_memory"]


class _Onaylayan:
    async def confirm(self, request):
        return True

    async def ask(self, question):
        return ""


async def test_goal_kipi_tui_de_prompt_ve_adim_sinirini_tasir(tmp_path, monkeypatch) -> None:
    """`/goal` TUI'de kipin ÜÇ ayarını da taşımalı.

    Buraya eskiden yalnız `workflow` geçiyordu: hedef kipinin sistem promptu
    ("pes etme, ask_user ile müdahale iste") ve yükseltilmiş adım sınırı (100)
    sessizce düşüyordu. Düz konsol yüzeyi (`loop.py`) üçünü de geçiriyordu.
    """
    from fusion_cli.cli.repl import macros
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    session = _TuiSession(state)
    calls: list[dict[str, object]] = []

    async def _fake_run_agent_task(task, config, **kwargs):
        calls.append(kwargs)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _fake_run_agent_task)

    await session._turn("hedefi tamamla", mode=macros.Mode.GOAL)

    assert calls[0]["step_limit"] == macros.MODE_STEP_LIMITS[macros.Mode.GOAL]
    assert "HEDEF KİPİNDESİN" in str(calls[0]["extra_system"])
    assert calls[0]["workflow"] is False


async def test_kipsiz_turda_varsayilan_butce_korunur(tmp_path, monkeypatch) -> None:
    """Makro yoksa adım sınırı yükseltilmez; varsayılan bütçe geçerlidir."""
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    session = _TuiSession(state)
    calls: list[dict[str, object]] = []

    async def _fake_run_agent_task(task, config, **kwargs):
        calls.append(kwargs)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _fake_run_agent_task)

    await session._turn("sıradan görev")

    assert calls[0]["step_limit"] is None
    assert calls[0]["extra_system"] == ""


# --- Dalga 4: yol mesajı, iptalde kuyruk, hata ayrıntısı, künye, Ctrl-C (L2-16, L2-24) --- #


def test_yolla_baslayan_mesaj_komut_sayilmaz():
    """Ölçüldü (30 Ekim): '/Users/x/proje/main.py dosyasını incele' bilinmeyen komut oluyordu."""
    from fusion_cli.cli.repl.commands import is_command_line

    assert is_command_line("/help")
    assert is_command_line("/mode auto")
    assert is_command_line("/olmayan komut")  # bilinmeyen komut hatası korunur
    assert not is_command_line("/Users/x/proje/main.py dosyasını incele")
    assert not is_command_line("/tmp/a.txt")
    assert not is_command_line("merhaba")


async def test_yolla_baslayan_mesaj_tura_gider_komuta_degil(tmp_path, monkeypatch):
    session = _TuiSession(_state(tmp_path))
    gelen: list[str] = []

    async def _tur(line, **kwargs):
        gelen.append(line)

    monkeypatch.setattr(session, "_turn", _tur)

    await session._handle("/Users/x/proje/main.py dosyasını incele")

    assert gelen == ["/Users/x/proje/main.py dosyasını incele"]
    assert "bilinmeyen komut" not in session.tui.transcript.lower()


async def test_tur_durdurulunca_kuyruktaki_mesaj_hemen_gonderilir(tmp_path, monkeypatch):
    """Claude Code (#190): Esc turu keser, kuyruktakiler korunur ve hemen gönderilir."""
    session = _TuiSession(_state(tmp_path))
    session._queue = ["sıradaki iş"]
    gelen: list[str] = []

    async def _tur(line, **kwargs):
        gelen.append(line)
        if line == "uzun iş":
            raise asyncio.CancelledError

    monkeypatch.setattr(session, "_turn", _tur)

    await session._handle("uzun iş")
    assert session._task is not None
    await session._task

    assert gelen == ["uzun iş", "sıradaki iş"]
    assert session._queue == []
    assert "şimdi gönderiliyor" in session.tui.transcript


async def test_beklenmeyen_hata_sebebini_kullaniciya_gosterir(tmp_path, monkeypatch):
    session = _TuiSession(_state(tmp_path))

    async def _patla(line, **kwargs):
        raise RuntimeError("kota tükendi")

    monkeypatch.setattr(session, "_turn", _patla)

    await session._handle("iş")

    assert "kota tükendi" in session.tui.transcript


async def test_basarisiz_turda_devralma_kunyesi_kaybolmaz(tmp_path, monkeypatch):
    state = _state(tmp_path)
    session = _TuiSession(state)

    async def _patla(task, config, **kwargs):
        raise RuntimeError("motor çöktü")

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _patla)
    state.pending_digest = "devralınan oturum künyesi"

    with contextlib.suppress(RuntimeError):
        await session._turn("görev")

    assert state.pending_digest == "devralınan oturum künyesi"


async def test_ctrl_c_calisan_turu_once_iptal_eder(tmp_path):
    session = _TuiSession(_state(tmp_path))

    async def _bekle() -> None:
        await asyncio.sleep(30)

    session._task = asyncio.ensure_future(_bekle())
    session._queue = ["x"]
    await asyncio.sleep(0)

    session._exit()
    await asyncio.sleep(0)

    assert session._task.cancelled() or session._task.cancelling() > 0
    assert session._queue == []
    assert session._state.running is False


async def test_prompter_ask_bos_cevap_modele_bos_metin_olarak_gitmez():
    """Ölçüldü (30 Ekim): Esc boş string döndürüyor, model aynı soruyu tekrar soruyordu (L2-23)."""
    from fusion_cli.ui import messages

    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(prompter.ask("hangi dosya?"))
    await asyncio.sleep(0)
    tui._resolve("")

    assert await task == messages.ASK_DECLINED


async def test_prompter_ask_secici_esc_vazgecildi_der_etkilesimsiz_demez():
    from fusion_cli.ui import messages

    tui = _noop_tui()
    prompter = TuiPrompter(tui, None)

    task = asyncio.ensure_future(
        prompter.ask("hangisi?", options=(QuestionOption(label="a", description=""),))
    )
    await asyncio.sleep(0)
    tui._resolve(None)  # Esc

    sonuc = await task
    assert sonuc == messages.ASK_DECLINED
    assert sonuc != messages.NO_ANSWER_AVAILABLE


async def test_tui_turu_kullanim_gunlugunu_besler(tmp_path, monkeypatch) -> None:
    """Varsayılan TUI yolu da kalıcı kullanım günlüğünü sinks'e katmalı.

    Ölçüldü (31 Ekim): günlük yalnız satır-içi yola bağlıydı; terminalde `fusion` açıp
    `/usage` yazan kullanıcı TUI turlarının harcamasını hiç göremiyordu.
    """
    from fusion_cli.engines.agent import AgentOutcome
    from fusion_cli.observability.usage_log import UsageLog

    state = _state(tmp_path)
    state.usage_log = UsageLog(tmp_path / "usage.jsonl", session_id="tui")
    session = _TuiSession(state)
    calls: list[dict[str, object]] = []

    async def _fake_run_agent_task(task, config, **kwargs):
        calls.append(kwargs)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _fake_run_agent_task)

    await session._turn("görev")

    assert state.usage_log in calls[0]["sinks"]


async def test_tui_turu_gunluk_kapaliyken_sinks_degismez(tmp_path, monkeypatch) -> None:
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    session = _TuiSession(state)
    calls: list[dict[str, object]] = []

    async def _fake_run_agent_task(task, config, **kwargs):
        calls.append(kwargs)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", _fake_run_agent_task)

    await session._turn("görev")

    assert None not in calls[0]["sinks"]


async def test_mesgulken_anlik_komutlar_hemen_calisir(tmp_path):
    """Claude Code (#209): yanıt sürerken /status, /tasks, /usage, /model, /effort, /fast,
    /add-dir ve /permissions kuyruğa girmez, hemen çalışır; diğer komutlar kuyruğa girer."""
    from fusion_cli.cli.repl.busy_commands import runs_while_busy

    session = _TuiSession(_state(tmp_path))
    for line in ("/status", "/tasks", "/usage", "/cost", "/model", "/effort", "/permissions"):
        assert runs_while_busy(session._registry, line), line
    assert not runs_while_busy(session._registry, "/agent")
    assert not runs_while_busy(session._registry, "düz mesaj")

    async def _bekle() -> None:
        await asyncio.sleep(10)

    session._task = asyncio.ensure_future(_bekle())
    session._submit("/model")
    session._submit("/agent")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert session._queue == ["/agent"]
    assert session._task is not None and not session._task.done()
    session._task.cancel()


async def test_mesgulken_duz_mesaj_ayni_tura_verilir_up_geri_alir_sendnow_keser(tmp_path):
    """Claude Code (#190): düz mesaj koşan agent turuna verilir; komut kuyrukta bekler.
    Tüketilmeyen tur sonunda kuyruğun başına döner; ilk satırda Up geri alır;
    chat:sendNow bekleyen varken turu keser."""
    session = _TuiSession(_state(tmp_path))

    async def _bekle() -> None:
        await asyncio.sleep(10)

    session._task = asyncio.ensure_future(_bekle())
    steering = session._steer.begin()
    session._submit("şunu da yap")
    session._submit("/status")
    session._submit("/compact")
    assert steering.pending and session._queue == ["/compact"]
    assert "sıraya alındı" in session.tui.transcript

    taken = session._take_back_queue()
    assert taken == ["şunu da yap", "/compact"] and session._queue == []
    session._submit("bir daha")
    session._settle_steer()
    assert session._queue == ["bir daha"]

    session._steer.begin()
    session._submit("hemen")
    session._send_now("taslak")
    await asyncio.sleep(0)
    assert session._task.cancelled()


async def test_sendnow_suren_kabuk_komutunu_arka_plana_alir_turu_kesmez(tmp_path):
    """Claude Code (#190, #218): ajanın kabuk komutu sürerken sendNow komutu arka plana
    alır, kuyruktaki mesaj araç sonucu döner dönmez aynı tura verilir."""
    session = _TuiSession(_state(tmp_path))
    session._task = asyncio.ensure_future(asyncio.sleep(10))
    session._steer.begin()
    event = session._state.shell_handoff.begin()
    session._submit("testler bitince şunu da yap")
    session._send_now("")
    await asyncio.sleep(0)
    assert event.is_set() and not session._task.cancelled()
    session._task.cancel()


def test_ctrl_enter_dizileri_sendnow_tusuna_eslenir(tmp_path):
    from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
    from prompt_toolkit.keys import Keys

    from fusion_cli.cli.repl.tui_input_keys import CTRL_ENTER_SEQUENCES, register_shift_enter
    from fusion_cli.config.claude_keybindings import keystroke_to_key
    from fusion_cli.config.keybindings import load_keymap

    register_shift_enter()
    assert all(ANSI_SEQUENCES[seq] is Keys.F24 for seq in CTRL_ENTER_SEQUENCES)
    assert keystroke_to_key("ctrl+enter") == "f24"
    keymap = load_keymap(tmp_path / "yok.json", tmp_path / "yok-claude.json")
    assert keymap.contexts["tui"]["f24"] == "simdi_gonder"


def test_import_history_oturumsuz_kaynagi_ayiklar():
    """`/import history claude` oturumsuzsa TUI modal seçici açar (#223)."""
    from fusion_cli.cli.repl.tui_loop import _history_source

    assert _history_source("history claude") == "claude"
    assert _history_source("history claude s1") is None
    assert _history_source("claude --yes") is None


async def test_ctrl_x_ctrl_k_cift_basista_arka_plan_ajanlarini_durdurur(tmp_path):
    """Claude Code chat:killAgents (#216): ilk basış uyarır, ikincisi durdurur."""
    session = _TuiSession(_state(tmp_path))
    runs = session._state.child_runs
    task = asyncio.ensure_future(asyncio.sleep(10))
    runs._background["ajan-1"] = task
    session._tui._kill_agents_pressed()
    assert "yeniden bas" in session.tui.transcript and not task.cancelled()
    session._tui._kill_agents_pressed()
    for _ in range(20):
        await asyncio.sleep(0)
        if "durduruldu" in session.tui.transcript:
            break
    assert task.cancelled()
    assert "1 arka plan alt ajanı durduruldu" in session.tui.transcript


def test_bos_girdide_soru_isareti_kisayol_panelini_basar(tmp_path):
    from fusion_cli.config.claude_keybindings import translate_action
    from fusion_cli.config.keybindings import load_keymap

    session = _TuiSession(_state(tmp_path))
    session._tui._show_shortcuts()
    assert "Ctrl+X Ctrl+K" in session.tui.transcript
    keymap = load_keymap(tmp_path / "yok.json", tmp_path / "yok-claude.json")
    assert keymap.contexts["tui"]["?"] == "kisayollar"
    assert keymap.contexts["tui"]["c-x c-k"] == "ajanlari_durdur"
    assert translate_action("chat:killAgents") == "ajanlari_durdur"
