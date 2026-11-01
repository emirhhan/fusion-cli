"""Ajan frontmatter'ındaki yapılandırılmış ayarlar kaybolmaz."""

from __future__ import annotations

from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.tools.frontmatter import parse_frontmatter


def test_yapilandirilmis_kancalar_komut_eslestirici_sure_ve_http_alanlarini_korur():
    fields = parse_frontmatter("""---
name: denetci
description: inceler
initialPrompt: İlk görevi incele.
omitClaudeMd: true
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "python check.py"
          timeout: 17
  Stop:
    - hooks:
        - type: http
          url: https://example.invalid/hooks
          headers:
            X-Check: "${CHECK}"
          allowedEnvVars: [CHECK]
---
Gövde.
""")
    assert fields.get("initial_prompt") == "İlk görevi incele."
    assert fields.get("omit_claude_md") is True
    hooks = fields.get("hook_definitions")
    assert isinstance(hooks, HookSet)
    command, http = hooks.commands
    assert command.event is HookEvent.PRE_TOOL_USE
    assert command.matcher == "Bash" and command.command == "python check.py"
    assert command.timeout_s == 17
    assert http.headers == (("X-Check", "${CHECK}"),)
    assert http.allowed_env_vars == ("CHECK",)
    assert fields["hooks"] == ("PreToolUse", "Stop")


def test_inline_mcp_sunucu_tanimi_ve_ad_basvurusu_ayri_tiplenir():
    fields = parse_frontmatter("""---
name: denetci
description: inceler
mcpServers:
  - yerel:
      command: python
      args: [server.py]
      env:
        PUBLIC_SETTING: value
  - github
---
Gövde.
""")
    assert fields["mcp_servers"] == ("yerel", "github")
    inline = fields.get("inline_mcp_servers")
    assert isinstance(inline, tuple) and len(inline) == 1
    assert isinstance(inline[0], McpServerConfig)
    assert inline[0].command == "python" and inline[0].args == ("server.py",)


def test_kanca_kontrol_alanlari_ayristirilir():
    fields = parse_frontmatter("""---
name: denetci
description: inceler
hooks:
  PreToolUse:
    - hooks:
        - type: command
          command: python
          args: [check.py]
          async: true
---
Gövde.
""")
    hooks = fields.get("hook_definitions")
    assert isinstance(hooks, HookSet)
    # Claude komut alanları artık uygulanır (#94): exec biçimi ve arka plan.
    assert hooks.skipped == ()
    (command,) = hooks.commands
    assert command.args == ("check.py",) and command.run_async is True


async def test_desteklenmeyen_guvenlik_kancasi_gercek_alt_ajan_cagrisini_engeller(tmp_path):
    import pytest

    from fusion_cli.engines.agent.team import spawn_agent_tool
    from tests.test_team_settings import _deps

    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "denetci.md").write_text("""---
name: denetci
description: inceler
hooks:
  PreToolUse:
    - hooks:
        - type: prompt
          command: SECRET_SENTINEL
---
Gövde.
""")
    deps, _ = _deps(tmp_path)

    async def forbidden(task, child, **kwargs):
        pytest.fail("Desteklenmeyen koruyucu kanca ajan çağrısına ulaşmamalı")

    result = await spawn_agent_tool(deps, depth=0, run_agent=forbidden).run(
        {"task": "incele", "uzman": "denetci"}, deps.tool_context
    )
    assert "desteklenmiyor" in result.output
    assert "SECRET_SENTINEL" not in result.output


def test_desteklenmeyen_kancanin_ham_tanimi_yalniz_gorunmez_metaveride_kalir():
    fields = parse_frontmatter("""---
name: denetci
description: inceler
hooks:
  PreToolUse:
    - hooks:
        - type: prompt
          command: SECRET_SENTINEL
---
Gövde.
""")
    skip = fields["hook_definitions"].skipped[0]
    assert "SECRET_SENTINEL" not in skip.detail
    assert "SECRET_SENTINEL" not in repr(skip)
    assert "SECRET_SENTINEL" in skip.definition_json


