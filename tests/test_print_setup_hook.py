"""`--init`, `--init-only`, `-p --maintenance` → `Setup` kanca olayı (#301).

Claude Code: Setup yalnız `--init-only` ya da `-p --init` / `-p --maintenance` ile tetiklenir;
eşleştirici değeri (`init`|`maintenance`) bayrağı söyler, girdi `trigger` alanını taşır.
`--init-only` Setup ve `SessionStart(startup)` kancalarını koşup konuşma açmadan, çıktısız
çıkar. Setup engelleyemez: çıkış kodu ve JSON çıktısı yok sayılır.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run, print_setup
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookRun, HookSet, parse_event
from fusion_cli.engines.hooks import lifecycle
from fusion_cli.engines.hooks.session import HookSession

runner = CliRunner()


def _commands() -> HookSet:
    return HookSet(
        (
            HookCommand(HookEvent.SETUP, "init", "kur.sh", 5),
            HookCommand(HookEvent.SETUP, "maintenance", "temizle.sh", 5),
            HookCommand(HookEvent.SESSION_START, "startup", "basla.sh", 5),
        )
    )


@pytest.fixture
def ran(monkeypatch, tmp_path):
    seen: list[tuple[str, dict[str, object]]] = []

    async def _run(command, payload, **_kwargs):
        seen.append((command.command, dict(payload)))
        return HookRun(command, 2, '{"decision": "block"}', "hata")

    monkeypatch.setattr(lifecycle, "run_hook", _run)
    monkeypatch.setattr(
        print_setup,
        "open_hook_session",
        lambda root, config, **_kw: HookSession(root=root, loader=_commands),
    )
    return seen


def _agent(monkeypatch) -> list[str]:
    calls: list[str] = []

    async def _fake(task, config, **kwargs):
        calls.append(task)
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    return calls


def test_setup_olayi_taninir_ve_ayar_blogundan_okunur(tmp_path):
    assert parse_event("Setup") is HookEvent.SETUP
    block = {"Setup": [{"matcher": "init", "hooks": [{"type": "command", "command": "k"}]}]}
    found, skipped = parse_hooks_block(
        block, source="proje", path=tmp_path / "settings.json", default_timeout_s=5
    )
    assert not skipped and found[0].event is HookEvent.SETUP and found[0].matcher == "init"


def test_p_init_setup_init_kancasini_kosar_sonra_konusur(monkeypatch, ran):
    calls = _agent(monkeypatch)
    result = runner.invoke(app_module.app, ["-p", "selam", "--init"])
    assert result.exit_code == 0, result.output
    assert "etkisiz" not in result.output
    setup = [payload for name, payload in ran if name == "kur.sh"]
    assert setup and setup[0]["hook_event_name"] == "Setup" and setup[0]["trigger"] == "init"
    assert "temizle.sh" not in [name for name, _ in ran]
    assert calls == ["selam"]


def test_p_maintenance_yalniz_maintenance_eslesir(monkeypatch, ran):
    _agent(monkeypatch)
    result = runner.invoke(app_module.app, ["-p", "selam", "--maintenance"])
    assert result.exit_code == 0, result.output
    names = [name for name, _ in ran]
    assert "temizle.sh" in names and "kur.sh" not in names
    assert dict(ran)["temizle.sh"]["trigger"] == "maintenance"


def test_init_only_setup_ve_session_start_kosar_cikti_vermez(monkeypatch, ran):
    calls = _agent(monkeypatch)
    for argv in (["-p", "--init-only"], ["--init-only"]):
        ran.clear()
        result = runner.invoke(app_module.app, argv)
        assert result.exit_code == 0, result.output
        assert result.output == ""
        names = [name for name, _ in ran]
        assert names == ["kur.sh", "basla.sh"]
        assert dict(ran)["basla.sh"]["source"] == "startup"
    assert not calls


def test_setup_kancasi_engelleyemez(monkeypatch, ran):
    calls = _agent(monkeypatch)
    result = runner.invoke(app_module.app, ["-p", "selam", "--init"])
    # Kanca 2 ile çıktı ve `decision: block` yazdı: Claude'da yok sayılır, koşu sürer.
    assert result.exit_code == 0 and calls == ["selam"]


def test_bayraksiz_setup_kosmaz(monkeypatch, ran):
    _agent(monkeypatch)
    result = runner.invoke(app_module.app, ["-p", "selam"])
    assert result.exit_code == 0, result.output
    assert not [name for name, _ in ran if name in {"kur.sh", "temizle.sh"}]
