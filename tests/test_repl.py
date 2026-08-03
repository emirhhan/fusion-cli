"""REPL: komut kayıt defteri, durum yönetimi ve arka plan işleri."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

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


def test_istem_mesaji_mod_ile_canli_hesaplanir(tmp_path, monkeypatch):
    """shift-tab modu değiştirince istem mesajı yeniden hesaplanır — Enter beklemeden.

    Mesaj `prompt_async`'e callable olarak verildiği için her yeniden çizimde bu
    metot çağrılır; içeriği o anki moda göre üretir. Statik verilseydi etiket
    donardı (kullanıcının 'shift-tab çalışıyor ama Enter gerekiyor' sorunu).
    """
    from fusion_cli.cli.repl.input import ReplInput

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    reader = ReplInput(Path(tmp_path) / "history", ["/help"], mode=ApprovalMode.AUTO)

    auto_message = reader._prompt_message().value  # auto: yalnız sembol, etiketsiz
    reader.cycle_mode()  # auto -> sonraki mod
    switched_message = reader._prompt_message().value

    assert switched_message != auto_message  # mesaj gerçekten değişti
    assert reader.mode.value in switched_message  # yeni mod etiketi mesajda görünür


class _FakeBuffer:
    """insert_text'i biriktiren minik tampon taklidi."""

    def __init__(self) -> None:
        self.text = ""

    def insert_text(self, text: str) -> None:
        self.text += text


