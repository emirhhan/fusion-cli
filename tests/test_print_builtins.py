"""`-p` isteminde /model, /effort, /config key=value, /output-style, /mcp (#303, #311)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run

runner = CliRunner()


def _print(monkeypatch, args, *, input=None):
    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        calls.append({"task": task, "config": config, **kwargs})
        return SimpleNamespace(
            final_text="model cevabı",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    return calls, runner.invoke(app_module.app, args, input=input)


def test_config_key_value_kalici_yazar_ve_modele_gitmez(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "/config runtime.max_tokens=4321"])
    assert result.exit_code == 0, result.output
    assert not calls
    assert "runtime.max_tokens = 4321" in result.stdout
    written = Path(result.stdout.split("yazıldı:", 1)[1].strip())
    assert "4321" in written.read_text(encoding="utf-8")


def test_config_argumansiz_kullanilamaz(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "/config"])
    assert not calls and "isn't available" in result.stdout


def test_gecersiz_config_yolu_cevap_metnidir(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "/config yok.boyle=1"])
    assert not calls and result.stdout.strip()


def test_mcp_ozeti(monkeypatch):
    raw = '{"mcpServers": {"dosya": {"command": "npx", "args": ["x"]}}}'
    calls, result = _print(monkeypatch, ["-p", "/mcp", "--mcp-config", raw])
    assert not calls and "dosya (stdio): yapılandırıldı" in result.stdout


def test_stream_json_model_komutu_sonraki_tura_uygulanir(monkeypatch):
    lines = [
        {"type": "user", "message": {"role": "user", "content": "/effort high"}},
        {"type": "user", "message": {"role": "user", "content": "devam"}},
    ]
    stdin = "".join(json.dumps(line) + "\n" for line in lines)
    calls, result = _print(
        monkeypatch,
        ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"],
        input=stdin,
    )
    assert result.exit_code == 0, result.output
    assert [c["task"] for c in calls] == ["devam"]
    assert calls[0]["config"].runtime.reasoning_effort.value == "high"
    results = [json.loads(x) for x in result.stdout.splitlines() if '"type": "result"' in x]
    assert "Effort ayarlandı: high" in results[0]["result"]


def test_disable_slash_commands_yerlesigi_de_kapatir(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "/effort high", "--disable-slash-commands"])
    assert [c["task"] for c in calls] == ["/effort high"]


def test_output_style_listesi(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "/output-style"])
    assert not calls and result.exit_code == 0 and result.stdout.strip()
