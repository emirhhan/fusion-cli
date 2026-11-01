"""`fusion -p` — Claude Code `claude -p/--print` başsız kip paritesi (headless-cli alanı).

Ölçüldü (1 Kasım): `fusion -p "x"` bilinmeyen seçenek hatası veriyordu; başsız kip yalnız
`fusion agent` alt komutuydu, çıktı alanları Türkçeydi (`sonuc`, `durum`), `--allowed-tools`
araç kümesini daraltıyordu, varsayılan kip `auto`ydu ve oturum kimliği hiç dönmüyordu.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli import __version__
from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.cli.print_argv import INITIAL_PROMPT_OPTION, expand_variadic, rewrite_root_args
from fusion_cli.cli.print_options import UNLIMITED_TURNS
from fusion_cli.cli.print_runtime import BARE_TOOLS
from fusion_cli.config.permission_rules import PermissionDecision
from fusion_cli.engines.agent.approval import ApprovalMode

runner = CliRunner()


def _group():
    import typer

    return typer.main.get_group(app_module.app)


def _outcome(**overrides):
    values = {
        "final_text": "tamam",
        "ok": True,
        "budget_stopped": False,
        "stop_reason": None,
        "model_calls_made": 2,
        "hit_step_limit": False,
        "messages": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _print(monkeypatch, args, *, outcomes=None, input=None):
    """`run_agent_task`'ı sahteyle değiştirip `fusion <args>` çalıştır."""
    calls: list[dict] = []
    queue = list(outcomes or [])

    async def _fake(task, config, **kwargs):
        calls.append({"task": task, "config": config, **kwargs})
        return queue.pop(0) if queue else _outcome()

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    result = runner.invoke(app_module.app, args, input=input)
    return calls, result


# --- argv yeniden yazımı (#275, #276, #287, #314) ------------------------------------- #


def test_kok_p_bayragi_print_alt_komutuna_cevrilir():
    args = rewrite_root_args(["-p", "sorgu", "--output-format", "json"], _group())
    assert args == ["print", "sorgu", "--output-format", "json"]


def test_bilinen_alt_komut_degismez():
    group = _group()
    assert rewrite_root_args(["agent", "-p", "x"], group) == ["agent", "-p", "x"]


def test_konumsal_istem_ilk_tur_secenegine_cevrilir():
    args = rewrite_root_args(["--agent", "plan", "merhaba"], _group())
    assert args == ["--agent", "plan", INITIAL_PROMPT_OPTION, "merhaba"]


def test_bosluklu_coklu_deger_bayrak_tekrarina_acilir():
    args = expand_variadic(["q", "--allowedTools", "Bash(git log *)", "Read", "--verbose"])
    assert args == ["q", "--allowedTools", "Bash(git log *)", "--allowedTools", "Read", "--verbose"]


def test_degersiz_worktree_ad_uretir():
    args = rewrite_root_args(["-w"], _group())
    assert args[0] == "-w" and args[1].startswith("wt-")


# --- temel koşu ve çıktı (#275, #278, #279, #281) -------------------------------------- #


def test_p_metin_kipinde_yalniz_cevap_yazilir(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "selam"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "tamam\n"
    assert calls[0]["task"] == "selam"
    assert calls[0]["mode"] is ApprovalMode.SECURITY  # Claude -p varsayılanı: default
    assert calls[0]["interactive"] is False


def test_json_sonuc_nesnesi_claude_alanlariyla(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "selam", "--output-format", "json"])
    data = json.loads(result.stdout)
    assert data["type"] == "result" and data["subtype"] == "success"
    assert data["result"] == "tamam" and data["is_error"] is False
    assert data["num_turns"] == 2
    uuid.UUID(data["session_id"])
    for key in ("total_cost_usd", "duration_ms", "duration_api_ms", "modelUsage", "uuid"):
        assert key in data
    assert data["usage"]["input_tokens"] == 0
    assert data["permission_denials"] == []


def test_boru_stdin_istemle_birlesir(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "açıkla"], input="log satırı\n")
    assert result.exit_code == 0, result.output
    assert calls[0]["task"] == "açıkla\n\nlog satırı"


def test_istemsiz_ve_stdinsiz_koşu_claude_hatasiyla_biter(monkeypatch):
    calls, result = _print(monkeypatch, ["-p"], input="")
    assert result.exit_code == 1
    assert "Input must be provided" in result.output
    assert not calls


