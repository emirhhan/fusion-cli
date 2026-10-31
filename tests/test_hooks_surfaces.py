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
from fusion_cli.engines.hooks.session import open_hook_session

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
    session = open_hook_session(proje, make_config())
    payload = dispatch_hooks("kanca.listele", session)
    assert payload["ok"] is True and payload["guvensiz_katmanlar"] == ["proje"]
    olaylar = {(row["olay"], row["atlandi"]) for row in payload["kancalar"]}
    assert ("PreToolUse", "") in olaylar
    assert ("Stop", hooks_config.REASON_UNTRUSTED) in olaylar
    assert payload["kullanici_dosyasi"].endswith("hooks.json")
    # Güven verildikten sonra liste hemen güncellenir (istek anında okunur).
    trust.trust_project(proje)
    payload = dispatch_hooks("kanca.listele", session)
    assert ("Stop", "") in {(row["olay"], row["atlandi"]) for row in payload["kancalar"]}
    assert dispatch_hooks("kanca.yok", session)["ok"] is False


def test_yapilandirma_varsayilanlari_tutarli():
    runtime = make_config().runtime
    assert runtime.hooks_enabled is True and runtime.claude_hooks is True
    assert runtime.hook_timeout_s == 60.0
