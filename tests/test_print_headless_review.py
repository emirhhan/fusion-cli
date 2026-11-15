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


# --- bulgu 4: stream-json turlarında /beceri genişletmesi (#303, #280) ---------------- #


def _skill(root: Path) -> None:
    folder = root / ".claude" / "commands"
    folder.mkdir(parents=True)
    (folder / "foo.md").write_text(
        "---\nallowed-tools: Read\n---\nEXPANDED $ARGUMENTS\n", encoding="utf-8"
    )


def test_stream_json_turunda_ozel_komut_genisletilir(monkeypatch, tmp_path):
    _skill(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls, result, out = _stream(monkeypatch, [_user("/foo bar"), _user("düz"), _user("/clear")])
    assert result.exit_code == 0, result.output
    assert len(calls) == 2
    first, second = calls
    assert "EXPANDED bar" in first["task"] + first["extra_system"]
    assert first["allowed_tools"] is not None and "read_file" in first["allowed_tools"]
    assert second["task"] == "düz" and "EXPANDED" not in second["extra_system"]
    assert second["allowed_tools"] is None
    final = [m for m in out if m["type"] == "result"][-1]
    assert final["result"] == "/clear isn't available in this environment."


# --- bulgu 7: --json-schema çit ayıklaması geçerli JSON'u bozmaz (#301) ---------------- #


def test_icinde_cit_gecen_gecerli_json_bozulmaz():
    value, errors = print_run._structured('{"a": "```x```"}', {"type": "object"})
    assert errors == () and value == {"a": "```x```"}


def test_citli_json_hala_ayiklanir():
    value, errors = print_run._structured('Sonuç:\n```json\n{"a": 1}\n```', {"type": "object"})
    assert errors == () and value == {"a": 1}


# --- bulgu 8: ulaşılamayan --debug-file düzgün hata (#301) ----------------------------- #


def test_ulasilamayan_debug_file_hata_ve_cikis_1(monkeypatch, tmp_path):
    calls = _fake_agent(monkeypatch)
    target = tmp_path / "yok" / "dizin" / "x.log"
    result = runner.invoke(app_module.app, ["-p", "x", "--debug-file", str(target)])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--debug-file" in result.output
    assert not calls


# --- bulgu 3: onay aracı — tool_use_id, updatedInput, deny.message (#284) ------------- #


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


def _prompt_tool(answer: dict, seen: list[dict]):
    from fusion_cli.core.tools import ToolResult

    def _run(args, _ctx):
        seen.append(args)
        return ToolResult(json.dumps(answer))

    async def _loader(_name):
        return SimpleNamespace(run=_run)

    return _loader


async def _loop_with(monkeypatch, tmp_path, prompter, results):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent

    from .fakes import RecordingSink, ScriptedProvider, make_config

    provider = ScriptedProvider(results)
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.SECURITY, prompter),
        tool_context=ToolContext(root=tmp_path),
    )
    return await run_agent("iş", deps)


def _write_then_done(path: str):
    from .fakes import model_result, tool_call

    return [
        model_result(tool_calls=[tool_call("write_file", path=path, content="x")]),
        model_result("bitti"),
    ]


async def test_onay_aracina_gercek_cagri_kimligi_ve_claude_girdisi_gider(monkeypatch, tmp_path):
    from fusion_cli.cli.print_prompt_tool import PromptToolPrompter

    seen: list[dict] = []
    loader = _prompt_tool({"behavior": "allow"}, seen)
    prompter = PromptToolPrompter("mcp__onay__sor", loader, root=tmp_path)
    await _loop_with(monkeypatch, tmp_path, prompter, _write_then_done("a.txt"))
    assert seen[0]["tool_use_id"] == "call_write_file"
    assert seen[0]["tool_name"] == "Write"
    # Claude Write girdisinde `file_path` mutlaktır (kancalar alanı #91); kök onaylayıcının
    # köküdür, süreç dizini değil.
    assert seen[0]["input"]["file_path"] == str((tmp_path / "a.txt").resolve())
    assert (tmp_path / "a.txt").exists()


async def test_onay_aracinin_updated_input_u_uygulanir(monkeypatch, tmp_path):
    from fusion_cli.cli.print_prompt_tool import PromptToolPrompter

    seen: list[dict] = []
    answer = {"behavior": "allow", "updatedInput": {"file_path": "b.txt", "content": "y"}}
    prompter = PromptToolPrompter("mcp__onay__sor", _prompt_tool(answer, seen), root=tmp_path)
    await _loop_with(monkeypatch, tmp_path, prompter, _write_then_done("a.txt"))
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "y"


