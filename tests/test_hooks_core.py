"""Kanca sistemi çekirdeği (P-009): eşleştirici, karar sözleşmesi, ayar katmanları, yürütücü."""

from __future__ import annotations

import json
import shlex
import sys
import time
from pathlib import Path

import pytest

from fusion_cli.cli.hooks_view import hook_list_lines
from fusion_cli.config import hooks as hooks_config
from fusion_cli.config import trust
from fusion_cli.core.hooks.decision import merge_verdicts, verdict_from_run
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookRun, HookSet
from fusion_cli.core.hooks.matcher import matcher_matches
from fusion_cli.engines.hooks.runner import run_hook
from fusion_cli.tools.permission_match import claude_tool_names


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return ev


def _komut(event=HookEvent.PRE_TOOL_USE, command="true", matcher="", timeout_s=5.0):
    return HookCommand(event, matcher, command, timeout_s, "test", "")


def _run(event, exit_code, stdout="", stderr=""):
    return HookRun(_komut(event), exit_code, stdout, stderr)


def _karar(event, exit_code, stdout="", stderr=""):
    return verdict_from_run(event, _run(event, exit_code, stdout, stderr))


_PRE = HookEvent.PRE_TOOL_USE


def _ayar(path: Path, hooks: dict, **extra) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks, **extra}), encoding="utf-8")


def _grup(command: str, matcher: str = "", **handler) -> list[dict]:
    return [{"matcher": matcher, "hooks": [{"type": "command", "command": command, **handler}]}]


# --- Eşleştirici ----------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("matcher", "names", "expected"),
    [
        ("", ("run_shell",), True),
        ("*", ("x",), True),
        ("Bash", ("Bash", "run_shell"), True),
        ("Bash", ("BashOutput",), False),
        ("Edit|Write", ("Write", "write_file"), True),
        ("Edit, Write", ("Edit",), True),
        ("mcp__github__.*", ("mcp__github__create_issue",), True),
        ("mcp__github__.*", ("mcp__gitlab__x",), False),
        ("Notebook.*", ("NotebookEdit",), True),
        ("([bozuk", ("([bozuk",), False),
    ],
)
def test_eslestirici_claude_sozdizimini_uygular(matcher, names, expected):
    assert matcher_matches(matcher, names) is expected


def test_fusion_araci_claude_adlariyla_eslesir():
    assert claude_tool_names("run_shell")[0] == "Bash"
    assert {"Write", "Edit"} <= set(claude_tool_names("write_file"))
    assert claude_tool_names("write_file")[0] == "Write"
    assert "mcp__github__create_issue" in claude_tool_names("github__create_issue")
    assert claude_tool_names("bilinmeyen_arac") == ("bilinmeyen_arac",)


def test_ayni_komut_bir_kez_ve_eslestiricisiz_olayda_matcher_yok_sayilir():
    hooks = HookSet(
        (
            _komut(command="a", matcher="Bash"),
            _komut(command="a", matcher="*"),
            _komut(command="b", matcher="Read"),
            _komut(HookEvent.STOP, command="c", matcher="Bash"),
        )
    )
    assert [c.command for c in hooks.for_event(HookEvent.PRE_TOOL_USE, ("Bash",))] == ["a"]
    assert [c.command for c in hooks.for_event(HookEvent.STOP)] == ["c"]
    assert HookSet((_komut(),), disabled_reason="kapalı").for_event(HookEvent.PRE_TOOL_USE) == ()


# --- Karar sözleşmesi ----------------------------------------------------------- #


def test_cikis_2_engeller_ve_stderr_gerekce_olur():
    verdict = _karar(_PRE, 2, "", "yasak\n")
    assert verdict.blocked and verdict.reason == "yasak"


def test_cikis_2_engelleyemeyen_olayda_yalniz_hata_olur():
    verdict = verdict_from_run(HookEvent.SESSION_END, _run(HookEvent.SESSION_END, 2, "", "x"))
    assert not verdict.blocked and verdict.errors