def test_stdin_10mb_siniri(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "x"], input="a" * (10 * 1024 * 1024 + 5))
    assert result.exit_code == 1
    assert "10 MB" in result.output and not calls


def test_hatali_tur_cikis_kodu_1_ve_alt_tur(monkeypatch):
    _calls, result = _print(
        monkeypatch,
        ["-p", "x", "--output-format", "json"],
        outcomes=[_outcome(ok=False, hit_step_limit=True, final_text="sınır")],
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["subtype"] == "error_max_turns" and data["is_error"] is True
    assert data["errors"] == ["sınır"]


# --- oturum (#277, #304) ---------------------------------------------------------------- #


def test_continue_onceki_p_oturumunu_surdurur(monkeypatch):
    _calls, first = _print(monkeypatch, ["-p", "ilk", "--output-format", "json"])
    session_id = json.loads(first.stdout)["session_id"]
    calls, second = _print(monkeypatch, ["-c", "-p", "ikinci", "--output-format", "json"])
    assert second.exit_code == 0, second.output
    assert json.loads(second.stdout)["session_id"] == session_id
    history = calls[0]["history"]
    assert [m.content for m in history][:2] == ["ilk", "tamam"]


def test_resume_kimlikle_ve_session_id(monkeypatch):
    sid = str(uuid.uuid4())
    _print(monkeypatch, ["-p", "ilk", "--session-id", sid])
    calls, result = _print(monkeypatch, ["-r", sid, "-p", "sonra", "--output-format", "json"])
    assert json.loads(result.stdout)["session_id"] == sid
    assert calls[0]["conversation_id"] == sid


def test_gecersiz_session_id(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "x", "--session-id", "kimlik"])
    assert result.exit_code == 1 and "valid UUID" in result.output


def test_kalicilik_kapali_oturum_yazilmaz(monkeypatch):
    _print(monkeypatch, ["-p", "ilk", "--no-session-persistence"])
    _calls, result = _print(monkeypatch, ["-c", "-p", "x", "--output-format", "json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["is_error"] is True


# --- izin ve araç bayrakları (#286-#292) ------------------------------------------------ #


def test_allowedtools_on_onay_kuralidir_daraltmaz(monkeypatch):
    calls, result = _print(
        monkeypatch, ["-p", "x", "--allowedTools", "Bash(git log *)", "Read", "--verbose"]
    )
    assert result.exit_code == 0, result.output
    rules = calls[0]["extra_permission_rules"]
    assert {(r.tool, r.specifier) for r in rules} == {("Bash", "git log *"), ("Read", None)}
    assert all(r.decision is PermissionDecision.ALLOW for r in rules)
    assert calls[0]["allowed_tools"] is None


def test_disallowedtools_ciplak_ad_cikarir_kapsamli_kural_cagri_reddeder(monkeypatch):
    calls, _ = _print(
        monkeypatch,
        ["-p", "x", "--disallowed-tools", "WebSearch", "--disallowedTools", "Bash(rm *)"],
    )
    assert calls[0]["denied_tools"] == frozenset({"web_search"})
    (rule,) = calls[0]["extra_permission_rules"]
    assert rule.decision is PermissionDecision.DENY and rule.specifier == "rm *"


def test_bilinmeyen_claude_adi_kosuyu_dusurmez(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "x", "--allowedTools", "KillShell"])
    assert result.exit_code == 0
    assert "KillShell" in result.output  # stderr uyarısı
    assert "strict_tool_names" not in calls[0]


def test_tools_bayragi_kumeyi_daraltir(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "x", "--tools", "Read,Bash"])
    assert calls[0]["allowed_tools"] == {"read_file", "view_file", "run_shell"}
    calls, _ = _print(monkeypatch, ["-p", "x", "--tools", ""])
    assert calls[0]["allowed_tools"] == set()