async def test_updated_input_kok_disi_engeli_asamaz(monkeypatch, tmp_path):
    from fusion_cli.cli.print_prompt_tool import PromptToolPrompter
    from fusion_cli.config.permission_rules import PermissionRuleSet
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent

    from .fakes import RecordingSink, ScriptedProvider, make_config

    outside = tmp_path.parent / f"{tmp_path.name}-disari.txt"
    answer = {"behavior": "allow", "updatedInput": {"file_path": str(outside), "content": "y"}}
    prompter = PromptToolPrompter("mcp__onay__sor", _prompt_tool(answer, []), root=tmp_path)
    provider = ScriptedProvider(_write_then_done("a.txt"))
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.SECURITY, prompter),
        tool_context=ToolContext(root=tmp_path),
        permission_rules=PermissionRuleSet(block_writes_outside_root=True),
    )
    await run_agent("iş", deps)
    assert not outside.exists()
    assert not (tmp_path / "a.txt").exists()


async def test_deny_mesaji_modele_gider_ve_tur_surer(monkeypatch, tmp_path):
    from fusion_cli.cli.print_prompt_tool import PromptToolPrompter

    answer = {"behavior": "deny", "message": "bu dosyaya yazma"}
    prompter = PromptToolPrompter("mcp__onay__sor", _prompt_tool(answer, []), root=tmp_path)
    outcome = await _loop_with(monkeypatch, tmp_path, prompter, _write_then_done("a.txt"))
    tool_texts = [m.content for m in outcome.messages if m.role == "tool"]
    assert any("bu dosyaya yazma" in text for text in tool_texts)
    assert outcome.final_text == "bitti"


def test_onay_araci_hatasi_stderr_e_yazilir(capsys, tmp_path):
    import asyncio

    from fusion_cli.cli.print_prompt_tool import PromptToolPrompter

    async def _loader(_name):
        raise RuntimeError("sunucu bağlanamadı")

    prompter = PromptToolPrompter("mcp__yok__arac", _loader, root=tmp_path)
    request = SimpleNamespace(tool=SimpleNamespace(name="run_shell"), args={}, call_id="c1")
    asyncio.run(prompter.confirm(request))  # type: ignore[arg-type]
    assert "sunucu bağlanamadı" in capsys.readouterr().err


# --- bulgu 6: system/init keşif alanları, önbellek token'ları (#280, #279) ------------ #


def test_init_ve_initialize_komut_ve_beceri_listesini_verir(monkeypatch, tmp_path):
    _skill(tmp_path)
    skill = tmp_path / ".claude" / "skills" / "ozetle"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ozetle\ndescription: kısa özet\n---\ngövde\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    _calls, result, out = _stream(monkeypatch, [_control("initialize", "i1"), _user("bir")])
    assert result.exit_code == 0, result.output
    init = next(m for m in out if m.get("subtype") == "init")
    assert {"foo", "ozetle", "model", "config"} <= set(init["slash_commands"])
    assert "ozetle" in init["skills"] and "foo" not in init["skills"]
    assert isinstance(init["plugins"], list)
    commands = _responses(out)["i1"]["response"]["commands"]
    names = {item["name"] for item in commands}
    assert {"foo", "ozetle"} <= names
    assert all({"name", "description", "argumentHint"} <= set(item) for item in commands)


def test_onbellek_tokenlari_sonuca_ve_model_kullanimina_yazilir():
    from fusion_cli.cli import sdk_messages as sdk
    from fusion_cli.core.events import ModelCallFinished
    from fusion_cli.core.types import ModelResult, TokenUsage

    usage = TokenUsage(prompt_tokens=100, completion_tokens=5, cache_read_tokens=60)
    stats = sdk.RunStats()
    stats.handle(
        ModelCallFinished(
            role="ajan",
            result=ModelResult(
                name="ajan", text="x", latency_ms=1, ok=True, model="m1", usage=usage
            ),
        )
    )
    assert stats.model_usage["m1"]["cacheReadInputTokens"] == 60
    data = sdk.ResultInput(
        session_id="s",
        final_text="x",
        subtype=sdk.SUBTYPE_SUCCESS,
        num_turns=1,
        duration_ms=1,
        stop_reason=None,
        prompt_tokens=100,
        completion_tokens=5,
        cost_usd=0.0,
        cost_complete=True,
        cache_read_tokens=60,
    )
    assert sdk.result_message(data, stats)["usage"]["cache_read_input_tokens"] == 60


def test_token_usage_toplami_onbellegi_tasir():
    from fusion_cli.core.types import TokenUsage

    total = TokenUsage(cache_read_tokens=2, cache_creation_tokens=3) + TokenUsage(
        cache_read_tokens=1
    )
    assert (total.cache_read_tokens, total.cache_creation_tokens) == (3, 3)


def test_litellm_kullanimindan_onbellek_okunur():
    from fusion_cli.providers.litellm_provider import _response_usage

    usage = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=2,
        cache_read_input_tokens=4,
        cache_creation_input_tokens=3,
    )
    parsed = _response_usage(SimpleNamespace(usage=usage), "yok/model")
    assert (parsed.cache_read_tokens, parsed.cache_creation_tokens) == (4, 3)
    details = SimpleNamespace(
        prompt_tokens=10, completion_tokens=2, prompt_tokens_details={"cached_tokens": 7}
    )
    assert _response_usage(SimpleNamespace(usage=details), "yok/model").cache_read_tokens == 7