def test_diger_cikis_kodu_engellemez_kullaniciya_hata_doner():
    verdict = _karar(_PRE, 1, "", "patladı")
    assert not verdict.blocked
    assert "çıkış kodu 1" in verdict.errors[0] and "patladı" in verdict.errors[0]


def test_json_pretooluse_izin_karari_ve_girdi_degisikligi():
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "updatedInput": {"command": "ls -la"},
        },
        "systemMessage": "denetlendi",
    }
    verdict = verdict_from_run(
        HookEvent.PRE_TOOL_USE, _run(HookEvent.PRE_TOOL_USE, 0, json.dumps(payload))
    )
    assert verdict.permission == "ask"
    assert verdict.updated_input == {"command": "ls -la"}
    assert verdict.system_messages == ("denetlendi",)


def test_json_deny_ve_decision_block_engeller():
    deny = {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "r"}}
    verdict = _karar(_PRE, 0, json.dumps(deny))
    assert verdict.blocked and verdict.reason == "r"
    block = _karar(HookEvent.STOP, 0, json.dumps({"decision": "block", "reason": "bitmedi"}))
    assert block.blocked and block.reason == "bitmedi"


def test_continue_false_turu_durdurur():
    verdict = verdict_from_run(
        HookEvent.POST_TOOL_USE,
        _run(HookEvent.POST_TOOL_USE, 0, json.dumps({"continue": False, "stopReason": "yeter"})),
    )
    assert verdict.halt and verdict.stop_reason == "yeter"


def test_duz_stdout_yalniz_istem_ve_oturum_olayinda_baglam_olur():
    istem = verdict_from_run(
        HookEvent.USER_PROMPT_SUBMIT, _run(HookEvent.USER_PROMPT_SUBMIT, 0, "dal: main")
    )
    assert istem.additional_context == ("dal: main",)
    arac = verdict_from_run(HookEvent.PRE_TOOL_USE, _run(HookEvent.PRE_TOOL_USE, 0, "gürültü"))
    assert arac.additional_context == ()


def test_birlesimde_en_kisitlayici_izin_ve_her_engel_kazanir():
    allow = verdict_from_run(
        HookEvent.PRE_TOOL_USE,
        _run(HookEvent.PRE_TOOL_USE, 0, '{"hookSpecificOutput": {"permissionDecision": "allow"}}'),
    )
    ask = verdict_from_run(
        HookEvent.PRE_TOOL_USE,
        _run(HookEvent.PRE_TOOL_USE, 0, '{"hookSpecificOutput": {"permissionDecision": "ask"}}'),
    )
    blocked = verdict_from_run(HookEvent.PRE_TOOL_USE, _run(HookEvent.PRE_TOOL_USE, 2, "", "hayır"))
    assert merge_verdicts((allow, ask)).permission == "ask"
    merged = merge_verdicts((allow, blocked))
    assert merged.blocked and merged.reason == "hayır" and merged.ran == 2


# --- Ayar katmanları ------------------------------------------------------------ #


def test_kullanici_dosyalari_okunur_proje_dosyasi_guven_ister(tmp_path, _izole_ev):
    proje = tmp_path / "proje"
    proje.mkdir()
    _ayar(hooks_config.user_hooks_file(), {"Stop": _grup("fusion-kanca")})
    _ayar(_izole_ev / ".claude" / "settings.json", {"PreToolUse": _grup("claude-kanca", "Bash")})
    _ayar(proje / ".claude" / "settings.json", {"PreToolUse": _grup("depo-kancasi")})
    hooks = hooks_config.load_hooks(proje, include_claude=True)
    assert {c.command for c in hooks.commands} == {"fusion-kanca", "claude-kanca"}
    assert hooks.untrusted_layers == ("proje",)
    assert any(s.detail == "depo-kancasi" for s in hooks.skipped)
    trust.trust_project(proje)
    assert "depo-kancasi" in {c.command for c in hooks_config.load_hooks(proje).commands}
    # Güvenden SONRA değişen dosya yeniden güvensizdir.
    _ayar(proje / ".claude" / "settings.json", {"PreToolUse": _grup("yeni-kanca")})
    assert "yeni-kanca" not in {c.command for c in hooks_config.load_hooks(proje).commands}