def _reader(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.input import ReplInput

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    return ReplInput(Path(tmp_path) / "history", ["/help"], mode=ApprovalMode.AUTO)


def test_uzun_yapistirma_tampona_tek_satir_girer(tmp_path, monkeypatch):
    """40 satırlık yapıştırma tampona tek satır olarak girmeli; yükseklik patlamaz."""
    from fusion_cli.cli.repl.input import FOLD_PASTE_LINES

    reader = _reader(tmp_path, monkeypatch)
    buffer = _FakeBuffer()
    pasted = "\n".join(f"satir-{i}" for i in range(40))
    assert FOLD_PASTE_LINES < 40  # eşiğin üstünde olduğundan emin ol

    reader.fold_paste_into(buffer, pasted)

    assert buffer.text.count("\n") == 0  # tampona tek satır girdi
    assert "40" in buffer.text  # yer tutucu satır sayısını gösteriyor


def test_katlanan_yapistirma_gonderimde_tam_metne_acilir(tmp_path, monkeypatch):
    reader = _reader(tmp_path, monkeypatch)
    buffer = _FakeBuffer()
    pasted = "\n".join(f"satir-{i}" for i in range(40))

    reader.fold_paste_into(buffer, pasted)
    acik = reader.expand_pastes(f"şuna bak: {buffer.text} teşekkürler")

    assert pasted in acik
    assert acik == f"şuna bak: {pasted} teşekkürler"


def test_az_satirli_ama_uzun_yapistirma_da_katlanir(tmp_path, monkeypatch):
    """Satır sayısı eşik altında olsa bile karakter sayısı yüksekse katlanmalı."""
    from fusion_cli.cli.repl.input import FOLD_PASTE_CHARS, FOLD_PASTE_LINES

    reader = _reader(tmp_path, monkeypatch)
    buffer = _FakeBuffer()
    # Tek satır ama eşiğin çok üstünde karakter.
    uzun = "x" * (FOLD_PASTE_CHARS + 100)
    assert uzun.count("\n") + 1 <= FOLD_PASTE_LINES  # satır sayısı eşik altında

    reader.fold_paste_into(buffer, uzun)

    assert buffer.text != uzun  # tampona ham metin girmedi
    assert "\n" not in buffer.text  # tek satır yer tutucu
    assert reader.expand_pastes(buffer.text) == uzun  # gönderimde tam metin geri gelir


def test_hem_kisa_hem_az_satirli_yapistirma_katlanmaz(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.input import FOLD_PASTE_CHARS

    reader = _reader(tmp_path, monkeypatch)
    buffer = _FakeBuffer()
    kisa = "birkaç satır\niki\nüç"
    assert len(kisa) < FOLD_PASTE_CHARS

    reader.fold_paste_into(buffer, kisa)

    assert buffer.text == kisa


def test_kisa_yapistirma_oldugu_gibi_girer(tmp_path, monkeypatch):
    reader = _reader(tmp_path, monkeypatch)
    buffer = _FakeBuffer()
    kisa = "tek satır metin"

    reader.fold_paste_into(buffer, kisa)

    assert buffer.text == kisa
    assert reader.expand_pastes(buffer.text) == kisa


def test_katlama_kapaliyken_yapistirma_oldugu_gibi_girer(tmp_path, monkeypatch):
    reader = _reader(tmp_path, monkeypatch)
    reader.toggle_fold()  # katlamayı kapat
    buffer = _FakeBuffer()
    uzun = "\n".join(f"satir-{i}" for i in range(40))

    reader.fold_paste_into(buffer, uzun)

    assert buffer.text == uzun


def test_birden_cok_yapistirma_ayri_ayri_acilir(tmp_path, monkeypatch):
    reader = _reader(tmp_path, monkeypatch)
    buffer = _FakeBuffer()
    ilk = "\n".join(f"a-{i}" for i in range(40))
    ikinci = "\n".join(f"b-{i}" for i in range(40))

    reader.fold_paste_into(buffer, ilk)
    buffer.insert_text(" ve ")
    reader.fold_paste_into(buffer, ikinci)

    acik = reader.expand_pastes(buffer.text)
    assert acik == f"{ilk} ve {ikinci}"


def test_exit_veda_mesajini_kendisi_basmaz(registry, state):
    """Veda mesajı kapanışta basılır; komut da basarsa satır iki kez görünür."""
    assert _calistir(registry, state, "/exit") == ""


# --- Karşılama ekranı --------------------------------------------------------- #


def _welcome_output(width, *, lesson_count=28):
    import io
    import re

    from rich.console import Console

    from fusion_cli.ui.banner import SessionInfo, print_welcome

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=width, no_color=True)
    print_welcome(
        console,
        SessionInfo(
            version="1.0",
            engine="agent",
            approval="auto",
            model="test-model",
            working_dir="~/proje",
            lesson_count=lesson_count,
        ),
        clear=False,
    )
    return re.sub(r"\x1b\[[0-9;]*m", "", buffer.getvalue())


def test_karsilama_oturum_bilgisini_gosterir():
    cikti = _welcome_output(100)

    assert "test-model" in cikti
    assert "~/proje" in cikti
    assert "28 ders" in cikti


def test_karsilama_kutusu_terminali_tasmaz():
    for width in (72, 88, 100, 140):
        satirlar = [satir for satir in _welcome_output(width).splitlines() if satir.strip()]

        assert all(len(satir) <= width for satir in satirlar), width


def test_karsilama_kompakt_imza_gosterir_buyuk_ascii_yok():
    """Claude dizilimi: büyük ASCII logo yerine kompakt `✻ Fusion CLI` başlığı."""
    from fusion_cli.ui import theme

    for width in (72, 120):
        cikti = _welcome_output(width)
        assert "███████╗" not in cikti
        assert theme.ICON_SPARKLE in cikti and "Fusion CLI" in cikti


def test_karsilama_ipucu_ve_tanitim_icerir():
    cikti = _welcome_output(120)

    assert "İpucu" in cikti
    # Kutuda tanıtım satırı (WELCOME_ABOUT_TEXT'in bir parçası) yer alır.
    assert "Ücretsiz LLM" in cikti


def test_ipucu_secimi_kararli():
    """Aynı projede hep aynı ipucu görünmeli; ekran her açılışta değişmemeli."""
    from fusion_cli.ui.banner import pick_tip

    assert pick_tip("~/proje") == pick_tip("~/proje")


def test_farkli_projelerde_farkli_ipucu_gelebilir():
    from fusion_cli.ui.banner import pick_tip
    from fusion_cli.ui.messages import WELCOME_TIPS

    secilenler = {pick_tip(f"~/proje{index}") for index in range(40)}

    assert len(secilenler) > 1
    assert secilenler <= set(WELCOME_TIPS)


def test_bellek_kapaliysa_belirtilir():
    assert "kapalı" in _welcome_output(100, lesson_count=None)


# --- Durum çubuğu -------------------------------------------------------------- #


def _status_text(mode, context=""):
    import re
    import tempfile

    from fusion_cli.cli.repl.input import ReplInput

    history = Path(tempfile.mkdtemp(prefix="fusion-test-history-")) / "history"
    reader = ReplInput(history, ["/help"], mode=mode)
    reader.context = context
    return re.sub(r"<[^>]+>", "", reader.status_bar().value)


def test_durum_cubugu_modu_ve_baglami_gosterir():
    metin = _status_text(ApprovalMode.SECURITY, "agent · general · model-x")

    assert "security" in metin
    assert "model-x" in metin


def test_durum_cubugu_tek_satira_sigar():
    """80 sütunluk terminalde sarmamalı."""
    metin = _status_text(ApprovalMode.SECURITY, "agent · reasoning · nemotron-super")

    assert len(metin) <= 80


def test_durum_cubugu_baglamsiz_da_calisir():
    assert "auto" in _status_text(ApprovalMode.AUTO)


# --- Çalışma göstergesi -------------------------------------------------------- #


def _indicator():
    import io

    from rich.console import Console

    from fusion_cli.ui.work import WorkIndicator

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=100, no_color=True)
    return WorkIndicator(console), buffer