@pytest.mark.parametrize(
    ("args", "mode"),
    [
        (["--permission-mode", "acceptEdits"], ApprovalMode.ACCEPT_EDITS),
        (["--permission-mode", "dontAsk"], ApprovalMode.DONT_ASK),
        (["--permission-mode", "bypassPermissions"], ApprovalMode.BYPASS),
        (["--dangerously-skip-permissions"], ApprovalMode.BYPASS),
        (["--permission-mode", "plan"], ApprovalMode.PLAN),
    ],
)
def test_permission_mode_claude_adlari(monkeypatch, args, mode):
    calls, result = _print(monkeypatch, ["-p", "x", *args])
    assert result.exit_code == 0, result.output
    assert calls[0]["mode"] is mode


def test_p_onay_istemcisi_kimseye_sormaz(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "x"])
    prompter = calls[0]["prompter_factory"](lambda: None)
    assert type(prompter).__name__ == "PrintPrompter"


# --- şema, sınırlar, model, sistem istemi (#285, #295, #296, #298, #300, #301) ----------- #


def test_satir_ici_gecersiz_sema_claude_hatasi(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "x", "--json-schema", '{"type": 5}'])
    assert result.exit_code == 1
    assert "--json-schema is not a valid JSON Schema" in result.output


def test_sema_uyan_cevap_structured_output(monkeypatch):
    schema = '{"type":"object","properties":{"a":{"type":"integer"}},"required":["a"]}'
    _calls, result = _print(
        monkeypatch,
        ["-p", "x", "--output-format", "json", "--json-schema", schema],
        outcomes=[_outcome(final_text='{"a": 1}')],
    )
    data = json.loads(result.stdout)
    assert data["subtype"] == "success" and data["structured_output"] == {"a": 1}


def test_sema_uymayinca_yeniden_dener_sonra_alt_tur(monkeypatch):
    schema = '{"type":"object","required":["a"]}'
    calls, result = _print(
        monkeypatch,
        ["-p", "x", "--output-format", "json", "--json-schema", schema],
        outcomes=[_outcome(final_text="{}")] * 3,
    )
    data = json.loads(result.stdout)
    assert len(calls) == 3
    assert data["subtype"] == "error_max_structured_output_retries"
    assert "structured_output" not in data


def test_max_turns_varsayilan_sinirsiz(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "x"])
    assert calls[0]["config"].runtime.agent_max_steps == UNLIMITED_TURNS
    calls, _ = _print(monkeypatch, ["-p", "x", "--max-turns", "3"])
    assert calls[0]["config"].runtime.agent_max_steps == 3


def test_model_ve_yedek_zincir(monkeypatch):
    calls, result = _print(
        monkeypatch, ["-p", "x", "--model", "openrouter/x/y", "--fallback-model", "a/b,c/d"]
    )
    assert result.exit_code == 0, result.output
    agent = calls[0]["config"].agent
    assert agent.model == "openrouter/x/y" and agent.fallback == ("a/b", "c/d")


def test_sistem_istemi_bayraklari(monkeypatch, tmp_path):
    (tmp_path / "s.txt").write_text("DOSYA", encoding="utf-8")
    (tmp_path / "e.txt").write_text("EK-DOSYA", encoding="utf-8")
    calls, _ = _print(
        monkeypatch,
        [
            "-p",
            "x",
            "--system-prompt-file",
            str(tmp_path / "s.txt"),
            "--append-system-prompt-file",
            str(tmp_path / "e.txt"),
            "--append-system-prompt",
            "EK",
        ],
    )
    assert calls[0]["system_prompt"] == "DOSYA"
    assert calls[0]["extra_system"] == "EK-DOSYA\n\nEK"


def test_mcp_config_satir_ici_ve_strict(monkeypatch):
    raw = '{"mcpServers": {"dosya": {"command": "npx", "args": ["x"]}}}'
    calls, result = _print(monkeypatch, ["-p", "x", "--mcp-config", raw, "--strict-mcp-config"])
    assert result.exit_code == 0, result.output
    assert [s.name for s in calls[0]["config"].mcp_servers] == ["dosya"]


def test_bare_kancalari_kapatir_araclari_sinirlar(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "x", "--bare"])
    config = calls[0]["config"]
    assert config.runtime.hooks_enabled is False and config.mcp_servers == ()
    assert calls[0]["allowed_tools"] == set(BARE_TOOLS)


# --- diğer kök bayraklar (#303, #306, #311, #315) --------------------------------------- #


def test_version_bayragi():
    result = runner.invoke(app_module.app, ["-v"])
    assert result.exit_code == 0 and result.stdout.strip() == __version__


