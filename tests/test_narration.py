"""Claude gibi konuşma: işe başlamadan giriş paragrafı ve adımlar arasında ara anlatım.

Ölçüldü (30 Eylül, masaüstü): nemotron çırak araç çağırırken hiç metin yazmıyordu;
sohbette yalnız alt alta adım satırları görünüyordu, kullanıcı ne anlaşıldığını ve
neye geçildiğini hiç okumuyordu.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from fusion_cli.core.events import NarrationPublished, ToolStarted
from fusion_cli.core.tools import TodoItem, TodoStatus, ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.agent.narration import todo_transitions
from fusion_cli.providers.web_browser import WebBrowserError

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self.sink = sink

    def publish(self, event: object) -> None:
        self.sink.handle(event)


def _deps(tmp_path):
    sink = RecordingSink()
    deps = AgentDeps(
        config=make_config(
            agent=ModelSpec(name="cirak", model="nvidia_nim/cirak"), task_model_map={}
        ),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    return deps, sink


def _patch(monkeypatch, provider):
    from fusion_cli.engines.agent import loop, narration

    monkeypatch.setattr(loop, "build_provider", lambda _spec, **_kwargs: provider)
    monkeypatch.setattr(narration, "build_provider", lambda _spec, **_kwargs: provider)


@pytest.mark.parametrize("instruction", ["Son yanıtın yalnız JSON olsun.", "Yalnız sonucu yaz."])
async def test_explicit_compact_reply_does_not_start_cosmetic_model_call(monkeypatch, instruction):
    from fusion_cli.engines.agent import narration

    def forbidden_call(*args, **kwargs):
        pytest.fail("A strict-format task must not spend a call on unsolicited prose")

    monkeypatch.setattr(narration, "build_provider", forbidden_call)
    config = make_config()
    result = await narration.intro_paragraph(
        "result.txt dosyasını oluştur. " + instruction, config.agent, config, None
    )
    assert result == ""


def test_yeni_adima_gecis_ara_anlatim_uretir() -> None:
    once = (
        TodoItem("Dosyayı oku", TodoStatus.COMPLETED),
        TodoItem("Testi yaz", TodoStatus.PENDING),
    )
    sonra = (
        TodoItem("Dosyayı oku", TodoStatus.COMPLETED),
        TodoItem("Testi yaz", TodoStatus.IN_PROGRESS),
    )

    assert todo_transitions(once, sonra) == ("Şimdi “Testi yaz” adımına geçiyorum.",)
    assert todo_transitions(sonra, sonra) == ()


async def test_karmasik_iste_once_giris_paragrafi_yazilir(monkeypatch, tmp_path) -> None:
    deps, sink = _deps(tmp_path)
    provider = ScriptedProvider(
        [
            model_result(
                "İsteği şöyle anladım: yeni bir modül ekleyeceğim. "
                "Önce yapıyı okuyup sonra yazacağım."
            ),
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result("Modül eklendi."),
        ]
    )
    _patch(monkeypatch, provider)

    await run_agent("a.py dosyasını oluştur ve içine x değişkenini yaz", deps)

    anlatim = [event.text for event in sink.events if isinstance(event, NarrationPublished)]
    assert anlatim and anlatim[0].startswith("İsteği şöyle anladım")
    # Giriş, işi yapan ilk çağrıdan önce gelir ve araçsız istenir.
    assert provider.seen_requests[0] == []
    # Ama hangi araçların gerçekten var olduğunu bilir: olmayan eklentiyi vaat etmez.
    giris_istemi = provider.seen_messages[0][0].content
    assert "write_file" in giris_istemi and "listede olmayan" in giris_istemi


async def test_basit_sohbette_giris_paragrafi_istenmez(monkeypatch, tmp_path) -> None:
    deps, sink = _deps(tmp_path)
    provider = ScriptedProvider([model_result("Merhaba!")])
    _patch(monkeypatch, provider)

    await run_agent("Merhaba", deps)

    assert provider.calls == 1
    assert not any(isinstance(event, NarrationPublished) for event in sink.events)


@pytest.mark.parametrize("approved", [True, False])
async def test_atomic_cancel_probe_skips_intro_and_preserves_shell_approval(
    monkeypatch, tmp_path, approved
):
    from fusion_cli.config.permission_rules import (
        PermissionDecision,
        PermissionRule,
        PermissionRuleSet,
    )
    from fusion_cli.engines.agent import narration

    deps, sink = _deps(tmp_path)
    approvals = []

    class ShellApproval:
        async def confirm(self, request):
            approvals.append(request)
            return approved

    deps.policy = build_policy(ApprovalMode.SECURITY, ShellApproval())
    deps.permission_rules = PermissionRuleSet(
        (PermissionRule("Bash", None, PermissionDecision.ASK),)
    )
    actor = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("run_shell", command="sleep 0"),)),
            model_result("Komut sonucu incelendi."),
        ]
    )
    _patch(monkeypatch, actor)

    def forbidden_intro(*args, **kwargs):
        pytest.fail("An atomic command must reach the actor without a cosmetic model call")

    monkeypatch.setattr(narration, "build_provider", forbidden_intro)
    outcome = await run_agent(
        "İptal düğmesini test etmek için terminalde sleep 30 komutunu çalıştır. Dosya değiştirme.",
        deps,
    )

    assert outcome.ok
    assert actor.calls == (2 if approved else 1)
    assert len(approvals) == 1
    started = [event for event in sink.events if isinstance(event, ToolStarted)]
    assert [event.name for event in started] == (["run_shell"] if approved else [])
    assert not any(isinstance(event, NarrationPublished) for event in sink.events)
    assert all(
        "Kullanıcıya şu girişi zaten yazdın" not in message.content
        for messages in actor.seen_messages
        for message in messages
    )


async def test_intro_requests_no_thinking_without_changing_actor_reasoning(monkeypatch, tmp_path):
    from fusion_cli.engines.agent import narration

    deps, sink = _deps(tmp_path)
    requests = []

    class CapturingProvider(ScriptedProvider):
        def _next(self, request):
            requests.append(request)
            return super()._next(request)

    provider = CapturingProvider(
        [
            model_result("Önce dosyayı okuyorum, ardından değişikliği uygulayacağım."),
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result("Modül eklendi."),
        ]
    )
    _patch(monkeypatch, provider)
    outcome = await run_agent("a.py dosyasını oluştur ve içine x değişkenini yaz", deps)

    assert outcome.ok and (tmp_path / "a.py").read_text() == "x = 1\n"
    assert any(isinstance(event, NarrationPublished) for event in sink.events)
    assert requests[0].disable_thinking is True
    assert requests[0].tools == ()
    assert requests[0].max_tokens == narration.INTRO_MAX_TOKENS
    assert requests[0].timeout_s == narration.INTRO_TIMEOUT_S
    assert requests[0].max_retries == 0
    assert all(not request.disable_thinking for request in requests[1:])


async def test_atomic_file_read_reaches_tools_without_intro(monkeypatch, tmp_path):
    from fusion_cli.engines.agent import narration

    deps, sink = _deps(tmp_path)
    (tmp_path / "test.txt").write_text("Tek test geçti.")
    actor = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("read_file", path="test.txt"),)),
            model_result("Tek test geçti."),
        ]
    )
    _patch(monkeypatch, actor)

    def forbidden_intro(*args, **kwargs):
        pytest.fail("A single file read must not wait for cosmetic prose")

    monkeypatch.setattr(narration, "build_provider", forbidden_intro)
    outcome = await run_agent("test.txt dosyasını oku. Dosya değiştirme.", deps)

    assert outcome.ok
    assert actor.calls == 2
    assert any(
        isinstance(event, ToolStarted) and event.name == "read_file" for event in sink.events
    )
    assert not any(isinstance(event, NarrationPublished) for event in sink.events)


async def test_intro_does_not_swallow_parent_cancellation(monkeypatch, tmp_path):
    from fusion_cli.engines.agent import narration

    deps, _sink = _deps(tmp_path)
    entered = asyncio.Event()

    class WaitingProvider:
        async def complete(self, request):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(narration, "build_provider", lambda *args, **kwargs: WaitingProvider())
    running = asyncio.create_task(
        narration.intro_paragraph("Bir modül ekle.", deps.config.agent, deps.config, None)
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running


@pytest.mark.parametrize("mode", ["chat_mode", "internal", "plan_mode"])
async def test_complex_task_modes_do_not_start_cosmetic_intro(monkeypatch, tmp_path, mode):
    from fusion_cli.engines.agent import narration

    deps, sink = _deps(tmp_path)
    actor = ScriptedProvider([model_result("Dosya ekleme talebini inceledim.")])
    _patch(monkeypatch, actor)

    def forbidden_intro(*args, **kwargs):
        pytest.fail("Chat, internal and plan turns must not request cosmetic intros")

    monkeypatch.setattr(narration, "build_provider", forbidden_intro)
    await run_agent(
        "a.py dosyasını oluştur ve içine x değişkenini yaz",
        deps,
        **{mode: True},
        self_review=False,
        verify=False,
    )

    assert actor.calls >= 1
    assert not any(isinstance(event, NarrationPublished) for event in sink.events)


async def test_web_execution_does_not_start_cosmetic_intro(monkeypatch, tmp_path):
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    deps, sink = _deps(tmp_path)
    messages = []

    async def forbidden_intro(*args, **kwargs):
        pytest.fail("Web execution must not add a cosmetic model call")

    monkeypatch.setattr(loop, "intro_paragraph", forbidden_intro)
    await loop._publish_intro(
        "a.py dosyasını oluştur ve içine x değişkenini yaz",
        messages,
        deps,
        ExecutionPolicy(is_web=True, complex_task=True),
        ("write_file",),
    )

    assert messages == []
    assert not any(isinstance(event, NarrationPublished) for event in sink.events)


async def test_giris_saglayicisi_kurulamazsa_ana_tur_surer(monkeypatch, tmp_path) -> None:
    """Yardımcı giriş çağrısı kurulamazsa dosya yazma turu yine çalışır."""
    from fusion_cli.engines.agent import narration

    deps, _sink = _deps(tmp_path)
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result("Modül eklendi."),
        ]
    )
    _patch(monkeypatch, provider)

    def giris_kurulamaz(_spec, **_kwargs):
        raise WebBrowserError("test sağlayıcısı kurulamadı")

    monkeypatch.setattr(narration, "build_provider", giris_kurulamaz)
    sonuc = await run_agent("a.py dosyasını oluştur ve içine x değişkenini yaz", deps)

    assert sonuc.ok
    assert (tmp_path / "a.py").read_text() == "x = 1\n"


async def test_giris_paragrafi_ogretmen_ve_platform_isinden_once_gelir(
    monkeypatch, tmp_path
) -> None:
    """Kullanıcı ilk yanıtı öğretmen beklenirken de görür."""
    from fusion_cli.engines.agent import loop

    deps, _sink = _deps(tmp_path)
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result("Modül eklendi."),
        ]
    )
    _patch(monkeypatch, provider)
    sira: list[str] = []

    async def giris(*_args, **_kwargs):
        sira.append("giris")
        return "İsteğini aldım; dosyayı ekleyip doğrulayacağım."

    async def ogretmen(*_args):
        sira.append("ogretmen")

    async def platform(*_args):
        sira.append("platform")

    monkeypatch.setattr(loop, "intro_paragraph", giris)
    monkeypatch.setattr(loop, "prepare_teacher_plan", ogretmen)
    monkeypatch.setattr(loop, "run_platform_check", platform)

    await run_agent("a.py dosyasını oluştur ve içine x değişkenini yaz", deps)

    assert sira[:3] == ["giris", "ogretmen", "platform"]


@pytest.mark.parametrize(
    "text",
    [
        "Önce dosyayı yazıyorum.\n"
        '{"tool": "write_file", "path": "index.html", "content": "<!DOCTYPE',
        'Önce dosyayı yazıyorum. {"name": "write_file", "arguments": {"path":',
        'FUSION_TOOL_CALL\n{"name": "write_file", "arguments": {',
        'Önce dosyayı yazıyorum.\nFUSION_TOOL_PAYLOAD id="x"\n<html>',
        "Önce dosyayı yazıyorum.\n```html\n<!DOCTYPE html>",
        "Önce dosyayı yazıyorum.\n<html><body>Sayaç</body></html>",
        'Önce dosyayı yazıyorum.\n<tool_call>{"name": "write_file"}</tool_call>',
        'Önce dosyayı yazıyorum.\nwrite_file(path="a.py", content="x = 1")',
        "# Plan\nDosyayı yazıyorum.",
        "Önce dosyayı yazıyorum.\n- Sonra test ediyorum.",
    ],
)
async def test_cosmetic_intro_rejects_tool_or_code_payload_without_retry(
    tmp_path, monkeypatch, text
):
    from fusion_cli.engines.agent.narration import intro_paragraph

    deps, _sink = _deps(tmp_path)
    provider = ScriptedProvider([model_result(text)])
    _patch(monkeypatch, provider)

    intro = await intro_paragraph(
        "Bir sayaç oluştur.", deps.config.agent, deps.config, None, ("write_file",)
    )

    assert intro == ""
    assert provider.calls == 1


async def test_cosmetic_intro_rejects_native_tool_calls(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.narration import intro_paragraph

    deps, _sink = _deps(tmp_path)
    provider = ScriptedProvider(
        [model_result("Dosyayı yazıyorum.", tool_calls=(tool_call("write_file", path="a.py"),))]
    )
    _patch(monkeypatch, provider)

    assert await intro_paragraph("Bir dosya oluştur.", deps.config.agent, deps.config, None) == ""
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            model_result("Önce ilgili dosyayı okuyorum, ardından testi çalıştırıyorum."),
            "Önce ilgili dosyayı okuyorum, ardından testi çalıştırıyorum.",
        ),
        (
            model_result('<think>{"tool": "write_file"}</think>Önce testi okuyorum.'),
            "Önce testi okuyorum.",
        ),
        (
            replace(model_result("Önce testi okuyorum. Sonra düzelt"), truncated=True),
            "Önce testi okuyorum.",
        ),
        (replace(model_result('Önce testi okuyorum.\n{"tool": "write_file"'), truncated=True), ""),
    ],
)
async def test_plain_intro_and_truncation_preserve_only_valid_prose(
    tmp_path, monkeypatch, result, expected
):
    from fusion_cli.engines.agent.narration import intro_paragraph

    deps, _sink = _deps(tmp_path)
    provider = ScriptedProvider([result])
    _patch(monkeypatch, provider)

    assert await intro_paragraph("Testi düzelt.", deps.config.agent, deps.config, None) == expected
    assert provider.calls == 1


async def test_invalid_intro_is_not_published_or_reinjected_and_main_work_continues(
    tmp_path, monkeypatch
):
    deps, sink = _deps(tmp_path)
    payload = 'Önce dosyayı yazıyorum.\n{"tool": "write_file", "content": "<!DOCTYPE'
    provider = ScriptedProvider(
        [
            model_result(payload),
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result("Modül eklendi."),
        ]
    )
    _patch(monkeypatch, provider)

    outcome = await run_agent("a.py dosyasını oluştur ve içine x değişkenini yaz", deps)

    assert outcome.ok
    assert (tmp_path / "a.py").read_text() == "x = 1\n"
    assert provider.calls == 3
    assert not any(isinstance(event, NarrationPublished) for event in sink.events)
    assert all(
        payload not in message.content
        for request in provider.seen_messages[1:]
        for message in request
    )
