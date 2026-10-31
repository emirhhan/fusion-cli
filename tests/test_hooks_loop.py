"""Kancalar ajan döngüsünde (P-009): PreToolUse/PostToolUse/UserPromptSubmit/Stop/Session*.

Kanca betikleri gerçek alt süreçtir (Python); sağlayıcı sahtedir (`ScriptedProvider`).
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.core.events import ErrorOccurred, NarrationPublished
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalMode, build_policy
from fusion_cli.engines.agent.hook_bridge import MAX_STOP_CONTINUATIONS
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.hooks.notify import notifying
from fusion_cli.engines.hooks.session import HookSession

from .fakes import RecordingSink, ScriptedProvider, make_config, model_result, tool_call


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


class _Kaydeden:
    def __init__(self):
        self.soruldu: list[str] = []

    async def confirm(self, request):
        self.soruldu.append(request.tool.name)
        return ApprovalAnswer.ONCE


def _kanca(tmp_path: Path, event: HookEvent, body: str, matcher: str = "") -> HookCommand:
    script = tmp_path / f"kanca_{event.value}_{abs(hash(body))}.py"
    script.write_text("import json, sys\ndata = json.load(sys.stdin)\n" + body, encoding="utf-8")
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return HookCommand(event, matcher, command, 20.0, "test", "")


def _oturum(tmp_path: Path, *commands: HookCommand) -> HookSession:
    return HookSession(root=tmp_path, loader=lambda: HookSet(tuple(commands)))


def _kayit_kancasi(tmp_path: Path, event: HookEvent, kayit: Path, matcher: str = "") -> HookCommand:
    """Olay yükünü `kayit` dosyasına satır satır yazan kanca."""
    return _kanca(
        tmp_path,
        event,
        f"open({str(kayit)!r}, 'a', encoding='utf-8').write(json.dumps(data) + '\\n')\n",
        matcher,
    )


def _satirlar(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def _tur(
    monkeypatch,
    tmp_path,
    results,
    session,
    *,
    mod=ApprovalMode.AUTO,
    rules=None,
    task="iş",
):
    sink = RecordingSink()
    provider = ScriptedProvider(results)
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    prompter = _Kaydeden()
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(sink),
        policy=build_policy(mod, notifying(prompter, session)),
        tool_context=ToolContext(root=tmp_path),
        permission_rules=rules,
        hooks=session,
    )
    outcome = await run_agent(task, deps)
    return outcome, provider, prompter, sink


def _yaz(path: str, content: str = "x", final: str = "ok") -> list:
    """Tek `write_file` çağrısı ve ardından son cevap."""
    return [
        model_result(tool_calls=[tool_call("write_file", path=path, content=content)]),
        model_result(final),
    ]


def _arac_mesajlari(outcome):
    return [m.content for m in outcome.messages if m.role == "tool"]


# --- PreToolUse ----------------------------------------------------------------- #


async def test_pretooluse_cikis_2_araci_calistirmaz_gerekce_modele_gider(monkeypatch, tmp_path):
    session = _oturum(
        tmp_path,
        _kanca(
            tmp_path,
            HookEvent.PRE_TOOL_USE,
            "sys.stderr.write('.env yazılamaz: ' + data['tool_input']['file_path'])\nsys.exit(2)\n",
            "Write",
        ),
    )
    outcome, provider, _, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz(".env", "X=1", "tamam"),
        session,
    )
    assert not (tmp_path / ".env").exists()
    assert "KANCA ENGELLEDİ (PreToolUse): .env yazılamaz: .env" in _arac_mesajlari(outcome)[0]
    assert provider.calls >= 2  # tur durmadı; model gerekçeyi gördü


async def test_pretooluse_eslesmeyen_arac_icin_calismaz(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(tmp_path, _kayit_kancasi(tmp_path, HookEvent.PRE_TOOL_USE, kayit, "Bash"))
    await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.txt", "x", "ok"),
        session,
    )
    assert (tmp_path / "a.txt").exists()
    assert _satirlar(kayit) == []


async def test_pretooluse_updated_input_file_path_ile_hedefi_degistirir(monkeypatch, tmp_path):
    session = _oturum(
        tmp_path,
        _kanca(
            tmp_path,
            HookEvent.PRE_TOOL_USE,
            "inp = dict(data['tool_input']); inp['file_path'] = 'yonlendirildi.txt'\n"
            "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
            " 'permissionDecision': 'allow', 'updatedInput': inp}}))\n",
        ),
    )
    await _tur(
        monkeypatch,
        tmp_path,
        _yaz("asil.txt", "x", "ok"),
        session,
    )
    assert (tmp_path / "yonlendirildi.txt").read_text(encoding="utf-8") == "x"
    assert not (tmp_path / "asil.txt").exists()


_ASK = (
    "print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'ask',"
    " 'permissionDecisionReason': 'gözden geçir'}}))\n"
)
_ALLOW = "print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'allow'}}))\n"


async def test_pretooluse_ask_otomatik_kipte_de_sordurur(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _ASK))
    _, _, prompter, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.txt", "x", "ok"),
        session,
    )
    assert prompter.soruldu == ["write_file"]


async def test_pretooluse_allow_manuelde_sormaz_deny_kuralini_gecemez(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _ALLOW))
    _, _, prompter, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.txt", "x", "ok"),
        session,
        mod=ApprovalMode.SECURITY,
    )
    assert prompter.soruldu == [] and (tmp_path / "a.txt").exists()

    deny = PermissionRuleSet((parse_rule("Edit(/b.txt)", PermissionDecision.DENY, source="t"),))
    outcome, _, prompter, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("b.txt", "x", "ok"),
        session,
        rules=deny,
    )
    assert not (tmp_path / "b.txt").exists()
    assert "izin kuralı" in _arac_mesajlari(outcome)[0]


async def test_pretooluse_allow_plan_kipinde_yazmaya_izin_vermez(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _ALLOW))
    await _tur(
        monkeypatch,
        tmp_path,
        _yaz("p.txt", "x", "ok"),
        session,
        mod=ApprovalMode.PLAN,
    )
    assert not (tmp_path / "p.txt").exists()


async def test_pretooluse_continue_false_turu_durdurur(monkeypatch, tmp_path):
    session = _oturum(
        tmp_path,
        _kanca(
            tmp_path,
            HookEvent.PRE_TOOL_USE,
            "print(json.dumps({'continue': False, 'stopReason': 'bakım modu'}))\n",
        ),
    )
    outcome, provider, _, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.txt", "x", "devam"),
        session,
    )
    assert provider.calls == 1
    assert "bakım modu" in _arac_mesajlari(outcome)[0]


# --- PostToolUse ---------------------------------------------------------------- #


async def test_posttooluse_geri_bildirimi_ve_baglami_arac_sonucuna_eklenir(monkeypatch, tmp_path):
    session = _oturum(
        tmp_path,
        _kanca(
            tmp_path,
            HookEvent.POST_TOOL_USE,
            "assert data['tool_response']['success'] is True\n"
            "print(json.dumps({'decision': 'block', 'reason': 'lint hatası: satır 1',"
            " 'hookSpecificOutput': {'additionalContext': 'stil rehberi: PEP 8'}}))\n",
            "Edit|Write",
        ),
    )
    outcome, _, _, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.py", "x", "ok"),
        session,
    )
    govde = _arac_mesajlari(outcome)[0]
    assert "KANCA GERİ BİLDİRİMİ (PostToolUse): lint hatası: satır 1" in govde
    assert "stil rehberi: PEP 8" in govde
    assert (tmp_path / "a.py").exists()  # PostToolUse geri almaz


async def test_posttoolusefailure_basarisiz_aracta_tetiklenir(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(
        tmp_path, _kayit_kancasi(tmp_path, HookEvent.POST_TOOL_USE_FAILURE, kayit, "Read")
    )
    await _tur(
        monkeypatch,
        tmp_path,
        [model_result(tool_calls=[tool_call("read_file", path="yok.txt")]), model_result("ok")],
        session,
    )
    satirlar = _satirlar(kayit)
    assert len(satirlar) == 1 and satirlar[0]["tool_name"] == "Read"
    assert satirlar[0]["hook_event_name"] == "PostToolUseFailure" and satirlar[0]["error"]


# --- UserPromptSubmit / SessionStart / Stop -------------------------------------- #


async def test_userpromptsubmit_engeli_modeli_hic_cagirmaz(monkeypatch, tmp_path):
    session = _oturum(
        tmp_path,
        _kanca(
            tmp_path,
            HookEvent.USER_PROMPT_SUBMIT,
            "sys.stderr.write('sır içeriyor') if 'parola' in data['prompt'] else None\n"
            "sys.exit(2 if 'parola' in data['prompt'] else 0)\n",
        ),
    )
    outcome, provider, _, sink = await _tur(
        monkeypatch, tmp_path, [model_result("cevap")], session, task="parola: 1234"
    )
    assert provider.calls == 0 and not outcome.ok
    assert "sır içeriyor" in outcome.final_text
    assert any(isinstance(e, ErrorOccurred) and "sır içeriyor" in e.message for e in sink.events)


async def test_sessionstart_ve_istem_baglami_sisteme_eklenir_oturum_bir_kez_baslar(
    monkeypatch, tmp_path
):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.SESSION_START, kayit),
        _kanca(tmp_path, HookEvent.SESSION_START, "print('açık PR: #42')\n"),
        _kanca(tmp_path, HookEvent.USER_PROMPT_SUBMIT, "print('saat dilimi: UTC+3')\n"),
    )
    _, provider, _, _ = await _tur(monkeypatch, tmp_path, [model_result("bir")], session)
    sistem = "\n".join(m.content for m in provider.seen_messages[0] if m.role == "system")
    assert "açık PR: #42" in sistem and "saat dilimi: UTC+3" in sistem
    await _tur(monkeypatch, tmp_path, [model_result("iki")], session)
    assert [s["source"] for s in _satirlar(kayit)] == ["startup"]


async def test_stop_engeli_ajani_gerekceyle_surdurur_stop_hook_active_ile(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.STOP, kayit),
        _kanca(
            tmp_path,
            HookEvent.STOP,
            "if not data['stop_hook_active']:\n"
            "    print(json.dumps({'decision': 'block', 'reason': 'testleri koşmadın'}))\n",
        ),
    )
    outcome, provider, _, _ = await _tur(
        monkeypatch, tmp_path, [model_result("bitti"), model_result("testler geçti")], session
    )
    assert provider.calls == 2
    assert outcome.final_text == "testler geçti"
    devam = [m.content for m in provider.seen_messages[1] if m.role == "user"][-1]
    assert "testleri koşmadın" in devam
    assert [s["stop_hook_active"] for s in _satirlar(kayit)] == [False, True]
    assert _satirlar(kayit)[0]["last_assistant_message"] == "bitti"


async def test_stop_kancasi_hep_engellese_de_sinirda_durur(monkeypatch, tmp_path):
    session = _oturum(
        tmp_path,
        _kanca(
            tmp_path, HookEvent.STOP, "print(json.dumps({'decision': 'block', 'reason': 'y'}))\n"
        ),
    )
    results = [model_result(f"cevap {i}") for i in range(MAX_STOP_CONTINUATIONS + 3)]
    _, provider, _, _ = await _tur(monkeypatch, tmp_path, results, session)
    assert provider.calls == MAX_STOP_CONTINUATIONS + 1


async def test_sessionend_yalniz_baslamis_oturumda_bir_kez(tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(tmp_path, _kayit_kancasi(tmp_path, HookEvent.SESSION_END, kayit))
    await session.end("other")
    assert _satirlar(kayit) == []
    await session.start()
    await session.end("prompt_input_exit")
    await session.end("prompt_input_exit")
    assert [s["reason"] for s in _satirlar(kayit)] == ["prompt_input_exit"]


# --- Notification / hata görünürlüğü --------------------------------------------- #


async def test_notification_izin_sorusundan_once_tetiklenir(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(
        tmp_path, _kayit_kancasi(tmp_path, HookEvent.NOTIFICATION, kayit, "permission_prompt")
    )
    _, _, prompter, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.txt", "x", "ok"),
        session,
        mod=ApprovalMode.SECURITY,
    )
    assert prompter.soruldu == ["write_file"]
    satirlar = _satirlar(kayit)
    assert satirlar[0]["notification_type"] == "permission_prompt"
    assert "write_file" in satirlar[0]["message"]


async def test_bozuk_kanca_turu_bozmaz_kullaniciya_hata_ve_sistem_mesaji_gosterir(
    monkeypatch, tmp_path
):
    session = _oturum(
        tmp_path,
        _kanca(tmp_path, HookEvent.PRE_TOOL_USE, "sys.stderr.write('kırık')\nsys.exit(3)\n"),
        _kanca(
            tmp_path, HookEvent.PRE_TOOL_USE, "print(json.dumps({'systemMessage': 'denetlendi'}))"
        ),
    )
    _, _, _, sink = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.txt", "x", "ok"),
        session,
    )
    assert (tmp_path / "a.txt").exists()
    assert any(isinstance(e, ErrorOccurred) and "kırık" in e.message for e in sink.events)
    assert any(isinstance(e, NarrationPublished) and "denetlendi" in e.text for e in sink.events)


@pytest.mark.parametrize("hooks", [None])
async def test_kancasiz_deps_eski_davranisi_korur(monkeypatch, tmp_path, hooks):
    outcome, provider, _, _ = await _tur(
        monkeypatch,
        tmp_path,
        _yaz("a.txt", "x", "ok"),
        hooks,
    )
    assert (tmp_path / "a.txt").exists() and provider.calls == 2 and outcome.ok


async def test_subagentstop_ajan_turuyle_eslesir_ve_alt_ajani_surdurur(monkeypatch, tmp_path):
    from fusion_cli.core.events import Channel

    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.SUBAGENT_STOP, kayit, "denetci"),
        _kanca(
            tmp_path,
            HookEvent.SUBAGENT_STOP,
            "if not data['stop_hook_active']:\n"
            "    print(json.dumps({'decision': 'block', 'reason': 'kanıt ekle'}))\n",
            "denetci",
        ),
        _kayit_kancasi(tmp_path, HookEvent.STOP, tmp_path / "stop.jsonl"),
    )
    provider = ScriptedProvider([model_result("bitti"), model_result("kanıtlı bitti")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, _Kaydeden()),
        tool_context=ToolContext(root=tmp_path),
        hooks=session,
        channel=Channel.SUBAGENT,
        agent_type="denetci",
    )
    outcome = await run_agent("incele", deps, depth=1)
    assert outcome.final_text == "kanıtlı bitti" and provider.calls == 2
    assert [(s["agent_type"], s["stop_hook_active"]) for s in _satirlar(kayit)] == [
        ("denetci", False),
        ("denetci", True),
    ]
    # Alt ajan kök değildir: Stop ve UserPromptSubmit tetiklenmez.
    assert _satirlar(tmp_path / "stop.jsonl") == []


# --- İnceleme düzeltmeleri (31 Ekim) ---------------------------------------------- #


def _kabuk(command: str, final: str = "ok") -> list:
    """Tek `run_shell` çağrısı ve ardından son cevap."""
    return [
        model_result(tool_calls=[tool_call("run_shell", command=command)]),
        model_result(final),
    ]


class _Reddeden(_Kaydeden):
    async def confirm(self, request):
        self.soruldu.append(request.tool.name)
        return ApprovalAnswer.DENY


async def test_pretooluse_ask_kabuk_aracinda_otomatik_kipte_de_sordurur(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _ASK, "Bash"))
    _, _, prompter, _ = await _tur(monkeypatch, tmp_path, _kabuk("ls"), session)
    assert prompter.soruldu == ["run_shell"]


async def test_pretooluse_allow_kabukta_manuelde_sormaz_deny_kuralini_gecemez(
    monkeypatch, tmp_path
):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _ALLOW, "Bash"))
    _, _, prompter, _ = await _tur(
        monkeypatch, tmp_path, _kabuk("mkdir yeni"), session, mod=ApprovalMode.SECURITY
    )
    assert prompter.soruldu == [] and (tmp_path / "yeni").is_dir()

    deny = PermissionRuleSet((parse_rule("Bash(mkdir *)", PermissionDecision.DENY, source="t"),))
    await _tur(monkeypatch, tmp_path, _kabuk("mkdir yasak"), session, rules=deny)
    assert not (tmp_path / "yasak").exists()


async def test_belirtecsiz_bash_kurali_her_kabuk_komutuna_uyar(tmp_path):
    from fusion_cli.tools.permission_match import evaluate

    for decision in (PermissionDecision.DENY, PermissionDecision.ASK, PermissionDecision.ALLOW):
        rules = PermissionRuleSet((parse_rule("Bash", decision, source="t"),))
        hit = evaluate(rules, "run_shell", {"command": "ls -la && git status"}, tmp_path)
        assert hit is not None and hit.decision is decision