def test_bg_p_ile_birlesmez(monkeypatch):
    _calls, result = _print(monkeypatch, ["--bg", "-p", "x"])
    assert result.exit_code == 1 and "--bg cannot be used with --print" in result.output


def test_add_dir_var_olmayan_dizini_reddeder(monkeypatch, tmp_path):
    _calls, result = _print(monkeypatch, ["-p", "x", "--add-dir", str(tmp_path / "yok")])
    assert result.exit_code == 2


def test_stream_json_verbose_ister(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "x", "--output-format", "stream-json"])
    assert result.exit_code == 1 and "requires --verbose" in result.output


def test_stream_json_init_ve_result(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "x", "--output-format", "stream-json", "--verbose"])
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert lines[0]["type"] == "system" and lines[0]["subtype"] == "init"
    assert lines[0]["permissionMode"] == "default"
    assert lines[-2]["type"] == "assistant"
    assert lines[-1]["type"] == "result" and lines[-1]["session_id"] == lines[0]["session_id"]


def test_input_stream_json_her_satir_bir_tur(monkeypatch):
    stdin = "\n".join(
        json.dumps({"type": "user", "message": {"role": "user", "content": text}})
        for text in ("bir", "iki")
    )
    calls, result = _print(
        monkeypatch,
        ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"],
        input=stdin + "\n",
    )
    assert result.exit_code == 0, result.output
    assert [c["task"] for c in calls] == ["bir", "iki"]
    results = [json.loads(x) for x in result.stdout.splitlines() if '"type": "result"' in x]
    assert len(results) == 2


def test_root_konumsal_istem_repl_ilk_turu(monkeypatch):
    seen: dict[str, object] = {}

    async def _repl(config, **kwargs):
        seen.update(kwargs)
        return 0

    from fusion_cli.config.readiness import Readiness

    monkeypatch.setattr(app_module, "run_repl", _repl)
    monkeypatch.setattr(
        app_module, "evaluate", lambda *_a, **_k: SimpleNamespace(state=Readiness.READY)
    )
    result = runner.invoke(app_module.app, ["merhaba dünya"])
    assert result.exit_code == 0, result.output
    assert seen["initial_prompt"] == "merhaba dünya"


# --- SDK dönüştürücüsü (#280, #284, #292) ----------------------------------------------- #


def test_sdk_akisi_arac_cagrisini_claude_mesajlarina_cevirir():
    import io

    from fusion_cli.cli.sdk_messages import RunStats, SdkStream
    from fusion_cli.core.events import (
        Channel,
        TokenReceived,
        ToolExecuted,
        ToolOutcome,
        ToolStarted,
    )

    out = io.StringIO()
    stream = SdkStream("s1", lambda: "m", stdout=out, partial=True)
    stats = RunStats()
    events = [
        TokenReceived(Channel.MAIN, "bakıyorum", provisional=True),
        ToolStarted("run_shell", {"command": "ls"}, call_id="c1"),
        ToolExecuted("run_shell", {"command": "ls"}, ToolOutcome.OK, "a.txt", call_id="c1"),
        ToolExecuted("write_file", {"path": "x"}, ToolOutcome.DENIED, "reddedildi", call_id="c2"),
    ]
    for event in events:
        stream.handle(event)
        stats.handle(event)
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    kinds = [(m["type"], m.get("subtype")) for m in lines]
    assert kinds[0] == ("stream_event", None)
    assistant = lines[1]["message"]["content"]
    assert assistant[0] == {"type": "text", "text": "bakıyorum"}
    assert assistant[1]["type"] == "tool_use" and assistant[1]["name"] == "Bash"
    assert lines[2]["message"]["content"][0]["tool_use_id"] == "c1"
    assert ("system", "permission_denied") in kinds
    assert stats.denials == [
        {"tool_name": "Write", "tool_use_id": "c2", "tool_input": {"path": "x"}}
    ]


def test_print_cagrisi_run_agent_task_imzasina_uyar(monkeypatch):
    import inspect

    from fusion_cli.cli import session

    calls, _ = _print(monkeypatch, ["-p", "x"])
    kwargs = {k: v for k, v in calls[0].items() if k not in ("task", "config")}
    inspect.signature(session.run_agent_task).bind("x", calls[0]["config"], **kwargs)