def test_disable_all_hooks_guvenilmeyen_projeden_okunmaz_uyari_olarak_gorunur(tmp_path, _izole_ev):
    # Kullanıcının koruyucu kancalarını kapatmak gevşetmedir: indirilen depo bunu yapamaz.
    _ayar(hooks_config.user_hooks_file(), {"Stop": _grup("x")})
    _ayar(tmp_path / ".claude" / "settings.local.json", {}, disableAllHooks=True)
    hooks = hooks_config.load_hooks(tmp_path)
    assert hooks.disabled_reason is None
    assert [c.command for c in hooks.for_event(HookEvent.STOP)] == ["x"]
    assert hooks.ignored_disable_layers == ("yerel",)
    assert any("disableAllHooks" in line for line in hook_list_lines(hooks))
    trust.trust_project(tmp_path)
    trusted = hooks_config.load_hooks(tmp_path)
    assert trusted.disabled_reason is not None and "disableAllHooks" in trusted.disabled_reason
    assert trusted.for_event(HookEvent.STOP) == ()


def test_disable_all_hooks_kullanici_dosyasindan_okunur(tmp_path, _izole_ev):
    _ayar(hooks_config.user_hooks_file(), {"Stop": _grup("x")}, disableAllHooks=True)
    assert hooks_config.load_hooks(tmp_path).disabled_reason is not None


def test_kapatma_anahtarlari_ve_claude_dosyalari_secimi(tmp_path, _izole_ev, monkeypatch):
    _ayar(hooks_config.user_hooks_file(), {"Stop": _grup("fusion")})
    _ayar(_izole_ev / ".claude" / "settings.json", {"Stop": _grup("claude")})
    assert hooks_config.load_hooks(tmp_path, enabled=False).disabled_reason
    only_fusion = hooks_config.load_hooks(tmp_path, include_claude=False)
    assert [c.command for c in only_fusion.commands] == ["fusion"]
    # Kapalı Claude dosyasının kancaları listede gerekçesiyle görünür (kullanıcı bilsin).
    assert [(s.detail, s.reason) for s in only_fusion.skipped] == [
        ("claude", hooks_config.REASON_CLAUDE_OFF)
    ]
    monkeypatch.setenv("FUSION_HOOKS", "off")
    assert hooks_config.load_hooks(tmp_path).disabled_reason == "FUSION_HOOKS=off"


def test_desteklenmeyen_tur_ve_olay_gerekceli_atlanir_sure_sinirlanir(tmp_path):
    _ayar(
        hooks_config.user_hooks_file(),
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        # `http` artık desteklenir (bkz. test_hooks_http.py); `mcp_tool` değil.
                        {"type": "mcp_tool", "url": "https://ornek.test/kanca"},
                        {"type": "command", "command": "uzun", "timeout": 99999},
                        {"type": "command", "command": "   "},
                    ],
                }
            ],
            "WorktreeCreate": _grup("wt"),
            "Uydurma": _grup("u"),
        },
    )
    hooks = hooks_config.load_hooks(tmp_path, default_timeout_s=7)
    assert [(c.command, c.timeout_s) for c in hooks.commands] == [("uzun", 600.0)]
    reasons = {s.detail: s.reason for s in hooks.skipped}
    assert "desteklenmiyor: mcp_tool" in reasons["https://ornek.test/kanca"]
    assert reasons["wt"] == hooks_config.REASON_EVENT
    assert reasons["u"] == hooks_config.REASON_UNKNOWN_EVENT
    assert reasons["   "] == hooks_config.REASON_EMPTY


def test_bozuk_dosya_kanca_acmaz_otekileri_dusurmez(tmp_path, _izole_ev):
    (_izole_ev / ".claude").mkdir()
    (_izole_ev / ".claude" / "settings.json").write_text("{bozuk", encoding="utf-8")
    _ayar(hooks_config.user_hooks_file(), {"Stop": _grup("saglam")})
    assert [c.command for c in hooks_config.load_hooks(tmp_path).commands] == ["saglam"]


