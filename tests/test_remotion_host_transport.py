"""Host taşımasının farklı oturum kurulumlarında kaybolmama regresyonları."""

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import verification

from .fakes import make_config


@pytest.mark.parametrize("branch", ["contract", "state", "context"])
def test_host_transport_reaches_every_verifier_branch(monkeypatch, tmp_path, branch):
    captured = []

    async def transport(request):
        raise AssertionError("Kurulum render başlatmamalı")

    class CapturingVerifier:
        def __init__(self, *args, **kwargs):
            captured.append(kwargs.get("transport"))

    monkeypatch.setattr(verification, "RemotionRuntimeVerifier", CapturingVerifier)
    monkeypatch.setattr(verification, "DeferredRemotionVerifier", CapturingVerifier)
    context = ToolContext(root=tmp_path)
    options = {"remotion_transport": transport}
    if branch == "contract":
        options["remotion_contract"] = object()
    elif branch == "state":
        options["remotion_state"] = context.remotion_contract
    config = make_config(
        runtime={
            "web_verification": branch == "context",
            "browser_verification": False,
            "visual_verification": False,
        }
    )
    verification.build_verifier(config, root=tmp_path, tool_context=context, **options)
    assert captured == [transport]


async def test_single_task_host_transport_is_forwarded(monkeypatch, tmp_path):
    from fusion_cli.cli import session
    from fusion_cli.engines.agent import AgentOutcome

    captured = []
    original = session.build_verifier

    async def transport(request):
        raise AssertionError("Generic görev gözlem başlatmamalı")

    def build(*args, **kwargs):
        captured.append(kwargs.get("remotion_transport"))
        return original(*args, **kwargs)

    async def run(task, deps, **kwargs):
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(session, "build_verifier", build)
    monkeypatch.setattr(session, "run_agent", run)
    config = make_config(
        memory_dir=tmp_path / "memory",
        source=tmp_path / "config.yaml",
        mcp_servers=(),
        runtime={
            "web_verification": False,
            "browser_verification": False,
            "visual_verification": False,
        },
    )
    await session.run_agent_task(
        "Generic",
        config,
        sinks=(),
        prompter_factory=lambda drain: None,
        root=tmp_path,
        interactive=False,
        remotion_transport=transport,
    )
    assert captured == [transport]


async def test_repl_agent_turn_keeps_host_transport(monkeypatch, tmp_path):
    from rich.console import Console

    from fusion_cli.cli.repl import loop
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.engines.agent import AgentOutcome
    from fusion_cli.memory.factory import null_memory

    from .test_repl import _SahteArkaPlan

    captured = []
    original = verification.build_verifier

    async def transport(request):
        raise AssertionError("Generic görev gözlem başlatmamalı")

    def build(*args, **kwargs):
        captured.append(kwargs.get("remotion_transport"))
        return original(*args, **kwargs)

    async def run(task, deps, **kwargs):
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(verification, "build_verifier", build)
    monkeypatch.setattr("fusion_cli.engines.agent.run_agent", run)
    config = make_config(
        memory_dir=tmp_path / "memory",
        source=tmp_path / "config.yaml",
        mcp_servers=(),
        runtime={
            "web_verification": False,
            "browser_verification": False,
            "visual_verification": False,
        },
    )
    state = ReplState(
        config, null_memory(), tmp_path, tmp_path / "home", remotion_transport=transport
    )
    await loop._agent_turn("Generic", state, Console(quiet=True), _SahteArkaPlan())
    assert captured == [transport]


async def test_repl_entry_injects_host_transport_into_tui_state(monkeypatch, tmp_path):
    from rich.console import Console

    from fusion_cli.cli.repl.loop import run_repl
    from fusion_cli.memory.factory import null_memory

    captured = []

    async def transport(request):
        raise AssertionError("Kurulum render başlatmamalı")

    async def tui(state, console):
        captured.append(state.remotion_transport)
        return 0

    monkeypatch.delenv("FUSION_INLINE", raising=False)
    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_tui_repl", tui)
    await run_repl(
        make_config(),
        memory=null_memory(),
        root=tmp_path,
        console=Console(quiet=True),
        remotion_transport=transport,
    )
    assert captured == [transport]
