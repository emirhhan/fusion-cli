"""Kanca sistemi Claude Code ile birebir (fark listesi #89–#137): karar, yük, yükleyici."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.config import hooks as hooks_config
from fusion_cli.config import trust
from fusion_cli.core.hooks.decision import merge_verdicts, verdict_from_run
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookRun, HookSet
from fusion_cli.core.hooks.matcher import matcher_matches
from fusion_cli.core.hooks.output import terminal_sequence, tool_output_text
from fusion_cli.engines.agent import hook_text
from fusion_cli.engines.agent.hook_bridge import ToolGate, tool_hook_fields
from fusion_cli.engines.agent.hook_input import claude_tool_response, fusion_tool_args
from fusion_cli.engines.hooks.dispatch import with_event_timeout
from fusion_cli.engines.hooks.overflow import spill
from fusion_cli.engines.hooks.session import HookSession, claude_permission_mode

_PRE = HookEvent.PRE_TOOL_USE


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    monkeypatch.setattr(hooks_config, "managed_settings_file", lambda: ev / "managed.json")
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return ev


def _komut(event=_PRE, command="true", **extra) -> HookCommand:
    return HookCommand(event, "", command, 5.0, "test", "", **extra)


def _karar(event, exit_code, stdout="", stderr="", subject=""):
    return verdict_from_run(event, HookRun(_komut(event), exit_code, stdout, stderr), subject)


def _json(event: HookEvent, **specific) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": event.value, **specific}})


def _betik(tmp_path: Path, body: str, name: str = "k") -> str:
    script = tmp_path / f"{name}.py"
    script.write_text("import json, sys, os\n" + body, encoding="utf-8")
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


# --- Eşleştirici ve konu (#89, #97) ---------------------------------------------- #


@pytest.mark.parametrize(
    ("matcher", "name", "expected"),
    [
        ("Edit.*", "NotebookEdit", True),
        ("^Edit$", "NotebookEdit", False),
        ("^Notebook", "NotebookEdit", True),
        ("mcp__.*__create", "mcp__github__create_issue", True),
        ("Edit, Write", "Write", True),
    ],
)
def test_duzenli_ifade_capasiz_js_test_gibi(matcher, name, expected):
    assert matcher_matches(matcher, (name,)) is expected


def test_kanca_konusu_yalniz_birincil_claude_adi(tmp_path):
    fields = tool_hook_fields("write_file", {"path": "a.txt", "content": "x"}, root=tmp_path)
    hooks = HookSet((HookCommand(_PRE, "Edit", "e", 5.0), HookCommand(_PRE, "Write", "w", 5.0)))
    assert [c.command for c in hooks.for_event(_PRE, (str(fields["tool_name"]),))] == ["w"]
    assert "fusion_tool_name" not in fields


# --- tool_input / tool_response şeması (#91, #100, #101, #135) -------------------- #


def test_tool_input_claude_semasina_cevrilir_ve_mutlak_yol(tmp_path):
    edit = tool_hook_fields("edit_file", {"path": "a.py", "old": "x", "new": "y"}, root=tmp_path)
    assert edit["tool_input"] == {
        "file_path": str((tmp_path / "a.py").resolve()),
        "old_string": "x",
        "new_string": "y",
    }
    shell = tool_hook_fields("run_shell", {"command": "ls", "background": True}, root=tmp_path)
    assert shell["tool_name"] == "Bash"
    assert shell["tool_input"] == {"command": "ls", "run_in_background": True}


def test_updated_input_tamamini_degistirir_ve_geri_cevrilir(tmp_path):
    original = {"path": "a.py", "old": "x", "new": "y", "replace_all": False}
    absolute = str((tmp_path / "a.py").resolve())
    updated = {"file_path": absolute, "old_string": "x", "new_string": "z"}
    assert fusion_tool_args("edit_file", original, updated, tmp_path) == {
        "path": "a.py",
        "old": "x",
        "new": "z",
    }


def test_tool_response_arac_sekli_ve_mcp_server(tmp_path):
    assert claude_tool_response("run_shell", {}, "çıktı") == {
        "stdout": "çıktı",
        "stderr": "",
        "interrupted": False,
        "isImage": False,
    }
    fields = tool_hook_fields("github__create_issue", {}, root=tmp_path)
    assert fields["tool_name"] == "mcp__github__create_issue"
    assert fields["mcp_server"] == {"name": "github"}


# --- Karar sözleşmesi (#102–#104, #114–#118, #131, #132, #128) -------------------- #


def test_sifir_disi_cikis_gecerli_json_alanlari_uygular():
    verdict = _karar(_PRE, 1, _json(_PRE, permissionDecision="deny", permissionDecisionReason="r"))
    assert verdict.blocked and verdict.reason == "r" and verdict.errors == ()


def test_cikis_2_json_gerekcesi_ve_baglami_okunur_engel_kalkmaz():
    stdout = json.dumps(
        {
            "decision": "block",
            "reason": "json gerekçe",
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "bağlam",
            },
        }
    )
    verdict = _karar(HookEvent.POST_TOOL_USE, 2, stdout, "stderr metni")
    assert verdict.blocked and verdict.reason == "json gerekçe"
    assert verdict.additional_context == ("bağlam",)
    allow = _karar(_PRE, 2, _json(_PRE, permissionDecision="allow"), "hayır")
    assert allow.blocked and allow.permission is None and allow.block_source == "true"


def test_gecersiz_json_hata_olur_baglama_eklenmez():
    verdict = _karar(HookEvent.USER_PROMPT_SUBMIT, 0, "{bozuk}")
    assert verdict.additional_context == () and "ayrıştırılamadı" in verdict.errors[0]


def test_hook_event_name_eksik_ya_da_yanlis_sema_hatasi():
    eksik = _karar(_PRE, 0, json.dumps({"hookSpecificOutput": {"permissionDecision": "deny"}}))
    yanlis = _karar(_PRE, 0, _json(HookEvent.STOP, permissionDecision="deny"))
    for verdict in (eksik, yanlis):
        assert not verdict.blocked and "hookEventName" in verdict.errors[0]


def test_engellemeyen_hata_claude_bicimi_ilk_satir():
    verdict = _karar(_PRE, 3, "", "ilk satır\nikinci", subject="Bash")
    assert verdict.errors == (
        "PreToolUse:Bash hook error\nFailed with non-blocking status code: ilk satır",
    )


def test_defer_onceligi_deny_defer_ask_allow():
    def izin(decision):
        return _karar(_PRE, 0, _json(_PRE, permissionDecision=decision))

    assert merge_verdicts((izin("allow"), izin("defer"), izin("ask"))).permission == "defer"
    assert merge_verdicts((izin("defer"), izin("deny"))).blocked


def test_ask_gerekcesi_onay_kuralina_gider_ek_baglam_tutulur():
    verdict = _karar(
        _PRE,
        0,
        _json(
            _PRE,
            permissionDecision="ask",
            permissionDecisionReason="gözden geçir",
            additionalContext="üretim ortamı",
        ),
    )
    assert verdict.ask_reason == "gözden geçir" and verdict.context_text == "üretim ortamı"
    rules = ToolGate({}, permission="ask", ask_reason="gözden geçir").rules(None, "run_shell")
    assert rules is not None and rules.rules[-1].source == "kanca: gözden geçir"


def test_updated_tool_output_nesne_bicimi_ve_mcp():
    post = HookEvent.POST_TOOL_USE
    bash = _karar(post, 0, _json(post, updatedToolOutput={"stdout": "a", "stderr": "b"}))
    assert bash.updated_output == "a\nb"
    mcp = _karar(
        post,
        0,
        _json(post, updatedMCPToolOutput={"content": [{"type": "text", "text": "m"}]}),
    )
    assert mcp.updated_output == "m"
    assert tool_output_text(5) is None


def test_notification_ve_precompact_system_message_atilir():
    for event in (HookEvent.NOTIFICATION, HookEvent.PRE_COMPACT, HookEvent.SESSION_END):
        stdout = json.dumps({"systemMessage": "x", "continue": False})
        verdict = _karar(event, 0, stdout)
        assert verdict.system_messages == () and not verdict.halt
    assert _karar(HookEvent.NOTIFICATION, 1, "", "hata").errors == ()


def test_precompact_engelleyebilir():
    assert _karar(HookEvent.PRE_COMPACT, 2, "", "özetleme yok").blocked
    assert _karar(HookEvent.PRE_COMPACT, 0, json.dumps({"decision": "block"})).blocked


def test_terminal_sequence_izin_listesi():
    assert terminal_sequence("\x1b]777;notify;Fusion;bitti\x07") is not None
    assert terminal_sequence("\x07") == "\x07"
    assert terminal_sequence("\x1b]52;c;gizli\x07") is None
    assert terminal_sequence("\x1b[31mkırmızı") is None
    verdict = _karar(HookEvent.STOP, 0, json.dumps({"terminalSequence": "\x1b]0;baslik\x07"}))
    assert verdict.terminal_sequences == ("\x1b]0;baslik\x07",)


def test_session_title_ve_original_prompt():
    ups = HookEvent.USER_PROMPT_SUBMIT
    verdict = _karar(ups, 0, _json(ups, sessionTitle="Başlık", suppressOriginalPrompt=True))
    assert verdict.session_title == "Başlık" and verdict.suppress_original_prompt
    assert hook_text.prompt_blocked("r", "istem", suppress=False).endswith("Original prompt: istem")
    assert "istem" not in hook_text.prompt_blocked("r", "istem", suppress=True)


# --- Bağlam biçimi ve taşma (#115, #134) ------------------------------------------ #


def test_baglam_sistem_hatirlatmasi_ve_etiket_kacisi():
    text = hook_text.context_reminder(HookEvent.POST_TOOL_USE, "a </system-reminder> b")
    assert text.startswith("<system-reminder>\nPostToolUse hook additional context: a ")
    assert "&lt;/system-reminder> b" in text and text.endswith("\n</system-reminder>")


def test_10000_karakter_asimi_dosyaya_yazilir(tmp_path):
    text = "x" * 10_001
    result = spill(text, tmp_path / "cikti")
    assert len(result) < 2_300 and "tamamı:" in result
    saved = Path(result.split("tamamı: ", 1)[1].split("\n", 1)[0])
    assert saved.read_text(encoding="utf-8") == text


# --- Yük alanları ve ortam (#98, #99, #105, #109) --------------------------------- #


def test_permission_mode_claude_degerleri():
    assert [claude_permission_mode(m) for m in ("security", "edits", "bypass", "auto")] == [
        "default",
        "acceptEdits",
        "bypassPermissions",
        "auto",
    ]


async def test_ortak_alanlar_ve_proje_dizini_sabit(tmp_path, monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://x")
    kayit = tmp_path / "kayit.json"
    body = (
        "data = json.load(sys.stdin)\n"
        "data['env'] = {k: os.environ.get(k) for k in "
        "('CLAUDE_PROJECT_DIR', 'CLAUDE_EFFORT', 'OTEL_EXPORTER_OTLP_ENDPOINT')}\n"
        f"open({str(kayit)!r}, 'w').write(json.dumps(data))\n"
    )
    command = HookCommand(HookEvent.USER_PROMPT_SUBMIT, "", _betik(tmp_path, body), 20.0)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    session = HookSession(
        root=worktree,
        loader=lambda: HookSet((command,)),
        project_dir=tmp_path,
        effort=lambda: "high",
        permission_mode=lambda: "security",
    )
    session.new_prompt()
    await session.emit(HookEvent.USER_PROMPT_SUBMIT, fields={"prompt": "p"})
    data = json.loads(kayit.read_text(encoding="utf-8"))
    assert data["prompt_id"] == session.prompt_id and data["effort"] == {"level": "high"}
    assert data["permission_mode"] == "default" and data["cwd"] == str(worktree)
    assert data["env"] == {
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "CLAUDE_EFFORT": "high",
        "OTEL_EXPORTER_OTLP_ENDPOINT": None,
    }


def test_varsayilan_zaman_asimlari(monkeypatch):
    monkeypatch.delenv(hooks_config.SESSIONEND_TIMEOUT_ENV, raising=False)
    ups = HookEvent.USER_PROMPT_SUBMIT
    timed = with_event_timeout((_komut(ups), _komut(ups, timeout_explicit=True)), ups)
    assert [c.timeout_s for c in timed] == [30.0, 5.0]
    end = HookEvent.SESSION_END
    assert [c.timeout_s for c in with_event_timeout((_komut(end),), end)] == [1.5]
    monkeypatch.setenv(hooks_config.SESSIONEND_TIMEOUT_ENV, "5000")
    assert [c.timeout_s for c in with_event_timeout((_komut(end),), end)] == [5.0]


# --- Yükleyici: tür, olay×tür, öncelik, güven, managed (#95–#96, #107, #108, #119, #137) #


def _ayar(path: Path, hooks: dict, **extra) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks, **extra}), encoding="utf-8")


def _grup(command: str, kind: str | None = "command", **handler) -> list[dict]:
    entry = {"command": command, **handler}
    if kind is not None:
        entry["type"] = kind
    return [{"matcher": "", "hooks": [entry]}]


def test_tur_zorunlu_ve_olay_tur_tablosu(tmp_path, _izole_ev):
    _ayar(
        _izole_ev / ".claude" / "settings.json",
        {
            "Stop": _grup("turu-yok", kind=None),
            "SessionStart": [{"hooks": [{"type": "http", "url": "https://x.test/k"}]}],
            "Notification": _grup("p", kind="prompt"),
        },
    )
    hooks = hooks_config.load_hooks(tmp_path)
    reasons = {skip.event: skip.reason for skip in hooks.skipped}
    assert hooks.commands == ()
    assert "'type' alanı zorunlu" in reasons["Stop"]
    assert reasons["SessionStart"] == "SessionStart olayı http türünü desteklemez"
    assert reasons["Notification"] == "Notification olayı prompt türünü desteklemez"


def test_kullanici_kancalari_varsayilan_acik_eski_dosya_uyarili(tmp_path, _izole_ev):
    _ayar(_izole_ev / ".claude" / "settings.json", {"Stop": _grup("claude")})
    _ayar(hooks_config.user_hooks_file(), {"Stop": _grup("eski")})
    hooks = hooks_config.load_hooks(tmp_path)
    assert {c.command for c in hooks.commands} == {"claude", "eski"}
    assert len(hooks.notices) == 1 and "kullanımdan kalktı" in hooks.notices[0]


def test_disable_all_hooks_oncelik_sirasiyla_cozulur(tmp_path, _izole_ev):
    _ayar(_izole_ev / ".claude" / "settings.json", {"Stop": _grup("a")}, disableAllHooks=True)
    proje = tmp_path / "proje"
    _ayar(proje / ".claude" / "settings.json", {}, disableAllHooks=False)
    assert hooks_config.load_hooks(proje, interactive=False).disabled_reason is None
    assert hooks_config.load_hooks(tmp_path / "bos").disabled_reason is not None


def test_p_kipinde_proje_kancalari_guvensiz_klasorde_calisir(tmp_path):
    """Claude: -p/SDK klasörü güvenilir sayar (güvenlik davranışı değişti, #108)."""
    _ayar(tmp_path / ".claude" / "settings.json", {"Stop": _grup("depo")})
    assert hooks_config.load_hooks(tmp_path).commands == ()
    assert [c.command for c in hooks_config.load_hooks(tmp_path, interactive=False).commands] == [
        "depo"
    ]


def test_yonetilen_katman_ve_allow_managed_hooks_only(tmp_path, _izole_ev):
    _ayar(_izole_ev / ".claude" / "settings.json", {"Stop": _grup("kullanici")})
    _ayar(_izole_ev / "managed.json", {"Stop": _grup("yonetilen")}, allowManagedHooksOnly=True)
    hooks = hooks_config.load_hooks(tmp_path)
    assert [c.command for c in hooks.commands] == ["yonetilen"]
    assert [s.reason for s in hooks.skipped] == [hooks_config.REASON_MANAGED_ONLY]


def test_kullanici_disable_yonetilen_kancayi_kapatamaz(tmp_path, _izole_ev):
    _ayar(_izole_ev / ".claude" / "settings.json", {"Stop": _grup("k")}, disableAllHooks=True)
    _ayar(_izole_ev / "managed.json", {"Stop": _grup("y")})
    hooks = hooks_config.load_hooks(tmp_path)
    assert hooks.disabled_reason is None and [c.command for c in hooks.commands] == ["y"]


# --- Komut alanları: if, args, onFailure, async (#94) ----------------------------- #


async def test_if_kosulu_yalniz_uyan_aracta_calisir(tmp_path):
    command = HookCommand(_PRE, "", "exit 2", 5.0, condition="Bash(git *)")
    session = HookSession(root=tmp_path, loader=lambda: HookSet((command,)))
    git = await session.emit(_PRE, subjects=("Bash",), target=("run_shell", {"command": "git st"}))
    ls = await session.emit(_PRE, subjects=("Bash",), target=("run_shell", {"command": "ls"}))
    stop = await session.emit(HookEvent.STOP)
    assert git.blocked and not ls.blocked and ls.ran == 0
    assert HookSet((replace_event(command, HookEvent.STOP),)).for_event(HookEvent.STOP)
    assert stop.ran == 0


def replace_event(command: HookCommand, event: HookEvent) -> HookCommand:
    from dataclasses import replace

    return replace(command, event=event)


async def test_args_kabuksuz_exec_bicimi(tmp_path):
    body = "sys.stderr.write(sys.argv[1])\nsys.exit(2)\n"
    script = tmp_path / "a.py"
    script.write_text("import sys\n" + body, encoding="utf-8")
    command = HookCommand(_PRE, "", sys.executable, 20.0, args=(str(script), "$HOME `x` 'y'"))
    session = HookSession(root=tmp_path, loader=lambda: HookSet((command,)))
    verdict = await session.emit(_PRE, subjects=("Bash",))
    assert verdict.blocked and verdict.reason == "$HOME `x` 'y'"


async def test_on_failure_block_basarisiz_kancada_engeller(tmp_path):
    command = HookCommand(_PRE, "", "exit 7", 5.0, on_failure="block")
    session = HookSession(root=tmp_path, loader=lambda: HookSet((command,)))
    assert (await session.emit(_PRE, subjects=("Bash",))).blocked
    stop = HookCommand(HookEvent.STOP, "", "exit 7", 5.0, on_failure="block")
    stop_session = HookSession(root=tmp_path, loader=lambda: HookSet((stop,)))
    assert not (await stop_session.emit(HookEvent.STOP)).blocked


async def test_async_kanca_karari_beklenmez_rewake_sonraki_tura(tmp_path):
    import asyncio

    command = HookCommand(
        HookEvent.POST_TOOL_USE, "", "echo uyan >&2; exit 2", 5.0, async_rewake=True
    )
    session = HookSession(root=tmp_path, loader=lambda: HookSet((command,)))
    verdict = await session.emit(HookEvent.POST_TOOL_USE, subjects=("Bash",))
    assert not verdict.blocked and verdict.ran == 0
    for _ in range(100):
        if session.rewake_notes:
            break
        await asyncio.sleep(0.02)
    assert session.take_rewake_notes() == ("PostToolUse hook (async): uyan",)


# --- PreCompact girdisi (#112) ---------------------------------------------------- #


async def test_precompact_custom_instructions_null_ya_da_metin(tmp_path):
    kayit = tmp_path / "pc.jsonl"
    body = f"open({str(kayit)!r}, 'a').write(sys.stdin.read() + '\\n')\n"
    command = HookCommand(HookEvent.PRE_COMPACT, "", _betik(tmp_path, body), 20.0)
    session = HookSession(root=tmp_path, loader=lambda: HookSet((command,)))
    await session.pre_compact("auto", "yok sayılır")
    await session.pre_compact("manual", "testlere odaklan")
    rows = [json.loads(line) for line in kayit.read_text(encoding="utf-8").splitlines()]
    assert [r["custom_instructions"] for r in rows] == [None, "testlere odaklan"]