# --- Yürütücü ------------------------------------------------------------------- #


def _betik(tmp_path: Path, body: str) -> str:
    script = tmp_path / f"kanca_{abs(hash(body))}.py"
    script.write_text(body, encoding="utf-8")
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


async def test_yurutucu_stdine_olay_jsonunu_yazar_ve_proje_degiskenini_verir(tmp_path):
    command = _betik(
        tmp_path,
        "import json, os, sys\n"
        "data = json.load(sys.stdin)\n"
        "dizin = os.environ['CLAUDE_PROJECT_DIR']\n"
        "print(json.dumps({'systemMessage': data['tool_name'] + '|' + dizin}))\n",
    )
    run = await run_hook(
        _komut(command=command),
        {"tool_name": "Bash"},
        cwd=tmp_path,
        environment=hooks_config.hook_environment(tmp_path),
    )
    verdict = verdict_from_run(HookEvent.PRE_TOOL_USE, run)
    assert verdict.system_messages == (f"Bash|{tmp_path}",)


async def test_yurutucu_zaman_asiminda_sureci_oldurur(tmp_path):
    started = time.monotonic()
    run = await run_hook(
        _komut(command="sleep 30", timeout_s=0.5),
        {},
        cwd=tmp_path,
        environment=hooks_config.hook_environment(tmp_path),
    )
    assert run.timed_out and time.monotonic() - started < 10
    assert "bitmedi" in verdict_from_run(HookEvent.PRE_TOOL_USE, run).errors[0]


async def test_stdini_okumayan_kanca_da_calisir(tmp_path):
    run = await run_hook(
        _komut(command="echo merhaba"),
        {"buyuk": "x" * 200_000},
        cwd=tmp_path,
        environment=hooks_config.hook_environment(tmp_path),
    )
    assert run.exit_code == 0 and run.stdout.strip() == "merhaba"


def test_claude_hooks_kapaliyken_guvenilen_proje_kancalari_calisir(tmp_path, _izole_ev):
    # `runtime.claude_hooks` yalnız ~/.claude/settings.json'ı yönetir; proje dosyası güvenle açılır.
    _ayar(
        _izole_ev / ".claude" / "settings.json",
        {"Stop": _grup("claude"), "x": []},
        disableAllHooks=True,
    )
    _ayar(tmp_path / ".claude" / "settings.json", {"Stop": _grup("depo")})
    trust.trust_project(tmp_path)
    hooks = hooks_config.load_hooks(tmp_path, include_claude=False)
    assert hooks.disabled_reason is None
    assert [c.command for c in hooks.commands] == ["depo"]


async def test_kanca_sureci_mcp_sirlarini_ortamdan_almaz(tmp_path, monkeypatch):
    from fusion_cli.engines.hooks.session import HookSession

    monkeypatch.setenv("GIZLI_MCP_ANAHTARI", "sk-gizli-123")
    monkeypatch.setenv("SIRADAN_DEGISKEN", "gorunur")
    script = tmp_path / "env_yaz.py"
    script.write_text(
        "import os, sys\n"
        "sys.stderr.write(os.environ.get('GIZLI_MCP_ANAHTARI', 'yok') + ' '"
        " + os.environ.get('SIRADAN_DEGISKEN', 'yok'))\nsys.exit(2)\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    session = HookSession(
        root=tmp_path,
        loader=lambda: HookSet((_komut(command=command),)),
        hidden_env=lambda: frozenset({"GIZLI_MCP_ANAHTARI"}),
    )
    verdict = await session.emit(HookEvent.PRE_TOOL_USE, subjects=("Bash",))
    assert verdict.reason == "yok gorunur"
    assert "GIZLI_MCP_ANAHTARI" not in hooks_config.hook_environment(
        tmp_path, frozenset({"GIZLI_MCP_ANAHTARI"})
    )
