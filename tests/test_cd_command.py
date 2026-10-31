"""`/cd` çalışma dizini değiştirme (P-072).

Ölçüldü (31 Ekim): `/add-dir` vardı ama oturumun kökünü değiştiren komut yoktu; başka
projeye geçmek için REPL'i kapatıp yeniden açmak gerekiyordu.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.completion import ReplCompleter
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages

from .fakes import make_config


@pytest.fixture
def ev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ev"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def _state(root: Path, home: Path) -> ReplState:
    return ReplState(config=make_config(), memory=null_memory(), root=root, home=home)


def _cd(state: ReplState, argument: str) -> str:
    command = build_registry().get("cd")
    assert command is not None
    return command.handler(state, argument)


def test_cd_kokunu_degistirir_ve_modele_baglam_notu_birakir(tmp_path: Path, ev: Path):
    eski = tmp_path / "a"
    yeni = tmp_path / "b"
    eski.mkdir()
    yeni.mkdir()
    state = _state(eski, ev)

    mesaj = _cd(state, "../b")

    assert state.root == yeni.resolve()
    assert "Çalışma dizini değişti" in mesaj
    assert any("calisma_dizini_degisti" in blok for blok in state.pending_blocks)
    assert str(yeni.resolve()) in state.take_pending_digest()


def test_cd_argumansiz_mevcut_dizini_soyler(tmp_path: Path, ev: Path):
    state = _state(tmp_path, ev)
    assert str(tmp_path) in _cd(state, "")


def test_cd_ek_klasorleri_ve_oturum_izinlerini_tasimaz(tmp_path: Path, ev: Path):
    eski, yeni, ek = tmp_path / "a", tmp_path / "b", tmp_path / "ek"
    for klasor in (eski, yeni, ek):
        klasor.mkdir()
    state = _state(eski, ev)
    state.extra_roots = (ek,)
    once = state.approval_memory.revision

    _cd(state, str(yeni))

    assert state.extra_roots == ()
    assert state.approval_memory.revision > once


def test_cd_yeni_kokun_becerilerini_yukler(tmp_path: Path, ev: Path):
    eski, yeni = tmp_path / "a", tmp_path / "b"
    eski.mkdir()
    beceri = yeni / ".claude" / "skills" / "yerel"
    beceri.mkdir(parents=True)
    (beceri / "SKILL.md").write_text(
        "---\nname: yerel\ndescription: yeni projenin becerisi\n---\ngövde\n", encoding="utf-8"
    )
    state = _state(eski, ev)
    assert state.capabilities is not None
    assert "yerel" not in {skill.name for skill in state.capabilities.skills()}

    _cd(state, str(yeni))

    assert state.capabilities is not None
    assert "yerel" in {skill.name for skill in state.capabilities.skills()}


@pytest.mark.parametrize("hedef", ["yok-boyle-klasor", "~"])
def test_cd_olmayan_ya_da_genis_hedefi_reddeder(tmp_path: Path, ev: Path, hedef: str):
    state = _state(tmp_path, ev)
    mesaj = _cd(state, hedef)
    assert state.root == tmp_path
    assert mesaj in {messages.CD_NOT_FOUND, messages.CD_TOO_BROAD}


def test_cd_disk_kokunu_reddeder(tmp_path: Path, ev: Path):
    state = _state(tmp_path, ev)
    assert _cd(state, "/") == messages.CD_TOO_BROAD
    assert state.root == tmp_path


def test_cd_deny_kurali_hedefi_engeller(tmp_path: Path, ev: Path):
    yasak = tmp_path / "gizli"
    yasak.mkdir()
    proje = tmp_path / "proje"
    proje.mkdir()
    (ev / ".claude").mkdir()
    (ev / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"deny": [f"Cd(/{yasak.as_posix()})"]}}),
        encoding="utf-8",
    )
    state = _state(proje, ev)

    mesaj = _cd(state, str(yasak))

    assert mesaj.startswith("Bu dizine geçiş izin kuralıyla engelli")
    assert state.root == proje


def _deny_cd(ev: Path, *patterns: str) -> None:
    (ev / ".claude").mkdir(exist_ok=True)
    (ev / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"deny": [f"Cd({p})" for p in patterns]}}), encoding="utf-8"
    )


def test_cd_deny_kurali_sembolik_bagla_yazilan_yolu_da_engeller(tmp_path: Path, ev: Path):
    """Ölçüldü (31 Ekim): hedef `.resolve()` ile değerlendirildiği için macOS'ta
    `Cd(//etc/**)` kuralı `/cd /etc` (`/private/etc`) geçişini engellemiyordu."""
    gercek = tmp_path / "gercek"
    (gercek / "alt").mkdir(parents=True)
    bag = tmp_path / "bag"
    bag.symlink_to(gercek, target_is_directory=True)
    proje = tmp_path / "proje"
    proje.mkdir()
    _deny_cd(ev, f"/{bag.as_posix()}", f"/{bag.as_posix()}/**")
    state = _state(proje, ev)

    assert _cd(state, str(bag)).startswith("Bu dizine geçiş izin kuralıyla engelli")
    assert _cd(state, str(bag / "alt")).startswith("Bu dizine geçiş izin kuralıyla engelli")
    assert state.root == proje


def test_cd_deny_kurali_cozulmus_yolla_yazilinca_bagdan_gecisi_engeller(
    tmp_path: Path, ev: Path
):
    gercek = tmp_path / "gercek"
    gercek.mkdir()
    bag = tmp_path / "bag"
    bag.symlink_to(gercek, target_is_directory=True)
    proje = tmp_path / "proje"
    proje.mkdir()
    _deny_cd(ev, f"/{gercek.resolve().as_posix()}")
    state = _state(proje, ev)

    assert _cd(state, str(bag)).startswith("Bu dizine geçiş izin kuralıyla engelli")
    assert state.root == proje


def test_cd_guvenilmeyen_izin_dosyasinda_uyarir(tmp_path: Path, ev: Path):
    eski, yeni = tmp_path / "a", tmp_path / "b"
    eski.mkdir()
    (yeni / ".claude").mkdir(parents=True)
    (yeni / ".claude" / "settings.local.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(*)"]}}), encoding="utf-8"
    )
    state = _state(eski, ev)

    mesaj = _cd(state, str(yeni))

    assert messages.PERMISSIONS_UNTRUSTED in mesaj
    assert state.allowed_commands == frozenset()


def test_loop_cd_komutunu_zamanlamaz(tmp_path: Path, ev: Path):
    state = _state(tmp_path, ev)
    command = build_registry().get("loop")
    assert command is not None
    mesaj = command.handler(state, "5m /cd ..")
    assert "cd" in mesaj
    assert len(state.cron) == 0


def test_tamamlayici_kokleri_her_cagrida_yeniden_okur(tmp_path: Path):
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

    eski, yeni = tmp_path / "a", tmp_path / "b"
    eski.mkdir()
    yeni.mkdir()
    (yeni / "sadece_yeni.txt").write_text("x", encoding="utf-8")
    kokler = [eski]
    tamamlayici = ReplCompleter([], lambda: tuple(kokler))
    belge = Document("@sadece", cursor_position=7)

    assert not list(tamamlayici.get_completions(belge, CompleteEvent()))
    kokler[0] = yeni
    assert [c.text for c in tamamlayici.get_completions(belge, CompleteEvent())] == [
        "@sadece_yeni.txt"
    ]


async def test_masaustu_cd_sekme_kokunu_tasir_ve_kok_dondurur(tmp_path: Path, ev: Path):
    """Masaüstü `/cd` sonucu `kok` taşır; arayüz sekmeyi yeni köke bağlar (`kokuDevral`)."""
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    eski, yeni = tmp_path / "a", tmp_path / "b"
    eski.mkdir()
    yeni.mkdir()
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=eski, home=ev)

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "cd", "arguman": str(yeni)})
    )

    sonuc = next(
        json.loads(satir)["veri"]
        for satir in reversed(satirlar)
        if json.loads(satir).get("tip") == "sonuc" and json.loads(satir).get("id") == "1"
    )
    assert sonuc["kok"] == str(yeni.resolve())
    assert oturum._state.root.resolve() == yeni.resolve()
