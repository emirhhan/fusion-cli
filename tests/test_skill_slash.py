"""`/<beceri> argüman`, `.claude/commands` ve `$beceri` yazımı (P-019, P-052).

Ölçüldü (31 Ekim): REPL'de `_COMMANDS` sabitti; `/deploy` "bilinmeyen komut" veriyordu, `/skills`
yalnız listeliyordu; masaüstünde `.claude/commands` hiç taranmıyordu.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver.commands import list_commands, run_command
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.commands import build_registry, is_command_line, parse
from fusion_cli.cli.repl.skill_commands import skill_prefix_to_slash
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.capabilities import CapabilityRegistry


@pytest.fixture
def kutuphane(tmp_path: Path) -> tuple[Path, Path]:
    home, root = tmp_path / "ev", tmp_path / "proje"
    (home / ".claude" / "skills" / "rapor").mkdir(parents=True)
    (home / ".claude" / "skills" / "rapor" / "SKILL.md").write_text(
        "---\nname: rapor\ndescription: Haftalık rapor yazar\nallowed-tools: Read, Grep\n"
        "argument-hint: '[hafta]'\n---\nRapor: $ARGUMENTS\nDurum: !`echo canli`",
        encoding="utf-8",
    )
    (home / ".claude" / "skills" / "gizli").mkdir(parents=True)
    (home / ".claude" / "skills" / "gizli" / "SKILL.md").write_text(
        "---\nname: gizli\nuser-invocable: false\n---\nx", encoding="utf-8"
    )
    (home / ".claude" / "skills" / "model").mkdir(parents=True)
    (home / ".claude" / "skills" / "model" / "SKILL.md").write_text(
        "---\nname: model\ndescription: yerleşikle çakışır\n---\nx", encoding="utf-8"
    )
    (root / ".claude" / "commands" / "git").mkdir(parents=True)
    (root / ".claude" / "commands" / "git" / "commit.md").write_text(
        "Şu bağlamla commit'le: $1", encoding="utf-8"
    )
    return home, root


@pytest.fixture
def state(kutuphane, tmp_path: Path) -> ReplState:
    home, root = kutuphane
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source),
        memory=null_memory(),
        root=root,
        home=home,
        capabilities=CapabilityRegistry(home, root),
    )


def test_beceri_ve_komut_dosyalari_slash_komutu_olur(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    rapor = registry.get("rapor")
    assert rapor is not None and rapor.group == "Beceri"
    assert rapor.display == "/rapor [hafta]"
    assert registry.get("git:commit") is not None
    assert "/rapor" in registry.completion_words()
    assert "/git:commit" in registry.completion_words()
    assert registry.is_dynamic("rapor") and not registry.is_dynamic("help")


def test_yerlesik_komut_ayni_adli_beceriyi_golgeler(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    assert registry.get("model") is not None
    assert registry.get("model").group == "Model"  # type: ignore[union-attr]
    assert not registry.is_dynamic("model")


def test_user_invocable_false_beceri_sunulmaz(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    assert registry.get("gizli") is None


def test_isleyici_gorev_baglam_ve_arac_kisitini_hazirlar(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)
    komut = registry.get("rapor")
    assert komut is not None

    sonuc = komut.handler(state, "42")

    assert "rapor" in sonuc
    assert state.pending_task == "42"
    assert "Rapor: 42" in state.pending_context
    assert "Durum: canli" in state.pending_context  # ~/.claude güvenilir kök, auto kipi
    assert state.pending_tools == frozenset(
        {"read_file", "view_file", "grep_search", "search_code"}
    )
    ekler = state.take_pending_extras()
    assert ekler.merged_tools({"read_file", "run_shell"}) == {"read_file"}
    assert state.pending_context == "" and state.pending_tools is None


def test_plan_kipinde_shell_baglami_calismaz(state: ReplState):
    state.approval = ApprovalMode.PLAN
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    registry.get("rapor").handler(state, "")  # type: ignore[union-attr]

    assert "[komut çalıştırılmadı" in state.pending_context
    assert "rapor" in state.pending_task  # varsayılan görev metni


def test_komut_dosyasi_govdeyi_gorev_yapar(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    registry.get("git:commit").handler(state, "kapsam: arayüz")  # type: ignore[union-attr]

    assert state.pending_task == "Şu bağlamla commit'le: kapsam:"
    assert state.pending_context == ""


def test_dolar_yazimi_bilinen_beceri_icin_slash_olur(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    assert skill_prefix_to_slash("$rapor 42", registry.is_dynamic) == "/rapor 42"
    assert skill_prefix_to_slash("$5 fiyat", registry.is_dynamic) == "$5 fiyat"
    assert skill_prefix_to_slash("$model x", registry.is_dynamic) == "$model x"
    assert is_command_line("/rapor 42") and parse("/git:commit a") == ("git:commit", "a")


async def test_masaustu_komut_listesinde_beceri_grubu_ve_calistirma(kutuphane):
    home, root = kutuphane
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    await session.handle(Request(id="l", name="komut.listele", data={}))
    listed = json.loads(lines[-1])["veri"]["komutlar"]
    await session.handle(
        Request(id="r", name="komut.calistir", data={"ad": "rapor", "arguman": "7"})
    )
    sonuc = json.loads(lines[-1])["veri"]
    await session.close()

    beceri = next(c for c in listed if c["ad"] == "rapor")
    assert beceri["grup"] == "Beceri" and beceri["destekleniyor"] is True
    assert sonuc["ok"] is True and sonuc["gorev"] == "7"
    assert "Rapor: 7" in session._state.pending_context


def test_run_command_koprusu_dinamik_komutu_calistirir(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    assert any(c["ad"] == "git:commit" for c in list_commands(registry))
    sonuc = run_command(registry, state, "git:commit", "x")

    assert sonuc["ok"] is True
    assert state.pending_task.startswith("Şu bağlamla")


# --- İnceleme bulguları (31 Ekim) --------------------------------------------- #


def test_guvenilen_projenin_becerisinde_yalniz_salt_okur_komut_calisir(
    state: ReplState, monkeypatch
):
    """Ölçüldü: proje becerisi `fusion trust` sonrası `git pull` ile değişse de tam yetkiliydi."""
    from fusion_cli.cli.repl import skill_commands as modul
    from fusion_cli.config.trust import TrustState

    monkeypatch.setattr(modul.trust, "resolve_project_trust", lambda root: TrustState(True, "test"))
    beceri = state.root / ".claude" / "skills" / "proje-b"
    beceri.mkdir(parents=True)
    (beceri / "SKILL.md").write_text(
        "---\nname: proje-b\n---\nYaz: !`touch sizinti`\nOku: !`echo guvenli`", encoding="utf-8"
    )
    state.capabilities = CapabilityRegistry(state.home, state.root)
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    registry.get("proje-b").handler(state, "")  # type: ignore[union-attr]

    assert not (state.root / "sizinti").exists()
    assert "Oku: guvenli" in state.pending_context
    assert "[komut çalıştırılmadı: touch sizinti]" in state.pending_context


def test_beceri_komutu_fusion_motorunu_agent_motoruna_cevirir(state: ReplState):
    """Ölçüldü: Fusion motorunda beceri gövdesi kullanılmıyor, sonraki agent turuna sızıyordu."""
    from fusion_cli.cli.repl.state import Engine

    state.engine = Engine.FUSION
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    cikti = registry.get("rapor").handler(state, "")  # type: ignore[union-attr]

    assert state.engine is Engine.AGENT
    assert "agent" in cikti.lower()


async def test_masaustu_beceri_komutu_olay_dongusunu_bloklamaz(kutuphane, monkeypatch):
    """Ölçüldü: `!`cmd`` 10 sn'ye kadar bloklayan `subprocess.run` olay döngüsünde koşuyordu."""
    import threading

    from fusion_cli.appserver import session as modul

    home, root = kutuphane
    gorulen: list[str] = []
    gercek = modul.run_command

    def kaydet(*args, **kwargs):
        gorulen.append(threading.current_thread().name)
        return gercek(*args, **kwargs)

    monkeypatch.setattr(modul, "run_command", kaydet)
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)
    await session.handle(
        Request(id="r", name="komut.calistir", data={"ad": "rapor", "arguman": "7"})
    )
    await session.close()

    assert gorulen and gorulen[0] != threading.main_thread().name
    assert json.loads(lines[-1])["veri"]["ok"] is True
