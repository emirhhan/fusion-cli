"""`/import` ve `fusion import` (P-071): Claude/Codex/Gemini/Cursor yapılandırmasını taşıma."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.extension_cli import register_extension_commands
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config import release_notes
from fusion_cli.config.importers import ImportStatus, apply_plan, build_plan
from fusion_cli.config.importers.claude_codex import codex_rule_items
from fusion_cli.config.importers.gemini_cursor import gemini_command_markdown
from fusion_cli.config.loader import load_config
from fusion_cli.config.models import McpScope, McpTransport
from fusion_cli.config.permission_rules import read_rules_file, user_permissions_file
from fusion_cli.core.errors import ConfigError
from fusion_cli.memory.factory import null_memory


class _Kasa:
    """Sahte şifreli depo."""

    def __init__(self, available: bool = True) -> None:
        self.values: dict[str, str] = {}
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def set(self, env_name: str, value: str) -> None:
        self.values[env_name] = value


@pytest.fixture
def ortam(tmp_path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    home.mkdir()
    root.mkdir()
    config_file = tmp_path / "config.yaml"
    config_file.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return home, root, config_file


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _by_name(plan, name):
    return next(item for item in plan.items if item.name == name)


def test_claude_mcp_kayitlari_tasinir_sir_kasaya_gider_degeri_gorunmez(ortam):
    home, root, config_file = ortam
    _write(
        home / ".claude.json",
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-github"],
                        "env": {"GITHUB_TOKEN": "ghp_gizli123", "LOG_LEVEL": "info"},
                    },
                    "eski": {"type": "sse", "url": "https://x.example.com/sse"},
                },
                "projects": {
                    str(root): {
                        "mcpServers": {
                            "linear": {
                                "type": "http",
                                "url": "https://mcp.linear.app/mcp",
                                "headers": {"Authorization": "Bearer ${LINEAR_TOKEN}"},
                            }
                        }
                    }
                },
            }
        ),
    )
    _write(home / ".claude" / "CLAUDE.md", "kurallar\n")
    config = load_config(config_file)

    plan = build_plan("claude", home=home, root=root, config=config)

    github = _by_name(plan, "github")
    assert github.status is ImportStatus.NEW
    assert "ghp_gizli123" not in github.detail and "GITHUB_TOKEN" in github.detail
    assert _by_name(plan, "eski").status is ImportStatus.SKIPPED
    assert _by_name(plan, "CLAUDE.md").status is ImportStatus.NATIVE
    kasa = _Kasa()
    updated, report = apply_plan(plan, config=config, root=root, secrets=kasa)

    assert not report.failed
    assert kasa.values == {"GITHUB_TOKEN": "ghp_gizli123"}
    written = config_file.read_text(encoding="utf-8")
    assert "ghp_gizli123" not in written
    reloaded = {s.name: s for s in load_config(config_file).mcp_servers}
    assert reloaded["github"].env_names == ("GITHUB_TOKEN",)
    assert reloaded["github"].env_literals == (("LOG_LEVEL", "info"),)
    assert reloaded["linear"].transport is McpTransport.STREAMABLE_HTTP
    assert reloaded["linear"].token_env == "LINEAR_TOKEN"
    # İkinci önizleme: aynı adlar "zaten var".
    again = build_plan("claude", home=home, root=root, config=updated)
    assert _by_name(again, "github").status is ImportStatus.EXISTS


def test_sir_deposu_yoksa_sunucu_yazilmaz(ortam):
    home, root, config_file = ortam
    _write(
        home / ".cursor" / "mcp.json",
        json.dumps({"mcpServers": {"db": {"command": "pg", "env": {"DB_PASSWORD": "x"}}}}),
    )
    config = load_config(config_file)
    plan = build_plan("cursor", home=home, root=root, config=config)

    _updated, report = apply_plan(plan, config=config, root=root, secrets=_Kasa(available=False))

    assert report.failed and "şifreli depo" in report.failed[0][1]
    assert "db" not in {s.name for s in load_config(config_file).mcp_servers}


def test_codex_config_toml_kurallar_ve_promptlar(ortam):
    home, root, config_file = ortam
    _write(
        home / ".codex" / "config.toml",
        'approval_policy = "on-request"\n'
        "[mcp_servers.figma]\n"
        'url = "https://mcp.figma.com/mcp"\n'
        'bearer_token_env_var = "FIGMA_TOKEN"\n'
        "[mcp_servers.kapali]\n"
        'command = "x"\n'
        "enabled = false\n",
    )
    _write(
        home / ".codex" / "rules" / "default.rules",
        'prefix_rule(pattern = ["git", ["push", "reset"]], decision = "forbidden",\n'
        '            justification = "tehlikeli (geri alınamaz)")\n'
        'prefix_rule(pattern = ["npm", "test"])\n',
    )
    _write(home / ".codex" / "prompts" / "inceleme.md", "Şunu incele: $ARGUMENTS\n")
    config = load_config(config_file)

    plan = build_plan("codex", home=home, root=root, config=config)
    _updated, report = apply_plan(plan, config=config, root=root, secrets=_Kasa())

    assert not report.failed
    servers = {s.name: s for s in load_config(config_file).mcp_servers}
    assert servers["figma"].token_env == "FIGMA_TOKEN" and "kapali" not in servers
    rules = {(r.pattern, r.decision.value) for r in read_rules_file(user_permissions_file())}
    assert rules == {
        ("Bash(git push *)", "deny"),
        ("Bash(git reset *)", "deny"),
        ("Bash(npm test *)", "allow"),
    }
    assert (
        (home / ".fusion" / "commands" / "inceleme.md")
        .read_text(encoding="utf-8")
        .startswith("Şunu incele")
    )
    assert _by_name(plan, "approval_policy").status is ImportStatus.SKIPPED


def test_codex_cozulemeyen_kalip_gerekceyle_atlanir():
    (item,) = codex_rule_items('prefix_rule(pattern = [a_var], decision = "allow")', Path("r"))
    assert item.status is ImportStatus.SKIPPED


def test_gemini_talimat_baglantisi_komut_ve_arac_izinleri(ortam):
    home, root, config_file = ortam
    _write(
        home / ".gemini" / "settings.json",
        json.dumps(
            {
                "mcpServers": {
                    "akis": {"httpUrl": "https://mcp.example.com/mcp"},
                    "eski": {"url": "https://mcp.example.com/sse"},
                },
                "tools": {"allowed": ["run_shell_command(git status)"], "exclude": ["web_fetch"]},
            }
        ),
    )
    _write(home / ".gemini" / "GEMINI.md", "Gemini kuralları\n")
    _write(
        home / ".gemini" / "commands" / "git" / "ozet.toml",
        'description = "Değişiklik özeti"\nprompt = "Özetle {{args}}: !{git diff --stat}"\n',
    )
    config = load_config(config_file)

    plan = build_plan("gemini", home=home, root=root, config=config)
    assert _by_name(plan, "eski").status is ImportStatus.SKIPPED
    _updated, report = apply_plan(plan, config=config, root=root, secrets=_Kasa())

    assert not report.failed
    talimat = (home / ".fusion" / "TALIMAT.md").read_text(encoding="utf-8")
    assert "@~/.gemini/GEMINI.md" in talimat
    command = (home / ".fusion" / "commands" / "git" / "ozet.md").read_text(encoding="utf-8")
    assert "description: Değişiklik özeti" in command
    assert "$ARGUMENTS" in command and "!`git diff --stat`" in command
    rules = {(r.pattern, r.decision.value) for r in read_rules_file(user_permissions_file())}
    assert ("Bash(git status *)", "allow") in rules and ("WebFetch", "deny") in rules
    # Bağlantı ikinci kez eklenmez.
    again = build_plan("gemini", home=home, root=root, config=load_config(config_file))
    assert _by_name(again, "GEMINI.md").status is ImportStatus.EXISTS


def test_gemini_komut_cevirisi_aciklamasiz():
    assert gemini_command_markdown({"prompt": "Yap {{args}}"}) == "Yap $ARGUMENTS\n"


def test_cursor_proje_mcp_proje_dosyasina_kurallar_secici_izinler(ortam):
    home, root, config_file = ortam
    _write(root / ".cursor" / "mcp.json", json.dumps({"mcpServers": {"yerel": {"command": "srv"}}}))
    _write(
        home / ".cursor" / "cli-config.json",
        json.dumps(
            {"permissions": {"allow": ["Shell(ls)", "Mcp(github:*)"], "deny": ["Write(**/.env)"]}}
        ),
    )
    _write(root / ".cursor" / "rules" / "her-zaman.mdc", "---\nalwaysApply: true\n---\nKural A\n")
    _write(root / ".cursor" / "rules" / "ts.mdc", "---\nglobs: src/**/*.ts\n---\nKural B\n")
    _write(root / ".cursor" / "rules" / "istege.mdc", "---\ndescription: bazen\n---\nKural C\n")
    existing = _write(root / ".fusion" / "rules" / "ts.mdc", "benim kuralım\n")
    config = load_config(config_file)

    plan = build_plan("cursor", home=home, root=root, config=config)

    assert _by_name(plan, "istege").status is ImportStatus.SKIPPED
    assert _by_name(plan, "ts").status is ImportStatus.EXISTS
    _updated, report = apply_plan(plan, config=config, root=root, secrets=_Kasa())
    assert not report.failed
    assert existing.read_text(encoding="utf-8") == "benim kuralım\n"
    assert (root / ".fusion" / "rules" / "her-zaman.mdc").is_file()
    project = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert project["mcpServers"]["yerel"]["command"] == "srv"
    assert "yerel" not in {
        s.name for s in load_config(config_file).mcp_servers if s.scope is McpScope.USER
    }
    rules = {(r.pattern, r.decision.value) for r in read_rules_file(user_permissions_file())}
    assert rules == {("Bash(ls *)", "allow"), ("mcp__github", "allow"), ("Edit(**/.env)", "deny")}


def test_bilinmeyen_kaynak_ve_bos_kaynak(ortam):
    home, root, config_file = ortam
    with pytest.raises(ConfigError, match="Geçerli"):
        build_plan("vscode", home=home, root=root, config=load_config(config_file))
    plan = build_plan("cursor", home=home, root=root, config=load_config(config_file))
    assert plan.items == () and plan.pending == ()


def test_bozuk_kaynak_dosyasi_uyari_olur(ortam):
    home, root, config_file = ortam
    _write(home / ".gemini" / "settings.json", "{bozuk")
    plan = build_plan("gemini", home=home, root=root, config=load_config(config_file))
    assert plan.warnings and "okunamadı" in plan.warnings[0]


def test_repl_import_onizler_yes_ile_uygular(ortam, monkeypatch):
    home, root, config_file = ortam
    _write(home / ".codex" / "prompts" / "x.md", "X yap\n")
    state = ReplState(config=load_config(config_file), memory=null_memory(), root=root, home=home)
    registry = build_registry(home, skills=lambda: state.capabilities)
    command = registry.get("import")
    assert command is not None

    preview = command.handler(state, "codex")
    assert "eklenecek" in preview and "/import codex --yes" in preview
    assert not (home / ".fusion" / "commands" / "x.md").exists()

    from fusion_cli.cli.repl import import_command

    monkeypatch.setattr(import_command, "default_secrets", _Kasa)
    applied = command.handler(state, "codex --yes")
    assert "İçe aktarıldı: 1 öğe." in applied
    assert (home / ".fusion" / "commands" / "x.md").is_file()
    assert "Kullanım" in command.handler(state, "")


def test_cli_import_kuru_calisma_yazmaz(ortam, monkeypatch):
    import typer

    home, root, config_file = ortam
    _write(home / ".codex" / "prompts" / "x.md", "X yap\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FUSION_CONFIG", str(config_file))
    monkeypatch.chdir(root)
    app = typer.Typer()
    register_extension_commands(app)

    result = CliRunner().invoke(app, ["import", "codex", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "eklenecek" in result.output
    assert not (home / ".fusion" / "commands" / "x.md").exists()
    # Etkileşimsiz terminalde --yes olmadan yazılmaz.
    result = CliRunner().invoke(app, ["import", "codex"])
    assert "--yes" in result.output
    assert not (home / ".fusion" / "commands" / "x.md").exists()


# --- Sürüm notları ----------------------------------------------------------------- #

_CHANGELOG = """# Değişiklik günlüğü