def test_ham_kanca_metaverisi_gercek_json_ve_metin_listesine_sizmaz(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from typer.testing import CliRunner

    from fusion_cli.cli import hooks_commands
    from tests.fakes import make_config

    fields = parse_frontmatter("""---
name: denetci
description: inceler
hooks:
  PreToolUse:
    - hooks:
        - type: agent
          command: SECRET_SENTINEL
          args: [SECRET_SENTINEL]
          headers:
            Authorization: SECRET_SENTINEL
---
Gövde.
""")
    hookset = fields["hook_definitions"]
    monkeypatch.setattr(
        hooks_commands, "load_config", lambda: make_config(memory_dir=tmp_path / "memory")
    )
    monkeypatch.setattr(
        hooks_commands,
        "open_hook_session",
        lambda *args, **kwargs: SimpleNamespace(refresh=lambda: hookset),
    )
    runner = CliRunner()
    for args in (["list"], ["list", "--json"]):
        result = runner.invoke(hooks_commands.app, args)
        assert result.exit_code == 0, result.output
        assert "SECRET_SENTINEL" not in result.output
        assert "definition_json" not in result.output


def test_desteklenmeyen_guvenlik_kancasi_gercek_ana_cli_cagrisini_engeller(tmp_path, monkeypatch):
    from fusion_cli.cli import app as app_module
    from tests.fakes import make_config
    from tests.test_headless import _agent

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        app_module, "_session_config", lambda: make_config(memory_dir=tmp_path / "memory")
    )
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "denetci.md").write_text("""---
name: denetci
description: inceler
hooks:
  PreToolUse:
    - hooks:
        - type: prompt
          command: SECRET_SENTINEL
---
Gövde.
""")
    seen, result = _agent(monkeypatch, ["Görev", "--agent", "denetci"])
    assert result.exit_code == 2
    assert seen == {}
    assert "desteklenmiyor" in result.output
    assert "SECRET_SENTINEL" not in result.output


def test_tools_ortak_normalizasyonu_cok_satirli_metin_ve_apostrofu_aynen_korur():
    from fusion_cli.tools import frontmatter

    assert hasattr(frontmatter, "normalize_agent_fields")
    raw = {
        "name": "denetci",
        "description": "İlk satır\najanın ikinci satırı",
        "initialPrompt": "Ajanın görevi.",
        "tools": ["Read"],
        "permissionMode": "dontAsk",
    }
    raw["hooks"] = {"PreToolUse": [{"hooks": [{"type": "command", "command": "echo ajan\n"}]}]}
    fields = frontmatter.normalize_agent_fields(raw)
    assert fields["description"] == raw["description"]
    assert fields["initial_prompt"] == raw["initialPrompt"]
    assert fields["tools"] == ("Read",)
    assert fields["permission_mode"] == "dontAsk"
    assert fields["hook_definitions"].commands[0].command == "echo ajan\n"


def test_yeni_kanca_ve_mcp_metaverisi_katalog_ve_agent_arama_ciktilarina_sizmaz(tmp_path):
    import json

    from fusion_cli.appserver.capabilities import catalog
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.engine_tools import _find_agent_tool
    from fusion_cli.engines.agent.team import resolve_persona
    from fusion_cli.tools.agent_catalog_index import agent_catalog_index
    from fusion_cli.tools.agent_catalog_launch import session_agents_from_json
    from fusion_cli.tools.capabilities import CapabilityRegistry
    from tests.fakes import make_config

    raw = json.dumps(
        {
            "denetci": {
                "description": "inceler",
                "prompt": "Gövde.",
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "SECRET_SENTINEL",
                                    "args": ["SECRET_SENTINEL"],
                                }
                            ]
                        }
                    ]
                },
                "mcpServers": [{"yerel": {"command": "python", "args": ["SECRET_SENTINEL"]}}],
            }
        }
    )
    entries = session_agents_from_json(raw, root=tmp_path)
    registry = CapabilityRegistry(tmp_path / "home", tmp_path, session_agents=entries)
    config = make_config(memory_dir=tmp_path / "memory")
    found = _find_agent_tool(registry).run({"query": "denetci"}, ToolContext(root=tmp_path))
    assert "SECRET_SENTINEL" not in found.output
    payload = catalog(
        registry,
        config,
        tmp_path,
        disabled_skills=set(),
        disabled_agents=set(),
        disabled_mcp=set(),
        home=tmp_path / "home",
    )
    assert "SECRET_SENTINEL" not in json.dumps(payload)
    assert "SECRET_SENTINEL" not in agent_catalog_index(
        registry, count_tokens=lambda text: len(text)
    )
    assert "SECRET_SENTINEL" not in repr(entries[0])
    assert "SECRET_SENTINEL" not in repr(resolve_persona(registry, "denetci"))
