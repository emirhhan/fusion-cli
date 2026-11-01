"""Sistem istemi bayrakları kök komutta ve `--system-prompt-snapshot` (#295)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import launch_prompts as lp
from fusion_cli.cli import print_run
from fusion_cli.cli.repl.persona_commands import PersonaTurn

runner = CliRunner()


def _print(monkeypatch, args):
    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    result = runner.invoke(app_module.app, args)
    return calls, result


def test_surdurulen_p_oturumu_kayitli_istemi_kullanir(monkeypatch):
    sid = str(uuid.uuid4())
    _print(monkeypatch, ["-p", "ilk", "--session-id", sid, "--append-system-prompt", "ESKİ"])
    calls, result = _print(
        monkeypatch, ["-r", sid, "-p", "sonra", "--append-system-prompt", "YENİ"]
    )
    assert result.exit_code == 0, result.output
    assert "ESKİ" in calls[0]["extra_system"] and "YENİ" not in calls[0]["extra_system"]


def test_snapshot_off_istemi_yeniden_kurar(monkeypatch):
    sid = str(uuid.uuid4())
    _print(monkeypatch, ["-p", "ilk", "--session-id", sid, "--append-system-prompt", "ESKİ"])
    calls, _ = _print(
        monkeypatch,
        ["-r", sid, "-p", "x", "--append-system-prompt", "YENİ", "--system-prompt-snapshot", "off"],
    )
    assert "YENİ" in calls[0]["extra_system"]


def test_gecersiz_snapshot_degeri(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "x", "--system-prompt-snapshot", "belki"])
    assert result.exit_code == 1 and "--system-prompt-snapshot" in result.output


def test_bare_kipinde_kayit_kapali(tmp_path):
    current = lp.LaunchPrompts(None, "A")
    lp.recorded(
        tmp_path, "s1", current, resuming=False, enabled=lp.snapshot_enabled(None, bare=True)
    )
    assert not (tmp_path / lp.SNAPSHOT_DIR).exists()
    assert lp.snapshot_enabled("on", bare=True)


def test_kok_komut_sistem_istemi_bayraklari(monkeypatch, tmp_path):
    from fusion_cli.config.readiness import Readiness

    seen: dict[str, object] = {}

    async def _repl(config, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(app_module, "run_repl", _repl)
    monkeypatch.setattr(
        app_module, "evaluate", lambda *_a, **_k: SimpleNamespace(state=Readiness.READY)
    )
    style = tmp_path / "stil.md"
    style.write_text("DOSYA", encoding="utf-8")
    result = runner.invoke(
        app_module.app,
        [
            "--system-prompt",
            "YERİNE",
            "--append-system-prompt",
            "EK",
            "--append-system-prompt-file",
            str(style),
            "merhaba",
        ],
    )
    assert result.exit_code == 0, result.output
    spec = seen["launch_prompts"]
    assert isinstance(spec, lp.LaunchSpec) and spec.snapshot
    assert spec.prompts == lp.LaunchPrompts("YERİNE", "DOSYA\n\nEK")


def test_repl_turu_acilis_istemini_kisilikten_once_uygular(tmp_path):
    state = SimpleNamespace(
        config=SimpleNamespace(memory_dir=tmp_path),
        conversation_id="c1",
    )
    spec = lp.LaunchSpec(lp.LaunchPrompts("YERİNE", "EK"))
    state.launch_prompts = lp.bind(state, spec, resumed=None)
    turn = lp.apply_to_turn(PersonaTurn(extra_system="KİŞİLİK", system_prompt="AJAN"), state)
    assert turn.system_prompt == "YERİNE"
    assert turn.extra_system == "KİŞİLİK\n\nEK"
    later = lp.bind(state, lp.LaunchSpec(lp.LaunchPrompts(None, "BAŞKA")), resumed=object())
    assert later == lp.LaunchPrompts("YERİNE", "EK")
