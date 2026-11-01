"""Bağımsız inceleme bulguları (headless-cli, tur 6): -p /config, denetim kanalı, onay aracı."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run

runner = CliRunner()
_STREAM = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]


def _fake_agent(monkeypatch):
    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        calls.append({"task": task, "config": config, **kwargs})
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


def _user(text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _stream(monkeypatch, lines, extra=()):
    calls = _fake_agent(monkeypatch)
    stdin = "".join(json.dumps(line) + "\n" for line in lines)
    result = runner.invoke(app_module.app, [*_STREAM, *extra], input=stdin)
    out = [json.loads(x) for x in result.stdout.splitlines() if x.strip().startswith("{")]
    return calls, result, out


def _config_files() -> list[Path]:
    root = Path(os.environ["XDG_CONFIG_HOME"])
    return list(root.rglob("config.yaml")) if root.is_dir() else []


# --- bulgu 1: -p /config kalıcı yazmaz (#303) ----------------------------------------- #


def test_borulu_config_kalici_ayar_yazmaz(monkeypatch):
    calls = _fake_agent(monkeypatch)
    result = runner.invoke(
        app_module.app, ["-p"], input="/config runtime.block_writes_outside_root=false\n"
    )
    assert result.exit_code == 0, result.output
    assert not calls
    for path in _config_files():
        assert "block_writes_outside_root" not in path.read_text(encoding="utf-8")


def test_config_degeri_yalniz_bu_kosuya_uygulanir(monkeypatch):
    calls, result, _out = _stream(
        monkeypatch, [_user("/config runtime.max_tokens=4321"), _user("devam")]
    )
    assert result.exit_code == 0, result.output
    assert [c["task"] for c in calls] == ["devam"]
    assert calls[0]["config"].runtime.max_tokens == 4321
    for path in _config_files():
        assert "4321" not in path.read_text(encoding="utf-8")


# --- bulgu 2: set_permission_mode bypassPermissions denetimi (#280) ------------------- #


def _control(subtype: str, rid: str, **fields: object) -> dict[str, object]:
    return {"type": "control_request", "request_id": rid, "request": {"subtype": subtype, **fields}}


def _responses(out) -> dict[str, dict]:
    return {
        m["response"]["request_id"]: m["response"] for m in out if m["type"] == "control_response"
    }


def _bypass_lines():
    return [_control("set_permission_mode", "b1", mode="bypassPermissions"), _user("bir")]


def test_izin_bayragi_olmadan_bypass_istegi_reddedilir(monkeypatch):
    from fusion_cli.engines.agent.approval import ApprovalMode

    calls, result, out = _stream(monkeypatch, _bypass_lines())
    assert result.exit_code == 0, result.output
    assert _responses(out)["b1"]["subtype"] == "error"
    assert "--allow-dangerously-skip-permissions" in _responses(out)["b1"]["error"]
    assert calls[0]["mode"] is not ApprovalMode.BYPASS


def test_restricted_kosuda_bypass_istegi_reddedilir(monkeypatch):
    from fusion_cli.engines.agent.approval import ApprovalMode

    extra = ["--restricted", "--allow-dangerously-skip-permissions"]
    calls, _result, out = _stream(monkeypatch, _bypass_lines(), extra)
    assert _responses(out)["b1"]["subtype"] == "error"
    assert calls[0]["mode"] is not ApprovalMode.BYPASS


def test_allow_dangerously_skip_ile_bypass_istegi_kabul_edilir(monkeypatch):
    from fusion_cli.engines.agent.approval import ApprovalMode

    extra = ["--allow-dangerously-skip-permissions"]
    calls, _result, out = _stream(monkeypatch, _bypass_lines(), extra)
    assert _responses(out)["b1"]["subtype"] == "success"
    assert calls[0]["mode"] is ApprovalMode.BYPASS


# --- bulgu 5: set_model istek anında doğrulanır (#280) -------------------------------- #


def test_gecersiz_set_model_hata_doner_ve_oturum_surer(monkeypatch):
    from fusion_cli.cli import print_options

    real = print_options.apply_model

    def _apply(config, model, fallback):
        if model == "bozuk-model":
            raise ValueError("model çözülemedi: bozuk-model")
        return real(config, model, fallback)

    monkeypatch.setattr(print_options, "apply_model", _apply)
    calls, result, out = _stream(
        monkeypatch, [_control("set_model", "s1", model="bozuk-model"), _user("bir")]
    )
    assert _responses(out)["s1"]["subtype"] == "error"
    assert "bozuk-model" in _responses(out)["s1"]["error"]
    assert result.exit_code == 0, result.output
    assert [c["task"] for c in calls] == ["bir"]