def test_gosterge_baslayip_ozet_dondurur():
    gosterge, _ = _indicator()

    gosterge.start("hazırlanıyor…", model="model-x")
    gosterge.update(tokens=231)
    ozet = gosterge.finish()

    assert ozet is not None
    assert "231 token" in ozet and "model-x" in ozet


def test_gosterge_is_yapilmadiysa_ozet_basmaz():
    gosterge, _ = _indicator()

    gosterge.start("bekliyor…")

    assert gosterge.finish() is None


def test_gosterge_tokenlari_biriktirir():
    gosterge, _ = _indicator()
    gosterge.start("x", model="m")

    gosterge.update(tokens=100)
    gosterge.update(tokens=50)

    assert "150 token" in gosterge.finish()


def test_gosterge_terminal_disinda_ciktiyi_kirletmez():
    gosterge, buffer = _indicator()

    gosterge.start("hazırlanıyor…", model="m")
    gosterge.pause()
    gosterge.finish()

    assert buffer.getvalue() == ""


def test_gosterge_bittikten_sonra_calismiyor():
    gosterge, _ = _indicator()
    gosterge.start("x", model="m")

    gosterge.finish()

    assert not gosterge.running


def test_token_sayisi_kisaltilir():
    from fusion_cli.ui.work import format_tokens

    assert format_tokens(840) == "840"
    assert format_tokens(1234) == "1.2k"
    assert format_tokens(12_500) == "12.5k"


def test_gosterge_calisirken_yeni_etiket_sureyi_sifirlamaz():
    """Kullanıcı TURUN tamamının ne kadar sürdüğünü görmek ister."""
    import time

    gosterge, _ = _indicator()
    gosterge.start("ilk", model="m")
    baslangic = gosterge._state.started_at
    time.sleep(0.01)

    gosterge.update(label="ikinci")

    assert gosterge._state.started_at == baslangic


def test_bilgi_satiri_sarmaz():
    """Sarınca alt satırda öksüz parça kalıyor; sığmazsa alan düşürülür."""
    for width in (60, 72, 80, 100, 140):
        satirlar = _welcome_output(width).splitlines()
        bilgi = next(satir for satir in satirlar if "motor" in satir)

        assert len(bilgi) <= width, (width, bilgi)


def test_dar_terminalde_de_dizin_gorunur_kalir():
    """Kutu içinde bilgi satırı kendiliğinden sarar; alan düşürülmez, dizin görünür kalır."""
    dar = _welcome_output(60)

    assert "motor" in dar
    assert "dizin" in dar


# --- /undo ------------------------------------------------------------------ #


def test_undo_degisiklik_yokken_bilgi_verir(state):
    from fusion_cli.cli.repl.commands import build_registry
    from fusion_cli.ui import messages

    komut = build_registry().get("undo")

    assert komut is not None
    assert komut.handler(state, "") == messages.UNDO_NOTHING


def test_undo_son_turun_dosyalarini_geri_alir(state, tmp_path):
    from fusion_cli.cli.repl.commands import build_registry
    from fusion_cli.core.changeset import ChangeSet

    dosya = tmp_path / "a.py"
    dosya.write_text("eski\n", encoding="utf-8")
    kayit = ChangeSet()
    kayit.record(dosya)
    dosya.write_text("agent yazdi\n", encoding="utf-8")

    state.last_changes = kayit
    komut = build_registry().get("undo")
    assert komut is not None

    mesaj = komut.handler(state, "")

    assert dosya.read_text(encoding="utf-8") == "eski\n"
    assert "a.py" in mesaj
    assert state.last_changes is None, "aynı kayıt iki kez geri alınmamalı"


