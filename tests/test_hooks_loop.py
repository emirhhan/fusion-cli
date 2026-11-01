"""Kancalar ajan döngüsünde (P-009): PreToolUse/PostToolUse/UserPromptSubmit/Stop/Session*.

Kanca betikleri gerçek alt süreçtir (Python); sağlayıcı sahtedir (`ScriptedProvider`).
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.config.hooks import DEFAULT_STOP_BLOCK_CAP
from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.core.events import ErrorOccurred, NarrationPublished
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalMode, build_policy
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
    # Claude biçimi: `PreToolUse:Write hook error: [komut]: <stderr>`; dosya yolu mutlak (#91).
    mesaj = _arac_mesajlari(outcome)[0]
    assert mesaj.startswith("PreToolUse:Write hook error: [")
    assert f"]: .env yazılamaz: {tmp_path / '.env'}" in mesaj
    assert "farklı bir yol dene" not in mesaj
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
    "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
    " 'permissionDecision': 'ask',"
    " 'permissionDecisionReason': 'gözden geçir'}}))\n"
)
_ALLOW = (
    "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
    " 'permissionDecision': 'allow'}}))\n"
)


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
            "assert data['tool_response']['filePath'].endswith('a.py')\n"
            "print(json.dumps({'decision': 'block', 'reason': 'lint hatası: satır 1',"
            " 'hookSpecificOutput': {'hookEventName': 'PostToolUse',"
            " 'additionalContext': 'stil rehberi: PEP 8'}}))\n",
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
    assert "PostToolUse:Write hook error: lint hatası: satır 1" in govde
    assert "<system-reminder>\nPostToolUse hook additional context: stil rehberi: PEP 8" in govde
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
    # Claude: bağlam sistem hatırlatması olarak istemle birlikte konuşmada kalır (#92, #134).
    istem = [m.content for m in provider.seen_messages[0] if m.role == "user"][-1]
    assert istem.index("açık PR: #42") < istem.index("saat dilimi: UTC+3")
    assert "<system-reminder>\nSessionStart hook additional context: açık PR: #42" in istem
    assert "UserPromptSubmit hook additional context: saat dilimi: UTC+3" in istem
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
    # Claude: art arda 8 sürdürme tavanı; CLAUDE_CODE_STOP_HOOK_BLOCK_CAP ile değişir (#110).
    assert DEFAULT_STOP_BLOCK_CAP == 8
    monkeypatch.setenv("CLAUDE_CODE_STOP_HOOK_BLOCK_CAP", "4")
    results = [model_result(f"cevap {i}") for i in range(10)]
    _, provider, _, _ = await _tur(monkeypatch, tmp_path, results, session)
    assert provider.calls == 4 + 1


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


def _yavas_soru(monkeypatch, gecikme: float = 0.5) -> None:
    """Yanıtı geciken kullanıcı: bildirim gecikmesi (Claude ~6 sn) testte kısaltılır."""
    import asyncio

    from fusion_cli.engines.hooks import notify

    monkeypatch.setattr(notify, "PERMISSION_NOTIFY_DELAY_S", 0.01)
    hizli = _Kaydeden.confirm

    async def confirm(self, request):
        await asyncio.sleep(gecikme)
        return await hizli(self, request)

    monkeypatch.setattr(_Kaydeden, "confirm", confirm)


async def test_notification_yanitsiz_izin_sorusunda_gecikmeli_tetiklenir(monkeypatch, tmp_path):
    _yavas_soru(monkeypatch)
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
    assert "write_file" in satirlar[0]["message"] and satirlar[0]["title"] == "Fusion"


async def test_notification_hizli_yanitta_iptal_edilir_soruyu_bekletmez(monkeypatch, tmp_path):
    """Claude: bildirim ~6 sn yanıtsız kalınca; yanıt erken gelirse hiç tetiklenmez (#136)."""
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(
        tmp_path, _kayit_kancasi(tmp_path, HookEvent.NOTIFICATION, kayit, "permission_prompt")
    )
    _, _, prompter, _ = await _tur(
        monkeypatch, tmp_path, _yaz("a.txt", "x", "ok"), session, mod=ApprovalMode.SECURITY
    )
    assert prompter.soruldu == ["write_file"] and not kayit.exists()


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


_HALT = "print(json.dumps({'continue': False, 'stopReason': 'bakım modu'}))\n"


async def test_continue_false_kullaniciya_kanca_gerekcesini_soyler_ret_metnini_degil(
    monkeypatch, tmp_path
):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _HALT))
    outcome, provider, _, _ = await _tur(monkeypatch, tmp_path, _yaz("a.txt"), session)
    assert provider.calls == 1
    assert "bakım modu" in outcome.final_text
    assert "onaylamadınız" not in outcome.final_text


