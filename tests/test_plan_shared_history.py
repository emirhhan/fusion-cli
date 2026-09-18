"""Plan adımları tek konuşma geçmişini paylaşır; geri alma görünür olur.

Ölçüldü ("gizli kelime" vakası): her plan adımı kendi taze geçmişiyle
çalışıyordu. Kullanıcının kök turda söylediği bir kısıt (gizli kelime, tercih)
ikinci adıma hiç ulaşmıyordu — adımlar aynı konuşmanın parçası değil, ayrı ayrı
turlar gibi davranıyordu. Bu dosya adımların artık PAYLAŞILAN bir konuşma
geçmişi taşıdığını ve düşen bir denemenin geri aldığı dosyaların kullanıcıya
(duraklama metni) ve modele (geçmiş notu) açıkça bildirildiğini kilitler (A4,
A9, D4).
"""

from __future__ import annotations

from fusion_cli.core.execution_plan import ExecutionPlan, RetrySafety
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import plan_context, plan_runner
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from tests.test_plan_runner import _FakeDeps, _step


async def test_plan_adimi_onceki_sohbeti_gorur(tmp_path):
    """Kök turda söylenen bir şey (gizli kelime) HER adıma ulaşmalı."""
    conversation = [
        Message("system", "sistem talimatı"),
        Message("user", "gizli kelime: MAVİ-KEDİ"),
    ]
    plan = ExecutionPlan(
        plan_id="p",
        task="iş",
        steps=(_step("inspect"), _step("patch", depends_on=("inspect",))),
    )
    histories: list[list[Message] | None] = []

    async def agent(task, deps, **kwargs):
        del task, deps
        history = kwargs.get("history")
        histories.append(list(history) if history is not None else None)
        return AgentOutcome(
            final_text="tamam",
            messages=[*(history or []), Message("assistant", "tamam")],
            model_calls_made=1,
        )

    await run_execution_plan(
        "iş",
        _FakeDeps(ToolContext(root=tmp_path)),
        agent,
        plan=plan,
        conversation=conversation,
    )

    assert len(histories) == 2
    for history in histories:
        assert history is not None
        assert any("MAVİ-KEDİ" in message.content for message in history)


async def test_ikinci_adim_birinci_adimin_mesajlarini_gorur(tmp_path):
    plan = ExecutionPlan(
        plan_id="p",
        task="iş",
        steps=(_step("inspect"), _step("patch", depends_on=("inspect",))),
    )
    histories: list[list[Message]] = []

    async def agent(task, deps, **kwargs):
        del task, deps
        history = list(kwargs.get("history") or [])
        histories.append(history)
        arac = Message("tool", "arac ciktisi", tool_call_id="t1", name="read_file")
        asistan = Message("assistant", f"{len(histories)}. adım bitti")
        return AgentOutcome(
            final_text=asistan.content,
            messages=[*history, arac, asistan],
            model_calls_made=1,
        )

    await run_execution_plan("iş", _FakeDeps(ToolContext(root=tmp_path)), agent, plan=plan)

    assert len(histories) == 2
    ikinci_gecmis = histories[1]
    assert any(message.content == "1. adım bitti" for message in ikinci_gecmis)
    assert any(message.content == "arac ciktisi" for message in ikinci_gecmis)


async def test_plan_sonucu_gecmisi_kok_konusmayla_baslar_ve_tek_sistem_mesaji_tasir(tmp_path):
    conversation = [Message("system", "sistem talimatı"), Message("user", "kök görev")]
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(_step("inspect"),))

    async def agent(task, deps, **kwargs):
        del task, deps
        history = list(kwargs.get("history") or [])
        return AgentOutcome(
            final_text="bitti",
            messages=[*history, Message("assistant", "bitti")],
            model_calls_made=1,
        )

    result = await run_execution_plan(
        "iş",
        _FakeDeps(ToolContext(root=tmp_path)),
        agent,
        plan=plan,
        conversation=conversation,
    )

    assert result.messages[: len(conversation)] == conversation
    assert sum(1 for message in result.messages if message.role == "system") == 1