def test_print_istemcisi_sorulamadi_doner():
    import asyncio

    from fusion_cli.cli.print_runtime import PrintPrompter
    from fusion_cli.engines.agent.approval import ApprovalAnswer

    prompter = PrintPrompter()
    assert asyncio.run(prompter.confirm(SimpleNamespace())) is ApprovalAnswer.UNAVAILABLE


# --- onay aracı ve beceri genişletmesi (#293, #313) ------------------------------------- #


def test_onay_araci_allow_cevabi_onaydir():
    import asyncio

    from fusion_cli.cli.print_prompt_tool import PromptToolPrompter
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent.approval import ApprovalAnswer

    seen: list[dict] = []

    def _run(args, _ctx):
        seen.append(args)
        behavior = "allow" if args["tool_name"] == "Bash" else "deny"
        return ToolResult(json.dumps({"behavior": behavior}))

    async def _loader(name):
        assert name == "onay__sor"
        return SimpleNamespace(run=_run)

    prompter = PromptToolPrompter("mcp__onay__sor", _loader, root=__import__("pathlib").Path("."))
    bash = SimpleNamespace(tool=SimpleNamespace(name="run_shell"), args={"command": "ls"})
    write = SimpleNamespace(tool=SimpleNamespace(name="write_file"), args={"path": "x"})
    assert asyncio.run(prompter.confirm(bash)) is ApprovalAnswer.ONCE
    assert asyncio.run(prompter.confirm(write)) is ApprovalAnswer.UNAVAILABLE
    assert seen[0]["input"] == {"command": "ls"}


def test_onay_araci_bulunamazsa_reddeder():
    import asyncio

    from fusion_cli.cli.print_prompt_tool import PromptToolPrompter
    from fusion_cli.engines.agent.approval import ApprovalAnswer

    async def _loader(_name):
        return None

    prompter = PromptToolPrompter("mcp__yok__arac", _loader, root=__import__("pathlib").Path("."))
    request = SimpleNamespace(tool=SimpleNamespace(name="run_shell"), args={})
    assert asyncio.run(prompter.confirm(request)) is ApprovalAnswer.UNAVAILABLE
    assert prompter.errors


def test_p_isteminde_beceri_genisletilir(monkeypatch, tmp_path):
    skill_dir = tmp_path / ".claude" / "skills" / "ozetle"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ozetle\ndescription: kısa özet\n---\nHER ZAMAN TEK PARAGRAF YAZ.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    calls, result = _print(monkeypatch, ["-p", "/ozetle README"])
    assert result.exit_code == 0, result.output
    assert "README" in calls[0]["task"]
    assert "TEK PARAGRAF" in calls[0]["extra_system"] + calls[0]["task"]


def test_p_isteminde_etkilesimli_komut_kullanilamaz(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "/clear"])
    assert result.stdout.strip() == "/clear isn't available in this environment."
    assert not calls


def test_disable_slash_commands_metni_aynen_gonderir(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "/clear", "--disable-slash-commands"])
    assert calls[0]["task"] == "/clear"


def test_sigterm_istisnaya_cevrilir():
    import os
    import signal

    from fusion_cli.cli.print_runtime import TerminatedError, sigterm_as_exception

    with pytest.raises(TerminatedError), sigterm_as_exception():
        os.kill(os.getpid(), signal.SIGTERM)
        __import__("time").sleep(1)


# --- --from-pr, kök --bg, kök --model (#302, #311, #296) -------------------------------- #


def test_from_pr_pre_bagli_oturumu_surdurur(monkeypatch):
    from fusion_cli.cli.repl import linked_pr
    from fusion_cli.config.loader import load_config
    from fusion_cli.core.pull_request import PullRequestLink

    _calls, first = _print(monkeypatch, ["-p", "ilk", "--output-format", "json"])
    sid = json.loads(first.stdout)["session_id"]
    url = "https://github.com/o/r/pull/42"
    linked_pr.save(load_config().memory_dir, sid, PullRequestLink("o/r", 42, url))
    for value in ("42", url):
        calls, result = _print(
            monkeypatch, ["-p", "sürdür", "--from-pr", value, "--output-format", "json"]
        )
        assert json.loads(result.stdout)["session_id"] == sid, result.output
        assert calls[0]["history"]


