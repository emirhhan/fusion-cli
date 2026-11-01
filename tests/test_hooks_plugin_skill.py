"""Eklenti ve beceri frontmatter kancaları (#96) — Claude Code "Hook locations".

Ölçüldü (1 Kasım): `PLUGIN_HOOKS_ACTIVE = False`; eklentinin `hooks/hooks.json`'u ve
becerinin frontmatter `hooks:` bloğu listede görünüp hiç çalışmıyordu.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from fusion_cli.config import hooks as hooks_config
from fusion_cli.config import plugin_store
from fusion_cli.config.plugin_hooks import plugin_environment, plugin_hooks
from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.engines.agent.skill_hooks import activate_skill, after_skill_tool
from fusion_cli.engines.hooks.session import HookSession

#: Kanca yükleme testleri güvenilmiş klasörde (#108; kapı: test_hooks_workspace_trust).
pytestmark = pytest.mark.usefixtures("guvenilir_klasor")


@pytest.fixture(autouse=True)
def _kancalar_acik(monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)


_BLOCK = {
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "kontrol"}]}]
    }
}


def _fake_blocks(monkeypatch, tmp_path: Path) -> Path:
    """Tek etkin eklenti `denetim`: `hooks/hooks.json` içinde bir PreToolUse kancası."""
    from fusion_cli.config import plugin_hooks as plugin_hooks_module

    root = tmp_path / "eklentiler" / "denetim"

    def _blocks(base=None, project=None):
        yield "eklenti:denetim", "denetim@yerel", root / "hooks" / "hooks.json", _BLOCK, root

    monkeypatch.setattr(plugin_hooks_module, "_blocks", _blocks)
    monkeypatch.setattr(plugin_hooks_module, "plugin_values", lambda _root, _key: ({}, {}))
    return root


def test_eklenti_kancalari_yukleyicide_kok_ve_veri_yoluyla(monkeypatch, tmp_path):
    root = _fake_blocks(monkeypatch, tmp_path)
    commands, skipped = plugin_hooks(default_timeout_s=600.0)
    assert not skipped
    (command,) = commands
    assert command.source == "eklenti:denetim"
    env = plugin_environment(command)
    assert env["CLAUDE_PLUGIN_ROOT"] == str(root)
    assert Path(env["CLAUDE_PLUGIN_DATA"]).is_dir()
    loaded = hooks_config.load_hooks(tmp_path / "proje", home=tmp_path / "ev")
    assert [c.command for c in loaded.for_event(HookEvent.PRE_TOOL_USE, ("Bash",))] == ["kontrol"]
    assert plugin_store.PLUGIN_HOOKS_ACTIVE is True


def test_yalniz_yonetilen_kancalar_eklentiyi_de_atlar(monkeypatch, tmp_path):
    _fake_blocks(monkeypatch, tmp_path)
    managed = tmp_path / "managed.json"
    managed.write_text(json.dumps({"allowManagedHooksOnly": True}), encoding="utf-8")
    monkeypatch.setattr(hooks_config, "managed_settings_file", lambda: managed)
    loaded = hooks_config.load_hooks(tmp_path / "proje", home=tmp_path / "ev")
    assert not loaded.commands
    assert any(skip.reason == hooks_config.REASON_MANAGED_ONLY for skip in loaded.skipped)


def _skill(folder: Path, *, once: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    marker = folder / "calisti.txt"
    command = f"{sys.executable} -c \"open(r'{marker}', 'a').write('x')\""
    handler: dict[str, object] = {"type": "command", "command": command}
    if once:
        handler["once"] = True
    meta = {
        "name": "bicim",
        "description": "biçimle",
        "hooks": {"PostToolUse": [{"matcher": "Write", "hooks": [handler]}]},
    }
    path.write_text(f"---\n{yaml.safe_dump(meta)}---\nGövde\n", encoding="utf-8")
    return path


def _emit(session: HookSession) -> None:
    session.root.mkdir(parents=True, exist_ok=True)
    asyncio.run(session.emit(HookEvent.POST_TOOL_USE, subjects=("Write",)))


def test_beceri_cagrilinca_kancalari_oturum_boyu_calisir(tmp_path):
    skill = _skill(tmp_path / "beceriler" / "bicim")
    session = HookSession(root=tmp_path / "proje", loader=HookSet)
    assert activate_skill(session, "bicim", skill) == 1
    assert session.current().commands[0].source == "beceri:bicim"
    _emit(session)
    _emit(session)
    assert (skill.parent / "calisti.txt").read_text() == "xx"
    # Aynı beceri ikinci kez çağrılınca tanım yinelenmez.
    activate_skill(session, "bicim", skill)
    assert len(session.session_commands) == 1


def test_once_ilk_basarili_calismadan_sonra_kalkar(tmp_path):
    skill = _skill(tmp_path / "beceriler" / "bicim", once=True)
    session = HookSession(root=tmp_path / "proje", loader=HookSet)
    activate_skill(session, "bicim", skill)
    _emit(session)
    _emit(session)
    assert (skill.parent / "calisti.txt").read_text() == "x"
    assert session.session_commands == ()


def test_guvenilmeyen_proje_becerisinin_kancasi_etkilesimli_oturumda_eklenmez(tmp_path):
    root = tmp_path / "proje"
    skill = _skill(root / ".claude" / "skills" / "bicim")
    interactive = HookSession(root=root, loader=HookSet, interactive=True)
    assert activate_skill(interactive, "bicim", skill) == 0
    headless = HookSession(root=root, loader=HookSet, interactive=False)
    assert activate_skill(headless, "bicim", skill) == 1


def test_read_skill_basarili_olunca_kancalar_baglanir(tmp_path):
    skill_path = _skill(tmp_path / "beceriler" / "bicim")
    skill = SimpleNamespace(name="bicim", path=skill_path)
    library = SimpleNamespace(get_skill=lambda name: skill if name == "bicim" else None)
    deps = SimpleNamespace(capabilities=library)
    session = HookSession(root=tmp_path / "proje", loader=HookSet)
    after_skill_tool(deps, session, "read_skill", {"name": "bicim", "file": "ek.md"}, ok=True)
    after_skill_tool(deps, session, "read_skill", {"name": "bicim"}, ok=False)
    assert session.session_commands == ()
    after_skill_tool(deps, session, "read_skill", {"name": "bicim"}, ok=True)
    assert len(session.session_commands) == 1


def test_eklenti_mcp_sunucusu_claude_adiyla_cagrilir():
    from fusion_cli.engines.agent.hook_services import fusion_server_name

    # Claude adı `plugin:<eklenti>:<sunucu>` (#400); araç adındaki `:` kayıtta `_` olur.
    assert fusion_server_name("plugin:rapor-araclari:veri") == "plugin:rapor-araclari:veri"
    assert fusion_server_name("tara") == "tara"
