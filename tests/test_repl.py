"""REPL: komut kayıt defteri, durum yönetimi ve arka plan işleri."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import RENDERED_COMMANDS, build_registry, parse
from fusion_cli.cli.repl.state import TASK_TYPES, Engine, ReplState
from fusion_cli.core.concurrency import BackgroundTasks
from fusion_cli.core.memory import Feedback, LessonKind, LessonSource
from fusion_cli.core.types import FusionResult, Message, VerdictSource
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


class _SayacBellek:
    """Ders eklemelerini ve geri bildirimleri sayan sahte bellek."""

    def __init__(self):
        self.lessons_added = []
        self.feedback = []
        self.applied = 1

    def add(self, lesson):
        self.lessons_added.append(lesson)
        return True

    def recall(self, task, limit=4):
        return ()

    def all(self):
        return ()

    def count(self):
        return len(self.lessons_added)

    def apply_feedback(self, task_type, model_name, verdict):
        self.feedback.append((task_type, model_name, verdict))
        return self.applied


@pytest.fixture
def state(tmp_path):
    memory = null_memory()
    return ReplState(config=make_config(), memory=memory, root=tmp_path)


@pytest.fixture
def registry():
    return build_registry()


def _calistir(registry, state, satir):
    name, argument = parse(satir)
    command = registry.get(name)
    assert command is not None, satir
    return command.handler(state, argument)


# --- Ayrıştırma -------------------------------------------------------------- #


def test_komut_ve_arguman_ayrilir():
    assert parse("/type code") == ("type", "code")


def test_argümansiz_komut():
    assert parse("/help") == ("help", "")


def test_cok_kelimeli_arguman_korunur():
    assert parse("/learn her zaman testleri calistir") == (
        "learn",
        "her zaman testleri calistir",
    )


def test_buyuk_harf_normalize_edilir():
    assert parse("/HELP")[0] == "help"


# --- Kayıt defteri ----------------------------------------------------------- #


def test_takma_adlar_ayni_komuta_cozer(registry):
    assert registry.get("q") is registry.get("exit")
    assert registry.get("h") is registry.get("help")


def test_bilinmeyen_komut_none_doner(registry):
    assert registry.get("olmayan") is None


def test_tamamlama_sozcukleri_slash_ile_baslar(registry):
    words = registry.completion_words()

    assert all(word.startswith("/") for word in words)
    assert "/agent" in words and "/q" in words


def test_her_komutun_aciklamasi_var(registry):
    assert all(command.summary.strip() for command in registry.all())


def test_kendi_ciktisini_basan_komutlar_kayitli(registry):
    for name in RENDERED_COMMANDS:
        assert registry.get(name) is not None, name


# --- Durum değişiklikleri ---------------------------------------------------- #


def test_motor_degistirilebilir(registry, state):
    _calistir(registry, state, "/fusion")
    assert state.engine is Engine.FUSION

    _calistir(registry, state, "/agent")
    assert state.engine is Engine.AGENT


def test_onay_modu_komutla_degisir(registry, state):
    _calistir(registry, state, "/security")

    assert state.approval is ApprovalMode.SECURITY


def test_onay_modu_dongusel_ilerler(state):
    baslangic = state.approval
    goruilen = {baslangic}

    for _ in range(len(ApprovalMode)):
        goruilen.add(state.cycle_approval())

    assert goruilen == set(ApprovalMode)
    assert state.approval is baslangic  # tam tur


def test_gorev_tipi_dogrulanir(registry, state):
    _calistir(registry, state, "/type code")
    assert state.task_type == "code"

    sonuc = _calistir(registry, state, "/type olmayan")
    assert state.task_type == "code"  # değişmedi
    assert "Bilinmeyen görev tipi" in sonuc


def test_tanimli_tum_gorev_tipleri_kabul_edilir(registry, state):
    for task_type in TASK_TYPES:
        _calistir(registry, state, f"/type {task_type}")
        assert state.task_type == task_type


def test_gecmis_temizlenir(registry, state):
    state.history = [Message("user", "a"), Message("assistant", "b")]

    sonuc = _calistir(registry, state, "/reset")

    assert state.history == []
    assert "2" in sonuc


def test_tum_cevaplar_ac_kapa(registry, state):
    _calistir(registry, state, "/all")
    assert state.show_all_answers

    _calistir(registry, state, "/all")
    assert not state.show_all_answers


def test_sentez_yapilandirmadan_baslar_ve_terslenir(registry, state):
    assert state.synthesis is None  # yapılandırmadaki değer geçerli

    _calistir(registry, state, "/synth")

    assert state.synthesis is not state.config.runtime.synthesis


def test_exit_dongu_bayragini_dusurur(registry, state):
    _calistir(registry, state, "/exit")

    assert not state.running


# --- Bellek komutları -------------------------------------------------------- #


def test_geri_bildirim_fusion_turu_olmadan_uyarir(registry, state):
    sonuc = _calistir(registry, state, "/good")

    assert "fusion turu" in sonuc


def test_geri_bildirim_son_kazanana_uygulanir(registry, state):
    bellek = _SayacBellek()
    state.memory = state.memory.__class__(
        performance=bellek,
        lessons=bellek,
        code_index=state.memory.code_index,
    )
    state.last_fusion = FusionResult(
        task="t",
        task_type="code",
        winner="nemotron",
        final_answer="cevap",
        source=VerdictSource.JUDGE,
        candidates=(),
    )

    _calistir(registry, state, "/bad")

    assert bellek.feedback == [("code", "nemotron", Feedback.BAD)]


def test_learn_kurali_elle_kaydeder(registry, state):
    bellek = _SayacBellek()
    state.memory = state.memory.__class__(
        performance=bellek, lessons=bellek, code_index=state.memory.code_index
    )

    _calistir(registry, state, "/learn her zaman testleri calistir")

    kaydedilen = bellek.lessons_added[0]
    assert kaydedilen.text == "her zaman testleri calistir"
    assert kaydedilen.source is LessonSource.MANUAL
    assert kaydedilen.kind is LessonKind.SUCCESS


def test_learn_argumansiz_kullanim_gosterir(registry, state):
    assert "Kullanım" in _calistir(registry, state, "/learn")


# --- Arka plan işleri -------------------------------------------------------- #


async def test_arka_plan_isi_beklenir():
    tamamlanan = []

    async def _is():
        tamamlanan.append("bitti")

    tasks = BackgroundTasks()
    tasks.spawn(_is())
    await tasks.drain()

    assert tamamlanan == ["bitti"]
    assert tasks.pending == 0


async def test_arka_plan_hatasi_yutulmaz():
    async def _patla():
        raise RuntimeError("ders cikarimi patladi")

    tasks = BackgroundTasks()
    tasks.spawn(_patla())
    await tasks.drain()

    assert tasks.failures and "ders cikarimi patladi" in tasks.failures[0]


async def test_birden_cok_is_paralel_tamamlanir():
    import asyncio

    sonuclar = []

    async def _is(index):
        await asyncio.sleep(0.01)
        sonuclar.append(index)

    tasks = BackgroundTasks()
    for index in range(5):
        tasks.spawn(_is(index))
    await tasks.drain()

    assert sorted(sonuclar) == [0, 1, 2, 3, 4]


# --- Giriş katmanı ----------------------------------------------------------- #


def test_tty_yoksa_prompt_toolkit_kurulmaz(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.input import ReplInput

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    reader = ReplInput(tmp_path / "history", ["/help"], mode=ApprovalMode.AUTO)

    assert not reader.interactive


def test_mod_dongusu_giriste_de_calisir(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.input import ReplInput

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    reader = ReplInput(Path(tmp_path) / "history", ["/help"], mode=ApprovalMode.AUTO)

    assert reader.cycle_mode() is not ApprovalMode.AUTO


def test_exit_veda_mesajini_kendisi_basmaz(registry, state):
    """Veda mesajı kapanışta basılır; komut da basarsa satır iki kez görünür."""
    assert _calistir(registry, state, "/exit") == ""
