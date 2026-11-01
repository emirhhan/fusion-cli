"""`MessageDisplay` kancası (#90): görünen asistan metni satır partileriyle dönüştürülür.

Claude Code: `hookSpecificOutput.displayContent` yalnız ekrandaki metni değiştirir; döküm ve
modelin bağlamı değişmez. Girdi `turn_id`, `message_id`, `index`, `final`, `delta`.
"""

from __future__ import annotations

from fusion_cli.core import display_filter
from fusion_cli.core.events import TokenReceived, TurnAnswered
from fusion_cli.core.hooks.events import HookEvent
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.hooks.message_display import MessageDisplayStream, display_opener
from fusion_cli.engines.hooks.notify import notifying
from fusion_cli.providers.eventing import EventingProvider

from .fakes import RecordingSink, ScriptedProvider, make_config, model_result
from .test_hooks_loop import _kanca, _Kaydeden, _oturum, _Publisher, _satirlar

_BUYUT = (
    "open({kayit!r}, 'a').write(json.dumps(data) + '\\n')\n"
    "print(json.dumps({{'hookSpecificOutput': {{'hookEventName': 'MessageDisplay',"
    " 'displayContent': data['delta'].upper()}}}}))\n"
)


def _buyuten(tmp_path):
    kayit = tmp_path / "md.jsonl"
    return _kanca(tmp_path, HookEvent.MESSAGE_DISPLAY, _BUYUT.format(kayit=str(kayit))), kayit


async def test_satir_partileri_kancadan_gecer_girdi_alanlari_claude_ile_ayni(tmp_path):
    hook, kayit = _buyuten(tmp_path)
    akis = MessageDisplayStream(_oturum(tmp_path, hook), "tur-1", "msg-1")
    assert await akis.feed("merha", False) == []
    assert await akis.feed("ba\ndün", False) == [("MERHABA\n", False)]
    assert await akis.finish() == [("DÜN", False)]
    satirlar = _satirlar(kayit)
    assert [(s["index"], s["final"], s["delta"]) for s in satirlar] == [
        (0, False, "merhaba\n"),
        (1, True, "dün"),
    ]
    assert {s["turn_id"] for s in satirlar} == {"tur-1"}
    assert {s["message_id"] for s in satirlar} == {"msg-1"}
    assert {s["hook_event_name"] for s in satirlar} == {"MessageDisplay"}


async def test_bos_display_content_partiyi_gizler_alan_yoksa_aynen_kalir(tmp_path):
    gizle = _kanca(
        tmp_path,
        HookEvent.MESSAGE_DISPLAY,
        "if 'gizli' in data['delta']:\n"
        "    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'MessageDisplay',"
        " 'displayContent': ''}}))\n",
    )
    akis = MessageDisplayStream(_oturum(tmp_path, gizle), "t", "m")
    assert await akis.feed("gizli satır\nacik satır\n", False) == []
    akis = MessageDisplayStream(_oturum(tmp_path, gizle), "t", "m")
    assert await akis.feed("acik satır\n", False) == [("acik satır\n", False)]


async def test_eventing_saglayici_kurulu_suzgecle_tokenlari_donusturur(tmp_path):
    hook, _ = _buyuten(tmp_path)
    sink = RecordingSink()
    saglayici = EventingProvider(
        ScriptedProvider([model_result("bir\niki")]), publisher=_Publisher(sink), role="agent"
    )
    token = display_filter.install(display_opener(_oturum(tmp_path, hook), "t"))
    try:
        async for _ in saglayici.stream(_istek()):
            pass
    finally:
        display_filter.reset(token)
    metin = "".join(e.text for e in sink.events if isinstance(e, TokenReceived))
    assert metin == "BIR\nIKI"


def _istek():
    from fusion_cli.core.types import CompletionRequest, Message

    return CompletionRequest(
        messages=(Message("user", "x"),), temperature=0.0, max_tokens=10, timeout_s=5.0
    )


async def _tur(monkeypatch, tmp_path, session, *, interactive):
    sink = RecordingSink()
    provider = ScriptedProvider([model_result("cevap satırı\nson")])
    monkeypatch.setattr(
        agent_loop,
        "build_provider",
        lambda spec, **kwargs: EventingProvider(
            provider, publisher=kwargs["publisher"], role="agent", channel=kwargs["channel"]
        ),
    )
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, notifying(_Kaydeden(), session)),
        tool_context=ToolContext(root=tmp_path),
        hooks=session,
    )
    deps.interactive = interactive
    outcome = await run_agent("iş", deps)
    return outcome, sink


def _gorunen(sink) -> str:
    return "".join(e.text for e in sink.events if isinstance(e, (TokenReceived, TurnAnswered)))


async def test_etkilesimli_turda_gorunen_metin_degisir_kayit_degismez(monkeypatch, tmp_path):
    hook, _ = _buyuten(tmp_path)
    outcome, sink = await _tur(monkeypatch, tmp_path, _oturum(tmp_path, hook), interactive=True)
    assert "CEVAP SATIRI" in _gorunen(sink)
    assert "cevap satırı" not in _gorunen(sink)
    # Model bağlamı ve sohbet kaydı özgün metni taşır.
    assert "cevap satırı" in outcome.final_text
    assert any("cevap satırı" in (m.content or "") for m in outcome.messages)


async def test_etkilesimsiz_kosuda_metin_suzulmez(monkeypatch, tmp_path):
    hook, kayit = _buyuten(tmp_path)
    _, sink = await _tur(monkeypatch, tmp_path, _oturum(tmp_path, hook), interactive=False)
    assert "cevap satırı" in _gorunen(sink)
    assert _satirlar(kayit) == []