async def test_posttooluse_continue_false_gerekceyle_durur(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.POST_TOOL_USE, _HALT))
    outcome, provider, _, _ = await _tur(monkeypatch, tmp_path, _yaz("a.txt"), session)
    assert provider.calls == 1 and (tmp_path / "a.txt").exists()
    assert "bakım modu" in outcome.final_text
    assert "onaylamadınız" not in outcome.final_text


_STOP_BLOK = "print(json.dumps({'decision': 'block', 'reason': 'testleri koş'}))\n"


async def test_stop_kancasi_kanca_durdurmasindan_sonra_turu_acamaz(monkeypatch, tmp_path):
    kayit = tmp_path / "stop.jsonl"
    session = _oturum(
        tmp_path,
        _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _HALT),
        _kayit_kancasi(tmp_path, HookEvent.STOP, kayit),
        _kanca(tmp_path, HookEvent.STOP, _STOP_BLOK),
    )
    _, provider, _, _ = await _tur(
        monkeypatch, tmp_path, [*_yaz("a.txt"), model_result("yine")], session
    )
    assert provider.calls == 1 and _satirlar(kayit) == []


async def test_stop_kancasi_kullanici_reddinden_sonra_calismaz(monkeypatch, tmp_path):
    kayit = tmp_path / "stop.jsonl"
    session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.STOP, kayit),
        _kanca(tmp_path, HookEvent.STOP, _STOP_BLOK),
    )
    sink = RecordingSink()
    provider = ScriptedProvider([*_yaz("a.txt"), model_result("yine")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.SECURITY, _Reddeden()),
        tool_context=ToolContext(root=tmp_path),
        hooks=session,
    )
    outcome = await run_agent("iş", deps)
    assert "onaylamadınız" in outcome.final_text
    assert provider.calls == 1 and _satirlar(kayit) == []


async def test_stop_kancasi_butce_sinirinda_calismaz(monkeypatch, tmp_path):
    kayit = tmp_path / "stop.jsonl"
    session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.STOP, kayit),
        _kanca(tmp_path, HookEvent.STOP, _STOP_BLOK),
    )
    provider = ScriptedProvider([*_yaz("a.txt"), model_result("yine")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(runtime={"agent_max_steps": 1}),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, _Kaydeden()),
        tool_context=ToolContext(root=tmp_path),
        hooks=session,
    )
    outcome = await run_agent("iş", deps)
    assert outcome.budget_stopped and _satirlar(kayit) == []


async def test_dosyadaki_disable_all_hooks_oturumda_bir_kez_bildirilir(monkeypatch, tmp_path):
    kapali = HookSet(
        (_kanca(tmp_path, HookEvent.STOP, "sys.exit(2)\n"),),
        disabled_reason="disableAllHooks (proje: .claude/settings.json)",
    )
    session = HookSession(root=tmp_path, loader=lambda: kapali)
    _, _, _, sink = await _tur(monkeypatch, tmp_path, [model_result("bir")], session)
    _, _, _, ikinci = await _tur(monkeypatch, tmp_path, [model_result("iki")], session)
    notlar = [e.text for e in [*sink.events, *ikinci.events] if isinstance(e, NarrationPublished)]
    assert [n for n in notlar if "Kancalar bu oturumda kapalı" in n] == [
        "Kancalar bu oturumda kapalı: disableAllHooks (proje: .claude/settings.json)"
    ]