def test_from_pr_bagli_oturum_yoksa_hata_sonucu(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "x", "--from-pr", "7", "--output-format", "json"])
    assert result.exit_code == 1 and json.loads(result.stdout)["is_error"] is True


def test_kok_bg_arka_plan_komutuna_cevrilir():
    assert rewrite_root_args(["--bg", "görev"], _group()) == ["agent", "--bg", "görev"]


def test_kok_model_repl_yapilandirmasina_gecer(monkeypatch):
    seen: dict[str, object] = {}

    async def _repl(config, **kwargs):
        seen["config"] = config
        return 0

    from fusion_cli.config.readiness import Readiness

    monkeypatch.setattr(app_module, "run_repl", _repl)
    monkeypatch.setattr(
        app_module, "evaluate", lambda *_a, **_k: SimpleNamespace(state=Readiness.READY)
    )
    result = runner.invoke(app_module.app, ["--model", "openrouter/a/b"])
    assert result.exit_code == 0, result.output
    assert seen["config"].agent.model == "openrouter/a/b"


# --- fusion update / install (#308) ----------------------------------------------------- #


def test_update_paket_yoneticisini_calistirir(monkeypatch):
    from fusion_cli.cli import maintenance, self_update
    from fusion_cli.install import InstallMethod

    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, "current_method", lambda: InstallMethod.UV)
    monkeypatch.setattr(self_update, "default_runner", lambda argv: ran.append(list(argv)) or 0)
    monkeypatch.setattr(
        self_update,
        "run_maintenance",
        lambda argv, method, runner=None: (
            self_update.default_runner(argv) if argv else 1,
            "",
        ),
    )
    result = runner.invoke(app_module.app, ["update"])
    assert result.exit_code == 0, result.output
    assert ran == [["uv", "tool", "upgrade", "fusion-cli"]]


def test_install_surum_iğneler_ve_bilinmeyen_yontem_talimat_verir():
    from fusion_cli.cli.self_update import install_argv, run_maintenance
    from fusion_cli.install import InstallMethod

    assert install_argv(InstallMethod.PIPX, "0.8.0") == [
        "pipx",
        "install",
        "--force",
        "fusion-cli==0.8.0",
    ]
    assert install_argv(InstallMethod.UV, "stable")[-1] == "fusion-cli"
    code, text = run_maintenance(None, InstallMethod.VENV, runner=lambda _a: 0)
    assert code == 1 and "git pull" in text
    code, text = run_maintenance(["x"], InstallMethod.UV, runner=lambda _a: 3)
    assert code == 3 and "uv tool upgrade" in text


# --- fusion doctor ayar doğrulaması (#309) ---------------------------------------------- #


def test_doctor_bozuk_ayar_dosyasini_raporlar(monkeypatch, tmp_path):
    from fusion_cli.cli.doctor_settings import remote_control_check, settings_checks

    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        '{"permissions": {"allow": ["Bash(git *)", "Bash(("], "deny": "Read"}}', encoding="utf-8"
    )
    (claude / "settings.local.json").write_text("{bozuk", encoding="utf-8")
    checks = {c.name: c for c in settings_checks(tmp_path)}
    bad = [c for c in checks.values() if c.ok is False]
    assert len(bad) == 2
    text = " ".join(c.value for c in bad)
    assert "Bash((" in text and "bir liste olmalı" in text and "okunamadı" in text
    assert remote_control_check().name == "Remote Control"


# --- arka plan işini bekleme (#316) ----------------------------------------------------- #


def test_arka_plan_isi_beklenir_ve_bildirilir(monkeypatch):
    import asyncio

    from fusion_cli.cli import print_runtime

    class _Runs:
        def __init__(self, seconds):
            self.seconds = seconds
            self.closed = False

        @property
        def active_count(self):
            return 1

        async def drain(self):
            await asyncio.sleep(self.seconds)

        async def close(self):
            self.closed = True

    notes: list[str] = []
    asyncio.run(print_runtime.wait_background(_Runs(0.05), notes.append, delay_s=0.01))
    assert notes == ["Waiting for background work to finish"]
    monkeypatch.setenv("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "20")
    slow = _Runs(5)
    asyncio.run(print_runtime.wait_background(slow, notes.append, delay_s=0.01))
    assert slow.closed
