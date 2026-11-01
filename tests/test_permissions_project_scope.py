"""`/permissions` kuralı proje `settings.json`'a da kaydedebilir — Claude gibi (#83).

Claude (permissions#manage-permissions): kural kullanıcı, proje ya da yerel dosyaya kaydedilir.
Fusion: `--user` → `~/.claude/settings.json`, `--project` → `<proje>/.claude/settings.json`,
bayraksız → yerel `settings.local.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.repl.permissions_command import permissions
from fusion_cli.config import permission_admin, trust
from fusion_cli.config.permission_rules import PermissionDecision, PermissionRule
from fusion_cli.config.trust import PROJECT_SETTINGS_PATH

from .fakes import make_config


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")


@pytest.fixture
def proje(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    return kok


def _state(proje):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    return ReplState(config=make_config(), memory=null_memory(), root=proje, home=proje / "ev")


def _oku(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_repl_project_bayragi_proje_settings_jsona_yazar_ve_siler(proje):
    state = _state(proje)
    sonuc = permissions(state, "add deny Bash(git push *) --project")
    hedef = proje / PROJECT_SETTINGS_PATH
    assert str(hedef) in sonuc
    assert _oku(hedef)["permissions"]["deny"] == ["Bash(git push *)"]
    assert not (proje / trust.PROJECT_PERMISSIONS_PATH).exists()
    assert "silindi" in permissions(state, "remove deny Bash(git push *)")
    assert _oku(hedef)["permissions"]["deny"] == []


def test_project_ve_user_birlikte_kullanilamaz(proje):
    sonuc = permissions(_state(proje), "add allow Bash(ls) --project --user")
    assert "Kullanım" in sonuc


def test_proje_dosyasina_yazmak_guven_vermez(proje):
    rule = PermissionRule("Bash", "npm test *", PermissionDecision.ALLOW)
    change = permission_admin.add_permission_rule(proje, rule, project_shared=True)
    assert change.path == proje / PROJECT_SETTINGS_PATH and not change.fell_back
    # Paylaşılan proje dosyasının allow kuralları yine klasör güvenine bağlıdır.
    assert not trust.is_project_settings_trusted(proje)


def test_cli_project_bayragi(proje):
    from fusion_cli.cli.app import app

    sonuc = CliRunner().invoke(
        app, ["permissions", "add", "ask", "Bash(npm publish *)", "--project", "--path", str(proje)]
    )
    assert sonuc.exit_code == 0, sonuc.output
    assert _oku(proje / PROJECT_SETTINGS_PATH)["permissions"]["ask"] == ["Bash(npm publish *)"]


def test_rpc_paylasilan_kapsam(proje):
    from fusion_cli.appserver.permissions_rpc import add_rule

    sonuc = add_rule(proje, {"kalip": "Read(./.env)", "karar": "deny", "kapsam": "paylasilan"})
    assert sonuc["ok"] is True and sonuc["dosya"] == str(proje / PROJECT_SETTINGS_PATH)
    assert _oku(proje / PROJECT_SETTINGS_PATH)["permissions"]["deny"] == ["Read(./.env)"]