async def test_yuk_claude_transcript_path_ve_tool_use_id_tasir(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    okuyan = (
        "satirlar = [json.loads(s) for s in open(data['transcript_path'], encoding='utf-8')]\n"
        f"open({str(kayit)!r}, 'a', encoding='utf-8').write("
        "json.dumps({'olay': data['hook_event_name'], 'id': data.get('tool_use_id'),"
        " 'satirlar': satirlar}) + '\\n')\n"
    )
    session = HookSession(
        root=tmp_path,
        loader=lambda: HookSet(
            (
                _kanca(tmp_path, HookEvent.PRE_TOOL_USE, okuyan),
                _kanca(tmp_path, HookEvent.POST_TOOL_USE, okuyan),
                _kanca(tmp_path, HookEvent.STOP, okuyan),
            )
        ),
        transcript_dir=tmp_path / "dokum",
    )
    await _tur(monkeypatch, tmp_path, _yaz("a.txt", "x", "bitti"), session, task="dosya yaz")
    pre, post, stop = _satirlar(kayit)
    assert (pre["olay"], pre["id"]) == ("PreToolUse", "call_write_file")
    assert post["id"] == "call_write_file" and stop["id"] is None
    son = stop["satirlar"][-1]
    assert son["type"] == "assistant"
    assert son["message"]["content"][0]["text"].endswith("bitti")
    assert stop["satirlar"][0]["message"]["content"][0]["text"] == "dosya yaz"
    await session.end("other")
    # Claude dökümü gibi kalıcı: oturum bitince silinmez (#129).
    assert list((tmp_path / "dokum").glob("*.jsonl"))


async def test_tur_basinda_eklenen_notification_kancasi_ayni_turda_calisir(monkeypatch, tmp_path):
    _yavas_soru(monkeypatch)
    kayit = tmp_path / "bildirim.jsonl"
    tanimlar: list[HookCommand] = []
    session = HookSession(root=tmp_path, loader=lambda: HookSet(tuple(tanimlar)))
    session.refresh()  # önceki tur: hiç kanca yok
    tanimlar.append(_kayit_kancasi(tmp_path, HookEvent.NOTIFICATION, kayit, "permission_prompt"))
    _, _, prompter, _ = await _tur(
        monkeypatch, tmp_path, _yaz("a.txt"), session, mod=ApprovalMode.SECURITY
    )
    assert prompter.soruldu == ["write_file"]
    assert [s["notification_type"] for s in _satirlar(kayit)] == ["permission_prompt"]


# --- Uçtan uca kapatma anahtarları ve updatedInput kök dışı ----------------------- #

_DENY = (
    "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
    " 'permissionDecision': 'deny',"
    " 'permissionDecisionReason': 'yasak'}}))\n"
)


def _dosyali_oturum(tmp_path: Path, monkeypatch, *, user_file: Path, **runtime) -> HookSession:
    """Gerçek katman dosyalarından yüklenen oturum (ev ve yapılandırma dizini geçici)."""
    from fusion_cli.engines.hooks.session import open_hook_session

    script = tmp_path / "deny.py"
    script.write_text("import json, sys\njson.load(sys.stdin)\n" + _DENY, encoding="utf-8")
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": command}]}]}}
        ),
        encoding="utf-8",
    )
    return open_hook_session(tmp_path, make_config(runtime=runtime), home=tmp_path / "ev")


@pytest.mark.parametrize(
    ("runtime", "kaynak", "yazildi"),
    [
        ({}, "fusion", False),
        ({"hooks_enabled": False}, "fusion", True),
        ({}, "claude", False),  # Claude gibi kullanıcı kancaları varsayılan açık (#95)
        ({"claude_hooks": False}, "claude", True),
        ({"claude_hooks": True}, "claude", False),
    ],
)
async def test_kapatma_anahtarlari_uctan_uca_tur(monkeypatch, tmp_path, runtime, kaynak, yazildi):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "ev" / ".config"))
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    from fusion_cli.config.hooks import user_hooks_file

    user_file = (
        user_hooks_file() if kaynak == "fusion" else tmp_path / "ev" / ".claude" / "settings.json"
    )
    session = _dosyali_oturum(tmp_path, monkeypatch, user_file=user_file, **runtime)
    await _tur(monkeypatch, tmp_path, _yaz("a.txt"), session)
    assert (tmp_path / "a.txt").exists() is yazildi


async def test_updated_input_kok_disina_yonlendirirse_onay_ve_engel_yeni_hedefe_bakar(
    monkeypatch, tmp_path
):
    proje = tmp_path / "proje"
    proje.mkdir()
    dis = tmp_path / "dis.txt"
    # Claude: updatedInput girdinin TAMAMINI değiştirir; değişmeyen alanlar da yazılır (#101).
    cikti = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"file_path": str(dis), "content": "x"},
        }
    }
    yonlendiren = f"print(json.dumps({cikti!r}))\n"
    session = _oturum(proje, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, yonlendiren))
    _, _, prompter, _ = await _tur(monkeypatch, proje, _yaz("ic.txt"), session)
    assert prompter.soruldu == ["write_file"]  # Otomatik kip kök dışı yazmayı sorar

    dis.unlink(missing_ok=True)
    engel = PermissionRuleSet(block_writes_outside_root=True)
    _, _, prompter, _ = await _tur(monkeypatch, proje, _yaz("ic.txt"), session, rules=engel)
    assert not dis.exists() and not (proje / "ic.txt").exists()
