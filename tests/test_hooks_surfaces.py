"""Kanca yüzeyleri (P-009): `fusion hooks list|test`, REPL `/hooks`, masaüstü `kanca.listele`."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.appserver.hooks_routes import HOOK_ROUTES, dispatch_hooks
from fusion_cli.cli import hooks_commands
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.config import hooks as hooks_config
from fusion_cli.config import trust

from .fakes import make_config


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return ev


def _yaz_ayar(path: Path, hooks: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")


def _engelleyen(tmp_path: Path) -> str:
    script = tmp_path / "engel.py"
    script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "if 'rm -rf' in data['tool_input'].get('command', ''):\n"
        "    sys.stderr.write('yıkıcı komut'); sys.exit(2)\n",
        encoding="utf-8",
    )
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


@pytest.fixture
def proje(tmp_path, _izole_ev):
    root = tmp_path / "proje"
    root.mkdir()
    _yaz_ayar(
        hooks_config.user_hooks_file(),
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": _engelleyen(tmp_path)}],
                }
            ]
        },
    )
    _yaz_ayar(
        root / ".claude" / "settings.json",
        {"Stop": [{"hooks": [{"type": "command", "command": "depo-kancasi"}]}]},
    )
    return root


def test_cli_list_json_etkin_ve_guvensiz_satirlari_verir(proje, monkeypatch):
    monkeypatch.setattr(hooks_commands, "load_config", make_config)
    result = CliRunner().invoke(hooks_commands.app, ["list", "--json", "--path", str(proje)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    by_command = {row["command"]: row for row in payload["kancalar"]}
    assert by_command["depo-kancasi"]["skipped"] == hooks_config.REASON_UNTRUSTED
    assert payload["guvensiz_katmanlar"] == ["proje"]
    etkin = [row for row in payload["kancalar"] if not row["skipped"]]
    assert etkin[0]["event"] == "PreToolUse" and etkin[0]["matcher"] == "Bash"


def test_cli_test_engelleyen_kancada_cikis_2_ve_gerekce(proje, monkeypatch):
    monkeypatch.setattr(hooks_commands, "load_config", make_config)
    runner = CliRunner()
    blocked = runner.invoke(
        hooks_commands.app,
        [
            "test",
            "PreToolUse",
            "--tool",
            "run_shell",
            "--input",
            '{"command": "rm -rf /tmp/x"}',
            "--path",
            str(proje),
        ],
    )
    assert blocked.exit_code == 2
    assert "engel: evet" in blocked.output and "yıkıcı komut" in blocked.output
    passed = runner.invoke(
        hooks_commands.app,
        ["test", "PreToolUse", "--input", '{"command": "ls"}', "--path", str(proje)],
    )
    assert passed.exit_code == 0 and "engel: hayır" in passed.output
    unknown = runner.invoke(hooks_commands.app, ["test", "Uydurma", "--path", str(proje)])
    assert unknown.exit_code == 2 and "Bilinmeyen olay" in unknown.output


def test_repl_hooks_komutu_listeyi_gosterir(proje):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    registry = build_registry()
    command = registry.get("hooks")
    assert command is not None and registry.get("kancalar") is command
    state = ReplState(config=make_config(), memory=null_memory(), root=proje, home=proje.parent)
    text = command.handler(state, "")
    assert "PreToolUse [Bash]" in text and "atlandı: proje güvenilmiyor" in text
    assert "fusion trust" in text
    assert command.handler(state, "sil").startswith("Kullanım: /hooks")


def test_kanca_listesi_bossa_nasil_eklenecegini_soyler(tmp_path):
    from fusion_cli.cli.hooks_view import hook_list_lines

    lines = hook_list_lines(hooks_config.load_hooks(tmp_path))
    assert "Tanımlı kanca yok" in lines[0] and "hooks.json" in lines[0]


def test_masaustu_kanca_listele_rpc(proje):
    assert "kanca.listele" in HOOK_ROUTES
    state = _repl_durumu(proje)
    payload = dispatch_hooks("kanca.listele", state)
    assert payload["ok"] is True and payload["guvensiz_katmanlar"] == ["proje"]
    assert payload["etkin"] is True and payload["claude_kancalari"] is False
    olaylar = {(row["olay"], row["atlandi"]) for row in payload["kancalar"]}
    assert ("PreToolUse", "") in olaylar
    assert ("Stop", hooks_config.REASON_UNTRUSTED) in olaylar
    assert payload["kullanici_dosyasi"].endswith("hooks.json")
    # Güven verildikten sonra liste hemen güncellenir (istek anında okunur).
    trust.trust_project(proje)
    payload = dispatch_hooks("kanca.listele", state)
    assert ("Stop", "") in {(row["olay"], row["atlandi"]) for row in payload["kancalar"]}
    assert dispatch_hooks("kanca.yok", state)["ok"] is False


def test_masaustu_kanca_ayar_rpc_yazar_ve_acik_oturumda_etkili(proje):
    state = _repl_durumu(proje)
    kapali = dispatch_hooks("kanca.ayar", state, {"anahtar": "hooks_enabled", "deger": False})
    assert kapali["ok"] is True and kapali["etkin"] is False
    assert state.config.runtime.hooks_enabled is False
    assert state.hooks().refresh().disabled_reason == "runtime.hooks_enabled: false"
    # `make_config` yazma hedefi geçici dosyadır (gerçek kullanıcı config'i değil).
    assert "hooks_enabled: false" in state.config.source.read_text(encoding="utf-8")
    acik = dispatch_hooks("kanca.ayar", state, {"anahtar": "claude_hooks", "deger": True})
    assert acik["claude_kancalari"] is True
    hatali = dispatch_hooks("kanca.ayar", state, {"anahtar": "temperature", "deger": True})
    assert hatali["ok"] is False and "geçersiz" in hatali["metin"]


def test_yapilandirma_varsayilanlari_tutarli():
    runtime = make_config().runtime
    # Claude kullanıcı dosyası (ECC vb. betikler) varsayılan kapalı; açıkça seçilir.
    assert runtime.hooks_enabled is True and runtime.claude_hooks is False
    assert runtime.hook_timeout_s == 60.0


# --- Oturum yaşam döngüsü ve canlı ayar (inceleme düzeltmeleri, 31 Ekim) ------------ #


def _repl_durumu(root: Path, **kwargs):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    return ReplState(
        config=make_config(), memory=null_memory(), root=root, home=root.parent, **kwargs
    )


def _kaydeden_kancalar(tmp_path: Path) -> Path:
    """SessionStart/SessionEnd yükünü satır satır yazan kullanıcı kancaları."""
    kayit = tmp_path / "oturum.jsonl"
    script = tmp_path / "kaydet.py"
    script.write_text(
        "import json, sys\n"
        f"open({str(kayit)!r}, 'a', encoding='utf-8').write(sys.stdin.read().strip() + '\\n')\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    grup = [{"hooks": [{"type": "command", "command": command}]}]
    _yaz_ayar(hooks_config.user_hooks_file(), {"SessionStart": grup, "SessionEnd": grup})
    return kayit


def _olaylar(kayit: Path) -> list[tuple[str, str, str]]:
    satirlar = [json.loads(s) for s in kayit.read_text(encoding="utf-8").splitlines()]
    return [
        (s["hook_event_name"], s.get("source") or s.get("reason"), s["session_id"])
        for s in satirlar
    ]


def test_config_degisince_kanca_ayari_acik_oturumda_hemen_etkili(proje):
    from dataclasses import replace

    state = _repl_durumu(proje)
    assert state.hooks().refresh().commands
    state.config = replace(state.config, runtime=replace(state.config.runtime, hooks_enabled=False))
    assert state.hooks().refresh().disabled_reason == "runtime.hooks_enabled: false"


async def test_worktree_kok_degisimi_oturumu_surdurur_yeniden_baslatmaz(tmp_path):
    kayit = _kaydeden_kancalar(tmp_path)
    ana, agac = tmp_path / "ana", tmp_path / "agac"
    ana.mkdir()
    agac.mkdir()
    state = _repl_durumu(ana)
    session = state.hooks()
    await session.start()
    state.root = agac
    assert state.hooks() is session and session.root == agac
    await state.hooks().start()
    await state.hooks().end("prompt_input_exit")
    assert [olay[:2] for olay in _olaylar(kayit)] == [
        ("SessionStart", "startup"),
        ("SessionEnd", "prompt_input_exit"),
    ]


async def test_reset_eski_oturumu_clear_ile_kapatip_yenisini_clear_ile_acar(tmp_path):
    kayit = _kaydeden_kancalar(tmp_path)
    state = _repl_durumu(tmp_path)
    await state.hooks().start()
    state.reset_history()
    await state.hooks().start()
    await state.hooks().end("prompt_input_exit")
    assert [olay[:2] for olay in _olaylar(kayit)] == [
        ("SessionStart", "startup"),
        ("SessionEnd", "clear"),
        ("SessionStart", "clear"),
        ("SessionEnd", "prompt_input_exit"),
    ]


async def test_sohbet_degisince_eski_oturum_kapanir_yenisi_resume_ile_acilir(tmp_path):
    from fusion_cli.core.types import Message

    kayit = _kaydeden_kancalar(tmp_path)
    state = _repl_durumu(tmp_path, conversation_id="ilk")
    await state.hooks().start()
    state.conversation_id = "ikinci"
    state.history = [Message("user", "eski soru")]
    await state.hooks().start()
    assert _olaylar(kayit) == [
        ("SessionStart", "startup", "ilk"),
        ("SessionEnd", "other", "ilk"),
        ("SessionStart", "resume", "ikinci"),
    ]


async def test_gecmisle_acilan_oturum_resume_kaynagiyla_baslar(tmp_path):
    from fusion_cli.core.types import Message

    kayit = _kaydeden_kancalar(tmp_path)
    state = _repl_durumu(tmp_path)
    state.history = [Message("user", "önceki")]
    await state.hooks().start()
    assert [olay[:2] for olay in _olaylar(kayit)] == [("SessionStart", "resume")]