# --- REPL ile tek-atış yolu aynı bağımlılıkları kurmalı ---------------------- #


async def test_repl_agent_turu_gorev_tipini_gecirir(state, monkeypatch):
    """`/type code` agent turunda da etkili olmalı.

    Gerçek hata: REPL `task_type`i fusion turuna geçiriyor ama AgentDeps'e
    geçirmiyordu. `select_agent_spec` varsayılan "general" ile çağrılıyor,
    dolayısıyla `task_model_map` agent modunda REPL'de hiç uygulanmıyordu —
    kullanıcı `/type code` yazıp modelin değiştiğini sanıyordu.
    """
    from fusion_cli.cli.repl import loop as repl_loop
    from fusion_cli.engines.agent.loop import AgentDeps

    yakalanan = {}
    gercek = AgentDeps

    def _yakala(**kwargs):
        yakalanan.update(kwargs)
        return gercek(**kwargs)

    async def _sahte_run_agent(task, deps, **kwargs):
        from fusion_cli.engines.agent import AgentOutcome

        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.engines.agent.loop.AgentDeps", _yakala)
    monkeypatch.setattr("fusion_cli.engines.agent.run_agent", _sahte_run_agent)

    state.task_type = "code"
    await repl_loop._agent_turn("bir sey yap", state, Console(quiet=True), _SahteArkaPlan())

    assert yakalanan.get("task_type") == "code"


class _SahteArkaPlan:
    def spawn(self, *a, **k):
        return None

    async def drain(self):
        return None


# --- /provider -------------------------------------------------------------- #


def test_provider_secimi_yapilandirmaya_uygulanir(state, tmp_path, monkeypatch):
    """Sağlayıcı seçimi oturumda hemen etkili olmalı."""
    from fusion_cli.cli.repl import provider_flow

    monkeypatch.setattr(
        "fusion_cli.config.writer._target_path", lambda cfg: tmp_path / "config.yaml"
    )

    def _sec(choices, *, title, **kwargs):
        return "nvidia"

    sonuc = provider_flow.choose_provider(state.config, picker=_sec)

    assert sonuc.config.runtime.provider == "nvidia"
    assert (tmp_path / "config.yaml").exists()


def test_provider_vazgecince_degismez(state):
    from fusion_cli.cli.repl import provider_flow
    from fusion_cli.ui import messages

    sonuc = provider_flow.choose_provider(state.config, picker=lambda choices, *, title, **kw: None)

    assert sonuc.message == messages.PICKER_CANCELLED
    assert sonuc.config is state.config


# --- /tips ------------------------------------------------------------------ #


def test_tips_komutu_kayitli_ve_kendi_ciktisini_basar():
    """`/tips` tek satırlık sonuç döndürmez, panel basar."""
    from fusion_cli.cli.repl.commands import RENDERED_COMMANDS, build_registry

    komut = build_registry().get("tips")

    assert komut is not None
    assert "tips" in RENDERED_COMMANDS


def test_tips_ekrani_komutlari_gorev_ekseninde_anlatir(capsys):
    """`/help` komutları LİSTELER; `/tips` ne zaman kullanılacağını söyler."""
    from rich.console import Console

    from fusion_cli.cli.repl.help_view import _tips

    _tips(Console(force_terminal=False, width=200))
    cikti = capsys.readouterr().out

    for komut in ("/agent", "/fusion", "/level", "/provider", "/verify", "/undo"):
        assert komut in cikti, f"{komut} rehberde yok"
    assert "kota" in cikti, "kota yönlendirmesi olmalı"


def test_tips_bolum_kapanislari_komut_gibi_gorunmez():
    """Bölüm sonundaki karar kuralı komut sütununa yazılmamalı."""
    from fusion_cli.ui import messages

    for _baslik, satirlar in messages.TIPS_SECTIONS:
        for komut, aciklama in satirlar:
            assert aciklama, "açıklamasız satır olmaz"
            if not komut:
                continue
            assert len(komut) <= 16, f"komut sütununa sığmıyor: {komut}"