## Yayımlanmamış

- Yeni şey.

## 0.7.18 — 2026-10-21

- Düzeltme A.

## [0.3.0a1] — 2026-07-26

- İlk.
"""


def test_surum_notlari_bolum_secer(tmp_path):
    path = _write(tmp_path / "CHANGELOG.md", _CHANGELOG)

    sections = release_notes.parse_changelog(_CHANGELOG)
    assert [s.version for s in sections] == ["", "0.7.18", "0.3.0a1"]
    assert sections[1].date == "2026-10-21"
    assert "Yeni şey" in release_notes.release_notes_text("", path=path)
    assert "Düzeltme A" in release_notes.release_notes_text("v0.7.18", path=path)
    assert "0.3.0a1" in release_notes.release_notes_text("liste", path=path)
    assert "sürüm notu yok" in release_notes.release_notes_text("9.9", path=path)


def test_surum_notlari_dosya_yoksa_yayin_sayfasi(tmp_path):
    assert release_notes.changelog_path(tmp_path / "a" / "b" / "c") is None
    text = release_notes.release_notes_text("", path=tmp_path / "yok.md")
    assert release_notes.RELEASES_URL in text


def test_depo_changelog_bulunur_ve_repl_komutu_surumu_basar(ortam):
    home, root, config_file = ortam
    assert release_notes.changelog_path() is not None
    state = ReplState(config=load_config(config_file), memory=null_memory(), root=root, home=home)
    command = build_registry(home).get("surum-notlari")
    assert command is not None
    assert command.handler(state, "").startswith("Kurulu sürüm:")
