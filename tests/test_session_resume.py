"""Fusion'ın kendi sohbetini sürdürme: `--continue/--resume/--fork-session/--name`, `/resume`,
`/rename`, `/branch` (P-014).

Ölçüldü (31 Ekim): transcript deposu sohbetleri kimlikle yazıp geri okuyabiliyordu ama
CLI her açılışta yeni kimlik üretiyor, önceki konuşmaya dönmenin hiçbir yolu yoktu.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.appserver.commands import list_commands, run_command
from fusion_cli.cli.repl import session_resume
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.transcript_store import (
    TranscriptStore,
    copy_conversation,
    find_conversation,
    list_conversations,
    load_transcript_messages,
)
from fusion_cli.core.errors import SessionNotFoundError
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _seed(memory: Path, root: Path, conversation_id: str, *turns: tuple[str, str]) -> None:
    store = TranscriptStore(memory, root, conversation_id=conversation_id)
    for soru, cevap in turns:
        store.record_user(soru)
        store.record_assistant(cevap)


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    config = make_config(memory_dir=tmp_path / "bellek")
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(config=config, memory=null_memory(), root=root, home=tmp_path / "ev")


def _run(state: ReplState, line: str) -> str:
    name, argument = parse(line)
    command = build_registry().get(name)
    assert command is not None, line
    return command.handler(state, argument)


# --- Transcript deposu: ad, geri sarma, kopya, arama ---------------------------------- #


def test_sohbet_adi_listede_baslik_olur(tmp_path):
    memory, root = tmp_path / "m", tmp_path / "r"
    _seed(memory, root, "s-1", ("oyun yaz", "tamam"))
    TranscriptStore(memory, root, conversation_id="s-1").record_name("Oyun projesi")

    (ref,) = list_conversations(memory, root)
    assert ref.name == "Oyun projesi"
    assert ref.title == "Oyun projesi"
    assert ref.message_count == 2, "ad bir mesaj değildir, sayılmaz"


def test_geri_sarma_olayi_yuklenen_gecmisi_kirpar(tmp_path):
    memory, root = tmp_path / "m", tmp_path / "r"
    _seed(memory, root, "s-1", ("a", "1"), ("b", "2"), ("c", "3"))
    store = TranscriptStore(memory, root, conversation_id="s-1")
    store.record_rewind(1)
    store.record_user("d")

    assert [m.content for m in load_transcript_messages(memory, root, conversation_id="s-1")] == [
        "a",
        "1",
        "d",
    ]


def test_liste_sayimi_geri_sarmayi_hesaba_katar(tmp_path):
    """Ölçüldü (31 Ekim): `message_count` ConversationRewound'u görmeyip geri sarılmış
    mesajları da sayıyor, /resume listesi yüklenecekten fazla mesaj gösteriyordu."""
    memory, root = tmp_path / "m", tmp_path / "r"
    _seed(memory, root, "s-1", ("a", "1"), ("b", "2"), ("c", "3"))
    store = TranscriptStore(memory, root, conversation_id="s-1")
    store.record_rewind(1)
    store.record_user("d")

    (ref,) = list_conversations(memory, root)
    assert ref.message_count == 3, "a, 1, d"


def test_copy_conversation_yeni_kimlige_yazar_ve_dogrular(tmp_path):
    memory, root = tmp_path / "m", tmp_path / "r"
    history = [
        Message("user", "soru"),
        Message("tool", "araç çıktısı", tool_call_id="t1", name="run_shell"),
        Message("assistant", "cevap"),
    ]
    count = copy_conversation(memory, root, history, target_id="kopya", name="Dal")

    assert count == 2
    yuklenen = load_transcript_messages(memory, root, conversation_id="kopya")
    assert [(m.role, m.content) for m in yuklenen] == [("user", "soru"), ("assistant", "cevap")]
    assert find_conversation(memory, root, "dal").conversation_id == "kopya"


def test_copy_conversation_kullanici_mesaji_yoksa_reddeder(tmp_path):
    with pytest.raises(ValueError):
        copy_conversation(
            tmp_path / "m", tmp_path / "r", [Message("assistant", "x")], target_id="k"
        )


def test_find_conversation_kimlik_ad_ve_tek_onek(tmp_path):
    memory, root = tmp_path / "m", tmp_path / "r"
    _seed(memory, root, "session-aaaa1111", ("ilk", "1"))
    _seed(memory, root, "session-aaaa2222", ("ikinci", "2"))
    TranscriptStore(memory, root, conversation_id="session-aaaa2222").record_name("Fatura")

    assert find_conversation(memory, root, "session-aaaa1111").conversation_id == "session-aaaa1111"
    assert find_conversation(memory, root, "FATURA").conversation_id == "session-aaaa2222"
    assert find_conversation(memory, root, "session-aaaa") is None, "iki sohbet eşleşir; seçilmez"
    assert find_conversation(memory, root, "session-aaaa1").conversation_id == "session-aaaa1111"
    assert find_conversation(memory, root, "ses") is None, "kısa önek yanlış sohbeti açar"
    assert find_conversation(memory, root, "yok") is None


# --- Açılış bayrakları ----------------------------------------------------------------- #


def test_continue_son_sohbeti_gecmisiyle_acar(tmp_path):
    memory, root = tmp_path / "m", tmp_path / "r"
    _seed(memory, root, "eski", ("eski soru", "eski cevap"))
    _seed(memory, root, "yeni", ("yeni soru", "yeni cevap"))

    target = session_resume.resolve_launch(memory, root, continue_last=True)

    assert target is not None
    assert target.conversation_id == "yeni"
    assert [m.content for m in target.history] == ["yeni soru", "yeni cevap"]


def test_continue_sohbet_yoksa_hata_verir_sessizce_yeni_acmaz(tmp_path):
    with pytest.raises(SessionNotFoundError):
        session_resume.resolve_launch(tmp_path / "m", tmp_path / "r", continue_last=True)
    with pytest.raises(SessionNotFoundError):
        session_resume.resolve_launch(tmp_path / "m", tmp_path / "r", resume="yok")


def test_fork_session_kopya_acar_ozgun_degismez(tmp_path):
    memory, root = tmp_path / "m", tmp_path / "r"
    _seed(memory, root, "kaynak", ("soru", "cevap"))

    target = session_resume.resolve_launch(memory, root, resume="kaynak", fork=True, name="Dal")

    assert target is not None
    assert target.conversation_id != "kaynak"
    assert target.forked_from == "kaynak"
    assert target.name == "Dal"
    kimlikler = {ref.conversation_id: ref for ref in list_conversations(memory, root)}
    assert kimlikler["kaynak"].name == ""
    assert kimlikler[target.conversation_id].name == "Dal"


def test_fork_session_kaynaksiz_hata_verir(tmp_path):
    """Ölçüldü (31 Ekim): `--fork-session` tek başına sessizce yok sayılıp boş sohbet açılıyordu."""
    memory, root = tmp_path / "m", tmp_path / "r"
    with pytest.raises(SessionNotFoundError, match="--continue"):
        session_resume.resolve_launch(memory, root, fork=True)


def test_name_yeni_sohbete_ad_verir_ve_resume_ile_bulunur(tmp_path):
    memory, root = tmp_path / "m", tmp_path / "r"
    target = session_resume.resolve_launch(memory, root, name="Deneme")
    assert target is not None and target.history == ()
    TranscriptStore(memory, root, conversation_id=target.conversation_id).record_user("merhaba")

    bulunan = session_resume.resolve_launch(memory, root, resume="deneme")
    assert bulunan is not None and bulunan.conversation_id == target.conversation_id


def test_bayraksiz_acilis_yeni_sohbettir(tmp_path):
    assert session_resume.resolve_launch(tmp_path / "m", tmp_path / "r") is None


# --- Slash komutları ---------------------------------------------------------------------- #


def test_resume_komutu_sohbeti_duruma_baglar(state):
    _seed(state.config.memory_dir, state.root, "s-1", ("soru", "cevap"))
    TranscriptStore(state.config.memory_dir, state.root, conversation_id="s-1").record_name("Ad")
    state.history = [Message("user", "başka")]

    sonuc = _run(state, "/resume s-1")

    assert "Sürdürülüyor" in sonuc and "Ad" in sonuc
    assert state.conversation_id == "s-1"
    assert state.conversation_name == "Ad"
    assert [m.content for m in state.history] == ["soru", "cevap"]
    assert _run(state, "/resume s-1") == "Bu sohbet zaten açık."


def test_resume_listesi_bos_ve_bulunamayan(state):
    assert "yok" in _run(state, "/resume")
    _seed(state.config.memory_dir, state.root, "s-1", ("soru", "cevap"))
    assert "bulunamadı" in _run(state, "/resume olmayan")


def test_rename_adi_kalici_yazar(state):
    _seed(state.config.memory_dir, state.root, state.conversation_id, ("soru", "cevap"))
    state.history = [Message("user", "ödeme akışını düzelt\nayrıntı"), Message("assistant", "ok")]
    # Claude Code (#224): argümansız `/rename` geçmişten otomatik ad üretir.
    assert _run(state, "/rename") == "Sohbet adı: ödeme akışını düzelt"

    assert _run(state, "/rename Yeni ad") == "Sohbet adı: Yeni ad"

    assert state.conversation_name == "Yeni ad"
    (ref,) = list_conversations(state.config.memory_dir, state.root)
    assert ref.name == "Yeni ad"


def test_branch_konusmayi_yeni_sohbete_kopyalar(state):
    assert "önce bir mesaj" in _run(state, "/branch")
    kaynak = state.conversation_id
    _seed(state.config.memory_dir, state.root, kaynak, ("soru", "cevap"))
    state.history = [Message("user", "soru"), Message("assistant", "cevap")]

    sonuc = _run(state, "/branch deneme")

    assert "Dallandırıldı: 2 mesaj" in sonuc
    assert state.conversation_id != kaynak
    assert state.conversation_name == "deneme"
    refs = {
        ref.conversation_id: ref for ref in list_conversations(state.config.memory_dir, state.root)
    }
    assert refs[state.conversation_id].name == "deneme"
    assert refs[kaynak].name == ""
    # Claude Code (#224): onay iki kimliği de basar.
    assert state.conversation_id in sonuc and kaynak in sonuc


def test_branch_argumansiz_adi_ilk_istemden_alir(state):
    state.history = [Message("user", "giriş sayfasını yap"), Message("assistant", "tamam")]
    _run(state, "/branch")
    assert state.conversation_name == "giriş sayfasını yap"


def test_branch_harness_notlu_gecmisi_notsuz_kopyalar(state):
    """Ölçüldü (31 Ekim): FUSION_NOT: notu kopyaya yazılmaya çalışılıyor, transcript onu
    atlıyor ve doğrulama `ValueError` ile düşüyordu; öneksiz harness notu (compaction
    özeti) ise kopyaya sıradan kullanıcı mesajı olarak giriyordu."""
    state.history = [
        Message("user", "soru"),
        Message("assistant", "cevap"),
        Message("user", "FUSION_NOT: edit_streak", harness_note=True),
        Message("user", "[önceki konuşmanın özeti]\nözet", harness_note=True),
        Message("user", "ikinci"),
        Message("assistant", "cevap2"),
    ]

    sonuc = _run(state, "/branch")

    assert "Dallandırıldı: 4 mesaj" in sonuc, sonuc
    yuklenen = load_transcript_messages(
        state.config.memory_dir, state.root, conversation_id=state.conversation_id
    )
    assert [m.content for m in yuklenen] == ["soru", "cevap", "ikinci", "cevap2"]


def test_masaustu_koprusu_rename_destekler_resume_branch_reddeder(state):
    registry = build_registry()
    destek = {item["ad"]: item["destekleniyor"] for item in list_commands(registry)}
    assert destek["rename"] is True
    assert destek["resume"] is False and destek["branch"] is False
    assert run_command(registry, state, "rename", "Masa")["metin"] == "Sohbet adı: Masa"
    assert run_command(registry, state, "resume", "")["ok"] is False


# --- CLI ----------------------------------------------------------------------------------- #


def test_cli_continue_sohbet_yoksa_hata_ile_cikar(tmp_path, monkeypatch):
    from fusion_cli.cli import app as app_module

    monkeypatch.setattr(app_module, "load_config", lambda: make_config(memory_dir=tmp_path / "m"))
    monkeypatch.setattr(app_module, "evaluate", lambda *_a, **_k: type("R", (), {"state": None})())
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app_module.app, ["--continue"])

    assert result.exit_code == 1
    assert "sürdürülecek sohbet yok" in (result.stderr or "") + result.stdout
