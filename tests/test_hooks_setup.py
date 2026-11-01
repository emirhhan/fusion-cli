"""`Setup` kancası (#90): `--init`/`--init-only` → init, `--maintenance` → maintenance."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.app import app
from fusion_cli.config import trust
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.errors import FusionError
from fusion_cli.core.hooks.events import HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.engines.hooks.setup_hook import run_setup

#: Kanca yükleme testleri güvenilmiş klasörde (#108; kapı: test_hooks_workspace_trust).
pytestmark = pytest.mark.usefixtures("guvenilir_klasor")


def _script(tmp_path: Path, log: Path, context: str = "kurulum tamam") -> str:
    path = tmp_path / "setup.py"
    path.write_text(
        "import json, os, sys\n"
        "data = json.load(sys.stdin)\n"
        "data['env_file'] = os.environ.get('CLAUDE_ENV_FILE', '')\n"
        f"open(r'{log}', 'a').write(json.dumps(data) + '\\n')\n"
        "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'Setup',"
        f" 'additionalContext': {context!r}}}}}))\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {path}"


def _block(command: str, matcher: str) -> dict[str, object]:
    return {"Setup": [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]}


def _session(tmp_path: Path, block: dict[str, object]) -> HookSession:
    commands, skipped = parse_hooks_block(block, source="kullanici", path=Path("settings.json"))
    assert not skipped
    return HookSession(
        root=tmp_path, loader=lambda: HookSet(commands), transcript_dir=tmp_path / "dokum"
    )


def _lines(log: Path) -> list[dict[str, object]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_eslestirici_tetige_bakar_baglam_acilisa_eklenir(tmp_path):
    log = tmp_path / "log.jsonl"
    session = _session(tmp_path, _block(_script(tmp_path, log), "init"))

    asyncio.run(run_setup(session, "maintenance"))
    assert _lines(log) == []

    verdict = asyncio.run(run_setup(session, "init"))
    assert verdict.ran == 1
    (payload,) = _lines(log)
    assert payload["hook_event_name"] == "Setup"
    assert payload["trigger"] == "init"
    assert str(payload["env_file"]).endswith("-env.sh")
    context = session.take_start_context()
    assert "Setup hook additional context: kurulum tamam" in context


def test_gecersiz_tetik_reddedilir(tmp_path):
    with pytest.raises(FusionError):
        asyncio.run(run_setup(_session(tmp_path, {}), "startup"))


@pytest.fixture
def ev(tmp_path, monkeypatch):
    home = tmp_path / "ev"
    home.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(trust, "trust_store_file", lambda: home / "guven.json")
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return home


def test_init_only_kancayi_calistirir_oturum_acmaz(tmp_path, ev, monkeypatch):
    log = tmp_path / "log.jsonl"
    settings = ev / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"hooks": _block(_script(tmp_path, log), "init")}))
    project = tmp_path / "proje"
    project.mkdir()
    monkeypatch.chdir(project)

    result = CliRunner().invoke(app, ["--init-only"])

    assert result.exit_code == 0, result.output
    (payload,) = _lines(log)
    assert payload["trigger"] == "init"
    assert payload["cwd"] == str(project)