async def test_plan_uretimi_sohbet_gecmisini_gorur(tmp_path):
    conversation = [Message("system", "sistem talimatı"), Message("user", "gizli kelime: MOR-FARE")]
    histories: list[list[Message] | None] = []

    async def agent(task, deps, **kwargs):
        del task, deps
        histories.append(kwargs.get("history"))
        return AgentOutcome(final_text="{bozuk", messages=[])

    await run_execution_plan(
        "iş", _FakeDeps(ToolContext(root=tmp_path)), agent, conversation=conversation
    )

    assert histories
    assert all(history == conversation for history in histories)


async def test_dusen_adimin_geri_alinan_dosyalari_duraklama_metninde_ve_gecmiste_bildirilir(
    tmp_path,
):
    """A9: geri alma sessiz kalırsa kullanıcı dosyanın neden kaybolduğunu bilemez."""
    from dataclasses import replace

    step = replace(
        _step("write-both", expected_effects=("file:missing.png",)),
        retry_safety=RetrySafety.NEVER,
    )
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(step,))

    async def agent(task, deps, **kwargs):
        del task, kwargs
        a = deps.tool_context.root / "a.py"
        b = deps.tool_context.root / "b.py"
        deps.tool_context.changes.record_created(a)
        deps.tool_context.changes.record_created(b)
        a.write_text("a")
        b.write_text("b")
        deps.tool_context.touched.add(a)
        deps.tool_context.touched.add(b)
        return AgentOutcome(
            final_text="denedim", messages=[Message("assistant", "denedim")], model_calls_made=1
        )

    result = await run_execution_plan(
        "iş", _FakeDeps(ToolContext(root=tmp_path)), agent, plan=plan
    )

    assert not result.ok
    assert "Geri alınan değişiklikler: a.py, b.py" in result.final_text
    assert not (tmp_path / "a.py").exists()
    assert not (tmp_path / "b.py").exists()
    assert any(
        message.role == "user" and "[Fusion] Şu değişiklikler geri alındı" in message.content
        for message in result.messages
    )


async def test_butce_durdurmasinda_plan_kurtarma_yapmadan_duraklar(tmp_path, monkeypatch):
    """G2'nin USER_DENIED'ı bu yoldan geçer: kör kurtarma denenmez, doğrudan duraklar."""

    def choose_recovery_patlar(*args, **kwargs):
        raise AssertionError("choose_recovery çağrılmamalıydı: bütçe zaten durmuştu")

    async def replan_patlar(self, *args, **kwargs):
        raise AssertionError("replan_failed_step çağrılmamalıydı: bütçe zaten durmuştu")

    monkeypatch.setattr(plan_runner, "choose_recovery", choose_recovery_patlar)
    monkeypatch.setattr(plan_runner._PlanRun, "replan_failed_step", replan_patlar)

    class _DurdurulmusButce:
        stop = "user_denied"

        def record_progress(self):
            pass

    step = _step("inspect", expected_effects=("file:missing.png",))
    plan = ExecutionPlan(plan_id="p", task="iş", steps=(step,))

    async def agent(task, deps, **kwargs):
        del task, deps, kwargs
        return AgentOutcome(final_text="denedim", messages=[], model_calls_made=1)

    result = await run_execution_plan(
        "iş",
        _FakeDeps(ToolContext(root=tmp_path), budget=_DurdurulmusButce()),
        agent,
        plan=plan,
    )

    assert not result.ok
    assert "duraklat" in result.final_text.lower()


def test_adim_istemi_rapor_sablonu_istemez():
    """D4: adım istemi kanıt raporu şablonu değil, tek cümlelik özet ister."""
    metin = plan_context.step_prompt(_step("inspect"), {})

    assert "gözlediğin kanıtı" not in metin
    assert "Adım bitince tek cümleyle ne yaptığını söyle." in metin
